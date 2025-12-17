"""
Domain enums - Status, Priority, and other enumerated types.
"""

from __future__ import annotations

from enum import Enum, auto


class Status(Enum):
    """Status of a story or subtask."""

    PLANNED = auto()
    OPEN = auto()
    IN_PROGRESS = auto()
    IN_REVIEW = auto()
    DONE = auto()
    CANCELLED = auto()

    @classmethod
    def from_string(cls, value: str) -> Status:
        """
        Parse status from various string formats.

        Handles emoji prefixes, different naming conventions, etc.
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
    """Priority level for stories."""

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()

    @classmethod
    def from_string(cls, value: str) -> Priority:
        """Parse priority from string."""
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
    def display_name(self) -> str:
        """Human-readable name."""
        return self.name.capitalize()


class IssueType(Enum):
    """Type of issue in the tracker."""

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
