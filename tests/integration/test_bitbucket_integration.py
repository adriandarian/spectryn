"""
Integration tests with mocked Bitbucket API responses.

These tests verify the full flow from adapter through client
using realistic API responses for both Cloud and Server.

Note: For actual integration testing with real Bitbucket instances,
set environment variables:
- BITBUCKET_USERNAME
- BITBUCKET_APP_PASSWORD
- BITBUCKET_WORKSPACE
- BITBUCKET_REPO
- BITBUCKET_BASE_URL (optional, defaults to Cloud)
"""

import json
from unittest.mock import Mock, patch

import pytest

from spectryn.adapters.bitbucket.adapter import BitbucketAdapter
from spectryn.adapters.bitbucket.client import BitbucketApiClient
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    RateLimitError,
    TransitionError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bitbucket_cloud_config():
    """Bitbucket Cloud adapter configuration."""
    return {
        "username": "testuser",
        "app_password": "test_app_password_12345",
        "workspace": "test-workspace",
        "repo": "test-repo",
        "base_url": "https://api.bitbucket.org/2.0",
    }


@pytest.fixture
def bitbucket_server_config():
    """Bitbucket Server adapter configuration."""
    return {
        "username": "testuser",
        "app_password": "test_pat_token_12345",
        "workspace": "TEST",
        "repo": "test-repo",
        "base_url": "https://bitbucket.example.com/rest/api/2.0",
    }


@pytest.fixture
def mock_user_response():
    """Mock response for authenticated user."""
    return {
        "username": "testuser",
        "display_name": "Test User",
        "uuid": "{12345678-1234-1234-1234-123456789abc}",
        "account_id": "12345678",
    }


@pytest.fixture
def mock_repo_response():
    """Mock response for repository."""
    return {
        "name": "test-repo",
        "full_name": "test-workspace/test-repo",
        "uuid": "{repo-uuid}",
        "is_private": False,
    }


@pytest.fixture
def mock_issue_response():
    """Mock response for Bitbucket issue GET."""
    return {
        "id": 123,
        "title": "Sample User Story",
        "content": {
            "raw": "**As a** developer\n**I want** a feature\n**So that** I can test",
            "markup": "markdown",
        },
        "state": "open",
        "priority": "minor",
        "kind": "task",
        "assignee": {"username": "testuser", "display_name": "Test User"},
        "reporter": {"username": "testuser"},
        "created_on": "2024-01-01T00:00:00+00:00",
        "updated_on": "2024-01-02T00:00:00+00:00",
    }


@pytest.fixture
def mock_issues_list_response():
    """Mock response for listing issues."""
    return {
        "values": [
            {
                "id": 10,
                "title": "Story Alpha",
                "content": {"raw": "First story", "markup": "markdown"},
                "state": "new",
                "priority": "minor",
                "kind": "task",
                "assignee": None,
            },
            {
                "id": 11,
                "title": "Story Beta",
                "content": {"raw": "Second story", "markup": "markdown"},
                "state": "open",
                "priority": "major",
                "kind": "enhancement",
                "assignee": {"username": "testuser"},
            },
        ],
        "page": 1,
        "pagelen": 50,
        "size": 2,
    }


@pytest.fixture
def mock_milestone_response():
    """Mock response for milestone."""
    return {
        "id": 1,
        "name": "Sprint 1",
        "description": "First sprint",
    }


@pytest.fixture
def mock_pr_response():
    """Mock response for pull request."""
    return {
        "id": 456,
        "title": "Feature PR",
        "state": "OPEN",
        "source": {"branch": {"name": "feature-branch"}},
        "destination": {"branch": {"name": "main"}},
    }


@pytest.fixture
def mock_attachments_response():
    """Mock response for issue attachments."""
    return {
        "values": [
            {
                "id": "att1",
                "name": "file1.pdf",
                "links": {"self": {"href": "https://api.bitbucket.org/2.0/attachments/att1"}},
            },
            {
                "id": "att2",
                "name": "file2.png",
                "links": {"self": {"href": "https://api.bitbucket.org/2.0/attachments/att2"}},
            },
        ]
    }


@pytest.fixture
def mock_components_response():
    """Mock response for components."""
    return {
        "values": [
            {"name": "Frontend", "id": "comp1"},
            {"name": "Backend", "id": "comp2"},
        ]
    }


@pytest.fixture
def mock_versions_response():
    """Mock response for versions."""
    return {
        "values": [
            {"name": "v1.0", "id": "ver1"},
            {"name": "v2.0", "id": "ver2"},
        ]
    }


# =============================================================================
# BitbucketApiClient Integration Tests
# =============================================================================


class TestBitbucketApiClientIntegration:
    """Integration tests for BitbucketApiClient with mocked HTTP."""

    def test_connection_test_success_cloud(
        self, bitbucket_cloud_config, mock_user_response, mock_repo_response
    ):
        """Test connection test succeeds for Cloud."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            # Mock user response
            mock_user = Mock()
            mock_user.ok = True
            mock_user.text = json.dumps(mock_user_response)
            mock_user.json.return_value = mock_user_response

            # Mock repo response
            mock_repo = Mock()
            mock_repo.ok = True
            mock_repo.text = json.dumps(mock_repo_response)
            mock_repo.json.return_value = mock_repo_response

            mock_request.side_effect = [mock_user, mock_repo]

            assert client.test_connection() is True

    def test_connection_test_success_server(
        self, bitbucket_server_config, mock_user_response, mock_repo_response
    ):
        """Test connection test succeeds for Server."""
        client = BitbucketApiClient(
            username=bitbucket_server_config["username"],
            app_password=bitbucket_server_config["app_password"],
            workspace=bitbucket_server_config["workspace"],
            repo=bitbucket_server_config["repo"],
            base_url=bitbucket_server_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_user = Mock()
            mock_user.ok = True
            mock_user.text = json.dumps(mock_user_response)
            mock_user.json.return_value = mock_user_response

            mock_repo = Mock()
            mock_repo.ok = True
            mock_repo.text = json.dumps(mock_repo_response)
            mock_repo.json.return_value = mock_repo_response

            mock_request.side_effect = [mock_user, mock_repo]

            assert client.test_connection() is True

    def test_connection_test_failure_authentication(self, bitbucket_cloud_config):
        """Test connection test returns False on authentication failure."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password="bad-password",
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_request.return_value = mock_response

            assert client.test_connection() is False

    def test_get_issue_cloud(self, bitbucket_cloud_config, mock_issue_response):
        """Test getting issue from Cloud."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_issue_response)
            mock_response.json.return_value = mock_issue_response
            mock_request.return_value = mock_response

            issue = client.get_issue(123)
            assert issue["id"] == 123
            assert issue["title"] == "Sample User Story"
            assert issue["state"] == "open"

    def test_list_issues_with_pagination(self, bitbucket_cloud_config, mock_issues_list_response):
        """Test listing issues with pagination."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_issues_list_response)
            mock_response.json.return_value = mock_issues_list_response
            mock_request.return_value = mock_response

            issues = client.list_issues(page=1, pagelen=50)
            assert len(issues) == 2
            assert issues[0]["id"] == 10
            assert issues[1]["id"] == 11

    def test_create_issue_cloud(self, bitbucket_cloud_config, mock_issue_response):
        """Test creating issue in Cloud."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_issue_response)
            mock_response.json.return_value = mock_issue_response
            mock_request.return_value = mock_response

            result = client.create_issue(
                title="New Issue",
                content="Issue description",
                kind="task",
                priority="minor",
            )
            assert result["id"] == 123
            assert mock_request.call_count == 1

    def test_get_pull_requests(self, bitbucket_cloud_config, mock_pr_response):
        """Test getting pull requests."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps({"values": [mock_pr_response]})
            mock_response.json.return_value = {"values": [mock_pr_response]}
            mock_request.return_value = mock_response

            prs = client.list_pull_requests()
            assert len(prs) == 1
            assert prs[0]["id"] == 456

    def test_get_attachments(self, bitbucket_cloud_config, mock_attachments_response):
        """Test getting issue attachments."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_attachments_response)
            mock_response.json.return_value = mock_attachments_response
            mock_request.return_value = mock_response

            attachments = client.get_issue_attachments(123)
            assert len(attachments) == 2
            assert attachments[0]["name"] == "file1.pdf"


# =============================================================================
# BitbucketAdapter Integration Tests
# =============================================================================


class TestBitbucketAdapterIntegration:
    """Integration tests for BitbucketAdapter with mocked client."""

    def test_get_issue_flow(self, bitbucket_cloud_config, mock_issue_response):
        """Test full flow of getting an issue."""
        adapter = BitbucketAdapter(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(adapter._client, "get_issue") as mock_get:
            mock_get.return_value = mock_issue_response

            issue = adapter.get_issue("#123")
            assert issue.key == "#123"
            assert issue.summary == "Sample User Story"
            assert issue.status == "open"

    def test_create_subtask_flow(self, bitbucket_cloud_config):
        """Test full flow of creating a subtask."""
        adapter = BitbucketAdapter(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(adapter._client, "create_issue") as mock_create:
            mock_create.return_value = {"id": 456}

            result = adapter.create_subtask(
                parent_key="#123",
                summary="Subtask",
                description="Description",
                project_key="TEST",
            )
            assert result == "#456"
            mock_create.assert_called_once()

    def test_link_pull_request_flow(self, bitbucket_cloud_config, mock_issue_response):
        """Test linking pull request to issue."""
        adapter = BitbucketAdapter(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with (
            patch.object(adapter._client, "get_issue") as mock_get,
            patch.object(adapter._client, "update_issue") as mock_update,
        ):
            mock_get.return_value = mock_issue_response
            mock_update.return_value = {"id": 123}

            result = adapter.link_pull_request("#123", 456)
            assert result is True
            mock_update.assert_called_once()

    def test_get_attachments_flow(self, bitbucket_cloud_config, mock_attachments_response):
        """Test getting attachments for issue."""
        adapter = BitbucketAdapter(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            dry_run=False,
        )

        with patch.object(adapter._client, "get_issue_attachments") as mock_get_attachments:
            mock_get_attachments.return_value = mock_attachments_response["values"]

            attachments = adapter.get_issue_attachments("#123")
            assert len(attachments) == 2
            assert attachments[0]["name"] == "file1.pdf"


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting behavior."""

    def test_rate_limit_enforcement(self, bitbucket_cloud_config):
        """Test that rate limiting is enforced."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            requests_per_second=1.0,  # Very low for testing (1 request per second)
            dry_run=False,
        )

        with (
            patch.object(client._session, "request") as mock_request,
            patch("time.sleep"),  # Mock sleep to avoid actual delays
            patch("time.time") as mock_time,
        ):
            # Simulate time passing - need enough values for all time.time() calls
            time_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
            mock_time.side_effect = time_values

            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps({"username": "testuser"})
            mock_response.json.return_value = {"username": "testuser"}
            mock_request.return_value = mock_response

            # Clear cache first
            client._current_user = None

            # Make multiple requests - use different endpoints to avoid caching
            client.get_authenticated_user()
            client.get(client.repo_endpoint())  # Different endpoint
            client.list_issues()  # Different endpoint

            # Verify requests were made (rate limiting may have caused delays)
            assert mock_request.call_count == 3

    def test_rate_limit_429_response(self, bitbucket_cloud_config):
        """Test handling of 429 rate limit response."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            max_retries=2,
            initial_delay=0.01,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request, patch("time.sleep"):
            # First response is 429, second succeeds
            rate_limit_response = Mock()
            rate_limit_response.status_code = 429
            rate_limit_response.ok = False
            rate_limit_response.text = "Rate limit exceeded"
            rate_limit_response.headers = {"Retry-After": "1"}

            success_response = Mock()
            success_response.ok = True
            success_response.status_code = 200
            success_response.text = json.dumps({"username": "testuser"})
            success_response.json.return_value = {"username": "testuser"}

            mock_request.side_effect = [rate_limit_response, success_response]

            # Should retry and succeed
            user = client.get_authenticated_user()
            assert user["username"] == "testuser"
            assert mock_request.call_count == 2

    def test_rate_limit_exceeded_after_retries(self, bitbucket_cloud_config):
        """Test that RateLimitError is raised after max retries."""
        client = BitbucketApiClient(
            username=bitbucket_cloud_config["username"],
            app_password=bitbucket_cloud_config["app_password"],
            workspace=bitbucket_cloud_config["workspace"],
            repo=bitbucket_cloud_config["repo"],
            base_url=bitbucket_cloud_config["base_url"],
            max_retries=1,
            initial_delay=0.01,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request, patch("time.sleep"):
            rate_limit_response = Mock()
            rate_limit_response.status_code = 429
            rate_limit_response.ok = False
            rate_limit_response.text = "Rate limit exceeded"
            rate_limit_response.headers = {"Retry-After": "60"}

            mock_request.return_value = rate_limit_response

            with pytest.raises(RateLimitError) as exc_info:
                client.get_authenticated_user()

            assert "rate limit exceeded" in str(exc_info.value).lower()
            assert exc_info.value.retry_after == 60


# =============================================================================
# Server-Specific Tests
# =============================================================================


class TestBitbucketServerIntegration:
    """Integration tests specific to Bitbucket Server."""

    def test_server_base_url(self, bitbucket_server_config):
        """Test that Server uses correct base URL."""
        adapter = BitbucketAdapter(
            username=bitbucket_server_config["username"],
            app_password=bitbucket_server_config["app_password"],
            workspace=bitbucket_server_config["workspace"],
            repo=bitbucket_server_config["repo"],
            base_url=bitbucket_server_config["base_url"],
            dry_run=True,
        )

        assert adapter._client.base_url == bitbucket_server_config["base_url"]
        assert "bitbucket.example.com" in adapter._client.base_url

    def test_server_authentication(self, bitbucket_server_config, mock_user_response):
        """Test Server authentication flow."""
        client = BitbucketApiClient(
            username=bitbucket_server_config["username"],
            app_password=bitbucket_server_config["app_password"],
            workspace=bitbucket_server_config["workspace"],
            repo=bitbucket_server_config["repo"],
            base_url=bitbucket_server_config["base_url"],
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_user_response)
            mock_response.json.return_value = mock_user_response
            mock_request.return_value = mock_response

            user = client.get_authenticated_user()
            assert user["username"] == "testuser"

            # Verify request was made to Server URL
            call_args = mock_request.call_args
            assert bitbucket_server_config["base_url"] in str(call_args)
