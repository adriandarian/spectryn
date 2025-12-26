"""
Dedicated tests for YouTrack API Client.

Tests cover:
- Rate limiting and retry logic
- Error handling (403, 500, network errors, timeouts)
- Edge cases (empty responses, malformed JSON, connection errors)
- Connection pooling and session management
- Dry-run mode for all write operations
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from spectra.adapters.youtrack.client import YouTrackApiClient
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


# =============================================================================
# Client Initialization Tests
# =============================================================================


class TestYouTrackClientInit:
    """Tests for YouTrack client initialization."""

    def test_client_initialization(self):
        """Should initialize with correct settings."""
        with patch("spectra.adapters.youtrack.client.requests.Session"):
            client = YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
            )

        assert client.base_url == "https://test.youtrack.com"
        assert client.api_url == "https://test.youtrack.com/api"
        assert client.token == "test-token"
        assert client.dry_run is True  # Default

    def test_client_initialization_with_trailing_slash(self):
        """Should handle trailing slash in URL."""
        with patch("spectra.adapters.youtrack.client.requests.Session"):
            client = YouTrackApiClient(
                url="https://test.youtrack.com/",
                token="test-token",
            )

        assert client.base_url == "https://test.youtrack.com"

    def test_client_custom_retry_settings(self):
        """Should accept custom retry settings."""
        with patch("spectra.adapters.youtrack.client.requests.Session"):
            client = YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
                max_retries=5,
                initial_delay=2.0,
                max_delay=120.0,
            )

        assert client.max_retries == 5
        assert client.initial_delay == 2.0
        assert client.max_delay == 120.0


# =============================================================================
# Rate Limiting and Retry Tests
# =============================================================================


class TestYouTrackRateLimiting:
    """Tests for rate limiting and retry logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with minimal retry delays."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,  # Minimal delay for testing
            max_delay=0.1,
        )

    def test_retry_on_429_rate_limit(self, client, mock_session):
        """Should retry on 429 rate limit and eventually raise."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}
        rate_limit_response.text = "Rate limit exceeded"

        mock_session.request.return_value = rate_limit_response

        with pytest.raises(RateLimitError) as exc_info:
            client.get("issues/TEST-1")

        assert "rate limit" in str(exc_info.value).lower()
        # Should have tried max_retries + 1 times
        assert mock_session.request.call_count == 3

    def test_retry_on_503_service_unavailable(self, client, mock_session):
        """Should retry on 503 and eventually raise TransientError."""
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"

        mock_session.request.return_value = error_response

        with pytest.raises(TransientError):
            client.get("issues/TEST-1")

        assert mock_session.request.call_count == 3

    def test_retry_then_succeed(self, client, mock_session):
        """Should succeed after retry."""
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.text = "Service Unavailable"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.ok = True
        success_response.json.return_value = {"id": "TEST-1"}

        mock_session.request.side_effect = [error_response, success_response]

        result = client.get("issues/TEST-1")

        assert result["id"] == "TEST-1"
        assert mock_session.request.call_count == 2


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestYouTrackErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
            max_retries=0,  # No retries for error testing
        )

    def test_401_unauthorized(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        response = MagicMock()
        response.status_code = 401
        response.ok = False
        response.text = "Unauthorized"
        mock_session.request.return_value = response

        with pytest.raises(AuthenticationError):
            client.get("issues/TEST-1")

    def test_403_forbidden(self, client, mock_session):
        """Should raise PermissionError on 403."""
        response = MagicMock()
        response.status_code = 403
        response.ok = False
        response.text = "Forbidden"
        mock_session.request.return_value = response

        with pytest.raises(PermissionError):
            client.get("issues/TEST-1")

    def test_404_not_found(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        response = MagicMock()
        response.status_code = 404
        response.ok = False
        response.text = "Not Found"
        mock_session.request.return_value = response

        with pytest.raises(NotFoundError):
            client.get("issues/TEST-999")

    def test_500_server_error(self, client, mock_session):
        """Should raise IssueTrackerError on 500."""
        response = MagicMock()
        response.status_code = 500
        response.ok = False
        response.text = "Internal Server Error"
        mock_session.request.return_value = response

        with pytest.raises(IssueTrackerError):
            client.get("issues/TEST-1")

    def test_connection_error(self, client, mock_session):
        """Should raise IssueTrackerError on connection error."""
        mock_session.request.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(IssueTrackerError) as exc_info:
            client.get("issues/TEST-1")

        assert "Connection failed" in str(exc_info.value)

    def test_timeout_error(self, client, mock_session):
        """Should raise IssueTrackerError on timeout."""
        mock_session.request.side_effect = requests.exceptions.Timeout("Request timed out")

        with pytest.raises(IssueTrackerError) as exc_info:
            client.get("issues/TEST-1")

        assert "timed out" in str(exc_info.value)


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestYouTrackEdgeCases:
    """Tests for edge cases."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
            max_retries=0,
        )

    def test_empty_json_response(self, client, mock_session):
        """Should handle empty JSON response."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {}
        mock_session.request.return_value = response

        result = client.get("issues/TEST-1")

        assert result == {}

    def test_empty_list_response(self, client, mock_session):
        """Should handle empty list response."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = []
        mock_session.request.return_value = response

        result = client.get("issues")

        assert result == []

    def test_malformed_json_response(self, client, mock_session):
        """Should handle malformed JSON response."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.side_effect = ValueError("Invalid JSON")
        response.text = "not json"
        mock_session.request.return_value = response

        # Should return empty dict on parse failure
        result = client.get("issues/TEST-1")
        assert result == {}

    def test_204_no_content_response(self, client, mock_session):
        """Should handle 204 No Content response."""
        response = MagicMock()
        response.status_code = 204
        response.ok = True
        mock_session.request.return_value = response

        result = client.delete("issues/TEST-1")

        assert result == {}

    def test_absolute_endpoint(self, client, mock_session):
        """Should handle absolute endpoints."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"id": "1"}
        mock_session.request.return_value = response

        client.get("/issues/TEST-1")

        # Should use absolute path
        call_args = mock_session.request.call_args
        assert "/api/issues/TEST-1" in call_args[0][1]

    def test_relative_endpoint(self, client, mock_session):
        """Should handle relative endpoints."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"id": "1"}
        mock_session.request.return_value = response

        client.get("issues/TEST-1")

        call_args = mock_session.request.call_args
        assert "/api/issues/TEST-1" in call_args[0][1]


# =============================================================================
# Connection Pooling and Session Tests
# =============================================================================


class TestYouTrackSessionManagement:
    """Tests for connection pooling and session management."""

    def test_session_headers(self):
        """Should set correct session headers."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session

            YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
            )

            # Check headers were set
            session.headers.update.assert_called()
            headers = session.headers.update.call_args[0][0]
            assert "Authorization" in headers
            assert "Bearer test-token" in headers["Authorization"]
            assert headers["Accept"] == "application/json"
            assert headers["Content-Type"] == "application/json"

    def test_session_mount_http_adapter(self):
        """Should mount HTTP adapter for connection pooling."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session

            YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
            )

            # Should mount adapter for both http and https
            assert session.mount.call_count >= 2

    def test_context_manager(self):
        """Should work as context manager."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session

            with YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
            ) as client:
                assert client is not None

            session.close.assert_called_once()

    def test_close_session(self):
        """Should close session on close()."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session

            client = YouTrackApiClient(
                url="https://test.youtrack.com",
                token="test-token",
            )
            client.close()

            session.close.assert_called_once()


# =============================================================================
# Dry-Run Mode Tests
# =============================================================================


class TestYouTrackDryRunMode:
    """Tests for dry-run mode on all write operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client in dry-run mode."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=True,
        )

    def test_create_issue_dry_run(self, client, mock_session):
        """Should not create issue in dry-run mode."""
        result = client.create_issue("PROJ", "Test Issue", "Task", "Description")

        # Dry-run returns empty dict (post() returns {})
        assert result == {}
        mock_session.request.assert_not_called()

    def test_update_issue_dry_run(self, client, mock_session):
        """Should not update issue in dry-run mode."""
        result = client.update_issue("TEST-1", summary="Updated")

        assert result == {}
        mock_session.request.assert_not_called()

    def test_add_comment_dry_run(self, client, mock_session):
        """Should not add comment in dry-run mode."""
        result = client.add_comment("TEST-1", "Test comment")

        # Dry-run returns empty dict (post() returns {})
        assert result == {}
        mock_session.request.assert_not_called()

    def test_transition_issue_dry_run(self, client, mock_session):
        """Should not transition issue in dry-run mode."""
        result = client.transition_issue("TEST-1", "Done")

        assert result == {}
        mock_session.request.assert_not_called()

    def test_bulk_create_dry_run(self, client, mock_session):
        """Should not bulk create in dry-run mode."""
        result = client.bulk_create_issues([{"summary": "Test"}])

        assert len(result) == 1
        assert "dry-run" in result[0].get("id", "")
        mock_session.request.assert_not_called()

    def test_bulk_update_dry_run(self, client, mock_session):
        """Should not bulk update in dry-run mode."""
        result = client.bulk_update_issues([{"id": "TEST-1", "summary": "Updated"}])

        assert len(result) == 1
        assert result[0].get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_bulk_delete_dry_run(self, client, mock_session):
        """Should not bulk delete in dry-run mode."""
        result = client.bulk_delete_issues(["TEST-1", "TEST-2"])

        assert len(result) == 2
        assert all(r.get("status") == "dry-run" for r in result)
        mock_session.request.assert_not_called()

    def test_upload_attachment_dry_run(self, client, mock_session):
        """Should not upload attachment in dry-run mode."""
        result = client.upload_attachment("TEST-1", "/path/to/file.txt")

        assert "dry-run" in result.get("id", "")
        mock_session.post.assert_not_called()

    def test_delete_attachment_dry_run(self, client, mock_session):
        """Should not delete attachment in dry-run mode."""
        result = client.delete_attachment("TEST-1", "att-1")

        assert result is True
        mock_session.request.assert_not_called()

    def test_execute_command_dry_run(self, client, mock_session):
        """Should not execute command in dry-run mode."""
        result = client.execute_command("TEST-1", "State In Progress")

        assert result.get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_add_tag_dry_run(self, client, mock_session):
        """Should not add tag in dry-run mode."""
        result = client.add_issue_tag("TEST-1", "urgent")

        assert result.get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_remove_tag_dry_run(self, client, mock_session):
        """Should not remove tag in dry-run mode."""
        result = client.remove_issue_tag("TEST-1", "urgent")

        assert result.get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_add_watcher_dry_run(self, client, mock_session):
        """Should not add watcher in dry-run mode."""
        result = client.add_issue_watcher("TEST-1", "john.doe")

        assert result.get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_remove_watcher_dry_run(self, client, mock_session):
        """Should not remove watcher in dry-run mode."""
        result = client.remove_issue_watcher("TEST-1", "john.doe")

        assert result is True
        mock_session.request.assert_not_called()

    def test_create_sprint_dry_run(self, client, mock_session):
        """Should not create sprint in dry-run mode."""
        result = client.create_sprint("board-1", "Sprint 1")

        assert "dry-run" in result.get("id", "")
        mock_session.request.assert_not_called()

    def test_add_work_item_dry_run(self, client, mock_session):
        """Should not add work item in dry-run mode."""
        result = client.add_work_item("TEST-1", 60)

        assert "dry-run" in result.get("id", "")
        mock_session.request.assert_not_called()

    def test_delete_work_item_dry_run(self, client, mock_session):
        """Should not delete work item in dry-run mode."""
        result = client.delete_work_item("TEST-1", "work-1")

        assert result is True
        mock_session.request.assert_not_called()

    def test_set_time_estimate_dry_run(self, client, mock_session):
        """Should not set time estimate in dry-run mode."""
        result = client.set_time_estimate("TEST-1", 480)

        assert "estimate" in result
        mock_session.request.assert_not_called()

    def test_set_due_date_dry_run(self, client, mock_session):
        """Should not set due date in dry-run mode."""
        result = client.set_issue_due_date("TEST-1", 1704067200000)

        assert result.get("status") == "dry-run"
        mock_session.request.assert_not_called()

    def test_add_comment_with_mentions_dry_run(self, client, mock_session):
        """Should not add comment with mentions in dry-run mode."""
        result = client.add_comment_with_mentions("TEST-1", "Test", ["user1"])

        assert "dry-run" in result.get("id", "")
        mock_session.request.assert_not_called()


# =============================================================================
# API Method Tests
# =============================================================================


class TestYouTrackApiMethods:
    """Tests for specific API methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
            max_retries=0,
        )

    def test_get_current_user(self, client, mock_session):
        """Should get current user."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"login": "admin", "name": "Admin User"}
        mock_session.request.return_value = response

        result = client.get_current_user()

        assert result["login"] == "admin"

    def test_test_connection_success(self, client, mock_session):
        """Should return True on successful connection test."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"login": "admin"}
        mock_session.request.return_value = response

        assert client.test_connection() is True

    def test_test_connection_failure(self, client, mock_session):
        """Should return False on failed connection test."""
        mock_session.request.side_effect = requests.exceptions.ConnectionError()

        assert client.test_connection() is False

    def test_is_connected_property(self, client, mock_session):
        """Should check connection status via property."""
        # is_connected is a property that checks if _current_user is set
        # By default it's None, so should be False
        assert client.is_connected is False

        # After setting current user, should be True
        client._current_user = {"login": "admin"}
        assert client.is_connected is True

    def test_get_issue_with_fields(self, client, mock_session):
        """Should get issue with specific fields."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"id": "TEST-1", "summary": "Test"}
        mock_session.request.return_value = response

        result = client.get_issue("TEST-1", fields="id,summary")

        assert result["id"] == "TEST-1"
        # Check fields param was passed
        call_args = mock_session.request.call_args
        assert "fields" in call_args[1].get("params", {})

    def test_search_issues(self, client, mock_session):
        """Should search issues."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = [{"id": "TEST-1"}, {"id": "TEST-2"}]
        mock_session.request.return_value = response

        result = client.search_issues("project: PROJ", max_results=10)

        assert len(result) == 2

    def test_create_link(self, client, mock_session):
        """Should create link between issues."""
        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {}
        mock_session.request.return_value = response

        result = client.create_link("TEST-1", "TEST-2", "depends on")

        assert result == {}
        mock_session.request.assert_called_once()
