"""
Domain Entities - Objects with identity that persist over time.

Entities are mutable and have a unique identifier.
They represent the core business objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from .enums import Priority, Status
from .value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)


@dataclass
class Subtask:
    """
    A subtask within a user story.

    Subtasks break down stories into smaller, actionable items.
    """

    id: str = field(default_factory=lambda: str(uuid4())[:8])
    number: int = 0
    name: str = ""
    description: str = ""
    story_points: int = 1
    status: Status = Status.PLANNED
    priority: Priority | None = None
    assignee: str | None = None

    # External references (populated when synced)
    external_key: IssueKey | None = None

    def normalize_name(self) -> str:
        """Normalize the subtask name for fuzzy matching.

        Converts the name to lowercase and normalizes whitespace and
        punctuation to enable reliable comparison between subtasks
        from different sources.

        Returns:
            Normalized name string with consistent formatting.
        """
        name = self.name.lower()
        name = re.sub(r"[^\w\s]", " ", name)
        return " ".join(name.split())

    def matches(self, other: Subtask) -> bool:
        """Check if this subtask matches another using fuzzy name matching.

        Performs a case-insensitive comparison of the first 30 characters
        of normalized names, checking if either name contains the other.

        Args:
            other: The subtask to compare against.

        Returns:
            True if the subtasks are considered a match.
        """
        self_normalized = self.normalize_name()[:30]
        other_normalized = other.normalize_name()[:30]
        return self_normalized in other_normalized or other_normalized in self_normalized

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "description": self.description,
            "story_points": self.story_points,
            "status": self.status.name,
            "assignee": self.assignee,
            "external_key": str(self.external_key) if self.external_key else None,
        }


@dataclass
class Comment:
    """A comment on an issue."""

    id: str = field(default_factory=lambda: str(uuid4())[:8])
    body: str = ""
    author: str | None = None
    created_at: datetime | None = None
    comment_type: str = "text"  # text, commits, etc.

    # For commits comments
    commits: list[CommitRef] = field(default_factory=list)

    def is_commits_comment(self) -> bool:
        """Check if this is a commits table comment."""
        return self.comment_type == "commits" or bool(self.commits)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "body": self.body,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "comment_type": self.comment_type,
            "commits": [{"hash": c.hash, "message": c.message} for c in self.commits],
        }


@dataclass
class UserStory:
    """
    A user story - the primary work item.

    User stories capture requirements in a user-centric format
    and can contain subtasks, acceptance criteria, and commits.
    """

    # Identity
    id: StoryId
    title: str

    # Content
    description: Description | None = None
    acceptance_criteria: AcceptanceCriteria = field(
        default_factory=lambda: AcceptanceCriteria.from_list([])
    )
    technical_notes: str = ""

    # Metadata
    story_points: int = 0
    priority: Priority = Priority.MEDIUM
    status: Status = Status.PLANNED
    assignee: str | None = None
    labels: list[str] = field(default_factory=list)
    sprint: str | None = None  # Sprint/iteration name

    # Children
    subtasks: list[Subtask] = field(default_factory=list)
    commits: list[CommitRef] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)

    # Attachments (file references)
    attachments: list[str] = field(default_factory=list)  # List of file paths

    # Links to other issues (cross-project linking)
    links: list[tuple[str, str]] = field(default_factory=list)  # [(link_type, target_key), ...]

    # External references
    external_key: IssueKey | None = None
    external_url: str | None = None

    # Sync metadata (populated from source file tracker info)
    last_synced: datetime | None = None
    sync_status: str | None = None  # synced, pending, modified, conflict
    content_hash: str | None = None

    def normalize_title(self) -> str:
        """Normalize the title for matching with external issues.

        Performs several normalizations:
        - Converts to lowercase
        - Removes common suffixes like '(future)'
        - Normalizes punctuation to spaces
        - Collapses multiple whitespace

        Returns:
            Normalized title suitable for fuzzy matching.
        """
        title = self.title.lower()
        # Remove common suffixes
        title = re.sub(r"\s*\(future\)\s*$", "", title)
        # Normalize whitespace and punctuation
        title = re.sub(r"[^\w\s]", " ", title)
        return " ".join(title.split())

    def matches_title(self, other_title: str) -> bool:
        """Check if this story matches an external title using fuzzy matching.

        Normalizes both titles and checks for equality or substring match
        in either direction.

        Args:
            other_title: The external issue title to compare against.

        Returns:
            True if titles are considered a match.
        """
        self_normalized = self.normalize_title()
        other_normalized = re.sub(r"[^\w\s]", " ", other_title.lower())
        other_normalized = " ".join(other_normalized.split())

        return (
            self_normalized == other_normalized
            or self_normalized in other_normalized
            or other_normalized in self_normalized
        )

    def get_full_description(self) -> str:
        """Get the complete description including acceptance criteria and notes.

        Assembles a full markdown description by combining:
        - The main story description
        - Acceptance criteria section
        - Technical notes section

        Returns:
            Complete markdown-formatted description string.
        """
        parts = []

        if self.description:
            parts.append(self.description.to_markdown())

        if self.acceptance_criteria:
            parts.append("\n## Acceptance Criteria\n")
            parts.append(self.acceptance_criteria.to_markdown())

        if self.technical_notes:
            parts.append(f"\n## Technical Notes\n{self.technical_notes}")

        return "\n".join(parts)

    def find_subtask(self, name: str) -> Subtask | None:
        """Find a subtask by name using fuzzy matching.

        Searches through the story's subtasks and returns the first one
        whose normalized name matches the given name (case-insensitive,
        first 30 characters).

        Args:
            name: The subtask name to search for.

        Returns:
            The matching Subtask, or None if not found.
        """
        name_lower = name.lower()[:30]
        for subtask in self.subtasks:
            subtask_lower = subtask.normalize_name()[:30]
            if name_lower in subtask_lower or subtask_lower in name_lower:
                return subtask
        return None

    def has_commits(self) -> bool:
        """Check if story has associated commits."""
        return bool(self.commits)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description.to_markdown() if self.description else None,
            "acceptance_criteria": list(self.acceptance_criteria.items),
            "technical_notes": self.technical_notes,
            "story_points": self.story_points,
            "priority": self.priority.name,
            "status": self.status.name,
            "assignee": self.assignee,
            "labels": self.labels,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "commits": [{"hash": c.hash, "message": c.message} for c in self.commits],
            "comments": [c.to_dict() for c in self.comments],
            "attachments": self.attachments,
            "links": [{"type": link_type, "target": target} for link_type, target in self.links],
            "external_key": str(self.external_key) if self.external_key else None,
        }


@dataclass
class Epic:
    """
    An epic - a collection of related user stories.

    Epics represent large features or initiatives that are
    broken down into multiple user stories.
    """

    # Identity
    key: IssueKey
    title: str

    # Content
    summary: str = ""
    description: str = ""

    # Metadata
    status: Status = Status.PLANNED
    priority: Priority = Priority.MEDIUM

    # Hierarchy
    parent_key: IssueKey | None = None  # Parent epic for multi-level hierarchies
    level: str = "epic"  # Hierarchy level (portfolio, initiative, epic, feature)

    # Children
    stories: list[UserStory] = field(default_factory=list)
    child_epics: list[Epic] = field(default_factory=list)  # Child epics

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def find_story(self, story_id: StoryId) -> UserStory | None:
        """Find a story by its unique identifier.

        Args:
            story_id: The StoryId to search for.

        Returns:
            The matching UserStory, or None if not found.
        """
        for story in self.stories:
            if story.id == story_id:
                return story
        return None

    def find_story_by_title(self, title: str) -> UserStory | None:
        """Find a story by title using fuzzy matching.

        Searches through the epic's stories and returns the first one
        whose title matches using normalized comparison.

        Args:
            title: The story title to search for.

        Returns:
            The matching UserStory, or None if not found.
        """
        for story in self.stories:
            if story.matches_title(title):
                return story
        return None

    @property
    def total_story_points(self) -> int:
        """Calculate total story points."""
        return sum(s.story_points for s in self.stories)

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage based on done stories."""
        if not self.stories:
            return 0.0
        done = sum(1 for s in self.stories if s.status.is_complete())
        return (done / len(self.stories)) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "key": str(self.key),
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "status": self.status.name,
            "priority": self.priority.name,
            "parent_key": str(self.parent_key) if self.parent_key else None,
            "level": self.level,
            "stories": [s.to_dict() for s in self.stories],
            "child_epics": [e.to_dict() for e in self.child_epics],
            "total_story_points": self.total_story_points,
            "completion_percentage": self.completion_percentage,
        }
