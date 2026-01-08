"""
Tests for Basecamp Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.basecamp.adapter import BasecampAdapter
from spectryn.adapters.basecamp.client import BasecampApiClient, BasecampRateLimiter
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestBasecampRateLimiter:
    """Tests for BasecampRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = BasecampRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = BasecampRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "current_tokens" in stats
        assert "requests_per_second" in stats

    def test_update_from_response(self):
        """Should update state from Basecamp response headers."""
        limiter = BasecampRateLimiter()

        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "60"}
        mock_response.status_code = 200

        limiter.update_from_response(mock_response)

        # Should handle retry-after header
        assert limiter._retry_after is not None

    def test_rate_limit_429(self):
        """Should reduce rate on 429 response."""
        limiter = BasecampRateLimiter(requests_per_second=10.0)

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        old_rate = limiter.requests_per_second
        limiter.update_from_response(mock_response)

        assert limiter.requests_per_second < old_rate


# =============================================================================
# API Client Tests
# =============================================================================


class TestBasecampApiClient:
    """Tests for BasecampApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.basecamp.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return BasecampApiClient(
            access_token="test_token",
            account_id="123456",
            project_id="789012",
            dry_run=False,
        )

    def test_init(self, client):
        """Should initialize client with correct parameters."""
        assert client.access_token == "test_token"
        assert client.account_id == "123456"
        assert client.project_id == "789012"
        assert client.dry_run is False
        assert client.api_url == "https://3.basecampapi.com"

    def test_headers(self, client):
        """Should include correct headers."""
        assert "Authorization" in client.headers
        assert client.headers["Authorization"] == "Bearer test_token"
        assert "User-Agent" in client.headers
        assert "Content-Type" in client.headers

    def test_build_url(self, client):
        """Should build correct URLs."""
        url = client._build_url("people/me.json")
        assert url == "https://3.basecampapi.com/123456/people/me.json"

        url = client._build_url("projects/789012/todos.json")
        assert url == "https://3.basecampapi.com/123456/projects/789012/todos.json"

    def test_get_current_user(self, client, mock_session):
        """Should get current user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "name": "Test User",
            "email": "test@example.com",
        }
        mock_response.text = '{"id": 123, "name": "Test User", "email": "test@example.com"}'
        mock_session.request.return_value = mock_response

        user = client.get_current_user()

        assert user["id"] == 123
        assert user["name"] == "Test User"
        mock_session.request.assert_called_once()

    def test_get_current_user_cached(self, client, mock_session):
        """Should cache current user."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "name": "Test User"}
        mock_response.text = '{"id": 123, "name": "Test User"}'
        mock_session.request.return_value = mock_response

        user1 = client.get_current_user()
        user2 = client.get_current_user()

        assert user1 == user2
        # Should only call once due to caching
        assert mock_session.request.call_count == 1

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get("people/me.json")

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get("projects/789012/todos/999.json")

    def test_get_project(self, client, mock_session):
        """Should get project."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 789012, "name": "Test Project"}
        mock_response.text = '{"id": 789012, "name": "Test Project"}'
        mock_session.request.return_value = mock_response

        project = client.get_project()

        assert project["id"] == 789012
        assert project["name"] == "Test Project"

    def test_get_todolists(self, client, mock_session):
        """Should get todo lists."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "To Do"},
            {"id": 2, "name": "In Progress"},
        ]
        mock_response.text = '[{"id": 1, "name": "To Do"}, {"id": 2, "name": "In Progress"}]'
        mock_session.request.return_value = mock_response

        todolists = client.get_todolists()

        assert len(todolists) == 2
        assert todolists[0]["name"] == "To Do"
        assert todolists[1]["name"] == "In Progress"

    def test_get_todos(self, client, mock_session):
        """Should get todos from a todo list."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "content": "Todo 1", "completed": False},
            {"id": 2, "content": "Todo 2", "completed": True},
        ]
        mock_response.text = '[{"id": 1, "content": "Todo 1", "completed": false}, {"id": 2, "content": "Todo 2", "completed": true}]'
        mock_session.request.return_value = mock_response

        todos = client.get_todos("todolist123")

        assert len(todos) == 2
        assert todos[0]["content"] == "Todo 1"
        assert todos[1]["content"] == "Todo 2"

    def test_get_todo(self, client, mock_session):
        """Should get a specific todo."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "content": "Test Todo",
            "notes": "Test notes",
            "completed": False,
        }
        mock_response.text = (
            '{"id": 123, "content": "Test Todo", "notes": "Test notes", "completed": false}'
        )
        mock_session.request.return_value = mock_response

        todo = client.get_todo("123")

        assert todo["id"] == 123
        assert todo["content"] == "Test Todo"

    def test_create_todo(self, client, mock_session):
        """Should create a todo."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 456, "content": "New Todo"}
        mock_response.text = '{"id": 456, "content": "New Todo"}'
        mock_session.request.return_value = mock_response

        todo = client.create_todo(
            todolist_id="todolist123",
            content="New Todo",
            notes="Some notes",
        )

        assert todo["id"] == 456
        assert todo["content"] == "New Todo"
        mock_session.request.assert_called_once()

    def test_create_todo_dry_run(self, mock_session):
        """Should not create todo in dry-run mode."""
        client = BasecampApiClient(
            access_token="test_token",
            account_id="123456",
            project_id="789012",
            dry_run=True,
        )

        result = client.create_todo(todolist_id="todolist123", content="New Todo")

        assert result == {}
        mock_session.request.assert_not_called()

    def test_update_todo(self, client, mock_session):
        """Should update a todo."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "content": "Updated Todo"}
        mock_response.text = '{"id": 123, "content": "Updated Todo"}'
        mock_session.request.return_value = mock_response

        todo = client.update_todo("123", content="Updated Todo", completed=True)

        assert todo["id"] == 123
        mock_session.request.assert_called_once()

    def test_complete_todo(self, client, mock_session):
        """Should mark todo as completed."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "completed": True}
        mock_response.text = '{"id": 123, "completed": true}'
        mock_session.request.return_value = mock_response

        todo = client.complete_todo("123")

        assert todo["completed"] is True

    def test_get_messages(self, client, mock_session):
        """Should get messages."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "subject": "Message 1"},
            {"id": 2, "subject": "Message 2"},
        ]
        mock_response.text = (
            '[{"id": 1, "subject": "Message 1"}, {"id": 2, "subject": "Message 2"}]'
        )
        mock_session.request.return_value = mock_response

        messages = client.get_messages()

        assert len(messages) == 2
        assert messages[0]["subject"] == "Message 1"

    def test_get_comments(self, client, mock_session):
        """Should get comments for a recording."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "content": "Comment 1"},
            {"id": 2, "content": "Comment 2"},
        ]
        mock_response.text = (
            '[{"id": 1, "content": "Comment 1"}, {"id": 2, "content": "Comment 2"}]'
        )
        mock_session.request.return_value = mock_response

        comments = client.get_comments("recording123", "Todo")

        assert len(comments) == 2
        assert comments[0]["content"] == "Comment 1"

    def test_create_comment(self, client, mock_session):
        """Should create a comment."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 789, "content": "New comment"}
        mock_response.text = '{"id": 789, "content": "New comment"}'
        mock_session.request.return_value = mock_response

        comment = client.create_comment("recording123", "Todo", "New comment")

        assert comment["id"] == 789
        assert comment["content"] == "New comment"

    def test_get_campfires(self, client, mock_session):
        """Should get Campfire chats."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "Campfire 1"},
            {"id": 2, "name": "Campfire 2"},
        ]
        mock_response.text = '[{"id": 1, "name": "Campfire 1"}, {"id": 2, "name": "Campfire 2"}]'
        mock_session.request.return_value = mock_response

        campfires = client.get_campfires()

        assert len(campfires) == 2
        assert campfires[0]["name"] == "Campfire 1"

    def test_get_campfire_lines(self, client, mock_session):
        """Should get Campfire messages."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "content": "Message 1"},
            {"id": 2, "content": "Message 2"},
        ]
        mock_response.text = (
            '[{"id": 1, "content": "Message 1"}, {"id": 2, "content": "Message 2"}]'
        )
        mock_session.request.return_value = mock_response

        lines = client.get_campfire_lines("chat123", since="2024-01-01T00:00:00Z", limit=10)

        assert len(lines) == 2
        assert lines[0]["content"] == "Message 1"

    def test_send_campfire_message(self, client, mock_session):
        """Should send Campfire message."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 999, "content": "Hello"}
        mock_response.text = '{"id": 999, "content": "Hello"}'
        mock_session.request.return_value = mock_response

        line = client.send_campfire_message("chat123", "Hello")

        assert line["id"] == 999
        assert line["content"] == "Hello"

    def test_create_webhook(self, client, mock_session):
        """Should create a webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "webhook123",
            "url": "https://example.com/webhook",
            "events": ["todo.created"],
        }
        mock_response.text = (
            '{"id": "webhook123", "url": "https://example.com/webhook", "events": ["todo.created"]}'
        )
        mock_session.request.return_value = mock_response

        webhook = client.create_webhook(
            url="https://example.com/webhook",
            events=["todo.created"],
            description="Test webhook",
        )

        assert webhook["id"] == "webhook123"
        assert webhook["url"] == "https://example.com/webhook"

    def test_list_webhooks(self, client, mock_session):
        """Should list webhooks."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "webhook1", "url": "https://example.com/webhook1"},
            {"id": "webhook2", "url": "https://example.com/webhook2"},
        ]
        mock_response.text = '[{"id": "webhook1", "url": "https://example.com/webhook1"}, {"id": "webhook2", "url": "https://example.com/webhook2"}]'
        mock_session.request.return_value = mock_response

        webhooks = client.list_webhooks()

        assert len(webhooks) == 2
        assert webhooks[0]["id"] == "webhook1"

    def test_test_connection(self, client, mock_session):
        """Should test connection."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "name": "Test User"}
        mock_response.text = '{"id": 123, "name": "Test User"}'
        mock_session.request.return_value = mock_response

        assert client.test_connection() is True

    def test_test_connection_failure(self, client, mock_session):
        """Should return False on connection failure."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        assert client.test_connection() is False


# =============================================================================
# Adapter Tests
# =============================================================================


class TestBasecampAdapter:
    """Tests for BasecampAdapter."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client."""
        with patch("spectryn.adapters.basecamp.adapter.BasecampApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, mock_client):
        """Create a test adapter with mocked client."""
        return BasecampAdapter(
            access_token="test_token",
            account_id="123456",
            project_id="789012",
            dry_run=True,
        )

    def test_name_property(self, adapter):
        """Should return 'Basecamp' as tracker name."""
        assert adapter.name == "Basecamp"

    def test_is_connected(self, adapter, mock_client):
        """Should check connection status."""
        mock_client.is_connected = True
        assert adapter.is_connected is True

        mock_client.is_connected = False
        assert adapter.is_connected is False

    def test_test_connection(self, adapter, mock_client):
        """Should test connection."""
        mock_client.test_connection.return_value = True

        assert adapter.test_connection() is True
        mock_client.test_connection.assert_called_once()

    def test_get_current_user(self, adapter, mock_client):
        """Should get current user."""
        mock_client.get_current_user.return_value = {
            "id": 123,
            "name": "Test User",
            "email": "test@example.com",
        }

        user = adapter.get_current_user()

        assert user["id"] == 123
        assert user["name"] == "Test User"
        mock_client.get_current_user.assert_called_once()

    def test_get_issue_todo(self, adapter, mock_client):
        """Should get a todo as issue."""
        mock_client.get_todo.return_value = {
            "id": 123,
            "content": "Test Todo",
            "notes": "Test notes",
            "completed": False,
            "assignees": [],
            "due_on": None,
        }
        mock_client.get_comments.return_value = []

        issue = adapter.get_issue("TODO-123")

        assert issue.key == "TODO-123"
        assert issue.summary == "Test Todo"
        assert issue.description == "Test notes"
        assert issue.status == "Planned"
        assert issue.issue_type == "Story"

    def test_get_issue_message(self, adapter, mock_client):
        """Should get a message as issue."""
        mock_client.get_message.return_value = {
            "id": 456,
            "subject": "Test Message",
            "content": "Message content",
        }
        mock_client.get_comments.return_value = []

        issue = adapter.get_issue("MSG-456")

        assert issue.key == "MSG-456"
        assert issue.summary == "Test Message"
        assert issue.description == "Message content"
        assert issue.status == "Planned"

    def test_get_issue_with_completed_todo(self, adapter, mock_client):
        """Should parse completed todo correctly."""
        mock_client.get_todo.return_value = {
            "id": 123,
            "content": "Completed Todo",
            "notes": "",
            "completed": True,
            "assignees": [],
            "due_on": None,
        }
        mock_client.get_comments.return_value = []

        issue = adapter.get_issue("TODO-123")

        assert issue.status == "Done"

    def test_get_issue_with_story_points(self, adapter, mock_client):
        """Should extract story points from notes."""
        mock_client.get_todo.return_value = {
            "id": 123,
            "content": "Todo with points",
            "notes": "Some notes\n\nStory Points: 5",
            "completed": False,
            "assignees": [],
            "due_on": None,
        }
        mock_client.get_comments.return_value = []

        issue = adapter.get_issue("TODO-123")

        assert issue.story_points == 5.0

    def test_get_epic_children_todos(self, adapter, mock_client):
        """Should get epic children as todos."""
        mock_client.get_todolists.return_value = [
            {"id": 1, "name": "Todo List 1"},
            {"id": 2, "name": "Todo List 2"},
        ]
        mock_client.get_todos.side_effect = [
            [
                {
                    "id": 1,
                    "content": "Todo 1",
                    "notes": "",
                    "completed": False,
                    "assignees": [],
                    "due_on": None,
                }
            ],
            [
                {
                    "id": 2,
                    "content": "Todo 2",
                    "notes": "",
                    "completed": False,
                    "assignees": [],
                    "due_on": None,
                }
            ],
        ]
        mock_client.get_comments.return_value = []

        children = adapter.get_epic_children("epic123")

        assert len(children) == 2
        assert children[0].key == "TODO-1"
        assert children[1].key == "TODO-2"

    def test_get_epic_children_messages(self, adapter, mock_client):
        """Should get epic children as messages when configured."""
        adapter.use_messages_for_stories = True
        mock_client.get_messages.return_value = [
            {"id": 1, "subject": "Message 1", "content": "Content 1"},
            {"id": 2, "subject": "Message 2", "content": "Content 2"},
        ]
        mock_client.get_comments.return_value = []

        children = adapter.get_epic_children("epic123")

        assert len(children) == 2
        assert children[0].key == "MSG-1"
        assert children[1].key == "MSG-2"

    def test_get_issue_comments(self, adapter, mock_client):
        """Should get issue comments."""
        mock_client.get_comments.return_value = [
            {
                "id": 1,
                "content": "Comment 1",
                "creator": {"name": "User 1"},
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "content": "Comment 2",
                "creator": {"name": "User 2"},
                "created_at": "2024-01-02T00:00:00Z",
            },
        ]

        comments = adapter.get_issue_comments("TODO-123")

        assert len(comments) == 2
        # The adapter returns raw comments from the client
        assert comments[0]["content"] == "Comment 1"
        assert comments[0]["creator"]["name"] == "User 1"
        assert comments[0]["id"] == 1

    def test_update_issue_description_todo(self, adapter, mock_client):
        """Should update todo description."""
        adapter._dry_run = False
        mock_client.update_todo.return_value = {"id": 123}

        result = adapter.update_issue_description("TODO-123", "New description")

        assert result is True
        mock_client.update_todo.assert_called_once_with("123", notes="New description")

    def test_update_issue_description_dry_run(self, adapter, mock_client):
        """Should not update in dry-run mode."""
        result = adapter.update_issue_description("TODO-123", "New description")

        assert result is True
        mock_client.update_todo.assert_not_called()

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update story points in notes."""
        adapter._dry_run = False
        mock_client.get_todo.return_value = {
            "id": 123,
            "content": "Todo",
            "notes": "Existing notes",
            "completed": False,
            "assignees": [],
            "due_on": None,
        }
        mock_client.update_todo.return_value = {"id": 123}
        mock_client.get_comments.return_value = []

        result = adapter.update_issue_story_points("TODO-123", 8.0)

        assert result is True
        mock_client.update_todo.assert_called_once()
        # Check that notes were updated with story points
        call_args = mock_client.update_todo.call_args
        assert "notes" in call_args.kwargs
        assert "Story Points" in call_args.kwargs["notes"]

    def test_create_subtask(self, adapter, mock_client):
        """Should create a subtask."""
        adapter._dry_run = False
        mock_client.get_todo.return_value = {
            "id": 123,
            "content": "Parent Todo",
            "parent": {"id": "todolist123"},
        }
        mock_client.create_todo.return_value = {"id": 456}

        result = adapter.create_subtask(
            parent_key="TODO-123",
            summary="Subtask",
            description="Subtask description",
            project_key="PROJ",
        )

        assert result == "TODO-456"
        mock_client.create_todo.assert_called_once()

    def test_create_subtask_dry_run(self, adapter, mock_client):
        """Should not create subtask in dry-run mode."""
        result = adapter.create_subtask(
            parent_key="TODO-123",
            summary="Subtask",
            description="Description",
            project_key="PROJ",
        )

        assert result is None
        mock_client.create_todo.assert_not_called()

    def test_create_subtask_not_todo(self, adapter):
        """Should raise error for non-todo parent."""
        adapter._dry_run = False

        with pytest.raises(IssueTrackerError):
            adapter.create_subtask(
                parent_key="MSG-123",
                summary="Subtask",
                description="Description",
                project_key="PROJ",
            )

    def test_add_comment(self, adapter, mock_client):
        """Should add a comment."""
        adapter._dry_run = False
        mock_client.create_comment.return_value = {"id": 789}

        result = adapter.add_comment("TODO-123", "New comment")

        assert result is True
        mock_client.create_comment.assert_called_once_with("123", "Todo", "New comment")

    def test_transition_issue_completed(self, adapter, mock_client):
        """Should transition issue to completed."""
        adapter._dry_run = False
        mock_client.complete_todo.return_value = {"id": 123, "completed": True}

        result = adapter.transition_issue("TODO-123", "Done")

        assert result is True
        mock_client.complete_todo.assert_called_once_with("123")

    def test_transition_issue_not_completed(self, adapter, mock_client):
        """Should transition issue to not completed."""
        adapter._dry_run = False
        mock_client.uncomplete_todo.return_value = {"id": 123, "completed": False}

        result = adapter.transition_issue("TODO-123", "Planned")

        assert result is True
        mock_client.uncomplete_todo.assert_called_once_with("123")

    def test_transition_issue_message_error(self, adapter):
        """Should raise error for message transitions."""
        adapter._dry_run = False

        with pytest.raises(TransitionError):
            adapter.transition_issue("MSG-123", "Done")

    def test_get_available_transitions(self, adapter):
        """Should return available transitions."""
        transitions = adapter.get_available_transitions("TODO-123")

        assert len(transitions) == 2
        assert transitions[0]["name"] == "Completed"
        assert transitions[1]["name"] == "Not Completed"

    def test_format_description(self, adapter):
        """Should return markdown as-is."""
        markdown = "## Test\n\nSome **bold** text"
        result = adapter.format_description(markdown)

        assert result == markdown

    def test_search_issues(self, adapter, mock_client):
        """Should search issues."""
        mock_client.get_todolists.return_value = [{"id": 1, "name": "List 1"}]
        mock_client.get_todos.return_value = [
            {
                "id": 1,
                "content": "Test Todo",
                "notes": "Some notes",
                "completed": False,
                "assignees": [],
                "due_on": None,
            }
        ]
        mock_client.get_comments.return_value = []

        results = adapter.search_issues("Test", max_results=10)

        assert len(results) == 1
        assert results[0].key == "TODO-1"

    def test_get_campfires(self, adapter, mock_client):
        """Should get Campfire chats."""
        mock_client.get_campfires.return_value = [
            {"id": 1, "name": "Campfire 1"},
            {"id": 2, "name": "Campfire 2"},
        ]

        campfires = adapter.get_campfires()

        assert len(campfires) == 2
        assert campfires[0]["name"] == "Campfire 1"

    def test_send_campfire_message(self, adapter, mock_client):
        """Should send Campfire message."""
        adapter._dry_run = False
        mock_client.send_campfire_message.return_value = {"id": 999, "content": "Hello"}

        result = adapter.send_campfire_message("chat123", "Hello")

        assert result["id"] == 999
        assert result["content"] == "Hello"
        mock_client.send_campfire_message.assert_called_once_with(
            chat_id="chat123", content="Hello"
        )

    def test_send_campfire_message_dry_run(self, adapter, mock_client):
        """Should not send message in dry-run mode."""
        result = adapter.send_campfire_message("chat123", "Hello")

        assert result["id"] == "line:dry-run"
        mock_client.send_campfire_message.assert_not_called()

    def test_create_campfire(self, adapter, mock_client):
        """Should create Campfire."""
        adapter._dry_run = False
        mock_client.create_campfire.return_value = {"id": 123, "name": "New Campfire"}

        result = adapter.create_campfire("New Campfire")

        assert result["id"] == 123
        assert result["name"] == "New Campfire"
        mock_client.create_campfire.assert_called_once_with(name="New Campfire")

    def test_create_webhook(self, adapter, mock_client):
        """Should create webhook."""
        adapter._dry_run = False
        mock_client.create_webhook.return_value = {
            "id": "webhook123",
            "url": "https://example.com/webhook",
        }

        result = adapter.create_webhook("https://example.com/webhook", events=["todo.created"])

        assert result["id"] == "webhook123"
        mock_client.create_webhook.assert_called_once()

    def test_list_webhooks(self, adapter, mock_client):
        """Should list webhooks."""
        mock_client.list_webhooks.return_value = [
            {"id": "webhook1", "url": "https://example.com/webhook1"},
        ]

        webhooks = adapter.list_webhooks()

        assert len(webhooks) == 1
        assert webhooks[0]["id"] == "webhook1"

    def test_delete_webhook(self, adapter, mock_client):
        """Should delete webhook."""
        adapter._dry_run = False
        mock_client.delete_webhook.return_value = True

        result = adapter.delete_webhook("webhook123")

        assert result is True
        mock_client.delete_webhook.assert_called_once_with("webhook123")
