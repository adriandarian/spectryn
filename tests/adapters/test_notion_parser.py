"""
Tests for Notion Parser.
"""

from textwrap import dedent

import pytest

from spectryn.adapters.parsers.notion_parser import NotionParser
from spectryn.adapters.parsers.notion_plugin import NotionParserPlugin, create_plugin
from spectryn.core.domain.enums import Priority, Status


# =============================================================================
# NotionParser Tests
# =============================================================================


class TestNotionParser:
    """Tests for NotionParser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return NotionParser()

    # -------------------------------------------------------------------------
    # Basic Properties
    # -------------------------------------------------------------------------

    def test_name(self, parser):
        """Should return 'Notion' as parser name."""
        assert parser.name == "Notion"

    def test_supported_extensions(self, parser):
        """Should support .md, .markdown, and .csv."""
        extensions = parser.supported_extensions
        assert ".md" in extensions
        assert ".csv" in extensions

    # -------------------------------------------------------------------------
    # can_parse Tests
    # -------------------------------------------------------------------------

    def test_can_parse_with_properties(self, parser):
        """Should detect Notion content with properties block."""
        content = dedent(
            """
            Status: In Progress
            Priority: High
            Story Points: 5

            # Story Title

            Description here.
        """
        )

        assert parser.can_parse(content) is True

    def test_can_parse_with_callout(self, parser):
        """Should detect Notion content with emoji callout."""
        content = dedent(
            """
            # Story Title

            > 👤 As a user, I want to do something so that I get benefit
        """
        )

        assert parser.can_parse(content) is True

    def test_can_parse_with_toggle(self, parser):
        """Should detect Notion content with toggle blocks."""
        content = dedent(
            """
            # Story Title

            <details>
            <summary>Toggle content</summary>
            Hidden content here.
            </details>
        """
        )

        assert parser.can_parse(content) is True

    def test_cannot_parse_plain_text(self, parser):
        """Should reject plain text without Notion patterns."""
        content = "Just some plain text without any structure."

        assert parser.can_parse(content) is False

    # -------------------------------------------------------------------------
    # parse_stories Tests - Basic
    # -------------------------------------------------------------------------

    def test_parse_simple_story(self, parser):
        """Should parse a basic Notion story page."""
        content = dedent(
            """
            Status: Planned
            Priority: Medium
            Story Points: 3

            # US-001: User Login

            ## Description

            As a user, I want to log in so that I can access my account.
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert "US-001" in str(stories[0].id)
        assert "User Login" in stories[0].title
        assert stories[0].story_points == 3
        assert stories[0].priority == Priority.MEDIUM
        assert stories[0].status == Status.PLANNED

    def test_parse_story_with_callout_description(self, parser):
        """Should parse description from emoji callout."""
        content = dedent(
            """
            # Feature Implementation

            > 👤 As a developer, I want automated tests so that I can catch bugs early
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        desc = stories[0].description
        assert desc is not None
        assert desc.role == "developer"
        assert "automated tests" in desc.want
        assert "catch bugs" in desc.benefit

    def test_parse_story_with_acceptance_criteria(self, parser):
        """Should parse acceptance criteria checkboxes."""
        content = dedent(
            """
            Status: In Progress
            Priority: High

            # Story Title

            ## Acceptance Criteria

            - [ ] First criterion not done
            - [x] Second criterion completed
            - [ ] Third criterion pending
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        ac = stories[0].acceptance_criteria
        assert len(ac.items) == 3
        assert ac.checked[0] is False
        assert ac.checked[1] is True
        assert ac.checked[2] is False

    def test_parse_story_with_subtasks_table(self, parser):
        """Should parse subtasks from markdown table."""
        content = dedent(
            """
            Status: Planned

            # Story Title

            ## Subtasks

            | Task | Description | Points | Status |
            |------|-------------|--------|--------|
            | Create UI | Build the form | 2 | Done |
            | Add validation | Validate inputs | 3 | In Progress |
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        subtasks = stories[0].subtasks
        assert len(subtasks) == 2
        assert subtasks[0].name == "Create UI"
        assert subtasks[0].story_points == 2
        assert subtasks[0].status == Status.DONE
        assert subtasks[1].name == "Add validation"
        assert subtasks[1].status == Status.IN_PROGRESS

    def test_parse_story_with_technical_notes(self, parser):
        """Should parse technical notes section."""
        content = dedent(
            """
            Status: Planned

            # Story Title

            ## Technical Notes

            Use React for the frontend.
            Consider caching for performance.
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert "React" in stories[0].technical_notes
        assert "caching" in stories[0].technical_notes

    # -------------------------------------------------------------------------
    # parse_stories Tests - Multiple Stories
    # -------------------------------------------------------------------------

    def test_parse_multiple_stories_h1(self, parser):
        """Should parse multiple stories separated by H1."""
        content = dedent(
            """
            # US-001: First Story

            Status: Done

            Description of first story.

            # US-002: Second Story

            Status: Planned

            Description of second story.
        """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 2
        assert "First Story" in stories[0].title
        assert "Second Story" in stories[1].title

    def test_parse_multiple_stories_h2(self, parser):
        """Should parse multiple stories with H2 headings."""
        content = dedent(
            """
            Status: Planned
            Priority: High

            # Epic Title

            ## US-001: First Story

            First description.

            ## US-002: Second Story

            Second description.
        """
        )

        stories = parser.parse_stories(content)

        # Should find at least the individual stories
        assert len(stories) >= 1

    # -------------------------------------------------------------------------
    # parse_epic Tests
    # -------------------------------------------------------------------------

    def test_parse_epic_from_content(self, parser):
        """Should parse epic with stories."""
        content = dedent(
            """
            # Epic: User Authentication

            ## US-001: Login

            Status: Done

            > 👤 As a user, I want to log in so that I can access my account

            ## US-002: Logout

            Status: Planned

            > 👤 As a user, I want to log out so that my session is secure
        """
        )

        epic = parser.parse_epic(content)

        assert epic is not None
        assert "Authentication" in epic.title or "Epic" in epic.title
        assert len(epic.stories) >= 1

    def test_parse_epic_empty_returns_none(self, parser):
        """Should return None for content with no stories."""
        content = "Just some random text without structure."

        epic = parser.parse_epic(content)

        assert epic is None

    # -------------------------------------------------------------------------
    # validate Tests
    # -------------------------------------------------------------------------

    def test_validate_valid_content(self, parser):
        """Should return no errors for valid Notion content."""
        content = dedent(
            """
            Status: Planned
            Priority: High

            # Story Title

            > 👤 As a user, I want something so that I benefit
        """
        )

        errors = parser.validate(content)

        assert len(errors) == 0

    def test_validate_non_notion_content(self, parser):
        """Should report error for non-Notion content."""
        content = "Plain text without Notion patterns."

        errors = parser.validate(content)

        assert len(errors) > 0
        assert any("notion" in e.lower() for e in errors)

    # -------------------------------------------------------------------------
    # Property Extraction Tests
    # -------------------------------------------------------------------------

    def test_extract_properties_block(self, parser):
        """Should extract properties from top of content."""
        content = dedent(
            """
            Status: In Progress
            Priority: High
            Story Points: 5
            Assignee: @john.doe

            # Story Title
        """
        )

        properties = parser._extract_properties(content)

        assert properties["status"] == "In Progress"
        assert properties["priority"] == "High"
        assert properties["story points"] == "5"
        assert properties["assignee"] == "john.doe"

    def test_extract_properties_with_brackets(self, parser):
        """Should handle Notion-style link formatting."""
        content = dedent(
            """
            Related: [Project Link]
            Owner: @user

            # Title
        """
        )

        properties = parser._extract_properties(content)

        assert properties["related"] == "Project Link"

    # -------------------------------------------------------------------------
    # Table Parsing Tests
    # -------------------------------------------------------------------------

    def test_parse_markdown_table(self, parser):
        """Should parse markdown table correctly."""
        table_content = dedent(
            """
            | Name | Status | Points |
            |------|--------|--------|
            | Task 1 | Done | 2 |
            | Task 2 | Pending | 3 |
        """
        )

        rows = parser._parse_markdown_table(table_content)

        assert len(rows) == 2
        assert rows[0]["name"] == "Task 1"
        assert rows[0]["status"] == "Done"
        assert rows[1]["points"] == "3"

    def test_parse_table_with_empty_cells(self, parser):
        """Should handle tables with empty cells."""
        table_content = dedent(
            """
            | Task | Description | Status |
            |------|-------------|--------|
            | Task 1 | | Done |
            | Task 2 | Some desc | |
        """
        )

        rows = parser._parse_markdown_table(table_content)

        assert len(rows) == 2
        assert rows[0]["description"] == ""
        assert rows[1]["status"] == ""

    # -------------------------------------------------------------------------
    # File Handling Tests
    # -------------------------------------------------------------------------

    def test_parse_from_file(self, parser, tmp_path):
        """Should parse from actual file."""
        md_file = tmp_path / "story.md"
        md_file.write_text(
            dedent(
                """
            Status: Planned
            Priority: High

            # US-001: From File

            > 👤 As a user, I want file parsing so that I can import Notion exports
        """
            ),
            encoding="utf-8",
        )

        stories = parser.parse_stories(md_file)

        assert len(stories) == 1
        assert "From File" in stories[0].title

    def test_parse_csv_database(self, parser, tmp_path):
        """Should parse Notion database CSV export."""
        csv_file = tmp_path / "database.csv"
        csv_file.write_text(
            dedent(
                """
            Name,Status,Priority,Story Points
            "First Task",Done,High,3
            "Second Task",Planned,Medium,5
        """
            ).strip()
        )

        stories = parser.parse_stories(csv_file)

        assert len(stories) == 2
        assert stories[0].title == "First Task"
        assert stories[0].status == Status.DONE
        assert stories[1].story_points == 5

    def test_parse_folder_structure(self, parser, tmp_path):
        """Should parse Notion folder export."""
        # Create folder structure
        folder = tmp_path / "notion_export_abc123"
        folder.mkdir()

        (folder / "Story 1.md").write_text(
            dedent(
                """
            Status: Done
            Priority: High

            # US-001: Story One

            First story content.
        """
            )
        )

        (folder / "Story 2.md").write_text(
            dedent(
                """
            Status: Planned

            # US-002: Story Two

            Second story content.
        """
            )
        )

        stories = parser.parse_stories(folder)

        assert len(stories) == 2


# =============================================================================
# NotionParserPlugin Tests
# =============================================================================


class TestNotionParserPlugin:
    """Tests for NotionParserPlugin."""

    def test_metadata(self):
        """Should have correct metadata."""
        plugin = NotionParserPlugin()

        assert plugin.metadata.name == "notion-parser"
        assert plugin.metadata.version == "1.0.0"
        assert "Notion" in plugin.metadata.description

    def test_initialize_creates_parser(self):
        """Should create parser on initialize."""
        plugin = NotionParserPlugin()

        plugin.initialize()

        assert plugin.is_initialized
        assert plugin._parser is not None

    def test_get_parser_before_initialize(self):
        """Should raise error if not initialized."""
        plugin = NotionParserPlugin()

        with pytest.raises(RuntimeError):
            plugin.get_parser()

    def test_get_parser_after_initialize(self):
        """Should return parser after initialization."""
        plugin = NotionParserPlugin()
        plugin.initialize()

        parser = plugin.get_parser()

        assert parser is not None
        assert parser.name == "Notion"

    def test_shutdown_clears_parser(self):
        """Should clear parser on shutdown."""
        plugin = NotionParserPlugin()
        plugin.initialize()
        plugin.shutdown()

        assert not plugin.is_initialized
        assert plugin._parser is None

    def test_create_plugin_factory(self):
        """Should create plugin via factory function."""
        plugin = create_plugin()

        assert isinstance(plugin, NotionParserPlugin)


# =============================================================================
# Integration Tests
# =============================================================================


class TestNotionParserIntegration:
    """Integration tests for Notion parser."""

    def test_full_notion_page_export(self):
        """Should parse a complete Notion page export."""
        content = dedent(
            """
            Status: In Progress
            Priority: High
            Story Points: 8
            Assignee: @developer
            Sprint: Sprint 5

            # US-042: Complete Authentication Flow

            ## Description

            > 👤 As a registered user, I want to securely authenticate so that my data is protected

            ## Acceptance Criteria

            - [x] User can log in with email/password
            - [x] Password is validated for strength
            - [ ] 2FA is supported
            - [ ] Session timeout after inactivity

            ## Subtasks

            | Task | Description | Points | Status |
            |------|-------------|--------|--------|
            | Login Form | Create responsive login UI | 2 | Done |
            | Password Validation | Implement strength checker | 2 | Done |
            | 2FA Setup | Add TOTP support | 3 | In Progress |
            | Session Management | Handle timeouts | 1 | Planned |

            ## Technical Notes

            Using bcrypt for password hashing.
            TOTP implementation with speakeasy library.
            Redis for session storage.
        """
        )

        parser = NotionParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]

        # Verify basic fields
        assert "US-042" in str(story.id) or "042" in str(story.id)
        assert "Authentication" in story.title
        assert story.story_points == 8
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS

        # Verify description
        assert story.description is not None
        assert "registered user" in story.description.role

        # Verify acceptance criteria
        assert len(story.acceptance_criteria.items) == 4
        assert story.acceptance_criteria.checked[0] is True
        assert story.acceptance_criteria.checked[2] is False

        # Verify subtasks
        assert len(story.subtasks) == 4
        assert story.subtasks[0].name == "Login Form"
        assert story.subtasks[2].status == Status.IN_PROGRESS

        # Verify technical notes
        assert "bcrypt" in story.technical_notes
        assert "Redis" in story.technical_notes

    def test_parse_minimal_notion_export(self):
        """Should handle minimal Notion exports."""
        content = dedent(
            """
            Status: Planned

            # Simple Task
        """
        )

        parser = NotionParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert stories[0].title == "Simple Task"
        assert stories[0].status == Status.PLANNED

    def test_parse_notion_database_export(self, tmp_path):
        """Should parse a Notion database CSV export."""
        csv_content = dedent(
            """
            Name,Description,Status,Priority,Story Points,Assignee
            "User Authentication","Implement login flow",In Progress,High,5,john@example.com
            "Dashboard Design","Create main dashboard",Planned,Medium,8,jane@example.com
            "API Integration","Connect to backend",Done,High,3,john@example.com
        """
        ).strip()

        csv_file = tmp_path / "tasks.csv"
        csv_file.write_text(csv_content)

        parser = NotionParser()
        stories = parser.parse_stories(csv_file)

        assert len(stories) == 3

        # Check first story
        assert stories[0].title == "User Authentication"
        assert stories[0].status == Status.IN_PROGRESS
        assert stories[0].priority == Priority.HIGH
        assert stories[0].story_points == 5

        # Check last story
        assert stories[2].title == "API Integration"
        assert stories[2].status == Status.DONE
