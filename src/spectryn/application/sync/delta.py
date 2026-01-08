"""
Delta Sync - Only sync fields that have actually changed.

This module extends incremental sync by tracking changes at the field level,
enabling more granular updates that:
- Reduce API calls by only updating changed fields
- Preserve remote changes to fields not modified locally
- Support partial sync by field selection

Components:
- FieldChange: Represents a change to a specific field
- DeltaTracker: Compares local and remote states to find deltas
- DeltaSyncResult: Results with field-level change stats
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import UserStory
from spectryn.core.ports.issue_tracker import IssueData


logger = logging.getLogger(__name__)


class SyncableField(Enum):
    """Fields that can be synced individually."""

    TITLE = "title"
    DESCRIPTION = "description"
    STATUS = "status"
    STORY_POINTS = "story_points"
    PRIORITY = "priority"
    ASSIGNEE = "assignee"
    LABELS = "labels"
    DUE_DATE = "due_date"
    SUBTASKS = "subtasks"
    COMMENTS = "comments"
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    TECHNICAL_NOTES = "technical_notes"

    @classmethod
    def content_fields(cls) -> set[SyncableField]:
        """Fields that represent story content."""
        return {
            cls.TITLE,
            cls.DESCRIPTION,
            cls.ACCEPTANCE_CRITERIA,
            cls.TECHNICAL_NOTES,
        }

    @classmethod
    def metadata_fields(cls) -> set[SyncableField]:
        """Fields that represent metadata."""
        return {
            cls.STATUS,
            cls.STORY_POINTS,
            cls.PRIORITY,
            cls.ASSIGNEE,
            cls.LABELS,
            cls.DUE_DATE,
        }


class ChangeDirection(Enum):
    """Direction of a change."""

    LOCAL_TO_REMOTE = "push"  # Push local change to tracker
    REMOTE_TO_LOCAL = "pull"  # Pull remote change to local
    CONFLICT = "conflict"  # Both sides changed


@dataclass
class FieldChange:
    """
    Represents a change to a single field.

    Tracks what changed, the old/new values, and sync direction.
    """

    field: SyncableField
    direction: ChangeDirection
    local_value: Any
    remote_value: Any
    base_value: Any | None = None  # Value at last sync

    # Hashes for comparison
    local_hash: str = ""
    remote_hash: str = ""
    base_hash: str = ""

    # Metadata
    story_id: str = ""
    issue_key: str = ""

    def __post_init__(self) -> None:
        if not self.local_hash:
            self.local_hash = self._hash_value(self.local_value)
        if not self.remote_hash:
            self.remote_hash = self._hash_value(self.remote_value)
        if self.base_value is not None and not self.base_hash:
            self.base_hash = self._hash_value(self.base_value)

    @staticmethod
    def _hash_value(value: Any) -> str:
        """Compute hash of a value."""
        if value is None:
            return "null"
        content = json.dumps(value, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    @property
    def needs_push(self) -> bool:
        """Check if this change needs to be pushed to remote."""
        return self.direction == ChangeDirection.LOCAL_TO_REMOTE

    @property
    def needs_pull(self) -> bool:
        """Check if this change needs to be pulled from remote."""
        return self.direction == ChangeDirection.REMOTE_TO_LOCAL

    @property
    def is_conflict(self) -> bool:
        """Check if this is a conflict."""
        return self.direction == ChangeDirection.CONFLICT

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field.value,
            "direction": self.direction.value,
            "local_value": self.local_value,
            "remote_value": self.remote_value,
            "base_value": self.base_value,
            "local_hash": self.local_hash,
            "remote_hash": self.remote_hash,
            "base_hash": self.base_hash,
            "story_id": self.story_id,
            "issue_key": self.issue_key,
        }


@dataclass
class StoryDelta:
    """
    Delta (difference) for a single story.

    Contains all field-level changes detected for a story.
    """

    story_id: str
    issue_key: str
    changes: list[FieldChange] = field(default_factory=list)

    # Is this a new story (not in tracker)?
    is_new: bool = False

    # Is this story deleted locally?
    is_deleted_locally: bool = False

    # Is this story deleted remotely?
    is_deleted_remotely: bool = False

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.changes) or self.is_new or self.is_deleted_locally

    @property
    def push_changes(self) -> list[FieldChange]:
        """Get changes that need to be pushed."""
        return [c for c in self.changes if c.needs_push]

    @property
    def pull_changes(self) -> list[FieldChange]:
        """Get changes that need to be pulled."""
        return [c for c in self.changes if c.needs_pull]

    @property
    def conflicts(self) -> list[FieldChange]:
        """Get conflicting changes."""
        return [c for c in self.changes if c.is_conflict]

    @property
    def changed_fields(self) -> set[SyncableField]:
        """Get set of changed fields."""
        return {c.field for c in self.changes}

    def get_change(self, field_name: SyncableField) -> FieldChange | None:
        """Get change for a specific field."""
        for change in self.changes:
            if change.field == field_name:
                return change
        return None

    def add_change(self, change: FieldChange) -> None:
        """Add a field change."""
        change.story_id = self.story_id
        change.issue_key = self.issue_key
        self.changes.append(change)

    def summary(self) -> str:
        """Generate human-readable summary."""
        if self.is_new:
            return f"{self.story_id}: NEW"
        if self.is_deleted_locally:
            return f"{self.story_id}: DELETED locally"
        if not self.changes:
            return f"{self.story_id}: no changes"

        push_count = len(self.push_changes)
        pull_count = len(self.pull_changes)
        conflict_count = len(self.conflicts)

        parts = [self.story_id]
        if push_count:
            parts.append(f"↑{push_count}")
        if pull_count:
            parts.append(f"↓{pull_count}")
        if conflict_count:
            parts.append(f"⚠{conflict_count}")

        return " ".join(parts)


@dataclass
class DeltaSyncResult:
    """
    Result of delta sync analysis.

    Contains all deltas for all stories with statistics.
    """

    deltas: list[StoryDelta] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Statistics
    total_stories: int = 0
    stories_with_changes: int = 0
    stories_unchanged: int = 0
    new_stories: int = 0

    # Field-level stats
    fields_to_push: int = 0
    fields_to_pull: int = 0
    fields_conflicting: int = 0

    # By field type
    fields_by_type: dict[str, int] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes to sync."""
        return self.fields_to_push > 0 or self.fields_to_pull > 0

    @property
    def has_conflicts(self) -> bool:
        """Check if there are any conflicts."""
        return self.fields_conflicting > 0

    def get_delta(self, story_id: str) -> StoryDelta | None:
        """Get delta for a specific story."""
        for delta in self.deltas:
            if delta.story_id == story_id:
                return delta
        return None

    def get_stories_to_push(self) -> list[StoryDelta]:
        """Get stories with changes to push."""
        return [d for d in self.deltas if d.push_changes or d.is_new]

    def get_stories_to_pull(self) -> list[StoryDelta]:
        """Get stories with changes to pull."""
        return [d for d in self.deltas if d.pull_changes]

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "Delta Sync Analysis",
            "=" * 40,
            f"Total stories: {self.total_stories}",
            f"  Changed: {self.stories_with_changes}",
            f"  Unchanged: {self.stories_unchanged}",
            f"  New: {self.new_stories}",
            "",
            "Fields:",
            f"  To push: {self.fields_to_push}",
            f"  To pull: {self.fields_to_pull}",
            f"  Conflicts: {self.fields_conflicting}",
        ]

        if self.fields_by_type:
            lines.append("")
            lines.append("By field type:")
            for field_name, count in sorted(self.fields_by_type.items()):
                lines.append(f"  {field_name}: {count}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_stories": self.total_stories,
            "stories_with_changes": self.stories_with_changes,
            "stories_unchanged": self.stories_unchanged,
            "new_stories": self.new_stories,
            "fields_to_push": self.fields_to_push,
            "fields_to_pull": self.fields_to_pull,
            "fields_conflicting": self.fields_conflicting,
            "fields_by_type": self.fields_by_type,
            "analyzed_at": self.analyzed_at,
        }


class DeltaTracker:
    """
    Tracks field-level changes between local and remote states.

    Compares local stories (from markdown) with remote issues (from tracker)
    to determine exactly which fields need to be synced.

    Features:
    - Field-level change detection
    - Three-way comparison with baseline
    - Conflict detection when both sides changed
    - Field filtering for partial sync

    Example:
        >>> tracker = DeltaTracker()
        >>>
        >>> # Analyze changes
        >>> result = tracker.analyze(
        ...     local_stories=stories,
        ...     remote_issues=issues,
        ...     matches={"US-001": "PROJ-123"},
        ... )
        >>>
        >>> # Check what needs to sync
        >>> for delta in result.get_stories_to_push():
        ...     for change in delta.push_changes:
        ...         print(f"Push {change.field.value} for {delta.story_id}")
    """

    def __init__(
        self,
        baseline_dir: str | Path = "~/.spectra/delta",
        sync_fields: set[SyncableField] | None = None,
    ):
        """
        Initialize the delta tracker.

        Args:
            baseline_dir: Directory to store baseline state.
            sync_fields: Fields to sync (None = all fields).
        """
        self.baseline_dir = Path(baseline_dir).expanduser()
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.sync_fields = sync_fields or set(SyncableField)
        self.logger = logging.getLogger("DeltaTracker")

        self._baseline: dict[str, dict[str, str]] = {}  # story_id -> field -> hash

    def _baseline_path(self, epic_key: str) -> Path:
        """Get baseline file path for an epic."""
        safe_key = epic_key.replace("-", "_").lower()
        return self.baseline_dir / f"{safe_key}_delta.json"

    def load_baseline(self, epic_key: str) -> bool:
        """
        Load baseline state from previous sync.

        Args:
            epic_key: Epic being synced.

        Returns:
            True if baseline was loaded.
        """
        baseline_path = self._baseline_path(epic_key)

        if not baseline_path.exists():
            self.logger.info(f"No baseline found for {epic_key}")
            return False

        try:
            data = json.loads(baseline_path.read_text())
            self._baseline = data.get("stories", {})
            self.logger.info(f"Loaded baseline for {len(self._baseline)} stories")
            return True
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load baseline: {e}")
            return False

    def save_baseline(
        self,
        epic_key: str,
        stories: list[UserStory],
        matches: dict[str, str],
    ) -> None:
        """
        Save current state as new baseline.

        Args:
            epic_key: Epic being synced.
            stories: Stories that were synced.
            matches: Mapping of story_id to issue_key.
        """
        baseline: dict[str, dict[str, str]] = {}

        for story in stories:
            story_id = str(story.id)
            issue_key = matches.get(story_id, "")
            if not issue_key:
                continue

            baseline[story_id] = self._compute_field_hashes(story)

        data = {
            "epic_key": epic_key,
            "saved_at": datetime.now().isoformat(),
            "story_count": len(baseline),
            "stories": baseline,
        }

        baseline_path = self._baseline_path(epic_key)
        baseline_path.write_text(json.dumps(data, indent=2))
        self.logger.info(f"Saved baseline for {len(baseline)} stories")

    def analyze(
        self,
        local_stories: list[UserStory],
        remote_issues: list[IssueData],
        matches: dict[str, str],  # story_id -> issue_key
    ) -> DeltaSyncResult:
        """
        Analyze changes between local and remote states.

        Compares each field individually to determine what needs syncing.

        Args:
            local_stories: Stories from markdown.
            remote_issues: Issues from tracker.
            matches: Mapping of story_id to issue_key.

        Returns:
            DeltaSyncResult with all field-level changes.
        """
        result = DeltaSyncResult()
        result.total_stories = len(local_stories)

        # Build remote lookup
        remote_by_key = {issue.key: issue for issue in remote_issues}

        for story in local_stories:
            story_id = str(story.id)
            issue_key = matches.get(story_id, "")

            delta = StoryDelta(story_id=story_id, issue_key=issue_key)

            if not issue_key:
                # New story - not in tracker
                delta.is_new = True
                result.new_stories += 1
                result.stories_with_changes += 1
                result.deltas.append(delta)
                continue

            remote = remote_by_key.get(issue_key)
            if not remote:
                # Story matched but issue not found (deleted remotely?)
                delta.is_deleted_remotely = True
                result.deltas.append(delta)
                continue

            # Compare each field
            self._compare_fields(story, remote, delta)

            # Update stats
            if delta.has_changes:
                result.stories_with_changes += 1
                result.fields_to_push += len(delta.push_changes)
                result.fields_to_pull += len(delta.pull_changes)
                result.fields_conflicting += len(delta.conflicts)

                # Count by field type
                for change in delta.changes:
                    field_name = change.field.value
                    result.fields_by_type[field_name] = result.fields_by_type.get(field_name, 0) + 1
            else:
                result.stories_unchanged += 1

            result.deltas.append(delta)

        self.logger.info(
            f"Delta analysis: {result.stories_with_changes}/{result.total_stories} "
            f"stories with changes, {result.fields_to_push} fields to push"
        )

        return result

    def _compare_fields(
        self,
        local: UserStory,
        remote: IssueData,
        delta: StoryDelta,
    ) -> None:
        """Compare individual fields between local and remote."""
        story_id = str(local.id)
        base_hashes = self._baseline.get(story_id, {})

        # Title
        if SyncableField.TITLE in self.sync_fields:
            self._compare_field(
                delta,
                SyncableField.TITLE,
                local_value=local.title,
                remote_value=remote.summary,
                base_hash=base_hashes.get("title"),
            )

        # Description
        if SyncableField.DESCRIPTION in self.sync_fields:
            local_desc = local.description.to_markdown() if local.description else ""
            remote_desc = self._extract_description_text(remote.description)
            self._compare_field(
                delta,
                SyncableField.DESCRIPTION,
                local_value=local_desc,
                remote_value=remote_desc,
                base_hash=base_hashes.get("description"),
            )

        # Status
        if SyncableField.STATUS in self.sync_fields:
            from spectryn.core.domain.enums import Status

            local_status = local.status.value
            remote_status = Status.from_string(remote.status).value
            self._compare_field(
                delta,
                SyncableField.STATUS,
                local_value=local_status,
                remote_value=remote_status,
                base_hash=base_hashes.get("status"),
            )

        # Story points
        if SyncableField.STORY_POINTS in self.sync_fields:
            local_sp = local.story_points
            remote_sp = int(remote.story_points) if remote.story_points else 0
            self._compare_field(
                delta,
                SyncableField.STORY_POINTS,
                local_value=local_sp,
                remote_value=remote_sp,
                base_hash=base_hashes.get("story_points"),
            )

        # Priority
        if SyncableField.PRIORITY in self.sync_fields:
            local_priority = local.priority.value
            # Remote priority would need mapping - simplified here
            self._compare_field(
                delta,
                SyncableField.PRIORITY,
                local_value=local_priority,
                remote_value=local_priority,  # Can't compare without remote priority
                base_hash=base_hashes.get("priority"),
            )

        # Assignee
        if SyncableField.ASSIGNEE in self.sync_fields:
            self._compare_field(
                delta,
                SyncableField.ASSIGNEE,
                local_value=local.assignee or "",
                remote_value=remote.assignee or "",
                base_hash=base_hashes.get("assignee"),
            )

        # Subtasks (as count for simplicity)
        if SyncableField.SUBTASKS in self.sync_fields:
            local_subtasks = len(local.subtasks)
            remote_subtasks = len(remote.subtasks)
            if local_subtasks != remote_subtasks:
                self._compare_field(
                    delta,
                    SyncableField.SUBTASKS,
                    local_value=local_subtasks,
                    remote_value=remote_subtasks,
                    base_hash=base_hashes.get("subtasks"),
                )

    def _compare_field(
        self,
        delta: StoryDelta,
        field: SyncableField,
        local_value: Any,
        remote_value: Any,
        base_hash: str | None,
    ) -> None:
        """Compare a single field and add change if different."""
        local_hash = FieldChange._hash_value(local_value)
        remote_hash = FieldChange._hash_value(remote_value)

        # Same values - no change
        if local_hash == remote_hash:
            return

        # Determine direction based on baseline
        if base_hash is None:
            # No baseline - assume local is authoritative (push)
            direction = ChangeDirection.LOCAL_TO_REMOTE
        elif local_hash != base_hash and remote_hash == base_hash:
            # Only local changed - push
            direction = ChangeDirection.LOCAL_TO_REMOTE
        elif local_hash == base_hash and remote_hash != base_hash:
            # Only remote changed - pull
            direction = ChangeDirection.REMOTE_TO_LOCAL
        else:
            # Both changed - conflict
            direction = ChangeDirection.CONFLICT

        change = FieldChange(
            field=field,
            direction=direction,
            local_value=local_value,
            remote_value=remote_value,
            base_hash=base_hash or "",
        )
        delta.add_change(change)

    def _compute_field_hashes(self, story: UserStory) -> dict[str, str]:
        """Compute hashes for all fields of a story."""
        hashes = {}

        hashes["title"] = FieldChange._hash_value(story.title)

        desc = story.description.to_markdown() if story.description else ""
        hashes["description"] = FieldChange._hash_value(desc)

        hashes["status"] = FieldChange._hash_value(story.status.value)
        hashes["story_points"] = FieldChange._hash_value(story.story_points)
        hashes["priority"] = FieldChange._hash_value(story.priority.value)
        hashes["assignee"] = FieldChange._hash_value(story.assignee or "")
        hashes["subtasks"] = FieldChange._hash_value(len(story.subtasks))

        return hashes

    def _extract_description_text(self, description: Any) -> str:
        """Extract plain text from description (may be ADF)."""
        if description is None:
            return ""
        if isinstance(description, str):
            return description
        if isinstance(description, dict):
            # ADF format
            return self._adf_to_text(description)
        return str(description)

    def _adf_to_text(self, adf: dict) -> str:
        """Convert ADF to plain text."""
        if not isinstance(adf, dict):
            return str(adf) if adf else ""

        texts = []
        for node in adf.get("content", []):
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                elif "content" in node:
                    texts.append(self._adf_to_text(node))
        return "".join(texts)

    def clear_baseline(self, epic_key: str) -> bool:
        """Clear baseline for an epic."""
        baseline_path = self._baseline_path(epic_key)
        if baseline_path.exists():
            baseline_path.unlink()
            return True
        return False


def create_delta_tracker(
    sync_fields: list[str] | None = None,
    baseline_dir: str | None = None,
) -> DeltaTracker:
    """
    Factory function to create a DeltaTracker.

    Args:
        sync_fields: List of field names to sync (None = all).
        baseline_dir: Directory for baseline storage.

    Returns:
        Configured DeltaTracker.
    """
    fields = None
    if sync_fields:
        fields = set()
        for name in sync_fields:
            try:
                fields.add(SyncableField(name))
            except ValueError:
                logger.warning(f"Unknown field: {name}")

    return DeltaTracker(
        baseline_dir=baseline_dir or "~/.spectra/delta",
        sync_fields=fields,
    )
