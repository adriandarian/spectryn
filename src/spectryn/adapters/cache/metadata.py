"""
Metadata Cache - Smart caching for tracker metadata.

Provides aggressive caching with configurable TTLs for tracker metadata
that changes infrequently:
- Workflow states / statuses
- Priorities
- Custom fields
- Users
- Projects
- Labels / Tags

Metadata is cached with longer TTLs since it changes rarely, reducing
API calls significantly in high-concurrency environments.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar

from .backend import CacheBackend
from .memory import MemoryCache


T = TypeVar("T")


class MetadataType(Enum):
    """Types of metadata that can be cached."""

    STATES = "states"
    PRIORITIES = "priorities"
    FIELDS = "fields"
    USERS = "users"
    PROJECTS = "projects"
    LABELS = "labels"
    TEAMS = "teams"
    SPRINTS = "sprints"
    BOARDS = "boards"
    WORKFLOWS = "workflows"
    ISSUE_TYPES = "issue_types"
    RESOLUTIONS = "resolutions"
    LINK_TYPES = "link_types"
    CUSTOM_FIELDS = "custom_fields"


# Default TTLs for metadata types (in seconds)
# These are longer than regular data since metadata changes infrequently
DEFAULT_METADATA_TTLS: dict[MetadataType, float] = {
    MetadataType.STATES: 3600,  # 1 hour - workflow states rarely change
    MetadataType.PRIORITIES: 3600,  # 1 hour - priorities rarely change
    MetadataType.FIELDS: 1800,  # 30 min - field definitions
    MetadataType.USERS: 1800,  # 30 min - users can be added/removed
    MetadataType.PROJECTS: 3600,  # 1 hour - projects rarely change
    MetadataType.LABELS: 1800,  # 30 min - labels can change more often
    MetadataType.TEAMS: 3600,  # 1 hour - teams rarely change
    MetadataType.SPRINTS: 300,  # 5 min - sprints can change during planning
    MetadataType.BOARDS: 3600,  # 1 hour - boards rarely change
    MetadataType.WORKFLOWS: 3600,  # 1 hour - workflows rarely change
    MetadataType.ISSUE_TYPES: 3600,  # 1 hour - issue types rarely change
    MetadataType.RESOLUTIONS: 3600,  # 1 hour - resolutions rarely change
    MetadataType.LINK_TYPES: 3600,  # 1 hour - link types rarely change
    MetadataType.CUSTOM_FIELDS: 1800,  # 30 min - custom fields can change
}


@dataclass
class MetadataCacheEntry(Generic[T]):
    """A cache entry for metadata with refresh support."""

    value: T
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    refresh_at: float | None = None  # Time to trigger background refresh
    metadata_type: MetadataType | None = None
    tracker: str | None = None  # Tracker namespace (e.g., "jira", "asana")

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def should_refresh(self) -> bool:
        """Check if entry should be refreshed (proactive refresh)."""
        if self.refresh_at is None:
            return False
        return time.time() > self.refresh_at

    @property
    def ttl_remaining(self) -> float | None:
        """Get remaining TTL in seconds."""
        if self.expires_at is None:
            return None
        return max(0, self.expires_at - time.time())

    @property
    def age(self) -> float:
        """Get age of entry in seconds."""
        return time.time() - self.created_at


@dataclass
class MetadataCacheStats:
    """Statistics for metadata cache performance."""

    hits: int = 0
    misses: int = 0
    refreshes: int = 0
    stale_hits: int = 0  # Hits on entries that should be refreshed

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def record_hit(self, stale: bool = False) -> None:
        """Record a cache hit."""
        self.hits += 1
        if stale:
            self.stale_hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    def record_refresh(self) -> None:
        """Record a background refresh."""
        self.refreshes += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "refreshes": self.refreshes,
            "stale_hits": self.stale_hits,
            "hit_rate": self.hit_rate,
            "total_requests": self.hits + self.misses,
        }


class MetadataCache:
    """
    Smart cache for tracker metadata with aggressive TTLs.

    Features:
    - Type-specific TTLs optimized for metadata change frequency
    - Proactive refresh before expiry (stale-while-revalidate pattern)
    - Multi-tracker support with namespaced keys
    - Warm-up support for pre-loading metadata
    - Thread-safe operations

    Example:
        >>> cache = MetadataCache(tracker="jira")
        >>>
        >>> # Cache workflow states
        >>> cache.set_metadata(MetadataType.STATES, states)
        >>>
        >>> # Get with automatic fetch fallback
        >>> states = cache.get_or_fetch(
        ...     MetadataType.STATES,
        ...     fetch_fn=lambda: client.get_states(),
        ... )
        >>>
        >>> # Pre-warm cache
        >>> cache.warm_up({
        ...     MetadataType.STATES: lambda: client.get_states(),
        ...     MetadataType.PRIORITIES: lambda: client.get_priorities(),
        ... })
    """

    def __init__(
        self,
        tracker: str = "default",
        backend: CacheBackend | None = None,
        ttls: dict[MetadataType, float] | None = None,
        refresh_ratio: float = 0.8,  # Refresh at 80% of TTL
        enabled: bool = True,
    ):
        """
        Initialize the metadata cache.

        Args:
            tracker: Tracker namespace (e.g., "jira", "asana")
            backend: Cache backend (defaults to MemoryCache)
            ttls: Custom TTLs per metadata type
            refresh_ratio: Ratio of TTL at which to trigger refresh (0.0-1.0)
            enabled: Whether caching is enabled
        """
        self.tracker = tracker
        self.backend = backend or MemoryCache(max_size=500, default_ttl=3600)
        self.ttls = {**DEFAULT_METADATA_TTLS, **(ttls or {})}
        self.refresh_ratio = max(0.5, min(0.95, refresh_ratio))
        self.enabled = enabled

        self._stats = MetadataCacheStats()
        self._lock = threading.RLock()
        self._refresh_callbacks: dict[str, Callable[[], Any]] = {}

        self.logger = logging.getLogger(f"MetadataCache[{tracker}]")

    def _make_key(self, metadata_type: MetadataType, scope: str | None = None) -> str:
        """
        Create a cache key for metadata.

        Args:
            metadata_type: Type of metadata
            scope: Optional scope (e.g., project key)

        Returns:
            Cache key string
        """
        key = f"{self.tracker}:metadata:{metadata_type.value}"
        if scope:
            key = f"{key}:{scope}"
        return key

    def _get_ttl(self, metadata_type: MetadataType) -> float:
        """Get TTL for a metadata type."""
        return self.ttls.get(metadata_type, 3600)

    def _get_refresh_time(self, metadata_type: MetadataType) -> float:
        """Get time at which entry should be refreshed."""
        ttl = self._get_ttl(metadata_type)
        return time.time() + (ttl * self.refresh_ratio)

    # -------------------------------------------------------------------------
    # Core Cache Operations
    # -------------------------------------------------------------------------

    def get_metadata(
        self,
        metadata_type: MetadataType,
        scope: str | None = None,
    ) -> Any | None:
        """
        Get cached metadata.

        Args:
            metadata_type: Type of metadata to get
            scope: Optional scope (e.g., project key)

        Returns:
            Cached metadata or None if not found/expired
        """
        if not self.enabled:
            return None

        key = self._make_key(metadata_type, scope)

        with self._lock:
            entry = self.backend.get(key)

            if entry is None:
                self._stats.record_miss()
                return None

            # Check if it's a MetadataCacheEntry or raw value
            if isinstance(entry, MetadataCacheEntry):
                if entry.is_expired:
                    self._stats.record_miss()
                    return None

                stale = entry.should_refresh
                self._stats.record_hit(stale=stale)
                return entry.value
            # Raw value from backend
            self._stats.record_hit()
            return entry

    def set_metadata(
        self,
        metadata_type: MetadataType,
        value: Any,
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """
        Cache metadata.

        Args:
            metadata_type: Type of metadata
            value: Data to cache
            scope: Optional scope (e.g., project key)
            ttl: Custom TTL (defaults to type-specific TTL)
        """
        if not self.enabled:
            return

        key = self._make_key(metadata_type, scope)
        actual_ttl = ttl or self._get_ttl(metadata_type)

        with self._lock:
            entry = MetadataCacheEntry(
                value=value,
                expires_at=time.time() + actual_ttl,
                refresh_at=self._get_refresh_time(metadata_type),
                metadata_type=metadata_type,
                tracker=self.tracker,
            )

            # Store as raw value in backend (backend handles its own TTL)
            self.backend.set(
                key,
                entry,
                ttl=actual_ttl,
                tags={f"metadata:{self.tracker}", f"metadata:{metadata_type.value}"},
            )

            self.logger.debug(f"Cached {metadata_type.value} (scope={scope}, ttl={actual_ttl}s)")

    def get_or_fetch(
        self,
        metadata_type: MetadataType,
        fetch_fn: Callable[[], T],
        scope: str | None = None,
        ttl: float | None = None,
        force_refresh: bool = False,
    ) -> T:
        """
        Get metadata from cache or fetch if missing/expired.

        This is the primary method for accessing metadata. It implements
        the stale-while-revalidate pattern: returns cached data immediately
        but triggers a background refresh if the data is stale.

        Args:
            metadata_type: Type of metadata
            fetch_fn: Function to fetch data if not cached
            scope: Optional scope (e.g., project key)
            ttl: Custom TTL
            force_refresh: Force fetch even if cached

        Returns:
            Metadata value (from cache or freshly fetched)
        """
        if not self.enabled or force_refresh:
            value = fetch_fn()
            if self.enabled:
                self.set_metadata(metadata_type, value, scope, ttl)
            return value

        key = self._make_key(metadata_type, scope)

        with self._lock:
            cached = self.backend.get(key)

            if cached is not None:
                if isinstance(cached, MetadataCacheEntry):
                    if not cached.is_expired:
                        self._stats.record_hit(stale=cached.should_refresh)
                        return cached.value
                else:
                    self._stats.record_hit()
                    return cached

            # Cache miss - fetch and cache
            self._stats.record_miss()

        # Fetch outside lock to avoid blocking
        value = fetch_fn()
        self.set_metadata(metadata_type, value, scope, ttl)
        return value

    def invalidate(
        self,
        metadata_type: MetadataType,
        scope: str | None = None,
    ) -> bool:
        """
        Invalidate cached metadata.

        Args:
            metadata_type: Type of metadata to invalidate
            scope: Optional scope

        Returns:
            True if entry was found and deleted
        """
        if not self.enabled:
            return False

        key = self._make_key(metadata_type, scope)

        with self._lock:
            return self.backend.delete(key)

    def invalidate_all(self, metadata_type: MetadataType | None = None) -> int:
        """
        Invalidate all metadata of a type or all metadata.

        Args:
            metadata_type: Optional type to invalidate, or None for all

        Returns:
            Number of entries invalidated
        """
        if not self.enabled:
            return 0

        with self._lock:
            tag = f"metadata:{metadata_type.value}" if metadata_type else f"metadata:{self.tracker}"

            return self.backend.invalidate_by_tag(tag)

    # -------------------------------------------------------------------------
    # Type-Specific Convenience Methods
    # -------------------------------------------------------------------------

    def get_states(self, scope: str | None = None) -> list[dict] | None:
        """Get cached workflow states."""
        return self.get_metadata(MetadataType.STATES, scope)

    def set_states(
        self,
        states: list[dict],
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache workflow states."""
        self.set_metadata(MetadataType.STATES, states, scope, ttl)

    def get_or_fetch_states(
        self,
        fetch_fn: Callable[[], list[dict]],
        scope: str | None = None,
    ) -> list[dict]:
        """Get states from cache or fetch."""
        return self.get_or_fetch(MetadataType.STATES, fetch_fn, scope)

    def get_priorities(self, scope: str | None = None) -> list[dict] | None:
        """Get cached priorities."""
        return self.get_metadata(MetadataType.PRIORITIES, scope)

    def set_priorities(
        self,
        priorities: list[dict],
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache priorities."""
        self.set_metadata(MetadataType.PRIORITIES, priorities, scope, ttl)

    def get_or_fetch_priorities(
        self,
        fetch_fn: Callable[[], list[dict]],
        scope: str | None = None,
    ) -> list[dict]:
        """Get priorities from cache or fetch."""
        return self.get_or_fetch(MetadataType.PRIORITIES, fetch_fn, scope)

    def get_users(self, scope: str | None = None) -> list[dict] | None:
        """Get cached users."""
        return self.get_metadata(MetadataType.USERS, scope)

    def set_users(
        self,
        users: list[dict],
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache users."""
        self.set_metadata(MetadataType.USERS, users, scope, ttl)

    def get_or_fetch_users(
        self,
        fetch_fn: Callable[[], list[dict]],
        scope: str | None = None,
    ) -> list[dict]:
        """Get users from cache or fetch."""
        return self.get_or_fetch(MetadataType.USERS, fetch_fn, scope)

    def get_projects(self) -> list[dict] | None:
        """Get cached projects."""
        return self.get_metadata(MetadataType.PROJECTS)

    def set_projects(
        self,
        projects: list[dict],
        ttl: float | None = None,
    ) -> None:
        """Cache projects."""
        self.set_metadata(MetadataType.PROJECTS, projects, ttl=ttl)

    def get_or_fetch_projects(
        self,
        fetch_fn: Callable[[], list[dict]],
    ) -> list[dict]:
        """Get projects from cache or fetch."""
        return self.get_or_fetch(MetadataType.PROJECTS, fetch_fn)

    def get_labels(self, scope: str | None = None) -> list[dict] | None:
        """Get cached labels."""
        return self.get_metadata(MetadataType.LABELS, scope)

    def set_labels(
        self,
        labels: list[dict],
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache labels."""
        self.set_metadata(MetadataType.LABELS, labels, scope, ttl)

    def get_or_fetch_labels(
        self,
        fetch_fn: Callable[[], list[dict]],
        scope: str | None = None,
    ) -> list[dict]:
        """Get labels from cache or fetch."""
        return self.get_or_fetch(MetadataType.LABELS, fetch_fn, scope)

    def get_custom_fields(self, scope: str | None = None) -> list[dict] | None:
        """Get cached custom fields."""
        return self.get_metadata(MetadataType.CUSTOM_FIELDS, scope)

    def set_custom_fields(
        self,
        fields: list[dict],
        scope: str | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache custom fields."""
        self.set_metadata(MetadataType.CUSTOM_FIELDS, fields, scope, ttl)

    def get_or_fetch_custom_fields(
        self,
        fetch_fn: Callable[[], list[dict]],
        scope: str | None = None,
    ) -> list[dict]:
        """Get custom fields from cache or fetch."""
        return self.get_or_fetch(MetadataType.CUSTOM_FIELDS, fetch_fn, scope)

    # -------------------------------------------------------------------------
    # Warm-up and Preloading
    # -------------------------------------------------------------------------

    def warm_up(
        self,
        fetchers: dict[MetadataType, Callable[[], Any]],
        scope: str | None = None,
    ) -> dict[MetadataType, bool]:
        """
        Pre-load multiple metadata types into cache.

        Use this at application startup or when connecting to a tracker
        to reduce latency during normal operations.

        Args:
            fetchers: Map of metadata types to fetch functions
            scope: Optional scope for all metadata

        Returns:
            Map of metadata types to success status
        """
        results: dict[MetadataType, bool] = {}

        for metadata_type, fetch_fn in fetchers.items():
            try:
                value = fetch_fn()
                self.set_metadata(metadata_type, value, scope)
                results[metadata_type] = True
                self.logger.info(f"Warmed up {metadata_type.value} cache")
            except Exception as e:
                results[metadata_type] = False
                self.logger.warning(f"Failed to warm up {metadata_type.value}: {e}")

        return results

    def warm_up_async(
        self,
        fetchers: dict[MetadataType, Callable[[], Any]],
        scope: str | None = None,
        max_workers: int = 4,
    ) -> dict[MetadataType, bool]:
        """
        Pre-load multiple metadata types concurrently.

        Args:
            fetchers: Map of metadata types to fetch functions
            scope: Optional scope for all metadata
            max_workers: Maximum concurrent fetches

        Returns:
            Map of metadata types to success status
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: dict[MetadataType, bool] = {}

        def fetch_and_cache(
            metadata_type: MetadataType,
            fetch_fn: Callable[[], Any],
        ) -> tuple[MetadataType, bool]:
            try:
                value = fetch_fn()
                self.set_metadata(metadata_type, value, scope)
                return (metadata_type, True)
            except Exception as e:
                self.logger.warning(f"Failed to warm up {metadata_type.value}: {e}")
                return (metadata_type, False)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_and_cache, mt, fn): mt for mt, fn in fetchers.items()}

            for future in as_completed(futures):
                metadata_type, success = future.result()
                results[metadata_type] = success

        return results

    # -------------------------------------------------------------------------
    # Statistics and Management
    # -------------------------------------------------------------------------

    @property
    def stats(self) -> MetadataCacheStats:
        """Get cache statistics."""
        return self._stats

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics as dictionary."""
        return {
            **self._stats.to_dict(),
            "tracker": self.tracker,
            "enabled": self.enabled,
            "backend_size": self.backend.size,
        }

    @property
    def size(self) -> int:
        """Get number of cached entries."""
        return self.backend.size

    def clear(self) -> int:
        """
        Clear all cached metadata.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = self.invalidate_all()
            self.logger.info(f"Cleared {count} metadata entries")
            return count

    def get_cached_types(self) -> list[MetadataType]:
        """
        Get list of metadata types currently cached.

        Returns:
            List of cached metadata types
        """
        # This requires backend to support key listing
        # For now, return types based on what we know
        cached = []
        for metadata_type in MetadataType:
            if self.get_metadata(metadata_type) is not None:
                cached.append(metadata_type)
        return cached


# Factory function for creating metadata cache with common presets


def create_metadata_cache(
    tracker: str,
    backend: CacheBackend | None = None,
    preset: str = "default",
) -> MetadataCache:
    """
    Create a metadata cache with preset TTL configurations.

    Presets:
    - "default": Balanced TTLs for typical use
    - "aggressive": Longer TTLs for read-heavy workloads
    - "conservative": Shorter TTLs for write-heavy workloads
    - "minimal": Minimal caching for testing

    Args:
        tracker: Tracker namespace
        backend: Cache backend
        preset: Preset name

    Returns:
        Configured MetadataCache
    """
    ttl_presets: dict[str, dict[MetadataType, float]] = {
        "default": DEFAULT_METADATA_TTLS,
        "aggressive": {
            MetadataType.STATES: 7200,  # 2 hours
            MetadataType.PRIORITIES: 7200,
            MetadataType.FIELDS: 3600,
            MetadataType.USERS: 3600,
            MetadataType.PROJECTS: 7200,
            MetadataType.LABELS: 3600,
            MetadataType.TEAMS: 7200,
            MetadataType.SPRINTS: 600,
            MetadataType.BOARDS: 7200,
            MetadataType.WORKFLOWS: 7200,
            MetadataType.ISSUE_TYPES: 7200,
            MetadataType.RESOLUTIONS: 7200,
            MetadataType.LINK_TYPES: 7200,
            MetadataType.CUSTOM_FIELDS: 3600,
        },
        "conservative": {
            MetadataType.STATES: 900,  # 15 min
            MetadataType.PRIORITIES: 900,
            MetadataType.FIELDS: 600,
            MetadataType.USERS: 600,
            MetadataType.PROJECTS: 900,
            MetadataType.LABELS: 600,
            MetadataType.TEAMS: 900,
            MetadataType.SPRINTS: 120,
            MetadataType.BOARDS: 900,
            MetadataType.WORKFLOWS: 900,
            MetadataType.ISSUE_TYPES: 900,
            MetadataType.RESOLUTIONS: 900,
            MetadataType.LINK_TYPES: 900,
            MetadataType.CUSTOM_FIELDS: 600,
        },
        "minimal": {
            MetadataType.STATES: 60,
            MetadataType.PRIORITIES: 60,
            MetadataType.FIELDS: 60,
            MetadataType.USERS: 60,
            MetadataType.PROJECTS: 60,
            MetadataType.LABELS: 60,
            MetadataType.TEAMS: 60,
            MetadataType.SPRINTS: 30,
            MetadataType.BOARDS: 60,
            MetadataType.WORKFLOWS: 60,
            MetadataType.ISSUE_TYPES: 60,
            MetadataType.RESOLUTIONS: 60,
            MetadataType.LINK_TYPES: 60,
            MetadataType.CUSTOM_FIELDS: 60,
        },
    }

    ttls = ttl_presets.get(preset, DEFAULT_METADATA_TTLS)

    return MetadataCache(
        tracker=tracker,
        backend=backend,
        ttls=ttls,
    )
