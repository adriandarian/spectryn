"""
Tests for ClickUp Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.clickup.adapter import ClickUpAdapter
from spectra.adapters.clickup.client import ClickUpApiClient, ClickUpRateLimiter
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestClickUpRateLimiter:
    """Tests for ClickUpRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = ClickUpRateLimiter(requests_per_minute=100.0)

        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        # Should not raise
        assert len(limiter.request_times) == 3

    def test_rate_limit_enforcement(self):
        """Should wait when rate limit is reached."""
        limiter = ClickUpRateLimiter(requests_per_minute=2.0)  # Very low limit

        # Make 2 requests quickly
        limiter.acquire()
        limiter.acquire()

        # Third request should wait
        import time

        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        # Should have waited at least a bit
        assert elapsed > 0


# =============================================================================
# API Client Tests
# =============================================================================


class TestClickUpApiClient:
    """Tests for ClickUpApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.clickup.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ClickUpApiClient(
            api_token="test_token",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = ClickUpApiClient(api_token="test_token")

        assert client.api_url == "https://api.clickup.com/api/v2"
        assert client.dry_run is True  # Default

    def test_get_user(self, client, mock_session):
        """Should get current user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"user": {"id": "123", "username": "test"}}
        mock_session.request.return_value = mock_response

        result = client.get_user()

        assert result["id"] == "123"
        assert result["username"] == "test"

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_user()

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_task("nonexistent")

    def test_get_task(self, client, mock_session):
        """Should get a task by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task": {
                "id": "abc123",
                "name": "Test Task",
                "description": "Test description",
                "status": {"status": "open"},
            }
        }
        mock_session.request.return_value = mock_response

        result = client.get_task("abc123")

        assert result["id"] == "abc123"
        assert result["name"] == "Test Task"

    def test_create_task_dry_run(self):
        """Should not make API call in dry-run mode."""
        client = ClickUpApiClient(api_token="test_token", dry_run=True)

        result = client.create_task(list_id="list123", name="Test Task")

        assert result["id"] == "dry-run-task-id"
        assert result["name"] == "Test Task"


# =============================================================================
# Adapter Tests
# =============================================================================


class TestClickUpAdapter:
    """Tests for ClickUpAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        return MagicMock(spec=ClickUpApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ClickUpAdapter(
            api_token="test_token",
            list_id="list123",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "ClickUp"

    def test_is_connected(self, adapter, mock_client):
        """Should check connection status."""
        mock_client.is_connected = True
        assert adapter.is_connected is True

        mock_client.is_connected = False
        assert adapter.is_connected is False

    def test_test_connection(self, adapter, mock_client):
        """Should test connection."""
        mock_client.test_connection.return_value = True
        mock_client.get_list.return_value = {"id": "list123"}

        assert adapter.test_connection() is True

    def test_get_current_user(self, adapter, mock_client):
        """Should get current user."""
        mock_client.get_user.return_value = {"id": "123", "username": "test"}

        result = adapter.get_current_user()

        assert result["id"] == "123"
        mock_client.get_user.assert_called_once()

    def test_get_issue(self, adapter, mock_client):
        """Should get an issue by key."""
        mock_task = {
            "id": "abc123",
            "name": "Test Task",
            "description": "Test description",
            "status": {"status": "open"},
            "priority": {"priority": 2},
            "assignees": [],
            "subtasks": [],
            "comments": [],
            "custom_fields": [],
        }
        mock_client.get_task.return_value = mock_task

        result = adapter.get_issue("abc123")

        assert result.key == "abc123"
        assert result.summary == "Test Task"
        assert result.status == "open"

    def test_get_issue_not_found(self, adapter, mock_client):
        """Should raise NotFoundError when issue not found."""
        mock_client.get_task.side_effect = NotFoundError("Task not found")
        mock_client.get_goal.side_effect = NotFoundError("Goal not found")

        with pytest.raises(NotFoundError):
            adapter.get_issue("nonexistent")

    def test_get_epic_children(self, adapter, mock_client):
        """Should get epic children."""
        mock_folder = {"id": "folder123"}
        mock_lists = [{"id": "list1"}]  # Single list
        mock_tasks = [
            {
                "id": "task1",
                "name": "Task 1",
                "status": {"status": "open"},
                "priority": {"priority": 3},
                "assignees": [],
                "subtasks": [],
                "comments": [],
                "custom_fields": [],
            }
        ]

        # get_goal should raise NotFoundError (not a goal)
        mock_client.get_goal.side_effect = NotFoundError("Not a goal")
        mock_client.get_folder.return_value = mock_folder
        mock_client.get_lists.return_value = mock_lists
        mock_client.get_tasks.return_value = mock_tasks

        result = adapter.get_epic_children("folder123")

        assert len(result) == 1
        assert result[0].key == "task1"

    def test_update_issue_description(self, adapter, mock_client):
        """Should update issue description."""
        adapter.update_issue_description("abc123", "New description")

        mock_client.update_task.assert_called_once_with("abc123", description="New description")

    def test_update_issue_description_dry_run(self):
        """Should not update in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", list_id="list123", dry_run=True)
        adapter._client = mock_client

        result = adapter.update_issue_description("abc123", "New description")

        assert result is True
        mock_client.update_task.assert_not_called()

    def test_create_subtask(self, adapter, mock_client):
        """Should create a subtask."""
        mock_parent = {
            "id": "parent123",
            "list": {"id": "list123"},
        }
        mock_subtask = {
            "id": "subtask123",
            "name": "Subtask",
        }

        mock_client.get_task.return_value = mock_parent
        mock_client.create_subtask.return_value = mock_subtask

        result = adapter.create_subtask(
            parent_key="parent123",
            summary="Subtask",
            description="Description",
            project_key="proj",
        )

        assert result == "subtask123"
        mock_client.create_subtask.assert_called_once()

    def test_transition_issue(self, adapter, mock_client):
        """Should transition an issue to new status."""
        mock_task = {
            "id": "abc123",
            "list": {"id": "list123"},
        }
        mock_statuses = [
            {"status": "open", "type": "open"},
            {"status": "in progress", "type": "custom"},
            {"status": "complete", "type": "closed"},
        ]

        mock_client.get_task.return_value = mock_task
        mock_client.get_list_statuses.return_value = mock_statuses

        result = adapter.transition_issue("abc123", "in progress")

        assert result is True
        mock_client.update_task.assert_called_once_with("abc123", status="in progress")

    def test_transition_issue_invalid_status(self, adapter, mock_client):
        """Should raise TransitionError for invalid status."""
        mock_task = {
            "id": "abc123",
            "list": {"id": "list123"},
        }
        mock_statuses = [{"status": "open", "type": "open"}]

        mock_client.get_task.return_value = mock_task
        mock_client.get_list_statuses.return_value = mock_statuses

        with pytest.raises(TransitionError):
            adapter.transition_issue("abc123", "nonexistent")

    def test_get_available_transitions(self, adapter, mock_client):
        """Should get available transitions."""
        mock_task = {
            "id": "abc123",
            "list": {"id": "list123"},
        }
        mock_statuses = [
            {"status": "open", "type": "open"},
            {"status": "in progress", "type": "custom"},
        ]

        mock_client.get_task.return_value = mock_task
        mock_client.get_list_statuses.return_value = mock_statuses

        result = adapter.get_available_transitions("abc123")

        assert len(result) == 2
        assert result[0]["name"] == "open"

    def test_format_description(self, adapter):
        """Should format description (ClickUp uses markdown natively)."""
        markdown = "# Title\n\nBody"
        result = adapter.format_description(markdown)

        assert result == markdown

    def test_priority_mapping(self, adapter):
        """Should map priorities correctly."""
        assert adapter._map_priority_to_clickup("Critical") == 1
        assert adapter._map_priority_to_clickup("High") == 2
        assert adapter._map_priority_to_clickup("Medium") == 3
        assert adapter._map_priority_to_clickup("Low") == 4

    def test_parse_task(self, adapter):
        """Should parse task correctly."""
        task_data = {
            "id": "abc123",
            "name": "Test Task",
            "description": "Description",
            "status": {"status": "open"},
            "priority": {"priority": 2},
            "assignees": [{"username": "user1"}],
            "subtasks": [],
            "comments": [],
            "custom_fields": [],
        }

        result = adapter._parse_task(task_data)

        assert result.key == "abc123"
        assert result.summary == "Test Task"
        assert result.status == "open"
        assert result.assignee == "user1"


# =============================================================================
# Webhook Tests
# =============================================================================


class TestClickUpAdapterWebhooks:
    """Tests for ClickUpAdapter webhook methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        return MagicMock(spec=ClickUpApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ClickUpAdapter(
            api_token="test_token",
            space_id="space123",
            list_id="list123",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_create_webhook(self, adapter, mock_client):
        """Should create a webhook."""
        mock_webhook = {
            "id": "webhook123",
            "endpoint": "https://example.com/webhook",
            "team_id": "team123",
        }
        mock_client.create_webhook.return_value = mock_webhook

        # Mock space to get team_id
        mock_space = {"team": {"id": "team123"}}
        mock_client.get_space.return_value = mock_space

        result = adapter.create_webhook(endpoint="https://example.com/webhook")

        assert result["id"] == "webhook123"
        mock_client.create_webhook.assert_called_once()

    def test_create_webhook_with_team_id(self, adapter, mock_client):
        """Should create a webhook with explicit team_id."""
        mock_webhook = {
            "id": "webhook123",
            "endpoint": "https://example.com/webhook",
        }
        mock_client.create_webhook.return_value = mock_webhook

        result = adapter.create_webhook(endpoint="https://example.com/webhook", team_id="team123")

        assert result["id"] == "webhook123"
        mock_client.create_webhook.assert_called_once_with(
            team_id="team123",
            endpoint="https://example.com/webhook",
            client_id=None,
            events=None,
            task_id=None,
            list_id="list123",
            folder_id=None,
            space_id="space123",
        )

    def test_create_webhook_dry_run(self):
        """Should not create webhook in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", space_id="space123", dry_run=True)
        adapter._client = mock_client

        result = adapter.create_webhook(endpoint="https://example.com/webhook", team_id="team123")

        assert result["id"] == "webhook:dry-run"
        mock_client.create_webhook.assert_not_called()

    def test_create_webhook_missing_team_id(self, adapter, mock_client):
        """Should raise error if team_id is missing and space_id doesn't resolve."""
        mock_client.get_space.side_effect = NotFoundError("Space not found")

        with pytest.raises(IssueTrackerError, match="team_id is required"):
            adapter.create_webhook(endpoint="https://example.com/webhook")

    def test_get_webhook(self, adapter, mock_client):
        """Should get a webhook by ID."""
        mock_webhook = {
            "id": "webhook123",
            "endpoint": "https://example.com/webhook",
        }
        mock_client.get_webhook.return_value = mock_webhook

        result = adapter.get_webhook("webhook123")

        assert result["id"] == "webhook123"
        mock_client.get_webhook.assert_called_once_with("webhook123")

    def test_list_webhooks(self, adapter, mock_client):
        """Should list webhooks."""
        mock_webhooks = [
            {"id": "webhook1", "endpoint": "https://example.com/webhook1"},
            {"id": "webhook2", "endpoint": "https://example.com/webhook2"},
        ]
        mock_client.list_webhooks.return_value = mock_webhooks

        # Mock space to get team_id
        mock_space = {"team": {"id": "team123"}}
        mock_client.get_space.return_value = mock_space

        result = adapter.list_webhooks()

        assert len(result) == 2
        assert result[0]["id"] == "webhook1"
        mock_client.list_webhooks.assert_called_once_with("team123")

    def test_list_webhooks_with_team_id(self, adapter, mock_client):
        """Should list webhooks with explicit team_id."""
        mock_webhooks = [{"id": "webhook1"}]
        mock_client.list_webhooks.return_value = mock_webhooks

        result = adapter.list_webhooks(team_id="team123")

        assert len(result) == 1
        mock_client.list_webhooks.assert_called_once_with("team123")

    def test_update_webhook(self, adapter, mock_client):
        """Should update a webhook."""
        mock_webhook = {"id": "webhook123", "endpoint": "https://new-url.com/webhook"}
        mock_client.update_webhook.return_value = mock_webhook

        result = adapter.update_webhook(
            webhook_id="webhook123", endpoint="https://new-url.com/webhook"
        )

        assert result["endpoint"] == "https://new-url.com/webhook"
        mock_client.update_webhook.assert_called_once_with(
            webhook_id="webhook123",
            endpoint="https://new-url.com/webhook",
            events=None,
            status=None,
        )

    def test_update_webhook_dry_run(self):
        """Should not update webhook in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", dry_run=True)
        adapter._client = mock_client

        result = adapter.update_webhook("webhook123", endpoint="https://new-url.com")

        assert result["id"] == "webhook123"
        mock_client.update_webhook.assert_not_called()

    def test_delete_webhook(self, adapter, mock_client):
        """Should delete a webhook."""
        mock_client.delete_webhook.return_value = True

        result = adapter.delete_webhook("webhook123")

        assert result is True
        mock_client.delete_webhook.assert_called_once_with("webhook123")

    def test_delete_webhook_dry_run(self):
        """Should not delete webhook in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", dry_run=True)
        adapter._client = mock_client

        result = adapter.delete_webhook("webhook123")

        assert result is True
        mock_client.delete_webhook.assert_not_called()


class TestClickUpApiClientWebhooks:
    """Tests for ClickUpApiClient webhook methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectra.adapters.clickup.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return ClickUpApiClient(api_token="test_token", dry_run=False)

    def test_create_webhook(self, client, mock_session):
        """Should create a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "webhook": {
                "id": "webhook123",
                "endpoint": "https://example.com/webhook",
                "team_id": "team123",
            }
        }
        mock_session.request.return_value = mock_response

        result = client.create_webhook(team_id="team123", endpoint="https://example.com/webhook")

        assert result["id"] == "webhook123"
        assert result["endpoint"] == "https://example.com/webhook"

    def test_create_webhook_dry_run(self):
        """Should not make API call in dry-run mode."""
        client = ClickUpApiClient(api_token="test_token", dry_run=True)

        result = client.create_webhook(team_id="team123", endpoint="https://example.com/webhook")

        assert result["id"] == "webhook:dry-run"
        assert result["team_id"] == "team123"

    def test_get_webhook(self, client, mock_session):
        """Should get a webhook by ID."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "webhook": {"id": "webhook123", "endpoint": "https://example.com/webhook"}
        }
        mock_session.request.return_value = mock_response

        result = client.get_webhook("webhook123")

        assert result["id"] == "webhook123"

    def test_list_webhooks(self, client, mock_session):
        """Should list webhooks."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "webhooks": [
                {"id": "webhook1", "endpoint": "https://example.com/webhook1"},
                {"id": "webhook2", "endpoint": "https://example.com/webhook2"},
            ]
        }
        mock_session.request.return_value = mock_response

        result = client.list_webhooks("team123")

        assert len(result) == 2
        assert result[0]["id"] == "webhook1"

    def test_update_webhook(self, client, mock_session):
        """Should update a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "webhook": {
                "id": "webhook123",
                "endpoint": "https://new-url.com/webhook",
            }
        }
        mock_session.request.return_value = mock_response

        result = client.update_webhook(
            webhook_id="webhook123", endpoint="https://new-url.com/webhook"
        )

        assert result["endpoint"] == "https://new-url.com/webhook"

    def test_delete_webhook(self, client, mock_session):
        """Should delete a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        result = client.delete_webhook("webhook123")

        assert result is True

    def test_delete_webhook_dry_run(self):
        """Should not make API call in dry-run mode."""
        client = ClickUpApiClient(api_token="test_token", dry_run=True)

        result = client.delete_webhook("webhook123")

        assert result is True


# =============================================================================
# Time Tracking Tests
# =============================================================================


class TestClickUpAdapterTimeTracking:
    """Tests for ClickUpAdapter time tracking methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        return MagicMock(spec=ClickUpApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ClickUpAdapter(
            api_token="test_token",
            space_id="space123",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_get_task_time_stats(self, adapter, mock_client):
        """Should get time tracking stats."""
        mock_client.get_task_time_stats.return_value = {
            "time_spent": 3600000,
            "time_estimate": 7200000,
            "time_entries_count": 3,
        }

        result = adapter.get_task_time_stats("task123")

        assert result["time_spent"] == 3600000
        assert result["time_estimate"] == 7200000
        mock_client.get_task_time_stats.assert_called_once_with("task123")

    def test_add_spent_time(self, adapter, mock_client):
        """Should add spent time to task."""
        adapter.add_spent_time(
            task_id="task123",
            duration=1800000,
            start=1609459200000,
            billable=True,
            description="Worked on feature",
        )

        mock_client.create_time_entry.assert_called_once_with(
            task_id="task123",
            duration=1800000,
            start=1609459200000,
            billable=True,
            description="Worked on feature",
        )

    def test_add_spent_time_dry_run(self):
        """Should not add time in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", dry_run=True)
        adapter._client = mock_client

        result = adapter.add_spent_time("task123", duration=1800000, start=1609459200000)

        assert result is True
        mock_client.create_time_entry.assert_not_called()

    def test_get_time_entries(self, adapter, mock_client):
        """Should get time entries."""
        mock_entries = [
            {"id": "entry1", "duration": 1800000, "task": {"id": "task123"}},
            {"id": "entry2", "duration": 3600000, "task": {"id": "task456"}},
        ]
        mock_client.get_time_entries.return_value = mock_entries

        # Mock space to get team_id
        mock_space = {"team": {"id": "team123"}}
        mock_client.get_space.return_value = mock_space

        result = adapter.get_time_entries()

        assert len(result) == 2
        mock_client.get_time_entries.assert_called_once()

    def test_get_time_entries_for_task(self, adapter, mock_client):
        """Should get time entries for specific task."""
        mock_entries = [{"id": "entry1", "duration": 1800000}]
        mock_client.get_task_time_entries.return_value = mock_entries

        result = adapter.get_time_entries(task_id="task123")

        assert len(result) == 1
        mock_client.get_task_time_entries.assert_called_once_with("task123")


# =============================================================================
# Dependencies & Relationships Tests
# =============================================================================


class TestClickUpAdapterDependencies:
    """Tests for ClickUpAdapter dependency methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        return MagicMock(spec=ClickUpApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ClickUpAdapter(api_token="test_token", dry_run=False)
        adapter._client = mock_client
        return adapter

    def test_get_issue_links(self, adapter, mock_client):
        """Should get issue links (dependencies)."""
        mock_dependencies = [
            {"task_id": "task456", "type": "waiting_on"},
            {"task_id": "task789", "type": "blocked_by"},
        ]
        mock_client.get_task_dependencies.return_value = mock_dependencies

        links = adapter.get_issue_links("task123")

        assert len(links) == 2
        assert links[0].target_key == "task456"
        assert links[0].link_type.value == "depends on"
        assert links[1].target_key == "task789"
        assert links[1].link_type.value == "is blocked by"

    def test_get_issue_links_empty(self, adapter, mock_client):
        """Should return empty list when no dependencies."""
        mock_client.get_task_dependencies.return_value = []

        links = adapter.get_issue_links("task123")

        assert links == []

    def test_create_link_depends_on(self, adapter, mock_client):
        """Should create a DEPENDS_ON link."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("task123", "task456", LinkType.DEPENDS_ON)

        mock_client.create_task_dependency.assert_called_once_with(
            task_id="task123",
            depends_on_task_id="task456",
            dependency_type="waiting_on",
        )

    def test_create_link_blocked_by(self, adapter, mock_client):
        """Should create a BLOCKS link (maps to blocked_by)."""
        from spectra.core.ports.issue_tracker import LinkType

        adapter.create_link("task123", "task456", LinkType.BLOCKS)

        mock_client.create_task_dependency.assert_called_once_with(
            task_id="task123",
            depends_on_task_id="task456",
            dependency_type="blocked_by",
        )

    def test_create_link_dry_run(self):
        """Should not create link in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", dry_run=True)
        adapter._client = mock_client

        from spectra.core.ports.issue_tracker import LinkType

        result = adapter.create_link("task123", "task456", LinkType.DEPENDS_ON)

        assert result is True
        mock_client.create_task_dependency.assert_not_called()

    def test_delete_link(self, adapter, mock_client):
        """Should delete a link."""
        adapter.delete_link("task123", "task456")

        mock_client.delete_task_dependency.assert_called_once_with("task123", "task456")

    def test_delete_link_dry_run(self):
        """Should not delete link in dry-run mode."""
        mock_client = MagicMock()
        adapter = ClickUpAdapter(api_token="test_token", dry_run=True)
        adapter._client = mock_client

        result = adapter.delete_link("task123", "task456")

        assert result is True
        mock_client.delete_task_dependency.assert_not_called()

    def test_get_link_types(self, adapter):
        """Should get available link types."""
        result = adapter.get_link_types()

        assert len(result) == 2
        assert result[0]["type"] == "waiting_on"
        assert result[1]["type"] == "blocked_by"


# =============================================================================
# Views Tests
# =============================================================================


class TestClickUpAdapterViews:
    """Tests for ClickUpAdapter views methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        return MagicMock(spec=ClickUpApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        """Create an adapter with mocked client."""
        adapter = ClickUpAdapter(
            api_token="test_token",
            space_id="space123",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_get_views(self, adapter, mock_client):
        """Should get views for a team."""
        mock_views = [
            {"id": "view1", "name": "Board View", "type": "board"},
            {"id": "view2", "name": "List View", "type": "list"},
        ]
        mock_client.get_views.return_value = mock_views

        # Mock space to get team_id
        mock_space = {"team": {"id": "team123"}}
        mock_client.get_space.return_value = mock_space

        result = adapter.get_views()

        assert len(result) == 2
        assert result[0]["type"] == "board"
        mock_client.get_views.assert_called_once_with(team_id="team123", view_type=None)

    def test_get_views_with_type(self, adapter, mock_client):
        """Should get views filtered by type."""
        mock_views = [{"id": "view1", "name": "Board View", "type": "board"}]
        mock_client.get_views.return_value = mock_views

        # Mock space to get team_id
        mock_space = {"team": {"id": "team123"}}
        mock_client.get_space.return_value = mock_space

        result = adapter.get_views(view_type="board")

        assert len(result) == 1
        mock_client.get_views.assert_called_once_with(team_id="team123", view_type="board")

    def test_get_view(self, adapter, mock_client):
        """Should get a specific view."""
        mock_view = {"id": "view123", "name": "Board View", "type": "board"}
        mock_client.get_view.return_value = mock_view

        result = adapter.get_view("view123")

        assert result["id"] == "view123"
        mock_client.get_view.assert_called_once_with("view123")

    def test_get_view_tasks(self, adapter, mock_client):
        """Should get tasks from a view."""
        mock_tasks = [
            {
                "id": "task1",
                "name": "Task 1",
                "status": {"status": "open"},
                "priority": {"priority": 3},
                "assignees": [],
                "subtasks": [],
                "comments": [],
                "custom_fields": [],
            }
        ]
        mock_client.get_view_tasks.return_value = mock_tasks

        result = adapter.get_view_tasks("view123")

        assert len(result) == 1
        assert result[0].key == "task1"
        mock_client.get_view_tasks.assert_called_once_with(
            view_id="view123",
            page=0,
            include_closed=False,
        )
