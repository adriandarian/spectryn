"""
Memory Cache - In-memory LRU cache with TTL support.

Fast, thread-safe in-memory cache using an LRU eviction policy.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, TypeVar

from .backend import CacheBackend, CacheEntry, CacheStats


T = TypeVar("T")


class MemoryCache(CacheBackend):
    """
    In-memory LRU cache with TTL support.

    Features:
    - LRU (Least Recently Used) eviction when max_size is reached
    - Per-entry TTL (time-to-live) for automatic expiration
    - Tag-based group invalidation
    - Thread-safe operations
    - Statistics tracking

    Example:
        >>> cache = MemoryCache(max_size=1000, default_ttl=300)
        >>> cache.set("user:123", {"name": "Alice"}, ttl=600)
        >>> user = cache.get("user:123")
        >>> print(cache.get_stats().hit_rate)
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float | None = 300.0,  # 5 minutes default
        cleanup_interval: float = 60.0,  # Clean expired entries every 60s
    ):
        """
        Initialize the memory cache.

        Args:
            max_size: Maximum number of entries before LRU eviction
            default_ttl: Default TTL in seconds (None = no expiry)
            cleanup_interval: How often to clean expired entries (seconds)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval

        # OrderedDict maintains insertion order for LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._tags: dict[str, set[str]] = {}  # tag -> set of keys
        self._lock = threading.RLock()
        self._stats = CacheStats()
        self._last_cleanup = time.time()

        self.logger = logging.getLogger("MemoryCache")

    def get(self, key: str) -> Any | None:
        """
        Get a value from the cache.

        Moves the accessed entry to the end (most recently used).
        Returns None if not found or expired.
        """
        with self._lock:
            self._maybe_cleanup()

            entry = self._cache.get(key)
            if entry is None:
                self._stats.record_miss()
                return None

            # Check expiration
            if entry.is_expired:
                self._delete_entry(key)
                self._stats.record_expiration()
                self._stats.record_miss()
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.record_hit()
            self._stats.record_hit()

            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """
        Set a value in the cache.

        If max_size is reached, evicts least recently used entries.
        """
        with self._lock:
            self._maybe_cleanup()

            # Determine TTL
            if ttl is None:
                ttl = self.default_ttl

            expires_at = None
            if ttl is not None:
                expires_at = time.time() + ttl

            # Create entry
            entry = CacheEntry(
                value=value,
                expires_at=expires_at,
                tags=tags or set(),
            )

            # If key exists, delete old entry first (for tag cleanup)
            if key in self._cache:
                self._delete_entry(key)

            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                self._evict_lru()

            # Add new entry
            self._cache[key] = entry
            self._cache.move_to_end(key)

            # Update tag index
            for tag in entry.tags:
                if tag not in self._tags:
                    self._tags[tag] = set()
                self._tags[tag].add(key)

            self._stats.record_set()

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        with self._lock:
            if key not in self._cache:
                return False

            self._delete_entry(key)
            self._stats.record_delete()
            return True

    def exists(self, key: str) -> bool:
        """Check if a key exists and is not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False

            if entry.is_expired:
                self._delete_entry(key)
                self._stats.record_expiration()
                return False

            return True

    def clear(self) -> int:
        """Clear all entries from the cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._tags.clear()
            return count

    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all entries with a given tag."""
        with self._lock:
            keys = self._tags.get(tag, set()).copy()
            count = 0
            for key in keys:
                if self._delete_entry(key):
                    count += 1

            # Remove the tag
            self._tags.pop(tag, None)

            return count

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """Get the current number of entries in the cache."""
        with self._lock:
            return len(self._cache)

    def _delete_entry(self, key: str) -> bool:
        """Delete an entry and clean up tags. Must hold lock."""
        entry = self._cache.pop(key, None)
        if entry is None:
            return False

        # Remove from tag index
        for tag in entry.tags:
            if tag in self._tags:
                self._tags[tag].discard(key)
                if not self._tags[tag]:
                    del self._tags[tag]

        return True

    def _evict_lru(self) -> None:
        """Evict the least recently used entry. Must hold lock."""
        if not self._cache:
            return

        # First item is least recently used
        key = next(iter(self._cache))
        self._delete_entry(key)
        self._stats.record_eviction()
        self.logger.debug(f"Evicted LRU entry: {key}")

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed. Must hold lock."""
        now = time.time()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        self._last_cleanup = now
        self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        """Remove all expired entries. Must hold lock."""
        expired_keys = [key for key, entry in self._cache.items() if entry.is_expired]

        for key in expired_keys:
            self._delete_entry(key)
            self._stats.record_expiration()

        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

    def get_entry(self, key: str) -> CacheEntry | None:
        """
        Get the full cache entry with metadata.

        Unlike get(), does not update LRU order or record stats.
        """
        with self._lock:
            return self._cache.get(key)

    def keys(self) -> list[str]:
        """Get all keys in the cache (including expired)."""
        with self._lock:
            return list(self._cache.keys())

    def items(self) -> list[tuple[str, Any]]:
        """Get all valid (non-expired) items."""
        with self._lock:
            return [
                (key, entry.value) for key, entry in self._cache.items() if not entry.is_expired
            ]
