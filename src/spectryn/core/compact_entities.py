"""
Compact Entities - Memory-optimized versions of domain entities.

Provides __slots__-based implementations for reduced memory footprint.
Use these when processing large numbers of entities.

Memory savings:
- Regular dataclass: ~400 bytes per instance overhead
- Slots-based class: ~100 bytes per instance overhead

Example:
    >>> from spectryn.core.compact_entities import CompactUserStory, CompactSubtask
    >>>
    >>> # Use compact entities for bulk processing
    >>> stories = [CompactUserStory.from_dict(d) for d in large_dataset]
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .domain.enums import Priority, Status
from .domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from .memory import intern_string


class CompactSubtask:
    """
    Memory-efficient subtask using __slots__.

    Saves ~70% memory compared to dataclass version.
    """

    __slots__ = (
        "assignee",
        "description",
        "external_key",
        "id",
        "name",
        "number",
        "priority",
        "status",
        "story_points",
    )

    def __init__(
        self,
        id: str = "",
        number: int = 0,
        name: str = "",
        description: str = "",
        story_points: int = 1,
        status: Status = Status.PLANNED,
        priority: Priority | None = None,
        assignee: str | None = None,
        external_key: IssueKey | None = None,
    ):
        self.id = id or self._generate_id()
        self.number = number
        self.name = intern_string(name)
        self.description = description
        self.story_points = story_points
        self.status = status
        self.priority = priority
        self.assignee = intern_string(assignee) if assignee else None
        self.external_key = external_key

    @staticmethod
    def _generate_id() -> str:
        """Generate a short unique ID."""
        import uuid

        return str(uuid.uuid4())[:8]

    def normalize_name(self) -> str:
        """Normalize name for matching."""
        name = self.name.lower()
        name = re.sub(r"[^\w\s]", " ", name)
        return " ".join(name.split())

    def matches(self, other: CompactSubtask) -> bool:
        """Check if this subtask matches another."""
        self_normalized = self.normalize_name()[:30]
        other_normalized = other.normalize_name()[:30]
        return self_normalized in other_normalized or other_normalized in self_normalized

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompactSubtask:
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            number=data.get("number", 0),
            name=data.get("name", ""),
            description=data.get("description", ""),
            story_points=data.get("story_points", 1),
            status=Status[data["status"]] if "status" in data else Status.PLANNED,
            assignee=data.get("assignee"),
            external_key=IssueKey(data["external_key"]) if data.get("external_key") else None,
        )

    def __repr__(self) -> str:
        return f"CompactSubtask(id={self.id!r}, name={self.name!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompactSubtask):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class CompactComment:
    """Memory-efficient comment using __slots__."""

    __slots__ = ("_commits", "author", "body", "comment_type", "created_at", "id")

    def __init__(
        self,
        id: str = "",
        body: str = "",
        author: str | None = None,
        created_at: datetime | None = None,
        comment_type: str = "text",
        commits: list[CommitRef] | None = None,
    ):
        self.id = id or self._generate_id()
        self.body = body
        self.author = intern_string(author) if author else None
        self.created_at = created_at
        self.comment_type = intern_string(comment_type)
        self._commits: tuple[CommitRef, ...] = tuple(commits) if commits else ()

    @staticmethod
    def _generate_id() -> str:
        import uuid

        return str(uuid.uuid4())[:8]

    @property
    def commits(self) -> tuple[CommitRef, ...]:
        """Get commits as tuple (immutable)."""
        return self._commits

    def is_commits_comment(self) -> bool:
        """Check if this is a commits table comment."""
        return self.comment_type == "commits" or bool(self._commits)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "body": self.body,
            "author": self.author,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "comment_type": self.comment_type,
            "commits": [{"hash": c.hash, "message": c.message} for c in self._commits],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompactComment:
        """Create from dictionary."""
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        commits = [CommitRef(hash=c["hash"], message=c["message"]) for c in data.get("commits", [])]

        return cls(
            id=data.get("id", ""),
            body=data.get("body", ""),
            author=data.get("author"),
            created_at=created_at,
            comment_type=data.get("comment_type", "text"),
            commits=commits,
        )

    def __repr__(self) -> str:
        return f"CompactComment(id={self.id!r}, author={self.author!r})"


class CompactUserStory:
    """
    Memory-efficient user story using __slots__.

    Saves ~60% memory compared to dataclass version.
    Uses tuples instead of lists for immutable collections.
    """

    __slots__ = (
        "_attachments",
        "_comments",
        "_commits",
        "_labels",
        "_links",
        "_subtasks",
        "acceptance_criteria",
        "assignee",
        "content_hash",
        "description",
        "external_key",
        "external_url",
        "id",
        "last_synced",
        "priority",
        "sprint",
        "status",
        "story_points",
        "sync_status",
        "technical_notes",
        "title",
    )

    def __init__(
        self,
        id: StoryId,
        title: str,
        description: Description | None = None,
        acceptance_criteria: AcceptanceCriteria | None = None,
        technical_notes: str = "",
        story_points: int = 0,
        priority: Priority = Priority.MEDIUM,
        status: Status = Status.PLANNED,
        assignee: str | None = None,
        labels: list[str] | None = None,
        sprint: str | None = None,
        subtasks: list[CompactSubtask] | None = None,
        commits: list[CommitRef] | None = None,
        comments: list[CompactComment] | None = None,
        attachments: list[str] | None = None,
        links: list[tuple[str, str]] | None = None,
        external_key: IssueKey | None = None,
        external_url: str | None = None,
        last_synced: datetime | None = None,
        sync_status: str | None = None,
        content_hash: str | None = None,
    ):
        self.id = id
        self.title = intern_string(title)
        self.description = description
        self.acceptance_criteria = acceptance_criteria or AcceptanceCriteria.from_list([])
        self.technical_notes = technical_notes
        self.story_points = story_points
        self.priority = priority
        self.status = status
        self.assignee = intern_string(assignee) if assignee else None
        self._labels: tuple[str, ...] = tuple(intern_string(l) for l in (labels or []))
        self.sprint = intern_string(sprint) if sprint else None
        self._subtasks: tuple[CompactSubtask, ...] = tuple(subtasks or [])
        self._commits: tuple[CommitRef, ...] = tuple(commits or [])
        self._comments: tuple[CompactComment, ...] = tuple(comments or [])
        self._attachments: tuple[str, ...] = tuple(attachments or [])
        self._links: tuple[tuple[str, str], ...] = tuple(links or [])
        self.external_key = external_key
        self.external_url = external_url
        self.last_synced = last_synced
        self.sync_status = intern_string(sync_status) if sync_status else None
        self.content_hash = content_hash

    @property
    def labels(self) -> tuple[str, ...]:
        """Get labels as tuple."""
        return self._labels

    @property
    def subtasks(self) -> tuple[CompactSubtask, ...]:
        """Get subtasks as tuple."""
        return self._subtasks

    @property
    def commits(self) -> tuple[CommitRef, ...]:
        """Get commits as tuple."""
        return self._commits

    @property
    def comments(self) -> tuple[CompactComment, ...]:
        """Get comments as tuple."""
        return self._comments

    @property
    def attachments(self) -> tuple[str, ...]:
        """Get attachments as tuple."""
        return self._attachments

    @property
    def links(self) -> tuple[tuple[str, str], ...]:
        """Get links as tuple."""
        return self._links

    def normalize_title(self) -> str:
        """Normalize title for matching."""
        title = self.title.lower()
        title = re.sub(r"\s*\(future\)\s*$", "", title)
        title = re.sub(r"[^\w\s]", " ", title)
        return " ".join(title.split())

    def matches_title(self, other_title: str) -> bool:
        """Check if this story matches an external title."""
        self_normalized = self.normalize_title()
        other_normalized = re.sub(r"[^\w\s]", " ", other_title.lower())
        other_normalized = " ".join(other_normalized.split())
        return (
            self_normalized == other_normalized
            or self_normalized in other_normalized
            or other_normalized in self_normalized
        )

    def get_full_description(self) -> str:
        """Get complete description with acceptance criteria."""
        parts = []
        if self.description:
            parts.append(self.description.to_markdown())
        if self.acceptance_criteria:
            parts.append("\n## Acceptance Criteria\n")
            parts.append(self.acceptance_criteria.to_markdown())
        if self.technical_notes:
            parts.append(f"\n## Technical Notes\n{self.technical_notes}")
        return "\n".join(parts)

    def find_subtask(self, name: str) -> CompactSubtask | None:
        """Find a subtask by name."""
        name_lower = name.lower()[:30]
        for subtask in self._subtasks:
            subtask_lower = subtask.normalize_name()[:30]
            if name_lower in subtask_lower or subtask_lower in name_lower:
                return subtask
        return None

    def has_commits(self) -> bool:
        """Check if story has commits."""
        return bool(self._commits)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
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
            "labels": list(self._labels),
            "subtasks": [st.to_dict() for st in self._subtasks],
            "commits": [{"hash": c.hash, "message": c.message} for c in self._commits],
            "comments": [c.to_dict() for c in self._comments],
            "attachments": list(self._attachments),
            "links": [{"type": t, "target": k} for t, k in self._links],
            "external_key": str(self.external_key) if self.external_key else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompactUserStory:
        """Create from dictionary."""
        return cls(
            id=StoryId(data["id"]),
            title=data["title"],
            description=Description(**data["description"]) if data.get("description") else None,
            story_points=data.get("story_points", 0),
            priority=Priority[data["priority"]] if "priority" in data else Priority.MEDIUM,
            status=Status[data["status"]] if "status" in data else Status.PLANNED,
            assignee=data.get("assignee"),
            labels=data.get("labels", []),
            subtasks=[CompactSubtask.from_dict(s) for s in data.get("subtasks", [])],
            commits=[
                CommitRef(hash=c["hash"], message=c["message"]) for c in data.get("commits", [])
            ],
            comments=[CompactComment.from_dict(c) for c in data.get("comments", [])],
            attachments=data.get("attachments", []),
            links=[(l["type"], l["target"]) for l in data.get("links", [])],
            external_key=IssueKey(data["external_key"]) if data.get("external_key") else None,
        )

    def __repr__(self) -> str:
        return f"CompactUserStory(id={self.id!r}, title={self.title!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompactUserStory):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class CompactEpic:
    """Memory-efficient epic using __slots__."""

    __slots__ = (
        "_child_epics",
        "_stories",
        "created_at",
        "description",
        "key",
        "level",
        "parent_key",
        "priority",
        "status",
        "summary",
        "title",
        "updated_at",
    )

    def __init__(
        self,
        key: IssueKey,
        title: str,
        summary: str = "",
        description: str = "",
        status: Status = Status.PLANNED,
        priority: Priority = Priority.MEDIUM,
        parent_key: IssueKey | None = None,
        level: str = "epic",
        stories: list[CompactUserStory] | None = None,
        child_epics: list[CompactEpic] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.key = key
        self.title = intern_string(title)
        self.summary = summary
        self.description = description
        self.status = status
        self.priority = priority
        self.parent_key = parent_key
        self.level = intern_string(level)
        self._stories: tuple[CompactUserStory, ...] = tuple(stories or [])
        self._child_epics: tuple[CompactEpic, ...] = tuple(child_epics or [])
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def stories(self) -> tuple[CompactUserStory, ...]:
        """Get stories as tuple."""
        return self._stories

    @property
    def child_epics(self) -> tuple[CompactEpic, ...]:
        """Get child epics as tuple."""
        return self._child_epics

    def find_story(self, story_id: StoryId) -> CompactUserStory | None:
        """Find a story by ID."""
        for story in self._stories:
            if story.id == story_id:
                return story
        return None

    def find_story_by_title(self, title: str) -> CompactUserStory | None:
        """Find a story by title."""
        for story in self._stories:
            if story.matches_title(title):
                return story
        return None

    @property
    def total_story_points(self) -> int:
        """Calculate total story points."""
        return sum(s.story_points for s in self._stories)

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if not self._stories:
            return 0.0
        done = sum(1 for s in self._stories if s.status.is_complete())
        return (done / len(self._stories)) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": str(self.key),
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "status": self.status.name,
            "priority": self.priority.name,
            "parent_key": str(self.parent_key) if self.parent_key else None,
            "level": self.level,
            "stories": [s.to_dict() for s in self._stories],
            "child_epics": [e.to_dict() for e in self._child_epics],
            "total_story_points": self.total_story_points,
            "completion_percentage": self.completion_percentage,
        }

    def __repr__(self) -> str:
        return f"CompactEpic(key={self.key!r}, title={self.title!r})"


def estimate_memory_savings(num_stories: int = 1000, avg_subtasks: int = 3) -> dict[str, Any]:
    """
    Estimate memory savings from using compact entities.

    Args:
        num_stories: Number of stories to estimate for
        avg_subtasks: Average subtasks per story

    Returns:
        Dictionary with memory estimates
    """
    # Rough estimates based on typical object sizes
    regular_story_overhead = 400  # bytes
    compact_story_overhead = 120  # bytes
    regular_subtask_overhead = 200
    compact_subtask_overhead = 80

    total_regular = (
        num_stories * regular_story_overhead + num_stories * avg_subtasks * regular_subtask_overhead
    )
    total_compact = (
        num_stories * compact_story_overhead + num_stories * avg_subtasks * compact_subtask_overhead
    )

    savings = total_regular - total_compact
    savings_pct = (savings / total_regular) * 100 if total_regular > 0 else 0

    return {
        "num_stories": num_stories,
        "avg_subtasks": avg_subtasks,
        "regular_bytes": total_regular,
        "compact_bytes": total_compact,
        "savings_bytes": savings,
        "savings_percent": savings_pct,
        "regular_mb": total_regular / (1024 * 1024),
        "compact_mb": total_compact / (1024 * 1024),
    }


__all__ = [
    "CompactComment",
    "CompactEpic",
    "CompactSubtask",
    "CompactUserStory",
    "estimate_memory_savings",
]
