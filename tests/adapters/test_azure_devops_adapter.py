"""
Tests for Azure DevOps Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.azure_devops.adapter import AzureDevOpsAdapter
from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient, AzureDevOpsRateLimiter
from spectryn.adapters.azure_devops.plugin import AzureDevOpsTrackerPlugin, create_plugin
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestAzureDevOpsRateLimiter:
    """Tests for AzureDevOpsRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats

    def test_update_from_response_rate_limited(self):
        """Should handle 429 response."""
        limiter = AzureDevOpsRateLimiter()

        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "5"}
        mock_response.status_code = 429

        original_rate = limiter.requests_per_second
        limiter.update_from_response(mock_response)

        # Rate should be reduced
        assert limiter.requests_per_second < original_rate

    def test_reset(self):
        """Should reset limiter state."""
        limiter = AzureDevOpsRateLimiter(burst_size=5)

        limiter.acquire()
        limiter.acquire()
        limiter.reset()

        stats = limiter.stats
        assert stats["total_requests"] == 0
        assert stats["total_wait_time"] == 0.0


# =============================================================================
# API Client Tests
# =============================================================================


class TestAzureDevOpsApiClient:
    """Tests for AzureDevOpsApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return AzureDevOpsApiClient(
            organization="test-org",
            project="test-project",
            pat="test-pat-token",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        """Should initialize with correct configuration."""
        client = AzureDevOpsApiClient(
            organization="my-org",
            project="my-project",
            pat="my-pat",
        )

        assert client.organization == "my-org"
        assert client.project == "my-project"
        assert client.dry_run is True  # Default

    def test_build_url_wit(self, client):
        """Should build correct WIT API URLs."""
        url = client._build_url("workitems/123", area="wit")
        assert "dev.azure.com/test-org/test-project/_apis/wit/workitems/123" in url

    def test_build_url_core(self, client):
        """Should build correct Core API URLs."""
        url = client._build_url("connectionData", area="core")
        assert "dev.azure.com/test-org/_apis/connectionData" in url

    def test_get_work_item(self, client, mock_session):
        """Should fetch work item data."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.text = '{"id": 123, "fields": {"System.Title": "Test Item"}}'
        mock_response.json.return_value = {"id": 123, "fields": {"System.Title": "Test Item"}}
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.get_work_item(123)

        assert result["id"] == 123
        assert result["fields"]["System.Title"] == "Test Item"

    def test_create_work_item_dry_run(self, mock_session):
        """Should not create in dry_run mode."""
        client = AzureDevOpsApiClient(
            organization="org",
            project="proj",
            pat="pat",
            dry_run=True,
        )

        result = client.create_work_item(
            work_item_type="User Story",
            title="Test Story",
        )

        assert result == {}
        # Should not have made any PATCH request
        for call in mock_session.request.call_args_list:
            if call[0]:
                assert call[0][0] != "PATCH"

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get("connectionData", area="core")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_work_item(99999)

    def test_query_work_items(self, client, mock_session):
        """Should execute WIQL query."""
        # First call returns work item IDs
        query_response = MagicMock()
        query_response.ok = True
        query_response.status_code = 200
        query_response.json.return_value = {"workItems": [{"id": 1}, {"id": 2}]}
        query_response.headers = {}

        # Second call returns full work items
        items_response = MagicMock()
        items_response.ok = True
        items_response.status_code = 200
        items_response.json.return_value = {
            "value": [
                {"id": 1, "fields": {"System.Title": "Item 1"}},
                {"id": 2, "fields": {"System.Title": "Item 2"}},
            ]
        }
        items_response.headers = {}

        mock_session.request.side_effect = [query_response, items_response]

        result = client.query_work_items("SELECT [System.Id] FROM WorkItems")

        assert len(result) == 2
        assert result[0]["fields"]["System.Title"] == "Item 1"

    def test_add_comment(self, client, mock_session):
        """Should add a comment to work item."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 456,
            "text": "Test comment",
        }
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        result = client.add_comment(123, "Test comment")

        assert result["id"] == 456


# =============================================================================
# Adapter Tests
# =============================================================================


class TestAzureDevOpsAdapter:
    """Tests for AzureDevOpsAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectryn.adapters.azure_devops.adapter.AzureDevOpsApiClient") as mock:
            client = MagicMock()
            client.get_work_item_states.return_value = [
                {"name": "New", "category": "Proposed"},
                {"name": "Active", "category": "InProgress"},
                {"name": "Resolved", "category": "Resolved"},
                {"name": "Closed", "category": "Completed"},
            ]
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter with mocked client."""
        return AzureDevOpsAdapter(
            organization="test-org",
            project="test-project",
            pat="test-pat",
            dry_run=True,
        )

    def test_name_property(self, adapter):
        """Should return 'Azure DevOps' as tracker name."""
        assert adapter.name == "Azure DevOps"

    def test_get_issue(self, adapter, mock_client):
        """Should fetch and parse work item data."""
        mock_client.get_work_item.return_value = {
            "id": 123,
            "fields": {
                "System.Title": "Test Story",
                "System.Description": "<p>Description here</p>",
                "System.State": "Active",
                "System.WorkItemType": "User Story",
                "System.AssignedTo": {"displayName": "Test User", "uniqueName": "test@example.com"},
                "Microsoft.VSTS.Scheduling.StoryPoints": 5,
            },
            "relations": [],
        }

        result = adapter.get_issue("123")

        assert result.key == "123"
        assert result.summary == "Test Story"
        assert result.status == "Active"
        assert result.issue_type == "Story"
        assert result.assignee == "test@example.com"
        assert result.story_points == 5.0

    def test_parse_work_item_id_formats(self, adapter, mock_client):
        """Should parse various work item ID formats."""
        mock_client.get_work_item.return_value = {
            "id": 456,
            "fields": {
                "System.Title": "Test",
                "System.State": "New",
                "System.WorkItemType": "Task",
            },
            "relations": [],
        }

        # Test different formats
        for key in ["456", "#456", "AB#456"]:
            result = adapter.get_issue(key)
            assert result.key == "456"
            mock_client.get_work_item.assert_called_with(456)

    def test_get_epic_children(self, adapter, mock_client):
        """Should fetch children of a work item."""
        mock_client.get_work_item_children.return_value = [
            {
                "id": 101,
                "fields": {
                    "System.Title": "Child 1",
                    "System.State": "New",
                    "System.WorkItemType": "User Story",
                },
                "relations": [],
            },
            {
                "id": 102,
                "fields": {
                    "System.Title": "Child 2",
                    "System.State": "Active",
                    "System.WorkItemType": "User Story",
                },
                "relations": [],
            },
        ]

        result = adapter.get_epic_children("100")

        assert len(result) == 2
        assert result[0].summary == "Child 1"

    def test_get_issue_status(self, adapter, mock_client):
        """Should return work item state."""
        mock_client.get_work_item.return_value = {
            "id": 123,
            "fields": {"System.State": "Active"},
        }

        status = adapter.get_issue_status("123")

        assert status == "Active"

    def test_update_description_dry_run(self, adapter, mock_client):
        """Should not update in dry_run mode."""
        result = adapter.update_issue_description("123", "New description")

        assert result is True
        mock_client.update_work_item.assert_not_called()

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create in dry_run mode."""
        result = adapter.create_subtask(
            parent_key="123",
            summary="Task title",
            description="Task description",
            project_key="test",
        )

        assert result is None
        mock_client.create_work_item.assert_not_called()

    def test_transition_issue_dry_run(self, adapter, mock_client):
        """Should not transition in dry_run mode."""
        result = adapter.transition_issue("123", "Active")

        assert result is True
        mock_client.update_work_item.assert_not_called()

    def test_add_comment_dry_run(self, adapter, mock_client):
        """Should not add comment in dry_run mode."""
        result = adapter.add_comment("123", "Test comment")

        assert result is True
        mock_client.add_comment.assert_not_called()

    def test_format_description_converts_markdown(self, adapter):
        """Should convert markdown to HTML."""
        markdown = "# Title\n\nSome **bold** text."

        result = adapter.format_description(markdown)

        assert "<h1>" in result
        assert "<strong>bold</strong>" in result

    def test_get_available_transitions(self, adapter, mock_client):
        """Should return all workflow states."""
        mock_client.get_work_item.return_value = {
            "id": 123,
            "fields": {"System.WorkItemType": "User Story"},
        }

        result = adapter.get_available_transitions("123")

        assert len(result) == 4
        state_names = [t["name"] for t in result]
        assert "New" in state_names
        assert "Active" in state_names
        assert "Closed" in state_names

    def test_find_state_exact_match(self, adapter, mock_client):
        """Should find state by exact match."""
        state = adapter._find_state("User Story", "Active")

        assert state == "Active"

    def test_find_state_partial_match(self, adapter, mock_client):
        """Should find state by partial match."""
        state = adapter._find_state("User Story", "resolve")

        assert state == "Resolved"

    def test_find_state_by_mapping(self, adapter, mock_client):
        """Should find state by common mapping."""
        state = adapter._find_state("User Story", "closed")

        assert state == "Closed"

    def test_markdown_to_html_headers(self, adapter):
        """Should convert markdown headers to HTML."""
        result = adapter._markdown_to_html("# H1\n## H2\n### H3")

        assert "<h1>H1</h1>" in result
        assert "<h2>H2</h2>" in result
        assert "<h3>H3</h3>" in result

    def test_markdown_to_html_bold_italic(self, adapter):
        """Should convert bold and italic."""
        result = adapter._markdown_to_html("**bold** and *italic*")

        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_markdown_to_html_code(self, adapter):
        """Should convert inline code."""
        result = adapter._markdown_to_html("Use `code` here")

        assert "<code>code</code>" in result

    def test_markdown_to_html_links(self, adapter):
        """Should convert markdown links."""
        result = adapter._markdown_to_html("[link](https://example.com)")

        assert '<a href="https://example.com">link</a>' in result


# =============================================================================
# Plugin Tests
# =============================================================================


class TestAzureDevOpsTrackerPlugin:
    """Tests for AzureDevOpsTrackerPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = AzureDevOpsTrackerPlugin()

        assert plugin.metadata.name == "azure-devops"
        assert plugin.metadata.version == "1.0.0"
        assert "Azure DevOps" in plugin.metadata.description

    def test_validate_config_missing_organization(self):
        """Should report missing organization."""
        plugin = AzureDevOpsTrackerPlugin(
            {
                "project": "test",
                "pat": "test",
            }
        )

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("organization" in e.lower() for e in errors)

    def test_validate_config_missing_project(self):
        """Should report missing project."""
        plugin = AzureDevOpsTrackerPlugin(
            {
                "organization": "test",
                "pat": "test",
            }
        )

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("project" in e.lower() for e in errors)

    def test_validate_config_missing_pat(self):
        """Should report missing PAT."""
        plugin = AzureDevOpsTrackerPlugin(
            {
                "organization": "test",
                "project": "test",
            }
        )

        with patch.dict("os.environ", {}, clear=True):
            errors = plugin.validate_config()

        assert any("pat" in e.lower() for e in errors)

    def test_validate_config_from_env(self):
        """Should accept config from environment variables."""
        plugin = AzureDevOpsTrackerPlugin()

        with patch.dict(
            "os.environ",
            {
                "AZURE_DEVOPS_ORG": "test-org",
                "AZURE_DEVOPS_PROJECT": "test-project",
                "AZURE_DEVOPS_PAT": "test-pat",
            },
        ):
            errors = plugin.validate_config()

        assert len(errors) == 0

    def test_initialize_creates_adapter(self):
        """Should create adapter on initialize."""
        plugin = AzureDevOpsTrackerPlugin(
            {
                "organization": "test-org",
                "project": "test-project",
                "pat": "test-pat",
                "dry_run": True,
            }
        )

        with patch("spectryn.adapters.azure_devops.plugin.AzureDevOpsAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()

            assert plugin.is_initialized
            MockAdapter.assert_called_once()

    def test_get_tracker_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = AzureDevOpsTrackerPlugin()

        with pytest.raises(RuntimeError):
            plugin.get_tracker()

    def test_shutdown_cleans_up(self):
        """Should cleanup on shutdown."""
        plugin = AzureDevOpsTrackerPlugin(
            {
                "organization": "test",
                "project": "test",
                "pat": "test",
            }
        )

        with patch("spectryn.adapters.azure_devops.plugin.AzureDevOpsAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter

            plugin.initialize()
            plugin.shutdown()

            assert not plugin.is_initialized
            mock_adapter._client.close.assert_called_once()

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        config = {
            "organization": "test",
            "project": "test",
            "pat": "test",
        }

        plugin = create_plugin(config)

        assert isinstance(plugin, AzureDevOpsTrackerPlugin)
        assert plugin.config == config


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestAzureDevOpsAdapterIntegration:
    """Integration-style tests for AzureDevOpsAdapter workflows."""

    @pytest.fixture
    def live_adapter(self):
        """Create adapter with mocked client for workflow tests."""
        with patch("spectryn.adapters.azure_devops.adapter.AzureDevOpsApiClient") as MockClient:
            client = MagicMock()
            client.get_work_item_states.return_value = [
                {"name": "New", "category": "Proposed"},
                {"name": "Active", "category": "InProgress"},
                {"name": "Resolved", "category": "Resolved"},
                {"name": "Closed", "category": "Completed"},
            ]
            client.is_connected = True
            MockClient.return_value = client

            adapter = AzureDevOpsAdapter(
                organization="test-org",
                project="test-project",
                pat="test-pat",
                dry_run=False,
            )
            adapter._client = client
            yield adapter, client

    def test_create_user_story_workflow(self, live_adapter):
        """Should create a user story."""
        adapter, client = live_adapter
        client.create_work_item.return_value = {"id": 999}

        result = adapter.create_user_story(
            title="New Feature",
            description="Feature description",
            story_points=5,
            assigned_to="developer@example.com",
            state="New",
        )

        assert result == "999"
        client.create_work_item.assert_called_once()
        call_kwargs = client.create_work_item.call_args[1]
        assert call_kwargs["work_item_type"] == "User Story"
        assert call_kwargs["title"] == "New Feature"
        assert call_kwargs["story_points"] == 5

    def test_transition_to_closed(self, live_adapter):
        """Should transition work item to Closed."""
        adapter, client = live_adapter
        client.get_work_item.return_value = {
            "id": 123,
            "fields": {"System.WorkItemType": "User Story"},
        }

        adapter.transition_issue("123", "Closed")

        client.update_work_item.assert_called_once()
        call_args = client.update_work_item.call_args
        assert call_args[0][0] == 123
        assert call_args[1]["state"] == "Closed"

    def test_transition_invalid_state(self, live_adapter):
        """Should raise error for invalid state."""
        adapter, client = live_adapter
        client.get_work_item.return_value = {
            "id": 123,
            "fields": {"System.WorkItemType": "User Story"},
        }

        with pytest.raises(TransitionError) as exc_info:
            adapter.transition_issue("123", "NonexistentState")

        assert "not found" in str(exc_info.value).lower()

    def test_create_task_under_story(self, live_adapter):
        """Should create a Task linked to parent."""
        adapter, client = live_adapter
        client.create_work_item.return_value = {"id": 456}

        result = adapter.create_subtask(
            parent_key="123",
            summary="Task title",
            description="Task description",
            project_key="test",
            story_points=2,
        )

        assert result == "456"
        client.create_work_item.assert_called_once()
        call_kwargs = client.create_work_item.call_args[1]
        assert call_kwargs["work_item_type"] == "Task"
        assert call_kwargs["parent_id"] == 123
        assert call_kwargs["story_points"] == 2.0

    def test_add_comment(self, live_adapter):
        """Should add comment to work item."""
        adapter, client = live_adapter
        client.add_comment.return_value = {"id": 789, "text": "Test comment"}

        result = adapter.add_comment("123", "Test comment")

        assert result is True
        client.add_comment.assert_called_once_with(123, "Test comment")

    def test_create_epic(self, live_adapter):
        """Should create an Epic work item."""
        adapter, client = live_adapter
        client.create_work_item.return_value = {"id": 100}

        result = adapter.create_epic(
            title="Q1 Release",
            description="Release goals",
        )

        assert result == "100"
        client.create_work_item.assert_called_once()
        call_kwargs = client.create_work_item.call_args[1]
        assert call_kwargs["work_item_type"] == "Epic"
        assert call_kwargs["title"] == "Q1 Release"
