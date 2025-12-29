"""Tests for notification system functionality."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.application.notifications import (
    DiscordNotifier,
    GenericWebhookNotifier,
    NotificationConfig,
    NotificationEvent,
    NotificationLevel,
    NotificationManager,
    NotificationType,
    SlackNotifier,
    TeamsNotifier,
    create_notification_manager,
)


class TestNotificationLevel:
    """Tests for NotificationLevel enum."""

    def test_all_levels_exist(self):
        """Test all notification levels are defined."""
        assert NotificationLevel.INFO.value == "info"
        assert NotificationLevel.SUCCESS.value == "success"
        assert NotificationLevel.WARNING.value == "warning"
        assert NotificationLevel.ERROR.value == "error"


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_all_types_exist(self):
        """Test all notification types are defined."""
        assert NotificationType.SYNC_STARTED.value == "sync_started"
        assert NotificationType.SYNC_COMPLETED.value == "sync_completed"
        assert NotificationType.SYNC_FAILED.value == "sync_failed"
        assert NotificationType.CONFLICT_DETECTED.value == "conflict_detected"


class TestNotificationEvent:
    """Tests for NotificationEvent dataclass."""

    def test_create_basic(self):
        """Test creating a basic event."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
            level=NotificationLevel.SUCCESS,
            message="Sync completed",
            epic_key="PROJ-123",
        )
        assert event.notification_type == NotificationType.SYNC_COMPLETED
        assert event.epic_key == "PROJ-123"

    def test_to_dict(self):
        """Test converting event to dictionary."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_FAILED,
            level=NotificationLevel.ERROR,
            message="Sync failed",
            epic_key="PROJ-456",
            error="Connection timeout",
        )
        data = event.to_dict()

        assert data["type"] == "sync_failed"
        assert data["level"] == "error"
        assert data["epic_key"] == "PROJ-456"
        assert data["error"] == "Connection timeout"

    def test_default_timestamp(self):
        """Test that timestamp is set automatically."""
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_STARTED,
        )
        assert isinstance(event.timestamp, datetime)


class TestSlackNotifier:
    """Tests for Slack notifier."""

    def test_name(self):
        """Test provider name."""
        notifier = SlackNotifier("https://hooks.slack.com/test")
        assert notifier.name == "Slack"

    def test_build_payload(self):
        """Test building Slack payload."""
        notifier = SlackNotifier("https://hooks.slack.com/test")
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
            level=NotificationLevel.SUCCESS,
            message="Synced 5 stories",
            epic_key="PROJ-123",
            stories_affected=5,
        )

        payload = notifier._build_payload(event)

        assert "blocks" in payload
        assert len(payload["blocks"]) > 0

    def test_build_payload_with_channel(self):
        """Test building payload with channel override."""
        notifier = SlackNotifier("https://hooks.slack.com/test", channel="#alerts")
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_STARTED,
        )

        payload = notifier._build_payload(event)

        assert payload["channel"] == "#alerts"

    def test_get_emoji(self):
        """Test emoji selection for levels."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        assert notifier._get_emoji(NotificationLevel.SUCCESS) == "✅"
        assert notifier._get_emoji(NotificationLevel.ERROR) == "❌"
        assert notifier._get_emoji(NotificationLevel.WARNING) == "⚠️"

    def test_get_color(self):
        """Test color selection for levels."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        assert notifier._get_color(NotificationLevel.SUCCESS) == "#4CAF50"
        assert notifier._get_color(NotificationLevel.ERROR) == "#F44336"

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        """Test successful send."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        notifier = SlackNotifier("https://hooks.slack.com/test")
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
            message="Test",
        )

        result = notifier.send(event)

        assert result is True
        mock_urlopen.assert_called_once()


class TestDiscordNotifier:
    """Tests for Discord notifier."""

    def test_name(self):
        """Test provider name."""
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test")
        assert notifier.name == "Discord"

    def test_build_payload(self):
        """Test building Discord payload."""
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test")
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_FAILED,
            level=NotificationLevel.ERROR,
            message="Sync failed",
            epic_key="PROJ-123",
            error="API error",
        )

        payload = notifier._build_payload(event)

        assert payload["username"] == "Spectra"
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

    def test_custom_username(self):
        """Test custom username."""
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test", username="MyBot")
        event = NotificationEvent(notification_type=NotificationType.SYNC_STARTED)

        payload = notifier._build_payload(event)

        assert payload["username"] == "MyBot"

    def test_get_color(self):
        """Test color selection (decimal format for Discord)."""
        notifier = DiscordNotifier("https://discord.com/api/webhooks/test")

        assert notifier._get_color(NotificationLevel.SUCCESS) == 0x4CAF50
        assert notifier._get_color(NotificationLevel.ERROR) == 0xF44336


class TestTeamsNotifier:
    """Tests for Teams notifier."""

    def test_name(self):
        """Test provider name."""
        notifier = TeamsNotifier("https://outlook.office.com/webhook/test")
        assert notifier.name == "Teams"

    def test_build_payload(self):
        """Test building Teams Adaptive Card payload."""
        notifier = TeamsNotifier("https://outlook.office.com/webhook/test")
        event = NotificationEvent(
            notification_type=NotificationType.CONFLICT_DETECTED,
            level=NotificationLevel.WARNING,
            message="Conflict found",
            epic_key="PROJ-123",
        )

        payload = notifier._build_payload(event)

        assert payload["type"] == "message"
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"


class TestGenericWebhookNotifier:
    """Tests for generic webhook notifier."""

    def test_name(self):
        """Test provider name."""
        notifier = GenericWebhookNotifier("https://example.com/webhook")
        assert notifier.name == "Webhook"

    @patch("urllib.request.urlopen")
    def test_send_with_custom_headers(self, mock_urlopen):
        """Test sending with custom headers."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        notifier = GenericWebhookNotifier(
            "https://example.com/webhook",
            headers={"Authorization": "Bearer token"},
        )
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
        )

        result = notifier.send(event)

        assert result is True


class TestNotificationConfig:
    """Tests for NotificationConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = NotificationConfig()
        assert config.enabled is True
        assert config.notify_on_success is True
        assert config.notify_on_failure is True
        assert config.slack_webhook is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = NotificationConfig(
            slack_webhook="https://hooks.slack.com/test",
            discord_webhook="https://discord.com/api/webhooks/test",
            notify_on_success=False,
        )
        assert config.slack_webhook == "https://hooks.slack.com/test"
        assert config.discord_webhook == "https://discord.com/api/webhooks/test"
        assert config.notify_on_success is False


class TestNotificationManager:
    """Tests for NotificationManager."""

    def test_create_with_no_providers(self):
        """Test creating manager with no providers."""
        manager = NotificationManager()
        assert len(manager.providers) == 0

    def test_create_with_slack(self):
        """Test creating manager with Slack webhook."""
        config = NotificationConfig(slack_webhook="https://hooks.slack.com/test")
        manager = NotificationManager(config)

        assert len(manager.providers) == 1
        assert manager.providers[0].name == "Slack"

    def test_create_with_multiple_providers(self):
        """Test creating manager with multiple providers."""
        config = NotificationConfig(
            slack_webhook="https://hooks.slack.com/test",
            discord_webhook="https://discord.com/api/webhooks/test",
            teams_webhook="https://outlook.office.com/webhook/test",
        )
        manager = NotificationManager(config)

        assert len(manager.providers) == 3

    def test_add_provider(self):
        """Test adding a provider."""
        manager = NotificationManager()
        provider = SlackNotifier("https://hooks.slack.com/test")

        manager.add_provider(provider)

        assert len(manager.providers) == 1

    def test_notify_disabled(self):
        """Test that notifications are skipped when disabled."""
        config = NotificationConfig(enabled=False, slack_webhook="https://hooks.slack.com/test")
        manager = NotificationManager(config)

        event = NotificationEvent(notification_type=NotificationType.SYNC_COMPLETED)
        results = manager.notify(event)

        assert results == {}

    def test_notify_level_filter(self):
        """Test level filtering."""
        config = NotificationConfig(
            slack_webhook="https://hooks.slack.com/test",
            min_level=NotificationLevel.WARNING,
        )
        manager = NotificationManager(config)

        # Info level should be filtered
        event = NotificationEvent(
            notification_type=NotificationType.SYNC_STARTED,
            level=NotificationLevel.INFO,
        )
        results = manager.notify(event)

        assert results == {}

    def test_notify_success_filter(self):
        """Test success notification filtering."""
        config = NotificationConfig(
            slack_webhook="https://hooks.slack.com/test",
            notify_on_success=False,
        )
        manager = NotificationManager(config)

        event = NotificationEvent(
            notification_type=NotificationType.SYNC_COMPLETED,
            level=NotificationLevel.SUCCESS,
        )
        results = manager.notify(event)

        assert results == {}

    def test_notify_sync_started(self):
        """Test notify_sync_started convenience method."""
        manager = NotificationManager()
        mock_provider = MagicMock()
        mock_provider.name = "Mock"
        mock_provider.send = MagicMock(return_value=True)
        manager.providers = [mock_provider]

        manager.notify_sync_started("PROJ-123", "epic.md")

        mock_provider.send.assert_called_once()
        event = mock_provider.send.call_args[0][0]
        assert event.notification_type == NotificationType.SYNC_STARTED
        assert event.epic_key == "PROJ-123"

    def test_notify_sync_completed(self):
        """Test notify_sync_completed convenience method."""
        manager = NotificationManager()
        mock_provider = MagicMock()
        mock_provider.name = "Mock"
        mock_provider.send = MagicMock(return_value=True)
        manager.providers = [mock_provider]

        manager.notify_sync_completed("PROJ-123", 5)

        mock_provider.send.assert_called_once()
        event = mock_provider.send.call_args[0][0]
        assert event.notification_type == NotificationType.SYNC_COMPLETED
        assert event.stories_affected == 5

    def test_notify_sync_failed(self):
        """Test notify_sync_failed convenience method."""
        manager = NotificationManager()
        mock_provider = MagicMock()
        mock_provider.name = "Mock"
        mock_provider.send = MagicMock(return_value=True)
        manager.providers = [mock_provider]

        manager.notify_sync_failed("PROJ-123", "Connection error")

        mock_provider.send.assert_called_once()
        event = mock_provider.send.call_args[0][0]
        assert event.notification_type == NotificationType.SYNC_FAILED
        assert event.error == "Connection error"


class TestCreateNotificationManager:
    """Tests for create_notification_manager function."""

    def test_create_with_defaults(self):
        """Test creating manager with defaults."""
        manager = create_notification_manager()

        assert manager.config.enabled is True
        assert len(manager.providers) == 0

    def test_create_with_webhooks(self):
        """Test creating manager with webhooks."""
        manager = create_notification_manager(
            slack_webhook="https://hooks.slack.com/test",
            discord_webhook="https://discord.com/api/webhooks/test",
            notify_on_success=True,
            notify_on_failure=True,
        )

        assert len(manager.providers) == 2
        assert manager.config.notify_on_success is True
