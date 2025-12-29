"""
Change Notifications - Slack/Discord/Teams notifications on sync.

This module provides notification support for sync events:
- Slack incoming webhooks
- Discord webhooks
- Microsoft Teams webhooks
- Generic webhook (custom endpoints)

Notifications are sent when:
- Sync completes (success or failure)
- Stories are created/updated
- Conflicts are detected
- Errors occur
"""

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class NotificationLevel(Enum):
    """Notification severity levels."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationType(Enum):
    """Types of notifications."""

    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"
    STORY_CREATED = "story_created"
    STORY_UPDATED = "story_updated"
    STORY_DELETED = "story_deleted"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    PULL_COMPLETED = "pull_completed"
    PUSH_COMPLETED = "push_completed"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class NotificationEvent:
    """A notification event to be sent."""

    notification_type: NotificationType
    level: NotificationLevel = NotificationLevel.INFO
    title: str = ""
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    # Context
    epic_key: str | None = None
    project: str | None = None
    source: str | None = None  # markdown file, tracker name, etc.

    # Details
    stories_affected: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    # For errors
    error: str | None = None
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.notification_type.value,
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "epic_key": self.epic_key,
            "project": self.project,
            "source": self.source,
            "stories_affected": self.stories_affected,
            "details": self.details,
            "error": self.error,
        }


class NotificationProvider(ABC):
    """Abstract base for notification providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        ...

    @abstractmethod
    def send(self, event: NotificationEvent) -> bool:
        """
        Send a notification.

        Args:
            event: The notification event.

        Returns:
            True if sent successfully.
        """
        ...

    def format_title(self, event: NotificationEvent) -> str:
        """Format the notification title."""
        if event.title:
            return event.title

        type_titles = {
            NotificationType.SYNC_STARTED: "Sync Started",
            NotificationType.SYNC_COMPLETED: "Sync Completed",
            NotificationType.SYNC_FAILED: "Sync Failed",
            NotificationType.STORY_CREATED: "Story Created",
            NotificationType.STORY_UPDATED: "Story Updated",
            NotificationType.CONFLICT_DETECTED: "Conflict Detected",
            NotificationType.PULL_COMPLETED: "Pull Completed",
            NotificationType.PUSH_COMPLETED: "Push Completed",
            NotificationType.ERROR: "Error",
        }
        return type_titles.get(event.notification_type, "Notification")


class SlackNotifier(NotificationProvider):
    """
    Slack incoming webhook notifier.

    Uses Slack's Block Kit for rich formatting.
    """

    def __init__(self, webhook_url: str, channel: str | None = None):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack incoming webhook URL.
            channel: Optional channel override.
        """
        self.webhook_url = webhook_url
        self.channel = channel
        self.logger = logging.getLogger("SlackNotifier")

    @property
    def name(self) -> str:
        return "Slack"

    def send(self, event: NotificationEvent) -> bool:
        """Send notification to Slack."""
        payload = self._build_payload(event)

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except urllib.error.URLError as e:
            self.logger.error(f"Failed to send Slack notification: {e}")
            return False

    def _build_payload(self, event: NotificationEvent) -> dict[str, Any]:
        """Build Slack message payload."""
        title = self.format_title(event)
        emoji = self._get_emoji(event.level)
        color = self._get_color(event.level)

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {title}", "emoji": True},
            }
        ]

        # Main message
        if event.message:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": event.message},
                }
            )

        # Context fields
        fields = []
        if event.epic_key:
            fields.append({"type": "mrkdwn", "text": f"*Epic:* {event.epic_key}"})
        if event.project:
            fields.append({"type": "mrkdwn", "text": f"*Project:* {event.project}"})
        if event.stories_affected > 0:
            fields.append(
                {
                    "type": "mrkdwn",
                    "text": f"*Stories:* {event.stories_affected}",
                }
            )

        if fields:
            blocks.append({"type": "section", "fields": fields})

        # Error details
        if event.error:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"```{event.error}```"},
                }
            )

        # Timestamp
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🕐 {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            }
        )

        payload: dict[str, Any] = {
            "blocks": blocks,
            "attachments": [{"color": color, "blocks": []}],
        }

        if self.channel:
            payload["channel"] = self.channel

        return payload

    def _get_emoji(self, level: NotificationLevel) -> str:
        """Get emoji for level."""
        emojis = {
            NotificationLevel.INFO: "ℹ️",
            NotificationLevel.SUCCESS: "✅",
            NotificationLevel.WARNING: "⚠️",
            NotificationLevel.ERROR: "❌",
        }
        return emojis.get(level, "📢")

    def _get_color(self, level: NotificationLevel) -> str:
        """Get Slack color for level."""
        colors = {
            NotificationLevel.INFO: "#2196F3",
            NotificationLevel.SUCCESS: "#4CAF50",
            NotificationLevel.WARNING: "#FF9800",
            NotificationLevel.ERROR: "#F44336",
        }
        return colors.get(level, "#9E9E9E")


class DiscordNotifier(NotificationProvider):
    """
    Discord webhook notifier.

    Uses Discord's embed format for rich messages.
    """

    def __init__(self, webhook_url: str, username: str = "Spectra"):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL.
            username: Bot username to display.
        """
        self.webhook_url = webhook_url
        self.username = username
        self.logger = logging.getLogger("DiscordNotifier")

    @property
    def name(self) -> str:
        return "Discord"

    def send(self, event: NotificationEvent) -> bool:
        """Send notification to Discord."""
        payload = self._build_payload(event)

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status in (200, 204)
        except urllib.error.URLError as e:
            self.logger.error(f"Failed to send Discord notification: {e}")
            return False

    def _build_payload(self, event: NotificationEvent) -> dict[str, Any]:
        """Build Discord message payload."""
        title = self.format_title(event)
        color = self._get_color(event.level)

        embed: dict[str, Any] = {
            "title": title,
            "color": color,
            "timestamp": event.timestamp.isoformat(),
        }

        if event.message:
            embed["description"] = event.message

        # Fields
        fields = []
        if event.epic_key:
            fields.append({"name": "Epic", "value": event.epic_key, "inline": True})
        if event.project:
            fields.append({"name": "Project", "value": event.project, "inline": True})
        if event.stories_affected > 0:
            fields.append(
                {
                    "name": "Stories",
                    "value": str(event.stories_affected),
                    "inline": True,
                }
            )

        if event.error:
            fields.append(
                {
                    "name": "Error",
                    "value": f"```{event.error[:1000]}```",
                    "inline": False,
                }
            )

        if fields:
            embed["fields"] = fields

        # Footer
        embed["footer"] = {"text": "Spectra Sync"}

        return {
            "username": self.username,
            "embeds": [embed],
        }

    def _get_color(self, level: NotificationLevel) -> int:
        """Get Discord color (decimal) for level."""
        colors = {
            NotificationLevel.INFO: 0x2196F3,
            NotificationLevel.SUCCESS: 0x4CAF50,
            NotificationLevel.WARNING: 0xFF9800,
            NotificationLevel.ERROR: 0xF44336,
        }
        return colors.get(level, 0x9E9E9E)


class TeamsNotifier(NotificationProvider):
    """
    Microsoft Teams webhook notifier.

    Uses Adaptive Cards for rich formatting.
    """

    def __init__(self, webhook_url: str):
        """
        Initialize Teams notifier.

        Args:
            webhook_url: Teams incoming webhook URL.
        """
        self.webhook_url = webhook_url
        self.logger = logging.getLogger("TeamsNotifier")

    @property
    def name(self) -> str:
        return "Teams"

    def send(self, event: NotificationEvent) -> bool:
        """Send notification to Teams."""
        payload = self._build_payload(event)

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except urllib.error.URLError as e:
            self.logger.error(f"Failed to send Teams notification: {e}")
            return False

    def _build_payload(self, event: NotificationEvent) -> dict[str, Any]:
        """Build Teams Adaptive Card payload."""
        title = self.format_title(event)
        color = self._get_theme_color(event.level)

        # Build facts list
        facts = []
        if event.epic_key:
            facts.append({"title": "Epic", "value": event.epic_key})
        if event.project:
            facts.append({"title": "Project", "value": event.project})
        if event.stories_affected > 0:
            facts.append({"title": "Stories", "value": str(event.stories_affected)})
        facts.append(
            {
                "title": "Time",
                "value": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        # Build card body
        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "size": "Large",
                "weight": "Bolder",
                "text": title,
                "wrap": True,
            }
        ]

        if event.message:
            body.append(
                {
                    "type": "TextBlock",
                    "text": event.message,
                    "wrap": True,
                }
            )

        if facts:
            body.append(
                {
                    "type": "FactSet",
                    "facts": facts,
                }
            )

        if event.error:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"Error: {event.error}",
                    "wrap": True,
                    "color": "Attention",
                }
            )

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "themeColor": color,
                        "body": body,
                    },
                }
            ],
        }

    def _get_theme_color(self, level: NotificationLevel) -> str:
        """Get Teams theme color for level."""
        colors = {
            NotificationLevel.INFO: "2196F3",
            NotificationLevel.SUCCESS: "4CAF50",
            NotificationLevel.WARNING: "FF9800",
            NotificationLevel.ERROR: "F44336",
        }
        return colors.get(level, "9E9E9E")


class GenericWebhookNotifier(NotificationProvider):
    """
    Generic webhook notifier.

    Sends JSON payload to any HTTP endpoint.
    """

    def __init__(
        self,
        webhook_url: str,
        headers: dict[str, str] | None = None,
        method: str = "POST",
    ):
        """
        Initialize generic webhook notifier.

        Args:
            webhook_url: Webhook URL.
            headers: Optional custom headers.
            method: HTTP method (default: POST).
        """
        self.webhook_url = webhook_url
        self.headers = headers or {}
        self.method = method
        self.logger = logging.getLogger("GenericWebhookNotifier")

    @property
    def name(self) -> str:
        return "Webhook"

    def send(self, event: NotificationEvent) -> bool:
        """Send notification to webhook."""
        payload = event.to_dict()

        try:
            data = json.dumps(payload).encode("utf-8")
            req_headers = {"Content-Type": "application/json", **self.headers}
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers=req_headers,
                method=self.method,
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return 200 <= response.status < 300
        except urllib.error.URLError as e:
            self.logger.error(f"Failed to send webhook notification: {e}")
            return False


@dataclass
class NotificationConfig:
    """Configuration for notifications."""

    enabled: bool = True

    # Webhook URLs
    slack_webhook: str | None = None
    discord_webhook: str | None = None
    teams_webhook: str | None = None
    generic_webhook: str | None = None

    # Filtering
    min_level: NotificationLevel = NotificationLevel.INFO
    notify_on_success: bool = True
    notify_on_failure: bool = True
    notify_on_conflicts: bool = True

    # Additional settings
    slack_channel: str | None = None
    discord_username: str = "Spectra"


class NotificationManager:
    """
    Manages notification providers and dispatches events.
    """

    def __init__(self, config: NotificationConfig | None = None):
        """
        Initialize notification manager.

        Args:
            config: Notification configuration.
        """
        self.config = config or NotificationConfig()
        self.providers: list[NotificationProvider] = []
        self.logger = logging.getLogger("NotificationManager")

        self._setup_providers()

    def _setup_providers(self) -> None:
        """Setup notification providers based on config."""
        if self.config.slack_webhook:
            self.providers.append(
                SlackNotifier(
                    self.config.slack_webhook,
                    channel=self.config.slack_channel,
                )
            )

        if self.config.discord_webhook:
            self.providers.append(
                DiscordNotifier(
                    self.config.discord_webhook,
                    username=self.config.discord_username,
                )
            )

        if self.config.teams_webhook:
            self.providers.append(TeamsNotifier(self.config.teams_webhook))

        if self.config.generic_webhook:
            self.providers.append(GenericWebhookNotifier(self.config.generic_webhook))

    def add_provider(self, provider: NotificationProvider) -> None:
        """Add a notification provider."""
        self.providers.append(provider)

    def notify(self, event: NotificationEvent) -> dict[str, bool]:
        """
        Send notification to all providers.

        Args:
            event: The notification event.

        Returns:
            Dictionary of provider name -> success status.
        """
        if not self.config.enabled:
            return {}

        # Check level filter
        level_order = [
            NotificationLevel.INFO,
            NotificationLevel.SUCCESS,
            NotificationLevel.WARNING,
            NotificationLevel.ERROR,
        ]
        if level_order.index(event.level) < level_order.index(self.config.min_level):
            return {}

        # Check type filters
        if event.notification_type == NotificationType.SYNC_COMPLETED:
            if not self.config.notify_on_success:
                return {}
        elif event.notification_type == NotificationType.SYNC_FAILED:
            if not self.config.notify_on_failure:
                return {}
        elif event.notification_type == NotificationType.CONFLICT_DETECTED:
            if not self.config.notify_on_conflicts:
                return {}

        results = {}
        for provider in self.providers:
            try:
                success = provider.send(event)
                results[provider.name] = success
                if success:
                    self.logger.debug(f"Notification sent to {provider.name}")
                else:
                    self.logger.warning(f"Failed to send notification to {provider.name}")
            except Exception as e:
                self.logger.error(f"Error sending to {provider.name}: {e}")
                results[provider.name] = False

        return results

    def notify_sync_started(
        self,
        epic_key: str,
        source: str | None = None,
    ) -> dict[str, bool]:
        """Notify that sync has started."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_STARTED,
            level=NotificationLevel.INFO,
            message=f"Starting sync for {epic_key}",
            epic_key=epic_key,
            source=source,
        )
        return self.notify(event)

    def notify_sync_completed(
        self,
        epic_key: str,
        stories_synced: int,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        """Notify that sync completed successfully."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
            level=NotificationLevel.SUCCESS,
            message=f"Successfully synced {stories_synced} stories for {epic_key}",
            epic_key=epic_key,
            source=source,
            stories_affected=stories_synced,
            details=details or {},
        )
        return self.notify(event)

    def notify_sync_failed(
        self,
        epic_key: str,
        error: str,
        source: str | None = None,
    ) -> dict[str, bool]:
        """Notify that sync failed."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_FAILED,
            level=NotificationLevel.ERROR,
            message=f"Sync failed for {epic_key}",
            epic_key=epic_key,
            source=source,
            error=error,
        )
        return self.notify(event)

    def notify_conflict(
        self,
        epic_key: str,
        story_id: str,
        conflict_details: str,
    ) -> dict[str, bool]:
        """Notify about a conflict."""
        event = NotificationEvent(
            notification_type=NotificationType.CONFLICT_DETECTED,
            level=NotificationLevel.WARNING,
            message=f"Conflict detected in {story_id}",
            epic_key=epic_key,
            details={"story_id": story_id, "conflict": conflict_details},
        )
        return self.notify(event)


def create_notification_manager(
    slack_webhook: str | None = None,
    discord_webhook: str | None = None,
    teams_webhook: str | None = None,
    generic_webhook: str | None = None,
    slack_channel: str | None = None,
    notify_on_success: bool = True,
    notify_on_failure: bool = True,
) -> NotificationManager:
    """
    Create a notification manager with the given webhooks.

    Args:
        slack_webhook: Slack incoming webhook URL.
        discord_webhook: Discord webhook URL.
        teams_webhook: Teams incoming webhook URL.
        generic_webhook: Generic webhook URL.
        slack_channel: Optional Slack channel override.
        notify_on_success: Whether to notify on successful sync.
        notify_on_failure: Whether to notify on failed sync.

    Returns:
        Configured NotificationManager.
    """
    config = NotificationConfig(
        slack_webhook=slack_webhook,
        discord_webhook=discord_webhook,
        teams_webhook=teams_webhook,
        generic_webhook=generic_webhook,
        slack_channel=slack_channel,
        notify_on_success=notify_on_success,
        notify_on_failure=notify_on_failure,
    )
    return NotificationManager(config)
