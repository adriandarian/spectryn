"""
Time Tracking Sync - Parse/sync time estimates and logged time.

This module provides comprehensive time tracking synchronization:
- Parse time estimates from markdown (e.g., "2h", "1d", "30m")
- Sync original and remaining estimates to/from trackers
- Sync work logs/time entries
- Track time spent across stories and subtasks
- Support multiple time formats (hours, days, weeks)
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


class TimeUnit(Enum):
    """Time units for estimates and tracking."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


@dataclass
class TimeValue:
    """
    Represents a time value with unit.

    Can represent time estimates, time spent, or remaining time.
    """

    value: float
    unit: TimeUnit = TimeUnit.HOURS

    # Standard conversion factors (configurable per organization)
    MINUTES_PER_HOUR: int = 60
    HOURS_PER_DAY: int = 8  # Work day
    DAYS_PER_WEEK: int = 5  # Work week

    def to_minutes(self) -> int:
        """Convert to minutes."""
        if self.unit == TimeUnit.MINUTES:
            return int(self.value)
        if self.unit == TimeUnit.HOURS:
            return int(self.value * self.MINUTES_PER_HOUR)
        if self.unit == TimeUnit.DAYS:
            return int(self.value * self.HOURS_PER_DAY * self.MINUTES_PER_HOUR)
        if self.unit == TimeUnit.WEEKS:
            return int(self.value * self.DAYS_PER_WEEK * self.HOURS_PER_DAY * self.MINUTES_PER_HOUR)
        return 0

    def to_hours(self) -> float:
        """Convert to hours."""
        return self.to_minutes() / self.MINUTES_PER_HOUR

    def to_days(self) -> float:
        """Convert to work days."""
        return self.to_hours() / self.HOURS_PER_DAY

    def to_jira_format(self) -> str:
        """
        Convert to Jira time tracking format.

        Jira accepts: 2w, 3d, 4h, 45m
        """
        minutes = self.to_minutes()
        if minutes == 0:
            return "0m"

        parts = []
        # Weeks
        weeks = minutes // (self.DAYS_PER_WEEK * self.HOURS_PER_DAY * self.MINUTES_PER_HOUR)
        if weeks > 0:
            parts.append(f"{weeks}w")
            minutes %= self.DAYS_PER_WEEK * self.HOURS_PER_DAY * self.MINUTES_PER_HOUR

        # Days
        days = minutes // (self.HOURS_PER_DAY * self.MINUTES_PER_HOUR)
        if days > 0:
            parts.append(f"{days}d")
            minutes %= self.HOURS_PER_DAY * self.MINUTES_PER_HOUR

        # Hours
        hours = minutes // self.MINUTES_PER_HOUR
        if hours > 0:
            parts.append(f"{hours}h")
            minutes %= self.MINUTES_PER_HOUR

        # Minutes (only if no larger units or if there's a remainder)
        if minutes > 0 or not parts:
            parts.append(f"{minutes}m")

        return " ".join(parts)

    def to_display(self) -> str:
        """Convert to human-readable display format."""
        if self.unit == TimeUnit.MINUTES:
            return f"{int(self.value)}m"
        if self.unit == TimeUnit.HOURS:
            return f"{self.value:.1f}h" if self.value != int(self.value) else f"{int(self.value)}h"
        if self.unit == TimeUnit.DAYS:
            return f"{self.value:.1f}d" if self.value != int(self.value) else f"{int(self.value)}d"
        if self.unit == TimeUnit.WEEKS:
            return f"{self.value:.1f}w" if self.value != int(self.value) else f"{int(self.value)}w"
        return str(self.value)

    @classmethod
    def from_minutes(cls, minutes: int) -> "TimeValue":
        """Create from minutes value."""
        return cls(value=float(minutes), unit=TimeUnit.MINUTES)

    @classmethod
    def from_hours(cls, hours: float) -> "TimeValue":
        """Create from hours value."""
        return cls(value=hours, unit=TimeUnit.HOURS)

    @classmethod
    def parse(cls, text: str) -> "TimeValue | None":
        """
        Parse a time value from text.

        Supports formats:
        - "2h", "2 hours", "2hrs"
        - "30m", "30 minutes", "30min"
        - "1d", "1 day", "1 days"
        - "1w", "1 week", "1 weeks"
        - "2h 30m" (combined)
        - "1.5h" (decimal)

        Returns:
            TimeValue or None if parsing fails
        """
        if not text:
            return None

        text = text.strip().lower()

        # Try combined format first (e.g., "2h 30m", "1d 4h")
        total_minutes = 0
        combined_pattern = r"(\d+(?:\.\d+)?)\s*(w|d|h|m|weeks?|days?|hours?|hrs?|minutes?|mins?)"
        matches = re.findall(combined_pattern, text)

        if matches:
            for value_str, unit_str in matches:
                value = float(value_str)
                if unit_str.startswith("w"):
                    total_minutes += int(value * 5 * 8 * 60)  # weeks
                elif unit_str.startswith("d"):
                    total_minutes += int(value * 8 * 60)  # days
                elif unit_str.startswith("h"):
                    total_minutes += int(value * 60)  # hours
                else:  # minutes
                    total_minutes += int(value)

            # Return in most appropriate unit
            if total_minutes >= 5 * 8 * 60:  # >= 1 week
                return cls(value=total_minutes / (5 * 8 * 60), unit=TimeUnit.WEEKS)
            if total_minutes >= 8 * 60:  # >= 1 day
                return cls(value=total_minutes / (8 * 60), unit=TimeUnit.DAYS)
            if total_minutes >= 60:  # >= 1 hour
                return cls(value=total_minutes / 60, unit=TimeUnit.HOURS)
            return cls(value=float(total_minutes), unit=TimeUnit.MINUTES)

        # Try plain number (assume hours)
        try:
            value = float(text)
            return cls(value=value, unit=TimeUnit.HOURS)
        except ValueError:
            pass

        return None


@dataclass
class WorkLogEntry:
    """
    Represents a time log/work entry.

    Tracks actual time spent on a task.
    """

    id: str = ""
    duration: TimeValue | None = None
    started: datetime | None = None
    ended: datetime | None = None
    comment: str = ""
    author: str | None = None

    # Sync metadata
    remote_id: str | None = None
    synced_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "duration_minutes": self.duration.to_minutes() if self.duration else None,
            "started": self.started.isoformat() if self.started else None,
            "ended": self.ended.isoformat() if self.ended else None,
            "comment": self.comment,
            "author": self.author,
            "remote_id": self.remote_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkLogEntry":
        """Create from dictionary."""
        duration = None
        if data.get("duration_minutes"):
            duration = TimeValue.from_minutes(data["duration_minutes"])

        started = None
        if data.get("started"):
            started = datetime.fromisoformat(data["started"])

        ended = None
        if data.get("ended"):
            ended = datetime.fromisoformat(data["ended"])

        return cls(
            id=data.get("id", ""),
            duration=duration,
            started=started,
            ended=ended,
            comment=data.get("comment", ""),
            author=data.get("author"),
            remote_id=data.get("remote_id"),
        )


@dataclass
class TimeTrackingInfo:
    """
    Complete time tracking information for a story/issue.

    Includes estimates, time spent, and work log entries.
    """

    story_id: str
    issue_key: str | None = None

    # Estimates
    original_estimate: TimeValue | None = None
    remaining_estimate: TimeValue | None = None

    # Aggregated time spent
    time_spent: TimeValue | None = None

    # Work log entries
    work_logs: list[WorkLogEntry] = field(default_factory=list)

    # Sync metadata
    last_synced: datetime | None = None

    @property
    def total_logged_minutes(self) -> int:
        """Calculate total logged time from work logs."""
        return sum(wl.duration.to_minutes() for wl in self.work_logs if wl.duration)

    @property
    def progress_percentage(self) -> float | None:
        """Calculate progress percentage based on estimates and time spent."""
        if not self.original_estimate or self.original_estimate.to_minutes() == 0:
            return None

        spent = self.time_spent.to_minutes() if self.time_spent else 0
        return min(100.0, (spent / self.original_estimate.to_minutes()) * 100)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "issue_key": self.issue_key,
            "original_estimate_minutes": (
                self.original_estimate.to_minutes() if self.original_estimate else None
            ),
            "remaining_estimate_minutes": (
                self.remaining_estimate.to_minutes() if self.remaining_estimate else None
            ),
            "time_spent_minutes": self.time_spent.to_minutes() if self.time_spent else None,
            "work_logs": [wl.to_dict() for wl in self.work_logs],
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimeTrackingInfo":
        """Create from dictionary."""
        original = None
        if data.get("original_estimate_minutes"):
            original = TimeValue.from_minutes(data["original_estimate_minutes"])

        remaining = None
        if data.get("remaining_estimate_minutes"):
            remaining = TimeValue.from_minutes(data["remaining_estimate_minutes"])

        spent = None
        if data.get("time_spent_minutes"):
            spent = TimeValue.from_minutes(data["time_spent_minutes"])

        work_logs = [WorkLogEntry.from_dict(wl) for wl in data.get("work_logs", [])]

        return cls(
            story_id=data.get("story_id", ""),
            issue_key=data.get("issue_key"),
            original_estimate=original,
            remaining_estimate=remaining,
            time_spent=spent,
            work_logs=work_logs,
        )


@dataclass
class TimeTrackingSyncConfig:
    """Configuration for time tracking sync."""

    enabled: bool = True
    sync_estimates: bool = True
    sync_work_logs: bool = True

    # Work day settings (for conversions)
    hours_per_day: int = 8
    days_per_week: int = 5

    # Sync behavior
    push_estimates: bool = True  # Push estimates to tracker
    pull_estimates: bool = True  # Pull estimates from tracker
    push_work_logs: bool = False  # Push work logs (usually read-only from tracker)
    pull_work_logs: bool = True  # Pull work logs from tracker

    # Default estimate for stories without one
    default_estimate: str | None = None  # e.g., "1d"


class TimeTrackingExtractor:
    """Extract time tracking information from markdown content."""

    # Patterns for time values in markdown
    TIME_ESTIMATE_PATTERNS = [
        # | **Time Estimate** | 2h |
        r"\|\s*\*\*(?:Time\s*)?Estimate\*\*\s*\|\s*([^\|]+)\s*\|",
        # | **Original Estimate** | 4h |
        r"\|\s*\*\*Original\s*Estimate\*\*\s*\|\s*([^\|]+)\s*\|",
        # **Estimate:** 2h
        r"\*\*(?:Time\s*)?Estimate:\*\*\s*(.+?)(?:\n|$)",
        # Estimate:: 2h (Obsidian dataview)
        r"(?:Time\s*)?Estimate::\s*(.+?)(?:\n|$)",
    ]

    REMAINING_ESTIMATE_PATTERNS = [
        r"\|\s*\*\*Remaining(?:\s*Estimate)?\*\*\s*\|\s*([^\|]+)\s*\|",
        r"\*\*Remaining(?:\s*Estimate)?:\*\*\s*(.+?)(?:\n|$)",
        r"Remaining(?:\s*Estimate)?::\s*(.+?)(?:\n|$)",
    ]

    TIME_SPENT_PATTERNS = [
        r"\|\s*\*\*(?:Time\s*)?Spent\*\*\s*\|\s*([^\|]+)\s*\|",
        r"\|\s*\*\*Logged(?:\s*Time)?\*\*\s*\|\s*([^\|]+)\s*\|",
        r"\*\*(?:Time\s*)?Spent:\*\*\s*(.+?)(?:\n|$)",
        r"(?:Time\s*)?Spent::\s*(.+?)(?:\n|$)",
    ]

    # Work log section pattern
    WORK_LOG_SECTION = re.compile(
        r"#{2,4}\s*(?:Work\s*Log|Time\s*Log|Time\s*Entries)\s*\n([\s\S]*?)(?=#{2,4}|\Z)",
        re.IGNORECASE,
    )

    # Work log entry pattern (table row or list item)
    WORK_LOG_ENTRY = re.compile(
        r"[-*]\s*(?:(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s*[-–:])?\s*"
        r"(\d+(?:\.\d+)?[hmdw])\s*(?:[-–:]\s*(.+?))?$",
        re.MULTILINE,
    )

    def __init__(self, config: TimeTrackingSyncConfig | None = None):
        """Initialize the extractor."""
        self.config = config or TimeTrackingSyncConfig()

    def extract_from_content(self, content: str, story_id: str) -> TimeTrackingInfo:
        """
        Extract time tracking info from markdown content.

        Args:
            content: Markdown content
            story_id: Story ID for the tracking info

        Returns:
            TimeTrackingInfo with parsed data
        """
        info = TimeTrackingInfo(story_id=story_id)

        # Extract original estimate
        for pattern in self.TIME_ESTIMATE_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                estimate = TimeValue.parse(match.group(1).strip())
                if estimate:
                    info.original_estimate = estimate
                    break

        # Extract remaining estimate
        for pattern in self.REMAINING_ESTIMATE_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                estimate = TimeValue.parse(match.group(1).strip())
                if estimate:
                    info.remaining_estimate = estimate
                    break

        # Extract time spent
        for pattern in self.TIME_SPENT_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                spent = TimeValue.parse(match.group(1).strip())
                if spent:
                    info.time_spent = spent
                    break

        # Extract work log entries
        section_match = self.WORK_LOG_SECTION.search(content)
        if section_match:
            section_content = section_match.group(1)
            for match in self.WORK_LOG_ENTRY.finditer(section_content):
                date_str, time_str, duration_str, comment = match.groups()

                duration = TimeValue.parse(duration_str)
                if not duration:
                    continue

                started = None
                if date_str:
                    try:
                        if time_str:
                            started = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                        else:
                            started = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        pass

                info.work_logs.append(
                    WorkLogEntry(
                        duration=duration,
                        started=started,
                        comment=comment.strip() if comment else "",
                    )
                )

        return info


@dataclass
class TimeTrackingSyncResult:
    """Result of time tracking sync operation."""

    story_id: str
    issue_key: str | None = None

    # What was synced
    estimate_pushed: bool = False
    estimate_pulled: bool = False
    work_logs_pushed: int = 0
    work_logs_pulled: int = 0

    # Values
    local_estimate: TimeValue | None = None
    remote_estimate: TimeValue | None = None
    local_spent: TimeValue | None = None
    remote_spent: TimeValue | None = None

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if sync was successful."""
        return len(self.errors) == 0


class TimeTrackingSyncer:
    """
    Synchronize time tracking between markdown and issue trackers.

    Supports:
    - Syncing time estimates (original and remaining)
    - Pulling work logs from trackers
    - Aggregating time across stories
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: TimeTrackingSyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or TimeTrackingSyncConfig()
        self.logger = logging.getLogger("TimeTrackingSyncer")

    def sync_story_time(
        self,
        story_id: str,
        issue_key: str,
        local_info: TimeTrackingInfo | None,
        dry_run: bool = True,
    ) -> TimeTrackingSyncResult:
        """
        Sync time tracking for a single story/issue.

        Args:
            story_id: Local story ID
            issue_key: Remote issue key
            local_info: Time tracking info extracted from markdown
            dry_run: If True, don't make changes

        Returns:
            TimeTrackingSyncResult
        """
        result = TimeTrackingSyncResult(story_id=story_id, issue_key=issue_key)

        if not self.config.enabled:
            return result

        # Get remote time tracking info
        remote_info = self._get_remote_time_tracking(issue_key)

        # Record values for comparison
        if local_info:
            result.local_estimate = local_info.original_estimate
            result.local_spent = local_info.time_spent

        if remote_info:
            result.remote_estimate = remote_info.original_estimate
            result.remote_spent = remote_info.time_spent

        # Push estimates to tracker
        if self.config.push_estimates and local_info and local_info.original_estimate:
            if dry_run:
                self.logger.info(
                    f"[DRY-RUN] Would set estimate for {issue_key} to "
                    f"{local_info.original_estimate.to_jira_format()}"
                )
            else:
                success = self._set_remote_estimate(issue_key, local_info.original_estimate)
                result.estimate_pushed = success
                if not success:
                    result.errors.append(f"Failed to push estimate to {issue_key}")

        # Pull work logs from tracker
        if self.config.pull_work_logs:
            try:
                work_logs = self._get_remote_work_logs(issue_key)
                result.work_logs_pulled = len(work_logs)
                if local_info:
                    local_info.work_logs = work_logs
            except Exception as e:
                result.errors.append(f"Failed to pull work logs: {e}")

        return result

    def _get_remote_time_tracking(self, issue_key: str) -> TimeTrackingInfo | None:
        """Get time tracking info from remote tracker."""
        try:
            # Try using tracker's get_time_tracking if available
            if hasattr(self.tracker, "get_time_tracking"):
                data = self.tracker.get_time_tracking(issue_key)
                info = TimeTrackingInfo(story_id="", issue_key=issue_key)

                if data.get("estimate_minutes"):
                    info.original_estimate = TimeValue.from_minutes(data["estimate_minutes"])
                if data.get("remaining_minutes"):
                    info.remaining_estimate = TimeValue.from_minutes(data["remaining_minutes"])
                if data.get("spent_minutes"):
                    info.time_spent = TimeValue.from_minutes(data["spent_minutes"])

                return info

            # Fallback: try to get from issue fields
            issue = self.tracker.get_issue(issue_key)
            info = TimeTrackingInfo(story_id="", issue_key=issue_key)

            # Try common time tracking field names
            if hasattr(issue, "time_estimate"):
                info.original_estimate = TimeValue.from_minutes(issue.time_estimate or 0)
            if hasattr(issue, "time_spent"):
                info.time_spent = TimeValue.from_minutes(issue.time_spent or 0)

            return info
        except Exception as e:
            self.logger.warning(f"Failed to get time tracking for {issue_key}: {e}")
            return None

    def _set_remote_estimate(self, issue_key: str, estimate: TimeValue) -> bool:
        """Set time estimate on remote tracker."""
        try:
            if hasattr(self.tracker, "set_time_estimate"):
                return self.tracker.set_time_estimate(issue_key, estimate.to_minutes())

            # Fallback: try updating via generic field update
            if hasattr(self.tracker, "update_time_tracking"):
                return self.tracker.update_time_tracking(
                    issue_key, original_estimate=estimate.to_jira_format()
                )

            self.logger.warning(f"Tracker {self.tracker.name} doesn't support time estimates")
            return False
        except Exception as e:
            self.logger.error(f"Failed to set estimate for {issue_key}: {e}")
            return False

    def _get_remote_work_logs(self, issue_key: str) -> list[WorkLogEntry]:
        """Get work logs from remote tracker."""
        try:
            if hasattr(self.tracker, "get_work_logs"):
                raw_logs = self.tracker.get_work_logs(issue_key)
                return [self._parse_work_log(wl) for wl in raw_logs]

            if hasattr(self.tracker, "get_time_entries"):
                raw_logs = self.tracker.get_time_entries(issue_key)
                return [self._parse_work_log(wl) for wl in raw_logs]

            return []
        except Exception as e:
            self.logger.warning(f"Failed to get work logs for {issue_key}: {e}")
            return []

    def _parse_work_log(self, data: dict[str, Any]) -> WorkLogEntry:
        """Parse a work log entry from tracker data."""
        # Handle different tracker formats
        duration_seconds = data.get("timeSpentSeconds", data.get("duration", 0))
        duration_minutes = duration_seconds // 60 if duration_seconds else 0

        started = None
        started_str = data.get("started", data.get("start"))
        if started_str:
            from contextlib import suppress

            with suppress(ValueError):
                started = datetime.fromisoformat(started_str.replace("Z", "+00:00"))

        return WorkLogEntry(
            id=str(data.get("id", "")),
            duration=TimeValue.from_minutes(duration_minutes) if duration_minutes else None,
            started=started,
            comment=data.get("comment", data.get("description", "")),
            author=data.get("author", {}).get("displayName", data.get("author_name")),
            remote_id=str(data.get("id", "")),
        )


def parse_time_estimate(text: str) -> TimeValue | None:
    """
    Parse a time estimate from text.

    Convenience function for parsing time values.

    Args:
        text: Time string (e.g., "2h", "1d 4h", "30m")

    Returns:
        TimeValue or None if parsing fails
    """
    return TimeValue.parse(text)


def format_time_for_markdown(minutes: int, compact: bool = True) -> str:
    """
    Format time value for markdown display.

    Args:
        minutes: Time in minutes
        compact: Use compact format (e.g., "2h" vs "2 hours")

    Returns:
        Formatted time string
    """
    value = TimeValue.from_minutes(minutes)
    return value.to_display() if compact else value.to_jira_format()


def extract_time_tracking(
    content: str, story_id: str, config: TimeTrackingSyncConfig | None = None
) -> TimeTrackingInfo:
    """
    Convenience function to extract time tracking from markdown.

    Args:
        content: Markdown content
        story_id: Story ID
        config: Optional config

    Returns:
        TimeTrackingInfo with parsed data
    """
    extractor = TimeTrackingExtractor(config)
    return extractor.extract_from_content(content, story_id)
