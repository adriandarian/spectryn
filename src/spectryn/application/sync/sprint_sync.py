"""
Sprint/Iteration Sync - Parse and sync sprint assignments.

This module provides comprehensive sprint synchronization:
- Parse sprint assignments from markdown
- Sync sprints to/from trackers (Jira, Azure DevOps, etc.)
- Support multiple sprint naming conventions
- Handle sprint planning and backlog organization
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


class SprintState(Enum):
    """State of a sprint."""

    FUTURE = "future"  # Not yet started
    ACTIVE = "active"  # Currently in progress
    CLOSED = "closed"  # Completed
    UNKNOWN = "unknown"


@dataclass
class Sprint:
    """
    Represents a sprint/iteration.

    Sprints are time-boxed periods for completing work.
    """

    id: str = ""
    name: str = ""
    goal: str = ""
    state: SprintState = SprintState.UNKNOWN

    # Dates
    start_date: datetime | None = None
    end_date: datetime | None = None

    # Tracker-specific
    board_id: str | None = None  # Jira board ID
    remote_id: str | None = None  # Tracker's sprint ID

    # Iteration path (Azure DevOps)
    iteration_path: str | None = None

    def is_active(self) -> bool:
        """Check if sprint is currently active."""
        if self.state == SprintState.ACTIVE:
            return True

        if self.start_date and self.end_date:
            now = datetime.now()
            return self.start_date <= now <= self.end_date

        return False

    def is_future(self) -> bool:
        """Check if sprint is in the future."""
        if self.state == SprintState.FUTURE:
            return True

        if self.start_date:
            return datetime.now() < self.start_date

        return False

    def days_remaining(self) -> int | None:
        """Calculate days remaining in sprint."""
        if not self.end_date:
            return None

        delta = self.end_date - datetime.now()
        return max(0, delta.days)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "state": self.state.value,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "board_id": self.board_id,
            "remote_id": self.remote_id,
            "iteration_path": self.iteration_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Sprint":
        """Create from dictionary."""
        start_date = None
        if data.get("start_date"):
            start_date = datetime.fromisoformat(data["start_date"])

        end_date = None
        if data.get("end_date"):
            end_date = datetime.fromisoformat(data["end_date"])

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            state=SprintState(data.get("state", "unknown")),
            start_date=start_date,
            end_date=end_date,
            board_id=data.get("board_id"),
            remote_id=data.get("remote_id"),
            iteration_path=data.get("iteration_path"),
        )

    @classmethod
    def from_jira_sprint(cls, data: dict[str, Any]) -> "Sprint":
        """Create Sprint from Jira sprint API response."""
        state_map = {
            "future": SprintState.FUTURE,
            "active": SprintState.ACTIVE,
            "closed": SprintState.CLOSED,
        }

        from contextlib import suppress

        start_date = None
        if data.get("startDate"):
            with suppress(ValueError):
                start_date = datetime.fromisoformat(data["startDate"].replace("Z", "+00:00"))

        end_date = None
        if data.get("endDate"):
            with suppress(ValueError):
                end_date = datetime.fromisoformat(data["endDate"].replace("Z", "+00:00"))

        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            state=state_map.get(data.get("state", "").lower(), SprintState.UNKNOWN),
            start_date=start_date,
            end_date=end_date,
            board_id=str(data.get("originBoardId", "")),
            remote_id=str(data.get("id", "")),
        )


@dataclass
class SprintAssignment:
    """
    Sprint assignment for a story.

    Tracks which sprint(s) a story is assigned to.
    """

    story_id: str
    issue_key: str | None = None

    # Sprint info
    sprint_name: str | None = None
    sprint_id: str | None = None
    sprint: Sprint | None = None

    # For trackers that support multiple sprints
    additional_sprints: list[Sprint] = field(default_factory=list)

    # Sync metadata
    source: str = "markdown"  # markdown or tracker
    last_synced: datetime | None = None

    def has_sprint(self) -> bool:
        """Check if story has a sprint assigned."""
        return bool(self.sprint_name or self.sprint_id or self.sprint)

    def get_sprint_name(self) -> str | None:
        """Get the sprint name."""
        if self.sprint:
            return self.sprint.name
        return self.sprint_name


@dataclass
class SprintSyncConfig:
    """Configuration for sprint synchronization."""

    enabled: bool = True
    sync_sprint_assignment: bool = True

    # Sync behavior
    push_to_tracker: bool = True  # Push sprint from markdown to tracker
    pull_from_tracker: bool = True  # Pull sprint from tracker to markdown

    # Sprint matching
    match_by_name: bool = True  # Match sprints by name
    match_by_id: bool = True  # Match sprints by ID
    case_sensitive: bool = False  # Case-sensitive sprint name matching

    # Default handling
    default_sprint: str | None = None  # Default sprint for new stories
    use_active_sprint: bool = False  # Assign to active sprint if none specified
    clear_sprint_on_done: bool = False  # Clear sprint when story is done

    # Sprint name patterns
    sprint_pattern: str | None = None  # Regex pattern for sprint names
    allowed_sprints: list[str] = field(default_factory=list)  # Allowed sprint names


class SprintExtractor:
    """Extract sprint information from markdown content."""

    # Patterns for sprint in markdown
    SPRINT_PATTERNS = [
        # | **Sprint** | Sprint 23 |
        r"\|\s*\*\*Sprint\*\*\s*\|\s*([^\|]+)\s*\|",
        # | **Iteration** | Iteration 5 |
        r"\|\s*\*\*Iteration\*\*\s*\|\s*([^\|]+)\s*\|",
        # **Sprint:** Sprint 23
        r"\*\*Sprint:\*\*\s*(.+?)(?:\n|$)",
        # **Iteration:** Iteration 5
        r"\*\*Iteration:\*\*\s*(.+?)(?:\n|$)",
        # Sprint:: Sprint 23 (Obsidian dataview)
        r"Sprint::\s*(.+?)(?:\n|$)",
        # Iteration:: Iteration 5
        r"Iteration::\s*(.+?)(?:\n|$)",
    ]

    # Common sprint name patterns
    SPRINT_NAME_PATTERNS = [
        r"^Sprint\s*(\d+)",  # Sprint 23
        r"^Iteration\s*(\d+)",  # Iteration 5
        r"^(\d{4})-W(\d{2})",  # 2024-W05 (ISO week)
        r"^Q(\d)\s*(\d{4})",  # Q1 2024
        r"^([A-Za-z]+)\s*(\d{4})",  # January 2024
    ]

    def __init__(self, config: SprintSyncConfig | None = None):
        """Initialize the extractor."""
        self.config = config or SprintSyncConfig()

    def extract_from_content(self, content: str, story_id: str) -> SprintAssignment:
        """
        Extract sprint assignment from markdown content.

        Args:
            content: Markdown content
            story_id: Story ID

        Returns:
            SprintAssignment with parsed data
        """
        assignment = SprintAssignment(story_id=story_id, source="markdown")

        # Try each pattern
        for pattern in self.SPRINT_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                sprint_value = match.group(1).strip()
                # Clean up the value
                sprint_value = self._clean_sprint_value(sprint_value)
                if sprint_value and sprint_value.lower() not in ("none", "n/a", "-", ""):
                    assignment.sprint_name = sprint_value
                    break

        return assignment

    def _clean_sprint_value(self, value: str) -> str:
        """Clean up sprint value from markdown."""
        # Remove common non-sprint values
        value = value.strip()

        # Remove emoji
        value = re.sub(r"[🏃‍♂️🏃🔄⏰📅]", "", value).strip()

        # Remove trailing pipes or other markdown artifacts
        return re.sub(r"\s*\|.*$", "", value)

    def parse_sprint_name(self, name: str) -> dict[str, Any]:
        """
        Parse a sprint name into components.

        Args:
            name: Sprint name

        Returns:
            Dictionary with parsed components
        """
        result: dict[str, Any] = {"raw": name, "number": None, "year": None, "week": None}

        # Try Sprint N pattern
        match = re.match(r"Sprint\s*(\d+)", name, re.IGNORECASE)
        if match:
            result["number"] = int(match.group(1))
            return result

        # Try Iteration N pattern
        match = re.match(r"Iteration\s*(\d+)", name, re.IGNORECASE)
        if match:
            result["number"] = int(match.group(1))
            return result

        # Try ISO week pattern (2024-W05)
        match = re.match(r"(\d{4})-W(\d{2})", name)
        if match:
            result["year"] = int(match.group(1))
            result["week"] = int(match.group(2))
            return result

        return result


@dataclass
class SprintSyncResult:
    """Result of sprint sync operation."""

    story_id: str
    issue_key: str | None = None

    # What was synced
    sprint_pushed: bool = False
    sprint_pulled: bool = False

    # Values
    local_sprint: str | None = None
    remote_sprint: str | None = None

    # Sprint details
    sprint: Sprint | None = None

    # Errors
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if sync was successful."""
        return len(self.errors) == 0


class SprintSyncer:
    """
    Synchronize sprint assignments between markdown and issue trackers.

    Supports:
    - Reading/writing sprint assignments
    - Sprint discovery from trackers
    - Sprint name matching
    - Active sprint handling
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: SprintSyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or SprintSyncConfig()
        self.logger = logging.getLogger("SprintSyncer")

        # Cache for sprints
        self._sprint_cache: dict[str, Sprint] = {}
        self._all_sprints: list[Sprint] | None = None

    def sync_story_sprint(
        self,
        story_id: str,
        issue_key: str,
        local_assignment: SprintAssignment | None,
        dry_run: bool = True,
    ) -> SprintSyncResult:
        """
        Sync sprint assignment for a single story/issue.

        Args:
            story_id: Local story ID
            issue_key: Remote issue key
            local_assignment: Sprint assignment from markdown
            dry_run: If True, don't make changes

        Returns:
            SprintSyncResult
        """
        result = SprintSyncResult(story_id=story_id, issue_key=issue_key)

        if not self.config.enabled:
            return result

        # Get remote sprint assignment
        remote_sprint = self._get_remote_sprint(issue_key)

        # Record values
        if local_assignment and local_assignment.has_sprint():
            result.local_sprint = local_assignment.get_sprint_name()

        if remote_sprint:
            result.remote_sprint = remote_sprint.name
            result.sprint = remote_sprint

        # Push sprint to tracker
        if self.config.push_to_tracker and local_assignment and local_assignment.has_sprint():
            sprint_name = local_assignment.get_sprint_name()
            if sprint_name:
                # Find matching sprint in tracker
                target_sprint = self._find_sprint_by_name(sprint_name, issue_key)
                if target_sprint:
                    if dry_run:
                        self.logger.info(
                            f"[DRY-RUN] Would assign {issue_key} to sprint '{target_sprint.name}'"
                        )
                    else:
                        success = self._assign_to_sprint(issue_key, target_sprint)
                        result.sprint_pushed = success
                        if not success:
                            result.errors.append(f"Failed to assign to sprint '{sprint_name}'")
                else:
                    result.errors.append(f"Sprint '{sprint_name}' not found in tracker")

        return result

    def get_available_sprints(
        self, board_id: str | None = None, project_key: str | None = None
    ) -> list[Sprint]:
        """
        Get available sprints from the tracker.

        Args:
            board_id: Optional board ID (Jira)
            project_key: Optional project key

        Returns:
            List of available sprints
        """
        if self._all_sprints is not None:
            return self._all_sprints

        try:
            if hasattr(self.tracker, "get_sprints"):
                raw_sprints = self.tracker.get_sprints(board_id=board_id)
                self._all_sprints = [Sprint.from_jira_sprint(s) for s in raw_sprints]
                return self._all_sprints

            if hasattr(self.tracker, "get_iterations"):
                raw_iterations = self.tracker.get_iterations(project_key=project_key)
                self._all_sprints = [
                    Sprint(
                        id=str(it.get("id", "")),
                        name=it.get("name", ""),
                        iteration_path=it.get("path"),
                        state=SprintState.ACTIVE
                        if it.get("attributes", {}).get("timeFrame") == "current"
                        else SprintState.UNKNOWN,
                    )
                    for it in raw_iterations
                ]
                return self._all_sprints

        except Exception as e:
            self.logger.warning(f"Failed to get sprints: {e}")

        self._all_sprints = []
        return self._all_sprints

    def get_active_sprint(
        self, board_id: str | None = None, project_key: str | None = None
    ) -> Sprint | None:
        """Get the currently active sprint."""
        sprints = self.get_available_sprints(board_id, project_key)
        for sprint in sprints:
            if sprint.is_active():
                return sprint
        return None

    def _get_remote_sprint(self, issue_key: str) -> Sprint | None:
        """Get sprint assignment from remote tracker."""
        try:
            if hasattr(self.tracker, "get_issue_sprint"):
                sprint_data = self.tracker.get_issue_sprint(issue_key)
                if sprint_data:
                    return Sprint.from_jira_sprint(sprint_data)

            # Fallback: try to get from issue fields
            issue = self.tracker.get_issue(issue_key)
            if hasattr(issue, "sprint") and issue.sprint:
                return Sprint(name=issue.sprint)

        except Exception as e:
            self.logger.warning(f"Failed to get sprint for {issue_key}: {e}")

        return None

    def _find_sprint_by_name(self, name: str, issue_key: str | None = None) -> Sprint | None:
        """Find a sprint by name."""
        # Check cache first
        cache_key = name.lower() if not self.config.case_sensitive else name
        if cache_key in self._sprint_cache:
            return self._sprint_cache[cache_key]

        # Get project from issue key if available
        project_key = None
        if issue_key and "-" in issue_key:
            project_key = issue_key.split("-")[0]

        # Get all sprints and search
        sprints = self.get_available_sprints(project_key=project_key)

        for sprint in sprints:
            sprint_name = sprint.name
            compare_name = name

            if not self.config.case_sensitive:
                sprint_name = sprint_name.lower()
                compare_name = compare_name.lower()

            if sprint_name == compare_name:
                self._sprint_cache[cache_key] = sprint
                return sprint

            # Fuzzy match: check if names contain each other
            if self.config.match_by_name:
                if compare_name in sprint_name or sprint_name in compare_name:
                    self._sprint_cache[cache_key] = sprint
                    return sprint

        return None

    def _assign_to_sprint(self, issue_key: str, sprint: Sprint) -> bool:
        """Assign an issue to a sprint."""
        try:
            if hasattr(self.tracker, "move_to_sprint"):
                return self.tracker.move_to_sprint(issue_key, sprint.remote_id)

            if hasattr(self.tracker, "set_sprint"):
                return self.tracker.set_sprint(issue_key, sprint.remote_id or sprint.id)

            if hasattr(self.tracker, "set_iteration"):
                return self.tracker.set_iteration(issue_key, sprint.iteration_path or sprint.name)

            self.logger.warning(f"Tracker {self.tracker.name} doesn't support sprint assignment")
            return False

        except Exception as e:
            self.logger.error(f"Failed to assign {issue_key} to sprint: {e}")
            return False


def extract_sprint(
    content: str, story_id: str, config: SprintSyncConfig | None = None
) -> SprintAssignment:
    """
    Convenience function to extract sprint from markdown.

    Args:
        content: Markdown content
        story_id: Story ID
        config: Optional config

    Returns:
        SprintAssignment with parsed data
    """
    extractor = SprintExtractor(config)
    return extractor.extract_from_content(content, story_id)


def parse_sprint_name(name: str) -> dict[str, Any]:
    """
    Parse a sprint name into components.

    Args:
        name: Sprint name (e.g., "Sprint 23", "2024-W05")

    Returns:
        Dictionary with parsed components
    """
    extractor = SprintExtractor()
    return extractor.parse_sprint_name(name)
