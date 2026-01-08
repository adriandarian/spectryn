"""
Scheduled Sync - Cron-like scheduled syncs.

Provides scheduling capabilities for automatic sync operations
at specified intervals or times.
"""

import logging
import signal
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from .sync import SyncOrchestrator, SyncResult

logger = logging.getLogger(__name__)


class ScheduleType(Enum):
    """Types of schedules."""

    INTERVAL = "interval"  # Every N seconds/minutes/hours
    DAILY = "daily"  # At specific time each day
    HOURLY = "hourly"  # At specific minute each hour
    CRON = "cron"  # Cron-like expression (simplified)


@dataclass
class ScheduleStats:
    """Statistics for a scheduled sync session."""

    started_at: datetime = field(default_factory=datetime.now)
    runs_completed: int = 0
    runs_successful: int = 0
    runs_failed: int = 0
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
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


class Schedule(ABC):
    """Base class for schedules."""

    @abstractmethod
    def next_run_time(self, after: datetime | None = None) -> datetime:
        """Calculate the next run time after the given time."""
        ...

    @abstractmethod
    def description(self) -> str:
        """Get a human-readable description of the schedule."""
        ...

    def seconds_until_next(self, after: datetime | None = None) -> float:
        """Calculate seconds until the next run."""
        after = after or datetime.now()
        next_time = self.next_run_time(after)
        return max(0, (next_time - datetime.now()).total_seconds())


class IntervalSchedule(Schedule):
    """
    Run at fixed intervals.

    Examples:
    - Every 30 seconds
    - Every 5 minutes
    - Every 1 hour
    """

    def __init__(self, seconds: float = 0, minutes: float = 0, hours: float = 0):
        """
        Initialize interval schedule.

        Args:
            seconds: Interval in seconds.
            minutes: Interval in minutes (added to seconds).
            hours: Interval in hours (added to total).
        """
        self.interval_seconds = seconds + (minutes * 60) + (hours * 3600)
        if self.interval_seconds <= 0:
            raise ValueError("Interval must be positive")

    def next_run_time(self, after: datetime | None = None) -> datetime:
        after = after or datetime.now()
        return after + timedelta(seconds=self.interval_seconds)

    def description(self) -> str:
        if self.interval_seconds >= 3600:
            hours = self.interval_seconds / 3600
            return f"every {hours:.1f} hour(s)"
        if self.interval_seconds >= 60:
            minutes = self.interval_seconds / 60
            return f"every {minutes:.1f} minute(s)"
        return f"every {self.interval_seconds:.0f} second(s)"


class DailySchedule(Schedule):
    """
    Run at a specific time each day.

    Example: Run at 09:00 every day
    """

    def __init__(self, hour: int = 0, minute: int = 0):
        """
        Initialize daily schedule.

        Args:
            hour: Hour of day (0-23).
            minute: Minute of hour (0-59).
        """
        if not (0 <= hour <= 23):
            raise ValueError("Hour must be 0-23")
        if not (0 <= minute <= 59):
            raise ValueError("Minute must be 0-59")

        self.hour = hour
        self.minute = minute

    def next_run_time(self, after: datetime | None = None) -> datetime:
        after = after or datetime.now()

        # Calculate today's run time
        today_run = after.replace(
            hour=self.hour,
            minute=self.minute,
            second=0,
            microsecond=0,
        )

        # If today's time has passed, schedule for tomorrow
        if today_run <= after:
            today_run += timedelta(days=1)

        return today_run

    def description(self) -> str:
        return f"daily at {self.hour:02d}:{self.minute:02d}"


class HourlySchedule(Schedule):
    """
    Run at a specific minute each hour.

    Example: Run at :30 every hour
    """

    def __init__(self, minute: int = 0):
        """
        Initialize hourly schedule.

        Args:
            minute: Minute of hour (0-59).
        """
        if not (0 <= minute <= 59):
            raise ValueError("Minute must be 0-59")

        self.minute = minute

    def next_run_time(self, after: datetime | None = None) -> datetime:
        after = after or datetime.now()

        # Calculate this hour's run time
        this_hour_run = after.replace(
            minute=self.minute,
            second=0,
            microsecond=0,
        )

        # If this hour's time has passed, schedule for next hour
        if this_hour_run <= after:
            this_hour_run += timedelta(hours=1)

        return this_hour_run

    def description(self) -> str:
        return f"hourly at :{self.minute:02d}"


class CronSchedule(Schedule):
    """
    Simplified cron-like schedule.

    Supports basic patterns:
    - minute hour day_of_week
    - * for any value
    - Specific numbers

    Examples:
    - "0 9 *" = 9:00 AM every day
    - "30 * *" = :30 every hour
    - "0 12 1" = 12:00 on Mondays (1=Monday, 7=Sunday)
    """

    WEEKDAYS = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
        "1": 0,
        "2": 1,
        "3": 2,
        "4": 3,
        "5": 4,
        "6": 5,
        "7": 6,
        "0": 6,
    }

    def __init__(self, expression: str):
        """
        Initialize cron schedule.

        Args:
            expression: Cron-like expression "minute hour day_of_week".
        """
        self.expression = expression
        self._parse_expression(expression)

    def _parse_expression(self, expression: str) -> None:
        """Parse the cron expression."""
        parts = expression.strip().split()

        if len(parts) != 3:
            raise ValueError(
                f"Invalid cron expression: '{expression}'. "
                "Expected format: 'minute hour day_of_week'"
            )

        minute_str, hour_str, dow_str = parts

        # Parse minute
        self.minutes = self._parse_field(minute_str, 0, 59)

        # Parse hour
        self.hours = self._parse_field(hour_str, 0, 23)

        # Parse day of week
        if dow_str == "*":
            self.days_of_week = list(range(7))
        elif dow_str.lower() in self.WEEKDAYS:
            self.days_of_week = [self.WEEKDAYS[dow_str.lower()]]
        else:
            self.days_of_week = self._parse_field(dow_str, 0, 6)

    def _parse_field(self, field: str, min_val: int, max_val: int) -> list[int]:
        """Parse a cron field into a list of values."""
        if field == "*":
            return list(range(min_val, max_val + 1))

        try:
            val = int(field)
            if min_val <= val <= max_val:
                return [val]
            raise ValueError(f"Value {val} out of range [{min_val}, {max_val}]")
        except ValueError:
            pass

        # Handle comma-separated values
        if "," in field:
            values = []
            for part in field.split(","):
                val = int(part)
                if min_val <= val <= max_val:
                    values.append(val)
            return sorted(values)

        raise ValueError(f"Invalid field: {field}")

    def next_run_time(self, after: datetime | None = None) -> datetime:
        after = after or datetime.now()
        current = after.replace(second=0, microsecond=0)

        # Search up to 7 days ahead
        for _ in range(7 * 24 * 60):  # Max iterations
            current += timedelta(minutes=1)

            if (
                current.weekday() in self.days_of_week
                and current.hour in self.hours
                and current.minute in self.minutes
            ):
                return current

        # Fallback (shouldn't reach here with valid schedule)
        return after + timedelta(days=1)

    def description(self) -> str:
        return f"cron: {self.expression}"


def parse_schedule(spec: str) -> Schedule:
    """
    Parse a schedule specification string.

    Formats:
    - "30s", "5m", "1h" - Interval
    - "daily:09:00" - Daily at time
    - "hourly:30" - Hourly at minute
    - "cron:0 9 *" - Cron expression

    Args:
        spec: Schedule specification string.

    Returns:
        Appropriate Schedule instance.

    Raises:
        ValueError: If spec format is invalid.
    """
    spec = spec.strip().lower()

    # Interval format: 30s, 5m, 1h
    if spec[-1] in "smh" and spec[:-1].replace(".", "").isdigit():
        value = float(spec[:-1])
        unit = spec[-1]

        if unit == "s":
            return IntervalSchedule(seconds=value)
        if unit == "m":
            return IntervalSchedule(minutes=value)
        if unit == "h":
            return IntervalSchedule(hours=value)

    # Daily format: daily:HH:MM
    if spec.startswith("daily:"):
        time_part = spec[6:]
        parts = time_part.split(":")
        if len(parts) == 2:
            hour, minute = int(parts[0]), int(parts[1])
            return DailySchedule(hour=hour, minute=minute)
        raise ValueError(f"Invalid daily format: {spec}. Expected daily:HH:MM")

    # Hourly format: hourly:MM
    if spec.startswith("hourly:"):
        minute_str = spec[7:]
        minute = int(minute_str)
        return HourlySchedule(minute=minute)

    # Cron format: cron:expression
    if spec.startswith("cron:"):
        expression = spec[5:].strip()
        return CronSchedule(expression)

    raise ValueError(
        f"Invalid schedule format: {spec}. "
        "Expected: 30s, 5m, 1h, daily:HH:MM, hourly:MM, or cron:expression"
    )


class ScheduledSyncRunner:
    """
    Runs syncs on a schedule.

    Provides:
    - Scheduled execution at intervals or times
    - Statistics tracking
    - Graceful shutdown
    - Error handling and recovery
    """

    def __init__(
        self,
        orchestrator: "SyncOrchestrator",
        schedule: Schedule,
        markdown_path: str,
        epic_key: str,
        run_immediately: bool = False,
        max_runs: int | None = None,
        on_run_start: Callable[[], None] | None = None,
        on_run_complete: Callable[["SyncResult"], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        """
        Initialize the scheduled sync runner.

        Args:
            orchestrator: Sync orchestrator to use.
            schedule: Schedule to follow.
            markdown_path: Path to markdown file.
            epic_key: Jira epic key.
            run_immediately: Whether to run immediately on start.
            max_runs: Maximum number of runs (None for unlimited).
            on_run_start: Callback when sync starts.
            on_run_complete: Callback when sync completes.
            on_error: Callback on error.
        """
        self.orchestrator = orchestrator
        self.schedule = schedule
        self.markdown_path = markdown_path
        self.epic_key = epic_key
        self.run_immediately = run_immediately
        self.max_runs = max_runs

        self._running = False
        self._stop_event = threading.Event()
        self._current_run: threading.Thread | None = None

        self.stats = ScheduleStats()

        self._on_run_start = on_run_start
        self._on_run_complete = on_run_complete
        self._on_error = on_error

        self.logger = logging.getLogger("ScheduledSyncRunner")

    def start(self) -> None:
        """
        Start the scheduled sync runner.

        This method blocks until stop() is called or max_runs is reached.
        """
        self._running = True
        self._setup_signal_handlers()

        self.logger.info(f"Starting scheduled sync: {self.schedule.description()}")
        self.logger.info(f"Markdown: {self.markdown_path}")
        self.logger.info(f"Epic: {self.epic_key}")
        self.logger.info("Press Ctrl+C to stop")

        # Run immediately if requested
        if self.run_immediately:
            self._execute_sync()

        # Main scheduling loop
        try:
            while self._running and not self._stop_event.is_set():
                # Check max runs
                if self.max_runs and self.stats.runs_completed >= self.max_runs:
                    self.logger.info(f"Reached max runs ({self.max_runs})")
                    break

                # Calculate next run time
                next_run = self.schedule.next_run_time()
                self.stats.next_run_at = next_run
                wait_seconds = self.schedule.seconds_until_next()

                self.logger.info(
                    f"Next sync at {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(in {wait_seconds:.0f}s)"
                )

                # Wait until next run (interruptible)
                if self._stop_event.wait(timeout=wait_seconds):
                    break  # Stop was requested

                # Execute sync
                if self._running:
                    self._execute_sync()

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        finally:
            self.stop()

    def start_async(self) -> threading.Thread:
        """
        Start the scheduled sync runner in a background thread.

        Returns:
            The runner thread.
        """
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """Stop the scheduled sync runner."""
        self._running = False
        self._stop_event.set()
        self.logger.info("Scheduled sync stopped")

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        # Signal handlers can only be set in the main thread
        if threading.current_thread() is not threading.main_thread():
            return

        def signal_handler(signum: int, frame: Any) -> None:
            self.logger.info(f"Received signal {signum}")
            self.stop()

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except ValueError:
            # Signal handling not supported in this context
            pass

    def _execute_sync(self) -> None:
        """Execute a single sync run."""
        self.stats.last_run_at = datetime.now()

        try:
            if self._on_run_start:
                self._on_run_start()

            self.logger.info("Starting scheduled sync...")

            result = self.orchestrator.sync(
                markdown_path=self.markdown_path,
                epic_key=self.epic_key,
            )

            self.stats.runs_completed += 1

            if result.success:
                self.stats.runs_successful += 1
                self.logger.info(
                    f"Sync completed successfully: {result.stories_updated} stories updated"
                )
            else:
                self.stats.runs_failed += 1
                self.logger.error(f"Sync failed: {len(result.errors)} errors")
                for error in result.errors[:3]:
                    self.logger.error(f"  - {error}")

            if self._on_run_complete:
                self._on_run_complete(result)

        except Exception as e:
            self.stats.runs_completed += 1
            self.stats.runs_failed += 1
            self.stats.errors.append(str(e))
            self.logger.error(f"Sync error: {e}")

            if self._on_error:
                self._on_error(e)

    def get_status(self) -> dict[str, Any]:
        """Get current runner status."""
        return {
            "running": self._running,
            "schedule": self.schedule.description(),
            "markdown_path": self.markdown_path,
            "epic_key": self.epic_key,
            "uptime": self.stats.uptime_formatted,
            "runs_completed": self.stats.runs_completed,
            "runs_successful": self.stats.runs_successful,
            "runs_failed": self.stats.runs_failed,
            "last_run": self.stats.last_run_at.isoformat() if self.stats.last_run_at else None,
            "next_run": self.stats.next_run_at.isoformat() if self.stats.next_run_at else None,
        }


class ScheduleDisplay:
    """
    Display handler for scheduled sync output.
    """

    def __init__(self, color: bool = True, quiet: bool = False):
        self.color = color
        self.quiet = quiet

    def show_start(
        self,
        markdown_path: str,
        epic_key: str,
        schedule: Schedule,
    ) -> None:
        """Show scheduler start message."""
        if self.quiet:
            return

        print()
        self._print_colored("⏰ Scheduled Sync Active", "cyan", bold=True)
        print(f"   File: {markdown_path}")
        print(f"   Epic: {epic_key}")
        print(f"   Schedule: {schedule.description()}")
        print()

        next_run = schedule.next_run_time()
        print(f"   Next sync: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        print("   Press Ctrl+C to stop")
        print()

    def show_run_start(self) -> None:
        """Show sync run starting message."""
        if self.quiet:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._print_colored(f"🔄 [{timestamp}] Running scheduled sync...", "blue")

    def show_run_complete(self, result: "SyncResult") -> None:
        """Show sync run complete message."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if result.success:
            self._print_colored(f"✅ [{timestamp}] Sync complete", "green")
            if not self.quiet:
                print(
                    f"   Stories: {result.stories_matched} matched, "
                    f"{result.stories_updated} updated"
                )
        else:
            self._print_colored(f"❌ [{timestamp}] Sync failed", "red")
            if not self.quiet:
                for error in result.errors[:3]:
                    print(f"   - {error}")
        print()

    def show_next_run(self, next_time: datetime) -> None:
        """Show next run time."""
        if self.quiet:
            return

        print(f"   Next sync: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

    def show_stop(self, stats: ScheduleStats) -> None:
        """Show scheduler stop message."""
        print()
        self._print_colored("🛑 Scheduled Sync Stopped", "cyan", bold=True)
        print(f"   Uptime: {stats.uptime_formatted}")
        print(f"   Total runs: {stats.runs_completed}")
        print(f"   Successful: {stats.runs_successful}")
        print(f"   Failed: {stats.runs_failed}")
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
