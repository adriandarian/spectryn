"""
Tests for audit trail functionality.
"""

import json

from spectryn.application.sync.audit import (
    AuditEntry,
    AuditTrailRecorder,
    create_audit_trail,
)
from spectryn.core.domain.events import (
    CommentAdded,
    EventBus,
    StoryMatched,
    StoryUpdated,
    SubtaskCreated,
    SyncCompleted,
    SyncStarted,
)


# =============================================================================
# AuditEntry Tests
# =============================================================================


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_basic_entry(self):
        """Test creating a basic audit entry."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00Z",
            event_type="StoryUpdated",
            operation="Updated description",
            issue_key="PROJ-123",
            status="success",
        )

        assert entry.event_type == "StoryUpdated"
        assert entry.operation == "Updated description"
        assert entry.issue_key == "PROJ-123"
        assert entry.status == "success"

    def test_entry_with_details(self):
        """Test entry with additional details."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00Z",
            event_type="SubtaskCreated",
            operation="Created subtask",
            issue_key="PROJ-124",
            status="dry_run",
            details={"parent_key": "PROJ-123", "story_points": 3},
        )

        assert entry.details["parent_key"] == "PROJ-123"
        assert entry.details["story_points"] == 3

    def test_entry_with_error(self):
        """Test entry with error status."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00Z",
            event_type="StatusTransitioned",
            operation="Transition failed",
            issue_key="PROJ-125",
            status="failed",
            error="Transition not allowed from 'Done' to 'In Progress'",
        )

        assert entry.status == "failed"
        assert "not allowed" in entry.error

    def test_entry_to_dict(self):
        """Test serialization to dictionary."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00Z",
            event_type="CommentAdded",
            operation="Added commit log",
            issue_key="PROJ-126",
            status="success",
            details={"commit_count": 5},
        )

        data = entry.to_dict()

        assert data["timestamp"] == "2024-01-15T10:30:00Z"
        assert data["event_type"] == "CommentAdded"
        assert data["details"]["commit_count"] == 5
        assert "error" not in data  # Shouldn't include null error


# =============================================================================
# AuditTrail Tests
# =============================================================================


class TestAuditTrail:
    """Tests for AuditTrail class."""

    def test_create_audit_trail(self):
        """Test creating an audit trail."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
            dry_run=True,
        )

        assert trail.session_id == "abc123"
        assert trail.epic_key == "PROJ-100"
        assert trail.dry_run is True
        assert trail.entries == []

    def test_add_entry(self):
        """Test adding entries to audit trail."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )

        entry = trail.add_entry(
            event_type="StoryMatched",
            operation="Matched story US-001",
            issue_key="PROJ-101",
            status="success",
        )

        assert len(trail.entries) == 1
        assert trail.entries[0] == entry
        assert entry.event_type == "StoryMatched"

    def test_complete_audit_trail(self):
        """Test completing an audit trail with summary."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )

        trail.add_entry(
            event_type="StoryUpdated",
            operation="Updated description",
            issue_key="PROJ-101",
        )

        trail.complete(
            success=True,
            stories_matched=5,
            stories_updated=3,
            subtasks_created=10,
        )

        assert trail.completed_at is not None
        assert trail.summary["success"] is True
        assert trail.summary["stories_matched"] == 5
        assert trail.summary["subtasks_created"] == 10
        assert trail.summary["total_operations"] == 1

    def test_to_dict(self):
        """Test serialization to dictionary."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
            dry_run=False,
        )

        trail.add_entry(
            event_type="SubtaskCreated",
            operation="Created subtask",
            issue_key="PROJ-102",
        )
        trail.complete(success=True)

        data = trail.to_dict()

        assert "audit_trail" in data
        assert data["audit_trail"]["session_id"] == "abc123"
        assert data["audit_trail"]["epic_key"] == "PROJ-100"
        assert data["audit_trail"]["dry_run"] is False
        assert "summary" in data
        assert "entries" in data
        assert len(data["entries"]) == 1

    def test_to_json(self):
        """Test JSON serialization."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )

        trail.complete(success=True, stories_matched=2)

        json_str = trail.to_json()
        parsed = json.loads(json_str)

        assert parsed["audit_trail"]["session_id"] == "abc123"
        assert parsed["summary"]["stories_matched"] == 2

    def test_export_to_file(self, tmp_path):
        """Test exporting audit trail to file."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )

        trail.add_entry(
            event_type="SyncStarted",
            operation="Started sync",
            issue_key="PROJ-100",
        )
        trail.complete(success=True)

        output_path = tmp_path / "audit.json"
        result_path = trail.export(output_path)

        assert result_path.exists()

        # Verify content
        with open(result_path) as f:
            data = json.load(f)

        assert data["audit_trail"]["session_id"] == "abc123"
        assert len(data["entries"]) == 1

    def test_export_creates_parent_directories(self, tmp_path):
        """Test that export creates parent directories."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        trail.complete(success=True)

        nested_path = tmp_path / "deep" / "nested" / "audit.json"
        result_path = trail.export(nested_path)

        assert result_path.exists()


# =============================================================================
# AuditTrailRecorder Tests
# =============================================================================


class TestAuditTrailRecorder:
    """Tests for AuditTrailRecorder class."""

    def test_subscribe_to_event_bus(self):
        """Test subscribing to event bus."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=True)
        event_bus = EventBus()

        recorder.subscribe_to(event_bus)

        # Publish an event
        event_bus.publish(
            SyncStarted(
                epic_key="PROJ-100",
                markdown_path="/path/to/epic.md",
                dry_run=True,
            )
        )

        assert len(trail.entries) == 1
        assert trail.entries[0].event_type == "SyncStarted"

    def test_records_story_matched(self):
        """Test recording StoryMatched events."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=False)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        event_bus.publish(
            StoryMatched(
                story_id="US-001",
                issue_key="PROJ-101",
                match_confidence=1.0,
                match_method="title",
            )
        )

        assert len(trail.entries) == 1
        entry = trail.entries[0]
        assert entry.event_type == "StoryMatched"
        assert entry.issue_key == "PROJ-101"
        assert entry.status == "success"  # Not dry_run

    def test_records_story_updated(self):
        """Test recording StoryUpdated events."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=True)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        event_bus.publish(
            StoryUpdated(
                issue_key="PROJ-101",
                field_name="description",
                old_value="Old desc",
                new_value="New desc",
            )
        )

        entry = trail.entries[0]
        assert entry.event_type == "StoryUpdated"
        assert entry.operation == "Updated description"
        assert entry.status == "dry_run"

    def test_records_subtask_created(self):
        """Test recording SubtaskCreated events."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=False)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        event_bus.publish(
            SubtaskCreated(
                parent_key="PROJ-101",
                subtask_key="PROJ-102",
                subtask_name="Implement feature X",
                story_points=3,
            )
        )

        entry = trail.entries[0]
        assert entry.event_type == "SubtaskCreated"
        assert "Implement feature X" in entry.operation
        assert entry.details["story_points"] == 3

    def test_records_comment_added(self):
        """Test recording CommentAdded events."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=False)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        event_bus.publish(
            CommentAdded(
                issue_key="PROJ-101",
                comment_type="commits",
                commit_count=5,
            )
        )

        entry = trail.entries[0]
        assert entry.event_type == "CommentAdded"
        assert "5 commits" in entry.operation

    def test_records_sync_completed(self):
        """Test recording SyncCompleted events."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=False)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        event_bus.publish(
            SyncCompleted(
                epic_key="PROJ-100",
                stories_matched=5,
                stories_updated=3,
                subtasks_created=10,
                comments_added=2,
                errors=[],
            )
        )

        entry = trail.entries[0]
        assert entry.event_type == "SyncCompleted"
        assert entry.status == "success"
        assert entry.details["stories_matched"] == 5

    def test_full_sync_flow(self):
        """Test recording a complete sync flow."""
        trail = create_audit_trail(
            session_id="abc123",
            epic_key="PROJ-100",
            markdown_path="/path/to/epic.md",
        )
        recorder = AuditTrailRecorder(trail, dry_run=False)
        event_bus = EventBus()
        recorder.subscribe_to(event_bus)

        # Simulate sync flow
        event_bus.publish(
            SyncStarted(
                epic_key="PROJ-100",
                markdown_path="/path/to/epic.md",
                dry_run=False,
            )
        )
        event_bus.publish(
            StoryMatched(
                story_id="US-001",
                issue_key="PROJ-101",
            )
        )
        event_bus.publish(
            StoryUpdated(
                issue_key="PROJ-101",
                field_name="description",
            )
        )
        event_bus.publish(
            SubtaskCreated(
                parent_key="PROJ-101",
                subtask_key="PROJ-102",
                subtask_name="Task 1",
            )
        )
        event_bus.publish(
            SyncCompleted(
                epic_key="PROJ-100",
                stories_matched=1,
                stories_updated=1,
                subtasks_created=1,
            )
        )

        assert len(trail.entries) == 5
        assert trail.entries[0].event_type == "SyncStarted"
        assert trail.entries[-1].event_type == "SyncCompleted"


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIArgumentParsing:
    """Test CLI argument parsing for audit trail."""

    def test_audit_trail_argument(self):
        """Test --audit-trail argument parsing."""
        from spectryn.cli.app import create_parser

        parser = create_parser()

        # Default is None
        args = parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "PROJ-123",
            ]
        )
        assert args.audit_trail is None

        # With path
        args = parser.parse_args(
            [
                "--input",
                "epic.md",
                "--epic",
                "PROJ-123",
                "--audit-trail",
                "/var/log/audit.json",
            ]
        )
        assert args.audit_trail == "/var/log/audit.json"
