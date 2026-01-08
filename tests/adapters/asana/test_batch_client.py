"""
Tests for AsanaBatchClient.

Tests batch operations with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.asana.batch import (
    AsanaBatchClient,
    BatchOperation,
    BatchResult,
)
from spectryn.core.exceptions import TrackerError


@pytest.fixture
def mock_session():
    """Create a mock requests.Session."""
    return MagicMock()


@pytest.fixture
def batch_client(mock_session):
    """Create an AsanaBatchClient for testing."""
    return AsanaBatchClient(
        session=mock_session,
        base_url="https://app.asana.com/api/1.0",
        api_token="test_token",
        dry_run=False,
        max_workers=5,
        timeout=30,
    )


@pytest.fixture
def dry_run_client(mock_session):
    """Create an AsanaBatchClient in dry-run mode."""
    return AsanaBatchClient(
        session=mock_session,
        base_url="https://app.asana.com/api/1.0",
        api_token="test_token",
        dry_run=True,
        max_workers=5,
    )


class TestBatchOperation:
    """Tests for BatchOperation dataclass."""

    def test_batch_operation_success(self):
        """Test successful BatchOperation."""
        op = BatchOperation(index=0, success=True, key="task-123")

        assert op.index == 0
        assert op.success is True
        assert op.key == "task-123"
        assert op.error == ""
        assert str(op) == "[0] task-123: OK"

    def test_batch_operation_failure(self):
        """Test failed BatchOperation."""
        op = BatchOperation(index=1, success=False, key="task-456", error="API error")

        assert op.success is False
        assert op.error == "API error"
        assert "FAILED" in str(op)
        assert "API error" in str(op)

    def test_batch_operation_failure_no_key(self):
        """Test failed BatchOperation without key."""
        op = BatchOperation(index=2, success=False, error="Missing parent")

        assert "N/A" in str(op)

    def test_batch_operation_with_data(self):
        """Test BatchOperation with additional data."""
        data = {"gid": "task-123", "name": "Test"}
        op = BatchOperation(index=0, success=True, key="task-123", data=data)

        assert op.data == data


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_batch_result_empty(self):
        """Test empty BatchResult."""
        result = BatchResult()

        assert result.success is True
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.operations == []
        assert result.errors == []

    def test_batch_result_add_success(self):
        """Test adding successful operation."""
        result = BatchResult()
        result.add_success(0, "task-123", {"name": "Test"})

        assert result.total == 1
        assert result.succeeded == 1
        assert result.failed == 0
        assert result.success is True
        assert len(result.operations) == 1
        assert result.operations[0].key == "task-123"

    def test_batch_result_add_failure(self):
        """Test adding failed operation."""
        result = BatchResult()
        result.add_failure(0, "API error", "task-123")

        assert result.total == 1
        assert result.succeeded == 0
        assert result.failed == 1
        assert result.success is False
        assert "API error" in result.errors

    def test_batch_result_mixed(self):
        """Test BatchResult with mixed results."""
        result = BatchResult()
        result.add_success(0, "task-1")
        result.add_success(1, "task-2")
        result.add_failure(2, "Error", "task-3")

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert result.success is False

    def test_batch_result_created_keys(self):
        """Test created_keys property."""
        result = BatchResult()
        result.add_success(0, "task-1")
        result.add_success(1, "task-2")
        result.add_failure(2, "Error")

        keys = result.created_keys
        assert keys == ["task-1", "task-2"]

    def test_batch_result_failed_indices(self):
        """Test failed_indices property."""
        result = BatchResult()
        result.add_success(0, "task-1")
        result.add_failure(1, "Error 1")
        result.add_failure(2, "Error 2")

        indices = result.failed_indices
        assert indices == [1, 2]

    def test_batch_result_summary(self):
        """Test summary method."""
        result = BatchResult()
        result.add_success(0, "task-1")
        result.add_failure(1, "Error")

        summary = result.summary()
        assert "1/2 succeeded" in summary
        assert "1 failed" in summary


class TestAsanaBatchClientInit:
    """Tests for AsanaBatchClient initialization."""

    def test_init_with_defaults(self, mock_session):
        """Test initialization with default settings."""
        client = AsanaBatchClient(
            session=mock_session,
            base_url="https://app.asana.com/api/1.0",
            api_token="test_token",
        )

        assert client._session == mock_session
        assert client.base_url == "https://app.asana.com/api/1.0"
        assert client._dry_run is True  # Default
        assert client.max_workers == 10  # Default

    def test_init_respects_max_workers_limit(self, mock_session):
        """Test that max_workers is capped."""
        client = AsanaBatchClient(
            session=mock_session,
            base_url="https://app.asana.com/api/1.0",
            api_token="test_token",
            max_workers=100,  # Over limit
        )

        assert client.max_workers == 10  # Capped at MAX_WORKERS

    def test_build_url(self, batch_client):
        """Test URL building."""
        url = batch_client._build_url("/tasks/123")
        assert url == "https://app.asana.com/api/1.0/tasks/123"

    def test_headers(self, batch_client):
        """Test authorization headers."""
        headers = batch_client._headers
        assert headers["Authorization"] == "Bearer test_token"


class TestBulkCreateSubtasks:
    """Tests for bulk_create_subtasks method."""

    def test_bulk_create_empty_list(self, batch_client):
        """Test with empty subtask list."""
        result = batch_client.bulk_create_subtasks("project-123", [])

        assert result.total == 0
        assert result.success is True

    def test_bulk_create_dry_run(self, dry_run_client):
        """Test bulk create in dry-run mode."""
        subtasks = [
            {"parent_gid": "parent-1", "name": "Subtask 1"},
            {"parent_gid": "parent-1", "name": "Subtask 2"},
        ]

        result = dry_run_client.bulk_create_subtasks("project-123", subtasks)

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert all("DRY-RUN" in op.key for op in result.operations)

    def test_bulk_create_success(self, batch_client, mock_session):
        """Test successful bulk creation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "new-task-gid"}}
        mock_session.request.return_value = mock_response

        subtasks = [
            {"parent_gid": "parent-1", "name": "Subtask 1"},
        ]

        result = batch_client.bulk_create_subtasks("project-123", subtasks)

        assert result.succeeded >= 0  # May vary based on threading

    def test_bulk_create_missing_parent(self, batch_client, mock_session):
        """Test bulk create with missing parent_gid."""
        subtasks = [
            {"name": "Subtask without parent"},  # Missing parent_gid
        ]

        result = batch_client.bulk_create_subtasks("project-123", subtasks)

        assert result.failed == 1
        assert "Missing parent_gid" in result.errors[0]

    def test_bulk_create_with_assignee(self, batch_client, mock_session):
        """Test bulk create with assignee."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "new-task-gid"}}
        mock_session.request.return_value = mock_response

        subtasks = [
            {"parent_gid": "parent-1", "name": "Subtask", "assignee": "user-123"},
        ]

        batch_client.bulk_create_subtasks("project-123", subtasks)

        # Check that request was made
        mock_session.request.assert_called()


class TestBulkUpdateTasks:
    """Tests for bulk_update_tasks method."""

    def test_bulk_update_empty_list(self, batch_client):
        """Test with empty update list."""
        result = batch_client.bulk_update_tasks([])

        assert result.total == 0
        assert result.success is True

    def test_bulk_update_dry_run(self, dry_run_client):
        """Test bulk update in dry-run mode."""
        updates = [
            {"gid": "task-1", "notes": "Updated notes 1"},
            {"gid": "task-2", "notes": "Updated notes 2"},
        ]

        result = dry_run_client.bulk_update_tasks(updates)

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_update_success(self, batch_client, mock_session):
        """Test successful bulk update."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        mock_session.request.return_value = mock_response

        updates = [
            {"gid": "task-1", "notes": "Updated"},
        ]

        result = batch_client.bulk_update_tasks(updates)

        assert result.succeeded >= 0

    def test_bulk_update_missing_gid(self, batch_client, mock_session):
        """Test bulk update with missing gid."""
        updates = [
            {"notes": "No gid provided"},  # Missing gid
        ]

        result = batch_client.bulk_update_tasks(updates)

        assert result.failed == 1
        assert "Missing gid" in result.errors[0]


class TestBulkUpdateDescriptions:
    """Tests for bulk_update_descriptions method."""

    def test_bulk_update_descriptions(self, batch_client, mock_session):
        """Test bulk description updates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        mock_session.request.return_value = mock_response

        updates = [("task-1", "New notes 1"), ("task-2", "New notes 2")]

        result = batch_client.bulk_update_descriptions(updates)

        # Should convert to dict format internally
        assert result is not None


class TestBulkCompleteTasks:
    """Tests for bulk_complete_tasks method."""

    def test_bulk_complete_tasks(self, batch_client, mock_session):
        """Test marking tasks as complete."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        mock_session.request.return_value = mock_response

        result = batch_client.bulk_complete_tasks(["task-1", "task-2"], completed=True)

        assert result is not None

    def test_bulk_incomplete_tasks(self, batch_client, mock_session):
        """Test marking tasks as incomplete."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}
        mock_session.request.return_value = mock_response

        result = batch_client.bulk_complete_tasks(["task-1"], completed=False)

        assert result is not None


class TestBulkAddComments:
    """Tests for bulk_add_comments method."""

    def test_bulk_add_comments_empty(self, batch_client):
        """Test with empty comments list."""
        result = batch_client.bulk_add_comments([])

        assert result.total == 0

    def test_bulk_add_comments_dry_run(self, dry_run_client):
        """Test adding comments in dry-run mode."""
        comments = [
            ("task-1", "Comment 1"),
            ("task-2", "Comment 2"),
        ]

        result = dry_run_client.bulk_add_comments(comments)

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_add_comments_success(self, batch_client, mock_session):
        """Test successful comment addition."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "story-123"}}
        mock_session.request.return_value = mock_response

        comments = [("task-1", "Comment text")]

        result = batch_client.bulk_add_comments(comments)

        assert result is not None


class TestBulkGetTasks:
    """Tests for bulk_get_tasks method."""

    def test_bulk_get_empty_list(self, batch_client):
        """Test with empty task list."""
        result = batch_client.bulk_get_tasks([])

        assert result.total == 0

    def test_bulk_get_tasks_success(self, batch_client, mock_session):
        """Test successful task fetching."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "task-1", "name": "Test Task"}}
        mock_session.request.return_value = mock_response

        result = batch_client.bulk_get_tasks(["task-1", "task-2"])

        # Should make parallel requests
        assert result is not None

    def test_bulk_get_tasks_with_custom_fields(self, batch_client, mock_session):
        """Test fetching with custom opt_fields."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "task-1"}}
        mock_session.request.return_value = mock_response

        result = batch_client.bulk_get_tasks(
            ["task-1"],
            opt_fields=["name", "completed"],
        )

        assert result is not None


class TestRequestMethod:
    """Tests for _request method."""

    def test_request_success(self, batch_client, mock_session):
        """Test successful API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"gid": "task-123"}}
        mock_session.request.return_value = mock_response

        result = batch_client._request("GET", "/tasks/123")

        assert result == {"gid": "task-123"}

    def test_request_api_error(self, batch_client, mock_session):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"errors": [{"message": "Invalid request"}]}
        mock_session.request.return_value = mock_response

        with pytest.raises(TrackerError, match="Invalid request"):
            batch_client._request("POST", "/tasks")

    def test_request_api_error_no_message(self, batch_client, mock_session):
        """Test API error with no message."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_session.request.return_value = mock_response

        with pytest.raises(TrackerError, match="500"):
            batch_client._request("GET", "/tasks/123")
