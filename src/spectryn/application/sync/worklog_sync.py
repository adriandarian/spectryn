"""
Worklog Sync - Sync time logs between markdown and issue trackers.

This module provides comprehensive worklog synchronization:
- Parse work log entries from markdown
- Push work logs to trackers
- Pull work logs from trackers
- Bidirectional sync with conflict detection
- Worklog formatting for markdown output
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .time_tracking import TimeValue, WorkLogEntry


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


@dataclass
class WorklogSyncConfig:
    """Configuration for worklog synchronization."""

    enabled: bool = True

    # Sync direction
    push_to_tracker: bool = True  # Push local worklogs to tracker
    pull_from_tracker: bool = True  # Pull remote worklogs to markdown

    # Conflict handling
    skip_duplicates: bool = True  # Skip entries that appear to be duplicates
    duplicate_threshold_minutes: int = 5  # Time window for duplicate detection

    # Author filtering
    filter_by_author: str | None = None  # Only sync logs from specific author
    include_all_authors: bool = True  # Include all authors in pull

    # Formatting
    date_format: str = "%Y-%m-%d"  # Date format for markdown
    include_author: bool = True  # Include author in markdown output
    include_comment: bool = True  # Include comment in markdown output


@dataclass
class WorklogChange:
    """A single worklog change."""

    entry: WorkLogEntry
    action: str  # "create", "update", "delete", "pull"
    success: bool = True
    error: str | None = None


@dataclass
class WorklogSyncResult:
    """Result of worklog sync operation."""

    success: bool = True
    dry_run: bool = False

    # Story info
    story_id: str = ""
    issue_key: str = ""

    # Counts
    worklogs_pushed: int = 0
    worklogs_pulled: int = 0
    worklogs_skipped: int = 0
    worklogs_failed: int = 0

    # Changes
    changes: list[WorklogChange] = field(default_factory=list)

    # Errors
    errors: list[str] = field(default_factory=list)

    def add_pushed(self, entry: WorkLogEntry) -> None:
        """Record a pushed worklog."""
        self.worklogs_pushed += 1
        self.changes.append(WorklogChange(entry=entry, action="create"))

    def add_pulled(self, entry: WorkLogEntry) -> None:
        """Record a pulled worklog."""
        self.worklogs_pulled += 1
        self.changes.append(WorklogChange(entry=entry, action="pull"))

    def add_skipped(self, entry: WorkLogEntry, reason: str = "") -> None:
        """Record a skipped worklog."""
        self.worklogs_skipped += 1
        self.changes.append(WorklogChange(entry=entry, action="skip", error=reason))

    def add_failed(self, entry: WorkLogEntry, error: str) -> None:
        """Record a failed worklog."""
        self.worklogs_failed += 1
        self.success = False
        self.changes.append(WorklogChange(entry=entry, action="create", success=False, error=error))
        self.errors.append(error)


class WorklogExtractor:
    """Extract work log entries from markdown content."""

    # Patterns for work logs in markdown
    WORKLOG_PATTERNS = [
        # - 2024-01-15 - 2h - Comment
        r"-\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*-\s*(.+)",
        # - 2024-01-15: 2h - Comment
        r"-\s*(\d{4}-\d{2}-\d{2}):\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*-\s*(.+)",
        # - 2h - Comment (no date, assume today)
        r"-\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*-\s*(.+)",
        # | 2024-01-15 | 2h | Comment | (table format)
        r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*\|\s*([^|]+)\s*\|",
    ]

    # Section header patterns
    SECTION_PATTERNS = [
        r"#{2,4}\s*(?:Work\s*Log|Time\s*Log|Logged\s*Time|Time\s*Entries)\s*\n([\s\S]*?)(?=#{2,4}|\Z)",
    ]

    def __init__(self, config: WorklogSyncConfig | None = None):
        """Initialize the extractor."""
        self.config = config or WorklogSyncConfig()
        self.logger = logging.getLogger("WorklogExtractor")

    def extract_from_content(self, content: str, story_id: str) -> list[WorkLogEntry]:
        """
        Extract work log entries from markdown content.

        Args:
            content: Markdown content
            story_id: Story ID

        Returns:
            List of WorkLogEntry objects
        """
        entries: list[WorkLogEntry] = []

        # Look for worklog section first
        for section_pattern in self.SECTION_PATTERNS:
            for section_match in re.finditer(section_pattern, content, re.IGNORECASE):
                section_content = section_match.group(1)
                section_entries = self._extract_from_section(section_content)
                entries.extend(section_entries)

        # If no section found, try to find inline worklogs
        if not entries:
            entries = self._extract_inline(content)

        return entries

    def _extract_from_section(self, section_content: str) -> list[WorkLogEntry]:
        """Extract worklogs from a section."""
        entries = []
        matched_positions: set[int] = set()

        # Try date-time-comment pattern first (most specific)
        pattern1 = r"-\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*-\s*(.+)"
        for match in re.finditer(pattern1, section_content):
            date_str = match.group(1)
            duration_str = match.group(2)
            comment = match.group(3).strip()

            entry = self._create_entry(date_str, duration_str, comment)
            if entry:
                entries.append(entry)
                matched_positions.add(match.start())

        # Try table format
        table_pattern = r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        for match in re.finditer(table_pattern, section_content):
            if match.start() in matched_positions:
                continue

            date_str = match.group(1)
            duration_str = match.group(2).strip()
            comment = match.group(3).strip()

            # Skip header row
            if "duration" in duration_str.lower() or "time" in duration_str.lower():
                continue

            entry = self._create_entry(date_str, duration_str, comment)
            if entry:
                entries.append(entry)
                matched_positions.add(match.start())

        # Only try simple pattern if no date patterns matched
        if not entries:
            simple_pattern = r"-\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)\s*-\s*(.+)"
            for match in re.finditer(simple_pattern, section_content):
                duration_str = match.group(1)
                comment = match.group(2).strip()

                entry = self._create_entry(None, duration_str, comment)
                if entry:
                    entries.append(entry)

        return entries

    def _extract_inline(self, content: str) -> list[WorkLogEntry]:
        """Extract inline worklog entries."""
        entries = []

        # Look for explicit worklog markers
        inline_pattern = r"\*\*(?:Logged|Time Spent):\*\*\s*(\d+(?:\.\d+)?[hmd](?:\s*\d+[hmd])?)"
        for match in re.finditer(inline_pattern, content, re.IGNORECASE):
            duration_str = match.group(1)
            entry = self._create_entry(None, duration_str, "")
            if entry:
                entries.append(entry)

        return entries

    def _create_entry(
        self,
        date_str: str | None,
        duration_str: str,
        comment: str,
    ) -> WorkLogEntry | None:
        """Create a WorkLogEntry from parsed values."""
        # Parse duration
        duration = TimeValue.parse(duration_str)
        if not duration:
            return None

        # Parse date
        started = None
        if date_str:
            from contextlib import suppress

            with suppress(ValueError):
                started = datetime.strptime(date_str, "%Y-%m-%d")

        return WorkLogEntry(
            id=f"local-{hash(f'{date_str}-{duration_str}-{comment}') % 10000:04d}",
            duration=duration,
            started=started,
            comment=comment,
        )


class WorklogSyncer:
    """
    Synchronize work logs between markdown and issue trackers.
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: WorklogSyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or WorklogSyncConfig()
        self.logger = logging.getLogger("WorklogSyncer")

    def sync_worklogs(
        self,
        story_id: str,
        issue_key: str,
        local_entries: list[WorkLogEntry],
        dry_run: bool = True,
    ) -> WorklogSyncResult:
        """
        Sync work logs for a story/issue.

        Args:
            story_id: Local story ID
            issue_key: Remote issue key
            local_entries: Work logs from markdown
            dry_run: If True, don't make changes

        Returns:
            WorklogSyncResult
        """
        result = WorklogSyncResult(
            dry_run=dry_run,
            story_id=story_id,
            issue_key=issue_key,
        )

        if not self.config.enabled:
            return result

        # Get remote worklogs
        remote_entries = self._get_remote_worklogs(issue_key)

        # Push local worklogs to tracker
        if self.config.push_to_tracker:
            for entry in local_entries:
                # Check for duplicates
                if self.config.skip_duplicates and self._is_duplicate(entry, remote_entries):
                    result.add_skipped(entry, "Duplicate entry")
                    continue

                # Push to tracker
                if dry_run:
                    self.logger.info(
                        f"[DRY-RUN] Would add worklog to {issue_key}: "
                        f"{entry.duration.to_display() if entry.duration else '?'}"
                    )
                    result.add_pushed(entry)
                else:
                    success = self._push_worklog(issue_key, entry)
                    if success:
                        result.add_pushed(entry)
                    else:
                        result.add_failed(entry, f"Failed to push to {issue_key}")

        # Pull remote worklogs
        if self.config.pull_from_tracker:
            for entry in remote_entries:
                # Filter by author if configured
                if self.config.filter_by_author:
                    if entry.author != self.config.filter_by_author:
                        continue

                # Check for duplicates
                if self.config.skip_duplicates and self._is_duplicate(entry, local_entries):
                    continue

                result.add_pulled(entry)

        return result

    def pull_worklogs(self, issue_key: str) -> list[WorkLogEntry]:
        """
        Pull all work logs from an issue.

        Args:
            issue_key: Issue key

        Returns:
            List of WorkLogEntry objects
        """
        return self._get_remote_worklogs(issue_key)

    def push_worklog(
        self,
        issue_key: str,
        entry: WorkLogEntry,
        dry_run: bool = True,
    ) -> bool:
        """
        Push a single worklog to the tracker.

        Args:
            issue_key: Issue key
            entry: Worklog entry
            dry_run: If True, don't make changes

        Returns:
            True if successful
        """
        if dry_run:
            self.logger.info(
                f"[DRY-RUN] Would add worklog to {issue_key}: "
                f"{entry.duration.to_display() if entry.duration else '?'}"
            )
            return True

        return self._push_worklog(issue_key, entry)

    def format_worklogs_markdown(self, entries: list[WorkLogEntry]) -> str:
        """
        Format work logs as markdown.

        Args:
            entries: List of worklog entries

        Returns:
            Markdown formatted string
        """
        if not entries:
            return ""

        lines = ["#### Work Log", ""]

        for entry in entries:
            date_str = ""
            if entry.started:
                date_str = entry.started.strftime(self.config.date_format)

            duration_str = entry.duration.to_display() if entry.duration else "?"

            parts = []
            if date_str:
                parts.append(date_str)
            parts.append(duration_str)

            if self.config.include_comment and entry.comment:
                parts.append(entry.comment)

            if self.config.include_author and entry.author:
                parts.append(f"(@{entry.author})")

            lines.append(f"- {' - '.join(parts)}")

        return "\n".join(lines)

    def _get_remote_worklogs(self, issue_key: str) -> list[WorkLogEntry]:
        """Get worklogs from the tracker."""
        try:
            if hasattr(self.tracker, "get_work_logs"):
                raw_logs = self.tracker.get_work_logs(issue_key)
                return [self._parse_remote_worklog(wl) for wl in raw_logs]
        except Exception as e:
            self.logger.error(f"Failed to get worklogs for {issue_key}: {e}")

        return []

    def _push_worklog(self, issue_key: str, entry: WorkLogEntry) -> bool:
        """Push a worklog to the tracker."""
        try:
            if hasattr(self.tracker, "add_work_log"):
                # Format duration for Jira
                time_spent = entry.duration.to_jira_format() if entry.duration else "1h"

                # Format start time
                started = None
                if entry.started:
                    started = entry.started.strftime("%Y-%m-%dT%H:%M:%S.000+0000")

                result = self.tracker.add_work_log(
                    issue_key=issue_key,
                    time_spent=time_spent,
                    started=started,
                    comment=entry.comment,
                )
                return result is not None

        except Exception as e:
            self.logger.error(f"Failed to push worklog to {issue_key}: {e}")

        return False

    def _parse_remote_worklog(self, data: dict[str, Any]) -> WorkLogEntry:
        """Parse a worklog from tracker response."""
        # Parse duration
        duration = None
        if data.get("timeSpentSeconds"):
            duration = TimeValue.from_minutes(data["timeSpentSeconds"] // 60)
        elif data.get("timeSpent"):
            duration = TimeValue.parse(data["timeSpent"])

        # Parse started time
        started = None
        started_str = data.get("started")
        if started_str:
            from contextlib import suppress

            with suppress(ValueError):
                # Handle Jira date format
                started = datetime.fromisoformat(started_str.replace("Z", "+00:00").split(".")[0])

        # Parse comment
        comment = ""
        if isinstance(data.get("comment"), dict):
            # ADF format
            content = data["comment"].get("content", [])
            if content:
                for block in content:
                    for item in block.get("content", []):
                        if item.get("type") == "text":
                            comment += item.get("text", "")
        elif isinstance(data.get("comment"), str):
            comment = data["comment"]

        # Get author
        author = None
        if data.get("author"):
            author = data["author"].get("displayName") or data["author"].get("name")

        return WorkLogEntry(
            id=str(data.get("id", "")),
            duration=duration,
            started=started,
            comment=comment,
            author=author,
            remote_id=str(data.get("id", "")),
        )

    def _is_duplicate(self, entry: WorkLogEntry, existing: list[WorkLogEntry]) -> bool:
        """Check if a worklog entry is a duplicate."""
        if not entry.duration:
            return False

        entry_minutes = entry.duration.to_minutes()

        for existing_entry in existing:
            if not existing_entry.duration:
                continue

            existing_minutes = existing_entry.duration.to_minutes()

            # Check duration match
            if abs(entry_minutes - existing_minutes) > self.config.duplicate_threshold_minutes:
                continue

            # Check date match
            if entry.started and existing_entry.started:
                if entry.started.date() != existing_entry.started.date():
                    continue

            # Check comment match (if both have comments)
            if entry.comment and existing_entry.comment:
                if entry.comment.lower() == existing_entry.comment.lower():
                    return True

            # If duration and date match, consider it a duplicate
            if entry.started and existing_entry.started:
                if entry.started.date() == existing_entry.started.date():
                    return True

        return False


def extract_worklogs(content: str, story_id: str) -> list[WorkLogEntry]:
    """
    Convenience function to extract worklogs from markdown.

    Args:
        content: Markdown content
        story_id: Story ID

    Returns:
        List of WorkLogEntry objects
    """
    extractor = WorklogExtractor()
    return extractor.extract_from_content(content, story_id)


def format_worklogs_as_markdown(
    entries: list[WorkLogEntry],
    config: WorklogSyncConfig | None = None,
) -> str:
    """
    Format worklogs as markdown string.

    Args:
        entries: List of worklog entries
        config: Optional config

    Returns:
        Markdown formatted string
    """
    syncer = WorklogSyncer(None, config)  # type: ignore
    return syncer.format_worklogs_markdown(entries)
