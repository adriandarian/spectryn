"""
Tests for Plane.so Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.plane.adapter import PlaneAdapter
from spectryn.adapters.plane.client import PlaneApiClient, PlaneRateLimiter
from spectryn.core.ports.config_provider import PlaneConfig
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestPlaneRateLimiter:
    """Tests for PlaneRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = PlaneRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = PlaneRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats
        assert "requests_per_second" in stats


# =============================================================================
# API Client Tests
# =============================================================================


class TestPlaneApiClient:
    """Tests for PlaneApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.plane.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return PlaneApiClient(
            api_token="test_api_token",
            workspace_slug="test-workspace",
            project_id="test-project-id",
            dry_run=False,
        )

    def test_init(self, client):
        """Should initialize client with correct parameters."""
        assert client.api_token == "test_api_token"
        assert client.workspace_slug == "test-workspace"
        assert client.project_id == "test-project-id"
        assert client.dry_run is False

    def test_headers(self, client):
        """Should include auth header in requests."""
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer test_api_token"

    def test_get_current_user(self, client, mock_session):
        """Should get current user."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user-123",
            "email": "test@example.com",
            "display_name": "Test User",
        }
        mock_session.request.return_value = mock_response

        user = client.get_current_user()
        assert user["id"] == "user-123"
        assert user["email"] == "test@example.com"

    def test_test_connection_success(self, client, mock_session):
        """Should return True on successful connection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "user-123"}
        mock_session.request.return_value = mock_response

        assert client.test_connection() is True

    def test_test_connection_failure(self, client, mock_session):
        """Should return False on connection failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.request.return_value = mock_response

        assert client.test_connection() is False

    def test_get_project(self, client, mock_session):
        """Should get project information."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test-project-id",
            "name": "Test Project",
            "description": "Test Description",
        }
        mock_session.request.return_value = mock_response

        project = client.get_project()
        assert project["id"] == "test-project-id"
        assert project["name"] == "Test Project"

    def test_get_states(self, client, mock_session):
        """Should get all states."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "state-1", "name": "Backlog", "group": "backlog"},
            {"id": "state-2", "name": "Started", "group": "started"},
        ]
        mock_session.request.return_value = mock_response

        states = client.get_states()
        assert len(states) == 2
        assert states[0]["name"] == "Backlog"

    def test_get_issue(self, client, mock_session):
        """Should get an issue by ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "issue-123",
            "name": "Test Issue",
            "description": "Test Description",
            "state": "state-1",
        }
        mock_session.request.return_value = mock_response

        issue = client.get_issue("issue-123")
        assert issue["id"] == "issue-123"
        assert issue["name"] == "Test Issue"

    def test_create_issue_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client, "request") as mock_request:
            result = client.create_issue(name="Test Issue")
            mock_request.assert_not_called()
            assert result["id"] == "dry-run-issue-id"

    def test_create_issue(self, client, mock_session):
        """Should create an issue."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "issue-123",
            "name": "Test Issue",
            "project": "test-project-id",
        }
        mock_session.request.return_value = mock_response

        issue = client.create_issue(name="Test Issue", description="Test Description")
        assert issue["id"] == "issue-123"
        assert issue["name"] == "Test Issue"

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_current_user()

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_issue("nonexistent")

    def test_create_webhook(self, client, mock_session):
        """Should create a webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
            "events": ["issue.created"],
        }
        mock_session.request.return_value = mock_response

        webhook = client.create_webhook(url="https://example.com/webhook", events=["issue.created"])
        assert webhook["id"] == "webhook-123"
        assert webhook["url"] == "https://example.com/webhook"

    def test_create_webhook_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client, "request") as mock_request:
            result = client.create_webhook(url="https://example.com/webhook")
            mock_request.assert_not_called()
            assert result["id"] == "webhook:dry-run"

    def test_get_webhook(self, client, mock_session):
        """Should get a webhook by ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
        }
        mock_session.request.return_value = mock_response

        webhook = client.get_webhook("webhook-123")
        assert webhook["id"] == "webhook-123"

    def test_list_webhooks(self, client, mock_session):
        """Should list all webhooks."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "webhook-1", "url": "https://example.com/webhook1"},
            {"id": "webhook-2", "url": "https://example.com/webhook2"},
        ]
        mock_session.request.return_value = mock_response

        webhooks = client.list_webhooks()
        assert len(webhooks) == 2
        assert webhooks[0]["id"] == "webhook-1"

    def test_update_webhook(self, client, mock_session):
        """Should update a webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook-123",
            "url": "https://example.com/new-webhook",
        }
        mock_session.request.return_value = mock_response

        webhook = client.update_webhook(
            webhook_id="webhook-123", url="https://example.com/new-webhook"
        )
        assert webhook["id"] == "webhook-123"
        assert webhook["url"] == "https://example.com/new-webhook"

    def test_delete_webhook(self, client, mock_session):
        """Should delete a webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        result = client.delete_webhook("webhook-123")
        assert result is True

    def test_delete_webhook_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client, "request") as mock_request:
            result = client.delete_webhook("webhook-123")
            mock_request.assert_not_called()
            assert result is True

    def test_get_views(self, client, mock_session):
        """Should get all views."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "view-1", "name": "My Issues", "filters": {"assignee": "user-123"}},
            {"id": "view-2", "name": "High Priority", "filters": {"priority": "high"}},
        ]
        mock_session.request.return_value = mock_response

        views = client.get_views()
        assert len(views) == 2
        assert views[0]["name"] == "My Issues"

    def test_get_view(self, client, mock_session):
        """Should get a view by ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "view-123",
            "name": "My Issues",
            "filters": {"assignee": "user-123"},
        }
        mock_session.request.return_value = mock_response

        view = client.get_view("view-123")
        assert view["id"] == "view-123"
        assert view["name"] == "My Issues"

    def test_get_view_issues(self, client, mock_session):
        """Should get issues from a view."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
            {"id": "issue-2", "name": "Issue 2", "state": "state-1"},
        ]
        mock_session.request.return_value = mock_response

        issues = client.get_view_issues("view-123")
        assert len(issues) == 2
        assert issues[0]["id"] == "issue-1"

    def test_create_view(self, client, mock_session):
        """Should create a view."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "view-123",
            "name": "My View",
            "filters": {"state": "started"},
        }
        mock_session.request.return_value = mock_response

        view = client.create_view(
            name="My View", filters={"state": "started"}, description="Test view"
        )
        assert view["id"] == "view-123"
        assert view["name"] == "My View"

    def test_create_view_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client, "request") as mock_request:
            result = client.create_view(name="My View", filters={"state": "started"})
            mock_request.assert_not_called()
            assert result["id"] == "view:dry-run"

    def test_update_view(self, client, mock_session):
        """Should update a view."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "view-123",
            "name": "Updated View",
        }
        mock_session.request.return_value = mock_response

        view = client.update_view(view_id="view-123", name="Updated View")
        assert view["id"] == "view-123"
        assert view["name"] == "Updated View"

    def test_delete_view(self, client, mock_session):
        """Should delete a view."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        result = client.delete_view("view-123")
        assert result is True

    def test_delete_view_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client, "request") as mock_request:
            result = client.delete_view("view-123")
            mock_request.assert_not_called()
            assert result is True

    def test_get_issues_with_filters(self, client, mock_session):
        """Should get issues with additional filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
        ]
        mock_session.request.return_value = mock_response

        issues = client.get_issues(
            state="state-1",
            priority="high",
            assignee="user-123",
            filters={"cycle": "cycle-123", "labels": ["bug"]},
        )
        assert len(issues) == 1
        assert issues[0]["id"] == "issue-1"

    def test_get_issue_attachments(self, client, mock_session):
        """Should get all attachments for an issue."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "att-1", "name": "file1.pdf", "url": "https://example.com/file1.pdf"},
            {"id": "att-2", "name": "file2.png", "url": "https://example.com/file2.png"},
        ]
        mock_session.request.return_value = mock_response

        attachments = client.get_issue_attachments("issue-123")
        assert len(attachments) == 2
        assert attachments[0]["id"] == "att-1"

    def test_upload_issue_attachment(self, client, mock_session):
        """Should upload an attachment."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "att-123",
            "name": "test.pdf",
            "url": "https://example.com/test.pdf",
        }
        mock_session.request.return_value = mock_response
        mock_session.post.return_value = mock_response

        # Create a temporary file for testing
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = tmp_file.name

        try:
            attachment = client.upload_issue_attachment("issue-123", tmp_path, name="test.pdf")
            assert attachment["id"] == "att-123"
        finally:
            Path(tmp_path).unlink()

    def test_upload_issue_attachment_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(b"test content")
            tmp_path = tmp_file.name

        try:
            with patch.object(client._session, "post") as mock_post:
                result = client.upload_issue_attachment("issue-123", tmp_path)
                mock_post.assert_not_called()
                assert result["id"] == "attachment:dry-run"
        finally:
            Path(tmp_path).unlink()

    def test_upload_issue_attachment_file_not_found(self, client):
        """Should raise NotFoundError if file doesn't exist."""
        with pytest.raises(NotFoundError):
            client.upload_issue_attachment("issue-123", "/nonexistent/file.pdf")

    def test_delete_issue_attachment(self, client, mock_session):
        """Should delete an attachment."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_session.delete.return_value = mock_response

        result = client.delete_issue_attachment("issue-123", "att-123")
        assert result is True

    def test_delete_issue_attachment_dry_run(self):
        """Should not make request in dry-run mode."""
        client = PlaneApiClient(
            api_token="test_token",
            workspace_slug="test-workspace",
            project_id="test-project",
            dry_run=True,
        )
        with patch.object(client._session, "delete") as mock_delete:
            result = client.delete_issue_attachment("issue-123", "att-123")
            mock_delete.assert_not_called()
            assert result is True

    def test_download_attachment(self, client, mock_session):
        """Should download an attachment."""
        # Mock get_issue_attachments response
        mock_attachments_response = MagicMock()
        mock_attachments_response.status_code = 200
        mock_attachments_response.json.return_value = [
            {
                "id": "att-123",
                "name": "test.pdf",
                "url": "https://example.com/test.pdf",
            }
        ]
        mock_session.request.return_value = mock_attachments_response

        # Mock download response
        mock_download_response = MagicMock()
        mock_download_response.status_code = 200
        mock_download_response.ok = True
        mock_download_response.iter_content.return_value = [b"file content"]
        mock_session.get.return_value = mock_download_response

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp_dir:
            download_path = Path(tmp_dir) / "downloaded.pdf"
            result = client.download_attachment("issue-123", "att-123", str(download_path))
            assert result is True
            assert download_path.exists()


# =============================================================================
# Adapter Tests
# =============================================================================


class TestPlaneAdapter:
    """Tests for PlaneAdapter."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return PlaneConfig(
            api_token="test_api_token",
            workspace_slug="test-workspace",
            project_id="test-project-id",
        )

    @pytest.fixture
    def adapter(self, config):
        """Create a test adapter."""
        return PlaneAdapter(config=config, dry_run=True)

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Plane"

    def test_is_connected(self, adapter):
        """Should check connection status."""
        adapter._client._current_user = None  # Reset connection
        assert adapter.is_connected is False
        adapter._client._current_user = {"id": "user-123"}  # Set connected
        assert adapter.is_connected is True

    def test_test_connection(self, adapter):
        """Should test connection."""
        with (
            patch.object(adapter._client, "test_connection", return_value=True),
            patch.object(adapter._client, "get_project", return_value={}),
        ):
            assert adapter.test_connection() is True

    def test_get_current_user(self, adapter):
        """Should get current user."""
        mock_user = {"id": "user-123", "email": "test@example.com"}
        with patch.object(adapter._client, "get_current_user", return_value=mock_user):
            user = adapter.get_current_user()
            assert user["id"] == "user-123"

    def test_get_issue(self, adapter):
        """Should get an issue."""
        mock_issue = {
            "id": "issue-123",
            "name": "Test Issue",
            "description": "Test Description",
            "state": "state-1",
            "estimate_point": 5,
        }
        with (
            patch.object(adapter._client, "get_issue", return_value=mock_issue),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            issue = adapter.get_issue("issue-123")
            assert issue.key == "issue-123"
            assert issue.summary == "Test Issue"
            assert issue.story_points == 5.0

    def test_get_epic_children_cycle(self, adapter):
        """Should get epic children as cycle."""
        adapter.config.epic_as_cycle = True
        mock_issues = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
            {"id": "issue-2", "name": "Issue 2", "state": "state-1"},
        ]
        with (
            patch.object(adapter._client, "get_cycle", return_value={"id": "cycle-1"}),
            patch.object(adapter._client, "get_cycle_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            children = adapter.get_epic_children("cycle-1")
            assert len(children) == 2
            assert children[0].key == "issue-1"

    def test_get_epic_children_module(self, adapter):
        """Should get epic children as module."""
        adapter.config.epic_as_cycle = False
        mock_issues = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
        ]
        with (
            patch.object(adapter._client, "get_module", return_value={"id": "module-1"}),
            patch.object(adapter._client, "get_module_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            children = adapter.get_epic_children("module-1")
            assert len(children) == 1

    def test_update_issue_description(self, adapter):
        """Should update issue description."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "update_issue", return_value={}) as mock_update:
            result = adapter.update_issue_description("issue-123", "New Description")
            assert result is True
            mock_update.assert_called_once()

    def test_update_issue_story_points(self, adapter):
        """Should update issue story points."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "update_issue", return_value={}) as mock_update:
            result = adapter.update_issue_story_points("issue-123", 8.0)
            assert result is True
            mock_update.assert_called_once_with("issue-123", estimate_point=8)

    def test_create_subtask(self, adapter):
        """Should create a subtask."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_parent = {"id": "parent-123"}
        mock_result = {"id": "subtask-123"}
        with (
            patch.object(adapter._client, "get_issue", return_value=mock_parent),
            patch.object(adapter._client, "create_issue", return_value=mock_result),
        ):
            result = adapter.create_subtask(
                parent_key="parent-123",
                summary="Subtask",
                description="Description",
                project_key="test-project",
            )
            assert result == "subtask-123"

    def test_transition_issue(self, adapter):
        """Should transition an issue."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_states = {"started": {"id": "state-2", "name": "Started"}}
        with (
            patch.object(adapter, "_get_states", return_value=mock_states),
            patch.object(adapter._client, "update_issue", return_value={}) as mock_update,
        ):
            result = adapter.transition_issue("issue-123", "started")
            assert result is True
            mock_update.assert_called_once_with("issue-123", state_id="state-2")

    def test_transition_issue_not_found(self, adapter):
        """Should raise TransitionError when state not found."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter, "_get_states", return_value={}):
            with pytest.raises(TransitionError) as exc_info:
                adapter.transition_issue("issue-123", "nonexistent")
            assert "nonexistent" in str(exc_info.value)

    def test_get_available_transitions(self, adapter):
        """Should get available transitions."""
        mock_states = {
            "backlog": {"id": "state-1", "name": "Backlog", "group": "backlog"},
            "started": {"id": "state-2", "name": "Started", "group": "started"},
        }
        with patch.object(adapter, "_get_states", return_value=mock_states):
            transitions = adapter.get_available_transitions("issue-123")
            assert len(transitions) == 2
            assert transitions[0]["name"] == "Backlog"

    def test_format_description(self, adapter):
        """Should format description."""
        markdown = "# Test\n\nThis is a test."
        result = adapter.format_description(markdown)
        assert result == markdown

    def test_create_cycle(self, adapter):
        """Should create a cycle."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "cycle-123"}
        with patch.object(adapter._client, "create_cycle", return_value=mock_result):
            cycle_id = adapter.create_cycle(name="Test Cycle", description="Description")
            assert cycle_id == "cycle-123"

    def test_create_module(self, adapter):
        """Should create a module."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "module-123"}
        with patch.object(adapter._client, "create_module", return_value=mock_result):
            module_id = adapter.create_module(name="Test Module", description="Description")
            assert module_id == "module-123"

    # -------------------------------------------------------------------------
    # Webhook Tests
    # -------------------------------------------------------------------------

    def test_create_webhook(self, adapter):
        """Should create a webhook."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {
            "id": "webhook-123",
            "url": "https://example.com/webhook",
            "events": ["issue.created"],
        }
        with patch.object(adapter._client, "create_webhook", return_value=mock_result):
            webhook = adapter.create_webhook(
                url="https://example.com/webhook", events=["issue.created"]
            )
            assert webhook["id"] == "webhook-123"
            assert webhook["url"] == "https://example.com/webhook"

    def test_create_webhook_dry_run(self, adapter):
        """Should not create webhook in dry-run mode."""
        result = adapter.create_webhook(url="https://example.com/webhook")
        assert result["id"] == "webhook:dry-run"
        assert result["url"] == "https://example.com/webhook"

    def test_list_webhooks(self, adapter):
        """Should list webhooks."""
        mock_webhooks = [
            {"id": "webhook-1", "url": "https://example.com/webhook1"},
            {"id": "webhook-2", "url": "https://example.com/webhook2"},
        ]
        with patch.object(adapter._client, "list_webhooks", return_value=mock_webhooks):
            webhooks = adapter.list_webhooks()
            assert len(webhooks) == 2
            assert webhooks[0]["id"] == "webhook-1"

    def test_get_webhook(self, adapter):
        """Should get a webhook by ID."""
        mock_webhook = {"id": "webhook-123", "url": "https://example.com/webhook"}
        with patch.object(adapter._client, "get_webhook", return_value=mock_webhook):
            webhook = adapter.get_webhook("webhook-123")
            assert webhook["id"] == "webhook-123"
            assert webhook["url"] == "https://example.com/webhook"

    def test_update_webhook(self, adapter):
        """Should update a webhook."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "webhook-123", "url": "https://example.com/new-webhook"}
        with patch.object(adapter._client, "update_webhook", return_value=mock_result):
            webhook = adapter.update_webhook(
                webhook_id="webhook-123", url="https://example.com/new-webhook"
            )
            assert webhook["id"] == "webhook-123"
            assert webhook["url"] == "https://example.com/new-webhook"

    def test_update_webhook_dry_run(self, adapter):
        """Should not update webhook in dry-run mode."""
        result = adapter.update_webhook(webhook_id="webhook-123", url="https://example.com/new")
        assert result["id"] == "webhook-123"

    def test_delete_webhook(self, adapter):
        """Should delete a webhook."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "delete_webhook", return_value=True):
            result = adapter.delete_webhook("webhook-123")
            assert result is True

    def test_delete_webhook_dry_run(self, adapter):
        """Should not delete webhook in dry-run mode."""
        result = adapter.delete_webhook("webhook-123")
        assert result is True

    # -------------------------------------------------------------------------
    # Views & Filters Tests
    # -------------------------------------------------------------------------

    def test_get_views(self, adapter):
        """Should get all views."""
        mock_views = [
            {"id": "view-1", "name": "My Issues", "filters": {"assignee": "user-123"}},
            {"id": "view-2", "name": "High Priority", "filters": {"priority": "high"}},
        ]
        with patch.object(adapter._client, "get_views", return_value=mock_views):
            views = adapter.get_views()
            assert len(views) == 2
            assert views[0]["name"] == "My Issues"

    def test_get_view(self, adapter):
        """Should get a view by ID."""
        mock_view = {
            "id": "view-123",
            "name": "My Issues",
            "filters": {"assignee": "user-123"},
        }
        with patch.object(adapter._client, "get_view", return_value=mock_view):
            view = adapter.get_view("view-123")
            assert view["id"] == "view-123"
            assert view["name"] == "My Issues"

    def test_get_view_issues(self, adapter):
        """Should get issues from a view."""
        mock_issues = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
            {"id": "issue-2", "name": "Issue 2", "state": "state-1"},
        ]
        with (
            patch.object(adapter._client, "get_view_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            issues = adapter.get_view_issues("view-123")
            assert len(issues) == 2
            assert issues[0].key == "issue-1"

    def test_create_view(self, adapter):
        """Should create a view."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "view-123", "name": "My View"}
        with patch.object(adapter._client, "create_view", return_value=mock_result):
            view_id = adapter.create_view(
                name="My View", filters={"state": "started"}, description="Test view"
            )
            assert view_id == "view-123"

    def test_create_view_dry_run(self, adapter):
        """Should not create view in dry-run mode."""
        result = adapter.create_view(name="My View", filters={"state": "started"})
        assert result == "view:dry-run"

    def test_update_view(self, adapter):
        """Should update a view."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "view-123", "name": "Updated View"}
        with patch.object(adapter._client, "update_view", return_value=mock_result):
            view = adapter.update_view(view_id="view-123", name="Updated View")
            assert view["id"] == "view-123"
            assert view["name"] == "Updated View"

    def test_update_view_dry_run(self, adapter):
        """Should not update view in dry-run mode."""
        result = adapter.update_view(view_id="view-123", name="Updated View")
        assert result["id"] == "view-123"

    def test_delete_view(self, adapter):
        """Should delete a view."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "delete_view", return_value=True):
            result = adapter.delete_view("view-123")
            assert result is True

    def test_delete_view_dry_run(self, adapter):
        """Should not delete view in dry-run mode."""
        result = adapter.delete_view("view-123")
        assert result is True

    def test_filter_issues(self, adapter):
        """Should filter issues by various criteria."""
        mock_issues = [
            {"id": "issue-1", "name": "Issue 1", "state": "state-1"},
        ]
        with (
            patch.object(adapter._client, "get_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"started": {"id": "state-1", "name": "Started"}},
            ),
            patch.object(adapter, "_get_priority_key", return_value="high"),
        ):
            issues = adapter.filter_issues(state="started", priority="high", assignee="user-123")
            assert len(issues) == 1
            assert issues[0].key == "issue-1"

    def test_filter_issues_with_cycle(self, adapter):
        """Should filter issues by cycle."""
        mock_issues = [{"id": "issue-1", "name": "Issue 1", "state": "state-1"}]
        with (
            patch.object(adapter._client, "get_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            issues = adapter.filter_issues(cycle_id="cycle-123")
            assert len(issues) == 1

    def test_filter_issues_with_module(self, adapter):
        """Should filter issues by module."""
        mock_issues = [{"id": "issue-1", "name": "Issue 1", "state": "state-1"}]
        with (
            patch.object(adapter._client, "get_issues", return_value=mock_issues),
            patch.object(
                adapter,
                "_get_states",
                return_value={"state-1": {"id": "state-1", "name": "Backlog"}},
            ),
        ):
            issues = adapter.filter_issues(module_id="module-123")
            assert len(issues) == 1

    # -------------------------------------------------------------------------
    # Attachment Tests
    # -------------------------------------------------------------------------

    def test_get_issue_attachments(self, adapter):
        """Should get all attachments for an issue."""
        mock_attachments = [
            {"id": "att-1", "name": "file1.pdf", "url": "https://example.com/file1.pdf"},
            {"id": "att-2", "name": "file2.png", "url": "https://example.com/file2.png"},
        ]
        with patch.object(adapter._client, "get_issue_attachments", return_value=mock_attachments):
            attachments = adapter.get_issue_attachments("issue-123")
            assert len(attachments) == 2
            assert attachments[0]["id"] == "att-1"

    def test_upload_attachment(self, adapter):
        """Should upload an attachment."""
        adapter._dry_run = False  # Disable dry-run for this test
        mock_result = {"id": "att-123", "name": "test.pdf", "url": "https://example.com/test.pdf"}
        with patch.object(
            adapter._client, "upload_issue_attachment", return_value=mock_result
        ) as mock_upload:
            result = adapter.upload_attachment("issue-123", "/path/to/file.pdf")
            assert result["id"] == "att-123"
            mock_upload.assert_called_once()

    def test_upload_attachment_dry_run(self, adapter):
        """Should not upload attachment in dry-run mode."""
        result = adapter.upload_attachment("issue-123", "/path/to/file.pdf", name="test.pdf")
        assert result["id"] == "attachment:dry-run"
        assert result["name"] == "test.pdf"

    def test_delete_attachment(self, adapter):
        """Should delete an attachment."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "delete_issue_attachment", return_value=True):
            result = adapter.delete_attachment("issue-123", "att-123")
            assert result is True

    def test_delete_attachment_dry_run(self, adapter):
        """Should not delete attachment in dry-run mode."""
        result = adapter.delete_attachment("issue-123", "att-123")
        assert result is True

    def test_download_attachment(self, adapter):
        """Should download an attachment."""
        adapter._dry_run = False  # Disable dry-run for this test
        with patch.object(adapter._client, "download_attachment", return_value=True):
            result = adapter.download_attachment("issue-123", "att-123", "/path/to/download")
            assert result is True

    def test_download_attachment_dry_run(self, adapter):
        """Should not download attachment in dry-run mode."""
        result = adapter.download_attachment("issue-123", "att-123", "/path/to/download")
        assert result is True
