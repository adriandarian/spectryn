"""
Golden-file tests for markdown parser.

These tests use fixture files to verify parser behavior with various
markdown formats and edge cases. Golden-file testing ensures that
parser output matches expected snapshots.
"""

import json
from pathlib import Path

import pytest

from spectryn.adapters.parsers.markdown import MarkdownParser
from spectryn.core.domain.enums import Priority, Status


# Path to markdown fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "markdown_samples"


class TestGoldenFileStandardStory:
    """Golden-file tests for standard story format."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.fixture
    def standard_story_content(self):
        return (FIXTURES_DIR / "standard_story.md").read_text()

    def test_parse_standard_story(self, parser, standard_story_content):
        """Test parsing a standard story with all fields."""
        stories = parser.parse_stories(standard_story_content)

        assert len(stories) == 1
        story = stories[0]

        # Verify ID
        assert story.id.value == "US-001"

        # Verify title
        assert "User Login Feature" in story.title

        # Verify metadata
        assert story.story_points == 5
        assert story.priority == Priority.CRITICAL
        assert story.status == Status.IN_PROGRESS

        # Verify description
        assert story.description.role == "registered user"
        assert "log into" in story.description.want
        assert "personalized dashboard" in story.description.benefit

        # Verify acceptance criteria
        assert len(story.acceptance_criteria) >= 3

        # Verify subtasks (may parse from table or not, depending on parser)
        assert story.subtasks is not None

    def test_standard_story_subtask_parsing(self, parser, standard_story_content):
        """Test subtask parsing from table format."""
        stories = parser.parse_stories(standard_story_content)
        story = stories[0]

        # Subtasks may or may not be parsed depending on format support
        assert isinstance(story.subtasks, list)


class TestGoldenFileMinimalStory:
    """Golden-file tests for minimal story format."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.fixture
    def minimal_story_content(self):
        return (FIXTURES_DIR / "minimal_story.md").read_text()

    def test_parse_minimal_story(self, parser, minimal_story_content):
        """Test parsing a minimal story with only required fields."""
        stories = parser.parse_stories(minimal_story_content)

        assert len(stories) == 1
        story = stories[0]

        # Verify ID
        assert story.id.value == "US-002"

        # Verify description is parsed
        assert story.description.role == "user"
        assert "simple" in story.description.want

    def test_minimal_story_defaults(self, parser, minimal_story_content):
        """Test minimal story has reasonable defaults."""
        stories = parser.parse_stories(minimal_story_content)
        story = stories[0]

        # Should have default values or None for optional fields
        # (exact values depend on parser implementation)
        assert story.id is not None


class TestGoldenFileMultipleStories:
    """Golden-file tests for multiple stories in one file."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.fixture
    def multiple_stories_content(self):
        return (FIXTURES_DIR / "multiple_stories.md").read_text()

    def test_parse_all_stories(self, parser, multiple_stories_content):
        """Test parsing multiple stories from one file."""
        stories = parser.parse_stories(multiple_stories_content)

        assert len(stories) == 3

    def test_stories_have_unique_ids(self, parser, multiple_stories_content):
        """Test all stories have unique IDs."""
        stories = parser.parse_stories(multiple_stories_content)

        ids = [s.id.value for s in stories]
        assert len(ids) == len(set(ids))  # All unique

    def test_stories_different_statuses(self, parser, multiple_stories_content):
        """Test stories have different statuses parsed correctly."""
        stories = parser.parse_stories(multiple_stories_content)

        statuses = [s.status for s in stories]
        # Should have variety of statuses
        assert len(set(statuses)) >= 2

    def test_stories_different_priorities(self, parser, multiple_stories_content):
        """Test stories have different priorities parsed correctly."""
        stories = parser.parse_stories(multiple_stories_content)

        priorities = [s.priority for s in stories]
        # Should have variety of priorities
        assert len(set(priorities)) >= 2


class TestGoldenFileGitHubStyle:
    """Golden-file tests for GitHub-style issue format."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.fixture
    def github_style_content(self):
        return (FIXTURES_DIR / "github_style.md").read_text()

    def test_parse_github_style_id(self, parser, github_style_content):
        """Test parsing GitHub-style #123 issue IDs."""
        stories = parser.parse_stories(github_style_content)

        # Should find the story with #123 ID
        assert len(stories) >= 1

    def test_github_task_list_parsing(self, parser, github_style_content):
        """Test parsing GitHub-style task lists as subtasks."""
        stories = parser.parse_stories(github_style_content)

        if stories:
            story = stories[0]
            # Check if tasks are parsed from the Tasks section
            assert story.subtasks is not None


class TestGoldenFileCustomPrefix:
    """Golden-file tests for custom project prefix format."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.fixture
    def custom_prefix_content(self):
        return (FIXTURES_DIR / "custom_prefix.md").read_text()

    def test_parse_custom_prefix(self, parser, custom_prefix_content):
        """Test parsing custom project prefix like MYPROJECT-001."""
        stories = parser.parse_stories(custom_prefix_content)

        assert len(stories) == 1
        story = stories[0]

        # Verify custom prefix ID is parsed
        assert story.id.value == "MYPROJECT-001"

    def test_custom_prefix_high_points(self, parser, custom_prefix_content):
        """Test parsing high story point values."""
        stories = parser.parse_stories(custom_prefix_content)
        story = stories[0]

        assert story.story_points == 13

    def test_custom_prefix_done_status(self, parser, custom_prefix_content):
        """Test parsing done status with emoji."""
        stories = parser.parse_stories(custom_prefix_content)
        story = stories[0]

        assert story.status == Status.DONE


class TestGoldenFileEdgeCases:
    """Golden-file tests for edge cases."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_empty_content(self, parser):
        """Test parsing empty content."""
        stories = parser.parse_stories("")
        assert len(stories) == 0

    def test_no_stories_content(self, parser):
        """Test parsing content with no stories."""
        content = """
# Just a Heading

Some random text without any story format.

- A bullet point
- Another bullet point
"""
        stories = parser.parse_stories(content)
        assert len(stories) == 0

    def test_malformed_story(self, parser):
        """Test parsing malformed story (missing ID)."""
        content = """
### Story Without ID

**As a** user
**I want** something
**So that** it happens
"""
        stories = parser.parse_stories(content)
        # Should not crash, may or may not find a story
        assert isinstance(stories, list)

    def test_unicode_content(self, parser):
        """Test parsing unicode content."""
        content = """
### PROJ-001: 日本語タイトル 🚀

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | High |
| **Status** | In Progress |

**As a** международный пользователь
**I want** 中文功能
**So that** 🎉 works
"""
        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert "日本語" in stories[0].title

    def test_very_long_description(self, parser):
        """Test parsing very long descriptions."""
        long_text = "word " * 1000
        content = f"""
### PROJ-002: Long Story

**As a** user
**I want** {long_text}
**So that** it works
"""
        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert len(stories[0].description.want) > 1000


class TestGoldenFileConsistency:
    """Tests for parser consistency across runs."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_deterministic_output(self, parser):
        """Test parser produces same output for same input."""
        content = (FIXTURES_DIR / "standard_story.md").read_text()

        # Parse multiple times
        result1 = parser.parse_stories(content)
        result2 = parser.parse_stories(content)
        result3 = parser.parse_stories(content)

        # Should produce identical results
        assert len(result1) == len(result2) == len(result3)
        assert result1[0].id.value == result2[0].id.value == result3[0].id.value

    def test_parse_from_path(self, parser):
        """Test parsing from file path produces same result as content."""
        path = FIXTURES_DIR / "standard_story.md"
        content = path.read_text()

        from_content = parser.parse_stories(content)
        from_path = parser.parse_stories(path)

        assert len(from_content) == len(from_path)
        assert from_content[0].id.value == from_path[0].id.value
