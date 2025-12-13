"""
Conflict Detection and Resolution - Detect and resolve sync conflicts.

Conflicts occur when both markdown and Jira have been modified since
the last sync. This module provides:
- Snapshot storage of last successful sync state
- Conflict detection between current and last-synced states
- Resolution strategies (local, remote, merge, manual)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.ports.issue_tracker import IssueTrackerPort, IssueData
    from ...core.domain.entities import UserStory

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of conflicts that can occur during sync."""
    
    NONE = "none"  # No conflict
    BOTH_MODIFIED = "both_modified"  # Both sides changed the same field
    LOCAL_MODIFIED_REMOTE_DELETED = "local_modified_remote_deleted"
    REMOTE_MODIFIED_LOCAL_DELETED = "remote_modified_local_deleted"
    BOTH_DELETED = "both_deleted"
    NEW_ON_BOTH = "new_on_both"  # New story with same ID on both sides


class ResolutionStrategy(Enum):
    """Strategies for resolving conflicts."""
    
    ASK = "ask"  # Prompt user for each conflict
    FORCE_LOCAL = "force_local"  # Always take local (markdown) changes
    FORCE_REMOTE = "force_remote"  # Always take remote (Jira) changes
    SKIP = "skip"  # Skip conflicting items
    ABORT = "abort"  # Abort sync on any conflict


@dataclass
class FieldSnapshot:
    """Snapshot of a single field value."""
    
    value: Any
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = self._compute_hash(self.value)
    
    @staticmethod
    def _compute_hash(value: Any) -> str:
        """Compute hash of a value for comparison."""
        if value is None:
            return "null"
        content = json.dumps(value, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def matches(self, other: "FieldSnapshot") -> bool:
        """Check if this snapshot matches another."""
        return self.hash == other.hash
    
    def to_dict(self) -> dict:
        return {"value": self.value, "hash": self.hash}
    
    @classmethod
    def from_dict(cls, data: dict) -> "FieldSnapshot":
        return cls(value=data.get("value"), hash=data.get("hash", ""))


@dataclass
class StorySnapshot:
    """
    Snapshot of a story's state at sync time.
    
    Captures key fields that could conflict.
    """
    
    story_id: str
    jira_key: str
    title: FieldSnapshot = field(default_factory=lambda: FieldSnapshot(None))
    description: FieldSnapshot = field(default_factory=lambda: FieldSnapshot(None))
    status: FieldSnapshot = field(default_factory=lambda: FieldSnapshot(None))
    story_points: FieldSnapshot = field(default_factory=lambda: FieldSnapshot(None))
    subtask_count: int = 0
    subtask_hashes: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "jira_key": self.jira_key,
            "title": self.title.to_dict(),
            "description": self.description.to_dict(),
            "status": self.status.to_dict(),
            "story_points": self.story_points.to_dict(),
            "subtask_count": self.subtask_count,
            "subtask_hashes": self.subtask_hashes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StorySnapshot":
        return cls(
            story_id=data["story_id"],
            jira_key=data["jira_key"],
            title=FieldSnapshot.from_dict(data.get("title", {})),
            description=FieldSnapshot.from_dict(data.get("description", {})),
            status=FieldSnapshot.from_dict(data.get("status", {})),
            story_points=FieldSnapshot.from_dict(data.get("story_points", {})),
            subtask_count=data.get("subtask_count", 0),
            subtask_hashes=data.get("subtask_hashes", []),
        )
    
    @classmethod
    def from_story(cls, story: "UserStory", jira_key: str = "") -> "StorySnapshot":
        """Create snapshot from a UserStory entity."""
        desc_text = story.description.to_markdown() if story.description else None
        
        subtask_hashes = []
        for st in story.subtasks:
            content = f"{st.name}:{st.description}:{st.story_points}:{st.status.value}"
            subtask_hashes.append(hashlib.md5(content.encode()).hexdigest()[:8])
        
        return cls(
            story_id=str(story.id),
            jira_key=jira_key or (str(story.external_key) if story.external_key else ""),
            title=FieldSnapshot(story.title),
            description=FieldSnapshot(desc_text),
            status=FieldSnapshot(story.status.value),
            story_points=FieldSnapshot(story.story_points),
            subtask_count=len(story.subtasks),
            subtask_hashes=subtask_hashes,
        )


@dataclass
class SyncSnapshot:
    """
    Complete snapshot of sync state at a point in time.
    
    Stored after successful syncs to detect conflicts on next sync.
    """
    
    snapshot_id: str
    epic_key: str
    markdown_path: str
    markdown_hash: str  # Hash of markdown file content
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    stories: list[StorySnapshot] = field(default_factory=list)
    
    def get_story(self, story_id: str) -> Optional[StorySnapshot]:
        """Get a story snapshot by ID."""
        for story in self.stories:
            if story.story_id == story_id:
                return story
        return None
    
    def get_story_by_jira_key(self, jira_key: str) -> Optional[StorySnapshot]:
        """Get a story snapshot by Jira key."""
        for story in self.stories:
            if story.jira_key == jira_key:
                return story
        return None
    
    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "epic_key": self.epic_key,
            "markdown_path": self.markdown_path,
            "markdown_hash": self.markdown_hash,
            "created_at": self.created_at,
            "stories": [s.to_dict() for s in self.stories],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SyncSnapshot":
        snapshot = cls(
            snapshot_id=data["snapshot_id"],
            epic_key=data["epic_key"],
            markdown_path=data["markdown_path"],
            markdown_hash=data.get("markdown_hash", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )
        snapshot.stories = [
            StorySnapshot.from_dict(s) for s in data.get("stories", [])
        ]
        return snapshot
    
    @staticmethod
    def generate_id(epic_key: str, markdown_path: str) -> str:
        """Generate a unique snapshot ID."""
        content = f"{epic_key}:{markdown_path}:{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Conflict:
    """
    A detected conflict between local and remote state.
    """
    
    story_id: str
    jira_key: str
    field: str  # title, description, status, story_points, subtasks
    conflict_type: ConflictType
    local_value: Any  # Current markdown value
    remote_value: Any  # Current Jira value
    base_value: Any  # Value at last sync
    
    def __str__(self) -> str:
        return f"{self.story_id} ({self.jira_key}): {self.field} - {self.conflict_type.value}"
    
    @property
    def summary(self) -> str:
        """Get a human-readable summary."""
        if self.conflict_type == ConflictType.BOTH_MODIFIED:
            return f"Both modified: {self.field}"
        elif self.conflict_type == ConflictType.LOCAL_MODIFIED_REMOTE_DELETED:
            return f"Local modified, remote deleted: {self.field}"
        elif self.conflict_type == ConflictType.REMOTE_MODIFIED_LOCAL_DELETED:
            return f"Remote modified, local deleted: {self.field}"
        return self.conflict_type.value
    
    def to_dict(self) -> dict:
        return {
            "story_id": self.story_id,
            "jira_key": self.jira_key,
            "field": self.field,
            "conflict_type": self.conflict_type.value,
            "local_value": self.local_value,
            "remote_value": self.remote_value,
            "base_value": self.base_value,
        }


@dataclass
class ConflictResolution:
    """Resolution for a single conflict."""
    
    conflict: Conflict
    resolution: str  # "local", "remote", "skip", "merge"
    merged_value: Optional[Any] = None  # For merge resolution
    resolved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def final_value(self) -> Any:
        """Get the final value after resolution."""
        if self.resolution == "local":
            return self.conflict.local_value
        elif self.resolution == "remote":
            return self.conflict.remote_value
        elif self.resolution == "merge" and self.merged_value is not None:
            return self.merged_value
        return None


@dataclass
class ConflictReport:
    """
    Report of all conflicts detected during sync analysis.
    """
    
    epic_key: str
    conflicts: list[Conflict] = field(default_factory=list)
    resolutions: list[ConflictResolution] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0
    
    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)
    
    @property
    def resolved_count(self) -> int:
        return len(self.resolutions)
    
    @property
    def unresolved_count(self) -> int:
        return self.conflict_count - self.resolved_count
    
    @property
    def stories_with_conflicts(self) -> list[str]:
        """Get list of story IDs that have conflicts."""
        return list(set(c.story_id for c in self.conflicts))
    
    def add_conflict(self, conflict: Conflict) -> None:
        """Add a detected conflict."""
        self.conflicts.append(conflict)
    
    def add_resolution(self, resolution: ConflictResolution) -> None:
        """Add a conflict resolution."""
        self.resolutions.append(resolution)
    
    def get_conflicts_for_story(self, story_id: str) -> list[Conflict]:
        """Get all conflicts for a specific story."""
        return [c for c in self.conflicts if c.story_id == story_id]
    
    def summary(self) -> str:
        """Get a human-readable summary."""
        lines = [
            f"Conflict Report for {self.epic_key}",
            "-" * 40,
            f"Total conflicts: {self.conflict_count}",
            f"Resolved: {self.resolved_count}",
            f"Unresolved: {self.unresolved_count}",
        ]
        
        if self.conflicts:
            lines.append("")
            lines.append("Conflicts by story:")
            for story_id in self.stories_with_conflicts:
                story_conflicts = self.get_conflicts_for_story(story_id)
                lines.append(f"  {story_id}: {len(story_conflicts)} conflict(s)")
                for c in story_conflicts[:3]:
                    lines.append(f"    - {c.field}: {c.conflict_type.value}")
                if len(story_conflicts) > 3:
                    lines.append(f"    ... and {len(story_conflicts) - 3} more")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        return {
            "epic_key": self.epic_key,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "analyzed_at": self.analyzed_at,
            "conflict_count": self.conflict_count,
            "stories_with_conflicts": self.stories_with_conflicts,
        }


class ConflictDetector:
    """
    Detects conflicts between local (markdown) and remote (Jira) states.
    
    Compares current states with the last successful sync snapshot
    to identify what has changed on each side.
    """
    
    def __init__(self, base_snapshot: Optional[SyncSnapshot] = None):
        """
        Initialize the detector.
        
        Args:
            base_snapshot: The last successful sync snapshot (baseline).
        """
        self.base_snapshot = base_snapshot
        self.logger = logging.getLogger("ConflictDetector")
    
    def detect_conflicts(
        self,
        local_stories: list["UserStory"],
        remote_issues: list["IssueData"],
        matches: dict[str, str],  # story_id -> jira_key
    ) -> ConflictReport:
        """
        Detect conflicts between local and remote states.
        
        Args:
            local_stories: Current stories from markdown.
            remote_issues: Current issues from Jira.
            matches: Mapping of story IDs to Jira keys.
            
        Returns:
            ConflictReport with all detected conflicts.
        """
        report = ConflictReport(
            epic_key=self.base_snapshot.epic_key if self.base_snapshot else "UNKNOWN"
        )
        
        if not self.base_snapshot:
            self.logger.info("No base snapshot - no conflicts possible (first sync)")
            return report
        
        # Build lookup for remote issues
        remote_by_key = {issue.key: issue for issue in remote_issues}
        
        for story in local_stories:
            story_id = str(story.id)
            jira_key = matches.get(story_id, "")
            
            if not jira_key:
                continue  # Unmatched story, not a conflict
            
            base_story = self.base_snapshot.get_story(story_id)
            if not base_story:
                continue  # New story since last sync
            
            remote_issue = remote_by_key.get(jira_key)
            if not remote_issue:
                # Remote deleted, check if local modified
                local_snapshot = StorySnapshot.from_story(story, jira_key)
                if not self._snapshots_match(local_snapshot, base_story):
                    report.add_conflict(Conflict(
                        story_id=story_id,
                        jira_key=jira_key,
                        field="story",
                        conflict_type=ConflictType.LOCAL_MODIFIED_REMOTE_DELETED,
                        local_value="exists",
                        remote_value="deleted",
                        base_value="existed",
                    ))
                continue
            
            # Check each field for conflicts
            self._detect_field_conflicts(
                story, remote_issue, base_story, report
            )
        
        # Check for stories deleted locally but modified remotely
        for base_story in self.base_snapshot.stories:
            story_exists = any(str(s.id) == base_story.story_id for s in local_stories)
            if not story_exists:
                remote_issue = remote_by_key.get(base_story.jira_key)
                if remote_issue:
                    # Local deleted, check if remote modified
                    remote_changed = self._remote_changed(remote_issue, base_story)
                    if remote_changed:
                        report.add_conflict(Conflict(
                            story_id=base_story.story_id,
                            jira_key=base_story.jira_key,
                            field="story",
                            conflict_type=ConflictType.REMOTE_MODIFIED_LOCAL_DELETED,
                            local_value="deleted",
                            remote_value="modified",
                            base_value="existed",
                        ))
        
        self.logger.info(f"Detected {report.conflict_count} conflicts")
        return report
    
    def _detect_field_conflicts(
        self,
        local: "UserStory",
        remote: "IssueData",
        base: StorySnapshot,
        report: ConflictReport,
    ) -> None:
        """Detect conflicts for individual fields."""
        story_id = str(local.id)
        jira_key = remote.key
        
        # Status conflict
        local_status = local.status.value
        remote_status = self._normalize_status(remote.status)
        base_status = base.status.value
        
        local_status_changed = local_status != base_status
        remote_status_changed = remote_status != base_status
        
        if local_status_changed and remote_status_changed and local_status != remote_status:
            report.add_conflict(Conflict(
                story_id=story_id,
                jira_key=jira_key,
                field="status",
                conflict_type=ConflictType.BOTH_MODIFIED,
                local_value=local_status,
                remote_value=remote_status,
                base_value=base_status,
            ))
        
        # Story points conflict
        local_sp = local.story_points
        remote_sp = int(remote.story_points) if remote.story_points else 0
        base_sp = base.story_points.value or 0
        
        local_sp_changed = local_sp != base_sp
        remote_sp_changed = remote_sp != base_sp
        
        if local_sp_changed and remote_sp_changed and local_sp != remote_sp:
            report.add_conflict(Conflict(
                story_id=story_id,
                jira_key=jira_key,
                field="story_points",
                conflict_type=ConflictType.BOTH_MODIFIED,
                local_value=local_sp,
                remote_value=remote_sp,
                base_value=base_sp,
            ))
        
        # Description conflict (using hash comparison)
        local_desc = local.description.to_markdown() if local.description else ""
        local_desc_hash = FieldSnapshot._compute_hash(local_desc)
        base_desc_hash = base.description.hash
        
        # For remote, we'd need to convert ADF to text for comparison
        # Simplified: just check if local changed from base
        if local_desc_hash != base_desc_hash:
            # Check if remote also changed
            remote_desc = self._extract_remote_description(remote.description)
            remote_desc_hash = FieldSnapshot._compute_hash(remote_desc)
            
            if remote_desc_hash != base_desc_hash and local_desc_hash != remote_desc_hash:
                report.add_conflict(Conflict(
                    story_id=story_id,
                    jira_key=jira_key,
                    field="description",
                    conflict_type=ConflictType.BOTH_MODIFIED,
                    local_value=local_desc[:100] + "..." if len(local_desc) > 100 else local_desc,
                    remote_value=remote_desc[:100] + "..." if len(remote_desc) > 100 else remote_desc,
                    base_value="[previous version]",
                ))
    
    def _snapshots_match(self, a: StorySnapshot, b: StorySnapshot) -> bool:
        """Check if two snapshots represent the same state."""
        return (
            a.title.hash == b.title.hash and
            a.description.hash == b.description.hash and
            a.status.hash == b.status.hash and
            a.story_points.hash == b.story_points.hash
        )
    
    def _remote_changed(self, remote: "IssueData", base: StorySnapshot) -> bool:
        """Check if remote has changed from base."""
        remote_status = self._normalize_status(remote.status)
        if remote_status != base.status.value:
            return True
        
        remote_sp = int(remote.story_points) if remote.story_points else 0
        if remote_sp != (base.story_points.value or 0):
            return True
        
        return False
    
    def _normalize_status(self, status: str) -> int:
        """Normalize status string to enum value."""
        from ...core.domain.enums import Status
        return Status.from_string(status).value
    
    def _extract_remote_description(self, description: Any) -> str:
        """Extract text from remote description (may be ADF)."""
        if description is None:
            return ""
        if isinstance(description, str):
            return description
        if isinstance(description, dict):
            # ADF format - extract text
            return self._adf_to_text(description)
        return str(description)
    
    def _adf_to_text(self, adf: dict) -> str:
        """Convert ADF to plain text."""
        if not isinstance(adf, dict):
            return str(adf) if adf else ""
        
        content = adf.get("content", [])
        return self._extract_adf_text(content)
    
    def _extract_adf_text(self, nodes: list) -> str:
        """Recursively extract text from ADF nodes."""
        texts = []
        for node in nodes:
            if isinstance(node, dict):
                if node.get("type") == "text":
                    texts.append(node.get("text", ""))
                elif "content" in node:
                    texts.append(self._extract_adf_text(node["content"]))
        return "".join(texts)


class ConflictResolver:
    """
    Resolves conflicts using a specified strategy.
    """
    
    def __init__(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.ASK,
        prompt_func: Optional[Callable[[Conflict], str]] = None,
    ):
        """
        Initialize the resolver.
        
        Args:
            strategy: Default resolution strategy.
            prompt_func: Function to prompt user for resolution.
                         Should return "local", "remote", "skip", or "merge".
        """
        self.strategy = strategy
        self.prompt_func = prompt_func
        self.logger = logging.getLogger("ConflictResolver")
    
    def resolve(self, report: ConflictReport) -> ConflictReport:
        """
        Resolve all conflicts in a report.
        
        Args:
            report: The conflict report to resolve.
            
        Returns:
            Updated report with resolutions.
        """
        for conflict in report.conflicts:
            resolution = self._resolve_single(conflict)
            if resolution:
                report.add_resolution(resolution)
        
        return report
    
    def _resolve_single(self, conflict: Conflict) -> Optional[ConflictResolution]:
        """Resolve a single conflict."""
        if self.strategy == ResolutionStrategy.ABORT:
            return None  # Don't resolve, will abort
        
        if self.strategy == ResolutionStrategy.FORCE_LOCAL:
            return ConflictResolution(conflict=conflict, resolution="local")
        
        if self.strategy == ResolutionStrategy.FORCE_REMOTE:
            return ConflictResolution(conflict=conflict, resolution="remote")
        
        if self.strategy == ResolutionStrategy.SKIP:
            return ConflictResolution(conflict=conflict, resolution="skip")
        
        if self.strategy == ResolutionStrategy.ASK:
            if self.prompt_func:
                choice = self.prompt_func(conflict)
                return ConflictResolution(conflict=conflict, resolution=choice)
            else:
                # Default to skip if no prompt function
                self.logger.warning(f"No prompt function, skipping conflict: {conflict}")
                return ConflictResolution(conflict=conflict, resolution="skip")
        
        return None


class SnapshotStore:
    """
    Persistent storage for sync snapshots.
    
    Stores snapshots as JSON files in ~/.md2jira/snapshots/
    """
    
    DEFAULT_DIR = Path.home() / ".md2jira" / "snapshots"
    
    def __init__(self, snapshot_dir: Optional[Path] = None):
        """
        Initialize the store.
        
        Args:
            snapshot_dir: Directory to store snapshots.
        """
        self.snapshot_dir = snapshot_dir or self.DEFAULT_DIR
        self._ensure_dir()
    
    def _ensure_dir(self) -> None:
        """Ensure the snapshot directory exists."""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    def _snapshot_file(self, epic_key: str) -> Path:
        """Get the path to snapshot file for an epic."""
        # Use epic key as filename (sanitized)
        safe_key = epic_key.replace("-", "_").lower()
        return self.snapshot_dir / f"{safe_key}_snapshot.json"
    
    def save(self, snapshot: SyncSnapshot) -> Path:
        """
        Save a snapshot.
        
        Args:
            snapshot: The snapshot to save.
            
        Returns:
            Path to the saved file.
        """
        snapshot_file = self._snapshot_file(snapshot.epic_key)
        
        with open(snapshot_file, "w") as f:
            json.dump(snapshot.to_dict(), f, indent=2)
        
        logger.info(f"Saved sync snapshot to {snapshot_file}")
        return snapshot_file
    
    def load(self, epic_key: str) -> Optional[SyncSnapshot]:
        """
        Load the latest snapshot for an epic.
        
        Args:
            epic_key: The epic key.
            
        Returns:
            The snapshot, or None if not found.
        """
        snapshot_file = self._snapshot_file(epic_key)
        
        if not snapshot_file.exists():
            logger.debug(f"No snapshot found for {epic_key}")
            return None
        
        try:
            with open(snapshot_file) as f:
                data = json.load(f)
            return SyncSnapshot.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load snapshot: {e}")
            return None
    
    def delete(self, epic_key: str) -> bool:
        """
        Delete a snapshot.
        
        Args:
            epic_key: The epic key.
            
        Returns:
            True if deleted, False if not found.
        """
        snapshot_file = self._snapshot_file(epic_key)
        
        if snapshot_file.exists():
            snapshot_file.unlink()
            return True
        return False
    
    def list_snapshots(self) -> list[dict]:
        """
        List all stored snapshots.
        
        Returns:
            List of snapshot summaries.
        """
        snapshots = []
        
        for file in self.snapshot_dir.glob("*_snapshot.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                snapshots.append({
                    "epic_key": data.get("epic_key"),
                    "created_at": data.get("created_at"),
                    "story_count": len(data.get("stories", [])),
                    "file": str(file),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        
        return sorted(snapshots, key=lambda s: s.get("created_at", ""), reverse=True)


def create_snapshot_from_sync(
    epic_key: str,
    markdown_path: str,
    stories: list["UserStory"],
    matches: dict[str, str],  # story_id -> jira_key
) -> SyncSnapshot:
    """
    Create a snapshot from a successful sync.
    
    Args:
        epic_key: The epic key.
        markdown_path: Path to the markdown file.
        stories: Stories that were synced.
        matches: Mapping of story IDs to Jira keys.
        
    Returns:
        A new SyncSnapshot.
    """
    # Compute markdown file hash
    md_path = Path(markdown_path)
    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
        md_hash = hashlib.md5(content.encode()).hexdigest()
    else:
        md_hash = ""
    
    snapshot = SyncSnapshot(
        snapshot_id=SyncSnapshot.generate_id(epic_key, markdown_path),
        epic_key=epic_key,
        markdown_path=markdown_path,
        markdown_hash=md_hash,
    )
    
    for story in stories:
        story_id = str(story.id)
        jira_key = matches.get(story_id, "")
        if jira_key:
            snapshot.stories.append(StorySnapshot.from_story(story, jira_key))
    
    return snapshot

