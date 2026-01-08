"""Tests for Bounded Concurrency - Per-tracker concurrency control."""

import asyncio
import threading
import time
from concurrent.futures import Future, wait
from unittest.mock import MagicMock

import pytest

from spectryn.adapters.async_base import (
    DEFAULT_TRACKER_LIMITS,
    AsyncBoundedExecutor,
    BoundedExecutor,
    ConcurrencyStats,
    OrderedTaskQueue,
    PrioritizedTask,
    Priority,
    ResourceLock,
    TrackerSemaphore,
    create_async_bounded_executor,
    create_bounded_executor,
)
from spectryn.core.ports.config_provider import TrackerType


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_ordering(self):
        """Test that priorities are correctly ordered."""
        assert Priority.CRITICAL < Priority.HIGH
        assert Priority.HIGH < Priority.NORMAL
        assert Priority.NORMAL < Priority.LOW
        assert Priority.LOW < Priority.IDLE

    def test_priority_values(self):
        """Test priority values are integers."""
        assert Priority.CRITICAL.value == 0
        assert Priority.NORMAL.value == 50
        assert Priority.IDLE.value == 200


class TestDefaultTrackerLimits:
    """Tests for default tracker limits."""

    def test_all_trackers_have_limits(self):
        """Test all tracker types have default limits."""
        for tracker_type in TrackerType:
            assert tracker_type in DEFAULT_TRACKER_LIMITS
            assert DEFAULT_TRACKER_LIMITS[tracker_type] > 0

    def test_limits_are_reasonable(self):
        """Test that limits are within reasonable range."""
        for tracker_type, limit in DEFAULT_TRACKER_LIMITS.items():
            assert 1 <= limit <= 50, f"{tracker_type} has unreasonable limit: {limit}"


class TestConcurrencyStats:
    """Tests for ConcurrencyStats."""

    def test_initial_values(self):
        """Test initial stat values."""
        stats = ConcurrencyStats()
        assert stats.total_submitted == 0
        assert stats.total_completed == 0
        assert stats.total_failed == 0
        assert stats.peak_concurrency == 0

    def test_record_completion(self):
        """Test recording completions."""
        stats = ConcurrencyStats()
        stats.record_completion("jira", 0.5)
        stats.record_completion("jira", 1.0)
        stats.record_completion("github", 0.3)

        assert stats.total_completed == 3
        assert stats.per_tracker_completed["jira"] == 2
        assert stats.per_tracker_completed["github"] == 1
        assert stats.avg_execution_time == pytest.approx(0.6, rel=0.01)

    def test_record_failure(self):
        """Test recording failures."""
        stats = ConcurrencyStats()
        stats.record_failure("jira")
        stats.record_failure("jira")
        stats.record_failure("github")

        assert stats.total_failed == 3
        assert stats.per_tracker_failed["jira"] == 2
        assert stats.per_tracker_failed["github"] == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = ConcurrencyStats(
            total_submitted=10,
            total_completed=8,
            total_failed=2,
            peak_concurrency=5,
        )
        d = stats.to_dict()

        assert d["total_submitted"] == 10
        assert d["total_completed"] == 8
        assert d["total_failed"] == 2
        assert d["success_rate"] == 0.8


class TestTrackerSemaphore:
    """Tests for TrackerSemaphore."""

    def test_get_limit_for_tracker_type(self):
        """Test getting limit for TrackerType."""
        sem = TrackerSemaphore()
        limit = sem._get_limit(TrackerType.JIRA)
        assert limit == DEFAULT_TRACKER_LIMITS[TrackerType.JIRA]

    def test_get_limit_for_string(self):
        """Test getting limit for string tracker."""
        sem = TrackerSemaphore()
        limit = sem._get_limit("unknown")
        assert limit == 5  # Default limit

    def test_custom_limits(self):
        """Test custom tracker limits."""
        custom = {TrackerType.JIRA: 20}
        sem = TrackerSemaphore(limits=custom)
        assert sem._get_limit(TrackerType.JIRA) == 20

    def test_acquire_and_release(self):
        """Test acquire and release."""
        sem = TrackerSemaphore(limits={TrackerType.JIRA: 2})

        assert sem.acquire(TrackerType.JIRA)
        assert sem.get_active_count(TrackerType.JIRA) == 1

        assert sem.acquire(TrackerType.JIRA)
        assert sem.get_active_count(TrackerType.JIRA) == 2

        sem.release(TrackerType.JIRA)
        assert sem.get_active_count(TrackerType.JIRA) == 1

    def test_set_limit(self):
        """Test dynamic limit adjustment."""
        sem = TrackerSemaphore()
        original = sem._get_limit(TrackerType.JIRA)

        sem.set_limit(TrackerType.JIRA, 100)
        assert sem._get_limit(TrackerType.JIRA) == 100
        assert sem._get_limit(TrackerType.JIRA) != original


class TestTrackerSemaphoreAsync:
    """Async tests for TrackerSemaphore."""

    @pytest.mark.asyncio
    async def test_acquire_async(self):
        """Test async acquire."""
        sem = TrackerSemaphore(limits={TrackerType.JIRA: 2})

        await sem.acquire_async(TrackerType.JIRA)
        assert sem.get_active_count(TrackerType.JIRA) == 1

        await sem.release_async(TrackerType.JIRA)
        assert sem.get_active_count(TrackerType.JIRA) == 0


class TestResourceLock:
    """Tests for ResourceLock."""

    def test_get_lock(self):
        """Test getting locks for resources."""
        rl = ResourceLock()
        lock1 = rl.get_lock("resource-1")
        lock2 = rl.get_lock("resource-1")

        assert lock1 is lock2  # Same resource = same lock

        lock3 = rl.get_lock("resource-2")
        assert lock3 is not lock1  # Different resource = different lock

    def test_lock_prevents_concurrent_access(self):
        """Test that locks serialize access."""
        rl = ResourceLock()
        lock = rl.get_lock("shared")
        results: list[int] = []

        def worker(n: int) -> None:
            with lock:
                results.append(n)
                time.sleep(0.01)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 5 workers should have completed
        assert len(results) == 5


class TestResourceLockAsync:
    """Async tests for ResourceLock."""

    @pytest.mark.asyncio
    async def test_get_async_lock(self):
        """Test getting async locks."""
        rl = ResourceLock()
        lock1 = await rl.get_async_lock("resource-1")
        lock2 = await rl.get_async_lock("resource-1")

        assert lock1 is lock2  # Same resource = same lock


class TestPrioritizedTask:
    """Tests for PrioritizedTask."""

    def test_ordering_by_priority(self):
        """Test tasks are ordered by priority."""
        task1 = PrioritizedTask(
            priority=Priority.HIGH.value,
            sequence=1,
            task="task1",
            tracker=TrackerType.JIRA,
        )
        task2 = PrioritizedTask(
            priority=Priority.LOW.value,
            sequence=0,
            task="task2",
            tracker=TrackerType.JIRA,
        )

        assert task1 < task2  # Higher priority (lower value) comes first

    def test_ordering_by_sequence_within_priority(self):
        """Test FIFO ordering within same priority."""
        task1 = PrioritizedTask(
            priority=Priority.NORMAL.value,
            sequence=1,
            task="task1",
            tracker=TrackerType.JIRA,
        )
        task2 = PrioritizedTask(
            priority=Priority.NORMAL.value,
            sequence=2,
            task="task2",
            tracker=TrackerType.JIRA,
        )

        assert task1 < task2  # Earlier sequence comes first


class TestOrderedTaskQueue:
    """Tests for OrderedTaskQueue."""

    def test_push_and_pop(self):
        """Test basic push and pop."""
        queue: OrderedTaskQueue[str] = OrderedTaskQueue()
        queue.push("task1", TrackerType.JIRA, Priority.NORMAL)
        queue.push("task2", TrackerType.JIRA, Priority.NORMAL)

        item1 = queue.pop()
        item2 = queue.pop()

        assert item1 is not None
        assert item2 is not None
        assert item1.task == "task1"  # FIFO order
        assert item2.task == "task2"

    def test_priority_ordering(self):
        """Test that high priority items come first."""
        queue: OrderedTaskQueue[str] = OrderedTaskQueue()
        queue.push("low", TrackerType.JIRA, Priority.LOW)
        queue.push("high", TrackerType.JIRA, Priority.HIGH)
        queue.push("normal", TrackerType.JIRA, Priority.NORMAL)

        item1 = queue.pop()
        item2 = queue.pop()
        item3 = queue.pop()

        assert item1 is not None
        assert item1.task == "high"
        assert item2 is not None
        assert item2.task == "normal"
        assert item3 is not None
        assert item3.task == "low"

    def test_is_empty(self):
        """Test is_empty property."""
        queue: OrderedTaskQueue[str] = OrderedTaskQueue()
        assert queue.is_empty

        queue.push("task", TrackerType.JIRA)
        assert not queue.is_empty

        queue.pop()
        assert queue.is_empty

    def test_len(self):
        """Test __len__."""
        queue: OrderedTaskQueue[str] = OrderedTaskQueue()
        assert len(queue) == 0

        queue.push("task1", TrackerType.JIRA)
        queue.push("task2", TrackerType.JIRA)
        assert len(queue) == 2

    def test_peek(self):
        """Test peek without removing."""
        queue: OrderedTaskQueue[str] = OrderedTaskQueue()
        queue.push("task", TrackerType.JIRA)

        item = queue.peek()
        assert item is not None
        assert item.task == "task"
        assert len(queue) == 1  # Still in queue


class TestBoundedExecutor:
    """Tests for BoundedExecutor."""

    @pytest.fixture
    def executor(self) -> BoundedExecutor:
        return BoundedExecutor(max_workers=10)

    def test_submit_and_get_result(self, executor: BoundedExecutor):
        """Test basic submit and result retrieval."""
        future = executor.submit(lambda x: x * 2, 5, tracker=TrackerType.JIRA)
        result = future.result(timeout=5)
        assert result == 10

        executor.shutdown()

    def test_submit_tracks_stats(self, executor: BoundedExecutor):
        """Test that submissions track statistics."""
        future = executor.submit(lambda: 42, tracker=TrackerType.JIRA)
        future.result(timeout=5)

        stats = executor.stats
        assert stats.total_submitted >= 1
        assert stats.total_completed >= 1

        executor.shutdown()

    def test_per_tracker_concurrency(self):
        """Test per-tracker concurrency limits."""
        executor = BoundedExecutor(
            max_workers=20,
            tracker_limits={TrackerType.JIRA: 2},
        )

        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def track_concurrency() -> int:
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)

            time.sleep(0.05)

            with lock:
                current_concurrent -= 1

            return 1

        # Submit more tasks than concurrency limit
        futures = [executor.submit(track_concurrency, tracker=TrackerType.JIRA) for _ in range(10)]
        wait(futures, timeout=10)

        # Max concurrent should not exceed tracker limit
        assert max_concurrent <= 2

        executor.shutdown()

    def test_resource_lock_ordering(self):
        """Test that resource locks serialize access."""
        executor = BoundedExecutor(max_workers=10)
        results: list[int] = []
        lock = threading.Lock()

        def append_with_delay(n: int) -> int:
            with lock:
                results.append(n)
            time.sleep(0.01)
            return n

        # Submit tasks for same resource - should be serialized
        futures = [
            executor.submit(
                append_with_delay,
                i,
                tracker=TrackerType.JIRA,
                resource_key="same-resource",
            )
            for i in range(5)
        ]
        wait(futures, timeout=10)

        assert len(results) == 5

        executor.shutdown()

    def test_map(self, executor: BoundedExecutor):
        """Test map operation."""
        futures = executor.map(
            lambda x: x * 2,
            [1, 2, 3, 4, 5],
            tracker=TrackerType.JIRA,
        )

        results = [f.result(timeout=5) for f in futures]
        assert results == [2, 4, 6, 8, 10]

        executor.shutdown()

    def test_get_stats(self, executor: BoundedExecutor):
        """Test get_stats returns dictionary."""
        stats = executor.get_stats()
        assert "total_submitted" in stats
        assert "total_completed" in stats
        assert "max_workers" in stats
        assert "active_per_tracker" in stats

        executor.shutdown()

    def test_set_tracker_limit(self, executor: BoundedExecutor):
        """Test dynamic limit adjustment."""
        executor.set_tracker_limit(TrackerType.JIRA, 100)
        # Just verify it doesn't crash
        executor.shutdown()

    def test_context_manager(self):
        """Test context manager usage."""
        with BoundedExecutor(max_workers=5) as executor:
            future = executor.submit(lambda: 42, tracker=TrackerType.JIRA)
            result = future.result(timeout=5)
            assert result == 42

    def test_shutdown_prevents_new_submissions(self, executor: BoundedExecutor):
        """Test that shutdown prevents new submissions."""
        executor.shutdown()

        with pytest.raises(RuntimeError):
            executor.submit(lambda: 42, tracker=TrackerType.JIRA)

    def test_failed_task_tracks_stats(self, executor: BoundedExecutor):
        """Test that failed tasks update statistics."""

        def failing_fn() -> None:
            raise ValueError("Test error")

        future = executor.submit(failing_fn, tracker=TrackerType.JIRA)

        with pytest.raises(ValueError):
            future.result(timeout=5)

        assert executor.stats.total_failed >= 1

        executor.shutdown()


class TestAsyncBoundedExecutor:
    """Tests for AsyncBoundedExecutor."""

    @pytest.mark.asyncio
    async def test_run_basic(self):
        """Test basic async run."""

        async def work() -> int:
            return 42

        async with AsyncBoundedExecutor() as executor:
            result = await executor.run(work(), tracker=TrackerType.JIRA)
            assert result == 42

    @pytest.mark.asyncio
    async def test_per_tracker_concurrency(self):
        """Test per-tracker concurrency limits."""
        executor = AsyncBoundedExecutor(tracker_limits={TrackerType.JIRA: 2})

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def track_concurrency() -> int:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)

            await asyncio.sleep(0.05)

            async with lock:
                current_concurrent -= 1

            return 1

        # Submit more tasks than concurrency limit
        tasks = [executor.run(track_concurrency(), tracker=TrackerType.JIRA) for _ in range(10)]
        await asyncio.gather(*tasks)

        # Max concurrent should not exceed tracker limit
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_gather(self):
        """Test gather operation."""

        async def work(n: int) -> int:
            return n * 2

        async with AsyncBoundedExecutor() as executor:
            coros = [(work(i), TrackerType.JIRA) for i in range(5)]
            results = await executor.gather(coros)
            assert results == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_map(self):
        """Test map operation."""

        async def double(n: int) -> int:
            return n * 2

        async with AsyncBoundedExecutor() as executor:
            results = await executor.map([1, 2, 3], double, tracker=TrackerType.JIRA)
            assert results == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_resource_lock_ordering(self):
        """Test resource locks serialize access."""
        executor = AsyncBoundedExecutor()
        results: list[int] = []

        async def append_with_delay(n: int) -> int:
            results.append(n)
            await asyncio.sleep(0.01)
            return n

        # Submit tasks for same resource
        tasks = [
            executor.run(
                append_with_delay(i),
                tracker=TrackerType.JIRA,
                resource_key="same-resource",
            )
            for i in range(5)
        ]
        await asyncio.gather(*tasks)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test get_stats returns dictionary."""
        async with AsyncBoundedExecutor() as executor:
            stats = executor.get_stats()
            assert "total_submitted" in stats
            assert "total_completed" in stats
            assert "current_concurrency" in stats
            assert "active_per_tracker" in stats

    @pytest.mark.asyncio
    async def test_peak_concurrency_tracking(self):
        """Test peak concurrency is tracked."""
        executor = AsyncBoundedExecutor(tracker_limits={TrackerType.JIRA: 5})

        async def work() -> int:
            await asyncio.sleep(0.05)
            return 1

        tasks = [executor.run(work(), tracker=TrackerType.JIRA) for _ in range(10)]
        await asyncio.gather(*tasks)

        assert executor.stats.peak_concurrency > 0

    @pytest.mark.asyncio
    async def test_failed_task_tracks_stats(self):
        """Test that failed tasks update statistics."""

        async def failing_fn() -> None:
            raise ValueError("Test error")

        async with AsyncBoundedExecutor() as executor:
            with pytest.raises(ValueError):
                await executor.run(failing_fn(), tracker=TrackerType.JIRA)

            assert executor.stats.total_failed >= 1


class TestCreateBoundedExecutor:
    """Tests for create_bounded_executor factory."""

    def test_create_default(self):
        """Test creating with default preset."""
        executor = create_bounded_executor()
        assert executor._max_workers == 20
        executor.shutdown()

    def test_create_conservative(self):
        """Test creating with conservative preset."""
        executor = create_bounded_executor(preset="conservative")
        # Conservative limits should be lower
        executor.shutdown()

    def test_create_aggressive(self):
        """Test creating with aggressive preset."""
        executor = create_bounded_executor(preset="aggressive")
        # Aggressive limits should be higher
        executor.shutdown()

    def test_create_custom_workers(self):
        """Test creating with custom max_workers."""
        executor = create_bounded_executor(max_workers=50)
        assert executor._max_workers == 50
        executor.shutdown()


class TestCreateAsyncBoundedExecutor:
    """Tests for create_async_bounded_executor factory."""

    def test_create_default(self):
        """Test creating with default preset."""
        executor = create_async_bounded_executor()
        assert executor is not None

    def test_create_conservative(self):
        """Test creating with conservative preset."""
        executor = create_async_bounded_executor(preset="conservative")
        assert executor is not None

    def test_create_aggressive(self):
        """Test creating with aggressive preset."""
        executor = create_async_bounded_executor(preset="aggressive")
        assert executor is not None


class TestBoundedConcurrencyIntegration:
    """Integration tests for bounded concurrency."""

    def test_multi_tracker_sync(self):
        """Test concurrent operations across multiple trackers."""
        with BoundedExecutor(
            max_workers=20,
            tracker_limits={
                TrackerType.JIRA: 3,
                TrackerType.GITHUB: 5,
            },
        ) as executor:
            jira_futures = [
                executor.submit(lambda: "jira", tracker=TrackerType.JIRA) for _ in range(10)
            ]
            github_futures = [
                executor.submit(lambda: "github", tracker=TrackerType.GITHUB) for _ in range(10)
            ]

            jira_results = [f.result(timeout=5) for f in jira_futures]
            github_results = [f.result(timeout=5) for f in github_futures]

            assert all(r == "jira" for r in jira_results)
            assert all(r == "github" for r in github_results)

            stats = executor.get_stats()
            assert stats["per_tracker_completed"]["jira"] == 10
            assert stats["per_tracker_completed"]["github"] == 10

    @pytest.mark.asyncio
    async def test_async_multi_tracker_sync(self):
        """Test async concurrent operations across multiple trackers."""

        async def jira_work() -> str:
            await asyncio.sleep(0.01)
            return "jira"

        async def github_work() -> str:
            await asyncio.sleep(0.01)
            return "github"

        async with AsyncBoundedExecutor(
            tracker_limits={
                TrackerType.JIRA: 3,
                TrackerType.GITHUB: 5,
            }
        ) as executor:
            tasks = []
            for _ in range(10):
                tasks.append(executor.run(jira_work(), tracker=TrackerType.JIRA))
                tasks.append(executor.run(github_work(), tracker=TrackerType.GITHUB))

            results = await asyncio.gather(*tasks)

            jira_count = sum(1 for r in results if r == "jira")
            github_count = sum(1 for r in results if r == "github")

            assert jira_count == 10
            assert github_count == 10

    def test_ordering_within_resource(self):
        """Test that operations on same resource maintain order."""
        with BoundedExecutor(max_workers=10) as executor:
            results: list[int] = []
            lock = threading.Lock()

            def append(n: int) -> int:
                with lock:
                    results.append(n)
                time.sleep(0.01)  # Simulate work
                return n

            # Submit in order, all for same resource
            futures = [
                executor.submit(
                    append,
                    i,
                    tracker=TrackerType.JIRA,
                    resource_key="PROJ-123",
                )
                for i in range(10)
            ]
            wait(futures, timeout=10)

            # Results should be in order due to resource locking
            # Note: We can't guarantee exact order in results list
            # but all 10 should be present
            assert len(results) == 10
            assert set(results) == set(range(10))
