"""Tests for CLI bulk operations commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.bulk import (
    BulkResult,
    StoryFilter,
    format_bulk_result,
    matches_filter,
    parse_filter,
    parse_updates,
    run_bulk_assign,
    run_bulk_update,
)
from spectryn.cli.exit_codes import ExitCode


# =============================================================================
# parse_filter Tests
# =============================================================================


class TestParseFilter:
    """Tests for parse_filter function."""

    def test_empty_filter(self):
        """Test parsing empty filter string."""
        result = parse_filter("")
        assert result.status is None
        assert result.priority is None
        assert result.labels == []

    def test_single_status_filter(self):
        """Test parsing single status filter."""
        result = parse_filter("status=planned")
        assert result.status == "planned"

    def test_single_priority_filter(self):
        """Test parsing single priority filter."""
        result = parse_filter("priority=high")
        assert result.priority == "high"

    def test_assignee_filter(self):
        """Test parsing assignee filter."""
        result = parse_filter("assignee=john")
        assert result.assignee == "john"

    def test_labels_filter(self):
        """Test parsing labels filter with multiple values."""
        result = parse_filter("labels=backend|frontend")
        assert result.labels == ["backend", "frontend"]

    def test_epic_filter(self):
        """Test parsing epic filter."""
        result = parse_filter("epic=EPIC-123")
        assert result.epic_key == "EPIC-123"

    def test_title_filter(self):
        """Test parsing title pattern filter."""
        result = parse_filter("title=test.*pattern")
        assert result.title_pattern == "test.*pattern"

    def test_points_min_filter(self):
        """Test parsing minimum points filter."""
        result = parse_filter("points>=5")
        assert result.points_min == 5

    def test_points_max_filter(self):
        """Test parsing maximum points filter."""
        result = parse_filter("points<=10")
        assert result.points_max == 10

    def test_multiple_filters(self):
        """Test parsing multiple filters."""
        result = parse_filter("status=planned,priority=high,assignee=john")
        assert result.status == "planned"
        assert result.priority == "high"
        assert result.assignee == "john"

    def test_filter_with_whitespace(self):
        """Test parsing filter with whitespace."""
        result = parse_filter("status = planned , priority = high")
        assert result.status == "planned"
        assert result.priority == "high"


# =============================================================================
# parse_updates Tests
# =============================================================================


class TestParseUpdates:
    """Tests for parse_updates function."""

    def test_empty_updates(self):
        """Test parsing empty update string."""
        result = parse_updates("")
        assert result == {}

    def test_status_update(self):
        """Test parsing status update."""
        result = parse_updates("status=in_progress")
        assert result["status"] == "in_progress"

    def test_priority_update(self):
        """Test parsing priority update."""
        result = parse_updates("priority=high")
        assert result["priority"] == "high"

    def test_labels_update(self):
        """Test parsing labels update."""
        result = parse_updates("labels=urgent|critical")
        assert result["labels"] == ["urgent", "critical"]

    def test_assignee_update(self):
        """Test parsing assignee update."""
        result = parse_updates("assignee=jane")
        assert result["assignee"] == "jane"

    def test_points_update(self):
        """Test parsing story points update."""
        result = parse_updates("points=5")
        assert result["story_points"] == 5

    def test_multiple_updates(self):
        """Test parsing multiple updates."""
        result = parse_updates("status=done,priority=low")
        assert result["status"] == "done"
        assert result["priority"] == "low"


# =============================================================================
# matches_filter Tests
# =============================================================================


class TestMatchesFilter:
    """Tests for matches_filter function."""

    @pytest.fixture
    def mock_story_obj(self):
        """Create a mock story object."""
        story = MagicMock()
        story.status = MagicMock()
        story.status.name = "PLANNED"
        story.priority = MagicMock()
        story.priority.name = "HIGH"
        story.story_points = 5
        story.title = "Test Story"
        story.assignee = "john"
        story.labels = ["backend"]
        return story

    @pytest.fixture
    def mock_story_dict(self):
        """Create a mock story as dictionary."""
        return {
            "status": "planned",
            "priority": "high",
            "story_points": 5,
            "title": "Test Story",
            "assignee": "john",
            "labels": ["backend"],
        }

    def test_matches_empty_filter_object(self, mock_story_obj):
        """Test matching with empty filter on object."""
        assert matches_filter(mock_story_obj, StoryFilter()) is True

    def test_matches_empty_filter_dict(self, mock_story_dict):
        """Test matching with empty filter on dict."""
        assert matches_filter(mock_story_dict, StoryFilter()) is True

    def test_matches_status_filter(self, mock_story_obj):
        """Test matching status filter."""
        filter_pass = StoryFilter(status="planned")
        filter_fail = StoryFilter(status="done")

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_priority_filter(self, mock_story_obj):
        """Test matching priority filter."""
        filter_pass = StoryFilter(priority="high")
        filter_fail = StoryFilter(priority="low")

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_assignee_filter(self, mock_story_obj):
        """Test matching assignee filter."""
        filter_pass = StoryFilter(assignee="john")
        filter_fail = StoryFilter(assignee="jane")

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_labels_filter(self, mock_story_obj):
        """Test matching labels filter."""
        filter_pass = StoryFilter(labels=["backend"])
        filter_fail = StoryFilter(labels=["frontend"])

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_points_min_filter(self, mock_story_obj):
        """Test matching minimum points filter."""
        filter_pass = StoryFilter(points_min=3)
        filter_fail = StoryFilter(points_min=10)

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_points_max_filter(self, mock_story_obj):
        """Test matching maximum points filter."""
        filter_pass = StoryFilter(points_max=10)
        filter_fail = StoryFilter(points_max=3)

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_title_pattern(self, mock_story_obj):
        """Test matching title pattern filter."""
        filter_pass = StoryFilter(title_pattern="Test.*")
        filter_fail = StoryFilter(title_pattern="Other.*")

        assert matches_filter(mock_story_obj, filter_pass) is True
        assert matches_filter(mock_story_obj, filter_fail) is False

    def test_matches_multiple_filters(self, mock_story_obj):
        """Test matching with multiple filters."""
        filter_all_pass = StoryFilter(status="planned", priority="high")
        filter_partial_fail = StoryFilter(status="planned", priority="low")

        assert matches_filter(mock_story_obj, filter_all_pass) is True
        assert matches_filter(mock_story_obj, filter_partial_fail) is False

    def test_handles_none_values(self):
        """Test matching story with None values."""
        story = MagicMock()
        story.status = None
        story.priority = None
        story.story_points = None
        story.title = None
        story.assignee = None
        story.labels = None

        # Should not crash, empty filter should still match
        assert matches_filter(story, StoryFilter()) is True


# =============================================================================
# format_bulk_result Tests
# =============================================================================


class TestFormatBulkResult:
    """Tests for format_bulk_result function."""

    def test_format_empty_result(self):
        """Test formatting empty result."""
        result = BulkResult()
        lines = format_bulk_result(result, "update", color=False)

        assert "Bulk Update Results" in lines[0]
        assert any("Matched:  0" in line for line in lines)

    def test_format_successful_result(self):
        """Test formatting successful result."""
        result = BulkResult(
            total_matched=10,
            total_updated=10,
            total_failed=0,
            updated_keys=["STORY-1", "STORY-2"],
        )
        lines = format_bulk_result(result, "update", color=False)

        assert any("Matched:  10" in line for line in lines)
        assert any("Updated:  10" in line for line in lines)
        assert "Updated:" in lines

    def test_format_with_failures(self):
        """Test formatting result with failures."""
        result = BulkResult(
            total_matched=10,
            total_updated=8,
            total_failed=2,
            updated_keys=["STORY-1"],
            failed_keys=["STORY-2"],
            errors=["Error 1"],
        )
        lines = format_bulk_result(result, "update", color=False)

        assert any("Failed:   2" in line for line in lines)
        assert "Failed:" in lines
        assert "Errors:" in lines

    def test_format_with_colors(self):
        """Test formatting with colors enabled."""
        result = BulkResult(total_matched=5, total_updated=5)
        lines = format_bulk_result(result, "assign", color=True)

        # Colors should be present in output
        assert len(lines) > 0

    def test_format_truncates_long_lists(self):
        """Test formatting truncates long lists."""
        result = BulkResult(
            total_matched=30,
            total_updated=30,
            updated_keys=[f"STORY-{i}" for i in range(30)],
        )
        lines = format_bulk_result(result, "update", color=False)

        # Should have "... and X more" message
        assert any("more" in line for line in lines)


# =============================================================================
# run_bulk_update Tests
# =============================================================================


class TestRunBulkUpdate:
    """Tests for run_bulk_update function."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        return MagicMock()

    @pytest.fixture
    def mock_story(self):
        """Create a mock story."""
        story = MagicMock()
        story.id = "STORY-1"
        story.title = "Test Story"
        story.status = MagicMock()
        story.status.name = "PLANNED"
        story.priority = MagicMock()
        story.priority.name = "HIGH"
        return story

    def test_update_missing_input(self, mock_console):
        """Test update without input file."""
        result = run_bulk_update(
            console=mock_console,
            input_path=None,
            update_str="status=done",
        )

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_update_missing_updates(self, mock_console, tmp_path):
        """Test update without update spec."""
        result = run_bulk_update(
            console=mock_console,
            input_path=tmp_path / "test.md",
            update_str="",
        )

        assert result == ExitCode.ERROR

    def test_update_invalid_updates(self, mock_console, tmp_path):
        """Test update with invalid update spec."""
        result = run_bulk_update(
            console=mock_console,
            input_path=tmp_path / "test.md",
            update_str="invalid",  # No valid fields
        )

        assert result == ExitCode.ERROR

    def test_update_file_not_found(self, mock_console, tmp_path):
        """Test update with non-existent file."""
        result = run_bulk_update(
            console=mock_console,
            input_path=tmp_path / "nonexistent.md",
            update_str="status=done",
        )

        assert result == ExitCode.ERROR

    def test_update_parse_error(self, mock_console, tmp_path):
        """Test update with file parse error."""
        # Create a file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.side_effect = Exception("Parse error")
            MockParser.return_value = mock_parser

            result = run_bulk_update(
                console=mock_console,
                input_path=test_file,
                update_str="status=done",
            )

            assert result == ExitCode.ERROR

    def test_update_no_matches(self, mock_console, tmp_path, mock_story):
        """Test update with no matching stories."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            # Filter that won't match
            result = run_bulk_update(
                console=mock_console,
                input_path=test_file,
                filter_str="status=done",
                update_str="status=in_progress",
            )

            assert result == ExitCode.SUCCESS
            mock_console.warning.assert_called()

    def test_update_dry_run(self, mock_console, tmp_path, mock_story):
        """Test update in dry run mode."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            result = run_bulk_update(
                console=mock_console,
                input_path=test_file,
                update_str="status=in_progress",
                dry_run=True,
            )

            assert result == ExitCode.SUCCESS

    def test_update_success(self, mock_console, tmp_path, mock_story):
        """Test successful update."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            result = run_bulk_update(
                console=mock_console,
                input_path=test_file,
                update_str="status=in_progress",
                dry_run=False,
            )

            assert result == ExitCode.SUCCESS


# =============================================================================
# run_bulk_assign Tests
# =============================================================================


class TestRunBulkAssign:
    """Tests for run_bulk_assign function."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console."""
        return MagicMock()

    @pytest.fixture
    def mock_story(self):
        """Create a mock story."""
        story = MagicMock()
        story.id = "STORY-1"
        story.title = "Test Story"
        story.status = MagicMock()
        story.status.name = "PLANNED"
        story.priority = MagicMock()
        story.priority.name = "HIGH"
        story.assignee = None
        return story

    def test_assign_missing_input(self, mock_console):
        """Test assign without input file."""
        result = run_bulk_assign(
            console=mock_console,
            input_path=None,
            assignee="john",
        )

        assert result == ExitCode.ERROR

    def test_assign_missing_assignee(self, mock_console, tmp_path):
        """Test assign without assignee."""
        result = run_bulk_assign(
            console=mock_console,
            input_path=tmp_path / "test.md",
            assignee="",
        )

        assert result == ExitCode.ERROR

    def test_assign_file_not_found(self, mock_console, tmp_path):
        """Test assign with non-existent file."""
        result = run_bulk_assign(
            console=mock_console,
            input_path=tmp_path / "nonexistent.md",
            assignee="john",
        )

        assert result == ExitCode.ERROR

    def test_assign_parse_error(self, mock_console, tmp_path):
        """Test assign with file parse error."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.side_effect = Exception("Parse error")
            MockParser.return_value = mock_parser

            result = run_bulk_assign(
                console=mock_console,
                input_path=test_file,
                assignee="john",
            )

            assert result == ExitCode.ERROR

    def test_assign_no_matches(self, mock_console, tmp_path, mock_story):
        """Test assign with no matching stories."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            # Filter that won't match
            result = run_bulk_assign(
                console=mock_console,
                input_path=test_file,
                filter_str="status=done",
                assignee="john",
            )

            assert result == ExitCode.SUCCESS
            mock_console.warning.assert_called()

    def test_assign_dry_run(self, mock_console, tmp_path, mock_story):
        """Test assign in dry run mode."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            result = run_bulk_assign(
                console=mock_console,
                input_path=test_file,
                assignee="john",
                dry_run=True,
            )

            assert result == ExitCode.SUCCESS

    def test_assign_success(self, mock_console, tmp_path, mock_story):
        """Test successful assign."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_stories.return_value = [mock_story]
            MockParser.return_value = mock_parser

            result = run_bulk_assign(
                console=mock_console,
                input_path=test_file,
                assignee="john",
                dry_run=False,
            )

            assert result == ExitCode.SUCCESS
