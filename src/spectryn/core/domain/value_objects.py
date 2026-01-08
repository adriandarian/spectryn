"""
Value Objects - Immutable objects defined by their attributes.

Value objects are compared by value, not identity.
They should be immutable and self-validating.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoryId:
    """
    Unique identifier for a story within a markdown document.

    Supported formats:
    - PREFIX-NUMBER: US-001, EU-042, PROJ-123, FEAT-001 (hyphen separator)
    - PREFIX_NUMBER: PROJ_001, US_123 (underscore separator)
    - PREFIX/NUMBER: PROJ/001, US/123 (forward slash separator)
    - #NUMBER: #123, #42 (GitHub-style numeric IDs)
    - NUMBER: 123, 42 (purely numeric IDs)

    Accepts any alphanumeric prefix followed by a separator and number,
    or just a number (with optional # prefix).
    This allows organizations to use their own naming conventions.
    """

    value: str

    # Pattern for valid story IDs:
    # - PREFIX[-_/]NUMBER: letters, separator, digits (e.g., US-001, PROJ_123, FEAT/001)
    # - #NUMBER: GitHub-style (e.g., #123)
    # - NUMBER: purely numeric (e.g., 123)
    PATTERN = re.compile(r"^(?:[A-Z]+[-_/]\d+|#?\d+)$", re.IGNORECASE)

    # Separator characters used in PREFIX-NUMBER format
    SEPARATORS = "-_/"

    def __post_init__(self) -> None:
        # Normalize: strip whitespace, uppercase prefix (not # or purely numeric)
        normalized = self.value.strip()
        if normalized.startswith("#") or re.match(r"^\d+$", normalized):
            # Keep # prefix or purely numeric as-is
            pass
        else:
            # Has prefix - uppercase it
            normalized = normalized.upper()

        if normalized != self.value:
            object.__setattr__(self, "value", normalized)

    @classmethod
    def from_string(cls, value: str) -> StoryId:
        """Parse a story ID from string.

        Accepts formats:
        - PREFIX-NUMBER: US-001, EU-042, PROJ-123
        - PREFIX_NUMBER: PROJ_001, US_123
        - PREFIX/NUMBER: PROJ/001, US/123
        - #NUMBER: #123 (GitHub-style)
        - NUMBER: 123 (purely numeric)
        """
        return cls(value.strip())

    @property
    def prefix(self) -> str:
        """Extract the prefix portion of the story ID.

        For IDs like 'US-001', returns 'US'. For numeric IDs like
        '#123' or '123', returns an empty string.

        Returns:
            The prefix string, or empty string for numeric IDs.
        """
        # Check for any separator
        for sep in self.SEPARATORS:
            if sep in self.value:
                return self.value.split(sep)[0]
        # No prefix for #123 or purely numeric
        return ""

    @property
    def separator(self) -> str:
        """Extract the separator character (-, _, or /)."""
        for sep in self.SEPARATORS:
            if sep in self.value:
                return sep
        return ""

    @property
    def number(self) -> int:
        """Extract the numeric portion."""
        match = re.search(r"\d+", self.value)
        return int(match.group()) if match else 0

    @property
    def is_numeric(self) -> bool:
        """Check if this is a purely numeric ID (no prefix)."""
        stripped = self.value.lstrip("#")
        return stripped.isdigit()

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class IssueKey:
    """
    Issue tracker key.

    Supported formats:
    - PROJECT-NUMBER: PROJ-123, UPP-80006 (hyphen separator - Jira, Linear)
    - PROJECT_NUMBER: PROJ_123 (underscore separator)
    - PROJECT/NUMBER: PROJ/123 (forward slash separator)
    - #NUMBER: #123 (GitHub Issues style)
    - NUMBER: 123 (Azure DevOps, purely numeric)
    """

    value: str

    # Separator characters used in PROJECT-NUMBER format
    SEPARATORS = "-_/"

    def __post_init__(self) -> None:
        upper_val = self.value.upper()
        # Accept: PREFIX[-_/]NUMBER, #NUMBER, or just NUMBER
        has_prefix_separator = any(
            re.match(rf"^[A-Z]+{re.escape(sep)}\d+$", upper_val) for sep in self.SEPARATORS
        )
        is_numeric = re.match(r"^#?\d+$", self.value)

        if not has_prefix_separator and not is_numeric:
            raise ValueError(f"Invalid issue key format: {self.value}")

    @property
    def project(self) -> str:
        """Extract project key."""
        for sep in self.SEPARATORS:
            if sep in self.value:
                return self.value.split(sep)[0].upper()
        # No project for #123 or purely numeric
        return ""

    @property
    def separator(self) -> str:
        """Extract the separator character (-, _, or /)."""
        for sep in self.SEPARATORS:
            if sep in self.value:
                return sep
        return ""

    @property
    def number(self) -> int:
        """Extract issue number."""
        for sep in self.SEPARATORS:
            if sep in self.value:
                return int(self.value.split(sep)[1])
        # Handle #123 or purely numeric
        return int(self.value.lstrip("#"))

    @property
    def is_numeric(self) -> bool:
        """Check if this is a purely numeric ID (no project prefix)."""
        stripped = self.value.lstrip("#")
        return stripped.isdigit()

    def __str__(self) -> str:
        # Keep numeric IDs as-is, uppercase prefix-based IDs
        if self.is_numeric:
            return self.value
        return self.value.upper()


@dataclass(frozen=True)
class CommitRef:
    """Reference to a git commit."""

    hash: str
    message: str
    author: str | None = None

    @property
    def short_hash(self) -> str:
        """Get abbreviated hash (7 chars)."""
        return self.hash[:7]

    def __str__(self) -> str:
        return f"{self.short_hash}: {self.message}"


@dataclass(frozen=True)
class Description:
    """
    User story description in "As a / I want / So that" format.

    Immutable value object representing the story's purpose.
    """

    role: str
    want: str
    benefit: str
    additional_context: str = ""

    @classmethod
    def from_markdown(cls, text: str) -> Description | None:
        """Parse a Description from markdown formatted text.

        Looks for the standard user story format:
        - **As a** role
        - **I want** feature
        - **So that** benefit

        Args:
            text: Markdown text containing the user story description.

        Returns:
            Description instance if parsing succeeds, None otherwise.
        """
        pattern = r"\*\*As a\*\*\s*(.+?)\s*\n\s*\*\*I want\*\*\s*(.+?)\s*\n\s*\*\*So that\*\*\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)

        if not match:
            return None

        return cls(
            role=match.group(1).strip(),
            want=match.group(2).strip(),
            benefit=match.group(3).strip(),
        )

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        parts = [
            f"**As a** {self.role}",
            f"**I want** {self.want}",
            f"**So that** {self.benefit}",
        ]
        if self.additional_context:
            parts.append(f"\n{self.additional_context}")
        return "\n".join(parts)

    def to_plain_text(self) -> str:
        """Convert to plain text."""
        return f"As a {self.role}, I want {self.want}, so that {self.benefit}"

    def __str__(self) -> str:
        return self.to_plain_text()


@dataclass(frozen=True)
class AcceptanceCriteria:
    """
    Collection of acceptance criteria for a story.

    Each criterion is a checkable item.
    """

    items: tuple[str, ...] = field(default_factory=tuple)
    checked: tuple[bool, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Ensure checked matches items length
        if len(self.checked) != len(self.items):
            object.__setattr__(self, "checked", tuple([False] * len(self.items)))

    @classmethod
    def from_list(cls, items: list[str], checked: list[bool] | None = None) -> AcceptanceCriteria:
        """Create from list of items."""
        return cls(
            items=tuple(items),
            checked=tuple(checked) if checked else tuple([False] * len(items)),
        )

    def to_markdown(self) -> str:
        """Convert acceptance criteria to markdown checkbox format.

        Generates a list of markdown checkboxes, with [x] for completed
        items and [ ] for incomplete items.

        Returns:
            Markdown formatted string with one checkbox per line.
        """
        lines = []
        for item, is_checked in zip(self.items, self.checked, strict=False):
            checkbox = "[x]" if is_checked else "[ ]"
            lines.append(f"- {checkbox} {item}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[tuple[str, bool]]:
        return iter(zip(self.items, self.checked, strict=False))

    @property
    def completion_ratio(self) -> float:
        """Calculate the ratio of completed acceptance criteria.

        Returns:
            Float between 0.0 and 1.0 representing completion percentage.
            Returns 1.0 if there are no criteria defined.
        """
        if not self.items:
            return 1.0
        return sum(self.checked) / len(self.items)
