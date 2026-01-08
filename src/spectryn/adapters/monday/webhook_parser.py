"""
Monday.com Webhook Parser - Parse Monday.com webhook events.

Monday.com webhooks send events when items on boards change.
This parser converts Monday.com webhook payloads into a standard format
that can be used by the webhook server for reverse sync.
"""

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class MondayWebhookEventType(Enum):
    """Types of Monday.com webhook events."""

    CHANGE_COLUMN_VALUE = "change_column_value"
    CREATE_ITEM = "create_item"
    CREATE_UPDATE = "create_update"
    CHANGE_STATUS = "change_status"
    CHANGE_NAME = "change_name"
    CREATE_SUBITEM = "create_subitem"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, event_type: str) -> "MondayWebhookEventType":
        """Parse event type from Monday.com webhook."""
        event_map = {
            "change_column_value": cls.CHANGE_COLUMN_VALUE,
            "create_item": cls.CREATE_ITEM,
            "create_update": cls.CREATE_UPDATE,
            "change_status": cls.CHANGE_STATUS,
            "change_name": cls.CHANGE_NAME,
            "create_subitem": cls.CREATE_SUBITEM,
        }
        return event_map.get(event_type.lower(), cls.UNKNOWN)


@dataclass
class MondayWebhookEvent:
    """Parsed Monday.com webhook event."""

    event_type: MondayWebhookEventType
    timestamp: datetime = field(default_factory=datetime.now)
    item_id: str | None = None
    board_id: str | None = None
    group_id: str | None = None
    user_id: str | None = None
    column_id: str | None = None
    column_type: str | None = None
    value: Any = None
    previous_value: Any = None
    raw_payload: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.event_type.value}: {self.item_id or 'N/A'}"

    @property
    def is_item_event(self) -> bool:
        """Check if this is an item-related event."""
        return self.event_type in (
            MondayWebhookEventType.CHANGE_COLUMN_VALUE,
            MondayWebhookEventType.CREATE_ITEM,
            MondayWebhookEventType.CHANGE_STATUS,
            MondayWebhookEventType.CHANGE_NAME,
            MondayWebhookEventType.CREATE_SUBITEM,
        )

    @property
    def is_update_event(self) -> bool:
        """Check if this is an update/comment event."""
        return self.event_type == MondayWebhookEventType.CREATE_UPDATE


class MondayWebhookParser:
    """
    Parses Monday.com webhook payloads.

    Monday.com webhooks have a specific format:
    {
        "event": {
            "type": "change_column_value",
            "pulseId": "123456789",
            "pulseName": "Item Name",
            "boardId": "123456789",
            "groupId": "group_123",
            "userId": "123456789",
            "columnId": "status",
            "columnType": "status",
            "value": {...},
            "previousValue": {...}
        }
    }
    """

    def parse(self, payload: dict[str, Any]) -> MondayWebhookEvent:
        """
        Parse a Monday.com webhook payload.

        Args:
            payload: Raw webhook payload from Monday.com

        Returns:
            Parsed webhook event
        """
        event_data = payload.get("event", {})

        # Extract event type
        event_type_str = event_data.get("type", "unknown")
        event_type = MondayWebhookEventType.from_string(event_type_str)

        # Extract item/board information
        item_id = event_data.get("pulseId")
        board_id = event_data.get("boardId")
        group_id = event_data.get("groupId")
        user_id = event_data.get("userId")

        # Extract column information (for column change events)
        column_id = event_data.get("columnId")
        column_type = event_data.get("columnType")
        value = event_data.get("value")
        previous_value = event_data.get("previousValue")

        # Extract timestamp if available
        timestamp = datetime.now()
        if "timestamp" in event_data:
            with contextlib.suppress(ValueError, TypeError):
                timestamp = datetime.fromtimestamp(event_data["timestamp"])

        return MondayWebhookEvent(
            event_type=event_type,
            timestamp=timestamp,
            item_id=str(item_id) if item_id else None,
            board_id=str(board_id) if board_id else None,
            group_id=str(group_id) if group_id else None,
            user_id=str(user_id) if user_id else None,
            column_id=str(column_id) if column_id else None,
            column_type=column_type,
            value=value,
            previous_value=previous_value,
            raw_payload=payload,
        )

    def should_trigger_sync(self, event: MondayWebhookEvent, board_id: str | None = None) -> bool:
        """
        Determine if a webhook event should trigger a sync.

        Args:
            event: Parsed webhook event
            board_id: Optional board ID to filter by

        Returns:
            True if sync should be triggered
        """
        # Only handle item-related events
        if not event.is_item_event and not event.is_update_event:
            return False

        # Filter by board if specified
        return not (board_id and event.board_id != board_id)

    def extract_item_key(self, event: MondayWebhookEvent) -> str | None:
        """
        Extract item key from event for sync operations.

        Args:
            event: Parsed webhook event

        Returns:
            Item ID/key or None
        """
        return event.item_id
