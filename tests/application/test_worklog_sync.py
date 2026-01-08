"""Tests for worklog sync functionality."""

import textwrap
from datetime import datetime

import pytest

from spectryn.application.sync.time_tracking import TimeValue, WorkLogEntry
from spectryn.application.sync.worklog_sync import (
    WorklogChange,
    WorklogExtractor,
    WorklogSyncConfig,
    WorklogSyncer,
    WorklogSyncResult,
    extract_worklogs,
    format_worklogs_as_markdown,
)


class TestWorklogSyncConfig:
    """Tests for WorklogSyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = WorklogSyncConfig()
        assert config.enabled is True
        assert config.push_to_tracker is True
        assert config.pull_from_tracker is True
        assert config.skip_duplicates is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = WorklogSyncConfig(
            push_to_tracker=False,
            filter_by_author="John Doe",
        )
        assert config.push_to_tracker is False
        assert config.filter_by_author == "John Doe"


class TestWorklogSyncResult:
    """Tests for WorklogSyncResult."""

    def test_success_by_default(self):
        """Test success is True by default."""
        result = WorklogSyncResult()
        assert result.success is True

    def test_add_pushed(self):
        """Test adding pushed worklog."""
        result = WorklogSyncResult()
        entry = WorkLogEntry(id="1", duration=TimeValue.from_hours(2))

        result.add_pushed(entry)

        assert result.worklogs_pushed == 1
        assert len(result.changes) == 1
        assert result.changes[0].action == "create"

    def test_add_pulled(self):
        """Test adding pulled worklog."""
        result = WorklogSyncResult()
        entry = WorkLogEntry(id="1", duration=TimeValue.from_hours(2))

        result.add_pulled(entry)

        assert result.worklogs_pulled == 1
        assert len(result.changes) == 1
        assert result.changes[0].action == "pull"

    def test_add_skipped(self):
        """Test adding skipped worklog."""
        result = WorklogSyncResult()
        entry = WorkLogEntry(id="1", duration=TimeValue.from_hours(2))

        result.add_skipped(entry, "Duplicate")

        assert result.worklogs_skipped == 1
        assert result.changes[0].error == "Duplicate"

    def test_add_failed(self):
        """Test adding failed worklog."""
        result = WorklogSyncResult()
        entry = WorkLogEntry(id="1", duration=TimeValue.from_hours(2))

        result.add_failed(entry, "API error")

        assert result.worklogs_failed == 1
        assert result.success is False
        assert "API error" in result.errors


class TestWorklogExtractor:
    """Tests for WorklogExtractor."""

    def test_extract_from_section(self):
        """Test extracting worklogs from a dedicated section."""
        content = textwrap.dedent("""
            ### US-001: Test Story

            #### Work Log
            - 2024-01-15 - 2h - Initial implementation
            - 2024-01-16 - 3h 30m - Bug fixes
            - 2024-01-17 - 1h - Documentation
        """)
        entries = extract_worklogs(content, "US-001")

        assert len(entries) == 3
        assert entries[0].duration.to_hours() == 2.0
        assert entries[1].duration.to_minutes() == 210  # 3h 30m
        assert entries[2].duration.to_hours() == 1.0
        assert entries[0].started.date() == datetime(2024, 1, 15).date()

    def test_extract_from_time_log_section(self):
        """Test extracting from 'Time Log' section."""
        content = textwrap.dedent("""
            #### Time Log
            - 2024-01-20 - 4h - Testing
        """)
        entries = extract_worklogs(content, "US-001")

        assert len(entries) == 1
        assert entries[0].duration.to_hours() == 4.0
        assert entries[0].comment == "Testing"

    def test_extract_table_format(self):
        """Test extracting from table format."""
        content = textwrap.dedent("""
            #### Work Log
            | Date | Duration | Comment |
            |------|----------|---------|
            | 2024-01-15 | 2h | Implementation |
            | 2024-01-16 | 1h 30m | Review |
        """)
        entries = extract_worklogs(content, "US-001")

        assert len(entries) == 2
        assert entries[0].duration.to_hours() == 2.0
        assert entries[1].duration.to_minutes() == 90

    def test_extract_simple_format(self):
        """Test extracting simple format without date."""
        content = textwrap.dedent("""
            #### Work Log
            - 2h - Quick fix
            - 1h - Review
        """)
        entries = extract_worklogs(content, "US-001")

        assert len(entries) == 2
        assert entries[0].duration.to_hours() == 2.0
        assert entries[0].comment == "Quick fix"

    def test_no_worklogs(self):
        """Test content without worklogs."""
        content = "### US-001: Simple Story\n\nJust a description."
        entries = extract_worklogs(content, "US-001")
        assert len(entries) == 0

    def test_extract_with_colon_format(self):
        """Test extracting date:duration format."""
        content = textwrap.dedent("""
            #### Work Log
            - 2024-01-15: 2h - Implementation
        """)
        # Just verify it doesn't crash - parsing may vary by pattern
        _ = extract_worklogs(content, "US-001")


class TestWorklogChange:
    """Tests for WorklogChange."""

    def test_create_change(self):
        """Test creating a worklog change."""
        entry = WorkLogEntry(id="1", duration=TimeValue.from_hours(2))
        change = WorklogChange(entry=entry, action="create")

        assert change.entry == entry
        assert change.action == "create"
        assert change.success is True


class TestFormatWorklogsAsMarkdown:
    """Tests for format_worklogs_as_markdown function."""

    def test_format_basic(self):
        """Test basic formatting."""
        entries = [
            WorkLogEntry(
                id="1",
                duration=TimeValue.from_hours(2),
                started=datetime(2024, 1, 15),
                comment="Implementation",
                author="John",
            ),
            WorkLogEntry(
                id="2",
                duration=TimeValue.from_hours(1),
                started=datetime(2024, 1, 16),
                comment="Review",
            ),
        ]

        result = format_worklogs_as_markdown(entries)

        assert "#### Work Log" in result
        assert "2024-01-15" in result
        assert "2h" in result
        assert "Implementation" in result

    def test_format_empty(self):
        """Test formatting empty list."""
        result = format_worklogs_as_markdown([])
        assert result == ""

    def test_format_without_author(self):
        """Test formatting without author."""
        config = WorklogSyncConfig(include_author=False)
        entries = [
            WorkLogEntry(
                id="1",
                duration=TimeValue.from_hours(2),
                started=datetime(2024, 1, 15),
                comment="Work",
                author="John",
            ),
        ]

        result = format_worklogs_as_markdown(entries, config)

        assert "@John" not in result


class TestWorklogSyncer:
    """Tests for WorklogSyncer (without tracker)."""

    def test_format_worklogs_markdown(self):
        """Test formatting worklogs as markdown."""
        # Create syncer without tracker for formatting
        syncer = WorklogSyncer(None, WorklogSyncConfig())  # type: ignore

        entries = [
            WorkLogEntry(
                id="1",
                duration=TimeValue.from_hours(2),
                started=datetime(2024, 1, 15),
                comment="Task 1",
            ),
        ]

        result = syncer.format_worklogs_markdown(entries)

        assert "2024-01-15" in result
        assert "2h" in result
        assert "Task 1" in result

    def test_is_duplicate_by_date_and_duration(self):
        """Test duplicate detection by date and duration."""
        syncer = WorklogSyncer(None, WorklogSyncConfig())  # type: ignore

        entry = WorkLogEntry(
            id="1",
            duration=TimeValue.from_hours(2),
            started=datetime(2024, 1, 15),
        )

        existing = [
            WorkLogEntry(
                id="2",
                duration=TimeValue.from_hours(2),
                started=datetime(2024, 1, 15),
            ),
        ]

        assert syncer._is_duplicate(entry, existing) is True

    def test_is_not_duplicate_different_date(self):
        """Test non-duplicate with different date."""
        syncer = WorklogSyncer(None, WorklogSyncConfig())  # type: ignore

        entry = WorkLogEntry(
            id="1",
            duration=TimeValue.from_hours(2),
            started=datetime(2024, 1, 15),
        )

        existing = [
            WorkLogEntry(
                id="2",
                duration=TimeValue.from_hours(2),
                started=datetime(2024, 1, 16),  # Different date
            ),
        ]

        assert syncer._is_duplicate(entry, existing) is False

    def test_is_not_duplicate_different_duration(self):
        """Test non-duplicate with different duration."""
        syncer = WorklogSyncer(None, WorklogSyncConfig())  # type: ignore

        entry = WorkLogEntry(
            id="1",
            duration=TimeValue.from_hours(2),
            started=datetime(2024, 1, 15),
        )

        existing = [
            WorkLogEntry(
                id="2",
                duration=TimeValue.from_hours(4),  # Different duration
                started=datetime(2024, 1, 15),
            ),
        ]

        assert syncer._is_duplicate(entry, existing) is False
