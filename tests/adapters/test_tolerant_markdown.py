"""
Tests for tolerant markdown parsing with precise error reporting.

Tests cover:
1. Tolerant field extraction (whitespace, case, aliases)
2. Tolerant section extraction (header levels, aliases)
3. Precise error location reporting (line, column, context)
4. Format variants (checkbox formats, description formats)
5. Warning collection for non-standard formats
"""

from textwrap import dedent

import pytest

from spectryn.adapters.parsers import (
    MarkdownParser,
    ParseErrorCode,
    ParseErrorInfo,
    ParseLocation,
    ParseResult,
    ParseWarning,
    TolerantFieldExtractor,
    TolerantPatterns,
    TolerantSectionExtractor,
    get_column_number,
    get_context_lines,
    get_line_content,
    get_line_number,
    parse_checkboxes_tolerant,
    parse_description_tolerant,
)


# =============================================================================
# Line/Position Utilities Tests
# =============================================================================


class TestLinePositionUtilities:
    """Tests for line number and position utilities."""

    def test_get_line_number_first_line(self):
        """Test line number for position on first line."""
        content = "hello world"
        assert get_line_number(content, 0) == 1
        assert get_line_number(content, 5) == 1

    def test_get_line_number_second_line(self):
        """Test line number for position on second line."""
        content = "line one\nline two"
        assert get_line_number(content, 9) == 2  # Start of "line two"

    def test_get_line_number_multiple_lines(self):
        """Test line number across multiple lines."""
        content = "line 1\nline 2\nline 3\nline 4"
        assert get_line_number(content, 0) == 1
        assert get_line_number(content, 7) == 2
        assert get_line_number(content, 14) == 3
        assert get_line_number(content, 21) == 4

    def test_get_column_number_start_of_line(self):
        """Test column number at start of line."""
        content = "hello\nworld"
        assert get_column_number(content, 6) == 1  # 'w' in world

    def test_get_column_number_middle_of_line(self):
        """Test column number in middle of line."""
        content = "hello\nworld"
        assert get_column_number(content, 8) == 3  # 'r' in world

    def test_get_line_content(self):
        """Test getting content of specific line."""
        content = "line one\nline two\nline three"
        assert get_line_content(content, 1) == "line one"
        assert get_line_content(content, 2) == "line two"
        assert get_line_content(content, 3) == "line three"

    def test_get_line_content_invalid_line(self):
        """Test getting content of invalid line returns empty."""
        content = "single line"
        assert get_line_content(content, 0) == ""
        assert get_line_content(content, 5) == ""

    def test_get_context_lines(self):
        """Test getting context lines with markers."""
        content = "line 1\nline 2\nline 3\nline 4\nline 5"
        context = get_context_lines(content, 3, before=1, after=1)
        assert "2: line 2" in context
        assert "> 3: line 3" in context  # Current line marked
        assert "4: line 4" in context


# =============================================================================
# Parse Location Tests
# =============================================================================


class TestParseLocation:
    """Tests for ParseLocation dataclass."""

    def test_location_str_with_line_only(self):
        """Test string representation with line only."""
        loc = ParseLocation(line=42)
        assert str(loc) == "line 42"

    def test_location_str_with_line_and_column(self):
        """Test string representation with line and column."""
        loc = ParseLocation(line=42, column=10)
        assert str(loc) == "line 42, column 10"

    def test_location_str_with_source(self):
        """Test string representation with source file."""
        loc = ParseLocation(line=42, source="test.md")
        assert str(loc) == "test.md:line 42"

    def test_location_str_full(self):
        """Test string representation with all fields."""
        loc = ParseLocation(line=42, column=10, source="test.md")
        assert str(loc) == "test.md:line 42, column 10"


# =============================================================================
# Tolerant Field Extractor Tests
# =============================================================================


class TestTolerantFieldExtractor:
    """Tests for TolerantFieldExtractor."""

    def test_extract_table_format(self):
        """Test extracting field from table format."""
        content = "| **Story Points** | 5 |"
        extractor = TolerantFieldExtractor(content)
        value, location = extractor.extract_field("Story Points")
        assert value == "5"
        assert location is not None

    def test_extract_inline_format(self):
        """Test extracting field from inline format."""
        content = "**Story Points**: 8"
        extractor = TolerantFieldExtractor(content)
        value, _location = extractor.extract_field("Story Points")
        assert value == "8"

    def test_extract_blockquote_format(self):
        """Test extracting field from blockquote format."""
        content = "> **Story Points**: 3"
        extractor = TolerantFieldExtractor(content)
        value, _location = extractor.extract_field("Story Points")
        assert value == "3"

    def test_extract_case_insensitive(self):
        """Test case-insensitive field extraction."""
        content = "| **story points** | 5 |"
        extractor = TolerantFieldExtractor(content)
        value, _ = extractor.extract_field("Story Points")
        assert value == "5"

    def test_extract_alias_points(self):
        """Test extraction with alias 'Points' for 'Story Points'."""
        content = "**Points**: 13"
        extractor = TolerantFieldExtractor(content)
        value, _ = extractor.extract_field("Story Points")
        assert value == "13"
        # Should generate warning about alias
        assert len(extractor.warnings) == 1
        assert "alias" in extractor.warnings[0].message.lower()

    def test_extract_with_extra_whitespace(self):
        """Test extraction tolerates extra whitespace."""
        content = "|  **Story Points**  |  5  |"
        extractor = TolerantFieldExtractor(content)
        value, _ = extractor.extract_field("Story Points")
        assert value == "5"

    def test_extract_missing_field_default(self):
        """Test default value for missing field."""
        content = "No fields here"
        extractor = TolerantFieldExtractor(content)
        value, location = extractor.extract_field("Story Points", default="0")
        assert value == "0"
        assert location is None

    def test_extract_missing_required_field_warning(self):
        """Test warning generated for missing required field."""
        content = "No fields here"
        extractor = TolerantFieldExtractor(content)
        extractor.extract_field("Story Points", required=True)
        assert len(extractor.warnings) == 1
        assert "Missing field" in extractor.warnings[0].message


# =============================================================================
# Tolerant Section Extractor Tests
# =============================================================================


class TestTolerantSectionExtractor:
    """Tests for TolerantSectionExtractor."""

    def test_extract_h4_section(self):
        """Test extracting h4 section."""
        content = dedent("""
            #### Acceptance Criteria
            - [ ] Item one
            - [x] Item two
            #### Next Section
        """)
        extractor = TolerantSectionExtractor(content)
        section, location = extractor.extract_section("Acceptance Criteria")
        assert "Item one" in section
        assert "Item two" in section
        assert location is not None

    def test_extract_h3_section(self):
        """Test extracting h3 section."""
        content = dedent("""
            ### Acceptance Criteria
            - [ ] Item one
            ### Next Section
        """)
        extractor = TolerantSectionExtractor(content)
        section, _ = extractor.extract_section("Acceptance Criteria")
        assert "Item one" in section

    def test_extract_h2_section(self):
        """Test extracting h2 section."""
        content = dedent("""
            ## Acceptance Criteria
            - [ ] Item one
            ## Next Section
        """)
        extractor = TolerantSectionExtractor(content)
        section, _ = extractor.extract_section("Acceptance Criteria")
        assert "Item one" in section

    def test_extract_section_alias(self):
        """Test section extraction with alias."""
        content = dedent("""
            #### AC
            - [ ] Acceptance item
        """)
        extractor = TolerantSectionExtractor(content)
        section, _ = extractor.extract_section("Acceptance Criteria")
        assert "Acceptance item" in section
        # Should generate alias warning
        assert len(extractor.warnings) == 1

    def test_extract_missing_section(self):
        """Test missing section returns empty string."""
        content = "No sections here"
        extractor = TolerantSectionExtractor(content)
        section, location = extractor.extract_section("Acceptance Criteria")
        assert section == ""
        assert location is None


# =============================================================================
# Tolerant Checkbox Parsing Tests
# =============================================================================


class TestTolerantCheckboxParsing:
    """Tests for tolerant checkbox parsing."""

    def test_parse_standard_checkboxes(self):
        """Test parsing standard checkbox format."""
        content = dedent("""
            - [ ] Unchecked item
            - [x] Checked item
            - [X] Also checked
        """)
        items, _warnings = parse_checkboxes_tolerant(content)
        assert len(items) == 3
        assert items[0] == ("Unchecked item", False)
        assert items[1] == ("Checked item", True)
        assert items[2] == ("Also checked", True)

    def test_parse_empty_checkbox(self):
        """Test parsing empty checkbox marker."""
        content = "- [] Empty checkbox"
        items, warnings = parse_checkboxes_tolerant(content)
        assert len(items) == 1
        assert items[0] == ("Empty checkbox", False)
        # Should generate warning
        assert len(warnings) >= 1

    def test_parse_asterisk_checkbox(self):
        """Test parsing checkbox with asterisk marker."""
        content = "* [ ] Asterisk item"
        items, warnings = parse_checkboxes_tolerant(content)
        assert len(items) == 1
        assert items[0] == ("Asterisk item", False)
        # Should generate warning about non-standard format
        assert len(warnings) >= 1

    def test_parse_plus_checkbox(self):
        """Test parsing checkbox with plus marker."""
        content = "+ [x] Plus item"
        items, _warnings = parse_checkboxes_tolerant(content)
        assert len(items) == 1
        assert items[0] == ("Plus item", True)


# =============================================================================
# Tolerant Description Parsing Tests
# =============================================================================


class TestTolerantDescriptionParsing:
    """Tests for tolerant description parsing."""

    def test_parse_standard_description(self):
        """Test parsing standard description format."""
        content = dedent("""
            **As a** developer
            **I want** to test parsing
            **So that** I can verify it works
        """)
        desc, _warnings = parse_description_tolerant(content)
        assert desc is not None
        assert desc["role"] == "developer"
        assert "test parsing" in desc["want"]
        assert "verify" in desc["benefit"]

    def test_parse_blockquote_description(self):
        """Test parsing blockquote description format."""
        content = dedent("""
            > **As a** user,
            > **I want** features,
            > **So that** I benefit.
        """)
        desc, _warnings = parse_description_tolerant(content)
        assert desc is not None
        assert desc["role"] == "user"

    def test_parse_single_line_description(self):
        """Test parsing single line description."""
        content = "**As a** user, **I want** features, **So that** I benefit"
        desc, _warnings = parse_description_tolerant(content)
        assert desc is not None
        assert desc["role"] == "user"
        assert desc["want"] == "features"
        assert desc["benefit"] == "I benefit"

    def test_parse_description_case_insensitive(self):
        """Test case-insensitive description keywords."""
        content = "**AS A** user **I WANT** features **SO THAT** I benefit"
        desc, _warnings = parse_description_tolerant(content)
        assert desc is not None

    def test_parse_partial_description_warning(self):
        """Test warning for incomplete description."""
        content = "**As a** user **I want** features"  # Missing "So that"
        desc, warnings = parse_description_tolerant(content)
        assert desc is not None
        assert "benefit" not in desc or not desc.get("benefit")
        assert len(warnings) >= 1


# =============================================================================
# Integration Tests - MarkdownParser.parse_stories_tolerant
# =============================================================================


class TestMarkdownParserTolerant:
    """Integration tests for MarkdownParser.parse_stories_tolerant()."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_parse_tolerant_basic(self, parser):
        """Test basic tolerant parsing."""
        content = dedent("""
            # Test Epic

            ### US-001: Test Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |
            | **Priority** | High |
            | **Status** | Planned |

            **As a** developer
            **I want** to test
            **So that** it works

            #### Acceptance Criteria
            - [ ] Test passes
        """)
        result = parser.parse_stories_tolerant(content)
        assert result.success
        assert len(result.stories) == 1
        assert str(result.stories[0].id) == "US-001"

    def test_parse_tolerant_returns_warnings(self, parser):
        """Test that tolerant parsing collects warnings."""
        content = dedent("""
            ### US-001: Story with Alias

            **Points**: 5

            **As a** user **I want** something **So that** it works
        """)
        result = parser.parse_stories_tolerant(content)
        assert result.success
        assert len(result.stories) == 1
        # Should have warning about using "Points" alias
        assert result.has_warnings

    def test_parse_tolerant_no_stories_error(self, parser):
        """Test error when no stories found."""
        content = "# Just a title\n\nNo stories here."
        result = parser.parse_stories_tolerant(content)
        assert not result.success
        assert len(result.errors) == 1
        assert result.errors[0].code == ParseErrorCode.NO_STORIES

    def test_parse_tolerant_duplicate_id_warning(self, parser):
        """Test warning for duplicate story IDs."""
        content = dedent("""
            ### US-001: First Story

            | **Story Points** | 3 |

            **As a** user **I want** first **So that** it works

            ### US-001: Duplicate Story

            | **Story Points** | 5 |

            **As a** user **I want** second **So that** it works
        """)
        result = parser.parse_stories_tolerant(content)
        assert result.success
        assert len(result.stories) == 2
        # Should have warning about duplicate
        assert any("Duplicate" in w.message for w in result.warnings)

    def test_parse_tolerant_error_location(self, parser):
        """Test that errors include precise location info."""
        content = "# Empty Epic\n\nNo stories."
        result = parser.parse_stories_tolerant(content)
        assert len(result.errors) == 1
        error = result.errors[0]
        assert error.location.line == 1
        assert error.context is not None


# =============================================================================
# Integration Tests - MarkdownParser.validate_detailed
# =============================================================================


class TestMarkdownParserValidateDetailed:
    """Tests for MarkdownParser.validate_detailed()."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_validate_detailed_valid(self, parser):
        """Test validation of valid markdown."""
        content = dedent("""
            ### US-001: Valid Story

            | **Story Points** | 5 |

            **As a** user
            **I want** something
            **So that** I benefit
        """)
        errors, _warnings = parser.validate_detailed(content)
        assert len(errors) == 0

    def test_validate_detailed_missing_story_points(self, parser):
        """Test validation catches missing story points."""
        content = dedent("""
            ### US-001: Missing Points

            **As a** user
            **I want** something
            **So that** I benefit
        """)
        errors, _warnings = parser.validate_detailed(content)
        assert len(errors) == 1
        assert "Story Points" in errors[0].message
        assert errors[0].location.line is not None

    def test_validate_detailed_invalid_story_points(self, parser):
        """Test validation warns about invalid story points."""
        content = dedent("""
            ### US-001: Invalid Points

            | **Story Points** | abc |

            **As a** user
            **I want** something
            **So that** I benefit
        """)
        _errors, warnings = parser.validate_detailed(content)
        # Invalid points should be a warning, not error
        assert any("not a valid number" in w.message for w in warnings)

    def test_validate_detailed_missing_description(self, parser):
        """Test validation warns about missing description."""
        content = dedent("""
            ### US-001: No Description

            | **Story Points** | 5 |

            Just some text without proper format.
        """)
        _errors, warnings = parser.validate_detailed(content)
        assert any("description" in w.message.lower() for w in warnings)

    def test_validate_detailed_error_has_context(self, parser):
        """Test that validation errors include context."""
        content = "# Empty file\n\nNo stories here."
        errors, _warnings = parser.validate_detailed(content)
        assert len(errors) == 1
        assert errors[0].context is not None

    def test_validate_detailed_error_has_suggestion(self, parser):
        """Test that validation errors include suggestions."""
        content = "# Empty file"
        errors, _warnings = parser.validate_detailed(content)
        assert len(errors) == 1
        assert errors[0].suggestion is not None


# =============================================================================
# Tolerant Pattern Tests
# =============================================================================


class TestTolerantPatterns:
    """Tests for TolerantPatterns regex patterns."""

    def test_story_header_standard(self):
        """Test standard story header pattern."""
        content = "### US-001: Story Title\n"
        match = TolerantPatterns.STORY_HEADER.search(content)
        assert match is not None
        assert match.group(1) == "US-001"
        assert match.group(2).strip() == "Story Title"

    def test_story_header_with_emoji(self):
        """Test story header with emoji prefix."""
        content = "### ✅ US-001: Completed Story\n"
        match = TolerantPatterns.STORY_HEADER.search(content)
        assert match is not None
        assert match.group(1) == "US-001"

    def test_story_header_underscore_separator(self):
        """Test story header with underscore separator."""
        content = "### PROJ_123: Underscore ID\n"
        match = TolerantPatterns.STORY_HEADER.search(content)
        assert match is not None
        assert match.group(1) == "PROJ_123"

    def test_story_header_slash_separator(self):
        """Test story header with slash separator."""
        content = "### PROJ/456: Slash ID\n"
        match = TolerantPatterns.STORY_HEADER.search(content)
        assert match is not None
        assert match.group(1) == "PROJ/456"

    def test_story_header_github_style(self):
        """Test story header with GitHub-style #number."""
        content = "### #123: GitHub Style\n"
        match = TolerantPatterns.STORY_HEADER.search(content)
        assert match is not None
        assert match.group(1) == "#123"

    def test_story_header_h1_standalone(self):
        """Test h1 standalone story header."""
        content = "# PROJ-001: Standalone Story"
        match = TolerantPatterns.STORY_HEADER_H1.search(content)
        assert match is not None
        assert match.group(1) == "PROJ-001"

    def test_checkbox_pattern_variations(self):
        """Test checkbox pattern matches various formats."""
        variations = [
            "- [ ] Item",
            "- [x] Item",
            "- [X] Item",
            "* [ ] Item",
            "+ [x] Item",
            "  - [ ] Indented",
        ]
        for variation in variations:
            match = TolerantPatterns.CHECKBOX.search(variation)
            assert match is not None, f"Failed to match: {variation}"

    def test_field_pattern_factory(self):
        """Test field pattern factory creates working patterns."""
        table_pattern = TolerantPatterns.field_pattern("Story Points", "table")
        content = "| **Story Points** | 5 |"
        match = table_pattern.search(content)
        assert match is not None
        assert match.group(1).strip() == "5"

    def test_section_pattern_factory(self):
        """Test section pattern factory creates working patterns."""
        pattern = TolerantPatterns.section_pattern("Acceptance Criteria")
        content = "#### Acceptance Criteria\n- Item\n#### Next"
        match = pattern.search(content)
        assert match is not None
        assert "Item" in match.group(2)
