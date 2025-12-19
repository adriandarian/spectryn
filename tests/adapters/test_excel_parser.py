"""Tests for Excel Parser."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.parsers import ExcelParser
from spectra.core.domain.enums import Priority, Status


class TestExcelParser:
    """Tests for ExcelParser class."""

    @pytest.fixture
    def parser(self) -> ExcelParser:
        """Create an Excel parser instance."""
        return ExcelParser()

    def test_name(self, parser: ExcelParser) -> None:
        """Test parser name property."""
        assert parser.name == "Excel"

    def test_supported_extensions(self, parser: ExcelParser) -> None:
        """Test supported file extensions."""
        assert ".xlsx" in parser.supported_extensions
        assert ".xlsm" in parser.supported_extensions
        assert ".xls" in parser.supported_extensions

    def test_can_parse_excel_file(self, parser: ExcelParser, tmp_path: Path) -> None:
        """Test can_parse with Excel file path."""
        excel_file = tmp_path / "test.xlsx"
        excel_file.touch()  # Just create the file
        assert parser.can_parse(excel_file) is True

    def test_can_parse_non_excel_file(self, parser: ExcelParser, tmp_path: Path) -> None:
        """Test can_parse rejects non-Excel files."""
        csv_file = tmp_path / "test.csv"
        csv_file.touch()
        assert parser.can_parse(csv_file) is False

    def test_can_parse_string_returns_false(self, parser: ExcelParser) -> None:
        """Test can_parse returns False for string content."""
        # Excel can't be parsed from string content
        assert parser.can_parse("some content") is False

    def test_validate_file_not_found(self, parser: ExcelParser, tmp_path: Path) -> None:
        """Test validation catches missing file."""
        missing_file = tmp_path / "nonexistent.xlsx"
        errors = parser.validate(missing_file)
        assert any("not found" in e for e in errors)

    @pytest.fixture
    def mock_workbook(self):
        """Create a mock openpyxl workbook."""
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = iter(
            [
                ("id", "title", "story_points", "priority", "status"),
                ("US-001", "Test Story", 5, "high", "planned"),
                ("US-002", "Another Story", 3, "medium", "done"),
            ]
        )

        mock_wb = MagicMock()
        mock_wb.active = mock_ws
        mock_wb.worksheets = [mock_ws]
        mock_wb.sheetnames = ["Sheet1"]
        mock_wb.__getitem__ = lambda self, key: mock_ws

        return mock_wb

    def test_parse_stories_with_mock(
        self, parser: ExcelParser, mock_workbook, tmp_path: Path
    ) -> None:
        """Test parsing stories with mocked openpyxl."""
        excel_file = tmp_path / "test.xlsx"
        excel_file.touch()

        with patch.object(parser, "_ensure_openpyxl") as mock_openpyxl:
            mock_module = MagicMock()
            mock_module.load_workbook.return_value = mock_workbook
            mock_openpyxl.return_value = mock_module

            stories = parser.parse_stories(excel_file)

            assert len(stories) == 2
            assert str(stories[0].id) == "US-001"
            assert stories[0].title == "Test Story"
            assert stories[0].story_points == 5
            assert stories[0].priority == Priority.HIGH
            assert str(stories[1].id) == "US-002"
            assert stories[1].status == Status.DONE

    def test_parse_epic_with_mock(self, parser: ExcelParser, mock_workbook, tmp_path: Path) -> None:
        """Test parsing epic with mocked openpyxl."""
        excel_file = tmp_path / "my_epic.xlsx"
        excel_file.touch()

        with patch.object(parser, "_ensure_openpyxl") as mock_openpyxl:
            mock_module = MagicMock()
            mock_module.load_workbook.return_value = mock_workbook
            mock_openpyxl.return_value = mock_module

            epic = parser.parse_epic(excel_file)

            assert epic is not None
            assert epic.title == "my_epic"
            assert len(epic.stories) == 2

    def test_parse_row_with_description(self, parser: ExcelParser) -> None:
        """Test parsing row with user story description."""
        row = {
            "id": "US-001",
            "title": "Test Story",
            "description": "As a user, I want to test, so that I verify functionality",
            "story_points": "5",
        }

        story = parser._parse_row(row, 0)

        assert story is not None
        assert story.description is not None
        assert story.description.role == "user"
        assert story.description.want == "to test"
        assert "verify" in story.description.benefit

    def test_parse_row_with_links(self, parser: ExcelParser) -> None:
        """Test parsing row with links."""
        row = {
            "id": "US-001",
            "title": "Test Story",
            "links": "blocks:PROJ-123;depends_on:OTHER-456",
        }

        story = parser._parse_row(row, 0)

        assert story is not None
        assert len(story.links) == 2
        assert ("blocks", "PROJ-123") in story.links
        assert ("depends on", "OTHER-456") in story.links

    def test_parse_row_with_subtasks(self, parser: ExcelParser) -> None:
        """Test parsing row with subtasks."""
        row = {
            "id": "US-001",
            "title": "Test Story",
            "subtasks": "Task 1;Task 2;Task 3",
        }

        story = parser._parse_row(row, 0)

        assert story is not None
        assert len(story.subtasks) == 3
        assert story.subtasks[0].name == "Task 1"
        assert story.subtasks[1].name == "Task 2"
        assert story.subtasks[2].name == "Task 3"

    def test_normalize_row(self, parser: ExcelParser) -> None:
        """Test column name normalization."""
        row = {
            "Story ID": "US-001",
            "Name": "Test Story",
            "SP": "5",
            "Prio": "high",
        }

        normalized = parser._normalize_row(row)

        assert normalized.get("id") == "US-001"
        assert normalized.get("title") == "Test Story"
        assert normalized.get("story_points") == "5"
        assert normalized.get("priority") == "high"
