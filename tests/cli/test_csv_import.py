"""Tests for CSV import functionality."""

import csv
import io
import tempfile
import textwrap
from pathlib import Path

import pytest

from spectryn.cli.csv_import import (
    GITHUB_COLUMNS,
    JIRA_COLUMNS,
    CsvImporter,
    CsvImportOptions,
    CsvImportResult,
    import_csv,
)
from spectryn.core.domain.enums import Priority, Status


class TestCsvImporter:
    """Tests for CsvImporter class."""

    def test_detect_format_jira(self) -> None:
        """Test detection of Jira CSV format."""
        importer = CsvImporter()
        headers = ["Issue key", "Summary", "Status", "Issue Type", "Epic Link"]
        assert importer.detect_format(headers) == "jira"

    def test_detect_format_github(self) -> None:
        """Test detection of GitHub CSV format."""
        importer = CsvImporter()
        headers = ["Number", "Title", "State", "Milestone", "Assignees"]
        assert importer.detect_format(headers) == "github"

    def test_detect_format_linear(self) -> None:
        """Test detection of Linear CSV format."""
        importer = CsvImporter()
        headers = ["Identifier", "Title", "Status", "Cycle", "Project"]
        assert importer.detect_format(headers) == "linear"

    def test_detect_format_generic(self) -> None:
        """Test fallback to generic format."""
        importer = CsvImporter()
        headers = ["ID", "Name", "Description"]
        assert importer.detect_format(headers) == "generic"

    def test_find_column_explicit_override(self) -> None:
        """Test finding column with explicit option override."""
        options = CsvImportOptions(title_column="custom_title")
        importer = CsvImporter(options)
        headers = ["custom_title", "Summary", "Description"]

        result = importer.find_column(headers, "title", JIRA_COLUMNS)
        assert result == "custom_title"

    def test_find_column_from_mappings(self) -> None:
        """Test finding column from format mappings."""
        importer = CsvImporter()
        headers = ["Issue key", "Summary", "Description"]

        result = importer.find_column(headers, "title", JIRA_COLUMNS)
        assert result == "Summary"

    def test_find_column_case_insensitive(self) -> None:
        """Test case-insensitive column matching."""
        importer = CsvImporter()
        headers = ["issue key", "SUMMARY", "description"]

        result = importer.find_column(headers, "title", JIRA_COLUMNS)
        assert result == "SUMMARY"

    def test_import_jira_csv(self, tmp_path: Path) -> None:
        """Test importing Jira CSV format."""
        csv_content = textwrap.dedent("""
            Issue key,Summary,Status,Priority,Story Points
            PROJ-1,First story,In Progress,High,5
            PROJ-2,Second story,Done,Medium,3
        """).strip()

        csv_file = tmp_path / "jira_export.csv"
        csv_file.write_text(csv_content)

        stories, result = import_csv(csv_file, format_type="jira")

        assert result.success
        assert result.stories_imported == 2
        assert len(stories) == 2

        assert stories[0].id.value == "PROJ-1"
        assert stories[0].title == "First story"
        assert stories[0].status == Status.IN_PROGRESS
        assert stories[0].priority == Priority.HIGH
        assert stories[0].story_points == 5

        assert stories[1].id.value == "PROJ-2"
        assert stories[1].title == "Second story"
        assert stories[1].status == Status.DONE

    def test_import_github_csv(self, tmp_path: Path) -> None:
        """Test importing GitHub CSV format."""
        csv_content = textwrap.dedent("""
            Number,Title,State,Labels,Body
            42,Fix login bug,open,bug,Fix the login issue
            43,Add feature,closed,enhancement,New feature
        """).strip()

        csv_file = tmp_path / "github_export.csv"
        csv_file.write_text(csv_content)

        stories, result = import_csv(csv_file, format_type="github")

        assert result.success
        assert result.stories_imported == 2

        # GitHub numbers get # prefix
        assert stories[0].id.value == "#42"
        assert stories[0].title == "Fix login bug"
        assert stories[0].status == Status.PLANNED  # open -> PLANNED

        assert stories[1].id.value == "#43"
        assert stories[1].status == Status.DONE  # closed -> DONE

    def test_import_generic_csv(self, tmp_path: Path) -> None:
        """Test importing generic CSV format."""
        csv_content = textwrap.dedent("""
            id,title,description,status,priority
            STORY-001,My story,A description,planned,high
            STORY-002,Another story,More details,in progress,low
        """).strip()

        csv_file = tmp_path / "stories.csv"
        csv_file.write_text(csv_content)

        stories, result = import_csv(csv_file, format_type="generic")

        assert result.success
        assert result.stories_imported == 2
        assert stories[0].title == "My story"

    def test_import_generates_ids_when_missing(self, tmp_path: Path) -> None:
        """Test that IDs are generated when not in CSV."""
        csv_content = textwrap.dedent("""
            title,description
            First story,Description 1
            Second story,Description 2
        """).strip()

        csv_file = tmp_path / "no_ids.csv"
        csv_file.write_text(csv_content)

        options = CsvImportOptions(id_prefix="GEN")
        importer = CsvImporter(options)
        stories, result = importer.import_file(csv_file)

        assert result.success
        assert stories[0].id.value == "GEN-001"
        assert stories[1].id.value == "GEN-002"

    def test_import_skips_rows_without_title(self, tmp_path: Path) -> None:
        """Test that rows without titles are skipped."""
        csv_content = textwrap.dedent("""
            id,title,status
            STORY-1,Has title,planned
            STORY-2,,planned
            STORY-3,Also has title,done
        """).strip()

        csv_file = tmp_path / "missing_titles.csv"
        csv_file.write_text(csv_content)

        _stories, result = import_csv(csv_file)

        assert result.success
        assert result.stories_imported == 2
        assert result.stories_skipped == 1
        assert len(result.warnings) == 1

    def test_import_handles_utf8_encoding(self, tmp_path: Path) -> None:
        """Test handling of UTF-8 encoded files."""
        csv_content = textwrap.dedent("""
            id,title,description
            STORY-1,Título en español,Descripción con acentos
            STORY-2,日本語タイトル,Description in Japanese
        """).strip()

        csv_file = tmp_path / "utf8.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        stories, result = import_csv(csv_file)

        assert result.success
        assert stories[0].title == "Título en español"
        assert stories[1].title == "日本語タイトル"

    def test_import_parses_labels(self, tmp_path: Path) -> None:
        """Test parsing of comma-separated labels."""
        csv_content = textwrap.dedent("""
            id,title,labels
            STORY-1,With labels,"bug, frontend, urgent"
        """).strip()

        csv_file = tmp_path / "labels.csv"
        csv_file.write_text(csv_content)

        stories, result = import_csv(csv_file)

        assert result.success
        assert stories[0].labels == ["bug", "frontend", "urgent"]

    def test_import_parses_description_format(self, tmp_path: Path) -> None:
        """Test parsing of As a/I want/So that format in descriptions."""
        csv_content = textwrap.dedent("""
            id,title,description
            STORY-1,User login,"As a user, I want to login, So that I can access my account"
        """).strip()

        csv_file = tmp_path / "descriptions.csv"
        csv_file.write_text(csv_content)

        stories, result = import_csv(csv_file)

        assert result.success
        desc = stories[0].description
        assert desc is not None
        assert desc.role == "user"
        assert "login" in desc.want

    def test_import_content_directly(self) -> None:
        """Test importing from content string."""
        csv_content = textwrap.dedent("""
            id,title,status
            STORY-1,Test story,done
        """).strip()

        importer = CsvImporter()
        stories, result = importer.import_content(csv_content)

        assert result.success
        assert len(stories) == 1

    def test_import_file_not_found(self, tmp_path: Path) -> None:
        """Test error handling for missing file."""
        _stories, result = import_csv(tmp_path / "nonexistent.csv")

        assert not result.success
        assert "not found" in result.errors[0].lower()

    def test_import_no_headers(self, tmp_path: Path) -> None:
        """Test error handling for CSV without headers."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        _stories, result = import_csv(csv_file)

        assert not result.success
        assert "headers" in result.errors[0].lower()

    def test_import_no_title_column(self, tmp_path: Path) -> None:
        """Test error when title column cannot be found."""
        csv_content = "id,data,info\n1,foo,bar"

        csv_file = tmp_path / "no_title.csv"
        csv_file.write_text(csv_content)

        _stories, result = import_csv(csv_file)

        assert not result.success
        assert "title column" in result.errors[0].lower()


class TestCsvImportOptions:
    """Tests for CsvImportOptions."""

    def test_default_options(self) -> None:
        """Test default option values."""
        options = CsvImportOptions()

        assert options.format == "auto"
        assert options.id_prefix == "STORY"
        assert options.starting_number == 1
        assert options.delimiter == ","

    def test_custom_options(self) -> None:
        """Test custom option values."""
        options = CsvImportOptions(
            format="jira",
            id_prefix="PROJ",
            starting_number=100,
            delimiter=";",
        )

        assert options.format == "jira"
        assert options.id_prefix == "PROJ"
        assert options.starting_number == 100
        assert options.delimiter == ";"


class TestToMarkdown:
    """Tests for markdown export from imported stories."""

    def test_to_markdown_basic(self, tmp_path: Path) -> None:
        """Test basic markdown generation."""
        csv_content = textwrap.dedent("""
            id,title,story_points,status,priority
            STORY-1,First story,5,done,high
            STORY-2,Second story,3,planned,medium
        """).strip()

        csv_file = tmp_path / "stories.csv"
        csv_file.write_text(csv_content)

        importer = CsvImporter()
        stories, _ = importer.import_file(csv_file)
        markdown = importer.to_markdown(stories, "Test Epic")

        assert "# 📋 Test Epic" in markdown
        assert "STORY-1" in markdown
        assert "First story" in markdown
        assert "Story Points" in markdown
        assert "Total Stories:** 2" in markdown

    def test_to_markdown_with_output_file(self, tmp_path: Path) -> None:
        """Test markdown output to file."""
        csv_content = textwrap.dedent("""
            id,title
            STORY-1,Test story
        """).strip()

        csv_file = tmp_path / "stories.csv"
        csv_file.write_text(csv_content)

        output_file = tmp_path / "output.md"
        import_csv(csv_file, output=output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "STORY-1" in content
        assert "Test story" in content


class TestStatusParsing:
    """Tests for status string parsing."""

    @pytest.mark.parametrize(
        ("status_str", "expected"),
        [
            ("Done", Status.DONE),
            ("done", Status.DONE),
            ("DONE", Status.DONE),
            ("Closed", Status.DONE),
            ("Resolved", Status.DONE),
            ("In Progress", Status.IN_PROGRESS),
            ("in progress", Status.IN_PROGRESS),
            ("In Development", Status.IN_PROGRESS),
            ("Open", Status.OPEN),  # Status.OPEN is returned for "open"
            ("To Do", Status.OPEN),  # Status.OPEN is returned for "to do"
        ],
    )
    def test_parse_jira_statuses(self, status_str: str, expected: Status) -> None:
        """Test parsing of various Jira status strings."""
        importer = CsvImporter()
        result = importer._parse_status(status_str, "jira")
        assert result == expected

    @pytest.mark.parametrize(
        ("status_str", "expected"),
        [
            ("open", Status.PLANNED),
            ("closed", Status.DONE),
        ],
    )
    def test_parse_github_statuses(self, status_str: str, expected: Status) -> None:
        """Test parsing of GitHub status strings."""
        importer = CsvImporter()
        result = importer._parse_status(status_str, "github")
        assert result == expected


class TestPriorityParsing:
    """Tests for priority string parsing."""

    @pytest.mark.parametrize(
        ("priority_str", "expected"),
        [
            ("1", Priority.HIGH),
            ("2", Priority.HIGH),
            ("3", Priority.MEDIUM),
            ("4", Priority.LOW),
            ("5", Priority.LOW),
            ("High", Priority.HIGH),
            ("Medium", Priority.MEDIUM),
            ("Low", Priority.LOW),
        ],
    )
    def test_parse_priorities(self, priority_str: str, expected: Priority) -> None:
        """Test parsing of various priority strings."""
        importer = CsvImporter()
        result = importer._parse_priority(priority_str, "jira")
        assert result == expected

    @pytest.mark.parametrize(
        ("labels", "expected"),
        [
            ("critical", Priority.HIGH),
            ("urgent", Priority.HIGH),
            ("p0", Priority.HIGH),
            ("p1", Priority.HIGH),
            ("minor", Priority.LOW),
            ("p3", Priority.LOW),
        ],
    )
    def test_parse_github_priority_labels(self, labels: str, expected: Priority) -> None:
        """Test parsing of GitHub priority labels."""
        importer = CsvImporter()
        result = importer._parse_priority(labels, "github")
        assert result == expected
