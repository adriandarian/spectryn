"""
Transactional Sync - All-or-nothing mode with rollback.

Provides transactional semantics for sync operations:
- Pre-sync state capture
- Operation logging with undo capability
- Automatic rollback on failure
- Commit/rollback API

This ensures that sync operations either complete fully or
leave the tracker in its original state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import TracebackType
from typing import TYPE_CHECKING, Any

from spectryn.application.sync.backup import BackupManager, IssueSnapshot


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort


logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """State of a transaction."""

    PENDING = "pending"  # Transaction created but not started
    ACTIVE = "active"  # Transaction in progress
    COMMITTED = "committed"  # Transaction completed successfully
    ROLLED_BACK = "rolled_back"  # Transaction rolled back
    FAILED = "failed"  # Transaction failed (partial completion)


class OperationType(Enum):
    """Types of operations that can be undone."""

    UPDATE_DESCRIPTION = "update_description"
    UPDATE_STORY_POINTS = "update_story_points"
    UPDATE_STATUS = "update_status"
    UPDATE_TITLE = "update_title"
    CREATE_ISSUE = "create_issue"
    CREATE_SUBTASK = "create_subtask"
    ADD_COMMENT = "add_comment"
    UPDATE_SUBTASK = "update_subtask"
    DELETE_SUBTASK = "delete_subtask"


@dataclass
class OperationRecord:
    """
    Record of a single operation for potential rollback.

    Stores both the operation performed and the original state
    needed to undo it.
    """

    operation_type: OperationType
    issue_key: str
    field_name: str | None = None
    original_value: Any = None
    new_value: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: str | None = None
    can_rollback: bool = True  # Some operations can't be rolled back

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "operation_type": self.operation_type.value,
            "issue_key": self.issue_key,
            "field_name": self.field_name,
            "original_value": str(self.original_value)[:100] if self.original_value else None,
            "new_value": str(self.new_value)[:100] if self.new_value else None,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
            "can_rollback": self.can_rollback,
        }


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    success: bool = True
    operations_rolled_back: int = 0
    operations_failed: int = 0
    operations_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error."""
        self.errors.append(error)
        if self.operations_failed > 0:
            self.success = False

    @property
    def summary(self) -> str:
        """Get summary message."""
        if self.success:
            return f"Rollback complete: {self.operations_rolled_back} operations rolled back"
        return (
            f"Rollback partial: {self.operations_rolled_back} rolled back, "
            f"{self.operations_failed} failed, {self.operations_skipped} skipped"
        )


@dataclass
class TransactionResult:
    """Result of a transactional sync operation."""

    transaction_id: str
    state: TransactionState
    started_at: str = ""
    completed_at: str = ""

    # Operation counts
    operations_executed: int = 0
    operations_succeeded: int = 0
    operations_failed: int = 0

    # Rollback info
    rollback_performed: bool = False
    rollback_result: RollbackResult | None = None

    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if transaction completed successfully."""
        return self.state == TransactionState.COMMITTED

    @property
    def summary(self) -> str:
        """Get summary message."""
        lines = [
            f"Transaction: {self.transaction_id}",
            f"State: {self.state.value}",
            f"Operations: {self.operations_succeeded}/{self.operations_executed} succeeded",
        ]
        if self.rollback_performed and self.rollback_result:
            lines.append(f"Rollback: {self.rollback_result.summary}")
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
        return "\n".join(lines)


class TransactionManager:
    """
    Manages transactional sync operations with rollback capability.

    Provides all-or-nothing semantics for sync operations:
    - Captures pre-operation state
    - Logs all operations with undo information
    - Rolls back on failure

    Example:
        >>> tm = TransactionManager(tracker)
        >>> tm.begin()
        >>> try:
        ...     tm.record_update("PROJ-123", "description", old_desc, new_desc)
        ...     tracker.update_description("PROJ-123", new_desc)
        ...     tm.record_update("PROJ-124", "story_points", 3, 5)
        ...     tracker.update_story_points("PROJ-124", 5)
        ...     tm.commit()
        ... except Exception as e:
        ...     tm.rollback()
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        backup_manager: BackupManager | None = None,
        fail_fast: bool = True,
    ):
        """
        Initialize the transaction manager.

        Args:
            tracker: Issue tracker for operations.
            backup_manager: Optional backup manager for state capture.
            fail_fast: If True, stop on first error and rollback.
        """
        self.tracker = tracker
        self.backup_manager = backup_manager or BackupManager()
        self.fail_fast = fail_fast
        self.logger = logging.getLogger("TransactionManager")

        self._transaction_id: str = ""
        self._state: TransactionState = TransactionState.PENDING
        self._operations: list[OperationRecord] = []
        self._snapshots: dict[str, IssueSnapshot] = {}
        self._started_at: str = ""

    @property
    def transaction_id(self) -> str:
        """Get current transaction ID."""
        return self._transaction_id

    @property
    def state(self) -> TransactionState:
        """Get current transaction state."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Check if a transaction is active."""
        return self._state == TransactionState.ACTIVE

    def begin(self, epic_key: str = "", markdown_path: str = "") -> str:
        """
        Begin a new transaction.

        Args:
            epic_key: Optional epic key for context.
            markdown_path: Optional markdown path for context.

        Returns:
            Transaction ID.

        Raises:
            RuntimeError: If a transaction is already active.
        """
        if self._state == TransactionState.ACTIVE:
            raise RuntimeError("Transaction already active. Commit or rollback first.")

        self._transaction_id = self._generate_transaction_id(epic_key)
        self._state = TransactionState.ACTIVE
        self._operations = []
        self._snapshots = {}
        self._started_at = datetime.now().isoformat()

        self.logger.info(f"Transaction started: {self._transaction_id}")
        return self._transaction_id

    def _generate_transaction_id(self, epic_key: str) -> str:
        """Generate a unique transaction ID."""
        import hashlib

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        content = f"{epic_key}:{timestamp}"
        short_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"txn_{timestamp[:15]}_{short_hash}"

    def capture_state(self, issue_key: str) -> IssueSnapshot | None:
        """
        Capture the current state of an issue before modification.

        Args:
            issue_key: Issue key to capture.

        Returns:
            IssueSnapshot of current state.
        """
        if issue_key in self._snapshots:
            return self._snapshots[issue_key]

        try:
            issue_data = self.tracker.get_issue(issue_key)
            snapshot = IssueSnapshot.from_issue_data(issue_data)
            self._snapshots[issue_key] = snapshot
            self.logger.debug(f"Captured state for {issue_key}")
            return snapshot
        except Exception as e:
            self.logger.warning(f"Failed to capture state for {issue_key}: {e}")
            return None

    def record_operation(
        self,
        operation_type: OperationType,
        issue_key: str,
        field_name: str | None = None,
        original_value: Any = None,
        new_value: Any = None,
        can_rollback: bool = True,
    ) -> OperationRecord:
        """
        Record an operation for potential rollback.

        Args:
            operation_type: Type of operation.
            issue_key: Issue key being modified.
            field_name: Field being modified.
            original_value: Value before modification.
            new_value: Value after modification.
            can_rollback: Whether this operation can be rolled back.

        Returns:
            The recorded operation.
        """
        if not self.is_active:
            raise RuntimeError("No active transaction. Call begin() first.")

        # Auto-capture state if not already captured
        if issue_key not in self._snapshots:
            self.capture_state(issue_key)

        record = OperationRecord(
            operation_type=operation_type,
            issue_key=issue_key,
            field_name=field_name,
            original_value=original_value,
            new_value=new_value,
            can_rollback=can_rollback,
        )
        self._operations.append(record)
        self.logger.debug(f"Recorded: {operation_type.value} on {issue_key}")
        return record

    def mark_operation_failed(self, record: OperationRecord, error: str) -> None:
        """
        Mark an operation as failed.

        Args:
            record: The operation record.
            error: Error message.
        """
        record.success = False
        record.error = error

        if self.fail_fast:
            self.logger.error(f"Operation failed (fail-fast enabled): {error}")

    def commit(self) -> TransactionResult:
        """
        Commit the transaction.

        Marks the transaction as committed if all operations succeeded.
        If any operation failed and fail_fast is True, rolls back instead.

        Returns:
            TransactionResult with outcome.
        """
        if not self.is_active:
            raise RuntimeError("No active transaction to commit.")

        result = TransactionResult(
            transaction_id=self._transaction_id,
            state=TransactionState.PENDING,
            started_at=self._started_at,
        )

        # Count operations
        result.operations_executed = len(self._operations)
        result.operations_succeeded = sum(1 for op in self._operations if op.success)
        result.operations_failed = result.operations_executed - result.operations_succeeded

        # Check if we need to rollback
        if result.operations_failed > 0 and self.fail_fast:
            self.logger.warning(
                f"Transaction has {result.operations_failed} failed operations, rolling back"
            )
            rollback_result = self.rollback()
            result.rollback_performed = True
            result.rollback_result = rollback_result
            result.state = TransactionState.ROLLED_BACK
        else:
            result.state = TransactionState.COMMITTED
            self._state = TransactionState.COMMITTED
            self.logger.info(f"Transaction committed: {self._transaction_id}")

        result.completed_at = datetime.now().isoformat()
        return result

    def rollback(self) -> RollbackResult:
        """
        Rollback all operations in reverse order.

        Returns:
            RollbackResult with outcome.
        """
        if self._state not in (TransactionState.ACTIVE, TransactionState.FAILED):
            self.logger.warning(f"Cannot rollback transaction in state: {self._state}")
            return RollbackResult(success=False, errors=["Invalid transaction state"])

        result = RollbackResult()

        self.logger.info(f"Rolling back transaction: {self._transaction_id}")

        # Rollback in reverse order
        for op in reversed(self._operations):
            if not op.success:
                # Operation failed, nothing to rollback
                result.operations_skipped += 1
                continue

            if not op.can_rollback:
                result.operations_skipped += 1
                result.details.append(
                    {
                        "issue_key": op.issue_key,
                        "operation": op.operation_type.value,
                        "status": "skipped",
                        "reason": "Cannot rollback this operation type",
                    }
                )
                continue

            try:
                self._rollback_operation(op)
                result.operations_rolled_back += 1
                result.details.append(
                    {
                        "issue_key": op.issue_key,
                        "operation": op.operation_type.value,
                        "status": "rolled_back",
                    }
                )
            except Exception as e:
                result.operations_failed += 1
                result.add_error(
                    f"Failed to rollback {op.operation_type.value} on {op.issue_key}: {e}"
                )
                result.details.append(
                    {
                        "issue_key": op.issue_key,
                        "operation": op.operation_type.value,
                        "status": "failed",
                        "error": str(e),
                    }
                )

        self._state = TransactionState.ROLLED_BACK
        result.success = result.operations_failed == 0

        self.logger.info(
            f"Rollback complete: {result.operations_rolled_back} rolled back, "
            f"{result.operations_failed} failed, {result.operations_skipped} skipped"
        )

        return result

    def _rollback_operation(self, op: OperationRecord) -> None:
        """
        Rollback a single operation.

        Args:
            op: Operation to rollback.
        """
        if op.operation_type == OperationType.UPDATE_DESCRIPTION:
            self.tracker.update_description(op.issue_key, op.original_value)

        elif op.operation_type == OperationType.UPDATE_STORY_POINTS:
            self.tracker.update_story_points(op.issue_key, op.original_value or 0)

        elif op.operation_type == OperationType.UPDATE_STATUS:
            # Status transitions might not be reversible
            # Try to transition back, but this may fail
            try:
                self.tracker.transition_issue(op.issue_key, str(op.original_value))
            except Exception as e:
                self.logger.warning(f"Could not rollback status for {op.issue_key}: {e}")
                raise

        elif op.operation_type == OperationType.UPDATE_TITLE:
            self.tracker.update_summary(op.issue_key, op.original_value)

        elif op.operation_type == OperationType.CREATE_ISSUE:
            # Cannot delete created issues, just log
            self.logger.warning(f"Cannot rollback issue creation: {op.issue_key}")
            raise NotImplementedError("Issue deletion not supported")

        elif op.operation_type == OperationType.CREATE_SUBTASK:
            # Cannot delete subtasks easily
            self.logger.warning(f"Cannot rollback subtask creation: {op.issue_key}")
            raise NotImplementedError("Subtask deletion not supported")

        elif op.operation_type == OperationType.ADD_COMMENT:
            # Cannot delete comments
            self.logger.warning(f"Cannot rollback comment addition: {op.issue_key}")
            raise NotImplementedError("Comment deletion not supported")

        elif op.operation_type == OperationType.UPDATE_SUBTASK:
            # Rollback subtask update
            snapshot = self._snapshots.get(op.issue_key)
            if snapshot:
                # Find the original subtask
                for st in snapshot.subtasks:
                    if st.get("summary") == op.field_name:
                        self.tracker.update_subtask(
                            op.issue_key,
                            op.new_value,  # subtask key
                            st.get("description"),
                            st.get("story_points"),
                        )
                        break

        else:
            self.logger.warning(f"Unknown operation type for rollback: {op.operation_type}")

    def get_operations(self) -> list[OperationRecord]:
        """Get all recorded operations."""
        return list(self._operations)

    def get_result(self) -> TransactionResult:
        """Get the transaction result."""
        return TransactionResult(
            transaction_id=self._transaction_id,
            state=self._state,
            started_at=self._started_at,
            completed_at=datetime.now().isoformat()
            if self._state != TransactionState.ACTIVE
            else "",
            operations_executed=len(self._operations),
            operations_succeeded=sum(1 for op in self._operations if op.success),
            operations_failed=sum(1 for op in self._operations if not op.success),
        )


class TransactionalSync:
    """
    Context manager for transactional sync operations.

    Example:
        >>> with TransactionalSync(tracker) as txn:
        ...     txn.execute_update("PROJ-123", "description", new_desc)
        ...     txn.execute_update("PROJ-124", "story_points", 5)
        ...     # Commits automatically on success, rolls back on exception
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        epic_key: str = "",
        fail_fast: bool = True,
        dry_run: bool = False,
    ):
        """
        Initialize transactional sync.

        Args:
            tracker: Issue tracker.
            epic_key: Epic key for context.
            fail_fast: If True, rollback on first error.
            dry_run: If True, don't execute operations.
        """
        self.tracker = tracker
        self.epic_key = epic_key
        self.fail_fast = fail_fast
        self.dry_run = dry_run
        self.manager = TransactionManager(tracker, fail_fast=fail_fast)
        self.result: TransactionResult | None = None
        self.logger = logging.getLogger("TransactionalSync")

    def __enter__(self) -> TransactionalSync:
        """Start the transaction."""
        self.manager.begin(self.epic_key)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """End the transaction (commit or rollback)."""
        if exc_type is not None:
            # Exception occurred, rollback
            self.logger.error(f"Exception during transaction: {exc_val}")
            rollback_result = self.manager.rollback()
            self.result = self.manager.get_result()
            self.result.rollback_performed = True
            self.result.rollback_result = rollback_result
            self.result.errors.append(str(exc_val))
            return  # Re-raise the exception

        # No exception, commit
        self.result = self.manager.commit()
        return

    def execute_update(
        self,
        issue_key: str,
        field: str,
        value: Any,
        operation_type: OperationType | None = None,
    ) -> bool:
        """
        Execute an update within the transaction.

        Args:
            issue_key: Issue to update.
            field: Field to update.
            value: New value.
            operation_type: Operation type (auto-detected if not provided).

        Returns:
            True if successful.
        """
        # Auto-detect operation type
        if operation_type is None:
            operation_type = self._detect_operation_type(field)

        # Capture original state
        snapshot = self.manager.capture_state(issue_key)
        original_value = self._get_original_value(snapshot, field)

        # Record the operation
        record = self.manager.record_operation(
            operation_type=operation_type,
            issue_key=issue_key,
            field_name=field,
            original_value=original_value,
            new_value=value,
        )

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would update {issue_key}.{field} to {value}")
            return True

        # Execute the operation
        try:
            self._execute_field_update(issue_key, field, value)
            return True
        except Exception as e:
            self.manager.mark_operation_failed(record, str(e))
            if self.fail_fast:
                raise
            return False

    def _detect_operation_type(self, field: str) -> OperationType:
        """Detect operation type from field name."""
        if field in ("description", "desc"):
            return OperationType.UPDATE_DESCRIPTION
        if field in ("story_points", "points", "estimate"):
            return OperationType.UPDATE_STORY_POINTS
        if field in ("status", "state"):
            return OperationType.UPDATE_STATUS
        if field in ("title", "summary"):
            return OperationType.UPDATE_TITLE
        return OperationType.UPDATE_DESCRIPTION  # Default

    def _get_original_value(self, snapshot: IssueSnapshot | None, field: str) -> Any:
        """Get original value from snapshot."""
        if not snapshot:
            return None
        if field in ("description", "desc"):
            return snapshot.description
        if field in ("story_points", "points", "estimate"):
            return snapshot.story_points
        if field in ("status", "state"):
            return snapshot.status
        if field in ("title", "summary"):
            return snapshot.summary
        return None

    def _execute_field_update(self, issue_key: str, field: str, value: Any) -> None:
        """Execute the actual field update."""
        if field in ("description", "desc"):
            self.tracker.update_description(issue_key, value)
        elif field in ("story_points", "points", "estimate"):
            self.tracker.update_story_points(issue_key, int(value) if value else 0)
        elif field in ("status", "state"):
            self.tracker.transition_issue(issue_key, str(value))
        elif field in ("title", "summary"):
            self.tracker.update_summary(issue_key, value)
        else:
            raise ValueError(f"Unknown field: {field}")


def create_transactional_sync(
    tracker: IssueTrackerPort,
    epic_key: str = "",
    fail_fast: bool = True,
    dry_run: bool = False,
) -> TransactionalSync:
    """
    Factory function to create a transactional sync context.

    Args:
        tracker: Issue tracker.
        epic_key: Epic key for context.
        fail_fast: If True, rollback on first error.
        dry_run: If True, don't execute operations.

    Returns:
        TransactionalSync context manager.
    """
    return TransactionalSync(
        tracker=tracker,
        epic_key=epic_key,
        fail_fast=fail_fast,
        dry_run=dry_run,
    )
