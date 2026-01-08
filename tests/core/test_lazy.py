"""Tests for lazy loading infrastructure."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from spectryn.core.lazy.cache import (
    CacheEntry,
    CacheStats,
    FieldCache,
    get_global_cache,
    set_global_cache,
)
from spectryn.core.lazy.collections import (
    LazyDict,
    LazyList,
    PaginatedCollection,
)
from spectryn.core.lazy.proxy import (
    LazyField,
    LazyLoadingConfig,
    LazyProxy,
    LazyStory,
)


class TestCacheStats:
    """Tests for CacheStats."""

    def test_default_values(self):
        """Test default statistics."""
        stats = CacheStats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.total_load_time_ms == 0.0

    def test_hit_rate(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=7, misses=3)

        assert stats.hit_rate == 0.7

    def test_hit_rate_zero_total(self):
        """Test hit rate with no operations."""
        stats = CacheStats()

        assert stats.hit_rate == 0.0

    def test_average_load_time(self):
        """Test average load time calculation."""
        stats = CacheStats(misses=5, total_load_time_ms=100.0)

        assert stats.average_load_time_ms == 20.0

    def test_record_hit(self):
        """Test recording a hit."""
        stats = CacheStats()
        stats.record_hit()

        assert stats.hits == 1

    def test_record_miss(self):
        """Test recording a miss."""
        stats = CacheStats()
        stats.record_miss(50.0)

        assert stats.misses == 1
        assert stats.total_load_time_ms == 50.0


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_default_values(self):
        """Test default entry values."""
        entry = CacheEntry(value="test")

        assert entry.value == "test"
        assert entry.ttl_seconds is None
        assert entry.is_expired is False

    def test_expiration(self):
        """Test entry expiration."""
        entry = CacheEntry(
            value="test",
            created_at=time.time() - 10,
            ttl_seconds=5,
        )

        assert entry.is_expired is True

    def test_not_expired(self):
        """Test entry not expired."""
        entry = CacheEntry(
            value="test",
            ttl_seconds=60,
        )

        assert entry.is_expired is False

    def test_touch_updates_access_time(self):
        """Test touch updates access time."""
        entry = CacheEntry(value="test")
        original_access = entry.accessed_at

        time.sleep(0.01)
        entry.touch()

        assert entry.accessed_at > original_access


class TestFieldCache:
    """Tests for FieldCache."""

    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        return FieldCache(max_size=10, default_ttl=60.0)

    def test_set_and_get(self, cache):
        """Test basic set and get."""
        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

    def test_get_missing(self, cache):
        """Test get missing key."""
        result = cache.get("nonexistent")

        assert result is None

    def test_get_expired(self, cache):
        """Test get expired entry."""
        cache.set("key1", "value1", ttl=0.01)
        time.sleep(0.02)

        result = cache.get("key1")

        assert result is None

    def test_get_or_load_cached(self, cache):
        """Test get_or_load with cached value."""
        cache.set("key1", "cached")
        loader = MagicMock(return_value="loaded")

        result = cache.get_or_load("key1", loader)

        assert result == "cached"
        loader.assert_not_called()

    def test_get_or_load_not_cached(self, cache):
        """Test get_or_load with no cached value."""
        loader = MagicMock(return_value="loaded")

        result = cache.get_or_load("key1", loader)

        assert result == "loaded"
        loader.assert_called_once()

        # Verify it's cached now
        result2 = cache.get("key1")
        assert result2 == "loaded"

    def test_invalidate(self, cache):
        """Test invalidating a key."""
        cache.set("key1", "value1")
        removed = cache.invalidate("key1")

        assert removed is True
        assert cache.get("key1") is None

    def test_invalidate_missing(self, cache):
        """Test invalidating missing key."""
        removed = cache.invalidate("nonexistent")

        assert removed is False

    def test_invalidate_prefix(self, cache):
        """Test invalidating by prefix."""
        cache.set("story:1:comments", "c1")
        cache.set("story:1:attachments", "a1")
        cache.set("story:2:comments", "c2")

        count = cache.invalidate_prefix("story:1:")

        assert count == 2
        assert cache.get("story:1:comments") is None
        assert cache.get("story:2:comments") == "c2"

    def test_clear(self, cache):
        """Test clearing cache."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        assert cache.size == 0

    def test_lru_eviction(self):
        """Test LRU eviction when max size reached."""
        import time

        cache = FieldCache(max_size=3, default_ttl=None)

        cache.set("key1", "value1")
        time.sleep(0.01)  # Ensure distinct timestamps
        cache.set("key2", "value2")
        time.sleep(0.01)
        cache.set("key3", "value3")
        time.sleep(0.01)

        # Access key1 to make it recently used
        cache.get("key1")
        time.sleep(0.01)

        # Add key4, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") is not None
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_stats_tracking(self, cache):
        """Test statistics are tracked."""
        cache.get_or_load("key1", lambda: "value1")  # Miss
        cache.get("key1")  # Hit

        stats = cache.stats
        assert stats.hits == 1
        assert stats.misses == 1


class TestGlobalCache:
    """Tests for global cache functions."""

    def test_get_global_cache(self):
        """Test getting global cache."""
        cache = get_global_cache()

        assert cache is not None
        assert isinstance(cache, FieldCache)

    def test_set_global_cache(self):
        """Test setting global cache."""
        custom_cache = FieldCache(max_size=5)
        set_global_cache(custom_cache)

        retrieved = get_global_cache()
        assert retrieved is custom_cache


class TestLazyList:
    """Tests for LazyList."""

    def test_lazy_loading(self):
        """Test data is loaded lazily."""
        loader = MagicMock(return_value=[1, 2, 3])
        lazy = LazyList(loader=loader)

        # Not loaded yet
        assert lazy.is_loaded is False
        loader.assert_not_called()

        # Access triggers load
        _ = lazy[0]

        assert lazy.is_loaded is True
        loader.assert_called_once()

    def test_with_initial_data(self):
        """Test with pre-loaded data."""
        lazy = LazyList(initial_data=[1, 2, 3])

        assert lazy.is_loaded is True
        assert list(lazy) == [1, 2, 3]

    def test_getitem(self):
        """Test indexing."""
        lazy = LazyList(initial_data=[1, 2, 3])

        assert lazy[0] == 1
        assert lazy[-1] == 3
        assert lazy[1:] == [2, 3]

    def test_setitem(self):
        """Test item assignment."""
        lazy = LazyList(initial_data=[1, 2, 3])
        lazy[1] = 10

        assert lazy[1] == 10

    def test_len(self):
        """Test length."""
        lazy = LazyList(initial_data=[1, 2, 3])

        assert len(lazy) == 3

    def test_iter(self):
        """Test iteration."""
        lazy = LazyList(initial_data=[1, 2, 3])
        result = list(lazy)

        assert result == [1, 2, 3]

    def test_contains(self):
        """Test containment check."""
        lazy = LazyList(initial_data=[1, 2, 3])

        assert 2 in lazy
        assert 5 not in lazy

    def test_bool(self):
        """Test boolean conversion."""
        empty = LazyList(initial_data=[])
        nonempty = LazyList(initial_data=[1])

        assert bool(empty) is False
        assert bool(nonempty) is True

    def test_append(self):
        """Test append."""
        lazy = LazyList(initial_data=[1, 2])
        lazy.append(3)

        assert list(lazy) == [1, 2, 3]

    def test_extend(self):
        """Test extend."""
        lazy = LazyList(initial_data=[1])
        lazy.extend([2, 3])

        assert list(lazy) == [1, 2, 3]

    def test_reload(self):
        """Test reloading data."""
        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return [call_count]

        lazy = LazyList(loader=loader)

        _ = lazy[0]  # First load
        assert lazy[0] == 1

        lazy.reload()  # Reload
        assert lazy[0] == 2
        assert call_count == 2

    def test_to_list(self):
        """Test converting to regular list."""
        lazy = LazyList(initial_data=[1, 2, 3])
        result = lazy.to_list()

        assert result == [1, 2, 3]
        assert isinstance(result, list)
        assert not isinstance(result, LazyList)

    def test_thread_safety(self):
        """Test thread-safe loading."""
        load_count = 0
        lock = threading.Lock()

        def loader():
            nonlocal load_count
            with lock:
                load_count += 1
            time.sleep(0.01)
            return [1, 2, 3]

        lazy = LazyList(loader=loader)

        threads = [threading.Thread(target=lambda: list(lazy)) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only load once
        assert load_count == 1


class TestLazyDict:
    """Tests for LazyDict."""

    def test_lazy_loading(self):
        """Test data is loaded lazily."""
        loader = MagicMock(return_value={"a": 1, "b": 2})
        lazy = LazyDict(loader=loader)

        # Not loaded yet
        assert lazy.is_loaded is False

        # Access triggers load
        _ = lazy["a"]

        assert lazy.is_loaded is True
        loader.assert_called_once()

    def test_with_initial_data(self):
        """Test with pre-loaded data."""
        lazy = LazyDict(initial_data={"a": 1, "b": 2})

        assert lazy.is_loaded is True
        assert lazy["a"] == 1

    def test_getitem(self):
        """Test key access."""
        lazy = LazyDict(initial_data={"a": 1, "b": 2})

        assert lazy["a"] == 1

    def test_setitem(self):
        """Test key assignment."""
        lazy = LazyDict(initial_data={"a": 1})
        lazy["b"] = 2

        assert lazy["b"] == 2

    def test_contains(self):
        """Test key containment."""
        lazy = LazyDict(initial_data={"a": 1})

        assert "a" in lazy
        assert "b" not in lazy

    def test_get(self):
        """Test get method."""
        lazy = LazyDict(initial_data={"a": 1})

        assert lazy.get("a") == 1
        assert lazy.get("b") is None
        assert lazy.get("b", 2) == 2

    def test_keys_values_items(self):
        """Test dict view methods."""
        lazy = LazyDict(initial_data={"a": 1, "b": 2})

        assert list(lazy.keys()) == ["a", "b"]
        assert list(lazy.values()) == [1, 2]
        assert list(lazy.items()) == [("a", 1), ("b", 2)]


class TestPaginatedCollection:
    """Tests for PaginatedCollection."""

    @pytest.fixture
    def data(self):
        """Create test data."""
        return list(range(100))

    @pytest.fixture
    def collection(self, data):
        """Create paginated collection."""

        def page_loader(offset: int, limit: int):
            return data[offset : offset + limit]

        return PaginatedCollection(
            page_loader=page_loader,
            page_size=10,
            total_count=100,
        )

    def test_lazy_page_loading(self, data):
        """Test pages are loaded lazily."""
        load_calls = []

        def page_loader(offset: int, limit: int):
            load_calls.append((offset, limit))
            return data[offset : offset + limit]

        collection = PaginatedCollection(
            page_loader=page_loader,
            page_size=10,
        )

        # No loads yet
        assert len(load_calls) == 0

        # Access item in first page
        _ = collection[5]
        assert len(load_calls) == 1
        assert load_calls[0] == (0, 10)

        # Access item in third page
        _ = collection[25]
        assert len(load_calls) == 2
        assert load_calls[1] == (20, 10)

    def test_getitem(self, collection):
        """Test indexing."""
        assert collection[0] == 0
        assert collection[50] == 50
        assert collection[99] == 99

    def test_negative_index(self, collection):
        """Test negative indexing."""
        assert collection[-1] == 99
        assert collection[-10] == 90

    def test_index_out_of_range(self, collection):
        """Test index out of range."""
        with pytest.raises(IndexError):
            _ = collection[200]

    def test_len(self, collection):
        """Test length."""
        assert len(collection) == 100

    def test_iter(self, collection):
        """Test iteration loads pages as needed."""
        result = list(collection)

        assert len(result) == 100
        assert result == list(range(100))

    def test_bool(self, collection):
        """Test boolean conversion."""
        assert bool(collection) is True

        empty = PaginatedCollection(
            page_loader=lambda o, l: [],
            page_size=10,
        )
        assert bool(empty) is False

    def test_loaded_count(self, collection):
        """Test loaded count tracking."""
        assert collection.loaded_count == 0

        _ = collection[5]  # Load first page
        assert collection.loaded_count == 10

        _ = collection[15]  # Load second page
        assert collection.loaded_count == 20

    def test_to_list(self, collection):
        """Test converting to regular list."""
        result = collection.to_list()

        assert result == list(range(100))
        assert isinstance(result, list)


class TestLazyLoadingConfig:
    """Tests for LazyLoadingConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = LazyLoadingConfig()

        assert LazyField.COMMENTS in config.lazy_fields
        assert LazyField.ATTACHMENTS in config.lazy_fields
        assert LazyField.COMMITS in config.lazy_fields
        assert config.use_cache is True
        assert config.cache_ttl == 300.0

    def test_eager_config(self):
        """Test eager loading configuration."""
        config = LazyLoadingConfig.eager()

        assert len(config.lazy_fields) == 0

    def test_minimal_config(self):
        """Test minimal loading configuration."""
        config = LazyLoadingConfig.minimal()

        assert len(config.lazy_fields) == len(LazyField)


class TestLazyProxy:
    """Tests for LazyProxy."""

    def test_basic_attribute_access(self):
        """Test accessing non-lazy attributes."""
        obj = MagicMock()
        obj.name = "test"
        obj.value = 42

        proxy = LazyProxy(obj)

        assert proxy.name == "test"
        assert proxy.value == 42

    def test_lazy_field_loading(self):
        """Test lazy field loading."""
        obj = MagicMock()
        obj.name = "test"

        loader = MagicMock(return_value=["comment1", "comment2"])

        proxy = LazyProxy(
            obj,
            lazy_fields={"comments": loader},
        )

        # Loader not called yet
        loader.assert_not_called()

        # Access triggers load
        result = proxy.comments

        loader.assert_called_once()
        assert result == ["comment1", "comment2"]

    def test_lazy_field_caching(self):
        """Test lazy fields are cached after first load."""
        obj = MagicMock()
        loader = MagicMock(return_value=[1, 2, 3])

        proxy = LazyProxy(
            obj,
            lazy_fields={"data": loader},
            cache=None,  # Disable external cache
        )

        # Access twice
        _ = proxy.data
        _ = proxy.data

        # Loader only called once
        loader.assert_called_once()

    def test_is_loaded(self):
        """Test checking if field is loaded."""
        obj = MagicMock()
        proxy = LazyProxy(
            obj,
            lazy_fields={"comments": list},
        )

        assert proxy._is_loaded("comments") is False

        _ = proxy.comments

        assert proxy._is_loaded("comments") is True

    def test_preload(self):
        """Test preloading specific fields."""
        obj = MagicMock()
        loader1 = MagicMock(return_value=[])
        loader2 = MagicMock(return_value=[])

        proxy = LazyProxy(
            obj,
            lazy_fields={
                "field1": loader1,
                "field2": loader2,
            },
        )

        proxy._preload("field1")

        loader1.assert_called_once()
        loader2.assert_not_called()

    def test_preload_all(self):
        """Test preloading all fields."""
        obj = MagicMock()
        loader1 = MagicMock(return_value=[])
        loader2 = MagicMock(return_value=[])

        proxy = LazyProxy(
            obj,
            lazy_fields={
                "field1": loader1,
                "field2": loader2,
            },
        )

        proxy._preload_all()

        loader1.assert_called_once()
        loader2.assert_called_once()

    def test_unwrap(self):
        """Test getting wrapped object."""
        obj = MagicMock()
        obj.name = "test"

        proxy = LazyProxy(obj)

        assert proxy._unwrap is obj

    def test_setattr_lazy_field(self):
        """Test setting lazy field value."""
        obj = MagicMock()
        proxy = LazyProxy(
            obj,
            lazy_fields={"comments": list},
        )

        proxy.comments = ["new comment"]

        assert proxy.comments == ["new comment"]


class TestLazyStory:
    """Tests for LazyStory."""

    @pytest.fixture
    def story(self):
        """Create a test story."""
        return LazyStory(
            story_id="US-001",
            title="Test Story",
            status="planned",
            priority="high",
            story_points=5,
        )

    def test_basic_attributes(self, story):
        """Test basic attributes are available."""
        assert story.story_id == "US-001"
        assert story.title == "Test Story"
        assert story.status == "planned"
        assert story.priority == "high"
        assert story.story_points == 5

    def test_comments_lazy_loading(self, story):
        """Test comments are lazy loaded."""
        comments_loader = MagicMock(return_value=[{"text": "comment1"}])
        story.set_loader(LazyField.COMMENTS, comments_loader)

        # Not loaded yet
        assert story.is_loaded(LazyField.COMMENTS) is False

        # Access triggers load
        result = story.comments

        comments_loader.assert_called_once()
        assert result == [{"text": "comment1"}]
        assert story.is_loaded(LazyField.COMMENTS) is True

    def test_subtasks_lazy_loading(self, story):
        """Test subtasks are lazy loaded."""
        subtasks_loader = MagicMock(return_value=[{"title": "subtask1"}])
        story.set_loader(LazyField.SUBTASKS, subtasks_loader)

        result = story.subtasks

        subtasks_loader.assert_called_once()
        assert result == [{"title": "subtask1"}]

    def test_attachments_lazy_loading(self, story):
        """Test attachments are lazy loaded."""
        loader = MagicMock(return_value=["file1.pdf", "file2.png"])
        story.set_loader(LazyField.ATTACHMENTS, loader)

        result = story.attachments

        loader.assert_called_once()
        assert result == ["file1.pdf", "file2.png"]

    def test_description_lazy_loading(self, story):
        """Test description is lazy loaded."""
        loader = MagicMock(return_value="Full description")
        story.set_loader(LazyField.DESCRIPTION, loader)

        result = story.description

        loader.assert_called_once()
        assert result == "Full description"

    def test_set_comments_directly(self, story):
        """Test setting comments directly."""
        story.comments = [{"text": "direct comment"}]

        assert story.comments == [{"text": "direct comment"}]
        assert story.is_loaded(LazyField.COMMENTS) is True

    def test_preload(self, story):
        """Test preloading specific fields."""
        loader1 = MagicMock(return_value=[])
        loader2 = MagicMock(return_value=[])

        story.set_loader(LazyField.COMMENTS, loader1)
        story.set_loader(LazyField.SUBTASKS, loader2)

        story.preload(LazyField.COMMENTS)

        loader1.assert_called_once()
        loader2.assert_not_called()

    def test_preload_all(self, story):
        """Test preloading all fields."""
        loaders = {}
        for field in LazyField:
            loader = MagicMock(return_value=[])
            story.set_loader(field, loader)
            loaders[field] = loader

        story.preload_all()

        for loader in loaders.values():
            loader.assert_called_once()

    def test_from_basic_data(self):
        """Test factory method."""
        story = LazyStory.from_basic_data(
            story_id="US-002",
            title="Factory Story",
            status="in_progress",
            assignee="developer",
        )

        assert story.story_id == "US-002"
        assert story.title == "Factory Story"
        assert story.status == "in_progress"
        assert story.assignee == "developer"

    def test_repr(self, story):
        """Test string representation."""
        repr_str = repr(story)

        assert "LazyStory" in repr_str
        assert "US-001" in repr_str

    def test_default_empty_values(self, story):
        """Test default empty values for lazy fields."""
        # No loaders set, should return empty lists/values
        assert story.comments == []
        assert story.subtasks == []
        assert story.attachments == []
        assert story.links == []
        assert story.technical_notes == ""
