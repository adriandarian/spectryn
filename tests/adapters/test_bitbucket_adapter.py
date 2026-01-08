"""
Tests for Bitbucket Issues Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.bitbucket.adapter import BitbucketAdapter
from spectryn.adapters.bitbucket.client import BitbucketApiClient
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueData,
    IssueTrackerError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# API Client Tests
# =============================================================================


class TestBitbucketApiClient:
    """Tests for BitbucketApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.bitbucket.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return BitbucketApiClient(
            username="test-user",
            app_password="test-password",
            workspace="test-workspace",
            repo="test-repo",
            dry_run=True,
        )

    def test_repo_endpoint(self, client):
        """Should construct correct repo endpoint."""
        assert client.repo_endpoint() == "repositories/test-workspace/test-repo"
        assert client.repo_endpoint("issues") == "repositories/test-workspace/test-repo/issues"

    def test_get_authenticated_user(self, client, mock_session):
        """Should get authenticated user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"username": "test-user", "display_name": "Test User"}
        mock_response.text = '{"username": "test-user"}'
        mock_session.request.return_value = mock_response

        user = client.get_authenticated_user()
        assert user["username"] == "test-user"

    def test_test_connection_success(self, client, mock_session):
        """Should return True on successful connection."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"username": "test-user"}
        mock_response.text = '{"username": "test-user"}'
        mock_session.request.return_value = mock_response

        assert client.test_connection() is True

    def test_test_connection_failure(self, client, mock_session):
        """Should return False on connection failure."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        assert client.test_connection() is False

    def test_get_issue(self, client, mock_session):
        """Should get issue by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "id": 123,
            "title": "Test Issue",
            "state": "open",
            "priority": "minor",
            "content": {"raw": "Test content"},
        }
        mock_response.text = '{"id": 123}'
        mock_session.request.return_value = mock_response

        issue = client.get_issue(123)
        assert issue["id"] == 123
        assert issue["title"] == "Test Issue"

    def test_create_issue_dry_run(self, client, mock_session):
        """Should not make request in dry-run mode."""
        result = client.create_issue(title="Test", content="Content")
        assert result == {}
        mock_session.request.assert_not_called()

    def test_list_issues(self, client, mock_session):
        """Should list issues with pagination."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "values": [
                {"id": 1, "title": "Issue 1"},
                {"id": 2, "title": "Issue 2"},
            ]
        }
        mock_response.text = '{"values": []}'
        mock_session.request.return_value = mock_response

        issues = client.list_issues()
        assert len(issues) == 2
        assert issues[0]["id"] == 1

    def test_list_pull_requests(self, client, mock_session):
        """Should list pull requests."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "values": [
                {"id": 1, "title": "PR 1", "state": "OPEN"},
                {"id": 2, "title": "PR 2", "state": "MERGED"},
            ]
        }
        mock_response.text = '{"values": []}'
        mock_session.request.return_value = mock_response

        prs = client.list_pull_requests()
        assert len(prs) == 2
        assert prs[0]["id"] == 1

    def test_get_pull_request(self, client, mock_session):
        """Should get pull request by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"id": 123, "title": "Test PR", "state": "OPEN"}
        mock_response.text = '{"id": 123}'
        mock_session.request.return_value = mock_response

        pr = client.get_pull_request(123)
        assert pr["id"] == 123
        assert pr["title"] == "Test PR"

    def test_get_issue_attachments(self, client, mock_session):
        """Should get issue attachments."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "values": [
                {"id": "att1", "name": "file.pdf"},
            ]
        }
        mock_response.text = '{"values": []}'
        mock_session.request.return_value = mock_response

        attachments = client.get_issue_attachments(123)
        assert len(attachments) == 1
        assert attachments[0]["name"] == "file.pdf"

    def test_list_components(self, client, mock_session):
        """Should list components."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"values": [{"name": "Frontend"}, {"name": "Backend"}]}
        mock_response.text = '{"values": []}'
        mock_session.request.return_value = mock_response

        components = client.list_components()
        assert len(components) == 2

    def test_list_versions(self, client, mock_session):
        """Should list versions."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"values": [{"name": "v1.0"}, {"name": "v2.0"}]}
        mock_response.text = '{"values": []}'
        mock_session.request.return_value = mock_response

        versions = client.list_versions()
        assert len(versions) == 2


# =============================================================================
# Adapter Tests
# =============================================================================


class TestBitbucketAdapter:
    """Tests for BitbucketAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        return BitbucketAdapter(
            username="test-user",
            app_password="test-password",
            workspace="test-workspace",
            repo="test-repo",
            dry_run=True,
        )

    @pytest.fixture
    def mock_client(self, adapter):
        """Mock the API client."""
        with patch.object(adapter, "_client") as mock:
            yield mock

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Bitbucket"

    def test_parse_issue_key(self, adapter):
        """Should parse various issue key formats."""
        assert adapter._parse_issue_key("123") == 123
        assert adapter._parse_issue_key("#123") == 123
        assert adapter._parse_issue_key("workspace/repo#123") == 123

    def test_parse_issue_key_invalid(self, adapter):
        """Should raise error for invalid issue key."""
        with pytest.raises(IssueTrackerError):
            adapter._parse_issue_key("invalid")

    def test_get_issue(self, adapter, mock_client):
        """Should get issue and parse correctly."""
        mock_client.get_issue.return_value = {
            "id": 123,
            "title": "Test Issue",
            "state": "open",
            "priority": "minor",
            "content": {"raw": "Test content"},
            "assignee": {"username": "test-user"},
        }

        issue = adapter.get_issue("#123")
        assert isinstance(issue, IssueData)
        assert issue.key == "#123"
        assert issue.summary == "Test Issue"
        assert issue.status == "open"

    def test_get_issue_status(self, adapter, mock_client):
        """Should get issue status."""
        mock_client.get_issue.return_value = {
            "id": 123,
            "state": "resolved",
        }

        status = adapter.get_issue_status("#123")
        assert status == "done"

    def test_update_issue_description_dry_run(self, adapter, mock_client):
        """Should not update in dry-run mode."""
        result = adapter.update_issue_description("#123", "New description")
        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_transition_issue(self, adapter, mock_client):
        """Should transition issue to new status."""
        adapter._dry_run = False
        mock_client.update_issue.return_value = {"id": 123}

        result = adapter.transition_issue("#123", "done")
        assert result is True
        mock_client.update_issue.assert_called_once_with(123, state="resolved")

    def test_transition_issue_error(self, adapter, mock_client):
        """Should raise TransitionError on failure."""
        adapter._dry_run = False
        mock_client.update_issue.side_effect = Exception("API Error")

        with pytest.raises(TransitionError):
            adapter.transition_issue("#123", "done")

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create subtask in dry-run mode."""
        result = adapter.create_subtask(
            parent_key="#100",
            summary="Subtask",
            description="Description",
            project_key="TEST",
        )
        assert result is None
        mock_client.create_issue.assert_not_called()

    def test_add_comment_dry_run(self, adapter, mock_client):
        """Should not add comment in dry-run mode."""
        result = adapter.add_comment("#123", "Comment text")
        assert result is True
        mock_client.add_issue_comment.assert_not_called()

    def test_format_description(self, adapter):
        """Should return markdown as-is."""
        markdown = "# Title\n\nContent"
        result = adapter.format_description(markdown)
        assert result == markdown

    def test_get_available_transitions(self, adapter):
        """Should return available transitions."""
        transitions = adapter.get_available_transitions("#123")
        assert len(transitions) > 0
        assert all("id" in t and "name" in t for t in transitions)

    def test_parse_issue_with_story_points(self, adapter):
        """Should parse story points from content."""
        data = {
            "id": 123,
            "title": "Test",
            "state": "open",
            "priority": "minor",
            "content": {"raw": "Story Points: 5\n\nDescription"},
        }

        issue = adapter._parse_issue(data)
        assert issue.story_points == 5.0

    def test_parse_issue_without_story_points(self, adapter):
        """Should handle missing story points."""
        data = {
            "id": 123,
            "title": "Test",
            "state": "open",
            "priority": "minor",
            "content": {"raw": "Description"},
        }

        issue = adapter._parse_issue(data)
        assert issue.story_points is None

    def test_get_epic_children_milestone(self, adapter, mock_client):
        """Should get children from milestone."""
        mock_client.get_milestone.return_value = {"id": 1, "name": "Epic 1"}
        mock_client.list_issues.return_value = [
            {
                "id": 100,
                "title": "Story 1",
                "state": "open",
                "priority": "minor",
                "content": {"raw": "Epic 1"},
            }
        ]

        children = adapter.get_epic_children("1")
        assert len(children) == 1
        assert children[0].key == "#100"

    def test_search_issues(self, adapter, mock_client):
        """Should search issues."""
        mock_client.list_issues.return_value = [
            {
                "id": 1,
                "title": "Issue 1",
                "state": "open",
                "priority": "minor",
                "content": {"raw": ""},
            }
        ]

        issues = adapter.search_issues('state="open"', max_results=10)
        assert len(issues) == 1
        assert issues[0].key == "#1"

    # -------------------------------------------------------------------------
    # Advanced Features Tests
    # -------------------------------------------------------------------------

    def test_link_pull_request(self, adapter, mock_client):
        """Should link pull request to issue."""
        adapter._dry_run = False
        mock_client.get_issue.return_value = {
            "id": 123,
            "content": {"raw": "Issue content"},
        }
        mock_client.update_issue.return_value = {"id": 123}
        mock_client.link_pull_request_to_issue.return_value = True

        result = adapter.link_pull_request("#123", 456)
        assert result is True
        mock_client.link_pull_request_to_issue.assert_called_once_with(123, 456)

    def test_link_pull_request_dry_run(self, adapter, mock_client):
        """Should not link PR in dry-run mode."""
        result = adapter.link_pull_request("#123", 456)
        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_get_pull_requests_for_issue(self, adapter, mock_client):
        """Should get pull requests linked to issue."""
        mock_client.get_issue.return_value = {
            "id": 123,
            "content": {"raw": "Issue content\n\n**Pull Requests:** PR #456"},
        }
        mock_client.get_pull_request.return_value = {
            "id": 456,
            "title": "Test PR",
            "state": "OPEN",
        }

        prs = adapter.get_pull_requests_for_issue("#123")
        assert len(prs) == 1
        assert prs[0]["id"] == 456

    def test_get_issue_attachments(self, adapter, mock_client):
        """Should get attachments for issue."""
        mock_client.get_issue_attachments.return_value = [
            {"id": "att1", "name": "file1.pdf", "links": {"self": {"href": "url1"}}},
            {"id": "att2", "name": "file2.png", "links": {"self": {"href": "url2"}}},
        ]

        attachments = adapter.get_issue_attachments("#123")
        assert len(attachments) == 2
        assert attachments[0]["name"] == "file1.pdf"

    def test_upload_attachment_dry_run(self, adapter, mock_client):
        """Should not upload attachment in dry-run mode."""
        result = adapter.upload_attachment("#123", "/path/to/file.pdf")
        assert result["id"] == "attachment:dry-run"
        mock_client.upload_issue_attachment.assert_not_called()

    def test_delete_attachment(self, adapter, mock_client):
        """Should delete attachment."""
        adapter._dry_run = False
        mock_client.delete_issue_attachment.return_value = True

        result = adapter.delete_attachment("#123", "att1")
        assert result is True
        mock_client.delete_issue_attachment.assert_called_once_with(123, "att1")

    def test_delete_attachment_dry_run(self, adapter, mock_client):
        """Should not delete attachment in dry-run mode."""
        result = adapter.delete_attachment("#123", "att1")
        assert result is True
        mock_client.delete_issue_attachment.assert_not_called()

    def test_list_components(self, adapter, mock_client):
        """Should list components."""
        mock_client.list_components.return_value = [
            {"name": "Frontend", "id": "comp1"},
            {"name": "Backend", "id": "comp2"},
        ]

        components = adapter.list_components()
        assert len(components) == 2
        assert components[0]["name"] == "Frontend"

    def test_list_versions(self, adapter, mock_client):
        """Should list versions."""
        mock_client.list_versions.return_value = [
            {"name": "v1.0", "id": "ver1"},
            {"name": "v2.0", "id": "ver2"},
        ]

        versions = adapter.list_versions()
        assert len(versions) == 2
        assert versions[0]["name"] == "v1.0"

    def test_update_issue_with_metadata(self, adapter, mock_client):
        """Should update issue component and version."""
        adapter._dry_run = False
        mock_client.update_issue.return_value = {"id": 123}

        result = adapter.update_issue_with_metadata("#123", component="Frontend", version="v1.0")
        assert result is True
        mock_client.update_issue.assert_called_once_with(123, component="Frontend", version="v1.0")

    def test_update_issue_with_metadata_dry_run(self, adapter, mock_client):
        """Should not update metadata in dry-run mode."""
        result = adapter.update_issue_with_metadata("#123", component="Frontend")
        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_create_subtask_with_metadata(self, adapter, mock_client):
        """Should create subtask with component and version."""
        adapter._dry_run = False
        mock_client.create_issue.return_value = {"id": 456}

        result = adapter.create_subtask(
            parent_key="#123",
            summary="Subtask",
            description="Description",
            project_key="TEST",
            component="Frontend",
            version="v1.0",
        )
        assert result == "#456"
        mock_client.create_issue.assert_called_once()
        call_kwargs = mock_client.create_issue.call_args[1]
        assert call_kwargs.get("component") == "Frontend"
        assert call_kwargs.get("version") == "v1.0"
