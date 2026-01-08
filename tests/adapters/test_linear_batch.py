"""
Comprehensive tests for Linear batch client.

Tests cover:
- BatchOperation and BatchResult data classes
- LinearBatchClient initialization
- Bulk operations (create, update, transition, comments)
- Dry-run behavior
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.linear.batch import (
    BatchOperation,
    BatchResult,
    LinearBatchClient,
)


class TestBatchOperation:
    """Tests for BatchOperation dataclass."""

    def test_success_str(self):
        """Test string representation for successful operation."""
        op = BatchOperation(index=0, success=True, key="ENG-123")
        assert "[0] ENG-123: OK" in str(op)

    def test_failure_str(self):
        """Test string representation for failed operation."""
        op = BatchOperation(index=1, success=False, key="ENG-456", error="API Error")
        assert "[1] ENG-456: FAILED" in str(op)
        assert "API Error" in str(op)

    def test_failure_no_key_str(self):
        """Test string representation for failed operation without key."""
        op = BatchOperation(index=2, success=False, error="Connection failed")
        assert "N/A" in str(op)
        assert "Connection failed" in str(op)


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_empty_result(self):
        """Test empty batch result."""
        result = BatchResult()
        assert result.success is True
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.created_keys == []
        assert result.failed_indices == []

    def test_add_success(self):
        """Test adding successful operation."""
        result = BatchResult()
        result.add_success(0, "ENG-123", {"id": "issue-123"})

        assert result.succeeded == 1
        assert result.total == 1
        assert result.success is True
        assert len(result.operations) == 1
        assert result.operations[0].key == "ENG-123"

    def test_add_failure(self):
        """Test adding failed operation."""
        result = BatchResult()
        result.add_failure(0, "API Error")

        assert result.failed == 1
        assert result.total == 1
        assert result.success is False
        assert len(result.errors) == 1
        assert "API Error" in result.errors[0]

    def test_created_keys(self):
        """Test getting created keys."""
        result = BatchResult()
        result.add_success(0, "ENG-1")
        result.add_success(1, "ENG-2")
        result.add_failure(2, "Error")

        assert result.created_keys == ["ENG-1", "ENG-2"]

    def test_failed_indices(self):
        """Test getting failed indices."""
        result = BatchResult()
        result.add_success(0, "ENG-1")
        result.add_failure(1, "Error 1")
        result.add_failure(2, "Error 2")

        assert result.failed_indices == [1, 2]


class TestLinearBatchClientInit:
    """Tests for LinearBatchClient initialization."""

    def test_init(self):
        """Test initialization with client."""
        mock_client = MagicMock()
        mock_client.team_id = "team-123"

        batch_client = LinearBatchClient(client=mock_client)

        assert batch_client.client == mock_client

    def test_init_with_max_workers(self):
        """Test initialization with custom max_workers."""
        mock_client = MagicMock()
        mock_client.team_id = "team-123"

        batch_client = LinearBatchClient(client=mock_client, max_workers=5)

        assert batch_client.max_workers == 5


class TestLinearBatchClientOperations:
    """Tests for LinearBatchClient operations."""

    @pytest.fixture
    def mock_client(self):
        """Create mock LinearApiClient."""
        client = MagicMock()
        client.team_id = "team-123"
        client.dry_run = False
        return client

    @pytest.fixture
    def batch_client(self, mock_client):
        """Create LinearBatchClient with mocked client."""
        return LinearBatchClient(client=mock_client)

    def test_bulk_create_subtasks_dry_run(self, mock_client):
        """Test bulk create subtasks in dry-run mode."""
        mock_client.dry_run = True
        batch_client = LinearBatchClient(client=mock_client)

        subtasks = [
            {"parent_key": "ENG-1", "summary": "Subtask 1"},
            {"parent_key": "ENG-2", "summary": "Subtask 2"},
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_create_subtasks_live(self, batch_client, mock_client):
        """Test bulk create subtasks live."""
        mock_client.create_issue.return_value = {"id": "issue-123", "identifier": "ENG-999"}

        subtasks = [
            {"parent_key": "ENG-1", "summary": "Subtask 1"},
        ]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.success is True

    def test_bulk_update_issues_dry_run(self, mock_client):
        """Test bulk update issues in dry-run mode."""
        mock_client.dry_run = True
        batch_client = LinearBatchClient(client=mock_client)

        updates = [
            {"key": "ENG-1", "description": "New desc 1"},
            {"key": "ENG-2", "description": "New desc 2"},
        ]
        result = batch_client.bulk_update_issues(updates)

        assert result.success is True
        assert result.total == 2

    def test_bulk_transition_issues_dry_run(self, mock_client):
        """Test bulk transition issues in dry-run mode."""
        mock_client.dry_run = True
        batch_client = LinearBatchClient(client=mock_client)

        transitions = [
            ("ENG-1", "Done"),
            ("ENG-2", "In Progress"),
        ]
        result = batch_client.bulk_transition_issues(transitions)

        assert result.success is True
        assert result.total == 2

    def test_bulk_add_comments_dry_run(self, mock_client):
        """Test bulk add comments in dry-run mode."""
        mock_client.dry_run = True
        batch_client = LinearBatchClient(client=mock_client)

        comments = [
            ("ENG-1", "Comment 1"),
            ("ENG-2", "Comment 2"),
        ]
        result = batch_client.bulk_add_comments(comments)

        assert result.success is True
        assert result.total == 2

    def test_bulk_get_issues(self, batch_client, mock_client):
        """Test bulk get issues."""
        mock_client.get_issue.return_value = {
            "id": "issue-123",
            "identifier": "ENG-1",
            "title": "Test",
        }

        keys = ["ENG-1", "ENG-2"]
        result = batch_client.bulk_get_issues(keys)

        # Returns BatchResult, not a list
        assert result.total == 2

    def test_bulk_operation_with_error(self, batch_client, mock_client):
        """Test handling errors in bulk operations."""
        from spectryn.core.ports.issue_tracker import IssueTrackerError

        mock_client.create_issue.side_effect = IssueTrackerError("API Error")

        subtasks = [{"parent_key": "ENG-1", "summary": "Subtask 1"}]
        result = batch_client.bulk_create_subtasks(subtasks)

        assert result.failed >= 1


class TestLinearBatchClientBatchResult:
    """Tests for LinearBatchClient batch result usage."""

    def test_batch_result_summary(self):
        """Test batch result summary generation."""
        result = BatchResult()
        result.add_success(0, "ENG-1")
        result.add_success(1, "ENG-2")
        result.add_failure(2, "Error")

        summary = result.summary()
        assert "2/3 succeeded" in summary
        assert "1 failed" in summary

    def test_batch_result_complete_workflow(self):
        """Test complete batch result workflow."""
        result = BatchResult()

        # Simulate a batch operation
        for i in range(10):
            if i % 3 == 0:
                result.add_failure(i, f"Error {i}")
            else:
                result.add_success(i, f"ENG-{i}")

        # Verify final state
        assert result.total == 10
        assert result.succeeded == 6  # indices 1,2,4,5,7,8
        assert result.failed == 4  # indices 0,3,6,9
        assert result.success is False  # At least one failure
        assert len(result.created_keys) == 6
        assert len(result.failed_indices) == 4
