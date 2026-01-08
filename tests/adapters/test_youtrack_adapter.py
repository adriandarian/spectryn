"""
Tests for YouTrack Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.youtrack.adapter import YouTrackAdapter
from spectryn.adapters.youtrack.client import YouTrackApiClient
from spectryn.core.ports.config_provider import YouTrackConfig
from spectryn.core.ports.issue_tracker import (
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
        with patch("spectryn.adapters.youtrack.client.requests.Session") as mock:
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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
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
        from spectryn.core.ports.issue_tracker import LinkType

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


# =============================================================================
# Custom Fields Tests
# =============================================================================


class TestYouTrackCustomFields:
    """Tests for YouTrack custom fields operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_project_custom_fields(self, adapter, mock_client):
        """Should get project custom field definitions."""
        mock_client.get_project_custom_fields.return_value = [
            {
                "id": "field1",
                "name": "Priority",
                "field": {
                    "name": "Priority",
                    "fieldType": {"presentation": "enum[Priority]"},
                },
            },
            {
                "id": "field2",
                "name": "Story Points",
                "field": {
                    "name": "Story Points",
                    "fieldType": {"presentation": "integer"},
                },
            },
        ]

        fields = adapter.get_project_custom_fields()

        assert len(fields) == 2
        assert fields[0]["name"] == "Priority"
        assert fields[0]["field_type"] == "enum[Priority]"
        assert fields[1]["name"] == "Story Points"
        mock_client.get_project_custom_fields.assert_called_once_with("PROJ")

    def test_get_issue_custom_fields(self, adapter, mock_client):
        """Should get issue custom field values."""
        mock_client.get_issue_custom_fields.return_value = [
            {
                "id": "field1",
                "name": "Priority",
                "value": {"name": "High"},
                "$type": "EnumBundleElement",
            },
            {
                "id": "field2",
                "name": "Story Points",
                "value": 5,
                "$type": "SimpleValue",
            },
            {
                "id": "field3",
                "name": "Assignee",
                "value": {"login": "john.doe"},
                "$type": "User",
            },
        ]

        fields = adapter.get_issue_custom_fields("PROJ-123")

        assert len(fields) == 3
        assert fields[0]["name"] == "Priority"
        assert fields[0]["value"] == "High"
        assert fields[1]["name"] == "Story Points"
        assert fields[1]["value"] == 5
        assert fields[2]["name"] == "Assignee"
        assert fields[2]["value"] == "john.doe"

    def test_get_issue_custom_field(self, adapter, mock_client):
        """Should get a specific custom field value."""
        mock_client.get_issue_custom_fields.return_value = [
            {
                "id": "field1",
                "name": "Priority",
                "value": {"name": "High"},
                "$type": "EnumBundleElement",
            },
        ]

        value = adapter.get_issue_custom_field("PROJ-123", "Priority")

        assert value == "High"

    def test_get_issue_custom_field_not_found(self, adapter, mock_client):
        """Should return None for non-existent field."""
        mock_client.get_issue_custom_fields.return_value = []

        value = adapter.get_issue_custom_field("PROJ-123", "NonExistent")

        assert value is None

    def test_update_issue_custom_field(self, adapter, mock_client):
        """Should update a custom field value."""
        mock_client.update_issue_custom_field.return_value = {"id": "field1"}

        result = adapter.update_issue_custom_field("PROJ-123", "Priority", "High")

        assert result is True
        mock_client.update_issue_custom_field.assert_called_once_with(
            "PROJ-123", "Priority", "High"
        )

    def test_update_issue_custom_field_dry_run(self, config):
        """Should not update in dry run mode."""
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = YouTrackAdapter(config=config, dry_run=True)

        result = adapter.update_issue_custom_field("PROJ-123", "Priority", "High")

        assert result is True
        mock_client.update_issue_custom_field.assert_not_called()

    def test_get_custom_field_options(self, adapter, mock_client):
        """Should get available options for enum field."""
        mock_client.get_project_custom_fields.return_value = [
            {
                "id": "field1",
                "name": "Priority",
                "field": {
                    "name": "Priority",
                    "fieldType": {"id": "EnumBundleElement"},
                    "bundle": {"id": "priority-bundle"},
                },
            },
        ]
        mock_client.get_custom_field_bundle.return_value = {
            "id": "priority-bundle",
            "name": "Priority",
            "values": [
                {"id": "1", "name": "Critical", "description": "Urgent"},
                {"id": "2", "name": "High", "description": "Important"},
                {"id": "3", "name": "Normal", "description": "Standard"},
            ],
        }

        options = adapter.get_custom_field_options("Priority")

        assert len(options) == 3
        assert options[0]["name"] == "Critical"
        assert options[1]["name"] == "High"
        assert options[2]["name"] == "Normal"


class TestYouTrackApiClientCustomFields:
    """Tests for YouTrack API client custom field methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectryn.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        from spectryn.adapters.youtrack.client import YouTrackApiClient

        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
        )

    def test_get_project_custom_fields(self, client, mock_session):
        """Should get project custom fields."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "field1", "name": "Priority"},
        ]
        mock_session.request.return_value = mock_response

        fields = client.get_project_custom_fields("PROJ")

        assert len(fields) == 1
        assert fields[0]["name"] == "Priority"

    def test_get_issue_custom_fields(self, client, mock_session):
        """Should get issue custom fields."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "field1", "name": "Priority", "value": {"name": "High"}},
        ]
        mock_session.request.return_value = mock_response

        fields = client.get_issue_custom_fields("PROJ-123")

        assert len(fields) == 1
        assert fields[0]["name"] == "Priority"

    def test_get_issue_custom_field(self, client, mock_session):
        """Should get specific custom field."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "field1", "name": "Priority", "value": {"name": "High"}},
            {"id": "field2", "name": "Status", "value": {"name": "Open"}},
        ]
        mock_session.request.return_value = mock_response

        field = client.get_issue_custom_field("PROJ-123", "Priority")

        assert field is not None
        assert field["name"] == "Priority"

    def test_update_issue_custom_field(self, client, mock_session):
        """Should update custom field."""
        # First call returns fields for lookup
        fields_response = MagicMock()
        fields_response.ok = True
        fields_response.status_code = 200
        fields_response.json.return_value = [
            {"id": "field1", "name": "Priority", "$type": "EnumBundleElement"},
        ]

        # Second call is the update
        update_response = MagicMock()
        update_response.ok = True
        update_response.status_code = 200
        update_response.json.return_value = {"id": "field1"}

        mock_session.request.side_effect = [fields_response, update_response]

        result = client.update_issue_custom_field("PROJ-123", "Priority", "High")

        assert result["id"] == "field1"

    def test_get_custom_field_bundle(self, client, mock_session):
        """Should get custom field bundle."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "priority-bundle",
            "values": [{"name": "High"}, {"name": "Low"}],
        }
        mock_session.request.return_value = mock_response

        bundle = client.get_custom_field_bundle("enum", "priority-bundle")

        assert bundle["id"] == "priority-bundle"
        assert len(bundle["values"]) == 2


# =============================================================================
# Bulk Operations Tests
# =============================================================================


class TestYouTrackBulkOperations:
    """Tests for YouTrack bulk operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_bulk_create_issues(self, adapter, mock_client):
        """Should create multiple issues."""
        mock_client.bulk_create_issues.return_value = [
            {"id": "1", "idReadable": "PROJ-1"},
            {"id": "2", "idReadable": "PROJ-2"},
        ]

        issues = [
            {"summary": "Issue 1", "description": "Desc 1"},
            {"summary": "Issue 2", "description": "Desc 2"},
        ]
        results = adapter.bulk_create_issues(issues)

        assert len(results) == 2
        assert results[0]["key"] == "PROJ-1"
        assert results[1]["key"] == "PROJ-2"

    def test_bulk_create_issues_dry_run(self, config):
        """Should not create in dry run mode."""
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = YouTrackAdapter(config=config, dry_run=True)

        results = adapter.bulk_create_issues([{"summary": "Test"}])

        assert len(results) == 1
        assert results[0]["status"] == "dry-run"
        mock_client.bulk_create_issues.assert_not_called()

    def test_bulk_update_issues(self, adapter, mock_client):
        """Should update multiple issues."""
        mock_client.bulk_update_issues.return_value = [
            {"id": "PROJ-1", "status": "updated"},
            {"id": "PROJ-2", "status": "updated"},
        ]

        updates = [
            {"id": "PROJ-1", "summary": "Updated 1"},
            {"id": "PROJ-2", "summary": "Updated 2"},
        ]
        results = adapter.bulk_update_issues(updates)

        assert len(results) == 2
        mock_client.bulk_update_issues.assert_called_once()

    def test_bulk_delete_issues(self, adapter, mock_client):
        """Should delete multiple issues."""
        mock_client.bulk_delete_issues.return_value = [
            {"id": "PROJ-1", "status": "deleted"},
            {"id": "PROJ-2", "status": "deleted"},
        ]

        results = adapter.bulk_delete_issues(["PROJ-1", "PROJ-2"])

        assert len(results) == 2
        mock_client.bulk_delete_issues.assert_called_once_with(["PROJ-1", "PROJ-2"])

    def test_bulk_transition_issues(self, adapter, mock_client):
        """Should transition multiple issues."""
        mock_client.get_available_states.return_value = [
            {"name": "Done"},
            {"name": "In Progress"},
        ]
        mock_client.bulk_execute_command.return_value = [
            {"id": "PROJ-1", "status": "executed"},
            {"id": "PROJ-2", "status": "executed"},
        ]

        results = adapter.bulk_transition_issues(["PROJ-1", "PROJ-2"], "done")

        assert len(results) == 2
        mock_client.bulk_execute_command.assert_called_once()


# =============================================================================
# File Attachment Tests
# =============================================================================


class TestYouTrackAttachments:
    """Tests for YouTrack file attachment operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_attachments(self, adapter, mock_client):
        """Should get issue attachments."""
        mock_client.get_issue_attachments.return_value = [
            {
                "id": "att1",
                "name": "file.pdf",
                "url": "https://youtrack.example.com/api/files/att1",
                "size": 1024,
                "mimeType": "application/pdf",
                "created": 1704067200000,
                "author": {"login": "john.doe"},
            }
        ]

        attachments = adapter.get_issue_attachments("PROJ-123")

        assert len(attachments) == 1
        assert attachments[0]["id"] == "att1"
        assert attachments[0]["name"] == "file.pdf"
        assert attachments[0]["author"] == "john.doe"

    def test_upload_attachment(self, adapter, mock_client, tmp_path):
        """Should upload an attachment."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client.upload_attachment.return_value = {"id": "att1", "name": "test.txt"}

        result = adapter.upload_attachment("PROJ-123", str(test_file))

        assert result["id"] == "att1"
        mock_client.upload_attachment.assert_called_once()

    def test_upload_attachment_dry_run(self, config):
        """Should not upload in dry run mode."""
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = YouTrackAdapter(config=config, dry_run=True)

        result = adapter.upload_attachment("PROJ-123", "/path/to/file.txt")

        assert result["id"] == "attachment:dry-run"
        mock_client.upload_attachment.assert_not_called()

    def test_delete_attachment(self, adapter, mock_client):
        """Should delete an attachment."""
        mock_client.delete_attachment.return_value = True

        result = adapter.delete_attachment("PROJ-123", "att1")

        assert result is True
        mock_client.delete_attachment.assert_called_once_with("PROJ-123", "att1")

    def test_download_attachment(self, adapter, mock_client, tmp_path):
        """Should download an attachment."""
        output_path = str(tmp_path / "downloaded.txt")
        mock_client.download_attachment.return_value = output_path

        result = adapter.download_attachment("PROJ-123", "att1", output_path)

        assert result is True
        mock_client.download_attachment.assert_called_once()


class TestYouTrackApiClientBulkOperations:
    """Tests for YouTrack API client bulk operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectryn.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        from spectryn.adapters.youtrack.client import YouTrackApiClient

        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
        )

    def test_bulk_create_issues(self, client, mock_session):
        """Should create multiple issues."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "1", "idReadable": "PROJ-1"}
        mock_session.request.return_value = mock_response

        issues = [{"summary": "Test 1"}, {"summary": "Test 2"}]
        results = client.bulk_create_issues(issues)

        assert len(results) == 2

    def test_bulk_update_issues(self, client, mock_session):
        """Should update multiple issues."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        updates = [{"id": "PROJ-1", "summary": "Updated"}]
        results = client.bulk_update_issues(updates)

        assert len(results) == 1

    def test_bulk_delete_issues(self, client, mock_session):
        """Should delete multiple issues."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        results = client.bulk_delete_issues(["PROJ-1", "PROJ-2"])

        assert len(results) == 2


class TestYouTrackApiClientAttachments:
    """Tests for YouTrack API client attachment operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch("spectryn.adapters.youtrack.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client."""
        from spectryn.adapters.youtrack.client import YouTrackApiClient

        return YouTrackApiClient(
            url="https://test.youtrack.com",
            token="test-token",
            dry_run=False,
        )

    def test_get_issue_attachments(self, client, mock_session):
        """Should get issue attachments."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "att1", "name": "file.pdf"}]
        mock_session.request.return_value = mock_response

        attachments = client.get_issue_attachments("PROJ-123")

        assert len(attachments) == 1
        assert attachments[0]["name"] == "file.pdf"

    def test_upload_attachment(self, client, mock_session, tmp_path):
        """Should upload an attachment."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "att1", "name": "test.txt"}]
        mock_session.post.return_value = mock_response

        result = client.upload_attachment("PROJ-123", str(test_file))

        assert result["id"] == "att1"

    def test_delete_attachment(self, client, mock_session):
        """Should delete an attachment."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        result = client.delete_attachment("PROJ-123", "att1")

        assert result is True

    def test_download_attachment(self, client, mock_session, tmp_path):
        """Should download an attachment."""
        # Mock get_issue_attachments
        attachments_response = MagicMock()
        attachments_response.ok = True
        attachments_response.status_code = 200
        attachments_response.json.return_value = [
            {"id": "att1", "url": "https://youtrack.example.com/api/files/att1"}
        ]

        # Mock file download
        download_response = MagicMock()
        download_response.ok = True
        download_response.content = b"file content"

        mock_session.request.return_value = attachments_response
        mock_session.get.return_value = download_response

        output_path = str(tmp_path / "downloaded.txt")
        result = client.download_attachment("PROJ-123", "att1", output_path)

        assert result == output_path


# =============================================================================
# Workflow & Commands Tests
# =============================================================================


class TestYouTrackWorkflow:
    """Tests for YouTrack workflow and command operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_execute_command(self, adapter, mock_client):
        """Should execute a command."""
        mock_client.execute_command.return_value = {}

        result = adapter.execute_command("PROJ-123", "State In Progress")

        assert result is True
        mock_client.execute_command.assert_called_once()

    def test_execute_command_dry_run(self, config):
        """Should not execute in dry run mode."""
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = YouTrackAdapter(config=config, dry_run=True)

        result = adapter.execute_command("PROJ-123", "State In Progress")

        assert result is True
        mock_client.execute_command.assert_not_called()

    def test_get_available_commands(self, adapter, mock_client):
        """Should get available commands."""
        mock_client.get_available_commands.return_value = [
            {"id": "cmd1", "name": "State"},
            {"id": "cmd2", "name": "Priority"},
        ]

        commands = adapter.get_available_commands("PROJ-123")

        assert len(commands) == 2


# =============================================================================
# Due Dates Tests
# =============================================================================


class TestYouTrackDueDates:
    """Tests for YouTrack due dates operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_due_date(self, adapter, mock_client):
        """Should get due date as ISO string."""
        # Timestamp for 2024-01-15T12:00:00Z
        mock_client.get_issue_due_date.return_value = 1705320000000

        result = adapter.get_issue_due_date("PROJ-123")

        assert result is not None
        assert "2024-01-15" in result

    def test_get_issue_due_date_not_set(self, adapter, mock_client):
        """Should return None when due date not set."""
        mock_client.get_issue_due_date.return_value = None

        result = adapter.get_issue_due_date("PROJ-123")

        assert result is None

    def test_update_issue_due_date(self, adapter, mock_client):
        """Should set due date."""
        mock_client.set_issue_due_date.return_value = {}

        result = adapter.update_issue_due_date("PROJ-123", "2024-01-15T12:00:00Z")

        assert result is True
        mock_client.set_issue_due_date.assert_called_once()

    def test_update_issue_due_date_clear(self, adapter, mock_client):
        """Should clear due date."""
        mock_client.set_issue_due_date.return_value = {}

        result = adapter.update_issue_due_date("PROJ-123", None)

        assert result is True

    def test_update_issue_due_date_dry_run(self, config):
        """Should not update in dry run mode."""
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = YouTrackAdapter(config=config, dry_run=True)

        result = adapter.update_issue_due_date("PROJ-123", "2024-01-15T12:00:00Z")

        assert result is True
        mock_client.set_issue_due_date.assert_not_called()


# =============================================================================
# Tags Tests
# =============================================================================


class TestYouTrackTags:
    """Tests for YouTrack tags operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_tags(self, adapter, mock_client):
        """Should get issue tags."""
        mock_client.get_issue_tags.return_value = [
            {"id": "tag1", "name": "bug", "color": {"background": "#ff0000"}},
            {"id": "tag2", "name": "feature", "color": {"background": "#00ff00"}},
        ]

        tags = adapter.get_issue_tags("PROJ-123")

        assert len(tags) == 2
        assert tags[0]["name"] == "bug"
        assert tags[0]["color"] == "#ff0000"

    def test_add_issue_tag(self, adapter, mock_client):
        """Should add a tag."""
        mock_client.add_issue_tag.return_value = {}

        result = adapter.add_issue_tag("PROJ-123", "urgent")

        assert result is True
        mock_client.add_issue_tag.assert_called_once_with("PROJ-123", "urgent")

    def test_remove_issue_tag(self, adapter, mock_client):
        """Should remove a tag."""
        mock_client.remove_issue_tag.return_value = {}

        result = adapter.remove_issue_tag("PROJ-123", "urgent")

        assert result is True
        mock_client.remove_issue_tag.assert_called_once_with("PROJ-123", "urgent")

    def test_get_available_tags(self, adapter, mock_client):
        """Should get available project tags."""
        mock_client.get_project_tags.return_value = [
            {"id": "tag1", "name": "bug"},
            {"id": "tag2", "name": "feature"},
        ]

        tags = adapter.get_available_tags()

        assert len(tags) == 2
        mock_client.get_project_tags.assert_called_once_with("PROJ")


# =============================================================================
# Watchers Tests
# =============================================================================


class TestYouTrackWatchers:
    """Tests for YouTrack watchers operations."""

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
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create test adapter."""
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_watchers(self, adapter, mock_client):
        """Should get issue watchers."""
        mock_client.get_issue_watchers.return_value = [
            {"id": "u1", "login": "john.doe", "name": "John Doe", "email": "john@example.com"},
        ]

        watchers = adapter.get_issue_watchers("PROJ-123")

        assert len(watchers) == 1
        assert watchers[0]["login"] == "john.doe"
        assert watchers[0]["name"] == "John Doe"

    def test_add_issue_watcher(self, adapter, mock_client):
        """Should add a watcher."""
        mock_client.add_issue_watcher.return_value = {}

        result = adapter.add_issue_watcher("PROJ-123", "john.doe")

        assert result is True
        mock_client.add_issue_watcher.assert_called_once_with("PROJ-123", "john.doe")

    def test_remove_issue_watcher(self, adapter, mock_client):
        """Should remove a watcher."""
        mock_client.remove_issue_watcher.return_value = True

        result = adapter.remove_issue_watcher("PROJ-123", "john.doe")

        assert result is True
        mock_client.remove_issue_watcher.assert_called_once_with("PROJ-123", "john.doe")

    def test_is_watching(self, adapter, mock_client):
        """Should check if watching."""
        mock_client.is_watching.return_value = True

        result = adapter.is_watching("PROJ-123", "john.doe")

        assert result is True
        mock_client.is_watching.assert_called_once_with("PROJ-123", "john.doe")


# =============================================================================
# Agile Boards Tests
# =============================================================================


class TestYouTrackAgileBoards:
    """Tests for YouTrack agile boards operations."""

    @pytest.fixture
    def config(self):
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_agile_boards(self, adapter, mock_client):
        """Should get agile boards."""
        mock_client.get_agile_boards.return_value = [
            {
                "id": "board1",
                "name": "Sprint Board",
                "owner": {"login": "admin"},
                "projects": [{"shortName": "PROJ"}],
            },
        ]

        boards = adapter.get_agile_boards()

        assert len(boards) == 1
        assert boards[0]["name"] == "Sprint Board"
        assert boards[0]["owner"] == "admin"

    def test_get_agile_board(self, adapter, mock_client):
        """Should get a specific board."""
        mock_client.get_agile_board.return_value = {
            "id": "board1",
            "name": "Sprint Board",
            "owner": {"login": "admin"},
            "projects": [{"shortName": "PROJ"}],
            "sprints": [{"id": "sprint1", "name": "Sprint 1"}],
        }

        board = adapter.get_agile_board("board1")

        assert board["name"] == "Sprint Board"
        assert len(board["sprints"]) == 1


# =============================================================================
# Sprints Tests
# =============================================================================


class TestYouTrackSprints:
    """Tests for YouTrack sprints operations."""

    @pytest.fixture
    def config(self):
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_board_sprints(self, adapter, mock_client):
        """Should get sprints for a board."""
        mock_client.get_board_sprints.return_value = [
            {"id": "sprint1", "name": "Sprint 1", "start": 1704067200000, "finish": 1705276800000},
        ]

        sprints = adapter.get_board_sprints("board1")

        assert len(sprints) == 1
        assert sprints[0]["name"] == "Sprint 1"

    def test_get_sprint(self, adapter, mock_client):
        """Should get a specific sprint."""
        mock_client.get_sprint.return_value = {
            "id": "sprint1",
            "name": "Sprint 1",
            "issues": [{"idReadable": "PROJ-1", "summary": "Issue 1"}],
        }

        sprint = adapter.get_sprint("board1", "sprint1")

        assert sprint["name"] == "Sprint 1"
        assert len(sprint["issues"]) == 1

    def test_create_sprint(self, adapter, mock_client):
        """Should create a sprint."""
        mock_client.create_sprint.return_value = {"id": "sprint2", "name": "Sprint 2"}

        result = adapter.create_sprint("board1", "Sprint 2")

        assert result["name"] == "Sprint 2"
        mock_client.create_sprint.assert_called_once()

    def test_add_issue_to_sprint(self, adapter, mock_client):
        """Should add issue to sprint."""
        mock_client.add_issue_to_sprint.return_value = {}

        result = adapter.add_issue_to_sprint("board1", "sprint1", "PROJ-123")

        assert result is True

    def test_remove_issue_from_sprint(self, adapter, mock_client):
        """Should remove issue from sprint."""
        mock_client.remove_issue_from_sprint.return_value = {}

        result = adapter.remove_issue_from_sprint("PROJ-123")

        assert result is True


# =============================================================================
# Time Tracking Tests
# =============================================================================


class TestYouTrackTimeTracking:
    """Tests for YouTrack time tracking operations."""

    @pytest.fixture
    def config(self):
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_work_items(self, adapter, mock_client):
        """Should get work items."""
        mock_client.get_issue_work_items.return_value = [
            {
                "id": "work1",
                "author": {"login": "john.doe"},
                "duration": {"minutes": 60, "presentation": "1h"},
                "text": "Coding",
            }
        ]

        items = adapter.get_issue_work_items("PROJ-123")

        assert len(items) == 1
        assert items[0]["duration_minutes"] == 60
        assert items[0]["author"] == "john.doe"

    def test_add_work_item(self, adapter, mock_client):
        """Should add work item."""
        mock_client.add_work_item.return_value = {"id": "work1"}

        result = adapter.add_work_item("PROJ-123", 60, "Coding")

        assert result["id"] == "work1"
        mock_client.add_work_item.assert_called_once()

    def test_delete_work_item(self, adapter, mock_client):
        """Should delete work item."""
        mock_client.delete_work_item.return_value = True

        result = adapter.delete_work_item("PROJ-123", "work1")

        assert result is True

    def test_get_time_tracking(self, adapter, mock_client):
        """Should get time tracking summary."""
        mock_client.get_time_tracking_settings.return_value = {
            "enabled": True,
            "estimate": {"minutes": 480, "presentation": "1d"},
            "spentTime": {"minutes": 120, "presentation": "2h"},
        }

        tracking = adapter.get_time_tracking("PROJ-123")

        assert tracking["enabled"] is True
        assert tracking["estimate_minutes"] == 480
        assert tracking["spent_minutes"] == 120

    def test_set_time_estimate(self, adapter, mock_client):
        """Should set time estimate."""
        mock_client.set_time_estimate.return_value = {}

        result = adapter.set_time_estimate("PROJ-123", 480)

        assert result is True


# =============================================================================
# Issue History Tests
# =============================================================================


class TestYouTrackHistory:
    """Tests for YouTrack issue history operations."""

    @pytest.fixture
    def config(self):
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        return YouTrackAdapter(config=config, dry_run=False)

    def test_get_issue_history(self, adapter, mock_client):
        """Should get issue history."""
        mock_client.get_issue_changes.return_value = [
            {"id": "change1", "timestamp": 1704067200000, "author": "john.doe", "field": "State"},
        ]

        history = adapter.get_issue_history("PROJ-123")

        assert len(history) == 1
        assert history[0]["author"] == "john.doe"

    def test_get_issue_activities(self, adapter, mock_client):
        """Should get issue activities."""
        mock_client.get_issue_activities.return_value = [
            {"id": "act1", "timestamp": 1704067200000},
        ]

        activities = adapter.get_issue_activities("PROJ-123")

        assert len(activities) == 1


# =============================================================================
# Mentions Tests
# =============================================================================


class TestYouTrackMentions:
    """Tests for YouTrack mentions operations."""

    @pytest.fixture
    def config(self):
        return YouTrackConfig(
            url="https://test.youtrack.com",
            token="test-token",
            project_id="PROJ",
        )

    @pytest.fixture
    def mock_client(self):
        with patch("spectryn.adapters.youtrack.adapter.YouTrackApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        return YouTrackAdapter(config=config, dry_run=False)

    def test_add_comment_with_mentions(self, adapter, mock_client):
        """Should add comment with mentions."""
        mock_client.add_comment_with_mentions.return_value = {}

        result = adapter.add_comment_with_mentions(
            "PROJ-123", "Please review", ["john.doe", "jane.doe"]
        )

        assert result is True
        mock_client.add_comment_with_mentions.assert_called_once()

    def test_get_mentionable_users(self, adapter, mock_client):
        """Should get mentionable users."""
        mock_client.get_mentionable_users.return_value = [
            {"id": "u1", "login": "john.doe", "name": "John Doe", "email": "john@example.com"},
        ]

        users = adapter.get_mentionable_users("john")

        assert len(users) == 1
        assert users[0]["login"] == "john.doe"
