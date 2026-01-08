"""
Cache Key Builder - Utilities for generating consistent cache keys.

Provides a structured way to generate cache keys for different API resources.
"""

import hashlib
from typing import Any


class CacheKeyBuilder:
    """
    Builder for generating consistent cache keys.

    Creates hierarchical keys that are:
    - Human-readable for debugging
    - Unique per resource
    - Grouped for tag-based invalidation

    Key format: {namespace}:{resource_type}:{identifier}[:{params_hash}]

    Example:
        >>> builder = CacheKeyBuilder(namespace="jira")
        >>> key = builder.issue("PROJ-123")
        >>> # "jira:issue:PROJ-123"
        >>>
        >>> key = builder.issue("PROJ-123", fields=["summary", "status"])
        >>> # "jira:issue:PROJ-123:a1b2c3d4"
    """

    def __init__(self, namespace: str = "default"):
        """
        Initialize the key builder.

        Args:
            namespace: Namespace prefix for all keys (e.g., "jira", "github")
        """
        self.namespace = namespace

    def _make_key(
        self,
        resource_type: str,
        identifier: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a cache key.

        Args:
            resource_type: Type of resource (e.g., "issue", "user")
            identifier: Resource identifier
            params: Optional query parameters to include in key

        Returns:
            Cache key string
        """
        key = f"{self.namespace}:{resource_type}:{identifier}"

        if params:
            # Sort params for consistent hashing
            sorted_params = sorted(params.items())
            params_str = str(sorted_params)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            key = f"{key}:{params_hash}"

        return key

    # -------------------------------------------------------------------------
    # Issue Keys
    # -------------------------------------------------------------------------

    def issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> str:
        """
        Create a key for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Optional list of fields requested

        Returns:
            Cache key
        """
        params = {"fields": sorted(fields)} if fields else None
        return self._make_key("issue", issue_key, params)

    def issue_comments(self, issue_key: str) -> str:
        """Create a key for issue comments."""
        return self._make_key("issue_comments", issue_key)

    def issue_status(self, issue_key: str) -> str:
        """Create a key for issue status."""
        return self._make_key("issue_status", issue_key)

    def issue_transitions(self, issue_key: str) -> str:
        """Create a key for issue transitions."""
        return self._make_key("issue_transitions", issue_key)

    def issue_links(self, issue_key: str) -> str:
        """Create a key for issue links."""
        return self._make_key("issue_links", issue_key)

    def epic_children(
        self,
        epic_key: str,
        fields: list[str] | None = None,
    ) -> str:
        """Create a key for epic children."""
        params = {"fields": sorted(fields)} if fields else None
        return self._make_key("epic_children", epic_key, params)

    # -------------------------------------------------------------------------
    # User Keys
    # -------------------------------------------------------------------------

    def user(self, user_id: str) -> str:
        """Create a key for a user."""
        return self._make_key("user", user_id)

    def current_user(self) -> str:
        """Create a key for the current authenticated user."""
        return self._make_key("user", "myself")

    # -------------------------------------------------------------------------
    # Metadata Keys
    # -------------------------------------------------------------------------

    def link_types(self) -> str:
        """Create a key for link types."""
        return self._make_key("metadata", "link_types")

    def project(self, project_key: str) -> str:
        """Create a key for a project."""
        return self._make_key("project", project_key)

    def workflow_states(self, project_key: str) -> str:
        """Create a key for workflow states."""
        return self._make_key("workflow_states", project_key)

    def fields(self) -> str:
        """Create a key for field definitions."""
        return self._make_key("metadata", "fields")

    # -------------------------------------------------------------------------
    # Search Keys
    # -------------------------------------------------------------------------

    def search(self, query: str, max_results: int = 100) -> str:
        """
        Create a key for a search query.

        Args:
            query: Search query (JQL, etc.)
            max_results: Maximum results

        Returns:
            Cache key
        """
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        return self._make_key("search", query_hash, {"max": max_results})

    # -------------------------------------------------------------------------
    # Tags
    # -------------------------------------------------------------------------

    def tag_for_issue(self, issue_key: str) -> str:
        """
        Get the tag for an issue (for invalidation).

        When an issue is modified, all cache entries with this tag
        should be invalidated.
        """
        return f"issue:{issue_key}"

    def tag_for_project(self, project_key: str) -> str:
        """Get the tag for a project."""
        return f"project:{project_key}"

    def tag_for_epic(self, epic_key: str) -> str:
        """Get the tag for an epic."""
        return f"epic:{epic_key}"


# Default key builders for common trackers
jira_keys = CacheKeyBuilder("jira")
github_keys = CacheKeyBuilder("github")
linear_keys = CacheKeyBuilder("linear")
azure_keys = CacheKeyBuilder("azure")
