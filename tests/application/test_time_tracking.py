"""Tests for time tracking sync functionality."""

import textwrap
from datetime import datetime

import pytest

from spectryn.application.sync.time_tracking import (
    TimeTrackingExtractor,
    TimeTrackingInfo,
    TimeTrackingSyncConfig,
    TimeTrackingSyncer,
    TimeTrackingSyncResult,
    TimeUnit,
    TimeValue,
    WorkLogEntry,
    extract_time_tracking,
    format_time_for_markdown,
    parse_time_estimate,
)


class TestTimeUnit:
    """Tests for TimeUnit enum."""

    def test_all_units_exist(self):
        """Test all time units are defined."""
        assert TimeUnit.MINUTES.value == "minutes"
        assert TimeUnit.HOURS.value == "hours"
        assert TimeUnit.DAYS.value == "days"
        assert TimeUnit.WEEKS.value == "weeks"


class TestTimeValue:
    """Tests for TimeValue class."""

    def test_create_from_hours(self):
        """Test creating time value from hours."""
        tv = TimeValue(value=2.5, unit=TimeUnit.HOURS)
        assert tv.value == 2.5
        assert tv.unit == TimeUnit.HOURS

    def test_to_minutes_from_hours(self):
        """Test converting hours to minutes."""
        tv = TimeValue(value=2, unit=TimeUnit.HOURS)
        assert tv.to_minutes() == 120

    def test_to_minutes_from_days(self):
        """Test converting days to minutes (8-hour work day)."""
        tv = TimeValue(value=1, unit=TimeUnit.DAYS)
        assert tv.to_minutes() == 8 * 60  # 480 minutes

    def test_to_minutes_from_weeks(self):
        """Test converting weeks to minutes (5-day work week)."""
        tv = TimeValue(value=1, unit=TimeUnit.WEEKS)
        assert tv.to_minutes() == 5 * 8 * 60  # 2400 minutes

    def test_to_hours(self):
        """Test converting to hours."""
        tv = TimeValue(value=90, unit=TimeUnit.MINUTES)
        assert tv.to_hours() == 1.5

    def test_to_days(self):
        """Test converting to work days."""
        tv = TimeValue(value=16, unit=TimeUnit.HOURS)
        assert tv.to_days() == 2.0

    def test_to_jira_format_hours(self):
        """Test converting to Jira format (hours)."""
        tv = TimeValue(value=2, unit=TimeUnit.HOURS)
        assert tv.to_jira_format() == "2h"

    def test_to_jira_format_combined(self):
        """Test converting to Jira format (combined)."""
        tv = TimeValue(value=90, unit=TimeUnit.MINUTES)
        assert tv.to_jira_format() == "1h 30m"

    def test_to_jira_format_days(self):
        """Test converting to Jira format (days)."""
        tv = TimeValue(value=2, unit=TimeUnit.DAYS)
        assert tv.to_jira_format() == "2d"

    def test_to_jira_format_full(self):
        """Test converting to Jira format (weeks+days+hours+minutes)."""
        # 1 week + 2 days + 3 hours + 30 minutes
        minutes = 1 * 5 * 8 * 60 + 2 * 8 * 60 + 3 * 60 + 30
        tv = TimeValue.from_minutes(minutes)
        result = tv.to_jira_format()
        assert "1w" in result
        assert "2d" in result
        assert "3h" in result
        assert "30m" in result

    def test_to_display_hours(self):
        """Test display format for hours."""
        tv = TimeValue(value=2, unit=TimeUnit.HOURS)
        assert tv.to_display() == "2h"

    def test_to_display_decimal_hours(self):
        """Test display format for decimal hours."""
        tv = TimeValue(value=1.5, unit=TimeUnit.HOURS)
        assert tv.to_display() == "1.5h"

    def test_from_minutes_factory(self):
        """Test creating from minutes."""
        tv = TimeValue.from_minutes(90)
        assert tv.to_minutes() == 90
        assert tv.unit == TimeUnit.MINUTES

    def test_from_hours_factory(self):
        """Test creating from hours."""
        tv = TimeValue.from_hours(2.5)
        assert tv.to_hours() == 2.5
        assert tv.unit == TimeUnit.HOURS

    def test_parse_simple_hours(self):
        """Test parsing simple hour format."""
        tv = TimeValue.parse("2h")
        assert tv is not None
        assert tv.to_hours() == 2.0

    def test_parse_simple_minutes(self):
        """Test parsing simple minute format."""
        tv = TimeValue.parse("30m")
        assert tv is not None
        assert tv.to_minutes() == 30

    def test_parse_simple_days(self):
        """Test parsing simple day format."""
        tv = TimeValue.parse("1d")
        assert tv is not None
        assert tv.to_days() == 1.0

    def test_parse_simple_weeks(self):
        """Test parsing simple week format."""
        tv = TimeValue.parse("2w")
        assert tv is not None
        # 2 weeks = 10 days = 80 hours
        assert tv.to_hours() == 80.0

    def test_parse_combined(self):
        """Test parsing combined format."""
        tv = TimeValue.parse("2h 30m")
        assert tv is not None
        assert tv.to_minutes() == 150

    def test_parse_combined_days_hours(self):
        """Test parsing days and hours."""
        tv = TimeValue.parse("1d 4h")
        assert tv is not None
        assert tv.to_hours() == 12.0  # 8 + 4

    def test_parse_decimal_hours(self):
        """Test parsing decimal hours."""
        tv = TimeValue.parse("1.5h")
        assert tv is not None
        assert tv.to_minutes() == 90

    def test_parse_verbose_format(self):
        """Test parsing verbose format."""
        tv = TimeValue.parse("2 hours")
        assert tv is not None
        assert tv.to_hours() == 2.0

    def test_parse_empty_returns_none(self):
        """Test parsing empty string."""
        assert TimeValue.parse("") is None
        assert TimeValue.parse("   ") is None

    def test_parse_plain_number(self):
        """Test parsing plain number (assumes hours)."""
        tv = TimeValue.parse("5")
        assert tv is not None
        assert tv.to_hours() == 5.0


class TestWorkLogEntry:
    """Tests for WorkLogEntry class."""

    def test_create_basic(self):
        """Test creating a basic work log entry."""
        wl = WorkLogEntry(
            id="wl-1",
            duration=TimeValue.from_hours(2),
            comment="Fixed bugs",
            author="John Doe",
        )
        assert wl.id == "wl-1"
        assert wl.duration.to_hours() == 2.0
        assert wl.comment == "Fixed bugs"

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        wl = WorkLogEntry(
            id="wl-1",
            duration=TimeValue.from_minutes(90),
            started=datetime(2024, 1, 15, 10, 0),
            comment="Testing",
            author="Jane",
        )
        data = wl.to_dict()
        restored = WorkLogEntry.from_dict(data)

        assert restored.id == wl.id
        assert restored.duration.to_minutes() == 90
        assert restored.started == wl.started
        assert restored.comment == wl.comment


class TestTimeTrackingInfo:
    """Tests for TimeTrackingInfo class."""

    def test_create_basic(self):
        """Test creating basic time tracking info."""
        info = TimeTrackingInfo(
            story_id="US-001",
            issue_key="PROJ-123",
            original_estimate=TimeValue.from_hours(8),
            time_spent=TimeValue.from_hours(4),
        )
        assert info.story_id == "US-001"
        assert info.original_estimate.to_hours() == 8.0
        assert info.time_spent.to_hours() == 4.0

    def test_total_logged_minutes(self):
        """Test calculating total logged time from work logs."""
        info = TimeTrackingInfo(
            story_id="US-001",
            work_logs=[
                WorkLogEntry(duration=TimeValue.from_hours(2)),
                WorkLogEntry(duration=TimeValue.from_hours(3)),
            ],
        )
        assert info.total_logged_minutes == 300  # 5 hours

    def test_progress_percentage(self):
        """Test calculating progress percentage."""
        info = TimeTrackingInfo(
            story_id="US-001",
            original_estimate=TimeValue.from_hours(10),
            time_spent=TimeValue.from_hours(5),
        )
        assert info.progress_percentage == 50.0

    def test_progress_percentage_capped_at_100(self):
        """Test progress percentage doesn't exceed 100."""
        info = TimeTrackingInfo(
            story_id="US-001",
            original_estimate=TimeValue.from_hours(4),
            time_spent=TimeValue.from_hours(8),
        )
        assert info.progress_percentage == 100.0

    def test_progress_percentage_none_without_estimate(self):
        """Test progress is None without original estimate."""
        info = TimeTrackingInfo(story_id="US-001", time_spent=TimeValue.from_hours(5))
        assert info.progress_percentage is None

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        info = TimeTrackingInfo(
            story_id="US-001",
            issue_key="PROJ-123",
            original_estimate=TimeValue.from_hours(8),
            remaining_estimate=TimeValue.from_hours(4),
            time_spent=TimeValue.from_hours(4),
            work_logs=[WorkLogEntry(duration=TimeValue.from_hours(2))],
        )
        data = info.to_dict()
        restored = TimeTrackingInfo.from_dict(data)

        assert restored.story_id == info.story_id
        assert restored.original_estimate.to_hours() == 8.0
        assert len(restored.work_logs) == 1


class TestTimeTrackingExtractor:
    """Tests for TimeTrackingExtractor."""

    def test_extract_estimate_from_table(self):
        """Test extracting estimate from markdown table."""
        content = textwrap.dedent("""
            ### US-001: Test Story

            | **Property** | **Value** |
            |--------------|-----------|
            | **Time Estimate** | 4h |
            | **Priority** | High |
        """)
        info = extract_time_tracking(content, "US-001")
        assert info.original_estimate is not None
        assert info.original_estimate.to_hours() == 4.0

    def test_extract_estimate_combined(self):
        """Test extracting combined estimate."""
        content = "| **Estimate** | 2h 30m |"
        info = extract_time_tracking(content, "US-001")
        assert info.original_estimate is not None
        assert info.original_estimate.to_minutes() == 150

    def test_extract_remaining_estimate(self):
        """Test extracting remaining estimate."""
        content = "| **Remaining** | 1d |"
        info = extract_time_tracking(content, "US-001")
        assert info.remaining_estimate is not None
        assert info.remaining_estimate.to_days() == 1.0

    def test_extract_time_spent(self):
        """Test extracting time spent."""
        content = "| **Time Spent** | 3h |"
        info = extract_time_tracking(content, "US-001")
        assert info.time_spent is not None
        assert info.time_spent.to_hours() == 3.0

    def test_extract_logged_time(self):
        """Test extracting logged time (alternative name)."""
        content = "| **Logged Time** | 5h |"
        info = extract_time_tracking(content, "US-001")
        assert info.time_spent is not None
        assert info.time_spent.to_hours() == 5.0

    def test_extract_estimate_inline(self):
        """Test extracting inline estimate format."""
        content = "**Estimate:** 2h\n**Priority:** High"
        info = extract_time_tracking(content, "US-001")
        assert info.original_estimate is not None
        assert info.original_estimate.to_hours() == 2.0

    def test_extract_obsidian_dataview(self):
        """Test extracting Obsidian dataview format."""
        content = "Estimate:: 3d\nStatus:: In Progress"
        info = extract_time_tracking(content, "US-001")
        assert info.original_estimate is not None
        assert info.original_estimate.to_days() == 3.0

    def test_extract_work_log_section(self):
        """Test extracting work log entries from section."""
        content = textwrap.dedent("""
            ### US-001: Test Story

            #### Work Log
            - 2024-01-15 - 2h - Initial implementation
            - 2024-01-16 - 3h - Bug fixes
            - 1h - Quick fix
        """)
        info = extract_time_tracking(content, "US-001")
        assert len(info.work_logs) == 3
        assert info.work_logs[0].duration.to_hours() == 2.0
        assert info.work_logs[0].started is not None
        assert info.work_logs[0].comment == "Initial implementation"

    def test_no_time_tracking(self):
        """Test content without time tracking."""
        content = "### US-001: Simple Story\n\nJust a description."
        info = extract_time_tracking(content, "US-001")
        assert info.original_estimate is None
        assert info.time_spent is None
        assert len(info.work_logs) == 0


class TestTimeTrackingSyncResult:
    """Tests for TimeTrackingSyncResult."""

    def test_success_when_no_errors(self):
        """Test success property when no errors."""
        result = TimeTrackingSyncResult(story_id="US-001")
        assert result.success is True

    def test_failure_when_errors(self):
        """Test success property when errors."""
        result = TimeTrackingSyncResult(story_id="US-001", errors=["Failed to push estimate"])
        assert result.success is False


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_parse_time_estimate(self):
        """Test parse_time_estimate function."""
        tv = parse_time_estimate("2h 30m")
        assert tv is not None
        assert tv.to_minutes() == 150

    def test_format_time_for_markdown_compact(self):
        """Test format_time_for_markdown compact mode."""
        result = format_time_for_markdown(150)
        assert result == "150m"  # Returns display format (minutes)

    def test_format_time_for_markdown_full(self):
        """Test format_time_for_markdown full mode."""
        result = format_time_for_markdown(90, compact=False)
        assert "1h" in result
        assert "30m" in result

    def test_extract_time_tracking_function(self):
        """Test extract_time_tracking convenience function."""
        content = "| **Estimate** | 4h |"
        info = extract_time_tracking(content, "US-001")
        assert info.story_id == "US-001"
        assert info.original_estimate is not None


class TestTimeTrackingSyncConfig:
    """Tests for TimeTrackingSyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TimeTrackingSyncConfig()
        assert config.enabled is True
        assert config.sync_estimates is True
        assert config.sync_work_logs is True
        assert config.hours_per_day == 8
        assert config.days_per_week == 5

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TimeTrackingSyncConfig(
            enabled=True,
            sync_estimates=True,
            push_work_logs=False,
            hours_per_day=7,
            days_per_week=4,
        )
        assert config.hours_per_day == 7
        assert config.days_per_week == 4
        assert config.push_work_logs is False
