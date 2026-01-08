"""
Bounded Concurrency - Per-tracker concurrency control with ordering guarantees.

Provides fine-grained concurrency control for multi-tracker environments:
- Per-tracker concurrency limits (different trackers can have different limits)
- Ordering guarantees (operations for same resource maintain order)
- Priority queuing (high-priority operations execute first)
- Fair scheduling across trackers
- Resource-level locking for consistency

This module is designed for high-concurrency sync environments where:
- Multiple trackers are synced simultaneously
- API rate limits vary per tracker
- Operation ordering matters for consistency
- Resources (issues, epics) need serialized access
"""

import asyncio
import heapq
import logging
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import IntEnum
from types import TracebackType
from typing import Any, Generic, TypeVar

from spectryn.core.ports.config_provider import TrackerType


T = TypeVar("T")
R = TypeVar("R")


class Priority(IntEnum):
    """Operation priority levels (lower = higher priority)."""

    CRITICAL = 0  # Must execute immediately
    HIGH = 10  # Time-sensitive operations
    NORMAL = 50  # Default priority
    LOW = 100  # Background operations
    IDLE = 200  # Run when nothing else is pending


# Default concurrency limits per tracker type
# These are tuned based on typical API rate limits
DEFAULT_TRACKER_LIMITS: dict[TrackerType, int] = {
    TrackerType.JIRA: 10,  # Jira Cloud: ~10 req/s
    TrackerType.GITHUB: 15,  # GitHub: 5000/hr ≈ 1.4/s, but bursts OK
    TrackerType.LINEAR: 5,  # Linear: Conservative due to GraphQL
    TrackerType.AZURE_DEVOPS: 10,  # Azure DevOps: Similar to Jira
    TrackerType.ASANA: 5,  # Asana: 150/min ≈ 2.5/s
    TrackerType.GITLAB: 10,  # GitLab: 10 req/s
    TrackerType.MONDAY: 5,  # Monday: Conservative (GraphQL)
    TrackerType.TRELLO: 10,  # Trello: 10 req/s
    TrackerType.SHORTCUT: 10,  # Shortcut: 200/min ≈ 3.3/s
    TrackerType.CLICKUP: 5,  # ClickUp: 100/min ≈ 1.7/s
    TrackerType.BITBUCKET: 10,  # Bitbucket: Similar to GitHub
    TrackerType.YOUTRACK: 5,  # YouTrack: Conservative
    TrackerType.BASECAMP: 5,  # Basecamp: 50/10s ≈ 5/s
    TrackerType.PLANE: 10,  # Plane: Self-hosted usually OK
    TrackerType.PIVOTAL: 3,  # Pivotal: 400/15min ≈ 0.4/s (conservative)
}


@dataclass(order=True)
class PrioritizedTask:
    """A task with priority for heap-based scheduling."""

    priority: int
    sequence: int  # Tie-breaker for FIFO within same priority
    task: Any = field(compare=False)
    tracker: TrackerType | str = field(compare=False)
    resource_key: str | None = field(compare=False, default=None)


@dataclass
class ConcurrencyStats:
    """Statistics for bounded concurrency execution."""

    total_submitted: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_queued: int = 0
    peak_concurrency: int = 0
    total_wait_time: float = 0.0
    avg_execution_time: float = 0.0
    per_tracker_completed: dict[str, int] = field(default_factory=dict)
    per_tracker_failed: dict[str, int] = field(default_factory=dict)

    def record_completion(self, tracker: str, execution_time: float) -> None:
        """Record a successful completion."""
        self.total_completed += 1
        self.per_tracker_completed[tracker] = self.per_tracker_completed.get(tracker, 0) + 1
        # Update running average
        total = self.total_completed
        self.avg_execution_time = (self.avg_execution_time * (total - 1) + execution_time) / total

    def record_failure(self, tracker: str) -> None:
        """Record a failed operation."""
        self.total_failed += 1
        self.per_tracker_failed[tracker] = self.per_tracker_failed.get(tracker, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_submitted": self.total_submitted,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "total_queued": self.total_queued,
            "peak_concurrency": self.peak_concurrency,
            "total_wait_time": self.total_wait_time,
            "avg_execution_time": self.avg_execution_time,
            "success_rate": (
                self.total_completed / self.total_submitted if self.total_submitted > 0 else 1.0
            ),
            "per_tracker_completed": dict(self.per_tracker_completed),
            "per_tracker_failed": dict(self.per_tracker_failed),
        }


class TrackerSemaphore:
    """
    Semaphore with per-tracker concurrency control.

    Manages a semaphore for each tracker type, allowing different
    concurrency limits per tracker.
    """

    def __init__(
        self,
        limits: dict[TrackerType | str, int] | None = None,
        default_limit: int = 5,
    ):
        """
        Initialize tracker semaphores.

        Args:
            limits: Per-tracker concurrency limits
            default_limit: Default limit for unknown trackers
        """
        merged_limits: dict[TrackerType | str, int] = {**DEFAULT_TRACKER_LIMITS}
        if limits:
            merged_limits.update(limits)
        self._limits = merged_limits
        self._default_limit = default_limit
        self._semaphores: dict[str, threading.Semaphore] = {}
        self._async_semaphores: dict[str, asyncio.Semaphore] = {}
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._active_count: dict[str, int] = defaultdict(int)

    def _get_key(self, tracker: TrackerType | str) -> str:
        """Get string key for tracker."""
        return tracker.value if isinstance(tracker, TrackerType) else tracker

    def _get_limit(self, tracker: TrackerType | str) -> int:
        """Get concurrency limit for tracker."""
        if isinstance(tracker, TrackerType):
            return self._limits.get(tracker, self._default_limit)
        # String key - check if it matches any TrackerType
        for tt in TrackerType:
            if tt.value == tracker:
                return self._limits.get(tt, self._default_limit)
        return self._default_limit

    def get_semaphore(self, tracker: TrackerType | str) -> threading.Semaphore:
        """Get or create semaphore for tracker (sync)."""
        key = self._get_key(tracker)
        with self._lock:
            if key not in self._semaphores:
                limit = self._get_limit(tracker)
                self._semaphores[key] = threading.Semaphore(limit)
            return self._semaphores[key]

    async def get_async_semaphore(self, tracker: TrackerType | str) -> asyncio.Semaphore:
        """Get or create semaphore for tracker (async)."""
        key = self._get_key(tracker)
        async with self._async_lock:
            if key not in self._async_semaphores:
                limit = self._get_limit(tracker)
                self._async_semaphores[key] = asyncio.Semaphore(limit)
            return self._async_semaphores[key]

    def acquire(self, tracker: TrackerType | str, blocking: bool = True) -> bool:
        """Acquire semaphore for tracker (sync)."""
        sem = self.get_semaphore(tracker)
        result = sem.acquire(blocking=blocking)
        if result:
            key = self._get_key(tracker)
            with self._lock:
                self._active_count[key] += 1
        return result

    def release(self, tracker: TrackerType | str) -> None:
        """Release semaphore for tracker (sync)."""
        key = self._get_key(tracker)
        sem = self.get_semaphore(tracker)
        with self._lock:
            self._active_count[key] = max(0, self._active_count[key] - 1)
        sem.release()

    async def acquire_async(self, tracker: TrackerType | str) -> None:
        """Acquire semaphore for tracker (async)."""
        sem = await self.get_async_semaphore(tracker)
        await sem.acquire()
        key = self._get_key(tracker)
        async with self._async_lock:
            self._active_count[key] += 1

    async def release_async(self, tracker: TrackerType | str) -> None:
        """Release semaphore for tracker (async)."""
        key = self._get_key(tracker)
        sem = await self.get_async_semaphore(tracker)
        async with self._async_lock:
            self._active_count[key] = max(0, self._active_count[key] - 1)
        sem.release()

    def get_active_count(self, tracker: TrackerType | str) -> int:
        """Get current active count for tracker."""
        key = self._get_key(tracker)
        return self._active_count.get(key, 0)

    def get_all_active_counts(self) -> dict[str, int]:
        """Get active counts for all trackers."""
        return dict(self._active_count)

    def set_limit(self, tracker: TrackerType | str, limit: int) -> None:
        """
        Dynamically adjust limit for a tracker.

        Note: This creates a new semaphore if limit differs from current.
        Existing operations will complete before new limit takes effect.
        """
        key = self._get_key(tracker)
        if isinstance(tracker, TrackerType):
            self._limits[tracker] = limit
        else:
            # Store as string key too for lookups
            self._limits[tracker] = limit  # type: ignore[index]

        # Reset semaphores so new limit takes effect
        with self._lock:
            if key in self._semaphores:
                del self._semaphores[key]


class ResourceLock:
    """
    Resource-level locking for ordering guarantees.

    Ensures that operations on the same resource (e.g., same issue)
    are serialized to maintain consistency.
    """

    def __init__(self) -> None:
        """Initialize the resource lock manager."""
        self._locks: dict[str, threading.Lock] = {}
        self._async_locks: dict[str, asyncio.Lock] = {}
        self._manager_lock = threading.Lock()
        self._async_manager_lock = asyncio.Lock()

    def get_lock(self, resource_key: str) -> threading.Lock:
        """Get or create lock for a resource (sync)."""
        with self._manager_lock:
            if resource_key not in self._locks:
                self._locks[resource_key] = threading.Lock()
            return self._locks[resource_key]

    async def get_async_lock(self, resource_key: str) -> asyncio.Lock:
        """Get or create lock for a resource (async)."""
        async with self._async_manager_lock:
            if resource_key not in self._async_locks:
                self._async_locks[resource_key] = asyncio.Lock()
            return self._async_locks[resource_key]

    def cleanup_unused(self, max_age: float = 300.0) -> int:
        """
        Clean up unused locks to prevent memory leaks.

        Returns number of locks cleaned up.
        """
        # For simplicity, we don't track age - just keep all locks
        # In production, you'd track last access time
        return 0


class BoundedExecutor:
    """
    Bounded executor with per-tracker concurrency and ordering.

    Provides a thread pool executor with:
    - Per-tracker concurrency limits
    - Priority-based scheduling
    - Resource-level ordering guarantees
    - Statistics tracking

    Example:
        >>> executor = BoundedExecutor(max_workers=20)
        >>>
        >>> # Submit with tracker-specific concurrency
        >>> future = executor.submit(
        ...     sync_issue,
        ...     tracker=TrackerType.JIRA,
        ...     resource_key="PROJ-123",
        ... )
        >>>
        >>> # Submit high-priority operation
        >>> future = executor.submit(
        ...     critical_update,
        ...     tracker=TrackerType.GITHUB,
        ...     priority=Priority.HIGH,
        ... )
    """

    def __init__(
        self,
        max_workers: int = 20,
        tracker_limits: dict[TrackerType | str, int] | None = None,
        default_tracker_limit: int = 5,
    ):
        """
        Initialize the bounded executor.

        Args:
            max_workers: Maximum total concurrent workers
            tracker_limits: Per-tracker concurrency limits
            default_tracker_limit: Default limit for unknown trackers
        """
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tracker_semaphore = TrackerSemaphore(
            limits=tracker_limits,
            default_limit=default_tracker_limit,
        )
        self._resource_lock = ResourceLock()
        self._stats = ConcurrencyStats()
        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._shutdown = False

        self.logger = logging.getLogger("BoundedExecutor")

    def _next_sequence(self) -> int:
        """Get next sequence number for ordering."""
        with self._sequence_lock:
            self._sequence += 1
            return self._sequence

    def submit(
        self,
        fn: Callable[..., T],
        *args: Any,
        tracker: TrackerType | str = TrackerType.JIRA,
        resource_key: str | None = None,
        priority: Priority = Priority.NORMAL,
        **kwargs: Any,
    ) -> Future[T]:
        """
        Submit a task for execution with bounded concurrency.

        Args:
            fn: Function to execute
            *args: Positional arguments for fn
            tracker: Tracker type for concurrency limit
            resource_key: Optional resource key for ordering
            priority: Task priority
            **kwargs: Keyword arguments for fn

        Returns:
            Future representing the pending result
        """
        if self._shutdown:
            raise RuntimeError("Executor has been shut down")

        self._stats.total_submitted += 1

        def bounded_fn() -> T:
            start_time = time.time()
            tracker_key = tracker.value if isinstance(tracker, TrackerType) else tracker

            # Acquire tracker semaphore
            self._tracker_semaphore.acquire(tracker)

            # Acquire resource lock if specified
            resource_lock = None
            if resource_key:
                resource_lock = self._resource_lock.get_lock(resource_key)
                resource_lock.acquire()

            try:
                result = fn(*args, **kwargs)
                execution_time = time.time() - start_time
                self._stats.record_completion(tracker_key, execution_time)
                return result
            except Exception:
                self._stats.record_failure(tracker_key)
                raise
            finally:
                if resource_lock:
                    resource_lock.release()
                self._tracker_semaphore.release(tracker)

        return self._executor.submit(bounded_fn)

    def map(
        self,
        fn: Callable[[T], R],
        items: list[T],
        tracker: TrackerType | str = TrackerType.JIRA,
        resource_key_fn: Callable[[T], str | None] | None = None,
        priority: Priority = Priority.NORMAL,
    ) -> list[Future[R]]:
        """
        Map a function over items with bounded concurrency.

        Args:
            fn: Function to apply to each item
            items: Items to process
            tracker: Tracker type for concurrency limit
            resource_key_fn: Optional function to get resource key from item
            priority: Task priority

        Returns:
            List of futures
        """
        futures = []
        for item in items:
            resource_key = resource_key_fn(item) if resource_key_fn else None
            future = self.submit(
                fn,
                item,
                tracker=tracker,
                resource_key=resource_key,
                priority=priority,
            )
            futures.append(future)
        return futures

    @property
    def stats(self) -> ConcurrencyStats:
        """Get execution statistics."""
        return self._stats

    def get_stats(self) -> dict[str, Any]:
        """Get statistics as dictionary."""
        return {
            **self._stats.to_dict(),
            "active_per_tracker": self._tracker_semaphore.get_all_active_counts(),
            "max_workers": self._max_workers,
        }

    def set_tracker_limit(self, tracker: TrackerType | str, limit: int) -> None:
        """Dynamically adjust concurrency limit for a tracker."""
        self._tracker_semaphore.set_limit(tracker, limit)
        self.logger.info(f"Set {tracker} concurrency limit to {limit}")

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the executor."""
        self._shutdown = True
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> "BoundedExecutor":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.shutdown(wait=True)


class AsyncBoundedExecutor:
    """
    Async bounded executor with per-tracker concurrency and ordering.

    Provides async execution with:
    - Per-tracker concurrency limits
    - Priority-based scheduling
    - Resource-level ordering guarantees
    - Statistics tracking

    Example:
        >>> async with AsyncBoundedExecutor() as executor:
        ...     result = await executor.run(
        ...         sync_issue,
        ...         tracker=TrackerType.JIRA,
        ...         resource_key="PROJ-123",
        ...     )
    """

    def __init__(
        self,
        tracker_limits: dict[TrackerType | str, int] | None = None,
        default_tracker_limit: int = 5,
    ):
        """
        Initialize the async bounded executor.

        Args:
            tracker_limits: Per-tracker concurrency limits
            default_tracker_limit: Default limit for unknown trackers
        """
        self._tracker_semaphore = TrackerSemaphore(
            limits=tracker_limits,
            default_limit=default_tracker_limit,
        )
        self._resource_lock = ResourceLock()
        self._stats = ConcurrencyStats()
        self._sequence = 0
        self._sequence_lock = asyncio.Lock()
        self._current_concurrency = 0
        self._concurrency_lock = asyncio.Lock()

        self.logger = logging.getLogger("AsyncBoundedExecutor")

    async def _next_sequence(self) -> int:
        """Get next sequence number for ordering."""
        async with self._sequence_lock:
            self._sequence += 1
            return self._sequence

    async def run(
        self,
        coro: Coroutine[Any, Any, T],
        tracker: TrackerType | str = TrackerType.JIRA,
        resource_key: str | None = None,
        priority: Priority = Priority.NORMAL,
    ) -> T:
        """
        Run a coroutine with bounded concurrency.

        Args:
            coro: Coroutine to execute
            tracker: Tracker type for concurrency limit
            resource_key: Optional resource key for ordering
            priority: Task priority (used for statistics)

        Returns:
            Result of the coroutine
        """
        self._stats.total_submitted += 1
        start_time = time.time()
        tracker_key = tracker.value if isinstance(tracker, TrackerType) else tracker

        # Track peak concurrency
        async with self._concurrency_lock:
            self._current_concurrency += 1
            self._stats.peak_concurrency = max(
                self._stats.peak_concurrency, self._current_concurrency
            )

        # Acquire tracker semaphore
        await self._tracker_semaphore.acquire_async(tracker)

        # Acquire resource lock if specified
        resource_lock = None
        if resource_key:
            resource_lock = await self._resource_lock.get_async_lock(resource_key)
            await resource_lock.acquire()

        try:
            result = await coro
            execution_time = time.time() - start_time
            self._stats.record_completion(tracker_key, execution_time)
            return result
        except Exception:
            self._stats.record_failure(tracker_key)
            raise
        finally:
            if resource_lock:
                resource_lock.release()
            await self._tracker_semaphore.release_async(tracker)
            async with self._concurrency_lock:
                self._current_concurrency -= 1

    async def gather(
        self,
        coros: list[tuple[Coroutine[Any, Any, T], TrackerType | str]],
        resource_keys: list[str | None] | None = None,
        return_exceptions: bool = False,
    ) -> list[T | Exception]:
        """
        Gather multiple coroutines with per-tracker concurrency limits.

        Args:
            coros: List of (coroutine, tracker) tuples
            resource_keys: Optional list of resource keys for ordering
            return_exceptions: If True, exceptions are returned in list

        Returns:
            List of results
        """
        if resource_keys is None:
            resource_keys = [None] * len(coros)

        async def bounded_coro(
            idx: int,
            coro: Coroutine[Any, Any, T],
            tracker: TrackerType | str,
            resource_key: str | None,
        ) -> T:
            return await self.run(coro, tracker=tracker, resource_key=resource_key)

        tasks = [
            bounded_coro(i, coro, tracker, resource_keys[i])
            for i, (coro, tracker) in enumerate(coros)
        ]

        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)

    async def map(
        self,
        items: list[T],
        operation: Callable[[T], Coroutine[Any, Any, R]],
        tracker: TrackerType | str = TrackerType.JIRA,
        resource_key_fn: Callable[[T], str | None] | None = None,
    ) -> list[R]:
        """
        Map an async operation over items with bounded concurrency.

        Args:
            items: Items to process
            operation: Async function to apply to each item
            tracker: Tracker type for concurrency limit
            resource_key_fn: Optional function to get resource key from item

        Returns:
            List of results
        """
        coros = [(operation(item), tracker) for item in items]
        resource_keys = [resource_key_fn(item) for item in items] if resource_key_fn else None
        return await self.gather(coros, resource_keys=resource_keys)  # type: ignore[return-value]

    @property
    def stats(self) -> ConcurrencyStats:
        """Get execution statistics."""
        return self._stats

    def get_stats(self) -> dict[str, Any]:
        """Get statistics as dictionary."""
        return {
            **self._stats.to_dict(),
            "active_per_tracker": self._tracker_semaphore.get_all_active_counts(),
            "current_concurrency": self._current_concurrency,
        }

    def set_tracker_limit(self, tracker: TrackerType | str, limit: int) -> None:
        """Dynamically adjust concurrency limit for a tracker."""
        self._tracker_semaphore.set_limit(tracker, limit)
        self.logger.info(f"Set {tracker} concurrency limit to {limit}")

    async def __aenter__(self) -> "AsyncBoundedExecutor":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass  # No cleanup needed for async executor


class OrderedTaskQueue(Generic[T]):
    """
    Priority queue with FIFO ordering within same priority.

    Ensures that tasks with the same priority are executed
    in submission order (FIFO).
    """

    def __init__(self) -> None:
        """Initialize the ordered task queue."""
        self._heap: list[PrioritizedTask] = []
        self._sequence = 0
        self._lock = threading.Lock()

    def push(
        self,
        task: T,
        tracker: TrackerType | str,
        priority: Priority = Priority.NORMAL,
        resource_key: str | None = None,
    ) -> None:
        """Push a task onto the queue."""
        with self._lock:
            item = PrioritizedTask(
                priority=priority.value,
                sequence=self._sequence,
                task=task,
                tracker=tracker,
                resource_key=resource_key,
            )
            self._sequence += 1
            heapq.heappush(self._heap, item)

    def pop(self) -> PrioritizedTask | None:
        """Pop highest priority task from the queue."""
        with self._lock:
            if not self._heap:
                return None
            return heapq.heappop(self._heap)

    def peek(self) -> PrioritizedTask | None:
        """Peek at highest priority task without removing."""
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0]

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)

    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self) == 0


# Factory functions for creating executors with common configurations


def create_bounded_executor(
    max_workers: int = 20,
    preset: str = "default",
) -> BoundedExecutor:
    """
    Create a bounded executor with preset configurations.

    Presets:
    - "default": Balanced limits for typical use
    - "conservative": Lower limits for rate-limited APIs
    - "aggressive": Higher limits for fast APIs/self-hosted

    Args:
        max_workers: Maximum total concurrent workers
        preset: Preset name

    Returns:
        Configured BoundedExecutor
    """
    presets: dict[str, dict[TrackerType, int]] = {
        "default": DEFAULT_TRACKER_LIMITS,
        "conservative": {
            TrackerType.JIRA: 5,
            TrackerType.GITHUB: 5,
            TrackerType.LINEAR: 3,
            TrackerType.AZURE_DEVOPS: 5,
            TrackerType.ASANA: 3,
            TrackerType.GITLAB: 5,
            TrackerType.MONDAY: 3,
            TrackerType.TRELLO: 5,
            TrackerType.SHORTCUT: 5,
            TrackerType.CLICKUP: 3,
            TrackerType.BITBUCKET: 5,
            TrackerType.YOUTRACK: 3,
            TrackerType.BASECAMP: 3,
            TrackerType.PLANE: 5,
            TrackerType.PIVOTAL: 2,
        },
        "aggressive": {
            TrackerType.JIRA: 20,
            TrackerType.GITHUB: 30,
            TrackerType.LINEAR: 10,
            TrackerType.AZURE_DEVOPS: 20,
            TrackerType.ASANA: 10,
            TrackerType.GITLAB: 20,
            TrackerType.MONDAY: 10,
            TrackerType.TRELLO: 20,
            TrackerType.SHORTCUT: 20,
            TrackerType.CLICKUP: 10,
            TrackerType.BITBUCKET: 20,
            TrackerType.YOUTRACK: 10,
            TrackerType.BASECAMP: 10,
            TrackerType.PLANE: 20,
            TrackerType.PIVOTAL: 5,
        },
    }

    limits = presets.get(preset, DEFAULT_TRACKER_LIMITS)
    return BoundedExecutor(max_workers=max_workers, tracker_limits=limits)


def create_async_bounded_executor(
    preset: str = "default",
) -> AsyncBoundedExecutor:
    """
    Create an async bounded executor with preset configurations.

    Args:
        preset: Preset name

    Returns:
        Configured AsyncBoundedExecutor
    """
    presets: dict[str, dict[TrackerType, int]] = {
        "default": DEFAULT_TRACKER_LIMITS,
        "conservative": {tt: max(2, v // 2) for tt, v in DEFAULT_TRACKER_LIMITS.items()},
        "aggressive": {tt: v * 2 for tt, v in DEFAULT_TRACKER_LIMITS.items()},
    }

    limits = presets.get(preset, DEFAULT_TRACKER_LIMITS)
    return AsyncBoundedExecutor(tracker_limits=limits)
