"""
Tests for Monday.com Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.monday.adapter import MondayAdapter
from spectryn.adapters.monday.client import MondayApiClient, MondayRateLimiter
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
    TransitionError,
)


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestMondayRateLimiter:
    """Tests for MondayRateLimiter."""

    def test_acquire_with_available_capacity(self):
        """Should immediately acquire when capacity available."""
        limiter = MondayRateLimiter(requests_per_10s=500.0)

        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        # Should not raise
        assert len(limiter.request_times) == 3


# =============================================================================
# API Client Tests
# =============================================================================


class TestMondayApiClient:
    """Tests for MondayApiClient."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        with patch("spectryn.adapters.monday.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        """Create a test client with mocked session."""
        return MondayApiClient(
            api_token="monday_token_test123",
            dry_run=False,
        )

    def test_init(self, client):
        """Should initialize client with correct settings."""
        assert client.api_token == "monday_token_test123"
        assert client.api_url == "https://api.monday.com/v2"
        assert client.dry_run is False

    def test_is_connected(self, client):
        """Should return True when token is set."""
        assert client.is_connected is True

    def test_get_viewer(self, client, mock_session):
        """Should fetch viewer information."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "me": {
                    "id": "user-123",
                    "name": "Test User",
                    "email": "test@example.com",
                }
            }
        }
        mock_session.post.return_value = mock_response

        viewer = client.get_viewer()

        assert viewer["id"] == "user-123"
        assert viewer["name"] == "Test User"
        assert viewer["email"] == "test@example.com"

    def test_get_board(self, client, mock_session):
        """Should fetch board information."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "boards": [
                    {
                        "id": "board-123",
                        "name": "Test Board",
                        "description": "Test Description",
                        "workspace": {"id": "workspace-123", "name": "Test Workspace"},
                        "groups": [{"id": "group-1", "title": "Group 1"}],
                        "columns": [
                            {"id": "status_col", "title": "Status", "type": "status"},
                            {"id": "priority_col", "title": "Priority", "type": "priority"},
                        ],
                    }
                ]
            }
        }
        mock_session.post.return_value = mock_response

        board = client.get_board("board-123")

        assert board["id"] == "board-123"
        assert board["name"] == "Test Board"
        assert len(board["groups"]) == 1
        assert len(board["columns"]) == 2

    def test_get_board_not_found(self, client, mock_session):
        """Should raise NotFoundError when board not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"boards": []}}
        mock_session.post.return_value = mock_response

        with pytest.raises(NotFoundError, match="Board not found"):
            client.get_board("board-123")

    def test_get_item(self, client, mock_session):
        """Should fetch item information."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "items": [
                    {
                        "id": "item-123",
                        "name": "Test Item",
                        "group": {"id": "group-1", "title": "Group 1"},
                        "board": {"id": "board-123", "name": "Test Board"},
                        "column_values": [],
                        "subitems": [],
                        "updates": [],
                    }
                ]
            }
        }
        mock_session.post.return_value = mock_response

        item = client.get_item("item-123")

        assert item["id"] == "item-123"
        assert item["name"] == "Test Item"

    def test_create_item(self, client, mock_session):
        """Should create a new item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "create_item": {
                    "id": "item-456",
                    "name": "New Item",
                }
            }
        }
        mock_session.post.return_value = mock_response

        result = client.create_item(
            board_id="board-123",
            group_id="group-1",
            item_name="New Item",
        )

        assert result["id"] == "item-456"
        assert result["name"] == "New Item"

    def test_add_update(self, client, mock_session):
        """Should add an update (comment) to an item."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "create_update": {
                    "id": "update-123",
                    "body": "Test comment",
                }
            }
        }
        mock_session.post.return_value = mock_response

        result = client.add_update("item-123", "Test comment")

        assert result["id"] == "update-123"
        assert result["body"] == "Test comment"


# =============================================================================
# Adapter Tests
# =============================================================================


class TestMondayAdapter:
    """Tests for MondayAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        with patch("spectryn.adapters.monday.adapter.MondayApiClient"):
            return MondayAdapter(
                api_token="test_token",
                board_id="board-123",
                dry_run=False,  # Set to False to test actual API calls
            )

    def test_name(self, adapter):
        """Should return correct name."""
        assert adapter.name == "Monday.com"

    def test_is_connected(self, adapter):
        """Should check connection status."""
        adapter._client.is_connected = True
        assert adapter.is_connected is True

    def test_get_current_user(self, adapter):
        """Should get current user."""
        adapter._client.get_viewer.return_value = {
            "id": "user-123",
            "name": "Test User",
        }

        user = adapter.get_current_user()

        assert user["id"] == "user-123"
        assert user["name"] == "Test User"

    def test_get_issue(self, adapter):
        """Should fetch an issue."""
        adapter._client.get_item.return_value = {
            "id": "item-123",
            "name": "Test Item",
            "column_values": [],
            "subitems": [],
            "updates": [],
        }

        issue = adapter.get_issue("item-123")

        assert issue.key == "item-123"
        assert issue.summary == "Test Item"

    def test_get_epic_children(self, adapter):
        """Should fetch children of an epic (group)."""
        adapter._client.get_board_items.return_value = [
            {
                "id": "item-1",
                "name": "Item 1",
                "column_values": [],
                "subitems": [],
                "updates": [],
            },
            {
                "id": "item-2",
                "name": "Item 2",
                "column_values": [],
                "subitems": [],
                "updates": [],
            },
        ]
        adapter._get_group_id = MagicMock(return_value="group-1")

        children = adapter.get_epic_children("group-1")

        assert len(children) == 2
        assert children[0].key == "item-1"
        assert children[1].key == "item-2"

    def test_add_comment(self, adapter):
        """Should add a comment."""
        adapter._client.add_update.return_value = {"id": "update-123"}
        adapter._dry_run = False  # Ensure not in dry run mode

        result = adapter.add_comment("item-123", "Test comment")

        assert result is True
        adapter._client.add_update.assert_called_once_with("item-123", "Test comment")

    def test_update_issue_story_points(self, adapter):
        """Should update story points."""
        adapter._get_story_points_column_id = MagicMock(return_value="numbers_col")
        adapter._dry_run = False  # Ensure not in dry run mode

        result = adapter.update_issue_story_points("item-123", 5.0)

        assert result is True
        adapter._client.update_item.assert_called_once()

    def test_create_subtask(self, adapter):
        """Should create a subtask."""
        adapter._client.create_subitem.return_value = {"id": "subitem-123"}
        adapter._get_story_points_column_id = MagicMock(return_value=None)
        adapter._dry_run = False  # Ensure not in dry run mode

        result = adapter.create_subtask(
            parent_key="item-123",
            summary="Subtask",
            description="Description",
            project_key="board-123",
        )

        assert result == "subitem-123"
        adapter._client.create_subitem.assert_called_once()

    def test_transition_issue(self, adapter):
        """Should transition an issue to a new status."""
        adapter._get_status_column_id = MagicMock(return_value="status_col")
        adapter._client.get_item.return_value = {
            "id": "item-123",
            "column_values": [
                {
                    "id": "status_col",
                    "type": "status",
                    "text": "Working on it",
                    "settings_str": '{"labels":{"0":{"label":"Not Started"},"1":{"label":"Working on it"},"2":{"label":"Done"}}}',
                }
            ],
        }
        adapter._dry_run = False  # Ensure not in dry run mode

        result = adapter.transition_issue("item-123", "Done")

        assert result is True
        adapter._client.update_item.assert_called_once()

    def test_transition_issue_status_not_found(self, adapter):
        """Should raise TransitionError when status column not found."""
        adapter._get_status_column_id = MagicMock(return_value=None)
        adapter._dry_run = False  # Ensure not in dry run mode

        with pytest.raises(TransitionError, match="Status column not found"):
            adapter.transition_issue("item-123", "Done")

    def test_get_available_transitions(self, adapter):
        """Should get available status transitions."""
        adapter._get_status_column_id = MagicMock(return_value="status_col")
        adapter._get_board = MagicMock(
            return_value={
                "columns": [
                    {
                        "id": "status_col",
                        "type": "status",
                        "settings_str": '{"labels":{"0":{"label":"Not Started"},"1":{"label":"Working on it"},"2":{"label":"Done"}}}',
                    }
                ]
            }
        )

        transitions = adapter.get_available_transitions("item-123")

        assert len(transitions) == 3
        assert transitions[0]["name"] == "Not Started"
        assert transitions[1]["name"] == "Working on it"
        assert transitions[2]["name"] == "Done"


# =============================================================================
# File Attachment Tests
# =============================================================================


class TestMondayAdapterFileAttachments:
    """Tests for file attachment functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        with patch("spectryn.adapters.monday.adapter.MondayApiClient"):
            return MondayAdapter(
                api_token="test_token",
                board_id="board-123",
                dry_run=False,
            )

    def test_upload_file(self, adapter, tmp_path):
        """Should upload a file to an item."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        adapter._client.upload_file.return_value = {"id": "file-123", "name": "test.txt"}

        result = adapter.upload_file("item-123", str(test_file))

        assert result["id"] == "file-123"
        adapter._client.upload_file.assert_called_once_with("item-123", str(test_file), None)

    def test_upload_file_to_column(self, adapter, tmp_path):
        """Should upload a file to a specific column."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        adapter._client.upload_file.return_value = {"id": "file-123"}

        result = adapter.upload_file("item-123", str(test_file), column_id="file_col")

        assert result["id"] == "file-123"
        adapter._client.upload_file.assert_called_once_with("item-123", str(test_file), "file_col")

    def test_get_item_files(self, adapter):
        """Should get all files attached to an item."""
        adapter._client.get_item_files.return_value = [
            {"id": "file-1", "name": "file1.pdf", "url": "https://example.com/file1.pdf"},
            {"id": "file-2", "name": "file2.png", "url": "https://example.com/file2.png"},
        ]

        files = adapter.get_item_files("item-123")

        assert len(files) == 2
        assert files[0]["name"] == "file1.pdf"
        assert files[1]["name"] == "file2.png"
        adapter._client.get_item_files.assert_called_once_with("item-123")


# =============================================================================
# Timeline/Gantt Tests
# =============================================================================


class TestMondayAdapterTimeline:
    """Tests for timeline/Gantt view functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        with patch("spectryn.adapters.monday.adapter.MondayApiClient"):
            return MondayAdapter(
                api_token="test_token",
                board_id="board-123",
                dry_run=False,
            )

    def test_set_timeline_dates(self, adapter):
        """Should set timeline dates for an item."""
        adapter._get_timeline_column_id = MagicMock(return_value="timeline_col")
        adapter._client.update_timeline_dates.return_value = {"id": "item-123"}

        result = adapter.set_timeline_dates(
            "item-123", start_date="2025-01-01", end_date="2025-01-31"
        )

        assert result is True
        adapter._client.update_timeline_dates.assert_called_once_with(
            "item-123",
            start_date="2025-01-01",
            end_date="2025-01-31",
            timeline_column_id="timeline_col",
        )

    def test_get_timeline_dates(self, adapter):
        """Should get timeline dates from an item."""
        adapter._client.get_timeline_dates.return_value = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        }

        dates = adapter.get_timeline_dates("item-123")

        assert dates["start_date"] == "2025-01-01"
        assert dates["end_date"] == "2025-01-31"
        adapter._client.get_timeline_dates.assert_called_once_with("item-123")

    def test_get_timeline_column_id(self, adapter):
        """Should auto-detect timeline column."""
        adapter._get_column_id = MagicMock(return_value="timeline_col")

        col_id = adapter._get_timeline_column_id()

        assert col_id == "timeline_col"
        adapter._get_column_id.assert_called_once_with("timeline", "Timeline")

    def test_get_start_date_column_id(self, adapter):
        """Should auto-detect start date column."""
        adapter._get_column_id = MagicMock(return_value="start_date_col")

        col_id = adapter._get_start_date_column_id()

        assert col_id == "start_date_col"
        adapter._get_column_id.assert_called_once_with("date", "Start Date")

    def test_get_end_date_column_id(self, adapter):
        """Should auto-detect end date column."""
        adapter._get_column_id = MagicMock(return_value="end_date_col")

        col_id = adapter._get_end_date_column_id()

        assert col_id == "end_date_col"
        adapter._get_column_id.assert_called_once_with("date", "End Date")


# =============================================================================
# Webhook Tests
# =============================================================================


class TestMondayAdapterWebhooks:
    """Tests for webhook functionality."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter."""
        with patch("spectryn.adapters.monday.adapter.MondayApiClient"):
            return MondayAdapter(
                api_token="test_token",
                board_id="board-123",
                dry_run=False,
            )

    def test_create_webhook(self, adapter):
        """Should create a webhook subscription."""
        adapter._client.create_webhook.return_value = {
            "id": "webhook-123",
            "board_id": "board-123",
            "url": "https://example.com/webhook",
            "event": "change_column_value",
        }

        result = adapter.create_webhook("https://example.com/webhook")

        assert result["id"] == "webhook-123"
        adapter._client.create_webhook.assert_called_once_with(
            board_id="board-123",
            url="https://example.com/webhook",
            event="change_column_value",
        )

    def test_create_webhook_custom_event(self, adapter):
        """Should create a webhook with custom event type."""
        adapter._client.create_webhook.return_value = {"id": "webhook-123"}

        adapter.create_webhook("https://example.com/webhook", event="create_item")

        adapter._client.create_webhook.assert_called_once_with(
            board_id="board-123",
            url="https://example.com/webhook",
            event="create_item",
        )

    def test_list_webhooks(self, adapter):
        """Should list webhook subscriptions."""
        adapter._client.list_webhooks.return_value = [
            {"id": "webhook-1", "board_id": "board-123", "url": "https://example.com/webhook1"},
            {"id": "webhook-2", "board_id": "board-123", "url": "https://example.com/webhook2"},
        ]

        webhooks = adapter.list_webhooks()

        assert len(webhooks) == 2
        assert webhooks[0]["id"] == "webhook-1"
        adapter._client.list_webhooks.assert_called_once_with(board_id="board-123")

    def test_delete_webhook(self, adapter):
        """Should delete a webhook subscription."""
        adapter._client.delete_webhook.return_value = True

        result = adapter.delete_webhook("webhook-123")

        assert result is True
        adapter._client.delete_webhook.assert_called_once_with("webhook-123")

    def test_verify_webhook(self, adapter):
        """Should verify a webhook subscription."""
        adapter._client.verify_webhook.return_value = {
            "id": "webhook-123",
            "board_id": "board-123",
            "url": "https://example.com/webhook",
            "event": "change_column_value",
        }

        webhook = adapter.verify_webhook("webhook-123")

        assert webhook["id"] == "webhook-123"
        adapter._client.verify_webhook.assert_called_once_with("webhook-123")


class TestMondayWebhookParser:
    """Tests for Monday.com webhook parser."""

    @pytest.fixture
    def parser(self):
        """Create a webhook parser."""
        from spectryn.adapters.monday.webhook_parser import MondayWebhookParser

        return MondayWebhookParser()

    def test_parse_change_column_value(self, parser):
        """Should parse change_column_value event."""
        payload = {
            "event": {
                "type": "change_column_value",
                "pulseId": "123456789",
                "pulseName": "Test Item",
                "boardId": "987654321",
                "groupId": "group_123",
                "userId": "111222333",
                "columnId": "status",
                "columnType": "status",
                "value": {"index": 1, "label": "Working on it"},
                "previousValue": {"index": 0, "label": "Not Started"},
            }
        }

        event = parser.parse(payload)

        assert event.event_type.value == "change_column_value"
        assert event.item_id == "123456789"
        assert event.board_id == "987654321"
        assert event.group_id == "group_123"
        assert event.column_id == "status"
        assert event.is_item_event is True

    def test_parse_create_item(self, parser):
        """Should parse create_item event."""
        payload = {
            "event": {
                "type": "create_item",
                "pulseId": "123456789",
                "pulseName": "New Item",
                "boardId": "987654321",
                "groupId": "group_123",
                "userId": "111222333",
            }
        }

        event = parser.parse(payload)

        assert event.event_type.value == "create_item"
        assert event.item_id == "123456789"
        assert event.is_item_event is True

    def test_parse_create_update(self, parser):
        """Should parse create_update event."""
        payload = {
            "event": {
                "type": "create_update",
                "pulseId": "123456789",
                "boardId": "987654321",
                "userId": "111222333",
            }
        }

        event = parser.parse(payload)

        assert event.event_type.value == "create_update"
        assert event.is_update_event is True
        assert event.is_item_event is False

    def test_parse_unknown_event(self, parser):
        """Should handle unknown event types."""
        payload = {
            "event": {
                "type": "unknown_event_type",
                "pulseId": "123456789",
            }
        }

        event = parser.parse(payload)

        assert event.event_type.value == "unknown"

    def test_should_trigger_sync(self, parser):
        """Should determine if sync should be triggered."""
        event = parser.parse(
            {
                "event": {
                    "type": "change_column_value",
                    "pulseId": "123456789",
                    "boardId": "987654321",
                }
            }
        )

        # Should trigger for item events
        assert parser.should_trigger_sync(event, board_id="987654321") is True

        # Should not trigger for different board
        assert parser.should_trigger_sync(event, board_id="999999999") is False

    def test_extract_item_key(self, parser):
        """Should extract item key from event."""
        event = parser.parse(
            {
                "event": {
                    "type": "change_column_value",
                    "pulseId": "123456789",
                    "boardId": "987654321",
                }
            }
        )

        item_key = parser.extract_item_key(event)

        assert item_key == "123456789"
