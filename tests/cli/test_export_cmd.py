"""Tests for spectra.cli.export_cmd module."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.export_cmd import (
    ExportOptions,
    ExportResult,
    export_to_csv,
    export_to_html,
    export_to_json,
    run_export,
)


class TestExportOptions:
    """Tests for ExportOptions dataclass."""

    def test_default_options(self):
        """Test ExportOptions with defaults."""
        options = ExportOptions()
        assert options.include_subtasks is True
        assert options.include_comments is False
        assert options.include_links is True
        assert options.include_metadata is True
        assert options.template is None
        assert options.style == "default"

    def test_custom_options(self):
        """Test ExportOptions with custom values."""
        options = ExportOptions(
            include_subtasks=False,
            include_comments=True,
            include_links=False,
            include_metadata=False,
            template="custom.html",
            style="minimal",
        )
        assert options.include_subtasks is False
        assert options.include_comments is True
        assert options.include_links is False
        assert options.include_metadata is False
        assert options.template == "custom.html"
        assert options.style == "minimal"


class TestExportResult:
    """Tests for ExportResult dataclass."""

    def test_default_result(self):
        """Test ExportResult with defaults."""
        result = ExportResult()
        assert result.success is True
        assert result.output_path == ""
        assert result.format == ""
        assert result.stories_exported == 0
        assert result.errors == []

    def test_custom_result(self):
        """Test ExportResult with custom values."""
        result = ExportResult(
            success=True,
            output_path="/path/to/output.html",
            format="html",
            stories_exported=10,
            errors=["Warning: Large file"],
        )
        assert result.success is True
        assert result.output_path == "/path/to/output.html"
        assert result.format == "html"
        assert result.stories_exported == 10
        assert result.errors == ["Warning: Large file"]


class TestExportToHtml:
    """Tests for export_to_html function."""

    @pytest.fixture
    def mock_stories(self):
        """Create mock stories for testing."""
        story1 = MagicMock()
        story1.id = "US-001"
        story1.title = "Test Story 1"
        story1.status = MagicMock()
        story1.status.value = "Done"
        story1.priority = MagicMock()
        story1.priority.value = "High"
        story1.story_points = 5
        story1.description = MagicMock()
        story1.description.as_a = "user"
        story1.description.i_want = "to test"
        story1.description.so_that = "it works"
        story1.acceptance_criteria = MagicMock()
        story1.acceptance_criteria.items = ["AC 1", "AC 2"]
        story1.subtasks = [
            MagicMock(name="Subtask 1", is_complete=True),
            MagicMock(name="Subtask 2", is_complete=False),
        ]
        story1.subtasks[0].name = "Subtask 1"
        story1.subtasks[1].name = "Subtask 2"

        story2 = MagicMock()
        story2.id = "US-002"
        story2.title = "Test Story 2"
        story2.status = MagicMock()
        story2.status.value = "In Progress"
        story2.priority = MagicMock()
        story2.priority.value = "Medium"
        story2.story_points = 3
        story2.description = None
        story2.acceptance_criteria = None
        story2.subtasks = []

        return [story1, story2]

    def test_export_html_structure(self, mock_stories):
        """Test HTML export has correct structure."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "Test Epic" in html
        assert "US-001" in html
        assert "US-002" in html

    def test_export_html_status_classes(self, mock_stories):
        """Test HTML export has correct status classes."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        # Done status should have status-done class
        assert "status-done" in html
        # In Progress should have status-progress
        assert "status-progress" in html

    def test_export_html_priority_classes(self, mock_stories):
        """Test HTML export has correct priority classes."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "priority-high" in html
        assert "priority-medium" in html

    def test_export_html_summary(self, mock_stories):
        """Test HTML export has summary section."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "Stories:" in html
        assert "Total Points:" in html

    def test_export_html_with_subtasks(self, mock_stories):
        """Test HTML export includes subtasks when enabled."""
        options = ExportOptions(include_subtasks=True)
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "Subtask 1" in html
        assert "Subtask 2" in html

    def test_export_html_without_subtasks(self, mock_stories):
        """Test HTML export excludes subtasks when disabled."""
        options = ExportOptions(include_subtasks=False)
        html = export_to_html(mock_stories, "Test Epic", options)

        # Subtasks section should not appear
        assert "Subtask 1" not in html

    def test_export_html_acceptance_criteria(self, mock_stories):
        """Test HTML export includes acceptance criteria."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "Acceptance Criteria" in html
        assert "AC 1" in html
        assert "AC 2" in html

    def test_export_html_description(self, mock_stories):
        """Test HTML export includes description."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "As a" in html
        assert "user" in html
        assert "I want" in html

    def test_export_html_story_points(self, mock_stories):
        """Test HTML export includes story points."""
        options = ExportOptions()
        html = export_to_html(mock_stories, "Test Epic", options)

        assert "pts" in html

    def test_export_html_empty_stories(self):
        """Test HTML export with no stories."""
        options = ExportOptions()
        html = export_to_html([], "Empty Epic", options)

        assert "Empty Epic" in html
        assert "Stories:" in html

    def test_export_html_null_status(self):
        """Test HTML export handles null status."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test"
        story.status = None
        story.priority = None
        story.story_points = None
        story.description = None
        story.acceptance_criteria = None
        story.subtasks = None

        options = ExportOptions()
        html = export_to_html([story], "Test", options)

        assert "Planned" in html  # Default status
        assert "Medium" in html  # Default priority

    def test_export_html_low_priority(self):
        """Test HTML export with low priority."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test"
        story.status = MagicMock()
        story.status.value = "Planned"
        story.priority = MagicMock()
        story.priority.value = "Low"
        story.story_points = None
        story.description = None
        story.acceptance_criteria = None
        story.subtasks = None

        options = ExportOptions()
        html = export_to_html([story], "Test", options)

        assert "priority-low" in html


class TestExportToCsv:
    """Tests for export_to_csv function."""

    @pytest.fixture
    def mock_stories(self):
        """Create mock stories for testing."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test Story"
        story.status = MagicMock()
        story.status.value = "Done"
        story.priority = MagicMock()
        story.priority.value = "High"
        story.story_points = 5
        story.subtasks = [MagicMock(), MagicMock()]
        story.acceptance_criteria = MagicMock()
        story.acceptance_criteria.items = ["AC1", "AC2", "AC3"]
        story.assignee = "john.doe"

        return [story]

    def test_export_csv_header(self, mock_stories):
        """Test CSV export has correct header."""
        csv = export_to_csv(mock_stories)
        lines = csv.strip().split("\n")

        header = lines[0]
        assert "ID" in header
        assert "Title" in header
        assert "Status" in header
        assert "Priority" in header
        assert "Story Points" in header

    def test_export_csv_data(self, mock_stories):
        """Test CSV export has correct data."""
        csv = export_to_csv(mock_stories)

        assert "US-001" in csv
        assert "Test Story" in csv
        assert "Done" in csv
        assert "High" in csv
        assert "5" in csv

    def test_export_csv_subtask_count(self, mock_stories):
        """Test CSV export includes subtask count."""
        csv = export_to_csv(mock_stories)

        # Should have 2 subtasks
        assert "2" in csv

    def test_export_csv_ac_count(self, mock_stories):
        """Test CSV export includes AC count."""
        csv = export_to_csv(mock_stories)

        # Should have 3 ACs
        assert "3" in csv

    def test_export_csv_empty_stories(self):
        """Test CSV export with no stories."""
        csv = export_to_csv([])

        # Should still have header
        assert "ID" in csv
        lines = csv.strip().split("\n")
        assert len(lines) == 1  # Only header

    def test_export_csv_null_values(self):
        """Test CSV export handles null values."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test"
        story.status = None
        story.priority = None
        story.story_points = None
        story.subtasks = None
        story.acceptance_criteria = None
        story.assignee = None

        csv = export_to_csv([story])

        assert "US-001" in csv
        assert "Test" in csv


class TestExportToJson:
    """Tests for export_to_json function."""

    @pytest.fixture
    def mock_stories(self):
        """Create mock stories for testing."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test Story"
        story.status = MagicMock()
        story.status.value = "Done"
        story.priority = MagicMock()
        story.priority.value = "High"
        story.story_points = 5
        story.description = MagicMock()
        story.description.as_a = "user"
        story.description.i_want = "to test"
        story.description.so_that = "it works"
        story.acceptance_criteria = MagicMock()
        story.acceptance_criteria.items = ["AC1", "AC2"]
        story.subtasks = [
            MagicMock(name="ST1", is_complete=True),
        ]
        story.subtasks[0].name = "ST1"

        return [story]

    def test_export_json_structure(self, mock_stories):
        """Test JSON export has correct structure."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        assert "epic" in data
        assert "exported_at" in data
        assert "story_count" in data
        assert "stories" in data

    def test_export_json_epic_title(self, mock_stories):
        """Test JSON export has correct epic title."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        assert data["epic"] == "Test Epic"

    def test_export_json_story_count(self, mock_stories):
        """Test JSON export has correct story count."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        assert data["story_count"] == 1

    def test_export_json_story_fields(self, mock_stories):
        """Test JSON export has all story fields."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        story = data["stories"][0]
        assert story["id"] == "US-001"
        assert story["title"] == "Test Story"
        assert story["status"] == "Done"
        assert story["priority"] == "High"
        assert story["story_points"] == 5

    def test_export_json_description(self, mock_stories):
        """Test JSON export includes description."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        story = data["stories"][0]
        assert story["description"]["as_a"] == "user"
        assert story["description"]["i_want"] == "to test"
        assert story["description"]["so_that"] == "it works"

    def test_export_json_acceptance_criteria(self, mock_stories):
        """Test JSON export includes acceptance criteria."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        story = data["stories"][0]
        assert story["acceptance_criteria"] == ["AC1", "AC2"]

    def test_export_json_subtasks(self, mock_stories):
        """Test JSON export includes subtasks."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        story = data["stories"][0]
        assert len(story["subtasks"]) == 1
        assert story["subtasks"][0]["name"] == "ST1"
        assert story["subtasks"][0]["complete"] is True

    def test_export_json_exported_at(self, mock_stories):
        """Test JSON export has valid timestamp."""
        json_str = export_to_json(mock_stories, "Test Epic")
        data = json.loads(json_str)

        # Should be valid ISO format
        datetime.fromisoformat(data["exported_at"])

    def test_export_json_null_values(self):
        """Test JSON export handles null values."""
        story = MagicMock()
        story.id = "US-001"
        story.title = "Test"
        story.status = None
        story.priority = None
        story.story_points = None
        story.description = None
        story.acceptance_criteria = None
        story.subtasks = None

        json_str = export_to_json([story], "Test")
        data = json.loads(json_str)

        story_data = data["stories"][0]
        assert story_data["status"] is None
        assert story_data["priority"] is None


class TestRunExport:
    """Tests for run_export function."""

    @pytest.fixture
    def mock_console(self):
        """Create mock console."""
        console = MagicMock()
        console.color = True
        return console

    @pytest.fixture
    def sample_markdown(self, tmp_path):
        """Create sample markdown file."""
        content = """# EPIC-1: Test Epic

## US-001: Test Story

**Status:** Done
**Priority:** High
**Story Points:** 5

As a user
I want to test
So that it works

### Acceptance Criteria
- [ ] AC 1
- [ ] AC 2

### Subtasks
- [ ] ST-1: Subtask 1
"""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)
        return file_path

    def test_run_export_file_not_found(self, mock_console, tmp_path):
        """Test run_export with non-existent file."""
        result = run_export(
            console=mock_console,
            input_path=str(tmp_path / "nonexistent.md"),
            output_format="html",
        )
        assert result == ExitCode.FILE_NOT_FOUND

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_html_success(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export HTML success."""
        # Create test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_path = tmp_path / "output.html"

        # Setup mocks
        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Medium"
        mock_story.story_points = None
        mock_story.description = None
        mock_story.acceptance_criteria = None
        mock_story.subtasks = []

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_path),
            output_format="html",
        )

        assert result == ExitCode.SUCCESS
        # Check output file was created
        assert output_path.exists()

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_csv_success(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export CSV success."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_path = tmp_path / "output.csv"

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Medium"
        mock_story.story_points = 5
        mock_story.subtasks = []
        mock_story.acceptance_criteria = None
        mock_story.assignee = None

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_path),
            output_format="csv",
        )

        assert result == ExitCode.SUCCESS
        assert output_path.exists()

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_json_success(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export JSON success."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_path = tmp_path / "output.json"

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Medium"
        mock_story.story_points = None
        mock_story.description = None
        mock_story.acceptance_criteria = None
        mock_story.subtasks = None

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_path),
            output_format="json",
        )

        assert result == ExitCode.SUCCESS
        assert output_path.exists()

        # Verify JSON content
        content = json.loads(output_path.read_text())
        assert "stories" in content

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_custom_output_path(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export with custom output path."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")
        output_path = tmp_path / "custom" / "output.html"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_path=str(output_path),
            output_format="html",
        )

        assert result == ExitCode.SUCCESS
        assert output_path.exists()

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_unknown_format(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export with unknown format."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_format="unknown",
        )

        assert result == ExitCode.CONFIG_ERROR
        mock_console.error.assert_called()

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_pdf_missing_weasyprint(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export PDF fails without weasyprint."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Medium"
        mock_story.story_points = None
        mock_story.description = None
        mock_story.acceptance_criteria = None
        mock_story.subtasks = []

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        # This will fail because weasyprint is not installed
        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_format="pdf",
        )

        assert result == ExitCode.CONFIG_ERROR

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_docx_missing_python_docx(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export DOCX fails without python-docx."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_story = MagicMock()
        mock_story.id = "US-001"
        mock_story.title = "Test"
        mock_story.status = MagicMock()
        mock_story.status.value = "Done"
        mock_story.priority = MagicMock()
        mock_story.priority.value = "Medium"
        mock_story.story_points = None
        mock_story.description = None
        mock_story.acceptance_criteria = None
        mock_story.subtasks = []

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = [mock_story]
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_format="docx",
        )

        assert result == ExitCode.CONFIG_ERROR

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_with_epic(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export when file has epic structure."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# EPIC-1: Test Epic\n")

        mock_epic = MagicMock()
        mock_epic.key = "EPIC-1"
        mock_epic.title = "Test Epic"
        mock_epic.stories = []

        mock_parser = MagicMock()
        mock_parser.parse_epic.return_value = mock_epic
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_format="html",
        )

        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_include_options(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export respects include options."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_format="html",
            include_subtasks=False,
            include_comments=True,
        )

        assert result == ExitCode.SUCCESS

    @patch("spectryn.adapters.parsers.MarkdownParser")
    def test_run_export_error_handling(self, mock_parser_class, mock_console, tmp_path):
        """Test run_export handles export errors."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test\n")

        mock_parser = MagicMock()
        mock_parser.parse_epic.side_effect = Exception("Not an epic")
        mock_parser.parse_stories.return_value = []
        mock_parser_class.return_value = mock_parser

        # Try to write to a directory that doesn't exist with restricted path
        result = run_export(
            console=mock_console,
            input_path=str(test_file),
            output_path="/nonexistent/dir/output.html",
            output_format="html",
        )

        assert result == ExitCode.ERROR
