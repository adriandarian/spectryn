"""
State Store Port - Abstract interface for sync state persistence.

Provides a pluggable backend for persisting sync state. Default implementation
uses JSON files, but this port enables alternative backends like SQLite or
PostgreSQL for large-scale deployments.

Benefits of database backends:
- Better concurrent access handling
- Transaction support for atomic operations
- Efficient querying across many sessions
- Better scalability for large state volumes
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.application.sync.state import SyncState


class StateStoreError(Exception):
    """Base exception for state store errors."""


class ConnectionError(StateStoreError):
    """Failed to connect to the state store."""


class TransactionError(StateStoreError):
    """Transaction failed."""


class MigrationError(StateStoreError):
    """Database migration failed."""


class QuerySortField(Enum):
    """Fields available for sorting state queries."""

    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    SESSION_ID = "session_id"
    EPIC_KEY = "epic_key"


class QuerySortOrder(Enum):
    """Sort order for queries."""

    ASC = "asc"
    DESC = "desc"


@dataclass
class StateQuery:
    """
    Query parameters for finding sync states.

    Attributes:
        session_id: Filter by exact session ID.
        markdown_path: Filter by markdown file path.
        epic_key: Filter by epic key.
        phases: Filter by phase (e.g., ["completed", "failed"]).
        exclude_phases: Exclude these phases from results.
        dry_run: Filter by dry_run flag (None = any).
        created_after: States created after this time.
        created_before: States created before this time.
        updated_after: States updated after this time.
        updated_before: States updated before this time.
        sort_by: Field to sort by.
        sort_order: Sort direction.
        limit: Maximum results to return.
        offset: Skip this many results (for pagination).
    """

    session_id: str | None = None
    markdown_path: str | None = None
    epic_key: str | None = None
    phases: list[str] | None = None
    exclude_phases: list[str] | None = None
    dry_run: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    sort_by: QuerySortField = QuerySortField.UPDATED_AT
    sort_order: QuerySortOrder = QuerySortOrder.DESC
    limit: int | None = None
    offset: int = 0


@dataclass
class StateSummary:
    """
    Summary of a sync state for listing.

    Lighter-weight than full SyncState for efficient listing.

    Attributes:
        session_id: Unique session identifier.
        markdown_path: Path to the markdown file.
        epic_key: Jira epic key.
        phase: Current sync phase.
        dry_run: Whether this was a dry run.
        created_at: When the session was created.
        updated_at: When the session was last updated.
        operation_count: Total number of operations.
        completed_count: Number of completed operations.
        failed_count: Number of failed operations.
    """

    session_id: str
    markdown_path: str
    epic_key: str
    phase: str
    dry_run: bool
    created_at: datetime
    updated_at: datetime
    operation_count: int = 0
    completed_count: int = 0
    failed_count: int = 0

    @property
    def progress_percent(self) -> float:
        """Progress as a percentage (0.0 to 100.0)."""
        if self.operation_count == 0:
            return 0.0
        return (self.completed_count / self.operation_count) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "markdown_path": self.markdown_path,
            "epic_key": self.epic_key,
            "phase": self.phase,
            "dry_run": self.dry_run,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "operation_count": self.operation_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
        }


@dataclass
class StoreInfo:
    """
    Information about the state store.

    Attributes:
        backend: Backend type (e.g., "file", "sqlite", "postgresql").
        version: Schema version.
        session_count: Total number of stored sessions.
        total_operations: Total operations across all sessions.
        storage_size_bytes: Approximate storage size in bytes.
        connection_info: Backend-specific connection info (sanitized).
    """

    backend: str
    version: str
    session_count: int = 0
    total_operations: int = 0
    storage_size_bytes: int | None = None
    connection_info: dict[str, Any] = field(default_factory=dict)


class StateStorePort(ABC):
    """
    Abstract interface for sync state persistence.

    Implementations can use different backends:
    - File-based (default): JSON files in ~/.spectra/state/
    - SQLite: Local database for better concurrency
    - PostgreSQL: For distributed/multi-user deployments

    Example usage:
        # Save a state
        state = SyncState(session_id="abc123", ...)
        store.save(state)

        # Load a state
        state = store.load("abc123")

        # Query states
        query = StateQuery(epic_key="PROJ-100", phases=["completed"])
        summaries = store.query(query)

        # Delete old states
        store.delete_before(datetime.now() - timedelta(days=30))
    """

    @abstractmethod
    def save(self, state: SyncState) -> None:
        """
        Save or update a sync state.

        If a state with the same session_id exists, it will be updated.
        Otherwise, a new state will be created.

        Args:
            state: The sync state to save.

        Raises:
            StateStoreError: If save fails.
        """

    @abstractmethod
    def load(self, session_id: str) -> SyncState | None:
        """
        Load a sync state by session ID.

        Args:
            session_id: The session ID to load.

        Returns:
            The SyncState if found, None otherwise.

        Raises:
            StateStoreError: If load fails due to backend error.
        """

    @abstractmethod
    def delete(self, session_id: str) -> bool:
        """
        Delete a sync state.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            StateStoreError: If delete fails.
        """

    @abstractmethod
    def query(self, query: StateQuery) -> list[StateSummary]:
        """
        Query sync states with filters.

        Returns lightweight summaries for efficient listing.

        Args:
            query: Query parameters.

        Returns:
            List of matching state summaries.

        Raises:
            StateStoreError: If query fails.
        """

    @abstractmethod
    def count(self, query: StateQuery | None = None) -> int:
        """
        Count states matching a query.

        Args:
            query: Optional query parameters (None = count all).

        Returns:
            Number of matching states.

        Raises:
            StateStoreError: If count fails.
        """

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        """
        Check if a state exists.

        Args:
            session_id: The session ID to check.

        Returns:
            True if exists, False otherwise.
        """

    @abstractmethod
    def delete_before(self, before: datetime) -> int:
        """
        Delete states updated before a given time.

        Useful for cleanup/retention policies.

        Args:
            before: Delete states updated before this time.

        Returns:
            Number of states deleted.

        Raises:
            StateStoreError: If deletion fails.
        """

    @abstractmethod
    def info(self) -> StoreInfo:
        """
        Get information about the state store.

        Returns:
            StoreInfo with backend details.
        """

    @abstractmethod
    def close(self) -> None:
        """
        Close the state store and release resources.

        Should be called when done with the store.
        """

    # Convenience methods with default implementations

    def list_sessions(self) -> list[StateSummary]:
        """
        List all sessions.

        Returns:
            List of all state summaries.
        """
        return self.query(StateQuery())

    def find_resumable(
        self,
        markdown_path: str | None = None,
        epic_key: str | None = None,
    ) -> list[StateSummary]:
        """
        Find sessions that can be resumed.

        Args:
            markdown_path: Filter by markdown path.
            epic_key: Filter by epic key.

        Returns:
            List of incomplete session summaries.
        """
        query = StateQuery(
            markdown_path=markdown_path,
            epic_key=epic_key,
            exclude_phases=["completed", "failed"],
            sort_by=QuerySortField.UPDATED_AT,
            sort_order=QuerySortOrder.DESC,
        )
        return self.query(query)

    def find_latest_resumable(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> SyncState | None:
        """
        Find the most recent resumable session.

        Args:
            markdown_path: Path to the markdown file.
            epic_key: Jira epic key.

        Returns:
            Most recent incomplete SyncState, or None.
        """
        summaries = self.find_resumable(markdown_path, epic_key)
        if not summaries:
            return None
        return self.load(summaries[0].session_id)

    def __enter__(self) -> StateStorePort:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
