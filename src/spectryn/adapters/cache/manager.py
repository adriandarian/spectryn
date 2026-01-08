"""
Cache Manager - High-level cache management for API clients.

Provides a convenient interface for caching API responses with
sensible defaults for different resource types.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .backend import CacheBackend, CacheStats
from .keys import CacheKeyBuilder
from .memory import MemoryCache


T = TypeVar("T")


# Default TTLs for different resource types (in seconds)
DEFAULT_TTLS = {
    "issue": 60,  # Issues change frequently, short TTL
    "issue_comments": 120,  # Comments change less often
    "issue_status": 30,  # Status is critical, very short TTL
    "issue_transitions": 300,  # Transitions rarely change
    "issue_links": 120,
    "epic_children": 60,  # Children list can change
    "user": 3600,  # User info rarely changes
    "current_user": 3600,
    "metadata": 3600,  # Link types, fields, etc. rarely change
    "project": 1800,  # Project config changes sometimes
    "workflow_states": 1800,
    "search": 30,  # Search results are dynamic
}


class CacheManager:
    """
    High-level cache manager for API clients.

    Wraps a cache backend with:
    - Resource-specific TTLs
    - Automatic cache key generation
    - Convenient get/set methods
    - Invalidation helpers
    - Statistics and monitoring

    Example:
        >>> manager = CacheManager()
        >>>
        >>> # Cache an issue
        >>> manager.set_issue("PROJ-123", issue_data)
        >>>
        >>> # Get from cache
        >>> issue = manager.get_issue("PROJ-123")
        >>>
        >>> # Or use get_or_fetch pattern
        >>> issue = manager.get_or_fetch_issue(
        ...     "PROJ-123",
        ...     fetch_fn=lambda: client.get_issue("PROJ-123"),
        ... )
    """

    def __init__(
        self,
        backend: CacheBackend | None = None,
        key_builder: CacheKeyBuilder | None = None,
        ttls: dict[str, float] | None = None,
        enabled: bool = True,
    ):
        """
        Initialize the cache manager.

        Args:
            backend: Cache backend (defaults to MemoryCache)
            key_builder: Key builder (defaults to "jira" namespace)
            ttls: Custom TTLs per resource type
            enabled: Whether caching is enabled
        """
        self.backend = backend or MemoryCache()
        self.keys = key_builder or CacheKeyBuilder("jira")
        self.ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self.enabled = enabled

        self.logger = logging.getLogger("CacheManager")

    def _get_ttl(self, resource_type: str) -> float | None:
        """Get TTL for a resource type."""
        return self.ttls.get(resource_type)

    # -------------------------------------------------------------------------
    # Issue Caching
    # -------------------------------------------------------------------------

    def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get a cached issue.

        Args:
            issue_key: Issue key
            fields: Fields that were requested

        Returns:
            Cached issue data or None
        """
        if not self.enabled:
            return None

        key = self.keys.issue(issue_key, fields)
        return self.backend.get(key)

    def set_issue(
        self,
        issue_key: str,
        data: dict[str, Any],
        fields: list[str] | None = None,
        ttl: float | None = None,
    ) -> None:
        """
        Cache an issue.

        Args:
            issue_key: Issue key
            data: Issue data to cache
            fields: Fields that were requested
            ttl: Custom TTL (defaults to issue TTL)
        """
        if not self.enabled:
            return

        key = self.keys.issue(issue_key, fields)
        tags = {
            self.keys.tag_for_issue(issue_key),
            self.keys.tag_for_project(issue_key.split("-")[0]),
        }

        self.backend.set(
            key,
            data,
            ttl=ttl or self._get_ttl("issue"),
            tags=tags,
        )

    def get_or_fetch_issue(
        self,
        issue_key: str,
        fetch_fn: Callable[[], dict[str, Any]],
        fields: list[str] | None = None,
        ttl: float | None = None,
    ) -> dict[str, Any]:
        """
        Get from cache or fetch and cache.

        Args:
            issue_key: Issue key
            fetch_fn: Function to fetch issue if not cached
            fields: Fields to request
            ttl: Custom TTL

        Returns:
            Issue data (from cache or freshly fetched)
        """
        cached = self.get_issue(issue_key, fields)
        if cached is not None:
            return cached

        data = fetch_fn()
        self.set_issue(issue_key, data, fields, ttl)
        return data

    # -------------------------------------------------------------------------
    # Epic Children Caching
    # -------------------------------------------------------------------------

    def get_epic_children(
        self,
        epic_key: str,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]] | None:
        """Get cached epic children."""
        if not self.enabled:
            return None

        key = self.keys.epic_children(epic_key, fields)
        return self.backend.get(key)

    def set_epic_children(
        self,
        epic_key: str,
        children: list[dict[str, Any]],
        fields: list[str] | None = None,
        ttl: float | None = None,
    ) -> None:
        """Cache epic children."""
        if not self.enabled:
            return

        key = self.keys.epic_children(epic_key, fields)
        tags = {self.keys.tag_for_epic(epic_key)}

        self.backend.set(
            key,
            children,
            ttl=ttl or self._get_ttl("epic_children"),
            tags=tags,
        )

    def get_or_fetch_epic_children(
        self,
        epic_key: str,
        fetch_fn: Callable[[], list[dict[str, Any]]],
        fields: list[str] | None = None,
        ttl: float | None = None,
    ) -> list[dict[str, Any]]:
        """Get from cache or fetch epic children."""
        cached = self.get_epic_children(epic_key, fields)
        if cached is not None:
            return cached

        data = fetch_fn()
        self.set_epic_children(epic_key, data, fields, ttl)
        return data

    # -------------------------------------------------------------------------
    # Comments Caching
    # -------------------------------------------------------------------------

    def get_comments(self, issue_key: str) -> list[dict[str, Any]] | None:
        """Get cached comments."""
        if not self.enabled:
            return None

        key = self.keys.issue_comments(issue_key)
        return self.backend.get(key)

    def set_comments(
        self,
        issue_key: str,
        comments: list[dict[str, Any]],
        ttl: float | None = None,
    ) -> None:
        """Cache comments."""
        if not self.enabled:
            return

        key = self.keys.issue_comments(issue_key)
        tags = {self.keys.tag_for_issue(issue_key)}

        self.backend.set(
            key,
            comments,
            ttl=ttl or self._get_ttl("issue_comments"),
            tags=tags,
        )

    # -------------------------------------------------------------------------
    # User Caching
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any] | None:
        """Get cached current user."""
        if not self.enabled:
            return None

        key = self.keys.current_user()
        return self.backend.get(key)

    def set_current_user(
        self,
        user_data: dict[str, Any],
        ttl: float | None = None,
    ) -> None:
        """Cache current user."""
        if not self.enabled:
            return

        key = self.keys.current_user()
        self.backend.set(
            key,
            user_data,
            ttl=ttl or self._get_ttl("current_user"),
        )

    # -------------------------------------------------------------------------
    # Metadata Caching
    # -------------------------------------------------------------------------

    def get_link_types(self) -> list[dict[str, Any]] | None:
        """Get cached link types."""
        if not self.enabled:
            return None

        key = self.keys.link_types()
        return self.backend.get(key)

    def set_link_types(
        self,
        link_types: list[dict[str, Any]],
        ttl: float | None = None,
    ) -> None:
        """Cache link types."""
        if not self.enabled:
            return

        key = self.keys.link_types()
        self.backend.set(
            key,
            link_types,
            ttl=ttl or self._get_ttl("metadata"),
        )

    # -------------------------------------------------------------------------
    # Search Caching
    # -------------------------------------------------------------------------

    def get_search(
        self,
        query: str,
        max_results: int = 100,
    ) -> dict[str, Any] | None:
        """Get cached search results."""
        if not self.enabled:
            return None

        key = self.keys.search(query, max_results)
        return self.backend.get(key)

    def set_search(
        self,
        query: str,
        results: dict[str, Any],
        max_results: int = 100,
        ttl: float | None = None,
    ) -> None:
        """Cache search results."""
        if not self.enabled:
            return

        key = self.keys.search(query, max_results)
        self.backend.set(
            key,
            results,
            ttl=ttl or self._get_ttl("search"),
        )

    # -------------------------------------------------------------------------
    # Invalidation
    # -------------------------------------------------------------------------

    def invalidate_issue(self, issue_key: str) -> int:
        """
        Invalidate all cached data for an issue.

        Call this after modifying an issue.

        Returns:
            Number of cache entries invalidated
        """
        tag = self.keys.tag_for_issue(issue_key)
        count = self.backend.invalidate_by_tag(tag)
        self.logger.debug(f"Invalidated {count} entries for {issue_key}")
        return count

    def invalidate_epic(self, epic_key: str) -> int:
        """
        Invalidate all cached data for an epic.

        Returns:
            Number of cache entries invalidated
        """
        tag = self.keys.tag_for_epic(epic_key)
        count = self.backend.invalidate_by_tag(tag)
        self.logger.debug(f"Invalidated {count} entries for epic {epic_key}")
        return count

    def invalidate_project(self, project_key: str) -> int:
        """
        Invalidate all cached data for a project.

        Returns:
            Number of cache entries invalidated
        """
        tag = self.keys.tag_for_project(project_key)
        count = self.backend.invalidate_by_tag(tag)
        self.logger.debug(f"Invalidated {count} entries for project {project_key}")
        return count

    def clear(self) -> int:
        """
        Clear all cached data.

        Returns:
            Number of entries cleared
        """
        count = self.backend.clear()
        self.logger.info(f"Cleared {count} cache entries")
        return count

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self.backend.get_stats()

    @property
    def size(self) -> int:
        """Get current cache size."""
        return self.backend.size

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        return self.get_stats().hit_rate
