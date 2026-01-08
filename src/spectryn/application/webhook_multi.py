"""
Multi-Tracker Webhook Support - Listen for webhooks from multiple trackers.

This module extends webhook support to handle events from:
- Jira (existing)
- GitHub Issues
- GitLab Issues
- Azure DevOps
- Linear

Each tracker has its own payload format and signature verification.
"""

import hashlib
import hmac
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .sync.reverse_sync import PullResult, ReverseSyncOrchestrator

logger = logging.getLogger(__name__)


class TrackerType(Enum):
    """Supported tracker types for webhooks."""

    JIRA = "jira"
    GITHUB = "github"
    GITLAB = "gitlab"
    AZURE = "azure"
    LINEAR = "linear"
    UNKNOWN = "unknown"


class WebhookEventCategory(Enum):
    """Categories of webhook events."""

    ISSUE_CREATED = "issue_created"
    ISSUE_UPDATED = "issue_updated"
    ISSUE_DELETED = "issue_deleted"
    ISSUE_CLOSED = "issue_closed"
    ISSUE_REOPENED = "issue_reopened"
    COMMENT_CREATED = "comment_created"
    COMMENT_UPDATED = "comment_updated"
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"
    ASSIGNEE_CHANGED = "assignee_changed"
    MILESTONE_CHANGED = "milestone_changed"
    SPRINT_CHANGED = "sprint_changed"
    UNKNOWN = "unknown"


@dataclass
class MultiTrackerEvent:
    """Normalized webhook event from any tracker."""

    tracker: TrackerType
    category: WebhookEventCategory
    timestamp: datetime = field(default_factory=datetime.now)

    # Issue details
    issue_key: str | None = None
    issue_id: str | None = None
    issue_title: str | None = None
    issue_url: str | None = None

    # Context
    project_key: str | None = None
    epic_key: str | None = None
    repository: str | None = None

    # Who and what changed
    actor: str | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)

    # Raw payload for debugging
    raw_payload: dict = field(default_factory=dict)

    def __str__(self) -> str:
        source = f"{self.tracker.value}"
        return f"[{source}] {self.category.value}: {self.issue_key or self.issue_id or 'N/A'}"


class WebhookPayloadParser(ABC):
    """Abstract base for tracker-specific webhook parsers."""

    @property
    @abstractmethod
    def tracker_type(self) -> TrackerType:
        """Return the tracker type this parser handles."""
        ...

    @abstractmethod
    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check if this parser can handle the payload."""
        ...

    @abstractmethod
    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse the payload into a normalized event."""
        ...

    @abstractmethod
    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Verify the webhook signature."""
        ...


class JiraWebhookParser(WebhookPayloadParser):
    """Parser for Jira webhook payloads."""

    def __init__(self, epic_link_field: str = "customfield_10014"):
        self.epic_link_field = epic_link_field

    @property
    def tracker_type(self) -> TrackerType:
        return TrackerType.JIRA

    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check for Jira-specific fields."""
        return "webhookEvent" in payload and payload.get("webhookEvent", "").startswith("jira:")

    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse Jira webhook payload."""
        event_type = payload.get("webhookEvent", "")
        category = self._map_event_type(event_type)

        issue = payload.get("issue", {})
        fields = issue.get("fields", {})
        user = payload.get("user", {})

        # Extract changes
        changes = []
        changelog = payload.get("changelog", {})
        for item in changelog.get("items", []):
            changes.append(
                {
                    "field": item.get("field"),
                    "from": item.get("fromString"),
                    "to": item.get("toString"),
                }
            )

        return MultiTrackerEvent(
            tracker=TrackerType.JIRA,
            category=category,
            issue_key=issue.get("key"),
            issue_id=issue.get("id"),
            issue_title=fields.get("summary"),
            project_key=fields.get("project", {}).get("key"),
            epic_key=self._extract_epic_key(fields),
            actor=user.get("displayName") or user.get("name"),
            changes=changes,
            raw_payload=payload,
        )

    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Verify Jira webhook signature."""
        if not secret:
            return True

        signature = headers.get("X-Atlassian-Webhook-Signature", "")
        if not signature:
            return False

        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def _map_event_type(self, event_type: str) -> WebhookEventCategory:
        """Map Jira event type to category."""
        mapping = {
            "jira:issue_created": WebhookEventCategory.ISSUE_CREATED,
            "jira:issue_updated": WebhookEventCategory.ISSUE_UPDATED,
            "jira:issue_deleted": WebhookEventCategory.ISSUE_DELETED,
            "comment_created": WebhookEventCategory.COMMENT_CREATED,
            "comment_updated": WebhookEventCategory.COMMENT_UPDATED,
        }
        return mapping.get(event_type, WebhookEventCategory.UNKNOWN)

    def _extract_epic_key(self, fields: dict) -> str | None:
        """Extract epic key from issue fields."""
        parent = fields.get("parent", {})
        if parent:
            parent_type = parent.get("fields", {}).get("issuetype", {}).get("name", "")
            if parent_type.lower() == "epic":
                key = parent.get("key")
                return key if isinstance(key, str) else None

        epic_link = fields.get(self.epic_link_field)
        return epic_link if isinstance(epic_link, str) else None


class GitHubWebhookParser(WebhookPayloadParser):
    """Parser for GitHub Issues webhook payloads."""

    @property
    def tracker_type(self) -> TrackerType:
        return TrackerType.GITHUB

    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check for GitHub-specific headers."""
        return "X-GitHub-Event" in headers or ("issue" in payload and "repository" in payload)

    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse GitHub webhook payload."""
        event_header = headers.get("X-GitHub-Event", "")
        action = payload.get("action", "")
        category = self._map_event(event_header, action)

        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})

        # Build changes from label/assignee events
        changes = []
        if "label" in payload:
            label = payload["label"]
            changes.append(
                {
                    "field": "labels",
                    "action": action,
                    "label": label.get("name"),
                }
            )

        return MultiTrackerEvent(
            tracker=TrackerType.GITHUB,
            category=category,
            issue_key=f"#{issue.get('number')}",
            issue_id=str(issue.get("id", "")),
            issue_title=issue.get("title"),
            issue_url=issue.get("html_url"),
            repository=repo.get("full_name"),
            actor=sender.get("login"),
            changes=changes,
            raw_payload=payload,
        )

    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Verify GitHub webhook signature."""
        if not secret:
            return True

        signature = headers.get("X-Hub-Signature-256", "")
        if not signature or not signature.startswith("sha256="):
            return False

        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def _map_event(self, event: str, action: str) -> WebhookEventCategory:
        """Map GitHub event to category."""
        if event == "issues":
            action_map = {
                "opened": WebhookEventCategory.ISSUE_CREATED,
                "edited": WebhookEventCategory.ISSUE_UPDATED,
                "deleted": WebhookEventCategory.ISSUE_DELETED,
                "closed": WebhookEventCategory.ISSUE_CLOSED,
                "reopened": WebhookEventCategory.ISSUE_REOPENED,
                "labeled": WebhookEventCategory.LABEL_ADDED,
                "unlabeled": WebhookEventCategory.LABEL_REMOVED,
                "assigned": WebhookEventCategory.ASSIGNEE_CHANGED,
                "unassigned": WebhookEventCategory.ASSIGNEE_CHANGED,
                "milestoned": WebhookEventCategory.MILESTONE_CHANGED,
                "demilestoned": WebhookEventCategory.MILESTONE_CHANGED,
            }
            return action_map.get(action, WebhookEventCategory.ISSUE_UPDATED)
        if event == "issue_comment":
            if action == "created":
                return WebhookEventCategory.COMMENT_CREATED
            return WebhookEventCategory.COMMENT_UPDATED
        return WebhookEventCategory.UNKNOWN


class GitLabWebhookParser(WebhookPayloadParser):
    """Parser for GitLab Issues webhook payloads."""

    @property
    def tracker_type(self) -> TrackerType:
        return TrackerType.GITLAB

    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check for GitLab-specific fields."""
        return "object_kind" in payload and payload.get("object_kind") in (
            "issue",
            "note",
        )

    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse GitLab webhook payload."""
        object_kind = payload.get("object_kind", "")
        object_attrs = payload.get("object_attributes", {})
        project = payload.get("project", {})
        user = payload.get("user", {})

        category = self._map_event(object_kind, object_attrs.get("action", ""))

        # Extract changes
        changes = []
        if "changes" in payload:
            for field_name, change in payload["changes"].items():
                if isinstance(change, dict):
                    changes.append(
                        {
                            "field": field_name,
                            "from": change.get("previous"),
                            "to": change.get("current"),
                        }
                    )

        issue = payload.get("issue", object_attrs)
        return MultiTrackerEvent(
            tracker=TrackerType.GITLAB,
            category=category,
            issue_key=f"#{issue.get('iid')}",
            issue_id=str(issue.get("id", "")),
            issue_title=issue.get("title"),
            issue_url=issue.get("url"),
            repository=project.get("path_with_namespace"),
            actor=user.get("name") or user.get("username"),
            changes=changes,
            raw_payload=payload,
        )

    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Verify GitLab webhook token."""
        if not secret:
            return True

        token = headers.get("X-Gitlab-Token", "")
        return hmac.compare_digest(token, secret)

    def _map_event(self, object_kind: str, action: str) -> WebhookEventCategory:
        """Map GitLab event to category."""
        if object_kind == "issue":
            action_map = {
                "open": WebhookEventCategory.ISSUE_CREATED,
                "update": WebhookEventCategory.ISSUE_UPDATED,
                "close": WebhookEventCategory.ISSUE_CLOSED,
                "reopen": WebhookEventCategory.ISSUE_REOPENED,
            }
            return action_map.get(action, WebhookEventCategory.ISSUE_UPDATED)
        if object_kind == "note":
            return WebhookEventCategory.COMMENT_CREATED
        return WebhookEventCategory.UNKNOWN


class AzureDevOpsWebhookParser(WebhookPayloadParser):
    """Parser for Azure DevOps webhook payloads."""

    @property
    def tracker_type(self) -> TrackerType:
        return TrackerType.AZURE

    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check for Azure DevOps-specific fields."""
        return "eventType" in payload and payload.get("publisherId") == "tfs"

    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse Azure DevOps webhook payload."""
        event_type = payload.get("eventType", "")
        resource = payload.get("resource", {})
        category = self._map_event_type(event_type)

        # Work item details
        work_item = resource if "id" in resource else resource.get("workItem", {})
        fields = work_item.get("fields", {})

        return MultiTrackerEvent(
            tracker=TrackerType.AZURE,
            category=category,
            issue_key=str(work_item.get("id", "")),
            issue_id=str(work_item.get("id", "")),
            issue_title=fields.get("System.Title"),
            project_key=fields.get("System.TeamProject"),
            actor=payload.get("createdBy", {}).get("displayName"),
            raw_payload=payload,
        )

    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Azure DevOps uses Basic Auth for webhooks, not signatures."""
        # In practice, Azure DevOps webhooks are typically secured via
        # service hooks with Basic Auth or OAuth
        return True

    def _map_event_type(self, event_type: str) -> WebhookEventCategory:
        """Map Azure DevOps event type to category."""
        mapping = {
            "workitem.created": WebhookEventCategory.ISSUE_CREATED,
            "workitem.updated": WebhookEventCategory.ISSUE_UPDATED,
            "workitem.deleted": WebhookEventCategory.ISSUE_DELETED,
            "workitem.commented": WebhookEventCategory.COMMENT_CREATED,
        }
        return mapping.get(event_type, WebhookEventCategory.UNKNOWN)


class LinearWebhookParser(WebhookPayloadParser):
    """Parser for Linear webhook payloads."""

    @property
    def tracker_type(self) -> TrackerType:
        return TrackerType.LINEAR

    def can_parse(self, payload: dict, headers: dict[str, str]) -> bool:
        """Check for Linear-specific fields."""
        return "type" in payload and "action" in payload and "data" in payload

    def parse(self, payload: dict, headers: dict[str, str]) -> MultiTrackerEvent:
        """Parse Linear webhook payload."""
        payload_type = payload.get("type", "")
        action = payload.get("action", "")
        data = payload.get("data", {})

        category = self._map_event(payload_type, action)

        return MultiTrackerEvent(
            tracker=TrackerType.LINEAR,
            category=category,
            issue_key=data.get("identifier"),
            issue_id=data.get("id"),
            issue_title=data.get("title"),
            issue_url=data.get("url"),
            project_key=data.get("team", {}).get("key"),
            actor=payload.get("actor", {}).get("name"),
            raw_payload=payload,
        )

    def verify_signature(self, body: bytes, headers: dict[str, str], secret: str | None) -> bool:
        """Verify Linear webhook signature."""
        if not secret:
            return True

        signature = headers.get("Linear-Signature", "")
        if not signature:
            return False

        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    def _map_event(self, payload_type: str, action: str) -> WebhookEventCategory:
        """Map Linear event to category."""
        if payload_type == "Issue":
            action_map = {
                "create": WebhookEventCategory.ISSUE_CREATED,
                "update": WebhookEventCategory.ISSUE_UPDATED,
                "remove": WebhookEventCategory.ISSUE_DELETED,
            }
            return action_map.get(action, WebhookEventCategory.ISSUE_UPDATED)
        if payload_type == "Comment":
            if action == "create":
                return WebhookEventCategory.COMMENT_CREATED
            return WebhookEventCategory.COMMENT_UPDATED
        return WebhookEventCategory.UNKNOWN


@dataclass
class MultiTrackerWebhookConfig:
    """Configuration for multi-tracker webhook server."""

    host: str = "0.0.0.0"
    port: int = 8080

    # Secrets per tracker
    jira_secret: str | None = None
    github_secret: str | None = None
    gitlab_secret: str | None = None
    azure_secret: str | None = None
    linear_secret: str | None = None

    # Filtering
    epic_key: str | None = None
    project_filter: str | None = None

    # Behavior
    debounce_seconds: float = 5.0
    dry_run: bool = True


@dataclass
class MultiTrackerStats:
    """Statistics for multi-tracker webhook server."""

    started_at: datetime = field(default_factory=datetime.now)
    requests_received: int = 0
    events_by_tracker: dict[str, int] = field(default_factory=dict)
    events_by_category: dict[str, int] = field(default_factory=dict)
    syncs_triggered: int = 0
    syncs_successful: int = 0
    syncs_failed: int = 0

    def record_event(self, event: MultiTrackerEvent) -> None:
        """Record an event."""
        tracker = event.tracker.value
        category = event.category.value

        self.events_by_tracker[tracker] = self.events_by_tracker.get(tracker, 0) + 1
        self.events_by_category[category] = self.events_by_category.get(category, 0) + 1

    @property
    def total_events(self) -> int:
        return sum(self.events_by_tracker.values())

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def uptime_formatted(self) -> str:
        seconds = int(self.uptime_seconds)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


class MultiTrackerWebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for multi-tracker webhooks."""

    webhook_server: "MultiTrackerWebhookServer | None" = None

    def log_message(self, fmt: str, *args: Any) -> None:
        """Override to use our logger."""
        logger.debug(f"HTTP: {fmt % args}")

    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health":
            self._send_response(200, {"status": "ok", "service": "spectra-webhook-multi"})
        elif self.path == "/status":
            if self.webhook_server:
                stats = self.webhook_server.stats
                self._send_response(
                    200,
                    {
                        "status": "running",
                        "uptime": stats.uptime_formatted,
                        "requests": stats.requests_received,
                        "total_events": stats.total_events,
                        "events_by_tracker": stats.events_by_tracker,
                        "syncs": {
                            "triggered": stats.syncs_triggered,
                            "successful": stats.syncs_successful,
                            "failed": stats.syncs_failed,
                        },
                    },
                )
            else:
                self._send_response(200, {"status": "running"})
        else:
            self._send_response(404, {"error": "Not found"})

    def do_POST(self) -> None:
        """Handle POST requests (webhook events)."""
        if self.webhook_server:
            self.webhook_server.stats.requests_received += 1

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Get headers as dict
        headers_dict = dict(self.headers.items())

        # Parse JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._send_response(400, {"error": f"Invalid JSON: {e}"})
            return

        # Handle webhook
        if self.webhook_server:
            try:
                accepted = self.webhook_server.handle_webhook(payload, headers_dict, body)
                if accepted:
                    self._send_response(200, {"status": "accepted"})
                else:
                    self._send_response(401, {"error": "Signature verification failed"})
            except Exception as e:
                logger.exception(f"Webhook handling error: {e}")
                self._send_response(500, {"error": str(e)})
        else:
            self._send_response(200, {"status": "received"})

    def _send_response(self, status: int, body: dict) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


class MultiTrackerWebhookServer:
    """
    HTTP server for receiving webhooks from multiple trackers.

    Automatically detects the source tracker and parses the payload
    using the appropriate parser.
    """

    def __init__(
        self,
        config: MultiTrackerWebhookConfig,
        reverse_sync: "ReverseSyncOrchestrator | None" = None,
        output_path: str | None = None,
        on_event: Callable[[MultiTrackerEvent], None] | None = None,
        on_sync_start: Callable[[], None] | None = None,
        on_sync_complete: Callable[["PullResult"], None] | None = None,
    ):
        """
        Initialize the multi-tracker webhook server.

        Args:
            config: Server configuration.
            reverse_sync: Optional reverse sync orchestrator.
            output_path: Path to output markdown file.
            on_event: Callback when event is received.
            on_sync_start: Callback when sync starts.
            on_sync_complete: Callback when sync completes.
        """
        self.config = config
        self.reverse_sync = reverse_sync
        self.output_path = output_path

        self._on_event = on_event
        self._on_sync_start = on_sync_start
        self._on_sync_complete = on_sync_complete

        # Initialize parsers
        self.parsers: list[WebhookPayloadParser] = [
            JiraWebhookParser(),
            GitHubWebhookParser(),
            GitLabWebhookParser(),
            AzureDevOpsWebhookParser(),
            LinearWebhookParser(),
        ]

        self._server: HTTPServer | None = None
        self._running = False
        self._last_sync_time: float = 0
        self._sync_lock = threading.Lock()
        self._pending_sync = False
        self._pending_timer: threading.Timer | None = None

        self.stats = MultiTrackerStats()
        self.logger = logging.getLogger("MultiTrackerWebhookServer")

    def start(self) -> None:
        """Start the webhook server (blocking)."""
        MultiTrackerWebhookHandler.webhook_server = self

        self._server = HTTPServer((self.config.host, self.config.port), MultiTrackerWebhookHandler)
        self._running = True

        self.logger.info(
            f"Multi-tracker webhook server starting on {self.config.host}:{self.config.port}"
        )

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        finally:
            self.stop()

    def start_async(self) -> threading.Thread:
        """Start the webhook server in a background thread."""
        MultiTrackerWebhookHandler.webhook_server = self

        self._server = HTTPServer((self.config.host, self.config.port), MultiTrackerWebhookHandler)
        self._running = True

        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()

        self.logger.info(
            f"Multi-tracker webhook server started on {self.config.host}:{self.config.port}"
        )
        return thread

    def stop(self) -> None:
        """Stop the webhook server."""
        self._running = False
        with self._sync_lock:
            if self._pending_timer:
                self._pending_timer.cancel()
                self._pending_timer = None
        if self._server:
            self._server.shutdown()
            self._server = None
        self.logger.info("Multi-tracker webhook server stopped")

    def handle_webhook(self, payload: dict, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Handle an incoming webhook.

        Args:
            payload: Parsed JSON payload.
            headers: HTTP headers.
            raw_body: Raw request body for signature verification.

        Returns:
            True if webhook was accepted, False if signature verification failed.
        """
        # Find the right parser
        parser = self._find_parser(payload, headers)
        if not parser:
            self.logger.warning("No parser found for payload")
            return True  # Accept but ignore unknown payloads

        # Verify signature
        secret = self._get_secret_for_tracker(parser.tracker_type)
        if not parser.verify_signature(raw_body, headers, secret):
            self.logger.warning(f"Signature verification failed for {parser.tracker_type.value}")
            return False

        # Parse event
        event = parser.parse(payload, headers)
        self.stats.record_event(event)

        self.logger.info(f"Received event: {event}")

        if self._on_event:
            self._on_event(event)

        # Check if we should trigger sync
        if self._should_sync(event):
            self._trigger_sync()

        return True

    def _find_parser(self, payload: dict, headers: dict[str, str]) -> WebhookPayloadParser | None:
        """Find a parser that can handle this payload."""
        for parser in self.parsers:
            if parser.can_parse(payload, headers):
                return parser
        return None

    def _get_secret_for_tracker(self, tracker: TrackerType) -> str | None:
        """Get the secret for a specific tracker."""
        secrets = {
            TrackerType.JIRA: self.config.jira_secret,
            TrackerType.GITHUB: self.config.github_secret,
            TrackerType.GITLAB: self.config.gitlab_secret,
            TrackerType.AZURE: self.config.azure_secret,
            TrackerType.LINEAR: self.config.linear_secret,
        }
        return secrets.get(tracker)

    def _should_sync(self, event: MultiTrackerEvent) -> bool:
        """Determine if we should trigger a sync for this event."""
        # Skip unknown events
        if event.category == WebhookEventCategory.UNKNOWN:
            return False

        # Filter by epic/project if configured
        if self.config.epic_key:
            if event.epic_key and event.epic_key != self.config.epic_key:
                return False
            if event.issue_key == self.config.epic_key:
                return True
            if not event.epic_key:
                return False

        if self.config.project_filter:
            project = event.project_key or event.repository
            if project and self.config.project_filter not in project:
                return False

        return True

    def _trigger_sync(self) -> None:
        """Trigger a sync with debouncing."""
        now = time.time()

        with self._sync_lock:
            if now - self._last_sync_time < self.config.debounce_seconds:
                self._pending_sync = True
                if self._pending_timer:
                    self._pending_timer.cancel()
                self._pending_timer = threading.Timer(
                    self.config.debounce_seconds,
                    self._execute_pending_sync,
                )
                self._pending_timer.start()
                return

            self._last_sync_time = now
            self._pending_sync = False

        self._execute_sync()

    def _execute_pending_sync(self) -> None:
        """Execute a pending sync."""
        if not self._running:
            return
        with self._sync_lock:
            if not self._pending_sync:
                return
            self._pending_sync = False
            self._last_sync_time = time.time()
            self._pending_timer = None

        self._execute_sync()

    def _execute_sync(self) -> None:
        """Execute the reverse sync."""
        if not self.reverse_sync or not self.config.epic_key or not self.output_path:
            self.logger.warning("Cannot sync: missing configuration")
            return

        self.stats.syncs_triggered += 1

        try:
            if self._on_sync_start:
                self._on_sync_start()

            self.logger.info("Starting reverse sync...")

            result = self.reverse_sync.pull(
                epic_key=self.config.epic_key,
                output_path=self.output_path,
            )

            if result.success:
                self.stats.syncs_successful += 1
                self.logger.info(f"Sync completed: {result.stories_pulled} stories")
            else:
                self.stats.syncs_failed += 1
                self.logger.error(f"Sync failed: {result.errors}")

            if self._on_sync_complete:
                self._on_sync_complete(result)

        except Exception as e:
            self.stats.syncs_failed += 1
            self.logger.exception(f"Sync error: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get current server status."""
        return {
            "running": self._running,
            "host": self.config.host,
            "port": self.config.port,
            "epic_key": self.config.epic_key,
            "uptime": self.stats.uptime_formatted,
            "requests": self.stats.requests_received,
            "total_events": self.stats.total_events,
            "events_by_tracker": self.stats.events_by_tracker,
            "syncs": {
                "triggered": self.stats.syncs_triggered,
                "successful": self.stats.syncs_successful,
                "failed": self.stats.syncs_failed,
            },
        }


def create_multi_tracker_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    epic_key: str | None = None,
    output_path: str | None = None,
    jira_secret: str | None = None,
    github_secret: str | None = None,
    gitlab_secret: str | None = None,
    azure_secret: str | None = None,
    linear_secret: str | None = None,
    reverse_sync: "ReverseSyncOrchestrator | None" = None,
    on_event: Callable[[MultiTrackerEvent], None] | None = None,
) -> MultiTrackerWebhookServer:
    """
    Create a multi-tracker webhook server.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        epic_key: Epic key to filter events for.
        output_path: Path to output markdown file.
        jira_secret: Jira webhook secret.
        github_secret: GitHub webhook secret.
        gitlab_secret: GitLab webhook secret.
        azure_secret: Azure DevOps webhook secret.
        linear_secret: Linear webhook secret.
        reverse_sync: Optional reverse sync orchestrator.
        on_event: Callback when event is received.

    Returns:
        Configured MultiTrackerWebhookServer.
    """
    config = MultiTrackerWebhookConfig(
        host=host,
        port=port,
        epic_key=epic_key,
        jira_secret=jira_secret,
        github_secret=github_secret,
        gitlab_secret=gitlab_secret,
        azure_secret=azure_secret,
        linear_secret=linear_secret,
    )

    return MultiTrackerWebhookServer(
        config=config,
        reverse_sync=reverse_sync,
        output_path=output_path,
        on_event=on_event,
    )
