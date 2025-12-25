"""
Tests for Shortcut Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.shortcut.adapter import ShortcutAdapter
from spectra.adapters.shortcut.client import ShortcutApiClient, ShortcutRateLimiter
from spectra.adapters.shortcut.plugin import ShortcutTrackerPlugin, create_plugin
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestShortcutRateLimiter:
    """Tests for ShortcutRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = ShortcutRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = ShortcutRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "current_tokens" in stats
        assert "requests_per_second" in stats

    def test_update_from_response(self):
        """Should update state from Shortcut response headers."""
        limiter = ShortcutRateLimiter()

        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "60"}
        mock_response.status_code = 200

        limiter.update_from_response(mock_response)

        # Should handle retry-after header
        assert limiter._retry_after is not None


# =============================================================================
# API Client Tests
# =============================================================================


class TestShortcutApiClient:
    """Tests for ShortcutApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ShortcutApiClient(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = ShortcutApiClient(api_token="test_token", workspace_id="test_workspace")

        assert client.api_url == "https://api.app.shortcut.com/api/v3"
        assert client.dry_run is True  # Default

    def test_request_get(self, client, mock_session):
        """Should execute GET request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "name": "Test Story"}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.request("GET", "/stories/123")

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
            client.request("GET", "/member")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.request("GET", "/stories/999")

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
        mock_session.request.return_value = mock_response

        result = client.get_story(123)

        assert result["id"] == 123
        assert result["name"] == "Test Story"

    def test_get_story_dependencies(self, client, mock_session):
        """Should get story dependencies."""
        # Mock get_story to return story with dependencies
        mock_story_response = MagicMock()
        mock_story_response.ok = True
        mock_story_response.status_code = 200
        mock_story_response.json.return_value = {
            "id": 123,
            "depends_on": [{"id": 456}, {"id": 789}],
        }
        mock_story_response.headers = {}
        mock_session.request.return_value = mock_story_response

        deps = client.get_story_dependencies(123)

        assert deps == [456, 789]

    def test_add_story_dependency(self, client, mock_session):
        """Should add a story dependency."""
        # Mock get_story (called first to get current deps)
        mock_get_response = MagicMock()
        mock_get_response.ok = True
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "id": 123,
            "depends_on": [],
        }
        mock_get_response.headers = {}

        # Mock update_story response
        mock_update_response = MagicMock()
        mock_update_response.ok = True
        mock_update_response.status_code = 200
        mock_update_response.json.return_value = {"id": 123}
        mock_update_response.headers = {}

        mock_session.request.side_effect = [mock_get_response, mock_update_response]

        result = client.add_story_dependency(123, 456)

        assert result["id"] == 123
        # Verify update was called with new dependency
        assert mock_session.request.call_count == 2

    def test_remove_story_dependency(self, client, mock_session):
        """Should remove a story dependency."""
        # Mock get_story (called first to get current deps)
        mock_get_response = MagicMock()
        mock_get_response.ok = True
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "id": 123,
            "depends_on": [{"id": 456}, {"id": 789}],
        }
        mock_get_response.headers = {}

        # Mock update_story response
        mock_update_response = MagicMock()
        mock_update_response.ok = True
        mock_update_response.status_code = 200
        mock_update_response.json.return_value = {"id": 123}
        mock_update_response.headers = {}

        mock_session.request.side_effect = [mock_get_response, mock_update_response]

        result = client.remove_story_dependency(123, 456)

        assert result["id"] == 123
        # Verify update was called with dependency removed
        assert mock_session.request.call_count == 2

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
        mock_session.request.return_value = mock_response

        result = client.create_story(name="New Story", description="Description")

        assert result["id"] == 456
        mock_session.request.assert_called_once()

    def test_get_workflow_states(self, client, mock_session):
        """Should get workflow states."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "workflow-1",
                "states": [
                    {"id": 1, "name": "To Do", "type": "unstarted"},
                    {"id": 2, "name": "In Progress", "type": "started"},
                ],
            }
        ]
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        states = client.get_workflow_states()

        assert len(states) == 2
        assert states[0]["name"] == "To Do"


# =============================================================================
# Adapter Tests
# =============================================================================


class TestShortcutAdapter:
    """Tests for ShortcutAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        return MagicMock(spec=ShortcutApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ShortcutAdapter(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,  # Set to False so methods actually call the client
        )
        adapter._client = mock_client
        return adapter

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Shortcut"

    def test_get_issue(self, adapter, mock_client):
        """Should get an issue by key."""
        mock_client.get_story.return_value = {
            "id": 123,
            "name": "Test Story",
            "description": "Description",
            "workflow_state": {"name": "In Progress"},
            "story_type": "feature",
            "estimate": 5,
            "owners": [],
            "tasks": [],
            "comments": [],
        }

        result = adapter.get_issue("123")

        assert result.key == "123"
        assert result.summary == "Test Story"
        assert result.status == "In Progress"

    def test_get_epic_children(self, adapter, mock_client):
        """Should get epic children."""
        mock_client.get_epic_stories.return_value = [
            {
                "id": 1,
                "name": "Story 1",
                "workflow_state": {"name": "To Do"},
                "story_type": "feature",
                "estimate": None,
                "owners": [],
                "tasks": [],
                "comments": [],
            },
            {
                "id": 2,
                "name": "Story 2",
                "workflow_state": {"name": "Done"},
                "story_type": "feature",
                "estimate": 3,
                "owners": [],
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

    def test_transition_issue(self, adapter, mock_client):
        """Should transition an issue."""
        mock_client.get_workflow_states.return_value = [
            {"id": 1, "name": "To Do"},
            {"id": 2, "name": "In Progress"},
            {"id": 3, "name": "Done"},
        ]

        adapter.transition_issue("123", "In Progress")

        mock_client.update_story.assert_called_once_with(123, workflow_state_id=2)

    def test_transition_issue_invalid_state(self, adapter, mock_client):
        """Should raise TransitionError for invalid state."""
        mock_client.get_workflow_states.return_value = [
            {"id": 1, "name": "To Do"},
        ]

        with pytest.raises(TransitionError) as exc_info:
            adapter.transition_issue("123", "Invalid State")
        assert "Invalid State" in str(exc_info.value)

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update story points."""
        adapter.update_issue_story_points("123", 5.0)

        mock_client.update_story.assert_called_once_with(123, estimate=5)

    def test_add_comment(self, adapter, mock_client):
        """Should add a comment."""
        adapter.add_comment("123", "Test comment")

        mock_client.create_comment.assert_called_once_with(123, "Test comment")

    def test_get_issue_links(self, adapter, mock_client):
        """Should get issue links (dependencies)."""
        mock_client.get_story_dependencies.return_value = [456, 789]

        links = adapter.get_issue_links("123")

        assert len(links) == 2
        assert links[0].target_key == "456"
        assert links[1].target_key == "789"
        assert all(link.link_type.value == "depends on" for link in links)

    def test_get_issue_links_empty(self, adapter, mock_client):
        """Should return empty list when no dependencies."""
        mock_client.get_story_dependencies.return_value = []

        links = adapter.get_issue_links("123")

        assert links == []

    def test_create_link_depends_on(self, adapter, mock_client):
        """Should create a DEPENDS_ON link."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("123", "456", LinkType.DEPENDS_ON)

        mock_client.add_story_dependency.assert_called_once_with(123, 456)

    def test_create_link_is_dependency_of(self, adapter, mock_client):
        """Should create an IS_DEPENDENCY_OF link (reverse)."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("123", "456", LinkType.IS_DEPENDENCY_OF)

        mock_client.add_story_dependency.assert_called_once_with(456, 123)

    def test_create_link_blocks(self, adapter, mock_client):
        """Should create a BLOCKS link (target depends on source)."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("123", "456", LinkType.BLOCKS)

        mock_client.add_story_dependency.assert_called_once_with(456, 123)

    def test_create_link_is_blocked_by(self, adapter, mock_client):
        """Should create an IS_BLOCKED_BY link (source depends on target)."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("123", "456", LinkType.IS_BLOCKED_BY)

        mock_client.add_story_dependency.assert_called_once_with(123, 456)

    def test_delete_link(self, adapter, mock_client):
        """Should delete a dependency link."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.delete_link("123", "456", LinkType.DEPENDS_ON)

        mock_client.remove_story_dependency.assert_called_once_with(123, 456)

    def test_delete_link_no_type(self, adapter, mock_client):
        """Should delete link in both directions when type not specified."""
        adapter.delete_link("123", "456")

        # Should try both directions
        assert mock_client.remove_story_dependency.call_count == 2
        mock_client.remove_story_dependency.assert_any_call(123, 456)
        mock_client.remove_story_dependency.assert_any_call(456, 123)


# =============================================================================
# Plugin Tests
# =============================================================================


class TestShortcutTrackerPlugin:
    """Tests for ShortcutTrackerPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        from spectra.plugins.base import PluginType

        plugin = ShortcutTrackerPlugin()
        metadata = plugin.metadata

        assert metadata.name == "shortcut"
        assert metadata.plugin_type == PluginType.TRACKER

    @patch.dict(
        "os.environ", {"SHORTCUT_API_TOKEN": "env_token", "SHORTCUT_WORKSPACE_ID": "env_workspace"}
    )
    def test_initialize_from_env(self):
        """Should initialize from environment variables."""
        plugin = ShortcutTrackerPlugin()
        plugin.config = {}

        with patch("spectra.adapters.shortcut.plugin.ShortcutAdapter") as mock_adapter:
            mock_adapter.return_value = MagicMock()
            plugin.initialize()

            mock_adapter.assert_called_once_with(
                api_token="env_token",
                workspace_id="env_workspace",
                api_url="https://api.app.shortcut.com/api/v3",
                dry_run=True,
            )

    def test_validate_config_missing_token(self):
        """Should validate missing API token."""
        plugin = ShortcutTrackerPlugin()
        plugin.config = {}

        errors = plugin.validate_config()

        assert len(errors) > 0
        assert any("token" in error.lower() for error in errors)

    def test_create_plugin(self):
        """Should create plugin instance."""
        plugin = create_plugin({"api_token": "test", "workspace_id": "ws"})

        assert isinstance(plugin, ShortcutTrackerPlugin)


# =============================================================================
# Webhook Tests
# =============================================================================


class TestShortcutAdapterWebhooks:
    """Tests for webhook functionality."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectra.adapters.shortcut.adapter.ShortcutApiClient"):
            adapter = ShortcutAdapter(
                api_token="test_token",
                workspace_id="test_workspace",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            yield adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_create_webhook(self, adapter, mock_client):
        """Should create a webhook subscription."""
        mock_client.create_webhook.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
            "events": ["story.create", "story.update"],
        }

        result = adapter.create_webhook("https://example.com/webhook")

        assert result["id"] == "webhook-123"
        mock_client.create_webhook.assert_called_once_with(
            url="https://example.com/webhook", events=None, description=None
        )

    def test_create_webhook_with_events(self, adapter, mock_client):
        """Should create webhook with specific events."""
        mock_client.create_webhook.return_value = {"id": "webhook-123"}

        adapter.create_webhook(
            "https://example.com/webhook",
            events=["story.create", "epic.update"],
        )

        mock_client.create_webhook.assert_called_once_with(
            url="https://example.com/webhook",
            events=["story.create", "epic.update"],
            description=None,
        )

    def test_list_webhooks(self, adapter, mock_client):
        """Should list webhook subscriptions."""
        mock_client.list_webhooks.return_value = [
            {"id": "webhook-1", "url": "https://example.com/webhook1"},
            {"id": "webhook-2", "url": "https://example.com/webhook2"},
        ]

        webhooks = adapter.list_webhooks()

        assert len(webhooks) == 2
        assert webhooks[0]["id"] == "webhook-1"
        mock_client.list_webhooks.assert_called_once()

    def test_get_webhook(self, adapter, mock_client):
        """Should get a webhook by ID."""
        mock_client.get_webhook.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
        }

        webhook = adapter.get_webhook("webhook-123")

        assert webhook["id"] == "webhook-123"
        mock_client.get_webhook.assert_called_once_with("webhook-123")

    def test_update_webhook(self, adapter, mock_client):
        """Should update a webhook."""
        mock_client.update_webhook.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/new-webhook",
        }

        result = adapter.update_webhook("webhook-123", url="https://example.com/new-webhook")

        assert result["url"] == "https://example.com/new-webhook"
        mock_client.update_webhook.assert_called_once_with(
            webhook_id="webhook-123",
            url="https://example.com/new-webhook",
            events=None,
            description=None,
            enabled=None,
        )

    def test_delete_webhook(self, adapter, mock_client):
        """Should delete a webhook."""
        mock_client.delete_webhook.return_value = True

        result = adapter.delete_webhook("webhook-123")

        assert result is True
        mock_client.delete_webhook.assert_called_once_with("webhook-123")

    def test_create_webhook_dry_run(self, adapter, mock_client):
        """Should not create webhook in dry-run mode."""
        adapter._dry_run = True

        result = adapter.create_webhook("https://example.com/webhook")

        assert result["id"] == "webhook:dry-run"
        mock_client.create_webhook.assert_not_called()


class TestShortcutApiClientWebhooks:
    """Tests for ShortcutApiClient webhook methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ShortcutApiClient(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,
        )

    def test_create_webhook(self, client, mock_session):
        """Should create a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.create_webhook("https://example.com/webhook")

        assert result["id"] == "webhook-123"
        mock_session.request.assert_called_once()

    def test_list_webhooks(self, client, mock_session):
        """Should list webhooks."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "webhook-1", "url": "https://example.com/webhook1"},
        ]
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        webhooks = client.list_webhooks()

        assert len(webhooks) == 1
        assert webhooks[0]["id"] == "webhook-1"

    def test_get_webhook(self, client, mock_session):
        """Should get a webhook by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        webhook = client.get_webhook("webhook-123")

        assert webhook["id"] == "webhook-123"

    def test_update_webhook(self, client, mock_session):
        """Should update a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "webhook-123", "enabled": False}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.update_webhook("webhook-123", enabled=False)

        assert result["enabled"] is False

    def test_delete_webhook(self, client, mock_session):
        """Should delete a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.delete_webhook("webhook-123")

        assert result is True


# =============================================================================
# Iteration (Sprint) Tests
# =============================================================================


class TestShortcutAdapterIterations:
    """Tests for iteration (sprint) functionality."""

    @pytest.fixture
    def adapter(self):
        """Create an adapter with mocked client."""
        with patch("spectra.adapters.shortcut.adapter.ShortcutApiClient"):
            adapter = ShortcutAdapter(
                api_token="test_token",
                workspace_id="test_workspace",
                dry_run=False,
            )
            mock_client = MagicMock()
            adapter._client = mock_client
            yield adapter

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_list_iterations(self, adapter, mock_client):
        """Should list all iterations."""
        mock_client.list_iterations.return_value = [
            {
                "id": 1,
                "name": "Sprint 2025-W03",
                "start_date": "2025-01-13",
                "end_date": "2025-01-24",
            },
            {
                "id": 2,
                "name": "Sprint 2025-W04",
                "start_date": "2025-01-27",
                "end_date": "2025-02-07",
            },
        ]

        iterations = adapter.list_iterations()

        assert len(iterations) == 2
        assert iterations[0]["name"] == "Sprint 2025-W03"
        mock_client.list_iterations.assert_called_once()

    def test_get_iteration(self, adapter, mock_client):
        """Should get an iteration by ID."""
        mock_client.get_iteration.return_value = {
            "id": 1,
            "name": "Sprint 2025-W03",
            "start_date": "2025-01-13",
            "end_date": "2025-01-24",
        }

        iteration = adapter.get_iteration(1)

        assert iteration["id"] == 1
        assert iteration["name"] == "Sprint 2025-W03"
        mock_client.get_iteration.assert_called_once_with(1)

    def test_create_iteration(self, adapter, mock_client):
        """Should create a new iteration."""
        mock_client.create_iteration.return_value = {
            "id": 1,
            "name": "Sprint 2025-W03",
            "start_date": "2025-01-13",
            "end_date": "2025-01-24",
        }

        result = adapter.create_iteration(
            name="Sprint 2025-W03",
            start_date="2025-01-13",
            end_date="2025-01-24",
        )

        assert result["id"] == 1
        mock_client.create_iteration.assert_called_once_with(
            name="Sprint 2025-W03",
            start_date="2025-01-13",
            end_date="2025-01-24",
            description=None,
        )

    def test_update_iteration(self, adapter, mock_client):
        """Should update an iteration."""
        mock_client.update_iteration.return_value = {"id": 1, "name": "Updated Sprint"}

        result = adapter.update_iteration(1, name="Updated Sprint")

        assert result["name"] == "Updated Sprint"
        mock_client.update_iteration.assert_called_once_with(
            iteration_id=1,
            name="Updated Sprint",
            start_date=None,
            end_date=None,
            description=None,
        )

    def test_delete_iteration(self, adapter, mock_client):
        """Should delete an iteration."""
        mock_client.delete_iteration.return_value = True

        result = adapter.delete_iteration(1)

        assert result is True
        mock_client.delete_iteration.assert_called_once_with(1)

    def test_get_iteration_stories(self, adapter, mock_client):
        """Should get stories in an iteration."""
        mock_client.get_iteration_stories.return_value = [
            {"id": 123, "name": "Story 1"},
            {"id": 456, "name": "Story 2"},
        ]

        stories = adapter.get_iteration_stories(1)

        assert len(stories) == 2
        assert stories[0]["id"] == 123
        mock_client.get_iteration_stories.assert_called_once_with(1)

    def test_assign_story_to_iteration(self, adapter, mock_client):
        """Should assign a story to an iteration."""
        mock_client.assign_story_to_iteration.return_value = {"id": 123, "iteration_id": 1}

        result = adapter.assign_story_to_iteration(123, 1)

        assert result is True
        mock_client.assign_story_to_iteration.assert_called_once_with(123, 1)

    def test_remove_story_from_iteration(self, adapter, mock_client):
        """Should remove a story from its iteration."""
        mock_client.remove_story_from_iteration.return_value = {"id": 123, "iteration_id": None}

        result = adapter.remove_story_from_iteration(123)

        assert result is True
        mock_client.remove_story_from_iteration.assert_called_once_with(123)

    def test_create_iteration_dry_run(self, adapter):
        """Should not create iteration in dry-run mode."""
        adapter._dry_run = True

        result = adapter.create_iteration(
            name="Sprint 2025-W03",
            start_date="2025-01-13",
            end_date="2025-01-24",
        )

        assert result["id"] == 0
        assert result["name"] == "Sprint 2025-W03"
        adapter._client.create_iteration.assert_not_called()


class TestShortcutApiClientIterations:
    """Tests for ShortcutApiClient iteration methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ShortcutApiClient(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,
        )

    def test_list_iterations(self, client, mock_session):
        """Should list iterations."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 1,
                "name": "Sprint 2025-W03",
                "start_date": "2025-01-13",
                "end_date": "2025-01-24",
            },
        ]
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        iterations = client.list_iterations()

        assert len(iterations) == 1
        assert iterations[0]["name"] == "Sprint 2025-W03"

    def test_get_iteration(self, client, mock_session):
        """Should get an iteration by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "name": "Sprint 2025-W03",
            "start_date": "2025-01-13",
            "end_date": "2025-01-24",
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        iteration = client.get_iteration(1)

        assert iteration["id"] == 1
        assert iteration["name"] == "Sprint 2025-W03"

    def test_create_iteration(self, client, mock_session):
        """Should create an iteration."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "name": "Sprint 2025-W03",
            "start_date": "2025-01-13",
            "end_date": "2025-01-24",
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.create_iteration(
            name="Sprint 2025-W03",
            start_date="2025-01-13",
            end_date="2025-01-24",
        )

        assert result["id"] == 1
        mock_session.request.assert_called_once()

    def test_update_iteration(self, client, mock_session):
        """Should update an iteration."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "Updated Sprint"}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.update_iteration(1, name="Updated Sprint")

        assert result["name"] == "Updated Sprint"

    def test_delete_iteration(self, client, mock_session):
        """Should delete an iteration."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.delete_iteration(1)

        assert result is True

    def test_get_iteration_stories(self, client, mock_session):
        """Should get stories in an iteration."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 123, "name": "Story 1"}]
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        stories = client.get_iteration_stories(1)

        assert len(stories) == 1
        assert stories[0]["id"] == 123

    def test_assign_story_to_iteration(self, client, mock_session):
        """Should assign story to iteration."""
        # Mock update_story response (assign_story_to_iteration calls update_story directly)
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "name": "Story 1"}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.assign_story_to_iteration(123, 1)

        assert result["id"] == 123
        mock_session.request.assert_called_once()


# =============================================================================
# Attachment Tests
# =============================================================================


class TestShortcutAdapterAttachments:
    """Tests for ShortcutAdapter file attachment operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ShortcutApiClient."""
        return MagicMock(spec=ShortcutApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create adapter with mock client."""
        adapter = ShortcutAdapter(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_get_issue_attachments(self, adapter, mock_client):
        """Should get attachments for an issue."""
        mock_client.get_story_files.return_value = [
            {
                "id": 12345,
                "name": "design.png",
                "url": "https://files.shortcut.com/12345",
                "content_type": "image/png",
                "size": 50000,
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        attachments = adapter.get_issue_attachments("123")

        assert len(attachments) == 1
        assert attachments[0]["id"] == "12345"
        assert attachments[0]["name"] == "design.png"
        assert attachments[0]["url"] == "https://files.shortcut.com/12345"
        assert attachments[0]["content_type"] == "image/png"
        mock_client.get_story_files.assert_called_once_with(123)

    def test_upload_attachment(self, adapter, mock_client, tmp_path):
        """Should upload a file attachment."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client.upload_file.return_value = {"id": 12345, "name": "test.txt"}
        mock_client.link_file_to_story.return_value = {"id": 123}

        result = adapter.upload_attachment("123", str(test_file))

        assert result["id"] == 12345
        assert result["name"] == "test.txt"
        mock_client.upload_file.assert_called_once_with(str(test_file), None)
        mock_client.link_file_to_story.assert_called_once_with(123, 12345)

    def test_upload_attachment_with_name(self, adapter, mock_client, tmp_path):
        """Should upload a file attachment with custom name."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client.upload_file.return_value = {"id": 12345, "name": "custom-name.txt"}
        mock_client.link_file_to_story.return_value = {"id": 123}

        result = adapter.upload_attachment("123", str(test_file), name="custom-name.txt")

        assert result["name"] == "custom-name.txt"
        mock_client.upload_file.assert_called_once_with(str(test_file), "custom-name.txt")

    def test_upload_attachment_dry_run(self):
        """Should not upload in dry run mode."""
        mock_client = MagicMock(spec=ShortcutApiClient)
        adapter = ShortcutAdapter(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=True,
        )
        adapter._client = mock_client

        result = adapter.upload_attachment("123", "/path/to/file.txt")

        assert result["id"] == "attachment:dry-run"
        mock_client.upload_file.assert_not_called()
        mock_client.link_file_to_story.assert_not_called()

    def test_delete_attachment(self, adapter, mock_client):
        """Should delete a file attachment."""
        mock_client.unlink_file_from_story.return_value = {"id": 123}
        mock_client.delete_file.return_value = True

        result = adapter.delete_attachment("123", "12345")

        assert result is True
        mock_client.unlink_file_from_story.assert_called_once_with(123, 12345)
        mock_client.delete_file.assert_called_once_with(12345)

    def test_delete_attachment_dry_run(self):
        """Should not delete in dry run mode."""
        mock_client = MagicMock(spec=ShortcutApiClient)
        adapter = ShortcutAdapter(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=True,
        )
        adapter._client = mock_client

        result = adapter.delete_attachment("123", "12345")

        assert result is True
        mock_client.unlink_file_from_story.assert_not_called()
        mock_client.delete_file.assert_not_called()


class TestShortcutApiClientAttachments:
    """Tests for ShortcutApiClient file attachment operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ShortcutApiClient(
            api_token="test_token",
            workspace_id="test_workspace",
            dry_run=False,
        )

    def test_get_story_files(self, client, mock_session):
        """Should get files attached to a story."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "files": [
                {"id": 12345, "name": "design.png"},
                {"id": 12346, "name": "notes.pdf"},
            ],
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        files = client.get_story_files(123)

        assert len(files) == 2
        assert files[0]["name"] == "design.png"
        assert files[1]["name"] == "notes.pdf"

    def test_upload_file(self, client, mock_session, tmp_path):
        """Should upload a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": 12345, "name": "test.txt"}]
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.upload_file(str(test_file))

        assert result["id"] == 12345
        assert result["name"] == "test.txt"
        mock_session.post.assert_called_once()

    def test_upload_file_dry_run(self):
        """Should not upload in dry run mode."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            mock_session = MagicMock()
            mock.return_value = mock_session
            client = ShortcutApiClient(
                api_token="test_token",
                workspace_id="test_workspace",
                dry_run=True,
            )

        result = client.upload_file("/path/to/file.txt", "custom-name.txt")

        assert result["id"] == "file:dry-run"
        mock_session.post.assert_not_called()

    def test_link_file_to_story(self, client, mock_session):
        """Should link file to story."""
        # Mock get_story to return current file_ids
        get_response = MagicMock()
        get_response.ok = True
        get_response.status_code = 200
        get_response.json.return_value = {"id": 123, "file_ids": [100, 101]}
        get_response.headers = {}

        # Mock update_story response
        update_response = MagicMock()
        update_response.ok = True
        update_response.status_code = 200
        update_response.json.return_value = {"id": 123, "file_ids": [100, 101, 12345]}
        update_response.headers = {}

        mock_session.request.side_effect = [get_response, update_response]

        result = client.link_file_to_story(123, 12345)

        assert result["id"] == 123
        assert 12345 in result["file_ids"]

    def test_unlink_file_from_story(self, client, mock_session):
        """Should unlink file from story."""
        # Mock get_story to return current file_ids
        get_response = MagicMock()
        get_response.ok = True
        get_response.status_code = 200
        get_response.json.return_value = {"id": 123, "file_ids": [100, 101, 12345]}
        get_response.headers = {}

        # Mock update_story response
        update_response = MagicMock()
        update_response.ok = True
        update_response.status_code = 200
        update_response.json.return_value = {"id": 123, "file_ids": [100, 101]}
        update_response.headers = {}

        mock_session.request.side_effect = [get_response, update_response]

        result = client.unlink_file_from_story(123, 12345)

        assert result["id"] == 123
        assert 12345 not in result["file_ids"]

    def test_delete_file(self, client, mock_session):
        """Should delete a file."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.delete_file(12345)

        assert result is True

    def test_delete_file_dry_run(self):
        """Should not delete in dry run mode."""
        with patch("spectra.adapters.shortcut.client.requests.Session") as mock:
            mock_session = MagicMock()
            mock.return_value = mock_session
            client = ShortcutApiClient(
                api_token="test_token",
                workspace_id="test_workspace",
                dry_run=True,
            )

        result = client.delete_file(12345)

        assert result is True
        mock_session.request.assert_not_called()
