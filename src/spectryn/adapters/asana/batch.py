"""
Asana Batch Operations - Bulk operations for improved performance.

Provides batch operations for Asana, using parallel execution
since Asana doesn't have native bulk APIs.

Components:
- BatchOperation: Result of a single operation within a batch
- BatchResult: Aggregated results from a batch operation
- AsanaBatchClient: Client for batch operations
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import requests

from spectryn.core.exceptions import TrackerError


@dataclass
class BatchOperation:
    """
    Result of a single operation within a batch.

    Attributes:
        index: Position in the batch (0-indexed)
        success: Whether the operation succeeded
        key: Task GID (for created/updated tasks)
        error: Error message if failed
        data: Additional response data
    """

    index: int
    success: bool = True
    key: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        if self.success:
            return f"[{self.index}] {self.key}: OK"
        return f"[{self.index}] {self.key or 'N/A'}: FAILED - {self.error}"


@dataclass
class BatchResult:
    """
    Aggregated results from a batch operation.

    Attributes:
        success: True if all operations succeeded
        total: Total number of operations
        succeeded: Number of successful operations
        failed: Number of failed operations
        operations: Individual operation results
        errors: List of error messages
    """

    success: bool = True
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    operations: list[BatchOperation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def created_keys(self) -> list[str]:
        """Get keys of successfully created/processed tasks."""
        return [op.key for op in self.operations if op.success and op.key]

    @property
    def failed_indices(self) -> list[int]:
        """Get indices of failed operations."""
        return [op.index for op in self.operations if not op.success]

    def add_success(self, index: int, key: str, data: dict[str, Any] | None = None) -> None:
        """Add a successful operation."""
        self.operations.append(
            BatchOperation(
                index=index,
                success=True,
                key=key,
                data=data or {},
            )
        )
        self.succeeded += 1
        self.total += 1

    def add_failure(self, index: int, error: str, key: str = "") -> None:
        """Add a failed operation."""
        self.operations.append(
            BatchOperation(
                index=index,
                success=False,
                key=key,
                error=error,
            )
        )
        self.failed += 1
        self.total += 1
        self.errors.append(error)
        self.success = False

    def summary(self) -> str:
        """Generate human-readable summary."""
        return f"Batch: {self.succeeded}/{self.total} succeeded, {self.failed} failed"


class AsanaBatchClient:
    """
    Client for Asana batch operations.

    Uses parallel execution for all batch operations since
    Asana doesn't have native bulk APIs.

    Example:
        >>> from spectryn.adapters.asana import AsanaAdapter
        >>> adapter = AsanaAdapter(config, dry_run=False)
        >>> batch_client = AsanaBatchClient(adapter)
        >>>
        >>> # Bulk create subtasks
        >>> subtasks = [
        ...     {"parent_gid": "123", "name": "Task 1", "notes": "..."},
        ...     {"parent_gid": "123", "name": "Task 2", "notes": "..."},
        ... ]
        >>> result = batch_client.bulk_create_subtasks("456", subtasks)
        >>> print(f"Created: {result.created_keys}")
    """

    # Maximum concurrent threads for parallel operations
    MAX_WORKERS = 10

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        api_token: str,
        dry_run: bool = True,
        max_workers: int = 10,
        timeout: int = 30,
    ):
        """
        Initialize the batch client.

        Args:
            session: Requests session to use
            base_url: Asana API base URL
            api_token: Asana API token
            dry_run: If True, don't make changes
            max_workers: Maximum concurrent threads for parallel ops
            timeout: Request timeout in seconds
        """
        self._session = session
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._dry_run = dry_run
        self.max_workers = min(max_workers, self.MAX_WORKERS)
        self.timeout = timeout
        self.logger = logging.getLogger("AsanaBatchClient")

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a single API request."""
        url = self._build_url(path)
        response = self._session.request(
            method,
            url,
            headers=self._headers,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            try:
                payload = response.json()
                errors = payload.get("errors", [])
                if errors:
                    raise TrackerError(errors[0].get("message", "API error"))
            except ValueError:
                raise TrackerError(f"API error: {response.status_code}")

        result: dict[str, Any] = response.json().get("data", {})
        return result

    # -------------------------------------------------------------------------
    # Bulk Create Subtasks
    # -------------------------------------------------------------------------

    def bulk_create_subtasks(
        self,
        project_gid: str,
        subtasks: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Create multiple subtasks in parallel.

        Args:
            project_gid: Project GID to add tasks to
            subtasks: List of subtask data dicts with parent_gid, name, notes, etc.

        Returns:
            BatchResult with created task GIDs
        """
        result = BatchResult()

        if not subtasks:
            return result

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk create {len(subtasks)} subtasks")
            for i, st in enumerate(subtasks):
                result.add_success(i, f"DRY-RUN-{i}", {"name": st.get("name", "")[:30]})
            return result

        def create_single(idx: int, subtask: dict[str, Any]) -> tuple[int, str, str | None]:
            """Create a single subtask."""
            parent_gid = subtask.get("parent_gid")
            if not parent_gid:
                return (idx, "", "Missing parent_gid")

            payload: dict[str, Any] = {
                "name": subtask.get("name", "")[:255],
                "notes": subtask.get("notes", ""),
                "projects": [project_gid],
            }

            if subtask.get("assignee"):
                payload["assignee"] = subtask["assignee"]

            if subtask.get("custom_fields"):
                payload["custom_fields"] = subtask["custom_fields"]

            try:
                data = self._request(
                    "POST",
                    f"/tasks/{parent_gid}/subtasks",
                    json={"data": payload},
                )
                gid = data.get("gid", "")
                return (idx, gid, None)
            except TrackerError as e:
                return (idx, "", str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(create_single, i, st): i for i, st in enumerate(subtasks)}

            for future in as_completed(futures):
                try:
                    idx, gid, error = future.result()
                    if error is None and gid:
                        result.add_success(idx, gid)
                    else:
                        result.add_failure(idx, error or "No GID returned")
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk create subtasks: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Update Tasks
    # -------------------------------------------------------------------------

    def bulk_update_tasks(
        self,
        updates: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Update multiple tasks in parallel.

        Args:
            updates: List of update dicts with "gid" and fields to update

        Returns:
            BatchResult with update status for each task
        """
        result = BatchResult()

        if not updates:
            return result

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk update {len(updates)} tasks")
            for i, update in enumerate(updates):
                result.add_success(i, update.get("gid", f"DRY-RUN-{i}"))
            return result

        def update_single(idx: int, update: dict[str, Any]) -> tuple[int, str, str | None]:
            """Update a single task."""
            gid = update.get("gid", "")
            if not gid:
                return (idx, "", "Missing gid")

            # Build update payload (exclude gid)
            payload = {k: v for k, v in update.items() if k != "gid"}

            try:
                self._request("PUT", f"/tasks/{gid}", json={"data": payload})
                return (idx, gid, None)
            except TrackerError as e:
                return (idx, gid, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(update_single, i, update): i for i, update in enumerate(updates)
            }

            for future in as_completed(futures):
                try:
                    idx, gid, error = future.result()
                    if error is None:
                        result.add_success(idx, gid)
                    else:
                        result.add_failure(idx, error, gid)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk update tasks: {result.summary()}")
        return result

    def bulk_update_descriptions(
        self,
        updates: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Update notes (descriptions) for multiple tasks.

        Args:
            updates: List of (task_gid, notes) tuples

        Returns:
            BatchResult
        """
        update_dicts = [{"gid": gid, "notes": notes} for gid, notes in updates]
        return self.bulk_update_tasks(update_dicts)

    # -------------------------------------------------------------------------
    # Bulk Status Updates (Complete/Incomplete)
    # -------------------------------------------------------------------------

    def bulk_complete_tasks(
        self,
        task_gids: list[str],
        completed: bool = True,
    ) -> BatchResult:
        """
        Mark multiple tasks as complete or incomplete.

        Args:
            task_gids: List of task GIDs to update
            completed: True to mark complete, False to mark incomplete

        Returns:
            BatchResult
        """
        updates = [{"gid": gid, "completed": completed} for gid in task_gids]
        return self.bulk_update_tasks(updates)

    # -------------------------------------------------------------------------
    # Bulk Add Comments (Stories)
    # -------------------------------------------------------------------------

    def bulk_add_comments(
        self,
        comments: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Add comments to multiple tasks in parallel.

        Args:
            comments: List of (task_gid, comment_text) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not comments:
            return result

        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            for i, (gid, _) in enumerate(comments):
                result.add_success(i, gid)
            return result

        def add_comment_single(idx: int, gid: str, text: str) -> tuple[int, str, str | None]:
            """Add comment to a single task."""
            try:
                self._request(
                    "POST",
                    f"/tasks/{gid}/stories",
                    json={"data": {"text": text}},
                )
                return (idx, gid, None)
            except TrackerError as e:
                return (idx, gid, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(add_comment_single, i, gid, text): i
                for i, (gid, text) in enumerate(comments)
            }

            for future in as_completed(futures):
                try:
                    idx, gid, error = future.result()
                    if error is None:
                        result.add_success(idx, gid)
                    else:
                        result.add_failure(idx, error, gid)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk add comments: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Fetch Tasks
    # -------------------------------------------------------------------------

    def bulk_get_tasks(
        self,
        task_gids: list[str],
        opt_fields: list[str] | None = None,
    ) -> BatchResult:
        """
        Fetch multiple tasks in parallel.

        Args:
            task_gids: List of task GIDs to fetch
            opt_fields: Optional fields to include in response

        Returns:
            BatchResult with task data in each operation's data field
        """
        result = BatchResult()

        if not task_gids:
            return result

        if opt_fields is None:
            opt_fields = ["name", "notes", "completed", "assignee", "custom_fields"]

        def fetch_single(
            idx: int,
            gid: str,
        ) -> tuple[int, str, dict[str, Any] | None, str | None]:
            """Fetch a single task."""
            try:
                data = self._request(
                    "GET",
                    f"/tasks/{gid}",
                    params={"opt_fields": ",".join(opt_fields)},
                )
                return (idx, gid, data, None)
            except TrackerError as e:
                return (idx, gid, None, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_single, i, gid): i for i, gid in enumerate(task_gids)}

            for future in as_completed(futures):
                try:
                    idx, gid, data, error = future.result()
                    if error is None and data:
                        result.add_success(idx, gid, data)
                    else:
                        result.add_failure(idx, error or "No data returned", gid)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk fetch tasks: {result.summary()}")
        return result
