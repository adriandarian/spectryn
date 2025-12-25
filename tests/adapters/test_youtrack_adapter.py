"""
Tests for YouTrack Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.youtrack.adapter import YouTrackAdapter
from spectra.adapters.youtrack.client import YouTrackApiClient
from spectra.core.ports.config_provider import YouTrackConfig
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# API Client Tests
# =============================================================================


class TestYouTrackApiClient:
    """Tests for YouTrackApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=True,
        )

    def test_get_current_user(self, client, mock_session):
        """Should get current user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"login": "testuser", "name": "Test User"}
        mock_response.text = '{"login": "testuser"}'
        mock_session.request.return_value = mock_response

        user = client.get_current_user()
        assert user["login"] == "testuser"

    def test_get_issue(self, client, mock_session):
        """Should get an issue by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "idReadable": "PROJ-123",
            "summary": "Test Issue",
            "description": "Test description",
        }
        mock_response.text = '{"idReadable": "PROJ-123"}'
        mock_session.request.return_value = mock_response

        issue = client.get_issue("PROJ-123")
        assert issue["idReadable"] == "PROJ-123"
        assert issue["summary"] == "Test Issue"

    def test_create_issue(self, client, mock_session):
        """Should create an issue (dry-run mode)."""
        # In dry-run mode, should log but not make request
        result = client.create_issue(
            project_id="PROJ",
            summary="Test Issue",
            issue_type="Task",
        )
        # Dry-run returns empty dict
        assert result == {}

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get("issues/PROJ-123")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get("issues/PROJ-999")

    def test_test_connection(self, client, mock_session):
        """Should test connection successfully."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"login": "testuser"}
        mock_response.text = '{"login": "testuser"}'
        mock_session.request.return_value = mock_response

        assert client.test_connection() is True


# =============================================================================
# Adapter Tests
# =============================================================================


class TestYouTrackAdapter:
    """Tests for YouTrackAdapter."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectra.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=True)

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "YouTrack"

    def test_is_connected(self, adapter, mock_client):
        """Should check connection status."""
        mock_client.is_connected = True
        assert adapter.is_connected is True

    def test_test_connection(self, adapter, mock_client):
        """Should test connection."""
        mock_client.test_connection.return_value = True
        assert adapter.test_connection() is True

    def test_get_current_user(self, adapter, mock_client):
        """Should get current user."""
        mock_client.get_current_user.return_value = {"login": "testuser"}
        user = adapter.get_current_user()
        assert user["login"] == "testuser"

    def test_get_issue(self, adapter, mock_client):
        """Should get an issue."""
        mock_client.get_issue.return_value = {
            "idReadable": "PROJ-123",
            "summary": "Test Issue",
            "description": "Test description",
            "type": {"name": "Task"},
            "customFields": [],
        }
        mock_client.get_issue_comments.return_value = []

        issue = adapter.get_issue("PROJ-123")
        assert issue.key == "PROJ-123"
        assert issue.summary == "Test Issue"

    def test_get_epic_children(self, adapter, mock_client):
        """Should get epic children."""
        mock_client.get_epic_children.return_value = [
            {
                "idReadable": "PROJ-124",
                "summary": "Child Issue",
                "type": {"name": "Task"},
                "customFields": [],
            }
        ]
        mock_client.get_issue_comments.return_value = []

        children = adapter.get_epic_children("PROJ-123")
        assert len(children) == 1
        assert children[0].key == "PROJ-124"

    def test_update_issue_description(self, adapter, mock_client):
        """Should update issue description."""
        mock_client.update_issue.return_value = {}
        result = adapter.update_issue_description("PROJ-123", "New description")
        assert result is True

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update story points."""
        adapter.config.story_points_field = "Story Points"
        mock_client.update_issue.return_value = {}
        result = adapter.update_issue_story_points("PROJ-123", 5.0)
        assert result is True

    def test_create_subtask(self, adapter, mock_client):
        """Should create a subtask."""
        # In dry-run mode, returns mock ID
        result = adapter.create_subtask(
            parent_key="PROJ-123",
            summary="Subtask",
            description="Subtask description",
            project_key="PROJ",
        )
        assert result == "PROJ-123-subtask"

    def test_create_subtask_not_dry_run(self, config, mock_client):
        """Should create a subtask in non-dry-run mode."""
        adapter = YouTrackAdapter(config=config, dry_run=False)
        mock_client.create_issue.return_value = {"idReadable": "PROJ-125"}
        mock_client.create_link.return_value = {}

        result = adapter.create_subtask(
            parent_key="PROJ-123",
            summary="Subtask",
            description="Subtask description",
            project_key="PROJ",
        )
        assert result == "PROJ-125"

    def test_add_comment(self, adapter, mock_client):
        """Should add a comment."""
        mock_client.add_comment.return_value = {}
        result = adapter.add_comment("PROJ-123", "Test comment")
        assert result is True

    def test_transition_issue(self, adapter, mock_client):
        """Should transition an issue."""
        mock_client.get_available_states.return_value = [
            {"name": "Open"},
            {"name": "In Progress"},
            {"name": "Done"},
        ]
        mock_client.transition_issue.return_value = {}

        result = adapter.transition_issue("PROJ-123", "In Progress")
        assert result is True

    def test_transition_issue_error(self, config, mock_client):
        """Should raise TransitionError on failure."""
        adapter = YouTrackAdapter(config=config, dry_run=False)
        mock_client.get_available_states.return_value = []
        mock_client.transition_issue.side_effect = NotFoundError(
            "State not found", issue_key="PROJ-123"
        )

        with pytest.raises(TransitionError):
            adapter.transition_issue("PROJ-123", "Invalid State")

    def test_get_issue_links(self, adapter, mock_client):
        """Should get issue links."""
        mock_client.get_issue_links.return_value = [
            {
                "linkType": {"name": "depends on"},
                "target": {"idReadable": "PROJ-124"},
            }
        ]

        links = adapter.get_issue_links("PROJ-123")
        assert len(links) == 1
        assert links[0].target_key == "PROJ-124"

    def test_create_link(self, adapter, mock_client):
        """Should create a link."""
        from spectra.core.ports.issue_tracker import LinkType

        mock_client.create_link.return_value = {}
        result = adapter.create_link("PROJ-123", "PROJ-124", LinkType.DEPENDS_ON)
        assert result is True

    def test_search_issues(self, adapter, mock_client):
        """Should search for issues."""
        mock_client.search_issues.return_value = [
            {
                "idReadable": "PROJ-123",
                "summary": "Test Issue",
                "type": {"name": "Task"},
                "customFields": [],
            }
        ]
        mock_client.get_issue_comments.return_value = []

        issues = adapter.search_issues("project: PROJ", max_results=10)
        assert len(issues) == 1
        assert issues[0].key == "PROJ-123"

    def test_format_description(self, adapter):
        """Should format description (YouTrack uses Markdown)."""
        markdown = "# Title\n\nDescription"
        result = adapter.format_description(markdown)
        assert result == markdown

    def test_get_available_transitions(self, adapter, mock_client):
        """Should get available transitions."""
        mock_client.get_available_states.return_value = [
            {"name": "Open"},
            {"name": "In Progress"},
            {"name": "Done"},
        ]

        transitions = adapter.get_available_transitions("PROJ-123")
        assert len(transitions) == 3
        assert transitions[0]["name"] == "Open"

    def test_extract_status(self, adapter):
        """Should extract status from issue data."""
        data = {
            "customFields": [
                {"name": "State", "value": {"name": "In Progress"}},
            ]
        }
        status = adapter._extract_status(data)
        assert status == "In Progress"

    def test_extract_story_points(self, adapter):
        """Should extract story points from issue data."""
        adapter.config.story_points_field = "Story Points"
        data = {
            "customFields": [
                {"name": "Story Points", "value": 5.0},
            ]
        }
        points = adapter._extract_story_points(data)
        assert points == 5.0

    def test_map_status_to_youtrack_state(self, adapter, mock_client):
        """Should map status to YouTrack state."""
        mock_client.get_available_states.return_value = [
            {"name": "Open"},
            {"name": "In Progress"},
            {"name": "Done"},
        ]

        state = adapter._map_status_to_youtrack_state("done")
        assert state == "Done"

        state = adapter._map_status_to_youtrack_state("in progress")
        assert state == "In Progress"

    def test_map_priority_to_youtrack(self, adapter, mock_client):
        """Should map priority to YouTrack priority."""
        mock_client.get_available_priorities.return_value = [
            {"name": "Critical"},
            {"name": "High"},
            {"name": "Normal"},
            {"name": "Low"},
        ]

        priority = adapter._map_priority_to_youtrack("critical")
        assert priority == "Critical"

        priority = adapter._map_priority_to_youtrack("high")
        assert priority == "High"
