"""Tests for multi-tracker webhook functionality."""

import hashlib
import hmac
import json

import pytest

from spectryn.application.webhook_multi import (
    AzureDevOpsWebhookParser,
    GitHubWebhookParser,
    GitLabWebhookParser,
    JiraWebhookParser,
    LinearWebhookParser,
    MultiTrackerEvent,
    MultiTrackerStats,
    MultiTrackerWebhookConfig,
    MultiTrackerWebhookServer,
    TrackerType,
    WebhookEventCategory,
    create_multi_tracker_server,
)


class TestTrackerType:
    """Tests for TrackerType enum."""

    def test_all_types_exist(self):
        """Test all tracker types are defined."""
        assert TrackerType.JIRA.value == "jira"
        assert TrackerType.GITHUB.value == "github"
        assert TrackerType.GITLAB.value == "gitlab"
        assert TrackerType.AZURE.value == "azure"
        assert TrackerType.LINEAR.value == "linear"


class TestWebhookEventCategory:
    """Tests for WebhookEventCategory enum."""

    def test_all_categories_exist(self):
        """Test all event categories are defined."""
        assert WebhookEventCategory.ISSUE_CREATED.value == "issue_created"
        assert WebhookEventCategory.ISSUE_UPDATED.value == "issue_updated"
        assert WebhookEventCategory.COMMENT_CREATED.value == "comment_created"
        assert WebhookEventCategory.LABEL_ADDED.value == "label_added"


class TestMultiTrackerEvent:
    """Tests for MultiTrackerEvent dataclass."""

    def test_create_basic(self):
        """Test creating a basic event."""
        event = MultiTrackerEvent(
            tracker=TrackerType.GITHUB,
            category=WebhookEventCategory.ISSUE_CREATED,
            issue_key="#123",
            issue_title="Test Issue",
        )
        assert event.tracker == TrackerType.GITHUB
        assert event.issue_key == "#123"

    def test_str_representation(self):
        """Test string representation."""
        event = MultiTrackerEvent(
            tracker=TrackerType.JIRA,
            category=WebhookEventCategory.ISSUE_UPDATED,
            issue_key="PROJ-123",
        )
        assert "jira" in str(event)
        assert "issue_updated" in str(event)
        assert "PROJ-123" in str(event)


class TestJiraWebhookParser:
    """Tests for Jira webhook parser."""

    @pytest.fixture
    def parser(self):
        return JiraWebhookParser()

    def test_can_parse_jira_payload(self, parser):
        """Test recognizing Jira payloads."""
        payload = {"webhookEvent": "jira:issue_created"}
        assert parser.can_parse(payload, {}) is True

    def test_cannot_parse_github_payload(self, parser):
        """Test not matching GitHub payloads."""
        payload = {"action": "opened", "issue": {}}
        headers = {"X-GitHub-Event": "issues"}
        assert parser.can_parse(payload, headers) is False

    def test_parse_issue_created(self, parser):
        """Test parsing issue created event."""
        payload = {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "key": "PROJ-123",
                "id": "10001",
                "fields": {
                    "summary": "Test Issue",
                    "project": {"key": "PROJ"},
                },
            },
            "user": {"displayName": "John Doe"},
        }
        event = parser.parse(payload, {})

        assert event.tracker == TrackerType.JIRA
        assert event.category == WebhookEventCategory.ISSUE_CREATED
        assert event.issue_key == "PROJ-123"
        assert event.issue_title == "Test Issue"
        assert event.actor == "John Doe"

    def test_parse_issue_updated_with_changelog(self, parser):
        """Test parsing issue updated with changelog."""
        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {"key": "PROJ-456", "id": "10002", "fields": {}},
            "changelog": {
                "items": [{"field": "status", "fromString": "To Do", "toString": "In Progress"}]
            },
            "user": {},
        }
        event = parser.parse(payload, {})

        assert event.category == WebhookEventCategory.ISSUE_UPDATED
        assert len(event.changes) == 1
        assert event.changes[0]["field"] == "status"

    def test_verify_signature_no_secret(self, parser):
        """Test signature verification without secret."""
        assert parser.verify_signature(b"body", {}, None) is True

    def test_verify_signature_valid(self, parser):
        """Test signature verification with valid signature."""
        secret = "mysecret"
        body = b'{"test": "payload"}'
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        headers = {"X-Atlassian-Webhook-Signature": expected_sig}
        assert parser.verify_signature(body, headers, secret) is True

    def test_verify_signature_invalid(self, parser):
        """Test signature verification with invalid signature."""
        headers = {"X-Atlassian-Webhook-Signature": "invalid"}
        assert parser.verify_signature(b"body", headers, "secret") is False


class TestGitHubWebhookParser:
    """Tests for GitHub webhook parser."""

    @pytest.fixture
    def parser(self):
        return GitHubWebhookParser()

    def test_can_parse_github_payload(self, parser):
        """Test recognizing GitHub payloads."""
        payload = {"action": "opened", "issue": {}, "repository": {}}
        headers = {"X-GitHub-Event": "issues"}
        assert parser.can_parse(payload, headers) is True

    def test_parse_issue_opened(self, parser):
        """Test parsing issue opened event."""
        payload = {
            "action": "opened",
            "issue": {
                "number": 123,
                "id": 99999,
                "title": "Bug: Something broken",
                "html_url": "https://github.com/org/repo/issues/123",
            },
            "repository": {"full_name": "org/repo"},
            "sender": {"login": "octocat"},
        }
        headers = {"X-GitHub-Event": "issues"}
        event = parser.parse(payload, headers)

        assert event.tracker == TrackerType.GITHUB
        assert event.category == WebhookEventCategory.ISSUE_CREATED
        assert event.issue_key == "#123"
        assert event.repository == "org/repo"
        assert event.actor == "octocat"

    def test_parse_label_event(self, parser):
        """Test parsing label added event."""
        payload = {
            "action": "labeled",
            "issue": {"number": 456, "id": 88888, "title": "Feature"},
            "label": {"name": "enhancement"},
            "repository": {"full_name": "org/repo"},
            "sender": {"login": "user"},
        }
        headers = {"X-GitHub-Event": "issues"}
        event = parser.parse(payload, headers)

        assert event.category == WebhookEventCategory.LABEL_ADDED
        assert len(event.changes) == 1
        assert event.changes[0]["label"] == "enhancement"

    def test_verify_signature_valid(self, parser):
        """Test GitHub signature verification."""
        secret = "github_secret"
        body = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        headers = {"X-Hub-Signature-256": sig}
        assert parser.verify_signature(body, headers, secret) is True


class TestGitLabWebhookParser:
    """Tests for GitLab webhook parser."""

    @pytest.fixture
    def parser(self):
        return GitLabWebhookParser()

    def test_can_parse_gitlab_payload(self, parser):
        """Test recognizing GitLab payloads."""
        payload = {"object_kind": "issue"}
        assert parser.can_parse(payload, {}) is True

    def test_parse_issue_created(self, parser):
        """Test parsing issue created event."""
        payload = {
            "object_kind": "issue",
            "object_attributes": {
                "action": "open",
                "iid": 42,
                "id": 12345,
                "title": "New Feature",
                "url": "https://gitlab.com/org/repo/-/issues/42",
            },
            "project": {"path_with_namespace": "org/repo"},
            "user": {"name": "Jane Doe"},
        }
        event = parser.parse(payload, {})

        assert event.tracker == TrackerType.GITLAB
        assert event.category == WebhookEventCategory.ISSUE_CREATED
        assert event.issue_key == "#42"
        assert event.repository == "org/repo"

    def test_verify_token_valid(self, parser):
        """Test GitLab token verification."""
        headers = {"X-Gitlab-Token": "my_token"}
        assert parser.verify_signature(b"", headers, "my_token") is True

    def test_verify_token_invalid(self, parser):
        """Test GitLab token verification failure."""
        headers = {"X-Gitlab-Token": "wrong_token"}
        assert parser.verify_signature(b"", headers, "my_token") is False


class TestAzureDevOpsWebhookParser:
    """Tests for Azure DevOps webhook parser."""

    @pytest.fixture
    def parser(self):
        return AzureDevOpsWebhookParser()

    def test_can_parse_azure_payload(self, parser):
        """Test recognizing Azure DevOps payloads."""
        payload = {"eventType": "workitem.created", "publisherId": "tfs"}
        assert parser.can_parse(payload, {}) is True

    def test_parse_workitem_created(self, parser):
        """Test parsing work item created event."""
        payload = {
            "eventType": "workitem.created",
            "publisherId": "tfs",
            "resource": {
                "id": 123,
                "fields": {
                    "System.Title": "New Work Item",
                    "System.TeamProject": "MyProject",
                },
            },
            "createdBy": {"displayName": "Azure User"},
        }
        event = parser.parse(payload, {})

        assert event.tracker == TrackerType.AZURE
        assert event.category == WebhookEventCategory.ISSUE_CREATED
        assert event.issue_key == "123"
        assert event.project_key == "MyProject"


class TestLinearWebhookParser:
    """Tests for Linear webhook parser."""

    @pytest.fixture
    def parser(self):
        return LinearWebhookParser()

    def test_can_parse_linear_payload(self, parser):
        """Test recognizing Linear payloads."""
        payload = {"type": "Issue", "action": "create", "data": {}}
        assert parser.can_parse(payload, {}) is True

    def test_parse_issue_created(self, parser):
        """Test parsing issue created event."""
        payload = {
            "type": "Issue",
            "action": "create",
            "data": {
                "id": "abc123",
                "identifier": "TEAM-123",
                "title": "New Feature",
                "url": "https://linear.app/team/issue/TEAM-123",
                "team": {"key": "TEAM"},
            },
            "actor": {"name": "Linear User"},
        }
        event = parser.parse(payload, {})

        assert event.tracker == TrackerType.LINEAR
        assert event.category == WebhookEventCategory.ISSUE_CREATED
        assert event.issue_key == "TEAM-123"
        assert event.project_key == "TEAM"


class TestMultiTrackerWebhookConfig:
    """Tests for MultiTrackerWebhookConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = MultiTrackerWebhookConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.debounce_seconds == 5.0
        assert config.jira_secret is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = MultiTrackerWebhookConfig(
            port=9000,
            github_secret="gh_secret",
            epic_key="PROJ-100",
        )
        assert config.port == 9000
        assert config.github_secret == "gh_secret"
        assert config.epic_key == "PROJ-100"


class TestMultiTrackerStats:
    """Tests for MultiTrackerStats."""

    def test_initial_values(self):
        """Test initial statistics values."""
        stats = MultiTrackerStats()
        assert stats.requests_received == 0
        assert stats.total_events == 0

    def test_record_event(self):
        """Test recording an event."""
        stats = MultiTrackerStats()
        event = MultiTrackerEvent(
            tracker=TrackerType.GITHUB,
            category=WebhookEventCategory.ISSUE_CREATED,
        )

        stats.record_event(event)

        assert stats.events_by_tracker["github"] == 1
        assert stats.events_by_category["issue_created"] == 1
        assert stats.total_events == 1

    def test_uptime_formatted(self):
        """Test uptime formatting."""
        stats = MultiTrackerStats()
        # Just check it returns a string
        assert isinstance(stats.uptime_formatted, str)


class TestMultiTrackerWebhookServer:
    """Tests for MultiTrackerWebhookServer."""

    def test_create_server(self):
        """Test creating a server."""
        config = MultiTrackerWebhookConfig()
        server = MultiTrackerWebhookServer(config)

        assert len(server.parsers) == 5  # All parsers loaded
        assert not server._running

    def test_find_parser_jira(self):
        """Test finding Jira parser."""
        config = MultiTrackerWebhookConfig()
        server = MultiTrackerWebhookServer(config)

        payload = {"webhookEvent": "jira:issue_created"}
        parser = server._find_parser(payload, {})

        assert parser is not None
        assert parser.tracker_type == TrackerType.JIRA

    def test_find_parser_github(self):
        """Test finding GitHub parser."""
        config = MultiTrackerWebhookConfig()
        server = MultiTrackerWebhookServer(config)

        payload = {"action": "opened", "issue": {}, "repository": {}}
        headers = {"X-GitHub-Event": "issues"}
        parser = server._find_parser(payload, headers)

        assert parser is not None
        assert parser.tracker_type == TrackerType.GITHUB

    def test_should_sync_unknown_event(self):
        """Test should_sync for unknown event."""
        config = MultiTrackerWebhookConfig()
        server = MultiTrackerWebhookServer(config)

        event = MultiTrackerEvent(
            tracker=TrackerType.JIRA,
            category=WebhookEventCategory.UNKNOWN,
        )

        assert server._should_sync(event) is False

    def test_should_sync_with_epic_filter(self):
        """Test should_sync with epic filter."""
        config = MultiTrackerWebhookConfig(epic_key="PROJ-100")
        server = MultiTrackerWebhookServer(config)

        # Event for different epic
        event1 = MultiTrackerEvent(
            tracker=TrackerType.JIRA,
            category=WebhookEventCategory.ISSUE_UPDATED,
            epic_key="PROJ-200",
        )
        assert server._should_sync(event1) is False

        # Event for our epic
        event2 = MultiTrackerEvent(
            tracker=TrackerType.JIRA,
            category=WebhookEventCategory.ISSUE_UPDATED,
            epic_key="PROJ-100",
        )
        assert server._should_sync(event2) is True

    def test_get_status(self):
        """Test getting server status."""
        config = MultiTrackerWebhookConfig(epic_key="PROJ-123")
        server = MultiTrackerWebhookServer(config)

        status = server.get_status()

        assert status["running"] is False
        assert status["epic_key"] == "PROJ-123"
        assert "uptime" in status


class TestCreateMultiTrackerServer:
    """Tests for create_multi_tracker_server function."""

    def test_create_with_defaults(self):
        """Test creating server with defaults."""
        server = create_multi_tracker_server()

        assert server.config.host == "0.0.0.0"
        assert server.config.port == 8080

    def test_create_with_secrets(self):
        """Test creating server with secrets."""
        server = create_multi_tracker_server(
            port=9000,
            github_secret="gh_secret",
            linear_secret="linear_secret",
            epic_key="PROJ-100",
        )

        assert server.config.port == 9000
        assert server.config.github_secret == "gh_secret"
        assert server.config.linear_secret == "linear_secret"
        assert server.config.epic_key == "PROJ-100"
