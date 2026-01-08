"""
Azure DevOps Batch Operations - Bulk operations for improved performance.

Provides batch operations for Azure DevOps, using parallel execution
since Azure DevOps doesn't have native bulk APIs for all operations.

Components:
- BatchOperation: Result of a single operation within a batch
- BatchResult: Aggregated results from a batch operation
- AzureDevOpsBatchClient: Client for batch operations
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerError

from .client import AzureDevOpsApiClient


@dataclass
class BatchOperation:
    """
    Result of a single operation within a batch.

    Attributes:
        index: Position in the batch (0-indexed)
        success: Whether the operation succeeded
        key: Work item ID (for created/updated items)
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
        """Get keys of successfully created/processed work items."""
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


class AzureDevOpsBatchClient:
    """
    Client for Azure DevOps batch operations.

    Uses parallel execution for all batch operations since
    Azure DevOps doesn't have native bulk APIs for all operations.

    Example:
        >>> from spectryn.adapters.azure_devops import AzureDevOpsAdapter
        >>> adapter = AzureDevOpsAdapter(org, project, pat, dry_run=False)
        >>> batch_client = AzureDevOpsBatchClient(adapter._client)
        >>>
        >>> # Bulk create subtasks
        >>> subtasks = [
        ...     {"parent_key": "123", "summary": "Task 1", "description": "..."},
        ...     {"parent_key": "123", "summary": "Task 2", "description": "..."},
        ... ]
        >>> result = batch_client.bulk_create_subtasks(subtasks)
        >>> print(f"Created: {result.created_keys}")
    """

    # Maximum concurrent threads for parallel operations
    MAX_WORKERS = 10

    def __init__(
        self,
        client: AzureDevOpsApiClient,
        max_workers: int = 10,
    ):
        """
        Initialize the batch client.

        Args:
            client: AzureDevOpsApiClient instance
            max_workers: Maximum concurrent threads for parallel ops
        """
        self.client = client
        self.max_workers = min(max_workers, self.MAX_WORKERS)
        self.logger = logging.getLogger("AzureDevOpsBatchClient")

    def _parse_work_item_id(self, key: str) -> int:
        """Parse a work item key into an ID."""
        match = re.search(r"(\d+)", str(key))
        if match:
            return int(match.group(1))
        raise ValueError(f"Invalid work item key: {key}")

    def _markdown_to_html(self, markdown: str) -> str:
        """Convert markdown to HTML for Azure DevOps."""
        html = markdown
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", html, flags=re.DOTALL)
        html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

    # -------------------------------------------------------------------------
    # Bulk Create Subtasks
    # -------------------------------------------------------------------------

    def bulk_create_subtasks(
        self,
        subtasks: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Create multiple subtasks in parallel.

        Args:
            subtasks: List of subtask data dicts with parent_key, summary, description, etc.

        Returns:
            BatchResult with created work item IDs
        """
        result = BatchResult()

        if not subtasks:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk create {len(subtasks)} subtasks")
            for i, st in enumerate(subtasks):
                result.add_success(i, f"DRY-RUN-{i}", {"summary": st.get("summary", "")[:30]})
            return result

        def create_single(idx: int, subtask: dict[str, Any]) -> tuple[int, str, str | None]:
            """Create a single subtask."""
            try:
                parent_key = subtask.get("parent_key")
                if not parent_key:
                    return (idx, "", "Missing parent_key")

                parent_id = self._parse_work_item_id(parent_key)
                html_desc = self._markdown_to_html(str(subtask.get("description", "")))

                created = self.client.create_work_item(
                    work_item_type="Task",
                    title=subtask.get("summary", "")[:255],
                    description=html_desc,
                    parent_id=parent_id,
                    story_points=float(subtask["story_points"])
                    if subtask.get("story_points")
                    else None,
                    assigned_to=subtask.get("assignee"),
                )

                work_item_id = created.get("id")
                return (idx, str(work_item_id) if work_item_id else "", None)
            except (IssueTrackerError, ValueError) as e:
                return (idx, "", str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(create_single, i, st): i for i, st in enumerate(subtasks)}

            for future in as_completed(futures):
                try:
                    idx, work_item_id, error = future.result()
                    if error is None and work_item_id:
                        result.add_success(idx, work_item_id)
                    else:
                        result.add_failure(idx, error or "No work item ID returned")
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk create subtasks: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Update Work Items
    # -------------------------------------------------------------------------

    def bulk_update_work_items(
        self,
        updates: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Update multiple work items in parallel.

        Args:
            updates: List of update dicts with "work_item_id" and fields to update

        Returns:
            BatchResult with update status for each work item
        """
        result = BatchResult()

        if not updates:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk update {len(updates)} work items")
            for i, update in enumerate(updates):
                result.add_success(i, str(update.get("work_item_id", f"DRY-RUN-{i}")))
            return result

        def update_single(idx: int, update: dict[str, Any]) -> tuple[int, str, str | None]:
            """Update a single work item."""
            work_item_id = update.get("work_item_id")
            if not work_item_id:
                return (idx, "", "Missing work_item_id")

            try:
                # Build update dict (exclude work_item_id)
                update_data = {k: v for k, v in update.items() if k != "work_item_id"}
                self.client.update_work_item(work_item_id, **update_data)
                return (idx, str(work_item_id), None)
            except (IssueTrackerError, ValueError) as e:
                return (idx, str(work_item_id), str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(update_single, i, update): i for i, update in enumerate(updates)
            }

            for future in as_completed(futures):
                try:
                    idx, work_item_id, error = future.result()
                    if error is None:
                        result.add_success(idx, work_item_id)
                    else:
                        result.add_failure(idx, error, work_item_id)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk update work items: {result.summary()}")
        return result

    def bulk_update_descriptions(
        self,
        updates: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Update descriptions for multiple work items.

        Args:
            updates: List of (work_item_id, description) tuples

        Returns:
            BatchResult
        """
        update_dicts = [
            {
                "work_item_id": int(self._parse_work_item_id(work_item_id)),
                "description": self._markdown_to_html(desc),
            }
            for work_item_id, desc in updates
        ]
        return self.bulk_update_work_items(update_dicts)

    # -------------------------------------------------------------------------
    # Bulk Status Updates (Transitions)
    # -------------------------------------------------------------------------

    def bulk_transition_work_items(
        self,
        transitions: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Transition multiple work items in parallel.

        Args:
            transitions: List of (work_item_id, target_state) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not transitions:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} work items")
            for i, (work_item_id, _) in enumerate(transitions):
                result.add_success(i, str(work_item_id))
            return result

        def transition_single(
            idx: int, work_item_id: str, state: str
        ) -> tuple[int, str, str | None]:
            """Transition a single work item."""
            try:
                item_id = self._parse_work_item_id(work_item_id)
                self.client.update_work_item(item_id, state=state)
                return (idx, str(item_id), None)
            except (IssueTrackerError, ValueError) as e:
                return (idx, str(work_item_id), str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(transition_single, i, work_item_id, state): i
                for i, (work_item_id, state) in enumerate(transitions)
            }

            for future in as_completed(futures):
                try:
                    idx, work_item_id, error = future.result()
                    if error is None:
                        result.add_success(idx, work_item_id)
                    else:
                        result.add_failure(idx, error, work_item_id)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk transition work items: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Add Comments
    # -------------------------------------------------------------------------

    def bulk_add_comments(
        self,
        comments: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Add comments to multiple work items in parallel.

        Args:
            comments: List of (work_item_id, comment_text) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not comments:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            for i, (work_item_id, _) in enumerate(comments):
                result.add_success(i, str(work_item_id))
            return result

        def add_comment_single(
            idx: int, work_item_id: str, text: str
        ) -> tuple[int, str, str | None]:
            """Add comment to a single work item."""
            try:
                item_id = self._parse_work_item_id(work_item_id)
                self.client.add_comment(item_id, text)
                return (idx, str(item_id), None)
            except (IssueTrackerError, ValueError) as e:
                return (idx, str(work_item_id), str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(add_comment_single, i, work_item_id, text): i
                for i, (work_item_id, text) in enumerate(comments)
            }

            for future in as_completed(futures):
                try:
                    idx, work_item_id, error = future.result()
                    if error is None:
                        result.add_success(idx, work_item_id)
                    else:
                        result.add_failure(idx, error, work_item_id)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk add comments: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Fetch Work Items
    # -------------------------------------------------------------------------

    def bulk_get_work_items(
        self,
        work_item_ids: list[int],
    ) -> BatchResult:
        """
        Fetch multiple work items in parallel.

        Azure DevOps has a bulk GET endpoint, but we use parallel execution
        for consistency with other batch operations.

        Args:
            work_item_ids: List of work item IDs to fetch

        Returns:
            BatchResult with work item data in each operation's data field
        """
        result = BatchResult()

        if not work_item_ids:
            return result

        def fetch_single(
            idx: int,
            work_item_id: int,
        ) -> tuple[int, str, dict[str, Any] | None, str | None]:
            """Fetch a single work item."""
            try:
                data = self.client.get_work_item(work_item_id, expand="All")
                return (idx, str(work_item_id), data, None)
            except IssueTrackerError as e:
                return (idx, str(work_item_id), None, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(fetch_single, i, work_item_id): i
                for i, work_item_id in enumerate(work_item_ids)
            }

            for future in as_completed(futures):
                try:
                    idx, work_item_id, data, error = future.result()
                    if error is None and data:
                        result.add_success(idx, work_item_id, data)
                    else:
                        result.add_failure(idx, error or "No data returned", work_item_id)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk fetch work items: {result.summary()}")
        return result
