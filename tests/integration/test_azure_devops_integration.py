"""
Integration tests with mocked Azure DevOps API responses.

These tests verify the full flow from adapter through client
using realistic API responses.
"""

from unittest.mock import Mock, patch

import pytest

from spectryn.adapters.azure_devops.adapter import AzureDevOpsAdapter
from spectryn.core.ports.issue_tracker import IssueTrackerError, TransitionError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def azure_config():
    """Azure DevOps adapter configuration."""
    return {
        "organization": "test-org",
        "project": "TestProject",
        "pat": "test_pat_token_12345",
    }


@pytest.fixture
def mock_connection_response():
    """Mock response for connection data."""
    return {
        "authenticatedUser": {
            "id": "user-123",
            "displayName": "Test User",
            "uniqueName": "test@example.com",
        },
    }


@pytest.fixture
def mock_work_item_response():
    """Mock response for work item GET."""
    return {
        "id": 123,
        "rev": 5,
        "fields": {
            "System.Title": "Sample User Story",
            "System.Description": "<p><strong>As a</strong> developer</p>",
            "System.State": "Active",
            "System.WorkItemType": "User Story",
            "System.AssignedTo": {
                "displayName": "Test User",
                "uniqueName": "test@example.com",
            },
            "Microsoft.VSTS.Scheduling.StoryPoints": 5.0,
        },
        "relations": [],
    }


@pytest.fixture
def mock_work_items_list_response():
    """Mock response for queried work items."""
    return [
        {
            "id": 10,
            "fields": {
                "System.Title": "Story Alpha",
                "System.Description": "First story",
                "System.State": "New",
                "System.WorkItemType": "User Story",
            },
            "relations": [],
        },
        {
            "id": 11,
            "fields": {
                "System.Title": "Story Beta",
                "System.Description": "Second story",
                "System.State": "Active",
                "System.WorkItemType": "User Story",
            },
            "relations": [
                {
                    "rel": "System.LinkTypes.Hierarchy-Forward",
                    "url": "https://dev.azure.com/test-org/_apis/wit/workItems/12",
                }
            ],
        },
    ]


@pytest.fixture
def mock_states_response():
    """Mock response for work item states.

    Note: Order matters - the adapter finds the first matching state.
    "Closed" appears before "Resolved" so that "done" maps to "Closed".
    """
    return [
        {"name": "New", "category": "Proposed"},
        {"name": "Active", "category": "InProgress"},
        {"name": "Closed", "category": "Completed"},
        {"name": "Resolved", "category": "Resolved"},
    ]


@pytest.fixture
def mock_comments_response():
    """Mock response for work item comments."""
    return [
        {
            "id": 1001,
            "text": "This is a comment",
            "createdBy": {"displayName": "Test User"},
            "createdDate": "2024-01-15T10:00:00Z",
        },
    ]


# =============================================================================
# AzureDevOpsAdapter Tests
# =============================================================================


class TestAzureDevOpsAdapterIntegration:
    """Integration tests for AzureDevOpsAdapter with mocked HTTP."""

    def test_get_issue_parses_response(self, azure_config, mock_work_item_response):
        """Test get_issue correctly parses API response."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "get_work_item") as mock_get:
            mock_get.return_value = mock_work_item_response

            issue = adapter.get_issue("123")

            assert issue.key == "123"
            assert issue.summary == "Sample User Story"
            assert issue.status == "Active"
            assert issue.issue_type == "Story"
            assert issue.story_points == 5.0
            assert issue.assignee == "test@example.com"

    def test_get_epic_children(self, azure_config, mock_work_items_list_response):
        """Test get_epic_children fetches child work items."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "get_work_item_children") as mock_children:
            mock_children.return_value = mock_work_items_list_response

            children = adapter.get_epic_children("100")

            assert len(children) == 2
            assert children[0].key == "10"
            assert children[0].summary == "Story Alpha"
            assert children[1].key == "11"
            assert children[1].status == "Active"

    def test_get_issue_comments(self, azure_config, mock_comments_response):
        """Test get_issue_comments returns parsed comments."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "get_comments") as mock_comments:
            mock_comments.return_value = mock_comments_response

            comments = adapter.get_issue_comments("123")

            assert len(comments) == 1
            assert comments[0]["body"] == "This is a comment"

    def test_update_issue_description_dry_run(self, azure_config):
        """Test update_issue_description in dry_run mode."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        result = adapter.update_issue_description("123", "New description")

        assert result is True

    def test_create_subtask(self, azure_config):
        """Test create_subtask creates Task work item."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with patch.object(adapter._client, "create_work_item") as mock_create:
            mock_create.return_value = {"id": 200}

            result = adapter.create_subtask(
                parent_key="123",
                summary="New task",
                description="Task description",
                project_key="TestProject",
                story_points=3,
            )

            assert result == "200"
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("work_item_type") == "Task"
            assert call_kwargs.get("parent_id") == 123
            assert call_kwargs.get("story_points") == 3.0

    def test_transition_issue(self, azure_config, mock_work_item_response, mock_states_response):
        """Test transition_issue changes state."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_work_item") as mock_get,
            patch.object(adapter._client, "get_work_item_states") as mock_states,
            patch.object(adapter._client, "update_work_item") as mock_update,
        ):
            mock_get.return_value = mock_work_item_response
            mock_states.return_value = mock_states_response

            result = adapter.transition_issue("123", "Closed")

            assert result is True
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs.get("state") == "Closed"

    def test_transition_issue_status_mapping(
        self, azure_config, mock_work_item_response, mock_states_response
    ):
        """Test transition_issue maps common status names."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_work_item") as mock_get,
            patch.object(adapter._client, "get_work_item_states") as mock_states,
            patch.object(adapter._client, "update_work_item") as mock_update,
        ):
            mock_get.return_value = mock_work_item_response
            mock_states.return_value = mock_states_response

            # "done" should map to "Closed"
            result = adapter.transition_issue("123", "done")

            assert result is True
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs.get("state") == "Closed"

    def test_transition_issue_invalid_status(
        self, azure_config, mock_work_item_response, mock_states_response
    ):
        """Test transition_issue raises error for invalid status."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_work_item") as mock_get,
            patch.object(adapter._client, "get_work_item_states") as mock_states,
        ):
            mock_get.return_value = mock_work_item_response
            mock_states.return_value = mock_states_response

            with pytest.raises(TransitionError):
                adapter.transition_issue("123", "InvalidStatus")

    def test_add_comment(self, azure_config):
        """Test add_comment adds to work item."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with patch.object(adapter._client, "add_comment") as mock_comment:
            result = adapter.add_comment("123", "This is a comment")

            assert result is True
            mock_comment.assert_called_once_with(123, "This is a comment")

    def test_search_issues(self, azure_config, mock_work_items_list_response):
        """Test search_issues returns matching results."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "search_work_items") as mock_search:
            mock_search.return_value = mock_work_items_list_response

            results = adapter.search_issues("story", max_results=50)

            assert len(results) == 2
            assert results[0].summary == "Story Alpha"


class TestAzureDevOpsConnectionHandling:
    """Tests for connection handling."""

    def test_test_connection_success(self, azure_config, mock_connection_response):
        """Test connection test returns True on success."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "test_connection") as mock_test:
            mock_test.return_value = True

            assert adapter.test_connection() is True

    def test_test_connection_failure(self, azure_config):
        """Test connection test returns False on failure."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "test_connection") as mock_test:
            mock_test.return_value = False

            assert adapter.test_connection() is False

    def test_adapter_name(self, azure_config):
        """Test adapter returns correct name."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)
        assert adapter.name == "Azure DevOps"


class TestAzureDevOpsExtendedOperations:
    """Tests for Azure DevOps-specific extended operations."""

    def test_create_epic(self, azure_config):
        """Test create_epic creates Epic work item."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with patch.object(adapter._client, "create_work_item") as mock_create:
            mock_create.return_value = {"id": 500}

            result = adapter.create_epic("New Epic", "Epic description")

            assert result == "500"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("work_item_type") == "Epic"

    def test_create_user_story(self, azure_config):
        """Test create_user_story creates User Story work item."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=False)

        with patch.object(adapter._client, "create_work_item") as mock_create:
            mock_create.return_value = {"id": 600}

            result = adapter.create_user_story(
                title="New User Story",
                description="Story description",
                parent_id=500,
                story_points=8.0,
                tags=["feature", "sprint-1"],
            )

            assert result == "600"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("work_item_type") == "User Story"
            assert call_kwargs.get("parent_id") == 500
            assert call_kwargs.get("story_points") == 8.0

    def test_query_wiql(self, azure_config, mock_work_items_list_response):
        """Test query_wiql executes WIQL query."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with patch.object(adapter._client, "query_work_items") as mock_query:
            mock_query.return_value = mock_work_items_list_response

            results = adapter.query_wiql(
                "SELECT [System.Id] FROM WorkItems WHERE [System.State] = 'Active'"
            )

            assert len(results) == 2
            mock_query.assert_called_once()

    def test_get_available_transitions(
        self, azure_config, mock_work_item_response, mock_states_response
    ):
        """Test get_available_transitions returns all states."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_work_item") as mock_get,
            patch.object(adapter._client, "get_work_item_states") as mock_states,
        ):
            mock_get.return_value = mock_work_item_response
            mock_states.return_value = mock_states_response

            transitions = adapter.get_available_transitions("123")

            assert len(transitions) == 4
            assert any(t["name"] == "Closed" for t in transitions)

    def test_markdown_to_html_conversion(self, azure_config):
        """Test markdown to HTML conversion."""
        adapter = AzureDevOpsAdapter(**azure_config, dry_run=True)

        markdown = "# Heading\n**Bold** text\n- List item"
        html = adapter.format_description(markdown)

        assert "<h1>" in html
        assert "<strong>" in html
        assert "<li>" in html
