"""
Tolerant Markdown Parsing - Enhanced markdown parsing with precise error reporting.

This module provides utilities for flexible, forgiving markdown parsing that:
1. Tolerates common formatting variants (whitespace, case, etc.)
2. Provides precise parse error locations (line, column, context)
3. Collects warnings for non-critical issues without failing

Usage:
    from spectra.adapters.parsers.tolerant_markdown import (
        TolerantMarkdownParser,
        ParseResult,
        ParseError,
        ParseWarning,
    )

    parser = TolerantMarkdownParser()
    result = parser.parse(content)

    if result.errors:
        for error in result.errors:
            print(f"Error at line {error.line}: {error.message}")

    if result.warnings:
        for warning in result.warnings:
            print(f"Warning at line {warning.line}: {warning.message}")

    stories = result.stories
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from spectra.core.domain.entities import UserStory


class ParseSeverity(Enum):
    """Severity level for parse issues."""

    ERROR = "error"  # Parsing cannot continue or data is corrupt
    WARNING = "warning"  # Parsing can continue, but data may be incomplete
    INFO = "info"  # Informational message about parsing behavior


@dataclass(frozen=True)
class ParseLocation:
    """
    Precise location in the source document.

    Attributes:
        line: 1-indexed line number
        column: 1-indexed column number (optional)
        end_line: End line for multi-line issues (optional)
        end_column: End column for multi-line issues (optional)
        source: Source file path or identifier (optional)
    """

    line: int
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    source: str | None = None

    def __str__(self) -> str:
        """Format location for display."""
        parts = []
        if self.source:
            parts.append(self.source)
        if self.column:
            parts.append(f"line {self.line}, column {self.column}")
        else:
            parts.append(f"line {self.line}")
        return ":".join(parts) if self.source else parts[0]


@dataclass(frozen=True)
class ParseIssue:
    """
    Base class for parse errors and warnings.

    Attributes:
        message: Human-readable description of the issue
        location: Location in the source document
        severity: Error severity level
        context: Surrounding text for context (optional)
        suggestion: How to fix the issue (optional)
        code: Error code for programmatic handling (optional)
    """

    message: str
    location: ParseLocation
    severity: ParseSeverity
    context: str | None = None
    suggestion: str | None = None
    code: str | None = None

    @property
    def line(self) -> int:
        """Get the line number for convenience."""
        return self.location.line

    @property
    def column(self) -> int | None:
        """Get the column number for convenience."""
        return self.location.column

    def __str__(self) -> str:
        """Format issue for display."""
        parts = [f"[{self.severity.value.upper()}] {self.location}: {self.message}"]
        if self.context:
            parts.append(f"  Context: {self.context}")
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(parts)


@dataclass(frozen=True)
class ParseErrorInfo(ParseIssue):
    """A parse error that may prevent successful parsing."""

    severity: ParseSeverity = field(default=ParseSeverity.ERROR, init=False)


@dataclass(frozen=True)
class ParseWarning(ParseIssue):
    """A parse warning for non-critical issues."""

    severity: ParseSeverity = field(default=ParseSeverity.WARNING, init=False)


@dataclass
class ParseResult:
    """
    Result of parsing with stories, errors, and warnings.

    Attributes:
        stories: Successfully parsed user stories
        errors: Parse errors (may cause data loss)
        warnings: Parse warnings (parsing succeeded with caveats)
        source: Source file path or content identifier
    """

    stories: list[UserStory] = field(default_factory=list)
    errors: list[ParseErrorInfo] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    source: str | None = None

    @property
    def success(self) -> bool:
        """Check if parsing was successful (no errors)."""
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0


# =============================================================================
# Tolerant Pattern Matchers
# =============================================================================


class TolerantPatterns:
    """
    Tolerant regex patterns that handle common formatting variants.

    Each pattern is designed to be forgiving of:
    - Extra whitespace
    - Missing/extra newlines
    - Case variations
    - Alternative formatting
    """

    # Story header patterns - tolerant of whitespace, emoji, case
    # Matches: ### US-001: Title, ### ✅ PROJ-123: Title, ###US-001:Title
    STORY_HEADER = re.compile(
        r"^#{2,4}\s*"  # 2-4 hashes with optional space
        r"(?:[^\n]*?\s)?"  # Optional prefix (emoji, status)
        r"([A-Z]+[-_/]\d+|#\d+)"  # Story ID (flexible separators)
        r"\s*:\s*"  # Colon with flexible whitespace
        r"([^\n]+?)"  # Title
        r"\s*$",  # Trailing whitespace
        re.MULTILINE | re.IGNORECASE,
    )

    # Standalone h1 story - tolerant version
    STORY_HEADER_H1 = re.compile(
        r"^#\s*"  # Single hash
        r"(?:[^\n]*?\s)?"  # Optional prefix
        r"([A-Z]+[-_/]\d+|#?\d+)"  # Story ID (more flexible for h1)
        r"\s*:\s*"  # Colon
        r"([^\n]+?)"  # Title
        r"(?:\s*[✅🔲🟡⏸️🔄📋]+)?"  # Optional trailing emoji
        r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Field extraction - tolerant of formatting variations
    # Table format: | **Field** | Value | or |**Field**|Value|
    TABLE_FIELD = re.compile(r"\|\s*\*?\*?{field}\*?\*?\s*\|\s*([^|]+?)\s*\|", re.IGNORECASE)

    # Inline format: **Field**: Value or **Field** : Value
    INLINE_FIELD = re.compile(
        r"(?<!>)\s*\*\*{field}\*\*\s*:\s*(.+?)(?:\s*$|\s{{2,}}|\n)", re.MULTILINE | re.IGNORECASE
    )

    # Blockquote format: > **Field**: Value
    BLOCKQUOTE_FIELD = re.compile(
        r">\s*\*\*{field}\*\*\s*:\s*(.+?)(?:\s*$)", re.MULTILINE | re.IGNORECASE
    )

    # Acceptance criteria - various checkbox formats
    # Matches: - [ ] Item, - [x] Item, * [ ] Item, - [] Item, -[ ] Item
    CHECKBOX = re.compile(r"^[\s]*[-*+]\s*\[([xX\s]?)\]\s*(.+?)$", re.MULTILINE)

    # Section headers - tolerant of level and formatting
    # Matches: #### Section, ### Section, ## Section, ####Section
    SECTION_HEADER = re.compile(r"^(#{2,4})\s*{section}\s*$", re.MULTILINE | re.IGNORECASE)

    # Description pattern - flexible "As a/I want/So that"
    DESCRIPTION_FULL = re.compile(
        r"\*\*As\s+a\*\*\s*(.+?)"  # As a [role]
        r"(?:,?\s*\n\s*(?:>\s*)?)?"  # Optional newline with blockquote
        r"\*\*I\s+want\*\*\s*(.+?)"  # I want [feature]
        r"(?:,?\s*\n\s*(?:>\s*)?)?"  # Optional newline with blockquote
        r"\*\*So\s+that\*\*\s*(.+?)$",  # So that [benefit]
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )

    # Alternative description formats (single line, lenient)
    DESCRIPTION_SINGLE_LINE = re.compile(
        r"\*\*As\s+a\*\*\s*([^,\n]+)"
        r"[,\s]+"
        r"\*\*I\s+want\*\*\s*([^,\n]+)"
        r"[,\s]+"
        r"\*\*So\s+that\*\*\s*([^.\n]+)",
        re.IGNORECASE,
    )

    @classmethod
    def field_pattern(cls, field_name: str, format_type: str = "all") -> re.Pattern[str]:
        """
        Create a pattern for extracting a specific field.

        Args:
            field_name: Name of the field to match
            format_type: 'table', 'inline', 'blockquote', or 'all'

        Returns:
            Compiled regex pattern
        """
        # Escape special regex chars but allow flexible spacing
        field_escaped = re.escape(field_name)
        # Allow optional spaces in field name (e.g., "Story Points" or "Story  Points")
        field_pattern = field_escaped.replace(r"\ ", r"\s+")

        if format_type == "table":
            return re.compile(
                rf"\|\s*\*?\*?{field_pattern}\*?\*?\s*\|\s*([^|]+?)\s*\|",
                re.IGNORECASE,
            )
        if format_type == "inline":
            return re.compile(
                rf"(?<!>)\s*\*\*{field_pattern}\*\*\s*:\s*(.+?)(?:\s*$|\s{{2,}}|\n)",
                re.MULTILINE | re.IGNORECASE,
            )
        if format_type == "blockquote":
            return re.compile(
                rf">\s*\*\*{field_pattern}\*\*\s*:\s*(.+?)(?:\s*$)",
                re.MULTILINE | re.IGNORECASE,
            )
        # All formats combined
        return re.compile(
            rf"(?:"
            rf"\|\s*\*?\*?{field_pattern}\*?\*?\s*\|\s*([^|]+?)\s*\|"
            rf"|"
            rf"(?<!>)\s*\*\*{field_pattern}\*\*\s*:\s*(.+?)(?:\s*$|\s{{2,}}|\n)"
            rf"|"
            rf">\s*\*\*{field_pattern}\*\*\s*:\s*(.+?)(?:\s*$)"
            rf")",
            re.MULTILINE | re.IGNORECASE,
        )

    @classmethod
    def section_pattern(cls, section_name: str, levels: str = "2-4") -> re.Pattern[str]:
        """
        Create a pattern for matching a section header.

        Args:
            section_name: Name of the section (e.g., "Acceptance Criteria")
            levels: Header level range (e.g., "2-4" for ##-####) - currently unused

        Returns:
            Compiled regex pattern matching the section and capturing content
        """
        _ = levels  # Reserved for future use
        section_escaped = re.escape(section_name)
        # Allow flexible spacing and optional plural
        section_pattern = section_escaped.replace(r"\ ", r"\s+")

        return re.compile(
            rf"^(#{{2,4}})\s*{section_pattern}\s*\n([\s\S]*?)(?=^#{{2,4}}\s|\n---|\Z)",
            re.MULTILINE | re.IGNORECASE,
        )


# =============================================================================
# Line/Position Utilities
# =============================================================================


def get_line_number(content: str, position: int) -> int:
    """
    Get the 1-indexed line number for a character position.

    Args:
        content: Full text content
        position: Character position (0-indexed)

    Returns:
        1-indexed line number
    """
    return content[:position].count("\n") + 1


def get_column_number(content: str, position: int) -> int:
    """
    Get the 1-indexed column number for a character position.

    Args:
        content: Full text content
        position: Character position (0-indexed)

    Returns:
        1-indexed column number
    """
    line_start = content.rfind("\n", 0, position) + 1
    return position - line_start + 1


def get_line_content(content: str, line_number: int) -> str:
    """
    Get the content of a specific line.

    Args:
        content: Full text content
        line_number: 1-indexed line number

    Returns:
        Content of the specified line (without newline)
    """
    lines = content.split("\n")
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1]
    return ""


def get_context_lines(content: str, line_number: int, before: int = 1, after: int = 1) -> str:
    """
    Get surrounding lines for context.

    Args:
        content: Full text content
        line_number: 1-indexed line number
        before: Number of lines before
        after: Number of lines after

    Returns:
        Formatted context string with line numbers
    """
    lines = content.split("\n")
    start = max(0, line_number - 1 - before)
    end = min(len(lines), line_number + after)

    context_lines = []
    for i in range(start, end):
        prefix = ">" if i == line_number - 1 else " "
        context_lines.append(f"{prefix} {i + 1}: {lines[i]}")

    return "\n".join(context_lines)


def location_from_match(
    content: str, match: re.Match[str], source: str | None = None
) -> ParseLocation:
    """
    Create a ParseLocation from a regex match.

    Args:
        content: Full text content
        match: Regex match object
        source: Source file path (optional)

    Returns:
        ParseLocation with line and column info
    """
    start = match.start()
    end = match.end()
    return ParseLocation(
        line=get_line_number(content, start),
        column=get_column_number(content, start),
        end_line=get_line_number(content, end),
        end_column=get_column_number(content, end),
        source=source,
    )


# =============================================================================
# Tolerant Field Extraction
# =============================================================================


class TolerantFieldExtractor:
    """
    Extract fields from markdown content with tolerance for formatting variants.

    Handles:
    - Multiple format styles (table, inline, blockquote)
    - Case-insensitive field names
    - Field name aliases (Story Points / Points)
    - Extra/missing whitespace
    """

    # Field aliases for common variations
    FIELD_ALIASES: dict[str, list[str]] = {
        "Story Points": ["Points", "SP", "Estimate", "Story Point"],
        "Priority": ["Prio", "P"],
        "Status": ["State"],
        "Story ID": ["ID", "Issue ID"],
    }

    def __init__(self, content: str, source: str | None = None):
        """
        Initialize extractor with content.

        Args:
            content: Markdown content to extract from
            source: Source file path for error reporting
        """
        self.content = content
        self.source = source
        self.warnings: list[ParseWarning] = []

    def extract_field(
        self,
        field_name: str,
        default: str = "",
        required: bool = False,
    ) -> tuple[str, ParseLocation | None]:
        """
        Extract a field value with tolerance for variants.

        Args:
            field_name: Primary field name to look for
            default: Default value if not found
            required: Whether to add warning if not found

        Returns:
            Tuple of (value, location) where location is None if not found
        """
        # Get all variants of the field name
        variants = [field_name, *self.FIELD_ALIASES.get(field_name, [])]

        for variant in variants:
            # Try table format
            pattern = TolerantPatterns.field_pattern(variant, "table")
            match = pattern.search(self.content)
            if match:
                value = self._clean_field_value(match.group(1))
                location = location_from_match(self.content, match, self.source)
                if variant != field_name:
                    self._add_alias_warning(variant, field_name, location)
                return value, location

            # Try inline format
            pattern = TolerantPatterns.field_pattern(variant, "inline")
            match = pattern.search(self.content)
            if match:
                value = self._clean_field_value(match.group(1))
                location = location_from_match(self.content, match, self.source)
                if variant != field_name:
                    self._add_alias_warning(variant, field_name, location)
                return value, location

            # Try blockquote format
            pattern = TolerantPatterns.field_pattern(variant, "blockquote")
            match = pattern.search(self.content)
            if match:
                value = self._clean_field_value(match.group(1))
                location = location_from_match(self.content, match, self.source)
                if variant != field_name:
                    self._add_alias_warning(variant, field_name, location)
                return value, location

        # Not found
        if required:
            self.warnings.append(
                ParseWarning(
                    message=f"Missing field '{field_name}'",
                    location=ParseLocation(line=1, source=self.source),
                    suggestion=f"Add **{field_name}**: <value> or a table row with the field",
                    code="MISSING_FIELD",
                )
            )

        return default, None

    def _clean_field_value(self, value: str) -> str:
        """Clean and normalize a field value."""
        # Remove leading/trailing whitespace
        value = value.strip()
        # Remove trailing punctuation that might be noise
        value = value.rstrip(",;")
        # Normalize internal whitespace
        return " ".join(value.split())

    def _add_alias_warning(self, alias: str, canonical: str, location: ParseLocation) -> None:
        """Add warning about using an alias instead of canonical name."""
        self.warnings.append(
            ParseWarning(
                message=f"Field '{alias}' is an alias for '{canonical}'",
                location=location,
                suggestion=f"Consider using '{canonical}' for consistency",
                code="FIELD_ALIAS",
            )
        )


# =============================================================================
# Tolerant Section Extraction
# =============================================================================


class TolerantSectionExtractor:
    """
    Extract sections from markdown with tolerance for header level variations.

    Handles:
    - Different header levels (##, ###, ####)
    - Case-insensitive section names
    - Plural/singular variations
    """

    # Section name aliases
    SECTION_ALIASES: dict[str, list[str]] = {
        "Acceptance Criteria": ["AC", "Acceptance Criterion", "Criteria"],
        "Subtasks": ["Subtask", "Tasks", "Task List", "Sub Tasks"],
        "Description": ["User Story", "Story"],
        "Technical Notes": ["Tech Notes", "Notes", "Implementation Notes"],
        "Comments": ["Comment", "Discussion"],
        "Dependencies": ["Dependency", "Depends On", "Blocked By"],
        "Related Commits": ["Commits", "Git Commits"],
        "Links": ["Related Issues", "Related"],
    }

    def __init__(self, content: str, source: str | None = None):
        """
        Initialize extractor with content.

        Args:
            content: Markdown content to extract from
            source: Source file path for error reporting
        """
        self.content = content
        self.source = source
        self.warnings: list[ParseWarning] = []

    def extract_section(
        self,
        section_name: str,
        required: bool = False,
    ) -> tuple[str, ParseLocation | None]:
        """
        Extract a section's content with tolerance for variants.

        Args:
            section_name: Primary section name to look for
            required: Whether to add warning if not found

        Returns:
            Tuple of (content, location) where both are None if not found
        """
        variants = [section_name, *self.SECTION_ALIASES.get(section_name, [])]

        for variant in variants:
            pattern = TolerantPatterns.section_pattern(variant)
            match = pattern.search(self.content)
            if match:
                section_content = match.group(2).strip()
                location = location_from_match(self.content, match, self.source)
                if variant != section_name:
                    self._add_alias_warning(variant, section_name, location)
                return section_content, location

        if required:
            self.warnings.append(
                ParseWarning(
                    message=f"Missing section '{section_name}'",
                    location=ParseLocation(line=1, source=self.source),
                    suggestion=f"Add a section header: #### {section_name}",
                    code="MISSING_SECTION",
                )
            )

        return "", None

    def _add_alias_warning(self, alias: str, canonical: str, location: ParseLocation) -> None:
        """Add warning about using an alias instead of canonical name."""
        self.warnings.append(
            ParseWarning(
                message=f"Section '{alias}' is an alias for '{canonical}'",
                location=location,
                suggestion=f"Consider using '#### {canonical}' for consistency",
                code="SECTION_ALIAS",
            )
        )


# =============================================================================
# Tolerant Checkbox Parsing
# =============================================================================


def parse_checkboxes_tolerant(
    content: str,
    source: str | None = None,
) -> tuple[list[tuple[str, bool]], list[ParseWarning]]:
    """
    Parse checkboxes with tolerance for formatting variants.

    Handles:
    - [ ] and [x] and [X] (standard)
    - [] (empty, treated as unchecked)
    - -[ ] (no space after dash)
    - * [ ] (asterisk instead of dash)
    - + [ ] (plus instead of dash)

    Args:
        content: Content containing checkboxes
        source: Source file for error reporting

    Returns:
        Tuple of (items, warnings) where items is list of (text, checked) tuples
    """
    items: list[tuple[str, bool]] = []
    warnings: list[ParseWarning] = []

    # More lenient pattern for checkbox detection
    lenient_pattern = re.compile(r"^[\s]*[-*+]\s*\[([xX\s]?)\]\s*(.+?)$", re.MULTILINE)

    for match in lenient_pattern.finditer(content):
        checkbox_char = match.group(1).strip().lower()
        text = match.group(2).strip()
        checked = checkbox_char == "x"

        items.append((text, checked))

        # Warn about non-standard formatting
        full_match = match.group(0)
        if "* [" in full_match:
            location = location_from_match(content, match, source)
            warnings.append(
                ParseWarning(
                    message="Non-standard checkbox format (using * instead of -)",
                    location=location,
                    suggestion="Use '- [ ]' or '- [x]' for checkboxes",
                    code="NONSTANDARD_CHECKBOX",
                )
            )
        elif "[]" in full_match:
            location = location_from_match(content, match, source)
            warnings.append(
                ParseWarning(
                    message="Empty checkbox marker '[]', treating as unchecked",
                    location=location,
                    suggestion="Use '- [ ]' for unchecked items",
                    code="EMPTY_CHECKBOX",
                )
            )

    return items, warnings


# =============================================================================
# Inline Subtask Parsing (Checkboxes as Subtasks)
# =============================================================================


@dataclass
class InlineSubtaskInfo:
    """
    Information about a subtask parsed from an inline checkbox.

    Attributes:
        name: The subtask name/title
        checked: Whether the checkbox is checked
        description: Optional description extracted from the line
        line_number: Line number in the source document
        story_points: Estimated story points (default 1)
    """

    name: str
    checked: bool
    description: str = ""
    line_number: int = 0
    story_points: int = 1


def parse_inline_subtasks(
    content: str,
    source: str | None = None,
) -> tuple[list[InlineSubtaskInfo], list[ParseWarning]]:
    """
    Parse checkboxes as inline subtasks with tolerance for formatting variants.

    This function extracts subtask information from markdown checkbox lists.
    It supports various checkbox formats and extracts additional metadata
    when available (e.g., story points in parentheses).

    Supported formats:
    - [ ] Task name
    - [x] Completed task
    - [ ] Task name (2 SP)
    - [ ] Task name - description text
    - [ ] Task name: description text
    - [ ] **Task name** with bold formatting
    - [ ] `Task name` with code formatting

    Args:
        content: Content containing checkbox subtasks
        source: Source file for error reporting

    Returns:
        Tuple of (subtasks, warnings) where subtasks is list of InlineSubtaskInfo

    Examples:
        >>> content = '''
        ... - [ ] Implement feature
        ... - [x] Write tests (3 SP)
        ... - [ ] Update docs - Add API reference
        ... '''
        >>> subtasks, warnings = parse_inline_subtasks(content)
        >>> len(subtasks)
        3
        >>> subtasks[0].name
        'Implement feature'
        >>> subtasks[1].checked
        True
        >>> subtasks[1].story_points
        3
    """
    subtasks: list[InlineSubtaskInfo] = []
    warnings: list[ParseWarning] = []

    # Pattern for checkbox detection with optional metadata
    # Matches: - [ ] name, - [x] name, * [ ] name, + [ ] name
    checkbox_pattern = re.compile(
        r"^[\s]*[-*+]\s*\[([xX\s]?)\]\s*(.+?)$",
        re.MULTILINE,
    )

    # Pattern to extract story points from text like "(2 SP)" or "(3 points)"
    sp_pattern = re.compile(
        r"\s*\((\d+)\s*(?:SP|sp|pts?|points?|story\s*points?)\)\s*$",
        re.IGNORECASE,
    )

    # Pattern to extract description after separator (- or :)
    desc_pattern = re.compile(
        r"^(.+?)(?:\s*[-–—:]\s+(.+))?$",
    )

    for match in checkbox_pattern.finditer(content):
        checkbox_char = match.group(1).strip().lower()
        full_text = match.group(2).strip()
        checked = checkbox_char == "x"
        line_number = get_line_number(content, match.start())

        # Extract story points if present
        story_points = 1
        sp_match = sp_pattern.search(full_text)
        if sp_match:
            story_points = int(sp_match.group(1))
            full_text = full_text[: sp_match.start()].strip()

        # Remove markdown formatting (bold, code, etc.)
        name = full_text
        name = re.sub(r"\*\*(.+?)\*\*", r"\1", name)  # Remove bold
        name = re.sub(r"\*(.+?)\*", r"\1", name)  # Remove italic
        name = re.sub(r"`(.+?)`", r"\1", name)  # Remove code
        name = re.sub(r"~~(.+?)~~", r"\1", name)  # Remove strikethrough

        # Extract description if separator found
        description = ""
        desc_match = desc_pattern.match(name)
        if desc_match and desc_match.group(2):
            name = desc_match.group(1).strip()
            description = desc_match.group(2).strip()

        # Skip empty or very short names
        if len(name) < 2:
            location = location_from_match(content, match, source)
            warnings.append(
                ParseWarning(
                    message=f"Skipped checkbox with very short name: '{name}'",
                    location=location,
                    suggestion="Provide a descriptive subtask name",
                    code="SHORT_SUBTASK_NAME",
                )
            )
            continue

        subtasks.append(
            InlineSubtaskInfo(
                name=name,
                checked=checked,
                description=description,
                line_number=line_number,
                story_points=story_points,
            )
        )

        # Warn about non-standard formatting
        original = match.group(0)
        if "* [" in original or "+ [" in original:
            location = location_from_match(content, match, source)
            warnings.append(
                ParseWarning(
                    message="Non-standard checkbox format for subtask",
                    location=location,
                    suggestion="Use '- [ ]' or '- [x]' for subtask checkboxes",
                    code="NONSTANDARD_SUBTASK_CHECKBOX",
                )
            )

    return subtasks, warnings


# =============================================================================
# Tolerant Description Parsing
# =============================================================================


def parse_description_tolerant(
    content: str,
    source: str | None = None,
) -> tuple[dict[str, str] | None, list[ParseWarning]]:
    """
    Parse user story description with tolerance for formatting variants.

    Handles:
    - Multi-line with newlines between parts
    - Single-line comma-separated
    - Blockquote format
    - Missing commas/periods
    - Case variations in keywords

    Args:
        content: Content containing description
        source: Source file for error reporting

    Returns:
        Tuple of (description_dict, warnings) where dict has role/want/benefit keys
    """
    warnings: list[ParseWarning] = []

    # Try full multi-line pattern first
    match = TolerantPatterns.DESCRIPTION_FULL.search(content)
    if match:
        return {
            "role": _clean_description_part(match.group(1)),
            "want": _clean_description_part(match.group(2)),
            "benefit": _clean_description_part(match.group(3)),
        }, warnings

    # Try single-line pattern
    match = TolerantPatterns.DESCRIPTION_SINGLE_LINE.search(content)
    if match:
        return {
            "role": _clean_description_part(match.group(1)),
            "want": _clean_description_part(match.group(2)),
            "benefit": _clean_description_part(match.group(3)),
        }, warnings

    # Try very lenient pattern for blockquotes
    lenient_blockquote = re.compile(
        r">\s*\*\*As\s+a\*\*\s*([^,\n]+)"
        r"[\s\S]*?"
        r"\*\*I\s+want\*\*\s*([^,\n]+)"
        r"[\s\S]*?"
        r"\*\*So\s+that\*\*\s*([^.\n]+)",
        re.IGNORECASE,
    )
    match = lenient_blockquote.search(content)
    if match:
        return {
            "role": _clean_description_part(match.group(1)),
            "want": _clean_description_part(match.group(2)),
            "benefit": _clean_description_part(match.group(3)),
        }, warnings

    # Try partial matches with warnings
    partial_parts: dict[str, str] = {}

    # Look for individual parts
    as_a_match = re.search(r"\*\*As\s+a\*\*\s*([^,\n*]+)", content, re.IGNORECASE)
    if as_a_match:
        partial_parts["role"] = _clean_description_part(as_a_match.group(1))

    i_want_match = re.search(r"\*\*I\s+want\*\*\s*([^,\n*]+)", content, re.IGNORECASE)
    if i_want_match:
        partial_parts["want"] = _clean_description_part(i_want_match.group(1))

    so_that_match = re.search(r"\*\*So\s+that\*\*\s*([^,.\n*]+)", content, re.IGNORECASE)
    if so_that_match:
        partial_parts["benefit"] = _clean_description_part(so_that_match.group(1))

    if partial_parts:
        missing = [k for k in ["role", "want", "benefit"] if k not in partial_parts]
        if missing:
            warnings.append(
                ParseWarning(
                    message=f"Incomplete description: missing {', '.join(missing)}",
                    location=ParseLocation(line=1, source=source),
                    suggestion="Use format: **As a** [role] **I want** [feature] **So that** [benefit]",
                    code="INCOMPLETE_DESCRIPTION",
                )
            )
        return partial_parts, warnings

    return None, warnings


def _clean_description_part(text: str) -> str:
    """Clean a description part (role/want/benefit)."""
    # Remove trailing punctuation and whitespace
    text = text.strip().rstrip(",.")
    # Remove leading/trailing quotes
    text = text.strip("'\"")
    # Normalize whitespace
    return " ".join(text.split())


# =============================================================================
# Image Embedding - Extract and parse images from markdown
# =============================================================================


@dataclass
class EmbeddedImage:
    """
    Information about an image embedded in markdown content.

    Attributes:
        src: Image source (URL or local path)
        alt_text: Alternative text for the image
        title: Optional title attribute
        is_local: Whether the image is a local file (not URL)
        line_number: Line number in source document
        original_syntax: The original markdown syntax used
        width: Optional width specification (if provided)
        height: Optional height specification (if provided)
    """

    src: str
    alt_text: str = ""
    title: str = ""
    is_local: bool = False
    line_number: int = 0
    original_syntax: str = ""
    width: int | None = None
    height: int | None = None

    @property
    def filename(self) -> str:
        """Extract filename from the source path."""
        from pathlib import Path
        from urllib.parse import unquote, urlparse

        if self.is_local:
            return Path(self.src).name
        parsed = urlparse(self.src)
        return Path(unquote(parsed.path)).name or "image"

    @property
    def extension(self) -> str:
        """Get the file extension (lowercase, without dot)."""
        from pathlib import Path

        return Path(self.filename).suffix.lower().lstrip(".")

    @property
    def is_supported_format(self) -> bool:
        """Check if image is in a commonly supported format."""
        supported = {"png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico", "avif"}
        return self.extension in supported

    def to_markdown(self) -> str:
        """Convert back to markdown syntax."""
        if self.title:
            return f'![{self.alt_text}]({self.src} "{self.title}")'
        return f"![{self.alt_text}]({self.src})"

    def to_html(self) -> str:
        """Convert to HTML img tag."""
        parts = [f'<img src="{self.src}"']
        if self.alt_text:
            parts.append(f'alt="{self.alt_text}"')
        if self.title:
            parts.append(f'title="{self.title}"')
        if self.width:
            parts.append(f'width="{self.width}"')
        if self.height:
            parts.append(f'height="{self.height}"')
        parts.append("/>")
        return " ".join(parts)


def parse_embedded_images(
    content: str,
    source: str | None = None,
    include_remote: bool = True,
    include_local: bool = True,
) -> tuple[list[EmbeddedImage], list[ParseWarning]]:
    """
    Parse embedded images from markdown content.

    Supports multiple markdown image syntaxes:
    - Standard: ![alt](url)
    - With title: ![alt](url "title")
    - Reference style: ![alt][ref] with [ref]: url
    - HTML img tags: <img src="url" alt="alt">
    - Obsidian wikilinks: ![[image.png]] or ![[image.png|alt]]
    - With dimensions: ![alt](url =100x200) or ![alt](url){width=100}

    Args:
        content: Markdown content to parse
        source: Source file for error reporting
        include_remote: Include images with http/https URLs
        include_local: Include images with local file paths

    Returns:
        Tuple of (images, warnings) where images is list of EmbeddedImage

    Examples:
        >>> content = '''
        ... ![Logo](./images/logo.png)
        ... ![Banner](https://example.com/banner.jpg "Site Banner")
        ... ![[diagram.svg|Architecture Diagram]]
        ... '''
        >>> images, warnings = parse_embedded_images(content)
        >>> len(images)
        3
        >>> images[0].src
        './images/logo.png'
        >>> images[1].title
        'Site Banner'
    """
    images: list[EmbeddedImage] = []
    warnings: list[ParseWarning] = []
    seen_sources: set[str] = set()

    # Pattern 1: Standard markdown images ![alt](src) or ![alt](src "title")
    standard_pattern = re.compile(
        r"!\[([^\]]*)\]"  # ![alt text]
        r"\("  # Opening paren
        r'([^)\s"]+)'  # src (no spaces, quotes, or closing paren)
        r'(?:\s+"([^"]*)")?'  # Optional "title"
        r"(?:\s+=(\d+)?x(\d+)?)?"  # Optional =widthxheight
        r"\)",  # Closing paren
        re.MULTILINE,
    )

    for match in standard_pattern.finditer(content):
        alt_text = match.group(1).strip()
        src = match.group(2).strip()
        title = match.group(3) or ""
        width_str = match.group(4)
        height_str = match.group(5)

        if src in seen_sources:
            continue

        is_local = _is_local_path(src)
        if (is_local and not include_local) or (not is_local and not include_remote):
            continue

        seen_sources.add(src)
        images.append(
            EmbeddedImage(
                src=src,
                alt_text=alt_text,
                title=title,
                is_local=is_local,
                line_number=get_line_number(content, match.start()),
                original_syntax=match.group(0),
                width=int(width_str) if width_str else None,
                height=int(height_str) if height_str else None,
            )
        )

    # Pattern 2: Obsidian wikilink images ![[file]] or ![[file|alt]]
    wikilink_pattern = re.compile(
        r"!\[\["  # ![[
        r"([^\]|]+)"  # filename
        r"(?:\|([^\]]+))?"  # Optional |alt text
        r"\]\]",  # ]]
        re.MULTILINE,
    )

    for match in wikilink_pattern.finditer(content):
        src = match.group(1).strip()
        alt_text = match.group(2).strip() if match.group(2) else ""

        if src in seen_sources:
            continue

        # Wikilinks are always local
        if not include_local:
            continue

        seen_sources.add(src)
        images.append(
            EmbeddedImage(
                src=src,
                alt_text=alt_text or src,
                title="",
                is_local=True,
                line_number=get_line_number(content, match.start()),
                original_syntax=match.group(0),
            )
        )

        # Warn about non-standard syntax
        warnings.append(
            ParseWarning(
                message=f"Obsidian-style wikilink image: {src}",
                location=ParseLocation(line=get_line_number(content, match.start()), source=source),
                suggestion="Standard markdown: ![alt](path) may be more portable",
                code="WIKILINK_IMAGE",
            )
        )

    # Pattern 3: HTML img tags
    html_pattern = re.compile(
        r"<img\s+"  # <img followed by whitespace
        r"[^>]*"  # Any attributes
        r'src=["\']([^"\']+)["\']'  # src attribute
        r"[^>]*"  # More attributes
        r"/?>",  # Closing
        re.IGNORECASE | re.MULTILINE,
    )

    alt_in_html = re.compile(r'alt=["\']([^"\']*)["\']', re.IGNORECASE)
    title_in_html = re.compile(r'title=["\']([^"\']*)["\']', re.IGNORECASE)
    width_in_html = re.compile(r'width=["\']?(\d+)["\']?', re.IGNORECASE)
    height_in_html = re.compile(r'height=["\']?(\d+)["\']?', re.IGNORECASE)

    for match in html_pattern.finditer(content):
        src = match.group(1).strip()
        full_tag = match.group(0)

        if src in seen_sources:
            continue

        is_local = _is_local_path(src)
        if (is_local and not include_local) or (not is_local and not include_remote):
            continue

        # Extract other attributes
        alt_match = alt_in_html.search(full_tag)
        title_match = title_in_html.search(full_tag)
        width_match = width_in_html.search(full_tag)
        height_match = height_in_html.search(full_tag)

        seen_sources.add(src)
        images.append(
            EmbeddedImage(
                src=src,
                alt_text=alt_match.group(1) if alt_match else "",
                title=title_match.group(1) if title_match else "",
                is_local=is_local,
                line_number=get_line_number(content, match.start()),
                original_syntax=full_tag,
                width=int(width_match.group(1)) if width_match else None,
                height=int(height_match.group(1)) if height_match else None,
            )
        )

        # Warn about HTML in markdown
        warnings.append(
            ParseWarning(
                message="HTML img tag found in markdown",
                location=ParseLocation(line=get_line_number(content, match.start()), source=source),
                suggestion="Consider using markdown syntax: ![alt](src)",
                code="HTML_IMAGE_TAG",
            )
        )

    # Pattern 4: Reference-style images ![alt][ref] with [ref]: url
    # First, collect all reference definitions
    ref_definitions: dict[str, tuple[str, str]] = {}
    ref_def_pattern = re.compile(
        r"^\[([^\]]+)\]:\s*"  # [ref]:
        r"(\S+)"  # url
        r'(?:\s+"([^"]*)")?',  # Optional "title"
        re.MULTILINE,
    )

    for match in ref_def_pattern.finditer(content):
        ref_id = match.group(1).lower()
        url = match.group(2)
        title = match.group(3) or ""
        ref_definitions[ref_id] = (url, title)

    # Now find reference-style images
    ref_image_pattern = re.compile(
        r"!\[([^\]]*)\]"  # ![alt]
        r"\[([^\]]*)\]",  # [ref]
        re.MULTILINE,
    )

    for match in ref_image_pattern.finditer(content):
        alt_text = match.group(1).strip()
        ref_id = match.group(2).strip().lower() or alt_text.lower()

        if ref_id not in ref_definitions:
            # Reference not found - this might be a broken reference
            warnings.append(
                ParseWarning(
                    message=f"Image reference not found: [{ref_id}]",
                    location=ParseLocation(
                        line=get_line_number(content, match.start()), source=source
                    ),
                    suggestion=f"Add a reference definition: [{ref_id}]: image-url",
                    code="MISSING_IMAGE_REFERENCE",
                )
            )
            continue

        src, title = ref_definitions[ref_id]
        if src in seen_sources:
            continue

        is_local = _is_local_path(src)
        if (is_local and not include_local) or (not is_local and not include_remote):
            continue

        seen_sources.add(src)
        images.append(
            EmbeddedImage(
                src=src,
                alt_text=alt_text,
                title=title,
                is_local=is_local,
                line_number=get_line_number(content, match.start()),
                original_syntax=match.group(0),
            )
        )

    # Validate images and add warnings for potential issues
    for img in images:
        # Warn about missing alt text (accessibility)
        if not img.alt_text:
            warnings.append(
                ParseWarning(
                    message=f"Image missing alt text: {img.src}",
                    location=ParseLocation(line=img.line_number, source=source),
                    suggestion="Add descriptive alt text for accessibility",
                    code="MISSING_ALT_TEXT",
                )
            )

        # Warn about unsupported formats
        if not img.is_supported_format and img.extension:
            warnings.append(
                ParseWarning(
                    message=f"Potentially unsupported image format: .{img.extension}",
                    location=ParseLocation(line=img.line_number, source=source),
                    suggestion="Common formats: png, jpg, gif, svg, webp",
                    code="UNSUPPORTED_IMAGE_FORMAT",
                )
            )

    return images, warnings


def _is_local_path(path: str) -> bool:
    """Check if a path is local (not a URL)."""
    return not path.startswith(("http://", "https://", "ftp://", "data:", "//"))


def extract_images_from_section(
    content: str,
    section_name: str,
    source: str | None = None,
) -> tuple[list[EmbeddedImage], list[ParseWarning]]:
    """
    Extract images from a specific markdown section.

    Args:
        content: Full markdown content
        section_name: Name of section to extract from (e.g., "Description", "Technical Notes")
        source: Source file for error reporting

    Returns:
        Tuple of (images, warnings) for images found in the section
    """
    # Build pattern parts - avoid f-string issues with braces
    section_start = r"#{2,4}\s*" + re.escape(section_name) + r"\s*\n"
    section_body = r"([\s\S]*?)"
    section_end = r"(?=\n#{2,4}|\Z)"

    section_pattern = re.compile(
        section_start + section_body + section_end,
        re.IGNORECASE,
    )

    match = section_pattern.search(content)
    if not match:
        return [], []

    section_content = match.group(1)
    return parse_embedded_images(section_content, source)


# =============================================================================
# Table Parsing - Extract and parse markdown tables from content
# =============================================================================


class TableAlignment(Enum):
    """Column alignment in markdown tables."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    NONE = "none"


@dataclass
class TableCell:
    """
    A single cell in a markdown table.

    Attributes:
        content: Raw cell content
        cleaned: Content with markdown formatting removed
        row: Row index (0-indexed, excluding header)
        column: Column index (0-indexed)
        is_header: Whether this is a header cell
        alignment: Column alignment
        colspan: Column span (1 for normal cells)
        original_text: Original text before cleaning
    """

    content: str
    cleaned: str = ""
    row: int = 0
    column: int = 0
    is_header: bool = False
    alignment: TableAlignment = TableAlignment.NONE
    colspan: int = 1
    original_text: str = ""

    def __post_init__(self) -> None:
        """Clean content after initialization."""
        if not self.cleaned:
            self.cleaned = self._clean_content(self.content)
        if not self.original_text:
            self.original_text = self.content

    @staticmethod
    def _clean_content(content: str) -> str:
        """Remove markdown formatting from cell content."""
        text = content.strip()
        # Remove bold
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        # Remove italic
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)
        # Remove code
        text = re.sub(r"`(.+?)`", r"\1", text)
        # Remove links, keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text)
        return text.strip()

    @property
    def is_empty(self) -> bool:
        """Check if cell is empty or whitespace only."""
        return not self.cleaned or self.cleaned.isspace()

    @property
    def as_int(self) -> int | None:
        """Try to parse cell as integer."""
        cleaned = re.sub(r"[^\d-]", "", self.cleaned)
        try:
            return int(cleaned) if cleaned else None
        except ValueError:
            return None

    @property
    def as_float(self) -> float | None:
        """Try to parse cell as float."""
        cleaned = re.sub(r"[^\d.-]", "", self.cleaned)
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    @property
    def as_bool(self) -> bool | None:
        """Try to parse cell as boolean."""
        lower = self.cleaned.lower()
        if lower in ("yes", "true", "1", "✓", "✔", "x", "done"):
            return True
        if lower in ("no", "false", "0", "", "-", "n/a"):
            return False
        return None


@dataclass
class ParsedTable:
    """
    A parsed markdown table with headers and data rows.

    Attributes:
        headers: List of header cell contents
        rows: List of data rows, each row is a list of TableCell
        alignments: Column alignments from separator row
        line_number: Starting line number in source
        source: Source file path
        raw_content: Original table markdown
    """

    headers: list[str]
    rows: list[list[TableCell]]
    alignments: list[TableAlignment] = field(default_factory=list)
    line_number: int = 0
    source: str | None = None
    raw_content: str = ""

    @property
    def column_count(self) -> int:
        """Get the number of columns."""
        return len(self.headers)

    @property
    def row_count(self) -> int:
        """Get the number of data rows (excluding header)."""
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        """Check if table has no data rows."""
        return len(self.rows) == 0

    def get_column(self, index: int) -> list[TableCell]:
        """Get all cells in a column by index."""
        if index < 0 or index >= self.column_count:
            return []
        return [row[index] for row in self.rows if index < len(row)]

    def get_column_by_header(self, header: str) -> list[TableCell]:
        """Get all cells in a column by header name (case-insensitive)."""
        header_lower = header.lower().strip()
        for i, h in enumerate(self.headers):
            if h.lower().strip() == header_lower:
                return self.get_column(i)
        return []

    def get_row(self, index: int) -> list[TableCell]:
        """Get a row by index."""
        if index < 0 or index >= len(self.rows):
            return []
        return self.rows[index]

    def to_dicts(self) -> list[dict[str, str]]:
        """Convert table to list of dictionaries (header -> value)."""
        result = []
        for row in self.rows:
            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(self.headers):
                    header = self.headers[i].lower().strip()
                    row_dict[header] = cell.cleaned
            if any(row_dict.values()):
                result.append(row_dict)
        return result

    def find_column_index(self, *names: str) -> int | None:
        """Find column index by any of the given names (case-insensitive)."""
        names_lower = {n.lower().strip() for n in names}
        for i, h in enumerate(self.headers):
            if h.lower().strip() in names_lower:
                return i
        return None

    def get_cell(self, row: int, column: int | str) -> TableCell | None:
        """Get a specific cell by row index and column index or name."""
        if row < 0 or row >= len(self.rows):
            return None

        if isinstance(column, str):
            col_idx = self.find_column_index(column)
            if col_idx is None:
                return None
            column = col_idx

        if column < 0 or column >= len(self.rows[row]):
            return None

        return self.rows[row][column]


def parse_markdown_table(
    content: str,
    source: str | None = None,
    start_line: int = 1,
) -> tuple[ParsedTable | None, list[ParseWarning]]:
    """
    Parse a markdown table from content.

    Supports:
    - Standard GFM tables with pipe delimiters
    - Column alignment (:---, :---:, ---:)
    - Cells with markdown formatting (bold, italic, code, links)
    - Compact format without leading/trailing pipes
    - Multi-line cells (escaped newlines)

    Args:
        content: Markdown content containing a table
        source: Source file for error reporting
        start_line: Line number offset for error reporting

    Returns:
        Tuple of (ParsedTable or None, list of warnings)

    Examples:
        >>> content = '''
        ... | Name | Status | Points |
        ... |:-----|:------:|-------:|
        ... | Task 1 | Done | 5 |
        ... | Task 2 | Todo | 3 |
        ... '''
        >>> table, warnings = parse_markdown_table(content)
        >>> table.headers
        ['Name', 'Status', 'Points']
        >>> table.row_count
        2
    """
    warnings: list[ParseWarning] = []
    lines = content.strip().split("\n")

    if len(lines) < 2:
        return None, warnings

    # Find table start (first line with |)
    table_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") or ("|" in stripped and _looks_like_table_row(stripped)):
            table_start = i
            break

    if table_start == -1:
        return None, warnings

    # Parse header row
    header_line = lines[table_start].strip()
    headers = _parse_table_row(header_line)

    if not headers or len(headers) < 1:
        return None, warnings

    # Parse separator row (if present)
    alignments: list[TableAlignment] = []
    data_start = table_start + 1

    if data_start < len(lines):
        separator_line = lines[data_start].strip()
        if _is_separator_row(separator_line):
            alignments = _parse_alignments(separator_line)
            data_start += 1

    # Ensure alignments match header count
    while len(alignments) < len(headers):
        alignments.append(TableAlignment.NONE)

    # Parse data rows
    rows: list[list[TableCell]] = []
    row_lines = []

    for i in range(data_start, len(lines)):
        line = lines[i].strip()

        # Stop at empty line or non-table content
        if not line or (not line.startswith("|") and "|" not in line):
            break

        # Skip additional separator rows
        if _is_separator_row(line):
            continue

        row_lines.append((i, line))

    # Parse each data row
    for row_idx, (line_idx, line) in enumerate(row_lines):
        cells_content = _parse_table_row(line)
        cells: list[TableCell] = []

        for col_idx, cell_content in enumerate(cells_content):
            alignment = alignments[col_idx] if col_idx < len(alignments) else TableAlignment.NONE
            cells.append(
                TableCell(
                    content=cell_content,
                    row=row_idx,
                    column=col_idx,
                    is_header=False,
                    alignment=alignment,
                )
            )

        # Warn about column count mismatch
        if len(cells) != len(headers):
            warnings.append(
                ParseWarning(
                    message=f"Row has {len(cells)} columns, expected {len(headers)}",
                    location=ParseLocation(line=start_line + line_idx, source=source),
                    suggestion="Ensure all rows have the same number of columns",
                    code="TABLE_COLUMN_MISMATCH",
                )
            )

        # Pad or trim to match header count
        while len(cells) < len(headers):
            cells.append(
                TableCell(
                    content="",
                    row=row_idx,
                    column=len(cells),
                    alignment=alignments[len(cells)]
                    if len(cells) < len(alignments)
                    else TableAlignment.NONE,
                )
            )
        cells = cells[: len(headers)]

        rows.append(cells)

    if not rows and not headers:
        return None, warnings

    # Build raw content for reference
    table_lines = lines[table_start : data_start + len(rows)]
    raw_content = "\n".join(table_lines)

    return ParsedTable(
        headers=[h.strip() for h in headers],
        rows=rows,
        alignments=alignments[: len(headers)],
        line_number=start_line + table_start,
        source=source,
        raw_content=raw_content,
    ), warnings


def _looks_like_table_row(line: str) -> bool:
    """Check if a line looks like a table row."""
    # Must have at least one pipe that's not at the start/end only
    pipe_count = line.count("|")
    if pipe_count < 1:
        return False
    # Should have multiple cells or pipe-delimited content
    return pipe_count >= 2 or ("|" in line and line.strip() not in ("|", "||"))


def _parse_table_row(line: str) -> list[str]:
    """Parse a table row into cell contents."""
    line = line.strip()

    # Remove leading/trailing pipes
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]

    # Split by pipe, handling escaped pipes
    cells = []
    current = ""
    i = 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            # Escaped pipe
            current += "|"
            i += 2
        elif line[i] == "|":
            cells.append(current.strip())
            current = ""
            i += 1
        else:
            current += line[i]
            i += 1

    # Don't forget the last cell
    if current or cells:
        cells.append(current.strip())

    return cells


def _is_separator_row(line: str) -> bool:
    """Check if a line is a table separator row."""
    line = line.strip()
    if not line:
        return False

    # Remove leading/trailing pipes
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]

    # Split by pipe
    cells = line.split("|")

    # Each cell should be mostly dashes with optional colons
    for cell in cells:
        cell = cell.strip()
        if not cell:
            continue
        # Remove alignment indicators
        cell = cell.strip(":")
        # Should be only dashes
        if not cell or not all(c == "-" for c in cell):
            return False

    return True


def _parse_alignments(separator_line: str) -> list[TableAlignment]:
    """Parse column alignments from separator row."""
    alignments = []

    line = separator_line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]

    for cell in line.split("|"):
        cell = cell.strip()
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append(TableAlignment.CENTER)
        elif cell.endswith(":"):
            alignments.append(TableAlignment.RIGHT)
        elif cell.startswith(":"):
            alignments.append(TableAlignment.LEFT)
        else:
            alignments.append(TableAlignment.NONE)

    return alignments


def extract_tables_from_content(
    content: str,
    source: str | None = None,
) -> tuple[list[ParsedTable], list[ParseWarning]]:
    """
    Extract all markdown tables from content.

    Args:
        content: Markdown content potentially containing multiple tables
        source: Source file for error reporting

    Returns:
        Tuple of (list of ParsedTable, list of warnings)

    Examples:
        >>> content = '''
        ... # Section 1
        ...
        ... | A | B |
        ... |---|---|
        ... | 1 | 2 |
        ...
        ... # Section 2
        ...
        ... | X | Y |
        ... |---|---|
        ... | a | b |
        ... '''
        >>> tables, warnings = extract_tables_from_content(content)
        >>> len(tables)
        2
    """
    tables: list[ParsedTable] = []
    all_warnings: list[ParseWarning] = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for table start
        if line.startswith("|") or (_looks_like_table_row(line) and "|" in line):
            # Find table extent
            table_start = i
            table_end = i + 1

            while table_end < len(lines):
                next_line = lines[table_end].strip()
                if not next_line or (not next_line.startswith("|") and "|" not in next_line):
                    break
                if next_line.startswith("#"):
                    break
                table_end += 1

            # Parse this table
            table_content = "\n".join(lines[table_start:table_end])
            table, warnings = parse_markdown_table(
                table_content,
                source=source,
                start_line=table_start + 1,
            )

            if table:
                tables.append(table)
            all_warnings.extend(warnings)

            i = table_end
        else:
            i += 1

    return tables, all_warnings


def extract_table_from_section(
    content: str,
    section_name: str,
    source: str | None = None,
) -> tuple[ParsedTable | None, list[ParseWarning]]:
    """
    Extract a table from a specific markdown section.

    Args:
        content: Full markdown content
        section_name: Name of section to extract from (e.g., "Subtasks", "Metadata")
        source: Source file for error reporting

    Returns:
        Tuple of (ParsedTable or None, list of warnings)
    """
    # Build pattern parts - avoid f-string issues with braces
    section_start = r"#{2,4}\s*" + re.escape(section_name) + r"\s*\n"
    section_body = r"([\s\S]*?)"
    section_end = r"(?=\n#{2,4}|\Z)"

    section_pattern = re.compile(
        section_start + section_body + section_end,
        re.IGNORECASE,
    )

    match = section_pattern.search(content)
    if not match:
        return None, []

    section_content = match.group(1)
    section_line = get_line_number(content, match.start())

    return parse_markdown_table(section_content, source=source, start_line=section_line)


def table_to_markdown(
    table: ParsedTable,
    alignment: bool = True,
    padding: int = 1,
) -> str:
    """
    Convert a ParsedTable back to markdown format.

    Args:
        table: ParsedTable to convert
        alignment: Include alignment indicators in separator
        padding: Minimum padding around cell content

    Returns:
        Markdown table string
    """
    if not table.headers:
        return ""

    # Calculate column widths
    widths = [len(h) for h in table.headers]
    for row in table.rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell.cleaned))

    # Add minimum padding
    widths = [w + padding * 2 for w in widths]

    lines = []

    # Header row
    header_cells = []
    for i, h in enumerate(table.headers):
        width = widths[i] if i < len(widths) else len(h) + padding * 2
        header_cells.append(h.center(width))
    lines.append("| " + " | ".join(header_cells) + " |")

    # Separator row
    sep_cells = []
    for i, width in enumerate(widths):
        align = table.alignments[i] if i < len(table.alignments) else TableAlignment.NONE
        if alignment:
            if align == TableAlignment.CENTER:
                sep_cells.append(":" + "-" * (width - 2) + ":")
            elif align == TableAlignment.RIGHT:
                sep_cells.append("-" * (width - 1) + ":")
            elif align == TableAlignment.LEFT:
                sep_cells.append(":" + "-" * (width - 1))
            else:
                sep_cells.append("-" * width)
        else:
            sep_cells.append("-" * width)
    lines.append("|" + "|".join(sep_cells) + "|")

    # Data rows
    for row in table.rows:
        row_cells = []
        for i, cell in enumerate(row):
            width = widths[i] if i < len(widths) else len(cell.cleaned) + padding * 2
            align = table.alignments[i] if i < len(table.alignments) else TableAlignment.NONE

            if align == TableAlignment.CENTER:
                row_cells.append(cell.cleaned.center(width))
            elif align == TableAlignment.RIGHT:
                row_cells.append(cell.cleaned.rjust(width))
            else:
                row_cells.append(cell.cleaned.ljust(width))

        lines.append("| " + " | ".join(row_cells) + " |")

    return "\n".join(lines)


# =============================================================================
# Code Block Parsing - Preserve syntax highlighting in fenced code blocks
# =============================================================================


class CodeBlockType(Enum):
    """Type of code block."""

    FENCED_BACKTICK = "fenced_backtick"  # ```language
    FENCED_TILDE = "fenced_tilde"  # ~~~language
    INDENTED = "indented"  # 4-space indent
    INLINE = "inline"  # `code`


@dataclass
class CodeBlock:
    """
    A parsed code block with language and content.

    Attributes:
        content: The code content (without fencing)
        language: Programming language identifier (e.g., 'python', 'javascript')
        block_type: Type of code block (fenced, indented, inline)
        raw_content: Original markdown including fencing
        line_number: Starting line number in source
        end_line: Ending line number in source
        fence_char: The fence character used ('`' or '~')
        fence_count: Number of fence characters (typically 3+)
        info_string: Full info string after fence (language + attributes)
        source: Source file path
    """

    content: str
    language: str = ""
    block_type: CodeBlockType = CodeBlockType.FENCED_BACKTICK
    raw_content: str = ""
    line_number: int = 0
    end_line: int = 0
    fence_char: str = "`"
    fence_count: int = 3
    info_string: str = ""
    source: str | None = None

    @property
    def has_language(self) -> bool:
        """Check if code block has a language specified."""
        return bool(self.language and self.language.strip())

    @property
    def is_fenced(self) -> bool:
        """Check if this is a fenced code block."""
        return self.block_type in (CodeBlockType.FENCED_BACKTICK, CodeBlockType.FENCED_TILDE)

    @property
    def is_inline(self) -> bool:
        """Check if this is an inline code span."""
        return self.block_type == CodeBlockType.INLINE

    @property
    def line_count(self) -> int:
        """Get number of lines in the code content."""
        return len(self.content.split("\n"))

    @property
    def normalized_language(self) -> str:
        """
        Get normalized language identifier.

        Common aliases are normalized:
        - js -> javascript
        - ts -> typescript
        - py -> python
        - rb -> ruby
        - sh, bash, zsh -> shell
        - yml -> yaml
        - md -> markdown
        """
        lang = self.language.lower().strip()
        aliases = {
            "js": "javascript",
            "ts": "typescript",
            "py": "python",
            "rb": "ruby",
            "sh": "shell",
            "bash": "shell",
            "zsh": "shell",
            "yml": "yaml",
            "md": "markdown",
            "c++": "cpp",
            "c#": "csharp",
            "f#": "fsharp",
            "objective-c": "objc",
            "dockerfile": "docker",
        }
        return aliases.get(lang, lang)

    def to_markdown(self, fence_char: str | None = None, fence_count: int | None = None) -> str:
        """
        Convert code block back to markdown.

        Args:
            fence_char: Override fence character (default: original)
            fence_count: Override fence count (default: original)

        Returns:
            Markdown-formatted code block
        """
        if self.is_inline:
            return f"`{self.content}`"

        if self.block_type == CodeBlockType.INDENTED:
            # Indented code blocks use 4-space prefix
            lines = self.content.split("\n")
            return "\n".join("    " + line for line in lines)

        # Fenced code blocks
        char = fence_char or self.fence_char
        count = fence_count or max(self.fence_count, 3)
        fence = char * count

        info = self.info_string if self.info_string else self.language
        if info:
            return f"{fence}{info}\n{self.content}\n{fence}"
        return f"{fence}\n{self.content}\n{fence}"


@dataclass
class CodeBlockCollection:
    """
    Collection of code blocks extracted from content.

    Attributes:
        blocks: List of extracted code blocks
        warnings: Any warnings during extraction
        source: Source file path
    """

    blocks: list[CodeBlock] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    source: str | None = None

    @property
    def count(self) -> int:
        """Get total number of code blocks."""
        return len(self.blocks)

    @property
    def fenced_count(self) -> int:
        """Get count of fenced code blocks."""
        return sum(1 for b in self.blocks if b.is_fenced)

    @property
    def languages(self) -> list[str]:
        """Get list of unique languages used."""
        seen = set()
        result = []
        for block in self.blocks:
            lang = block.normalized_language
            if lang and lang not in seen:
                seen.add(lang)
                result.append(lang)
        return result

    def by_language(self, language: str) -> list[CodeBlock]:
        """Get all code blocks with a specific language."""
        lang_lower = language.lower().strip()
        return [
            b
            for b in self.blocks
            if b.language.lower().strip() == lang_lower or b.normalized_language == lang_lower
        ]

    def get_block(self, index: int) -> CodeBlock | None:
        """Get code block by index."""
        if 0 <= index < len(self.blocks):
            return self.blocks[index]
        return None


# Patterns for code block detection
_FENCED_CODE_PATTERN = re.compile(
    r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>[^\n`]*)\n"
    r"(?P<content>.*?)"
    r"(?:\n(?P=indent))?(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

_INDENTED_CODE_PATTERN = re.compile(
    r"(?:^|\n\n)((?:(?:^|\n)[ ]{4}[^\n]*)+)",
    re.MULTILINE,
)

_INLINE_CODE_PATTERN = re.compile(
    r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)",
    re.DOTALL,
)


def parse_code_blocks(
    content: str,
    source: str | None = None,
    include_inline: bool = False,
    include_indented: bool = True,
) -> tuple[CodeBlockCollection, list[ParseWarning]]:
    """
    Parse all code blocks from markdown content.

    Supports:
    - Fenced code blocks with backticks (```) or tildes (~~~)
    - Language identifiers and info strings
    - Indented code blocks (4 spaces)
    - Inline code spans (optional)
    - Nested fence handling (more fence chars than inner)

    Args:
        content: Markdown content to parse
        source: Source file for error reporting
        include_inline: Include inline `code` spans
        include_indented: Include indented (4-space) code blocks

    Returns:
        Tuple of (CodeBlockCollection, list of warnings)

    Examples:
        >>> content = '''
        ... ```python
        ... def hello():
        ...     print("Hello!")
        ... ```
        ... '''
        >>> collection, warnings = parse_code_blocks(content)
        >>> collection.count
        1
        >>> collection.blocks[0].language
        'python'
    """
    warnings: list[ParseWarning] = []
    blocks: list[CodeBlock] = []

    if not content or not content.strip():
        return CodeBlockCollection(blocks=[], source=source), warnings

    # Track positions that are already part of a code block
    used_ranges: list[tuple[int, int]] = []

    def is_in_used_range(start: int, end: int) -> bool:
        """Check if a range overlaps with already-used ranges."""
        return any(start < used_end and end > used_start for used_start, used_end in used_ranges)

    # Parse fenced code blocks first (highest priority)
    for match in _FENCED_CODE_PATTERN.finditer(content):
        start = match.start()
        end = match.end()

        if is_in_used_range(start, end):
            continue

        fence = match.group("fence")
        fence_char = fence[0]
        fence_count = len(fence)
        info_string = match.group("info").strip()
        code_content = match.group("content")

        # Extract language from info string (first word)
        language = info_string.split()[0] if info_string else ""

        line_number = get_line_number(content, start)
        end_line = get_line_number(content, end)

        block_type = (
            CodeBlockType.FENCED_BACKTICK if fence_char == "`" else CodeBlockType.FENCED_TILDE
        )

        blocks.append(
            CodeBlock(
                content=code_content,
                language=language,
                block_type=block_type,
                raw_content=match.group(0),
                line_number=line_number,
                end_line=end_line,
                fence_char=fence_char,
                fence_count=fence_count,
                info_string=info_string,
                source=source,
            )
        )
        used_ranges.append((start, end))

        # Warn about missing language identifier
        if not language:
            warnings.append(
                ParseWarning(
                    message="Code block without language identifier",
                    location=ParseLocation(line=line_number, source=source),
                    suggestion="Add a language identifier after the fence (e.g., ```python)",
                    code="CODE_BLOCK_NO_LANGUAGE",
                )
            )

    # Parse indented code blocks (if enabled)
    if include_indented:
        for match in _INDENTED_CODE_PATTERN.finditer(content):
            start = match.start()
            end = match.end()

            if is_in_used_range(start, end):
                continue

            raw_content = match.group(1)
            # Remove 4-space indent from each line
            lines = raw_content.split("\n")
            code_lines = []
            for line in lines:
                if line.startswith("    "):
                    code_lines.append(line[4:])
                elif line.strip() == "":
                    code_lines.append("")
                else:
                    code_lines.append(line)

            code_content = "\n".join(code_lines).strip()

            if code_content:
                line_number = get_line_number(content, start)
                end_line = get_line_number(content, end)

                blocks.append(
                    CodeBlock(
                        content=code_content,
                        language="",
                        block_type=CodeBlockType.INDENTED,
                        raw_content=raw_content,
                        line_number=line_number,
                        end_line=end_line,
                        fence_char="",
                        fence_count=0,
                        info_string="",
                        source=source,
                    )
                )
                used_ranges.append((start, end))

    # Parse inline code spans (if enabled)
    if include_inline:
        for match in _INLINE_CODE_PATTERN.finditer(content):
            start = match.start()
            end = match.end()

            if is_in_used_range(start, end):
                continue

            code_content = match.group(2).strip()
            line_number = get_line_number(content, start)

            blocks.append(
                CodeBlock(
                    content=code_content,
                    language="",
                    block_type=CodeBlockType.INLINE,
                    raw_content=match.group(0),
                    line_number=line_number,
                    end_line=line_number,
                    fence_char="`",
                    fence_count=len(match.group(1)),
                    info_string="",
                    source=source,
                )
            )
            used_ranges.append((start, end))

    # Sort blocks by line number
    blocks.sort(key=lambda b: b.line_number)

    return CodeBlockCollection(blocks=blocks, warnings=warnings, source=source), warnings


def extract_code_blocks_from_content(
    content: str,
    source: str | None = None,
    language_filter: str | None = None,
) -> tuple[list[CodeBlock], list[ParseWarning]]:
    """
    Extract all fenced code blocks from content.

    Args:
        content: Markdown content to parse
        source: Source file for error reporting
        language_filter: Only return blocks with this language

    Returns:
        Tuple of (list of CodeBlocks, list of warnings)
    """
    collection, warnings = parse_code_blocks(
        content,
        source=source,
        include_inline=False,
        include_indented=False,
    )

    blocks = collection.by_language(language_filter) if language_filter else collection.blocks

    return blocks, warnings


def extract_code_from_section(
    content: str,
    section_name: str,
    language: str | None = None,
    source: str | None = None,
) -> tuple[CodeBlock | None, list[ParseWarning]]:
    """
    Extract first code block from a named section.

    Args:
        content: Full markdown content
        section_name: Name of section to search (case-insensitive)
        language: Optional language filter
        source: Source file for error reporting

    Returns:
        Tuple of (CodeBlock or None, list of warnings)

    Examples:
        >>> content = '''
        ... ## Examples
        ...
        ... ```python
        ... print("hello")
        ... ```
        ... '''
        >>> block, warnings = extract_code_from_section(content, "Examples")
        >>> block.content
        'print("hello")'
    """
    warnings: list[ParseWarning] = []

    # Find section content
    section_pattern = re.compile(
        rf"^#+\s*{re.escape(section_name)}\s*$\n(.*?)(?=\n#|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    match = section_pattern.search(content)
    if not match:
        return None, warnings

    section_content = match.group(1)
    section_line = get_line_number(content, match.start())

    blocks, block_warnings = extract_code_blocks_from_content(
        section_content,
        source=source,
    )
    warnings.extend(block_warnings)

    # Adjust line numbers relative to section start
    for block in blocks:
        block = CodeBlock(
            content=block.content,
            language=block.language,
            block_type=block.block_type,
            raw_content=block.raw_content,
            line_number=block.line_number + section_line - 1,
            end_line=block.end_line + section_line - 1,
            fence_char=block.fence_char,
            fence_count=block.fence_count,
            info_string=block.info_string,
            source=source,
        )

    if language:
        blocks = [
            b
            for b in blocks
            if b.language.lower() == language.lower() or b.normalized_language == language.lower()
        ]

    return blocks[0] if blocks else None, warnings


def preserve_code_blocks(
    content: str,
    placeholder_prefix: str = "___CODE_BLOCK_",
) -> tuple[str, dict[str, CodeBlock]]:
    """
    Replace code blocks with placeholders for safe text processing.

    This is useful when you need to process markdown content but want
    to preserve code blocks exactly as they are (e.g., during formatting
    or transformation operations).

    Args:
        content: Markdown content with code blocks
        placeholder_prefix: Prefix for placeholder strings

    Returns:
        Tuple of (content with placeholders, mapping of placeholder -> CodeBlock)

    Examples:
        >>> content = '''
        ... Some text
        ... ```python
        ... code here
        ... ```
        ... More text
        ... '''
        >>> processed, mapping = preserve_code_blocks(content)
        >>> '___CODE_BLOCK_' in processed
        True
    """
    mapping: dict[str, CodeBlock] = {}
    result = content

    collection, _ = parse_code_blocks(content, include_inline=False, include_indented=True)

    # Process blocks in reverse order to maintain correct positions
    sorted_blocks = sorted(collection.blocks, key=lambda b: b.line_number, reverse=True)

    for i, block in enumerate(sorted_blocks):
        placeholder = f"{placeholder_prefix}{i}___"
        mapping[placeholder] = block

        # Replace the raw content with placeholder
        result = result.replace(block.raw_content, placeholder, 1)

    return result, mapping


def restore_code_blocks(
    content: str,
    mapping: dict[str, CodeBlock],
) -> str:
    """
    Restore code blocks from placeholders.

    Args:
        content: Content with placeholders
        mapping: Mapping from placeholder to CodeBlock

    Returns:
        Content with code blocks restored
    """
    result = content
    for placeholder, block in mapping.items():
        result = result.replace(placeholder, block.raw_content)
    return result


def code_block_to_markdown(
    code: str,
    language: str = "",
    fence_char: str = "`",
    fence_count: int = 3,
) -> str:
    """
    Create a markdown code block from code content.

    Args:
        code: The code content
        language: Programming language identifier
        fence_char: Character to use for fence ('`' or '~')
        fence_count: Number of fence characters (minimum 3)

    Returns:
        Markdown-formatted code block

    Examples:
        >>> code_block_to_markdown("print('hello')", "python")
        '```python\\nprint(\\'hello\\')\\n```'
    """
    fence = fence_char * max(fence_count, 3)

    # If code contains the fence pattern, increase fence count
    while fence in code:
        fence += fence_char

    if language:
        return f"{fence}{language}\n{code}\n{fence}"
    return f"{fence}\n{code}\n{fence}"


def get_code_block_stats(content: str) -> dict[str, int | list[str]]:
    """
    Get statistics about code blocks in content.

    Args:
        content: Markdown content to analyze

    Returns:
        Dictionary with stats:
        - total: Total code block count
        - fenced: Fenced code block count
        - indented: Indented code block count
        - with_language: Blocks with language specified
        - without_language: Blocks without language
        - languages: List of unique languages
        - lines_of_code: Total lines of code
    """
    collection, _ = parse_code_blocks(content, include_inline=False, include_indented=True)

    fenced = sum(1 for b in collection.blocks if b.is_fenced)
    indented = sum(1 for b in collection.blocks if b.block_type == CodeBlockType.INDENTED)
    with_lang = sum(1 for b in collection.blocks if b.has_language)
    total_lines = sum(b.line_count for b in collection.blocks)

    return {
        "total": collection.count,
        "fenced": fenced,
        "indented": indented,
        "with_language": with_lang,
        "without_language": collection.count - with_lang,
        "languages": collection.languages,
        "lines_of_code": total_lines,
    }


# =============================================================================
# Error Code Definitions
# =============================================================================


class ParseErrorCode:
    """Standard error codes for parse issues."""

    # Structure errors
    NO_STORIES = "E001"
    INVALID_HEADER = "E002"
    MISSING_REQUIRED_FIELD = "E003"
    DUPLICATE_STORY_ID = "E004"

    # Field errors
    INVALID_FIELD_VALUE = "E101"
    INVALID_STORY_POINTS = "E102"
    INVALID_PRIORITY = "E103"
    INVALID_STATUS = "E104"

    # Format warnings
    FIELD_ALIAS = "W001"
    SECTION_ALIAS = "W002"
    NONSTANDARD_FORMAT = "W003"
    MISSING_OPTIONAL_FIELD = "W004"
    INCOMPLETE_DESCRIPTION = "W005"
    EMPTY_CHECKBOX = "W006"
    NONSTANDARD_CHECKBOX = "W007"
    SHORT_SUBTASK_NAME = "W008"
    NONSTANDARD_SUBTASK_CHECKBOX = "W009"
    TABLE_COLUMN_MISMATCH = "W010"
    CODE_BLOCK_NO_LANGUAGE = "W011"


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Code Block Preservation
    "CodeBlock",
    "CodeBlockCollection",
    "CodeBlockType",
    # Image Embedding
    "EmbeddedImage",
    # Core types
    "InlineSubtaskInfo",
    # Error codes
    "ParseErrorCode",
    "ParseErrorInfo",
    "ParseIssue",
    "ParseLocation",
    "ParseResult",
    "ParseSeverity",
    "ParseWarning",
    "ParsedTable",
    # Table Parsing
    "TableAlignment",
    "TableCell",
    # Extractors
    "TolerantFieldExtractor",
    # Patterns
    "TolerantPatterns",
    "TolerantSectionExtractor",
    "code_block_to_markdown",
    "extract_code_blocks_from_content",
    "extract_code_from_section",
    "extract_images_from_section",
    "extract_table_from_section",
    "extract_tables_from_content",
    "get_code_block_stats",
    # Utilities
    "get_column_number",
    "get_context_lines",
    "get_line_content",
    "get_line_number",
    "location_from_match",
    "parse_checkboxes_tolerant",
    "parse_code_blocks",
    "parse_description_tolerant",
    "parse_embedded_images",
    "parse_inline_subtasks",
    "parse_markdown_table",
    "preserve_code_blocks",
    "restore_code_blocks",
    "table_to_markdown",
]
