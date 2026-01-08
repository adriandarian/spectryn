"""
Tests for Trello Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.trello.adapter import TrelloAdapter
from spectryn.adapters.trello.client import TrelloApiClient, TrelloRateLimiter
from spectryn.core.ports.config_provider import TrelloConfig
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestTrelloRateLimiter:
    """Tests for TrelloRateLimiter."""

    def test_acquire_with_available_tokens(self):
        """Should immediately acquire when tokens available."""
        limiter = TrelloRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.acquire(timeout=0.1) is True

    def test_stats_tracking(self):
        """Should track request statistics."""
        limiter = TrelloRateLimiter(requests_per_second=10.0, burst_size=5)

        limiter.acquire()
        limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert "available_tokens" in stats
        assert "requests_per_second" in stats

    def test_reset(self):
        """Should reset limiter state."""
        limiter = TrelloRateLimiter(burst_size=5)

        limiter.acquire()
        limiter.acquire()
        limiter.reset()

        stats = limiter.stats
        assert stats["total_requests"] == 0
        assert stats["total_wait_time"] == 0.0


# =============================================================================
# API Client Tests
# =============================================================================


class TestTrelloApiClient:
    """Tests for TrelloApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.trello.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return TrelloApiClient(
            api_key="test_api_key",
            api_token="test_api_token",
            board_id="test_board_id",
            dry_run=False,
        )

    def test_init(self, client):
        """Should initialize client with correct parameters."""
        assert client.api_key == "test_api_key"
        assert client.api_token == "test_api_token"
        assert client.board_id == "test_board_id"
        assert client.dry_run is False

    def test_auth_params(self, client):
        """Should include auth params in requests."""
        assert "key" in client.auth_params
        assert "token" in client.auth_params
        assert client.auth_params["key"] == "test_api_key"
        assert client.auth_params["token"] == "test_api_token"

    def test_get_current_user(self, client, mock_session):
        """Should get current user."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "user123", "fullName": "Test User"}
        mock_session.request.return_value = mock_response

        user = client.get_current_user()

        assert user["id"] == "user123"
        assert user["fullName"] == "Test User"
        mock_session.request.assert_called_once()

    def test_get_board(self, client, mock_session):
        """Should get board."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "board123", "name": "Test Board"}
        mock_session.request.return_value = mock_response

        board = client.get_board()

        assert board["id"] == "board123"
        assert board["name"] == "Test Board"

    def test_get_board_lists(self, client, mock_session):
        """Should get board lists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "list1", "name": "To Do"},
            {"id": "list2", "name": "In Progress"},
        ]
        mock_session.request.return_value = mock_response

        lists = client.get_board_lists()

        assert len(lists) == 2
        assert lists[0]["name"] == "To Do"
        assert lists[1]["name"] == "In Progress"

    def test_create_card(self, client, mock_session):
        """Should create a card."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "card123", "name": "Test Card"}
        mock_session.request.return_value = mock_response

        card = client.create_card(name="Test Card", list_id="list1")

        assert card["id"] == "card123"
        assert card["name"] == "Test Card"
        # Verify POST was called
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "POST"
        assert "cards" in call_args[0][1]

    def test_get_card(self, client, mock_session):
        """Should get a card by ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "card123", "name": "Test Card"}
        mock_session.request.return_value = mock_response

        card = client.get_card("card123")

        assert card["id"] == "card123"
        assert card["name"] == "Test Card"

    def test_authentication_error(self, client, mock_session):
        """Should raise AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.get_current_user()

    def test_not_found_error(self, client, mock_session):
        """Should raise NotFoundError on 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.get_card("nonexistent")

    def test_create_webhook(self, client, mock_session):
        """Should create a webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "webhook123",
            "idModel": "board123",
            "callbackURL": "https://example.com/webhook",
        }
        mock_session.request.return_value = mock_response

        webhook = client.create_webhook(
            model_id="board123",
            callback_url="https://example.com/webhook",
        )

        assert webhook["id"] == "webhook123"
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "POST"
        assert "webhooks" in call_args[0][1]

    def test_list_webhooks(self, client, mock_session):
        """Should list webhooks."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "webhook1", "callbackURL": "https://example.com/webhook1"},
        ]
        mock_session.request.return_value = mock_response

        webhooks = client.list_webhooks()

        assert len(webhooks) == 1
        assert webhooks[0]["id"] == "webhook1"

    def test_delete_webhook(self, client, mock_session):
        """Should delete a webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_session.request.return_value = mock_response

        result = client.delete_webhook("webhook123")

        assert result is True
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "webhooks/webhook123" in call_args[0][1]

    def test_get_board_plugins(self, client, mock_session):
        """Should get installed Power-Ups."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "plugin1", "name": "Custom Fields"},
        ]
        mock_session.request.return_value = mock_response

        plugins = client.get_board_plugins()

        assert len(plugins) == 1
        assert plugins[0]["name"] == "Custom Fields"

    def test_get_card_custom_fields(self, client, mock_session):
        """Should get custom fields for a card."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"idCustomField": "field1", "value": {"number": "5"}},
        ]
        mock_session.request.return_value = mock_response

        custom_fields = client.get_card_custom_fields("card123")

        assert len(custom_fields) == 1
        assert custom_fields[0]["idCustomField"] == "field1"

    def test_set_custom_field(self, client, mock_session):
        """Should set a custom field value."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "idCustomField": "field1",
            "value": {"number": "8"},
        }
        mock_session.request.return_value = mock_response

        result = client.set_custom_field("card123", "field1", 8)

        assert result["idCustomField"] == "field1"
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "PUT"
        assert "cards/card123/customField/field1" in call_args[0][1]


# =============================================================================
# Adapter Tests
# =============================================================================


class TestTrelloAdapter:
    """Tests for TrelloAdapter."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return TrelloConfig(
            api_key="test_api_key",
            api_token="test_api_token",
            board_id="test_board_id",
        )

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        with patch("spectryn.adapters.trello.adapter.TrelloApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create adapter with mocked client."""
        return TrelloAdapter(config=config, dry_run=False)

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Trello"

    def test_is_connected(self, adapter, mock_client):
        """Should check connection status."""
        mock_client.is_connected = True
        assert adapter.is_connected is True

        mock_client.is_connected = False
        assert adapter.is_connected is False

    def test_test_connection(self, adapter, mock_client):
        """Should test connection."""
        mock_client.test_connection.return_value = True
        mock_client.get_board.return_value = {"id": "board123"}

        assert adapter.test_connection() is True

    def test_get_current_user(self, adapter, mock_client):
        """Should get current user."""
        mock_client.get_current_user.return_value = {"id": "user123", "fullName": "Test User"}

        user = adapter.get_current_user()

        assert user["id"] == "user123"
        assert user["fullName"] == "Test User"

    def test_get_issue(self, adapter, mock_client):
        """Should get an issue (card)."""
        mock_card = {
            "id": "card123",
            "name": "Test Card",
            "desc": "Description",
            "idList": "list1",
            "labels": [],
            "checklists": [],
        }
        mock_client.get_card.return_value = mock_card
        mock_client.get_board_lists.return_value = [
            {"id": "list1", "name": "To Do"},
        ]

        issue = adapter.get_issue("card123")

        assert issue.key == "card123"
        assert issue.summary == "Test Card"
        assert issue.description == "Description"

    def test_get_epic_children(self, adapter, mock_client):
        """Should get epic children (cards in a list)."""
        mock_list = {"id": "list1", "name": "Epic List"}
        mock_client.get_list_by_name.return_value = mock_list
        mock_client.get_list_cards.return_value = [
            {"id": "card1", "name": "Card 1", "idList": "list1", "labels": [], "checklists": []},
            {"id": "card2", "name": "Card 2", "idList": "list1", "labels": [], "checklists": []},
        ]
        mock_client.get_board_lists.return_value = [mock_list]

        children = adapter.get_epic_children("Epic List")

        assert len(children) == 2
        assert children[0].key == "card1"
        assert children[1].key == "card2"

    def test_transition_issue(self, adapter, mock_client):
        """Should transition issue to new list."""
        mock_client.get_board_lists.return_value = [
            {"id": "list1", "name": "To Do"},
            {"id": "list2", "name": "In Progress"},
        ]
        mock_client.move_card_to_list.return_value = {"id": "card123"}

        result = adapter.transition_issue("card123", "In Progress")

        assert result is True
        mock_client.move_card_to_list.assert_called_once_with("card123", "list2")

    def test_transition_issue_not_found(self, adapter, mock_client):
        """Should raise TransitionError if list not found."""
        mock_client.get_board_lists.return_value = [
            {"id": "list1", "name": "To Do"},
        ]

        with pytest.raises(TransitionError):
            adapter.transition_issue("card123", "Nonexistent Status")

    def test_create_subtask_checklist(self, adapter, mock_client):
        """Should create subtask as checklist item."""
        adapter.config.subtask_mode = "checklist"
        mock_client.get_card.return_value = {"id": "card123"}
        mock_client.get_card_checklists.return_value = []
        mock_client.create_checklist.return_value = {"id": "checklist1"}
        mock_client.add_checklist_item.return_value = {"id": "item1"}

        result = adapter.create_subtask(
            parent_key="card123",
            summary="Subtask",
            description="Description",
            project_key="board",
        )

        assert result == "item1"
        mock_client.create_checklist.assert_called_once()
        mock_client.add_checklist_item.assert_called_once()

    def test_create_subtask_linked_card(self, adapter, mock_client):
        """Should create subtask as linked card."""
        adapter.config.subtask_mode = "linked_card"
        mock_client.get_card.return_value = {"id": "card123", "idList": "list1", "desc": ""}
        mock_client.create_card.return_value = {
            "id": "card456",
            "shortUrl": "https://trello.com/c/456",
        }

        result = adapter.create_subtask(
            parent_key="card123",
            summary="Subtask",
            description="Description",
            project_key="board",
        )

        assert result == "card456"
        mock_client.create_card.assert_called_once()

    def test_update_issue_description(self, adapter, mock_client):
        """Should update card description."""
        mock_client.update_card.return_value = {"id": "card123"}

        result = adapter.update_issue_description("card123", "New description")

        assert result is True
        mock_client.update_card.assert_called_once_with("card123", desc="New description")

    def test_update_issue_story_points(self, adapter, mock_client):
        """Should update story points in description."""
        mock_client.get_card.return_value = {"id": "card123", "desc": "Original description"}
        mock_client.update_card.return_value = {"id": "card123"}

        result = adapter.update_issue_story_points("card123", 5.0)

        assert result is True
        # Verify description was updated with story points
        call_args = mock_client.update_card.call_args
        assert "desc" in call_args[1]
        assert "**Story Points:** 5" in call_args[1]["desc"]

    def test_add_comment(self, adapter, mock_client):
        """Should add comment to card."""
        mock_client.add_comment.return_value = {"id": "comment1"}

        result = adapter.add_comment("card123", "Comment text")

        assert result is True
        mock_client.add_comment.assert_called_once_with("card123", "Comment text")

    def test_get_available_transitions(self, adapter, mock_client):
        """Should get available lists as transitions."""
        mock_client.get_board_lists.return_value = [
            {"id": "list1", "name": "To Do"},
            {"id": "list2", "name": "In Progress"},
            {"id": "list3", "name": "Done"},
        ]

        transitions = adapter.get_available_transitions("card123")

        assert len(transitions) == 3
        assert transitions[0]["name"] == "To Do"
        assert transitions[1]["name"] == "In Progress"
        assert transitions[2]["name"] == "Done"

    def test_format_description(self, adapter):
        """Should return markdown as-is."""
        markdown = "# Title\n\nDescription"
        result = adapter.format_description(markdown)

        assert result == markdown

    # -------------------------------------------------------------------------
    # Webhook Tests
    # -------------------------------------------------------------------------

    def test_create_webhook(self, adapter, mock_client):
        """Should create a webhook."""
        mock_client.create_webhook.return_value = {
            "id": "webhook123",
            "idModel": "board123",
            "callbackURL": "https://example.com/webhook",
            "active": True,
        }

        webhook = adapter.create_webhook(
            callback_url="https://example.com/webhook",
            description="Test webhook",
        )

        assert webhook["id"] == "webhook123"
        mock_client.create_webhook.assert_called_once()

    def test_list_webhooks(self, adapter, mock_client):
        """Should list webhooks."""
        mock_client.list_webhooks.return_value = [
            {"id": "webhook1", "callbackURL": "https://example.com/webhook1"},
            {"id": "webhook2", "callbackURL": "https://example.com/webhook2"},
        ]

        webhooks = adapter.list_webhooks()

        assert len(webhooks) == 2
        assert webhooks[0]["id"] == "webhook1"
        mock_client.list_webhooks.assert_called_once()

    def test_get_webhook(self, adapter, mock_client):
        """Should get a webhook by ID."""
        mock_client.get_webhook.return_value = {
            "id": "webhook123",
            "callbackURL": "https://example.com/webhook",
        }

        webhook = adapter.get_webhook("webhook123")

        assert webhook["id"] == "webhook123"
        mock_client.get_webhook.assert_called_once_with("webhook123")

    def test_update_webhook(self, adapter, mock_client):
        """Should update a webhook."""
        mock_client.update_webhook.return_value = {
            "id": "webhook123",
            "callbackURL": "https://example.com/new-webhook",
        }

        webhook = adapter.update_webhook(
            webhook_id="webhook123",
            callback_url="https://example.com/new-webhook",
        )

        assert webhook["id"] == "webhook123"
        mock_client.update_webhook.assert_called_once()

    def test_delete_webhook(self, adapter, mock_client):
        """Should delete a webhook."""
        mock_client.delete_webhook.return_value = True

        result = adapter.delete_webhook("webhook123")

        assert result is True
        mock_client.delete_webhook.assert_called_once_with("webhook123")

    # -------------------------------------------------------------------------
    # Power-Ups & Custom Fields Tests
    # -------------------------------------------------------------------------

    def test_get_installed_power_ups(self, adapter, mock_client):
        """Should get installed Power-Ups."""
        mock_client.get_board_plugins.return_value = [
            {"id": "plugin1", "name": "Custom Fields"},
            {"id": "plugin2", "name": "Calendar"},
        ]

        power_ups = adapter.get_installed_power_ups()

        assert len(power_ups) == 2
        assert power_ups[0]["name"] == "Custom Fields"
        mock_client.get_board_plugins.assert_called_once()

    def test_get_custom_fields(self, adapter, mock_client):
        """Should get custom fields for a card."""
        mock_client.get_card_custom_fields.return_value = [
            {"idCustomField": "field1", "value": {"number": "5"}},
            {"idCustomField": "field2", "value": {"text": "High"}},
        ]

        custom_fields = adapter.get_custom_fields("card123")

        assert len(custom_fields) == 2
        assert custom_fields[0]["idCustomField"] == "field1"
        mock_client.get_card_custom_fields.assert_called_once_with("card123")

    def test_get_board_custom_field_definitions(self, adapter, mock_client):
        """Should get custom field definitions."""
        mock_client.get_board_custom_fields.return_value = [
            {"id": "field1", "name": "Story Points", "type": "number"},
            {"id": "field2", "name": "Priority", "type": "text"},
        ]

        definitions = adapter.get_board_custom_field_definitions()

        assert len(definitions) == 2
        assert definitions[0]["name"] == "Story Points"
        mock_client.get_board_custom_fields.assert_called_once()

    def test_set_custom_field(self, adapter, mock_client):
        """Should set a custom field value."""
        mock_client.set_custom_field.return_value = {
            "idCustomField": "field1",
            "value": {"number": "8"},
        }

        result = adapter.set_custom_field("card123", "field1", 8)

        assert result is True
        mock_client.set_custom_field.assert_called_once_with("card123", "field1", 8)

    def test_get_custom_field_value(self, adapter, mock_client):
        """Should get a custom field value by name."""
        mock_client.get_card_custom_fields.return_value = [
            {"idCustomField": "field1", "value": {"number": "5"}},
        ]
        mock_client.get_custom_field_definition.return_value = {
            "id": "field1",
            "name": "Story Points",
            "type": "number",
        }

        value = adapter.get_custom_field_value("card123", "Story Points")

        assert value == 5.0
        mock_client.get_card_custom_fields.assert_called_once()
        mock_client.get_custom_field_definition.assert_called_once_with("field1")


# =============================================================================
# Attachment Tests
# =============================================================================


class TestTrelloAdapterAttachments:
    """Tests for attachment functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        config = TrelloConfig(
            api_key="test_key",
            api_token="test_token",
            board_id="board123",
        )
        with patch("spectryn.adapters.trello.adapter.TrelloApiClient"):
            return TrelloAdapter(config=config, dry_run=False)

    @pytest.fixture
    def mock_client(self, adapter):
        """Get the mocked client."""
        return adapter._client

    def test_get_card_attachments(self, adapter, mock_client):
        """Should get all attachments for a card."""
        mock_client.get_card_attachments.return_value = [
            {"id": "att1", "name": "file1.pdf", "url": "https://trello.com/att1"},
            {"id": "att2", "name": "file2.png", "url": "https://trello.com/att2"},
        ]

        attachments = adapter.get_card_attachments("card123")

        assert len(attachments) == 2
        assert attachments[0]["name"] == "file1.pdf"
        assert attachments[1]["name"] == "file2.png"
        mock_client.get_card_attachments.assert_called_once_with("card123")

    def test_upload_card_attachment(self, adapter, mock_client, tmp_path):
        """Should upload a file attachment to a card."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        mock_client.upload_card_attachment.return_value = {
            "id": "att123",
            "name": "test.txt",
            "url": "https://trello.com/att123",
        }

        result = adapter.upload_card_attachment("card123", str(test_file))

        assert result["id"] == "att123"
        assert result["name"] == "test.txt"
        mock_client.upload_card_attachment.assert_called_once_with("card123", str(test_file), None)

    def test_upload_card_attachment_with_name(self, adapter, mock_client, tmp_path):
        """Should upload attachment with custom name."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        mock_client.upload_card_attachment.return_value = {
            "id": "att123",
            "name": "Custom Name",
        }

        result = adapter.upload_card_attachment("card123", str(test_file), name="Custom Name")

        assert result["name"] == "Custom Name"
        mock_client.upload_card_attachment.assert_called_once_with(
            "card123", str(test_file), "Custom Name"
        )

    def test_delete_card_attachment(self, adapter, mock_client):
        """Should delete an attachment."""
        adapter.delete_card_attachment("att123")

        mock_client.delete_card_attachment.assert_called_once_with("att123")

    def test_upload_attachment_dry_run(self, adapter, tmp_path):
        """Should not upload in dry-run mode."""
        adapter._dry_run = True
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        result = adapter.upload_card_attachment("card123", str(test_file))

        assert result["id"] == "attachment:dry-run"
        adapter._client.upload_card_attachment.assert_not_called()

    def test_delete_attachment_dry_run(self, adapter):
        """Should not delete in dry-run mode."""
        adapter._dry_run = True

        result = adapter.delete_card_attachment("att123")

        assert result is True
        adapter._client.delete_card_attachment.assert_not_called()


class TestTrelloApiClientAttachments:
    """Tests for TrelloApiClient attachment methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.trello.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return TrelloApiClient(
            api_key="test_key",
            api_token="test_token",
            board_id="board123",
            dry_run=False,
        )

    def test_get_card_attachments(self, client, mock_session):
        """Should get card attachments."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "att1", "name": "file1.pdf", "url": "https://trello.com/att1"},
        ]
        mock_response.headers = {}
        mock_session.request.return_value = mock_response

        attachments = client.get_card_attachments("card123")

        assert len(attachments) == 1
        assert attachments[0]["name"] == "file1.pdf"

    def test_upload_card_attachment(self, client, mock_session, tmp_path):
        """Should upload file attachment."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "att123",
            "name": "test.txt",
            "url": "https://trello.com/att123",
        }
        mock_response.headers = {}
        mock_session.post.return_value = mock_response

        result = client.upload_card_attachment("card123", str(test_file))

        assert result["id"] == "att123"
        assert result["name"] == "test.txt"
        mock_session.post.assert_called_once()

    def test_upload_attachment_file_not_found(self, client, tmp_path):
        """Should raise NotFoundError if file doesn't exist."""
        non_existent_file = tmp_path / "nonexistent.txt"

        with pytest.raises(NotFoundError):
            client.upload_card_attachment("card123", str(non_existent_file))

    def test_delete_card_attachment(self, client, mock_session):
        """Should delete attachment."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_session.delete.return_value = mock_response

        result = client.delete_card_attachment("att123")

        assert result is True
        mock_session.delete.assert_called_once()

    def test_delete_attachment_not_found(self, client, mock_session):
        """Should raise NotFoundError for non-existent attachment."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.delete.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.delete_card_attachment("att123")


# =============================================================================
# Due Date Tests
# =============================================================================


class TestTrelloAdapterDueDates:
    """Tests for TrelloAdapter due date operations."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return TrelloConfig(
            api_key="test_api_key",
            api_token="test_api_token",
            board_id="test_board_id",
        )

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        with patch("spectryn.adapters.trello.adapter.TrelloApiClient") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def adapter(self, config, mock_client):
        """Create adapter with mocked client."""
        return TrelloAdapter(config=config, dry_run=False)

    def test_get_issue_due_date(self, adapter, mock_client):
        """Should get due date for an issue."""
        mock_client.get_card.return_value = {
            "id": "card123",
            "name": "Test Card",
            "due": "2024-01-15T12:00:00.000Z",
        }

        result = adapter.get_issue_due_date("card123")

        assert result == "2024-01-15T12:00:00.000Z"
        mock_client.get_card.assert_called_once_with("card123")

    def test_get_issue_due_date_not_set(self, adapter, mock_client):
        """Should return None when due date not set."""
        mock_client.get_card.return_value = {
            "id": "card123",
            "name": "Test Card",
        }

        result = adapter.get_issue_due_date("card123")

        assert result is None

    def test_update_issue_due_date(self, adapter, mock_client):
        """Should set due date for an issue."""
        mock_client.update_card.return_value = {
            "id": "card123",
            "due": "2024-01-15T12:00:00.000Z",
        }

        result = adapter.update_issue_due_date("card123", "2024-01-15T12:00:00.000Z")

        assert result is True
        mock_client.update_card.assert_called_once_with("card123", due="2024-01-15T12:00:00.000Z")

    def test_update_issue_due_date_clear(self, adapter, mock_client):
        """Should clear due date for an issue."""
        mock_client.update_card.return_value = {
            "id": "card123",
            "due": None,
        }

        result = adapter.update_issue_due_date("card123", None)

        assert result is True
        mock_client.update_card.assert_called_once_with("card123", due=None)

    def test_update_issue_due_date_dry_run(self, config):
        """Should not update in dry run mode."""
        with patch("spectryn.adapters.trello.adapter.TrelloApiClient") as mock:
            mock_client = MagicMock()
            mock.return_value = mock_client
            adapter = TrelloAdapter(config=config, dry_run=True)

        result = adapter.update_issue_due_date("card123", "2024-01-15T12:00:00.000Z")

        assert result is True
        mock_client.update_card.assert_not_called()

    def test_parse_card_with_due_date(self, adapter, mock_client):
        """Should parse due date from card data."""
        mock_client.get_card.return_value = {
            "id": "card123",
            "name": "Test Card with Due Date",
            "desc": "Description",
            "idList": "list123",
            "due": "2024-01-15T12:00:00.000Z",
            "checklists": [],
        }
        mock_client.get_board_lists.return_value = [
            {"id": "list123", "name": "To Do"},
        ]

        result = adapter.get_issue("card123")

        assert result.due_date == "2024-01-15T12:00:00.000Z"

    def test_parse_card_without_due_date(self, adapter, mock_client):
        """Should handle card without due date."""
        mock_client.get_card.return_value = {
            "id": "card123",
            "name": "Test Card without Due Date",
            "desc": "Description",
            "idList": "list123",
            "checklists": [],
        }
        mock_client.get_board_lists.return_value = [
            {"id": "list123", "name": "To Do"},
        ]

        result = adapter.get_issue("card123")

        assert result.due_date is None
