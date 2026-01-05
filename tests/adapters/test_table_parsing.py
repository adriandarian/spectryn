"""Tests for table parsing functionality in tolerant_markdown.

Tests cover:
- Basic table parsing (headers, rows, cells)
- Column alignment detection (left, center, right)
- Cell formatting cleanup (bold, italic, code)
- Edge cases (empty cells, mismatched columns, whitespace)
- to_dicts() conversion
- table_to_markdown() roundtrip
- Multi-table extraction
- Section-based extraction

Note: All parse functions return tuples of (result, warnings) to support
tolerant parsing with diagnostics.
"""

import textwrap

import pytest

from spectra.adapters.parsers.tolerant_markdown import (
    ParsedTable,
    TableAlignment,
    TableCell,
    extract_table_from_section,
    extract_tables_from_content,
    parse_markdown_table,
    table_to_markdown,
)


class TestBasicTableParsing:
    """Test basic table parsing functionality."""

    def test_parse_simple_table(self) -> None:
        """Parse a simple 2x2 table."""
        content = textwrap.dedent("""
            | Name | Value |
            |------|-------|
            | foo  | 123   |
            | bar  | 456   |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.headers == ["Name", "Value"]
        assert len(table.rows) == 2
        assert table.rows[0][0].cleaned == "foo"
        assert table.rows[0][1].cleaned == "123"
        assert table.rows[1][0].cleaned == "bar"
        assert table.rows[1][1].cleaned == "456"

    def test_parse_single_row_table(self) -> None:
        """Parse a table with only one data row."""
        content = textwrap.dedent("""
            | Column A | Column B |
            |----------|----------|
            | value    | data     |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert len(table.rows) == 1
        assert table.rows[0][0].cleaned == "value"

    def test_parse_table_with_many_columns(self) -> None:
        """Parse a table with many columns."""
        content = textwrap.dedent("""
            | A | B | C | D | E |
            |---|---|---|---|---|
            | 1 | 2 | 3 | 4 | 5 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert len(table.headers) == 5
        assert table.headers == ["A", "B", "C", "D", "E"]

    def test_parse_empty_content_returns_none(self) -> None:
        """Empty content should return None."""
        table, warnings = parse_markdown_table("")
        assert table is None

        table2, warnings2 = parse_markdown_table("   \n  \n  ")
        assert table2 is None

    def test_parse_non_table_content_returns_none(self) -> None:
        """Non-table content should return None."""
        content = textwrap.dedent("""
            This is just regular text
            Without any table structure
        """).strip()

        table, warnings = parse_markdown_table(content)
        assert table is None

    def test_parse_table_preserves_line_numbers(self) -> None:
        """Table should preserve line number information."""
        content = textwrap.dedent("""
            # Some header

            | Name | Value |
            |------|-------|
            | test | 123   |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.line_number == 3  # 0-indexed, starts at line 3


class TestColumnAlignment:
    """Test column alignment detection."""

    def test_default_alignment_is_none(self) -> None:
        """Default alignment should be NONE."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
            | 1 | 2 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.alignments == [TableAlignment.NONE, TableAlignment.NONE]

    def test_left_alignment(self) -> None:
        """Detect left alignment (:---)."""
        content = textwrap.dedent("""
            | Left |
            |:-----|
            | text |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.alignments == [TableAlignment.LEFT]

    def test_right_alignment(self) -> None:
        """Detect right alignment (---:)."""
        content = textwrap.dedent("""
            | Right |
            |------:|
            | text  |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.alignments == [TableAlignment.RIGHT]

    def test_center_alignment(self) -> None:
        """Detect center alignment (:---:)."""
        content = textwrap.dedent("""
            | Center |
            |:------:|
            | text   |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.alignments == [TableAlignment.CENTER]

    def test_mixed_alignments(self) -> None:
        """Test mixed alignments in one table."""
        content = textwrap.dedent("""
            | Left | Center | Right | Default |
            |:-----|:------:|------:|---------|
            | a    | b      | c     | d       |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.alignments == [
            TableAlignment.LEFT,
            TableAlignment.CENTER,
            TableAlignment.RIGHT,
            TableAlignment.NONE,
        ]

    def test_cell_inherits_alignment(self) -> None:
        """Cells should have alignment from column."""
        content = textwrap.dedent("""
            | Left | Right |
            |:-----|------:|
            | a    | b     |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].alignment == TableAlignment.LEFT
        assert table.rows[0][1].alignment == TableAlignment.RIGHT


class TestCellFormatting:
    """Test cell formatting cleanup."""

    def test_strip_bold_formatting(self) -> None:
        """Bold formatting should be stripped from cleaned."""
        content = textwrap.dedent("""
            | Col |
            |-----|
            | **bold** |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].content == "**bold**"
        assert table.rows[0][0].cleaned == "bold"

    def test_strip_italic_formatting(self) -> None:
        """Italic formatting should be stripped from cleaned."""
        content = textwrap.dedent("""
            | Col |
            |-----|
            | *italic* |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].cleaned == "italic"

    def test_strip_code_formatting(self) -> None:
        """Code formatting should be stripped from cleaned."""
        content = textwrap.dedent("""
            | Col |
            |-----|
            | `code` |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].cleaned == "code"

    def test_preserve_content_with_formatting(self) -> None:
        """Original content should preserve formatting."""
        content = textwrap.dedent("""
            | Col |
            |-----|
            | **bold** and *italic* |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert "**bold**" in table.rows[0][0].content
        assert "*italic*" in table.rows[0][0].content

    def test_strip_leading_trailing_whitespace(self) -> None:
        """Whitespace should be stripped from cells."""
        content = textwrap.dedent("""
            | Col |
            |-----|
            |   spaces   |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].cleaned == "spaces"


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_cells(self) -> None:
        """Handle empty cells gracefully."""
        content = textwrap.dedent("""
            | A | B | C |
            |---|---|---|
            |   | x |   |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].is_empty
        assert not table.rows[0][1].is_empty
        assert table.rows[0][2].is_empty

    def test_mismatched_column_count(self) -> None:
        """Handle rows with different column counts."""
        content = textwrap.dedent("""
            | A | B | C |
            |---|---|---|
            | 1 | 2 |
            | x | y | z |
        """).strip()

        table, warnings = parse_markdown_table(content)

        # Table should still parse but handle inconsistency
        assert table is not None
        assert len(table.headers) == 3

    def test_table_without_leading_pipe(self) -> None:
        """Tables without leading pipes should still parse."""
        content = textwrap.dedent("""
            A | B |
            ---|---|
            1 | 2 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert len(table.headers) >= 2

    def test_extra_whitespace_in_separator(self) -> None:
        """Extra whitespace in separator row should be handled."""
        content = textwrap.dedent("""
            | A | B |
            |  ---  |  ---  |
            | 1 | 2 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.headers == ["A", "B"]

    def test_unicode_content(self) -> None:
        """Handle unicode characters in cells."""
        content = textwrap.dedent("""
            | Name | Symbol |
            |------|--------|
            | café | ☕     |
            | 日本 | 🗾     |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].cleaned == "café"
        assert table.rows[0][1].cleaned == "☕"
        assert table.rows[1][0].cleaned == "日本"


class TestCellTypeConversion:
    """Test cell type conversion helpers."""

    def test_as_int_valid(self) -> None:
        """Valid integer string should convert."""
        content = textwrap.dedent("""
            | Num |
            |-----|
            | 123 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].as_int == 123

    def test_as_int_invalid_returns_none(self) -> None:
        """Invalid integer string should return None."""
        content = textwrap.dedent("""
            | Num |
            |-----|
            | abc |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].as_int is None

    def test_as_float_valid(self) -> None:
        """Valid float string should convert."""
        content = textwrap.dedent("""
            | Num |
            |-----|
            | 3.14 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].as_float == pytest.approx(3.14)

    def test_as_bool_variations(self) -> None:
        """Test various boolean representations."""
        content = textwrap.dedent("""
            | Val |
            |-----|
            | true |
            | yes |
            | 1 |
            | false |
            | no |
            | 0 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.rows[0][0].as_bool is True
        assert table.rows[1][0].as_bool is True
        assert table.rows[2][0].as_bool is True
        assert table.rows[3][0].as_bool is False
        assert table.rows[4][0].as_bool is False
        assert table.rows[5][0].as_bool is False


class TestParsedTableMethods:
    """Test ParsedTable dataclass methods."""

    def test_get_column_by_index(self) -> None:
        """Get column by numeric index."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
            | 1 | 2 |
            | 3 | 4 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        col_b = table.get_column(1)
        assert len(col_b) == 2
        assert col_b[0].cleaned == "2"
        assert col_b[1].cleaned == "4"

    def test_get_column_by_header(self) -> None:
        """Get column by header name."""
        content = textwrap.dedent("""
            | Name | Age |
            |------|-----|
            | Alice | 30 |
            | Bob | 25 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        ages = table.get_column_by_header("Age")
        assert ages is not None
        assert len(ages) == 2
        assert ages[0].cleaned == "30"
        assert ages[1].cleaned == "25"

    def test_get_column_by_header_not_found(self) -> None:
        """Non-existent header should return empty list."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
            | 1 | 2 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.get_column_by_header("C") == []

    def test_get_row(self) -> None:
        """Get row by index."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
            | 1 | 2 |
            | 3 | 4 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        row = table.get_row(1)
        assert row is not None
        assert row[0].cleaned == "3"
        assert row[1].cleaned == "4"

    def test_get_cell(self) -> None:
        """Get specific cell by row and column."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
            | 1 | 2 |
            | 3 | 4 |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        cell = table.get_cell(1, 1)
        assert cell is not None
        assert cell.cleaned == "4"

    def test_to_dicts(self) -> None:
        """Convert table to list of dictionaries."""
        content = textwrap.dedent("""
            | Name | Age | City |
            |------|-----|------|
            | Alice | 30 | NYC |
            | Bob | 25 | LA |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        dicts = table.to_dicts()
        assert len(dicts) == 2
        assert dicts[0] == {"name": "Alice", "age": "30", "city": "NYC"}
        assert dicts[1] == {"name": "Bob", "age": "25", "city": "LA"}

    def test_find_column_index(self) -> None:
        """Find column index by header name."""
        content = textwrap.dedent("""
            | First | Second | Third |
            |-------|--------|-------|
            | a     | b      | c     |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        assert table.find_column_index("First") == 0
        assert table.find_column_index("Second") == 1
        assert table.find_column_index("Third") == 2
        assert table.find_column_index("Fourth") is None


class TestMultiTableExtraction:
    """Test extracting multiple tables from content."""

    def test_extract_multiple_tables(self) -> None:
        """Extract all tables from content with multiple tables."""
        content = textwrap.dedent("""
            # First Section

            | A | B |
            |---|---|
            | 1 | 2 |

            Some text between tables.

            | X | Y | Z |
            |---|---|---|
            | a | b | c |
        """).strip()

        tables, warnings = extract_tables_from_content(content)

        assert len(tables) == 2
        assert tables[0].headers == ["A", "B"]
        assert tables[1].headers == ["X", "Y", "Z"]

    def test_extract_no_tables(self) -> None:
        """Return empty list when no tables found."""
        content = textwrap.dedent("""
            # Just Headers

            Some regular content without any tables.
        """).strip()

        tables, warnings = extract_tables_from_content(content)

        assert tables == []


class TestSectionExtraction:
    """Test extracting tables from specific sections."""

    def test_extract_from_named_section(self) -> None:
        """Extract table from a named section."""
        content = textwrap.dedent("""
            # Overview

            | Wrong | Table |
            |-------|-------|
            | skip  | this  |

            ## Data Section

            | Correct | Table |
            |---------|-------|
            | get     | this  |

            ## Another Section

            More content here.
        """).strip()

        table, warnings = extract_table_from_section(content, "Data Section")

        assert table is not None
        assert table.headers == ["Correct", "Table"]
        assert table.rows[0][0].cleaned == "get"

    def test_extract_from_nonexistent_section(self) -> None:
        """Return None when section not found."""
        content = textwrap.dedent("""
            # Only Section

            | A | B |
            |---|---|
            | 1 | 2 |
        """).strip()

        table, warnings = extract_table_from_section(content, "Missing Section")

        assert table is None

    def test_extract_from_section_without_table(self) -> None:
        """Return None when section has no table."""
        content = textwrap.dedent("""
            ## Target Section

            No table here, just text.

            ## Other Section

            | Has | Table |
            |-----|-------|
            | but | wrong |
        """).strip()

        table, warnings = extract_table_from_section(content, "Target Section")

        assert table is None


class TestTableToMarkdown:
    """Test converting ParsedTable back to markdown."""

    def test_basic_roundtrip(self) -> None:
        """Table should roundtrip to markdown correctly."""
        content = textwrap.dedent("""
            | Name | Value |
            |------|-------|
            | foo  | 123   |
            | bar  | 456   |
        """).strip()

        table, warnings = parse_markdown_table(content)
        assert table is not None

        markdown = table_to_markdown(table)

        # Should contain the data
        assert "Name" in markdown
        assert "Value" in markdown
        assert "foo" in markdown
        assert "123" in markdown

        # Should be parseable again
        reparsed, warnings2 = parse_markdown_table(markdown)
        assert reparsed is not None
        assert reparsed.headers == table.headers
        assert len(reparsed.rows) == len(table.rows)

    def test_alignment_preserved_in_roundtrip(self) -> None:
        """Alignment should be preserved in roundtrip."""
        content = textwrap.dedent("""
            | Left | Center | Right |
            |:-----|:------:|------:|
            | a    | b      | c     |
        """).strip()

        table, warnings = parse_markdown_table(content)
        assert table is not None

        markdown = table_to_markdown(table)

        # Parse again and check alignment
        reparsed, warnings2 = parse_markdown_table(markdown)
        assert reparsed is not None
        assert reparsed.alignments == [
            TableAlignment.LEFT,
            TableAlignment.CENTER,
            TableAlignment.RIGHT,
        ]

    def test_empty_table_to_markdown(self) -> None:
        """Empty rows table should produce valid markdown."""
        content = textwrap.dedent("""
            | A | B |
            |---|---|
        """).strip()

        table, warnings = parse_markdown_table(content)
        assert table is not None

        markdown = table_to_markdown(table)

        assert "A" in markdown
        assert "B" in markdown


class TestIntegration:
    """Integration tests for table parsing in realistic scenarios."""

    def test_user_story_acceptance_criteria_table(self) -> None:
        """Parse acceptance criteria in table format."""
        content = textwrap.dedent("""
            ## Acceptance Criteria

            | Criterion | Expected Result |
            |-----------|-----------------|
            | User enters valid email | System accepts input |
            | User enters invalid email | Error message shown |
            | Email field empty | Validation prevents submit |
        """).strip()

        table, warnings = extract_table_from_section(content, "Acceptance Criteria")

        assert table is not None
        assert len(table.rows) == 3
        criteria = table.to_dicts()
        assert criteria[0]["criterion"] == "User enters valid email"
        assert criteria[2]["expected result"] == "Validation prevents submit"

    def test_sprint_planning_table(self) -> None:
        """Parse sprint planning information table."""
        content = textwrap.dedent("""
            # Sprint 42

            | Story | Points | Assignee | Status |
            |:------|:------:|:--------:|-------:|
            | AUTH-1 | 5 | Alice | Done |
            | AUTH-2 | 3 | Bob | In Progress |
            | AUTH-3 | 8 | Carol | To Do |
        """).strip()

        table, warnings = parse_markdown_table(content)

        assert table is not None
        dicts = table.to_dicts()

        assert dicts[0]["story"] == "AUTH-1"
        assert dicts[0]["points"] == "5"
        assert dicts[1]["status"] == "In Progress"
        assert dicts[2]["assignee"] == "Carol"

    def test_requirements_matrix_table(self) -> None:
        """Parse requirements traceability matrix."""
        content = textwrap.dedent("""
            ## Requirements Matrix

            | Requirement | Priority | Test Case | Implemented |
            |-------------|----------|-----------|-------------|
            | REQ-001 | High | TC-001, TC-002 | Yes |
            | REQ-002 | Medium | TC-003 | No |
            | REQ-003 | Low | | No |
        """).strip()

        table, warnings = extract_table_from_section(content, "Requirements Matrix")

        assert table is not None
        assert len(table.rows) == 3

        # Check empty cell
        assert table.rows[2][2].is_empty

        # Check implemented column
        impl_col = table.get_column_by_header("Implemented")
        assert impl_col is not None
        assert len(impl_col) == 3
        assert impl_col[0].as_bool is True
        assert impl_col[1].as_bool is False
