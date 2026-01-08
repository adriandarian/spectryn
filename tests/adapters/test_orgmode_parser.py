"""Tests for Org-mode parser."""

import textwrap

import pytest

from spectryn.adapters.parsers.orgmode_parser import OrgModeParser
from spectryn.core.domain.enums import Priority, Status


class TestOrgModeParser:
    """Tests for OrgModeParser."""

    @pytest.fixture
    def parser(self) -> OrgModeParser:
        """Create parser instance."""
        return OrgModeParser()

    @pytest.fixture
    def sample_org(self) -> str:
        """Sample Org-mode content with stories."""
        return textwrap.dedent("""
            #+TITLE: Epic Title
            #+EPIC_KEY: PROJ-123

            * PROJ-001: User Registration
            :PROPERTIES:
            :STORY_POINTS: 5
            :PRIORITY: High
            :STATUS: Planned
            :END:

            ** Description
            *As a* new user
            *I want* to register an account
            *So that* I can access the system

            ** Acceptance Criteria
            - [ ] Email validation works
            - [X] Password strength check

            ** Subtasks
            | # | Task | SP | Status |
            |---+------+----+--------|
            | 1 | Implement form | 2 | Planned |
            | 2 | Write tests | 1 | Done |

            ** Technical Notes
            Use bcrypt for password hashing.

            ** Links
            - blocks :: PROJ-456
            - depends on :: OTHER-789

            * PROJ-002: User Login
            :PROPERTIES:
            :STORY_POINTS: 3
            :PRIORITY: Medium
            :STATUS: Done
            :END:

            ** Description
            *As a* registered user
            *I want* to log in
            *So that* I can use the application
        """)

    def test_name(self, parser: OrgModeParser) -> None:
        """Test parser name."""
        assert parser.name == "Org-mode"

    def test_supported_extensions(self, parser: OrgModeParser) -> None:
        """Test supported file extensions."""
        assert ".org" in parser.supported_extensions

    def test_can_parse_org_content(self, parser: OrgModeParser, sample_org: str) -> None:
        """Test can_parse with Org content."""
        assert parser.can_parse(sample_org) is True

    def test_cannot_parse_plain_text(self, parser: OrgModeParser) -> None:
        """Test can_parse with plain text."""
        assert parser.can_parse("Just plain text") is False

    def test_parse_stories(self, parser: OrgModeParser, sample_org: str) -> None:
        """Test parsing stories from Org content."""
        stories = parser.parse_stories(sample_org)

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
        assert "register" in story1.description.want

        # Acceptance criteria
        assert len(story1.acceptance_criteria.items) == 2

        # Subtasks
        assert len(story1.subtasks) == 2
        assert story1.subtasks[0].name == "Implement form"

        # Links
        assert len(story1.links) == 2

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: OrgModeParser, sample_org: str) -> None:
        """Test parsing epic from Org content."""
        epic = parser.parse_epic(sample_org)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert epic.title == "Epic Title"
        assert len(epic.stories) == 2

    def test_validate_valid_content(self, parser: OrgModeParser, sample_org: str) -> None:
        """Test validation of valid Org content."""
        errors = parser.validate(sample_org)
        assert len(errors) == 0

    def test_validate_invalid_content(self, parser: OrgModeParser) -> None:
        """Test validation of invalid Org content."""
        errors = parser.validate("No stories here")
        assert len(errors) > 0

    def test_parse_with_todo_keywords(self, parser: OrgModeParser) -> None:
        """Test parsing stories with TODO keywords."""
        content = textwrap.dedent("""
            #+TITLE: Test Epic

            * TODO PROJ-001: Pending Task
            :PROPERTIES:
            :STORY_POINTS: 2
            :END:

            * DONE PROJ-002: Completed Task
            :PROPERTIES:
            :STORY_POINTS: 1
            :END:
        """)

        stories = parser.parse_stories(content)
        assert len(stories) == 2

    def test_parse_file(self, parser: OrgModeParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            #+TITLE: Test

            * PROJ-001: Test Story
            :PROPERTIES:
            :STORY_POINTS: 3
            :END:

            ** Description
            As a user I want to test so that it works
        """)

        org_file = tmp_path / "epic.org"
        org_file.write_text(content)

        stories = parser.parse_stories(org_file)
        assert len(stories) == 1
