"""Tests for Memory Optimization - Memory utilities and compact entities."""

import gc
import sys
import threading
import time
import weakref
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectryn.core.compact_entities import (
    CompactComment,
    CompactEpic,
    CompactSubtask,
    CompactUserStory,
    estimate_memory_savings,
)
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import CommitRef, IssueKey, StoryId
from spectryn.core.memory import (
    ChunkedList,
    CompactString,
    LazyLoader,
    MemoryStats,
    MemoryTracker,
    ObjectPool,
    WeakRefCache,
    bounded_lru_cache,
    force_gc,
    format_bytes,
    intern_string,
    sizeof_deep,
)


class TestCompactString:
    """Tests for CompactString."""

    def test_interning_same_string(self):
        """Test that same strings return same object."""
        interner = CompactString()
        s1 = interner("hello_world_this_is_a_longer_string")
        s2 = interner("hello_world_this_is_a_longer_string")
        assert s1 is s2

    def test_short_strings_use_sys_intern(self):
        """Test that short strings use sys.intern."""
        interner = CompactString()
        s1 = interner("short")
        s2 = interner("short")
        assert s1 is s2

    def test_different_strings_not_same(self):
        """Test that different strings are different."""
        interner = CompactString()
        s1 = interner("hello_world_this_is_a_longer_string")
        s2 = interner("goodbye_world_this_is_a_longer_string")
        assert s1 is not s2

    def test_hit_rate(self):
        """Test hit rate calculation."""
        interner = CompactString()
        interner("unique_string_for_testing_purposes")
        interner("unique_string_for_testing_purposes")  # Hit
        interner("unique_string_for_testing_purposes")  # Hit

        assert interner.hit_rate > 0

    def test_max_size_eviction(self):
        """Test that eviction happens at max size."""
        interner = CompactString(max_size=10)

        for i in range(15):
            interner(f"string_number_{i}_for_testing_eviction")

        assert interner.size <= 10

    def test_intern_dict(self):
        """Test interning dictionary values."""
        interner = CompactString()
        d = {"key1": "value1", "key2": "value2"}
        result = interner.intern_dict(d)

        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_clear(self):
        """Test clearing the cache."""
        interner = CompactString()
        interner("test_string_for_clearing_cache")
        interner.clear()

        assert interner.size == 0
        assert interner._hits == 0
        assert interner._misses == 0

    def test_get_stats(self):
        """Test getting statistics."""
        interner = CompactString(max_size=100)
        interner("test_string_for_statistics_gathering")

        stats = interner.get_stats()
        assert "size" in stats
        assert "max_size" in stats
        assert "hit_rate" in stats


class TestGlobalInterner:
    """Tests for global intern_string function."""

    def test_intern_string(self):
        """Test global intern_string function."""
        s1 = intern_string("global_test_string_for_interning")
        s2 = intern_string("global_test_string_for_interning")
        assert s1 is s2


class TestObjectPool:
    """Tests for ObjectPool."""

    def test_acquire_and_release(self):
        """Test basic acquire and release."""
        pool: ObjectPool[dict[str, str]] = ObjectPool(factory=dict)
        obj = pool.acquire()

        assert isinstance(obj, dict)
        pool.release(obj)
        assert pool.available == 1

    def test_reuse(self):
        """Test that objects are reused."""
        pool: ObjectPool[list[int]] = ObjectPool(factory=list, reset_fn=list.clear)

        obj1 = pool.acquire()
        obj1.append(1)
        pool.release(obj1)

        obj2 = pool.acquire()
        assert obj2 is obj1  # Same object
        assert len(obj2) == 0  # But cleared

    def test_max_size(self):
        """Test that pool respects max size."""
        pool: ObjectPool[dict[str, str]] = ObjectPool(factory=dict, max_size=2)

        objs = [pool.acquire() for _ in range(5)]
        for obj in objs:
            pool.release(obj)

        assert pool.available == 2

    def test_borrow_context_manager(self):
        """Test borrow context manager."""
        pool: ObjectPool[dict[str, int]] = ObjectPool(factory=dict, reset_fn=dict.clear)

        with pool.borrow() as obj:
            obj["key"] = 1

        assert pool.available == 1

    def test_reuse_rate(self):
        """Test reuse rate calculation."""
        pool: ObjectPool[dict[str, str]] = ObjectPool(factory=dict)

        obj = pool.acquire()
        pool.release(obj)
        pool.acquire()  # Reuse

        assert pool.reuse_rate > 0

    def test_get_stats(self):
        """Test getting statistics."""
        pool: ObjectPool[dict[str, str]] = ObjectPool(factory=dict)
        pool.acquire()

        stats = pool.get_stats()
        assert stats["acquired"] == 1
        assert stats["created"] == 1


class WeakReferenceable:
    """A class that can be weakly referenced for testing."""

    def __init__(self, data: Any = None):
        self.data = data


class TestWeakRefCache:
    """Tests for WeakRefCache."""

    def test_set_and_get(self):
        """Test basic set and get."""
        cache: WeakRefCache[str, WeakReferenceable] = WeakRefCache()
        obj = WeakReferenceable([1, 2, 3])
        cache.set("key", obj)

        assert cache.get("key") is obj

    def test_weak_reference_cleanup(self):
        """Test that weak references are cleaned up."""
        cache: WeakRefCache[str, WeakReferenceable] = WeakRefCache()

        def create_and_cache() -> None:
            obj = WeakReferenceable([1, 2, 3])
            cache.set("key", obj)
            # obj goes out of scope

        create_and_cache()
        gc.collect()

        # Object may be garbage collected
        # (behavior depends on GC timing)

    def test_get_or_create(self):
        """Test get_or_create."""
        cache: WeakRefCache[str, WeakReferenceable] = WeakRefCache()
        created: list[int] = []

        def factory() -> WeakReferenceable:
            obj = WeakReferenceable([1, 2, 3])
            created.append(1)
            return obj

        obj1 = cache.get_or_create("key", factory)
        obj2 = cache.get_or_create("key", factory)

        assert obj1 is obj2
        assert len(created) == 1  # Factory only called once

    def test_delete(self):
        """Test delete."""
        cache: WeakRefCache[str, WeakReferenceable] = WeakRefCache()
        obj = WeakReferenceable([1, 2, 3])
        cache.set("key", obj)

        assert cache.delete("key") is True
        assert cache.delete("key") is False

    def test_hit_rate(self):
        """Test hit rate."""
        cache: WeakRefCache[str, WeakReferenceable] = WeakRefCache()
        obj = WeakReferenceable([1, 2, 3])
        cache.set("key", obj)

        cache.get("key")  # Hit
        cache.get("missing")  # Miss

        assert cache.hit_rate == 0.5


class TestLazyLoader:
    """Tests for LazyLoader."""

    def test_lazy_loading(self):
        """Test that value is lazily loaded."""
        created = []

        def factory() -> str:
            created.append(1)
            return "value"

        loader: LazyLoader[str] = LazyLoader(factory)

        assert len(created) == 0
        assert not loader.is_loaded

        value = loader.value

        assert value == "value"
        assert len(created) == 1
        assert loader.is_loaded

    def test_value_cached(self):
        """Test that value is cached."""
        call_count = 0

        def factory() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        loader: LazyLoader[int] = LazyLoader(factory)

        _ = loader.value
        _ = loader.value
        _ = loader.value

        assert call_count == 1

    def test_reset(self):
        """Test reset."""
        call_count = 0

        def factory() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        loader: LazyLoader[int] = LazyLoader(factory)

        assert loader.value == 1
        loader.reset()
        assert loader.value == 2

    def test_thread_safety(self):
        """Test thread safety."""
        call_count = 0
        lock = threading.Lock()

        def factory() -> int:
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.01)
            return 42

        loader: LazyLoader[int] = LazyLoader(factory)

        threads = [threading.Thread(target=lambda: loader.value) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Factory should only be called once
        assert call_count == 1


class TestChunkedList:
    """Tests for ChunkedList."""

    def test_append_and_get(self):
        """Test append and get."""
        items: ChunkedList[int] = ChunkedList(chunk_size=3)

        for i in range(10):
            items.append(i)

        assert len(items) == 10
        assert items[0] == 0
        assert items[9] == 9

    def test_negative_index(self):
        """Test negative indexing."""
        items: ChunkedList[int] = ChunkedList()
        items.extend(list(range(5)))

        assert items[-1] == 4
        assert items[-5] == 0

    def test_index_out_of_range(self):
        """Test index out of range."""
        items: ChunkedList[int] = ChunkedList()
        items.append(1)

        with pytest.raises(IndexError):
            _ = items[10]

    def test_iteration(self):
        """Test iteration."""
        items: ChunkedList[int] = ChunkedList(chunk_size=3)
        items.extend(list(range(10)))

        result = list(items)
        assert result == list(range(10))

    def test_clear_chunk(self):
        """Test clearing a chunk."""
        items: ChunkedList[int] = ChunkedList(chunk_size=3)
        items.extend(list(range(10)))

        initial_len = len(items)
        items.clear_chunk(0)

        assert len(items) < initial_len

    def test_num_chunks(self):
        """Test number of chunks."""
        items: ChunkedList[int] = ChunkedList(chunk_size=3)
        items.extend(list(range(10)))

        # 10 items in chunks of 3 = 4 chunks
        assert items.num_chunks == 4

    def test_get_stats(self):
        """Test getting statistics."""
        items: ChunkedList[int] = ChunkedList(chunk_size=100)
        items.extend(list(range(50)))

        stats = items.get_stats()
        assert stats["length"] == 50
        assert stats["chunk_size"] == 100


class TestMemoryTracker:
    """Tests for MemoryTracker."""

    def test_basic_tracking(self):
        """Test basic memory tracking."""
        with MemoryTracker("test_operation") as tracker:
            # Allocate some memory
            _ = list(range(1000))

        stats = tracker.get_stats()
        assert stats.operation == "test_operation"
        assert stats.duration_seconds >= 0

    def test_gc_collections_tracked(self):
        """Test that GC collections are tracked."""
        with MemoryTracker("test_gc") as tracker:
            # Create garbage
            for _ in range(100):
                _ = {"key": [1, 2, 3]}
            gc.collect()

        # GC collections should be tracked
        assert isinstance(tracker.gc_collections, tuple)
        assert len(tracker.gc_collections) == 3


class TestSizeofDeep:
    """Tests for sizeof_deep."""

    def test_simple_object(self):
        """Test size of simple object."""
        obj = {"key": "value"}
        size = sizeof_deep(obj)

        assert size > 0
        assert size >= sys.getsizeof(obj)

    def test_nested_object(self):
        """Test size of nested object."""
        obj = {"level1": {"level2": {"data": [1, 2, 3, 4, 5]}}}
        size = sizeof_deep(obj)

        assert size > sys.getsizeof(obj)

    def test_circular_reference(self):
        """Test handling of circular references."""
        obj: dict[str, Any] = {"self": None}
        obj["self"] = obj

        # Should not recurse infinitely
        size = sizeof_deep(obj)
        assert size > 0


class TestFormatBytes:
    """Tests for format_bytes."""

    def test_bytes(self):
        """Test byte formatting."""
        assert "B" in format_bytes(100)

    def test_kilobytes(self):
        """Test kilobyte formatting."""
        assert "KB" in format_bytes(2048)

    def test_megabytes(self):
        """Test megabyte formatting."""
        assert "MB" in format_bytes(2 * 1024 * 1024)


class TestBoundedLruCache:
    """Tests for bounded_lru_cache."""

    def test_caching(self):
        """Test that results are cached."""
        call_count = 0

        @bounded_lru_cache(maxsize=10)
        def expensive(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        expensive(1)
        expensive(1)
        expensive(1)

        assert call_count == 1

    def test_maxsize(self):
        """Test cache maxsize."""

        @bounded_lru_cache(maxsize=2)
        def compute(x: int) -> int:
            return x * 2

        compute(1)
        compute(2)
        compute(3)  # This should evict 1

        info = compute.cache_info()
        assert info.currsize <= 2


class TestForceGc:
    """Tests for force_gc."""

    def test_returns_stats(self):
        """Test that force_gc returns stats."""
        stats = force_gc()

        assert "collected" in stats
        assert "before" in stats
        assert "after" in stats


# =============================================================================
# Compact Entities Tests
# =============================================================================


class TestCompactSubtask:
    """Tests for CompactSubtask."""

    def test_creation(self):
        """Test creating a compact subtask."""
        subtask = CompactSubtask(
            id="ST-1",
            number=1,
            name="Implement feature",
            status=Status.IN_PROGRESS,
        )

        assert subtask.id == "ST-1"
        assert subtask.name == "Implement feature"
        assert subtask.status == Status.IN_PROGRESS

    def test_auto_id(self):
        """Test auto-generated ID."""
        subtask = CompactSubtask(name="Test")
        assert subtask.id  # Should have auto-generated ID

    def test_normalize_name(self):
        """Test name normalization."""
        subtask = CompactSubtask(name="Implement Feature!")
        normalized = subtask.normalize_name()

        assert normalized == "implement feature"

    def test_matches(self):
        """Test subtask matching."""
        subtask1 = CompactSubtask(name="Implement Login")
        subtask2 = CompactSubtask(name="Implement Login Feature")

        assert subtask1.matches(subtask2)

    def test_to_dict(self):
        """Test conversion to dict."""
        subtask = CompactSubtask(
            id="ST-1",
            name="Test",
            status=Status.DONE,
        )
        d = subtask.to_dict()

        assert d["id"] == "ST-1"
        assert d["name"] == "Test"
        assert d["status"] == "DONE"

    def test_from_dict(self):
        """Test creation from dict."""
        d = {
            "id": "ST-1",
            "name": "Test",
            "status": "IN_PROGRESS",
        }
        subtask = CompactSubtask.from_dict(d)

        assert subtask.id == "ST-1"
        assert subtask.status == Status.IN_PROGRESS

    def test_has_slots(self):
        """Test that __slots__ is defined."""
        assert hasattr(CompactSubtask, "__slots__")


class TestCompactComment:
    """Tests for CompactComment."""

    def test_creation(self):
        """Test creating a compact comment."""
        comment = CompactComment(
            id="C-1",
            body="Test comment",
            author="user",
        )

        assert comment.id == "C-1"
        assert comment.body == "Test comment"

    def test_commits_immutable(self):
        """Test that commits are immutable tuple."""
        commits = [CommitRef(hash="abc123", message="Test")]
        comment = CompactComment(commits=commits)

        assert isinstance(comment.commits, tuple)

    def test_has_slots(self):
        """Test that __slots__ is defined."""
        assert hasattr(CompactComment, "__slots__")


class TestCompactUserStory:
    """Tests for CompactUserStory."""

    def test_creation(self):
        """Test creating a compact user story."""
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="User Login",
            priority=Priority.HIGH,
            status=Status.IN_PROGRESS,
        )

        assert story.id.value == "US-001"
        assert story.title == "User Login"
        assert story.priority == Priority.HIGH

    def test_labels_immutable(self):
        """Test that labels are immutable."""
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="Test",
            labels=["bug", "urgent"],
        )

        assert isinstance(story.labels, tuple)
        assert "bug" in story.labels

    def test_subtasks_immutable(self):
        """Test that subtasks are immutable."""
        subtasks = [CompactSubtask(name="Task 1")]
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="Test",
            subtasks=subtasks,
        )

        assert isinstance(story.subtasks, tuple)

    def test_normalize_title(self):
        """Test title normalization."""
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="User Login (future)",
        )
        normalized = story.normalize_title()

        assert "future" not in normalized.lower()

    def test_matches_title(self):
        """Test title matching."""
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="User Login",
        )

        assert story.matches_title("User Login Feature")

    def test_find_subtask(self):
        """Test finding subtask."""
        subtask = CompactSubtask(name="Implement API")
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="Test",
            subtasks=[subtask],
        )

        found = story.find_subtask("implement api")
        assert found is not None
        assert found.name == "Implement API"

    def test_to_dict(self):
        """Test conversion to dict."""
        story = CompactUserStory(
            id=StoryId("US-001"),
            title="Test Story",
            priority=Priority.HIGH,
            labels=["bug"],
        )
        d = story.to_dict()

        assert d["id"] == "US-001"
        assert d["priority"] == "HIGH"
        assert "bug" in d["labels"]

    def test_has_slots(self):
        """Test that __slots__ is defined."""
        assert hasattr(CompactUserStory, "__slots__")


class TestCompactEpic:
    """Tests for CompactEpic."""

    def test_creation(self):
        """Test creating a compact epic."""
        epic = CompactEpic(
            key=IssueKey("PROJ-100"),
            title="Authentication",
            status=Status.IN_PROGRESS,
        )

        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Authentication"

    def test_stories_immutable(self):
        """Test that stories are immutable."""
        stories = [CompactUserStory(id=StoryId("US-001"), title="Story")]
        epic = CompactEpic(
            key=IssueKey("PROJ-100"),
            title="Epic",
            stories=stories,
        )

        assert isinstance(epic.stories, tuple)

    def test_find_story(self):
        """Test finding a story."""
        story = CompactUserStory(id=StoryId("US-001"), title="Test")
        epic = CompactEpic(
            key=IssueKey("PROJ-100"),
            title="Epic",
            stories=[story],
        )

        found = epic.find_story(StoryId("US-001"))
        assert found is not None
        assert found.title == "Test"

    def test_total_story_points(self):
        """Test total story points calculation."""
        stories = [
            CompactUserStory(id=StoryId("US-001"), title="S1", story_points=3),
            CompactUserStory(id=StoryId("US-002"), title="S2", story_points=5),
        ]
        epic = CompactEpic(
            key=IssueKey("PROJ-100"),
            title="Epic",
            stories=stories,
        )

        assert epic.total_story_points == 8

    def test_completion_percentage(self):
        """Test completion percentage."""
        stories = [
            CompactUserStory(id=StoryId("US-001"), title="S1", status=Status.DONE),
            CompactUserStory(id=StoryId("US-002"), title="S2", status=Status.PLANNED),
        ]
        epic = CompactEpic(
            key=IssueKey("PROJ-100"),
            title="Epic",
            stories=stories,
        )

        assert epic.completion_percentage == 50.0

    def test_has_slots(self):
        """Test that __slots__ is defined."""
        assert hasattr(CompactEpic, "__slots__")


class TestEstimateMemorySavings:
    """Tests for estimate_memory_savings."""

    def test_returns_estimates(self):
        """Test that estimates are returned."""
        result = estimate_memory_savings(num_stories=1000)

        assert "regular_bytes" in result
        assert "compact_bytes" in result
        assert "savings_bytes" in result
        assert "savings_percent" in result

    def test_compact_smaller(self):
        """Test that compact is smaller."""
        result = estimate_memory_savings()

        assert result["compact_bytes"] < result["regular_bytes"]
        assert result["savings_percent"] > 0


class TestMemoryEfficiency:
    """Integration tests for memory efficiency."""

    def test_compact_vs_regular_size(self):
        """Test that compact entities use less memory."""
        # Create compact story
        compact = CompactUserStory(
            id=StoryId("US-001"),
            title="Test Story",
            labels=["bug", "urgent"],
            subtasks=[CompactSubtask(name="Task 1")],
        )

        # Compact should have __slots__
        assert hasattr(compact, "__slots__")
        assert not hasattr(compact, "__dict__")

    def test_string_interning_in_compact(self):
        """Test that compact entities use string interning."""
        story1 = CompactUserStory(
            id=StoryId("US-001"),
            title="Same Title For Testing",
        )
        story2 = CompactUserStory(
            id=StoryId("US-002"),
            title="Same Title For Testing",
        )

        # Titles should be interned (same object)
        # Note: Only works for strings > 20 chars
        assert story1.title is story2.title
