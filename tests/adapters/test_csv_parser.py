"""Tests for CSV Parser."""

from pathlib import Path

import pytest

from spectra.adapters.parsers import CsvParser
from spectra.core.domain.enums import Priority, Status


class TestCsvParser:
    """Tests for CsvParser class."""

    @pytest.fixture
    def parser(self) -> CsvParser:
        """Create a CSV parser instance."""
        return CsvParser()

    def test_name(self, parser: CsvParser) -> None:
        """Test parser name property."""
        assert parser.name == "CSV"

    def test_supported_extensions(self, parser: CsvParser) -> None:
        """Test supported file extensions."""
        assert parser.supported_extensions == [".csv", ".tsv"]

    def test_can_parse_csv_file(self, parser: CsvParser, tmp_path: Path) -> None:
        """Test can_parse with CSV file."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,title\nUS-001,Test Story")
        assert parser.can_parse(csv_file) is True

    def test_can_parse_csv_content(self, parser: CsvParser) -> None:
        """Test can_parse with CSV content string."""
        content = "id,title\nUS-001,Test Story"
        assert parser.can_parse(content) is True

    def test_parse_stories_minimal(self, parser: CsvParser) -> None:
        """Test parsing minimal story structure."""
        content = "id,title\nUS-001,Test Story"

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"

    def test_parse_stories_full(self, parser: CsvParser) -> None:
        """Test parsing story with all fields."""
        content = '''id,title,description,story_points,priority,status,acceptance_criteria,subtasks,technical_notes,links
US-001,"Full Story","As a user, I want feature, so that benefit",5,high,in_progress,"AC1;AC2","Task1;Task2","Tech notes","blocks:PROJ-123"'''

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Full Story"
        assert story.description is not None
        assert story.description.role == "user"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS
        assert len(story.acceptance_criteria.items) == 2
        assert len(story.subtasks) == 2
        assert story.technical_notes == "Tech notes"
        assert len(story.links) == 1
        assert story.links[0] == ("blocks", "PROJ-123")

    def test_parse_multiple_stories(self, parser: CsvParser) -> None:
        """Test parsing multiple stories."""
        content = '''id,title,story_points
US-001,Story 1,3
US-002,Story 2,5
US-003,Story 3,8'''

        stories = parser.parse_stories(content)

        assert len(stories) == 3
        assert stories[0].story_points == 3
        assert stories[1].story_points == 5
        assert stories[2].story_points == 8

    def test_parse_epic(self, parser: CsvParser, tmp_path: Path) -> None:
        """Test parsing epic uses filename."""
        csv_file = tmp_path / "my_epic.csv"
        csv_file.write_text("id,title\nUS-001,Story 1")

        epic = parser.parse_epic(csv_file)

        assert epic is not None
        assert epic.title == "my_epic"
        assert len(epic.stories) == 1

    def test_flexible_column_names(self, parser: CsvParser) -> None:
        """Test flexible column name mappings."""
        content = '''story_id,name,points,prio
US-001,Test Story,5,high'''

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"
        assert stories[0].story_points == 5
        assert stories[0].priority == Priority.HIGH

    def test_parse_tsv(self, parser: CsvParser, tmp_path: Path) -> None:
        """Test parsing TSV file."""
        tsv_file = tmp_path / "test.tsv"
        tsv_file.write_text("id\ttitle\tstory_points\nUS-001\tTest Story\t5")

        stories = parser.parse_stories(tsv_file)

        assert len(stories) == 1
        assert stories[0].story_points == 5

    def test_validate_valid(self, parser: CsvParser) -> None:
        """Test validation passes for valid CSV."""
        content = "id,title\nUS-001,Valid Story"
        errors = parser.validate(content)
        assert errors == []

    def test_validate_missing_data(self, parser: CsvParser) -> None:
        """Test validation catches missing data."""
        content = "id,title\n,"  # Empty row
        errors = parser.validate(content)
        assert len(errors) > 0

    def test_parse_links_multiple(self, parser: CsvParser) -> None:
        """Test parsing multiple links."""
        content = '''id,title,links
US-001,Test Story,"blocks:PROJ-123;depends_on:OTHER-456"'''

        stories = parser.parse_stories(content)
        links = stories[0].links

        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "OTHER-456") in links

