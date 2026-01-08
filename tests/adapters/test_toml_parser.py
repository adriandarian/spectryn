"""Tests for TOML Parser."""

from pathlib import Path

import pytest

from spectryn.adapters.parsers import TomlParser
from spectryn.core.domain.enums import Priority, Status


class TestTomlParser:
    """Tests for TomlParser class."""

    @pytest.fixture
    def parser(self) -> TomlParser:
        """Create a TOML parser instance."""
        return TomlParser()

    def test_name(self, parser: TomlParser) -> None:
        """Test parser name property."""
        assert parser.name == "TOML"

    def test_supported_extensions(self, parser: TomlParser) -> None:
        """Test supported file extensions."""
        assert parser.supported_extensions == [".toml"]

    def test_can_parse_toml_file(self, parser: TomlParser, tmp_path: Path) -> None:
        """Test can_parse with TOML file."""
        toml_file = tmp_path / "test.toml"
        toml_file.write_text('[[stories]]\nid = "US-001"\ntitle = "Test"')
        assert parser.can_parse(toml_file) is True

    def test_can_parse_toml_content(self, parser: TomlParser) -> None:
        """Test can_parse with TOML content string."""
        content = '[[stories]]\nid = "US-001"\ntitle = "Test"'
        assert parser.can_parse(content) is True

    def test_parse_stories_minimal(self, parser: TomlParser) -> None:
        """Test parsing minimal story structure."""
        content = """
[[stories]]
id = "US-001"
title = "Test Story"
"""
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"

    def test_parse_stories_full(self, parser: TomlParser) -> None:
        """Test parsing story with all fields."""
        content = """
[[stories]]
id = "US-001"
title = "Full Story"
story_points = 5
priority = "high"
status = "in_progress"
technical_notes = "Use standard library"

[stories.description]
as_a = "developer"
i_want = "to parse TOML"
so_that = "I can use config files"

[[stories.acceptance_criteria]]
criterion = "Parse valid TOML"
done = true

[[stories.acceptance_criteria]]
criterion = "Handle errors"
done = false

[[stories.subtasks]]
name = "Implement parser"
description = "Write the code"
story_points = 3
status = "done"

[[stories.links]]
type = "blocks"
target = "PROJ-123"

[[stories.comments]]
body = "Good progress"
author = "user1"
created_at = "2025-01-15"
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
        assert len(story.links) == 1
        assert len(story.comments) == 1

    def test_parse_epic(self, parser: TomlParser) -> None:
        """Test parsing epic structure."""
        content = """
[epic]
key = "PROJ-100"
title = "Test Epic"
description = "Epic description"

[[stories]]
id = "US-001"
title = "Story 1"

[[stories]]
id = "US-002"
title = "Story 2"
"""
        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Test Epic"
        assert len(epic.stories) == 2

    def test_validate_valid(self, parser: TomlParser) -> None:
        """Test validation passes for valid TOML."""
        content = """
[[stories]]
id = "US-001"
title = "Valid Story"
"""
        errors = parser.validate(content)
        assert errors == []

    def test_validate_missing_fields(self, parser: TomlParser) -> None:
        """Test validation catches missing fields."""
        content = """
[[stories]]
title = "No ID"
"""
        errors = parser.validate(content)
        assert any("id" in e for e in errors)
