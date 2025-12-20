"""
Parallel Sync - High-level parallel operations for sync workflows.

Provides async-enabled batch operations for sync tasks:
- Parallel issue fetching
- Parallel description updates
- Parallel subtask creation
- Parallel comment addition
- Parallel status transitions

Can be used with or without asyncio - provides both sync and async interfaces.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast


if TYPE_CHECKING:
    from spectra.adapters.jira.async_client import AsyncJiraApiClient


logger = logging.getLogger("parallel_sync")


@dataclass
class ParallelSyncResult:
    """
    Result of a parallel sync operation.

    Tracks successes, failures, and provides summary statistics.
    """

    operation: str
    total: int = 0
    successful: int = 0
    failed: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (key, error_message)

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @property
    def all_succeeded(self) -> bool:
        """Check if all operations succeeded."""
        return self.failed == 0

    def __str__(self) -> str:
        return f"{self.operation}: {self.successful}/{self.total} succeeded ({self.failed} failed)"


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get existing event loop or create a new one."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.new_event_loop()


def run_async(coro: Any) -> Any:
    """
    Run an async coroutine from sync code.

    Handles event loop creation and cleanup.
    """
    try:
        asyncio.get_running_loop()
        # Already in an async context - can't use run()
        # This shouldn't happen in normal usage
        raise RuntimeError(
            "Cannot run parallel operations from within an async context. "
            "Use the async methods directly instead."
        )
    except RuntimeError:
        # No running loop - safe to create one
        return asyncio.run(coro)


class ParallelSyncOperations:
    """
    High-level parallel sync operations.

    Provides both sync and async interfaces for common sync tasks.
    Uses AsyncJiraApiClient internally for parallel requests.

    Example (sync usage):
        >>> ops = ParallelSyncOperations(
        ...     base_url="https://company.atlassian.net",
        ...     email="user@example.com",
        ...     api_token="token",
        ... )
        >>> result = ops.fetch_issues_parallel(
        ...     ["PROJ-1", "PROJ-2", "PROJ-3"]
        ... )
        >>> print(f"Fetched {result.successful} issues")

    Example (async usage):
        >>> async with ParallelSyncOperations(...) as ops:
        ...     result = await ops.fetch_issues_parallel_async(...)
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        dry_run: bool = True,
        concurrency: int = 5,
        requests_per_second: float = 5.0,
    ):
        """
        Initialize parallel sync operations.

        Args:
            base_url: Jira instance URL
            email: User email
            api_token: API token
            dry_run: If True, don't make writes
            concurrency: Max parallel requests
            requests_per_second: Rate limit
        """
        self.base_url = base_url
        self.email = email
        self.api_token = api_token
        self.dry_run = dry_run
        self.concurrency = concurrency
        self.requests_per_second = requests_per_second

        self._client: AsyncJiraApiClient | None = None

    def _get_client(self) -> "AsyncJiraApiClient":
        """Get or create the async client."""
        if self._client is None:
            from spectra.adapters.jira.async_client import AsyncJiraApiClient

            self._client = AsyncJiraApiClient(
                base_url=self.base_url,
                email=self.email,
                api_token=self.api_token,
                dry_run=self.dry_run,
                concurrency=self.concurrency,
                requests_per_second=self.requests_per_second,
            )
        return self._client

    # -------------------------------------------------------------------------
    # Async Methods
    # -------------------------------------------------------------------------

    async def fetch_issues_parallel_async(
        self,
        issue_keys: list[str],
        fields: list[str] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Fetch multiple issues in parallel (async).

        Args:
            issue_keys: Issue keys to fetch
            fields: Fields to include
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with fetched issues
        """
        client = self._get_client()
        result = ParallelSyncResult(operation="fetch_issues", total=len(issue_keys))

        if not issue_keys:
            return result

        from spectra.adapters.async_base import batch_execute

        async def fetch_issue(key: str) -> dict[str, Any]:
            return await client.get_issue(key, fields=fields)

        batch_result = await batch_execute(
            items=issue_keys,
            operation=fetch_issue,
            batch_size=50,
            concurrency=self.concurrency,
            rate_limiter=client._rate_limiter,
            progress_callback=progress_callback,
        )

        result.results = batch_result.results
        result.successful = len(batch_result.results)

        for idx, exc in batch_result.errors:
            key = issue_keys[idx] if idx < len(issue_keys) else f"index_{idx}"
            result.errors.append((key, str(exc)))
            result.failed += 1

        return result

    async def update_descriptions_parallel_async(
        self,
        updates: list[tuple[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Update multiple issue descriptions in parallel (async).

        Args:
            updates: List of (issue_key, description) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with update results
        """
        client = self._get_client()
        result = ParallelSyncResult(operation="update_descriptions", total=len(updates))

        if not updates:
            return result

        from spectra.adapters.async_base import batch_execute

        async def update_desc(item: tuple[str, Any]) -> dict[str, Any]:
            key, desc = item
            await client.update_issue(key, {"description": desc})
            return {"key": key, "success": True}

        batch_result = await batch_execute(
            items=updates,
            operation=update_desc,
            batch_size=20,
            concurrency=self.concurrency,
            rate_limiter=client._rate_limiter,
            progress_callback=progress_callback,
        )

        result.results = batch_result.results
        result.successful = len(batch_result.results)

        for idx, exc in batch_result.errors:
            key = updates[idx][0] if idx < len(updates) else f"index_{idx}"
            result.errors.append((key, str(exc)))
            result.failed += 1

        return result

    async def create_subtasks_parallel_async(
        self,
        subtasks: list[dict[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Create multiple subtasks in parallel (async).

        Args:
            subtasks: List of subtask field dicts (must include project, parent, etc.)
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with created subtask keys
        """
        client = self._get_client()
        result = ParallelSyncResult(operation="create_subtasks", total=len(subtasks))

        if not subtasks:
            return result

        from spectra.adapters.async_base import batch_execute

        async def create_subtask(fields: dict[str, Any]) -> dict[str, Any]:
            return await client.create_issue(fields)

        batch_result = await batch_execute(
            items=subtasks,
            operation=create_subtask,
            batch_size=10,
            concurrency=self.concurrency,
            rate_limiter=client._rate_limiter,
            progress_callback=progress_callback,
        )

        result.results = batch_result.results
        result.successful = len(batch_result.results)
        result.failed = len(batch_result.errors)

        for idx, exc in batch_result.errors:
            parent_key = subtasks[idx].get("parent", {}).get("key", f"index_{idx}")
            result.errors.append((parent_key, str(exc)))

        return result

    async def add_comments_parallel_async(
        self,
        comments: list[tuple[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Add comments to multiple issues in parallel (async).

        Args:
            comments: List of (issue_key, comment_body) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with comment results
        """
        client = self._get_client()
        result = ParallelSyncResult(operation="add_comments", total=len(comments))

        if not comments:
            return result

        from spectra.adapters.async_base import batch_execute

        async def add_comment(item: tuple[str, Any]) -> dict[str, Any]:
            key, body = item
            await client.add_comment(key, body)
            return {"key": key, "success": True}

        batch_result = await batch_execute(
            items=comments,
            operation=add_comment,
            batch_size=20,
            concurrency=self.concurrency,
            rate_limiter=client._rate_limiter,
            progress_callback=progress_callback,
        )

        result.results = batch_result.results
        result.successful = len(batch_result.results)

        for idx, exc in batch_result.errors:
            key = comments[idx][0] if idx < len(comments) else f"index_{idx}"
            result.errors.append((key, str(exc)))
            result.failed += 1

        return result

    async def transition_issues_parallel_async(
        self,
        transitions: list[tuple[str, str]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Transition multiple issues in parallel (async).

        Args:
            transitions: List of (issue_key, transition_id) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with transition results
        """
        client = self._get_client()
        result = ParallelSyncResult(operation="transition_issues", total=len(transitions))

        if not transitions:
            return result

        from spectra.adapters.async_base import batch_execute

        async def do_transition(item: tuple[str, str]) -> dict[str, Any]:
            key, transition_id = item
            await client.transition_issue(key, transition_id)
            return {"key": key, "success": True}

        batch_result = await batch_execute(
            items=transitions,
            operation=do_transition,
            batch_size=10,
            concurrency=self.concurrency,
            rate_limiter=client._rate_limiter,
            progress_callback=progress_callback,
        )

        result.results = batch_result.results
        result.successful = len(batch_result.results)

        for idx, exc in batch_result.errors:
            key = transitions[idx][0] if idx < len(transitions) else f"index_{idx}"
            result.errors.append((key, str(exc)))
            result.failed += 1

        return result

    async def close_async(self) -> None:
        """Close the async client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> "ParallelSyncOperations":
        """Async context manager entry."""
        self._get_client()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close_async()

    # -------------------------------------------------------------------------
    # Sync Methods (wrappers around async methods)
    # -------------------------------------------------------------------------

    def fetch_issues_parallel(
        self,
        issue_keys: list[str],
        fields: list[str] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Fetch multiple issues in parallel (sync wrapper).

        Args:
            issue_keys: Issue keys to fetch
            fields: Fields to include
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with fetched issues
        """

        async def _run() -> ParallelSyncResult:
            try:
                return await self.fetch_issues_parallel_async(issue_keys, fields, progress_callback)
            finally:
                await self.close_async()

        return cast(ParallelSyncResult, run_async(_run()))

    def update_descriptions_parallel(
        self,
        updates: list[tuple[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Update multiple issue descriptions in parallel (sync wrapper).

        Args:
            updates: List of (issue_key, description) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with update results
        """

        async def _run() -> ParallelSyncResult:
            try:
                return await self.update_descriptions_parallel_async(updates, progress_callback)
            finally:
                await self.close_async()

        return cast(ParallelSyncResult, run_async(_run()))

    def create_subtasks_parallel(
        self,
        subtasks: list[dict[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Create multiple subtasks in parallel (sync wrapper).

        Args:
            subtasks: List of subtask field dicts
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with created subtask keys
        """

        async def _run() -> ParallelSyncResult:
            try:
                return await self.create_subtasks_parallel_async(subtasks, progress_callback)
            finally:
                await self.close_async()

        return cast(ParallelSyncResult, run_async(_run()))

    def add_comments_parallel(
        self,
        comments: list[tuple[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Add comments to multiple issues in parallel (sync wrapper).

        Args:
            comments: List of (issue_key, comment_body) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with comment results
        """

        async def _run() -> ParallelSyncResult:
            try:
                return await self.add_comments_parallel_async(comments, progress_callback)
            finally:
                await self.close_async()

        return cast(ParallelSyncResult, run_async(_run()))

    def transition_issues_parallel(
        self,
        transitions: list[tuple[str, str]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Transition multiple issues in parallel (sync wrapper).

        Args:
            transitions: List of (issue_key, transition_id) tuples
            progress_callback: Optional progress callback

        Returns:
            ParallelSyncResult with transition results
        """

        async def _run() -> ParallelSyncResult:
            try:
                return await self.transition_issues_parallel_async(transitions, progress_callback)
            finally:
                await self.close_async()

        return cast(ParallelSyncResult, run_async(_run()))


def is_parallel_available() -> bool:
    """
    Check if parallel operations are available.

    Requires aiohttp to be installed.
    """
    try:
        import aiohttp  # noqa: F401

        return True
    except ImportError:
        return False
