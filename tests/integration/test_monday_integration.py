"""
Integration tests with mocked Monday.com API responses.

These tests verify the full flow from adapter through client
using realistic GraphQL responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.monday.adapter import MondayAdapter
from spectryn.adapters.monday.client import MondayApiClient
from spectryn.adapters.monday.webhook_parser import (
    MondayWebhookEvent,
    MondayWebhookEventType,
    MondayWebhookParser,
)
from spectryn.core.ports.issue_tracker import NotFoundError, TransitionError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def monday_config():
    """Monday.com adapter configuration."""
    return {
        "api_token": "monday_test_token_12345",
        "board_id": "123456789",
        "workspace_id": "987654321",
    }


@pytest.fixture
def mock_viewer_response():
    """Mock response for viewer query."""
    return {
        "id": "user-123",
        "name": "Test User",
        "email": "test@example.com",
    }


@pytest.fixture
def mock_board_response():
    """Mock response for board query."""
    return {
        "id": "123456789",
        "name": "Test Board",
        "description": "Test Description",
        "workspace": {"id": "987654321", "name": "Test Workspace"},
        "groups": [
            {"id": "group_1", "title": "Group 1"},
            {"id": "group_2", "title": "Group 2"},
        ],
        "columns": [
            {"id": "status", "title": "Status", "type": "status"},
            {"id": "priority", "title": "Priority", "type": "priority"},
            {"id": "numbers", "title": "Story Points", "type": "numbers"},
            {"id": "timeline", "title": "Timeline", "type": "timeline"},
        ],
    }


@pytest.fixture
def mock_item_response():
    """Mock response for item query."""
    return {
        "id": "item-789",
        "name": "Sample User Story",
        "group": {"id": "group_1", "title": "Group 1"},
        "board": {"id": "123456789", "name": "Test Board"},
        "column_values": [
            {
                "id": "status",
                "type": "status",
                "text": "Working on it",
                "value": '{"index": 1, "label": "Working on it"}',
            },
            {
                "id": "numbers",
                "type": "numbers",
                "text": "5",
                "value": "5",
            },
        ],
        "subitems": [
            {"id": "subitem-1", "name": "Subtask 1"},
            {"id": "subitem-2", "name": "Subtask 2"},
        ],
        "updates": [
            {
                "id": "update-1",
                "body": "This is a comment",
                "creator": {"name": "Test User", "email": "test@example.com"},
                "created_at": "2024-01-15T10:00:00Z",
            }
        ],
    }


@pytest.fixture
def mock_board_items_response():
    """Mock response for board items."""
    return [
        {
            "id": "item-10",
            "name": "Story Alpha",
            "group": {"id": "group_1", "title": "Group 1"},
            "column_values": [
                {
                    "id": "status",
                    "type": "status",
                    "text": "Not Started",
                    "value": '{"index": 0, "label": "Not Started"}',
                }
            ],
            "subitems": [],
            "updates": [],
        },
        {
            "id": "item-11",
            "name": "Story Beta",
            "group": {"id": "group_1", "title": "Group 1"},
            "column_values": [
                {
                    "id": "status",
                    "type": "status",
                    "text": "Working on it",
                    "value": '{"index": 1, "label": "Working on it"}',
                }
            ],
            "subitems": [
                {"id": "subitem-3", "name": "Subtask for Beta"},
            ],
            "updates": [],
        },
    ]


@pytest.fixture
def mock_webhook_response():
    """Mock response for webhook creation."""
    return {
        "id": "webhook-123",
        "board_id": "123456789",
        "url": "https://example.com/webhook",
        "event": "change_column_value",
    }


# =============================================================================
# MondayAdapter Tests
# =============================================================================


class TestMondayAdapterIntegration:
    """Integration tests for MondayAdapter with mocked GraphQL."""

    def test_get_issue_parses_response(
        self, monday_config, mock_item_response, mock_board_response
    ):
        """Test get_issue correctly parses API response."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_get.return_value = mock_item_response
            mock_board.return_value = mock_board_response

            issue = adapter.get_issue("item-789")

            assert issue.key == "item-789"
            assert issue.summary == "Sample User Story"
            assert issue.status == "Working on it"
            assert issue.story_points == 5.0
            assert len(issue.subtasks) == 2
            assert len(issue.comments) == 1

    def test_get_epic_children_from_group(
        self, monday_config, mock_board_items_response, mock_board_response
    ):
        """Test get_epic_children fetches group items."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_board_items") as mock_items,
            patch.object(adapter, "_get_group_id") as mock_group,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_items.return_value = mock_board_items_response
            mock_group.return_value = "group_1"
            mock_board.return_value = mock_board_response

            children = adapter.get_epic_children("group_1")

            assert len(children) == 2
            assert children[0].key == "item-10"
            assert children[0].summary == "Story Alpha"
            assert children[1].key == "item-11"
            assert len(children[1].subtasks) == 1

    def test_get_issue_comments(self, monday_config, mock_item_response, mock_board_response):
        """Test get_issue_comments returns parsed comments."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_get.return_value = mock_item_response
            mock_board.return_value = mock_board_response

            comments = adapter.get_issue_comments("item-789")

            assert len(comments) == 1
            assert comments[0]["body"] == "This is a comment"
            assert comments[0]["author"] == "Test User"

    def test_update_issue_description_dry_run(self, monday_config, mock_board_response):
        """Test update_issue_description in dry_run mode."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with patch.object(adapter, "_get_board") as mock_board:
            mock_board.return_value = mock_board_response

            result = adapter.update_issue_description("item-789", "New description")

            assert result is True

    def test_create_subtask(self, monday_config, mock_board_response):
        """Test create_subtask creates subitem."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter._client, "create_subitem") as mock_create,
            patch.object(adapter._client, "add_update"),
            patch.object(adapter, "_get_story_points_column_id") as mock_sp_col,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_create.return_value = {"id": "subitem-200"}
            mock_sp_col.return_value = None
            mock_board.return_value = mock_board_response

            result = adapter.create_subtask(
                parent_key="item-789",
                summary="New subtask",
                description="Subtask description",
                project_key="123456789",
                story_points=3,
            )

            assert result == "subitem-200"
            mock_create.assert_called_once()

    def test_transition_issue(self, monday_config, mock_item_response, mock_board_response):
        """Test transition_issue changes status."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        # Mock item with status column settings
        item_with_status = mock_item_response.copy()
        item_with_status["column_values"] = [
            {
                "id": "status",
                "type": "status",
                "text": "Working on it",
                "value": '{"index": 1}',
                "settings_str": '{"labels":{"0":{"label":"Not Started"},"1":{"label":"Working on it"},"2":{"label":"Done"}}}',
            }
        ]

        with (
            patch.object(adapter, "_get_status_column_id") as mock_status_col,
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter._client, "update_item") as mock_update,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_status_col.return_value = "status"
            mock_get.return_value = item_with_status
            mock_board.return_value = mock_board_response

            result = adapter.transition_issue("item-789", "Done")

            assert result is True
            mock_update.assert_called_once()

    def test_transition_issue_invalid_status(
        self, monday_config, mock_item_response, mock_board_response
    ):
        """Test transition_issue raises error for invalid status."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        # Use empty labels to trigger error when status not found
        item_with_status = mock_item_response.copy()
        item_with_status["column_values"] = [
            {
                "id": "status",
                "type": "status",
                "text": "Working on it",
                "settings_str": '{"labels":{}}',  # Empty labels will cause error
            }
        ]

        with (
            patch.object(adapter, "_get_status_column_id") as mock_status_col,
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_status_col.return_value = "status"
            mock_get.return_value = item_with_status
            mock_board.return_value = mock_board_response

            with pytest.raises(TransitionError, match="Status 'InvalidStatus' not found"):
                adapter.transition_issue("item-789", "InvalidStatus")

    def test_add_comment(self, monday_config, mock_board_response):
        """Test add_comment adds to item."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter._client, "add_update") as mock_comment,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_board.return_value = mock_board_response

            result = adapter.add_comment("item-789", "This is a comment")

            assert result is True
            mock_comment.assert_called_once_with("item-789", "This is a comment")

    def test_search_issues(self, monday_config, mock_board_items_response, mock_board_response):
        """Test search_issues returns matching results."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "get_board_items") as mock_items,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_items.return_value = mock_board_items_response
            mock_board.return_value = mock_board_response

            results = adapter.search_issues("story", max_results=50)

            assert len(results) == 2
            assert results[0].summary == "Story Alpha"


class TestMondayConnectionHandling:
    """Tests for connection handling."""

    def test_test_connection_success(
        self, monday_config, mock_viewer_response, mock_board_response
    ):
        """Test connection test returns True on success."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "test_connection") as mock_conn,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_conn.return_value = True
            mock_board.return_value = mock_board_response

            assert adapter.test_connection() is True

    def test_test_connection_board_not_found(self, monday_config, mock_viewer_response):
        """Test connection test returns False if board not found."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter._client, "test_connection") as mock_conn,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_conn.return_value = True
            mock_board.side_effect = NotFoundError("Board not found")

            assert adapter.test_connection() is False

    def test_adapter_name(self, monday_config):
        """Test adapter returns correct name."""
        adapter = MondayAdapter(**monday_config, dry_run=True)
        assert adapter.name == "Monday.com"


class TestMondayFileAttachments:
    """Tests for file attachment operations."""

    def test_upload_file(self, monday_config, mock_board_response, tmp_path):
        """Test upload_file uploads to item."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        with (
            patch.object(adapter._client, "upload_file") as mock_upload,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_upload.return_value = {"id": "file-123", "name": "test.txt"}
            mock_board.return_value = mock_board_response

            result = adapter.upload_file("item-789", str(test_file))

            assert result["id"] == "file-123"
            mock_upload.assert_called_once()

    def test_get_item_files(self, monday_config, mock_board_response):
        """Test get_item_files returns file list."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        mock_files = [
            {"id": "file-1", "name": "file1.pdf", "url": "https://example.com/file1.pdf"},
            {"id": "file-2", "name": "file2.png", "url": "https://example.com/file2.png"},
        ]

        with (
            patch.object(adapter._client, "get_item_files") as mock_get_files,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_get_files.return_value = mock_files
            mock_board.return_value = mock_board_response

            files = adapter.get_item_files("item-789")

            assert len(files) == 2
            assert files[0]["name"] == "file1.pdf"


class TestMondayTimelineOperations:
    """Tests for timeline/Gantt operations."""

    def test_set_timeline_dates(self, monday_config, mock_board_response):
        """Test set_timeline_dates updates timeline."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter, "_get_timeline_column_id") as mock_timeline_col,
            patch.object(adapter._client, "update_timeline_dates") as mock_update,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_timeline_col.return_value = "timeline"
            mock_board.return_value = mock_board_response

            result = adapter.set_timeline_dates(
                "item-789", start_date="2025-01-01", end_date="2025-01-31"
            )

            assert result is True
            mock_update.assert_called_once()

    def test_get_timeline_dates(self, monday_config, mock_board_response):
        """Test get_timeline_dates retrieves dates."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        mock_dates = {"start_date": "2025-01-01", "end_date": "2025-01-31"}

        with (
            patch.object(adapter._client, "get_timeline_dates") as mock_get_dates,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_get_dates.return_value = mock_dates
            mock_board.return_value = mock_board_response

            dates = adapter.get_timeline_dates("item-789")

            assert dates["start_date"] == "2025-01-01"
            assert dates["end_date"] == "2025-01-31"


class TestMondayWebhookOperations:
    """Tests for webhook operations."""

    def test_create_webhook(self, monday_config, mock_webhook_response, mock_board_response):
        """Test create_webhook creates subscription."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter._client, "create_webhook") as mock_create,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_create.return_value = mock_webhook_response
            mock_board.return_value = mock_board_response

            result = adapter.create_webhook("https://example.com/webhook")

            assert result["id"] == "webhook-123"
            mock_create.assert_called_once_with(
                board_id="123456789",
                url="https://example.com/webhook",
                event="change_column_value",
            )

    def test_list_webhooks(self, monday_config, mock_board_response):
        """Test list_webhooks returns subscriptions."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        mock_webhooks = [
            {"id": "webhook-1", "board_id": "123456789", "url": "https://example.com/webhook1"},
            {"id": "webhook-2", "board_id": "123456789", "url": "https://example.com/webhook2"},
        ]

        with (
            patch.object(adapter._client, "list_webhooks") as mock_list,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_list.return_value = mock_webhooks
            mock_board.return_value = mock_board_response

            webhooks = adapter.list_webhooks()

            assert len(webhooks) == 2
            assert webhooks[0]["id"] == "webhook-1"

    def test_delete_webhook(self, monday_config, mock_board_response):
        """Test delete_webhook removes subscription."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter._client, "delete_webhook") as mock_delete,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_delete.return_value = True
            mock_board.return_value = mock_board_response

            result = adapter.delete_webhook("webhook-123")

            assert result is True
            mock_delete.assert_called_once_with("webhook-123")


class TestMondayWebhookParser:
    """Tests for Monday.com webhook parser."""

    def test_parse_change_column_value(self):
        """Test parsing change_column_value event."""
        parser = MondayWebhookParser()

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

        assert event.event_type == MondayWebhookEventType.CHANGE_COLUMN_VALUE
        assert event.item_id == "123456789"
        assert event.board_id == "987654321"
        assert event.group_id == "group_123"
        assert event.column_id == "status"
        assert event.is_item_event is True

    def test_parse_create_item(self):
        """Test parsing create_item event."""
        parser = MondayWebhookParser()

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

        assert event.event_type == MondayWebhookEventType.CREATE_ITEM
        assert event.item_id == "123456789"
        assert event.is_item_event is True

    def test_should_trigger_sync(self):
        """Test should_trigger_sync logic."""
        parser = MondayWebhookParser()

        event = parser.parse(
            {
                "event": {
                    "type": "change_column_value",
                    "pulseId": "123456789",
                    "boardId": "987654321",
                }
            }
        )

        # Should trigger for item events on matching board
        assert parser.should_trigger_sync(event, board_id="987654321") is True

        # Should not trigger for different board
        assert parser.should_trigger_sync(event, board_id="999999999") is False

    def test_extract_item_key(self):
        """Test extract_item_key from event."""
        parser = MondayWebhookParser()

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


class TestMondayEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_issue_with_empty_subitems(self, monday_config, mock_board_response):
        """Test get_issue handles empty subitems."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        item_no_subitems = {
            "id": "item-1",
            "name": "Item without subitems",
            "group": {"id": "group_1", "title": "Group 1"},
            "board": {"id": "123456789", "name": "Test Board"},
            "column_values": [],
            "subitems": [],
            "updates": [],
        }

        with (
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_get.return_value = item_no_subitems
            mock_board.return_value = mock_board_response

            issue = adapter.get_issue("item-1")

            assert issue.key == "item-1"
            assert len(issue.subtasks) == 0

    def test_get_issue_with_missing_status_column(self, monday_config, mock_board_response):
        """Test get_issue handles missing status column."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        item_no_status = {
            "id": "item-1",
            "name": "Item without status",
            "group": {"id": "group_1", "title": "Group 1"},
            "board": {"id": "123456789", "name": "Test Board"},
            "column_values": [],
            "subitems": [],
            "updates": [],
        }

        with (
            patch.object(adapter, "_get_status_column_id") as mock_status_col,
            patch.object(adapter._client, "get_item") as mock_get,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_status_col.return_value = None
            mock_get.return_value = item_no_status
            mock_board.return_value = mock_board_response

            issue = adapter.get_issue("item-1")

            assert issue.key == "item-1"
            assert issue.status == "Unknown"

    def test_update_story_points_without_column(self, monday_config, mock_board_response):
        """Test update_story_points handles missing column."""
        adapter = MondayAdapter(**monday_config, dry_run=False)

        with (
            patch.object(adapter, "_get_story_points_column_id") as mock_sp_col,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_sp_col.return_value = None
            mock_board.return_value = mock_board_response

            result = adapter.update_issue_story_points("item-789", 5.0)

            assert result is False  # Should return False when column not found

    def test_get_epic_children_with_group_name(
        self, monday_config, mock_board_items_response, mock_board_response
    ):
        """Test get_epic_children with group name instead of ID."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter, "_get_group_id") as mock_group,
            patch.object(adapter._client, "get_board_items") as mock_items,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_group.return_value = "group_1"
            mock_items.return_value = mock_board_items_response
            mock_board.return_value = mock_board_response

            children = adapter.get_epic_children("Group 1")

            assert len(children) == 2
            mock_group.assert_called_once_with("Group 1")

    def test_get_epic_children_group_not_found(self, monday_config, mock_board_response):
        """Test get_epic_children raises error for non-existent group."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with (
            patch.object(adapter, "_get_group_id") as mock_group,
            patch.object(adapter, "_get_board") as mock_board,
        ):
            mock_group.return_value = None
            mock_board.return_value = mock_board_response

            with pytest.raises(NotFoundError, match="Group not found"):
                adapter.get_epic_children("NonExistentGroup")


class TestMondayColumnAutoDetection:
    """Tests for column auto-detection."""

    def test_auto_detect_status_column(self, monday_config, mock_board_response):
        """Test auto-detection of status column."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with patch.object(adapter, "_get_board") as mock_board:
            mock_board.return_value = mock_board_response

            col_id = adapter._get_status_column_id()

            assert col_id == "status"

    def test_auto_detect_story_points_column(self, monday_config, mock_board_response):
        """Test auto-detection of story points column."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with patch.object(adapter, "_get_board") as mock_board:
            mock_board.return_value = mock_board_response

            col_id = adapter._get_story_points_column_id()

            assert col_id == "numbers"

    def test_auto_detect_timeline_column(self, monday_config, mock_board_response):
        """Test auto-detection of timeline column."""
        adapter = MondayAdapter(**monday_config, dry_run=True)

        with patch.object(adapter, "_get_board") as mock_board:
            mock_board.return_value = mock_board_response

            col_id = adapter._get_timeline_column_id()

            assert col_id == "timeline"
