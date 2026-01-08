"""Tests for application commands."""

from unittest.mock import Mock

import pytest

from spectryn.application.commands import (
    AddCommentCommand,
    CommandBatch,
    CommandResult,
    CreateSubtaskCommand,
    TransitionStatusCommand,
    UpdateDescriptionCommand,
    UpdateSubtaskCommand,
)
from spectryn.core.domain.events import EventBus
from spectryn.core.ports.issue_tracker import IssueData, IssueTrackerError


class TestCommandResult:
    """Tests for CommandResult."""

    def test_ok(self):
        result = CommandResult.ok("data")
        assert result.success
        assert result.data == "data"
        assert not result.dry_run

    def test_ok_dry_run(self):
        result = CommandResult.ok("data", dry_run=True)
        assert result.success
        assert result.dry_run

    def test_fail(self):
        result = CommandResult.fail("error message")
        assert not result.success
        assert result.error == "error message"

    def test_skip(self):
        result = CommandResult.skip("reason")
        assert result.success
        assert result.skipped


class TestUpdateDescriptionCommand:
    """Tests for UpdateDescriptionCommand."""

    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.get_issue.return_value = IssueData(
            key="PROJ-123", summary="Test", description="Old description"
        )
        tracker.update_issue_description.return_value = True
        return tracker

    def test_validate_missing_key(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="", description="New description"
        )
        assert cmd.validate() is not None

    def test_validate_missing_description(self, mock_tracker):
        cmd = UpdateDescriptionCommand(tracker=mock_tracker, issue_key="PROJ-123", description="")
        assert cmd.validate() is not None

    def test_execute_dry_run(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New description", dry_run=True
        )

        result = cmd.execute()

        assert result.success
        assert result.dry_run
        mock_tracker.update_issue_description.assert_not_called()

    def test_execute_success(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New description", dry_run=False
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.update_issue_description.assert_called_once()

    def test_name_property(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New description"
        )
        assert "PROJ-123" in cmd.name

    def test_supports_undo(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New description"
        )
        assert cmd.supports_undo is True

    def test_undo(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New description", dry_run=False
        )
        # Execute to capture undo data
        cmd.execute()

        # Undo
        undo_result = cmd.undo()

        assert undo_result is not None
        assert undo_result.success
        # Should restore to "Old description"
        mock_tracker.update_issue_description.assert_called_with("PROJ-123", "Old description")

    def test_undo_without_execute(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New"
        )
        # Undo without execute returns None
        assert cmd.undo() is None

    def test_execute_with_tracker_error(self, mock_tracker):
        mock_tracker.get_issue.return_value = IssueData(
            key="PROJ-123", summary="Test", description="Old"
        )
        mock_tracker.update_issue_description.side_effect = IssueTrackerError("Update failed")

        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New", dry_run=False
        )

        result = cmd.execute()

        assert not result.success
        assert "Update failed" in result.error

    def test_undo_with_tracker_error(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker, issue_key="PROJ-123", description="New", dry_run=False
        )
        cmd.execute()

        # Make undo fail
        mock_tracker.update_issue_description.side_effect = IssueTrackerError("Undo failed")
        undo_result = cmd.undo()

        assert not undo_result.success
        assert "Undo failed" in undo_result.error

    def test_execute_with_event_bus(self, mock_tracker):
        from spectryn.core.domain.events import DomainEvent, StoryUpdated

        event_bus = EventBus()
        events: list[DomainEvent] = []
        event_bus.subscribe(DomainEvent, lambda e: events.append(e))

        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            description="New",
            event_bus=event_bus,
            dry_run=False,
        )

        cmd.execute()

        assert len(events) == 1
        assert isinstance(events[0], StoryUpdated)
        assert events[0].issue_key == "PROJ-123"
        assert events[0].field_name == "description"


class TestCreateSubtaskCommand:
    """Tests for CreateSubtaskCommand."""

    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.create_subtask.return_value = "PROJ-456"
        return tracker

    def test_validate_missing_parent(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker, parent_key="", project_key="PROJ", summary="Subtask"
        )
        assert cmd.validate() is not None

    def test_validate_missing_project(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker, parent_key="PROJ-123", project_key="", summary="Subtask"
        )
        assert cmd.validate() is not None
        assert "project" in cmd.validate().lower()

    def test_validate_missing_summary(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker, parent_key="PROJ-123", project_key="PROJ", summary=""
        )
        assert cmd.validate() is not None
        assert "summary" in cmd.validate().lower()

    def test_execute_dry_run(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="New subtask",
            dry_run=True,
        )

        result = cmd.execute()

        assert result.success
        assert result.dry_run
        mock_tracker.create_subtask.assert_not_called()

    def test_execute_success(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="New subtask",
            dry_run=False,
        )

        result = cmd.execute()

        assert result.success
        assert result.data == "PROJ-456"

    def test_name_property(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="New subtask with a long name that gets truncated",
        )
        assert "PROJ-123" in cmd.name
        assert "New subtask" in cmd.name

    def test_execute_with_all_options(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="Full subtask",
            description="Detailed description",
            story_points=3,
            assignee="user@example.com",
            priority="high",
            dry_run=False,
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.create_subtask.assert_called_once_with(
            parent_key="PROJ-123",
            summary="Full subtask",
            description="Detailed description",
            project_key="PROJ",
            story_points=3,
            assignee="user@example.com",
            priority="high",
        )

    def test_execute_with_tracker_error(self, mock_tracker):
        mock_tracker.create_subtask.side_effect = IssueTrackerError("Creation failed")

        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="Subtask",
            dry_run=False,
        )

        result = cmd.execute()

        assert not result.success
        assert "Creation failed" in result.error

    def test_execute_returns_none_key(self, mock_tracker):
        mock_tracker.create_subtask.return_value = None

        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="Subtask",
            dry_run=False,
        )

        result = cmd.execute()

        assert not result.success
        assert "Failed" in result.error

    def test_execute_with_event_bus(self, mock_tracker):
        from spectryn.core.domain.events import DomainEvent, SubtaskCreated

        event_bus = EventBus()
        events: list[DomainEvent] = []
        event_bus.subscribe(DomainEvent, lambda e: events.append(e))

        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="Subtask",
            story_points=3,
            event_bus=event_bus,
            dry_run=False,
        )

        cmd.execute()

        assert len(events) == 1
        assert isinstance(events[0], SubtaskCreated)
        assert events[0].parent_key == "PROJ-123"
        assert events[0].subtask_key == "PROJ-456"
        assert events[0].subtask_name == "Subtask"


class TestTransitionStatusCommand:
    """Tests for TransitionStatusCommand."""

    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.get_issue_status.return_value = "Open"
        tracker.transition_issue.return_value = True
        return tracker

    def test_execute_dry_run(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Resolved", dry_run=True
        )

        result = cmd.execute()

        assert result.success
        assert result.dry_run

    def test_execute_success(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Resolved", dry_run=False
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.transition_issue.assert_called_with("PROJ-123", "Resolved")

    def test_validate_missing_key(self, mock_tracker):
        cmd = TransitionStatusCommand(tracker=mock_tracker, issue_key="", target_status="Done")
        assert cmd.validate() is not None
        assert "key" in cmd.validate().lower()

    def test_validate_missing_status(self, mock_tracker):
        cmd = TransitionStatusCommand(tracker=mock_tracker, issue_key="PROJ-123", target_status="")
        assert cmd.validate() is not None
        assert "status" in cmd.validate().lower()

    def test_name_property(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done"
        )
        assert "PROJ-123" in cmd.name
        assert "Done" in cmd.name

    def test_supports_undo(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done"
        )
        assert cmd.supports_undo is True

    def test_undo(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done", dry_run=False
        )
        # Execute to capture undo data
        cmd.execute()

        # Undo
        undo_result = cmd.undo()

        assert undo_result is not None
        assert undo_result.success
        mock_tracker.transition_issue.assert_called_with("PROJ-123", "Open")

    def test_undo_without_execute(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done"
        )
        # Undo without execute returns None
        assert cmd.undo() is None

    def test_execute_with_tracker_error(self, mock_tracker):
        mock_tracker.get_issue_status.side_effect = IssueTrackerError("API error")

        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done", dry_run=False
        )

        result = cmd.execute()

        assert not result.success
        assert "API error" in result.error

    def test_undo_with_tracker_error(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker, issue_key="PROJ-123", target_status="Done", dry_run=False
        )
        cmd.execute()

        # Make undo fail
        mock_tracker.transition_issue.side_effect = IssueTrackerError("Undo failed")
        undo_result = cmd.undo()

        assert not undo_result.success
        assert "Undo failed" in undo_result.error


class TestAddCommentCommand:
    """Tests for AddCommentCommand."""

    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.add_comment.return_value = True
        return tracker

    def test_execute_dry_run(self, mock_tracker):
        cmd = AddCommentCommand(
            tracker=mock_tracker, issue_key="PROJ-123", body="Test comment", dry_run=True
        )

        result = cmd.execute()

        assert result.success
        assert result.dry_run
        mock_tracker.add_comment.assert_not_called()

    def test_execute_success(self, mock_tracker):
        cmd = AddCommentCommand(
            tracker=mock_tracker, issue_key="PROJ-123", body="Test comment", dry_run=False
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.add_comment.assert_called_once_with("PROJ-123", "Test comment")

    def test_validate_missing_key(self, mock_tracker):
        cmd = AddCommentCommand(tracker=mock_tracker, issue_key="", body="Comment")
        assert cmd.validate() is not None
        assert "key" in cmd.validate().lower()

    def test_validate_missing_body(self, mock_tracker):
        cmd = AddCommentCommand(tracker=mock_tracker, issue_key="PROJ-123", body="")
        assert cmd.validate() is not None
        assert "body" in cmd.validate().lower()

    def test_name_property(self, mock_tracker):
        cmd = AddCommentCommand(tracker=mock_tracker, issue_key="PROJ-123", body="Test")
        assert "PROJ-123" in cmd.name

    def test_execute_with_tracker_error(self, mock_tracker):
        mock_tracker.add_comment.side_effect = IssueTrackerError("Comment failed")

        cmd = AddCommentCommand(
            tracker=mock_tracker, issue_key="PROJ-123", body="Test", dry_run=False
        )

        result = cmd.execute()

        assert not result.success
        assert "Comment failed" in result.error

    def test_execute_with_event_bus(self, mock_tracker):
        from spectryn.core.domain.events import CommentAdded, DomainEvent

        event_bus = EventBus()
        events: list[DomainEvent] = []
        event_bus.subscribe(DomainEvent, lambda e: events.append(e))

        cmd = AddCommentCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            body="Test",
            event_bus=event_bus,
            dry_run=False,
        )

        cmd.execute()

        assert len(events) == 1
        assert isinstance(events[0], CommentAdded)
        assert events[0].issue_key == "PROJ-123"


class TestUpdateSubtaskCommand:
    """Tests for UpdateSubtaskCommand."""

    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.update_subtask.return_value = True
        return tracker

    def test_execute_with_description(self, mock_tracker):
        cmd = UpdateSubtaskCommand(
            tracker=mock_tracker,
            issue_key="PROJ-456",
            description="Updated description",
            dry_run=False,
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.update_subtask.assert_called_once()

    def test_execute_with_story_points(self, mock_tracker):
        cmd = UpdateSubtaskCommand(
            tracker=mock_tracker,
            issue_key="PROJ-456",
            story_points=5,
            dry_run=False,
        )

        result = cmd.execute()

        assert result.success

    def test_validate_missing_key(self, mock_tracker):
        cmd = UpdateSubtaskCommand(tracker=mock_tracker, issue_key="", description="Desc")
        assert cmd.validate() is not None
        assert "key" in cmd.validate().lower()

    def test_validate_no_fields_to_update(self, mock_tracker):
        cmd = UpdateSubtaskCommand(tracker=mock_tracker, issue_key="PROJ-123")
        assert cmd.validate() is not None
        assert "field" in cmd.validate().lower()

    def test_name_property(self, mock_tracker):
        cmd = UpdateSubtaskCommand(tracker=mock_tracker, issue_key="PROJ-456", description="Desc")
        assert "PROJ-456" in cmd.name

    def test_execute_with_tracker_error(self, mock_tracker):
        mock_tracker.update_subtask.side_effect = IssueTrackerError("Update failed")

        cmd = UpdateSubtaskCommand(
            tracker=mock_tracker,
            issue_key="PROJ-456",
            description="Desc",
            dry_run=False,
        )

        result = cmd.execute()

        assert not result.success
        assert "Update failed" in result.error

    def test_execute_with_multiple_fields(self, mock_tracker):
        cmd = UpdateSubtaskCommand(
            tracker=mock_tracker,
            issue_key="PROJ-456",
            description="Desc",
            story_points=3,
            assignee="user@example.com",
            priority_id="high",
            dry_run=False,
        )

        result = cmd.execute()

        assert result.success
        mock_tracker.update_subtask.assert_called_once_with(
            issue_key="PROJ-456",
            description="Desc",
            story_points=3,
            assignee="user@example.com",
            priority_id="high",
        )


class TestCommandBatch:
    """Tests for CommandBatch."""

    def test_execute_all_success(self):
        cmd1 = Mock()
        cmd1.execute.return_value = CommandResult.ok("result1")

        cmd2 = Mock()
        cmd2.execute.return_value = CommandResult.ok("result2")

        batch = CommandBatch()
        batch.add(cmd1).add(cmd2)

        results = batch.execute_all()

        assert len(results) == 2
        assert batch.all_succeeded
        assert batch.executed_count == 2

    def test_execute_stop_on_error(self):
        cmd1 = Mock()
        cmd1.execute.return_value = CommandResult.fail("error")

        cmd2 = Mock()
        cmd2.execute.return_value = CommandResult.ok()

        batch = CommandBatch(stop_on_error=True)
        batch.add(cmd1).add(cmd2)

        results = batch.execute_all()

        # Should stop after first failure
        assert len(results) == 1
        assert batch.failed_count == 1
        cmd2.execute.assert_not_called()

    def test_execute_continue_on_error(self):
        cmd1 = Mock()
        cmd1.execute.return_value = CommandResult.fail("error")

        cmd2 = Mock()
        cmd2.execute.return_value = CommandResult.ok()

        batch = CommandBatch(stop_on_error=False)
        batch.add(cmd1).add(cmd2)

        results = batch.execute_all()

        # Should continue despite failure
        assert len(results) == 2
        assert batch.failed_count == 1
        assert batch.executed_count == 1


# =============================================================================
# Graceful Degradation Tests
# =============================================================================


class TestSyncResultGracefulDegradation:
    """Tests for SyncResult graceful degradation features."""

    def test_failed_operation_str_format(self):
        """Test FailedOperation string representation."""
        from spectryn.application.sync.orchestrator import FailedOperation

        failed = FailedOperation(
            operation="update_description",
            issue_key="PROJ-123",
            error="Connection timeout",
            story_id="US-001",
        )

        assert "[update_description]" in str(failed)
        assert "PROJ-123" in str(failed)
        assert "US-001" in str(failed)
        assert "Connection timeout" in str(failed)

    def test_failed_operation_without_story_id(self):
        """Test FailedOperation without story ID."""
        from spectryn.application.sync.orchestrator import FailedOperation

        failed = FailedOperation(
            operation="transition_status",
            issue_key="PROJ-456",
            error="Invalid transition",
        )

        result = str(failed)
        assert "story" not in result.lower()
        assert "PROJ-456" in result

    def test_add_failed_operation(self):
        """Test adding failed operations to SyncResult."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult()
        assert result.success is True

        result.add_failed_operation(
            operation="create_subtask",
            issue_key="PROJ-789",
            error="Permission denied",
            story_id="US-002",
        )

        assert result.success is False
        assert len(result.failed_operations) == 1
        assert len(result.errors) == 1
        assert result.failed_operations[0].issue_key == "PROJ-789"

    def test_partial_success_detection(self):
        """Test partial success when some ops succeed and some fail."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult()
        result.stories_updated = 5
        result.subtasks_created = 3

        # No failures - not partial success
        assert result.partial_success is False
        assert result.success is True

        # Add a failure
        result.add_failed_operation(
            operation="update_description",
            issue_key="PROJ-001",
            error="API error",
        )

        # Now it's partial success
        assert result.partial_success is True
        assert result.success is False

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult()
        result.stories_updated = 8
        result.subtasks_created = 2
        # Total successful = 10

        # Add 2 failures
        result.add_failed_operation("op1", "PROJ-1", "err")
        result.add_failed_operation("op2", "PROJ-2", "err")

        # 10 success + 2 failures = 12 total, 10/12 = 0.833...
        assert result.total_operations == 12
        assert 0.83 < result.success_rate < 0.84

    def test_success_rate_with_no_operations(self):
        """Test success rate when no operations performed."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult()
        assert result.success_rate == 1.0

    def test_summary_generation(self):
        """Test summary generation."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult()
        result.stories_matched = 10
        result.stories_updated = 8
        result.subtasks_created = 5
        result.add_failed_operation("create_subtask", "PROJ-1", "Error 1")
        result.add_failed_operation("update_description", "PROJ-2", "Error 2")
        result.add_warning("Story US-999 not matched")

        summary = result.summary()

        assert "completed with errors" in summary.lower()
        assert "2 failures" in summary
        assert "Stories matched: 10" in summary
        assert "Descriptions updated: 8" in summary
        assert "Subtasks created: 5" in summary
        assert "Failed operations:" in summary
        assert "Warnings:" in summary

    def test_summary_dry_run(self):
        """Test summary shows dry run mode."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult(dry_run=True)
        summary = result.summary()

        assert "DRY RUN" in summary

    def test_summary_success(self):
        """Test summary for successful sync."""
        from spectryn.application.sync.orchestrator import SyncResult

        result = SyncResult(dry_run=False)
        result.stories_updated = 5
        summary = result.summary()

        assert "✓" in summary or "successfully" in summary.lower()


class TestSyncOrchestratorGracefulDegradation:
    """Tests for SyncOrchestrator graceful degradation."""

    def test_sync_continues_after_description_failure(
        self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config
    ):
        """Test that sync continues even if one description update fails."""
        from spectryn.application.sync.orchestrator import SyncOrchestrator
        from spectryn.core.ports.issue_tracker import IssueTrackerError

        # Make one description update fail
        call_count = [0]
        original_update = mock_tracker_with_children.update_issue_description

        def update_with_failure(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise IssueTrackerError("First update failed")
            return original_update(*args, **kwargs)

        mock_tracker_with_children.update_issue_description = Mock(side_effect=update_with_failure)

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.sync("/path/to/doc.md", "TEST-1")

        # Should have partial success - some updates succeeded
        assert result.stories_updated >= 1 or len(result.failed_operations) >= 1
        # Should have recorded the failure
        assert len(result.failed_operations) >= 1 or len(result.errors) >= 1

    def test_sync_result_has_failed_operations_list(
        self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config
    ):
        """Test that failed operations are tracked in a list."""
        from spectryn.application.sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.sync("/path/to/doc.md", "TEST-1")

        # failed_operations should be a list (even if empty)
        assert isinstance(result.failed_operations, list)
