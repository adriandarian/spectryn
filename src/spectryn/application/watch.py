"""
Watch Mode - Auto-sync on file changes.

Monitors markdown files for changes and automatically triggers
sync operations when modifications are detected.
"""

import hashlib
import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .sync import SyncOrchestrator, SyncResult

logger = logging.getLogger(__name__)


class WatchEvent(Enum):
    """Types of watch events."""

    MODIFIED = "modified"
    CREATED = "created"
    DELETED = "deleted"
    ERROR = "error"


@dataclass
class FileChange:
    """Represents a detected file change."""

    path: str
    event: WatchEvent
    timestamp: datetime = field(default_factory=datetime.now)
    old_hash: str = ""
    new_hash: str = ""

    def __str__(self) -> str:
        return f"{self.event.value}: {self.path} at {self.timestamp.strftime('%H:%M:%S')}"


@dataclass
class WatchStats:
    """Statistics for a watch session."""

    started_at: datetime = field(default_factory=datetime.now)
    changes_detected: int = 0
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
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


class FileWatcher:
    """
    Watches files for changes using polling.

    Uses content hashing to detect actual changes (not just mtime),
    which is more reliable across different filesystems.
    """

    def __init__(
        self,
        path: str,
        debounce_seconds: float = 1.0,
        poll_interval: float = 0.5,
    ):
        """
        Initialize the file watcher.

        Args:
            path: Path to the file to watch.
            debounce_seconds: Minimum time between change notifications.
            poll_interval: How often to check for changes (seconds).
        """
        self.path = Path(path)
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._last_hash: str | None = None
        self._last_change_time: float = 0
        self._callbacks: list[Callable[[FileChange], None]] = []
        self._lock = threading.Lock()

        self.logger = logging.getLogger("FileWatcher")

    def start(self) -> None:
        """Start watching the file."""
        if self._running:
            return

        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")

        self._last_hash = self._compute_hash()
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

        self.logger.info(f"Started watching: {self.path}")

    def stop(self) -> None:
        """Stop watching the file."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.logger.info("Stopped watching")

    def on_change(self, callback: Callable[[FileChange], None]) -> None:
        """
        Register a callback for file changes.

        Args:
            callback: Function to call when file changes.
        """
        self._callbacks.append(callback)

    def _watch_loop(self) -> None:
        """Main watch loop (runs in separate thread)."""
        while self._running:
            try:
                self._check_for_changes()
            except Exception as e:
                self.logger.error(f"Error in watch loop: {e}")
                self._notify_change(
                    FileChange(
                        path=str(self.path),
                        event=WatchEvent.ERROR,
                    )
                )

            time.sleep(self.poll_interval)

    def _check_for_changes(self) -> None:
        """Check if the file has changed."""
        if not self.path.exists():
            if self._last_hash is not None:
                # File was deleted
                self._notify_change(
                    FileChange(
                        path=str(self.path),
                        event=WatchEvent.DELETED,
                        old_hash=self._last_hash or "",
                    )
                )
                self._last_hash = None
            return

        current_hash = self._compute_hash()

        if self._last_hash is None:
            # File was created
            self._last_hash = current_hash
            self._notify_change(
                FileChange(
                    path=str(self.path),
                    event=WatchEvent.CREATED,
                    new_hash=current_hash,
                )
            )
            return

        if current_hash != self._last_hash:
            # File was modified - apply debouncing
            now = time.time()
            if now - self._last_change_time >= self.debounce_seconds:
                self._notify_change(
                    FileChange(
                        path=str(self.path),
                        event=WatchEvent.MODIFIED,
                        old_hash=self._last_hash,
                        new_hash=current_hash,
                    )
                )
                self._last_hash = current_hash
                self._last_change_time = now

    def _compute_hash(self) -> str:
        """Compute hash of file contents."""
        try:
            content = self.path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception as e:
            self.logger.warning(f"Failed to read file: {e}")
            return ""

    def _notify_change(self, change: FileChange) -> None:
        """Notify all registered callbacks of a change."""
        with self._lock:
            for callback in self._callbacks:
                try:
                    callback(change)
                except Exception as e:
                    self.logger.error(f"Callback error: {e}")


class WatchOrchestrator:
    """
    Orchestrates watch mode - monitors files and triggers syncs.

    Provides a complete watch experience with:
    - File change detection
    - Automatic sync triggering
    - Debouncing to avoid excessive syncs
    - Graceful shutdown handling
    - Status reporting
    """

    def __init__(
        self,
        orchestrator: "SyncOrchestrator",
        markdown_path: str,
        epic_key: str,
        debounce_seconds: float = 2.0,
        poll_interval: float = 1.0,
        on_sync_start: Callable[[], None] | None = None,
        on_sync_complete: Callable[["SyncResult"], None] | None = None,
        on_change_detected: Callable[[FileChange], None] | None = None,
    ):
        """
        Initialize the watch orchestrator.

        Args:
            orchestrator: The sync orchestrator to use.
            markdown_path: Path to the markdown file to watch.
            epic_key: Jira epic key.
            debounce_seconds: Minimum time between syncs.
            poll_interval: How often to check for changes.
            on_sync_start: Callback when sync starts.
            on_sync_complete: Callback when sync completes.
            on_change_detected: Callback when file change detected.
        """
        self.orchestrator = orchestrator
        self.markdown_path = markdown_path
        self.epic_key = epic_key
        self.debounce_seconds = debounce_seconds

        self._watcher = FileWatcher(
            path=markdown_path,
            debounce_seconds=debounce_seconds,
            poll_interval=poll_interval,
        )

        self._running = False
        self._syncing = False
        self._sync_lock = threading.Lock()
        self._stop_event = threading.Event()

        self.stats = WatchStats()

        self._on_sync_start = on_sync_start
        self._on_sync_complete = on_sync_complete
        self._on_change_detected = on_change_detected

        self.logger = logging.getLogger("WatchOrchestrator")

    def start(self) -> None:
        """
        Start watching and auto-syncing.

        This method blocks until stop() is called or Ctrl+C is pressed.
        """
        self._running = True
        self._setup_signal_handlers()

        # Register change handler
        self._watcher.on_change(self._handle_change)

        # Start the file watcher
        self._watcher.start()

        self.logger.info(f"Watch mode started for {self.markdown_path}")
        self.logger.info(f"Epic: {self.epic_key}")
        self.logger.info(f"Debounce: {self.debounce_seconds}s")
        self.logger.info("Press Ctrl+C to stop")

        # Block until stop signal
        try:
            while self._running and not self._stop_event.is_set():
                self._stop_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        finally:
            self.stop()

    def start_async(self) -> None:
        """
        Start watching in non-blocking mode.

        Use stop() to stop the watcher.
        """
        self._running = True
        self._watcher.on_change(self._handle_change)
        self._watcher.start()
        self.logger.info(f"Watch mode started (async) for {self.markdown_path}")

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        self._stop_event.set()
        self._watcher.stop()
        self.logger.info("Watch mode stopped")
        self.logger.info(
            f"Session stats: {self.stats.syncs_triggered} syncs, "
            f"{self.stats.syncs_successful} successful, "
            f"{self.stats.syncs_failed} failed"
        )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Received signal {signum}")
            self.stop()

        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _handle_change(self, change: FileChange) -> None:
        """Handle a file change event."""
        self.stats.changes_detected += 1

        if self._on_change_detected:
            self._on_change_detected(change)

        self.logger.info(f"Change detected: {change}")

        if change.event == WatchEvent.DELETED:
            self.logger.warning("File was deleted, cannot sync")
            return

        if change.event == WatchEvent.ERROR:
            self.stats.errors.append(f"Watch error at {change.timestamp}")
            return

        # Trigger sync
        self._trigger_sync()

    def _trigger_sync(self) -> None:
        """Trigger a sync operation."""
        with self._sync_lock:
            if self._syncing:
                self.logger.debug("Sync already in progress, skipping")
                return
            self._syncing = True

        try:
            self.stats.syncs_triggered += 1

            if self._on_sync_start:
                self._on_sync_start()

            self.logger.info("Starting sync...")

            result = self.orchestrator.sync(
                markdown_path=self.markdown_path,
                epic_key=self.epic_key,
            )

            if result.success:
                self.stats.syncs_successful += 1
                self.logger.info(
                    f"Sync completed: {result.stories_updated} stories updated, "
                    f"{result.subtasks_created} subtasks created"
                )
            else:
                self.stats.syncs_failed += 1
                self.logger.error(f"Sync failed: {len(result.errors)} errors")
                for error in result.errors[:3]:
                    self.logger.error(f"  - {error}")

            if self._on_sync_complete:
                self._on_sync_complete(result)

        except Exception as e:
            self.stats.syncs_failed += 1
            self.stats.errors.append(str(e))
            self.logger.error(f"Sync error: {e}")

        finally:
            with self._sync_lock:
                self._syncing = False

    def get_status(self) -> dict[str, Any]:
        """Get current watch status."""
        return {
            "running": self._running,
            "syncing": self._syncing,
            "markdown_path": self.markdown_path,
            "epic_key": self.epic_key,
            "uptime": self.stats.uptime_formatted,
            "changes_detected": self.stats.changes_detected,
            "syncs_triggered": self.stats.syncs_triggered,
            "syncs_successful": self.stats.syncs_successful,
            "syncs_failed": self.stats.syncs_failed,
            "errors": self.stats.errors[-5:],  # Last 5 errors
        }


class WatchDisplay:
    """
    Display handler for watch mode output.

    Provides a nice terminal UI for watch mode status.
    """

    def __init__(self, color: bool = True, quiet: bool = False):
        """
        Initialize the display.

        Args:
            color: Whether to use colored output.
            quiet: Minimal output mode.
        """
        self.color = color
        self.quiet = quiet

    def show_start(self, markdown_path: str, epic_key: str) -> None:
        """Show watch start message."""
        if self.quiet:
            return

        print()
        self._print_colored("👀 Watch Mode Active", "cyan", bold=True)
        print(f"   File: {markdown_path}")
        print(f"   Epic: {epic_key}")
        print()
        print("   Watching for changes... (Ctrl+C to stop)")
        print()

    def show_change_detected(self, change: FileChange) -> None:
        """Show change detected message."""
        if self.quiet:
            return

        timestamp = change.timestamp.strftime("%H:%M:%S")
        self._print_colored(f"📝 [{timestamp}] Change detected", "yellow")

    def show_sync_start(self) -> None:
        """Show sync starting message."""
        if self.quiet:
            return

        self._print_colored("🔄 Syncing...", "blue")

    def show_sync_complete(self, result: "SyncResult") -> None:
        """Show sync complete message."""
        if result.success:
            self._print_colored("✅ Sync complete", "green")
            if not self.quiet:
                print(
                    f"   Stories: {result.stories_matched} matched, {result.stories_updated} updated"
                )
                print(
                    f"   Subtasks: {result.subtasks_created} created, {result.subtasks_updated} updated"
                )
        else:
            self._print_colored("❌ Sync failed", "red")
            if not self.quiet:
                for error in result.errors[:3]:
                    print(f"   - {error}")
        print()

    def show_stop(self, stats: WatchStats) -> None:
        """Show watch stop message."""
        print()
        self._print_colored("🛑 Watch Mode Stopped", "cyan", bold=True)
        print(f"   Uptime: {stats.uptime_formatted}")
        print(f"   Changes detected: {stats.changes_detected}")
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
