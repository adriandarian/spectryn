"""
Audit Trail - Records all sync operations for compliance and debugging.

Provides a structured record of every action taken during a sync operation,
including timestamps, operation details, and outcomes.
"""

import getpass
import json
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spectryn.core.domain.events import (
    CommentAdded,
    DomainEvent,
    EventBus,
    StatusTransitioned,
    StoryMatched,
    StoryUpdated,
    SubtaskCreated,
    SubtaskUpdated,
    SyncCompleted,
    SyncStarted,
)


@dataclass
class AuditEntry:
    """
    A single audit trail entry.

    Captures all relevant details about an operation for auditing purposes.

    Attributes:
        timestamp: ISO8601 timestamp in UTC.
        event_type: Type of event (e.g., "StoryUpdated", "SubtaskCreated").
        operation: Human-readable operation description.
        issue_key: The Jira issue key involved.
        status: Outcome - "success", "failed", "skipped", "dry_run".
        details: Additional event-specific details.
        error: Error message if status is "failed".
    """

    timestamp: str
    event_type: str
    operation: str
    issue_key: str = ""
    status: str = "success"
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "operation": self.operation,
            "issue_key": self.issue_key,
            "status": self.status,
        }
        if self.details:
            result["details"] = self.details
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class AuditTrail:
    """
    Complete audit trail for a sync session.

    Records all operations performed during a sync, with metadata
    about the session for traceability.

    Attributes:
        session_id: Unique identifier for this sync session.
        started_at: When the sync started (ISO8601 UTC).
        completed_at: When the sync completed (ISO8601 UTC).
        epic_key: The Jira epic being synced.
        markdown_path: Path to the markdown file.
        dry_run: Whether this was a dry-run.
        user: Username of the person running the sync.
        hostname: Machine hostname where sync was run.
        entries: List of audit entries.
        summary: Summary statistics.
    """

    session_id: str
    started_at: str
    epic_key: str
    markdown_path: str
    dry_run: bool = True
    completed_at: str | None = None
    user: str = field(default_factory=lambda: getpass.getuser())
    hostname: str = field(default_factory=socket.gethostname)
    entries: list[AuditEntry] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    spectra_version: str = "2.0.0"

    def add_entry(
        self,
        event_type: str,
        operation: str,
        issue_key: str = "",
        status: str = "success",
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AuditEntry:
        """
        Add an audit entry.

        Args:
            event_type: Type of event.
            operation: Human-readable operation description.
            issue_key: Jira issue key involved.
            status: Outcome status.
            details: Additional details.
            error: Error message if failed.

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            operation=operation,
            issue_key=issue_key,
            status=status,
            details=details or {},
            error=error,
        )
        self.entries.append(entry)
        return entry

    def complete(
        self,
        success: bool,
        stories_matched: int = 0,
        stories_updated: int = 0,
        subtasks_created: int = 0,
        subtasks_updated: int = 0,
        comments_added: int = 0,
        statuses_updated: int = 0,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        """
        Mark the audit trail as complete with summary statistics.

        Args:
            success: Whether the sync was successful.
            stories_matched: Number of stories matched.
            stories_updated: Number of descriptions updated.
            subtasks_created: Number of subtasks created.
            subtasks_updated: Number of subtasks updated.
            comments_added: Number of comments added.
            statuses_updated: Number of status transitions.
            errors: List of error messages.
            warnings: List of warning messages.
        """
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.summary = {
            "success": success,
            "total_operations": len(self.entries),
            "stories_matched": stories_matched,
            "stories_updated": stories_updated,
            "subtasks_created": subtasks_created,
            "subtasks_updated": subtasks_updated,
            "comments_added": comments_added,
            "statuses_updated": statuses_updated,
            "errors_count": len(errors or []),
            "warnings_count": len(warnings or []),
        }
        if errors:
            self.summary["errors"] = errors
        if warnings:
            self.summary["warnings"] = warnings

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "audit_trail": {
                "version": "1.0",
                "spectra_version": self.spectra_version,
                "session_id": self.session_id,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "epic_key": self.epic_key,
                "markdown_path": self.markdown_path,
                "dry_run": self.dry_run,
                "user": self.user,
                "hostname": self.hostname,
            },
            "summary": self.summary,
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def export(self, path: str | Path) -> Path:
        """
        Export audit trail to a JSON file.

        Args:
            path: Path to the output file.

        Returns:
            Path to the exported file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

        return path


class AuditTrailRecorder:
    """
    Records domain events into an audit trail.

    Subscribe this to an EventBus to automatically capture all
    sync operations into the audit trail.
    """

    def __init__(
        self,
        audit_trail: AuditTrail,
        dry_run: bool = True,
    ):
        """
        Initialize the recorder.

        Args:
            audit_trail: The audit trail to record to.
            dry_run: Whether this is a dry-run sync.
        """
        self.audit_trail = audit_trail
        self.dry_run = dry_run

    def subscribe_to(self, event_bus: EventBus) -> None:
        """
        Subscribe to all relevant events on the event bus.

        Args:
            event_bus: The event bus to subscribe to.
        """
        event_bus.subscribe(DomainEvent, self._handle_event)

    def _handle_event(self, event: DomainEvent) -> None:
        """Handle any domain event and record it."""
        status = "dry_run" if self.dry_run else "success"

        if isinstance(event, SyncStarted):
            self.audit_trail.add_entry(
                event_type="SyncStarted",
                operation="Started sync operation",
                issue_key=str(event.epic_key) if event.epic_key else "",
                status=status,
                details={
                    "markdown_path": event.markdown_path,
                    "dry_run": event.dry_run,
                },
            )

        elif isinstance(event, StoryMatched):
            self.audit_trail.add_entry(
                event_type="StoryMatched",
                operation=f"Matched story '{event.story_id}' to issue",
                issue_key=str(event.issue_key) if event.issue_key else "",
                status=status,
                details={
                    "story_id": str(event.story_id) if event.story_id else "",
                    "match_confidence": event.match_confidence,
                    "match_method": event.match_method,
                },
            )

        elif isinstance(event, StoryUpdated):
            self.audit_trail.add_entry(
                event_type="StoryUpdated",
                operation=f"Updated {event.field_name}",
                issue_key=str(event.issue_key) if event.issue_key else "",
                status=status,
                details={
                    "field_name": event.field_name,
                    "had_previous_value": event.old_value is not None,
                },
            )

        elif isinstance(event, SubtaskCreated):
            self.audit_trail.add_entry(
                event_type="SubtaskCreated",
                operation=f"Created subtask '{event.subtask_name}'",
                issue_key=str(event.subtask_key) if event.subtask_key else "",
                status=status,
                details={
                    "parent_key": str(event.parent_key) if event.parent_key else "",
                    "subtask_name": event.subtask_name,
                    "story_points": event.story_points,
                },
            )

        elif isinstance(event, SubtaskUpdated):
            self.audit_trail.add_entry(
                event_type="SubtaskUpdated",
                operation="Updated subtask",
                issue_key=str(event.subtask_key) if event.subtask_key else "",
                status=status,
                details={
                    "changes": list(event.changes.keys()) if event.changes else [],
                },
            )

        elif isinstance(event, StatusTransitioned):
            self.audit_trail.add_entry(
                event_type="StatusTransitioned",
                operation=f"Transitioned from '{event.from_status}' to '{event.to_status}'",
                issue_key=str(event.issue_key) if event.issue_key else "",
                status=status,
                details={
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "transition_id": event.transition_id,
                },
            )

        elif isinstance(event, CommentAdded):
            operation = f"Added {event.comment_type} comment"
            if event.commit_count > 0:
                operation = f"Added commit log with {event.commit_count} commits"

            self.audit_trail.add_entry(
                event_type="CommentAdded",
                operation=operation,
                issue_key=str(event.issue_key) if event.issue_key else "",
                status=status,
                details={
                    "comment_type": event.comment_type,
                    "commit_count": event.commit_count,
                },
            )

        elif isinstance(event, SyncCompleted):
            self.audit_trail.add_entry(
                event_type="SyncCompleted",
                operation="Completed sync operation",
                issue_key=str(event.epic_key) if event.epic_key else "",
                status="success" if not event.errors else "partial_success",
                details={
                    "stories_matched": event.stories_matched,
                    "stories_updated": event.stories_updated,
                    "subtasks_created": event.subtasks_created,
                    "comments_added": event.comments_added,
                    "errors_count": len(event.errors) if event.errors else 0,
                },
            )


def create_audit_trail(
    session_id: str,
    epic_key: str,
    markdown_path: str,
    dry_run: bool = True,
) -> AuditTrail:
    """
    Create a new audit trail for a sync session.

    Args:
        session_id: Unique session identifier.
        epic_key: The Jira epic key.
        markdown_path: Path to the markdown file.
        dry_run: Whether this is a dry-run.

    Returns:
        Configured AuditTrail instance.
    """
    return AuditTrail(
        session_id=session_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        epic_key=epic_key,
        markdown_path=markdown_path,
        dry_run=dry_run,
    )
