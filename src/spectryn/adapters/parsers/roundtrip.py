"""
Round-trip Markdown Editor - Modify source markdown while preserving formatting.

This module provides capabilities to edit parsed markdown entities and write
them back to the original source while preserving:
- Original whitespace and indentation
- Comments and annotations
- Custom formatting choices
- Sections not recognized by the parser
- Line endings and file encoding

The key insight is that we track source spans for each parsed element,
allowing us to make surgical edits rather than regenerating the entire file.

Usage:
    from spectryn.adapters.parsers.roundtrip import (
        RoundtripParser,
        SourceSpan,
        EditOperation,
        RoundtripEditor,
    )

    # Parse with source tracking
    parser = RoundtripParser()
    result = parser.parse_with_spans("# Epic\\n### US-001: Story...")

    # Make edits
    editor = RoundtripEditor(result.source_content)
    editor.update_field(story_span, "Status", "Done")
    editor.update_field(story_span, "Story Points", "8")

    # Get result preserving formatting
    updated_content = editor.apply()
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    StoryId,
)


if TYPE_CHECKING:
    from pathlib import Path


# =============================================================================
# Source Span Tracking
# =============================================================================


@dataclass(frozen=True)
class SourceSpan:
    """
    Represents a span of text in the source document.

    All indices are 0-based character positions. Lines are 1-indexed for display.

    Attributes:
        start: Start character position (inclusive)
        end: End character position (exclusive)
        start_line: 1-indexed line number where span starts
        end_line: 1-indexed line number where span ends
        source: Optional source file path
    """

    start: int
    end: int
    start_line: int = 0
    end_line: int = 0
    source: str | None = None

    @property
    def length(self) -> int:
        """Get the length of this span in characters."""
        return self.end - self.start

    def contains(self, position: int) -> bool:
        """Check if a character position is within this span."""
        return self.start <= position < self.end

    def overlaps(self, other: SourceSpan) -> bool:
        """Check if this span overlaps with another."""
        return self.start < other.end and other.start < self.end

    def extract(self, content: str) -> str:
        """Extract the text covered by this span from content."""
        return content[self.start : self.end]

    def __repr__(self) -> str:
        if self.source:
            return f"SourceSpan({self.source}:{self.start_line}-{self.end_line})"
        return f"SourceSpan({self.start}:{self.end})"


@dataclass
class FieldSpan:
    """
    Source span for a specific field within a story.

    Tracks both the full field definition (including label) and just the value.

    Attributes:
        field_name: Name of the field (e.g., "Status", "Story Points")
        full_span: Span covering the entire field line/cell
        value_span: Span covering just the value portion
        format_type: How the field is formatted (table, inline, blockquote)
    """

    field_name: str
    full_span: SourceSpan
    value_span: SourceSpan
    format_type: str = "table"  # table, inline, blockquote


@dataclass
class SectionSpan:
    """
    Source span for a document section.

    Attributes:
        section_name: Name of the section (e.g., "Acceptance Criteria")
        header_span: Span for the section header
        content_span: Span for the section content
        level: Header level (2, 3, 4 for ##, ###, ####)
    """

    section_name: str
    header_span: SourceSpan
    content_span: SourceSpan
    level: int = 3


@dataclass
class StorySpan:
    """
    Complete source mapping for a user story.

    Contains spans for the header and all parseable sections/fields.
    Enables surgical editing of any part of the story.

    Attributes:
        story_id: The story ID (e.g., "US-001")
        full_span: Span covering the entire story section
        header_span: Span for the story header line
        fields: Map of field names to their spans
        sections: Map of section names to their spans
        subtask_spans: List of spans for individual subtasks
    """

    story_id: str
    full_span: SourceSpan
    header_span: SourceSpan
    title_span: SourceSpan
    fields: dict[str, FieldSpan] = field(default_factory=dict)
    sections: dict[str, SectionSpan] = field(default_factory=dict)
    subtask_spans: list[SourceSpan] = field(default_factory=list)
    acceptance_criteria_spans: list[SourceSpan] = field(default_factory=list)


@dataclass
class ParsedStoryWithSpans:
    """A parsed user story with its source spans for round-trip editing."""

    story: UserStory
    spans: StorySpan


@dataclass
class RoundtripParseResult:
    """Result of parsing with source span tracking."""

    source_content: str
    source_path: str | None = None
    stories: list[ParsedStoryWithSpans] = field(default_factory=list)
    epic_span: SourceSpan | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if parsing was successful."""
        return len(self.errors) == 0


# =============================================================================
# Edit Operations
# =============================================================================


class EditType(Enum):
    """Types of edit operations."""

    REPLACE = "replace"  # Replace text at span
    INSERT = "insert"  # Insert text at position
    DELETE = "delete"  # Delete text at span


@dataclass
class EditOperation:
    """
    A single edit operation to apply to source content.

    Edit operations are applied in reverse order (highest position first)
    to avoid invalidating positions of earlier operations.

    Attributes:
        edit_type: Type of edit (replace, insert, delete)
        span: The source span affected (for replace/delete)
        position: Insert position (for insert operations)
        new_text: New text to insert/replace with
        description: Human-readable description of the edit
    """

    edit_type: EditType
    span: SourceSpan | None = None
    position: int | None = None
    new_text: str = ""
    description: str = ""

    @property
    def start_position(self) -> int:
        """Get the starting position of this edit."""
        if self.span:
            return self.span.start
        return self.position or 0

    def apply(self, content: str) -> str:
        """Apply this edit operation to content."""
        if self.edit_type == EditType.REPLACE and self.span:
            return content[: self.span.start] + self.new_text + content[self.span.end :]
        if self.edit_type == EditType.INSERT and self.position is not None:
            return content[: self.position] + self.new_text + content[self.position :]
        if self.edit_type == EditType.DELETE and self.span:
            return content[: self.span.start] + content[self.span.end :]
        return content


# =============================================================================
# Round-trip Parser
# =============================================================================


class RoundtripParser:
    """
    Parser that tracks source spans for round-trip editing.

    Extends the tolerant parser to also record exact source locations
    for all parsed elements, enabling precise edits.
    """

    # Story ID patterns (same as main parser)
    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"
    STORY_ID_PATTERN_EXTENDED = r"(?:[A-Z]+[-_/]\d+|#?\d+)"

    # Field patterns for different formats
    TABLE_FIELD_PATTERN = r"\|\s*\*\*({field})\*\*\s*\|\s*([^|]+)\s*\|"
    INLINE_FIELD_PATTERN = r"\*\*({field})\*\*\s*:\s*(.+?)(?:\s*$|\n)"
    BLOCKQUOTE_FIELD_PATTERN = r">\s*\*\*({field})\*\*\s*:\s*(.+?)(?:\s*$|\n)"

    def __init__(self) -> None:
        """Initialize the round-trip parser."""
        self._content: str = ""
        self._source: str | None = None

    def parse_with_spans(
        self,
        source: str | Path,
        source_name: str | None = None,
    ) -> RoundtripParseResult:
        """
        Parse content and track source spans for all elements.

        Args:
            source: File path or content string
            source_name: Optional name for error reporting

        Returns:
            RoundtripParseResult with stories and their spans
        """
        # Get content
        if hasattr(source, "read_text"):
            # It's a Path
            self._content = source.read_text(encoding="utf-8")  # type: ignore[union-attr]
            self._source = str(source)
        else:
            self._content = str(source)
            self._source = source_name

        result = RoundtripParseResult(
            source_content=self._content,
            source_path=self._source,
        )

        # Find all story headers
        story_matches = list(self._find_story_headers())

        if not story_matches:
            result.errors.append("No user stories found in document")
            return result

        # Parse each story with spans
        for i, (match, header_type) in enumerate(story_matches):
            # Determine story boundaries
            story_start = match.start()
            if i + 1 < len(story_matches):
                story_end = story_matches[i + 1][0].start()
            else:
                story_end = len(self._content)

            story_content = self._content[story_start:story_end]

            try:
                parsed = self._parse_story_with_spans(
                    match, header_type, story_start, story_end, story_content
                )
                if parsed:
                    result.stories.append(parsed)
            except Exception as e:
                result.errors.append(f"Failed to parse story: {e}")

        return result

    def _find_story_headers(self) -> list[tuple[re.Match[str], str]]:
        """Find all story headers in content with their format type."""
        matches: list[tuple[re.Match[str], str]] = []

        # H3 pattern (standard): ### [emoji] STORY-001: Title
        h3_pattern = re.compile(
            rf"^#{{2,3}}\s*(?:[^\n]*?\s)?({self.STORY_ID_PATTERN})\s*:\s*([^\n]+?)$",
            re.MULTILINE,
        )
        for match in h3_pattern.finditer(self._content):
            matches.append((match, "h3"))

        # H1 pattern (standalone): # STORY-001: Title
        h1_pattern = re.compile(
            rf"^#\s*(?:[^\n]*?\s)?({self.STORY_ID_PATTERN_EXTENDED})\s*:\s*([^\n]+?)$",
            re.MULTILINE,
        )
        for match in h1_pattern.finditer(self._content):
            # Don't include h1 if we already have h3 matches starting nearby
            if not any(abs(match.start() - m[0].start()) < 10 for m in matches):
                matches.append((match, "h1"))

        # Sort by position
        matches.sort(key=lambda x: x[0].start())
        return matches

    def _parse_story_with_spans(
        self,
        header_match: re.Match[str],
        header_type: str,
        story_start: int,
        story_end: int,
        story_content: str,
    ) -> ParsedStoryWithSpans | None:
        """Parse a single story and track all source spans."""
        story_id = header_match.group(1)
        title = header_match.group(2).strip()

        # Clean title of trailing emoji/status
        title = re.sub(r"\s*[✅🔲🟡⏸️🔄📋]+\s*$", "", title).strip()

        # Create spans
        header_span = SourceSpan(
            start=header_match.start(),
            end=header_match.end(),
            start_line=self._get_line_number(header_match.start()),
            end_line=self._get_line_number(header_match.end()),
            source=self._source,
        )

        # Title span is within the header
        title_start = header_match.start() + header_match.group(0).find(title)
        title_span = SourceSpan(
            start=title_start,
            end=title_start + len(title),
            start_line=header_span.start_line,
            end_line=header_span.start_line,
            source=self._source,
        )

        full_span = SourceSpan(
            start=story_start,
            end=story_end,
            start_line=self._get_line_number(story_start),
            end_line=self._get_line_number(story_end),
            source=self._source,
        )

        # Initialize story spans
        story_spans = StorySpan(
            story_id=story_id,
            full_span=full_span,
            header_span=header_span,
            title_span=title_span,
        )

        # Parse fields with spans
        fields = self._extract_fields_with_spans(story_content, story_start)
        story_spans.fields = fields

        # Parse sections with spans
        sections = self._extract_sections_with_spans(story_content, story_start)
        story_spans.sections = sections

        # Extract field values for the story
        story_points = self._get_field_value(fields, "Story Points", "0")
        priority_str = self._get_field_value(fields, "Priority", "Medium")
        status_str = self._get_field_value(fields, "Status", "Planned")

        # Parse description
        description = self._parse_description(story_content)

        # Parse acceptance criteria with spans
        ac_items, ac_spans = self._parse_acceptance_criteria_with_spans(story_content, story_start)
        story_spans.acceptance_criteria_spans = ac_spans

        # Parse subtasks with spans
        subtasks, subtask_spans = self._parse_subtasks_with_spans(story_content, story_start)
        story_spans.subtask_spans = subtask_spans

        # Create the story entity
        story = UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            story_points=int(story_points) if story_points.isdigit() else 0,
            priority=Priority.from_string(priority_str),
            status=Status.from_string(status_str),
            acceptance_criteria=AcceptanceCriteria.from_list(
                [text for text, _checked in ac_items],
                [checked for _text, checked in ac_items],
            ),
            subtasks=subtasks,
        )

        return ParsedStoryWithSpans(story=story, spans=story_spans)

    def _extract_fields_with_spans(self, content: str, offset: int) -> dict[str, FieldSpan]:
        """Extract all fields with their source spans."""
        fields: dict[str, FieldSpan] = {}

        # Common field names
        field_names = [
            "Story Points",
            "Points",
            "Priority",
            "Status",
            "Assignee",
            "Labels",
            "Sprint",
            "Story ID",
        ]

        for field_name in field_names:
            span = self._find_field_span(content, field_name, offset)
            if span:
                # Normalize field name
                normalized = field_name
                if field_name == "Points":
                    normalized = "Story Points"
                fields[normalized] = span

        return fields

    def _find_field_span(self, content: str, field_name: str, offset: int) -> FieldSpan | None:
        """Find a field's source span in the content."""
        field_escaped = re.escape(field_name)

        # Try table format: | **Field** | Value |
        table_pattern = re.compile(
            rf"\|\s*\*\*({field_escaped})\*\*\s*\|\s*([^|]+?)\s*\|",
            re.IGNORECASE,
        )
        match = table_pattern.search(content)
        if match:
            full_start = offset + match.start()
            full_end = offset + match.end()
            # Value span is group 2
            value_start = offset + match.start(2)
            value_end = offset + match.end(2)
            return FieldSpan(
                field_name=field_name,
                full_span=SourceSpan(
                    start=full_start,
                    end=full_end,
                    start_line=self._get_line_number(full_start),
                    end_line=self._get_line_number(full_end),
                    source=self._source,
                ),
                value_span=SourceSpan(
                    start=value_start,
                    end=value_end,
                    start_line=self._get_line_number(value_start),
                    end_line=self._get_line_number(value_end),
                    source=self._source,
                ),
                format_type="table",
            )

        # Try inline format: **Field**: Value
        inline_pattern = re.compile(
            rf"(?<!>)\s*\*\*({field_escaped})\*\*\s*:\s*(.+?)(?:\s*$|\n)",
            re.MULTILINE | re.IGNORECASE,
        )
        match = inline_pattern.search(content)
        if match:
            full_start = offset + match.start()
            full_end = offset + match.end()
            value_start = offset + match.start(2)
            value_end = offset + match.end(2)
            return FieldSpan(
                field_name=field_name,
                full_span=SourceSpan(
                    start=full_start,
                    end=full_end,
                    start_line=self._get_line_number(full_start),
                    end_line=self._get_line_number(full_end),
                    source=self._source,
                ),
                value_span=SourceSpan(
                    start=value_start,
                    end=value_end,
                    start_line=self._get_line_number(value_start),
                    end_line=self._get_line_number(value_end),
                    source=self._source,
                ),
                format_type="inline",
            )

        # Try blockquote format: > **Field**: Value
        blockquote_pattern = re.compile(
            rf">\s*\*\*({field_escaped})\*\*\s*:\s*(.+?)(?:\s*$|\n)",
            re.MULTILINE | re.IGNORECASE,
        )
        match = blockquote_pattern.search(content)
        if match:
            full_start = offset + match.start()
            full_end = offset + match.end()
            value_start = offset + match.start(2)
            value_end = offset + match.end(2)
            return FieldSpan(
                field_name=field_name,
                full_span=SourceSpan(
                    start=full_start,
                    end=full_end,
                    start_line=self._get_line_number(full_start),
                    end_line=self._get_line_number(full_end),
                    source=self._source,
                ),
                value_span=SourceSpan(
                    start=value_start,
                    end=value_end,
                    start_line=self._get_line_number(value_start),
                    end_line=self._get_line_number(value_end),
                    source=self._source,
                ),
                format_type="blockquote",
            )

        return None

    def _extract_sections_with_spans(self, content: str, offset: int) -> dict[str, SectionSpan]:
        """Extract all sections with their source spans."""
        sections: dict[str, SectionSpan] = {}

        section_names = [
            "Acceptance Criteria",
            "Subtasks",
            "Description",
            "User Story",
            "Technical Notes",
            "Related Commits",
            "Dependencies",
        ]

        for section_name in section_names:
            span = self._find_section_span(content, section_name, offset)
            if span:
                # Normalize section names
                normalized = section_name
                if section_name == "User Story":
                    normalized = "Description"
                sections[normalized] = span

        return sections

    def _find_section_span(
        self, content: str, section_name: str, offset: int
    ) -> SectionSpan | None:
        """Find a section's source span."""
        section_escaped = re.escape(section_name)

        # Pattern to find section header and content
        pattern = re.compile(
            rf"^(#{{2,4}})\s*({section_escaped})\s*\n([\s\S]*?)(?=^#{{2,4}}\s|\Z)",
            re.MULTILINE | re.IGNORECASE,
        )

        match = pattern.search(content)
        if not match:
            return None

        level = len(match.group(1))  # Number of # characters
        header_start = offset + match.start()
        header_end = offset + match.start(3)  # End of header line
        content_start = offset + match.start(3)
        content_end = offset + match.end(3)

        return SectionSpan(
            section_name=section_name,
            header_span=SourceSpan(
                start=header_start,
                end=header_end,
                start_line=self._get_line_number(header_start),
                end_line=self._get_line_number(header_end),
                source=self._source,
            ),
            content_span=SourceSpan(
                start=content_start,
                end=content_end,
                start_line=self._get_line_number(content_start),
                end_line=self._get_line_number(content_end),
                source=self._source,
            ),
            level=level,
        )

    def _parse_description(self, content: str) -> Description | None:
        """Parse user story description."""
        # Pattern for "As a / I want / So that" format
        pattern = re.compile(
            r"\*\*As\s+a\*\*\s*(.+?)"
            r"(?:,?\s*\n\s*(?:>\s*)?)?"
            r"\*\*I\s+want\*\*\s*(.+?)"
            r"(?:,?\s*\n\s*(?:>\s*)?)?"
            r"\*\*So\s+that\*\*\s*(.+?)$",
            re.MULTILINE | re.IGNORECASE | re.DOTALL,
        )

        match = pattern.search(content)
        if match:
            role = match.group(1).strip().rstrip(",.")
            want = match.group(2).strip().rstrip(",.")
            benefit = match.group(3).strip().rstrip(",.")
            return Description(role=role, want=want, benefit=benefit)

        return None

    def _parse_acceptance_criteria_with_spans(
        self, content: str, offset: int
    ) -> tuple[list[tuple[str, bool]], list[SourceSpan]]:
        """Parse acceptance criteria with source spans."""
        items: list[tuple[str, bool]] = []
        spans: list[SourceSpan] = []

        # Find acceptance criteria section
        ac_pattern = re.compile(
            r"#{2,4}\s*Acceptance\s*Criteria\s*\n([\s\S]*?)(?=#{2,4}\s|\Z)",
            re.IGNORECASE,
        )
        ac_match = ac_pattern.search(content)
        if not ac_match:
            return items, spans

        ac_content = ac_match.group(1)
        ac_offset = offset + ac_match.start(1)

        # Find checkboxes
        checkbox_pattern = re.compile(
            r"^[\s]*[-*+]\s*\[([xX\s]?)\]\s*(.+?)$",
            re.MULTILINE,
        )

        for match in checkbox_pattern.finditer(ac_content):
            checked = match.group(1).strip().lower() == "x"
            text = match.group(2).strip()
            items.append((text, checked))

            span_start = ac_offset + match.start()
            span_end = ac_offset + match.end()
            spans.append(
                SourceSpan(
                    start=span_start,
                    end=span_end,
                    start_line=self._get_line_number(span_start),
                    end_line=self._get_line_number(span_end),
                    source=self._source,
                )
            )

        return items, spans

    def _parse_subtasks_with_spans(
        self, content: str, offset: int
    ) -> tuple[list[Subtask], list[SourceSpan]]:
        """Parse subtasks with source spans."""
        subtasks: list[Subtask] = []
        spans: list[SourceSpan] = []

        # Find subtasks section
        subtasks_pattern = re.compile(
            r"#{2,4}\s*Subtasks\s*\n([\s\S]*?)(?=#{2,4}\s|\Z)",
            re.IGNORECASE,
        )
        subtasks_match = subtasks_pattern.search(content)
        if not subtasks_match:
            return subtasks, spans

        subtasks_content = subtasks_match.group(1)
        subtasks_offset = offset + subtasks_match.start(1)

        # Parse table rows (skip header and separator)
        # Pattern: | number | name | description | sp | status |
        row_pattern = re.compile(
            r"^\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|",
            re.MULTILINE,
        )

        for match in row_pattern.finditer(subtasks_content):
            number = int(match.group(1))
            name = match.group(2).strip()
            description = match.group(3).strip()
            sp = int(match.group(4))
            status_str = match.group(5).strip()

            # Skip if this looks like a header row
            if name.lower() == "subtask" or "---" in name:
                continue

            subtask = Subtask(
                number=number,
                name=name,
                description=description,
                story_points=sp,
                status=Status.from_string(status_str),
            )
            subtasks.append(subtask)

            span_start = subtasks_offset + match.start()
            span_end = subtasks_offset + match.end()
            spans.append(
                SourceSpan(
                    start=span_start,
                    end=span_end,
                    start_line=self._get_line_number(span_start),
                    end_line=self._get_line_number(span_end),
                    source=self._source,
                )
            )

        return subtasks, spans

    def _get_field_value(self, fields: dict[str, FieldSpan], field_name: str, default: str) -> str:
        """Get a field's value from the source content."""
        if field_name not in fields:
            return default

        span = fields[field_name]
        value = self._content[span.value_span.start : span.value_span.end].strip()

        # Clean up emoji prefixes for status/priority
        value = re.sub(r"^[✅🔲🟡⏸️🔄📋🔴🟠🟢⬜🟤\s]+", "", value).strip()

        return value or default

    def _get_line_number(self, position: int) -> int:
        """Get 1-indexed line number for a character position."""
        return self._content[:position].count("\n") + 1


# =============================================================================
# Round-trip Editor
# =============================================================================


class RoundtripEditor:
    """
    Editor for making precise edits to markdown while preserving formatting.

    Collects edit operations and applies them in a way that preserves
    the original formatting, whitespace, and structure of the document.

    Usage:
        editor = RoundtripEditor(content)

        # Update a field value
        editor.update_field_value(story_spans.fields["Status"], "Done")

        # Update story title
        editor.update_title(story_spans.title_span, "New Title")

        # Apply all edits
        result = editor.apply()
    """

    def __init__(self, content: str):
        """
        Initialize the editor with source content.

        Args:
            content: Original markdown content to edit
        """
        self._original_content = content
        self._edits: list[EditOperation] = []

    def update_field_value(
        self,
        field_span: FieldSpan,
        new_value: str,
        preserve_emoji: bool = True,
    ) -> None:
        """
        Update a field's value while preserving formatting.

        Args:
            field_span: The field span to update
            new_value: New value for the field
            preserve_emoji: Whether to preserve emoji prefix for status/priority
        """
        # Get the original value to preserve formatting hints
        original_value = self._original_content[
            field_span.value_span.start : field_span.value_span.end
        ]

        # Preserve leading/trailing whitespace from original
        leading_ws = len(original_value) - len(original_value.lstrip())
        trailing_ws = len(original_value) - len(original_value.rstrip())

        # Build new value with preserved whitespace
        formatted_value = (
            original_value[:leading_ws]
            + new_value
            + original_value[len(original_value) - trailing_ws :]
            if trailing_ws
            else original_value[:leading_ws] + new_value
        )

        # For status/priority fields, try to preserve emoji format if present
        if preserve_emoji and field_span.field_name in ("Status", "Priority"):
            emoji_match = re.match(r"^([✅🔲🟡⏸️🔄📋🔴🟠🟢⬜🟤\s]+)", original_value.lstrip())
            if emoji_match:
                # There was an emoji - we need to update it based on new value
                formatted_value = self._format_field_with_emoji(field_span.field_name, new_value)

        self._edits.append(
            EditOperation(
                edit_type=EditType.REPLACE,
                span=field_span.value_span,
                new_text=formatted_value,
                description=f"Update {field_span.field_name} to {new_value}",
            )
        )

    def update_title(self, title_span: SourceSpan, new_title: str) -> None:
        """
        Update a story's title.

        Args:
            title_span: The span covering the current title
            new_title: New title text
        """
        self._edits.append(
            EditOperation(
                edit_type=EditType.REPLACE,
                span=title_span,
                new_text=new_title,
                description=f"Update title to: {new_title}",
            )
        )

    def update_acceptance_criterion(
        self,
        ac_span: SourceSpan,
        new_text: str,
        checked: bool | None = None,
    ) -> None:
        """
        Update an acceptance criterion.

        Args:
            ac_span: The span covering the criterion line
            new_text: New text for the criterion
            checked: New checked state (None to preserve original)
        """
        original = self._original_content[ac_span.start : ac_span.end]

        # Detect original format
        match = re.match(r"^([\s]*[-*+]\s*\[)([xX\s]?)(\]\s*)", original)
        if match:
            prefix = match.group(1)
            original_checked = match.group(2).strip().lower() == "x"
            suffix = match.group(3)

            if checked is None:
                checked = original_checked

            checkbox = "x" if checked else " "
            new_line = f"{prefix}{checkbox}{suffix}{new_text}"

            self._edits.append(
                EditOperation(
                    edit_type=EditType.REPLACE,
                    span=ac_span,
                    new_text=new_line,
                    description=f"Update AC: {new_text[:30]}...",
                )
            )

    def toggle_acceptance_criterion(self, ac_span: SourceSpan, checked: bool) -> None:
        """
        Toggle the checked state of an acceptance criterion.

        Args:
            ac_span: The span covering the criterion line
            checked: New checked state
        """
        original = self._original_content[ac_span.start : ac_span.end]

        # Just replace the checkbox character
        if checked:
            new_line = re.sub(r"\[\s?\]", "[x]", original)
        else:
            new_line = re.sub(r"\[[xX]\]", "[ ]", original)

        if new_line != original:
            self._edits.append(
                EditOperation(
                    edit_type=EditType.REPLACE,
                    span=ac_span,
                    new_text=new_line,
                    description=f"Toggle AC to {'checked' if checked else 'unchecked'}",
                )
            )

    def update_subtask_status(
        self,
        subtask_span: SourceSpan,
        new_status: Status,
    ) -> None:
        """
        Update a subtask's status in the table.

        Args:
            subtask_span: The span covering the subtask row
            new_status: New status value
        """
        original = self._original_content[subtask_span.start : subtask_span.end]

        # Parse the table row to find the status column
        # Pattern: | ... | status |
        # The status is typically the last column before the final |
        parts = original.split("|")
        if len(parts) >= 2:
            # Find status column (usually last non-empty column)
            status_col = -2  # Second to last (before trailing empty from split)
            while status_col > -len(parts) and not parts[status_col].strip():
                status_col -= 1

            # Update status with emoji
            status_display = f"{new_status.emoji} {new_status.display_name}"
            parts[status_col] = f" {status_display} "

            new_row = "|".join(parts)

            self._edits.append(
                EditOperation(
                    edit_type=EditType.REPLACE,
                    span=subtask_span,
                    new_text=new_row,
                    description=f"Update subtask status to {new_status.display_name}",
                )
            )

    def insert_acceptance_criterion(
        self,
        section_span: SectionSpan,
        text: str,
        checked: bool = False,
        position: int = -1,
    ) -> None:
        """
        Insert a new acceptance criterion.

        Args:
            section_span: The acceptance criteria section span
            text: Text for the new criterion
            checked: Whether it should be checked
            position: Position to insert (-1 for end)
        """
        checkbox = "[x]" if checked else "[ ]"
        new_line = f"- {checkbox} {text}\n"

        # Insert at end of section content
        insert_pos = section_span.content_span.end

        # Find last non-whitespace position in section
        content = self._original_content[
            section_span.content_span.start : section_span.content_span.end
        ]
        stripped_content = content.rstrip()
        if stripped_content:
            insert_pos = section_span.content_span.start + len(stripped_content) + 1

        self._edits.append(
            EditOperation(
                edit_type=EditType.INSERT,
                position=insert_pos,
                new_text=new_line,
                description=f"Add AC: {text[:30]}...",
            )
        )

    def delete_acceptance_criterion(self, ac_span: SourceSpan) -> None:
        """
        Delete an acceptance criterion.

        Args:
            ac_span: The span covering the criterion line to delete
        """
        # Extend span to include trailing newline
        end = ac_span.end
        if end < len(self._original_content) and self._original_content[end] == "\n":
            end += 1

        extended_span = SourceSpan(
            start=ac_span.start,
            end=end,
            start_line=ac_span.start_line,
            end_line=ac_span.end_line,
            source=ac_span.source,
        )

        self._edits.append(
            EditOperation(
                edit_type=EditType.DELETE,
                span=extended_span,
                description="Delete acceptance criterion",
            )
        )

    def add_custom_edit(
        self,
        edit_type: EditType,
        span: SourceSpan | None = None,
        position: int | None = None,
        new_text: str = "",
        description: str = "",
    ) -> None:
        """
        Add a custom edit operation.

        Args:
            edit_type: Type of edit
            span: Span to replace/delete (for replace/delete operations)
            position: Position to insert at (for insert operations)
            new_text: New text to insert/replace with
            description: Human-readable description
        """
        self._edits.append(
            EditOperation(
                edit_type=edit_type,
                span=span,
                position=position,
                new_text=new_text,
                description=description,
            )
        )

    def apply(self) -> str:
        """
        Apply all collected edits and return the result.

        Edits are applied in reverse order (highest position first)
        to avoid invalidating earlier positions.

        Returns:
            Updated content with all edits applied
        """
        if not self._edits:
            return self._original_content

        # Sort edits by position (descending) to apply from end to start
        sorted_edits = sorted(
            self._edits,
            key=lambda e: e.start_position,
            reverse=True,
        )

        # Apply edits
        result = self._original_content
        for edit in sorted_edits:
            result = edit.apply(result)

        return result

    def get_pending_edits(self) -> list[EditOperation]:
        """Get list of pending edit operations."""
        return list(self._edits)

    def clear_edits(self) -> None:
        """Clear all pending edits."""
        self._edits.clear()

    def preview_diff(self) -> str:
        """
        Generate a diff-like preview of pending changes.

        Returns:
            Human-readable diff preview
        """
        if not self._edits:
            return "No pending edits"

        lines = ["Pending edits:"]
        for i, edit in enumerate(self._edits, 1):
            lines.append(f"  {i}. {edit.description}")
            if edit.span:
                original = self._original_content[edit.span.start : edit.span.end]
                lines.append(f"      - {original[:50]}{'...' if len(original) > 50 else ''}")
            if edit.new_text:
                lines.append(
                    f"      + {edit.new_text[:50]}{'...' if len(edit.new_text) > 50 else ''}"
                )

        return "\n".join(lines)

    def _format_field_with_emoji(self, field_name: str, value: str) -> str:
        """Format a field value with appropriate emoji."""
        if field_name == "Status":
            try:
                status = Status.from_string(value)
                return f"{status.emoji} {status.display_name}"
            except ValueError:
                return value
        elif field_name == "Priority":
            try:
                priority = Priority.from_string(value)
                return f"{priority.emoji} {priority.display_name}"
            except ValueError:
                return value
        return value


# =============================================================================
# High-Level API
# =============================================================================


def update_story_in_file(
    file_path: Path,
    story_id: str,
    updates: dict[str, Any],
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Update a story in a markdown file while preserving formatting.

    This is the main entry point for round-trip editing.

    Args:
        file_path: Path to the markdown file
        story_id: ID of the story to update (e.g., "US-001")
        updates: Dictionary of field updates (e.g., {"status": "Done", "story_points": 5})
        dry_run: If True, return updated content without writing

    Returns:
        Tuple of (success, content_or_error)
        - On success: (True, updated_content)
        - On failure: (False, error_message)

    Example:
        >>> success, result = update_story_in_file(
        ...     Path("epic.md"),
        ...     "US-001",
        ...     {"status": "Done", "story_points": 8},
        ... )
        >>> if success and not dry_run:
        ...     print("Story updated!")
    """
    if not file_path.exists():
        return False, f"File not found: {file_path}"

    try:
        # Parse with spans
        parser = RoundtripParser()
        result = parser.parse_with_spans(file_path)

        if not result.success:
            return False, f"Parse errors: {', '.join(result.errors)}"

        # Find the story
        story_data = None
        for parsed in result.stories:
            if parsed.spans.story_id == story_id:
                story_data = parsed
                break

        if not story_data:
            return False, f"Story {story_id} not found in file"

        # Create editor
        editor = RoundtripEditor(result.source_content)

        # Apply updates
        for field_name, value in updates.items():
            if field_name == "title":
                editor.update_title(story_data.spans.title_span, str(value))
            elif field_name in ("status", "Status"):
                if "Status" in story_data.spans.fields:
                    value_str = value.display_name if isinstance(value, Status) else str(value)
                    editor.update_field_value(story_data.spans.fields["Status"], value_str)
            elif field_name in ("story_points", "Story Points", "points"):
                if "Story Points" in story_data.spans.fields:
                    editor.update_field_value(story_data.spans.fields["Story Points"], str(value))
            elif field_name in ("priority", "Priority"):
                if "Priority" in story_data.spans.fields:
                    value_str = value.display_name if isinstance(value, Priority) else str(value)
                    editor.update_field_value(story_data.spans.fields["Priority"], value_str)
            elif field_name in ("assignee", "Assignee"):
                if "Assignee" in story_data.spans.fields:
                    editor.update_field_value(
                        story_data.spans.fields["Assignee"], str(value) if value else ""
                    )

        # Apply edits
        updated_content = editor.apply()

        # Write if not dry run
        if not dry_run:
            file_path.write_text(updated_content, encoding="utf-8")

        return True, updated_content

    except Exception as e:
        return False, f"Error updating story: {e}"


def batch_update_stories(
    file_path: Path,
    updates: dict[str, dict[str, Any]],
    dry_run: bool = False,
) -> tuple[bool, str, dict[str, str]]:
    """
    Update multiple stories in a markdown file while preserving formatting.

    Args:
        file_path: Path to the markdown file
        updates: Dictionary mapping story IDs to their updates
        dry_run: If True, return updated content without writing

    Returns:
        Tuple of (success, content, errors_by_story)

    Example:
        >>> success, content, errors = batch_update_stories(
        ...     Path("epic.md"),
        ...     {
        ...         "US-001": {"status": "Done"},
        ...         "US-002": {"story_points": 5},
        ...     },
        ... )
    """
    if not file_path.exists():
        return False, "", {"_file": f"File not found: {file_path}"}

    errors: dict[str, str] = {}

    try:
        # Parse with spans
        parser = RoundtripParser()
        result = parser.parse_with_spans(file_path)

        if not result.success:
            return False, "", {"_parse": f"Parse errors: {', '.join(result.errors)}"}

        # Build story map
        story_map = {p.spans.story_id: p for p in result.stories}

        # Create editor
        editor = RoundtripEditor(result.source_content)

        # Apply updates for each story
        for story_id, story_updates in updates.items():
            if story_id not in story_map:
                errors[story_id] = "Story not found"
                continue

            story_data = story_map[story_id]

            for field_name, value in story_updates.items():
                try:
                    if field_name == "title":
                        editor.update_title(story_data.spans.title_span, str(value))
                    elif field_name in ("status", "Status"):
                        if "Status" in story_data.spans.fields:
                            value_str = (
                                value.display_name if isinstance(value, Status) else str(value)
                            )
                            editor.update_field_value(story_data.spans.fields["Status"], value_str)
                    elif field_name in ("story_points", "Story Points", "points"):
                        if "Story Points" in story_data.spans.fields:
                            editor.update_field_value(
                                story_data.spans.fields["Story Points"], str(value)
                            )
                    elif field_name in ("priority", "Priority"):
                        if "Priority" in story_data.spans.fields:
                            value_str = (
                                value.display_name if isinstance(value, Priority) else str(value)
                            )
                            editor.update_field_value(
                                story_data.spans.fields["Priority"], value_str
                            )
                except Exception as e:
                    errors[story_id] = f"Failed to update {field_name}: {e}"

        # Apply edits
        updated_content = editor.apply()

        # Write if not dry run
        if not dry_run:
            file_path.write_text(updated_content, encoding="utf-8")

        success = len(errors) == 0
        return success, updated_content, errors

    except Exception as e:
        return False, "", {"_error": f"Unexpected error: {e}"}


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Core types
    "EditOperation",
    "EditType",
    "FieldSpan",
    "ParsedStoryWithSpans",
    "RoundtripEditor",
    "RoundtripParseResult",
    "RoundtripParser",
    "SectionSpan",
    "SourceSpan",
    "StorySpan",
    # High-level API
    "batch_update_stories",
    "update_story_in_file",
]
