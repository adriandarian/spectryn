"""
Async Asana Adapter - Async implementation of IssueTrackerPort for Asana.

Provides high-performance parallel operations using asyncio and aiohttp.
Use this for bulk operations that benefit from concurrent API calls.

Example:
    >>> async with AsyncAsanaAdapter(config, dry_run=False) as adapter:
    ...     # Fetch multiple tasks in parallel
    ...     tasks = await adapter.get_tasks_async(task_gids)
    ...
    ...     # Update descriptions in parallel
    ...     results = await adapter.update_descriptions_async(updates)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any

from spectryn.core.ports.async_tracker import AsyncIssueTrackerPort
from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData


if TYPE_CHECKING:
    import aiohttp

try:
    import aiohttp

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]


DEFAULT_BASE_URL = "https://app.asana.com/api/1.0"


@dataclass
class AsyncResult:
    """Result of an async operation."""

    success: bool
    key: str = ""
    error: str | None = None
    data: dict[str, Any] | None = None


class AsyncAsanaAdapter(AsyncIssueTrackerPort):
    """
    Async Asana implementation of AsyncIssueTrackerPort.

    Wraps aiohttp to provide high-level async operations.
    Use via the context manager pattern for proper resource management.

    Requires aiohttp: pip install spectra[async]
    """

    def __init__(
        self,
        config: TrackerConfig,
        dry_run: bool = True,
        concurrency: int = 10,
        base_url: str | None = None,
        timeout: int = 30,
    ):
        """
        Initialize the async Asana adapter.

        Args:
            config: Tracker configuration
            dry_run: If True, don't make changes
            concurrency: Max parallel requests
            base_url: Optional API base URL override
            timeout: Request timeout in seconds
        """
        if not ASYNC_AVAILABLE:
            raise ImportError(
                "Async support requires aiohttp. Install with: pip install spectra[async]"
            )

        self.config = config
        self._dry_run = dry_run
        self._concurrency = concurrency
        self.base_url = (base_url or config.url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.logger = logging.getLogger("AsyncAsanaAdapter")

        self._session: aiohttp.ClientSession | None = None
        self._semaphore: Any = None

    async def connect(self) -> None:
        """Establish async connection."""
        import asyncio

        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.config.api_token}"},
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        )
        self.logger.debug("Async Asana connection established")

    async def disconnect(self) -> None:
        """Close async connection."""
        if self._session:
            await self._session.close()
            self._session = None
            self.logger.debug("Async Asana connection closed")

    async def __aenter__(self) -> AsyncAsanaAdapter:
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

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an async API request."""
        session = self._ensure_connected()
        url = self._build_url(path)

        async with (
            self._semaphore,
            session.request(
                method,
                url,
                params=params,
                json=json,
            ) as response,
        ):
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"API error {response.status}: {text}")

            data = await response.json()
            result: dict[str, Any] = data.get("data", {})
            return result

    # -------------------------------------------------------------------------
    # Async Read Operations
    # -------------------------------------------------------------------------

    async def get_issue_async(self, issue_key: str) -> IssueData:
        """Fetch a single task asynchronously."""
        data = await self._request(
            "GET",
            f"/tasks/{issue_key}",
            params={"opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields"},
        )
        return self._parse_task(data)

    async def get_issues_async(self, issue_keys: Sequence[str]) -> list[IssueData]:
        """Fetch multiple tasks in parallel."""
        import asyncio

        tasks = [self.get_issue_async(key) for key in issue_keys]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        issues = []
        for result in results:
            if isinstance(result, IssueData):
                issues.append(result)
            else:
                self.logger.warning(f"Failed to fetch task: {result}")

        return issues

    async def get_epic_children_async(self, epic_key: str) -> list[IssueData]:
        """Fetch all tasks in a project asynchronously."""
        project_gid = epic_key or self.config.project_key
        data = await self._request(
            "GET",
            f"/projects/{project_gid}/tasks",
            params={"opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields"},
        )

        # Handle paginated response
        if isinstance(data, list):
            return [self._parse_task(task) for task in data]
        return []

    async def search_issues_async(self, query: str, max_results: int = 50) -> list[IssueData]:
        """Search for tasks asynchronously."""
        project_gid = self.config.project_key
        data = await self._request(
            "GET",
            f"/projects/{project_gid}/tasks",
            params={"opt_fields": "name,notes,completed,resource_subtype,assignee,custom_fields"},
        )

        if not isinstance(data, list):
            return []

        # Filter client-side
        matches = []
        query_lower = query.lower()
        for task in data:
            name = task.get("name", "").lower()
            if query_lower in name:
                matches.append(self._parse_task(task))
            if len(matches) >= max_results:
                break

        return matches

    # -------------------------------------------------------------------------
    # Async Write Operations
    # -------------------------------------------------------------------------

    async def update_descriptions_async(
        self,
        updates: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Update multiple task descriptions in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update {len(updates)} descriptions")
            return [(key, True, None) for key, _ in updates]

        async def update_one(key: str, desc: Any) -> tuple[str, bool, str | None]:
            try:
                await self._request(
                    "PUT",
                    f"/tasks/{key}",
                    json={"data": {"notes": str(desc)}},
                )
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
            parent_key = st.get("parent_key")
            project_key = st.get("project_key") or self.config.project_key

            payload: dict[str, Any] = {
                "name": st.get("summary", "")[:255],
                "notes": st.get("description", ""),
                "projects": [project_key],
            }

            if st.get("assignee"):
                payload["assignee"] = st["assignee"]

            try:
                data = await self._request(
                    "POST",
                    f"/tasks/{parent_key}/subtasks",
                    json={"data": payload},
                )
                gid = data.get("gid")
                return (gid, True, None)
            except Exception as e:
                return (None, False, str(e))

        tasks = [create_one(st) for st in subtasks]
        return await asyncio.gather(*tasks)

    async def transition_issues_async(
        self,
        transitions: Sequence[tuple[str, str]],
    ) -> list[tuple[str, bool, str | None]]:
        """Transition multiple tasks in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} tasks")
            return [(key, True, None) for key, _ in transitions]

        async def transition_one(key: str, status: str) -> tuple[str, bool, str | None]:
            completed = status.lower() in {"done", "complete", "completed"}
            try:
                await self._request(
                    "PUT",
                    f"/tasks/{key}",
                    json={"data": {"completed": completed}},
                )
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [transition_one(key, status) for key, status in transitions]
        return await asyncio.gather(*tasks)

    async def add_comments_async(
        self,
        comments: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, str | None]]:
        """Add comments to multiple tasks in parallel."""
        import asyncio

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            return [(key, True, None) for key, _ in comments]

        async def add_one(key: str, body: Any) -> tuple[str, bool, str | None]:
            try:
                await self._request(
                    "POST",
                    f"/tasks/{key}/stories",
                    json={"data": {"text": str(body)}},
                )
                return (key, True, None)
            except Exception as e:
                return (key, False, str(e))

        tasks = [add_one(key, body) for key, body in comments]
        return await asyncio.gather(*tasks)

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _parse_task(self, data: dict) -> IssueData:
        """Parse Asana API response into IssueData."""
        custom_fields = data.get("custom_fields", [])
        story_points = None
        for field in custom_fields:
            if field.get("name", "").lower() == "story points":
                try:
                    story_points = float(field.get("number_value", 0) or 0)
                except (TypeError, ValueError):
                    story_points = None

        assignee = data.get("assignee", {}) or {}
        status = "Done" if data.get("completed") else "In Progress"

        return IssueData(
            key=data.get("gid", ""),
            summary=data.get("name", ""),
            description=data.get("notes"),
            status=status,
            issue_type=data.get("resource_subtype", "task"),
            assignee=assignee.get("gid"),
            story_points=story_points,
            comments=[],
            links=[],
        )


def is_async_available() -> bool:
    """Check if async operations are available."""
    return ASYNC_AVAILABLE


__all__ = ["ASYNC_AVAILABLE", "AsyncAsanaAdapter", "is_async_available"]
