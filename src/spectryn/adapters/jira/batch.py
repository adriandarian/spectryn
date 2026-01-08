"""
Jira Batch Operations - Bulk API operations for improved performance.

Provides batch operations using Jira's bulk APIs where available,
and parallel execution for operations without native bulk support.

Jira REST API Bulk Endpoints:
- POST /rest/api/3/issue/bulk - Create multiple issues
- Bulk edit/transition - Implemented via parallel execution

Components:
- BatchOperation: Result of a single operation within a batch
- BatchResult: Aggregated results from a batch operation
- JiraBatchClient: Client for batch operations
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerError

from .client import JiraApiClient


@dataclass
class BatchOperation:
    """
    Result of a single operation within a batch.

    Attributes:
        index: Position in the batch (0-indexed)
        success: Whether the operation succeeded
        key: Issue key (for created/updated issues)
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


class JiraBatchClient:
    """
    Client for Jira batch operations.

    Uses Jira's native bulk APIs where available (bulk create),
    and parallel execution for other operations.

    Example:
        >>> batch_client = JiraBatchClient(api_client)
        >>>
        >>> # Bulk create subtasks
        >>> issues = [
        ...     {"parent": "PROJ-100", "summary": "Task 1", ...},
        ...     {"parent": "PROJ-100", "summary": "Task 2", ...},
        ... ]
        >>> result = batch_client.bulk_create_issues(issues)
        >>> print(f"Created: {result.created_keys}")
        >>>
        >>> # Bulk update issues
        >>> updates = [
        ...     {"key": "PROJ-101", "fields": {"description": ...}},
        ...     {"key": "PROJ-102", "fields": {"description": ...}},
        ... ]
        >>> result = batch_client.bulk_update_issues(updates)
    """

    # Maximum issues in a single bulk create request
    BULK_CREATE_LIMIT = 50

    # Maximum concurrent threads for parallel operations
    MAX_WORKERS = 10

    def __init__(
        self,
        client: JiraApiClient,
        max_workers: int = 10,
    ):
        """
        Initialize the batch client.

        Args:
            client: JiraApiClient instance
            max_workers: Maximum concurrent threads for parallel ops
        """
        self.client = client
        self.max_workers = min(max_workers, self.MAX_WORKERS)
        self.logger = logging.getLogger("JiraBatchClient")

    # -------------------------------------------------------------------------
    # Bulk Create - Uses native Jira bulk API
    # -------------------------------------------------------------------------

    def bulk_create_issues(
        self,
        issues: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Create multiple issues using Jira's bulk create API.

        Uses POST /rest/api/3/issue/bulk which can create up to 50 issues
        at once. For larger batches, splits into multiple requests.

        Args:
            issues: List of issue data dicts, each with "fields" key

        Returns:
            BatchResult with created issue keys

        Example issue format:
            {
                "fields": {
                    "project": {"key": "PROJ"},
                    "parent": {"key": "PROJ-100"},
                    "summary": "Task summary",
                    "description": {...},  # ADF format
                    "issuetype": {"name": "Sub-task"},
                }
            }
        """
        result = BatchResult()

        if not issues:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk create {len(issues)} issues")
            for i, issue in enumerate(issues):
                summary = issue.get("fields", {}).get("summary", "Unknown")[:30]
                result.add_success(i, f"DRY-RUN-{i}", {"summary": summary})
            return result

        # Process in chunks of BULK_CREATE_LIMIT
        for chunk_start in range(0, len(issues), self.BULK_CREATE_LIMIT):
            chunk_end = min(chunk_start + self.BULK_CREATE_LIMIT, len(issues))
            chunk = issues[chunk_start:chunk_end]

            try:
                response = self.client.post("issue/bulk", json={"issueUpdates": chunk})

                # Process response
                created_issues = response.get("issues", [])
                errors = response.get("errors", [])

                for i, created in enumerate(created_issues):
                    global_idx = chunk_start + i
                    key = created.get("key", "")
                    if key:
                        result.add_success(global_idx, key, created)
                    else:
                        # Check if there's an error for this index
                        error_msg = "Unknown error"
                        if i < len(errors) and errors[i]:
                            error_msg = str(errors[i])
                        result.add_failure(global_idx, error_msg)

                # Handle any remaining errors
                for i, error in enumerate(errors):
                    if error and i >= len(created_issues):
                        global_idx = chunk_start + i
                        result.add_failure(global_idx, str(error))

            except IssueTrackerError as e:
                # Entire chunk failed
                self.logger.error(f"Bulk create failed for chunk {chunk_start}-{chunk_end}: {e}")
                for i in range(len(chunk)):
                    result.add_failure(chunk_start + i, str(e))

        self.logger.info(f"Bulk create: {result.summary()}")
        return result

    def bulk_create_subtasks(
        self,
        parent_key: str,
        project_key: str,
        subtasks: list[dict[str, Any]],
        assignee: str | None = None,
    ) -> BatchResult:
        """
        Create multiple subtasks under a parent issue.

        Convenience method that formats subtask data and calls bulk_create_issues.

        Args:
            parent_key: Parent issue key (e.g., "PROJ-100")
            project_key: Project key (e.g., "PROJ")
            subtasks: List of subtask data with summary, description, etc.
            assignee: Optional assignee account ID for all subtasks

        Returns:
            BatchResult with created subtask keys

        Example subtask format:
            {
                "summary": "Subtask name",
                "description": {...},  # ADF format
                "story_points": 3,
            }
        """
        if assignee is None:
            assignee = self.client.get_current_user_id()

        # Get story points field from adapter config if available
        story_points_field = "customfield_10014"  # Default

        issues = []
        for subtask in subtasks:
            fields: dict[str, Any] = {
                "project": {"key": project_key},
                "parent": {"key": parent_key},
                "summary": subtask.get("summary", "")[:255],
                "issuetype": {"name": "Sub-task"},
            }

            if subtask.get("description"):
                fields["description"] = subtask["description"]

            if assignee:
                fields["assignee"] = {"accountId": assignee}

            if subtask.get("story_points") is not None:
                fields[story_points_field] = float(subtask["story_points"])

            issues.append({"fields": fields})

        return self.bulk_create_issues(issues)

    # -------------------------------------------------------------------------
    # Bulk Update - Uses parallel execution
    # -------------------------------------------------------------------------

    def bulk_update_issues(
        self,
        updates: list[dict[str, Any]],
    ) -> BatchResult:
        """
        Update multiple issues in parallel.

        Jira doesn't have a native bulk edit endpoint for all fields,
        so this uses parallel PUT requests.

        Args:
            updates: List of update dicts with "key" and "fields"

        Returns:
            BatchResult with update status for each issue

        Example update format:
            {
                "key": "PROJ-101",
                "fields": {
                    "description": {...},  # ADF format
                    "customfield_10014": 5.0,  # story points
                }
            }
        """
        result = BatchResult()

        if not updates:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk update {len(updates)} issues")
            for i, update in enumerate(updates):
                result.add_success(i, update.get("key", f"DRY-RUN-{i}"))
            return result

        def update_single(idx: int, update: dict[str, Any]) -> tuple[int, str, str | None]:
            """Update a single issue, return (index, key, error_or_none)."""
            key = update.get("key", "")
            fields = update.get("fields", {})

            try:
                self.client.put(f"issue/{key}", json={"fields": fields})
                return (idx, key, None)
            except IssueTrackerError as e:
                return (idx, key, str(e))

        # Execute updates in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(update_single, i, update): i for i, update in enumerate(updates)
            }

            for future in as_completed(futures):
                try:
                    idx, key, error = future.result()
                    if error is None:
                        result.add_success(idx, key)
                    else:
                        result.add_failure(idx, error, key)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        # Sort operations by index for consistent ordering
        result.operations.sort(key=lambda op: op.index)

        self.logger.info(f"Bulk update: {result.summary()}")
        return result

    def bulk_update_descriptions(
        self,
        updates: list[tuple[str, Any]],
    ) -> BatchResult:
        """
        Update descriptions for multiple issues.

        Convenience method for bulk description updates.

        Args:
            updates: List of (issue_key, description_adf) tuples

        Returns:
            BatchResult
        """
        update_dicts = [{"key": key, "fields": {"description": desc}} for key, desc in updates]
        return self.bulk_update_issues(update_dicts)

    # -------------------------------------------------------------------------
    # Bulk Transitions - Uses parallel execution
    # -------------------------------------------------------------------------

    def bulk_transition_issues(
        self,
        transitions: list[tuple[str, str]],
    ) -> BatchResult:
        """
        Transition multiple issues in parallel.

        Jira doesn't have a native bulk transition endpoint,
        so this uses parallel requests.

        Args:
            transitions: List of (issue_key, target_status) tuples

        Returns:
            BatchResult with transition status for each issue
        """
        result = BatchResult()

        if not transitions:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would bulk transition {len(transitions)} issues")
            for i, (key, status) in enumerate(transitions):
                result.add_success(i, key, {"target_status": status})
            return result

        def transition_single(
            idx: int, key: str, target_status: str
        ) -> tuple[int, str, str | None]:
            """Transition a single issue, return (index, key, error_or_none)."""
            try:
                # Get available transitions
                trans_data = self.client.get(f"issue/{key}/transitions")
                available = trans_data.get("transitions", [])

                # Find matching transition
                transition_id = None
                for t in available:
                    if t.get("name", "").lower() == target_status.lower():
                        transition_id = t["id"]
                        break
                    # Also check target status name
                    to_status = t.get("to", {}).get("name", "")
                    if to_status.lower() == target_status.lower():
                        transition_id = t["id"]
                        break

                if transition_id is None:
                    available_names = [t.get("name", "") for t in available]
                    return (
                        idx,
                        key,
                        f"No transition to '{target_status}' available. Options: {available_names}",
                    )

                # Execute transition
                self.client.post(
                    f"issue/{key}/transitions", json={"transition": {"id": transition_id}}
                )
                return (idx, key, None)

            except IssueTrackerError as e:
                return (idx, key, str(e))

        # Execute transitions in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(transition_single, i, key, status): i
                for i, (key, status) in enumerate(transitions)
            }

            for future in as_completed(futures):
                try:
                    idx, key, error = future.result()
                    if error is None:
                        result.add_success(idx, key)
                    else:
                        result.add_failure(idx, error, key)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)

        self.logger.info(f"Bulk transition: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Comments - Uses parallel execution
    # -------------------------------------------------------------------------

    def bulk_add_comments(
        self,
        comments: list[tuple[str, Any]],
    ) -> BatchResult:
        """
        Add comments to multiple issues in parallel.

        Args:
            comments: List of (issue_key, comment_body_adf) tuples

        Returns:
            BatchResult
        """
        result = BatchResult()

        if not comments:
            return result

        if self.client.dry_run:
            self.logger.info(f"[DRY-RUN] Would add {len(comments)} comments")
            for i, (key, _) in enumerate(comments):
                result.add_success(i, key)
            return result

        def add_comment_single(idx: int, key: str, body: Any) -> tuple[int, str, str | None]:
            """Add comment to a single issue."""
            try:
                self.client.post(f"issue/{key}/comment", json={"body": body})
                return (idx, key, None)
            except IssueTrackerError as e:
                return (idx, key, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(add_comment_single, i, key, body): i
                for i, (key, body) in enumerate(comments)
            }

            for future in as_completed(futures):
                try:
                    idx, key, error = future.result()
                    if error is None:
                        result.add_success(idx, key)
                    else:
                        result.add_failure(idx, error, key)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)

        self.logger.info(f"Bulk comments: {result.summary()}")
        return result

    # -------------------------------------------------------------------------
    # Bulk Fetch - Uses parallel execution
    # -------------------------------------------------------------------------

    def bulk_get_issues(
        self,
        issue_keys: list[str],
        fields: list[str] | None = None,
    ) -> BatchResult:
        """
        Fetch multiple issues in parallel.

        Args:
            issue_keys: List of issue keys to fetch
            fields: Optional list of fields to include

        Returns:
            BatchResult with issue data in each operation's data field
        """
        result = BatchResult()

        if not issue_keys:
            return result

        if fields is None:
            fields = ["summary", "description", "status", "issuetype", "subtasks"]

        def fetch_single(
            idx: int,
            key: str,
        ) -> tuple[int, str, dict[str, Any] | None, str | None]:
            """Fetch a single issue."""
            try:
                data = self.client.get(f"issue/{key}", params={"fields": ",".join(fields)})
                return (idx, key, data, None)
            except IssueTrackerError as e:
                return (idx, key, None, str(e))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_single, i, key): i for i, key in enumerate(issue_keys)}

            for future in as_completed(futures):
                try:
                    idx, key, data, error = future.result()
                    if error is None and data:
                        result.add_success(idx, key, data)
                    else:
                        result.add_failure(idx, error or "No data returned", key)
                except Exception as e:
                    idx = futures[future]
                    result.add_failure(idx, f"Unexpected error: {e}")

        result.operations.sort(key=lambda op: op.index)

        self.logger.info(f"Bulk fetch: {result.summary()}")
        return result
