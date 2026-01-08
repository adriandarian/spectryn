"""
Tests for inline subtask parsing (checkboxes as subtasks).

Tests cover:
1. Basic checkbox parsing as subtasks
2. Checked/unchecked status mapping
3. Story points extraction from checkbox text
4. Description extraction with separators
5. Markdown formatting cleanup (bold, italic, code)
6. Integration with MarkdownParser
7. Mixed formats (table + checkbox fallback)
8. Edge cases and warnings
"""

from textwrap import dedent

import pytest

from spectryn.adapters.parsers import MarkdownParser
from spectryn.adapters.parsers.tolerant_markdown import (
    InlineSubtaskInfo,
    parse_inline_subtasks,
)
from spectryn.core.domain import Status


# =============================================================================
# parse_inline_subtasks Unit Tests
# =============================================================================


class TestParseInlineSubtasks:
    """Tests for the parse_inline_subtasks function."""

    def test_basic_unchecked_checkbox(self):
        """Test parsing a basic unchecked checkbox."""
        content = "- [ ] Implement feature"
        subtasks, warnings = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Implement feature"
        assert subtasks[0].checked is False
        assert subtasks[0].story_points == 1
        assert len(warnings) == 0

    def test_basic_checked_checkbox(self):
        """Test parsing a checked checkbox."""
        content = "- [x] Complete task"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Complete task"
        assert subtasks[0].checked is True

    def test_uppercase_x_checked(self):
        """Test parsing checkbox with uppercase X."""
        content = "- [X] Done task"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].checked is True

    def test_multiple_checkboxes(self):
        """Test parsing multiple checkboxes."""
        content = dedent(
            """
            - [ ] First task
            - [x] Second task
            - [ ] Third task
            """
        )
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 3
        assert subtasks[0].name == "First task"
        assert subtasks[0].checked is False
        assert subtasks[1].name == "Second task"
        assert subtasks[1].checked is True
        assert subtasks[2].name == "Third task"
        assert subtasks[2].checked is False

    def test_story_points_extraction(self):
        """Test extracting story points from checkbox text."""
        variations = [
            ("- [ ] Task (2 SP)", 2),
            ("- [ ] Task (3 sp)", 3),
            ("- [ ] Task (5 points)", 5),
            ("- [ ] Task (1 pt)", 1),
            ("- [ ] Task (8 story points)", 8),
        ]

        for content, expected_sp in variations:
            subtasks, _ = parse_inline_subtasks(content)
            assert len(subtasks) == 1, f"Failed for: {content}"
            assert subtasks[0].story_points == expected_sp, f"Failed for: {content}"
            assert "SP" not in subtasks[0].name, f"SP should be removed from name: {content}"

    def test_description_extraction_with_dash(self):
        """Test extracting description using dash separator."""
        content = "- [ ] Task name - This is the description"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Task name"
        assert subtasks[0].description == "This is the description"

    def test_description_extraction_with_colon(self):
        """Test extracting description using colon separator."""
        content = "- [ ] Task name: Description here"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Task name"
        assert subtasks[0].description == "Description here"

    def test_bold_formatting_removed(self):
        """Test that bold formatting is removed from task name."""
        content = "- [ ] **Bold task name**"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Bold task name"
        assert "**" not in subtasks[0].name

    def test_italic_formatting_removed(self):
        """Test that italic formatting is removed from task name."""
        content = "- [ ] *Italic task*"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Italic task"

    def test_code_formatting_removed(self):
        """Test that code formatting is removed from task name."""
        content = "- [ ] `Code task`"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Code task"

    def test_strikethrough_formatting_removed(self):
        """Test that strikethrough formatting is removed from task name."""
        content = "- [ ] ~~Strikethrough task~~"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Strikethrough task"

    def test_asterisk_checkbox_format(self):
        """Test parsing checkbox with asterisk list marker."""
        content = "* [ ] Asterisk task"
        subtasks, warnings = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Asterisk task"
        # Should have a warning about non-standard format
        assert any("NONSTANDARD_SUBTASK_CHECKBOX" in str(w.code) for w in warnings)

    def test_plus_checkbox_format(self):
        """Test parsing checkbox with plus list marker."""
        content = "+ [ ] Plus task"
        subtasks, warnings = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Plus task"
        # Should have a warning about non-standard format
        assert any("NONSTANDARD_SUBTASK_CHECKBOX" in str(w.code) for w in warnings)

    def test_indented_checkbox(self):
        """Test parsing indented checkboxes."""
        content = "  - [ ] Indented task"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Indented task"

    def test_short_name_warning(self):
        """Test that very short names generate warnings."""
        content = "- [ ] X"
        subtasks, warnings = parse_inline_subtasks(content)

        assert len(subtasks) == 0  # Should be skipped
        assert any("SHORT_SUBTASK_NAME" in str(w.code) for w in warnings)

    def test_line_number_tracking(self):
        """Test that line numbers are correctly tracked."""
        content = dedent(
            """
            Some text before

            - [ ] First task
            - [ ] Second task
            """
        )
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 2
        # Line numbers should be tracked (approximate check)
        assert subtasks[0].line_number > 0
        assert subtasks[1].line_number > subtasks[0].line_number

    def test_complex_task_with_all_features(self):
        """Test parsing a complex task with SP, description, and formatting."""
        content = "- [x] **Implement API** - Create REST endpoints (5 SP)"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Implement API"
        assert subtasks[0].description == "Create REST endpoints"
        assert subtasks[0].story_points == 5
        assert subtasks[0].checked is True


# =============================================================================
# MarkdownParser Integration Tests
# =============================================================================


class TestMarkdownParserInlineSubtasks:
    """Tests for inline subtask parsing in MarkdownParser."""

    @pytest.fixture
    def parser(self):
        """Create a MarkdownParser instance."""
        return MarkdownParser()

    def test_inline_subtasks_basic(self, parser):
        """Test parsing inline checkbox subtasks."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Story with Inline Subtasks

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |
            | **Priority** | High |
            | **Status** | In Progress |

            #### Description

            **As a** developer
            **I want** inline subtasks
            **So that** I can use checkboxes

            #### Subtasks

            - [ ] First subtask
            - [x] Second subtask (completed)
            - [ ] Third subtask (3 SP)
            """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        subtasks = stories[0].subtasks
        assert len(subtasks) == 3

        # Check first subtask
        assert subtasks[0].name == "First subtask"
        assert subtasks[0].status == Status.PLANNED
        assert subtasks[0].number == 1

        # Check second subtask (completed)
        assert subtasks[1].name == "Second subtask (completed)"
        assert subtasks[1].status == Status.DONE
        assert subtasks[1].number == 2

        # Check third subtask with story points
        assert subtasks[2].name == "Third subtask"
        assert subtasks[2].story_points == 3
        assert subtasks[2].number == 3

    def test_table_subtasks_preferred_over_inline(self, parser):
        """Test that table subtasks are preferred when present."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Story with Both Formats

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |

            #### Description

            **As a** developer
            **I want** to test
            **So that** it works

            #### Subtasks

            | # | Subtask | Description | SP | Status |
            |---|---------|-------------|----|--------|
            | 1 | Table task | From table | 2 | Done |

            - [ ] This should be ignored (inline after table)
            """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        subtasks = stories[0].subtasks
        # Should only have the table subtask
        assert len(subtasks) == 1
        assert subtasks[0].name == "Table task"

    def test_inline_subtasks_fallback(self, parser):
        """Test that inline subtasks work when no table is present."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Story with Only Inline

            | Field | Value |
            |-------|-------|
            | **Story Points** | 3 |

            #### Description

            **As a** user
            **I want** inline subtasks
            **So that** I can use simple lists

            #### Subtasks

            - [ ] Setup environment
            - [x] Write code
            - [ ] Add tests - Unit and integration tests (2 SP)
            """
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        subtasks = stories[0].subtasks
        assert len(subtasks) == 3

        # Check descriptions and story points
        assert subtasks[2].description == "Unit and integration tests"
        assert subtasks[2].story_points == 2

    def test_inline_subtasks_with_formatting(self, parser):
        """Test inline subtasks with markdown formatting."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Formatted Subtasks

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |

            #### Description

            **As a** developer
            **I want** to test
            **So that** it works

            #### Subtasks

            - [ ] **Bold task name**
            - [x] `Code formatted task`
            - [ ] *Italic task*
            """
        )

        stories = parser.parse_stories(content)
        subtasks = stories[0].subtasks

        assert len(subtasks) == 3
        assert subtasks[0].name == "Bold task name"
        assert subtasks[1].name == "Code formatted task"
        assert subtasks[2].name == "Italic task"

    def test_inline_subtasks_status_mapping(self, parser):
        """Test that checkbox status maps correctly to Status enum."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Status Mapping Test

            | Field | Value |
            |-------|-------|
            | **Story Points** | 2 |

            #### Description

            **As a** user
            **I want** to test
            **So that** it works

            #### Subtasks

            - [ ] Unchecked = Planned
            - [x] Checked = Done
            - [X] Uppercase X = Done
            """
        )

        stories = parser.parse_stories(content)
        subtasks = stories[0].subtasks

        assert subtasks[0].status == Status.PLANNED
        assert subtasks[1].status == Status.DONE
        assert subtasks[2].status == Status.DONE

    def test_no_subtasks_section(self, parser):
        """Test parsing when no Subtasks section exists."""
        content = dedent(
            """
            # Epic Title

            ### US-001: No Subtasks

            | Field | Value |
            |-------|-------|
            | **Story Points** | 1 |

            #### Description

            **As a** user
            **I want** to test
            **So that** it works
            """
        )

        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert len(stories[0].subtasks) == 0

    def test_empty_subtasks_section(self, parser):
        """Test parsing when Subtasks section is empty."""
        content = dedent(
            """
            # Epic Title

            ### US-001: Empty Subtasks

            | Field | Value |
            |-------|-------|
            | **Story Points** | 1 |

            #### Description

            **As a** user
            **I want** to test
            **So that** it works

            #### Subtasks

            #### Acceptance Criteria

            - [ ] AC item
            """
        )

        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert len(stories[0].subtasks) == 0


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestInlineSubtasksEdgeCases:
    """Tests for edge cases in inline subtask parsing."""

    def test_mixed_list_content(self):
        """Test that non-checkbox list items are ignored."""
        content = dedent(
            """
            - [ ] Real subtask
            - Regular list item without checkbox
            - [ ] Another subtask
            """
        )
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 2
        assert subtasks[0].name == "Real subtask"
        assert subtasks[1].name == "Another subtask"

    def test_nested_checkboxes(self):
        """Test parsing nested checkbox lists."""
        content = dedent(
            """
            - [ ] Parent task
              - [ ] Nested task
            - [ ] Another parent
            """
        )
        subtasks, _ = parse_inline_subtasks(content)

        # Should parse all checkboxes regardless of nesting
        assert len(subtasks) == 3

    def test_unicode_task_names(self):
        """Test parsing task names with unicode characters."""
        content = "- [ ] Implement 日本語 feature 🚀"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert "日本語" in subtasks[0].name
        assert "🚀" in subtasks[0].name

    def test_special_characters_in_name(self):
        """Test parsing task names with special characters."""
        content = "- [ ] Fix bug #123 & add tests"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Fix bug #123 & add tests"

    def test_no_space_after_dash(self):
        """Test parsing checkbox with no space between dash and bracket."""
        # This format is actually supported as the pattern is lenient
        content = "-[ ] No space after dash"
        subtasks, _ = parse_inline_subtasks(content)

        # The pattern matches because \s* allows zero spaces
        assert len(subtasks) == 1
        assert subtasks[0].name == "No space after dash"

    def test_multiple_story_point_formats(self):
        """Test various story point format variations."""
        test_cases = [
            ("- [ ] Task (0 SP)", 0),
            ("- [ ] Task (10 SP)", 10),
            ("- [ ] Task (99 points)", 99),
            ("- [ ] Task (1 story point)", 1),
            ("- [ ] Task (2 story points)", 2),
        ]

        for content, expected in test_cases:
            subtasks, _ = parse_inline_subtasks(content)
            assert len(subtasks) == 1, f"Failed for: {content}"
            assert subtasks[0].story_points == expected, f"Failed for: {content}"

    def test_em_dash_separator(self):
        """Test description extraction with em dash separator."""
        content = "- [ ] Task name — Description with em dash"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Task name"
        assert subtasks[0].description == "Description with em dash"

    def test_en_dash_separator(self):
        """Test description extraction with en dash separator."""
        content = "- [ ] Task name – Description with en dash"
        subtasks, _ = parse_inline_subtasks(content)

        assert len(subtasks) == 1
        assert subtasks[0].name == "Task name"
        assert subtasks[0].description == "Description with en dash"
