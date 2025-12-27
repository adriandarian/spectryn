"""Tests for Google Sheets parser."""

import pytest

from spectra.adapters.parsers.google_sheets_parser import GoogleSheetsParser
from spectra.core.domain.enums import Priority, Status


class TestGoogleSheetsParser:
    """Tests for GoogleSheetsParser."""

    @pytest.fixture
    def parser(self) -> GoogleSheetsParser:
        """Create parser instance."""
        return GoogleSheetsParser()

    def test_name(self, parser: GoogleSheetsParser) -> None:
        """Test parser name."""
        assert parser.name == "GoogleSheets"

    def test_supported_extensions(self, parser: GoogleSheetsParser) -> None:
        """Test supported file extensions (empty for API-based parser)."""
        assert parser.supported_extensions == []

    def test_can_parse_sheets_url(self, parser: GoogleSheetsParser) -> None:
        """Test can_parse with Google Sheets URL."""
        url = "https://docs.google.com/spreadsheets/d/1abcdefghijklmnopqrstuvwxyz12345/edit"
        assert parser.can_parse(url) is True

    def test_can_parse_spreadsheet_id(self, parser: GoogleSheetsParser) -> None:
        """Test can_parse with spreadsheet ID."""
        sheet_id = "1abcdefghijklmnopqrstuvwxyz12345"
        assert parser.can_parse(sheet_id) is True

    def test_cannot_parse_file_path(self, parser: GoogleSheetsParser, tmp_path) -> None:
        """Test can_parse rejects file paths."""
        test_file = tmp_path / "test.xlsx"
        test_file.write_text("content")
        assert parser.can_parse(test_file) is False

    def test_validate_missing_credentials(self, parser: GoogleSheetsParser) -> None:
        """Test validation fails without credentials."""
        errors = parser.validate("1abcdefghijklmnopqrstuvwxyz12345")
        assert any("credentials" in e.lower() for e in errors)

    def test_extract_spreadsheet_id_from_url(self, parser: GoogleSheetsParser) -> None:
        """Test extracting spreadsheet ID from URL."""
        url = "https://docs.google.com/spreadsheets/d/1abcdefghijklmnopqrstuvwxyz12345/edit#gid=0"
        sheet_id = parser._extract_spreadsheet_id(url)
        assert sheet_id == "1abcdefghijklmnopqrstuvwxyz12345"

    def test_extract_spreadsheet_id_direct(self, parser: GoogleSheetsParser) -> None:
        """Test extracting direct spreadsheet ID."""
        sheet_id = "1abcdefghijklmnopqrstuvwxyz12345"
        result = parser._extract_spreadsheet_id(sheet_id)
        assert result == sheet_id

    def test_find_column_index(self, parser: GoogleSheetsParser) -> None:
        """Test finding column index by name."""
        headers = ["Story ID", "Title", "Story Points", "Priority", "Status"]

        assert parser._find_column_index(headers, "story_id") == 0
        assert parser._find_column_index(headers, "title") == 1
        assert parser._find_column_index(headers, "story_points") == 2
        assert parser._find_column_index(headers, "priority") == 3
        assert parser._find_column_index(headers, "status") == 4

    def test_find_column_index_aliases(self, parser: GoogleSheetsParser) -> None:
        """Test finding column index with alternate names."""
        headers = ["ID", "Name", "SP", "Pri", "State"]

        assert parser._find_column_index(headers, "story_id") == 0
        assert parser._find_column_index(headers, "title") == 1
        assert parser._find_column_index(headers, "story_points") == 2

    def test_parse_stories_from_rows(self, parser: GoogleSheetsParser) -> None:
        """Test parsing stories from row data."""
        data = [
            [
                "Story ID",
                "Title",
                "Story Points",
                "Priority",
                "Status",
                "As a",
                "I want",
                "So that",
            ],
            ["PROJ-001", "First Story", "5", "High", "Planned", "user", "feature", "benefit"],
            ["PROJ-002", "Second Story", "3", "Medium", "Done", "admin", "manage", "control"],
        ]

        stories = parser._parse_stories_from_rows(data)

        assert len(stories) == 2

        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "First Story"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.PLANNED
        assert story1.description is not None
        assert story1.description.role == "user"

        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_stories_skip_invalid_ids(self, parser: GoogleSheetsParser) -> None:
        """Test that rows without valid story IDs are skipped."""
        data = [
            ["Story ID", "Title", "Story Points"],
            ["PROJ-001", "Valid Story", "5"],
            ["invalid", "Invalid ID", "3"],
            ["", "Empty ID", "2"],
            ["PROJ-002", "Another Valid", "4"],
        ]

        stories = parser._parse_stories_from_rows(data)
        assert len(stories) == 2
        assert str(stories[0].id) == "PROJ-001"
        assert str(stories[1].id) == "PROJ-002"

    def test_parse_key_value_sheet(self, parser: GoogleSheetsParser) -> None:
        """Test parsing key-value style sheet."""
        data = [
            ["Epic Key", "PROJ-123"],
            ["Title", "Epic Title"],
            ["Description", "Epic description text"],
        ]

        result = parser._parse_key_value_sheet(data)
        assert result["epic key"] == "PROJ-123"
        assert result["title"] == "Epic Title"
        assert result["description"] == "Epic description text"

    def test_enrich_stories_with_ac(self, parser: GoogleSheetsParser) -> None:
        """Test enriching stories with acceptance criteria."""
        data = [
            ["Story ID", "Title", "Story Points"],
            ["PROJ-001", "Test Story", "5"],
        ]
        stories = parser._parse_stories_from_rows(data)

        ac_data = [
            ["Story ID", "Criterion", "Done"],
            ["PROJ-001", "First criterion", "No"],
            ["PROJ-001", "Second criterion", "Yes"],
        ]

        parser._enrich_stories_with_ac(stories, ac_data)

        assert len(stories[0].acceptance_criteria.items) == 2
        assert "First criterion" in stories[0].acceptance_criteria.items

    def test_enrich_stories_with_subtasks(self, parser: GoogleSheetsParser) -> None:
        """Test enriching stories with subtasks."""
        data = [
            ["Story ID", "Title", "Story Points"],
            ["PROJ-001", "Test Story", "5"],
        ]
        stories = parser._parse_stories_from_rows(data)

        subtasks_data = [
            ["Story ID", "#", "Task", "SP", "Status"],
            ["PROJ-001", "1", "First task", "2", "Planned"],
            ["PROJ-001", "2", "Second task", "1", "Done"],
        ]

        parser._enrich_stories_with_subtasks(stories, subtasks_data)

        assert len(stories[0].subtasks) == 2
        assert stories[0].subtasks[0].name == "First task"
        assert stories[0].subtasks[0].story_points == 2
