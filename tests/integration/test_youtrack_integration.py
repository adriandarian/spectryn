"""
Integration tests with mocked YouTrack API responses.

These tests verify the full flow from adapter through client
using realistic API responses.
"""

import json
from unittest.mock import Mock, patch

import pytest

from spectryn.adapters.youtrack.adapter import YouTrackAdapter
from spectryn.core.ports.config_provider import YouTrackConfig
from spectryn.core.ports.issue_tracker import IssueTrackerError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def youtrack_config():
    """YouTrack adapter configuration."""
    return YouTrackConfig(
        url="https://test.youtrack.com",
        token="test-token-12345",
        project_id="PROJ",
        story_points_field="Story Points",
    )


@pytest.fixture
def mock_user_response():
    """Mock response for authenticated user."""
    return {
        "login": "testuser",
        "id": "user-123",
        "name": "Test User",
        "email": "test@example.com",
    }


@pytest.fixture
def mock_issue_response():
    """Mock response for YouTrack issue GET."""
    return {
        "idReadable": "PROJ-123",
        "id": "123-456-789",
        "summary": "Sample User Story",
        "description": "**As a** developer\n**I want** a feature\n**So that** I can test",
        "type": {"name": "Task"},
        "customFields": [
            {"name": "State", "value": {"name": "Open"}},
            {"name": "Priority", "value": {"name": "Normal"}},
            {"name": "Story Points", "value": 5},
        ],
        "assignee": {"login": "testuser", "name": "Test User"},
        "links": [],
    }


@pytest.fixture
def mock_issues_list_response():
    """Mock response for listing issues."""
    return [
        {
            "idReadable": "PROJ-10",
            "summary": "Story Alpha",
            "description": "First story",
            "type": {"name": "Task"},
            "customFields": [{"name": "State", "value": {"name": "Open"}}],
            "assignee": None,
        },
        {
            "idReadable": "PROJ-11",
            "summary": "Story Beta",
            "description": "Second story",
            "type": {"name": "Task"},
            "customFields": [{"name": "State", "value": {"name": "In Progress"}}],
            "assignee": {"login": "testuser"},
        },
    ]


@pytest.fixture
def mock_states_response():
    """Mock response for available states."""
    return [
        {"name": "Open", "id": "state-open"},
        {"name": "In Progress", "id": "state-in-progress"},
        {"name": "Done", "id": "state-done"},
    ]


@pytest.fixture
def mock_priorities_response():
    """Mock response for available priorities."""
    return [
        {"name": "Critical", "id": "priority-critical"},
        {"name": "High", "id": "priority-high"},
        {"name": "Normal", "id": "priority-normal"},
        {"name": "Low", "id": "priority-low"},
    ]


# =============================================================================
# Integration Tests
# =============================================================================


class TestYouTrackIntegration:
    """Integration tests for YouTrack adapter."""

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_get_current_user(self, mock_session, youtrack_config, mock_user_response):
        """Test getting current authenticated user."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = mock_user_response
        mock_response.text = json.dumps(mock_user_response)
        mock_session.return_value.request.return_value = mock_response

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        user = adapter.get_current_user()

        assert user["login"] == "testuser"
        assert user["email"] == "test@example.com"

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_get_issue(self, mock_session, youtrack_config, mock_issue_response):
        """Test getting a single issue."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = mock_issue_response
        mock_response.text = json.dumps(mock_issue_response)
        mock_session.return_value.request.return_value = mock_response

        # Mock comments endpoint
        comments_response = Mock()
        comments_response.ok = True
        comments_response.json.return_value = []
        comments_response.text = "[]"

        def side_effect(*args, **kwargs):
            endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint", "")
            if "comments" in endpoint:
                return comments_response
            return mock_response

        mock_session.return_value.request.side_effect = side_effect

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        issue = adapter.get_issue("PROJ-123")

        assert issue.key == "PROJ-123"
        assert issue.summary == "Sample User Story"
        assert issue.status == "Open"
        assert issue.story_points == 5

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_search_issues(self, mock_session, youtrack_config, mock_issues_list_response):
        """Test searching for issues."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = mock_issues_list_response
        mock_response.text = json.dumps(mock_issues_list_response)

        # Mock comments for each issue
        comments_response = Mock()
        comments_response.ok = True
        comments_response.json.return_value = []
        comments_response.text = "[]"

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint", "")
            if "comments" in endpoint:
                return comments_response
            call_count += 1
            return mock_response

        mock_session.return_value.request.side_effect = side_effect

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        issues = adapter.search_issues("project: PROJ", max_results=10)

        assert len(issues) == 2
        assert issues[0].key == "PROJ-10"
        assert issues[1].key == "PROJ-11"

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_create_subtask(self, mock_session, youtrack_config, mock_issue_response):
        """Test creating a subtask."""
        # Mock issue creation response
        create_response = Mock()
        create_response.ok = True
        create_response.json.return_value = {"idReadable": "PROJ-125"}
        create_response.text = json.dumps({"idReadable": "PROJ-125"})

        # Mock link creation response
        link_response = Mock()
        link_response.ok = True
        link_response.json.return_value = {}
        link_response.text = "{}"

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            method = args[0] if args else kwargs.get("method", "GET")
            endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint", "")

            if method == "POST" and "issues" in endpoint and "links" not in endpoint:
                return create_response
            if method == "POST" and "links" in endpoint:
                return link_response
            return Mock(ok=True, json=dict, text="{}")

        mock_session.return_value.request.side_effect = side_effect

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        subtask_id = adapter.create_subtask(
            parent_key="PROJ-123",
            summary="Subtask",
            description="Subtask description",
            project_key="PROJ",
            story_points=3,
        )

        assert subtask_id == "PROJ-125"

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_update_issue_description(self, mock_session, youtrack_config, mock_issue_response):
        """Test updating issue description."""
        update_response = Mock()
        update_response.ok = True
        update_response.json.return_value = mock_issue_response
        update_response.text = json.dumps(mock_issue_response)

        mock_session.return_value.request.return_value = update_response

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        result = adapter.update_issue_description("PROJ-123", "Updated description")

        assert result is True

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_add_comment(self, mock_session, youtrack_config):
        """Test adding a comment."""
        comment_response = Mock()
        comment_response.ok = True
        comment_response.json.return_value = {"id": "comment-123"}
        comment_response.text = json.dumps({"id": "comment-123"})

        mock_session.return_value.request.return_value = comment_response

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        result = adapter.add_comment("PROJ-123", "Test comment")

        assert result is True

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_transition_issue(self, mock_session, youtrack_config, mock_states_response):
        """Test transitioning an issue."""
        transition_response = Mock()
        transition_response.ok = True
        transition_response.json.return_value = {}
        transition_response.text = "{}"

        states_response = Mock()
        states_response.ok = True
        states_response.json.return_value = mock_states_response
        states_response.text = json.dumps(mock_states_response)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint", "")
            if "customFields/State" in endpoint:
                return states_response
            call_count += 1
            return transition_response

        mock_session.return_value.request.side_effect = side_effect

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        result = adapter.transition_issue("PROJ-123", "In Progress")

        assert result is True

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_get_epic_children(self, mock_session, youtrack_config, mock_issues_list_response):
        """Test getting epic children."""
        search_response = Mock()
        search_response.ok = True
        search_response.json.return_value = mock_issues_list_response
        search_response.text = json.dumps(mock_issues_list_response)

        comments_response = Mock()
        comments_response.ok = True
        comments_response.json.return_value = []
        comments_response.text = "[]"

        def side_effect(*args, **kwargs):
            endpoint = args[1] if len(args) > 1 else kwargs.get("endpoint", "")
            if "comments" in endpoint:
                return comments_response
            return search_response

        mock_session.return_value.request.side_effect = side_effect

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)
        children = adapter.get_epic_children("PROJ-123")

        assert len(children) == 2
        assert children[0].key == "PROJ-10"
        assert children[1].key == "PROJ-11"

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_error_handling_authentication(self, mock_session, youtrack_config):
        """Test authentication error handling."""
        error_response = Mock()
        error_response.ok = False
        error_response.status_code = 401
        error_response.text = "Unauthorized"

        mock_session.return_value.request.return_value = error_response

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)

        with pytest.raises(IssueTrackerError):
            adapter.get_current_user()

    @patch("spectryn.adapters.youtrack.client.requests.Session")
    def test_error_handling_not_found(self, mock_session, youtrack_config):
        """Test not found error handling."""
        error_response = Mock()
        error_response.ok = False
        error_response.status_code = 404
        error_response.text = "Not Found"

        mock_session.return_value.request.return_value = error_response

        adapter = YouTrackAdapter(config=youtrack_config, dry_run=False)

        with pytest.raises(IssueTrackerError):
            adapter.get_issue("PROJ-999")
