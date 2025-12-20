"""
Cache Backend - Abstract interface for cache storage.

Defines the contract that all cache implementations must follow.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar


T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """
    A cached value with metadata.

    Attributes:
        value: The cached data
        created_at: Unix timestamp when entry was created
        expires_at: Unix timestamp when entry expires (None = never)
        tags: Optional tags for group invalidation
        hit_count: Number of times this entry was accessed
    """

    value: T
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    tags: set[str] = field(default_factory=set)
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> float | None:
        """Get remaining TTL in seconds, or None if no expiry."""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - time.time()
        return max(0, remaining)

    @property
    def age(self) -> float:
        """Get age of entry in seconds."""
        return time.time() - self.created_at

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hit_count += 1


@dataclass
class CacheStats:
    """
    Cache statistics.

    Tracks hits, misses, and other cache metrics.
    """

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    expirations: int = 0

    @property
    def total_requests(self) -> int:
        """Total number of get requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self.total_requests
        if total == 0:
            return 0.0
        return self.hits / total

    @property
    def miss_rate(self) -> float:
        """Cache miss rate (0.0 to 1.0)."""
        return 1.0 - self.hit_rate

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    def record_set(self) -> None:
        """Record a cache set."""
        self.sets += 1

    def record_delete(self) -> None:
        """Record a cache delete."""
        self.deletes += 1

    def record_eviction(self) -> None:
        """Record an eviction (due to size limits)."""
        self.evictions += 1

    def record_expiration(self) -> None:
        """Record an expiration."""
        self.expirations += 1

    def reset(self) -> None:
        """Reset all statistics."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.evictions = 0
        self.expirations = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "total_requests": self.total_requests,
            "hit_rate": round(self.hit_rate, 4),
        }


class CacheBackend(ABC):
    """
    Abstract cache backend interface.

    All cache implementations must implement this interface.
    Supports:
    - Key-value storage with optional TTL
    - Tag-based invalidation
    - Statistics tracking
    """

    @abstractmethod
    def get(self, key: str) -> T | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value, or None if not found or expired
        """
        ...

    @abstractmethod
    def set(
        self,
        key: str,
        value: T,
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = use default)
            tags: Optional tags for group invalidation
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if a key exists and is not expired.

        Args:
            key: Cache key

        Returns:
            True if key exists and is valid
        """
        ...

    @abstractmethod
    def clear(self) -> int:
        """
        Clear all entries from the cache.

        Returns:
            Number of entries cleared
        """
        ...

    @abstractmethod
    def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all entries with a given tag.

        Args:
            tag: Tag to match

        Returns:
            Number of entries invalidated
        """
        ...

    @abstractmethod
    def get_stats(self) -> CacheStats:
        """
        Get cache statistics.

        Returns:
            CacheStats with hit/miss counts etc.
        """
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """Get the current number of entries in the cache."""
        ...

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> T:
        """
        Get from cache or compute and store.

        Args:
            key: Cache key
            factory: Callable to compute value if not cached
            ttl: Time-to-live in seconds
            tags: Optional tags

        Returns:
            Cached or computed value
        """
        value = self.get(key)
        if value is not None:
            return value

        value = factory()
        self.set(key, value, ttl=ttl, tags=tags)
        return value
