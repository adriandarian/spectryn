"""
Tests for Linear Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.linear.adapter import LinearAdapter
from spectryn.adapters.linear.client import LinearApiClient, LinearRateLimiter
from spectryn.adapters.linear.plugin import LinearTrackerPlugin, create_plugin
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestLinearRateLimiter:
    """Tests for LinearRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = LinearRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = LinearRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats
        assert "requests_per_second" in stats

    def test_update_from_response(self):
        """Should update state from Linear response headers."""
        limiter = LinearRateLimiter()

        mock_response = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Requests-Remaining": "1450",
            "X-RateLimit-Requests-Reset": "1234567890",
        }
        mock_response.status_code = 200

        limiter.update_from_response(mock_response)

        stats = limiter.stats
        assert stats["linear_remaining"] == 1450
        assert stats["linear_reset_at"] == 1234567890.0

    def test_reset(self):
        """Should reset limiter state."""
        limiter = LinearRateLimiter(burst_size=5)

        limiter.acquire()
        limiter.acquire()
        limiter.reset()

        stats = limiter.stats
        assert stats["total_requests"] == 0
        assert stats["total_wait_time"] == 0.0


# =============================================================================
# API Client Tests
# =============================================================================


class TestLinearApiClient:
    """Tests for LinearApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.linear.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return LinearApiClient(
            api_key="lin_api_test123",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = LinearApiClient(api_key="lin_api_mykey")

        assert client.api_url == "https://api.linear.app/graphql"
        assert client.dry_run is True  # Default

    def test_execute_query(self, client, mock_session):
        """Should execute GraphQL query."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"viewer": {"id": "user-123", "name": "Test User"}}
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.query("""query { viewer { id name } }""")

        assert result["viewer"]["id"] == "user-123"
        mock_session.post.assert_called_once()

    def test_mutate_respects_dry_run(self, mock_session):
        """Should not execute mutations in dry_run mode."""
        client = LinearApiClient(api_key="test", dry_run=True)

        result = client.mutate("""mutation { issueCreate(...) { ... } }""")

        assert result == {}
        mock_session.post.assert_not_called()

    def test_graphql_errors_raise_exception(self, client, mock_session):
        """Should raise exception on GraphQL errors."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": [{"message": "Issue not found"}]}
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_issue("nonexistent")

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_viewer()

    def test_get_viewer(self, client, mock_session):
        """Should get authenticated user info."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "viewer": {
                    "id": "user-123",
                    "name": "Test User",
                    "email": "test@example.com",
                }
            }
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.get_viewer()

        assert result["id"] == "user-123"
        assert result["email"] == "test@example.com"

    def test_get_teams(self, client, mock_session):
        """Should fetch teams."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "teams": {
                    "nodes": [
                        {"id": "team-1", "key": "ENG", "name": "Engineering"},
                        {"id": "team-2", "key": "DES", "name": "Design"},
                    ]
                }
            }
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.get_teams()

        assert len(result) == 2
        assert result[0]["key"] == "ENG"

    def test_create_issue(self, client, mock_session):
        """Should create a new issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "issue-123",
                        "identifier": "ENG-456",
                        "title": "New Issue",
                    },
                }
            }
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.create_issue(
            team_id="team-1",
            title="New Issue",
            description="Description here",
        )

        assert result["identifier"] == "ENG-456"

    def test_add_comment(self, client, mock_session):
        """Should add a comment to an issue."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {
                        "id": "comment-123",
                        "body": "Test comment",
                    },
                }
            }
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.add_comment("issue-123", "Test comment")

        assert result["id"] == "comment-123"


# =============================================================================
# Adapter Tests
# =============================================================================


class TestLinearAdapter:
    """Tests for LinearAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectryn.adapters.linear.adapter.LinearApiClient") as mock:
            client = MagicMock()
            # Setup default returns
            client.get_team_by_key.return_value = {
                "id": "team-123",
                "key": "ENG",
                "name": "Engineering",
            }
            client.get_workflow_states.return_value = [
                {"id": "state-1", "name": "Backlog", "type": "backlog", "position": 0},
                {"id": "state-2", "name": "Todo", "type": "unstarted", "position": 1},
                {"id": "state-3", "name": "In Progress", "type": "started", "position": 2},
                {"id": "state-4", "name": "Done", "type": "completed", "position": 3},
            ]
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter with mocked client."""
        return LinearAdapter(
            api_key="lin_api_test",
            team_key="ENG",
            dry_run=True,
        )

    def test_name_property(self, adapter):
        """Should return 'Linear' as tracker name."""
        assert adapter.name == "Linear"

    def test_get_issue(self, adapter, mock_client):
        """Should fetch and parse issue data."""
        mock_client.get_issue.return_value = {
            "id": "issue-123",
            "identifier": "ENG-456",
            "title": "Test Issue",
            "description": "Description here",
            "state": {"id": "state-3", "name": "In Progress", "type": "started"},
            "assignee": {"id": "user-1", "name": "Test User", "email": "test@example.com"},
            "estimate": 5,
            "children": {"nodes": []},
            "comments": {"nodes": []},
        }

        result = adapter.get_issue("ENG-456")

        assert result.key == "ENG-456"
        assert result.summary == "Test Issue"
        assert result.status == "In Progress"
        assert result.story_points == 5.0
        assert result.assignee == "test@example.com"

    def test_get_issue_with_subtasks(self, adapter, mock_client):
        """Should parse subtasks from children."""
        mock_client.get_issue.return_value = {
            "id": "issue-123",
            "identifier": "ENG-456",
            "title": "Parent Issue",
            "description": None,
            "state": {"name": "Todo"},
            "assignee": None,
            "estimate": None,
            "children": {
                "nodes": [
                    {
                        "id": "child-1",
                        "identifier": "ENG-457",
                        "title": "Subtask 1",
                        "state": {"name": "Done"},
                    },
                    {
                        "id": "child-2",
                        "identifier": "ENG-458",
                        "title": "Subtask 2",
                        "state": {"name": "Todo"},
                    },
                ]
            },
            "comments": {"nodes": []},
        }

        result = adapter.get_issue("ENG-456")

        assert len(result.subtasks) == 2
        assert result.subtasks[0].key == "ENG-457"
        assert result.subtasks[0].status == "Done"

    def test_get_epic_children_as_project(self, adapter, mock_client):
        """Should fetch children from a project."""
        mock_client.get_project_issues.return_value = [
            {
                "id": "issue-1",
                "identifier": "ENG-101",
                "title": "Story 1",
                "state": {"name": "Todo"},
                "assignee": None,
                "estimate": None,
                "children": {"nodes": []},
                "comments": {"nodes": []},
            },
            {
                "id": "issue-2",
                "identifier": "ENG-102",
                "title": "Story 2",
                "state": {"name": "Done"},
                "assignee": None,
                "estimate": None,
                "children": {"nodes": []},
                "comments": {"nodes": []},
            },
        ]

        result = adapter.get_epic_children("project-123")

        assert len(result) == 2
        assert result[0].key == "ENG-101"

    def test_get_issue_status(self, adapter, mock_client):
        """Should return workflow state name."""
        mock_client.get_issue.return_value = {
            "id": "issue-123",
            "identifier": "ENG-456",
            "state": {"id": "state-3", "name": "In Progress"},
        }

        status = adapter.get_issue_status("ENG-456")

        assert status == "In Progress"

    def test_update_description_dry_run(self, adapter, mock_client):
        """Should not update in dry_run mode."""
        result = adapter.update_issue_description("ENG-456", "New description")

        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create in dry_run mode."""
        result = adapter.create_subtask(
            parent_key="ENG-456",
            summary="Subtask title",
            description="Subtask description",
            project_key="ENG",
        )

        assert result is None
        mock_client.create_issue.assert_not_called()

    def test_transition_issue_dry_run(self, adapter, mock_client):
        """Should not transition in dry_run mode."""
        result = adapter.transition_issue("ENG-456", "Done")

        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_transition_issue_invalid_state(self, adapter, mock_client):
        """Should raise error for invalid state."""
        adapter._dry_run = False

        with pytest.raises(TransitionError) as exc_info:
            adapter.transition_issue("ENG-456", "NonexistentState")

        assert "not found" in str(exc_info.value).lower()

    def test_add_comment_dry_run(self, adapter, mock_client):
        """Should not add comment in dry_run mode."""
        result = adapter.add_comment("ENG-456", "Test comment")

        assert result is True
        mock_client.add_comment.assert_not_called()

    def test_format_description(self, adapter):
        """Should return markdown as-is."""
        markdown = "# Title\n\nSome **bold** text."

        result = adapter.format_description(markdown)

        assert result == markdown

    def test_get_available_transitions(self, adapter, mock_client):
        """Should return all workflow states."""
        result = adapter.get_available_transitions("ENG-456")

        assert len(result) == 4
        state_names = [t["name"] for t in result]
        assert "Backlog" in state_names
        assert "In Progress" in state_names
        assert "Done" in state_names

    def test_find_workflow_state_partial_match(self, adapter, mock_client):
        """Should find state by partial match."""
        state = adapter._find_workflow_state("progress")

        assert state is not None
        assert state["name"] == "In Progress"

    def test_find_workflow_state_by_type(self, adapter, mock_client):
        """Should find state by type mapping."""
        state = adapter._find_workflow_state("closed")

        assert state is not None
        assert state["type"] == "completed"


# =============================================================================
# Plugin Tests
# =============================================================================


class TestLinearTrackerPlugin:
    """Tests for LinearTrackerPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = LinearTrackerPlugin()

        assert plugin.metadata.name == "linear"
        assert plugin.metadata.version == "1.0.0"
        assert "Linear" in plugin.metadata.description

    def test_validate_config_missing_api_key(self):
        """Should report missing API key."""
        plugin = LinearTrackerPlugin({"team_key": "ENG"})

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("api_key" in e.lower() or "api key" in e.lower() for e in errors)

    def test_validate_config_missing_team_key(self):
        """Should report missing team key."""
        plugin = LinearTrackerPlugin({"api_key": "lin_api_test"})

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("team_key" in e.lower() or "team key" in e.lower() for e in errors)

    def test_validate_config_from_env(self):
        """Should accept config from environment variables."""
        plugin = LinearTrackerPlugin()

        with patch.dict(
            "os.environ",
            {
                "LINEAR_API_KEY": "lin_api_test",
                "LINEAR_TEAM_KEY": "ENG",
            },
        ):
            errors = plugin.validate_config()

        assert len(errors) == 0

    def test_initialize_creates_adapter(self):
        """Should create adapter on initialize."""
        plugin = LinearTrackerPlugin(
            {
                "api_key": "lin_api_test",
                "team_key": "ENG",
                "dry_run": True,
            }
        )

        with patch("spectryn.adapters.linear.plugin.LinearAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()

            assert plugin.is_initialized
            MockAdapter.assert_called_once()

    def test_get_tracker_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = LinearTrackerPlugin()

        with pytest.raises(RuntimeError):
            plugin.get_tracker()

    def test_shutdown_cleans_up(self):
        """Should cleanup on shutdown."""
        plugin = LinearTrackerPlugin(
            {
                "api_key": "lin_api_test",
                "team_key": "ENG",
            }
        )

        with patch("spectryn.adapters.linear.plugin.LinearAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()
            plugin.shutdown()

            assert not plugin.is_initialized
            mock_adapter._client.close.assert_called_once()

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        config = {
            "api_key": "lin_api_test",
            "team_key": "ENG",
        }

        plugin = create_plugin(config)

        assert isinstance(plugin, LinearTrackerPlugin)
        assert plugin.config == config


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestLinearAdapterIntegration:
    """Integration-style tests for LinearAdapter workflows."""

    @pytest.fixture
    def live_adapter(self):
        """Create adapter with mocked client for workflow tests."""
        with patch("spectryn.adapters.linear.adapter.LinearApiClient") as MockClient:
            client = MagicMock()
            client.get_team_by_key.return_value = {
                "id": "team-123",
                "key": "ENG",
                "name": "Engineering",
            }
            client.get_workflow_states.return_value = [
                {"id": "state-1", "name": "Backlog", "type": "backlog", "position": 0},
                {"id": "state-2", "name": "Todo", "type": "unstarted", "position": 1},
                {"id": "state-3", "name": "In Progress", "type": "started", "position": 2},
                {"id": "state-4", "name": "Done", "type": "completed", "position": 3},
            ]
            client.is_connected = True
            MockClient.return_value = client

            adapter = LinearAdapter(
                api_key="lin_api_test",
                team_key="ENG",
                dry_run=False,
            )
            adapter._client = client
            yield adapter, client

    def test_create_issue_workflow(self, live_adapter):
        """Should create an issue with all fields."""
        adapter, client = live_adapter
        client.create_issue.return_value = {
            "id": "issue-new",
            "identifier": "ENG-999",
            "title": "New Feature",
        }

        result = adapter.create_issue(
            title="New Feature",
            description="Feature description",
            priority=2,
            estimate=5,
            state_name="Todo",
        )

        assert result == "ENG-999"
        client.create_issue.assert_called_once()
        call_kwargs = client.create_issue.call_args[1]
        assert call_kwargs["title"] == "New Feature"
        assert call_kwargs["estimate"] == 5
        assert call_kwargs["state_id"] == "state-2"  # Todo

    def test_transition_to_done(self, live_adapter):
        """Should transition issue to Done state."""
        adapter, client = live_adapter

        adapter.transition_issue("ENG-456", "Done")

        client.update_issue.assert_called_once()
        call_args = client.update_issue.call_args
        assert call_args[0][0] == "ENG-456"
        assert call_args[1]["state_id"] == "state-4"  # Done

    def test_create_subtask(self, live_adapter):
        """Should create a subtask under parent."""
        adapter, client = live_adapter
        client.get_issue.return_value = {
            "id": "parent-issue-id",
            "identifier": "ENG-100",
        }
        client.create_issue.return_value = {
            "id": "new-subtask-id",
            "identifier": "ENG-101",
            "title": "Subtask",
        }

        result = adapter.create_subtask(
            parent_key="ENG-100",
            summary="Subtask title",
            description="Subtask body",
            project_key="ENG",
            story_points=2,
        )

        assert result == "ENG-101"
        client.create_issue.assert_called_once()
        call_kwargs = client.create_issue.call_args[1]
        assert call_kwargs["parent_id"] == "parent-issue-id"
        assert call_kwargs["estimate"] == 2

    def test_add_comment(self, live_adapter):
        """Should add comment to issue."""
        adapter, client = live_adapter
        client.add_comment.return_value = {
            "id": "comment-123",
            "body": "Test comment body",
        }

        result = adapter.add_comment("ENG-456", "Test comment body")

        assert result is True
        client.add_comment.assert_called_once_with("ENG-456", "Test comment body")

    def test_create_project(self, live_adapter):
        """Should create a project (epic)."""
        adapter, client = live_adapter
        client.create_project.return_value = {
            "id": "project-new",
            "name": "Q1 Release",
        }

        result = adapter.create_project(
            name="Q1 Release",
            description="Q1 2024 Release milestones",
        )

        assert result == "project-new"
        client.create_project.assert_called_once()
        call_kwargs = client.create_project.call_args[1]
        assert call_kwargs["name"] == "Q1 Release"
        assert call_kwargs["team_ids"] == ["team-123"]
