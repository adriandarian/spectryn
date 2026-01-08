"""Tests for spectra.cli.report module."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.report import (
    ReportData,
    _progress_bar,
    collect_report_data,
    format_html_report,
    format_text_report,
    run_report,
)
from spectryn.core.domain.enums import Priority, Status


class TestReportData:
    """Tests for ReportData dataclass."""

    def test_report_data_creation(self):
        """Test ReportData creation."""
        now = datetime.now()
        start = now - timedelta(days=7)
        report = ReportData(
            period="weekly",
            start_date=start,
            end_date=now,
            stories_total=10,
            stories_completed=5,
        )
        assert report.period == "weekly"
        assert report.stories_total == 10
        assert report.stories_completed == 5

    def test_report_data_defaults(self):
        """Test ReportData default values."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now,
            end_date=now,
        )
        assert report.stories_total == 0
        assert report.stories_completed == 0
        assert report.stories_in_progress == 0
        assert report.stories_blocked == 0
        assert report.points_total == 0
        assert report.points_completed == 0
        assert report.velocity == 0.0
        assert report.velocity_trend == "stable"
        assert report.completed_stories == []
        assert report.in_progress_stories == []
        assert report.blocked_stories == []

    def test_completion_rate_with_stories(self):
        """Test completion_rate property with stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now,
            end_date=now,
            stories_total=10,
            stories_completed=5,
        )
        assert report.completion_rate == 50.0

    def test_completion_rate_zero_stories(self):
        """Test completion_rate with zero stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now,
            end_date=now,
            stories_total=0,
        )
        assert report.completion_rate == 0.0

    def test_completion_rate_all_completed(self):
        """Test completion_rate at 100%."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now,
            end_date=now,
            stories_total=10,
            stories_completed=10,
        )
        assert report.completion_rate == 100.0


class TestProgressBar:
    """Tests for _progress_bar function."""

    def test_progress_bar_0_percent(self):
        """Test progress bar at 0%."""
        result = _progress_bar(0.0, width=10, color=False)
        assert "0.0%" in result
        assert "░" in result  # All empty

    def test_progress_bar_50_percent(self):
        """Test progress bar at 50%."""
        result = _progress_bar(50.0, width=10, color=False)
        assert "50.0%" in result
        assert "█" in result
        assert "░" in result

    def test_progress_bar_100_percent(self):
        """Test progress bar at 100%."""
        result = _progress_bar(100.0, width=10, color=False)
        assert "100.0%" in result
        assert "█" in result

    def test_progress_bar_with_color(self):
        """Test progress bar with color."""
        result = _progress_bar(50.0, width=10, color=True)
        assert "\x1b[" in result  # Has ANSI codes

    def test_progress_bar_custom_width(self):
        """Test progress bar with custom width."""
        result = _progress_bar(50.0, width=20, color=False)
        # Should have roughly 10 filled and 10 empty
        bar_content = result.split("[")[1].split("]")[0]
        assert len(bar_content) == 20


class TestCollectReportData:
    """Tests for collect_report_data function."""

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_weekly_report(self, mock_parser_class):
        """Test collecting weekly report data."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test Story"
        mock_story.story_points = 5
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "High"

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.period == "weekly"
        assert report.stories_total == 1
        assert report.stories_completed == 1
        assert report.points_completed == 5
        assert len(report.completed_stories) == 1

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_monthly_report(self, mock_parser_class):
        """Test collecting monthly report data."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.story_points = 8
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "monthly")

        assert report.period == "monthly"
        assert report.velocity == 8 / 4  # Weekly average

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_sprint_report(self, mock_parser_class):
        """Test collecting sprint report data."""
        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "sprint")

        assert report.period == "sprint"

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_in_progress_stories(self, mock_parser_class):
        """Test collecting in-progress stories."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "In Progress Story"
        mock_story.story_points = 3
        mock_story.status = MagicMock()
        mock_story.status.value = "In Progress"
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.stories_in_progress == 1
        assert len(report.in_progress_stories) == 1

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_blocked_stories(self, mock_parser_class):
        """Test collecting blocked stories."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Blocked Story"
        mock_story.story_points = 5
        mock_story.status = MagicMock()
        mock_story.status.value = "Blocked"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Critical"

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.stories_blocked == 1
        assert len(report.blocked_stories) == 1

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_no_status(self, mock_parser_class):
        """Test collecting story with no status."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Story"
        mock_story.story_points = None
        mock_story.status = None
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        # No status means planned, not counted as completed
        assert report.stories_completed == 0

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_closed_status(self, mock_parser_class):
        """Test collecting story with closed status."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Closed Story"
        mock_story.story_points = 2
        mock_story.status = MagicMock()
        mock_story.status.value = "Closed"
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.stories_completed == 1

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_resolved_status(self, mock_parser_class):
        """Test collecting story with resolved status."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Resolved Story"
        mock_story.story_points = 3
        mock_story.status = MagicMock()
        mock_story.status.value = "Resolved"
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.stories_completed == 1

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_collect_active_status(self, mock_parser_class):
        """Test collecting story with active status."""
        mock_parser = MagicMock()
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Active Story"
        mock_story.story_points = 1
        mock_story.status = MagicMock()
        mock_story.status.value = "Active"
        mock_story.priority = None

        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        report = collect_report_data("/test/file.md", "weekly")

        assert report.stories_in_progress == 1


class TestFormatTextReport:
    """Tests for format_text_report function."""

    def test_format_empty_report(self):
        """Test formatting empty report."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
        )
        output = format_text_report(report, color=False)

        assert "Weekly Progress Report" in output
        assert "0/0" in output

    def test_format_with_completed(self):
        """Test formatting report with completed stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=5,
            stories_completed=3,
            points_total=15,
            points_completed=10,
            completed_stories=[
                {
                    "id": "US-001",
                    "title": "Story 1",
                    "points": 5,
                    "status": "done",
                    "priority": "High",
                },
                {
                    "id": "US-002",
                    "title": "Story 2",
                    "points": 3,
                    "status": "done",
                    "priority": "Medium",
                },
            ],
        )
        output = format_text_report(report, color=False)

        assert "3/5" in output
        assert "10/15" in output
        assert "Completed Stories" in output
        assert "US-001" in output

    def test_format_with_in_progress(self):
        """Test formatting report with in-progress stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=3,
            stories_in_progress=2,
            in_progress_stories=[
                {
                    "id": "US-001",
                    "title": "In progress 1",
                    "points": 3,
                    "status": "in_progress",
                    "priority": "High",
                },
            ],
        )
        output = format_text_report(report, color=False)

        assert "In Progress" in output
        assert "US-001" in output

    def test_format_with_blocked(self):
        """Test formatting report with blocked stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=3,
            stories_blocked=1,
            blocked_stories=[
                {
                    "id": "US-001",
                    "title": "Blocked story",
                    "points": 5,
                    "status": "blocked",
                    "priority": "Critical",
                },
            ],
        )
        output = format_text_report(report, color=False)

        assert "Blocked" in output
        assert "US-001" in output

    def test_format_with_color(self):
        """Test formatting with color enabled."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
        )
        output = format_text_report(report, color=True)

        assert "\x1b[" in output  # Has ANSI codes

    def test_format_truncates_long_title(self):
        """Test that long titles are truncated."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_completed=1,
            stories_total=1,
            completed_stories=[
                {
                    "id": "US-001",
                    "title": "A" * 100,  # Very long title
                    "points": 5,
                    "status": "done",
                    "priority": "High",
                },
            ],
        )
        output = format_text_report(report, color=False)

        # Title should be truncated to 40 chars
        assert "A" * 41 not in output

    def test_format_shows_more_indicator(self):
        """Test that more indicator shows for many stories."""
        now = datetime.now()
        completed = [
            {
                "id": f"US-{i:03d}",
                "title": f"Story {i}",
                "points": 3,
                "status": "done",
                "priority": "High",
            }
            for i in range(15)
        ]
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=15,
            stories_completed=15,
            completed_stories=completed,
        )
        output = format_text_report(report, color=False)

        assert "... and 5 more" in output

    def test_format_monthly_report(self):
        """Test formatting monthly report."""
        now = datetime.now()
        report = ReportData(
            period="monthly",
            start_date=now - timedelta(days=30),
            end_date=now,
        )
        output = format_text_report(report, color=False)

        assert "Monthly Progress Report" in output

    def test_format_sprint_report(self):
        """Test formatting sprint report."""
        now = datetime.now()
        report = ReportData(
            period="sprint",
            start_date=now - timedelta(days=14),
            end_date=now,
        )
        output = format_text_report(report, color=False)

        assert "Sprint Progress Report" in output

    def test_format_velocity(self):
        """Test velocity is displayed."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            velocity=10.5,
        )
        output = format_text_report(report, color=False)

        assert "Velocity" in output
        assert "10.5" in output


class TestFormatHtmlReport:
    """Tests for format_html_report function."""

    def test_format_basic_html(self):
        """Test basic HTML formatting."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
        )
        html = format_html_report(report)

        assert "<!DOCTYPE html>" in html
        assert "Weekly Progress Report" in html
        assert "<html" in html
        assert "</html>" in html

    def test_format_html_metrics(self):
        """Test HTML metrics section."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=10,
            stories_completed=5,
            points_completed=20,
        )
        html = format_html_report(report)

        assert "5/10" in html
        assert "20" in html
        assert "50%" in html  # Completion rate

    def test_format_html_completed_stories(self):
        """Test HTML with completed stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=1,
            stories_completed=1,
            completed_stories=[
                {
                    "id": "US-001",
                    "title": "Story Title",
                    "points": 5,
                    "status": "done",
                    "priority": "High",
                },
            ],
        )
        html = format_html_report(report)

        assert "Completed Stories" in html
        assert "US-001" in html
        assert "Story Title" in html

    def test_format_html_in_progress(self):
        """Test HTML with in-progress stories."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_in_progress=1,
            in_progress_stories=[
                {
                    "id": "US-002",
                    "title": "In Progress",
                    "points": 3,
                    "status": "in_progress",
                    "priority": "Medium",
                },
            ],
        )
        html = format_html_report(report)

        assert "In Progress" in html
        assert "US-002" in html

    def test_format_html_progress_bar(self):
        """Test HTML progress bar."""
        now = datetime.now()
        report = ReportData(
            period="weekly",
            start_date=now - timedelta(days=7),
            end_date=now,
            stories_total=10,
            stories_completed=7,
        )
        html = format_html_report(report)

        # Should have progress bar with 70% width
        assert "progress-bar" in html
        assert "progress-fill" in html
        assert "70%" in html


class TestRunReport:
    """Tests for run_report function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    def test_run_report_file_not_found(self, mock_console, tmp_path):
        """Test run_report with non-existent file."""
        result = run_report(
            console=mock_console,
            input_path=str(tmp_path / "nonexistent.md"),
        )
        assert result == ExitCode.FILE_NOT_FOUND

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_text_output(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_report with text output."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_format="text",
        )

        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_html_output(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_report with HTML output."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_format="html",
        )

        assert result == ExitCode.SUCCESS
        captured = capsys.readouterr()
        assert "<!DOCTYPE html>" in captured.out

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_json_output(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_report with JSON output."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_format="json",
        )

        assert result == ExitCode.SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "period" in data
        assert "summary" in data

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_save_to_file(self, mock_parser_class, mock_console, tmp_path):
        """Test run_report saving to file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_file = tmp_path / "report.txt"

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_file),
            output_format="text",
        )

        assert result == ExitCode.SUCCESS
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Progress Report" in content

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_save_html(self, mock_parser_class, mock_console, tmp_path):
        """Test run_report saving HTML to file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_file = tmp_path / "report.html"

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_file),
            output_format="html",
        )

        assert result == ExitCode.SUCCESS
        assert output_file.exists()
        content = output_file.read_text()
        assert "<!DOCTYPE html>" in content

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_save_json(self, mock_parser_class, mock_console, tmp_path):
        """Test run_report saving JSON to file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_file = tmp_path / "report.json"

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_file),
            output_format="json",
        )

        assert result == ExitCode.SUCCESS
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "period" in data

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_monthly(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_report with monthly period."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            period="monthly",
        )

        assert result == ExitCode.SUCCESS
        captured = capsys.readouterr()
        assert "Monthly" in captured.out

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_sprint(self, mock_parser_class, mock_console, tmp_path, capsys):
        """Test run_report with sprint period."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            period="sprint",
        )

        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_report_strips_ansi_from_file(self, mock_parser_class, mock_console, tmp_path):
        """Test that ANSI codes are stripped when saving text to file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_file = tmp_path / "report.txt"

        # Enable color in console
        mock_console.color = True

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_report(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_file),
            output_format="text",
        )

        assert result == ExitCode.SUCCESS
        content = output_file.read_text(encoding="utf-8")
        # Should not contain ANSI escape codes
        assert "\x1b[" not in content
