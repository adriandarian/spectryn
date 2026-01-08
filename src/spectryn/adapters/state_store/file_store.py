"""
File State Store - File-based state persistence using JSON files.

This is an adapter that wraps the existing StateStore implementation
to conform to the StateStorePort interface. It provides backward
compatibility with the default file-based storage.

Features:
- JSON file per session in ~/.spectra/state/
- Simple and portable (no database required)
- Human-readable state files
- Index file for efficient listing
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spectryn.application.sync.state import StateStore as LegacyStateStore
from spectryn.core.ports.state_store import (
    QuerySortField,
    QuerySortOrder,
    StateQuery,
    StateStoreError,
    StateStorePort,
    StateSummary,
    StoreInfo,
)


if TYPE_CHECKING:
    from spectryn.application.sync.state import SyncState

logger = logging.getLogger(__name__)


class FileStateStore(StateStorePort):
    """
    File-based state store implementation.

    Wraps the existing StateStore to provide the StateStorePort interface.
    Uses JSON files for persistence, one file per sync session.

    Example:
        # Basic usage
        store = FileStateStore("~/.spectra/state")
        store.save(sync_state)

        # Query states
        query = StateQuery(epic_key="PROJ-100")
        summaries = store.query(query)

        # Context manager
        with FileStateStore() as store:
            store.save(state)
    """

    DEFAULT_STATE_DIR = Path.home() / ".spectra" / "state"

    def __init__(self, state_dir: str | Path | None = None) -> None:
        """
        Initialize the file state store.

        Args:
            state_dir: Directory to store state files.
                       Defaults to ~/.spectra/state/
        """
        self.state_dir = Path(state_dir).expanduser() if state_dir else self.DEFAULT_STATE_DIR
        self._store = LegacyStateStore(state_dir=self.state_dir)
        logger.debug(f"File state store initialized at {self.state_dir}")

    def save(self, state: SyncState) -> None:
        """Save or update a sync state."""
        try:
            self._store.save(state)
            logger.debug(f"Saved state for session {state.session_id}")
        except Exception as e:
            raise StateStoreError(f"Failed to save state: {e}") from e

    def load(self, session_id: str) -> SyncState | None:
        """Load a sync state by session ID."""
        try:
            return self._store.load(session_id)
        except Exception as e:
            raise StateStoreError(f"Failed to load state: {e}") from e

    def delete(self, session_id: str) -> bool:
        """Delete a sync state."""
        try:
            return self._store.delete(session_id)
        except Exception as e:
            raise StateStoreError(f"Failed to delete state: {e}") from e

    def query(self, query: StateQuery) -> list[StateSummary]:
        """Query sync states with filters."""
        # Load all sessions from legacy store
        sessions = self._store.list_sessions()

        # Filter sessions
        filtered = self._filter_sessions(sessions, query)

        # Sort
        filtered = self._sort_sessions(filtered, query.sort_by, query.sort_order)

        # Paginate
        if query.offset:
            filtered = filtered[query.offset :]
        if query.limit:
            filtered = filtered[: query.limit]

        # Convert to StateSummary
        return [self._to_summary(s) for s in filtered]

    def _filter_sessions(
        self,
        sessions: list[dict[str, Any]],
        query: StateQuery,
    ) -> list[dict[str, Any]]:
        """Filter sessions based on query parameters."""
        result = sessions

        if query.session_id:
            result = [s for s in result if s.get("session_id") == query.session_id]

        if query.markdown_path:
            result = [s for s in result if s.get("markdown_path") == query.markdown_path]

        if query.epic_key:
            result = [s for s in result if s.get("epic_key") == query.epic_key]

        if query.phases:
            result = [s for s in result if s.get("phase") in query.phases]

        if query.exclude_phases:
            result = [s for s in result if s.get("phase") not in query.exclude_phases]

        if query.dry_run is not None:
            result = [s for s in result if s.get("dry_run") == query.dry_run]

        if query.created_after:
            after_str = query.created_after.isoformat()
            result = [s for s in result if s.get("created_at", "") >= after_str]

        if query.created_before:
            before_str = query.created_before.isoformat()
            result = [s for s in result if s.get("created_at", "") <= before_str]

        if query.updated_after:
            after_str = query.updated_after.isoformat()
            result = [s for s in result if s.get("updated_at", "") >= after_str]

        if query.updated_before:
            before_str = query.updated_before.isoformat()
            result = [s for s in result if s.get("updated_at", "") <= before_str]

        return result

    def _sort_sessions(
        self,
        sessions: list[dict[str, Any]],
        sort_by: QuerySortField,
        sort_order: QuerySortOrder,
    ) -> list[dict[str, Any]]:
        """Sort sessions by field and order."""
        field_map = {
            QuerySortField.CREATED_AT: "created_at",
            QuerySortField.UPDATED_AT: "updated_at",
            QuerySortField.SESSION_ID: "session_id",
            QuerySortField.EPIC_KEY: "epic_key",
        }
        field = field_map.get(sort_by, "updated_at")
        reverse = sort_order == QuerySortOrder.DESC

        return sorted(sessions, key=lambda s: s.get(field, ""), reverse=reverse)

    def _to_summary(self, session: dict[str, Any]) -> StateSummary:
        """Convert session dict to StateSummary."""
        # Load full state to get operation counts
        state = self._store.load(session.get("session_id", ""))

        operation_count = 0
        completed_count = 0
        failed_count = 0

        if state:
            operation_count = state.total_count
            completed_count = state.completed_count
            failed_count = state.failed_count

        created_at = session.get("created_at", "")
        updated_at = session.get("updated_at", "")

        return StateSummary(
            session_id=session.get("session_id", ""),
            markdown_path=session.get("markdown_path", ""),
            epic_key=session.get("epic_key", ""),
            phase=session.get("phase", ""),
            dry_run=session.get("dry_run", True),
            created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
            updated_at=datetime.fromisoformat(updated_at) if updated_at else datetime.now(),
            operation_count=operation_count,
            completed_count=completed_count,
            failed_count=failed_count,
        )

    def count(self, query: StateQuery | None = None) -> int:
        """Count states matching a query."""
        if query:
            return len(self.query(query))
        return len(self._store.list_sessions())

    def exists(self, session_id: str) -> bool:
        """Check if a state exists."""
        state_file = self.state_dir / f"{session_id}.json"
        return state_file.exists()

    def delete_before(self, before: datetime) -> int:
        """Delete states updated before a given time."""
        sessions = self._store.list_sessions()
        deleted = 0

        before_str = before.isoformat()
        for session in sessions:
            updated_at = session.get("updated_at", "")
            if updated_at and updated_at < before_str:
                if self._store.delete(session.get("session_id", "")):
                    deleted += 1

        logger.info(f"Deleted {deleted} states updated before {before}")
        return deleted

    def info(self) -> StoreInfo:
        """Get information about the state store."""
        sessions = self._store.list_sessions()

        # Count operations
        total_operations = 0
        for session in sessions:
            state = self._store.load(session.get("session_id", ""))
            if state:
                total_operations += state.total_count

        # Get storage size
        storage_size = 0
        try:
            for entry in self.state_dir.iterdir():
                if entry.is_file():
                    storage_size += entry.stat().st_size
        except OSError:
            pass

        return StoreInfo(
            backend="file",
            version="1",
            session_count=len(sessions),
            total_operations=total_operations,
            storage_size_bytes=storage_size,
            connection_info={"path": str(self.state_dir)},
        )

    def close(self) -> None:
        """Close the state store (no-op for file store)."""
