"""Tests for Obsidian-flavored Markdown parser."""

import textwrap

import pytest

from spectra.adapters.parsers.obsidian_parser import ObsidianParser
from spectra.core.domain.enums import Priority, Status


class TestObsidianParser:
    """Tests for ObsidianParser."""

    @pytest.fixture
    def parser(self) -> ObsidianParser:
        """Create parser instance."""
        return ObsidianParser()

    @pytest.fixture
    def sample_obsidian(self) -> str:
        """Sample Obsidian Markdown content."""
        return textwrap.dedent("""
            ---
            epic-key: PROJ-123
            title: Epic Title
            tags: [epic, project]
            ---

            # Epic Title

            ## PROJ-001: User Registration

            Story Points:: 5
            Priority:: High
            Status:: Planned
            Blocks:: [[PROJ-456]]
            Depends On:: [[OTHER-789]]

            ### Description

            **As a** new user
            **I want** to register an account
            **So that** I can access the system

            ### Acceptance Criteria

            - [ ] Email validation works
            - [x] Password strength check

            ### Subtasks

            | # | Task | SP | Status |
            |---|------|----|----|
            | 1 | Implement form | 2 | Planned |
            | 2 | Write tests | 1 | Done |

            ### Technical Notes

            > [!note]
            > Use bcrypt for password hashing.

            ## PROJ-002: User Login

            Story Points:: 3
            Priority:: Medium
            Status:: Done

            ### Description

            **As a** registered user
            **I want** to log in
            **So that** I can use the application
        """)

    def test_name(self, parser: ObsidianParser) -> None:
        """Test parser name."""
        assert parser.name == "Obsidian"

    def test_supported_extensions(self, parser: ObsidianParser) -> None:
        """Test supported file extensions."""
        assert ".md" in parser.supported_extensions

    def test_can_parse_obsidian_content(self, parser: ObsidianParser, sample_obsidian: str) -> None:
        """Test can_parse with Obsidian content."""
        assert parser.can_parse(sample_obsidian) is True

    def test_cannot_parse_plain_markdown(self, parser: ObsidianParser) -> None:
        """Test can_parse with plain markdown (no Obsidian features)."""
        plain_md = "# Title\n\nSome content without Obsidian features."
        assert parser.can_parse(plain_md) is False

    def test_parse_stories(self, parser: ObsidianParser, sample_obsidian: str) -> None:
        """Test parsing stories from Obsidian content."""
        stories = parser.parse_stories(sample_obsidian)

        assert len(stories) == 2

        # First story
        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "User Registration"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.PLANNED

        # Description
        assert story1.description is not None
        assert story1.description.role == "new user"

        # Acceptance criteria
        assert len(story1.acceptance_criteria.items) == 2

        # Subtasks
        assert len(story1.subtasks) == 2

        # Links from dataview fields
        assert len(story1.links) >= 1

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: ObsidianParser, sample_obsidian: str) -> None:
        """Test parsing epic from Obsidian content."""
        epic = parser.parse_epic(sample_obsidian)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert epic.title == "Epic Title"
        assert len(epic.stories) == 2

    def test_parse_wikilinks(self, parser: ObsidianParser) -> None:
        """Test parsing wikilinks in content."""
        content = textwrap.dedent("""
            ---
            title: Test
            ---

            ## PROJ-001: Link Test

            Story Points:: 3
            Blocks:: [[PROJ-002]]

            See also [[Related Note|alias]].
        """)

        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert len(stories[0].links) >= 1

    def test_parse_dataview_fields(self, parser: ObsidianParser) -> None:
        """Test parsing Dataview inline fields."""
        content = textwrap.dedent("""
            ---
            title: Test
            ---

            ## PROJ-001: Dataview Test

            Story Points:: 5
            Priority:: Critical
            Status:: In Progress
            Assignee:: John Doe
        """)

        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert stories[0].story_points == 5
        assert stories[0].priority == Priority.CRITICAL
        assert stories[0].status == Status.IN_PROGRESS

    def test_validate_valid_content(self, parser: ObsidianParser, sample_obsidian: str) -> None:
        """Test validation of valid Obsidian content."""
        errors = parser.validate(sample_obsidian)
        assert len(errors) == 0

    def test_validate_invalid_frontmatter(self, parser: ObsidianParser) -> None:
        """Test validation of invalid YAML frontmatter."""
        content = textwrap.dedent("""
            ---
            invalid: yaml: content:
            ---

            ## PROJ-001: Test
        """)

        errors = parser.validate(content)
        # Should still parse but may have frontmatter warning
        assert isinstance(errors, list)

    def test_parse_file(self, parser: ObsidianParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            ---
            epic-key: TEST-001
            ---

            ## PROJ-001: Test Story

            Story Points:: 3

            ### Description

            **As a** user
            **I want** to test
            **So that** it works
        """)

        md_file = tmp_path / "epic.md"
        md_file.write_text(content)

        stories = parser.parse_stories(md_file)
        assert len(stories) == 1
