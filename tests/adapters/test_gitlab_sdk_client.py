"""
Tests for GitLabSdkClient (optional python-gitlab SDK support).

These tests verify that the SDK client wrapper works correctly when
python-gitlab is available, and handles gracefully when it's not.
"""

import pytest

from spectryn.adapters.gitlab.sdk_client import GITLAB_SDK_AVAILABLE, GitLabSdkClient


class TestGitLabSdkClientAvailability:
    """Tests for SDK availability detection."""

    def test_sdk_availability_check(self):
        """Should detect if python-gitlab is available."""
        # This will be False if python-gitlab is not installed
        assert isinstance(GITLAB_SDK_AVAILABLE, bool)

    def test_sdk_client_import_error_when_not_installed(self):
        """Should raise ImportError when SDK is not available and use_sdk=True."""
        if not GITLAB_SDK_AVAILABLE:
            with pytest.raises(ImportError, match="python-gitlab SDK is not installed"):
                GitLabSdkClient(
                    token="test",
                    project_id="123",
                )


@pytest.mark.skipif(not GITLAB_SDK_AVAILABLE, reason="python-gitlab SDK not installed")
class TestGitLabSdkClient:
    """Tests for GitLabSdkClient when SDK is available."""

    @pytest.fixture
    def mock_gitlab(self):
        """Mock gitlab module."""
        from unittest.mock import MagicMock, patch

        with patch("spectryn.adapters.gitlab.sdk_client.gitlab") as mock:
            mock_gitlab_instance = MagicMock()
            mock.Gitlab.return_value = mock_gitlab_instance

            # Mock user
            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.username = "testuser"
            mock_user.name = "Test User"
            mock_user.email = "test@example.com"
            mock_gitlab_instance.user = mock_user

            # Mock project
            mock_project = MagicMock()
            mock_project.id = 12345
            mock_gitlab_instance.projects.get.return_value = mock_project
            mock_gitlab_instance.projects.get.return_value.id = 12345

            yield mock_gitlab_instance, mock_project

    def test_initialization(self, mock_gitlab):
        """Should initialize SDK client."""
        _mock_gl, _mock_project = mock_gitlab
        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        assert client.project_id == "123"
        assert client.dry_run is True

    def test_get_authenticated_user(self, mock_gitlab):
        """Should get authenticated user."""
        _mock_gl, _mock_project = mock_gitlab
        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        user = client.get_authenticated_user()
        assert user["username"] == "testuser"

    def test_get_issue(self, mock_gitlab):
        """Should get issue using SDK."""
        _mock_gl, mock_project = mock_gitlab
        mock_issue = MagicMock()
        mock_issue.iid = 123
        mock_issue.id = 456789
        mock_issue.title = "Test Issue"
        mock_issue.description = "Description"
        mock_issue.state = "opened"
        mock_issue.labels = ["bug"]
        mock_issue.assignees = [{"username": "user1", "id": 1}]
        mock_issue.weight = 5
        mock_issue.milestone = None
        mock_project.issues.get.return_value = mock_issue

        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        result = client.get_issue(123)

        assert result["iid"] == 123
        assert result["title"] == "Test Issue"
        assert result["weight"] == 5

    def test_create_issue_dry_run(self, mock_gitlab):
        """Should not create issue in dry-run mode."""
        _mock_gl, mock_project = mock_gitlab
        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        result = client.create_issue(title="Test", description="Desc")
        assert result == {}
        mock_project.issues.create.assert_not_called()

    def test_list_labels(self, mock_gitlab):
        """Should list labels using SDK."""
        _mock_gl, mock_project = mock_gitlab
        mock_label = MagicMock()
        mock_label.name = "bug"
        mock_label.color = "#ff0000"
        mock_label.description = "Bug label"
        mock_project.labels.list.return_value = [mock_label]

        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        result = client.list_labels()

        assert len(result) == 1
        assert result[0]["name"] == "bug"

    def test_test_connection(self, mock_gitlab):
        """Should test connection."""
        _mock_gl, _mock_project = mock_gitlab
        client = GitLabSdkClient(token="test", project_id="123", dry_run=True)
        assert client.test_connection() is True
