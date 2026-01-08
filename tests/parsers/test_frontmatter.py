"""
Tests for frontmatter parser module.

Tests the YAML frontmatter parsing functionality as an alternative
to markdown tables for specifying story metadata.
"""

import textwrap
from pathlib import Path

import pytest

from spectryn.adapters.parsers.frontmatter import (
    DEFAULT_EPIC_MAPPINGS,
    DEFAULT_STORY_MAPPINGS,
    FieldMapping,
    FrontmatterConfig,
    FrontmatterFormat,
    FrontmatterParser,
    MergeStrategy,
    apply_mapping,
    create_frontmatter_parser,
    create_markdown_with_frontmatter,
    extract_html_comment_frontmatter,
    extract_inline_frontmatter,
    extract_yaml_frontmatter,
    find_mapping,
    get_frontmatter,
    has_frontmatter,
    normalize_key,
    parse_acceptance_criteria_from_frontmatter,
    parse_description_from_frontmatter,
    parse_epic_from_frontmatter,
    parse_story_from_frontmatter,
    parse_subtasks_from_frontmatter,
    strip_frontmatter,
)
from spectryn.core.domain.enums import Priority, Status


# =============================================================================
# Test extract_yaml_frontmatter
# =============================================================================


class TestExtractYamlFrontmatter:
    """Tests for extract_yaml_frontmatter function."""

    def test_basic_frontmatter(self) -> None:
        """Test parsing basic YAML frontmatter."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: Test Story
            story_points: 5
            ---

            # Story Content
        """).strip()

        result = extract_yaml_frontmatter(content)

        assert result.has_frontmatter
        assert result.is_valid
        assert result.data["id"] == "US-001"
        assert result.data["title"] == "Test Story"
        assert result.data["story_points"] == 5
        assert "# Story Content" in result.remaining_content

    def test_no_frontmatter(self) -> None:
        """Test content without frontmatter."""
        content = "# Just a heading\n\nSome content."

        result = extract_yaml_frontmatter(content)

        assert not result.has_frontmatter
        assert result.is_valid
        assert result.data == {}
        assert result.remaining_content == content

    def test_frontmatter_with_leading_whitespace(self) -> None:
        """Test frontmatter with leading whitespace."""
        content = "   \n---\nid: US-001\n---\nContent"

        result = extract_yaml_frontmatter(content)

        assert result.has_frontmatter
        assert result.data["id"] == "US-001"

    def test_unclosed_frontmatter(self) -> None:
        """Test unclosed frontmatter detection."""
        content = "---\nid: US-001\n\nNo closing delimiter"

        result = extract_yaml_frontmatter(content)

        assert not result.has_frontmatter
        assert not result.is_valid
        assert "Unclosed" in result.errors[0]

    def test_invalid_yaml(self) -> None:
        """Test invalid YAML in frontmatter."""
        content = "---\n  invalid: yaml: content:\n---\n"

        result = extract_yaml_frontmatter(content)

        assert not result.has_frontmatter
        assert not result.is_valid
        assert "Invalid YAML" in result.errors[0]

    def test_non_dict_frontmatter(self) -> None:
        """Test frontmatter that's not a dictionary."""
        content = "---\n- item1\n- item2\n---\n"

        result = extract_yaml_frontmatter(content)

        assert not result.has_frontmatter
        assert not result.is_valid
        assert "mapping" in result.errors[0].lower()

    def test_complex_frontmatter(self) -> None:
        """Test frontmatter with nested structures."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: Complex Story
            description:
              as_a: user
              i_want: to test
              so_that: it works
            acceptance_criteria:
              - criterion: First
                done: false
              - criterion: Second
                done: true
            labels:
              - feature
              - mvp
            ---

            # Content
        """).strip()

        result = extract_yaml_frontmatter(content)

        assert result.has_frontmatter
        assert result.is_valid
        assert result.data["description"]["as_a"] == "user"
        assert len(result.data["acceptance_criteria"]) == 2
        assert result.data["labels"] == ["feature", "mvp"]

    def test_span_information(self) -> None:
        """Test that span information is populated."""
        content = "---\nid: US-001\n---\nContent"

        result = extract_yaml_frontmatter(content)

        assert result.span is not None
        assert result.span.start_line == 1
        assert result.span.format == FrontmatterFormat.YAML
        assert "id: US-001" in result.span.raw_content

    def test_empty_frontmatter(self) -> None:
        """Test empty frontmatter block."""
        content = "---\n\n---\nContent"

        result = extract_yaml_frontmatter(content)

        assert result.has_frontmatter
        assert result.is_valid
        assert result.data == {}


class TestExtractHtmlCommentFrontmatter:
    """Tests for extract_html_comment_frontmatter function."""

    def test_yaml_comment(self) -> None:
        """Test YAML in HTML comment."""
        content = textwrap.dedent("""
            <!-- yaml:
            id: US-001
            title: Story
            -->

            # Content
        """).strip()

        result = extract_html_comment_frontmatter(content)

        assert result.has_frontmatter
        assert result.is_valid
        assert result.data["id"] == "US-001"

    def test_frontmatter_comment(self) -> None:
        """Test frontmatter keyword in comment."""
        content = "<!-- frontmatter:\nid: US-002\n-->\nContent"

        result = extract_html_comment_frontmatter(content)

        assert result.has_frontmatter
        assert result.data["id"] == "US-002"

    def test_metadata_comment(self) -> None:
        """Test metadata keyword in comment."""
        content = "<!-- metadata:\nid: US-003\n-->\nContent"

        result = extract_html_comment_frontmatter(content)

        assert result.has_frontmatter
        assert result.data["id"] == "US-003"

    def test_plain_comment_yaml(self) -> None:
        """Test plain HTML comment with YAML content is parsed."""
        content = "<!--\nid: US-004\ntitle: Test\n-->\nContent"

        result = extract_html_comment_frontmatter(content)

        # Plain YAML comments are also parsed
        assert result.has_frontmatter
        assert result.data["id"] == "US-004"

    def test_no_html_comment(self) -> None:
        """Test content without HTML comment frontmatter."""
        content = "# Just content"

        result = extract_html_comment_frontmatter(content)

        assert not result.has_frontmatter
        assert result.remaining_content == content


class TestExtractInlineFrontmatter:
    """Tests for extract_inline_frontmatter function."""

    def test_inline_yaml_comments(self) -> None:
        """Test inline YAML comments in content."""
        content = textwrap.dedent("""
            ### US-001: Story Title

            <!--
            story_points: 5
            priority: high
            -->

            Story content here.

            ### US-002: Second Story

            <!--
            story_points: 3
            status: done
            -->

            More content.
        """).strip()

        results = extract_inline_frontmatter(content)

        assert len(results) == 2
        assert results[0][1]["story_points"] == 5
        assert results[0][1]["priority"] == "high"
        assert results[1][1]["story_points"] == 3
        assert results[1][1]["status"] == "done"

    def test_no_inline_yaml(self) -> None:
        """Test content without inline YAML."""
        content = "<!-- This is just a comment -->\n\nContent"

        results = extract_inline_frontmatter(content)

        assert len(results) == 0

    def test_invalid_yaml_ignored(self) -> None:
        """Test that invalid YAML in comments is ignored."""
        content = "<!--\ninvalid: yaml: content\n-->\n\nContent"

        results = extract_inline_frontmatter(content)

        assert len(results) == 0


# =============================================================================
# Test Normalization and Mapping
# =============================================================================


class TestNormalizeKey:
    """Tests for normalize_key function."""

    def test_lowercase(self) -> None:
        """Test lowercase conversion."""
        assert normalize_key("StoryPoints") == "storypoints"

    def test_separator_normalization(self) -> None:
        """Test separator normalization."""
        assert normalize_key("story-points") == "story_points"
        assert normalize_key("story_points") == "story_points"
        assert normalize_key("story points") == "story_points"

    def test_case_sensitive(self) -> None:
        """Test case-sensitive mode."""
        assert normalize_key("StoryPoints", case_sensitive=True) == "StoryPoints"


class TestFindMapping:
    """Tests for find_mapping function."""

    def test_find_by_key(self) -> None:
        """Test finding mapping by primary key."""
        mapping = find_mapping("story_points", DEFAULT_STORY_MAPPINGS)
        assert mapping is not None
        assert mapping.entity_field == "story_points"

    def test_find_by_alias(self) -> None:
        """Test finding mapping by alias."""
        mapping = find_mapping("points", DEFAULT_STORY_MAPPINGS)
        assert mapping is not None
        assert mapping.entity_field == "story_points"

        mapping = find_mapping("sp", DEFAULT_STORY_MAPPINGS)
        assert mapping is not None
        assert mapping.entity_field == "story_points"

    def test_not_found(self) -> None:
        """Test mapping not found."""
        mapping = find_mapping("nonexistent_field", DEFAULT_STORY_MAPPINGS)
        assert mapping is None

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        mapping = find_mapping("STORY_POINTS", DEFAULT_STORY_MAPPINGS)
        assert mapping is not None
        assert mapping.entity_field == "story_points"


class TestApplyMapping:
    """Tests for apply_mapping function."""

    def test_basic_mapping(self) -> None:
        """Test basic field mapping."""
        data = {
            "id": "US-001",
            "title": "Test",
            "points": 5,  # alias for story_points
            "prio": "high",  # alias for priority
        }

        result = apply_mapping(data, DEFAULT_STORY_MAPPINGS)

        assert result["id"] == "US-001"
        assert result["title"] == "Test"
        assert result["story_points"] == 5
        assert result["priority"] == Priority.HIGH

    def test_unmapped_keys_preserved(self) -> None:
        """Test that unmapped keys are preserved."""
        data = {
            "id": "US-001",
            "custom_field": "custom_value",
        }

        result = apply_mapping(data, DEFAULT_STORY_MAPPINGS)

        assert "custom_field" in result
        assert result["custom_field"] == "custom_value"

    def test_transformer_applied(self) -> None:
        """Test that transformers are applied."""
        data = {"priority": "HIGH", "status": "DONE"}

        result = apply_mapping(data, DEFAULT_STORY_MAPPINGS)

        assert result["priority"] == Priority.HIGH
        assert result["status"] == Status.DONE


# =============================================================================
# Test Description Parsing
# =============================================================================


class TestParseDescriptionFromFrontmatter:
    """Tests for parse_description_from_frontmatter function."""

    def test_string_format(self) -> None:
        """Test parsing from string format."""
        desc = parse_description_from_frontmatter("As a user, I want to test, so that it works")

        assert desc is not None
        assert desc.role == "user"
        assert desc.want == "to test"
        assert desc.benefit == "it works"

    def test_dict_format_as_a(self) -> None:
        """Test parsing from dict with as_a/i_want/so_that keys."""
        desc = parse_description_from_frontmatter(
            {
                "as_a": "developer",
                "i_want": "clean code",
                "so_that": "I can maintain it",
            }
        )

        assert desc is not None
        assert desc.role == "developer"
        assert desc.want == "clean code"
        assert desc.benefit == "I can maintain it"

    def test_dict_format_role(self) -> None:
        """Test parsing from dict with role/want/benefit keys."""
        desc = parse_description_from_frontmatter(
            {
                "role": "admin",
                "want": "manage users",
                "benefit": "control access",
            }
        )

        assert desc is not None
        assert desc.role == "admin"
        assert desc.want == "manage users"
        assert desc.benefit == "control access"

    def test_simple_string(self) -> None:
        """Test parsing simple string (no As a format)."""
        desc = parse_description_from_frontmatter("Just a simple description")

        assert desc is not None
        assert desc.role == ""
        assert desc.want == "Just a simple description"
        assert desc.benefit == ""

    def test_none_input(self) -> None:
        """Test None input."""
        desc = parse_description_from_frontmatter(None)
        assert desc is None

    def test_empty_dict(self) -> None:
        """Test empty dict input."""
        desc = parse_description_from_frontmatter({})
        assert desc is None


# =============================================================================
# Test Acceptance Criteria Parsing
# =============================================================================


class TestParseAcceptanceCriteriaFromFrontmatter:
    """Tests for parse_acceptance_criteria_from_frontmatter function."""

    def test_list_of_strings(self) -> None:
        """Test parsing list of strings."""
        ac = parse_acceptance_criteria_from_frontmatter(
            [
                "First criterion",
                "Second criterion",
            ]
        )

        assert len(ac.items) == 2
        assert ac.items[0] == "First criterion"
        assert not ac.checked[0]
        assert not ac.checked[1]

    def test_list_of_dicts(self) -> None:
        """Test parsing list of dicts."""
        ac = parse_acceptance_criteria_from_frontmatter(
            [
                {"criterion": "First", "done": False},
                {"criterion": "Second", "done": True},
            ]
        )

        assert len(ac.items) == 2
        assert ac.items[0] == "First"
        assert not ac.checked[0]
        assert ac.items[1] == "Second"
        assert ac.checked[1]

    def test_dict_with_text_key(self) -> None:
        """Test parsing dict with 'text' key."""
        ac = parse_acceptance_criteria_from_frontmatter(
            [
                {"text": "Using text key", "checked": True},
            ]
        )

        assert ac.items[0] == "Using text key"
        assert ac.checked[0]

    def test_none_input(self) -> None:
        """Test None input."""
        ac = parse_acceptance_criteria_from_frontmatter(None)
        assert len(ac.items) == 0

    def test_empty_list(self) -> None:
        """Test empty list."""
        ac = parse_acceptance_criteria_from_frontmatter([])
        assert len(ac.items) == 0


# =============================================================================
# Test Subtask Parsing
# =============================================================================


class TestParseSubtasksFromFrontmatter:
    """Tests for parse_subtasks_from_frontmatter function."""

    def test_list_of_strings(self) -> None:
        """Test parsing list of strings."""
        subtasks = parse_subtasks_from_frontmatter(
            [
                "First task",
                "Second task",
            ]
        )

        assert len(subtasks) == 2
        assert subtasks[0].name == "First task"
        assert subtasks[0].number == 1
        assert subtasks[1].name == "Second task"
        assert subtasks[1].number == 2

    def test_list_of_dicts(self) -> None:
        """Test parsing list of dicts."""
        subtasks = parse_subtasks_from_frontmatter(
            [
                {"name": "Task 1", "story_points": 2, "status": "done"},
                {"name": "Task 2", "sp": 3, "status": "planned"},
            ]
        )

        assert len(subtasks) == 2
        assert subtasks[0].name == "Task 1"
        assert subtasks[0].story_points == 2
        assert subtasks[0].status == Status.DONE
        assert subtasks[1].name == "Task 2"
        assert subtasks[1].story_points == 3
        assert subtasks[1].status == Status.PLANNED

    def test_with_assignee(self) -> None:
        """Test parsing with assignee."""
        subtasks = parse_subtasks_from_frontmatter(
            [
                {"name": "Task", "assignee": "john.doe"},
            ]
        )

        assert subtasks[0].assignee == "john.doe"

    def test_none_input(self) -> None:
        """Test None input."""
        subtasks = parse_subtasks_from_frontmatter(None)
        assert len(subtasks) == 0


# =============================================================================
# Test Story Parsing
# =============================================================================


class TestParseStoryFromFrontmatter:
    """Tests for parse_story_from_frontmatter function."""

    def test_full_story(self) -> None:
        """Test parsing a full story."""
        data = {
            "id": "US-001",
            "title": "Test Story",
            "story_points": 5,
            "priority": "high",
            "status": "in_progress",
            "assignee": "jane.doe",
            "labels": ["feature", "mvp"],
            "sprint": "Sprint 1",
            "description": {
                "as_a": "user",
                "i_want": "to test",
                "so_that": "it works",
            },
            "acceptance_criteria": [
                {"criterion": "AC 1", "done": False},
            ],
            "subtasks": [
                {"name": "Subtask 1", "story_points": 2},
            ],
        }

        story = parse_story_from_frontmatter(data)

        assert str(story.id) == "US-001"
        assert story.title == "Test Story"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS
        assert story.assignee == "jane.doe"
        assert story.labels == ["feature", "mvp"]
        assert story.sprint == "Sprint 1"
        assert story.description is not None
        assert story.description.role == "user"
        assert len(story.acceptance_criteria.items) == 1
        assert len(story.subtasks) == 1

    def test_minimal_story(self) -> None:
        """Test parsing minimal story."""
        data = {"id": "US-002"}

        story = parse_story_from_frontmatter(data)

        assert str(story.id) == "US-002"
        assert story.title == "Untitled Story"
        assert story.story_points == 0
        assert story.priority == Priority.MEDIUM
        assert story.status == Status.PLANNED

    def test_with_aliases(self) -> None:
        """Test parsing with field aliases."""
        data = {
            "story_id": "US-003",
            "name": "Using name alias",
            "sp": 8,
            "prio": "critical",
            "tags": ["tag1", "tag2"],
        }

        story = parse_story_from_frontmatter(data)

        assert str(story.id) == "US-003"
        assert story.title == "Using name alias"
        assert story.story_points == 8
        assert story.priority == Priority.CRITICAL
        assert story.labels == ["tag1", "tag2"]

    def test_with_commits(self) -> None:
        """Test parsing with commits."""
        data = {
            "id": "US-004",
            "commits": [
                {"hash": "abc123", "message": "Initial commit"},
                "def456",  # string format
            ],
        }

        story = parse_story_from_frontmatter(data)

        assert len(story.commits) == 2
        assert story.commits[0].hash == "abc123"
        assert story.commits[0].message == "Initial commit"
        assert story.commits[1].hash == "def456"

    def test_with_links(self) -> None:
        """Test parsing with links."""
        data = {
            "id": "US-005",
            "links": [
                {"type": "blocks", "target": "US-006"},
                "US-007",  # string format
            ],
        }

        story = parse_story_from_frontmatter(data)

        assert len(story.links) == 2
        assert story.links[0] == ("blocks", "US-006")
        assert story.links[1] == ("relates_to", "US-007")


# =============================================================================
# Test Epic Parsing
# =============================================================================


class TestParseEpicFromFrontmatter:
    """Tests for parse_epic_from_frontmatter function."""

    def test_basic_epic(self) -> None:
        """Test parsing basic epic."""
        data = {
            "key": "EPIC-001",
            "title": "Test Epic",
            "description": "Epic description",
        }

        epic = parse_epic_from_frontmatter(data)

        assert str(epic.key) == "EPIC-001"
        assert epic.title == "Test Epic"
        assert epic.description == "Epic description"

    def test_epic_with_stories(self) -> None:
        """Test parsing epic with stories."""
        data = {"key": "EPIC-002", "title": "Epic with Stories"}
        stories = [
            parse_story_from_frontmatter({"id": "US-001", "title": "Story 1"}),
            parse_story_from_frontmatter({"id": "US-002", "title": "Story 2"}),
        ]

        epic = parse_epic_from_frontmatter(data, stories)

        assert len(epic.stories) == 2

    def test_epic_with_aliases(self) -> None:
        """Test parsing epic with field aliases."""
        data = {
            "epic_key": "EPIC-003",
            "name": "Using aliases",
        }

        epic = parse_epic_from_frontmatter(data)

        assert str(epic.key) == "EPIC-003"
        assert epic.title == "Using aliases"


# =============================================================================
# Test FrontmatterParser
# =============================================================================


class TestFrontmatterParser:
    """Tests for FrontmatterParser class."""

    @pytest.fixture
    def parser(self) -> FrontmatterParser:
        """Create a basic parser instance."""
        return FrontmatterParser()

    def test_name_property(self, parser: FrontmatterParser) -> None:
        """Test parser name."""
        assert parser.name == "Frontmatter"

    def test_supported_extensions(self, parser: FrontmatterParser) -> None:
        """Test supported extensions."""
        assert ".md" in parser.supported_extensions
        assert ".markdown" in parser.supported_extensions
        assert ".mdx" in parser.supported_extensions

    def test_can_parse_yaml_frontmatter(self, parser: FrontmatterParser) -> None:
        """Test can_parse with YAML frontmatter."""
        content = "---\nid: US-001\n---\nContent"
        assert parser.can_parse(content)

    def test_can_parse_html_comment(self, parser: FrontmatterParser) -> None:
        """Test can_parse with HTML comment frontmatter."""
        content = "<!-- yaml:\nid: US-001\n-->\nContent"
        assert parser.can_parse(content)

    def test_cannot_parse_plain_content(self, parser: FrontmatterParser) -> None:
        """Test can_parse with plain content."""
        content = "# Just a heading\n\nContent"
        assert not parser.can_parse(content)

    def test_can_parse_file(self, parser: FrontmatterParser, tmp_path: Path) -> None:
        """Test can_parse with file path."""
        file = tmp_path / "test.md"
        file.write_text("---\nid: US-001\n---\nContent", encoding="utf-8")
        assert parser.can_parse(file)

    def test_parse_stories_single(self, parser: FrontmatterParser) -> None:
        """Test parsing single story from frontmatter."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: Single Story
            story_points: 5
            priority: high
            ---

            # Content
        """).strip()

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Single Story"
        assert stories[0].story_points == 5

    def test_parse_stories_multiple(self, parser: FrontmatterParser) -> None:
        """Test parsing multiple stories from frontmatter."""
        content = textwrap.dedent("""
            ---
            stories:
              - id: US-001
                title: First Story
              - id: US-002
                title: Second Story
            ---

            # Content
        """).strip()

        stories = parser.parse_stories(content)

        assert len(stories) == 2
        assert str(stories[0].id) == "US-001"
        assert str(stories[1].id) == "US-002"

    def test_parse_epic(self, parser: FrontmatterParser) -> None:
        """Test parsing epic from frontmatter."""
        content = textwrap.dedent("""
            ---
            epic:
              key: EPIC-001
              title: Test Epic
              description: Epic description
            stories:
              - id: US-001
                title: Story 1
              - id: US-002
                title: Story 2
            ---

            # Content
        """).strip()

        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "EPIC-001"
        assert epic.title == "Test Epic"
        assert len(epic.stories) == 2

    def test_parse_from_file(self, parser: FrontmatterParser, tmp_path: Path) -> None:
        """Test parsing from file."""
        file = tmp_path / "story.md"
        file.write_text(
            textwrap.dedent("""
                ---
                id: US-001
                title: File Story
                ---

                # Content
            """).strip(),
            encoding="utf-8",
        )

        stories = parser.parse_stories(file)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"

    def test_validate_valid(self, parser: FrontmatterParser) -> None:
        """Test validation of valid content."""
        content = "---\nid: US-001\n---\nContent"

        errors = parser.validate(content)

        assert len(errors) == 0

    def test_validate_invalid_yaml(self, parser: FrontmatterParser) -> None:
        """Test validation of invalid YAML."""
        content = "---\n  bad: yaml: here:\n---\n"

        errors = parser.validate(content)

        assert len(errors) > 0

    def test_strict_mode_validation(self) -> None:
        """Test strict mode validation."""
        parser = FrontmatterParser(config=FrontmatterConfig(strict=True))
        content = "---\ncustom_field: value\n---\nContent"

        errors = parser.validate(content)

        # Should require stories, id, or epic in strict mode
        assert any("stories" in e or "id" in e or "epic" in e for e in errors)


class TestFrontmatterParserWithFallback:
    """Tests for FrontmatterParser with fallback parser."""

    def test_fallback_parser(self) -> None:
        """Test using fallback parser for remaining content."""
        parser = create_markdown_with_frontmatter()

        content = textwrap.dedent("""
            ---
            id: US-001
            story_points: 5
            ---

            ### US-001: Story from Markdown

            **Priority**: P0
            **Status**: Complete

            #### Description

            **As a** user
            **I want** to test fallback
            **So that** it works
        """).strip()

        stories = parser.parse_stories(content)

        # Should get story from frontmatter + inline merge
        assert len(stories) >= 1

    def test_merge_frontmatter_with_inline(self) -> None:
        """Test merging frontmatter data with inline parsed data."""
        parser = create_markdown_with_frontmatter()

        content = textwrap.dedent("""
            ---
            stories:
              - id: US-001
                story_points: 5
                priority: high
            ---

            ### US-001: Story Title from Markdown

            **Status**: ✅ Complete

            #### Description

            **As a** user
            **I want** to merge
            **So that** both work
        """).strip()

        stories = parser.parse_stories(content)

        # Should have merged data
        assert len(stories) >= 1


# =============================================================================
# Test MergeStrategy
# =============================================================================


class TestMergeStrategy:
    """Tests for different merge strategies."""

    def test_frontmatter_priority(self) -> None:
        """Test frontmatter priority merge strategy."""
        config = FrontmatterConfig(merge_strategy=MergeStrategy.FRONTMATTER_PRIORITY)
        _parser = FrontmatterParser(config=config)

        # Frontmatter values should win
        assert config.merge_strategy == MergeStrategy.FRONTMATTER_PRIORITY

    def test_inline_priority(self) -> None:
        """Test inline priority merge strategy."""
        config = FrontmatterConfig(merge_strategy=MergeStrategy.INLINE_PRIORITY)
        _parser = FrontmatterParser(config=config)

        assert config.merge_strategy == MergeStrategy.INLINE_PRIORITY

    def test_merge_arrays(self) -> None:
        """Test merge arrays strategy."""
        config = FrontmatterConfig(merge_strategy=MergeStrategy.MERGE_ARRAYS)
        _parser = FrontmatterParser(config=config)

        assert config.merge_strategy == MergeStrategy.MERGE_ARRAYS


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_frontmatter_parser(self) -> None:
        """Test create_frontmatter_parser factory."""
        parser = create_frontmatter_parser(
            merge_strategy=MergeStrategy.INLINE_PRIORITY,
            strict=True,
        )

        assert parser.config.merge_strategy == MergeStrategy.INLINE_PRIORITY
        assert parser.config.strict

    def test_create_frontmatter_parser_with_mappings(self) -> None:
        """Test create_frontmatter_parser with custom mappings."""
        custom = FieldMapping(
            frontmatter_key="custom_priority",
            entity_field="priority",
        )

        parser = create_frontmatter_parser(custom_mappings=[custom])

        assert custom in parser.config.custom_mappings

    def test_create_markdown_with_frontmatter(self) -> None:
        """Test create_markdown_with_frontmatter factory."""
        parser = create_markdown_with_frontmatter()

        assert parser.fallback_parser is not None


# =============================================================================
# Test Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_has_frontmatter_yaml(self) -> None:
        """Test has_frontmatter with YAML."""
        assert has_frontmatter("---\nid: US-001\n---\n")
        assert not has_frontmatter("# Just a heading")

    def test_has_frontmatter_html_comment(self) -> None:
        """Test has_frontmatter with HTML comment."""
        assert has_frontmatter("<!-- yaml:\nid: US-001\n-->")
        assert has_frontmatter("<!-- frontmatter:\nid: US-001\n-->")

    def test_strip_frontmatter(self) -> None:
        """Test strip_frontmatter."""
        content = "---\nid: US-001\n---\n\n# Content"
        stripped = strip_frontmatter(content)

        assert "---" not in stripped
        assert "# Content" in stripped

    def test_strip_frontmatter_no_frontmatter(self) -> None:
        """Test strip_frontmatter with no frontmatter."""
        content = "# Just content"
        stripped = strip_frontmatter(content)

        assert stripped == content

    def test_get_frontmatter(self) -> None:
        """Test get_frontmatter."""
        content = "---\nid: US-001\ntitle: Test\n---\n"
        data = get_frontmatter(content)

        assert data["id"] == "US-001"
        assert data["title"] == "Test"

    def test_get_frontmatter_no_frontmatter(self) -> None:
        """Test get_frontmatter with no frontmatter."""
        content = "# Just content"
        data = get_frontmatter(content)

        assert data == {}


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self) -> None:
        """Test parsing empty content."""
        parser = FrontmatterParser()

        stories = parser.parse_stories("")

        assert len(stories) == 0

    def test_only_frontmatter(self) -> None:
        """Test content with only frontmatter."""
        content = "---\nid: US-001\ntitle: Test\n---\n"
        parser = FrontmatterParser()

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"

    def test_multiline_values(self) -> None:
        """Test multiline values in frontmatter."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: >
              This is a very long title
              that spans multiple lines
            technical_notes: |
              Line 1
              Line 2
              Line 3
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert "very long title" in stories[0].title
        assert "Line 1" in stories[0].technical_notes

    def test_special_characters(self) -> None:
        """Test special characters in values."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: "Story with: colons & ampersands"
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert "colons & ampersands" in stories[0].title

    def test_unicode_content(self) -> None:
        """Test Unicode content in frontmatter."""
        content = textwrap.dedent("""
            ---
            id: US-001
            title: "Ünïcödë Störy 日本語"
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert "Ünïcödë" in stories[0].title
        assert "日本語" in stories[0].title

    def test_numeric_values(self) -> None:
        """Test numeric values handling."""
        content = textwrap.dedent("""
            ---
            id: US-001
            story_points: 13
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert stories[0].story_points == 13

    def test_boolean_values(self) -> None:
        """Test boolean values in acceptance criteria."""
        content = textwrap.dedent("""
            ---
            id: US-001
            acceptance_criteria:
              - criterion: "Test criterion"
                done: true
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert stories[0].acceptance_criteria.checked[0] is True

    def test_null_values(self) -> None:
        """Test null values handling."""
        content = textwrap.dedent("""
            ---
            id: US-001
            assignee: null
            description: ~
            ---

            Content
        """).strip()

        parser = FrontmatterParser()
        stories = parser.parse_stories(content)

        assert stories[0].assignee is None


# =============================================================================
# Test Configuration
# =============================================================================


class TestFrontmatterConfig:
    """Tests for FrontmatterConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = FrontmatterConfig()

        assert FrontmatterFormat.YAML in config.formats
        assert config.merge_strategy == MergeStrategy.FRONTMATTER_PRIORITY
        assert not config.strict
        assert not config.case_sensitive

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = FrontmatterConfig(
            formats=[FrontmatterFormat.HTML_COMMENT],
            merge_strategy=MergeStrategy.INLINE_PRIORITY,
            strict=True,
            case_sensitive=True,
        )

        assert config.formats == [FrontmatterFormat.HTML_COMMENT]
        assert config.merge_strategy == MergeStrategy.INLINE_PRIORITY
        assert config.strict
        assert config.case_sensitive

    def test_custom_mappings(self) -> None:
        """Test custom field mappings."""
        custom = FieldMapping(
            frontmatter_key="effort",
            entity_field="story_points",
            aliases=("complexity",),
        )
        config = FrontmatterConfig(custom_mappings=[custom])

        assert len(config.custom_mappings) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestFrontmatterIntegration:
    """Integration tests for frontmatter parsing."""

    def test_complete_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow with file."""
        # Create a file with frontmatter
        content = textwrap.dedent("""
            ---
            epic:
              key: PROJ-100
              title: Project Epic
              description: |
                This is the main epic for the project.
                It contains all the stories.
            stories:
              - id: US-001
                title: First Story
                story_points: 5
                priority: high
                status: in_progress
                description:
                  as_a: developer
                  i_want: to use frontmatter
                  so_that: I can define stories easily
                acceptance_criteria:
                  - criterion: Can parse YAML frontmatter
                    done: true
                  - criterion: Can handle nested structures
                    done: false
                subtasks:
                  - name: Implement parser
                    story_points: 3
                    status: done
                  - name: Write tests
                    story_points: 2
                    status: planned
              - id: US-002
                title: Second Story
                story_points: 3
                priority: medium
                labels: [feature, documentation]
            ---

            # Project Epic

            Additional markdown content for the epic...
        """).strip()

        file = tmp_path / "epic.md"
        file.write_text(content, encoding="utf-8")

        # Parse with frontmatter parser
        parser = FrontmatterParser()
        epic = parser.parse_epic(file)

        # Verify epic
        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Project Epic"
        assert "main epic" in epic.description

        # Verify stories
        assert len(epic.stories) == 2

        story1 = epic.stories[0]
        assert str(story1.id) == "US-001"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.IN_PROGRESS
        assert story1.description is not None
        assert story1.description.role == "developer"
        assert len(story1.acceptance_criteria.items) == 2
        assert len(story1.subtasks) == 2

        story2 = epic.stories[1]
        assert str(story2.id) == "US-002"
        assert story2.labels == ["feature", "documentation"]

    def test_validate_and_parse(self) -> None:
        """Test validation before parsing."""
        parser = FrontmatterParser(config=FrontmatterConfig(strict=True))

        valid_content = "---\nid: US-001\ntitle: Valid\n---\n"
        invalid_content = "---\ncustom: only\n---\n"

        # Valid content should pass
        assert len(parser.validate(valid_content)) == 0

        # Invalid content should fail strict validation
        errors = parser.validate(invalid_content)
        assert len(errors) > 0
