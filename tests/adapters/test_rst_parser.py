"""Tests for ReStructuredText parser."""

import textwrap

import pytest

from spectra.adapters.parsers.rst_parser import RstParser
from spectra.core.domain.enums import Priority, Status


class TestRstParser:
    """Tests for RstParser."""

    @pytest.fixture
    def parser(self) -> RstParser:
        """Create parser instance."""
        return RstParser()

    @pytest.fixture
    def sample_rst(self) -> str:
        """Sample RST content with stories."""
        return textwrap.dedent("""
            ==========
            Epic Title
            ==========

            :epic-key: PROJ-123

            PROJ-001: User Registration
            ---------------------------

            :story-points: 5
            :priority: High
            :status: Planned

            Description
            ^^^^^^^^^^^

            **As a** new user
            **I want** to register an account
            **So that** I can access the system

            Acceptance Criteria
            ^^^^^^^^^^^^^^^^^^^

            - [ ] Email validation works
            - [x] Password strength check

            Subtasks
            ^^^^^^^^

            * - 1
              - Implement form
              - 2
              - Planned
            * - 2
              - Write tests
              - 1
              - Done

            Technical Notes
            ^^^^^^^^^^^^^^^

            Use bcrypt for password hashing.

            PROJ-002: User Login
            --------------------

            :story-points: 3
            :priority: Medium
            :status: Done

            Description
            ^^^^^^^^^^^

            **As a** registered user
            **I want** to log in
            **So that** I can use the application
        """)

    def test_name(self, parser: RstParser) -> None:
        """Test parser name."""
        assert parser.name == "ReStructuredText"

    def test_supported_extensions(self, parser: RstParser) -> None:
        """Test supported file extensions."""
        assert ".rst" in parser.supported_extensions
        assert ".rest" in parser.supported_extensions

    def test_can_parse_rst_content(self, parser: RstParser, sample_rst: str) -> None:
        """Test can_parse with RST content."""
        assert parser.can_parse(sample_rst) is True

    def test_cannot_parse_plain_text(self, parser: RstParser) -> None:
        """Test can_parse with plain text."""
        assert parser.can_parse("Just plain text") is False

    def test_parse_stories(self, parser: RstParser, sample_rst: str) -> None:
        """Test parsing stories from RST content."""
        stories = parser.parse_stories(sample_rst)

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

        # Technical notes
        assert "bcrypt" in story1.technical_notes

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.story_points == 3
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: RstParser, sample_rst: str) -> None:
        """Test parsing epic from RST content."""
        epic = parser.parse_epic(sample_rst)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert "Epic Title" in epic.title
        assert len(epic.stories) == 2

    def test_validate_valid_content(self, parser: RstParser, sample_rst: str) -> None:
        """Test validation of valid RST content."""
        errors = parser.validate(sample_rst)
        assert len(errors) == 0

    def test_validate_invalid_content(self, parser: RstParser) -> None:
        """Test validation of invalid RST content."""
        errors = parser.validate("No stories here")
        assert len(errors) > 0
        assert any("No user stories" in e for e in errors)

    def test_parse_file(self, parser: RstParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            PROJ-001: Test Story
            --------------------

            :story-points: 3
            :priority: Medium
            :status: Planned

            Description
            ^^^^^^^^^^^

            As a user I want to test so that it works
        """)

        rst_file = tmp_path / "epic.rst"
        rst_file.write_text(content)

        stories = parser.parse_stories(rst_file)
        assert len(stories) == 1
        assert str(stories[0].id) == "PROJ-001"
