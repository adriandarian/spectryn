"""
Tests for Pivotal Tracker Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.pivotal.adapter import PivotalAdapter
from spectryn.adapters.pivotal.client import PivotalApiClient, PivotalRateLimiter
from spectryn.adapters.pivotal.plugin import PivotalTrackerPlugin, create_plugin
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestPivotalRateLimiter:
    """Tests for PivotalRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = PivotalRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = PivotalRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "current_tokens" in stats
        assert "requests_per_second" in stats

    def test_update_from_response(self):
        """Should update state from Pivotal response headers."""
        limiter = PivotalRateLimiter()

        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "60"}
        mock_response.status_code = 200

        limiter.update_from_response(mock_response)

        # Should handle retry-after header
        assert limiter._retry_after is not None


# =============================================================================
# API Client Tests
# =============================================================================


class TestPivotalApiClient:
    """Tests for PivotalApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.pivotal.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return PivotalApiClient(
            api_token="test_token",
            project_id="12345",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = PivotalApiClient(api_token="test_token", project_id="12345")

        assert client.api_url == "https://www.pivotaltracker.com/services/v5"
        assert client.dry_run is True  # Default

    def test_request_get(self, client, mock_session):
        """Should execute GET request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "name": "Test Story"}
        mock_response.headers = {}
        mock_response.text = '{"id": 123}'
        mock_session.request.return_value = mock_response

        result = client.request("GET", "/projects/12345/stories/123")

        assert result["id"] == 123
        mock_session.request.assert_called_once()

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.request("GET", "/me")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.request("GET", "/projects/12345/stories/999")

    def test_get_story(self, client, mock_session):
        """Should get a story by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "name": "Test Story",
            "description": "Test description",
        }
        mock_response.headers = {}
        mock_response.text = '{"id": 123}'
        mock_session.request.return_value = mock_response

        result = client.get_story(123)

        assert result["id"] == 123
        assert result["name"] == "Test Story"

    def test_create_story(self, client, mock_session):
        """Should create a new story."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 456,
            "name": "New Story",
        }
        mock_response.headers = {}
        mock_response.text = '{"id": 456}'
        mock_session.request.return_value = mock_response

        result = client.create_story(name="New Story", description="Description")

        assert result["id"] == 456
        mock_session.request.assert_called_once()

    def test_get_epic_stories(self, client, mock_session):
        """Should get stories in an epic."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "Story 1"},
            {"id": 2, "name": "Story 2"},
        ]
        mock_response.headers = {}
        mock_response.text = "[]"
        mock_session.request.return_value = mock_response

        stories = client.get_epic_stories(100)

        assert len(stories) == 2
        assert stories[0]["name"] == "Story 1"

    def test_create_task(self, client, mock_session):
        """Should create a task within a story."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 789, "description": "New Task"}
        mock_response.headers = {}
        mock_response.text = '{"id": 789}'
        mock_session.request.return_value = mock_response

        result = client.create_task(story_id=123, description="New Task")

        assert result["id"] == 789

    def test_list_iterations(self, client, mock_session):
        """Should list iterations."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"number": 1, "start": "2025-01-13"},
            {"number": 2, "start": "2025-01-20"},
        ]
        mock_response.headers = {}
        mock_response.text = "[]"
        mock_session.request.return_value = mock_response

        iterations = client.list_iterations()

        assert len(iterations) == 2
        assert iterations[0]["number"] == 1


# =============================================================================
# Adapter Tests
# =============================================================================


class TestPivotalAdapter:
    """Tests for PivotalAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        return MagicMock(spec=PivotalApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = PivotalAdapter(
            api_token="test_token",
            project_id="12345",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Pivotal Tracker"

    def test_get_issue(self, adapter, mock_client):
        """Should get an issue by key."""
        mock_client.get_story.return_value = {
            "id": 123,
            "name": "Test Story",
            "description": "Description",
            "current_state": "started",
            "story_type": "feature",
            "estimate": 5,
            "owner_ids": [],
            "tasks": [],
            "comments": [],
        }

        result = adapter.get_issue("123")

        assert result.key == "123"
        assert result.summary == "Test Story"
        assert result.status == "In Progress"

    def test_get_issue_with_prefix(self, adapter, mock_client):
        """Should handle issue key with PT- prefix."""
        mock_client.get_story.return_value = {
            "id": 456,
            "name": "Another Story",
            "current_state": "accepted",
            "story_type": "feature",
            "owner_ids": [],
            "tasks": [],
            "comments": [],
        }

        result = adapter.get_issue("PT-456")

        assert result.key == "456"
        assert result.status == "Done"

    def test_get_epic_children(self, adapter, mock_client):
        """Should get epic children."""
        mock_client.get_epic_stories.return_value = [
            {
                "id": 1,
                "name": "Story 1",
                "current_state": "unstarted",
                "story_type": "feature",
                "estimate": None,
                "owner_ids": [],
                "tasks": [],
                "comments": [],
            },
            {
                "id": 2,
                "name": "Story 2",
                "current_state": "accepted",
                "story_type": "feature",
                "estimate": 3,
                "owner_ids": [],
                "tasks": [],
                "comments": [],
            },
        ]

        results = adapter.get_epic_children("100")

        assert len(results) == 2
        assert results[0].key == "1"
        assert results[1].key == "2"

    def test_create_subtask(self, adapter, mock_client):
        """Should create a subtask."""
        mock_client.create_task.return_value = {"id": 456}

        result = adapter.create_subtask(
            parent_key="123",
            summary="Subtask",
            description="Description",
            project_key="PROJ",
        )

        assert result == "123-T456"
        mock_client.create_task.assert_called_once()

    def test_transition_issue_to_started(self, adapter, mock_client):
        """Should transition an issue to started state."""
        adapter.transition_issue("123", "In Progress")

        mock_client.update_story.assert_called_once_with(123, current_state="started")

    def test_transition_issue_to_accepted(self, adapter, mock_client):
        """Should transition an issue to accepted state."""
        adapter.transition_issue("123", "Done")

        mock_client.update_story.assert_called_once_with(123, current_state="accepted")

    def test_transition_issue_invalid_state(self, adapter, mock_client):
        """Should handle invalid state gracefully."""
        # The adapter maps unknown states to 'unstarted'
        adapter.transition_issue("123", "Unknown State")

        mock_client.update_story.assert_called_once_with(123, current_state="unstarted")

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update story points."""
        adapter.update_issue_story_points("123", 5.0)

        mock_client.update_story.assert_called_once_with(123, estimate=5)

    def test_add_comment(self, adapter, mock_client):
        """Should add a comment."""
        adapter.add_comment("123", "Test comment")

        mock_client.create_comment.assert_called_once_with(123, "Test comment")

    def test_get_issue_links_empty(self, adapter, mock_client):
        """Should return empty list (Pivotal doesn't have native linking)."""
        links = adapter.get_issue_links("123")

        assert links == []

    def test_create_link_via_label(self, adapter, mock_client):
        """Should create a link via label."""
        from spectryn.core.ports.issue_tracker import LinkType

        mock_client.get_or_create_label.return_value = {"id": 100, "name": "depends on:456"}
        mock_client.get_story.return_value = {"labels": []}
        mock_client.update_story.return_value = {}

        result = adapter.create_link("123", "456", LinkType.DEPENDS_ON)

        assert result is True

    def test_map_state_to_status(self, adapter):
        """Should correctly map Pivotal states to display statuses."""
        assert adapter._map_state_to_status("unscheduled") == "Planned"
        assert adapter._map_state_to_status("unstarted") == "Open"
        assert adapter._map_state_to_status("started") == "In Progress"
        assert adapter._map_state_to_status("finished") == "In Review"
        assert adapter._map_state_to_status("delivered") == "In Review"
        assert adapter._map_state_to_status("rejected") == "Open"
        assert adapter._map_state_to_status("accepted") == "Done"

    def test_map_status_to_state(self, adapter):
        """Should correctly map display statuses to Pivotal states."""
        assert adapter._map_status_to_state("Done") == "accepted"
        assert adapter._map_status_to_state("In Progress") == "started"
        assert adapter._map_status_to_state("Open") == "unstarted"
        assert adapter._map_status_to_state("Planned") == "unscheduled"
        assert adapter._map_status_to_state("In Review") == "finished"

    def test_map_story_type(self, adapter):
        """Should correctly map Pivotal story types."""
        assert adapter._map_story_type("feature") == "Story"
        assert adapter._map_story_type("bug") == "Bug"
        assert adapter._map_story_type("chore") == "Task"
        assert adapter._map_story_type("release") == "Release"


# =============================================================================
# Plugin Tests
# =============================================================================


class TestPivotalTrackerPlugin:
    """Tests for PivotalTrackerPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        from spectryn.plugins.base import PluginType

        plugin = PivotalTrackerPlugin()
        metadata = plugin.metadata

        assert metadata.name == "pivotal"
        assert metadata.plugin_type == PluginType.TRACKER

    @patch.dict(
        "os.environ",
        {"PIVOTAL_API_TOKEN": "env_token", "PIVOTAL_PROJECT_ID": "env_project"},
    )
    def test_initialize_from_env(self):
        """Should initialize from environment variables."""
        plugin = PivotalTrackerPlugin()
        plugin.config = {}

        with patch("spectryn.adapters.pivotal.plugin.PivotalAdapter") as mock_adapter:
            mock_adapter.return_value = MagicMock()
            plugin.initialize()

            mock_adapter.assert_called_once_with(
                api_token="env_token",
                project_id="env_project",
                api_url="https://www.pivotaltracker.com/services/v5",
                dry_run=True,
            )

    def test_validate_config_missing_token(self):
        """Should validate missing API token."""
        plugin = PivotalTrackerPlugin()
        plugin.config = {}

        errors = plugin.validate_config()

        assert len(errors) > 0
        assert any("token" in error.lower() for error in errors)

    def test_validate_config_missing_project_id(self):
        """Should validate missing project ID."""
        plugin = PivotalTrackerPlugin()
        plugin.config = {"api_token": "test_token"}

        errors = plugin.validate_config()

        assert len(errors) > 0
        assert any("project" in error.lower() for error in errors)

    def test_create_plugin(self):
        """Should create plugin instance."""
        plugin = create_plugin({"api_token": "test", "project_id": "12345"})

        assert isinstance(plugin, PivotalTrackerPlugin)


# =============================================================================
# Dry Run Tests
# =============================================================================


class TestPivotalAdapterDryRun:
    """Tests for dry-run mode."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter in dry-run mode."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=True,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            return adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create subtask in dry-run mode."""
        result = adapter.create_subtask(
            parent_key="123",
            summary="Test",
            description="Desc",
            project_key="PROJ",
        )

        assert result is None
        mock_client.create_task.assert_not_called()

    def test_update_description_dry_run(self, adapter, mock_client):
        """Should not update description in dry-run mode."""
        result = adapter.update_issue_description("123", "New description")

        assert result is True
        mock_client.update_story.assert_not_called()

    def test_transition_dry_run(self, adapter, mock_client):
        """Should not transition in dry-run mode."""
        result = adapter.transition_issue("123", "Done")

        assert result is True
        mock_client.update_story.assert_not_called()

    def test_add_comment_dry_run(self, adapter, mock_client):
        """Should not add comment in dry-run mode."""
        result = adapter.add_comment("123", "Test comment")

        assert result is True
        mock_client.create_comment.assert_not_called()

    def test_upload_attachment_dry_run(self, adapter, mock_client):
        """Should not upload in dry-run mode."""
        result = adapter.upload_attachment("123", "/path/to/file.txt")

        assert result["id"] == "attachment:dry-run"
        mock_client.upload_file.assert_not_called()


# =============================================================================
# Webhook Tests
# =============================================================================


class TestPivotalAdapterWebhooks:
    """Tests for webhook functionality."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            return adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_create_webhook(self, adapter, mock_client):
        """Should create a webhook subscription."""
        mock_client.create_webhook.return_value = {
            "id": 123,
            "webhook_url": "https://example.com/webhook",
        }

        result = adapter.create_webhook("https://example.com/webhook")

        assert result["id"] == 123
        mock_client.create_webhook.assert_called_once_with(url="https://example.com/webhook")

    def test_list_webhooks(self, adapter, mock_client):
        """Should list webhook subscriptions."""
        mock_client.list_webhooks.return_value = [
            {"id": 1, "webhook_url": "https://example.com/webhook1"},
            {"id": 2, "webhook_url": "https://example.com/webhook2"},
        ]

        webhooks = adapter.list_webhooks()

        assert len(webhooks) == 2
        mock_client.list_webhooks.assert_called_once()

    def test_delete_webhook(self, adapter, mock_client):
        """Should delete a webhook."""
        mock_client.delete_webhook.return_value = True

        result = adapter.delete_webhook("123")

        assert result is True
        mock_client.delete_webhook.assert_called_once_with(123)

    def test_create_webhook_dry_run(self):
        """Should not create webhook in dry-run mode."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=True,
            )
            mock_client = MagicMock()
            adapter._client = mock_client

        result = adapter.create_webhook("https://example.com/webhook")

        assert result["id"] == "webhook:dry-run"
        mock_client.create_webhook.assert_not_called()


# =============================================================================
# Iteration Tests
# =============================================================================


class TestPivotalAdapterIterations:
    """Tests for iteration functionality."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            return adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_list_iterations(self, adapter, mock_client):
        """Should list all iterations."""
        mock_client.list_iterations.return_value = [
            {"number": 1, "start": "2025-01-13", "finish": "2025-01-24"},
            {"number": 2, "start": "2025-01-27", "finish": "2025-02-07"},
        ]

        iterations = adapter.list_iterations()

        assert len(iterations) == 2
        assert iterations[0]["number"] == 1
        mock_client.list_iterations.assert_called_once()

    def test_get_iteration(self, adapter, mock_client):
        """Should get an iteration by number."""
        mock_client.get_iteration.return_value = {
            "number": 1,
            "start": "2025-01-13",
            "finish": "2025-01-24",
        }

        iteration = adapter.get_iteration(1)

        assert iteration["number"] == 1
        mock_client.get_iteration.assert_called_once_with(1)


# =============================================================================
# Attachment Tests
# =============================================================================


class TestPivotalAdapterAttachments:
    """Tests for file attachment operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock PivotalApiClient."""
        return MagicMock(spec=PivotalApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create adapter with mock client."""
        adapter = PivotalAdapter(
            api_token="test_token",
            project_id="12345",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_get_issue_attachments(self, adapter, mock_client):
        """Should get attachments for an issue."""
        mock_client.get_story_attachments.return_value = [
            {
                "id": 12345,
                "filename": "design.png",
                "download_url": "https://pivotaltracker.com/files/12345",
                "content_type": "image/png",
                "size": 50000,
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        attachments = adapter.get_issue_attachments("123")

        assert len(attachments) == 1
        assert attachments[0]["id"] == "12345"
        assert attachments[0]["name"] == "design.png"
        mock_client.get_story_attachments.assert_called_once_with(123)

    def test_upload_attachment(self, adapter, mock_client, tmp_path):
        """Should upload a file attachment."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client.upload_file.return_value = {"id": 12345, "filename": "test.txt"}
        mock_client.add_attachment_to_comment.return_value = {"id": 999}

        result = adapter.upload_attachment("123", str(test_file))

        assert result["id"] == 12345
        mock_client.upload_file.assert_called_once()
        mock_client.add_attachment_to_comment.assert_called_once()


# =============================================================================
# Label Tests
# =============================================================================


class TestPivotalAdapterLabels:
    """Tests for label operations."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            return adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_list_labels(self, adapter, mock_client):
        """Should list all labels."""
        mock_client.list_labels.return_value = [
            {"id": 1, "name": "feature"},
            {"id": 2, "name": "bug"},
        ]

        labels = adapter.list_labels()

        assert len(labels) == 2
        mock_client.list_labels.assert_called_once()

    def test_add_label_to_story(self, adapter, mock_client):
        """Should add a label to a story."""
        mock_client.get_or_create_label.return_value = {"id": 100, "name": "priority:high"}
        mock_client.get_story.return_value = {"labels": []}
        mock_client.update_story.return_value = {}

        result = adapter.add_label_to_story("123", "priority:high")

        assert result is True
        mock_client.update_story.assert_called_once()


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestPivotalAdapterErrors:
    """Tests for error handling."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectryn.adapters.pivotal.adapter.PivotalApiClient"):
            adapter = PivotalAdapter(
                api_token="test_token",
                project_id="12345",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            return adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_invalid_story_id_format(self, adapter):
        """Should raise NotFoundError for invalid ID format."""
        with pytest.raises(NotFoundError) as exc_info:
            adapter.get_issue("invalid-not-a-number")

        assert "Invalid story ID format" in str(exc_info.value)

    def test_invalid_subtask_key_format(self, adapter):
        """Should raise NotFoundError for invalid subtask key."""
        with pytest.raises(NotFoundError) as exc_info:
            adapter.update_subtask("invalid-subtask", description="test")

        assert "Invalid subtask key format" in str(exc_info.value)

    def test_story_not_found(self, adapter, mock_client):
        """Should raise NotFoundError when story doesn't exist."""
        mock_client.get_story.side_effect = NotFoundError("Not found")
        mock_client.get_epic.side_effect = NotFoundError("Not found")

        with pytest.raises(NotFoundError):
            adapter.get_issue("99999")
