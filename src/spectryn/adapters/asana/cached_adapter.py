"""
Cached Asana Adapter - Asana adapter with response caching.

Wraps AsanaAdapter with transparent caching to reduce API calls.
"""

import logging
from typing import Any

from spectryn.adapters.cache import CacheBackend, CacheManager, MemoryCache
from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData

from .adapter import AsanaAdapter


class CachedAsanaAdapter(AsanaAdapter):
    """
    Asana adapter with transparent response caching.

    Extends AsanaAdapter to cache GET requests automatically.
    Write operations (POST, PUT) bypass the cache and
    invalidate related cached entries.

    Features:
    - Automatic caching of task data, comments
    - Cache invalidation on writes
    - Configurable TTLs per resource type
    - Cache statistics for monitoring

    Example:
        >>> adapter = CachedAsanaAdapter(
        ...     config=config,
        ...     cache_enabled=True,
        ...     cache_ttl=300,  # 5 minutes default
        ... )
        >>>
        >>> # First call hits API
        >>> task = adapter.get_issue("12345")
        >>>
        >>> # Second call uses cache
        >>> task = adapter.get_issue("12345")
        >>>
        >>> # Check cache stats
        >>> print(adapter.cache_stats)
    """

    def __init__(
        self,
        config: TrackerConfig,
        dry_run: bool = True,
        cache_enabled: bool = True,
        cache_backend: CacheBackend | None = None,
        cache_ttl: float = 300.0,
        cache_max_size: int = 1000,
        **kwargs: Any,
    ):
        """
        Initialize the cached Asana adapter.

        Args:
            config: Tracker configuration
            dry_run: If True, don't make write operations
            cache_enabled: Whether to enable caching
            cache_backend: Custom cache backend (defaults to MemoryCache)
            cache_ttl: Default cache TTL in seconds
            cache_max_size: Maximum cache entries (for MemoryCache)
            **kwargs: Additional arguments for AsanaAdapter
        """
        super().__init__(config=config, dry_run=dry_run, **kwargs)

        self.cache_enabled = cache_enabled
        self._cache_logger = logging.getLogger("CachedAsanaAdapter")

        # Setup cache
        backend = cache_backend or MemoryCache(max_size=cache_max_size, default_ttl=cache_ttl)

        self._cache = CacheManager(
            backend=backend,
            enabled=cache_enabled,
            ttls={
                "issue": cache_ttl,
                "issue_comments": cache_ttl * 2,
                "issue_status": cache_ttl / 2,
                "epic_children": cache_ttl,
                "user": cache_ttl * 10,
                "current_user": cache_ttl * 10,
                "search": cache_ttl / 3,
            },
        )

        # Local user cache
        self._current_user: dict[str, Any] | None = None

    # -------------------------------------------------------------------------
    # Cached Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get current user (cached)."""
        if self._current_user is not None:
            return self._current_user

        cached = self._cache.get_current_user()
        if cached is not None:
            self._current_user = cached
            return cached

        user = super().get_current_user()
        self._current_user = user
        self._cache.set_current_user(user)
        return user

    def get_issue(self, issue_key: str) -> IssueData:
        """Get a task (cached)."""

        def fetch() -> IssueData:
            return super(CachedAsanaAdapter, self).get_issue(issue_key)

        cache_key = f"asana:issue:{issue_key}"

        if self.cache_enabled:
            cached = self._cache.backend.get(cache_key)
            if cached is not None:
                return cached

        result = fetch()

        if self.cache_enabled:
            self._cache.backend.set(
                cache_key,
                result,
                ttl=self._cache.ttls.get("issue", 300),
            )

        return result

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """Get project tasks (cached)."""
        cache_key = f"asana:epic_children:{epic_key}"

        if self.cache_enabled:
            cached = self._cache.backend.get(cache_key)
            if cached is not None:
                return cached

        result = super().get_epic_children(epic_key)

        if self.cache_enabled:
            self._cache.backend.set(
                cache_key,
                result,
                ttl=self._cache.ttls.get("epic_children", 300),
            )

        return result

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """Get task comments (cached)."""
        cache_key = f"asana:comments:{issue_key}"

        if self.cache_enabled:
            cached = self._cache.backend.get(cache_key)
            if cached is not None:
                return cached

        result = super().get_issue_comments(issue_key)

        if self.cache_enabled:
            self._cache.backend.set(
                cache_key,
                result,
                ttl=self._cache.ttls.get("issue_comments", 600),
            )

        return result

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """Search tasks (cached)."""
        cache_key = f"asana:search:{query}:{max_results}"

        if self.cache_enabled:
            cached = self._cache.backend.get(cache_key)
            if cached is not None:
                return cached

        result = super().search_issues(query, max_results)

        if self.cache_enabled:
            self._cache.backend.set(
                cache_key,
                result,
                ttl=self._cache.ttls.get("search", 100),
            )

        return result

    # -------------------------------------------------------------------------
    # Write Operations (with cache invalidation)
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        """Update task description with cache invalidation."""
        result = super().update_issue_description(issue_key, description)
        self._invalidate_task(issue_key)
        return result

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        """Update task story points with cache invalidation."""
        result = super().update_issue_story_points(issue_key, story_points)
        self._invalidate_task(issue_key)
        return result

    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: Any,
        project_key: str,
        story_points: int | None = None,
        assignee: str | None = None,
        priority: str | None = None,
    ) -> str | None:
        """Create subtask with cache invalidation."""
        result = super().create_subtask(
            parent_key, summary, description, project_key, story_points, assignee, priority
        )
        self._invalidate_task(parent_key)
        self._invalidate_project(project_key)
        return result

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        """Update subtask with cache invalidation."""
        result = super().update_subtask(issue_key, description, story_points, assignee, priority_id)
        self._invalidate_task(issue_key)
        return result

    def add_comment(self, issue_key: str, body: Any) -> bool:
        """Add comment with cache invalidation."""
        result = super().add_comment(issue_key, body)
        self._invalidate_comments(issue_key)
        return result

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        """Transition task with cache invalidation."""
        result = super().transition_issue(issue_key, target_status)
        self._invalidate_task(issue_key)
        return result

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def _invalidate_task(self, task_gid: str) -> None:
        """Invalidate cache for a task."""
        if not self.cache_enabled:
            return
        self._cache.backend.delete(f"asana:issue:{task_gid}")
        self._cache_logger.debug(f"Invalidated cache for task {task_gid}")

    def _invalidate_comments(self, task_gid: str) -> None:
        """Invalidate comments cache for a task."""
        if not self.cache_enabled:
            return
        self._cache.backend.delete(f"asana:comments:{task_gid}")

    def _invalidate_project(self, project_gid: str) -> None:
        """Invalidate cache for a project's children."""
        if not self.cache_enabled:
            return
        self._cache.backend.delete(f"asana:epic_children:{project_gid}")

    @property
    def cache(self) -> CacheManager:
        """Get the cache manager."""
        return self._cache

    @property
    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        stats = self._cache.get_stats()
        return {
            **stats.to_dict(),
            "size": self._cache.size,
            "enabled": self.cache_enabled,
        }

    @property
    def cache_hit_rate(self) -> float:
        """Get cache hit rate."""
        return self._cache.hit_rate

    def clear_cache(self) -> int:
        """Clear all cached data."""
        return self._cache.clear()

    def invalidate_task_cache(self, task_gid: str) -> None:
        """Manually invalidate cache for a task."""
        self._invalidate_task(task_gid)
        self._invalidate_comments(task_gid)

    def invalidate_project_cache(self, project_gid: str) -> None:
        """Manually invalidate cache for a project."""
        self._invalidate_project(project_gid)
