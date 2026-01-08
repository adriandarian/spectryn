"""
Linear Batch Operations - Bulk operations for improved performance.

Provides batch operations for Linear, using parallel execution
since Linear's GraphQL API doesn't have native bulk mutations.

Components:
- BatchOperation: Result of a single operation within a batch
- BatchResult: Aggregated results from a batch operation
- LinearBatchClient: Client for batch operations
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerError

from .client import LinearApiClient


@dataclass
class BatchOperation:
    """
    Result of a single operation within a batch.

    Attributes:
        index: Position in the batch (0-indexed)
        success: Whether the operation succeeded
        key: Issue identifier (for created/updated issues)
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
        """Get keys of successfully created/processed issues."""
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


class LinearBatchClient:
    """
    Client for Linear batch operations.

    Uses parallel execution for all batch operations since
    Linear's GraphQL API doesn't have native bulk mutations.

    Example:
        >>> from spectryn.adapters.linear import LinearAdapter
        >>> adapter = LinearAdapter(api_key, team_key, dry_run=False)
        >>> batch_client = LinearBatchClient(adapter._client)
        >>>
        >>> # Bulk create subtasks
        >>> subtasks = [
        ...     {"parent_key": "ENG-123", "summary": "Task 1", "description": "..."},
        ...     {"parent_key": "ENG-123", "summary": "Task 2", "description": "..."},
        ... ]
        >>> result = batch_client.bulk_create_subtasks(subtasks)
        >>> print(f"Created: {result.created_keys}")
    """

    # Maximum concurrent threads for parallel operations
    MAX_WORKERS = 10

    def __init__(
        self,
        client: LinearApiClient,
        max_workers: int = 10,
    ):
        """
        Initialize the batch client.

        Args:
            client: LinearApiClient instance
            max_workers: Maximum concurrent threads for parallel ops
        """
        self.client = client
        self.max_workers = min(max_workers, self.MAX_WORKERS)
        self.logger = logging.getLogger("LinearBatchClient")

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
            BatchResult with created issue identifiers
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

                # Get parent issue to extract team_id
                parent_issue = self.client.get_issue(parent_key)
                # Linear API returns team info in the issue
                team_id = parent_issue.get("team", {}).get("id")

                if not team_id:
                    return (idx, "", "Could not determine team_id from parent issue")

                result = self.client.create_issue(
                    team_id=team_id,
                    title=subtask.get("summary", "")[:255],
                    description=str(subtask.get("description", "")),
                    parent_id=parent_issue.get("id"),
                    estimate=subtask.get("story_points"),
                    assignee_id=subtask.get("assignee"),
                )

                identifier = result.get("identifier", "")
                return (idx, identifier, None)
            except IssueTrackerError as e:
                return (idx, "", str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(create_single, i, st): i for i, st in enumerate(subtasks)}

            for future in as_completed(futures):
                try:
                    idx, identifier, error = future.result()
                    if error is None and identifier:
                        result.add_success(idx, identifier)
                    else:
                        result.add_failure(idx, error or "No identifier returned")
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk create subtasks: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Update Issues
    # -------------------------------------------------------------------------

    def bulk_update_issues(
        self,
        updates: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Update multiple issues in parallel.

        Args:
            updates: List of update dicts with "identifier" and fields to update

        Returns:
            BatchResult with update status for each issue
        """
        result = BatchResult()

        if not updates:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk update {len(updates)} issues")
            for i, update in enumerate(updates):
                result.add_success(i, update.get("identifier", f"DRY-RUN-{i}"))
            return result

        def update_single(idx: int, update: dict[str, Any]) -> tuple[int, str, str | None]:
            """Update a single issue."""
            identifier = update.get("identifier", "")
            if not identifier:
                return (idx, "", "Missing identifier")

            try:
                # Build update dict (exclude identifier)
                update_data = {k: v for k, v in update.items() if k != "identifier"}
                self.client.update_issue(identifier, **update_data)
                return (idx, identifier, None)
            except IssueTrackerError as e:
                return (idx, identifier, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(update_single, i, update): i for i, update in enumerate(updates)
            }

            for future in as_completed(futures):
                try:
                    idx, identifier, error = future.result()
                    if error is None:
                        result.add_success(idx, identifier)
                    else:
                        result.add_failure(idx, error, identifier)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk update issues: {result.summary()}")
        return result

    def bulk_update_descriptions(
        self,
        updates: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Update descriptions for multiple issues.

        Args:
            updates: List of (issue_identifier, description) tuples

        Returns:
            BatchResult
        """
        update_dicts = [
            {"identifier": identifier, "description": desc} for identifier, desc in updates
        ]
        return self.bulk_update_issues(update_dicts)

    # -------------------------------------------------------------------------
    # Bulk Status Updates (Transitions)
    # -------------------------------------------------------------------------

    def bulk_transition_issues(
        self,
        transitions: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Transition multiple issues in parallel.

        Args:
            transitions: List of (issue_identifier, target_status) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not transitions:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {len(transitions)} issues")
            for i, (identifier, _) in enumerate(transitions):
                result.add_success(i, identifier)
            return result

        def transition_single(
            idx: int, identifier: str, status: str
        ) -> tuple[int, str, str | None]:
            """Transition a single issue."""
            try:
                # Get workflow states for the team
                issue = self.client.get_issue(identifier)
                team_id = issue.get("team", {}).get("id")
                if not team_id:
                    return (idx, identifier, "Could not determine team_id")

                states = self.client.get_workflow_states(team_id)
                state_map = {s["name"].lower(): s["id"] for s in states}

                # Find matching state
                status_lower = status.lower()
                state_id = None
                for name, sid in state_map.items():
                    if status_lower in name or name in status_lower:
                        state_id = sid
                        break

                if not state_id:
                    return (idx, identifier, f"State not found: {status}")

                self.client.update_issue(identifier, state_id=state_id)
                return (idx, identifier, None)
            except IssueTrackerError as e:
                return (idx, identifier, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(transition_single, i, identifier, status): i
                for i, (identifier, status) in enumerate(transitions)
            }

            for future in as_completed(futures):
                try:
                    idx, identifier, error = future.result()
                    if error is None:
                        result.add_success(idx, identifier)
                    else:
                        result.add_failure(idx, error, identifier)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk transition issues: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Add Comments
    # -------------------------------------------------------------------------

    def bulk_add_comments(
        self,
        comments: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Add comments to multiple issues in parallel.

        Args:
            comments: List of (issue_identifier, comment_text) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not comments:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            for i, (identifier, _) in enumerate(comments):
                result.add_success(i, identifier)
            return result

        def add_comment_single(idx: int, identifier: str, text: str) -> tuple[int, str, str | None]:
            """Add comment to a single issue."""
            try:
                self.client.add_comment(identifier, text)
                return (idx, identifier, None)
            except IssueTrackerError as e:
                return (idx, identifier, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(add_comment_single, i, identifier, text): i
                for i, (identifier, text) in enumerate(comments)
            }

            for future in as_completed(futures):
                try:
                    idx, identifier, error = future.result()
                    if error is None:
                        result.add_success(idx, identifier)
                    else:
                        result.add_failure(idx, error, identifier)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk add comments: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Fetch Issues
    # -------------------------------------------------------------------------

    def bulk_get_issues(
        self,
        issue_identifiers: list[str],
    ) -> BatchResult:
        """
        Fetch multiple issues in parallel.

        Args:
            issue_identifiers: List of issue identifiers to fetch

        Returns:
            BatchResult with issue data in each operation's data field
        """
        result = BatchResult()

        if not issue_identifiers:
            return result

        def fetch_single(
            idx: int,
            identifier: str,
        ) -> tuple[int, str, dict[str, Any] | None, str | None]:
            """Fetch a single issue."""
            try:
                data = self.client.get_issue(identifier)
                return (idx, identifier, data, None)
            except IssueTrackerError as e:
                return (idx, identifier, None, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(fetch_single, i, identifier): i
                for i, identifier in enumerate(issue_identifiers)
            }

            for future in as_completed(futures):
                try:
                    idx, identifier, data, error = future.result()
                    if error is None and data:
                        result.add_success(idx, identifier, data)
                    else:
                        result.add_failure(idx, error or "No data returned", identifier)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)
        self.logger.info(f"Bulk fetch issues: {result.summary()}")
        return result
