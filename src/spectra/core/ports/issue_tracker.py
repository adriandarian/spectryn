"""
Issue Tracker Port - Abstract interface for issue tracking systems.

Implementations:
- JiraAdapter: Atlassian Jira
- GitHubAdapter: GitHub Issues
- LinearAdapter: Linear
- AzureDevOpsAdapter: Azure DevOps
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Import exceptions from centralized module and re-export for backward compatibility
from spectra.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    RateLimitError,
    ResourceNotFoundError,
    TrackerError,
    TransientError,
    TransitionError,
)


# Re-export with backward-compatible aliases
IssueTrackerError = TrackerError
NotFoundError = ResourceNotFoundError
PermissionError = AccessDeniedError

__all__ = [
    # Re-exported exceptions (backward compatibility)
    "AccessDeniedError",
    "AuthenticationError",
    # Module types
    "IssueData",
    "IssueLink",
    "IssueTrackerError",
    "IssueTrackerPort",
    "LinkType",
    "NotFoundError",
    "PermissionError",
    "RateLimitError",
    "ResourceNotFoundError",
    "TrackerError",
    "TransientError",
    "TransitionError",
]


class LinkType(Enum):
    """
    Standard issue link types.

    These map to common link types across issue trackers:
    - Jira: blocks, is blocked by, relates to, etc.
    - GitHub: cross-references
    - Azure DevOps: related, predecessor, successor
    """

    BLOCKS = "blocks"
    IS_BLOCKED_BY = "is blocked by"
    RELATES_TO = "relates to"
    DUPLICATES = "duplicates"
    IS_DUPLICATED_BY = "is duplicated by"
    CLONES = "clones"
    IS_CLONED_BY = "is cloned by"
    DEPENDS_ON = "depends on"
    IS_DEPENDENCY_OF = "is dependency of"

    @classmethod
    def from_string(cls, value: str) -> "LinkType":
        """Parse link type from string."""
        value_lower = value.lower().strip()

        mappings = {
            "blocks": cls.BLOCKS,
            "is blocked by": cls.IS_BLOCKED_BY,
            "blocked by": cls.IS_BLOCKED_BY,
            "relates to": cls.RELATES_TO,
            "related to": cls.RELATES_TO,
            "relates": cls.RELATES_TO,
            "duplicates": cls.DUPLICATES,
            "duplicate of": cls.DUPLICATES,
            "is duplicated by": cls.IS_DUPLICATED_BY,
            "clones": cls.CLONES,
            "is cloned by": cls.IS_CLONED_BY,
            "depends on": cls.DEPENDS_ON,
            "dependency of": cls.IS_DEPENDENCY_OF,
            "is dependency of": cls.IS_DEPENDENCY_OF,
        }

        return mappings.get(value_lower, cls.RELATES_TO)

    @property
    def jira_name(self) -> str:
        """Get Jira link type name."""
        jira_mappings = {
            LinkType.BLOCKS: "Blocks",
            LinkType.IS_BLOCKED_BY: "Blocks",  # Jira uses same type, direction differs
            LinkType.RELATES_TO: "Relates",
            LinkType.DUPLICATES: "Duplicate",
            LinkType.IS_DUPLICATED_BY: "Duplicate",
            LinkType.CLONES: "Cloners",
            LinkType.IS_CLONED_BY: "Cloners",
            LinkType.DEPENDS_ON: "Dependency",
            LinkType.IS_DEPENDENCY_OF: "Dependency",
        }
        return jira_mappings.get(self, "Relates")

    @property
    def is_outward(self) -> bool:
        """Check if this is an outward link direction."""
        return self in (
            LinkType.BLOCKS,
            LinkType.DUPLICATES,
            LinkType.CLONES,
            LinkType.IS_DEPENDENCY_OF,
        )


@dataclass
class IssueLink:
    """
    A link between two issues.

    Supports cross-project linking by storing full issue keys.
    """

    link_type: LinkType
    target_key: str  # Full issue key (e.g., "OTHER-123")
    source_key: str | None = None  # Optional source key

    def __str__(self) -> str:
        return f"{self.link_type.value} → {self.target_key}"

    @property
    def target_project(self) -> str:
        """Extract project key from target issue key."""
        if "-" in self.target_key:
            return self.target_key.split("-")[0]
        return ""


# Exception classes are now imported from ..exceptions and re-exported above
# for backward compatibility. See core/exceptions.py for definitions.


@dataclass
class IssueData:
    """
    Generic issue data returned from tracker.

    This is a tracker-agnostic representation that adapters
    convert to/from their native formats.
    """

    key: str
    summary: str
    description: Any | None = None  # May be rich format
    status: str = ""
    issue_type: str = ""
    assignee: str | None = None
    story_points: float | None = None
    subtasks: list["IssueData"] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)
    links: list[IssueLink] = field(default_factory=list)

    @property
    def project_key(self) -> str:
        """Extract project key from issue key."""
        if "-" in self.key:
            return self.key.split("-")[0]
        return ""


class IssueTrackerPort(ABC):
    """
    Abstract interface for issue tracking systems.

    All issue tracker adapters must implement this interface.
    This enables swapping between Jira, GitHub Issues, etc.
    """

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the tracker name (e.g., 'Jira', 'GitHub')."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the tracker is connected and authenticated."""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Test the connection to the tracker."""
        ...

    # -------------------------------------------------------------------------
    # Read Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        ...

    @abstractmethod
    def get_issue(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue by key.

        Args:
            issue_key: The issue key (e.g., 'PROJ-123')

        Returns:
            IssueData with issue details

        Raises:
            NotFoundError: If issue doesn't exist
        """
        ...

    @abstractmethod
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic.

        Args:
            epic_key: The epic's key

        Returns:
            List of child issues (usually stories)
        """
        ...

    @abstractmethod
    def get_issue_comments(self, issue_key: str) -> list[dict]:
        """
        Fetch all comments on an issue.

        Args:
            issue_key: The issue key

        Returns:
            List of comment dictionaries
        """
        ...

    @abstractmethod
    def get_issue_status(self, issue_key: str) -> str:
        """Get the current status of an issue."""
        ...

    @abstractmethod
    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        """
        Search for issues using tracker-specific query language.

        Args:
            query: Search query (e.g., JQL for Jira)
            max_results: Maximum results to return

        Returns:
            List of matching issues
        """
        ...

    # -------------------------------------------------------------------------
    # Write Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        """
        Update an issue's description.

        Args:
            issue_key: The issue to update
            description: New description (format depends on tracker)

        Returns:
            True if successful
        """
        ...

    @abstractmethod
    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: Any,
        project_key: str,
        story_points: int | None = None,
        assignee: str | None = None,
        priority: str | None = None,
    ) -> str | None:
        """
        Create a subtask under a parent issue.

        Args:
            parent_key: Parent issue key
            summary: Subtask title
            description: Subtask description
            project_key: Project key for the new issue
            story_points: Optional story points
            assignee: Optional assignee ID

        Returns:
            New subtask key, or None if failed
        """
        ...

    @abstractmethod
    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        """Update a subtask's fields."""
        ...

    @abstractmethod
    def add_comment(self, issue_key: str, body: Any) -> bool:
        """Add a comment to an issue."""
        ...

    @abstractmethod
    def transition_issue(
        self,
        issue_key: str,
        target_status: str,
    ) -> bool:
        """
        Transition an issue to a new status.

        Args:
            issue_key: Issue to transition
            target_status: Target status name

        Returns:
            True if successful

        Raises:
            TransitionError: If transition failed
        """
        ...

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_available_transitions(self, issue_key: str) -> list[dict]:
        """Get available transitions for an issue."""
        ...

    @abstractmethod
    def format_description(self, markdown: str) -> Any:
        """
        Convert markdown to tracker-specific format.

        Args:
            markdown: Markdown text

        Returns:
            Tracker-specific format (e.g., ADF for Jira)
        """
        ...

    # -------------------------------------------------------------------------
    # Link Operations (Optional - default implementations provided)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        """
        Get all links for an issue.

        Args:
            issue_key: Issue to get links for

        Returns:
            List of IssueLinks
        """
        return []

    def create_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType,
    ) -> bool:
        """
        Create a link between two issues.

        Supports cross-project linking.

        Args:
            source_key: Source issue key (e.g., "PROJ-123")
            target_key: Target issue key (e.g., "OTHER-456")
            link_type: Type of link to create

        Returns:
            True if successful
        """
        return False

    def delete_link(
        self,
        source_key: str,
        target_key: str,
        link_type: LinkType | None = None,
    ) -> bool:
        """
        Delete a link between issues.

        Args:
            source_key: Source issue key
            target_key: Target issue key
            link_type: Optional specific link type to delete

        Returns:
            True if successful
        """
        return False

    def get_link_types(self) -> list[dict[str, Any]]:
        """
        Get available link types from the tracker.

        Returns:
            List of link type definitions
        """
        return []
