"""
Cache - Caching infrastructure for lazy-loaded fields.

Provides field-level caching with TTL support for lazy-loaded data.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, cast


T = TypeVar("T")


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_load_time_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def average_load_time_ms(self) -> float:
        """Calculate average load time for misses."""
        return self.total_load_time_ms / self.misses if self.misses > 0 else 0.0

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self, load_time_ms: float) -> None:
        """Record a cache miss with load time."""
        self.misses += 1
        self.total_load_time_ms += load_time_ms

    def record_eviction(self) -> None:
        """Record a cache eviction."""
        self.evictions += 1


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with TTL support."""

    value: T
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    ttl_seconds: float | None = None

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """Update last access time."""
        self.accessed_at = time.time()


class FieldCache:
    """
    Thread-safe cache for lazy-loaded fields.

    Features:
    - Per-field caching with TTL
    - LRU eviction when max size reached
    - Statistics tracking
    - Thread-safe operations

    Usage:
        cache = FieldCache(max_size=1000, default_ttl=300)

        # Store value
        cache.set("story:123:comments", comments)

        # Get value
        comments = cache.get("story:123:comments")

        # Get or load
        comments = cache.get_or_load(
            "story:123:comments",
            lambda: fetch_comments("123")
        )
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float | None = 300.0,
        cleanup_interval: int = 100,
    ):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds (None = no expiry)
            cleanup_interval: Run cleanup every N operations
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval

        self._cache: dict[str, CacheEntry[Any]] = {}
        self._lock = threading.RLock()
        self._stats = CacheStats()
        self._operation_count = 0

    def get(self, key: str) -> Any | None:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.is_expired:
                del self._cache[key]
                self._stats.record_eviction()
                return None

            entry.touch()
            self._stats.record_hit()
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """
        Store a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = use default)
        """
        with self._lock:
            self._maybe_cleanup()

            if len(self._cache) >= self.max_size:
                self._evict_lru()

            self._cache[key] = CacheEntry(
                value=value,
                ttl_seconds=ttl if ttl is not None else self.default_ttl,
            )

    def get_or_load(
        self,
        key: str,
        loader: Callable[[], T],
        ttl: float | None = None,
    ) -> T:
        """
        Get from cache or load if not present.

        Args:
            key: Cache key
            loader: Function to call if not cached
            ttl: TTL for the loaded value

        Returns:
            Cached or freshly loaded value
        """
        # Check cache first
        cached_value = self.get(key)
        if cached_value is not None:
            return cast(T, cached_value)

        # Load and cache
        start_time = time.time()
        value = loader()
        load_time_ms = (time.time() - start_time) * 1000

        self.set(key, value, ttl)
        self._stats.record_miss(load_time_ms)

        return value

    def invalidate(self, key: str) -> bool:
        """
        Remove a key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was present
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Remove all keys with given prefix.

        Args:
            prefix: Key prefix to match

        Returns:
            Number of keys removed
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        """Current cache size."""
        with self._lock:
            return len(self._cache)

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def _maybe_cleanup(self) -> None:
        """Periodically clean up expired entries."""
        self._operation_count += 1
        if self._operation_count >= self.cleanup_interval:
            self._operation_count = 0
            self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for key in expired:
            del self._cache[key]
            self._stats.record_eviction()

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].accessed_at)
        del self._cache[lru_key]
        self._stats.record_eviction()


# Global cache instance for shared use
_global_cache: FieldCache | None = None
_cache_lock = threading.Lock()


def get_global_cache() -> FieldCache:
    """Get or create the global field cache."""
    global _global_cache
    with _cache_lock:
        if _global_cache is None:
            _global_cache = FieldCache()
        return _global_cache


def set_global_cache(cache: FieldCache) -> None:
    """Set the global field cache."""
    global _global_cache
    with _cache_lock:
        _global_cache = cache
