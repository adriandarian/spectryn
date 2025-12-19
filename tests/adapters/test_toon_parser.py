"""Tests for TOON Parser."""

from pathlib import Path

import pytest

from spectra.adapters.parsers import ToonParser
from spectra.core.domain.enums import Priority, Status


class TestToonParser:
    """Tests for ToonParser class."""

    @pytest.fixture
    def parser(self) -> ToonParser:
        """Create a TOON parser instance."""
        return ToonParser()

    def test_name(self, parser: ToonParser) -> None:
        """Test parser name property."""
        assert parser.name == "TOON"

    def test_supported_extensions(self, parser: ToonParser) -> None:
        """Test supported file extensions."""
        assert parser.supported_extensions == [".toon"]

    def test_can_parse_toon_file(self, parser: ToonParser, tmp_path: Path) -> None:
        """Test can_parse with TOON file."""
        toon_file = tmp_path / "test.toon"
        toon_file.write_text("stories:\n  - id: US-001\n    title: Test")
        assert parser.can_parse(toon_file) is True

    def test_can_parse_toon_content(self, parser: ToonParser) -> None:
        """Test can_parse with TOON content string."""
        content = "stories:\n  - id: US-001\n    title: Test"
        assert parser.can_parse(content) is True

    def test_parse_stories_yaml_style(self, parser: ToonParser) -> None:
        """Test parsing YAML-style TOON content."""
        content = """
stories:
  - id: US-001
    title: Test Story
    story_points: 5
    priority: high
    status: planned
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"
        assert stories[0].story_points == 5
        assert stories[0].priority == Priority.HIGH

    def test_parse_stories_full(self, parser: ToonParser) -> None:
        """Test parsing story with all fields."""
        content = """
stories:
  - id: US-001
    title: Full Story
    story_points: 5
    priority: high
    status: in_progress
    technical_notes: Use standard library
    description:
      as_a: developer
      i_want: to parse TOON
      so_that: I can optimize for LLMs
    acceptance_criteria:
      - criterion: Parse valid TOON
        done: true
      - criterion: Handle errors
        done: false
    subtasks:
      - name: Implement parser
        description: Write the code
        story_points: 3
        status: done
    links:
      - type: blocks
        target: PROJ-123
    comments:
      - body: Good progress
        author: user1
        created_at: "2025-01-15"
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Full Story"
        assert story.description is not None
        assert story.description.role == "developer"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS
        assert len(story.acceptance_criteria.items) == 2
        assert len(story.subtasks) == 1
        assert story.subtasks[0].name == "Implement parser"
        assert len(story.links) == 1
        assert story.links[0] == ("blocks", "PROJ-123")
        assert len(story.comments) == 1
        assert story.comments[0].body == "Good progress"

    def test_parse_epic(self, parser: ToonParser) -> None:
        """Test parsing epic structure."""
        content = """
epic:
  key: PROJ-100
  title: Test Epic
  description: Epic description

stories:
  - id: US-001
    title: Story 1
  - id: US-002
    title: Story 2
"""
        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Test Epic"
        assert epic.description == "Epic description"
        assert len(epic.stories) == 2

    def test_parse_multiple_stories(self, parser: ToonParser) -> None:
        """Test parsing multiple stories."""
        content = """
stories:
  - id: US-001
    title: First Story
    story_points: 3
  - id: US-002
    title: Second Story
    story_points: 5
  - id: US-003
    title: Third Story
    story_points: 8
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 3
        assert stories[0].story_points == 3
        assert stories[1].story_points == 5
        assert stories[2].story_points == 8

    def test_parse_description_string(self, parser: ToonParser) -> None:
        """Test parsing description as simple string."""
        content = """
stories:
  - id: US-001
    title: Test
    description: As a user, I want to login, so that I can access my account
"""
        stories = parser.parse_stories(content)

        assert stories[0].description is not None
        assert stories[0].description.role == "user"
        assert stories[0].description.want == "to login"
        assert "access" in stories[0].description.benefit

    def test_parse_links_shorthand(self, parser: ToonParser) -> None:
        """Test parsing links with shorthand format."""
        content = """
stories:
  - id: US-001
    title: Test
    links:
      - blocks: PROJ-123
      - depends_on:
          - A-1
          - B-2
"""
        stories = parser.parse_stories(content)
        links = stories[0].links

        assert len(links) == 3
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "A-1") in links
        assert ("depends on", "B-2") in links

    def test_parse_comments_simple(self, parser: ToonParser) -> None:
        """Test parsing simple string comments."""
        content = """
stories:
  - id: US-001
    title: Test
    comments:
      - Simple comment
      - Another comment
"""
        stories = parser.parse_stories(content)
        comments = stories[0].comments

        assert len(comments) == 2
        assert comments[0].body == "Simple comment"
        assert comments[0].author is None
        assert comments[1].body == "Another comment"

    def test_validate_valid(self, parser: ToonParser) -> None:
        """Test validation passes for valid TOON."""
        content = """
stories:
  - id: US-001
    title: Valid Story
"""
        errors = parser.validate(content)
        assert errors == []

    def test_validate_missing_id(self, parser: ToonParser) -> None:
        """Test validation catches missing id."""
        content = """
stories:
  - title: No ID
"""
        errors = parser.validate(content)
        assert any("id" in e for e in errors)

    def test_validate_missing_title(self, parser: ToonParser) -> None:
        """Test validation catches missing title."""
        content = """
stories:
  - id: US-001
"""
        errors = parser.validate(content)
        assert any("title" in e for e in errors)

    def test_validate_invalid_priority(self, parser: ToonParser) -> None:
        """Test validation catches invalid priority."""
        content = """
stories:
  - id: US-001
    title: Test
    priority: invalid
"""
        errors = parser.validate(content)
        assert any("priority" in e for e in errors)

    def test_parse_from_file(self, parser: ToonParser, tmp_path: Path) -> None:
        """Test parsing from actual file."""
        toon_file = tmp_path / "stories.toon"
        toon_file.write_text("""
stories:
  - id: US-001
    title: From File
    story_points: 5
""")
        stories = parser.parse_stories(toon_file)

        assert len(stories) == 1
        assert stories[0].title == "From File"
        assert stories[0].story_points == 5

    def test_parse_subtasks_string_format(self, parser: ToonParser) -> None:
        """Test parsing subtasks as simple strings."""
        content = """
stories:
  - id: US-001
    title: Test
    subtasks:
      - Task 1
      - Task 2
"""
        stories = parser.parse_stories(content)
        subtasks = stories[0].subtasks

        assert len(subtasks) == 2
        assert subtasks[0].name == "Task 1"
        assert subtasks[0].number == 1
        assert subtasks[1].name == "Task 2"
        assert subtasks[1].number == 2

    def test_parse_acceptance_criteria_string(self, parser: ToonParser) -> None:
        """Test parsing acceptance criteria as simple strings."""
        content = """
stories:
  - id: US-001
    title: Test
    acceptance_criteria:
      - Criterion 1
      - Criterion 2
"""
        stories = parser.parse_stories(content)
        ac = stories[0].acceptance_criteria

        assert len(ac.items) == 2
        assert "Criterion 1" in ac.items
        assert "Criterion 2" in ac.items
