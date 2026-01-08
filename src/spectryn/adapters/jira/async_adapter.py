"""
Async Jira Adapter - Async implementation of IssueTrackerPort for Jira.

Provides high-performance parallel operations using asyncio and aiohttp.
Use this for bulk operations that benefit from concurrent API calls.

Example:
    >>> async with AsyncJiraAdapter(config, dry_run=False) as adapter:
    ...     # Fetch 100 issues in parallel (respecting rate limits)
    ...     issues = await adapter.get_issues_async(issue_keys)
    ...
    ...     # Update descriptions in parallel
    ...     results = await adapter.update_descriptions_async(updates)
"""

import logging
from collections.abc import Sequence
from typing import Any

from spectryn.core.constants import IssueType, JiraField
from spectryn.core.ports.async_tracker import AsyncIssueTrackerPort
from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData


try:
    from .async_client import AsyncJiraApiClient

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    AsyncJiraApiClient = None  # type: ignore


class AsyncJiraAdapter(AsyncIssueTrackerPort):
    """
    Async Jira implementation of AsyncIssueTrackerPort.

    Wraps AsyncJiraApiClient to provide high-level async operations.
    Use via the context manager pattern for proper resource management.

    Requires aiohttp: pip install spectra[async]
    """

    def __init__(
        self,
        config: TrackerConfig,
        dry_run: bool = True,
        formatter: Any | None = None,
        concurrency: int = 10,
    ):
        """
        Initialize the async Jira adapter.

        Args:
            config: Tracker configuration
            dry_run: If True, don't make changes
            formatter: Optional ADF formatter
            concurrency: Max parallel requests
        """
        if not ASYNC_AVAILABLE:
            raise ImportError(
                "Async support requires aiohttp. Install with: pip install spectra[async]"
            )

        self.config = config
        self._dry_run = dry_run
        self._concurrency = concurrency
        self.logger = logging.getLogger("AsyncJiraAdapter")

        # Lazy import to avoid circular deps
        if formatter is None:
            from spectryn.adapters.formatters.adf import ADFFormatter

            formatter = ADFFormatter()
        self.formatter = formatter

        self._client: AsyncJiraApiClient | None = None

    async def connect(self) -> None:
        """Establish async connection."""
        self._client = AsyncJiraApiClient(
            base_url=self.config.url,
            email=self.config.email,
            api_token=self.config.api_token,
            dry_run=self._dry_run,
            concurrency=self._concurrency,
        )
        await self._client.__aenter__()
        self.logger.debug("Async Jira connection established")

    async def disconnect(self) -> None:
        """Close async connection."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
            self.logger.debug("Async Jira connection closed")

    def _ensure_connected(self) -> AsyncJiraApiClient:
        """Ensure client is connected."""
        if self._client is None:
            raise RuntimeError("Async adapter not connected. Use 'async with' context manager.")
        return self._client

    # -------------------------------------------------------------------------
    # Async Read Operations
    # -------------------------------------------------------------------------

    async def get_issue_async(self, issue_key: str) -> IssueData:
        """Fetch a single issue asynchronously."""
        client = self._ensure_connected()
        data = await client.get(f"issue/{issue_key}")
        return self._parse_issue(data)

    async def get_issues_async(self, issue_keys: Sequence[str]) -> list[IssueData]:
        """Fetch multiple issues in parallel."""
        client = self._ensure_connected()

        fields = ",".join(JiraField.ISSUE_WITH_SUBTASKS)
        results = await client.get_issues_parallel(list(issue_keys), fields=[fields])

        issues = []
        for _key, data in results.items():
            if data is not None:
                issues.append(self._parse_issue(data))

        return issues

    async def get_epic_children_async(self, epic_key: str) -> list[IssueData]:
        """Fetch all children of an epic asynchronously."""
        client = self._ensure_connected()

        jql = f"{JiraField.PARENT} = {epic_key} ORDER BY {JiraField.KEY} ASC"
        data = await client.search_jql(jql, list(JiraField.ISSUE_WITH_SUBTASKS))

        return [self._parse_issue(issue) for issue in data.get("issues", [])]

    async def search_issues_async(self, query: str, max_results: int = 50) -> list[IssueData]:
        """Search for issues asynchronously."""
        client = self._ensure_connected()

        data = await client.search_jql(query, list(JiraField.BASIC_FIELDS), max_results=max_results)

        return [self._parse_issue(issue) for issue in data.get("issues", [])]

    # -------------------------------------------------------------------------
    # Async Write Operations
    # -------------------------------------------------------------------------

    async def update_descriptions_async(
        self,
        updates: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Update multiple issue descriptions in parallel."""
        client = self._ensure_connected()

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} descriptions")
            return [(key, True, None) for key, _ in updates]

        results = await client.update_issues_parallel(list(updates))

        return [
            (key, result.success, result.error if not result.success else None)
            for key, result in results.items()
        ]

    async def create_subtasks_async(
        self,
        subtasks: Sequence[dict[str, Any]],
    ) -> list[tuple[str | None, bool, str | None]]:
        """Create multiple subtasks in parallel."""
        client = self._ensure_connected()

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create {len(subtasks)} subtasks")
            return [(None, True, None) for _ in subtasks]

        # Format subtasks for the API
        api_subtasks = []
        for st in subtasks:
            api_subtasks.append(
                {
                    JiraField.PROJECT: {JiraField.KEY: st["project_key"]},
                    JiraField.PARENT: {JiraField.KEY: st["parent_key"]},
                    JiraField.SUMMARY: st["summary"][:255],
                    JiraField.DESCRIPTION: st.get("description", ""),
                    JiraField.ISSUETYPE: {JiraField.NAME: IssueType.JIRA_SUBTASK},
                }
            )

        results = await client.create_issues_parallel(api_subtasks)

        output = []
        for result in results:
            if result.success:
                output.append((result.key, True, None))
            else:
                output.append((None, False, result.error))

        return output

    async def transition_issues_async(
        self,
        transitions: Sequence[tuple[str, str]],
    ) -> list[tuple[str, bool, str | None]]:
        """Transition multiple issues in parallel."""
        client = self._ensure_connected()

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} issues")
            return [(key, True, None) for key, _ in transitions]

        results = await client.transition_issues_parallel(list(transitions))

        return [
            (key, result.success, result.error if not result.success else None)
            for key, result in results.items()
        ]

    async def add_comments_async(
        self,
        comments: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Add comments to multiple issues in parallel."""
        client = self._ensure_connected()

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            return [(key, True, None) for key, _ in comments]

        results = await client.add_comments_parallel(list(comments))

        return [
            (key, result.success, result.error if not result.success else None)
            for key, result in results.items()
        ]

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse Jira API response into IssueData."""
        fields = data.get(JiraField.FIELDS, {})

        subtasks = []
        for st in fields.get(JiraField.SUBTASKS, []):
            subtasks.append(
                IssueData(
                    key=st[JiraField.KEY],
                    summary=st[JiraField.FIELDS][JiraField.SUMMARY],
                    status=st[JiraField.FIELDS][JiraField.STATUS][JiraField.NAME],
                    issue_type=IssueType.SUBTASK,
                )
            )

        return IssueData(
            key=data[JiraField.KEY],
            summary=fields.get(JiraField.SUMMARY, ""),
            description=fields.get(JiraField.DESCRIPTION),
            status=fields.get(JiraField.STATUS, {}).get(JiraField.NAME, ""),
            issue_type=fields.get(JiraField.ISSUETYPE, {}).get(JiraField.NAME, ""),
            subtasks=subtasks,
        )


def is_async_available() -> bool:
    """Check if async operations are available."""
    return ASYNC_AVAILABLE


__all__ = ["ASYNC_AVAILABLE", "AsyncJiraAdapter", "is_async_available"]
