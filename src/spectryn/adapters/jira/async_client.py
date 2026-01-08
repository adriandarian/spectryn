"""
Async Jira API Client - Asyncio-compatible client for Jira REST API.

Provides parallel request support for high-performance Jira operations.
Uses the async_base infrastructure for rate limiting and connection pooling.
"""

import logging
from typing import Any

from spectryn.adapters.async_base import AsyncHttpClient, ParallelResult, batch_execute
from spectryn.core.ports.issue_tracker import (
    IssueTrackerError,
)


class AsyncJiraApiClient(AsyncHttpClient):
    """
    Async Jira REST API client with parallel request support.

    Extends AsyncHttpClient with Jira-specific functionality:
    - API version handling
    - Authentication
    - Batch operations for issues, subtasks, etc.
    - Parallel fetching of multiple issues

    Example:
        >>> async with AsyncJiraApiClient(
        ...     base_url="https://company.atlassian.net",
        ...     email="user@example.com",
        ...     api_token="your-token",
        ... ) as client:
        ...     # Fetch multiple issues in parallel
        ...     issues = await client.get_issues_parallel(
        ...         ["PROJ-1", "PROJ-2", "PROJ-3"]
        ...     )
    """

    API_VERSION = "3"

    # Default rate limiting for Jira Cloud
    # ~100 requests/minute for most endpoints
    DEFAULT_REQUESTS_PER_SECOND = 5.0
    DEFAULT_BURST_SIZE = 10

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        dry_run: bool = True,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: float = 0.1,
        timeout: float = 30.0,
        requests_per_second: float | None = DEFAULT_REQUESTS_PER_SECOND,
        burst_size: int = DEFAULT_BURST_SIZE,
        concurrency: int = 5,
    ):
        """
        Initialize the async Jira client.

        Args:
            base_url: Jira instance URL (e.g., https://company.atlassian.net)
            email: User email for authentication
            api_token: API token
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay
            backoff_factor: Exponential backoff multiplier
            jitter: Random jitter factor
            timeout: Request timeout in seconds
            requests_per_second: Rate limit (None to disable)
            burst_size: Rate limiter burst size
            concurrency: Max parallel requests for batch operations
        """
        api_url = f"{base_url.rstrip('/')}/rest/api/{self.API_VERSION}"

        # Setup basic auth header
        import base64

        credentials = f"{email}:{api_token}"
        auth_bytes = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_bytes}",
        }

        super().__init__(
            base_url=api_url,
            headers=headers,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            jitter=jitter,
            timeout=timeout,
            requests_per_second=requests_per_second,
            burst_size=burst_size,
        )

        self.dry_run = dry_run
        self.concurrency = concurrency
        self.logger = logging.getLogger("AsyncJiraApiClient")

        # Cache
        self._current_user: dict | None = None

    # -------------------------------------------------------------------------
    # Write Operation Overrides (respect dry_run)
    # -------------------------------------------------------------------------

    async def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """POST request with dry_run support."""
        if self.dry_run and not endpoint.endswith("search/jql"):
            self.logger.info(f"[DRY-RUN] Would POST to {endpoint}")
            return {}
        return await super().post(endpoint, json=json, **kwargs)

    async def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """PUT request with dry_run support."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PUT to {endpoint}")
            return {}
        return await super().put(endpoint, json=json, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """DELETE request with dry_run support."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {endpoint}")
            return {}
        return await super().delete(endpoint, **kwargs)

    # -------------------------------------------------------------------------
    # User API
    # -------------------------------------------------------------------------

    async def get_myself(self) -> dict[str, Any]:
        """Get the current authenticated user (cached)."""
        if self._current_user is None:
            result = await self.get("myself")
            self._current_user = result if isinstance(result, dict) else {}
        return self._current_user

    async def get_current_user_id(self) -> str:
        """Get the current user's Jira account ID."""
        user = await self.get_myself()
        return user.get("accountId", "")

    async def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            await self.get_myself()
            return True
        except IssueTrackerError:
            return False

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    async def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get a single issue by key.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Optional list of fields to include

        Returns:
            Issue data dict
        """
        params = {}
        if fields:
            params["fields"] = ",".join(fields)

        result = await self.get(f"issue/{issue_key}", params=params)
        return result if isinstance(result, dict) else {}

    async def get_issues_parallel(
        self,
        issue_keys: list[str],
        fields: list[str] | None = None,
        concurrency: int | None = None,
    ) -> ParallelResult[dict[str, Any]]:
        """
        Fetch multiple issues in parallel.

        Args:
            issue_keys: List of issue keys to fetch
            fields: Optional fields to include
            concurrency: Max parallel requests (defaults to self.concurrency)

        Returns:
            ParallelResult with issue data dicts

        Example:
            >>> result = await client.get_issues_parallel(
            ...     ["PROJ-1", "PROJ-2", "PROJ-3"],
            ...     fields=["summary", "status", "description"],
            ... )
            >>> for issue in result.results:
            ...     print(issue["key"], issue["fields"]["summary"])
        """

        async def fetch_issue(key: str) -> dict[str, Any]:
            return await self.get_issue(key, fields=fields)

        return await batch_execute(
            items=issue_keys,
            operation=fetch_issue,
            batch_size=50,
            concurrency=concurrency or self.concurrency,
            rate_limiter=self._rate_limiter,
        )

    async def search_jql(
        self,
        jql: str,
        fields: list[str],
        max_results: int = 100,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """
        Execute a JQL search query.

        Args:
            jql: JQL query string
            fields: Fields to include in results
            max_results: Maximum results per page
            start_at: Starting offset for pagination

        Returns:
            Search results with issues list and pagination info
        """
        result = await self.post(
            "search/jql",
            json={
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at,
                "fields": fields,
            },
        )
        return result if isinstance(result, dict) else {}

    async def search_all_jql(
        self,
        jql: str,
        fields: list[str],
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Execute a JQL search and paginate through all results.

        Args:
            jql: JQL query string
            fields: Fields to include
            page_size: Results per page

        Returns:
            List of all matching issues
        """
        all_issues: list[dict[str, Any]] = []
        start_at = 0

        while True:
            result = await self.search_jql(
                jql=jql,
                fields=fields,
                max_results=page_size,
                start_at=start_at,
            )

            issues = result.get("issues", [])
            all_issues.extend(issues)

            total = result.get("total", 0)
            if start_at + len(issues) >= total:
                break

            start_at += page_size

        return all_issues

    # -------------------------------------------------------------------------
    # Issue Operations
    # -------------------------------------------------------------------------

    async def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Update an issue's fields.

        Args:
            issue_key: Issue key
            fields: Fields to update

        Returns:
            Empty dict on success
        """
        return await self.put(f"issue/{issue_key}", json={"fields": fields})

    async def update_issues_parallel(
        self,
        updates: list[tuple[str, dict[str, Any]]],
        concurrency: int | None = None,
    ) -> ParallelResult[dict[str, Any]]:
        """
        Update multiple issues in parallel.

        Args:
            updates: List of (issue_key, fields) tuples
            concurrency: Max parallel updates

        Returns:
            ParallelResult with update results

        Example:
            >>> updates = [
            ...     ("PROJ-1", {"description": "New desc 1"}),
            ...     ("PROJ-2", {"description": "New desc 2"}),
            ... ]
            >>> result = await client.update_issues_parallel(updates)
        """

        async def do_update(update: tuple[str, dict[str, Any]]) -> dict[str, Any]:
            key, fields = update
            await self.update_issue(key, fields)
            return {"key": key, "success": True}

        return await batch_execute(
            items=updates,
            operation=do_update,
            batch_size=20,
            concurrency=concurrency or self.concurrency,
            rate_limiter=self._rate_limiter,
        )

    async def create_issue(
        self,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            fields: Issue fields

        Returns:
            Created issue data with key
        """
        result = await self.post("issue", json={"fields": fields})
        return result if isinstance(result, dict) else {}

    async def create_issues_parallel(
        self,
        issues: list[dict[str, Any]],
        concurrency: int | None = None,
    ) -> ParallelResult[dict[str, Any]]:
        """
        Create multiple issues in parallel.

        Args:
            issues: List of issue field dicts
            concurrency: Max parallel creates

        Returns:
            ParallelResult with created issue data
        """

        async def do_create(fields: dict[str, Any]) -> dict[str, Any]:
            return await self.create_issue(fields)

        return await batch_execute(
            items=issues,
            operation=do_create,
            batch_size=10,  # Smaller batches for creates
            concurrency=concurrency or self.concurrency,
            rate_limiter=self._rate_limiter,
        )

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    async def get_comments(self, issue_key: str) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        result = await self.get(f"issue/{issue_key}/comment")
        if isinstance(result, dict):
            return result.get("comments", [])
        return []

    async def add_comment(
        self,
        issue_key: str,
        body: Any,
    ) -> dict[str, Any]:
        """
        Add a comment to an issue.

        Args:
            issue_key: Issue key
            body: Comment body (ADF format for Jira Cloud)

        Returns:
            Created comment data
        """
        result = await self.post(f"issue/{issue_key}/comment", json={"body": body})
        return result if isinstance(result, dict) else {}

    async def add_comments_parallel(
        self,
        comments: list[tuple[str, Any]],
        concurrency: int | None = None,
    ) -> ParallelResult[dict[str, Any]]:
        """
        Add comments to multiple issues in parallel.

        Args:
            comments: List of (issue_key, body) tuples
            concurrency: Max parallel operations

        Returns:
            ParallelResult with comment creation results
        """

        async def do_add_comment(item: tuple[str, Any]) -> dict[str, Any]:
            key, body = item
            return await self.add_comment(key, body)

        return await batch_execute(
            items=comments,
            operation=do_add_comment,
            batch_size=20,
            concurrency=concurrency or self.concurrency,
            rate_limiter=self._rate_limiter,
        )

    # -------------------------------------------------------------------------
    # Transitions API
    # -------------------------------------------------------------------------

    async def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Get available transitions for an issue."""
        result = await self.get(f"issue/{issue_key}/transitions")
        if isinstance(result, dict):
            return result.get("transitions", [])
        return []

    async def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a transition on an issue.

        Args:
            issue_key: Issue key
            transition_id: Transition ID
            fields: Optional fields to set during transition

        Returns:
            Empty dict on success
        """
        payload: dict[str, Any] = {"transition": {"id": transition_id}}
        if fields:
            payload["fields"] = fields

        result = await self.post(f"issue/{issue_key}/transitions", json=payload)
        return result if isinstance(result, dict) else {}

    async def transition_issues_parallel(
        self,
        transitions: list[tuple[str, str, dict[str, Any] | None]],
        concurrency: int | None = None,
    ) -> ParallelResult[dict[str, Any]]:
        """
        Execute transitions on multiple issues in parallel.

        Args:
            transitions: List of (issue_key, transition_id, fields) tuples
            concurrency: Max parallel transitions

        Returns:
            ParallelResult with transition results
        """

        async def do_transition(item: tuple[str, str, dict[str, Any] | None]) -> dict[str, Any]:
            key, transition_id, fields = item
            await self.transition_issue(key, transition_id, fields)
            return {"key": key, "success": True}

        return await batch_execute(
            items=transitions,
            operation=do_transition,
            batch_size=10,
            concurrency=concurrency or self.concurrency,
            rate_limiter=self._rate_limiter,
        )

    # -------------------------------------------------------------------------
    # Links API
    # -------------------------------------------------------------------------

    async def get_issue_links(self, issue_key: str) -> list[dict[str, Any]]:
        """Get all links for an issue."""
        result = await self.get(f"issue/{issue_key}", params={"fields": "issuelinks"})
        if isinstance(result, dict):
            return result.get("fields", {}).get("issuelinks", [])
        return []

    async def create_link(
        self,
        link_type: str,
        inward_key: str,
        outward_key: str,
    ) -> dict[str, Any]:
        """
        Create a link between two issues.

        Args:
            link_type: Link type name (e.g., "Blocks")
            inward_key: Inward issue key
            outward_key: Outward issue key

        Returns:
            Empty dict on success
        """
        result = await self.post(
            "issueLink",
            json={
                "type": {"name": link_type},
                "inwardIssue": {"key": inward_key},
                "outwardIssue": {"key": outward_key},
            },
        )
        return result if isinstance(result, dict) else {}

    async def delete_link(self, link_id: str) -> dict[str, Any]:
        """Delete a link by ID."""
        result = await self.delete(f"issueLink/{link_id}")
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Epic Children API
    # -------------------------------------------------------------------------

    async def get_epic_children(
        self,
        epic_key: str,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all children of an epic.

        Args:
            epic_key: Epic issue key
            fields: Fields to include (defaults to basic fields)

        Returns:
            List of child issues
        """
        if fields is None:
            fields = ["summary", "description", "status", "issuetype", "subtasks"]

        jql = f"parent = {epic_key} ORDER BY key ASC"
        return await self.search_all_jql(jql, fields)

    # -------------------------------------------------------------------------
    # Bulk Operations
    # -------------------------------------------------------------------------

    async def get_subtasks_for_issues(
        self,
        issue_keys: list[str],
        fields: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Get subtasks for multiple issues in parallel.

        Args:
            issue_keys: Parent issue keys
            fields: Fields to include for subtasks

        Returns:
            Dict mapping parent key to list of subtasks
        """
        if fields is None:
            fields = ["summary", "status", "assignee"]

        async def fetch_issue_with_subtasks(key: str) -> tuple[str, list[dict[str, Any]]]:
            issue = await self.get_issue(key, fields=["subtasks"])
            subtasks = issue.get("fields", {}).get("subtasks", [])

            # Subtasks from the issue only have key and basic info
            # Fetch full details in parallel if needed
            if subtasks and fields != ["key"]:
                subtask_keys = [st["key"] for st in subtasks]
                result = await self.get_issues_parallel(subtask_keys, fields=fields)
                return (key, result.results)

            return (key, subtasks)

        # Fetch in parallel
        result = await batch_execute(
            items=issue_keys,
            operation=fetch_issue_with_subtasks,
            batch_size=20,
            concurrency=self.concurrency,
            rate_limiter=self._rate_limiter,
        )

        # Build result dict
        subtasks_map: dict[str, list[dict[str, Any]]] = {}
        for key, subtasks in result.results:
            subtasks_map[key] = subtasks

        return subtasks_map
