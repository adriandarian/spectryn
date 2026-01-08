"""
Tests for GitLab Issues Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.gitlab.adapter import GitLabAdapter
from spectryn.adapters.gitlab.client import GitLabApiClient
from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Adapter Tests
# =============================================================================


class TestGitLabAdapter:
    """Tests for GitLabAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectryn.adapters.gitlab.adapter.GitLabApiClient") as mock:
            client = MagicMock()
            client.list_labels.return_value = []
            client.is_connected = True
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter with mocked client."""
        adapter = GitLabAdapter(
            token="test-token",
            project_id="12345",
            dry_run=False,  # Set to False so we can test actual calls
        )
        adapter._client = mock_client
        return adapter

    def test_name_property(self, adapter):
        """Should return 'GitLab' as tracker name."""
        assert adapter.name == "GitLab"

    def test_is_connected(self, adapter, mock_client):
        """Should return connection status."""
        assert adapter.is_connected is True

    def test_test_connection(self, adapter, mock_client):
        """Should test connection."""
        mock_client.test_connection.return_value = True
        assert adapter.test_connection() is True

    def test_get_current_user(self, adapter, mock_client):
        """Should get current authenticated user."""
        mock_client.get_authenticated_user.return_value = {
            "id": 1,
            "username": "testuser",
        }
        result = adapter.get_current_user()
        assert result["username"] == "testuser"

    def test_get_issue(self, adapter, mock_client):
        """Should fetch and parse issue data."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "id": 456789,
            "title": "Test Story",
            "description": "Story description",
            "state": "opened",
            "labels": [{"name": "story"}],
            "assignees": [{"username": "testuser", "id": 1}],
            "weight": 5,
        }

        result = adapter.get_issue("#123")

        assert result.key == "#123"
        assert result.summary == "Test Story"
        assert result.status == "open"
        assert result.issue_type == "Story"
        assert result.assignee == "testuser"
        assert result.story_points == 5.0

    def test_parse_issue_key_formats(self, adapter, mock_client):
        """Should parse various issue key formats."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "title": "Test",
            "state": "opened",
            "labels": [],
        }

        # Test different formats
        adapter.get_issue("123")
        adapter.get_issue("#123")
        adapter.get_issue("project#123")

        assert mock_client.get_issue.call_count == 3

    def test_get_epic_children_from_milestone(self, adapter, mock_client):
        """Should get children from milestone."""
        mock_client.list_issues.return_value = [
            {
                "iid": 1,
                "title": "Story 1",
                "state": "opened",
                "labels": [{"name": "story"}],
            },
            {
                "iid": 2,
                "title": "Epic",
                "state": "opened",
                "labels": [{"name": "epic"}],
            },
        ]

        result = adapter.get_epic_children("1")

        assert len(result) == 1
        assert result[0].summary == "Story 1"

    def test_get_epic_children_from_epic_issue(self, adapter, mock_client):
        """Should get children from epic issue."""
        mock_client.get_issue.return_value = {
            "iid": 10,
            "title": "Epic",
            "state": "opened",
            "labels": [{"name": "epic"}],
            "description": "",
        }
        mock_client.list_issues.return_value = [
            {
                "iid": 1,
                "title": "Story 1",
                "state": "opened",
                "labels": [{"name": "story"}],
                "description": "Epic: #10",
            }
        ]

        result = adapter.get_epic_children("#10")

        assert len(result) == 1
        assert result[0].summary == "Story 1"

    def test_get_issue_status(self, adapter, mock_client):
        """Should get issue status from labels."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "opened",
            "labels": [{"name": "status:in-progress"}],
        }

        status = adapter.get_issue_status("#123")

        assert status == "in progress"

    def test_get_issue_status_fallback(self, adapter, mock_client):
        """Should fallback to state if no status label."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "closed",
            "labels": [],
        }

        status = adapter.get_issue_status("#123")

        assert status == "closed"

    def test_get_issue_comments(self, adapter, mock_client):
        """Should fetch issue comments."""
        mock_client.get_issue_comments.return_value = [
            {"id": 1, "body": "Comment 1"},
            {"id": 2, "body": "Comment 2"},
        ]

        comments = adapter.get_issue_comments("#123")

        assert len(comments) == 2
        assert comments[0]["body"] == "Comment 1"

    def test_search_issues(self, adapter, mock_client):
        """Should search issues by labels and state."""
        mock_client.list_issues.return_value = [
            {
                "iid": 1,
                "title": "Bug",
                "state": "opened",
                "labels": [{"name": "bug"}],
            }
        ]

        result = adapter.search_issues("label:bug state:opened", max_results=10)

        assert len(result) == 1
        assert result[0].summary == "Bug"

    def test_update_issue_description(self, adapter, mock_client):
        """Should update issue description."""
        mock_client.update_issue.return_value = {"iid": 123}

        result = adapter.update_issue_description("#123", "New description")

        assert result is True
        mock_client.update_issue.assert_called_once()
        call_args = mock_client.update_issue.call_args
        assert call_args[0][0] == 123
        assert call_args[1]["description"] == "New description"

    def test_update_issue_description_dry_run(self, adapter, mock_client):
        """Should not update in dry-run mode."""
        adapter._dry_run = True
        result = adapter.update_issue_description("#123", "New description")
        assert result is True
        mock_client.update_issue.assert_not_called()

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update issue weight (story points)."""
        mock_client.update_issue.return_value = {"iid": 123}

        result = adapter.update_issue_story_points("#123", 8.0)

        assert result is True
        mock_client.update_issue.assert_called_once()
        call_args = mock_client.update_issue.call_args
        assert call_args[0][0] == 123
        assert call_args[1]["weight"] == 8

    def test_create_subtask(self, adapter, mock_client):
        """Should create a subtask issue."""
        mock_client.create_issue.return_value = {
            "iid": 456,
            "title": "Subtask",
        }

        result = adapter.create_subtask(
            parent_key="#123",
            summary="Subtask title",
            description="Subtask description",
            project_key="12345",
            story_points=3,
        )

        assert result == "#456"
        mock_client.create_issue.assert_called_once()
        call_args = mock_client.create_issue.call_args
        call_kwargs = call_args[1] if call_args else {}
        assert call_kwargs.get("title") == "Subtask title"
        assert call_kwargs.get("weight") == 3
        assert "subtask" in call_kwargs.get("labels", [])

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create in dry-run mode."""
        adapter._dry_run = True
        result = adapter.create_subtask(
            parent_key="#123",
            summary="Subtask",
            description="Desc",
            project_key="12345",
        )
        assert result is None
        mock_client.create_issue.assert_not_called()

    def test_update_subtask(self, adapter, mock_client):
        """Should update subtask fields."""
        mock_client.update_issue.return_value = {"iid": 456}

        result = adapter.update_subtask(
            issue_key="#456",
            description="Updated description",
            story_points=5,
        )

        assert result is True
        mock_client.update_issue.assert_called_once()
        call_args = mock_client.update_issue.call_args
        call_kwargs = call_args[1] if call_args else {}
        assert call_kwargs.get("description") == "Updated description"
        assert call_kwargs.get("weight") == 5

    def test_add_comment(self, adapter, mock_client):
        """Should add a comment to an issue."""
        mock_client.add_issue_comment.return_value = {"id": 789}

        result = adapter.add_comment("#123", "Comment text")

        assert result is True
        mock_client.add_issue_comment.assert_called_once_with(123, "Comment text")

    def test_transition_issue(self, adapter, mock_client):
        """Should transition issue status."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "opened",
            "labels": [{"name": "story"}],
        }
        mock_client.update_issue.return_value = {"iid": 123}

        result = adapter.transition_issue("#123", "in progress")

        assert result is True
        mock_client.update_issue.assert_called_once()
        call_args = mock_client.update_issue.call_args
        call_kwargs = call_args[1] if call_args else {}
        assert "status:in-progress" in call_kwargs.get("labels", [])

    def test_transition_issue_to_done(self, adapter, mock_client):
        """Should close issue when transitioning to done."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "opened",
            "labels": [],
        }
        mock_client.update_issue.return_value = {"iid": 123}

        result = adapter.transition_issue("#123", "done")

        assert result is True
        call_args = mock_client.update_issue.call_args
        call_kwargs = call_args[1] if call_args else {}
        assert call_kwargs.get("state_event") == "close"

    def test_transition_issue_reopen(self, adapter, mock_client):
        """Should reopen issue when transitioning from closed."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "closed",
            "labels": [],
        }
        mock_client.update_issue.return_value = {"iid": 123}

        result = adapter.transition_issue("#123", "open")

        assert result is True
        call_args = mock_client.update_issue.call_args
        call_kwargs = call_args[1] if call_args else {}
        assert call_kwargs.get("state_event") == "reopen"

    def test_transition_issue_error(self, adapter, mock_client):
        """Should raise TransitionError on failure."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "state": "opened",
            "labels": [],
        }
        mock_client.update_issue.side_effect = IssueTrackerError("API error")

        with pytest.raises(TransitionError):
            adapter.transition_issue("#123", "done")

    def test_get_available_transitions(self, adapter):
        """Should return available status transitions."""
        transitions = adapter.get_available_transitions("#123")

        assert len(transitions) > 0
        assert all("id" in t and "name" in t and "label" in t for t in transitions)

    def test_format_description(self, adapter):
        """Should return markdown as-is (GitLab uses Markdown)."""
        markdown = "# Title\n\nBody text"
        result = adapter.format_description(markdown)
        assert result == markdown

    def test_parse_issue_with_weight(self, adapter, mock_client):
        """Should parse issue with weight (story points)."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "title": "Story",
            "state": "opened",
            "labels": [{"name": "story"}],
            "weight": 8,
        }

        result = adapter.get_issue("#123")

        assert result.story_points == 8.0

    def test_parse_issue_without_weight(self, adapter, mock_client):
        """Should handle issue without weight."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "title": "Story",
            "state": "opened",
            "labels": [{"name": "story"}],
        }

        result = adapter.get_issue("#123")

        assert result.story_points is None

    def test_parse_issue_with_task_list(self, adapter, mock_client):
        """Should parse task list items as subtasks."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "title": "Story",
            "state": "opened",
            "labels": [{"name": "story"}],
            "description": "- [ ] Task 1\n- [x] Task 2",
        }

        result = adapter.get_issue("#123")

        assert len(result.subtasks) == 2
        assert result.subtasks[0].summary == "Task 1"
        assert result.subtasks[0].status == "open"
        assert result.subtasks[1].summary == "Task 2"
        assert result.subtasks[1].status == "done"

    def test_ensure_labels_exist(self, mock_client):
        """Should create missing labels."""
        mock_client.list_labels.return_value = []
        GitLabAdapter(
            token="test",
            project_id="123",
            dry_run=False,
        )

        # Should have attempted to create labels
        assert mock_client.create_label.called

    def test_ensure_labels_exist_dry_run(self, mock_client):
        """Should not create labels in dry-run mode."""
        mock_client.list_labels.return_value = []
        GitLabAdapter(
            token="test",
            project_id="123",
            dry_run=True,
        )

        # Should not create labels in dry-run
        mock_client.create_label.assert_not_called()

    def test_parse_issue_epic_type(self, adapter, mock_client):
        """Should identify epic issue type."""
        mock_client.get_issue.return_value = {
            "iid": 10,
            "title": "Epic",
            "state": "opened",
            "labels": [{"name": "epic"}],
        }

        result = adapter.get_issue("#10")

        assert result.issue_type == "Epic"

    def test_parse_issue_subtask_type(self, adapter, mock_client):
        """Should identify subtask issue type."""
        mock_client.get_issue.return_value = {
            "iid": 20,
            "title": "Subtask",
            "state": "opened",
            "labels": [{"name": "subtask"}],
        }

        result = adapter.get_issue("#20")

        assert result.issue_type == "Sub-task"

    def test_parse_issue_story_type(self, adapter, mock_client):
        """Should identify story issue type."""
        mock_client.get_issue.return_value = {
            "iid": 30,
            "title": "Story",
            "state": "opened",
            "labels": [{"name": "story"}],
        }

        result = adapter.get_issue("#30")

        assert result.issue_type == "Story"

    def test_parse_issue_default_type(self, adapter, mock_client):
        """Should default to Issue type if no label."""
        mock_client.get_issue.return_value = {
            "iid": 40,
            "title": "Issue",
            "state": "opened",
            "labels": [],
        }

        result = adapter.get_issue("#40")

        assert result.issue_type == "Issue"

    def test_parse_issue_with_multiple_assignees(self, adapter, mock_client):
        """Should use first assignee when multiple exist."""
        mock_client.get_issue.return_value = {
            "iid": 123,
            "title": "Story",
            "state": "opened",
            "labels": [{"name": "story"}],
            "assignees": [
                {"username": "user1", "id": 1},
                {"username": "user2", "id": 2},
            ],
        }

        result = adapter.get_issue("#123")

        assert result.assignee == "user1"

    # -------------------------------------------------------------------------
    # Advanced Features - Merge Request Linking
    # -------------------------------------------------------------------------

    def test_get_merge_requests_for_issue(self, adapter, mock_client):
        """Should get merge requests linked to an issue."""
        mock_client.get_merge_requests_for_issue.return_value = [
            {"iid": 1, "title": "MR 1", "state": "opened"},
            {"iid": 2, "title": "MR 2", "state": "merged"},
        ]

        result = adapter.get_merge_requests_for_issue("#123")

        assert len(result) == 2
        assert result[0]["iid"] == 1
        mock_client.get_merge_requests_for_issue.assert_called_once_with(123)

    def test_link_merge_request(self, adapter, mock_client):
        """Should link a merge request to an issue."""
        mock_client.link_merge_request_to_issue.return_value = True

        result = adapter.link_merge_request(5, "#123", action="closes")

        assert result is True
        mock_client.link_merge_request_to_issue.assert_called_once_with(5, 123, "closes")

    def test_link_merge_request_dry_run(self, adapter, mock_client):
        """Should not link in dry-run mode."""
        adapter._dry_run = True
        result = adapter.link_merge_request(5, "#123")
        assert result is True
        mock_client.link_merge_request_to_issue.assert_not_called()

    # -------------------------------------------------------------------------
    # Advanced Features - Issue Boards
    # -------------------------------------------------------------------------

    def test_list_boards(self, adapter, mock_client):
        """Should list all boards."""
        mock_client.list_boards.return_value = [
            {"id": 1, "name": "Development"},
            {"id": 2, "name": "Backlog"},
        ]

        result = adapter.list_boards()

        assert len(result) == 2
        assert result[0]["name"] == "Development"

    def test_get_board(self, adapter, mock_client):
        """Should get a single board."""
        mock_client.get_board.return_value = {"id": 1, "name": "Development"}

        result = adapter.get_board(1)

        assert result["name"] == "Development"
        mock_client.get_board.assert_called_once_with(1)

    def test_get_board_lists(self, adapter, mock_client):
        """Should get board lists."""
        mock_client.get_board_lists.return_value = [
            {"id": 1, "label": {"name": "To Do"}},
            {"id": 2, "label": {"name": "In Progress"}},
        ]

        result = adapter.get_board_lists(1)

        assert len(result) == 2
        assert result[0]["label"]["name"] == "To Do"

    def test_move_issue_to_board_list(self, adapter, mock_client):
        """Should move issue to board list."""
        mock_client.move_issue_to_board_list.return_value = True

        result = adapter.move_issue_to_board_list("#123", board_id=1, list_id=2)

        assert result is True
        mock_client.move_issue_to_board_list.assert_called_once_with(123, 1, 2)

    def test_move_issue_to_board_list_dry_run(self, adapter, mock_client):
        """Should not move in dry-run mode."""
        adapter._dry_run = True
        result = adapter.move_issue_to_board_list("#123", board_id=1, list_id=2)
        assert result is True
        mock_client.move_issue_to_board_list.assert_not_called()

    def test_get_issue_board_position(self, adapter, mock_client):
        """Should get issue board position."""
        mock_client.get_issue_board_position.return_value = {
            "board_id": 1,
            "list_id": 2,
            "position": 0,
        }

        result = adapter.get_issue_board_position("#123")

        assert result["board_id"] == 1
        assert result["list_id"] == 2

    # -------------------------------------------------------------------------
    # Advanced Features - Time Tracking
    # -------------------------------------------------------------------------

    def test_get_issue_time_stats(self, adapter, mock_client):
        """Should get time tracking stats."""
        mock_client.get_issue_time_stats.return_value = {
            "time_estimate": 3600,
            "total_time_spent": 1800,
            "human_time_estimate": "1h",
            "human_total_time_spent": "30m",
        }

        result = adapter.get_issue_time_stats("#123")

        assert result["time_estimate"] == 3600
        assert result["total_time_spent"] == 1800

    def test_add_spent_time(self, adapter, mock_client):
        """Should add spent time to issue."""
        mock_client.add_spent_time.return_value = {
            "time_estimate": 3600,
            "total_time_spent": 1800,
        }

        result = adapter.add_spent_time("#123", "30m", summary="Worked on feature")

        assert result is True
        mock_client.add_spent_time.assert_called_once_with(123, "30m", "Worked on feature")

    def test_add_spent_time_dry_run(self, adapter, mock_client):
        """Should not add time in dry-run mode."""
        adapter._dry_run = True
        result = adapter.add_spent_time("#123", "30m")
        assert result is True
        mock_client.add_spent_time.assert_not_called()

    def test_reset_spent_time(self, adapter, mock_client):
        """Should reset spent time."""
        mock_client.reset_spent_time.return_value = {"total_time_spent": 0}

        result = adapter.reset_spent_time("#123")

        assert result is True
        mock_client.reset_spent_time.assert_called_once_with(123)

    def test_estimate_time(self, adapter, mock_client):
        """Should set time estimate."""
        mock_client.estimate_time.return_value = {"time_estimate": 7200}

        result = adapter.estimate_time("#123", "2h")

        assert result is True
        mock_client.estimate_time.assert_called_once_with(123, "2h")

    def test_reset_time_estimate(self, adapter, mock_client):
        """Should reset time estimate."""
        mock_client.reset_time_estimate.return_value = {"time_estimate": 0}

        result = adapter.reset_time_estimate("#123")

        assert result is True
        mock_client.reset_time_estimate.assert_called_once_with(123)
