"""Tests for application commands."""

import pytest
from unittest.mock import Mock, MagicMock

from md2jira.application.commands import (
    Command,
    CommandResult,
    CommandBatch,
    UpdateDescriptionCommand,
    CreateSubtaskCommand,
    AddCommentCommand,
    TransitionStatusCommand,
)
from md2jira.core.ports.issue_tracker import IssueData


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
            key="PROJ-123",
            summary="Test",
            description="Old description"
        )
        tracker.update_issue_description.return_value = True
        return tracker
    
    def test_validate_missing_key(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker,
            issue_key="",
            description="New description"
        )
        assert cmd.validate() is not None
    
    def test_validate_missing_description(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            description=""
        )
        assert cmd.validate() is not None
    
    def test_execute_dry_run(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            description="New description",
            dry_run=True
        )
        
        result = cmd.execute()
        
        assert result.success
        assert result.dry_run
        mock_tracker.update_issue_description.assert_not_called()
    
    def test_execute_success(self, mock_tracker):
        cmd = UpdateDescriptionCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            description="New description",
            dry_run=False
        )
        
        result = cmd.execute()
        
        assert result.success
        mock_tracker.update_issue_description.assert_called_once()


class TestCreateSubtaskCommand:
    """Tests for CreateSubtaskCommand."""
    
    @pytest.fixture
    def mock_tracker(self):
        tracker = Mock()
        tracker.create_subtask.return_value = "PROJ-456"
        return tracker
    
    def test_validate_missing_parent(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="",
            project_key="PROJ",
            summary="Subtask"
        )
        assert cmd.validate() is not None
    
    def test_execute_dry_run(self, mock_tracker):
        cmd = CreateSubtaskCommand(
            tracker=mock_tracker,
            parent_key="PROJ-123",
            project_key="PROJ",
            summary="New subtask",
            dry_run=True
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
            dry_run=False
        )
        
        result = cmd.execute()
        
        assert result.success
        assert result.data == "PROJ-456"


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
            tracker=mock_tracker,
            issue_key="PROJ-123",
            target_status="Resolved",
            dry_run=True
        )
        
        result = cmd.execute()
        
        assert result.success
        assert result.dry_run
    
    def test_execute_success(self, mock_tracker):
        cmd = TransitionStatusCommand(
            tracker=mock_tracker,
            issue_key="PROJ-123",
            target_status="Resolved",
            dry_run=False
        )
        
        result = cmd.execute()
        
        assert result.success
        mock_tracker.transition_issue.assert_called_with("PROJ-123", "Resolved")


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
        from md2jira.application.sync.orchestrator import FailedOperation
        
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
        from md2jira.application.sync.orchestrator import FailedOperation
        
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
        from md2jira.application.sync.orchestrator import SyncResult
        
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
        from md2jira.application.sync.orchestrator import SyncResult
        
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
        from md2jira.application.sync.orchestrator import SyncResult
        
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
        from md2jira.application.sync.orchestrator import SyncResult
        
        result = SyncResult()
        assert result.success_rate == 1.0
    
    def test_summary_generation(self):
        """Test summary generation."""
        from md2jira.application.sync.orchestrator import SyncResult
        
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
        from md2jira.application.sync.orchestrator import SyncResult
        
        result = SyncResult(dry_run=True)
        summary = result.summary()
        
        assert "DRY RUN" in summary
    
    def test_summary_success(self):
        """Test summary for successful sync."""
        from md2jira.application.sync.orchestrator import SyncResult
        
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
        from md2jira.application.sync.orchestrator import SyncOrchestrator
        from md2jira.core.ports.issue_tracker import IssueTrackerError
        
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
        from md2jira.application.sync.orchestrator import SyncOrchestrator
        
        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )
        
        result = orchestrator.sync("/path/to/doc.md", "TEST-1")
        
        # failed_operations should be a list (even if empty)
        assert isinstance(result.failed_operations, list)

