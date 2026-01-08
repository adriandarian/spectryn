"""
Tests for scheduled sync - cron-like scheduled syncs.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from spectryn.application.scheduler import (
    CronSchedule,
    DailySchedule,
    HourlySchedule,
    IntervalSchedule,
    ScheduleDisplay,
    ScheduledSyncRunner,
    ScheduleStats,
    parse_schedule,
)


class TestIntervalSchedule:
    """Tests for IntervalSchedule class."""

    def test_seconds(self):
        """Test interval in seconds."""
        schedule = IntervalSchedule(seconds=30)
        assert schedule.interval_seconds == 30
        assert "30 second" in schedule.description()

    def test_minutes(self):
        """Test interval in minutes."""
        schedule = IntervalSchedule(minutes=5)
        assert schedule.interval_seconds == 300
        assert "5" in schedule.description()
        assert "minute" in schedule.description()

    def test_hours(self):
        """Test interval in hours."""
        schedule = IntervalSchedule(hours=1)
        assert schedule.interval_seconds == 3600
        assert "hour" in schedule.description()

    def test_combined(self):
        """Test combined interval."""
        schedule = IntervalSchedule(hours=1, minutes=30, seconds=45)
        assert schedule.interval_seconds == 3600 + 1800 + 45

    def test_next_run_time(self):
        """Test next run time calculation."""
        schedule = IntervalSchedule(seconds=60)
        now = datetime.now()
        next_run = schedule.next_run_time(now)

        assert next_run > now
        assert (next_run - now).total_seconds() == 60

    def test_invalid_interval(self):
        """Test invalid interval raises error."""
        with pytest.raises(ValueError):
            IntervalSchedule(seconds=0)

        with pytest.raises(ValueError):
            IntervalSchedule(seconds=-10)


class TestDailySchedule:
    """Tests for DailySchedule class."""

    def test_basic(self):
        """Test basic daily schedule."""
        schedule = DailySchedule(hour=9, minute=30)
        assert schedule.hour == 9
        assert schedule.minute == 30
        assert "09:30" in schedule.description()

    def test_next_run_time_today(self):
        """Test next run when today's time hasn't passed."""
        schedule = DailySchedule(hour=23, minute=59)
        now = datetime.now().replace(hour=0, minute=0, second=0)
        next_run = schedule.next_run_time(now)

        assert next_run.hour == 23
        assert next_run.minute == 59
        assert next_run.date() == now.date()

    def test_next_run_time_tomorrow(self):
        """Test next run when today's time has passed."""
        schedule = DailySchedule(hour=0, minute=0)
        now = datetime.now().replace(hour=1, minute=0, second=0)
        next_run = schedule.next_run_time(now)

        assert next_run.hour == 0
        assert next_run.minute == 0
        assert next_run.date() == (now + timedelta(days=1)).date()

    def test_invalid_hour(self):
        """Test invalid hour raises error."""
        with pytest.raises(ValueError):
            DailySchedule(hour=25)

    def test_invalid_minute(self):
        """Test invalid minute raises error."""
        with pytest.raises(ValueError):
            DailySchedule(minute=60)


class TestHourlySchedule:
    """Tests for HourlySchedule class."""

    def test_basic(self):
        """Test basic hourly schedule."""
        schedule = HourlySchedule(minute=30)
        assert schedule.minute == 30
        assert ":30" in schedule.description()

    def test_next_run_time_this_hour(self):
        """Test next run when this hour's time hasn't passed."""
        schedule = HourlySchedule(minute=59)
        now = datetime.now().replace(minute=0, second=0)
        next_run = schedule.next_run_time(now)

        assert next_run.minute == 59
        assert next_run.hour == now.hour

    def test_next_run_time_next_hour(self):
        """Test next run when this hour's time has passed."""
        schedule = HourlySchedule(minute=0)
        now = datetime.now().replace(minute=1, second=0)
        next_run = schedule.next_run_time(now)

        assert next_run.minute == 0
        expected_hour = (now.hour + 1) % 24
        assert next_run.hour == expected_hour

    def test_invalid_minute(self):
        """Test invalid minute raises error."""
        with pytest.raises(ValueError):
            HourlySchedule(minute=60)


class TestCronSchedule:
    """Tests for CronSchedule class."""

    def test_parse_all_wildcards(self):
        """Test parsing with all wildcards."""
        schedule = CronSchedule("* * *")
        assert schedule.minutes == list(range(60))
        assert schedule.hours == list(range(24))
        assert schedule.days_of_week == list(range(7))

    def test_parse_specific_values(self):
        """Test parsing specific values."""
        schedule = CronSchedule("30 9 1")
        assert schedule.minutes == [30]
        assert schedule.hours == [9]
        assert schedule.days_of_week == [0]  # Monday

    def test_description(self):
        """Test description output."""
        schedule = CronSchedule("0 9 *")
        assert "cron:" in schedule.description()

    def test_next_run_time(self):
        """Test next run time calculation."""
        # Every minute
        schedule = CronSchedule("* * *")
        now = datetime.now()
        next_run = schedule.next_run_time(now)

        assert next_run > now
        assert (next_run - now) <= timedelta(minutes=2)

    def test_invalid_expression(self):
        """Test invalid expression raises error."""
        with pytest.raises(ValueError):
            CronSchedule("invalid")

        with pytest.raises(ValueError):
            CronSchedule("0 9")  # Too few parts


class TestParseSchedule:
    """Tests for parse_schedule function."""

    def test_parse_seconds(self):
        """Test parsing seconds interval."""
        schedule = parse_schedule("30s")
        assert isinstance(schedule, IntervalSchedule)
        assert schedule.interval_seconds == 30

    def test_parse_minutes(self):
        """Test parsing minutes interval."""
        schedule = parse_schedule("5m")
        assert isinstance(schedule, IntervalSchedule)
        assert schedule.interval_seconds == 300

    def test_parse_hours(self):
        """Test parsing hours interval."""
        schedule = parse_schedule("1h")
        assert isinstance(schedule, IntervalSchedule)
        assert schedule.interval_seconds == 3600

    def test_parse_daily(self):
        """Test parsing daily schedule."""
        schedule = parse_schedule("daily:09:30")
        assert isinstance(schedule, DailySchedule)
        assert schedule.hour == 9
        assert schedule.minute == 30

    def test_parse_hourly(self):
        """Test parsing hourly schedule."""
        schedule = parse_schedule("hourly:15")
        assert isinstance(schedule, HourlySchedule)
        assert schedule.minute == 15

    def test_parse_cron(self):
        """Test parsing cron schedule."""
        schedule = parse_schedule("cron:0 9 *")
        assert isinstance(schedule, CronSchedule)

    def test_parse_float_interval(self):
        """Test parsing float interval."""
        schedule = parse_schedule("1.5h")
        assert isinstance(schedule, IntervalSchedule)
        assert schedule.interval_seconds == 5400

    def test_invalid_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError):
            parse_schedule("invalid")

        with pytest.raises(ValueError):
            parse_schedule("daily:invalid")


class TestScheduleStats:
    """Tests for ScheduleStats class."""

    def test_initial_state(self):
        """Test initial state."""
        stats = ScheduleStats()

        assert stats.runs_completed == 0
        assert stats.runs_successful == 0
        assert stats.runs_failed == 0
        assert stats.last_run_at is None
        assert stats.next_run_at is None

    def test_uptime_formatted(self):
        """Test uptime formatting."""
        stats = ScheduleStats()
        formatted = stats.uptime_formatted

        assert "s" in formatted


class TestScheduledSyncRunner:
    """Tests for ScheduledSyncRunner class."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock sync orchestrator."""
        orchestrator = Mock()
        orchestrator.sync.return_value = Mock(
            success=True,
            stories_matched=2,
            stories_updated=1,
            errors=[],
        )
        return orchestrator

    def test_initialization(self, mock_orchestrator):
        """Test runner initialization."""
        schedule = IntervalSchedule(seconds=60)

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
        )

        assert runner.markdown_path == "/test.md"
        assert runner.epic_key == "PROJ-123"
        assert runner.stats.runs_completed == 0

    def test_run_immediately(self, mock_orchestrator):
        """Test run_immediately option."""
        schedule = IntervalSchedule(seconds=3600)  # Long interval

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
            run_immediately=True,
            max_runs=1,
        )

        # Start in thread and let it complete one run
        thread = runner.start_async()
        time.sleep(0.5)
        runner.stop()
        thread.join(timeout=2)

        # Should have run once immediately
        assert mock_orchestrator.sync.called
        assert runner.stats.runs_completed >= 1

    def test_max_runs(self, mock_orchestrator):
        """Test max_runs limit."""
        schedule = IntervalSchedule(seconds=0.1)

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
            run_immediately=True,
            max_runs=2,
        )

        thread = runner.start_async()
        time.sleep(1)
        runner.stop()
        thread.join(timeout=2)

        # Should have stopped at max_runs
        assert runner.stats.runs_completed <= 3  # Allow some timing variance

    def test_callbacks(self, mock_orchestrator):
        """Test that callbacks are invoked."""
        schedule = IntervalSchedule(seconds=3600)

        start_called = []
        complete_called = []

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
            run_immediately=True,
            max_runs=1,
            on_run_start=lambda: start_called.append(True),
            on_run_complete=lambda r: complete_called.append(r),
        )

        thread = runner.start_async()
        time.sleep(0.5)
        runner.stop()
        thread.join(timeout=2)

        assert len(start_called) >= 1
        assert len(complete_called) >= 1

    def test_error_handling(self, mock_orchestrator):
        """Test error handling."""
        mock_orchestrator.sync.side_effect = Exception("Test error")

        schedule = IntervalSchedule(seconds=3600)

        error_called = []

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
            run_immediately=True,
            max_runs=1,
            on_error=lambda e: error_called.append(e),
        )

        thread = runner.start_async()
        time.sleep(0.5)
        runner.stop()
        thread.join(timeout=2)

        assert runner.stats.runs_failed >= 1
        assert len(runner.stats.errors) >= 1
        assert len(error_called) >= 1

    def test_get_status(self, mock_orchestrator):
        """Test getting runner status."""
        schedule = IntervalSchedule(seconds=60)

        runner = ScheduledSyncRunner(
            orchestrator=mock_orchestrator,
            schedule=schedule,
            markdown_path="/test.md",
            epic_key="PROJ-123",
        )

        status = runner.get_status()

        assert status["epic_key"] == "PROJ-123"
        assert "schedule" in status
        assert "uptime" in status


class TestScheduleDisplay:
    """Tests for ScheduleDisplay class."""

    def test_show_start(self, capsys):
        """Test showing start message."""
        display = ScheduleDisplay(color=False)
        schedule = IntervalSchedule(minutes=5)

        display.show_start("/test.md", "PROJ-123", schedule)

        captured = capsys.readouterr()
        assert "Scheduled Sync" in captured.out
        assert "PROJ-123" in captured.out
        assert "5" in captured.out

    def test_show_start_quiet(self, capsys):
        """Test quiet mode suppresses output."""
        display = ScheduleDisplay(quiet=True)
        schedule = IntervalSchedule(minutes=5)

        display.show_start("/test.md", "PROJ-123", schedule)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_show_run_complete_success(self, capsys):
        """Test showing successful run complete."""
        display = ScheduleDisplay(color=False)
        result = Mock(
            success=True,
            stories_matched=5,
            stories_updated=2,
        )

        display.show_run_complete(result)

        captured = capsys.readouterr()
        assert "Sync complete" in captured.out

    def test_show_run_complete_failure(self, capsys):
        """Test showing failed run complete."""
        display = ScheduleDisplay(color=False)
        result = Mock(
            success=False,
            errors=["Error 1"],
        )

        display.show_run_complete(result)

        captured = capsys.readouterr()
        assert "Sync failed" in captured.out

    def test_show_stop(self, capsys):
        """Test showing stop message."""
        display = ScheduleDisplay(color=False)
        stats = ScheduleStats()
        stats.runs_completed = 5
        stats.runs_successful = 4
        stats.runs_failed = 1

        display.show_stop(stats)

        captured = capsys.readouterr()
        assert "Scheduled Sync Stopped" in captured.out
        assert "5" in captured.out


class TestSecondsUntilNext:
    """Tests for seconds_until_next method."""

    def test_interval_schedule(self):
        """Test seconds_until_next for interval schedule."""
        schedule = IntervalSchedule(seconds=60)

        seconds = schedule.seconds_until_next()

        # Should be close to 60 seconds
        assert 59 <= seconds <= 61

    def test_hourly_schedule(self):
        """Test seconds_until_next for hourly schedule."""
        now = datetime.now()
        # Schedule for next minute
        next_minute = (now.minute + 1) % 60
        schedule = HourlySchedule(minute=next_minute)

        seconds = schedule.seconds_until_next()

        # Should be less than 60 seconds
        assert 0 <= seconds <= 120
