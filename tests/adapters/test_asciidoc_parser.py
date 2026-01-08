"""Tests for AsciiDoc Parser."""

from pathlib import Path

import pytest

from spectryn.adapters.parsers import AsciiDocParser
from spectryn.core.domain.enums import Priority, Status


class TestAsciiDocParser:
    """Tests for AsciiDocParser class."""

    @pytest.fixture
    def parser(self) -> AsciiDocParser:
        """Create an AsciiDoc parser instance."""
        return AsciiDocParser()

    def test_name(self, parser: AsciiDocParser) -> None:
        """Test parser name property."""
        assert parser.name == "AsciiDoc"

    def test_supported_extensions(self, parser: AsciiDocParser) -> None:
        """Test supported file extensions."""
        assert ".adoc" in parser.supported_extensions
        assert ".asciidoc" in parser.supported_extensions

    def test_can_parse_adoc_file(self, parser: AsciiDocParser, tmp_path: Path) -> None:
        """Test can_parse with AsciiDoc file."""
        adoc_file = tmp_path / "test.adoc"
        adoc_file.write_text("= Epic Title\n\n== US-001: Test Story")
        assert parser.can_parse(adoc_file) is True

    def test_can_parse_adoc_content(self, parser: AsciiDocParser) -> None:
        """Test can_parse with AsciiDoc content string."""
        content = "= Epic Title\n\n== US-001: Test Story"
        assert parser.can_parse(content) is True

    def test_parse_stories_minimal(self, parser: AsciiDocParser) -> None:
        """Test parsing minimal story structure."""
        content = """
= Epic Title

== US-001: Test Story

Some content here.
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"

    def test_parse_stories_with_metadata(self, parser: AsciiDocParser) -> None:
        """Test parsing story with table metadata."""
        content = """
= Epic Title

== US-001: Full Story

[cols="1,1"]
|===
| *Story Points* | 5
| *Priority* | High
| *Status* | In Progress
|===

=== Description

*As a* developer +
*I want* to parse AsciiDoc +
*So that* I can use rich documentation

=== Acceptance Criteria

* [ ] Parse valid AsciiDoc
* [x] Extract metadata from tables

=== Technical Notes

Implementation details here.
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Full Story"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS
        assert story.description is not None
        assert story.description.role == "developer"
        assert len(story.acceptance_criteria.items) == 2
        assert story.technical_notes == "Implementation details here."

    def test_parse_multiple_stories(self, parser: AsciiDocParser) -> None:
        """Test parsing multiple stories."""
        content = """
= Epic Title

== US-001: First Story

First story content.

== US-002: Second Story

Second story content.

== US-003: Third Story

Third story content.
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 3
        assert str(stories[0].id) == "US-001"
        assert str(stories[1].id) == "US-002"
        assert str(stories[2].id) == "US-003"

    def test_parse_epic(self, parser: AsciiDocParser) -> None:
        """Test parsing epic with key attribute."""
        content = """
= My Epic Title
:epic-key: PROJ-100

== US-001: Story 1

Content.
"""
        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "My Epic Title"
        assert len(epic.stories) == 1

    def test_parse_subtasks_table(self, parser: AsciiDocParser) -> None:
        """Test parsing subtasks from table."""
        content = """
= Epic

== US-001: Story

=== Subtasks

[cols="1,3,1,1"]
|===
| # | Task | SP | Status

| 1 | Implement feature | 2 | Planned
| 2 | Write tests | 1 | Done
|===
"""
        stories = parser.parse_stories(content)
        subtasks = stories[0].subtasks

        assert len(subtasks) == 2
        assert subtasks[0].name == "Implement feature"
        assert subtasks[0].story_points == 2
        assert subtasks[1].name == "Write tests"
        assert subtasks[1].status == Status.DONE

    def test_parse_links(self, parser: AsciiDocParser) -> None:
        """Test parsing links section."""
        content = """
= Epic

== US-001: Story

=== Links

* blocks: PROJ-123
* depends on: OTHER-456
"""
        stories = parser.parse_stories(content)
        links = stories[0].links

        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "OTHER-456") in links

    def test_validate_valid(self, parser: AsciiDocParser) -> None:
        """Test validation passes for valid AsciiDoc."""
        content = "= Epic\n\n== US-001: Valid Story"
        errors = parser.validate(content)
        assert errors == []

    def test_validate_no_stories(self, parser: AsciiDocParser) -> None:
        """Test validation catches missing stories."""
        content = "= Just a title\n\nNo stories here."
        errors = parser.validate(content)
        assert any("No user stories" in e for e in errors)
