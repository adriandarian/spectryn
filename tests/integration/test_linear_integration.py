"""
Integration tests with mocked Linear API responses.

These tests verify the full flow from adapter through client
using realistic GraphQL responses.
"""

from unittest.mock import Mock, patch

import pytest

from spectryn.adapters.linear.adapter import LinearAdapter
from spectryn.core.ports.issue_tracker import IssueTrackerError, TransitionError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def linear_config():
    """Linear adapter configuration."""
    return {
        "api_key": "lin_api_test_token_12345",
        "team_key": "ENG",
    }


@pytest.fixture
def mock_viewer_response():
    """Mock response for viewer query."""
    return {
        "id": "user-123",
        "name": "Test User",
        "email": "test@example.com",
        "active": True,
    }


@pytest.fixture
def mock_team_response():
    """Mock response for team query."""
    return {
        "id": "team-456",
        "key": "ENG",
        "name": "Engineering",
    }


@pytest.fixture
def mock_issue_response():
    """Mock response for issue query."""
    return {
        "id": "issue-789",
        "identifier": "ENG-123",
        "title": "Sample User Story",
        "description": "**As a** developer\n**I want** a feature",
        "state": {
            "id": "state-1",
            "name": "In Progress",
            "type": "started",
        },
        "estimate": 5,
        "assignee": {
            "id": "user-123",
            "name": "Test User",
            "email": "test@example.com",
        },
        "children": {"nodes": []},
        "comments": {"nodes": []},
    }


@pytest.fixture
def mock_project_issues_response():
    """Mock response for project issues."""
    return [
        {
            "id": "issue-10",
            "identifier": "ENG-10",
            "title": "Story Alpha",
            "description": "First story",
            "state": {"id": "state-1", "name": "Backlog", "type": "backlog"},
            "estimate": 3,
            "children": {"nodes": []},
        },
        {
            "id": "issue-11",
            "identifier": "ENG-11",
            "title": "Story Beta",
            "description": "Second story",
            "state": {"id": "state-2", "name": "In Progress", "type": "started"},
            "estimate": 5,
            "children": {
                "nodes": [
                    {
                        "id": "issue-12",
                        "identifier": "ENG-12",
                        "title": "Subtask",
                        "state": {"name": "Todo"},
                    }
                ]
            },
        },
    ]


@pytest.fixture
def mock_workflow_states_response():
    """Mock response for workflow states."""
    return [
        {"id": "state-1", "name": "Backlog", "type": "backlog"},
        {"id": "state-2", "name": "Todo", "type": "unstarted"},
        {"id": "state-3", "name": "In Progress", "type": "started"},
        {"id": "state-4", "name": "Done", "type": "completed"},
        {"id": "state-5", "name": "Cancelled", "type": "canceled"},
    ]


@pytest.fixture
def mock_comments_response():
    """Mock response for issue comments."""
    return [
        {
            "id": "comment-1",
            "body": "This is a comment",
            "user": {"name": "Test User"},
            "createdAt": "2024-01-15T10:00:00Z",
        },
    ]


# =============================================================================
# LinearAdapter Tests
# =============================================================================


class TestLinearAdapterIntegration:
    """Integration tests for LinearAdapter with mocked GraphQL."""

    def test_get_issue_parses_response(
        self, linear_config, mock_issue_response, mock_team_response
    ):
        """Test get_issue correctly parses API response."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_issue") as mock_get,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_get.return_value = mock_issue_response
            mock_team.return_value = mock_team_response

            issue = adapter.get_issue("ENG-123")

            assert issue.key == "ENG-123"
            assert issue.summary == "Sample User Story"
            assert issue.status == "In Progress"
            assert issue.story_points == 5.0
            assert issue.assignee == "test@example.com"

    def test_get_epic_children_from_project(
        self, linear_config, mock_project_issues_response, mock_team_response
    ):
        """Test get_epic_children fetches project issues."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_project_issues") as mock_project,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_project.return_value = mock_project_issues_response
            mock_team.return_value = mock_team_response

            children = adapter.get_epic_children("project-123")

            assert len(children) == 2
            assert children[0].key == "ENG-10"
            assert children[0].summary == "Story Alpha"
            assert children[1].key == "ENG-11"
            assert len(children[1].subtasks) == 1

    def test_get_issue_comments(self, linear_config, mock_comments_response, mock_team_response):
        """Test get_issue_comments returns parsed comments."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_issue_comments") as mock_comments,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_comments.return_value = mock_comments_response
            mock_team.return_value = mock_team_response

            comments = adapter.get_issue_comments("ENG-123")

            assert len(comments) == 1
            assert comments[0]["body"] == "This is a comment"

    def test_update_issue_description_dry_run(self, linear_config, mock_team_response):
        """Test update_issue_description in dry_run mode."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with patch.object(adapter._client, "get_team_by_key") as mock_team:
            mock_team.return_value = mock_team_response

            result = adapter.update_issue_description("ENG-123", "New description")

            assert result is True

    def test_create_subtask(self, linear_config, mock_issue_response, mock_team_response):
        """Test create_subtask creates sub-issue."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_issue") as mock_get,
            patch.object(adapter._client, "create_issue") as mock_create,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_get.return_value = mock_issue_response
            mock_create.return_value = {"identifier": "ENG-200"}
            mock_team.return_value = mock_team_response

            result = adapter.create_subtask(
                parent_key="ENG-123",
                summary="New subtask",
                description="Subtask description",
                project_key="ENG",
                story_points=3,
            )

            assert result == "ENG-200"
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs.get("estimate") == 3
            assert call_kwargs.get("parent_id") == "issue-789"

    def test_transition_issue(
        self, linear_config, mock_team_response, mock_workflow_states_response
    ):
        """Test transition_issue changes workflow state."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_workflow_states") as mock_states,
            patch.object(adapter._client, "update_issue") as mock_update,
        ):
            mock_team.return_value = mock_team_response
            mock_states.return_value = mock_workflow_states_response

            result = adapter.transition_issue("ENG-123", "Done")

            assert result is True
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs.get("state_id") == "state-4"

    def test_transition_issue_invalid_status(
        self, linear_config, mock_team_response, mock_workflow_states_response
    ):
        """Test transition_issue raises error for invalid status."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_workflow_states") as mock_states,
        ):
            mock_team.return_value = mock_team_response
            mock_states.return_value = mock_workflow_states_response

            with pytest.raises(TransitionError):
                adapter.transition_issue("ENG-123", "InvalidStatus")

    def test_add_comment(self, linear_config, mock_team_response):
        """Test add_comment adds to issue."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "add_comment") as mock_comment,
        ):
            mock_team.return_value = mock_team_response

            result = adapter.add_comment("ENG-123", "This is a comment")

            assert result is True
            mock_comment.assert_called_once_with("ENG-123", "This is a comment")

    def test_search_issues(self, linear_config, mock_project_issues_response, mock_team_response):
        """Test search_issues returns matching results."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "search_issues") as mock_search,
        ):
            mock_team.return_value = mock_team_response
            mock_search.return_value = mock_project_issues_response

            results = adapter.search_issues("story", max_results=50)

            assert len(results) == 2
            assert results[0].summary == "Story Alpha"


class TestLinearConnectionHandling:
    """Tests for connection handling."""

    def test_test_connection_success(self, linear_config, mock_viewer_response, mock_team_response):
        """Test connection test returns True on success."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "test_connection") as mock_conn,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_conn.return_value = True
            mock_team.return_value = mock_team_response

            assert adapter.test_connection() is True

    def test_test_connection_team_not_found(self, linear_config, mock_viewer_response):
        """Test connection test returns False if team not found."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "test_connection") as mock_conn,
            patch.object(adapter._client, "get_team_by_key") as mock_team,
        ):
            mock_conn.return_value = True
            mock_team.return_value = None

            assert adapter.test_connection() is False

    def test_adapter_name(self, linear_config):
        """Test adapter returns correct name."""
        adapter = LinearAdapter(**linear_config, dry_run=True)
        assert adapter.name == "Linear"


class TestLinearExtendedOperations:
    """Tests for Linear-specific extended operations."""

    def test_create_project(self, linear_config, mock_team_response):
        """Test create_project creates Linear project."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "create_project") as mock_create,
        ):
            mock_team.return_value = mock_team_response
            mock_create.return_value = {"id": "project-new"}

            result = adapter.create_project("New Project", "Description")

            assert result == "project-new"
            mock_create.assert_called_once()

    def test_create_issue(self, linear_config, mock_team_response):
        """Test create_issue creates Linear issue."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "create_issue") as mock_create,
        ):
            mock_team.return_value = mock_team_response
            mock_create.return_value = {"identifier": "ENG-999"}

            result = adapter.create_issue(
                title="New Issue",
                description="Issue description",
                estimate=5,
            )

            assert result == "ENG-999"

    def test_list_workflow_states(
        self, linear_config, mock_team_response, mock_workflow_states_response
    ):
        """Test list_workflow_states returns all states."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_workflow_states") as mock_states,
        ):
            mock_team.return_value = mock_team_response
            mock_states.return_value = mock_workflow_states_response

            states = adapter.list_workflow_states()

            assert len(states) == 5
            assert any(s["name"] == "In Progress" for s in states)

    def test_get_available_transitions(
        self, linear_config, mock_team_response, mock_workflow_states_response
    ):
        """Test get_available_transitions returns all states."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_workflow_states") as mock_states,
        ):
            mock_team.return_value = mock_team_response
            mock_states.return_value = mock_workflow_states_response

            transitions = adapter.get_available_transitions("ENG-123")

            assert len(transitions) == 5
            assert any(t["name"] == "Done" for t in transitions)


# =============================================================================
# Linear Batch and Async Operation Tests
# =============================================================================


class TestLinearBatchOperations:
    """Tests for batch operations."""

    def test_bulk_update_descriptions(self, linear_config, mock_team_response):
        """Test bulk update of issue descriptions."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "update_issue") as mock_update,
        ):
            mock_team.return_value = mock_team_response

            updates = [
                ("ENG-1", "New desc 1"),
                ("ENG-2", "New desc 2"),
                ("ENG-3", "New desc 3"),
            ]

            for issue_key, description in updates:
                result = adapter.update_issue_description(issue_key, description)
                assert result is True

            assert mock_update.call_count == 3

    def test_bulk_add_comments(self, linear_config, mock_team_response):
        """Test adding comments to multiple issues."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "add_comment") as mock_comment,
        ):
            mock_team.return_value = mock_team_response

            comments = [
                ("ENG-1", "Comment 1"),
                ("ENG-2", "Comment 2"),
                ("ENG-3", "Comment 3"),
            ]

            for issue_key, comment in comments:
                result = adapter.add_comment(issue_key, comment)
                assert result is True

            assert mock_comment.call_count == 3

    def test_bulk_create_subtasks(self, linear_config, mock_team_response, mock_issue_response):
        """Test creating multiple subtasks."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_issue") as mock_get,
            patch.object(adapter._client, "create_issue") as mock_create,
        ):
            mock_team.return_value = mock_team_response
            mock_get.return_value = mock_issue_response
            mock_create.side_effect = [
                {"identifier": "ENG-100"},
                {"identifier": "ENG-101"},
                {"identifier": "ENG-102"},
            ]

            subtasks = [
                ("Task 1", "Description 1"),
                ("Task 2", "Description 2"),
                ("Task 3", "Description 3"),
            ]

            results = []
            for summary, description in subtasks:
                result = adapter.create_subtask(
                    parent_key="ENG-123",
                    summary=summary,
                    description=description,
                    project_key="ENG",
                )
                results.append(result)

            assert results == ["ENG-100", "ENG-101", "ENG-102"]


class TestLinearEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_issue_with_empty_description(self, linear_config, mock_team_response):
        """Test get_issue handles empty description."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        issue_no_desc = {
            "id": "issue-1",
            "identifier": "ENG-1",
            "title": "Issue without description",
            "description": None,
            "state": {"name": "Backlog"},
            "children": {"nodes": []},
        }

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_issue") as mock_get,
        ):
            mock_team.return_value = mock_team_response
            mock_get.return_value = issue_no_desc

            issue = adapter.get_issue("ENG-1")

            assert issue.key == "ENG-1"
            assert issue.description == "" or issue.description is None

    def test_get_issue_with_nested_subtasks(self, linear_config, mock_team_response):
        """Test get_issue with nested subtasks."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        issue_with_subtasks = {
            "id": "issue-1",
            "identifier": "ENG-1",
            "title": "Parent Issue",
            "description": "Description",
            "state": {"name": "In Progress"},
            "children": {
                "nodes": [
                    {
                        "id": "sub-1",
                        "identifier": "ENG-2",
                        "title": "Subtask 1",
                        "state": {"name": "Todo"},
                    },
                    {
                        "id": "sub-2",
                        "identifier": "ENG-3",
                        "title": "Subtask 2",
                        "state": {"name": "Done"},
                    },
                ]
            },
        }

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_issue") as mock_get,
        ):
            mock_team.return_value = mock_team_response
            mock_get.return_value = issue_with_subtasks

            issue = adapter.get_issue("ENG-1")

            assert issue.key == "ENG-1"
            assert len(issue.subtasks) == 2

    def test_transition_with_case_insensitive_status(
        self, linear_config, mock_team_response, mock_workflow_states_response
    ):
        """Test transition with case insensitive status matching."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_workflow_states") as mock_states,
            patch.object(adapter._client, "update_issue"),
        ):
            mock_team.return_value = mock_team_response
            mock_states.return_value = mock_workflow_states_response

            # Test with different case
            result = adapter.transition_issue("ENG-1", "done")

            assert result is True

    def test_update_issue_with_estimate(self, linear_config, mock_team_response):
        """Test updating issue with estimate."""
        adapter = LinearAdapter(**linear_config, dry_run=False)

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "update_issue") as mock_update,
        ):
            mock_team.return_value = mock_team_response

            result = adapter.update_subtask(
                issue_key="ENG-1",
                story_points=8,
            )

            assert result is True
            call_kwargs = mock_update.call_args.kwargs
            assert call_kwargs.get("estimate") == 8


class TestLinearPriorityMapping:
    """Tests for Linear priority mapping."""

    def test_get_issue_with_priority(self, linear_config, mock_team_response):
        """Test get_issue parses priority correctly."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        issue_with_priority = {
            "id": "issue-1",
            "identifier": "ENG-1",
            "title": "Priority Issue",
            "priority": 1,  # Urgent
            "state": {"name": "Backlog"},
            "children": {"nodes": []},
        }

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_issue") as mock_get,
        ):
            mock_team.return_value = mock_team_response
            mock_get.return_value = issue_with_priority

            issue = adapter.get_issue("ENG-1")

            # Issue parsed successfully
            assert issue.key == "ENG-1"


class TestLinearLabelOperations:
    """Tests for Linear label operations."""

    def test_get_issue_with_labels(self, linear_config, mock_team_response):
        """Test get_issue with labels."""
        adapter = LinearAdapter(**linear_config, dry_run=True)

        issue_with_labels = {
            "id": "issue-1",
            "identifier": "ENG-1",
            "title": "Labeled Issue",
            "state": {"name": "Backlog"},
            "labels": {
                "nodes": [
                    {"name": "bug"},
                    {"name": "frontend"},
                ]
            },
            "children": {"nodes": []},
        }

        with (
            patch.object(adapter._client, "get_team_by_key") as mock_team,
            patch.object(adapter._client, "get_issue") as mock_get,
        ):
            mock_team.return_value = mock_team_response
            mock_get.return_value = issue_with_labels

            issue = adapter.get_issue("ENG-1")

            assert issue.key == "ENG-1"
