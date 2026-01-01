"""
Tests for GitLabApiClient.

Tests REST API client with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.gitlab.client import GitLabApiClient, GitLabRateLimiter
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
)


@pytest.fixture
def mock_issue_response():
    """Mock GitLab issue response."""
    return {
        "iid": 123,
        "id": 456789,
        "title": "Test Issue",
        "description": "Issue description",
        "state": "opened",
        "labels": [{"name": "bug"}],
        "assignees": [{"username": "testuser", "id": 1}],
        "weight": 5,
        "milestone": {"id": 1, "title": "Sprint 1"},
    }


@pytest.fixture
def mock_session():
    """Create a mock requests session."""
    with patch("spectra.adapters.gitlab.client.requests.Session") as mock:
        session_instance = MagicMock()
        mock.return_value = session_instance
        yield session_instance


@pytest.fixture
def gitlab_client(mock_session):
    """Create GitLabApiClient with mocked session."""
    return GitLabApiClient(
        token="glpat_test",
        project_id="12345",
        dry_run=False,
        requests_per_hour=None,  # Disable rate limiting for tests
    )


class TestGitLabRateLimiter:
    """Tests for GitLabRateLimiter."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = GitLabRateLimiter(requests_per_hour=1000.0)
        assert limiter.requests_per_hour == 1000.0
        assert limiter.requests_per_second > 0

    def test_acquire(self):
        """Test acquiring permission."""
        limiter = GitLabRateLimiter(requests_per_hour=3600.0)  # 1 per second
        limiter.acquire()
        assert limiter.last_request_time > 0

    def test_update_from_response(self):
        """Test updating from response (no-op for GitLab)."""
        limiter = GitLabRateLimiter()
        mock_response = MagicMock()
        limiter.update_from_response(mock_response)
        # Should not raise


class TestGitLabApiClient:
    """Tests for GitLabApiClient."""

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = GitLabApiClient(
            token="my-token",
            project_id="my-project",
        )

        assert client.project_id == "my-project"
        assert client.dry_run is True  # Default
        assert "Bearer my-token" in str(mock_session.headers.update.call_args)

    def test_project_endpoint(self, gitlab_client):
        """Should generate correct project-scoped endpoints."""
        assert gitlab_client.project_endpoint() == "projects/12345"
        assert gitlab_client.project_endpoint("issues") == "projects/12345/issues"
        assert gitlab_client.project_endpoint("issues/123") == "projects/12345/issues/123"

    def test_project_endpoint_with_path(self):
        """Should URL-encode project IDs with slashes."""
        client = GitLabApiClient(
            token="test",
            project_id="group/subgroup/project",
            dry_run=True,
        )
        endpoint = client.project_endpoint("issues")
        assert "group%2Fsubgroup%2Fproject" in endpoint

    def test_get_issue(self, gitlab_client, mock_session):
        """Should fetch issue data."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"iid": 123, "title": "Test Issue"}'
        mock_response.json.return_value = {"iid": 123, "title": "Test Issue"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_issue(123)

        assert result["iid"] == 123
        assert result["title"] == "Test Issue"

    def test_create_issue(self, gitlab_client, mock_session):
        """Should create a new issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"iid": 456, "title": "New Issue"}'
        mock_response.json.return_value = {"iid": 456, "title": "New Issue"}
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.create_issue(
            title="New Issue",
            description="Issue body",
            labels=["bug"],
            weight=3,
        )

        assert result["iid"] == 456
        assert result["title"] == "New Issue"
        mock_session.request.assert_called_once()

    def test_create_issue_dry_run(self):
        """Should not make request in dry-run mode."""
        client = GitLabApiClient(
            token="test",
            project_id="123",
            dry_run=True,
        )
        result = client.create_issue(title="Test")
        assert result == {}

    def test_update_issue(self, gitlab_client, mock_session):
        """Should update an existing issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"iid": 123, "title": "Updated"}'
        mock_response.json.return_value = {"iid": 123, "title": "Updated"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.update_issue(123, title="Updated", description="New description")

        assert result["title"] == "Updated"

    def test_list_issues(self, gitlab_client, mock_session):
        """Should list issues with filters."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"iid": 1}, {"iid": 2}]'
        mock_response.json.return_value = [{"iid": 1}, {"iid": 2}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.list_issues(state="opened", labels=["bug"])

        assert len(result) == 2
        assert result[0]["iid"] == 1

    def test_get_issue_comments(self, gitlab_client, mock_session):
        """Should fetch issue comments (notes)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"id": 1, "body": "Comment 1"}]'
        mock_response.json.return_value = [{"id": 1, "body": "Comment 1"}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_issue_comments(123)

        assert len(result) == 1
        assert result[0]["body"] == "Comment 1"

    def test_add_issue_comment(self, gitlab_client, mock_session):
        """Should add a comment to an issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"id": 789, "body": "New comment"}'
        mock_response.json.return_value = {"id": 789, "body": "New comment"}
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.add_issue_comment(123, "New comment")

        assert result["id"] == 789
        assert result["body"] == "New comment"

    def test_list_labels(self, gitlab_client, mock_session):
        """Should list project labels."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"name": "bug", "color": "#ff0000"}]'
        mock_response.json.return_value = [{"name": "bug", "color": "#ff0000"}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.list_labels()

        assert len(result) == 1
        assert result[0]["name"] == "bug"

    def test_create_label(self, gitlab_client, mock_session):
        """Should create a new label."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"name": "new-label", "color": "#00ff00"}'
        mock_response.json.return_value = {"name": "new-label", "color": "#00ff00"}
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.create_label("new-label", "#00ff00", "Description")

        assert result["name"] == "new-label"

    def test_list_milestones(self, gitlab_client, mock_session):
        """Should list milestones."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"id": 1, "title": "Sprint 1"}]'
        mock_response.json.return_value = [{"id": 1, "title": "Sprint 1"}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.list_milestones(state="active")

        assert len(result) == 1
        assert result[0]["title"] == "Sprint 1"

    def test_create_milestone(self, gitlab_client, mock_session):
        """Should create a milestone."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"id": 2, "title": "Sprint 2"}'
        mock_response.json.return_value = {"id": 2, "title": "Sprint 2"}
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.create_milestone("Sprint 2", "Description")

        assert result["id"] == 2
        assert result["title"] == "Sprint 2"

    def test_get_authenticated_user(self, gitlab_client, mock_session):
        """Should fetch authenticated user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"id": 1, "username": "testuser"}'
        mock_response.json.return_value = {"id": 1, "username": "testuser"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_authenticated_user()

        assert result["username"] == "testuser"
        assert gitlab_client._current_user is not None

    def test_get_current_user_username(self, gitlab_client, mock_session):
        """Should get username from authenticated user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"id": 1, "username": "testuser"}'
        mock_response.json.return_value = {"id": 1, "username": "testuser"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        username = gitlab_client.get_current_user_username()

        assert username == "testuser"

    def test_test_connection_success(self, gitlab_client, mock_session):
        """Should return True when connection succeeds."""
        # Mock user endpoint
        user_response = MagicMock()
        user_response.ok = True
        user_response.text = '{"id": 1, "username": "test"}'
        user_response.json.return_value = {"id": 1, "username": "test"}
        user_response.status_code = 200
        user_response.headers = {}

        # Mock project endpoint
        project_response = MagicMock()
        project_response.ok = True
        project_response.text = '{"id": 12345}'
        project_response.json.return_value = {"id": 12345}
        project_response.status_code = 200
        project_response.headers = {}

        mock_session.request.side_effect = [user_response, project_response]

        assert gitlab_client.test_connection() is True

    def test_test_connection_failure(self, gitlab_client, mock_session):
        """Should return False when connection fails."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        assert gitlab_client.test_connection() is False

    def test_handle_response_authentication_error(self, gitlab_client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            gitlab_client.get("user")

    def test_handle_response_permission_error(self, gitlab_client, mock_session):
        """Should raise PermissionError on 403."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_session.request.return_value = mock_response

        with pytest.raises(PermissionError):
            gitlab_client.get("projects/123")

    def test_handle_response_not_found_error(self, gitlab_client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            gitlab_client.get_issue(999)

    @pytest.mark.slow
    def test_handle_response_rate_limit_error(self, gitlab_client, mock_session):
        """Should raise RateLimitError on 429."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_response.text = "Too Many Requests"
        mock_response.headers = {"Retry-After": "60"}
        mock_session.request.return_value = mock_response

        with pytest.raises(RateLimitError) as exc_info:
            gitlab_client.get("projects/123")
        assert exc_info.value.retry_after == 60

    def test_retry_on_transient_error(self, gitlab_client, mock_session):
        """Should retry on transient errors."""
        # First call fails, second succeeds
        fail_response = MagicMock()
        fail_response.ok = False
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"
        fail_response.headers = {}

        success_response = MagicMock()
        success_response.ok = True
        success_response.text = '{"iid": 123}'
        success_response.json.return_value = {"iid": 123}
        success_response.status_code = 200
        success_response.headers = {}

        mock_session.request.side_effect = [fail_response, success_response]

        result = gitlab_client.get_issue(123)

        assert result["iid"] == 123
        assert mock_session.request.call_count == 2

    def test_context_manager(self, mock_session):
        """Should work as context manager."""
        client = GitLabApiClient(token="test", project_id="123")
        # Verify session was created
        assert client._session is not None
        # Test context manager exit
        client.__exit__(None, None, None)
        # Verify close was called on the session
        assert client._session.close.called

    # -------------------------------------------------------------------------
    # Merge Requests API
    # -------------------------------------------------------------------------

    def test_get_merge_request(self, gitlab_client, mock_session):
        """Should fetch merge request data."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"iid": 5, "title": "Feature MR"}'
        mock_response.json.return_value = {"iid": 5, "title": "Feature MR"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_merge_request(5)

        assert result["iid"] == 5
        assert result["title"] == "Feature MR"

    def test_list_merge_requests(self, gitlab_client, mock_session):
        """Should list merge requests."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"iid": 1}, {"iid": 2}]'
        mock_response.json.return_value = [{"iid": 1}, {"iid": 2}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.list_merge_requests(state="opened")

        assert len(result) == 2

    def test_get_merge_requests_for_issue(self, gitlab_client, mock_session):
        """Should find MRs that reference an issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = (
            '[{"iid": 1, "description": "Closes #123"}, {"iid": 2, "description": "Other"}]'
        )
        mock_response.json.return_value = [
            {"iid": 1, "description": "Closes #123", "title": "MR 1"},
            {"iid": 2, "description": "Other", "title": "MR 2"},
        ]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_merge_requests_for_issue(123)

        assert len(result) == 1
        assert result[0]["iid"] == 1

    def test_link_merge_request_to_issue(self, gitlab_client, mock_session):
        """Should link MR to issue by updating description."""
        # Mock get MR
        get_mr_response = MagicMock()
        get_mr_response.ok = True
        get_mr_response.text = '{"iid": 5, "description": "Original"}'
        get_mr_response.json.return_value = {"iid": 5, "description": "Original"}
        get_mr_response.status_code = 200
        get_mr_response.headers = {}

        # Mock update MR
        update_mr_response = MagicMock()
        update_mr_response.ok = True
        update_mr_response.text = '{"iid": 5}'
        update_mr_response.json.return_value = {"iid": 5}
        update_mr_response.status_code = 200
        update_mr_response.headers = {}

        mock_session.request.side_effect = [get_mr_response, update_mr_response]

        result = gitlab_client.link_merge_request_to_issue(5, 123, "closes")

        assert result is True

    # -------------------------------------------------------------------------
    # Issue Boards API
    # -------------------------------------------------------------------------

    def test_list_boards(self, gitlab_client, mock_session):
        """Should list boards."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"id": 1, "name": "Development"}]'
        mock_response.json.return_value = [{"id": 1, "name": "Development"}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.list_boards()

        assert len(result) == 1
        assert result[0]["name"] == "Development"

    def test_get_board(self, gitlab_client, mock_session):
        """Should get a board."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"id": 1, "name": "Development"}'
        mock_response.json.return_value = {"id": 1, "name": "Development"}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_board(1)

        assert result["name"] == "Development"

    def test_get_board_lists(self, gitlab_client, mock_session):
        """Should get board lists."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '[{"id": 1, "label": {"name": "To Do"}}]'
        mock_response.json.return_value = [{"id": 1, "label": {"name": "To Do"}}]
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_board_lists(1)

        assert len(result) == 1
        assert result[0]["label"]["name"] == "To Do"

    def test_move_issue_to_board_list(self, gitlab_client, mock_session):
        """Should move issue to board list."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"success": true}'
        mock_response.json.return_value = {"success": True}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.move_issue_to_board_list(123, board_id=1, list_id=2)

        assert result is True

    def test_get_issue_board_position(self, gitlab_client, mock_session):
        """Should get issue board position."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"board_id": 1, "list_id": 2}'
        mock_response.json.return_value = {"board_id": 1, "list_id": 2}
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_issue_board_position(123)

        assert result["board_id"] == 1

    # -------------------------------------------------------------------------
    # Time Tracking API
    # -------------------------------------------------------------------------

    def test_get_issue_time_stats(self, gitlab_client, mock_session):
        """Should get time stats."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"time_estimate": 3600, "total_time_spent": 1800}'
        mock_response.json.return_value = {
            "time_estimate": 3600,
            "total_time_spent": 1800,
        }
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = gitlab_client.get_issue_time_stats(123)

        assert result["time_estimate"] == 3600
        assert result["total_time_spent"] == 1800

    def test_add_spent_time(self, gitlab_client, mock_session):
        """Should add spent time."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"total_time_spent": 1800}'
        mock_response.json.return_value = {"total_time_spent": 1800}
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        result = gitlab_client.add_spent_time(123, "30m", summary="Work")

        assert result["total_time_spent"] == 1800

    def test_reset_spent_time(self, gitlab_client, mock_session):
        """Should reset spent time."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"total_time_spent": 0}'
        mock_response.json.return_value = {"total_time_spent": 0}
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        result = gitlab_client.reset_spent_time(123)

        assert result["total_time_spent"] == 0

    def test_estimate_time(self, gitlab_client, mock_session):
        """Should set time estimate."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"time_estimate": 7200}'
        mock_response.json.return_value = {"time_estimate": 7200}
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        result = gitlab_client.estimate_time(123, "2h")

        assert result["time_estimate"] == 7200

    def test_reset_time_estimate(self, gitlab_client, mock_session):
        """Should reset time estimate."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.text = '{"time_estimate": 0}'
        mock_response.json.return_value = {"time_estimate": 0}
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        result = gitlab_client.reset_time_estimate(123)

        assert result["time_estimate"] == 0
