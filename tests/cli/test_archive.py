"""Tests for CLI archive command."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.archive import (
    ArchiveCandidate,
    ArchiveResult,
    find_archive_candidates,
    format_archive_result,
    run_archive,
)
from spectryn.cli.exit_codes import ExitCode


# =============================================================================
# ArchiveResult Tests
# =============================================================================


class TestArchiveResult:
    """Tests for ArchiveResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ArchiveResult()

        assert result.total_processed == 0
        assert result.total_archived == 0
        assert result.total_unarchived == 0
        assert result.total_skipped == 0
        assert result.total_failed == 0
        assert result.archived_keys == []
        assert result.unarchived_keys == []
        assert result.skipped_keys == []
        assert result.failed_keys == []
        assert result.errors == []

    def test_custom_values(self):
        """Test custom values."""
        result = ArchiveResult(
            total_processed=10,
            total_archived=5,
            total_unarchived=2,
            total_skipped=2,
            total_failed=1,
            archived_keys=["US-1", "US-2"],
            unarchived_keys=["US-3"],
            skipped_keys=["US-4"],
            failed_keys=["US-5"],
            errors=["Error 1"],
        )

        assert result.total_processed == 10
        assert result.total_archived == 5
        assert len(result.archived_keys) == 2


# =============================================================================
# ArchiveCandidate Tests
# =============================================================================


class TestArchiveCandidate:
    """Tests for ArchiveCandidate dataclass."""

    def test_default_values(self):
        """Test default values."""
        candidate = ArchiveCandidate(key="US-1", title="Test Story", status="done")

        assert candidate.key == "US-1"
        assert candidate.title == "Test Story"
        assert candidate.status == "done"
        assert candidate.last_updated is None
        assert candidate.days_since_update == 0
        assert candidate.reason == ""

    def test_custom_values(self):
        """Test custom values."""
        now = datetime.now()
        candidate = ArchiveCandidate(
            key="US-1",
            title="Test Story",
            status="done",
            last_updated=now,
            days_since_update=100,
            reason="Completed and inactive",
        )

        assert candidate.last_updated == now
        assert candidate.days_since_update == 100
        assert candidate.reason == "Completed and inactive"


# =============================================================================
# find_archive_candidates Tests
# =============================================================================


class TestFindArchiveCandidates:
    """Tests for find_archive_candidates function."""

    def test_find_candidates_with_dict_stories(self):
        """Test finding candidates with dict stories."""
        stories = [
            {
                "key": "US-1",
                "title": "Done Story",
                "status": "done",
                "updated": (datetime.now() - timedelta(days=100)).isoformat(),
            },
            {
                "key": "US-2",
                "title": "Active Story",
                "status": "in progress",
            },
        ]

        candidates = find_archive_candidates(stories, days_threshold=90)

        assert len(candidates) == 1
        assert candidates[0].key == "US-1"

    def test_find_candidates_with_object_stories(self):
        """Test finding candidates with object stories."""
        story1 = MagicMock()
        story1.id = "US-1"
        story1.title = "Done Story"
        story1.status = MagicMock()
        story1.status.name = "DONE"

        story2 = MagicMock()
        story2.id = "US-2"
        story2.title = "Active Story"
        story2.status = MagicMock()
        story2.status.name = "IN_PROGRESS"

        stories = [story1, story2]
        candidates = find_archive_candidates(stories, days_threshold=90)

        # Done stories without dates are assumed eligible
        assert len(candidates) == 1
        assert candidates[0].key == "US-1"

    def test_find_no_candidates(self):
        """Test when no candidates found."""
        stories = [
            {"key": "US-1", "status": "in progress"},
            {"key": "US-2", "status": "to do"},
        ]

        candidates = find_archive_candidates(stories, days_threshold=90)
        assert len(candidates) == 0

    def test_find_candidates_custom_threshold(self):
        """Test with custom days threshold."""
        stories = [
            {
                "key": "US-1",
                "status": "done",
                "updated": (datetime.now() - timedelta(days=50)).isoformat(),
            },
        ]

        # Not a candidate with 90 day threshold
        candidates = find_archive_candidates(stories, days_threshold=90)
        assert len(candidates) == 0

        # Is a candidate with 30 day threshold
        candidates = find_archive_candidates(stories, days_threshold=30)
        assert len(candidates) == 1

    def test_find_candidates_custom_status_filter(self):
        """Test with custom status filter."""
        stories = [
            {"key": "US-1", "status": "archived"},
            {"key": "US-2", "status": "done"},
        ]

        candidates = find_archive_candidates(stories, days_threshold=0, status_filter=["archived"])
        assert len(candidates) == 1
        assert candidates[0].key == "US-1"

    def test_find_candidates_various_done_statuses(self):
        """Test various done status names."""
        stories = [
            {"key": "US-1", "status": "done"},
            {"key": "US-2", "status": "closed"},
            {"key": "US-3", "status": "resolved"},
            {"key": "US-4", "status": "complete"},
            {"key": "US-5", "status": "completed"},
        ]

        candidates = find_archive_candidates(stories, days_threshold=0)
        assert len(candidates) == 5

    def test_find_candidates_iso_date_format(self):
        """Test ISO date format parsing."""
        stories = [
            {
                "key": "US-1",
                "status": "done",
                "updated": "2020-01-01T00:00:00Z",  # Long ago
            },
        ]

        candidates = find_archive_candidates(stories, days_threshold=90)
        assert len(candidates) == 1
        assert candidates[0].days_since_update > 1000


# =============================================================================
# format_archive_result Tests
# =============================================================================


class TestFormatArchiveResult:
    """Tests for format_archive_result function."""

    def test_format_archive_result_basic(self):
        """Test basic result formatting."""
        result = ArchiveResult(total_processed=5, total_archived=3)

        lines = format_archive_result(result, "archive", color=False)

        assert "Archive Operation Results" in lines[0]
        assert any("Processed: 5" in line for line in lines)
        assert any("Archived:  3" in line for line in lines)

    def test_format_unarchive_result(self):
        """Test unarchive result formatting."""
        result = ArchiveResult(total_processed=5, total_unarchived=3)

        lines = format_archive_result(result, "unarchive", color=False)

        assert any("Unarchived: 3" in line for line in lines)

    def test_format_with_skipped(self):
        """Test formatting with skipped entries."""
        result = ArchiveResult(total_processed=5, total_skipped=2)

        lines = format_archive_result(result, "archive", color=False)

        assert any("Skipped:  2" in line for line in lines)

    def test_format_with_failures(self):
        """Test formatting with failures."""
        result = ArchiveResult(total_processed=5, total_failed=1)

        lines = format_archive_result(result, "archive", color=False)

        assert any("Failed:   1" in line for line in lines)

    def test_format_with_archived_keys(self):
        """Test formatting with archived keys list."""
        result = ArchiveResult(total_archived=2, archived_keys=["US-1", "US-2"])

        lines = format_archive_result(result, "archive", color=False)

        assert any("Archived:" in line for line in lines)
        assert any("US-1" in line for line in lines)
        assert any("US-2" in line for line in lines)

    def test_format_with_many_keys_truncated(self):
        """Test truncation with many keys."""
        keys = [f"US-{i}" for i in range(20)]
        result = ArchiveResult(total_archived=20, archived_keys=keys)

        lines = format_archive_result(result, "archive", color=False)

        assert any("... and 5 more" in line for line in lines)

    def test_format_with_errors(self):
        """Test formatting with errors."""
        result = ArchiveResult(errors=["Error 1", "Error 2"])

        lines = format_archive_result(result, "archive", color=False)

        assert any("Errors:" in line for line in lines)
        assert any("Error 1" in line for line in lines)

    def test_format_with_colors(self):
        """Test formatting with colors enabled."""
        result = ArchiveResult(total_processed=5, total_archived=3)

        lines = format_archive_result(result, "archive", color=True)

        # Should have color codes
        output = "\n".join(lines)
        assert "\033[" in output  # ANSI escape codes


# =============================================================================
# run_archive Tests
# =============================================================================


class TestRunArchive:
    """Tests for run_archive function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        return MagicMock()

    def test_list_action_requires_input(self, mock_console):
        """Test list action requires input file."""
        result = run_archive(console=mock_console, action="list")

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_list_action_file_not_found(self, mock_console, tmp_path):
        """Test list action with non-existent file."""
        result = run_archive(
            console=mock_console, action="list", input_path=tmp_path / "nonexistent.md"
        )

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_list_action_parse_error(self, mock_console, tmp_path):
        """Test list action with parse error."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Invalid content")

        mock_parser = MagicMock()
        mock_parser.parse_stories.side_effect = Exception("Parse error")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(console=mock_console, action="list", input_path=md_file)

        assert result == ExitCode.ERROR

    def test_list_action_no_candidates(self, mock_console, tmp_path):
        """Test list action with no candidates."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Epic")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(console=mock_console, action="list", input_path=md_file)

        assert result == ExitCode.SUCCESS

    def test_list_action_with_candidates(self, mock_console, tmp_path):
        """Test list action with candidates."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Epic")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [
            {"key": "US-1", "title": "Done Story", "status": "done"}
        ]

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(
                console=mock_console, action="list", input_path=md_file, days_threshold=0
            )

        assert result == ExitCode.SUCCESS
        mock_console.info.assert_called()

    def test_archive_action_with_story_keys_dry_run(self, mock_console):
        """Test archive action with story keys in dry run."""
        result = run_archive(
            console=mock_console,
            action="archive",
            story_keys=["US-1", "US-2"],
            dry_run=True,
        )

        assert result == ExitCode.SUCCESS
        mock_console.info.assert_called()

    def test_archive_action_with_story_keys(self, mock_console):
        """Test archive action with story keys."""
        result = run_archive(
            console=mock_console, action="archive", story_keys=["US-1", "US-2"], dry_run=False
        )

        assert result == ExitCode.SUCCESS

    def test_archive_action_requires_input_or_keys(self, mock_console):
        """Test archive action requires input or keys."""
        result = run_archive(console=mock_console, action="archive")

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_archive_action_file_not_found(self, mock_console, tmp_path):
        """Test archive action with non-existent file."""
        result = run_archive(
            console=mock_console, action="archive", input_path=tmp_path / "nonexistent.md"
        )

        assert result == ExitCode.ERROR

    def test_archive_action_from_file_no_candidates(self, mock_console, tmp_path):
        """Test archive from file with no candidates."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Epic")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = []

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(
                console=mock_console, action="archive", input_path=md_file, days_threshold=0
            )

        assert result == ExitCode.SUCCESS

    def test_archive_action_from_file_with_candidates_dry_run(self, mock_console, tmp_path):
        """Test archive from file with candidates in dry run."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Epic")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [
            {"key": "US-1", "title": "Done Story", "status": "done"}
        ]

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(
                console=mock_console,
                action="archive",
                input_path=md_file,
                days_threshold=0,
                dry_run=True,
            )

        assert result == ExitCode.SUCCESS

    def test_archive_action_from_file_with_candidates(self, mock_console, tmp_path):
        """Test archive from file with candidates."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Epic")

        mock_parser = MagicMock()
        mock_parser.parse_stories.return_value = [
            {"key": "US-1", "title": "Done Story", "status": "done"}
        ]

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(
                console=mock_console,
                action="archive",
                input_path=md_file,
                days_threshold=0,
                dry_run=False,
            )

        assert result == ExitCode.SUCCESS

    def test_unarchive_action_requires_story_keys(self, mock_console):
        """Test unarchive action requires story keys."""
        result = run_archive(console=mock_console, action="unarchive")

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_unarchive_action_dry_run(self, mock_console):
        """Test unarchive action in dry run."""
        result = run_archive(
            console=mock_console,
            action="unarchive",
            story_keys=["US-1", "US-2"],
            dry_run=True,
        )

        assert result == ExitCode.SUCCESS

    def test_unarchive_action(self, mock_console):
        """Test unarchive action."""
        result = run_archive(
            console=mock_console, action="unarchive", story_keys=["US-1", "US-2"], dry_run=False
        )

        assert result == ExitCode.SUCCESS

    def test_unknown_action(self, mock_console):
        """Test unknown action."""
        result = run_archive(console=mock_console, action="invalid")

        assert result == ExitCode.ERROR
        mock_console.error.assert_called()

    def test_creates_console_if_not_provided(self):
        """Test console is created if not provided."""
        result = run_archive(action="invalid")

        assert result == ExitCode.ERROR

    def test_archive_action_parse_error(self, mock_console, tmp_path):
        """Test archive action with parse error."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Invalid content")

        mock_parser = MagicMock()
        mock_parser.parse_stories.side_effect = Exception("Parse error")

        with patch("spectryn.adapters.parsers.markdown.MarkdownParser", return_value=mock_parser):
            result = run_archive(console=mock_console, action="archive", input_path=md_file)

        assert result == ExitCode.ERROR
