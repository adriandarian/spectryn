"""
Incremental Sync - Only sync stories that have changed.

Tracks content hashes of stories between syncs to detect changes
and skip unchanged stories, significantly reducing API calls.

Components:
- StoryFingerprint: Hash of story content for change detection
- ChangeTracker: Persists and compares fingerprints between syncs
- IncrementalSyncResult: Results with change detection stats
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


@dataclass
class StoryFingerprint:
    """
    Fingerprint of a story's content for change detection.

    Captures a hash of all syncable content so we can detect
    when a story needs to be synced.

    Attributes:
        story_id: The story identifier
        content_hash: Hash of description, subtasks, etc.
        subtask_hashes: Individual hashes for each subtask
        metadata_hash: Hash of metadata (status, points, etc.)
        created_at: When this fingerprint was created
    """

    story_id: str
    content_hash: str
    subtask_hashes: dict[str, str] = field(default_factory=dict)  # subtask_name -> hash
    metadata_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def from_story(cls, story: UserStory) -> StoryFingerprint:
        """
        Create a fingerprint from a UserStory.

        Hashes all content that would be synced to the tracker.
        """
        # Hash the main content
        content_parts = [
            str(story.id),
            story.title,
            story.description.to_markdown() if story.description else "",
            story.acceptance_criteria.to_markdown() if story.acceptance_criteria else "",
            story.technical_notes or "",
        ]
        content_hash = cls._hash_content(content_parts)

        # Hash each subtask individually
        subtask_hashes = {}
        for subtask in story.subtasks:
            subtask_key = subtask.normalize_name()[:50]
            subtask_content = [
                subtask.name,
                subtask.description or "",
                str(subtask.story_points),
            ]
            subtask_hashes[subtask_key] = cls._hash_content(subtask_content)

        # Hash metadata
        metadata_parts = [
            str(story.status.value),
            str(story.story_points),
            str(story.priority.value),
            ",".join(sorted(story.labels)),
        ]
        metadata_hash = cls._hash_content(metadata_parts)

        return cls(
            story_id=str(story.id),
            content_hash=content_hash,
            subtask_hashes=subtask_hashes,
            metadata_hash=metadata_hash,
        )

    @staticmethod
    def _hash_content(parts: list[str]) -> str:
        """Create a hash from content parts."""
        content = "|".join(parts)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def content_changed(self, other: StoryFingerprint) -> bool:
        """Check if content has changed compared to another fingerprint."""
        return self.content_hash != other.content_hash

    def metadata_changed(self, other: StoryFingerprint) -> bool:
        """Check if metadata has changed."""
        return self.metadata_hash != other.metadata_hash

    def get_changed_subtasks(self, other: StoryFingerprint) -> tuple[set[str], set[str], set[str]]:
        """
        Compare subtasks with another fingerprint.

        Returns:
            Tuple of (added, removed, modified) subtask names
        """
        current_names = set(self.subtask_hashes.keys())
        previous_names = set(other.subtask_hashes.keys())

        added = current_names - previous_names
        removed = previous_names - current_names

        # Check for modifications in common subtasks
        modified = set()
        for name in current_names & previous_names:
            if self.subtask_hashes[name] != other.subtask_hashes[name]:
                modified.add(name)

        return added, removed, modified

    def has_any_changes(self, other: StoryFingerprint) -> bool:
        """Check if there are any changes compared to another fingerprint."""
        if self.content_hash != other.content_hash:
            return True
        if self.metadata_hash != other.metadata_hash:
            return True
        return self.subtask_hashes != other.subtask_hashes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "story_id": self.story_id,
            "content_hash": self.content_hash,
            "subtask_hashes": self.subtask_hashes,
            "metadata_hash": self.metadata_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryFingerprint:
        """Create from dictionary."""
        return cls(
            story_id=data["story_id"],
            content_hash=data["content_hash"],
            subtask_hashes=data.get("subtask_hashes", {}),
            metadata_hash=data.get("metadata_hash", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class ChangeDetectionResult:
    """
    Result of change detection for a story.

    Describes what has changed in a story since last sync.
    """

    story_id: str
    has_changes: bool = False

    # What changed
    description_changed: bool = False
    metadata_changed: bool = False
    subtasks_added: set[str] = field(default_factory=set)
    subtasks_removed: set[str] = field(default_factory=set)
    subtasks_modified: set[str] = field(default_factory=set)

    # Is this a new story?
    is_new: bool = False

    @property
    def subtasks_changed(self) -> bool:
        """Check if any subtasks changed."""
        return bool(self.subtasks_added or self.subtasks_removed or self.subtasks_modified)

    def __str__(self) -> str:
        if not self.has_changes:
            return f"{self.story_id}: no changes"

        parts = [self.story_id + ":"]
        if self.is_new:
            parts.append("new")
        if self.description_changed:
            parts.append("description")
        if self.metadata_changed:
            parts.append("metadata")
        if self.subtasks_added:
            parts.append(f"+{len(self.subtasks_added)} subtasks")
        if self.subtasks_removed:
            parts.append(f"-{len(self.subtasks_removed)} subtasks")
        if self.subtasks_modified:
            parts.append(f"~{len(self.subtasks_modified)} subtasks")

        return " ".join(parts)


class ChangeTracker:
    """
    Tracks story changes between syncs.

    Stores fingerprints of synced stories and compares them
    on subsequent syncs to detect what has changed.

    Example:
        >>> tracker = ChangeTracker(storage_dir="~/.spectra/sync")
        >>>
        >>> # Load previous state
        >>> tracker.load("EPIC-123", "path/to/doc.md")
        >>>
        >>> # Detect changes
        >>> changes = tracker.detect_changes(stories)
        >>> for story_id, result in changes.items():
        ...     if result.has_changes:
        ...         print(f"{story_id} needs sync")
        >>>
        >>> # After successful sync, save new state
        >>> tracker.save_fingerprints(stories)
    """

    def __init__(
        self,
        storage_dir: str | Path = "~/.spectra/sync",
    ):
        """
        Initialize the change tracker.

        Args:
            storage_dir: Directory to store sync state files
        """
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._current_key: str = ""
        self._previous_fingerprints: dict[str, StoryFingerprint] = {}
        self._current_fingerprints: dict[str, StoryFingerprint] = {}

        self.logger = logging.getLogger("ChangeTracker")

    def _get_state_path(self, epic_key: str, markdown_path: str) -> Path:
        """Get the state file path for a sync pair."""
        # Create a stable identifier from epic and markdown path
        path_hash = hashlib.sha256(markdown_path.encode()).hexdigest()[:8]
        filename = f"{epic_key}_{path_hash}.json"
        return self.storage_dir / filename

    def load(self, epic_key: str, markdown_path: str) -> bool:
        """
        Load previous sync state.

        Args:
            epic_key: Epic being synced
            markdown_path: Path to markdown file

        Returns:
            True if previous state was loaded
        """
        self._current_key = f"{epic_key}:{markdown_path}"
        self._previous_fingerprints = {}

        state_path = self._get_state_path(epic_key, markdown_path)

        if not state_path.exists():
            self.logger.info(f"No previous sync state found for {epic_key}")
            return False

        try:
            data = json.loads(state_path.read_text())

            for fp_data in data.get("fingerprints", []):
                fp = StoryFingerprint.from_dict(fp_data)
                self._previous_fingerprints[fp.story_id] = fp

            self.logger.info(
                f"Loaded {len(self._previous_fingerprints)} fingerprints from previous sync"
            )
            return True

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Failed to load previous state: {e}")
            return False

    def detect_changes(
        self,
        stories: list[UserStory],
    ) -> dict[str, ChangeDetectionResult]:
        """
        Detect changes in stories compared to last sync.

        Args:
            stories: Current stories from markdown

        Returns:
            Dict mapping story_id to ChangeDetectionResult
        """
        results: dict[str, ChangeDetectionResult] = {}
        self._current_fingerprints = {}

        for story in stories:
            story_id = str(story.id)
            current_fp = StoryFingerprint.from_story(story)
            self._current_fingerprints[story_id] = current_fp

            result = ChangeDetectionResult(story_id=story_id)

            # Check if this is a new story
            if story_id not in self._previous_fingerprints:
                result.is_new = True
                result.has_changes = True
                results[story_id] = result
                continue

            previous_fp = self._previous_fingerprints[story_id]

            # Check content changes
            if current_fp.content_changed(previous_fp):
                result.description_changed = True
                result.has_changes = True

            # Check metadata changes
            if current_fp.metadata_changed(previous_fp):
                result.metadata_changed = True
                result.has_changes = True

            # Check subtask changes
            added, removed, modified = current_fp.get_changed_subtasks(previous_fp)
            if added or removed or modified:
                result.subtasks_added = added
                result.subtasks_removed = removed
                result.subtasks_modified = modified
                result.has_changes = True

            results[story_id] = result

        # Count changes
        changed_count = sum(1 for r in results.values() if r.has_changes)
        self.logger.info(f"Change detection: {changed_count}/{len(stories)} stories changed")

        return results

    def save(self, epic_key: str, markdown_path: str) -> None:
        """
        Save current fingerprints for next sync.

        Call this after a successful sync to update the baseline.

        Args:
            epic_key: Epic being synced
            markdown_path: Path to markdown file
        """
        state_path = self._get_state_path(epic_key, markdown_path)

        data = {
            "epic_key": epic_key,
            "markdown_path": markdown_path,
            "synced_at": datetime.now().isoformat(),
            "fingerprints": [fp.to_dict() for fp in self._current_fingerprints.values()],
        }

        state_path.write_text(json.dumps(data, indent=2))
        self.logger.info(f"Saved {len(self._current_fingerprints)} fingerprints")

    def mark_story_synced(self, story: UserStory) -> None:
        """
        Mark a single story as synced.

        Updates the fingerprint for this story.
        """
        story_id = str(story.id)
        self._current_fingerprints[story_id] = StoryFingerprint.from_story(story)

    def get_changed_story_ids(
        self,
        stories: list[UserStory],
    ) -> set[str]:
        """
        Get IDs of stories that have changed.

        Convenience method for simple filtering.
        """
        changes = self.detect_changes(stories)
        return {story_id for story_id, result in changes.items() if result.has_changes}

    def clear(self, epic_key: str, markdown_path: str) -> bool:
        """
        Clear saved state for a sync pair.

        Forces full sync on next run.
        """
        state_path = self._get_state_path(epic_key, markdown_path)

        if state_path.exists():
            state_path.unlink()
            self.logger.info(f"Cleared sync state for {epic_key}")
            return True

        return False

    @property
    def has_previous_state(self) -> bool:
        """Check if previous state was loaded."""
        return bool(self._previous_fingerprints)

    @property
    def previous_story_count(self) -> int:
        """Get number of stories in previous sync."""
        return len(self._previous_fingerprints)


@dataclass
class IncrementalSyncStats:
    """
    Statistics for incremental sync.

    Tracks how many stories were skipped vs synced.
    """

    total_stories: int = 0
    changed_stories: int = 0
    skipped_stories: int = 0
    new_stories: int = 0

    # What changed
    descriptions_changed: int = 0
    subtasks_added: int = 0
    subtasks_modified: int = 0
    subtasks_removed: int = 0

    # Performance
    api_calls_saved: int = 0  # Estimated

    @property
    def skip_rate(self) -> float:
        """Percentage of stories skipped."""
        if self.total_stories == 0:
            return 0.0
        return self.skipped_stories / self.total_stories

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_stories": self.total_stories,
            "changed_stories": self.changed_stories,
            "skipped_stories": self.skipped_stories,
            "new_stories": self.new_stories,
            "skip_rate": round(self.skip_rate, 2),
            "descriptions_changed": self.descriptions_changed,
            "subtasks_added": self.subtasks_added,
            "subtasks_modified": self.subtasks_modified,
            "subtasks_removed": self.subtasks_removed,
            "api_calls_saved": self.api_calls_saved,
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        return (
            f"Incremental sync: {self.changed_stories}/{self.total_stories} "
            f"stories changed ({self.skipped_stories} skipped, "
            f"{self.new_stories} new)"
        )


def compute_story_hash(story: UserStory) -> str:
    """
    Compute a simple hash for a story.

    Convenience function for quick change detection.
    """
    fp = StoryFingerprint.from_story(story)
    return f"{fp.content_hash}:{fp.metadata_hash}"


def stories_differ(story1: UserStory, story2: UserStory) -> bool:
    """
    Check if two stories have different content.

    Convenience function for comparing stories.
    """
    fp1 = StoryFingerprint.from_story(story1)
    fp2 = StoryFingerprint.from_story(story2)
    return fp1.has_any_changes(fp2)
