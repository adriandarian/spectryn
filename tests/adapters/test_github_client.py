"""
Tests for GitHubApiClient.

Tests REST API client with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.github.client import GitHubApiClient, GitHubRateLimiter
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
)


@pytest.fixture
def mock_issue_response():
    """Mock GitHub issue response."""
    return {
        "number": 123,
        "title": "Test Issue",
        "body": "Issue description",
        "state": "open",
        "labels": [{"name": "bug"}],
        "assignee": {"login": "testuser"},
        "milestone": {"number": 1, "title": "Sprint 1"},
    }


@pytest.fixture
def mock_session():
    """Create a mock requests session."""
    with patch("spectryn.adapters.github.client.requests.Session") as mock:
        session_instance = MagicMock()
        mock.return_value = session_instance
        yield session_instance


@pytest.fixture
def github_client(mock_session):
    """Create GitHubApiClient with mocked session."""
    return GitHubApiClient(
        token="ghp_test",
        owner="testowner",
        repo="testrepo",
        dry_run=False,
        requests_per_second=None,  # Disable rate limiting for tests
    )


class TestGitHubRateLimiter:
    """Tests for GitHubRateLimiter."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = GitHubRateLimiter(requests_per_second=5.0, burst_size=10)
        assert limiter.requests_per_second == 5.0
        assert limiter.burst_size == 10

    def test_acquire_token(self):
        """Test acquiring a token."""
        limiter = GitHubRateLimiter(requests_per_second=100.0, burst_size=10)
        result = limiter.acquire(timeout=1.0)
        assert result is True

    def test_acquire_depletes_tokens(self):
        """Test that acquiring depletes tokens."""
        limiter = GitHubRateLimiter(requests_per_second=100.0, burst_size=5)

        # Acquire all tokens
        for _ in range(5):
            limiter.acquire(timeout=0.1)

        # Next acquire should wait
        initial_tokens = limiter._tokens
        assert initial_tokens < 1.0

    def test_stats(self):
        """Test stats property."""
        limiter = GitHubRateLimiter()
        limiter.acquire()

        stats = limiter.stats
        assert "total_requests" in stats
        assert stats["total_requests"] == 1

    def test_reset(self):
        """Test reset method."""
        limiter = GitHubRateLimiter(burst_size=10)
        limiter.acquire()
        limiter.acquire()

        limiter.reset()

        assert limiter._tokens == 10.0
        assert limiter._total_requests == 0

    def test_update_from_response(self):
        """Test updating from GitHub response headers."""
        limiter = GitHubRateLimiter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": "1234567890",
        }

        limiter.update_from_response(mock_response)

        assert limiter._rate_limit_remaining == 4999

    def test_update_from_rate_limit_response(self):
        """Test rate adjustment on 429."""
        limiter = GitHubRateLimiter(requests_per_second=10.0)
        original_rate = limiter.requests_per_second

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        limiter.update_from_response(mock_response)

        assert limiter.requests_per_second < original_rate

    def test_should_wait_for_github_limit_no_remaining(self):
        """Test _should_wait_for_github_limit when no remaining set."""
        limiter = GitHubRateLimiter()
        assert limiter._should_wait_for_github_limit() is False

    def test_should_wait_for_github_limit_low_remaining(self):
        """Test _should_wait_for_github_limit when remaining is low."""
        limiter = GitHubRateLimiter()
        limiter._rate_limit_remaining = 3
        assert limiter._should_wait_for_github_limit() is True

    def test_github_wait_time_no_reset(self):
        """Test _github_wait_time when no reset time set."""
        limiter = GitHubRateLimiter()
        assert limiter._github_wait_time() == 60.0

    def test_refill_tokens(self):
        """Test _refill_tokens adds tokens over time."""
        limiter = GitHubRateLimiter(requests_per_second=1000.0, burst_size=10)
        limiter._tokens = 0.0

        # Simulate time passing by calling refill
        # Use longer sleep for Windows timer resolution (~15ms)
        import time

        time.sleep(0.05)
        limiter._refill_tokens()

        assert limiter._tokens > 0


class TestGitHubApiClientInit:
    """Tests for GitHubApiClient initialization."""

    def test_init_sets_attributes(self):
        """Test initialization sets basic attributes."""
        with patch("spectryn.adapters.github.client.requests.Session"):
            from spectryn.adapters.github.client import GitHubApiClient

            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
            )

            assert client.owner == "owner"
            assert client.repo == "repo"
            assert client.dry_run is True

    def test_init_with_custom_base_url(self):
        """Test initialization with enterprise URL."""
        with patch("spectryn.adapters.github.client.requests.Session"):
            from spectryn.adapters.github.client import GitHubApiClient

            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                base_url="https://github.enterprise.com/api/v3/",
            )

            assert client.base_url == "https://github.enterprise.com/api/v3"

    def test_init_without_rate_limiter(self):
        """Test initialization without rate limiting."""
        with patch("spectryn.adapters.github.client.requests.Session"):
            from spectryn.adapters.github.client import GitHubApiClient

            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                requests_per_second=None,
            )

            assert client._rate_limiter is None

    def test_init_with_rate_limiter(self):
        """Test initialization with rate limiting."""
        with patch("spectryn.adapters.github.client.requests.Session"):
            from spectryn.adapters.github.client import GitHubApiClient

            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                requests_per_second=5.0,
            )

            assert client._rate_limiter is not None


class TestGitHubApiClientMethods:
    """Tests for GitHubApiClient API methods with mocked HTTP responses."""

    def test_get_request(self, github_client, mock_session):
        """Test GET request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"login": "testuser"}'
        mock_response.json.return_value = {"login": "testuser"}
        mock_session.request.return_value = mock_response

        result = github_client.get("/user")
        assert result == {"login": "testuser"}
        mock_session.request.assert_called()

    def test_post_request_dry_run(self, mock_session):
        """Test POST respects dry_run mode."""
        with patch("spectryn.adapters.github.client.requests.Session") as mock:
            mock.return_value = mock_session
            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                dry_run=True,
                requests_per_second=None,
            )

            result = client.post("/endpoint", json={"data": "test"})
            assert result == {}
            mock_session.request.assert_not_called()

    def test_post_request_executes(self, github_client, mock_session):
        """Test POST executes when not dry_run."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.text = '{"id": 123}'
        mock_response.json.return_value = {"id": 123}
        mock_session.request.return_value = mock_response

        result = github_client.post("/endpoint", json={"data": "test"})
        assert result == {"id": 123}
        mock_session.request.assert_called()

    def test_patch_request_dry_run(self, mock_session):
        """Test PATCH respects dry_run mode."""
        with patch("spectryn.adapters.github.client.requests.Session") as mock:
            mock.return_value = mock_session
            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                dry_run=True,
                requests_per_second=None,
            )

            result = client.patch("/endpoint", json={"data": "test"})
            assert result == {}
            mock_session.request.assert_not_called()

    def test_delete_request_dry_run(self, mock_session):
        """Test DELETE respects dry_run mode."""
        with patch("spectryn.adapters.github.client.requests.Session") as mock:
            mock.return_value = mock_session
            client = GitHubApiClient(
                token="ghp_test",
                owner="owner",
                repo="repo",
                dry_run=True,
                requests_per_second=None,
            )

            result = client.delete("/endpoint")
            assert result == {}
            mock_session.request.assert_not_called()

    def test_repo_endpoint(self, github_client):
        """Test repo_endpoint construction."""
        assert github_client.repo_endpoint() == "repos/testowner/testrepo"
        assert github_client.repo_endpoint("issues") == "repos/testowner/testrepo/issues"

    def test_get_authenticated_user(self, github_client, mock_session):
        """Test get_authenticated_user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"login": "testuser", "id": 123}'
        mock_response.json.return_value = {"login": "testuser", "id": 123}
        mock_session.request.return_value = mock_response

        result = github_client.get_authenticated_user()
        assert result == {"login": "testuser", "id": 123}
        assert github_client._current_user == {"login": "testuser", "id": 123}

    def test_get_authenticated_user_caches(self, github_client, mock_session):
        """Test get_authenticated_user caches result."""
        github_client._current_user = {"login": "cached", "id": 999}

        result = github_client.get_authenticated_user()
        assert result == {"login": "cached", "id": 999}
        mock_session.request.assert_not_called()

    def test_get_current_user_login(self, github_client, mock_session):
        """Test get_current_user_login."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"login": "testuser"}'
        mock_response.json.return_value = {"login": "testuser"}
        mock_session.request.return_value = mock_response

        result = github_client.get_current_user_login()
        assert result == "testuser"

    def test_is_connected_false_initially(self, github_client):
        """Test is_connected is False when no user fetched."""
        assert github_client.is_connected is False

    def test_is_connected_true_after_auth(self, github_client):
        """Test is_connected is True after fetching user."""
        github_client._current_user = {"login": "testuser"}
        assert github_client.is_connected is True


class TestGitHubApiClientIssues:
    """Tests for GitHub Issues API methods."""

    def test_get_issue(self, github_client, mock_session, mock_issue_response):
        """Test get_issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "{}"
        mock_response.json.return_value = mock_issue_response
        mock_session.request.return_value = mock_response

        result = github_client.get_issue(123)
        assert result["number"] == 123
        assert result["title"] == "Test Issue"

    def test_list_issues(self, github_client, mock_session):
        """Test list_issues."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "[]"
        mock_response.json.return_value = [
            {"number": 1, "title": "Issue 1"},
            {"number": 2, "title": "Issue 2"},
        ]
        mock_session.request.return_value = mock_response

        result = github_client.list_issues(state="open")
        assert len(result) == 2
        assert result[0]["number"] == 1

    def test_list_issues_with_filters(self, github_client, mock_session):
        """Test list_issues with labels and milestone."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "[]"
        mock_response.json.return_value = []
        mock_session.request.return_value = mock_response

        github_client.list_issues(
            state="closed",
            labels=["bug", "urgent"],
            milestone="v1.0",
        )
        mock_session.request.assert_called()

    def test_create_issue(self, github_client, mock_session):
        """Test create_issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.text = "{}"
        mock_response.json.return_value = {"number": 456, "title": "New Issue"}
        mock_session.request.return_value = mock_response

        result = github_client.create_issue(
            title="New Issue",
            body="Description",
            labels=["enhancement"],
            assignees=["dev1"],
        )
        assert result["number"] == 456

    def test_update_issue(self, github_client, mock_session):
        """Test update_issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "{}"
        mock_response.json.return_value = {"number": 123, "state": "closed"}
        mock_session.request.return_value = mock_response

        result = github_client.update_issue(
            issue_number=123,
            state="closed",
            labels=["done"],
        )
        assert result["state"] == "closed"

    def test_get_issue_comments(self, github_client, mock_session):
        """Test get_issue_comments."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "[]"
        mock_response.json.return_value = [
            {"id": 1, "body": "Comment 1"},
            {"id": 2, "body": "Comment 2"},
        ]
        mock_session.request.return_value = mock_response

        result = github_client.get_issue_comments(123)
        assert len(result) == 2
        assert result[0]["body"] == "Comment 1"

    def test_add_issue_comment(self, github_client, mock_session):
        """Test add_issue_comment."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.text = "{}"
        mock_response.json.return_value = {"id": 789, "body": "New comment"}
        mock_session.request.return_value = mock_response

        result = github_client.add_issue_comment(123, "New comment")
        assert result["id"] == 789


class TestGitHubApiClientLabels:
    """Tests for GitHub Labels API methods."""

    def test_list_labels(self, github_client, mock_session):
        """Test list_labels."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = "[]"
        mock_response.json.return_value = [
            {"name": "bug", "color": "d73a4a"},
            {"name": "enhancement", "color": "a2eeef"},
        ]
        mock_session.request.return_value = mock_response

        result = github_client.list_labels()
        assert len(result) == 2
        assert result[0]["name"] == "bug"

    def test_create_label(self, github_client, mock_session):
        """Test create_label."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.text = "{}"
        mock_response.json.return_value = {"name": "priority", "color": "ff0000"}
        mock_session.request.return_value = mock_response

        result = github_client.create_label(
            name="priority",
            color="ff0000",
            description="High priority issues",
        )
        assert result["name"] == "priority"


class TestGitHubApiClientErrors:
    """Tests for error handling in GitHubApiClient."""

    def test_authentication_error(self, github_client, mock_session):
        """Test 401 raises AuthenticationError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError, match="authentication failed"):
            github_client.get("/user")

    def test_permission_error(self, github_client, mock_session):
        """Test 403 raises PermissionError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_session.request.return_value = mock_response

        with pytest.raises(PermissionError, match="Permission denied"):
            github_client.get("/repo/private")

    def test_not_found_error(self, github_client, mock_session):
        """Test 404 raises NotFoundError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError, match="Not found"):
            github_client.get("/repo/nonexistent")

    def test_generic_api_error(self, github_client, mock_session):
        """Test other status codes raise IssueTrackerError."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 422
        mock_response.text = "Validation failed"
        mock_session.request.return_value = mock_response

        with pytest.raises(IssueTrackerError, match="API error 422"):
            github_client.get("/issues")

    def test_empty_response_body(self, github_client, mock_session):
        """Test handling of empty response body."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        mock_response.text = ""
        mock_session.request.return_value = mock_response

        result = github_client.get("/endpoint")
        assert result == {}


class TestGitHubApiClientTestConnection:
    """Tests for test_connection method."""

    def test_test_connection_success(self, github_client, mock_session):
        """Test test_connection returns True on success."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"login": "user"}'
        mock_response.json.return_value = {"login": "user"}
        mock_session.request.return_value = mock_response

        result = github_client.test_connection()
        assert result is True

    def test_test_connection_failure(self, github_client, mock_session):
        """Test test_connection returns False on failure."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        result = github_client.test_connection()
        assert result is False
