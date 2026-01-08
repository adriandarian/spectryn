"""
Integration tests for Basecamp adapter with live API.

These tests verify the full flow from adapter through client
using actual Basecamp 3 API calls.

To run these tests with a live Basecamp API:
1. Set environment variables:
   - BASECAMP_ACCESS_TOKEN: Your Basecamp OAuth access token
   - BASECAMP_ACCOUNT_ID: Your Basecamp account ID
   - BASECAMP_PROJECT_ID: Your Basecamp project ID (test project)

2. Run tests:
   pytest tests/integration/test_basecamp_integration.py -v

Note: These tests will be skipped if credentials are not provided.
"""

import contextlib
import os
from typing import Any

import pytest

from spectryn.adapters.basecamp.adapter import BasecampAdapter
from spectryn.adapters.basecamp.client import BasecampApiClient
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def basecamp_credentials():
    """Get Basecamp credentials from environment variables."""
    access_token = os.getenv("BASECAMP_ACCESS_TOKEN")
    account_id = os.getenv("BASECAMP_ACCOUNT_ID")
    project_id = os.getenv("BASECAMP_PROJECT_ID")

    if not all([access_token, account_id, project_id]):
        pytest.skip(
            "Basecamp credentials not provided. "
            "Set BASECAMP_ACCESS_TOKEN, BASECAMP_ACCOUNT_ID, and BASECAMP_PROJECT_ID "
            "environment variables to run integration tests."
        )

    return {
        "access_token": access_token,
        "account_id": account_id,
        "project_id": project_id,
    }


@pytest.fixture
def basecamp_client(basecamp_credentials):
    """Create a BasecampApiClient with live credentials."""
    return BasecampApiClient(
        access_token=basecamp_credentials["access_token"],
        account_id=basecamp_credentials["account_id"],
        project_id=basecamp_credentials["project_id"],
        dry_run=False,
    )


@pytest.fixture
def basecamp_adapter(basecamp_credentials):
    """Create a BasecampAdapter with live credentials."""
    return BasecampAdapter(
        access_token=basecamp_credentials["access_token"],
        account_id=basecamp_credentials["account_id"],
        project_id=basecamp_credentials["project_id"],
        dry_run=False,
    )


@pytest.fixture
def test_project_id(basecamp_credentials):
    """Get the test project ID."""
    return basecamp_credentials["project_id"]


# =============================================================================
# OAuth Flow Tests
# =============================================================================


class TestBasecampOAuthFlow:
    """Tests for OAuth authentication flow."""

    def test_oauth_token_validation(self, basecamp_client):
        """Test that OAuth token is valid and can authenticate."""
        # This should succeed if token is valid
        user = basecamp_client.get_current_user()

        assert user is not None
        assert "id" in user
        assert "name" in user or "email" in user

    def test_oauth_token_caching(self, basecamp_client):
        """Test that OAuth token is cached after first use."""
        # First call
        user1 = basecamp_client.get_current_user()

        # Second call should use cache (same object reference)
        user2 = basecamp_client.get_current_user()

        assert user1 == user2
        assert basecamp_client._current_user is not None

    def test_invalid_token_raises_error(self):
        """Test that invalid token raises AuthenticationError or NotFoundError."""
        client = BasecampApiClient(
            access_token="invalid_token_12345",
            account_id="123456",
            project_id="789012",
            dry_run=False,
        )

        with pytest.raises((AuthenticationError, NotFoundError)):
            client.get_current_user()

    def test_missing_token_raises_error(self):
        """Test that missing token raises AuthenticationError or NotFoundError."""
        client = BasecampApiClient(
            access_token="",
            account_id="123456",
            project_id="789012",
            dry_run=False,
        )

        with pytest.raises((AuthenticationError, NotFoundError)):
            client.get_current_user()

    def test_token_permissions_read(self, basecamp_client):
        """Test that token has read permissions."""
        # Should be able to read project
        project = basecamp_client.get_project()

        assert project is not None
        assert "id" in project
        assert str(project["id"]) == basecamp_client.project_id

    def test_token_permissions_write(self, basecamp_client, test_project_id):
        """Test that token has write permissions."""
        # Try to create a test todo (we'll clean it up)
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] OAuth Write Permission Test",
            notes="This is a test todo for OAuth permissions",
        )

        assert todo is not None
        assert "id" in todo

        # Clean up: delete the test todo
        # Basecamp doesn't have a direct delete endpoint for todos,
        # but we can mark it as completed or leave it
        # In a real scenario, you might want to manually clean up
        with contextlib.suppress(Exception):
            pass

    def test_connection_test_with_valid_token(self, basecamp_client):
        """Test connection test with valid OAuth token."""
        assert basecamp_client.test_connection() is True

    def test_connection_test_with_invalid_token(self):
        """Test connection test with invalid OAuth token."""
        client = BasecampApiClient(
            access_token="invalid_token",
            account_id="123456",
            project_id="789012",
            dry_run=False,
        )

        assert client.test_connection() is False


# =============================================================================
# BasecampApiClient Integration Tests
# =============================================================================


class TestBasecampApiClientIntegration:
    """Integration tests for BasecampApiClient with live API."""

    def test_get_current_user(self, basecamp_client):
        """Test getting current user from live API."""
        user = basecamp_client.get_current_user()

        assert user is not None
        assert "id" in user
        # User should have name or email
        assert "name" in user or "email" in user

    def test_get_project(self, basecamp_client, test_project_id):
        """Test getting project from live API."""
        project = basecamp_client.get_project()

        assert project is not None
        assert "id" in project
        assert str(project["id"]) == test_project_id
        assert "name" in project

    def test_get_todolists(self, basecamp_client):
        """Test getting todo lists from live API."""
        todolists = basecamp_client.get_todolists()

        assert isinstance(todolists, list)
        # Project might have no todo lists, which is fine
        if todolists:
            assert "id" in todolists[0]
            assert "name" in todolists[0]

    def test_get_todos(self, basecamp_client):
        """Test getting todos from live API."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])
        todos = basecamp_client.get_todos(todolist_id)

        assert isinstance(todos, list)
        # Might be empty, which is fine
        if todos:
            assert "id" in todos[0]
            assert "content" in todos[0]

    def test_get_messages(self, basecamp_client):
        """Test getting messages from live API."""
        messages = basecamp_client.get_messages()

        assert isinstance(messages, list)
        # Might be empty, which is fine
        if messages:
            assert "id" in messages[0]
            assert "subject" in messages[0] or "content" in messages[0]

    def test_get_campfires(self, basecamp_client):
        """Test getting Campfire chats from live API."""
        campfires = basecamp_client.get_campfires()

        assert isinstance(campfires, list)
        # Might be empty, which is fine
        if campfires:
            assert "id" in campfires[0]
            assert "name" in campfires[0]

    def test_create_and_get_todo(self, basecamp_client):
        """Test creating and retrieving a todo."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Integration Test Todo",
            notes="This is a test todo created by integration tests",
        )

        assert todo is not None
        assert "id" in todo
        todo_id = str(todo["id"])

        # Retrieve the todo
        retrieved_todo = basecamp_client.get_todo(todo_id)

        assert retrieved_todo is not None
        assert str(retrieved_todo["id"]) == todo_id
        assert retrieved_todo["content"] == "[TEST] Integration Test Todo"

    def test_update_todo(self, basecamp_client):
        """Test updating a todo."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo to Update",
            notes="Original notes",
        )

        todo_id = str(todo["id"])

        # Update the todo
        updated_todo = basecamp_client.update_todo(
            todo_id=todo_id,
            content="[TEST] Updated Todo",
            notes="Updated notes",
            completed=False,
        )

        assert updated_todo is not None
        assert updated_todo["content"] == "[TEST] Updated Todo"

    def test_complete_and_uncomplete_todo(self, basecamp_client):
        """Test completing and uncompleting a todo."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Completion Test",
        )

        todo_id = str(todo["id"])

        # Complete the todo
        completed_todo = basecamp_client.complete_todo(todo_id)
        assert completed_todo.get("completed") is True

        # Uncomplete the todo
        uncompleted_todo = basecamp_client.uncomplete_todo(todo_id)
        assert uncompleted_todo.get("completed") is False

    def test_create_comment(self, basecamp_client):
        """Test creating a comment on a todo."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Comment Test",
        )

        todo_id = str(todo["id"])

        # Create a comment
        comment = basecamp_client.create_comment(
            recording_id=todo_id,
            recording_type="Todo",
            content="[TEST] This is a test comment",
        )

        assert comment is not None
        assert "id" in comment
        assert "content" in comment

    def test_get_comments(self, basecamp_client):
        """Test getting comments for a recording."""
        todolists = basecamp_client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo with a comment
        todo = basecamp_client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Comments Test",
        )

        todo_id = str(todo["id"])

        # Add a comment
        basecamp_client.create_comment(
            recording_id=todo_id,
            recording_type="Todo",
            content="[TEST] Test comment",
        )

        # Get comments
        comments = basecamp_client.get_comments(todo_id, "Todo")

        assert isinstance(comments, list)
        assert len(comments) > 0
        assert any(c.get("content", "").startswith("[TEST]") for c in comments)

    def test_send_campfire_message(self, basecamp_client):
        """Test sending a Campfire message."""
        campfires = basecamp_client.get_campfires()
        if not campfires:
            pytest.skip("No Campfires available in test project")

        chat_id = str(campfires[0]["id"])

        # Send a test message
        line = basecamp_client.send_campfire_message(
            chat_id=chat_id,
            content="[TEST] Integration test message",
        )

        assert line is not None
        assert "id" in line
        assert "content" in line

    def test_webhook_operations(self, basecamp_client):
        """Test webhook create, list, and delete operations."""
        # Create a test webhook (using a test URL)
        webhook = basecamp_client.create_webhook(
            url="https://example.com/test-webhook",
            events=["todo.created"],
            description="[TEST] Integration test webhook",
        )

        assert webhook is not None
        assert "id" in webhook
        webhook_id = str(webhook["id"])

        # List webhooks
        webhooks = basecamp_client.list_webhooks()
        assert isinstance(webhooks, list)
        assert any(str(w.get("id")) == webhook_id for w in webhooks)

        # Delete the webhook
        deleted = basecamp_client.delete_webhook(webhook_id)
        assert deleted is True

        # Verify it's deleted
        webhooks_after = basecamp_client.list_webhooks()
        assert not any(str(w.get("id")) == webhook_id for w in webhooks_after)

    def test_rate_limiting(self, basecamp_client):
        """Test that rate limiting is respected."""
        # Make multiple rapid requests
        for _ in range(5):
            basecamp_client.get_current_user()

        # Should not raise rate limit error
        # (if it does, the rate limiter is working)
        user = basecamp_client.get_current_user()
        assert user is not None

    def test_error_handling_not_found(self, basecamp_client):
        """Test error handling for not found resources."""
        with pytest.raises(NotFoundError):
            basecamp_client.get_todo("999999999")


# =============================================================================
# BasecampAdapter Integration Tests
# =============================================================================


class TestBasecampAdapterIntegration:
    """Integration tests for BasecampAdapter with live API."""

    def test_adapter_connection(self, basecamp_adapter):
        """Test adapter connection to live API."""
        assert basecamp_adapter.test_connection() is True
        assert basecamp_adapter.is_connected is True

    def test_get_current_user(self, basecamp_adapter):
        """Test getting current user through adapter."""
        user = basecamp_adapter.get_current_user()

        assert user is not None
        assert "id" in user

    def test_get_project_through_adapter(self, basecamp_adapter, test_project_id):
        """Test getting project through adapter."""
        # Adapter doesn't have direct get_project, but we can test via client
        project = basecamp_adapter._client.get_project()

        assert project is not None
        assert str(project["id"]) == test_project_id

    def test_create_and_get_issue(self, basecamp_adapter):
        """Test creating and retrieving an issue through adapter."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a todo via client
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Adapter Integration Test",
            notes="Test notes",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # Get issue through adapter
        issue = basecamp_adapter.get_issue(issue_key)

        assert issue is not None
        assert issue.key == issue_key
        assert issue.summary == "[TEST] Adapter Integration Test"
        assert issue.description == "Test notes"

    def test_update_issue_description(self, basecamp_adapter):
        """Test updating issue description through adapter."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Update Test",
            notes="Original description",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # Update description
        result = basecamp_adapter.update_issue_description(issue_key, "Updated description")

        assert result is True

        # Verify update
        issue = basecamp_adapter.get_issue(issue_key)
        assert issue.description == "Updated description"

    def test_add_comment(self, basecamp_adapter):
        """Test adding a comment through adapter."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Comment Test",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # Add comment
        result = basecamp_adapter.add_comment(issue_key, "[TEST] Adapter comment")

        assert result is True

        # Verify comment
        comments = basecamp_adapter.get_issue_comments(issue_key)
        assert len(comments) > 0
        assert any("[TEST] Adapter comment" in c.get("content", "") for c in comments)

    def test_transition_issue(self, basecamp_adapter):
        """Test transitioning issue status through adapter."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create a test todo
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Todo for Transition Test",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # Transition to completed
        result = basecamp_adapter.transition_issue(issue_key, "Done")

        assert result is True

        # Verify status
        issue = basecamp_adapter.get_issue(issue_key)
        assert issue.status == "Done"

        # Transition back to planned
        result = basecamp_adapter.transition_issue(issue_key, "Planned")
        assert result is True

        issue = basecamp_adapter.get_issue(issue_key)
        assert issue.status == "Planned"

    def test_search_issues(self, basecamp_adapter):
        """Test searching issues through adapter."""
        # Search for test todos
        results = basecamp_adapter.search_issues("[TEST]", max_results=10)

        assert isinstance(results, list)
        # Should find at least some test todos if they exist

    def test_campfire_integration(self, basecamp_adapter):
        """Test Campfire integration through adapter."""
        campfires = basecamp_adapter.get_campfires()

        assert isinstance(campfires, list)

        if campfires:
            chat_id = str(campfires[0]["id"])

            # Send a message
            result = basecamp_adapter.send_campfire_message(
                chat_id=chat_id, content="[TEST] Adapter Campfire message"
            )

            assert result is not None
            assert "id" in result

    def test_webhook_management(self, basecamp_adapter):
        """Test webhook management through adapter."""
        # Create webhook
        webhook = basecamp_adapter.create_webhook(
            url="https://example.com/test-webhook",
            events=["todo.created"],
            description="[TEST] Adapter webhook",
        )

        assert webhook is not None
        webhook_id = str(webhook["id"])

        # List webhooks
        webhooks = basecamp_adapter.list_webhooks()
        assert isinstance(webhooks, list)

        # Delete webhook
        result = basecamp_adapter.delete_webhook(webhook_id)
        assert result is True


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================


class TestBasecampEndToEndWorkflow:
    """End-to-end workflow tests for Basecamp integration."""

    def test_full_sync_workflow(self, basecamp_adapter):
        """Test a full sync workflow: create, update, comment, transition."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # 1. Create a todo
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] E2E Workflow Test",
            notes="Initial description",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # 2. Get the issue
        issue = basecamp_adapter.get_issue(issue_key)
        assert issue.status == "Planned"

        # 3. Update description
        basecamp_adapter.update_issue_description(issue_key, "Updated description")

        # 4. Add a comment
        basecamp_adapter.add_comment(issue_key, "[TEST] Workflow comment")

        # 5. Transition to done
        basecamp_adapter.transition_issue(issue_key, "Done")

        # 6. Verify final state
        final_issue = basecamp_adapter.get_issue(issue_key)
        assert final_issue.status == "Done"
        assert final_issue.description == "Updated description"
        assert len(final_issue.comments) > 0

        # 7. Transition back
        basecamp_adapter.transition_issue(issue_key, "Planned")

        final_issue = basecamp_adapter.get_issue(issue_key)
        assert final_issue.status == "Planned"

    def test_story_points_workflow(self, basecamp_adapter):
        """Test story points extraction and update workflow."""
        todolists = basecamp_adapter._client.get_todolists()
        if not todolists:
            pytest.skip("No todo lists available in test project")

        todolist_id = str(todolists[0]["id"])

        # Create todo with story points in notes
        todo = basecamp_adapter._client.create_todo(
            todolist_id=todolist_id,
            content="[TEST] Story Points Test",
            notes="Some notes\n\nStory Points: 8",
        )

        todo_id = str(todo["id"])
        issue_key = f"TODO-{todo_id}"

        # Get issue and verify story points extracted
        issue = basecamp_adapter.get_issue(issue_key)
        assert issue.story_points == 8.0

        # Update story points
        basecamp_adapter.update_issue_story_points(issue_key, 13.0)

        # Verify update
        updated_issue = basecamp_adapter.get_issue(issue_key)
        assert updated_issue.story_points == 13.0
