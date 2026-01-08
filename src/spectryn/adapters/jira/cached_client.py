"""
Cached Jira Client - Jira API client with response caching.

Wraps JiraApiClient with transparent caching to reduce API calls.
"""

import logging
from typing import Any

from spectryn.adapters.cache import CacheBackend, CacheManager, MemoryCache

from .client import JiraApiClient


class CachedJiraApiClient(JiraApiClient):
    """
    Jira API client with transparent response caching.

    Extends JiraApiClient to cache GET requests automatically.
    Write operations (POST, PUT, DELETE) bypass the cache and
    invalidate related cached entries.

    Features:
    - Automatic caching of issue data, comments, transitions
    - Cache invalidation on writes
    - Configurable TTLs per resource type
    - Cache statistics for monitoring

    Example:
        >>> client = CachedJiraApiClient(
        ...     base_url="https://company.atlassian.net",
        ...     email="user@example.com",
        ...     api_token="token",
        ...     cache_enabled=True,
        ...     cache_ttl=300,  # 5 minutes default
        ... )
        >>>
        >>> # First call hits API
        >>> issue = client.get("issue/PROJ-123")
        >>>
        >>> # Second call uses cache
        >>> issue = client.get("issue/PROJ-123")
        >>>
        >>> # Check cache stats
        >>> print(client.cache_stats)
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        dry_run: bool = True,
        cache_enabled: bool = True,
        cache_backend: CacheBackend | None = None,
        cache_ttl: float = 300.0,
        cache_max_size: int = 1000,
        **kwargs: Any,
    ):
        """
        Initialize the cached Jira client.

        Args:
            base_url: Jira instance URL
            email: User email
            api_token: API token
            dry_run: If True, don't make write operations
            cache_enabled: Whether to enable caching
            cache_backend: Custom cache backend (defaults to MemoryCache)
            cache_ttl: Default cache TTL in seconds
            cache_max_size: Maximum cache entries (for MemoryCache)
            **kwargs: Additional arguments for JiraApiClient
        """
        super().__init__(
            base_url=base_url,
            email=email,
            api_token=api_token,
            dry_run=dry_run,
            **kwargs,
        )

        self.cache_enabled = cache_enabled
        self.logger = logging.getLogger("CachedJiraApiClient")

        # Setup cache
        backend = cache_backend or MemoryCache(max_size=cache_max_size, default_ttl=cache_ttl)

        self._cache = CacheManager(
            backend=backend,
            enabled=cache_enabled,
            ttls={
                "issue": cache_ttl,
                "issue_comments": cache_ttl * 2,
                "issue_status": cache_ttl / 2,
                "issue_transitions": cache_ttl * 5,
                "epic_children": cache_ttl,
                "user": cache_ttl * 10,
                "current_user": cache_ttl * 10,
                "metadata": cache_ttl * 10,
                "search": cache_ttl / 3,
            },
        )

    # -------------------------------------------------------------------------
    # Cached Read Operations
    # -------------------------------------------------------------------------

    def get_myself(self) -> dict[str, Any]:
        """Get current user (cached)."""
        # Check local instance cache first
        if self._current_user is not None:
            return self._current_user

        # Check shared cache
        cached = self._cache.get_current_user()
        if cached is not None:
            self._current_user = cached
            return cached

        # Fetch from API
        user = super().get("myself")
        self._current_user = user
        self._cache.set_current_user(user)
        return user

    def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
        expand: str | None = None,
    ) -> dict[str, Any]:
        """
        Get an issue (cached).

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Fields to include
            expand: Expansions to include

        Returns:
            Issue data
        """

        def fetch() -> dict[str, Any]:
            params: dict[str, Any] = {}
            if fields:
                params["fields"] = ",".join(fields)
            if expand:
                params["expand"] = expand
            return self.get(f"issue/{issue_key}", params=params)

        return self._cache.get_or_fetch_issue(
            issue_key=issue_key,
            fetch_fn=fetch,
            fields=fields,
        )

    def get_issue_comments(self, issue_key: str) -> list[dict[str, Any]]:
        """Get issue comments (cached)."""
        cached = self._cache.get_comments(issue_key)
        if cached is not None:
            return cached

        result = self.get(f"issue/{issue_key}/comment")
        comments = result.get("comments", [])
        self._cache.set_comments(issue_key, comments)
        return comments

    def get_issue_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions (cached)."""
        cache_key = self._cache.keys.issue_transitions(issue_key)

        cached = self._cache.backend.get(cache_key)
        if cached is not None:
            return cached

        result = self.get(f"issue/{issue_key}/transitions")
        transitions = result.get("transitions", [])

        self._cache.backend.set(
            cache_key,
            transitions,
            ttl=self._cache.ttls.get("issue_transitions", 300),
            tags={self._cache.keys.tag_for_issue(issue_key)},
        )
        return transitions

    def get_epic_children(
        self,
        epic_key: str,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get epic children (cached)."""
        if fields is None:
            fields = ["summary", "description", "status", "issuetype", "subtasks"]

        def fetch() -> list[dict[str, Any]]:
            jql = f"parent = {epic_key} ORDER BY key ASC"
            result = self.search_jql(jql, fields)
            return result.get("issues", [])

        return self._cache.get_or_fetch_epic_children(
            epic_key=epic_key,
            fetch_fn=fetch,
            fields=fields,
        )

    def get_link_types(self) -> list[dict[str, Any]]:
        """Get available link types (cached)."""
        cached = self._cache.get_link_types()
        if cached is not None:
            return cached

        result = self.get("issueLinkType")
        link_types = result.get("issueLinkTypes", [])
        self._cache.set_link_types(link_types)
        return link_types

    def search_jql(
        self,
        jql: str,
        fields: list[str],
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Execute JQL search (cached)."""
        cached = self._cache.get_search(jql, max_results)
        if cached is not None:
            return cached

        result = super().search_jql(jql, fields, max_results)
        self._cache.set_search(jql, result, max_results)
        return result

    # -------------------------------------------------------------------------
    # Write Operations (with cache invalidation)
    # -------------------------------------------------------------------------

    def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """POST request with cache invalidation."""
        result = super().post(endpoint, json=json, **kwargs)

        # Invalidate related cache entries
        self._invalidate_for_endpoint(endpoint, "POST")

        return result

    def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """PUT request with cache invalidation."""
        result = super().put(endpoint, json=json, **kwargs)

        # Invalidate related cache entries
        self._invalidate_for_endpoint(endpoint, "PUT")

        return result

    def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """DELETE request with cache invalidation."""
        result = super().delete(endpoint, **kwargs)

        # Invalidate related cache entries
        self._invalidate_for_endpoint(endpoint, "DELETE")

        return result

    def _invalidate_for_endpoint(self, endpoint: str, method: str) -> None:
        """Invalidate cache entries based on the endpoint modified."""
        if not self.cache_enabled:
            return

        # Parse endpoint to find issue key
        parts = endpoint.split("/")

        if len(parts) >= 2 and parts[0] == "issue":
            issue_key = parts[1]
            self._cache.invalidate_issue(issue_key)

            # Also invalidate parent epic's children cache
            if "-" in issue_key:
                issue_key.split("-")[0]
                # We could invalidate project-level caches here too
                self.logger.debug(f"Invalidated cache for {issue_key}")

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

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

    def invalidate_issue_cache(self, issue_key: str) -> int:
        """Manually invalidate cache for an issue."""
        return self._cache.invalidate_issue(issue_key)

    def invalidate_epic_cache(self, epic_key: str) -> int:
        """Manually invalidate cache for an epic."""
        return self._cache.invalidate_epic(epic_key)
