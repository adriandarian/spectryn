"""
Webhook Receiver - Receive Jira webhooks for reverse sync.

Provides an HTTP server that listens for Jira webhook events
and triggers reverse sync when issues are updated.
"""

import hashlib
import hmac
import json
import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Optional


if TYPE_CHECKING:
    from .sync.reverse_sync import PullResult, ReverseSyncOrchestrator

logger = logging.getLogger(__name__)


class WebhookEventType(Enum):
    """Types of Jira webhook events we handle."""

    ISSUE_CREATED = "jira:issue_created"
    ISSUE_UPDATED = "jira:issue_updated"
    ISSUE_DELETED = "jira:issue_deleted"
    COMMENT_CREATED = "comment_created"
    COMMENT_UPDATED = "comment_updated"
    SPRINT_UPDATED = "sprint_updated"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, event_type: str) -> "WebhookEventType":
        """Parse event type from Jira webhook."""
        event_map = {
            "jira:issue_created": cls.ISSUE_CREATED,
            "jira:issue_updated": cls.ISSUE_UPDATED,
            "jira:issue_deleted": cls.ISSUE_DELETED,
            "comment_created": cls.COMMENT_CREATED,
            "comment_updated": cls.COMMENT_UPDATED,
            "sprint_updated": cls.SPRINT_UPDATED,
        }
        return event_map.get(event_type, cls.UNKNOWN)


@dataclass
class WebhookEvent:
    """Parsed webhook event."""

    event_type: WebhookEventType
    timestamp: datetime = field(default_factory=datetime.now)
    issue_key: str | None = None
    issue_id: str | None = None
    project_key: str | None = None
    epic_key: str | None = None
    user: str | None = None
    changelog: list[dict] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.event_type.value}: {self.issue_key or 'N/A'}"

    @property
    def is_issue_event(self) -> bool:
        """Check if this is an issue-related event."""
        return self.event_type in (
            WebhookEventType.ISSUE_CREATED,
            WebhookEventType.ISSUE_UPDATED,
            WebhookEventType.ISSUE_DELETED,
        )


@dataclass
class WebhookStats:
    """Statistics for webhook server."""

    started_at: datetime = field(default_factory=datetime.now)
    requests_received: int = 0
    events_processed: int = 0
    syncs_triggered: int = 0
    syncs_successful: int = 0
    syncs_failed: int = 0
    errors: list[str] = field(default_factory=list)

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


class WebhookParser:
    """
    Parses Jira webhook payloads.

    Handles the various Jira webhook formats and extracts
    relevant information for sync operations.
    """

    def __init__(self, epic_link_field: str = "customfield_10014"):
        """
        Initialize the parser.

        Args:
            epic_link_field: Custom field ID for epic link.
        """
        self.epic_link_field = epic_link_field
        self.logger = logging.getLogger("WebhookParser")

    def parse(self, payload: dict) -> WebhookEvent:
        """
        Parse a Jira webhook payload.

        Args:
            payload: The raw webhook payload.

        Returns:
            Parsed WebhookEvent.
        """
        event_type_str = payload.get("webhookEvent", "unknown")
        event_type = WebhookEventType.from_string(event_type_str)

        issue = payload.get("issue", {})
        fields = issue.get("fields", {})

        # Extract issue info
        issue_key = issue.get("key")
        issue_id = issue.get("id")
        project = fields.get("project", {})
        project_key = project.get("key")

        # Extract epic key (from parent or epic link field)
        epic_key = self._extract_epic_key(fields)

        # Extract user
        user_obj = payload.get("user", {})
        user = user_obj.get("displayName") or user_obj.get("name")

        # Extract changelog
        changelog = self._extract_changelog(payload)

        return WebhookEvent(
            event_type=event_type,
            issue_key=issue_key,
            issue_id=issue_id,
            project_key=project_key,
            epic_key=epic_key,
            user=user,
            changelog=changelog,
            raw_payload=payload,
        )

    def _extract_epic_key(self, fields: dict) -> str | None:
        """Extract epic key from issue fields."""
        # Check parent field (Jira next-gen)
        parent = fields.get("parent", {})
        if parent:
            parent_type = parent.get("fields", {}).get("issuetype", {}).get("name", "")
            if parent_type.lower() == "epic":
                parent_key = parent.get("key")
                return parent_key if isinstance(parent_key, str) else None

        # Check epic link field (Jira classic)
        epic_link = fields.get(self.epic_link_field)
        if isinstance(epic_link, str):
            return epic_link

        # Check if this issue is an epic itself
        issue_type = fields.get("issuetype", {}).get("name", "")
        if issue_type.lower() == "epic":
            # Return None - the issue itself is the epic
            return None

        return None

    def _extract_changelog(self, payload: dict) -> list[dict]:
        """Extract changelog from payload."""
        changelog = payload.get("changelog", {})
        items = changelog.get("items", [])

        return [
            {
                "field": item.get("field"),
                "from": item.get("fromString"),
                "to": item.get("toString"),
            }
            for item in items
        ]


class WebhookHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for Jira webhooks.
    """

    # Class-level references (set by WebhookServer)
    webhook_server: Optional["WebhookServer"] = None

    def log_message(self, format: str, *args: Any) -> None:
        """Override to use our logger."""
        logger.debug(f"HTTP: {format % args}")

    def do_GET(self) -> None:
        """Handle GET requests (health check)."""
        if self.path == "/health":
            self._send_response(200, {"status": "ok", "service": "spectra-webhook"})
        elif self.path == "/status":
            if self.webhook_server:
                stats = self.webhook_server.stats
                self._send_response(
                    200,
                    {
                        "status": "running",
                        "uptime": stats.uptime_formatted,
                        "requests": stats.requests_received,
                        "events": stats.events_processed,
                        "syncs": stats.syncs_triggered,
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

        # Verify signature if configured
        if self.webhook_server and self.webhook_server.secret:
            if not self._verify_signature(body):
                self._send_response(401, {"error": "Invalid signature"})
                return

        # Parse JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._send_response(400, {"error": f"Invalid JSON: {e}"})
            return

        # Handle webhook
        if self.webhook_server:
            try:
                self.webhook_server.handle_webhook(payload)
                self._send_response(200, {"status": "accepted"})
            except Exception as e:
                logger.error(f"Webhook handling error: {e}")
                self._send_response(500, {"error": str(e)})
        else:
            self._send_response(200, {"status": "received"})

    def _verify_signature(self, body: bytes) -> bool:
        """Verify webhook signature."""
        if not self.webhook_server or not self.webhook_server.secret:
            return True

        signature = self.headers.get("X-Hub-Signature-256") or self.headers.get(
            "X-Atlassian-Webhook-Signature"
        )
        if not signature:
            return False

        expected = hmac.new(
            self.webhook_server.secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        # Handle "sha256=" prefix
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(signature, expected)

    def _send_response(self, status: int, body: dict) -> None:
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


class WebhookServer:
    """
    HTTP server for receiving Jira webhooks.

    Listens for webhook events and triggers reverse sync
    when relevant issues are updated.
    """

    def __init__(
        self,
        reverse_sync: "ReverseSyncOrchestrator",
        host: str = "0.0.0.0",
        port: int = 8080,
        epic_key: str | None = None,
        output_path: str | None = None,
        secret: str | None = None,
        debounce_seconds: float = 5.0,
        on_event: Callable[[WebhookEvent], None] | None = None,
        on_sync_start: Callable[[], None] | None = None,
        on_sync_complete: Callable[["PullResult"], None] | None = None,
    ):
        """
        Initialize the webhook server.

        Args:
            reverse_sync: Reverse sync orchestrator.
            host: Host to bind to.
            port: Port to listen on.
            epic_key: Epic key to filter events for.
            output_path: Path to output markdown file.
            secret: Webhook secret for signature verification.
            debounce_seconds: Minimum time between syncs.
            on_event: Callback when event is received.
            on_sync_start: Callback when sync starts.
            on_sync_complete: Callback when sync completes.
        """
        self.reverse_sync = reverse_sync
        self.host = host
        self.port = port
        self.epic_key = epic_key
        self.output_path = output_path
        self.secret = secret
        self.debounce_seconds = debounce_seconds

        self._on_event = on_event
        self._on_sync_start = on_sync_start
        self._on_sync_complete = on_sync_complete

        self._server: HTTPServer | None = None
        self._running = False
        self._last_sync_time: float = 0
        self._sync_lock = threading.Lock()
        self._pending_sync = False
        self._pending_timer: threading.Timer | None = None

        self.parser = WebhookParser()
        self.stats = WebhookStats()

        self.logger = logging.getLogger("WebhookServer")

    def start(self) -> None:
        """
        Start the webhook server.

        This method blocks until stop() is called.
        """
        self._setup_signal_handlers()

        # Configure handler
        WebhookHandler.webhook_server = self

        # Create server
        self._server = HTTPServer((self.host, self.port), WebhookHandler)
        self._running = True

        self.logger.info(f"Webhook server starting on {self.host}:{self.port}")
        self.logger.info("Press Ctrl+C to stop")

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        finally:
            self.stop()

    def start_async(self) -> threading.Thread:
        """
        Start the webhook server in a background thread.

        Returns:
            The server thread.
        """
        # Configure handler
        WebhookHandler.webhook_server = self

        # Create server
        self._server = HTTPServer((self.host, self.port), WebhookHandler)
        self._running = True

        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()

        self.logger.info(f"Webhook server started on {self.host}:{self.port}")
        return thread

    def stop(self) -> None:
        """Stop the webhook server."""
        self._running = False
        # Cancel any pending sync timer
        with self._sync_lock:
            if self._pending_timer:
                self._pending_timer.cancel()
                self._pending_timer = None
            self._pending_sync = False
        if self._server:
            self._server.shutdown()
            self._server = None
        self.logger.info("Webhook server stopped")

    def handle_webhook(self, payload: dict) -> None:
        """
        Handle an incoming webhook payload.

        Args:
            payload: The webhook payload.
        """
        # Parse event
        event = self.parser.parse(payload)
        self.stats.events_processed += 1

        self.logger.info(f"Received event: {event}")

        if self._on_event:
            self._on_event(event)

        # Check if we should trigger sync
        if self._should_sync(event):
            self._trigger_sync()

    def _should_sync(self, event: WebhookEvent) -> bool:
        """Determine if we should trigger a sync for this event."""
        # Only handle issue events
        if not event.is_issue_event:
            return False

        # If epic_key is configured, only sync for that epic
        if self.epic_key:
            if event.epic_key and event.epic_key != self.epic_key:
                return False
            # If the event is for the epic itself
            if event.issue_key and event.issue_key == self.epic_key:
                return True
            # If we couldn't determine the epic, skip
            if not event.epic_key:
                return False

        return True

    def _trigger_sync(self) -> None:
        """Trigger a reverse sync with debouncing."""
        now = time.time()

        with self._sync_lock:
            # Check debounce
            if now - self._last_sync_time < self.debounce_seconds:
                self._pending_sync = True
                self.logger.debug("Sync debounced, will run after delay")
                # Cancel any existing timer
                if self._pending_timer:
                    self._pending_timer.cancel()
                # Schedule delayed sync
                self._pending_timer = threading.Timer(
                    self.debounce_seconds,
                    self._execute_pending_sync,
                )
                self._pending_timer.start()
                return

            self._last_sync_time = now
            self._pending_sync = False
        self._execute_sync()

    def _execute_pending_sync(self) -> None:
        """Execute a pending sync if one is scheduled."""
        # Check if server was stopped
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
        if not self.epic_key or not self.output_path:
            self.logger.warning("Cannot sync: epic_key or output_path not configured")
            return

        self.stats.syncs_triggered += 1

        try:
            if self._on_sync_start:
                self._on_sync_start()

            self.logger.info("Starting reverse sync...")

            result = self.reverse_sync.pull(
                epic_key=self.epic_key,
                output_path=self.output_path,
            )

            if result.success:
                self.stats.syncs_successful += 1
                self.logger.info(f"Sync completed: {result.stories_pulled} stories pulled")
            else:
                self.stats.syncs_failed += 1
                self.logger.error(f"Sync failed: {result.errors}")

            if self._on_sync_complete:
                self._on_sync_complete(result)

        except Exception as e:
            self.stats.syncs_failed += 1
            self.stats.errors.append(str(e))
            self.logger.error(f"Sync error: {e}")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        if threading.current_thread() is not threading.main_thread():
            return

        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Received signal {signum}")
            self.stop()

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except ValueError:
            pass

    def get_status(self) -> dict[str, Any]:
        """Get current server status."""
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "epic_key": self.epic_key,
            "uptime": self.stats.uptime_formatted,
            "requests": self.stats.requests_received,
            "events": self.stats.events_processed,
            "syncs_triggered": self.stats.syncs_triggered,
            "syncs_successful": self.stats.syncs_successful,
            "syncs_failed": self.stats.syncs_failed,
        }


class WebhookDisplay:
    """
    Display handler for webhook server output.
    """

    def __init__(self, color: bool = True, quiet: bool = False):
        self.color = color
        self.quiet = quiet

    def show_start(
        self,
        host: str,
        port: int,
        epic_key: str | None,
    ) -> None:
        """Show server start message."""
        if self.quiet:
            return

        print()
        self._print_colored("🌐 Webhook Server Active", "cyan", bold=True)
        print(f"   Listening: http://{host}:{port}")
        if epic_key:
            print(f"   Epic filter: {epic_key}")
        print()
        print("   Endpoints:")
        print("     POST /         - Receive webhooks")
        print("     GET  /health   - Health check")
        print("     GET  /status   - Server status")
        print()
        print("   Press Ctrl+C to stop")
        print()

    def show_event(self, event: WebhookEvent) -> None:
        """Show received event."""
        if self.quiet:
            return

        timestamp = event.timestamp.strftime("%H:%M:%S")
        self._print_colored(
            f"📥 [{timestamp}] {event.event_type.value}: {event.issue_key or 'N/A'}",
            "yellow",
        )

    def show_sync_start(self) -> None:
        """Show sync starting message."""
        if self.quiet:
            return

        self._print_colored("🔄 Triggering reverse sync...", "blue")

    def show_sync_complete(self, result: "PullResult") -> None:
        """Show sync complete message."""
        if result.success:
            self._print_colored("✅ Sync complete", "green")
            if not self.quiet:
                print(f"   Stories: {result.stories_pulled} pulled")
        else:
            self._print_colored("❌ Sync failed", "red")
            if not self.quiet:
                for error in result.errors[:3]:
                    print(f"   - {error}")
        print()

    def show_stop(self, stats: WebhookStats) -> None:
        """Show server stop message."""
        print()
        self._print_colored("🛑 Webhook Server Stopped", "cyan", bold=True)
        print(f"   Uptime: {stats.uptime_formatted}")
        print(f"   Requests: {stats.requests_received}")
        print(f"   Events: {stats.events_processed}")
        print(f"   Syncs: {stats.syncs_successful} successful, {stats.syncs_failed} failed")
        print()

    def _print_colored(self, text: str, color: str, bold: bool = False) -> None:
        """Print with optional color."""
        if not self.color:
            print(text)
            return

        colors = {
            "red": "\033[91m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "cyan": "\033[96m",
        }

        color_code = colors.get(color, "")
        bold_code = "\033[1m" if bold else ""
        reset = "\033[0m"

        print(f"{bold_code}{color_code}{text}{reset}")
