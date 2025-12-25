"""
Optional Bitbucket Server client using atlassian-python-api.

This module provides an optional wrapper around atlassian-python-api
for enhanced Bitbucket Server support. It's only used when the library
is installed: pip install spectra[bitbucket]

The atlassian-python-api library provides better support for Server-specific
features and can handle some edge cases better than raw REST API calls.
"""

import logging
from typing import Any

from spectra.core.ports.issue_tracker import (
    IssueTrackerError,
    NotFoundError,
)


# Try to import atlassian-python-api
try:
    from atlassian import Bitbucket as AtlassianBitbucket  # type: ignore[import-untyped]

    ATLASSIAN_API_AVAILABLE = True
except ImportError:
    ATLASSIAN_API_AVAILABLE = False
    AtlassianBitbucket = None  # type: ignore[assignment, misc]


class BitbucketServerClient:
    """
    Optional wrapper around atlassian-python-api for Bitbucket Server.

    This provides enhanced Server support when the library is available.
    Falls back to standard REST API if not installed.

    Usage:
        if ATLASSIAN_API_AVAILABLE:
            server_client = BitbucketServerClient(...)
        else:
            # Use standard REST API client
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        project_key: str,
        repo_slug: str,
        dry_run: bool = True,
    ):
        """
        Initialize the Server client using atlassian-python-api.

        Args:
            url: Bitbucket Server base URL (e.g., https://bitbucket.example.com)
            username: Server username
            password: Personal Access Token or password
            project_key: Project key (workspace equivalent)
            repo_slug: Repository slug
            dry_run: If True, don't make write operations
        """
        if not ATLASSIAN_API_AVAILABLE:
            raise ImportError(
                "atlassian-python-api is required for Server support. "
                "Install with: pip install spectra[bitbucket]"
            )

        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.project_key = project_key
        self.repo_slug = repo_slug
        self.dry_run = dry_run
        self.logger = logging.getLogger("BitbucketServerClient")

        # Initialize Atlassian Bitbucket client
        self._client = AtlassianBitbucket(
            url=self.url,
            username=self.username,
            password=self.password,
            cloud=False,  # Server instance
        )

    def get_current_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        try:
            # atlassian-python-api provides a get_current_user method
            return self._client.get_current_user() or {}
        except Exception as e:
            self.logger.error(f"Failed to get current user: {e}")
            return {}

    def get_issue(self, issue_id: int) -> dict[str, Any]:
        """
        Get an issue by ID.

        Args:
            issue_id: Issue ID

        Returns:
            Issue data dictionary

        Raises:
            NotFoundError: If issue doesn't exist
        """
        try:
            # Use atlassian-python-api's issue methods
            issue = self._client.get_issue(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                issue_id=issue_id,
            )
            if not issue:
                raise NotFoundError(f"Issue {issue_id} not found", issue_key=str(issue_id))
            # Ensure we return a dict
            if isinstance(issue, dict):
                return issue
            # Fallback: convert to dict if needed
            return dict(issue) if hasattr(issue, "__dict__") else {"id": issue_id}
        except Exception as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise NotFoundError(f"Issue {issue_id} not found", issue_key=str(issue_id))
            raise IssueTrackerError(f"Failed to get issue {issue_id}: {e}", cause=e)

    def list_issues(
        self,
        state: str | None = None,
        kind: str | None = None,
        page: int = 1,
        pagelen: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List issues in the repository.

        Args:
            state: Filter by state
            kind: Filter by kind
            page: Page number
            pagelen: Results per page

        Returns:
            List of issue dictionaries
        """
        try:
            # Build query parameters
            params: dict[str, Any] = {
                "start": (page - 1) * pagelen,
                "limit": pagelen,
            }
            if state:
                params["state"] = state
            if kind:
                params["kind"] = kind

            # Use atlassian-python-api's issue list method
            issues = self._client.get_issues(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                **params,
            )
            return issues if isinstance(issues, list) else []
        except Exception as e:
            self.logger.error(f"Failed to list issues: {e}")
            return []

    def create_issue(
        self,
        title: str,
        content: str | None = None,
        kind: str = "task",
        priority: str = "minor",
        state: str = "new",
        assignee: str | None = None,
        component: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            title: Issue title
            content: Issue description
            kind: Issue kind
            priority: Priority level
            state: Initial state
            assignee: Assignee username
            component: Component name
            version: Version name

        Returns:
            Created issue dictionary
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create issue: {title}")
            return {"id": 0, "title": title}

        try:
            # Build issue data
            issue_data: dict[str, Any] = {
                "title": title,
                "kind": kind,
                "priority": priority,
                "state": state,
            }
            if content:
                issue_data["content"] = {"raw": content, "markup": "markdown"}
            if assignee:
                issue_data["assignee"] = {"username": assignee}
            if component:
                issue_data["component"] = {"name": component}
            if version:
                issue_data["version"] = {"name": version}

            # Use atlassian-python-api's create issue method
            result = self._client.create_issue(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                **issue_data,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            raise IssueTrackerError(f"Failed to create issue: {e}", cause=e)

    def update_issue(
        self,
        issue_id: int,
        title: str | None = None,
        content: str | None = None,
        state: str | None = None,
        priority: str | None = None,
        kind: str | None = None,
        assignee: str | None = None,
        component: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing issue.

        Args:
            issue_id: Issue ID
            title: New title
            content: New content
            state: New state
            priority: New priority
            kind: New kind
            assignee: New assignee
            component: New component
            version: New version

        Returns:
            Updated issue dictionary
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update issue {issue_id}")
            return {"id": issue_id}

        try:
            # Build update data
            update_data: dict[str, Any] = {}
            if title is not None:
                update_data["title"] = title
            if content is not None:
                update_data["content"] = {"raw": content, "markup": "markdown"}
            if state is not None:
                update_data["state"] = state
            if priority is not None:
                update_data["priority"] = priority
            if kind is not None:
                update_data["kind"] = kind
            if assignee is not None:
                update_data["assignee"] = {"username": assignee} if assignee else None
            if component is not None:
                update_data["component"] = {"name": component} if component else None
            if version is not None:
                update_data["version"] = {"name": version} if version else None

            # Use atlassian-python-api's update issue method
            result = self._client.update_issue(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                issue_id=issue_id,
                **update_data,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            raise IssueTrackerError(f"Failed to update issue {issue_id}: {e}", cause=e)

    def get_issue_comments(self, issue_id: int) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        try:
            comments = self._client.get_issue_comments(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                issue_id=issue_id,
            )
            return comments if isinstance(comments, list) else []
        except Exception as e:
            self.logger.error(f"Failed to get comments for issue {issue_id}: {e}")
            return []

    def add_issue_comment(self, issue_id: int, content: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to issue {issue_id}")
            return {"id": "comment:dry-run"}

        try:
            result = self._client.add_issue_comment(
                project_key=self.project_key,
                repo_slug=self.repo_slug,
                issue_id=issue_id,
                content=content,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            raise IssueTrackerError(f"Failed to add comment: {e}", cause=e)

    def test_connection(self) -> bool:
        """Test if the connection is valid."""
        try:
            user = self.get_current_user()
            return bool(user)
        except Exception:
            return False


def is_server_url(url: str) -> bool:
    """
    Determine if a URL is for Bitbucket Server vs Cloud.

    Args:
        url: Base URL

    Returns:
        True if Server, False if Cloud
    """
    url_lower = url.lower()
    # Cloud uses api.bitbucket.org
    if "api.bitbucket.org" in url_lower or "bitbucket.org" in url_lower:
        return False
    # Server typically uses custom domains or contains /rest/api
    return "/rest/api" in url_lower or "api.bitbucket.org" not in url_lower
