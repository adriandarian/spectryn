"""
Tests for Bitbucket Server client using atlassian-python-api.

These tests verify the optional integration with atlassian-python-api
for enhanced Bitbucket Server support.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.bitbucket.server_client import (
    ATLASSIAN_API_AVAILABLE,
    BitbucketServerClient,
    is_server_url,
)


# =============================================================================
# URL Detection Tests
# =============================================================================


class TestServerUrlDetection:
    """Tests for detecting Server vs Cloud URLs."""

    def test_is_server_url_cloud(self):
        """Should return False for Cloud URLs."""
        assert is_server_url("https://api.bitbucket.org/2.0") is False
        assert is_server_url("https://bitbucket.org") is False

    def test_is_server_url_server(self):
        """Should return True for Server URLs."""
        assert is_server_url("https://bitbucket.example.com/rest/api/2.0") is True
        assert is_server_url("https://server.company.com/rest/api") is True

    def test_is_server_url_custom_domain(self):
        """Should detect custom domains as Server."""
        assert is_server_url("https://git.company.com") is True


# =============================================================================
# Server Client Tests (when library available)
# =============================================================================


class TestBitbucketServerClient:
    """Tests for BitbucketServerClient."""

    @pytest.fixture
    def mock_atlassian_bitbucket(self):
        """Mock the atlassian Bitbucket class."""
        with patch("spectryn.adapters.bitbucket.server_client.Bitbucket") as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance

    def test_requires_library(self):
        """Should raise ImportError if library not available."""
        if not ATLASSIAN_API_AVAILABLE:
            with pytest.raises(ImportError) as exc_info:
                BitbucketServerClient(
                    url="https://server.example.com",
                    username="user",
                    password="pass",
                    project_key="PROJ",
                    repo_slug="repo",
                )
            assert "atlassian-python-api" in str(exc_info.value)

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_initialization(self, mock_atlassian_bitbucket):
        """Should initialize Server client when library available."""
        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )
        assert client.url == "https://server.example.com"
        assert client.project_key == "PROJ"
        assert client.repo_slug == "repo"

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_get_current_user(self, mock_atlassian_bitbucket):
        """Should get current user via library."""
        mock_atlassian_bitbucket.get_current_user.return_value = {
            "username": "testuser",
            "display_name": "Test User",
        }

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        user = client.get_current_user()
        assert user["username"] == "testuser"

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_get_issue(self, mock_atlassian_bitbucket):
        """Should get issue via library."""
        mock_atlassian_bitbucket.get_issue.return_value = {
            "id": 123,
            "title": "Test Issue",
            "state": "open",
        }

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        issue = client.get_issue(123)
        assert issue["id"] == 123
        mock_atlassian_bitbucket.get_issue.assert_called_once_with(
            project_key="PROJ", repo_slug="repo", issue_id=123
        )

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_get_issue_not_found(self, mock_atlassian_bitbucket):
        """Should raise NotFoundError when issue doesn't exist."""
        from spectryn.core.ports.issue_tracker import NotFoundError

        mock_atlassian_bitbucket.get_issue.return_value = None

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        with pytest.raises(NotFoundError):
            client.get_issue(999)

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_create_issue_dry_run(self, mock_atlassian_bitbucket):
        """Should not create issue in dry-run mode."""
        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        result = client.create_issue(title="Test", content="Description")
        assert result["id"] == 0
        mock_atlassian_bitbucket.create_issue.assert_not_called()

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_list_issues(self, mock_atlassian_bitbucket):
        """Should list issues via library."""
        mock_atlassian_bitbucket.get_issues.return_value = [
            {"id": 1, "title": "Issue 1"},
            {"id": 2, "title": "Issue 2"},
        ]

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        issues = client.list_issues(state="open", page=1, pagelen=50)
        assert len(issues) == 2
        assert issues[0]["id"] == 1

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_test_connection(self, mock_atlassian_bitbucket):
        """Should test connection via library."""
        mock_atlassian_bitbucket.get_current_user.return_value = {"username": "testuser"}

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        assert client.test_connection() is True

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_test_connection_failure(self, mock_atlassian_bitbucket):
        """Should return False on connection failure."""
        mock_atlassian_bitbucket.get_current_user.side_effect = Exception("Auth failed")

        client = BitbucketServerClient(
            url="https://server.example.com",
            username="user",
            password="pass",
            project_key="PROJ",
            repo_slug="repo",
            dry_run=True,
        )

        assert client.test_connection() is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestBitbucketClientIntegration:
    """Tests for BitbucketApiClient integration with Server client."""

    def test_client_falls_back_when_library_unavailable(self):
        """Should fall back to REST API when library not available."""
        from spectryn.adapters.bitbucket.client import BitbucketApiClient

        # Use Cloud URL (shouldn't try to use Server client)
        client = BitbucketApiClient(
            username="user",
            app_password="pass",
            workspace="workspace",
            repo="repo",
            base_url="https://api.bitbucket.org/2.0",
            dry_run=True,
        )

        # Should not have Server client
        assert not hasattr(client, "_server_client") or client._server_client is None
        assert not hasattr(client, "_use_atlassian_api") or not client._use_atlassian_api

    @pytest.mark.skipif(not ATLASSIAN_API_AVAILABLE, reason="atlassian-python-api not installed")
    def test_client_uses_library_for_server(self):
        """Should use atlassian-python-api for Server URLs when available."""
        from spectryn.adapters.bitbucket.client import BitbucketApiClient

        with patch(
            "spectryn.adapters.bitbucket.client.BitbucketServerClient"
        ) as mock_server_client_class:
            mock_server_client = MagicMock()
            mock_server_client.get_current_user.return_value = {"username": "testuser"}
            mock_server_client.test_connection.return_value = True
            mock_server_client_class.return_value = mock_server_client

            client = BitbucketApiClient(
                username="user",
                app_password="pass",
                workspace="PROJ",
                repo="repo",
                base_url="https://server.example.com/rest/api/2.0",
                dry_run=True,
            )

            # Should have initialized Server client
            assert client._use_atlassian_api is True
            assert client._server_client is not None
