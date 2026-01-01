"""
Domain enums - Status, Priority, and other enumerated types.

Provides enum classes for strongly-typed domain values with parsing
and display capabilities.

Example:
    >>> status = Status.from_string("in progress")
    >>> print(status.emoji)  # 🔄
    >>> print(status.display_name)  # In Progress

    >>> priority = Priority.from_string("P0")
    >>> print(priority.jira_name)  # Highest
"""

from __future__ import annotations

from enum import Enum, auto


class Status(Enum):
    """Status of a story or subtask.

    Represents the workflow state of an issue. Provides parsing from
    various string formats including emoji indicators.

    Attributes:
        PLANNED: Not yet started (📋)
        OPEN: Ready to start (📂)
        IN_PROGRESS: Currently being worked on (🔄)
        IN_REVIEW: Under review or testing (👀)
        DONE: Completed successfully (✅)
        CANCELLED: Will not be completed (❌)
    """

    PLANNED = auto()
    OPEN = auto()
    IN_PROGRESS = auto()
    IN_REVIEW = auto()
    DONE = auto()
    CANCELLED = auto()

    @classmethod
    def from_string(cls, value: str) -> Status:
        """Parse status from various string formats.

        Handles emoji prefixes, different naming conventions, and
        common variations like 'in-progress', 'To Do', etc.

        Args:
            value: Status string to parse (case-insensitive).

        Returns:
            Matching Status enum value, defaults to PLANNED.

        Examples:
            >>> Status.from_string("done")  # Status.DONE
            >>> Status.from_string("✅ Complete")  # Status.DONE
            >>> Status.from_string("in-progress")  # Status.IN_PROGRESS
        """
        value = value.strip().lower()

        # Done variations
        if any(x in value for x in ["done", "resolved", "closed", "complete", "✅"]):
            return cls.DONE

        # In Progress variations
        if any(x in value for x in ["progress", "in-progress", "🔄", "active"]):
            return cls.IN_PROGRESS

        # In Review
        if any(x in value for x in ["review", "testing"]):
            return cls.IN_REVIEW

        # Open variations
        if any(x in value for x in ["open", "todo", "to do", "new"]):
            return cls.OPEN

        # Cancelled
        if any(x in value for x in ["cancel", "wontfix", "won't fix"]):
            return cls.CANCELLED

        # Not started variations (including empty checkbox emoji)
        if any(x in value for x in ["not started", "🔲", "backlog"]):
            return cls.PLANNED

        # Default to planned
        return cls.PLANNED

    @property
    def emoji(self) -> str:
        """Get emoji representation."""
        return {
            Status.PLANNED: "📋",
            Status.OPEN: "📂",
            Status.IN_PROGRESS: "🔄",
            Status.IN_REVIEW: "👀",
            Status.DONE: "✅",
            Status.CANCELLED: "❌",
        }[self]

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return {
            Status.PLANNED: "Planned",
            Status.OPEN: "Open",
            Status.IN_PROGRESS: "In Progress",
            Status.IN_REVIEW: "In Review",
            Status.DONE: "Done",
            Status.CANCELLED: "Cancelled",
        }[self]

    def is_complete(self) -> bool:
        """Check if this represents a completed state."""
        return self in (Status.DONE, Status.CANCELLED)

    def is_active(self) -> bool:
        """Check if this represents an active/working state."""
        return self in (Status.IN_PROGRESS, Status.IN_REVIEW)


class Priority(Enum):
    """Priority level for stories.

    Represents the importance/urgency of an issue. Provides parsing from
    P0-P3 notation, names, and emoji indicators.

    Attributes:
        CRITICAL: Highest priority, blockers (🔴, P0)
        HIGH: Important items (🟡, P1)
        MEDIUM: Normal priority (🟢, P2)
        LOW: Nice to have (⚪, P3)
    """

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()

    @classmethod
    def from_string(cls, value: str) -> Priority:
        """Parse priority from various string formats.

        Supports P0-P3 notation, emoji indicators, and descriptive names.

        Args:
            value: Priority string to parse (case-insensitive).

        Returns:
            Matching Priority enum value, defaults to MEDIUM.

        Examples:
            >>> Priority.from_string("P0")  # Priority.CRITICAL
            >>> Priority.from_string("high")  # Priority.HIGH
            >>> Priority.from_string("🔴")  # Priority.CRITICAL
        """
        value = value.strip().lower()

        if any(x in value for x in ["critical", "blocker", "🔴", "p0"]):
            return cls.CRITICAL
        if any(x in value for x in ["high", "🟡", "p1"]):
            return cls.HIGH
        if any(x in value for x in ["medium", "🟢", "p2"]):
            return cls.MEDIUM
        if any(x in value for x in ["low", "minor", "p3"]):
            return cls.LOW

        return cls.MEDIUM

    @property
    def emoji(self) -> str:
        """Get emoji representation."""
        return {
            Priority.CRITICAL: "🔴",
            Priority.HIGH: "🟡",
            Priority.MEDIUM: "🟢",
            Priority.LOW: "⚪",
        }[self]

    @property
    def jira_name(self) -> str:
        """Get Jira-compatible priority name."""
        return {
            Priority.CRITICAL: "Highest",
            Priority.HIGH: "High",
            Priority.MEDIUM: "Medium",
            Priority.LOW: "Low",
        }[self]

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.name.capitalize()


class IssueType(Enum):
    """Type of issue in the tracker.

    Represents the category of work item in an issue tracker.

    Attributes:
        EPIC: Large feature/initiative containing multiple stories.
        STORY: User-facing feature described in user story format.
        TASK: Technical work item.
        SUBTASK: Child task within a story.
        BUG: Defect or issue to fix.
        SPIKE: Research or investigation task.
    """

    EPIC = auto()
    STORY = auto()
    TASK = auto()
    SUBTASK = auto()
    BUG = auto()
    SPIKE = auto()

    @classmethod
    def from_string(cls, value: str) -> IssueType:
        """Parse issue type from string."""
        value = value.strip().lower().replace("-", "").replace(" ", "")

        mapping = {
            "epic": cls.EPIC,
            "story": cls.STORY,
            "userstory": cls.STORY,
            "task": cls.TASK,
            "subtask": cls.SUBTASK,
            "sub-task": cls.SUBTASK,
            "bug": cls.BUG,
            "defect": cls.BUG,
            "spike": cls.SPIKE,
            "research": cls.SPIKE,
        }

        return mapping.get(value, cls.TASK)
