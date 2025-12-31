"""
Memory Optimization - Utilities for reducing memory footprint.

Provides tools for memory-efficient operations:
- ObjectPool: Reuse frequently created objects
- WeakRefCache: Cache with automatic garbage collection
- SlotsDataclass: Mixin for memory-efficient dataclasses
- MemoryTracker: Monitor memory usage
- CompactString: Interned strings for deduplication
- LazyLoader: Delay object creation until needed
- ChunkedList: Memory-efficient large list handling

Example:
    >>> from spectra.core.memory import ObjectPool, MemoryTracker
    >>>
    >>> # Object pooling for frequently created objects
    >>> pool = ObjectPool(factory=dict, max_size=100)
    >>> obj = pool.acquire()
    >>> pool.release(obj)
    >>>
    >>> # Track memory usage
    >>> with MemoryTracker("parse_stories") as tracker:
    ...     result = parser.parse(content)
    >>> print(f"Used {tracker.peak_mb:.2f} MB")
"""

from __future__ import annotations

import gc
import logging
import sys
import threading
import weakref
from collections import deque
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, TypeVar


try:
    import tracemalloc

    HAS_TRACEMALLOC = True
except ImportError:
    HAS_TRACEMALLOC = False


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


# =============================================================================
# String Interning
# =============================================================================


class CompactString:
    """
    String interning for memory deduplication.

    Interns frequently used strings to avoid duplicate allocations.
    Useful for repeated field values like status names, priorities, etc.

    Example:
        >>> intern = CompactString()
        >>> s1 = intern("IN_PROGRESS")
        >>> s2 = intern("IN_PROGRESS")
        >>> assert s1 is s2  # Same object
    """

    __slots__ = ("_cache", "_hits", "_lock", "_max_size", "_misses")

    def __init__(self, max_size: int = 10000):
        """
        Initialize string interning cache.

        Args:
            max_size: Maximum number of strings to cache
        """
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def __call__(self, s: str) -> str:
        """Intern a string."""
        if not isinstance(s, str):
            return s  # type: ignore[return-value]

        # Short strings are always interned by Python
        if len(s) <= 20:
            return sys.intern(s)

        with self._lock:
            if s in self._cache:
                self._hits += 1
                return self._cache[s]

            self._misses += 1

            # Evict if at capacity (simple FIFO)
            if len(self._cache) >= self._max_size:
                # Remove first 10% to avoid frequent evictions
                to_remove = max(1, self._max_size // 10)
                keys = list(self._cache.keys())[:to_remove]
                for key in keys:
                    del self._cache[key]

            self._cache[s] = s
            return s

    def intern_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        """Intern all string values in a dictionary."""
        return {
            self(k) if isinstance(k, str) else k: self(v) if isinstance(v, str) else v
            for k, v in d.items()
        }

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        """Get number of interned strings."""
        return len(self._cache)

    def clear(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get interning statistics."""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


# Global string interner for common values
_global_interner = CompactString(max_size=5000)


def intern_string(s: str) -> str:
    """Intern a string using the global interner."""
    return _global_interner(s)


# =============================================================================
# Object Pooling
# =============================================================================


class ObjectPool(Generic[T]):
    """
    Object pool for reusing frequently created objects.

    Reduces allocation overhead by reusing objects instead of
    creating new ones. Objects are reset before being returned.

    Example:
        >>> pool = ObjectPool(factory=dict, reset_fn=dict.clear, max_size=100)
        >>> obj = pool.acquire()
        >>> obj["key"] = "value"
        >>> pool.release(obj)  # Object is cleared and returned to pool
    """

    __slots__ = (
        "_acquired",
        "_created",
        "_factory",
        "_lock",
        "_max_size",
        "_pool",
        "_reset_fn",
        "_reused",
    )

    def __init__(
        self,
        factory: Callable[[], T],
        reset_fn: Callable[[T], None] | None = None,
        max_size: int = 100,
    ):
        """
        Initialize object pool.

        Args:
            factory: Function to create new objects
            reset_fn: Function to reset an object before reuse
            max_size: Maximum pool size
        """
        self._factory = factory
        self._reset_fn = reset_fn
        self._pool: deque[T] = deque(maxlen=max_size)
        self._max_size = max_size
        self._lock = threading.Lock()
        self._acquired = 0
        self._created = 0
        self._reused = 0

    def acquire(self) -> T:
        """
        Acquire an object from the pool.

        Returns a pooled object if available, otherwise creates a new one.
        """
        with self._lock:
            self._acquired += 1
            if self._pool:
                self._reused += 1
                return self._pool.pop()

            self._created += 1
            return self._factory()

    def release(self, obj: T) -> None:
        """
        Release an object back to the pool.

        The object is reset and made available for future use.
        """
        if self._reset_fn:
            self._reset_fn(obj)

        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)

    @contextmanager
    def borrow(self) -> Generator[T, None, None]:
        """
        Context manager for borrowing an object.

        Automatically releases the object when done.

        Example:
            >>> with pool.borrow() as obj:
            ...     obj["key"] = "value"
            ...     # Object is automatically released
        """
        obj = self.acquire()
        try:
            yield obj
        finally:
            self.release(obj)

    @property
    def available(self) -> int:
        """Number of objects available in the pool."""
        return len(self._pool)

    @property
    def reuse_rate(self) -> float:
        """Get object reuse rate."""
        return self._reused / self._acquired if self._acquired > 0 else 0.0

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "acquired": self._acquired,
            "created": self._created,
            "reused": self._reused,
            "available": self.available,
            "max_size": self._max_size,
            "reuse_rate": self.reuse_rate,
        }

    def clear(self) -> None:
        """Clear the pool."""
        with self._lock:
            self._pool.clear()


# =============================================================================
# Weak Reference Cache
# =============================================================================


class WeakRefCache(Generic[K, V]):
    """
    Cache using weak references for automatic cleanup.

    Cached values are automatically removed when no other references exist.
    Useful for caching expensive-to-compute values without preventing GC.

    Example:
        >>> cache = WeakRefCache()
        >>> class Heavy: pass
        >>> obj = Heavy()
        >>> cache.set("key", obj)
        >>> assert cache.get("key") is obj
        >>> del obj
        >>> # After GC, cache entry is automatically removed
    """

    __slots__ = ("_cache", "_hits", "_lock", "_misses")

    def __init__(self) -> None:
        self._cache: dict[K, weakref.ref[V]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> V | None:
        """Get a value from the cache."""
        with self._lock:
            ref = self._cache.get(key)
            if ref is None:
                self._misses += 1
                return None

            value = ref()
            if value is None:
                # Reference was garbage collected
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            return value

    def set(self, key: K, value: V) -> None:
        """Set a value in the cache."""

        def cleanup(_: weakref.ref[V]) -> None:
            """Remove key when value is garbage collected."""
            with self._lock:
                self._cache.pop(key, None)

        with self._lock:
            self._cache[key] = weakref.ref(value, cleanup)

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        """Get a value or create it if not cached."""
        value = self.get(key)
        if value is not None:
            return value

        value = factory()
        self.set(key, value)
        return value

    def delete(self, key: K) -> bool:
        """Delete a key from the cache."""
        with self._lock:
            return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Number of entries in cache (may include dead refs)."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def cleanup(self) -> int:
        """Remove dead references and return count removed."""
        removed = 0
        with self._lock:
            dead_keys = [k for k, ref in self._cache.items() if ref() is None]
            for key in dead_keys:
                del self._cache[key]
                removed += 1
        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }


# =============================================================================
# Lazy Loading
# =============================================================================


class LazyLoader(Generic[T]):
    """
    Lazy object loader - delays creation until first access.

    Useful for expensive objects that may not be needed.

    Example:
        >>> loader = LazyLoader(lambda: expensive_computation())
        >>> # Object not created yet
        >>> value = loader.value  # Now it's created
        >>> value2 = loader.value  # Returns cached value
    """

    __slots__ = ("_factory", "_loaded", "_lock", "_value")

    def __init__(self, factory: Callable[[], T]):
        """
        Initialize lazy loader.

        Args:
            factory: Function to create the object when needed
        """
        self._factory = factory
        self._value: T | None = None
        self._loaded = False
        self._lock = threading.Lock()

    @property
    def value(self) -> T:
        """Get the value, creating it if necessary."""
        if self._loaded:
            return self._value  # type: ignore[return-value]

        with self._lock:
            if not self._loaded:
                self._value = self._factory()
                self._loaded = True

        return self._value  # type: ignore[return-value]

    @property
    def is_loaded(self) -> bool:
        """Check if the value has been loaded."""
        return self._loaded

    def reset(self) -> None:
        """Reset the loader to unloaded state."""
        with self._lock:
            self._value = None
            self._loaded = False

    def __repr__(self) -> str:
        status = "loaded" if self._loaded else "not loaded"
        return f"LazyLoader({status})"


# =============================================================================
# Chunked List
# =============================================================================


class ChunkedList(Generic[T]):
    """
    Memory-efficient list for large collections.

    Stores items in fixed-size chunks to reduce memory fragmentation
    and allow partial garbage collection.

    Example:
        >>> items = ChunkedList(chunk_size=1000)
        >>> for i in range(10000):
        ...     items.append(i)
        >>> items.clear_chunk(0)  # Free first chunk
    """

    __slots__ = ("_chunk_size", "_chunks", "_length")

    def __init__(self, chunk_size: int = 1000):
        """
        Initialize chunked list.

        Args:
            chunk_size: Number of items per chunk
        """
        self._chunks: list[list[T]] = [[]]
        self._chunk_size = chunk_size
        self._length = 0

    def append(self, item: T) -> None:
        """Append an item to the list."""
        current_chunk = self._chunks[-1]
        if len(current_chunk) >= self._chunk_size:
            self._chunks.append([])
            current_chunk = self._chunks[-1]
        current_chunk.append(item)
        self._length += 1

    def extend(self, items: list[T]) -> None:
        """Extend the list with multiple items."""
        for item in items:
            self.append(item)

    def __getitem__(self, index: int) -> T:
        """Get item by index."""
        if index < 0:
            index = self._length + index
        if index < 0 or index >= self._length:
            raise IndexError("list index out of range")

        chunk_idx = index // self._chunk_size
        item_idx = index % self._chunk_size
        return self._chunks[chunk_idx][item_idx]

    def __len__(self) -> int:
        return self._length

    def __iter__(self) -> Iterator[T]:
        """Iterate over all items."""
        for chunk in self._chunks:
            yield from chunk

    def clear_chunk(self, chunk_index: int) -> None:
        """Clear a specific chunk to free memory."""
        if 0 <= chunk_index < len(self._chunks):
            chunk_size = len(self._chunks[chunk_index])
            self._chunks[chunk_index] = []
            self._length -= chunk_size

    def clear(self) -> None:
        """Clear all items."""
        self._chunks = [[]]
        self._length = 0

    @property
    def num_chunks(self) -> int:
        """Get number of chunks."""
        return len(self._chunks)

    def get_stats(self) -> dict[str, Any]:
        """Get list statistics."""
        return {
            "length": self._length,
            "chunk_size": self._chunk_size,
            "num_chunks": self.num_chunks,
            "memory_estimate_bytes": self._estimate_memory(),
        }

    def _estimate_memory(self) -> int:
        """Estimate memory usage in bytes."""
        # Rough estimate: object overhead + list overhead + items
        overhead = sys.getsizeof(self) + sys.getsizeof(self._chunks)
        chunk_overhead = sum(sys.getsizeof(chunk) for chunk in self._chunks)
        return overhead + chunk_overhead


# =============================================================================
# Memory Tracking
# =============================================================================


@dataclass
class MemorySnapshot:
    """Snapshot of memory usage at a point in time."""

    timestamp: float
    rss_bytes: int  # Resident Set Size
    vms_bytes: int  # Virtual Memory Size
    tracemalloc_bytes: int | None  # Allocated by Python (if tracemalloc enabled)

    @property
    def rss_mb(self) -> float:
        """RSS in megabytes."""
        return self.rss_bytes / (1024 * 1024)

    @property
    def vms_mb(self) -> float:
        """VMS in megabytes."""
        return self.vms_bytes / (1024 * 1024)


@dataclass
class MemoryStats:
    """Statistics from memory tracking."""

    operation: str
    start_rss_mb: float
    end_rss_mb: float
    peak_rss_mb: float
    allocated_mb: float | None  # From tracemalloc if available
    duration_seconds: float
    gc_collections: tuple[int, int, int]  # Gen 0, 1, 2 collections

    @property
    def delta_mb(self) -> float:
        """Change in RSS memory."""
        return self.end_rss_mb - self.start_rss_mb


class MemoryTracker:
    """
    Track memory usage during operations.

    Uses psutil if available for accurate measurements,
    falls back to gc module otherwise.

    Example:
        >>> with MemoryTracker("parse_large_file") as tracker:
        ...     result = parse_file(path)
        >>> print(f"Peak: {tracker.peak_mb:.2f} MB")
        >>> print(f"Delta: {tracker.delta_mb:.2f} MB")
    """

    __slots__ = (
        "_duration",
        "_end_gc_counts",
        "_end_snapshot",
        "_operation",
        "_peak_rss",
        "_start_gc_counts",
        "_start_snapshot",
        "_tracemalloc_peak",
        "_tracemalloc_start",
        "logger",
    )

    def __init__(self, operation: str = "operation"):
        """
        Initialize memory tracker.

        Args:
            operation: Name of the operation being tracked
        """
        self._operation = operation
        self._start_snapshot: MemorySnapshot | None = None
        self._end_snapshot: MemorySnapshot | None = None
        self._peak_rss: int = 0
        self._start_gc_counts: tuple[int, int, int] = (0, 0, 0)
        self._end_gc_counts: tuple[int, int, int] = (0, 0, 0)
        self._tracemalloc_start: int = 0
        self._tracemalloc_peak: int = 0
        self._duration: float = 0.0
        self.logger = logging.getLogger("MemoryTracker")

    def _get_memory_info(self) -> tuple[int, int]:
        """Get current RSS and VMS memory."""
        try:
            import psutil

            process = psutil.Process()
            info = process.memory_info()
            return info.rss, info.vms
        except ImportError:
            # Fallback: estimate from gc
            gc.collect()
            # Very rough estimate
            return 0, 0

    def _take_snapshot(self) -> MemorySnapshot:
        """Take a memory snapshot."""
        import time

        rss, vms = self._get_memory_info()
        tracemalloc_bytes = None

        if HAS_TRACEMALLOC and tracemalloc.is_tracing():
            current, _peak = tracemalloc.get_traced_memory()
            tracemalloc_bytes = current

        return MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=rss,
            vms_bytes=vms,
            tracemalloc_bytes=tracemalloc_bytes,
        )

    def __enter__(self) -> MemoryTracker:
        """Start tracking memory."""
        # Force GC before measurement
        gc.collect()

        self._start_gc_counts = tuple(gc.get_count())  # type: ignore[assignment]
        self._start_snapshot = self._take_snapshot()
        self._peak_rss = self._start_snapshot.rss_bytes

        if HAS_TRACEMALLOC:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
            tracemalloc.reset_peak()
            self._tracemalloc_start, _ = tracemalloc.get_traced_memory()

        return self

    def __exit__(self, *args: Any) -> None:
        """Stop tracking and compute stats."""
        gc.collect()

        self._end_snapshot = self._take_snapshot()
        self._end_gc_counts = tuple(gc.get_count())  # type: ignore[assignment]

        if self._start_snapshot:
            self._duration = self._end_snapshot.timestamp - self._start_snapshot.timestamp

        # Get peak from tracemalloc if available
        if HAS_TRACEMALLOC and tracemalloc.is_tracing():
            _, self._tracemalloc_peak = tracemalloc.get_traced_memory()

        # Update peak RSS
        current_rss = self._end_snapshot.rss_bytes
        self._peak_rss = max(self._peak_rss, current_rss)

    @property
    def start_mb(self) -> float:
        """Starting RSS in MB."""
        return self._start_snapshot.rss_mb if self._start_snapshot else 0.0

    @property
    def end_mb(self) -> float:
        """Ending RSS in MB."""
        return self._end_snapshot.rss_mb if self._end_snapshot else 0.0

    @property
    def peak_mb(self) -> float:
        """Peak RSS in MB."""
        return self._peak_rss / (1024 * 1024)

    @property
    def delta_mb(self) -> float:
        """Change in RSS memory."""
        return self.end_mb - self.start_mb

    @property
    def allocated_mb(self) -> float | None:
        """Allocated memory from tracemalloc (if available)."""
        if self._tracemalloc_peak:
            return self._tracemalloc_peak / (1024 * 1024)
        return None

    @property
    def gc_collections(self) -> tuple[int, int, int]:
        """Number of GC collections (gen 0, 1, 2) during tracking."""
        return (
            self._end_gc_counts[0] - self._start_gc_counts[0],
            self._end_gc_counts[1] - self._start_gc_counts[1],
            self._end_gc_counts[2] - self._start_gc_counts[2],
        )

    def get_stats(self) -> MemoryStats:
        """Get memory statistics."""
        return MemoryStats(
            operation=self._operation,
            start_rss_mb=self.start_mb,
            end_rss_mb=self.end_mb,
            peak_rss_mb=self.peak_mb,
            allocated_mb=self.allocated_mb,
            duration_seconds=self._duration,
            gc_collections=self.gc_collections,
        )

    def log_summary(self) -> None:
        """Log a summary of memory usage."""
        stats = self.get_stats()
        self.logger.info(
            f"Memory [{self._operation}]: "
            f"delta={stats.delta_mb:+.2f}MB, "
            f"peak={stats.peak_rss_mb:.2f}MB, "
            f"duration={stats.duration_seconds:.2f}s"
        )


# =============================================================================
# Size Estimation
# =============================================================================


def sizeof_deep(obj: Any, seen: set[int] | None = None) -> int:
    """
    Recursively calculate the deep size of an object.

    Traverses all references to compute total memory usage.

    Args:
        obj: Object to measure
        seen: Set of already-seen object IDs (for cycle detection)

    Returns:
        Total size in bytes
    """
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0

    seen.add(obj_id)
    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        size += sum(sizeof_deep(k, seen) + sizeof_deep(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        size += sum(sizeof_deep(item, seen) for item in obj)
    elif hasattr(obj, "__dict__"):
        size += sizeof_deep(obj.__dict__, seen)
    elif hasattr(obj, "__slots__"):
        size += sum(
            sizeof_deep(getattr(obj, slot, None), seen)
            for slot in obj.__slots__
            if hasattr(obj, slot)
        )

    return size


def format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024  # type: ignore[assignment]
    return f"{num_bytes:.2f} TB"


# =============================================================================
# Compact Dataclass Helpers
# =============================================================================


def make_slots_dataclass(cls: type[T]) -> type[T]:
    """
    Decorator to add __slots__ to a dataclass for memory efficiency.

    Note: This only works for simple dataclasses without inheritance.
    For complex hierarchies, manually define __slots__.

    Example:
        >>> @make_slots_dataclass
        ... @dataclass
        ... class Point:
        ...     x: float
        ...     y: float
    """
    if not hasattr(cls, "__dataclass_fields__"):
        raise TypeError(f"{cls.__name__} must be a dataclass")

    # Get field names
    field_names = tuple(cls.__dataclass_fields__.keys())

    # Create new class with slots
    class SlotClass(cls):  # type: ignore[valid-type,misc]
        __slots__ = field_names

    SlotClass.__name__ = cls.__name__
    SlotClass.__qualname__ = cls.__qualname__
    SlotClass.__module__ = cls.__module__

    return SlotClass  # type: ignore[return-value]


# =============================================================================
# Memory-Efficient LRU Cache
# =============================================================================


def bounded_lru_cache(
    maxsize: int = 128, typed: bool = False
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    LRU cache decorator with bounded memory and cache info.

    Like functools.lru_cache but with explicit bounds and
    easier cache management.

    Example:
        >>> @bounded_lru_cache(maxsize=100)
        ... def expensive_fn(x: int) -> int:
        ...     return x ** 2
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cached = lru_cache(maxsize=maxsize, typed=typed)(func)

        # Add a method to get memory estimate
        def cache_memory_estimate() -> int:
            """Estimate memory used by cache."""
            info = cached.cache_info()
            # Very rough estimate: assume each entry is ~500 bytes
            return info.currsize * 500

        cached.cache_memory_estimate = cache_memory_estimate  # type: ignore[attr-defined]
        return cached

    return decorator


# =============================================================================
# Garbage Collection Helpers
# =============================================================================


def force_gc() -> dict[str, Any]:
    """
    Force garbage collection and return stats.

    Returns:
        Dictionary with collection counts and freed objects
    """
    before = gc.get_count()
    collected = gc.collect()
    after = gc.get_count()

    return {
        "collected": collected,
        "before": before,
        "after": after,
        "freed_gen0": before[0] - after[0],
        "freed_gen1": before[1] - after[1],
        "freed_gen2": before[2] - after[2],
    }


def gc_threshold_tuning(gen0: int = 700, gen1: int = 10, gen2: int = 10) -> None:
    """
    Tune GC thresholds for better performance.

    Default Python thresholds (700, 10, 10) may not be optimal
    for applications with many short-lived objects.

    Args:
        gen0: Threshold for generation 0 (default 700)
        gen1: Threshold for generation 1 (default 10)
        gen2: Threshold for generation 2 (default 10)
    """
    gc.set_threshold(gen0, gen1, gen2)


# =============================================================================
# Exports
# =============================================================================


__all__ = [
    "ChunkedList",
    "CompactString",
    "LazyLoader",
    "MemorySnapshot",
    "MemoryStats",
    "MemoryTracker",
    "ObjectPool",
    "WeakRefCache",
    "bounded_lru_cache",
    "force_gc",
    "format_bytes",
    "gc_threshold_tuning",
    "intern_string",
    "make_slots_dataclass",
    "sizeof_deep",
]
