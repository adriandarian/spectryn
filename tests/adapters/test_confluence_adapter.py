"""
Tests for Confluence Adapter.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from spectryn.adapters.confluence.adapter import ConfluenceAdapter
from spectryn.adapters.confluence.client import (
    ConfluenceAPIError,
    ConfluenceClient,
    ConfluenceConfig,
)
from spectryn.adapters.confluence.plugin import ConfluencePlugin, create_plugin
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_output import (
    AuthenticationError,
    NotFoundError,
)


# =============================================================================
# ConfluenceClient Tests
# =============================================================================


class TestConfluenceClient:
    """Tests for ConfluenceClient."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return ConfluenceConfig(
            base_url="https://test.atlassian.net/wiki",
            username="test@example.com",
            api_token="test-token",
            is_cloud=True,
        )

    @pytest.fixture
    def client(self, config):
        """Create client instance."""
        return ConfluenceClient(config)

    def test_cloud_api_base_url(self, client):
        """Should set correct API base for Cloud."""
        assert "/wiki/rest/api" in client._api_base

    def test_server_api_base_url(self):
        """Should set correct API base for Server."""
        config = ConfluenceConfig(
            base_url="https://confluence.company.com",
            username="user",
            api_token="pass",
            is_cloud=False,
        )
        client = ConfluenceClient(config)
        assert client._api_base == "https://confluence.company.com/rest/api"

    @patch("requests.Session")
    def test_connect_creates_session(self, mock_session_class, client):
        """Should create session on connect."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        client.connect()

        assert client._session is not None
        mock_session.headers.update.assert_called()

    def test_disconnect_clears_session(self, client):
        """Should clear session on disconnect."""
        client._session = MagicMock()

        client.disconnect()

        assert client._session is None


# =============================================================================
# ConfluenceAdapter Tests
# =============================================================================


class TestConfluenceAdapter:
    """Tests for ConfluenceAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create mock client."""
        return Mock(spec=ConfluenceClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create adapter with mock client."""
        return ConfluenceAdapter(mock_client)

    # -------------------------------------------------------------------------
    # Connection Tests
    # -------------------------------------------------------------------------

    def test_name(self, adapter):
        """Should return 'Confluence' as name."""
        assert adapter.name == "Confluence"

    def test_connect_success(self, adapter, mock_client):
        """Should connect and verify user."""
        mock_client.get_current_user.return_value = {"displayName": "Test User"}

        adapter.connect()

        mock_client.connect.assert_called_once()
        mock_client.get_current_user.assert_called_once()

    def test_connect_auth_failure(self, adapter, mock_client):
        """Should raise AuthenticationError on 401."""
        mock_client.connect.side_effect = ConfluenceAPIError("Unauthorized", status_code=401)

        with pytest.raises(AuthenticationError):
            adapter.connect()

    def test_disconnect(self, adapter, mock_client):
        """Should disconnect client."""
        adapter.disconnect()

        mock_client.disconnect.assert_called_once()

    # -------------------------------------------------------------------------
    # Space Tests
    # -------------------------------------------------------------------------

    def test_get_space(self, adapter, mock_client):
        """Should get space by key."""
        mock_client.get_space.return_value = {
            "key": "DEV",
            "name": "Development",
            "type": "global",
        }

        space = adapter.get_space("DEV")

        assert space.key == "DEV"
        assert space.name == "Development"

    def test_get_space_not_found(self, adapter, mock_client):
        """Should raise NotFoundError for missing space."""
        mock_client.get_space.side_effect = ConfluenceAPIError("Not found", status_code=404)

        with pytest.raises(NotFoundError):
            adapter.get_space("MISSING")

    def test_list_spaces(self, adapter, mock_client):
        """Should list all spaces."""
        mock_client.list_spaces.return_value = [
            {"key": "DEV", "name": "Development"},
            {"key": "DOC", "name": "Documentation"},
        ]

        spaces = adapter.list_spaces()

        assert len(spaces) == 2
        assert spaces[0].key == "DEV"
        assert spaces[1].key == "DOC"

    # -------------------------------------------------------------------------
    # Page Tests
    # -------------------------------------------------------------------------

    def test_get_page(self, adapter, mock_client):
        """Should get page by ID."""
        mock_client.get_content.return_value = {
            "id": "123",
            "title": "Test Page",
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"number": 2},
            "space": {"key": "DEV"},
        }

        page = adapter.get_page("123")

        assert page.id == "123"
        assert page.title == "Test Page"
        assert page.content == "<p>Content</p>"
        assert page.version == 2

    def test_get_page_not_found(self, adapter, mock_client):
        """Should raise NotFoundError for missing page."""
        mock_client.get_content.side_effect = ConfluenceAPIError("Not found", status_code=404)

        with pytest.raises(NotFoundError):
            adapter.get_page("999")

    def test_get_page_by_title(self, adapter, mock_client):
        """Should find page by title."""
        mock_client.get_content_by_title.return_value = {
            "id": "456",
            "title": "Found Page",
            "body": {"storage": {"value": ""}},
            "version": {"number": 1},
        }

        page = adapter.get_page_by_title("DEV", "Found Page")

        assert page is not None
        assert page.id == "456"

    def test_get_page_by_title_not_found(self, adapter, mock_client):
        """Should return None if page not found."""
        mock_client.get_content_by_title.return_value = None

        page = adapter.get_page_by_title("DEV", "Missing")

        assert page is None

    def test_create_page(self, adapter, mock_client):
        """Should create new page."""
        mock_client.create_content.return_value = {
            "id": "789",
            "title": "New Page",
            "body": {"storage": {"value": "<p>Content</p>"}},
            "version": {"number": 1},
        }

        page = adapter.create_page(
            space_key="DEV",
            title="New Page",
            content="<p>Content</p>",
        )

        assert page.id == "789"
        assert page.title == "New Page"
        mock_client.create_content.assert_called_once()

    def test_create_page_with_labels(self, adapter, mock_client):
        """Should create page with labels."""
        mock_client.create_content.return_value = {
            "id": "789",
            "title": "New Page",
            "body": {"storage": {"value": ""}},
            "version": {"number": 1},
        }

        page = adapter.create_page(
            space_key="DEV",
            title="New Page",
            content="",
            labels=["label1", "label2"],
        )

        mock_client.add_labels.assert_called_once_with("789", ["label1", "label2"])
        assert page.labels == ["label1", "label2"]

    def test_update_page(self, adapter, mock_client):
        """Should update existing page."""
        mock_client.update_content.return_value = {
            "id": "123",
            "title": "Updated Page",
            "body": {"storage": {"value": "<p>New content</p>"}},
            "version": {"number": 3},
        }

        page = adapter.update_page(
            page_id="123",
            title="Updated Page",
            content="<p>New content</p>",
            version=2,
        )

        assert page.title == "Updated Page"
        assert page.version == 3
        mock_client.update_content.assert_called_once()

    def test_delete_page(self, adapter, mock_client):
        """Should delete page."""
        adapter.delete_page("123")

        mock_client.delete_content.assert_called_once_with("123")

    # -------------------------------------------------------------------------
    # Epic/Story Publishing Tests
    # -------------------------------------------------------------------------

    @pytest.fixture
    def sample_story(self):
        """Create a sample story."""
        return UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            description=Description(
                role="user",
                want="test feature",
                benefit="better experience",
            ),
            acceptance_criteria=AcceptanceCriteria.from_list(
                ["First criterion", "Second criterion"],
                [True, False],
            ),
            story_points=5,
            priority=Priority.HIGH,
            status=Status.IN_PROGRESS,
            subtasks=[
                Subtask(
                    number=1,
                    name="Subtask 1",
                    story_points=2,
                    status=Status.DONE,
                )
            ],
            commits=[],
        )

    @pytest.fixture
    def sample_epic(self, sample_story):
        """Create a sample epic."""
        return Epic(
            key=IssueKey("EPIC-001"),
            title="Test Epic",
            stories=[sample_story],
        )

    def test_publish_story_creates_page(self, adapter, mock_client, sample_story):
        """Should create page for story."""
        mock_client.get_content_by_title.return_value = None  # Not existing
        mock_client.create_content.return_value = {
            "id": "101",
            "title": "US-001: Test Story",
            "body": {"storage": {"value": ""}},
            "version": {"number": 1},
        }

        page = adapter.publish_story(sample_story, "DEV")

        assert page.id == "101"
        mock_client.create_content.assert_called_once()
        # Check title includes story ID
        call_args = mock_client.create_content.call_args
        assert "US-001" in call_args.kwargs.get("title", call_args[1].get("title", ""))

    def test_publish_story_updates_existing(self, adapter, mock_client, sample_story):
        """Should update existing story page."""
        mock_client.get_content_by_title.return_value = {
            "id": "101",
            "title": "US-001: Test Story",
            "body": {"storage": {"value": "old"}},
            "version": {"number": 2},
            "metadata": {"labels": {"results": []}},
        }
        mock_client.update_content.return_value = {
            "id": "101",
            "title": "US-001: Test Story",
            "body": {"storage": {"value": "new"}},
            "version": {"number": 3},
        }
        mock_client.get_labels.return_value = []

        page = adapter.publish_story(sample_story, "DEV", update_existing=True)

        assert page.id == "101"
        mock_client.update_content.assert_called_once()

    def test_publish_epic_creates_hierarchy(self, adapter, mock_client, sample_epic):
        """Should create epic page with story children."""
        mock_client.get_content_by_title.return_value = None

        # Mock epic creation
        mock_client.create_content.side_effect = [
            {
                "id": "epic-page",
                "title": "Epic: Test Epic",
                "body": {"storage": {"value": ""}},
                "version": {"number": 1},
            },
            {
                "id": "story-page",
                "title": "US-001: Test Story",
                "body": {"storage": {"value": ""}},
                "version": {"number": 1},
            },
        ]

        page = adapter.publish_epic(sample_epic, "DEV")

        assert page.id == "epic-page"
        # Should create both epic and story pages
        assert mock_client.create_content.call_count == 2

    # -------------------------------------------------------------------------
    # Content Formatting Tests
    # -------------------------------------------------------------------------

    def test_format_story_content(self, adapter, sample_story):
        """Should format story as Confluence storage format."""
        content = adapter.format_story_content(sample_story)

        # Check for key elements
        assert "User Story" in content or "As a" in content
        assert "Acceptance Criteria" in content
        assert "Subtasks" in content
        assert "user" in content  # role
        assert "test feature" in content  # want

    def test_format_story_with_status_panel(self, adapter, sample_story):
        """Should include status panel with metadata."""
        content = adapter.format_story_content(sample_story)

        assert "Status" in content
        assert "Priority" in content
        assert "Story Points" in content

    def test_format_epic_content(self, adapter, sample_epic):
        """Should format epic as Confluence storage format."""
        content = adapter.format_epic_content(sample_epic)

        assert "Epic Key" in content
        assert "Stories" in content
        assert "EPIC-001" in content

    def test_format_acceptance_criteria_as_tasks(self, adapter, sample_story):
        """Should format AC as task list."""
        content = adapter.format_story_content(sample_story)

        assert "ac:task-list" in content
        assert "ac:task" in content
        assert "complete" in content  # First criterion is checked
        assert "incomplete" in content  # Second is not

    def test_format_subtasks_as_table(self, adapter, sample_story):
        """Should format subtasks as table."""
        content = adapter.format_story_content(sample_story)

        assert "<table>" in content
        assert "Subtask 1" in content

    def test_status_lozenge(self, adapter):
        """Should create status lozenge macro."""
        lozenge = adapter._status_lozenge(Status.IN_PROGRESS)

        assert "ac:structured-macro" in lozenge
        assert 'ac:name="status"' in lozenge
        assert "Yellow" in lozenge  # IN_PROGRESS color

    def test_info_panel(self, adapter):
        """Should create info panel macro."""
        panel = adapter._info_panel("Test content")

        assert 'ac:name="info"' in panel
        assert "Test content" in panel

    def test_code_block(self, adapter):
        """Should create code block macro."""
        code = adapter._code_block("def hello(): pass", "python")

        assert 'ac:name="code"' in code
        assert "python" in code
        assert "def hello(): pass" in code


# =============================================================================
# ConfluencePlugin Tests
# =============================================================================


class TestConfluencePlugin:
    """Tests for ConfluencePlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = ConfluencePlugin()

        assert plugin.metadata.name == "confluence"
        assert plugin.metadata.version == "1.0.0"
        assert "Confluence" in plugin.metadata.description

    def test_initialize_requires_url(self):
        """Should require base URL."""
        plugin = ConfluencePlugin()

        with pytest.raises(ValueError, match="URL"):
            plugin.initialize()

    def test_initialize_requires_username(self):
        """Should require username."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
            }
        )

        with pytest.raises(ValueError, match="username"):
            plugin.initialize()

    def test_initialize_requires_token(self):
        """Should require API token."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
                "username": "test@example.com",
            }
        )

        with pytest.raises(ValueError, match="token"):
            plugin.initialize()

    @patch.object(ConfluenceAdapter, "connect")
    def test_initialize_success(self, mock_connect):
        """Should initialize with valid config."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
                "username": "test@example.com",
                "api_token": "test-token",
            }
        )

        plugin.initialize()

        assert plugin.is_initialized
        mock_connect.assert_called_once()

    @patch.object(ConfluenceAdapter, "connect")
    @patch.object(ConfluenceAdapter, "disconnect")
    def test_shutdown(self, mock_disconnect, mock_connect):
        """Should disconnect on shutdown."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
                "username": "test@example.com",
                "api_token": "test-token",
            }
        )
        plugin.initialize()

        plugin.shutdown()

        assert not plugin.is_initialized
        mock_disconnect.assert_called_once()

    def test_get_adapter_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = ConfluencePlugin()

        with pytest.raises(RuntimeError):
            plugin.get_adapter()

    @patch.object(ConfluenceAdapter, "connect")
    def test_get_adapter_after_initialize(self, mock_connect):
        """Should return adapter after initialization."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
                "username": "test@example.com",
                "api_token": "test-token",
            }
        )
        plugin.initialize()

        adapter = plugin.get_adapter()

        assert adapter is not None
        assert adapter.name == "Confluence"

    @patch.object(ConfluenceAdapter, "connect")
    def test_default_space_from_config(self, mock_connect):
        """Should expose default space from config."""
        plugin = ConfluencePlugin(
            {
                "base_url": "https://test.atlassian.net/wiki",
                "username": "test@example.com",
                "api_token": "test-token",
                "default_space": "DEV",
            }
        )
        plugin.initialize()

        assert plugin.default_space == "DEV"

    @patch.dict(
        "os.environ",
        {
            "CONFLUENCE_URL": "https://env.atlassian.net/wiki",
            "CONFLUENCE_USERNAME": "env@example.com",
            "CONFLUENCE_API_TOKEN": "env-token",
            "CONFLUENCE_SPACE": "ENV",
        },
    )
    @patch.object(ConfluenceAdapter, "connect")
    def test_config_from_environment(self, mock_connect):
        """Should read config from environment."""
        plugin = ConfluencePlugin()
        plugin.initialize()

        assert plugin.is_initialized
        assert plugin.default_space == "ENV"

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        plugin = create_plugin()

        assert isinstance(plugin, ConfluencePlugin)
