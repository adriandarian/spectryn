"""
TUI Data - Data providers and models for the TUI.

Provides reactive data models that bridge the spectra core
domain with the Textual TUI framework.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from spectryn.core.domain.entities import Epic, UserStory
from spectryn.core.domain.enums import Priority, Status


class SyncState(Enum):
    """State of a sync operation."""

    IDLE = "idle"
    LOADING = "loading"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"


class ConflictType(Enum):
    """Type of conflict between local and remote."""

    LOCAL_MODIFIED = "local_modified"
    REMOTE_MODIFIED = "remote_modified"
    BOTH_MODIFIED = "both_modified"
    DELETED_REMOTE = "deleted_remote"
    DELETED_LOCAL = "deleted_local"


@dataclass
class StoryConflict:
    """Represents a conflict between local and remote story."""

    story_id: str
    story_title: str
    conflict_type: ConflictType
    local_value: str
    remote_value: str
    field_name: str = "description"
    resolved: bool = False
    resolution: str | None = None  # "local", "remote", "merge"

    def resolve_with_local(self) -> None:
        """Resolve conflict using local value."""
        self.resolved = True
        self.resolution = "local"

    def resolve_with_remote(self) -> None:
        """Resolve conflict using remote value."""
        self.resolved = True
        self.resolution = "remote"


@dataclass
class SyncProgress:
    """Progress of a sync operation."""

    total_operations: int = 0
    completed_operations: int = 0
    current_operation: str = ""
    current_story: str = ""
    phase: str = "idle"  # idle, analyzing, syncing, complete
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_operations == 0:
            return 0.0
        return (self.completed_operations / self.total_operations) * 100

    @property
    def elapsed_time(self) -> float:
        """Calculate elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def is_complete(self) -> bool:
        """Check if sync is complete."""
        return self.phase == "complete"

    @property
    def has_errors(self) -> bool:
        """Check if there are errors."""
        return len(self.errors) > 0


@dataclass
class TUIState:
    """Global state for the TUI application."""

    # File/epic info
    markdown_path: Path | None = None
    epic_key: str | None = None
    epic: Epic | None = None

    # Stories
    stories: list[UserStory] = field(default_factory=list)
    selected_story_id: str | None = None
    selected_stories: set[str] = field(default_factory=set)  # For bulk operations

    # Sync state
    sync_state: SyncState = SyncState.IDLE
    sync_progress: SyncProgress = field(default_factory=SyncProgress)

    # Conflicts
    conflicts: list[StoryConflict] = field(default_factory=list)

    # Config
    dry_run: bool = True
    tracker_type: str = "jira"

    # UI state
    show_help: bool = False
    filter_status: Status | None = None
    filter_priority: Priority | None = None
    search_query: str = ""
    status_filter: str | None = None  # Quick filter: "in_progress", "planned", "done"
    sidebar_visible: bool = True  # Toggle sidebar visibility

    @property
    def has_conflicts(self) -> bool:
        """Check if there are unresolved conflicts."""
        return any(not c.resolved for c in self.conflicts)

    @property
    def unresolved_conflicts_count(self) -> int:
        """Count unresolved conflicts."""
        return sum(1 for c in self.conflicts if not c.resolved)

    def get_selected_story(self) -> UserStory | None:
        """Get the currently selected story."""
        if self.selected_story_id is None:
            return None
        for story in self.stories:
            if str(story.id) == self.selected_story_id:
                return story
        return None

    def get_filtered_stories(self) -> list[UserStory]:
        """Get stories filtered by current filter settings."""
        result = self.stories

        if self.filter_status:
            result = [s for s in result if s.status == self.filter_status]

        if self.filter_priority:
            result = [s for s in result if s.priority == self.filter_priority]

        if self.search_query:
            query = self.search_query.lower()
            result = [
                s
                for s in result
                if query in s.title.lower()
                or query in str(s.id).lower()
                or (s.external_key and query in str(s.external_key).lower())
            ]

        return result


def load_stories_from_file(path: Path) -> tuple[list[UserStory], Epic | None]:
    """
    Load stories from a markdown file.

    Args:
        path: Path to the markdown file.

    Returns:
        Tuple of (stories list, epic or None).
    """
    from spectryn.adapters import MarkdownParser

    parser = MarkdownParser()
    stories = parser.parse_stories(str(path))

    # Try to extract epic info from the file
    epic = None
    try:
        content = path.read_text()
        # Look for epic header pattern
        import re

        epic_match = re.search(r"^#\s+([A-Z]+-\d+):\s*(.+)$", content, re.MULTILINE)
        if epic_match:
            from spectryn.core.domain.value_objects import IssueKey

            epic = Epic(
                key=IssueKey(epic_match.group(1)),
                title=epic_match.group(2).strip(),
                stories=stories,
            )
    except Exception:
        pass

    return stories, epic


def create_demo_state() -> TUIState:
    """Create a demo state for testing the TUI."""
    from spectryn.core.domain.value_objects import IssueKey, StoryId

    stories = [
        UserStory(
            id=StoryId("US-001"),
            title="User Authentication",
            story_points=5,
            status=Status.DONE,
            priority=Priority.HIGH,
            external_key=IssueKey("PROJ-101"),
        ),
        UserStory(
            id=StoryId("US-002"),
            title="Dashboard Layout",
            story_points=3,
            status=Status.IN_PROGRESS,
            priority=Priority.MEDIUM,
            external_key=IssueKey("PROJ-102"),
        ),
        UserStory(
            id=StoryId("US-003"),
            title="API Rate Limiting",
            story_points=8,
            status=Status.PLANNED,
            priority=Priority.HIGH,
        ),
        UserStory(
            id=StoryId("US-004"),
            title="Email Notifications",
            story_points=5,
            status=Status.IN_REVIEW,
            priority=Priority.LOW,
        ),
    ]

    epic = Epic(
        key=IssueKey("PROJ-100"),
        title="User Management System",
        stories=stories,
    )

    return TUIState(
        epic_key="PROJ-100",
        epic=epic,
        stories=stories,
        selected_story_id="US-001",
    )
