"""
Sync History Port - Abstract interface for sync history persistence.

Provides a pluggable backend for storing sync history with:
- Complete audit trail of all sync operations
- Point-in-time rollback capabilities
- Analytics and reporting queries

The sync history differs from the state store in that it maintains
a complete, immutable record of all syncs, while the state store
tracks the current state of in-progress operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass


class SyncHistoryError(Exception):
    """Base exception for sync history errors."""


class RollbackError(SyncHistoryError):
    """Rollback operation failed."""


class SyncOutcome(Enum):
    """Outcome of a sync operation."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some operations failed
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRY_RUN = "dry_run"


@dataclass
class SyncHistoryEntry:
    """
    A record of a completed sync operation.

    Attributes:
        entry_id: Unique identifier for this history entry.
        session_id: The sync session ID that generated this entry.
        markdown_path: Path to the markdown file that was synced.
        epic_key: The tracker epic key.
        tracker_type: Type of tracker (jira, github, linear, etc.).
        outcome: Result of the sync operation.
        started_at: When the sync started.
        completed_at: When the sync completed.
        duration_seconds: Total sync duration.
        operations_total: Total operations attempted.
        operations_succeeded: Operations that succeeded.
        operations_failed: Operations that failed.
        operations_skipped: Operations that were skipped.
        dry_run: Whether this was a dry run.
        user: User who initiated the sync (if available).
        config_snapshot: Snapshot of config at sync time.
        changes_snapshot: Snapshot of changes made (for rollback).
        error_message: Error message if failed.
        metadata: Additional metadata.
    """

    entry_id: str
    session_id: str
    markdown_path: str
    epic_key: str
    tracker_type: str
    outcome: SyncOutcome
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    operations_total: int = 0
    operations_succeeded: int = 0
    operations_failed: int = 0
    operations_skipped: int = 0
    dry_run: bool = False
    user: str | None = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    changes_snapshot: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entry_id": self.entry_id,
            "session_id": self.session_id,
            "markdown_path": self.markdown_path,
            "epic_key": self.epic_key,
            "tracker_type": self.tracker_type,
            "outcome": self.outcome.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "operations_total": self.operations_total,
            "operations_succeeded": self.operations_succeeded,
            "operations_failed": self.operations_failed,
            "operations_skipped": self.operations_skipped,
            "dry_run": self.dry_run,
            "user": self.user,
            "config_snapshot": self.config_snapshot,
            "changes_snapshot": self.changes_snapshot,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncHistoryEntry:
        """Create from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            session_id=data["session_id"],
            markdown_path=data["markdown_path"],
            epic_key=data["epic_key"],
            tracker_type=data["tracker_type"],
            outcome=SyncOutcome(data["outcome"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]),
            duration_seconds=data["duration_seconds"],
            operations_total=data.get("operations_total", 0),
            operations_succeeded=data.get("operations_succeeded", 0),
            operations_failed=data.get("operations_failed", 0),
            operations_skipped=data.get("operations_skipped", 0),
            dry_run=data.get("dry_run", False),
            user=data.get("user"),
            config_snapshot=data.get("config_snapshot", {}),
            changes_snapshot=data.get("changes_snapshot", []),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ChangeRecord:
    """
    Record of a single change made during sync.

    Used for tracking individual operations and enabling rollback.

    Attributes:
        change_id: Unique identifier for this change.
        entry_id: The history entry this belongs to.
        operation_type: Type of operation (create, update, delete).
        entity_type: Type of entity (epic, story, subtask, comment).
        entity_id: ID of the entity in the tracker.
        story_id: ID from the markdown file.
        field_name: Field that was changed (for updates).
        old_value: Previous value (for rollback).
        new_value: New value that was set.
        timestamp: When the change was made.
        rolled_back: Whether this change has been rolled back.
        rollback_entry_id: Entry ID of the rollback operation.
    """

    change_id: str
    entry_id: str
    operation_type: str  # create, update, delete
    entity_type: str  # epic, story, subtask, comment
    entity_id: str
    story_id: str
    field_name: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    rolled_back: bool = False
    rollback_entry_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "change_id": self.change_id,
            "entry_id": self.entry_id,
            "operation_type": self.operation_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "story_id": self.story_id,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "timestamp": self.timestamp.isoformat(),
            "rolled_back": self.rolled_back,
            "rollback_entry_id": self.rollback_entry_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeRecord:
        """Create from dictionary."""
        return cls(
            change_id=data["change_id"],
            entry_id=data["entry_id"],
            operation_type=data["operation_type"],
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            story_id=data["story_id"],
            field_name=data.get("field_name"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            rolled_back=data.get("rolled_back", False),
            rollback_entry_id=data.get("rollback_entry_id"),
        )


@dataclass
class RollbackPlan:
    """
    Plan for rolling back to a specific point in time.

    Contains all the information needed to undo changes made after
    a target timestamp.

    Attributes:
        target_timestamp: The point in time to roll back to.
        created_at: When this plan was created.
        target_entry: The sync entry at the target timestamp (if any).
        changes_to_rollback: Changes that need to be undone, ordered newest first.
        epic_key: Epic key filter used (if any).
        tracker_type: Tracker type filter used (if any).
        total_changes: Total number of changes to roll back.
        affected_entities: Set of entity IDs that will be affected.
        affected_stories: Set of story IDs that will be affected.
        can_rollback: Whether the rollback can be executed.
        warnings: Any warnings about the rollback plan.
    """

    target_timestamp: datetime
    created_at: datetime = field(default_factory=datetime.now)
    target_entry: SyncHistoryEntry | None = None
    changes_to_rollback: list[ChangeRecord] = field(default_factory=list)
    epic_key: str | None = None
    tracker_type: str | None = None
    total_changes: int = 0
    affected_entities: set[str] = field(default_factory=set)
    affected_stories: set[str] = field(default_factory=set)
    can_rollback: bool = True
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Compute derived fields."""
        if self.changes_to_rollback and not self.affected_entities:
            self.affected_entities = {c.entity_id for c in self.changes_to_rollback}
        if self.changes_to_rollback and not self.affected_stories:
            self.affected_stories = {c.story_id for c in self.changes_to_rollback}
        if self.changes_to_rollback and not self.total_changes:
            self.total_changes = len(self.changes_to_rollback)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "target_timestamp": self.target_timestamp.isoformat(),
            "created_at": self.created_at.isoformat(),
            "target_entry": self.target_entry.to_dict() if self.target_entry else None,
            "changes_to_rollback": [c.to_dict() for c in self.changes_to_rollback],
            "epic_key": self.epic_key,
            "tracker_type": self.tracker_type,
            "total_changes": self.total_changes,
            "affected_entities": list(self.affected_entities),
            "affected_stories": list(self.affected_stories),
            "can_rollback": self.can_rollback,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackPlan:
        """Create from dictionary."""
        return cls(
            target_timestamp=datetime.fromisoformat(data["target_timestamp"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            target_entry=(
                SyncHistoryEntry.from_dict(data["target_entry"])
                if data.get("target_entry")
                else None
            ),
            changes_to_rollback=[
                ChangeRecord.from_dict(c) for c in data.get("changes_to_rollback", [])
            ],
            epic_key=data.get("epic_key"),
            tracker_type=data.get("tracker_type"),
            total_changes=data.get("total_changes", 0),
            affected_entities=set(data.get("affected_entities", [])),
            affected_stories=set(data.get("affected_stories", [])),
            can_rollback=data.get("can_rollback", True),
            warnings=data.get("warnings", []),
        )


@dataclass
class HistoryQuery:
    """
    Query parameters for finding sync history entries.

    Attributes:
        entry_id: Filter by exact entry ID.
        session_id: Filter by session ID.
        markdown_path: Filter by markdown file path.
        epic_key: Filter by epic key.
        tracker_type: Filter by tracker type.
        outcomes: Filter by outcomes (e.g., ["success", "failed"]).
        dry_run: Filter by dry_run flag (None = any).
        after: Entries after this timestamp.
        before: Entries before this timestamp.
        user: Filter by user.
        limit: Maximum results to return.
        offset: Skip this many results (for pagination).
        order_desc: Order by completed_at descending (default True).
    """

    entry_id: str | None = None
    session_id: str | None = None
    markdown_path: str | None = None
    epic_key: str | None = None
    tracker_type: str | None = None
    outcomes: list[str] | None = None
    dry_run: bool | None = None
    after: datetime | None = None
    before: datetime | None = None
    user: str | None = None
    limit: int | None = None
    offset: int = 0
    order_desc: bool = True


@dataclass
class SyncStatistics:
    """
    Aggregated statistics for sync operations.

    Attributes:
        total_syncs: Total number of syncs.
        successful_syncs: Number of successful syncs.
        failed_syncs: Number of failed syncs.
        partial_syncs: Number of partial syncs.
        dry_run_syncs: Number of dry run syncs.
        total_operations: Total operations across all syncs.
        successful_operations: Total successful operations.
        failed_operations: Total failed operations.
        average_duration_seconds: Average sync duration.
        total_duration_seconds: Total time spent syncing.
        first_sync_at: Timestamp of first sync.
        last_sync_at: Timestamp of last sync.
        syncs_by_tracker: Breakdown by tracker type.
        syncs_by_epic: Breakdown by epic key.
        syncs_by_outcome: Breakdown by outcome.
    """

    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    partial_syncs: int = 0
    dry_run_syncs: int = 0
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    average_duration_seconds: float = 0.0
    total_duration_seconds: float = 0.0
    first_sync_at: datetime | None = None
    last_sync_at: datetime | None = None
    syncs_by_tracker: dict[str, int] = field(default_factory=dict)
    syncs_by_epic: dict[str, int] = field(default_factory=dict)
    syncs_by_outcome: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_syncs": self.total_syncs,
            "successful_syncs": self.successful_syncs,
            "failed_syncs": self.failed_syncs,
            "partial_syncs": self.partial_syncs,
            "dry_run_syncs": self.dry_run_syncs,
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "average_duration_seconds": self.average_duration_seconds,
            "total_duration_seconds": self.total_duration_seconds,
            "first_sync_at": self.first_sync_at.isoformat() if self.first_sync_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "syncs_by_tracker": self.syncs_by_tracker,
            "syncs_by_epic": self.syncs_by_epic,
            "syncs_by_outcome": self.syncs_by_outcome,
        }


@dataclass
class VelocityMetrics:
    """
    Velocity metrics for a time period.

    Attributes:
        period_start: Start of the period.
        period_end: End of the period.
        total_syncs: Syncs in period.
        successful_syncs: Successful syncs.
        operations_completed: Operations completed.
        stories_synced: Unique stories synced.
        epics_touched: Unique epics touched.
        average_ops_per_sync: Average operations per sync.
    """

    period_start: datetime
    period_end: datetime
    total_syncs: int = 0
    successful_syncs: int = 0
    operations_completed: int = 0
    stories_synced: int = 0
    epics_touched: int = 0
    average_ops_per_sync: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_syncs": self.total_syncs,
            "successful_syncs": self.successful_syncs,
            "operations_completed": self.operations_completed,
            "stories_synced": self.stories_synced,
            "epics_touched": self.epics_touched,
            "average_ops_per_sync": self.average_ops_per_sync,
        }


@dataclass
class HistoryStoreInfo:
    """
    Information about the history store.

    Attributes:
        backend: Backend type (e.g., "sqlite").
        version: Schema version.
        entry_count: Total history entries.
        change_count: Total change records.
        storage_size_bytes: Approximate storage size.
        oldest_entry: Timestamp of oldest entry.
        newest_entry: Timestamp of newest entry.
    """

    backend: str
    version: str
    entry_count: int = 0
    change_count: int = 0
    storage_size_bytes: int | None = None
    oldest_entry: datetime | None = None
    newest_entry: datetime | None = None


class SyncHistoryPort(ABC):
    """
    Abstract interface for sync history persistence.

    Implementations provide:
    - Audit trail: Complete record of all sync operations
    - Rollback: Ability to undo sync operations
    - Analytics: Queries for reporting and insights

    Example usage:
        # Record a sync
        history.record(entry)

        # Query history
        entries = history.query(HistoryQuery(epic_key="PROJ-100"))

        # Get rollback-able changes
        changes = history.get_changes(entry_id)

        # Perform rollback
        history.mark_rolled_back(entry_id, rollback_entry_id)

        # Get statistics
        stats = history.get_statistics()
    """

    # =========================================================================
    # Core Operations
    # =========================================================================

    @abstractmethod
    def record(self, entry: SyncHistoryEntry) -> None:
        """
        Record a sync history entry.

        Args:
            entry: The history entry to record.

        Raises:
            SyncHistoryError: If recording fails.
        """

    @abstractmethod
    def record_change(self, change: ChangeRecord) -> None:
        """
        Record an individual change for rollback tracking.

        Args:
            change: The change record to save.

        Raises:
            SyncHistoryError: If recording fails.
        """

    @abstractmethod
    def record_changes(self, changes: list[ChangeRecord]) -> None:
        """
        Record multiple changes in a batch.

        Args:
            changes: The change records to save.

        Raises:
            SyncHistoryError: If recording fails.
        """

    @abstractmethod
    def get_entry(self, entry_id: str) -> SyncHistoryEntry | None:
        """
        Get a specific history entry.

        Args:
            entry_id: The entry ID to retrieve.

        Returns:
            The entry if found, None otherwise.

        Raises:
            SyncHistoryError: If retrieval fails.
        """

    @abstractmethod
    def query(self, query: HistoryQuery) -> list[SyncHistoryEntry]:
        """
        Query sync history entries.

        Args:
            query: Query parameters.

        Returns:
            List of matching entries.

        Raises:
            SyncHistoryError: If query fails.
        """

    @abstractmethod
    def count(self, query: HistoryQuery | None = None) -> int:
        """
        Count entries matching a query.

        Args:
            query: Optional query parameters (None = count all).

        Returns:
            Number of matching entries.
        """

    # =========================================================================
    # Change Tracking & Rollback
    # =========================================================================

    @abstractmethod
    def get_changes(self, entry_id: str) -> list[ChangeRecord]:
        """
        Get all changes for a history entry.

        Args:
            entry_id: The history entry ID.

        Returns:
            List of change records.

        Raises:
            SyncHistoryError: If retrieval fails.
        """

    @abstractmethod
    def get_rollbackable_changes(self, entry_id: str) -> list[ChangeRecord]:
        """
        Get changes that can be rolled back.

        Returns changes that haven't been rolled back yet.

        Args:
            entry_id: The history entry ID.

        Returns:
            List of rollback-able change records.
        """

    @abstractmethod
    def mark_rolled_back(
        self,
        entry_id: str,
        rollback_entry_id: str,
        change_ids: list[str] | None = None,
    ) -> int:
        """
        Mark changes as rolled back.

        Args:
            entry_id: The original entry whose changes were rolled back.
            rollback_entry_id: The entry ID of the rollback operation.
            change_ids: Specific change IDs to mark (None = all changes).

        Returns:
            Number of changes marked as rolled back.

        Raises:
            RollbackError: If marking fails.
        """

    # =========================================================================
    # Analytics
    # =========================================================================

    @abstractmethod
    def get_statistics(
        self,
        query: HistoryQuery | None = None,
    ) -> SyncStatistics:
        """
        Get aggregated statistics.

        Args:
            query: Optional query to filter entries.

        Returns:
            Aggregated statistics.
        """

    @abstractmethod
    def get_velocity(
        self,
        start: datetime,
        end: datetime,
        interval_days: int = 7,
    ) -> list[VelocityMetrics]:
        """
        Get velocity metrics over time.

        Calculates metrics for each interval in the time range.

        Args:
            start: Start of time range.
            end: End of time range.
            interval_days: Size of each interval in days.

        Returns:
            List of velocity metrics per interval.
        """

    @abstractmethod
    def get_recent_activity(
        self,
        days: int = 7,
        limit: int = 50,
    ) -> list[SyncHistoryEntry]:
        """
        Get recent sync activity.

        Args:
            days: Number of days to look back.
            limit: Maximum entries to return.

        Returns:
            Recent history entries.
        """

    # =========================================================================
    # Maintenance
    # =========================================================================

    @abstractmethod
    def delete_before(self, before: datetime) -> int:
        """
        Delete entries before a timestamp.

        Also deletes associated change records.

        Args:
            before: Delete entries completed before this time.

        Returns:
            Number of entries deleted.
        """

    @abstractmethod
    def info(self) -> HistoryStoreInfo:
        """
        Get information about the history store.

        Returns:
            Store information.
        """

    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self) -> SyncHistoryPort:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def get_latest(
        self,
        markdown_path: str | None = None,
        epic_key: str | None = None,
    ) -> SyncHistoryEntry | None:
        """
        Get the most recent sync entry.

        Args:
            markdown_path: Optional filter by markdown path.
            epic_key: Optional filter by epic key.

        Returns:
            Most recent entry or None.
        """
        query = HistoryQuery(
            markdown_path=markdown_path,
            epic_key=epic_key,
            limit=1,
            order_desc=True,
        )
        entries = self.query(query)
        return entries[0] if entries else None

    def get_last_successful(
        self,
        markdown_path: str | None = None,
        epic_key: str | None = None,
    ) -> SyncHistoryEntry | None:
        """
        Get the most recent successful sync entry.

        Args:
            markdown_path: Optional filter by markdown path.
            epic_key: Optional filter by epic key.

        Returns:
            Most recent successful entry or None.
        """
        query = HistoryQuery(
            markdown_path=markdown_path,
            epic_key=epic_key,
            outcomes=["success"],
            dry_run=False,
            limit=1,
            order_desc=True,
        )
        entries = self.query(query)
        return entries[0] if entries else None

    # =========================================================================
    # Timestamp-Based Rollback
    # =========================================================================

    @abstractmethod
    def get_state_at_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> list[ChangeRecord]:
        """
        Get the cumulative state of changes at a specific point in time.

        Returns all changes that were applied up to and including the
        given timestamp that have not been subsequently rolled back.

        Args:
            timestamp: Point in time to query state.
            epic_key: Optional filter by epic key.
            tracker_type: Optional filter by tracker type.

        Returns:
            List of change records representing the state at that time.
        """

    @abstractmethod
    def get_changes_since_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> list[ChangeRecord]:
        """
        Get all changes made after a specific timestamp.

        Returns changes that need to be rolled back to restore state
        to the given point in time.

        Args:
            timestamp: Point in time from which to get changes.
            epic_key: Optional filter by epic key.
            tracker_type: Optional filter by tracker type.

        Returns:
            List of change records made after the timestamp, ordered
            newest first (for rollback order).
        """

    @abstractmethod
    def get_entry_at_timestamp(
        self,
        timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> SyncHistoryEntry | None:
        """
        Get the most recent sync entry before or at a timestamp.

        Useful for finding a known good state to restore to.

        Args:
            timestamp: Point in time to query.
            epic_key: Optional filter by epic key.
            tracker_type: Optional filter by tracker type.

        Returns:
            The most recent entry before or at the timestamp, or None.
        """

    @abstractmethod
    def list_rollback_points(
        self,
        epic_key: str | None = None,
        tracker_type: str | None = None,
        limit: int = 20,
    ) -> list[SyncHistoryEntry]:
        """
        List available rollback points (successful syncs).

        Returns recent successful sync entries that can be used as
        rollback targets.

        Args:
            epic_key: Optional filter by epic key.
            tracker_type: Optional filter by tracker type.
            limit: Maximum number of rollback points to return.

        Returns:
            List of successful sync entries, most recent first.
        """

    @abstractmethod
    def create_rollback_plan(
        self,
        target_timestamp: datetime,
        epic_key: str | None = None,
        tracker_type: str | None = None,
    ) -> RollbackPlan:
        """
        Create a plan for rolling back to a specific timestamp.

        Analyzes what changes need to be undone to restore state to
        the target timestamp.

        Args:
            target_timestamp: Point in time to roll back to.
            epic_key: Optional filter by epic key.
            tracker_type: Optional filter by tracker type.

        Returns:
            RollbackPlan with details of what will be rolled back.

        Raises:
            RollbackError: If a valid rollback plan cannot be created.
        """

    @abstractmethod
    def execute_rollback_plan(
        self,
        plan: RollbackPlan,
        rollback_entry_id: str,
    ) -> int:
        """
        Execute a rollback plan by marking changes as rolled back.

        Does NOT actually undo changes in the tracker - that must be
        done separately using the plan's change records.

        Args:
            plan: The rollback plan to execute.
            rollback_entry_id: Entry ID for the rollback operation.

        Returns:
            Number of changes marked as rolled back.

        Raises:
            RollbackError: If execution fails.
        """
