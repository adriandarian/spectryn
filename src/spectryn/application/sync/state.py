"""
Sync State - Persistence for resumable sync operations.

Allows sync operations to be interrupted and resumed, tracking
which operations have been completed and which are pending.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast


logger = logging.getLogger(__name__)


class SyncPhase(Enum):
    """Sync operation phases."""

    INITIALIZED = "initialized"
    ANALYZING = "analyzing"
    DESCRIPTIONS = "descriptions"
    SUBTASKS = "subtasks"
    COMMENTS = "comments"
    STATUSES = "statuses"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OperationRecord:
    """
    Record of a single sync operation.

    Attributes:
        operation_type: Type of operation (update_description, create_subtask, etc.)
        issue_key: The Jira issue key.
        story_id: The markdown story ID.
        status: completed, failed, or pending.
        error: Error message if failed.
        timestamp: When the operation was executed.
    """

    operation_type: str
    issue_key: str
    story_id: str
    status: str = "pending"  # pending, completed, failed, skipped
    error: str | None = None
    timestamp: str | None = None

    def mark_completed(self) -> None:
        """Mark this operation as completed."""
        self.status = "completed"
        self.timestamp = datetime.now().isoformat()

    def mark_failed(self, error: str) -> None:
        """Mark this operation as failed."""
        self.status = "failed"
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def mark_skipped(self, reason: str = "") -> None:
        """Mark this operation as skipped."""
        self.status = "skipped"
        self.error = reason
        self.timestamp = datetime.now().isoformat()

    @property
    def is_pending(self) -> bool:
        """Check if operation is still pending."""
        return self.status == "pending"

    @property
    def is_completed(self) -> bool:
        """Check if operation completed successfully."""
        return self.status == "completed"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "operation_type": self.operation_type,
            "issue_key": self.issue_key,
            "story_id": self.story_id,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperationRecord":
        """Create from dictionary."""
        return cls(
            operation_type=data["operation_type"],
            issue_key=data["issue_key"],
            story_id=data["story_id"],
            status=data.get("status", "pending"),
            error=data.get("error"),
            timestamp=data.get("timestamp"),
        )


@dataclass
class SyncState:
    """
    Complete state of a sync operation for persistence.

    Tracks all operations and their status, allowing sync to be
    resumed from where it left off.

    Attributes:
        session_id: Unique identifier for this sync session.
        markdown_path: Path to the markdown file being synced.
        epic_key: Jira epic key being synced to.
        phase: Current sync phase.
        operations: List of all operations and their status.
        config: Serialized sync configuration.
        created_at: When the sync started.
        updated_at: When the state was last updated.
        dry_run: Whether this is a dry-run sync.
    """

    session_id: str
    markdown_path: str
    epic_key: str
    phase: str = SyncPhase.INITIALIZED.value
    operations: list[OperationRecord] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    dry_run: bool = True

    # Matching info for resume
    matched_stories: list[tuple[str, str]] = field(default_factory=list)
    unmatched_stories: list[str] = field(default_factory=list)

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()

    def set_phase(self, phase: SyncPhase) -> None:
        """Update the current phase."""
        self.phase = phase.value
        self.update_timestamp()

    def add_operation(
        self,
        operation_type: str,
        issue_key: str,
        story_id: str,
    ) -> OperationRecord:
        """
        Add a new pending operation.

        Args:
            operation_type: Type of operation.
            issue_key: Jira issue key.
            story_id: Markdown story ID.

        Returns:
            The created OperationRecord.
        """
        op = OperationRecord(
            operation_type=operation_type,
            issue_key=issue_key,
            story_id=story_id,
        )
        self.operations.append(op)
        self.update_timestamp()
        return op

    def find_operation(
        self,
        operation_type: str,
        issue_key: str,
        story_id: str = "",
    ) -> OperationRecord | None:
        """
        Find an existing operation record.

        Args:
            operation_type: Type of operation.
            issue_key: Jira issue key.
            story_id: Optional markdown story ID.

        Returns:
            The matching OperationRecord or None.
        """
        for op in self.operations:
            if op.operation_type == operation_type and op.issue_key == issue_key:
                if not story_id or op.story_id == story_id:
                    return op
        return None

    def is_operation_completed(
        self,
        operation_type: str,
        issue_key: str,
        story_id: str = "",
    ) -> bool:
        """Check if an operation was already completed."""
        op = self.find_operation(operation_type, issue_key, story_id)
        return op is not None and op.is_completed

    @property
    def pending_count(self) -> int:
        """Number of pending operations."""
        return sum(1 for op in self.operations if op.is_pending)

    @property
    def completed_count(self) -> int:
        """Number of completed operations."""
        return sum(1 for op in self.operations if op.is_completed)

    @property
    def failed_count(self) -> int:
        """Number of failed operations."""
        return sum(1 for op in self.operations if op.status == "failed")

    @property
    def total_count(self) -> int:
        """Total number of operations."""
        return len(self.operations)

    @property
    def progress_percent(self) -> float:
        """Progress as a percentage (0.0 to 100.0)."""
        if self.total_count == 0:
            return 0.0
        return (self.completed_count / self.total_count) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "markdown_path": self.markdown_path,
            "epic_key": self.epic_key,
            "phase": self.phase,
            "operations": [op.to_dict() for op in self.operations],
            "config": self.config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "dry_run": self.dry_run,
            "matched_stories": self.matched_stories,
            "unmatched_stories": self.unmatched_stories,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncState":
        """Create from dictionary."""
        state = cls(
            session_id=data["session_id"],
            markdown_path=data["markdown_path"],
            epic_key=data["epic_key"],
            phase=data.get("phase", SyncPhase.INITIALIZED.value),
            config=data.get("config", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            dry_run=data.get("dry_run", True),
            matched_stories=data.get("matched_stories", []),
            unmatched_stories=data.get("unmatched_stories", []),
        )
        state.operations = [OperationRecord.from_dict(op) for op in data.get("operations", [])]
        return state

    @staticmethod
    def generate_session_id(markdown_path: str, epic_key: str) -> str:
        """
        Generate a unique session ID for a sync operation.

        Uses a hash of the inputs plus timestamp.
        """
        content = f"{markdown_path}:{epic_key}:{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


class StateStore:
    """
    Persistent storage for sync state.

    Stores sync state as JSON files in a configurable directory.
    Default location: ~/.spectra/state/
    """

    DEFAULT_STATE_DIR = Path.home() / ".spectra" / "state"

    def __init__(self, state_dir: Path | None = None):
        """
        Initialize the state store.

        Args:
            state_dir: Directory to store state files. Defaults to ~/.spectra/state/
        """
        self.state_dir = state_dir or self.DEFAULT_STATE_DIR
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the state directory exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self, session_id: str) -> Path:
        """Get the path to a state file."""
        return self.state_dir / f"{session_id}.json"

    def _index_file(self) -> Path:
        """Get the path to the state index file."""
        return self.state_dir / "index.json"

    def save(self, state: SyncState) -> Path:
        """
        Save sync state to disk.

        Args:
            state: The sync state to save.

        Returns:
            Path to the saved state file.
        """
        state.update_timestamp()
        state_file = self._state_file(state.session_id)

        with open(state_file, "w") as f:
            json.dump(state.to_dict(), f, indent=2)

        # Update index
        self._update_index(state)

        logger.debug(f"Saved sync state to {state_file}")
        return state_file

    def load(self, session_id: str) -> SyncState | None:
        """
        Load sync state from disk.

        Args:
            session_id: The session ID to load.

        Returns:
            The loaded SyncState, or None if not found.
        """
        state_file = self._state_file(session_id)

        if not state_file.exists():
            logger.debug(f"State file not found: {state_file}")
            return None

        try:
            with open(state_file) as f:
                data = json.load(f)
            return SyncState.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load state file {state_file}: {e}")
            return None

    def delete(self, session_id: str) -> bool:
        """
        Delete a sync state file.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        state_file = self._state_file(session_id)

        if state_file.exists():
            state_file.unlink()
            self._remove_from_index(session_id)
            logger.debug(f"Deleted state file: {state_file}")
            return True

        return False

    def list_sessions(self) -> list[dict]:
        """
        List all saved sync sessions.

        Returns:
            List of session summaries (session_id, markdown_path, epic_key, etc.)
        """
        index_file = self._index_file()

        if not index_file.exists():
            return []

        try:
            with open(index_file) as f:
                index: dict[str, Any] = json.load(f)
            sessions = index.get("sessions", [])
            if not isinstance(sessions, list):
                return []
            return cast(list[dict[str, Any]], sessions)
        except (json.JSONDecodeError, KeyError):
            return []

    def find_resumable(
        self,
        markdown_path: str | None = None,
        epic_key: str | None = None,
    ) -> list[dict]:
        """
        Find sessions that can be resumed.

        Args:
            markdown_path: Filter by markdown path.
            epic_key: Filter by epic key.

        Returns:
            List of matching session summaries.
        """
        sessions = self.list_sessions()

        # Filter incomplete sessions
        resumable = [
            s
            for s in sessions
            if s.get("phase") not in (SyncPhase.COMPLETED.value, SyncPhase.FAILED.value)
        ]

        if markdown_path:
            resumable = [s for s in resumable if s.get("markdown_path") == markdown_path]

        if epic_key:
            resumable = [s for s in resumable if s.get("epic_key") == epic_key]

        return resumable

    def find_latest_resumable(
        self,
        markdown_path: str,
        epic_key: str,
    ) -> SyncState | None:
        """
        Find the most recent resumable session for a given markdown/epic.

        Args:
            markdown_path: Path to the markdown file.
            epic_key: Jira epic key.

        Returns:
            The most recent incomplete SyncState, or None.
        """
        resumable = self.find_resumable(markdown_path, epic_key)

        if not resumable:
            return None

        # Sort by updated_at descending
        resumable.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

        # Load the most recent
        return self.load(resumable[0]["session_id"])

    def cleanup_old_sessions(self, max_age_days: int = 7) -> int:
        """
        Clean up old completed/failed sessions.

        Args:
            max_age_days: Maximum age in days for completed sessions.

        Returns:
            Number of sessions cleaned up.
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        sessions = self.list_sessions()
        cleaned = 0

        for session in sessions:
            # Only clean up completed or failed sessions
            if session.get("phase") not in (SyncPhase.COMPLETED.value, SyncPhase.FAILED.value):
                continue

            # Check age
            updated_at = session.get("updated_at", "")
            try:
                session_time = datetime.fromisoformat(updated_at)
                if session_time < cutoff and self.delete(session["session_id"]):
                    cleaned += 1
            except ValueError:
                continue

        return cleaned

    def _update_index(self, state: SyncState) -> None:
        """Update the session index with current state info."""
        index_file = self._index_file()

        # Load existing index
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
            except (json.JSONDecodeError, KeyError):
                index = {"sessions": []}
        else:
            index = {"sessions": []}

        # Update or add session
        sessions = index.get("sessions", [])
        session_info = {
            "session_id": state.session_id,
            "markdown_path": state.markdown_path,
            "epic_key": state.epic_key,
            "phase": state.phase,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "dry_run": state.dry_run,
            "progress": f"{state.completed_count}/{state.total_count}",
        }

        # Update existing or append
        updated = False
        for i, s in enumerate(sessions):
            if s.get("session_id") == state.session_id:
                sessions[i] = session_info
                updated = True
                break

        if not updated:
            sessions.append(session_info)

        index["sessions"] = sessions

        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

    def _remove_from_index(self, session_id: str) -> None:
        """Remove a session from the index."""
        index_file = self._index_file()

        if not index_file.exists():
            return

        try:
            with open(index_file) as f:
                index = json.load(f)

            sessions = index.get("sessions", [])
            sessions = [s for s in sessions if s.get("session_id") != session_id]
            index["sessions"] = sessions

            with open(index_file, "w") as f:
                json.dump(index, f, indent=2)
        except (json.JSONDecodeError, KeyError):
            pass
