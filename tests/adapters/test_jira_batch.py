"""
Tests for Jira batch operations.

Tests the JiraBatchClient for bulk create, update, transition, and comment operations.
"""

from unittest.mock import MagicMock

import pytest

from spectryn.adapters.jira.batch import (
    BatchOperation,
    BatchResult,
    JiraBatchClient,
)
from spectryn.adapters.jira.client import JiraApiClient
from spectryn.core.ports.issue_tracker import IssueTrackerError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_client():
    """Create a mock JiraApiClient."""
    client = MagicMock(spec=JiraApiClient)
    client.dry_run = False
    client.get_current_user_id.return_value = "user-123"
    return client


@pytest.fixture
def dry_run_client():
    """Create a mock JiraApiClient in dry-run mode."""
    client = MagicMock(spec=JiraApiClient)
    client.dry_run = True
    return client


@pytest.fixture
def batch_client(mock_client):
    """Create a JiraBatchClient with mock client."""
    return JiraBatchClient(mock_client, max_workers=3)


@pytest.fixture
def dry_run_batch_client(dry_run_client):
    """Create a JiraBatchClient in dry-run mode."""
    return JiraBatchClient(dry_run_client)


# =============================================================================
# BatchOperation Tests
# =============================================================================


class TestBatchOperation:
    """Tests for BatchOperation dataclass."""

    def test_success_str(self):
        """Test string representation for success."""
        op = BatchOperation(index=0, success=True, key="PROJ-123")
        assert "[0] PROJ-123: OK" in str(op)

    def test_failure_str(self):
        """Test string representation for failure."""
        op = BatchOperation(index=1, success=False, key="PROJ-124", error="Not found")
        assert "[1] PROJ-124: FAILED" in str(op)
        assert "Not found" in str(op)

    def test_failure_no_key_str(self):
        """Test string representation for failure without key."""
        op = BatchOperation(index=2, success=False, error="API error")
        assert "N/A" in str(op)


# =============================================================================
# BatchResult Tests
# =============================================================================


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_empty_result(self):
        """Test empty result."""
        result = BatchResult()
        assert result.success is True
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0

    def test_add_success(self):
        """Test adding successful operations."""
        result = BatchResult()
        result.add_success(0, "PROJ-100")
        result.add_success(1, "PROJ-101", {"data": "test"})

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert result.success is True
        assert result.created_keys == ["PROJ-100", "PROJ-101"]

    def test_add_failure(self):
        """Test adding failed operations."""
        result = BatchResult()
        result.add_success(0, "PROJ-100")
        result.add_failure(1, "Error occurred", "PROJ-101")

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.success is False
        assert result.failed_indices == [1]
        assert "Error occurred" in result.errors

    def test_summary(self):
        """Test summary string."""
        result = BatchResult()
        result.add_success(0, "PROJ-100")
        result.add_failure(1, "Error", "PROJ-101")

        summary = result.summary()
        assert "1/2 succeeded" in summary
        assert "1 failed" in summary


# =============================================================================
# Bulk Create Tests
# =============================================================================


class TestBulkCreate:
    """Tests for bulk issue creation."""

    def test_bulk_create_empty(self, batch_client):
        """Test bulk create with empty list."""
        result = batch_client.bulk_create_issues([])

        assert result.success is True
        assert result.total == 0

    def test_bulk_create_dry_run(self, dry_run_batch_client):
        """Test bulk create in dry-run mode."""
        issues = [
            {"fields": {"summary": "Task 1"}},
            {"fields": {"summary": "Task 2"}},
        ]

        result = dry_run_batch_client.bulk_create_issues(issues)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2
        assert all(key.startswith("DRY-RUN") for key in result.created_keys)

    def test_bulk_create_success(self, batch_client, mock_client):
        """Test successful bulk create."""
        mock_client.post.return_value = {
            "issues": [
                {"id": "10001", "key": "PROJ-101"},
                {"id": "10002", "key": "PROJ-102"},
            ],
            "errors": [],
        }

        issues = [
            {"fields": {"summary": "Task 1"}},
            {"fields": {"summary": "Task 2"}},
        ]

        result = batch_client.bulk_create_issues(issues)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2
        assert result.created_keys == ["PROJ-101", "PROJ-102"]

        mock_client.post.assert_called_once_with("issue/bulk", json={"issueUpdates": issues})

    def test_bulk_create_partial_failure(self, batch_client, mock_client):
        """Test bulk create with some failures."""
        mock_client.post.return_value = {
            "issues": [
                {"id": "10001", "key": "PROJ-101"},
                {},  # Failed
            ],
            "errors": [None, {"status": 400, "message": "Invalid field"}],
        }

        issues = [
            {"fields": {"summary": "Task 1"}},
            {"fields": {"summary": "Task 2"}},
        ]

        result = batch_client.bulk_create_issues(issues)

        assert result.success is False
        assert result.succeeded == 1
        assert result.failed == 1

    def test_bulk_create_api_error(self, batch_client, mock_client):
        """Test bulk create with API error."""
        mock_client.post.side_effect = IssueTrackerError("API unavailable")

        issues = [
            {"fields": {"summary": "Task 1"}},
            {"fields": {"summary": "Task 2"}},
        ]

        result = batch_client.bulk_create_issues(issues)

        assert result.success is False
        assert result.failed == 2
        assert all("API unavailable" in e for e in result.errors)

    def test_bulk_create_subtasks(self, batch_client, mock_client):
        """Test bulk create subtasks convenience method."""
        mock_client.post.return_value = {
            "issues": [
                {"id": "10001", "key": "PROJ-101"},
            ],
            "errors": [],
        }

        subtasks = [
            {"summary": "Subtask 1", "description": {"type": "doc"}, "story_points": 3},
        ]

        result = batch_client.bulk_create_subtasks(
            parent_key="PROJ-100",
            project_key="PROJ",
            subtasks=subtasks,
        )

        assert result.success is True

        # Verify the API call
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "issue/bulk"

        issue_data = call_args[1]["json"]["issueUpdates"][0]
        assert issue_data["fields"]["parent"]["key"] == "PROJ-100"
        assert issue_data["fields"]["project"]["key"] == "PROJ"
        assert issue_data["fields"]["summary"] == "Subtask 1"


# =============================================================================
# Bulk Update Tests
# =============================================================================


class TestBulkUpdate:
    """Tests for bulk issue updates."""

    def test_bulk_update_empty(self, batch_client):
        """Test bulk update with empty list."""
        result = batch_client.bulk_update_issues([])

        assert result.success is True
        assert result.total == 0

    def test_bulk_update_dry_run(self, dry_run_batch_client):
        """Test bulk update in dry-run mode."""
        updates = [
            {"key": "PROJ-101", "fields": {"description": {"type": "doc"}}},
            {"key": "PROJ-102", "fields": {"description": {"type": "doc"}}},
        ]

        result = dry_run_batch_client.bulk_update_issues(updates)

        assert result.success is True
        assert result.total == 2

    def test_bulk_update_success(self, batch_client, mock_client):
        """Test successful bulk update."""
        mock_client.put.return_value = {}

        updates = [
            {"key": "PROJ-101", "fields": {"description": {"type": "doc"}}},
            {"key": "PROJ-102", "fields": {"description": {"type": "doc"}}},
        ]

        result = batch_client.bulk_update_issues(updates)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2
        assert mock_client.put.call_count == 2

    def test_bulk_update_partial_failure(self, batch_client, mock_client):
        """Test bulk update with some failures."""

        def put_side_effect(endpoint, json=None):
            if "PROJ-102" in endpoint:
                raise IssueTrackerError("Permission denied")
            return {}

        mock_client.put.side_effect = put_side_effect

        updates = [
            {"key": "PROJ-101", "fields": {"description": {"type": "doc"}}},
            {"key": "PROJ-102", "fields": {"description": {"type": "doc"}}},
        ]

        result = batch_client.bulk_update_issues(updates)

        assert result.success is False
        assert result.succeeded == 1
        assert result.failed == 1

    def test_bulk_update_descriptions(self, batch_client, mock_client):
        """Test bulk update descriptions convenience method."""
        mock_client.put.return_value = {}

        updates = [
            ("PROJ-101", {"type": "doc", "content": []}),
            ("PROJ-102", {"type": "doc", "content": []}),
        ]

        result = batch_client.bulk_update_descriptions(updates)

        assert result.success is True
        assert result.total == 2


# =============================================================================
# Bulk Transition Tests
# =============================================================================


class TestBulkTransition:
    """Tests for bulk issue transitions."""

    def test_bulk_transition_empty(self, batch_client):
        """Test bulk transition with empty list."""
        result = batch_client.bulk_transition_issues([])

        assert result.success is True
        assert result.total == 0

    def test_bulk_transition_dry_run(self, dry_run_batch_client):
        """Test bulk transition in dry-run mode."""
        transitions = [
            ("PROJ-101", "Done"),
            ("PROJ-102", "In Progress"),
        ]

        result = dry_run_batch_client.bulk_transition_issues(transitions)

        assert result.success is True
        assert result.total == 2

    def test_bulk_transition_success(self, batch_client, mock_client):
        """Test successful bulk transitions."""
        mock_client.get.return_value = {
            "transitions": [
                {"id": "5", "name": "Done", "to": {"name": "Done"}},
                {"id": "4", "name": "In Progress", "to": {"name": "In Progress"}},
            ]
        }
        mock_client.post.return_value = {}

        transitions = [
            ("PROJ-101", "Done"),
            ("PROJ-102", "Done"),
        ]

        result = batch_client.bulk_transition_issues(transitions)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_transition_no_available(self, batch_client, mock_client):
        """Test bulk transition with unavailable transition."""
        mock_client.get.return_value = {
            "transitions": [
                {"id": "4", "name": "In Progress", "to": {"name": "In Progress"}},
            ]
        }

        transitions = [
            ("PROJ-101", "Done"),
        ]

        result = batch_client.bulk_transition_issues(transitions)

        assert result.success is False
        assert result.failed == 1
        assert "No transition" in result.errors[0]


# =============================================================================
# Bulk Comments Tests
# =============================================================================


class TestBulkComments:
    """Tests for bulk comment operations."""

    def test_bulk_add_comments_empty(self, batch_client):
        """Test bulk add comments with empty list."""
        result = batch_client.bulk_add_comments([])

        assert result.success is True
        assert result.total == 0

    def test_bulk_add_comments_dry_run(self, dry_run_batch_client):
        """Test bulk add comments in dry-run mode."""
        comments = [
            ("PROJ-101", {"type": "doc"}),
            ("PROJ-102", {"type": "doc"}),
        ]

        result = dry_run_batch_client.bulk_add_comments(comments)

        assert result.success is True
        assert result.total == 2

    def test_bulk_add_comments_success(self, batch_client, mock_client):
        """Test successful bulk add comments."""
        mock_client.post.return_value = {}

        comments = [
            ("PROJ-101", {"type": "doc"}),
            ("PROJ-102", {"type": "doc"}),
        ]

        result = batch_client.bulk_add_comments(comments)

        assert result.success is True
        assert result.total == 2
        assert result.succeeded == 2


# =============================================================================
# Bulk Fetch Tests
# =============================================================================


class TestBulkFetch:
    """Tests for bulk issue fetching."""

    def test_bulk_get_issues_empty(self, batch_client):
        """Test bulk get with empty list."""
        result = batch_client.bulk_get_issues([])

        assert result.success is True
        assert result.total == 0

    def test_bulk_get_issues_success(self, batch_client, mock_client):
        """Test successful bulk fetch."""
        mock_client.get.return_value = {
            "key": "PROJ-101",
            "fields": {"summary": "Test Issue"},
        }

        result = batch_client.bulk_get_issues(["PROJ-101", "PROJ-102"])

        assert result.success is True
        assert result.total == 2
        assert mock_client.get.call_count == 2

    def test_bulk_get_issues_partial_failure(self, batch_client, mock_client):
        """Test bulk fetch with some failures."""

        def get_side_effect(endpoint, params=None):
            if "PROJ-102" in endpoint:
                raise IssueTrackerError("Not found")
            return {"key": "PROJ-101", "fields": {}}

        mock_client.get.side_effect = get_side_effect

        result = batch_client.bulk_get_issues(["PROJ-101", "PROJ-102"])

        assert result.success is False
        assert result.succeeded == 1
        assert result.failed == 1


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrency:
    """Tests for concurrent execution."""

    def test_max_workers_limit(self, mock_client):
        """Test that max_workers is limited."""
        batch_client = JiraBatchClient(mock_client, max_workers=100)

        # Should be capped at MAX_WORKERS
        assert batch_client.max_workers == JiraBatchClient.MAX_WORKERS

    def test_operations_sorted_by_index(self, batch_client, mock_client):
        """Test that operations are sorted by index in results."""
        mock_client.put.return_value = {}

        updates = [{"key": f"PROJ-{i}", "fields": {}} for i in range(10)]

        result = batch_client.bulk_update_issues(updates)

        # Operations should be sorted by index
        indices = [op.index for op in result.operations]
        assert indices == sorted(indices)
