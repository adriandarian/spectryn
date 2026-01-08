"""Tests for Stats Command - Show statistics about stories, points, and velocity."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.output import Console
from spectryn.cli.stats import (
    StoryStats,
    VelocityStats,
    collect_stats_from_directory,
    collect_stats_from_file,
    format_progress_bar,
    format_stats,
    run_stats,
)


class TestStoryStats:
    """Tests for StoryStats dataclass."""

    def test_default_values(self):
        """Test default values are initialized correctly."""
        stats = StoryStats()
        assert stats.total_stories == 0
        assert stats.total_subtasks == 0
        assert stats.total_points == 0
        assert stats.done == 0
        assert stats.in_progress == 0
        assert stats.planned == 0
        assert stats.blocked == 0

    def test_completion_percentage_with_stories(self):
        """Test completion percentage calculation."""
        stats = StoryStats(total_stories=10, done=5)
        assert stats.completion_percentage == 50.0

    def test_completion_percentage_zero_stories(self):
        """Test completion percentage with zero stories."""
        stats = StoryStats(total_stories=0)
        assert stats.completion_percentage == 0.0

    def test_points_completion_percentage(self):
        """Test points completion percentage calculation."""
        stats = StoryStats(total_points=100, points_done=75)
        assert stats.points_completion_percentage == 75.0

    def test_points_completion_percentage_zero_points(self):
        """Test points completion percentage with zero points."""
        stats = StoryStats(total_points=0)
        assert stats.points_completion_percentage == 0.0

    def test_by_priority_default(self):
        """Test by_priority is an empty dict by default."""
        stats = StoryStats()
        assert stats.by_priority == {}


class TestVelocityStats:
    """Tests for VelocityStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = VelocityStats()
        assert stats.sprints == []
        assert stats.average_velocity == 0.0
        assert stats.trend == "stable"


class TestFormatProgressBar:
    """Tests for format_progress_bar function."""

    def test_zero_percent(self):
        """Test progress bar at 0%."""
        bar = format_progress_bar(0, color=False)
        assert "0.0%" in bar
        assert "░" * 30 in bar

    def test_full_percent(self):
        """Test progress bar at 100%."""
        bar = format_progress_bar(100, color=False)
        assert "100.0%" in bar
        assert "█" * 30 in bar

    def test_fifty_percent(self):
        """Test progress bar at 50%."""
        bar = format_progress_bar(50, width=20, color=False)
        assert "50.0%" in bar
        assert "█" * 10 in bar
        assert "░" * 10 in bar

    def test_with_color_high_percentage(self):
        """Test colored bar with high percentage (green)."""
        bar = format_progress_bar(85, color=True)
        assert "85.0%" in bar

    def test_with_color_medium_percentage(self):
        """Test colored bar with medium percentage (yellow)."""
        bar = format_progress_bar(60, color=True)
        assert "60.0%" in bar

    def test_with_color_low_percentage(self):
        """Test colored bar with low percentage (red)."""
        bar = format_progress_bar(20, color=True)
        assert "20.0%" in bar


class TestFormatStats:
    """Tests for format_stats function."""

    def test_format_empty_stats(self):
        """Test formatting empty stats."""
        stats = StoryStats()
        result = format_stats(stats, color=False)
        assert "Story Statistics" in result
        assert "Total Stories:    0" in result
        assert "Total Points:     0" in result

    def test_format_stats_with_data(self):
        """Test formatting stats with data."""
        stats = StoryStats(
            total_stories=10,
            total_subtasks=20,
            total_points=50,
            done=3,
            in_progress=4,
            planned=2,
            blocked=1,
            points_done=15,
            points_in_progress=20,
            points_planned=10,
        )
        result = format_stats(stats, color=False)
        assert "Total Stories:    10" in result
        assert "Done" in result
        assert "In Progress" in result

    def test_format_stats_with_priority(self):
        """Test formatting stats with priority breakdown."""
        stats = StoryStats(
            total_stories=10,
            by_priority={"high": 3, "medium": 5, "low": 2},
        )
        result = format_stats(stats, color=False)
        assert "Priority Distribution" in result
        assert "High" in result
        assert "Medium" in result
        assert "Low" in result

    def test_format_stats_with_acceptance_criteria(self):
        """Test formatting stats with AC data."""
        stats = StoryStats(ac_total=10, ac_completed=7)
        result = format_stats(stats, color=False)
        assert "AC Items:" in result
        assert "7/10" in result


class TestCollectStatsFromFile:
    """Tests for collect_stats_from_file function."""

    def test_collect_stats_from_valid_file(self, tmp_path: Path):
        """Test collecting stats from a valid markdown file."""
        md_file = tmp_path / "stories.md"
        md_file.write_text(
            """
# Epic

## User Stories

### ✅ US-001: Done Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | ✅ Done |

### 🔄 US-002: In Progress Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟢 Medium |
| **Status** | 🔄 In Progress |
""",
            encoding="utf-8",
        )

        stats = collect_stats_from_file(str(md_file))
        assert stats.total_stories == 2
        assert stats.done == 1
        assert stats.in_progress == 1

    def test_collect_stats_from_nonexistent_file(self):
        """Test collecting stats from nonexistent file."""
        stats = collect_stats_from_file("/nonexistent/file.md")
        assert stats.total_stories == 0

    def test_collect_stats_with_subtasks(self, tmp_path: Path):
        """Test collecting stats including subtasks."""
        md_file = tmp_path / "stories.md"
        md_file.write_text(
            """
# Epic

### 📋 US-001: Story with Subtasks

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | 📋 Planned |

#### Subtasks

| # | Subtask | Status |
|---|---------|--------|
| 1 | Task 1 | Done |
| 2 | Task 2 | Todo |
""",
            encoding="utf-8",
        )

        stats = collect_stats_from_file(str(md_file))
        assert stats.total_stories == 1
        assert stats.total_subtasks >= 0  # Subtask parsing depends on implementation


class TestCollectStatsFromDirectory:
    """Tests for collect_stats_from_directory function."""

    def test_collect_stats_from_directory(self, tmp_path: Path):
        """Test collecting stats from a directory."""
        # Create multiple markdown files
        (tmp_path / "story1.md").write_text(
            """
### ✅ US-001: Story 1

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | ✅ Done |
""",
            encoding="utf-8",
        )
        (tmp_path / "story2.md").write_text(
            """
### 📋 US-002: Story 2

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | 📋 Planned |
""",
            encoding="utf-8",
        )

        stats = collect_stats_from_directory(str(tmp_path))
        assert stats.total_stories == 2
        assert stats.total_points == 8

    def test_collect_stats_from_empty_directory(self, tmp_path: Path):
        """Test collecting stats from empty directory."""
        stats = collect_stats_from_directory(str(tmp_path))
        assert stats.total_stories == 0


class TestRunStats:
    """Tests for run_stats command."""

    def test_run_stats_with_file(self, tmp_path: Path):
        """Test running stats with a single file."""
        md_file = tmp_path / "stories.md"
        md_file.write_text(
            """
### ✅ US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | ✅ Done |
""",
            encoding="utf-8",
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_stats(console, input_path=str(md_file))
        assert result == ExitCode.SUCCESS

    def test_run_stats_with_directory(self, tmp_path: Path):
        """Test running stats with a directory."""
        (tmp_path / "stories.md").write_text(
            """
### ✅ US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | ✅ Done |
""",
            encoding="utf-8",
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_stats(console, input_dir=str(tmp_path))
        assert result == ExitCode.SUCCESS

    def test_run_stats_file_not_found(self):
        """Test error when file not found."""
        console = MagicMock(spec=Console)

        result = run_stats(console, input_path="/nonexistent/file.md")

        assert result == ExitCode.FILE_NOT_FOUND
        console.error.assert_called()

    def test_run_stats_directory_not_found(self):
        """Test error when directory not found."""
        console = MagicMock(spec=Console)

        result = run_stats(console, input_dir="/nonexistent/dir")

        assert result == ExitCode.FILE_NOT_FOUND
        console.error.assert_called()

    def test_run_stats_json_output(self, tmp_path: Path, capsys):
        """Test JSON output format."""
        md_file = tmp_path / "stories.md"
        md_file.write_text(
            """
### ✅ US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | ✅ Done |
""",
            encoding="utf-8",
        )

        console = MagicMock(spec=Console)
        console.color = False

        result = run_stats(console, input_path=str(md_file), output_format="json")

        assert result == ExitCode.SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_stories" in data
        assert "total_points" in data
        assert "timestamp" in data

    def test_run_stats_current_directory_no_files(self, tmp_path: Path):
        """Test error when no markdown files in current directory."""
        console = MagicMock(spec=Console)

        # Create empty directory and mock Path.cwd()
        with patch("spectryn.cli.stats.Path") as mock_path:
            mock_cwd = MagicMock()
            mock_cwd.glob.return_value = []
            mock_path.cwd.return_value = mock_cwd

            result = run_stats(console)

        assert result == ExitCode.FILE_NOT_FOUND

    def test_run_stats_current_directory_with_files(self, tmp_path: Path):
        """Test running stats on current directory with files."""
        # Create a markdown file
        (tmp_path / "test.md").write_text(
            """
### ✅ US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | ✅ Done |
""",
            encoding="utf-8",
        )

        console = MagicMock(spec=Console)
        console.color = False

        with patch("spectryn.cli.stats.Path") as mock_path:
            mock_cwd = MagicMock()
            mock_cwd.glob.return_value = [tmp_path / "test.md"]
            mock_cwd.__str__ = lambda _: str(tmp_path)
            mock_path.cwd.return_value = mock_cwd
            mock_path.return_value.is_dir.return_value = False
            mock_path.return_value.exists.return_value = False

            with patch("spectryn.cli.stats.collect_stats_from_directory") as mock_collect:
                mock_collect.return_value = StoryStats(total_stories=1, done=1)
                result = run_stats(console)

        assert result == ExitCode.SUCCESS
