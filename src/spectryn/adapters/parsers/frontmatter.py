"""
Frontmatter Parser - Parse YAML frontmatter as alternative to tables.

Implements extensible YAML frontmatter parsing for markdown epic/story files.
This allows using YAML frontmatter (the `---` delimited block at the start of
markdown files) as an alternative way to specify story metadata instead of tables.

Features:
- Parse story metadata from YAML frontmatter
- Support both single-story and multi-story frontmatter formats
- Merge frontmatter data with inline markdown content
- Preserve backward compatibility with table-based format
- Extensible field mapping for custom metadata

Example formats:

Single-Story Frontmatter:
-------------------------
```markdown
---
id: US-001
title: Story Title
story_points: 5
priority: high
status: planned
description:
  as_a: user
  i_want: to do something
  so_that: I get benefit
acceptance_criteria:
  - criterion: First criterion
    done: false
  - criterion: Second criterion
    done: true
subtasks:
  - name: Subtask 1
    story_points: 2
    status: planned
labels: [feature, mvp]
assignee: john.doe
sprint: Sprint 1
---

# US-001: Story Title

Additional markdown content here...
```

Multi-Story Frontmatter:
------------------------
```markdown
---
epic:
  key: PROJ-123
  title: Epic Title
  description: Epic description
stories:
  - id: US-001
    title: First Story
    story_points: 3
  - id: US-002
    title: Second Story
    story_points: 5
---

## PROJ-123: Epic Title

...
```

Inline Frontmatter (per story):
-------------------------------
```markdown
### US-001: Story Title

<!--
story_points: 5
priority: high
status: in_progress
-->

Story content...
```
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort

from .tolerant_markdown import (
    ParseLocation,
    ParseWarning,
)


# =============================================================================
# Enums
# =============================================================================


class FrontmatterFormat(Enum):
    """Supported frontmatter formats."""

    YAML = "yaml"  # Standard YAML frontmatter (---)
    TOML = "toml"  # TOML frontmatter (+++)
    JSON = "json"  # JSON frontmatter (;;; or {})
    HTML_COMMENT = "html_comment"  # HTML comment YAML (<!-- -->)


class MergeStrategy(Enum):
    """Strategy for merging frontmatter with inline content."""

    FRONTMATTER_PRIORITY = "frontmatter"  # Frontmatter values override inline
    INLINE_PRIORITY = "inline"  # Inline values override frontmatter
    MERGE_ARRAYS = "merge_arrays"  # Arrays are merged, scalars use frontmatter
    DEEP_MERGE = "deep_merge"  # Deep merge all nested structures


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class FrontmatterSpan:
    """Location of frontmatter in source content."""

    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    format: FrontmatterFormat
    raw_content: str

    def to_location(self) -> ParseLocation:
        """Convert to ParseLocation for error reporting."""
        return ParseLocation(
            line=self.start_line,
            column=1,
            end_line=self.end_line,
        )


@dataclass(frozen=True)
class FieldMapping:
    """Mapping configuration for a frontmatter field."""

    frontmatter_key: str  # Key in YAML frontmatter
    entity_field: str  # Field name on UserStory/Epic
    aliases: tuple[str, ...] = ()  # Alternative key names
    transformer: Callable[[Any], Any] | None = None  # Value transformer
    required: bool = False


@dataclass
class FrontmatterParseResult:
    """Result of parsing frontmatter from content."""

    data: dict[str, Any]
    span: FrontmatterSpan | None
    remaining_content: str
    warnings: list[ParseWarning] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_frontmatter(self) -> bool:
        """Check if frontmatter was found."""
        return self.span is not None

    @property
    def is_valid(self) -> bool:
        """Check if parsing succeeded without errors."""
        return len(self.errors) == 0


@dataclass
class FrontmatterConfig:
    """Configuration for frontmatter parsing."""

    # Supported formats (in order of preference)
    formats: list[FrontmatterFormat] = field(
        default_factory=lambda: [
            FrontmatterFormat.YAML,
            FrontmatterFormat.HTML_COMMENT,
        ]
    )

    # Merge strategy for combining frontmatter with inline content
    merge_strategy: MergeStrategy = MergeStrategy.FRONTMATTER_PRIORITY

    # Custom field mappings (extends defaults)
    custom_mappings: list[FieldMapping] = field(default_factory=list)

    # Whether to parse inline frontmatter (<!-- yaml -->) per story
    parse_inline_frontmatter: bool = True

    # Whether to preserve raw frontmatter for round-trip editing
    preserve_raw: bool = False

    # Strict mode - fail on unknown fields
    strict: bool = False

    # Case sensitivity for field names
    case_sensitive: bool = False


# =============================================================================
# Default Field Mappings
# =============================================================================


def _parse_priority(value: Any) -> Priority:
    """Transform frontmatter value to Priority enum."""
    if isinstance(value, Priority):
        return value
    return Priority.from_string(str(value))


def _parse_status(value: Any) -> Status:
    """Transform frontmatter value to Status enum."""
    if isinstance(value, Status):
        return value
    return Status.from_string(str(value))


def _parse_story_points(value: Any) -> int:
    """Transform frontmatter value to story points integer."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        # Handle "5 SP" or "5 points" formats
        match = re.match(r"(\d+)", value.strip())
        if match:
            return int(match.group(1))
    return 0


def _parse_datetime(value: Any) -> datetime | None:
    """Transform frontmatter value to datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _parse_labels(value: Any) -> list[str]:
    """Transform frontmatter value to labels list."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        # Support comma-separated or space-separated
        return [v.strip() for v in re.split(r"[,\s]+", value) if v.strip()]
    return []


# Default field mappings for UserStory
DEFAULT_STORY_MAPPINGS: list[FieldMapping] = [
    FieldMapping(
        frontmatter_key="id",
        entity_field="id",
        aliases=("story_id", "story-id", "storyId"),
    ),
    FieldMapping(
        frontmatter_key="title",
        entity_field="title",
        aliases=("name", "summary"),
    ),
    FieldMapping(
        frontmatter_key="story_points",
        entity_field="story_points",
        aliases=("points", "sp", "story-points", "storyPoints"),
        transformer=_parse_story_points,
    ),
    FieldMapping(
        frontmatter_key="priority",
        entity_field="priority",
        aliases=("prio", "p"),
        transformer=_parse_priority,
    ),
    FieldMapping(
        frontmatter_key="status",
        entity_field="status",
        aliases=("state",),
        transformer=_parse_status,
    ),
    FieldMapping(
        frontmatter_key="assignee",
        entity_field="assignee",
        aliases=("assigned_to", "assigned-to", "owner"),
    ),
    FieldMapping(
        frontmatter_key="labels",
        entity_field="labels",
        aliases=("tags",),
        transformer=_parse_labels,
    ),
    FieldMapping(
        frontmatter_key="sprint",
        entity_field="sprint",
        aliases=("iteration", "milestone"),
    ),
    FieldMapping(
        frontmatter_key="technical_notes",
        entity_field="technical_notes",
        aliases=("tech_notes", "technical-notes", "technicalNotes", "notes"),
    ),
]

# Default field mappings for Epic
DEFAULT_EPIC_MAPPINGS: list[FieldMapping] = [
    FieldMapping(
        frontmatter_key="key",
        entity_field="key",
        aliases=("epic_key", "epic-key", "epicKey", "id"),
    ),
    FieldMapping(
        frontmatter_key="title",
        entity_field="title",
        aliases=("name", "summary"),
    ),
    FieldMapping(
        frontmatter_key="description",
        entity_field="description",
        aliases=("desc",),
    ),
]


# =============================================================================
# Core Functions
# =============================================================================


def extract_yaml_frontmatter(content: str) -> FrontmatterParseResult:
    """
    Extract YAML frontmatter from content.

    Args:
        content: Source content (markdown, etc.)

    Returns:
        FrontmatterParseResult with parsed data and metadata.
    """
    stripped = content.lstrip()

    if not stripped.startswith("---"):
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
        )

    # Find the end delimiter
    match = re.match(r"^---\s*\n([\s\S]*?)\n---[ \t]*\n?", stripped)
    if not match:
        # Unclosed frontmatter
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
            errors=["Unclosed YAML frontmatter (missing closing ---)"],
        )

    yaml_content = match.group(1)
    full_match = match.group(0)

    # Calculate positions (accounting for stripped whitespace)
    leading_ws = len(content) - len(stripped)
    start_line = content[:leading_ws].count("\n") + 1
    end_line = start_line + full_match.count("\n")

    try:
        data = yaml.safe_load(yaml_content) or {}
        if not isinstance(data, dict):
            return FrontmatterParseResult(
                data={},
                span=None,
                remaining_content=content,
                errors=[f"YAML frontmatter must be a mapping, got {type(data).__name__}"],
            )
    except yaml.YAMLError as e:
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
            errors=[f"Invalid YAML in frontmatter: {e}"],
        )

    span = FrontmatterSpan(
        start_line=start_line,
        end_line=end_line,
        start_offset=leading_ws,
        end_offset=leading_ws + len(full_match),
        format=FrontmatterFormat.YAML,
        raw_content=yaml_content,
    )

    remaining = content[leading_ws + len(full_match) :]

    return FrontmatterParseResult(
        data=data,
        span=span,
        remaining_content=remaining,
    )


def extract_html_comment_frontmatter(content: str) -> FrontmatterParseResult:
    """
    Extract YAML from HTML comment frontmatter.

    Supports:
    - <!-- yaml: ... --> (explicit yaml marker)
    - <!-- frontmatter: ... -->
    - <!-- metadata: ... -->

    Args:
        content: Source content

    Returns:
        FrontmatterParseResult with parsed data.
    """
    # Look for HTML comment at start of content (after optional whitespace)
    stripped = content.lstrip()

    # Pattern for YAML in HTML comment
    pattern = r"^<!--\s*(?:yaml|frontmatter|metadata)?\s*:?\s*\n?([\s\S]*?)\s*-->"
    match = re.match(pattern, stripped, re.IGNORECASE)

    if not match:
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
        )

    yaml_content = match.group(1)
    full_match = match.group(0)

    # Calculate positions
    leading_ws = len(content) - len(stripped)
    start_line = content[:leading_ws].count("\n") + 1
    end_line = start_line + full_match.count("\n")

    try:
        data = yaml.safe_load(yaml_content) or {}
        if not isinstance(data, dict):
            return FrontmatterParseResult(
                data={},
                span=None,
                remaining_content=content,
                errors=[f"HTML comment YAML must be a mapping, got {type(data).__name__}"],
            )
    except yaml.YAMLError as e:
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
            errors=[f"Invalid YAML in HTML comment: {e}"],
        )

    span = FrontmatterSpan(
        start_line=start_line,
        end_line=end_line,
        start_offset=leading_ws,
        end_offset=leading_ws + len(full_match),
        format=FrontmatterFormat.HTML_COMMENT,
        raw_content=yaml_content,
    )

    # Skip any whitespace/newlines after comment
    remaining = content[leading_ws + len(full_match) :].lstrip("\n")

    return FrontmatterParseResult(
        data=data,
        span=span,
        remaining_content=remaining,
    )


def extract_inline_frontmatter(content: str) -> list[tuple[int, dict[str, Any], str]]:
    """
    Extract inline frontmatter from HTML comments within content.

    Finds all <!-- yaml --> blocks that appear after story headers.

    Args:
        content: Source content

    Returns:
        List of (line_number, data, remaining_block_content) tuples.
    """
    results: list[tuple[int, dict[str, Any], str]] = []

    # Pattern for inline YAML comments
    pattern = r"<!--\s*\n?([\s\S]*?)\s*-->"

    for match in re.finditer(pattern, content):
        yaml_content = match.group(1).strip()

        # Skip if it looks like a regular HTML comment (not YAML)
        if not yaml_content or not re.search(r"\w+\s*:", yaml_content):
            continue

        try:
            data = yaml.safe_load(yaml_content)
            if isinstance(data, dict):
                # Calculate line number
                line_num = content[: match.start()].count("\n") + 1
                # Get content after this comment
                after = content[match.end() :]
                results.append((line_num, data, after))
        except yaml.YAMLError:
            # Not valid YAML, skip
            continue

    return results


def normalize_key(key: str, case_sensitive: bool = False) -> str:
    """Normalize a frontmatter key for matching."""
    if case_sensitive:
        return key
    # Convert to lowercase and normalize separators
    return key.lower().replace("-", "_").replace(" ", "_")


def find_mapping(
    key: str,
    mappings: list[FieldMapping],
    case_sensitive: bool = False,
) -> FieldMapping | None:
    """Find a field mapping for a given key."""
    normalized = normalize_key(key, case_sensitive)

    for mapping in mappings:
        mapping_key = normalize_key(mapping.frontmatter_key, case_sensitive)
        if normalized == mapping_key:
            return mapping

        for alias in mapping.aliases:
            if normalized == normalize_key(alias, case_sensitive):
                return mapping

    return None


def apply_mapping(
    data: dict[str, Any],
    mappings: list[FieldMapping],
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """
    Apply field mappings to transform frontmatter data.

    Args:
        data: Raw frontmatter data
        mappings: Field mappings to apply
        case_sensitive: Whether keys are case-sensitive

    Returns:
        Transformed data with entity field names.
    """
    result: dict[str, Any] = {}

    for key, value in data.items():
        mapping = find_mapping(key, mappings, case_sensitive)
        if mapping:
            # Apply transformer if present
            if mapping.transformer:
                value = mapping.transformer(value)
            result[mapping.entity_field] = value
        else:
            # Keep unmapped keys as-is
            result[key] = value

    return result


# =============================================================================
# Description Parsing
# =============================================================================


def parse_description_from_frontmatter(data: Any) -> Description | None:
    """
    Parse a Description value object from frontmatter data.

    Supports multiple formats:
    - String: "As a user, I want X, so that Y"
    - Dict: {as_a: role, i_want: want, so_that: benefit}
    - Dict: {role: role, want: want, benefit: benefit}

    Args:
        data: Frontmatter description data

    Returns:
        Description value object or None
    """
    if data is None:
        return None

    if isinstance(data, str):
        # Try to parse "As a..., I want..., so that..." format
        pattern = r"[Aa]s\s+(?:a[n]?\s+)?(.+?),?\s+[Ii]\s*want\s+(.+?),?\s+[Ss]o\s+that\s+(.+)"
        match = re.match(pattern, data, re.DOTALL)
        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )
        # Return as simple description (want only)
        return Description(role="", want=data.strip(), benefit="")

    if isinstance(data, dict):
        # Support both naming conventions
        role = data.get("as_a") or data.get("role") or data.get("as_a_role") or ""
        want = data.get("i_want") or data.get("want") or ""
        benefit = data.get("so_that") or data.get("benefit") or ""

        if role or want or benefit:
            return Description(
                role=str(role).strip(),
                want=str(want).strip(),
                benefit=str(benefit).strip(),
            )

    return None


# =============================================================================
# Acceptance Criteria Parsing
# =============================================================================


def parse_acceptance_criteria_from_frontmatter(data: Any) -> AcceptanceCriteria:
    """
    Parse AcceptanceCriteria from frontmatter data.

    Supports multiple formats:
    - List of strings: ["criterion 1", "criterion 2"]
    - List of dicts: [{criterion: "text", done: false}]
    - Dict with items: {items: [...], checked: [...]}

    Args:
        data: Frontmatter acceptance criteria data

    Returns:
        AcceptanceCriteria value object
    """
    if data is None:
        return AcceptanceCriteria.from_list([])

    items: list[str] = []
    checked: list[bool] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                items.append(item)
                checked.append(False)
            elif isinstance(item, dict):
                text = item.get("criterion") or item.get("text") or item.get("ac") or str(item)
                done = bool(item.get("done") or item.get("checked") or item.get("complete"))
                items.append(str(text))
                checked.append(done)

    elif isinstance(data, dict):
        # Support {items: [...], checked: [...]} format
        if "items" in data:
            items = [str(i) for i in data["items"]]
            checked = list(data.get("checked", [False] * len(items)))

    return AcceptanceCriteria.from_list(items, checked)


# =============================================================================
# Subtask Parsing
# =============================================================================


def parse_subtasks_from_frontmatter(data: Any) -> list[Subtask]:
    """
    Parse subtasks from frontmatter data.

    Supports multiple formats:
    - List of strings: ["subtask 1", "subtask 2"]
    - List of dicts: [{name: "task", story_points: 2, status: "planned"}]

    Args:
        data: Frontmatter subtasks data

    Returns:
        List of Subtask entities
    """
    if data is None or not isinstance(data, list):
        return []

    subtasks: list[Subtask] = []

    for i, item in enumerate(data):
        if isinstance(item, str):
            subtasks.append(
                Subtask(
                    number=i + 1,
                    name=item,
                    description="",
                    story_points=1,
                    status=Status.PLANNED,
                )
            )
        elif isinstance(item, dict):
            subtasks.append(
                Subtask(
                    number=item.get("number", i + 1),
                    name=item.get("name") or item.get("title") or "",
                    description=item.get("description") or "",
                    story_points=_parse_story_points(item.get("story_points", item.get("sp", 1))),
                    status=_parse_status(item.get("status", "planned")),
                    assignee=item.get("assignee"),
                    priority=_parse_priority(item.get("priority"))
                    if item.get("priority")
                    else None,
                )
            )

    return subtasks


# =============================================================================
# Story Parsing
# =============================================================================


def parse_story_from_frontmatter(
    data: dict[str, Any],
    config: FrontmatterConfig | None = None,
) -> UserStory:
    """
    Parse a UserStory from frontmatter data.

    Args:
        data: Frontmatter dictionary
        config: Optional configuration

    Returns:
        UserStory entity
    """
    config = config or FrontmatterConfig()

    # Build mappings list
    mappings = DEFAULT_STORY_MAPPINGS + config.custom_mappings

    # Apply mappings
    mapped = apply_mapping(data, mappings, config.case_sensitive)

    # Extract and parse special fields
    story_id = mapped.get("id", "STORY-000")
    title = mapped.get("title", "Untitled Story")

    # Parse complex fields
    description = parse_description_from_frontmatter(data.get("description"))
    acceptance = parse_acceptance_criteria_from_frontmatter(data.get("acceptance_criteria"))
    subtasks = parse_subtasks_from_frontmatter(data.get("subtasks"))

    # Parse commits
    commits: list[CommitRef] = []
    for commit_data in data.get("commits", []):
        if isinstance(commit_data, str):
            commits.append(CommitRef(hash=commit_data, message=""))
        elif isinstance(commit_data, dict):
            commits.append(
                CommitRef(
                    hash=commit_data.get("hash", ""),
                    message=commit_data.get("message", ""),
                )
            )

    # Parse links
    links: list[tuple[str, str]] = []
    for link_data in data.get("links", []):
        if isinstance(link_data, dict):
            link_type = link_data.get("type", "relates_to")
            target = link_data.get("target", link_data.get("key", ""))
            links.append((link_type, target))
        elif isinstance(link_data, str):
            links.append(("relates_to", link_data))

    return UserStory(
        id=StoryId(story_id),
        title=title,
        description=description,
        acceptance_criteria=acceptance,
        technical_notes=mapped.get("technical_notes", ""),
        story_points=mapped.get("story_points", 0),
        priority=mapped.get("priority", Priority.MEDIUM),
        status=mapped.get("status", Status.PLANNED),
        assignee=mapped.get("assignee"),
        labels=mapped.get("labels", []),
        sprint=mapped.get("sprint"),
        subtasks=subtasks,
        commits=commits,
        links=links,
    )


# =============================================================================
# Epic Parsing
# =============================================================================


def parse_epic_from_frontmatter(
    data: dict[str, Any],
    stories: list[UserStory] | None = None,
    config: FrontmatterConfig | None = None,
) -> Epic:
    """
    Parse an Epic from frontmatter data.

    Args:
        data: Frontmatter dictionary (epic section)
        stories: Optional list of stories to include
        config: Optional configuration

    Returns:
        Epic entity
    """
    config = config or FrontmatterConfig()

    # Apply epic mappings
    mapped = apply_mapping(data, DEFAULT_EPIC_MAPPINGS, config.case_sensitive)

    epic_key = mapped.get("key", "EPIC-0")
    title = mapped.get("title", "Untitled Epic")
    description = mapped.get("description", "")

    return Epic(
        key=IssueKey(epic_key),
        title=title,
        description=description,
        stories=stories or [],
    )


# =============================================================================
# FrontmatterParser - DocumentParserPort Implementation
# =============================================================================


class FrontmatterParser(DocumentParserPort):
    """
    Parser for markdown files with YAML frontmatter metadata.

    This parser allows using YAML frontmatter as an alternative to
    markdown tables for specifying story metadata. It's particularly
    useful for:
    - Single-story markdown files (one story per file)
    - Programmatic generation of story files
    - Integration with static site generators
    - Better IDE support (YAML validation)

    The parser can be used standalone or as a wrapper around MarkdownParser
    to enhance its capabilities with frontmatter support.
    """

    def __init__(
        self,
        config: FrontmatterConfig | None = None,
        fallback_parser: DocumentParserPort | None = None,
    ):
        """
        Initialize the frontmatter parser.

        Args:
            config: Parser configuration
            fallback_parser: Parser to use for remaining content (e.g., MarkdownParser)
        """
        self.config = config or FrontmatterConfig()
        self.fallback_parser = fallback_parser
        self.logger = logging.getLogger("FrontmatterParser")

    @property
    def name(self) -> str:
        return "Frontmatter"

    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown", ".mdx"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source contains frontmatter we can parse."""
        if isinstance(source, Path):
            if source.suffix.lower() not in self.supported_extensions:
                return False
            try:
                content = source.read_text(encoding="utf-8")
            except Exception:
                return False
        else:
            content = source

        # Check for frontmatter markers
        stripped = content.lstrip()
        has_yaml_frontmatter = stripped.startswith("---")
        has_comment_frontmatter = bool(
            re.match(r"<!--\s*(?:yaml|frontmatter|metadata)", stripped, re.IGNORECASE)
        )

        return has_yaml_frontmatter or has_comment_frontmatter

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from source with frontmatter."""
        content = self._get_content(source)
        result = self._extract_frontmatter(content)

        if not result.is_valid:
            for error in result.errors:
                self.logger.warning(f"Frontmatter error: {error}")

        stories: list[UserStory] = []

        if result.has_frontmatter:
            data = result.data

            # Check for multi-story format (stories array)
            if "stories" in data and isinstance(data["stories"], list):
                for story_data in data["stories"]:
                    if isinstance(story_data, dict):
                        story = parse_story_from_frontmatter(story_data, self.config)
                        stories.append(story)

            # Check for single-story format (id field at top level)
            elif "id" in data or "story_id" in data:
                story = parse_story_from_frontmatter(data, self.config)
                stories.append(story)

        # If we have a fallback parser, use it for remaining content
        if self.fallback_parser and result.remaining_content.strip():
            try:
                fallback_stories = self.fallback_parser.parse_stories(result.remaining_content)

                # Merge frontmatter data with fallback stories
                if result.has_frontmatter and fallback_stories:
                    stories = self._merge_stories(stories, fallback_stories)
                elif fallback_stories:
                    stories.extend(fallback_stories)
            except Exception as e:
                self.logger.warning(f"Fallback parser error: {e}")

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with stories from source with frontmatter."""
        content = self._get_content(source)
        result = self._extract_frontmatter(content)

        if not result.is_valid:
            for error in result.errors:
                self.logger.warning(f"Frontmatter error: {error}")

        epic: Epic | None = None
        stories: list[UserStory] = []

        if result.has_frontmatter:
            data = result.data

            # Check for epic metadata
            epic_data = data.get("epic", {})
            if isinstance(epic_data, dict) and epic_data:
                # Parse stories first
                if "stories" in data:
                    for story_data in data["stories"]:
                        if isinstance(story_data, dict):
                            stories.append(parse_story_from_frontmatter(story_data, self.config))

                epic = parse_epic_from_frontmatter(epic_data, stories, self.config)

            # Single story with epic key
            elif "id" in data:
                stories.append(parse_story_from_frontmatter(data, self.config))
                # Check for epic info at top level
                if "epic_key" in data or "epic" in data:
                    epic_key = data.get("epic_key") or data.get("epic")
                    epic = Epic(
                        key=IssueKey(epic_key) if isinstance(epic_key, str) else IssueKey("EPIC-0"),
                        title="",
                        stories=stories,
                    )

        # Use fallback parser for remaining content
        if self.fallback_parser and result.remaining_content.strip():
            try:
                fallback_epic = self.fallback_parser.parse_epic(result.remaining_content)
                if fallback_epic:
                    if epic:
                        # Merge epics
                        epic = Epic(
                            key=epic.key or fallback_epic.key,
                            title=epic.title or fallback_epic.title,
                            description=epic.description or fallback_epic.description,
                            stories=self._merge_stories(stories, fallback_epic.stories),
                        )
                    else:
                        epic = fallback_epic
                        if stories:
                            epic = Epic(
                                key=epic.key,
                                title=epic.title,
                                description=epic.description,
                                stories=self._merge_stories(stories, epic.stories),
                            )
            except Exception as e:
                self.logger.warning(f"Fallback parser error: {e}")

        # If we only have stories, create a minimal epic
        if stories and not epic:
            epic = Epic(
                key=IssueKey("EPIC-0"),
                title="Untitled Epic",
                stories=stories,
            )

        return epic

    def validate(self, source: str | Path) -> list[str]:
        """Validate source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        result = self._extract_frontmatter(content)
        errors.extend(result.errors)

        # Validate required fields in strict mode
        if self.config.strict and result.has_frontmatter:
            data = result.data

            # Check for stories or single story
            if "stories" not in data and "id" not in data and "epic" not in data:
                errors.append("Frontmatter must contain 'stories', 'id', or 'epic' key")

            # Validate individual stories
            stories_data = data.get("stories", [])
            if isinstance(stories_data, list):
                for i, story in enumerate(stories_data):
                    if isinstance(story, dict):
                        if "id" not in story:
                            errors.append(f"Story {i + 1} missing required 'id' field")

        # Use fallback parser for remaining content validation
        if self.fallback_parser and result.remaining_content.strip():
            fallback_errors = self.fallback_parser.validate(result.remaining_content)
            errors.extend(fallback_errors)

        return errors

    def _get_content(self, source: str | Path) -> str:
        """Get content from source."""
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8")

        # Check if string is a file path
        if isinstance(source, str) and "\n" not in source and len(source) < 4096:
            try:
                path = Path(source)
                if path.exists() and path.suffix.lower() in self.supported_extensions:
                    return path.read_text(encoding="utf-8")
            except OSError:
                pass

        return source

    def _extract_frontmatter(self, content: str) -> FrontmatterParseResult:
        """Extract frontmatter using configured formats."""
        for fmt in self.config.formats:
            if fmt == FrontmatterFormat.YAML:
                result = extract_yaml_frontmatter(content)
            elif fmt == FrontmatterFormat.HTML_COMMENT:
                result = extract_html_comment_frontmatter(content)
            else:
                continue

            if result.has_frontmatter or result.errors:
                return result

        # No frontmatter found
        return FrontmatterParseResult(
            data={},
            span=None,
            remaining_content=content,
        )

    def _merge_stories(
        self,
        frontmatter_stories: list[UserStory],
        inline_stories: list[UserStory],
    ) -> list[UserStory]:
        """Merge stories from frontmatter with inline-parsed stories."""
        if not frontmatter_stories:
            return inline_stories
        if not inline_stories:
            return frontmatter_stories

        # Build index of frontmatter stories by ID
        fm_by_id: dict[str, UserStory] = {str(s.id): s for s in frontmatter_stories}

        merged: list[UserStory] = []
        seen_ids: set[str] = set()

        # Merge matching stories
        for inline_story in inline_stories:
            story_id = str(inline_story.id)

            if story_id in fm_by_id:
                # Merge frontmatter data with inline data
                fm_story = fm_by_id[story_id]
                merged_story = self._merge_story(fm_story, inline_story)
                merged.append(merged_story)
                seen_ids.add(story_id)
            else:
                merged.append(inline_story)
                seen_ids.add(story_id)

        # Add frontmatter-only stories
        for story_id, fm_story in fm_by_id.items():
            if story_id not in seen_ids:
                merged.append(fm_story)

        return merged

    def _merge_story(self, fm_story: UserStory, inline_story: UserStory) -> UserStory:
        """Merge a frontmatter story with an inline-parsed story."""
        strategy = self.config.merge_strategy

        if strategy == MergeStrategy.FRONTMATTER_PRIORITY:
            # Frontmatter values take precedence
            return UserStory(
                id=fm_story.id or inline_story.id,
                title=fm_story.title or inline_story.title,
                description=fm_story.description or inline_story.description,
                acceptance_criteria=(
                    fm_story.acceptance_criteria
                    if fm_story.acceptance_criteria.items
                    else inline_story.acceptance_criteria
                ),
                technical_notes=fm_story.technical_notes or inline_story.technical_notes,
                story_points=fm_story.story_points or inline_story.story_points,
                priority=fm_story.priority
                if fm_story.priority != Priority.MEDIUM
                else inline_story.priority,
                status=fm_story.status
                if fm_story.status != Status.PLANNED
                else inline_story.status,
                assignee=fm_story.assignee or inline_story.assignee,
                labels=fm_story.labels or inline_story.labels,
                sprint=fm_story.sprint or inline_story.sprint,
                subtasks=fm_story.subtasks or inline_story.subtasks,
                commits=fm_story.commits or inline_story.commits,
                links=fm_story.links or inline_story.links,
            )

        if strategy == MergeStrategy.INLINE_PRIORITY:
            # Inline values take precedence
            return UserStory(
                id=inline_story.id or fm_story.id,
                title=inline_story.title or fm_story.title,
                description=inline_story.description or fm_story.description,
                acceptance_criteria=(
                    inline_story.acceptance_criteria
                    if inline_story.acceptance_criteria.items
                    else fm_story.acceptance_criteria
                ),
                technical_notes=inline_story.technical_notes or fm_story.technical_notes,
                story_points=inline_story.story_points or fm_story.story_points,
                priority=inline_story.priority
                if inline_story.priority != Priority.MEDIUM
                else fm_story.priority,
                status=inline_story.status
                if inline_story.status != Status.PLANNED
                else fm_story.status,
                assignee=inline_story.assignee or fm_story.assignee,
                labels=inline_story.labels or fm_story.labels,
                sprint=inline_story.sprint or fm_story.sprint,
                subtasks=inline_story.subtasks or fm_story.subtasks,
                commits=inline_story.commits or fm_story.commits,
                links=inline_story.links or fm_story.links,
            )

        if strategy == MergeStrategy.MERGE_ARRAYS:
            # Merge arrays, use frontmatter for scalars
            return UserStory(
                id=fm_story.id or inline_story.id,
                title=fm_story.title or inline_story.title,
                description=fm_story.description or inline_story.description,
                acceptance_criteria=AcceptanceCriteria.from_list(
                    list(
                        set(
                            fm_story.acceptance_criteria.items
                            + inline_story.acceptance_criteria.items
                        )
                    )
                ),
                technical_notes=fm_story.technical_notes or inline_story.technical_notes,
                story_points=fm_story.story_points or inline_story.story_points,
                priority=fm_story.priority
                if fm_story.priority != Priority.MEDIUM
                else inline_story.priority,
                status=fm_story.status
                if fm_story.status != Status.PLANNED
                else inline_story.status,
                assignee=fm_story.assignee or inline_story.assignee,
                labels=list(set(fm_story.labels + inline_story.labels)),
                sprint=fm_story.sprint or inline_story.sprint,
                subtasks=fm_story.subtasks + inline_story.subtasks,
                commits=fm_story.commits + inline_story.commits,
                links=fm_story.links + inline_story.links,
            )

        # Default: DEEP_MERGE - similar to FRONTMATTER_PRIORITY
        return self._merge_story(fm_story, inline_story)


# =============================================================================
# Factory Functions
# =============================================================================


def create_frontmatter_parser(
    fallback_parser: DocumentParserPort | None = None,
    merge_strategy: MergeStrategy = MergeStrategy.FRONTMATTER_PRIORITY,
    strict: bool = False,
    custom_mappings: list[FieldMapping] | None = None,
) -> FrontmatterParser:
    """
    Create a configured FrontmatterParser.

    Args:
        fallback_parser: Parser for remaining content (e.g., MarkdownParser)
        merge_strategy: How to merge frontmatter with inline content
        strict: Whether to fail on validation errors
        custom_mappings: Additional field mappings

    Returns:
        Configured FrontmatterParser
    """
    config = FrontmatterConfig(
        merge_strategy=merge_strategy,
        strict=strict,
        custom_mappings=custom_mappings or [],
    )
    return FrontmatterParser(config=config, fallback_parser=fallback_parser)


def create_markdown_with_frontmatter() -> FrontmatterParser:
    """
    Create a FrontmatterParser with MarkdownParser as fallback.

    This gives the best of both worlds - YAML frontmatter support
    plus full markdown parsing for story content.

    Returns:
        FrontmatterParser with MarkdownParser fallback
    """
    # Import here to avoid circular imports
    from .markdown import MarkdownParser

    return FrontmatterParser(fallback_parser=MarkdownParser())


def has_frontmatter(content: str) -> bool:
    """
    Check if content has YAML frontmatter.

    Args:
        content: Source content

    Returns:
        True if frontmatter is present
    """
    stripped = content.lstrip()
    return stripped.startswith("---") or bool(
        re.match(r"<!--\s*(?:yaml|frontmatter|metadata)", stripped, re.IGNORECASE)
    )


def strip_frontmatter(content: str) -> str:
    """
    Remove frontmatter from content.

    Args:
        content: Source content with frontmatter

    Returns:
        Content without frontmatter
    """
    result = extract_yaml_frontmatter(content)
    if result.has_frontmatter:
        return result.remaining_content

    result = extract_html_comment_frontmatter(content)
    if result.has_frontmatter:
        return result.remaining_content

    return content


def get_frontmatter(content: str) -> dict[str, Any]:
    """
    Extract just the frontmatter data from content.

    Args:
        content: Source content with frontmatter

    Returns:
        Frontmatter data dictionary
    """
    result = extract_yaml_frontmatter(content)
    if result.has_frontmatter:
        return result.data

    result = extract_html_comment_frontmatter(content)
    if result.has_frontmatter:
        return result.data

    return {}
