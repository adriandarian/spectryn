"""Tests for transactional sync module."""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.sync.transaction import (
    OperationType,
    RollbackResult,
    TransactionalSync,
    TransactionManager,
    TransactionResult,
    TransactionState,
    create_transactional_sync,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tracker():
    """Create a mock issue tracker."""
    tracker = MagicMock()
    tracker.name = "MockTracker"

    # Mock issue data
    mock_issue = MagicMock()
    mock_issue.key = "PROJ-123"
    mock_issue.summary = "Test Issue"
    mock_issue.description = "Original description"
    mock_issue.status = "Open"
    mock_issue.story_points = 5

    tracker.get_issue.return_value = mock_issue
    tracker.update_description.return_value = True
    tracker.update_story_points.return_value = True
    tracker.update_summary.return_value = True
    tracker.transition_issue.return_value = True

    return tracker


# =============================================================================
# TransactionState Tests
# =============================================================================


class TestTransactionState:
    """Tests for TransactionState enum."""

    def test_states_exist(self):
        """Test all expected states exist."""
        assert TransactionState.PENDING.value == "pending"
        assert TransactionState.ACTIVE.value == "active"
        assert TransactionState.COMMITTED.value == "committed"
        assert TransactionState.ROLLED_BACK.value == "rolled_back"
        assert TransactionState.FAILED.value == "failed"


# =============================================================================
# OperationType Tests
# =============================================================================


class TestOperationType:
    """Tests for OperationType enum."""

    def test_operation_types_exist(self):
        """Test all expected operation types exist."""
        assert OperationType.UPDATE_DESCRIPTION.value == "update_description"
        assert OperationType.UPDATE_STORY_POINTS.value == "update_story_points"
        assert OperationType.UPDATE_STATUS.value == "update_status"
        assert OperationType.CREATE_ISSUE.value == "create_issue"
        assert OperationType.ADD_COMMENT.value == "add_comment"


# =============================================================================
# TransactionManager Tests
# =============================================================================


class TestTransactionManager:
    """Tests for TransactionManager class."""

    def test_init(self, mock_tracker):
        """Test initialization."""
        tm = TransactionManager(mock_tracker)

        assert tm.tracker == mock_tracker
        assert tm.state == TransactionState.PENDING
        assert not tm.is_active

    def test_begin_transaction(self, mock_tracker):
        """Test starting a transaction."""
        tm = TransactionManager(mock_tracker)

        txn_id = tm.begin(epic_key="PROJ-123")

        assert txn_id is not None
        assert tm.is_active
        assert tm.state == TransactionState.ACTIVE
        assert "txn_" in tm.transaction_id

    def test_begin_when_active_raises(self, mock_tracker):
        """Test that beginning when active raises error."""
        tm = TransactionManager(mock_tracker)
        tm.begin()

        with pytest.raises(RuntimeError, match="already active"):
            tm.begin()

    def test_record_operation(self, mock_tracker):
        """Test recording an operation."""
        tm = TransactionManager(mock_tracker)
        tm.begin()

        record = tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
            field_name="description",
            original_value="old",
            new_value="new",
        )

        assert record.operation_type == OperationType.UPDATE_DESCRIPTION
        assert record.issue_key == "PROJ-123"
        assert record.original_value == "old"
        assert record.new_value == "new"
        assert record.success is True

    def test_record_operation_without_transaction_raises(self, mock_tracker):
        """Test that recording without active transaction raises error."""
        tm = TransactionManager(mock_tracker)

        with pytest.raises(RuntimeError, match="No active transaction"):
            tm.record_operation(
                operation_type=OperationType.UPDATE_DESCRIPTION,
                issue_key="PROJ-123",
            )

    def test_commit_success(self, mock_tracker):
        """Test successful commit."""
        tm = TransactionManager(mock_tracker)
        tm.begin()
        tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
            original_value="old",
            new_value="new",
        )

        result = tm.commit()

        assert result.state == TransactionState.COMMITTED
        assert result.success is True
        assert result.operations_executed == 1
        assert result.operations_succeeded == 1

    def test_commit_with_failures_triggers_rollback(self, mock_tracker):
        """Test that commit with failures triggers rollback in fail-fast mode."""
        tm = TransactionManager(mock_tracker, fail_fast=True)
        tm.begin()

        record = tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
            original_value="old",
            new_value="new",
        )
        tm.mark_operation_failed(record, "Test failure")

        result = tm.commit()

        assert result.state == TransactionState.ROLLED_BACK
        assert result.rollback_performed is True
        assert result.operations_failed == 1

    def test_rollback(self, mock_tracker):
        """Test rollback."""
        tm = TransactionManager(mock_tracker)
        tm.begin()
        tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
            original_value="old",
            new_value="new",
        )

        result = tm.rollback()

        assert result.success is True
        assert result.operations_rolled_back == 1
        assert tm.state == TransactionState.ROLLED_BACK
        mock_tracker.update_description.assert_called_with("PROJ-123", "old")

    def test_rollback_story_points(self, mock_tracker):
        """Test rollback of story points update."""
        tm = TransactionManager(mock_tracker)
        tm.begin()
        tm.record_operation(
            operation_type=OperationType.UPDATE_STORY_POINTS,
            issue_key="PROJ-123",
            original_value=3,
            new_value=5,
        )

        result = tm.rollback()

        assert result.operations_rolled_back == 1
        mock_tracker.update_story_points.assert_called_with("PROJ-123", 3)

    def test_rollback_skips_non_rollbackable(self, mock_tracker):
        """Test that non-rollbackable operations are skipped."""
        tm = TransactionManager(mock_tracker)
        tm.begin()
        tm.record_operation(
            operation_type=OperationType.ADD_COMMENT,
            issue_key="PROJ-123",
            new_value="comment",
            can_rollback=False,
        )

        result = tm.rollback()

        assert result.operations_skipped == 1
        assert result.operations_rolled_back == 0

    def test_get_operations(self, mock_tracker):
        """Test getting recorded operations."""
        tm = TransactionManager(mock_tracker)
        tm.begin()
        tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
        )
        tm.record_operation(
            operation_type=OperationType.UPDATE_STORY_POINTS,
            issue_key="PROJ-124",
        )

        ops = tm.get_operations()

        assert len(ops) == 2


# =============================================================================
# RollbackResult Tests
# =============================================================================


class TestRollbackResult:
    """Tests for RollbackResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = RollbackResult()

        assert result.success is True
        assert result.operations_rolled_back == 0
        assert result.operations_failed == 0
        assert result.errors == []

    def test_summary_success(self):
        """Test summary for successful rollback."""
        result = RollbackResult(operations_rolled_back=5)

        assert "5 operations rolled back" in result.summary

    def test_summary_partial(self):
        """Test summary for partial rollback."""
        result = RollbackResult(
            success=False,
            operations_rolled_back=3,
            operations_failed=2,
            operations_skipped=1,
        )

        assert "3 rolled back" in result.summary
        assert "2 failed" in result.summary


# =============================================================================
# TransactionResult Tests
# =============================================================================


class TestTransactionResult:
    """Tests for TransactionResult dataclass."""

    def test_success_property(self):
        """Test success property."""
        committed = TransactionResult(
            transaction_id="test",
            state=TransactionState.COMMITTED,
        )
        assert committed.success is True

        rolled_back = TransactionResult(
            transaction_id="test",
            state=TransactionState.ROLLED_BACK,
        )
        assert rolled_back.success is False

    def test_summary(self):
        """Test summary generation."""
        result = TransactionResult(
            transaction_id="txn_123",
            state=TransactionState.COMMITTED,
            operations_executed=5,
            operations_succeeded=5,
        )

        summary = result.summary
        assert "txn_123" in summary
        assert "committed" in summary
        assert "5/5 succeeded" in summary


# =============================================================================
# TransactionalSync Tests
# =============================================================================


class TestTransactionalSync:
    """Tests for TransactionalSync context manager."""

    def test_context_manager_success(self, mock_tracker):
        """Test successful context manager usage."""
        with TransactionalSync(mock_tracker, epic_key="PROJ-123") as txn:
            assert txn.manager.is_active

        assert txn.result is not None
        assert txn.result.state == TransactionState.COMMITTED

    def test_context_manager_rollback_on_exception(self, mock_tracker):
        """Test rollback on exception."""
        txn = TransactionalSync(mock_tracker)

        try:
            with txn:
                txn.execute_update("PROJ-123", "description", "new value")
                raise ValueError("Test error")
        except ValueError:
            pass

        assert txn.result.rollback_performed is True
        assert txn.result.state == TransactionState.ROLLED_BACK

    def test_execute_update_description(self, mock_tracker):
        """Test executing a description update."""
        with TransactionalSync(mock_tracker) as txn:
            success = txn.execute_update("PROJ-123", "description", "new description")
            assert success is True

        mock_tracker.update_description.assert_called_with("PROJ-123", "new description")

    def test_execute_update_story_points(self, mock_tracker):
        """Test executing a story points update."""
        with TransactionalSync(mock_tracker) as txn:
            success = txn.execute_update("PROJ-123", "story_points", 8)
            assert success is True

        mock_tracker.update_story_points.assert_called_with("PROJ-123", 8)

    def test_dry_run_mode(self, mock_tracker):
        """Test dry run mode doesn't execute operations."""
        with TransactionalSync(mock_tracker, dry_run=True) as txn:
            txn.execute_update("PROJ-123", "description", "new")

        mock_tracker.update_description.assert_not_called()

    def test_fail_fast_disabled(self, mock_tracker):
        """Test behavior with fail_fast disabled."""
        mock_tracker.update_description.side_effect = Exception("API Error")

        with TransactionalSync(mock_tracker, fail_fast=False) as txn:
            success = txn.execute_update("PROJ-123", "description", "new")
            assert success is False
            # Should continue despite error


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateTransactionalSync:
    """Tests for create_transactional_sync factory function."""

    def test_creates_context_manager(self, mock_tracker):
        """Test that factory creates correct context manager."""
        txn = create_transactional_sync(
            tracker=mock_tracker,
            epic_key="PROJ-123",
            fail_fast=True,
            dry_run=False,
        )

        assert isinstance(txn, TransactionalSync)
        assert txn.epic_key == "PROJ-123"
        assert txn.fail_fast is True
        assert txn.dry_run is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestTransactionIntegration:
    """Integration tests for transactional sync."""

    def test_multiple_operations_commit(self, mock_tracker):
        """Test multiple operations commit together."""
        with TransactionalSync(mock_tracker) as txn:
            txn.execute_update("PROJ-123", "description", "new desc")
            txn.execute_update("PROJ-123", "story_points", 8)
            txn.execute_update("PROJ-124", "description", "other desc")

        assert txn.result.operations_succeeded == 3
        assert txn.result.state == TransactionState.COMMITTED

    def test_multiple_operations_rollback(self, mock_tracker):
        """Test multiple operations rollback on failure."""
        # Third update will fail
        call_count = [0]

        class APIError(Exception):
            pass

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 3:
                raise APIError("API Error")
            return True

        mock_tracker.update_description.side_effect = side_effect

        txn = TransactionalSync(mock_tracker)
        try:
            with txn:
                txn.execute_update("PROJ-123", "description", "new 1")
                txn.execute_update("PROJ-124", "description", "new 2")
                txn.execute_update("PROJ-125", "description", "new 3")  # Fails
        except APIError:
            pass

        # First two operations should be rolled back
        assert txn.result.rollback_performed is True

    def test_transaction_preserves_original_values(self, mock_tracker):
        """Test that transaction preserves original values for rollback."""
        tm = TransactionManager(mock_tracker)
        tm.begin()

        # Record with original value
        tm.record_operation(
            operation_type=OperationType.UPDATE_DESCRIPTION,
            issue_key="PROJ-123",
            original_value="Original description",
            new_value="Modified description",
        )

        # Rollback should restore original
        tm.rollback()

        mock_tracker.update_description.assert_called_with("PROJ-123", "Original description")
