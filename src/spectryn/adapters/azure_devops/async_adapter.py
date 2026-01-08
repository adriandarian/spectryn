"""
Async Azure DevOps Adapter - Async implementation of IssueTrackerPort for Azure DevOps.

Provides high-performance parallel operations using asyncio and aiohttp.
Use this for bulk operations that benefit from concurrent API calls.

Example:
    >>> async with AsyncAzureDevOpsAdapter(org, project, pat, dry_run=False) as adapter:
    ...     # Fetch multiple work items in parallel
    ...     items = await adapter.get_issues_async(work_item_ids)
    ...
    ...     # Update descriptions in parallel
    ...     results = await adapter.update_descriptions_async(updates)
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from types import TracebackType
from typing import TYPE_CHECKING, Any

from spectryn.core.ports.async_tracker import AsyncIssueTrackerPort
from spectryn.core.ports.issue_tracker import IssueData


if TYPE_CHECKING:
    import aiohttp

try:
    import aiohttp

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]


DEFAULT_BASE_URL = "https://dev.azure.com"
API_VERSION = "7.1"


class AsyncAzureDevOpsAdapter(AsyncIssueTrackerPort):
    """
    Async Azure DevOps implementation of AsyncIssueTrackerPort.

    Wraps aiohttp to provide high-level async operations for Azure DevOps REST API.
    Use via the context manager pattern for proper resource management.

    Requires aiohttp: pip install spectra[async]
    """

    def __init__(
        self,
        organization: str,
        project: str,
        pat: str,
        dry_run: bool = True,
        base_url: str = DEFAULT_BASE_URL,
        concurrency: int = 10,
        timeout: int = 30,
    ):
        """
        Initialize the async Azure DevOps adapter.

        Args:
            organization: Azure DevOps organization name
            project: Project name
            pat: Personal Access Token
            dry_run: If True, don't make changes
            base_url: Azure DevOps base URL
            concurrency: Max parallel requests
            timeout: Request timeout in seconds
        """
        if not ASYNC_AVAILABLE:
            raise ImportError(
                "Async support requires aiohttp. Install with: pip install spectra[async]"
            )

        self.organization = organization
        self.project = project
        self.pat = pat
        self._dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        self._concurrency = concurrency
        self.timeout = timeout
        self.logger = logging.getLogger("AsyncAzureDevOpsAdapter")

        # Build auth header
        auth_string = base64.b64encode(f":{pat}".encode()).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_string}",
        }

        self._session: aiohttp.ClientSession | None = None
        self._semaphore: Any = None

    async def connect(self) -> None:
        """Establish async connection."""
        import asyncio

        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._session = aiohttp.ClientSession(
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self.logger.debug("Async Azure DevOps connection established")

    async def disconnect(self) -> None:
        """Close async connection."""
        if self._session:
            await self._session.close()
            self._session = None
            self.logger.debug("Async Azure DevOps connection closed")

    async def __aenter__(self) -> AsyncAzureDevOpsAdapter:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    def _ensure_connected(self) -> aiohttp.ClientSession:
        """Ensure client is connected."""
        if self._session is None:
            raise RuntimeError("Async adapter not connected. Use 'async with' context manager.")
        return self._session

    def _build_url(self, endpoint: str, area: str = "wit") -> str:
        """Build the full API URL."""
        if endpoint.startswith("http"):
            return endpoint
        if area == "wit":
            return f"{self.base_url}/{self.organization}/{self.project}/_apis/wit/{endpoint}?api-version={API_VERSION}"
        if area == "core":
            return f"{self.base_url}/{self.organization}/_apis/{endpoint}?api-version={API_VERSION}"
        return f"{self.base_url}/{self.organization}/{self.project}/_apis/{endpoint}?api-version={API_VERSION}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        area: str = "wit",
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an async API request."""
        session = self._ensure_connected()
        url = self._build_url(endpoint, area)

        # Azure DevOps uses application/json-patch+json for PATCH
        headers = dict(self._headers)
        if method == "PATCH":
            headers["Content-Type"] = "application/json-patch+json"

        async with (
            self._semaphore,
            session.request(method, url, params=params, json=json, headers=headers) as response,
        ):
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"API error {response.status}: {text}")

            if response.content_type == "application/json":
                return await response.json()
            return {}

    def _parse_work_item_id(self, key: str) -> int:
        """Parse a work item key into an ID."""
        import re

        match = re.search(r"(\d+)", str(key))
        if match:
            return int(match.group(1))
        raise ValueError(f"Invalid work item key: {key}")

    # -------------------------------------------------------------------------
    # Async Read Operations
    # -------------------------------------------------------------------------

    async def get_issue_async(self, issue_key: str) -> IssueData:
        """Fetch a single work item asynchronously."""
        work_item_id = self._parse_work_item_id(issue_key)
        data = await self._request("GET", f"workitems/{work_item_id}", params={"$expand": "All"})
        return self._parse_work_item(data if isinstance(data, dict) else {})

    async def get_issues_async(self, issue_keys: Sequence[str]) -> list[IssueData]:
        """Fetch multiple work items in parallel."""
        import asyncio

        tasks = [self.get_issue_async(key) for key in issue_keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        issues = []
        for result in results:
            if isinstance(result, IssueData):
                issues.append(result)
            else:
                self.logger.warning(f"Failed to fetch work item: {result}")

        return issues

    async def get_epic_children_async(self, epic_key: str) -> list[IssueData]:
        """Fetch all children of an epic asynchronously."""
        # Azure DevOps uses relations for hierarchy
        # Fetch epic to validate it exists, but relations would need separate API call
        _ = await self.get_issue_async(epic_key)
        # Would need to fetch relations separately - simplified for now
        return []

    async def search_issues_async(self, query: str, max_results: int = 50) -> list[IssueData]:
        """Search for work items asynchronously."""
        # Azure DevOps uses WIQL (Work Item Query Language)
        # Simplified - would need proper WIQL query building
        return []

    # -------------------------------------------------------------------------
    # Async Write Operations
    # -------------------------------------------------------------------------

    async def update_descriptions_async(
        self,
        updates: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Update multiple work item descriptions in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} descriptions")
            return [(key, True, None) for key, _ in updates]

        async def update_one(key: str, desc: Any) -> tuple[str, bool, str | None]:
            try:
                work_item_id = self._parse_work_item_id(key)
                html_desc = self._markdown_to_html(str(desc))
                operations = [
                    {
                        "op": "replace",
                        "path": "/fields/System.Description",
                        "value": html_desc,
                    }
                ]
                await self._request("PATCH", f"workitems/{work_item_id}", json=operations)
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [update_one(key, desc) for key, desc in updates]
        return await asyncio.gather(*tasks)

    async def create_subtasks_async(
        self,
        subtasks: Sequence[dict[str, Any]],
    ) -> list[tuple[str | None, bool, str | None]]:
        """Create multiple subtasks in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create {len(subtasks)} subtasks")
            return [(None, True, None) for _ in subtasks]

        async def create_one(st: dict[str, Any]) -> tuple[str | None, bool, str | None]:
            try:
                parent_id = self._parse_work_item_id(st.get("parent_key", ""))
                html_desc = self._markdown_to_html(str(st.get("description", "")))

                operations = [
                    {
                        "op": "add",
                        "path": "/fields/System.Title",
                        "value": st.get("summary", "")[:255],
                    },
                    {"op": "add", "path": "/fields/System.Description", "value": html_desc},
                    {
                        "op": "add",
                        "path": "/relations/-",
                        "value": {
                            "rel": "System.LinkTypes.Hierarchy-Reverse",
                            "url": f"{self.base_url}/{self.organization}/{self.project}/_apis/wit/workItems/{parent_id}",
                        },
                    },
                ]

                if st.get("story_points"):
                    operations.append(
                        {
                            "op": "add",
                            "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints",
                            "value": float(st["story_points"]),
                        }
                    )

                data = await self._request("PATCH", "workitems/$Task", json=operations)
                work_item_id = data.get("id") if isinstance(data, dict) else None
                return (str(work_item_id) if work_item_id else None, True, None)
            except Exception as e:
                return (None, False, str(e))

        tasks = [create_one(st) for st in subtasks]
        return await asyncio.gather(*tasks)

    async def transition_issues_async(
        self,
        transitions: Sequence[tuple[str, str]],
    ) -> list[tuple[str, bool, str | None]]:
        """Transition multiple work items in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} work items")
            return [(key, True, None) for key, _ in transitions]

        async def transition_one(key: str, status: str) -> tuple[str, bool, str | None]:
            try:
                work_item_id = self._parse_work_item_id(key)
                operations = [
                    {
                        "op": "replace",
                        "path": "/fields/System.State",
                        "value": status,
                    }
                ]
                await self._request("PATCH", f"workitems/{work_item_id}", json=operations)
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [transition_one(key, status) for key, status in transitions]
        return await asyncio.gather(*tasks)

    async def add_comments_async(
        self,
        comments: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Add comments to multiple work items in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            return [(key, True, None) for key, _ in comments]

        async def add_one(key: str, body: Any) -> tuple[str, bool, str | None]:
            try:
                work_item_id = self._parse_work_item_id(key)
                await self._request(
                    "POST",
                    f"workitems/{work_item_id}/comments",
                    json={"text": str(body)},
                )
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [add_one(key, body) for key, body in comments]
        return await asyncio.gather(*tasks)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _parse_work_item(self, data: dict) -> IssueData:
        """Parse Azure DevOps work item into IssueData."""
        fields = data.get("fields", {})
        work_item_type = fields.get("System.WorkItemType", "")

        issue_type = "Sub-task" if work_item_type.lower() == "task" else "Story"

        assignee = None
        assigned_to = fields.get("System.AssignedTo")
        if assigned_to:
            if isinstance(assigned_to, dict):
                assignee = assigned_to.get("uniqueName") or assigned_to.get("displayName")
            else:
                assignee = str(assigned_to)

        story_points = fields.get("Microsoft.VSTS.Scheduling.StoryPoints")

        return IssueData(
            key=str(data.get("id", "")),
            summary=fields.get("System.Title", ""),
            description=fields.get("System.Description"),
            status=fields.get("System.State", ""),
            issue_type=issue_type,
            assignee=assignee,
            story_points=float(story_points) if story_points else None,
            subtasks=[],
            comments=[],
        )

    def _markdown_to_html(self, markdown: str) -> str:
        """Convert markdown to HTML for Azure DevOps."""
        import re

        html = markdown
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", html, flags=re.DOTALL)
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)


def is_async_available() -> bool:
    """Check if async operations are available."""
    return ASYNC_AVAILABLE


__all__ = ["ASYNC_AVAILABLE", "AsyncAzureDevOpsAdapter", "is_async_available"]
