"""
Integration tests with mocked Asana API responses.

These tests verify the full flow from adapter through API
using realistic API responses.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.asana import (
    AsanaAdapter,
    AsanaBatchClient,
    CachedAsanaAdapter,
)
from spectryn.core.exceptions import (
    AuthenticationError,
    RateLimitError,
    ResourceNotFoundError,
)
from spectryn.core.ports.config_provider import TrackerConfig


# =============================================================================
# Fixtures
# =============================================================================


class FakeResponse:
    """Simple fake response object for mocking requests.Session."""

    def __init__(self, status_code: int, data: dict[str, Any]):
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._data


@pytest.fixture
def tracker_config() -> TrackerConfig:
    """Create a test TrackerConfig for Asana."""
    return TrackerConfig(
        url="https://app.asana.com/api/1.0",
        email="user@example.com",
        api_token="asana_test_token_12345",
        project_key="project-123",
    )


@pytest.fixture
def mock_user_response():
    """Mock response for current user."""
    return {
        "data": {
            "gid": "user-456",
            "name": "Test User",
            "email": "test@example.com",
        }
    }


@pytest.fixture
def mock_task_response():
    """Mock response for task GET."""
    return {
        "data": {
            "gid": "task-789",
            "name": "Sample User Story",
            "notes": "**As a** developer\n**I want** a feature",
            "completed": False,
            "resource_subtype": "default_task",
            "assignee": {
                "gid": "user-456",
                "name": "Test User",
            },
            "custom_fields": [
                {"name": "Story Points", "number_value": 5},
                {"name": "Priority", "enum_value": {"name": "High"}},
            ],
        }
    }


@pytest.fixture
def mock_project_tasks_response():
    """Mock response for project tasks."""
    return {
        "data": [
            {
                "gid": "task-10",
                "name": "Story Alpha",
                "notes": "First story",
                "completed": False,
                "custom_fields": [],
            },
            {
                "gid": "task-11",
                "name": "Story Beta",
                "notes": "Second story",
                "completed": True,
                "custom_fields": [{"name": "Story Points", "number_value": 3}],
            },
        ],
        "next_page": None,
    }


@pytest.fixture
def mock_comments_response():
    """Mock response for task stories (comments)."""
    return {
        "data": [
            {
                "gid": "story-1",
                "type": "comment",
                "text": "This is a comment",
                "created_by": {"name": "Test User"},
                "created_at": "2024-01-15T10:00:00Z",
            },
            {
                "gid": "story-2",
                "type": "system",
                "text": "Status changed",
            },
        ]
    }


# =============================================================================
# AsanaAdapter Tests
# =============================================================================


class TestAsanaAdapterIntegration:
    """Integration tests for AsanaAdapter with mocked HTTP."""

    def test_get_issue_parses_response(self, tracker_config, mock_task_response):
        """Test get_issue correctly parses API response."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        adapter = AsanaAdapter(config=tracker_config, session=session)
        issue = adapter.get_issue("task-789")

        assert issue.key == "task-789"
        assert issue.summary == "Sample User Story"
        assert issue.status == "In Progress"
        assert issue.story_points == 5.0
        assert issue.assignee == "user-456"

    def test_get_epic_children(self, tracker_config, mock_project_tasks_response):
        """Test get_epic_children fetches project tasks."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_project_tasks_response)

        adapter = AsanaAdapter(config=tracker_config, session=session)
        children = adapter.get_epic_children("project-123")

        assert len(children) == 2
        assert children[0].key == "task-10"
        assert children[0].summary == "Story Alpha"
        assert children[1].key == "task-11"
        assert children[1].status == "Done"

    def test_get_issue_comments_filters_system_stories(
        self, tracker_config, mock_comments_response
    ):
        """Test get_issue_comments only returns comment-type stories."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_comments_response)

        adapter = AsanaAdapter(config=tracker_config, session=session)
        comments = adapter.get_issue_comments("task-789")

        # Should only include the comment, not the system story
        assert len(comments) == 1
        assert comments[0]["text"] == "This is a comment"

    def test_update_issue_description_dry_run(self, tracker_config):
        """Test update_issue_description in dry_run mode."""
        session = MagicMock()
        adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=True)

        result = adapter.update_issue_description("task-789", "New description")

        assert result is True
        session.request.assert_not_called()

    def test_create_subtask(self, tracker_config):
        """Test create_subtask creates task under parent."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, {"data": {"gid": "task-999"}})

        adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=False)

        result = adapter.create_subtask(
            parent_key="task-789",
            summary="New subtask",
            description="Subtask description",
            project_key="project-123",
            story_points=3,
            assignee="user-456",
        )

        assert result == "task-999"
        session.request.assert_called_once()
        method, url = session.request.call_args[0][:2]
        assert method == "POST"
        assert "task-789/subtasks" in url

    def test_transition_issue_to_complete(self, tracker_config):
        """Test transition_issue marks task as complete."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, {"data": {}})

        adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=False)

        result = adapter.transition_issue("task-789", "done")

        assert result is True
        payload = session.request.call_args.kwargs["json"]["data"]
        assert payload["completed"] is True

    def test_add_comment(self, tracker_config):
        """Test add_comment creates story on task."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, {"data": {}})

        adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=False)

        result = adapter.add_comment("task-789", "This is a comment")

        assert result is True
        method, url = session.request.call_args[0][:2]
        assert method == "POST"
        assert "task-789/stories" in url

    def test_search_issues(self, tracker_config, mock_project_tasks_response):
        """Test search_issues filters tasks by query."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_project_tasks_response)

        adapter = AsanaAdapter(config=tracker_config, session=session)
        results = adapter.search_issues("alpha", max_results=50)

        # Should match "Story Alpha"
        assert len(results) == 1
        assert results[0].summary == "Story Alpha"


class TestAsanaErrorHandling:
    """Tests for error handling."""

    def test_authentication_error(self, tracker_config):
        """Test 401 response raises AuthenticationError."""
        session = MagicMock()
        session.request.return_value = FakeResponse(401, {"errors": [{"message": "Invalid token"}]})

        adapter = AsanaAdapter(config=tracker_config, session=session)

        with pytest.raises(AuthenticationError):
            adapter.get_issue("task-789")

    def test_not_found_error(self, tracker_config):
        """Test 404 response raises ResourceNotFoundError."""
        session = MagicMock()
        session.request.return_value = FakeResponse(
            404, {"errors": [{"message": "Task not found"}]}
        )

        adapter = AsanaAdapter(config=tracker_config, session=session)

        with pytest.raises(ResourceNotFoundError):
            adapter.get_issue("nonexistent")

    def test_rate_limit_error(self, tracker_config):
        """Test 429 response raises RateLimitError."""
        session = MagicMock()
        session.request.return_value = FakeResponse(
            429, {"errors": [{"message": "Rate limit exceeded"}]}
        )

        adapter = AsanaAdapter(config=tracker_config, session=session)

        with pytest.raises(RateLimitError):
            adapter.get_issue("task-789")


class TestAsanaConnectionHandling:
    """Tests for connection handling."""

    def test_test_connection_success(self, tracker_config, mock_user_response):
        """Test connection test returns True on success."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_user_response)

        adapter = AsanaAdapter(config=tracker_config, session=session)

        assert adapter.test_connection() is True
        assert adapter.is_connected is True

    def test_test_connection_failure(self, tracker_config):
        """Test connection test returns False on failure."""
        session = MagicMock()
        session.request.return_value = FakeResponse(401, {"errors": [{"message": "Invalid token"}]})

        adapter = AsanaAdapter(config=tracker_config, session=session)

        assert adapter.test_connection() is False
        assert adapter.is_connected is False

    def test_adapter_name(self, tracker_config):
        """Test adapter returns correct name."""
        adapter = AsanaAdapter(config=tracker_config)
        assert adapter.name == "Asana"


# =============================================================================
# AsanaBatchClient Tests
# =============================================================================


class TestAsanaBatchClientIntegration:
    """Integration tests for AsanaBatchClient."""

    def test_bulk_create_subtasks(self, tracker_config):
        """Test bulk_create_subtasks creates multiple tasks."""
        session = MagicMock()
        # Return different GIDs for each call
        session.request.side_effect = [
            FakeResponse(200, {"data": {"gid": "task-101"}}),
            FakeResponse(200, {"data": {"gid": "task-102"}}),
        ]

        batch_client = AsanaBatchClient(
            session=session,
            base_url=tracker_config.url,
            api_token=tracker_config.api_token,
            dry_run=False,
        )

        subtasks = [
            {"parent_gid": "task-100", "name": "Subtask 1", "notes": "Description 1"},
            {"parent_gid": "task-100", "name": "Subtask 2", "notes": "Description 2"},
        ]

        result = batch_client.bulk_create_subtasks("project-123", subtasks)

        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert "task-101" in result.created_keys
        assert "task-102" in result.created_keys

    def test_bulk_update_tasks(self, tracker_config):
        """Test bulk_update_tasks updates multiple tasks."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, {"data": {}})

        batch_client = AsanaBatchClient(
            session=session,
            base_url=tracker_config.url,
            api_token=tracker_config.api_token,
            dry_run=False,
        )

        updates = [
            {"gid": "task-101", "notes": "Updated 1"},
            {"gid": "task-102", "notes": "Updated 2"},
        ]

        result = batch_client.bulk_update_tasks(updates)

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_complete_tasks(self, tracker_config):
        """Test bulk_complete_tasks marks multiple tasks complete."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, {"data": {}})

        batch_client = AsanaBatchClient(
            session=session,
            base_url=tracker_config.url,
            api_token=tracker_config.api_token,
            dry_run=False,
        )

        result = batch_client.bulk_complete_tasks(["task-101", "task-102"])

        assert result.total == 2
        assert result.succeeded == 2

    def test_bulk_operations_dry_run(self, tracker_config):
        """Test bulk operations in dry_run mode."""
        session = MagicMock()

        batch_client = AsanaBatchClient(
            session=session,
            base_url=tracker_config.url,
            api_token=tracker_config.api_token,
            dry_run=True,
        )

        subtasks = [
            {"parent_gid": "task-100", "name": "Subtask 1"},
        ]

        result = batch_client.bulk_create_subtasks("project-123", subtasks)

        assert result.total == 1
        assert result.succeeded == 1
        # Should not make any actual API calls
        session.request.assert_not_called()


# =============================================================================
# CachedAsanaAdapter Tests
# =============================================================================


class TestCachedAsanaAdapterIntegration:
    """Integration tests for CachedAsanaAdapter."""

    def test_caches_task_data(self, tracker_config, mock_task_response):
        """Test that task data is cached."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        adapter = CachedAsanaAdapter(config=tracker_config, session=session, cache_enabled=True)

        # First call hits API
        adapter.get_issue("task-789")

        # Second call should use cache
        adapter.get_issue("task-789")

        # Should only have made one API call
        assert session.request.call_count == 1

    def test_cache_invalidation_on_update(self, tracker_config, mock_task_response):
        """Test that cache is invalidated on updates."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        adapter = CachedAsanaAdapter(
            config=tracker_config, session=session, cache_enabled=True, dry_run=False
        )

        # Cache the task
        adapter.get_issue("task-789")

        # Update the task (should invalidate cache)
        adapter.update_issue_description("task-789", "New description")

        # Clear the mock to track only new calls
        session.request.reset_mock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        # Next get should hit API again
        adapter.get_issue("task-789")

        assert session.request.call_count == 1

    def test_cache_stats(self, tracker_config, mock_task_response):
        """Test cache statistics."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        adapter = CachedAsanaAdapter(config=tracker_config, session=session, cache_enabled=True)

        # Make some requests
        adapter.get_issue("task-789")
        adapter.get_issue("task-789")  # Should be cached

        stats = adapter.cache_stats
        assert "enabled" in stats
        assert stats["enabled"] is True

    def test_clear_cache(self, tracker_config, mock_task_response):
        """Test clearing the cache."""
        session = MagicMock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        adapter = CachedAsanaAdapter(config=tracker_config, session=session, cache_enabled=True)

        # Cache some data
        adapter.get_issue("task-789")

        # Clear cache
        adapter.clear_cache()

        # Reset mock
        session.request.reset_mock()
        session.request.return_value = FakeResponse(200, mock_task_response)

        # Should hit API again
        adapter.get_issue("task-789")

        assert session.request.call_count == 1


# =============================================================================
# Custom Fields Tests
# =============================================================================


class TestAsanaCustomFields:
    """Tests for custom field operations."""

    def test_get_custom_field_value(self, tracker_config):
        """Test getting a custom field value."""
        session = MagicMock()
        session.request.return_value = FakeResponse(
            200,
            {
                "data": {
                    "gid": "task-789",
                    "custom_fields": [
                        {"name": "Story Points", "number_value": 5},
                        {"name": "Priority", "enum_value": {"name": "High"}},
                    ],
                }
            },
        )

        adapter = AsanaAdapter(config=tracker_config, session=session)

        story_points = adapter.get_custom_field_value("task-789", "Story Points")
        assert story_points == 5

        priority = adapter.get_custom_field_value("task-789", "Priority")
        assert priority == "High"

    def test_set_custom_field_dry_run(self, tracker_config):
        """Test setting a custom field in dry run mode."""
        session = MagicMock()

        adapter = AsanaAdapter(config=tracker_config, session=session, dry_run=True)

        result = adapter.set_custom_field("task-789", "Story Points", 8)

        assert result is True
        session.request.assert_not_called()

    def test_batch_client_property(self, tracker_config):
        """Test batch client property creates client."""
        session = MagicMock()

        adapter = AsanaAdapter(config=tracker_config, session=session)

        batch = adapter.batch_client

        assert isinstance(batch, AsanaBatchClient)
        # Should return same instance
        assert adapter.batch_client is batch
