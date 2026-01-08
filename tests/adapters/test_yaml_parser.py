"""
Tests for YAML Parser.
"""

from textwrap import dedent

import pytest

from spectryn.adapters.parsers.yaml_parser import YamlParser
from spectryn.adapters.parsers.yaml_plugin import YamlParserPlugin, create_plugin
from spectryn.core.domain.enums import Priority, Status


# =============================================================================
# YamlParser Tests
# =============================================================================


class TestYamlParser:
    """Tests for YamlParser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return YamlParser()

    # -------------------------------------------------------------------------
    # Basic Properties
    # -------------------------------------------------------------------------

    def test_name(self, parser):
        """Should return 'YAML' as parser name."""
        assert parser.name == "YAML"

    def test_supported_extensions(self, parser):
        """Should support .yaml and .yml extensions."""
        extensions = parser.supported_extensions
        assert ".yaml" in extensions
        assert ".yml" in extensions

    # -------------------------------------------------------------------------
    # can_parse Tests
    # -------------------------------------------------------------------------

    def test_can_parse_yaml_file_path(self, parser, tmp_path):
        """Should detect YAML files by extension."""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("stories: []")

        assert parser.can_parse(yaml_file) is True

    def test_can_parse_yml_file_path(self, parser, tmp_path):
        """Should detect .yml files by extension."""
        yml_file = tmp_path / "test.yml"
        yml_file.write_text("stories: []")

        assert parser.can_parse(yml_file) is True

    def test_can_parse_yaml_content(self, parser):
        """Should detect valid YAML content with expected structure."""
        content = "stories:\n  - id: US-001\n    title: Test"
        assert parser.can_parse(content) is True

    def test_cannot_parse_invalid_yaml(self, parser):
        """Should reject invalid YAML."""
        content = "this is not: valid: yaml:"
        assert parser.can_parse(content) is False

    def test_cannot_parse_yaml_without_expected_keys(self, parser):
        """Should reject YAML without stories or epic keys."""
        content = "some_key: some_value"
        assert parser.can_parse(content) is False

    # -------------------------------------------------------------------------
    # parse_stories Tests
    # -------------------------------------------------------------------------

    def test_parse_simple_story(self, parser):
        """Should parse a minimal story."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Simple Story"
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Simple Story"

    def test_parse_story_with_structured_description(self, parser):
        """Should parse structured description format."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story with Description"
                description:
                  as_a: "user"
                  i_want: "to do something"
                  so_that: "I get benefit"
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        desc = stories[0].description
        assert desc is not None
        assert desc.role == "user"
        assert desc.want == "to do something"
        assert desc.benefit == "I get benefit"

    def test_parse_story_with_string_description(self, parser):
        """Should parse string description format."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                description: "As a user, I want feature so that benefit"
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        desc = stories[0].description
        assert desc is not None
        assert desc.role == "user"
        assert "feature" in desc.want

    def test_parse_story_points(self, parser):
        """Should parse story points."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                story_points: 5
        """
        )

        stories = parser.parse_stories(content)

        assert stories[0].story_points == 5

    def test_parse_priority(self, parser):
        """Should parse priority values."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "High Priority"
                priority: high
              - id: US-002
                title: "Low Priority"
                priority: low
        """
        )

        stories = parser.parse_stories(content)

        assert stories[0].priority == Priority.HIGH
        assert stories[1].priority == Priority.LOW

    def test_parse_status(self, parser):
        """Should parse status values."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "In Progress"
                status: in_progress
              - id: US-002
                title: "Done"
                status: done
        """
        )

        stories = parser.parse_stories(content)

        assert stories[0].status == Status.IN_PROGRESS
        assert stories[1].status == Status.DONE

    def test_parse_acceptance_criteria_structured(self, parser):
        """Should parse structured acceptance criteria."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                acceptance_criteria:
                  - criterion: "First criterion"
                    done: false
                  - criterion: "Second criterion"
                    done: true
        """
        )

        stories = parser.parse_stories(content)

        ac = stories[0].acceptance_criteria
        assert len(ac.items) == 2
        assert ac.items[0] == "First criterion"
        assert ac.items[1] == "Second criterion"
        assert ac.checked[0] is False
        assert ac.checked[1] is True

    def test_parse_acceptance_criteria_simple(self, parser):
        """Should parse simple string acceptance criteria."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                acceptance_criteria:
                  - "First criterion"
                  - "Second criterion"
        """
        )

        stories = parser.parse_stories(content)

        ac = stories[0].acceptance_criteria
        assert len(ac.items) == 2
        assert ac.items[0] == "First criterion"
        assert all(c is False for c in ac.checked)

    def test_parse_subtasks_structured(self, parser):
        """Should parse structured subtasks."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                subtasks:
                  - name: "Subtask 1"
                    description: "Do something"
                    story_points: 2
                    status: planned
                  - name: "Subtask 2"
                    story_points: 3
                    status: in_progress
        """
        )

        stories = parser.parse_stories(content)

        subtasks = stories[0].subtasks
        assert len(subtasks) == 2
        assert subtasks[0].name == "Subtask 1"
        assert subtasks[0].description == "Do something"
        assert subtasks[0].story_points == 2
        assert subtasks[0].status == Status.PLANNED
        assert subtasks[1].status == Status.IN_PROGRESS

    def test_parse_subtasks_simple(self, parser):
        """Should parse simple string subtasks."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                subtasks:
                  - "Do first thing"
                  - "Do second thing"
        """
        )

        stories = parser.parse_stories(content)

        subtasks = stories[0].subtasks
        assert len(subtasks) == 2
        assert subtasks[0].name == "Do first thing"
        assert subtasks[1].name == "Do second thing"

    def test_parse_commits(self, parser):
        """Should parse commit references."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                commits:
                  - hash: "a1b2c3d4e5f6"
                    message: "Add feature"
                  - "b2c3d4e5"
        """
        )

        stories = parser.parse_stories(content)

        commits = stories[0].commits
        assert len(commits) == 2
        assert commits[0].hash == "a1b2c3d4"  # Truncated to 8 chars
        assert commits[0].message == "Add feature"
        assert commits[1].hash == "b2c3d4e5"

    # -------------------------------------------------------------------------
    # Links Tests
    # -------------------------------------------------------------------------

    def test_parse_links_structured(self, parser):
        """Should parse structured link format."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story with Links"
                links:
                  - type: "blocks"
                    target: "PROJ-123"
                  - type: "depends on"
                    target: "OTHER-456"
        """
        )

        stories = parser.parse_stories(content)

        links = stories[0].links
        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "OTHER-456") in links

    def test_parse_links_shorthand(self, parser):
        """Should parse shorthand link format."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story with Links"
                links:
                  - blocks: "PROJ-123"
                  - relates_to: "OTHER-456"
        """
        )

        stories = parser.parse_stories(content)

        links = stories[0].links
        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("relates to", "OTHER-456") in links

    def test_parse_links_shorthand_multiple_targets(self, parser):
        """Should parse shorthand links with multiple targets."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story with Links"
                links:
                  - blocks:
                      - "PROJ-123"
                      - "PROJ-456"
        """
        )

        stories = parser.parse_stories(content)

        links = stories[0].links
        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("blocks", "PROJ-456") in links

    def test_parse_links_string_format(self, parser):
        """Should parse simple string link format."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story with Links"
                links:
                  - "blocks PROJ-123"
                  - "depends_on OTHER-456"
        """
        )

        stories = parser.parse_stories(content)

        links = stories[0].links
        assert len(links) == 2
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "OTHER-456") in links

    def test_parse_links_empty(self, parser):
        """Should handle story without links."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story without Links"
        """
        )

        stories = parser.parse_stories(content)

        assert stories[0].links == []

    def test_parse_technical_notes(self, parser):
        """Should parse technical notes."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                technical_notes: |
                  Some technical details here.
                  Multi-line notes.
        """
        )

        stories = parser.parse_stories(content)

        assert "technical details" in stories[0].technical_notes

    def test_parse_multiple_stories(self, parser):
        """Should parse multiple stories."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "First Story"
                story_points: 3
              - id: US-002
                title: "Second Story"
                story_points: 5
              - id: US-003
                title: "Third Story"
                story_points: 8
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 3
        assert stories[0].story_points == 3
        assert stories[1].story_points == 5
        assert stories[2].story_points == 8

    # -------------------------------------------------------------------------
    # parse_epic Tests
    # -------------------------------------------------------------------------

    def test_parse_epic_basic(self, parser):
        """Should parse basic epic structure."""
        content = dedent(
            """
            epic:
              title: "Epic Title"
              description: "Epic description"

            stories:
              - id: US-001
                title: "Story"
        """
        )

        epic = parser.parse_epic(content)

        assert epic is not None
        assert epic.title == "Epic Title"
        assert len(epic.stories) == 1

    def test_parse_epic_with_key(self, parser):
        """Should parse epic with existing key."""
        content = dedent(
            """
            epic:
              key: PROJ-123
              title: "Epic Title"

            stories:
              - id: US-001
                title: "Story"
        """
        )

        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"

    def test_parse_epic_stories_only(self, parser):
        """Should create epic from stories-only file."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
        """
        )

        epic = parser.parse_epic(content)

        assert epic is not None
        assert epic.title == "Untitled Epic"
        assert len(epic.stories) == 1

    def test_parse_epic_empty_returns_none(self, parser):
        """Should return None for empty content."""
        content = "stories: []"

        epic = parser.parse_epic(content)

        assert epic is None

    # -------------------------------------------------------------------------
    # validate Tests
    # -------------------------------------------------------------------------

    def test_validate_valid_content(self, parser):
        """Should return empty errors for valid content."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Valid Story"
        """
        )

        errors = parser.validate(content)

        assert len(errors) == 0

    def test_validate_missing_stories_and_epic(self, parser):
        """Should report error for missing required keys."""
        content = "some_key: some_value"

        errors = parser.validate(content)

        assert any("stories" in e or "epic" in e for e in errors)

    def test_validate_missing_story_id(self, parser):
        """Should report missing story ID."""
        content = dedent(
            """
            stories:
              - title: "Story without ID"
        """
        )

        errors = parser.validate(content)

        assert any("id" in e for e in errors)

    def test_validate_missing_story_title(self, parser):
        """Should report missing story title."""
        content = dedent(
            """
            stories:
              - id: US-001
        """
        )

        errors = parser.validate(content)

        assert any("title" in e for e in errors)

    def test_validate_invalid_priority(self, parser):
        """Should report invalid priority value."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                priority: invalid_priority
        """
        )

        errors = parser.validate(content)

        assert any("priority" in e for e in errors)

    def test_validate_invalid_status(self, parser):
        """Should report invalid status value."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                status: invalid_status
        """
        )

        errors = parser.validate(content)

        assert any("status" in e for e in errors)

    def test_validate_invalid_yaml_syntax(self, parser):
        """Should report YAML syntax errors."""
        content = "invalid: yaml: syntax:"

        errors = parser.validate(content)

        assert len(errors) > 0

    def test_validate_story_points_must_be_number(self, parser):
        """Should report error for non-numeric story points."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                story_points: "five"
        """
        )

        errors = parser.validate(content)

        assert any("story_points" in e for e in errors)

    # -------------------------------------------------------------------------
    # File Handling Tests
    # -------------------------------------------------------------------------

    def test_parse_from_file(self, parser, tmp_path):
        """Should parse from actual file."""
        yaml_file = tmp_path / "stories.yaml"
        yaml_file.write_text(
            dedent(
                """
            stories:
              - id: US-001
                title: "From File"
                story_points: 3
        """
            )
        )

        stories = parser.parse_stories(yaml_file)

        assert len(stories) == 1
        assert stories[0].title == "From File"

    def test_parse_from_file_path_string(self, parser, tmp_path):
        """Should parse from file path as string."""
        yaml_file = tmp_path / "stories.yaml"
        yaml_file.write_text("stories:\n  - id: US-001\n    title: Test")

        stories = parser.parse_stories(str(yaml_file))

        assert len(stories) == 1


# =============================================================================
# YamlParserPlugin Tests
# =============================================================================


class TestYamlParserPlugin:
    """Tests for YamlParserPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = YamlParserPlugin()

        assert plugin.metadata.name == "yaml-parser"
        assert plugin.metadata.version == "1.0.0"
        assert "YAML" in plugin.metadata.description

    def test_initialize_creates_parser(self):
        """Should create parser on initialize."""
        plugin = YamlParserPlugin()

        plugin.initialize()

        assert plugin.is_initialized
        assert plugin._parser is not None

    def test_get_parser_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = YamlParserPlugin()

        with pytest.raises(RuntimeError):
            plugin.get_parser()

    def test_get_parser_after_initialize(self):
        """Should return parser after initialization."""
        plugin = YamlParserPlugin()
        plugin.initialize()

        parser = plugin.get_parser()

        assert parser is not None
        assert parser.name == "YAML"

    def test_shutdown_clears_parser(self):
        """Should clear parser on shutdown."""
        plugin = YamlParserPlugin()
        plugin.initialize()
        plugin.shutdown()

        assert not plugin.is_initialized
        assert plugin._parser is None

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        plugin = create_plugin()

        assert isinstance(plugin, YamlParserPlugin)

    def test_create_plugin_with_config(self):
        """Should create plugin with config."""
        config = {"strict": True}
        plugin = create_plugin(config)

        assert plugin.config == config


# =============================================================================
# Integration Tests
# =============================================================================


class TestYamlParserIntegration:
    """Integration tests for YAML parser."""

    def test_full_story_roundtrip(self):
        """Should parse a complete story with all fields."""
        content = dedent(
            """
            epic:
              key: PROJ-100
              title: "Complete Epic"
              description: "A full-featured epic"

            stories:
              - id: US-001
                title: "Complete Story"
                description:
                  as_a: "developer"
                  i_want: "comprehensive testing"
                  so_that: "code is reliable"
                story_points: 8
                priority: high
                status: in_progress
                acceptance_criteria:
                  - criterion: "All tests pass"
                    done: true
                  - criterion: "Coverage > 80%"
                    done: false
                subtasks:
                  - name: "Write unit tests"
                    description: "Cover core functionality"
                    story_points: 3
                    status: done
                  - name: "Write integration tests"
                    story_points: 5
                    status: in_progress
                commits:
                  - hash: "abc12345"
                    message: "Add test framework"
                technical_notes: |
                  Using pytest for testing.
                  Mock external dependencies.
        """
        )

        parser = YamlParser()
        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Complete Epic"

        story = epic.stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Complete Story"
        assert story.story_points == 8
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS

        assert story.description is not None
        assert story.description.role == "developer"

        assert len(story.acceptance_criteria.items) == 2
        assert story.acceptance_criteria.checked[0] is True

        assert len(story.subtasks) == 2
        assert story.subtasks[0].status == Status.DONE

        assert len(story.commits) == 1
        assert story.commits[0].hash == "abc12345"

        assert "pytest" in story.technical_notes

    def test_validate_then_parse(self):
        """Should validate before parsing for safety."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Valid Story"
                story_points: 5
        """
        )

        parser = YamlParser()

        # Validate first
        errors = parser.validate(content)
        assert len(errors) == 0

        # Then parse
        stories = parser.parse_stories(content)
        assert len(stories) == 1

    def test_parse_with_alternative_field_names(self):
        """Should accept alternative field name formats."""
        content = dedent(
            """
            stories:
              - id: US-001
                title: "Story"
                description:
                  role: "user"
                  want: "feature"
                  benefit: "value"
                subtasks:
                  - title: "Subtask"
                    sp: 2
        """
        )

        parser = YamlParser()
        stories = parser.parse_stories(content)

        assert stories[0].description.role == "user"
        assert stories[0].subtasks[0].story_points == 2
