"""
Tests for webhook receiver - receive Jira webhooks for reverse sync.
"""

import contextlib
import json
import time
from http.client import HTTPConnection
from unittest.mock import Mock

import pytest

from spectryn.application.webhook import (
    WebhookDisplay,
    WebhookEvent,
    WebhookEventType,
    WebhookParser,
    WebhookServer,
    WebhookStats,
)


class TestWebhookEventType:
    """Tests for WebhookEventType enum."""

    def test_from_string_issue_created(self):
        """Test parsing issue created event."""
        result = WebhookEventType.from_string("jira:issue_created")
        assert result == WebhookEventType.ISSUE_CREATED

    def test_from_string_issue_updated(self):
        """Test parsing issue updated event."""
        result = WebhookEventType.from_string("jira:issue_updated")
        assert result == WebhookEventType.ISSUE_UPDATED

    def test_from_string_unknown(self):
        """Test parsing unknown event."""
        result = WebhookEventType.from_string("unknown_event")
        assert result == WebhookEventType.UNKNOWN


class TestWebhookEvent:
    """Tests for WebhookEvent dataclass."""

    def test_str(self):
        """Test string representation."""
        event = WebhookEvent(
            event_type=WebhookEventType.ISSUE_UPDATED,
            issue_key="PROJ-123",
        )

        result = str(event)
        assert "issue_updated" in result
        assert "PROJ-123" in result

    def test_is_issue_event(self):
        """Test is_issue_event property."""
        issue_event = WebhookEvent(event_type=WebhookEventType.ISSUE_UPDATED)
        assert issue_event.is_issue_event

        comment_event = WebhookEvent(event_type=WebhookEventType.COMMENT_CREATED)
        assert not comment_event.is_issue_event


class TestWebhookStats:
    """Tests for WebhookStats dataclass."""

    def test_initial_state(self):
        """Test initial state."""
        stats = WebhookStats()

        assert stats.requests_received == 0
        assert stats.events_processed == 0
        assert stats.syncs_triggered == 0

    def test_uptime_formatted(self):
        """Test uptime formatting."""
        stats = WebhookStats()
        formatted = stats.uptime_formatted

        assert "s" in formatted


class TestWebhookParser:
    """Tests for WebhookParser class."""

    def test_parse_issue_created(self):
        """Test parsing issue created event."""
        parser = WebhookParser()

        payload = {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "key": "PROJ-123",
                "id": "10001",
                "fields": {
                    "project": {"key": "PROJ"},
                    "issuetype": {"name": "Story"},
                },
            },
            "user": {
                "displayName": "John Doe",
            },
        }

        event = parser.parse(payload)

        assert event.event_type == WebhookEventType.ISSUE_CREATED
        assert event.issue_key == "PROJ-123"
        assert event.project_key == "PROJ"
        assert event.user == "John Doe"

    def test_parse_issue_updated_with_changelog(self):
        """Test parsing issue updated event with changelog."""
        parser = WebhookParser()

        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-123",
                "fields": {
                    "project": {"key": "PROJ"},
                },
            },
            "changelog": {
                "items": [
                    {
                        "field": "status",
                        "fromString": "Open",
                        "toString": "In Progress",
                    },
                ],
            },
        }

        event = parser.parse(payload)

        assert event.event_type == WebhookEventType.ISSUE_UPDATED
        assert len(event.changelog) == 1
        assert event.changelog[0]["field"] == "status"
        assert event.changelog[0]["to"] == "In Progress"

    def test_parse_with_parent_epic(self):
        """Test extracting epic from parent field."""
        parser = WebhookParser()

        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-124",
                "fields": {
                    "project": {"key": "PROJ"},
                    "parent": {
                        "key": "PROJ-100",
                        "fields": {
                            "issuetype": {"name": "Epic"},
                        },
                    },
                },
            },
        }

        event = parser.parse(payload)

        assert event.epic_key == "PROJ-100"

    def test_parse_empty_payload(self):
        """Test parsing empty payload."""
        parser = WebhookParser()

        event = parser.parse({})

        assert event.event_type == WebhookEventType.UNKNOWN
        assert event.issue_key is None


class TestWebhookServer:
    """Tests for WebhookServer class."""

    @pytest.fixture
    def mock_reverse_sync(self):
        """Create mock reverse sync orchestrator."""
        sync = Mock()
        sync.pull.return_value = Mock(
            success=True,
            stories_pulled=2,
            errors=[],
        )
        return sync

    @pytest.fixture
    def webhook_server(self, mock_reverse_sync):
        """Create a webhook server that is automatically cleaned up."""
        servers = []

        def _create_server(**kwargs):
            defaults = {
                "reverse_sync": mock_reverse_sync,
                "host": "localhost",
            }
            defaults.update(kwargs)
            server = WebhookServer(**defaults)
            servers.append(server)
            return server

        yield _create_server

        # Cleanup all created servers
        for server in servers:
            with contextlib.suppress(Exception):
                server.stop()

    def test_initialization(self, webhook_server):
        """Test server initialization."""
        server = webhook_server(
            port=9999,
            epic_key="PROJ-100",
            output_path="/test.md",
        )

        assert server.host == "localhost"
        assert server.port == 9999
        assert server.epic_key == "PROJ-100"

    def test_start_async_and_stop(self, webhook_server):
        """Test starting and stopping server."""
        server = webhook_server(port=9998)

        server.start_async()
        assert server._running

        time.sleep(0.2)
        server.stop()

        assert not server._running

    def test_handle_webhook_triggers_sync(self, webhook_server):
        """Test that handling webhook triggers sync."""
        server = webhook_server(
            port=9997,
            epic_key="PROJ-100",
            output_path="/test.md",
            debounce_seconds=0.1,
        )

        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-123",
                "fields": {
                    "project": {"key": "PROJ"},
                    "parent": {
                        "key": "PROJ-100",
                        "fields": {"issuetype": {"name": "Epic"}},
                    },
                },
            },
        }

        server.handle_webhook(payload)

        # Wait for potential async sync
        time.sleep(0.3)

        assert server.stats.events_processed == 1
        assert server.stats.syncs_triggered >= 1

    def test_should_sync_filters_by_epic(self, webhook_server):
        """Test that should_sync filters by epic key."""
        server = webhook_server(
            epic_key="PROJ-100",
            output_path="/test.md",
        )

        # Event for our epic
        matching_event = WebhookEvent(
            event_type=WebhookEventType.ISSUE_UPDATED,
            issue_key="PROJ-123",
            epic_key="PROJ-100",
        )
        assert server._should_sync(matching_event)

        # Event for different epic
        different_event = WebhookEvent(
            event_type=WebhookEventType.ISSUE_UPDATED,
            issue_key="PROJ-456",
            epic_key="PROJ-200",
        )
        assert not server._should_sync(different_event)

    def test_should_sync_ignores_non_issue_events(self, webhook_server):
        """Test that should_sync ignores non-issue events."""
        server = webhook_server(
            epic_key="PROJ-100",
            output_path="/test.md",
        )

        comment_event = WebhookEvent(
            event_type=WebhookEventType.COMMENT_CREATED,
            issue_key="PROJ-123",
        )
        assert not server._should_sync(comment_event)

    def test_get_status(self, webhook_server):
        """Test getting server status."""
        server = webhook_server(
            port=9996,
            epic_key="PROJ-100",
        )

        status = server.get_status()

        assert status["host"] == "localhost"
        assert status["port"] == 9996
        assert status["epic_key"] == "PROJ-100"
        assert "uptime" in status


class TestWebhookServerHTTP:
    """Integration tests for webhook HTTP endpoints."""

    @pytest.fixture
    def mock_reverse_sync(self):
        """Create mock reverse sync orchestrator."""
        sync = Mock()
        sync.pull.return_value = Mock(
            success=True,
            stories_pulled=2,
            errors=[],
        )
        return sync

    @pytest.fixture
    def webhook_server(self, mock_reverse_sync):
        """Create a webhook server that is automatically cleaned up."""
        servers = []

        def _create_server(**kwargs):
            defaults = {
                "reverse_sync": mock_reverse_sync,
                "host": "localhost",
            }
            defaults.update(kwargs)
            server = WebhookServer(**defaults)
            servers.append(server)
            return server

        yield _create_server

        # Cleanup all created servers
        for server in servers:
            with contextlib.suppress(Exception):
                server.stop()

    def test_health_endpoint(self, webhook_server):
        """Test health check endpoint."""
        server = webhook_server(port=9995)

        server.start_async()
        time.sleep(0.2)

        conn = HTTPConnection("localhost", 9995)
        conn.request("GET", "/health")
        response = conn.getresponse()

        assert response.status == 200
        body = json.loads(response.read().decode())
        assert body["status"] == "ok"

    def test_status_endpoint(self, webhook_server):
        """Test status endpoint."""
        server = webhook_server(port=9994)

        server.start_async()
        time.sleep(0.2)

        conn = HTTPConnection("localhost", 9994)
        conn.request("GET", "/status")
        response = conn.getresponse()

        assert response.status == 200
        body = json.loads(response.read().decode())
        assert body["status"] == "running"

    def test_webhook_endpoint(self, webhook_server):
        """Test webhook POST endpoint."""
        server = webhook_server(
            port=9993,
            epic_key="PROJ-100",
            output_path="/test.md",
        )

        server.start_async()
        time.sleep(0.2)

        payload = json.dumps(
            {
                "webhookEvent": "jira:issue_updated",
                "issue": {
                    "key": "PROJ-123",
                    "fields": {"project": {"key": "PROJ"}},
                },
            }
        )

        conn = HTTPConnection("localhost", 9993)
        conn.request(
            "POST",
            "/",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()

        assert response.status == 200
        body = json.loads(response.read().decode())
        assert body["status"] == "accepted"

    def test_invalid_json(self, webhook_server):
        """Test handling of invalid JSON."""
        server = webhook_server(port=9992)

        server.start_async()
        time.sleep(0.2)

        conn = HTTPConnection("localhost", 9992)
        conn.request(
            "POST",
            "/",
            body="not valid json",
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()

        assert response.status == 400


class TestWebhookDisplay:
    """Tests for WebhookDisplay class."""

    def test_show_start(self, capsys):
        """Test showing start message."""
        display = WebhookDisplay(color=False)
        display.show_start("localhost", 8080, "PROJ-100")

        captured = capsys.readouterr()
        assert "Webhook Server" in captured.out
        assert "localhost" in captured.out
        assert "8080" in captured.out
        assert "PROJ-100" in captured.out

    def test_show_start_quiet(self, capsys):
        """Test quiet mode suppresses output."""
        display = WebhookDisplay(quiet=True)
        display.show_start("localhost", 8080, "PROJ-100")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_show_event(self, capsys):
        """Test showing event."""
        display = WebhookDisplay(color=False)
        event = WebhookEvent(
            event_type=WebhookEventType.ISSUE_UPDATED,
            issue_key="PROJ-123",
        )
        display.show_event(event)

        captured = capsys.readouterr()
        assert "PROJ-123" in captured.out

    def test_show_sync_complete_success(self, capsys):
        """Test showing successful sync."""
        display = WebhookDisplay(color=False)
        result = Mock(success=True, stories_pulled=5)
        display.show_sync_complete(result)

        captured = capsys.readouterr()
        assert "Sync complete" in captured.out

    def test_show_sync_complete_failure(self, capsys):
        """Test showing failed sync."""
        display = WebhookDisplay(color=False)
        result = Mock(success=False, errors=["Error 1"])
        display.show_sync_complete(result)

        captured = capsys.readouterr()
        assert "Sync failed" in captured.out

    def test_show_stop(self, capsys):
        """Test showing stop message."""
        display = WebhookDisplay(color=False)
        stats = WebhookStats()
        stats.requests_received = 10
        stats.events_processed = 8
        stats.syncs_successful = 5
        stats.syncs_failed = 1

        display.show_stop(stats)

        captured = capsys.readouterr()
        assert "Webhook Server Stopped" in captured.out
        assert "10" in captured.out


class TestDebouncing:
    """Tests for webhook debouncing."""

    @pytest.fixture
    def mock_reverse_sync(self):
        """Create mock reverse sync orchestrator."""
        sync = Mock()
        sync.pull.return_value = Mock(
            success=True,
            stories_pulled=2,
            errors=[],
        )
        return sync

    def test_debounce_prevents_rapid_syncs(self, mock_reverse_sync):
        """Test that debouncing prevents rapid syncs."""
        server = WebhookServer(
            reverse_sync=mock_reverse_sync,
            epic_key="PROJ-100",
            output_path="/test.md",
            debounce_seconds=1.0,
        )

        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "PROJ-123",
                "fields": {
                    "project": {"key": "PROJ"},
                    "parent": {
                        "key": "PROJ-100",
                        "fields": {"issuetype": {"name": "Epic"}},
                    },
                },
            },
        }

        # Send multiple webhooks rapidly
        for _ in range(5):
            server.handle_webhook(payload)

        # Wait a bit for any syncs to complete
        time.sleep(0.5)

        # Should have triggered fewer syncs than events due to debouncing
        assert server.stats.events_processed == 5
        assert server.stats.syncs_triggered < 5
