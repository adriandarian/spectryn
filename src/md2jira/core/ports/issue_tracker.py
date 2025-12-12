"""
Issue Tracker Port - Abstract interface for issue tracking systems.

Implementations:
- JiraAdapter: Atlassian Jira
- (Future) GitHubAdapter: GitHub Issues
- (Future) LinearAdapter: Linear
- (Future) AzureDevOpsAdapter: Azure DevOps
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..domain.entities import Epic, UserStory, Subtask, Comment
from ..domain.value_objects import IssueKey
from ..domain.enums import Status


class IssueTrackerError(Exception):
    """Base exception for issue tracker errors."""
    
    def __init__(self, message: str, issue_key: Optional[str] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.issue_key = issue_key
        self.cause = cause


class AuthenticationError(IssueTrackerError):
    """Authentication failed."""
    pass


class NotFoundError(IssueTrackerError):
    """Issue not found."""
    pass


class PermissionError(IssueTrackerError):
    """Insufficient permissions."""
    pass


class TransitionError(IssueTrackerError):
    """Failed to transition issue status."""
    pass


class RateLimitError(IssueTrackerError):
    """Rate limit exceeded (HTTP 429)."""
    
    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None
    ):
        super().__init__(message, issue_key, cause)
        self.retry_after = retry_after


class TransientError(IssueTrackerError):
    """Transient server error (5xx) that may succeed on retry."""
    pass


@dataclass
class IssueData:
    """
    Generic issue data returned from tracker.
    
    This is a tracker-agnostic representation that adapters
    convert to/from their native formats.
    """
    
    key: str
    summary: str
    description: Optional[Any] = None  # May be rich format
    status: str = ""
    issue_type: str = ""
    assignee: Optional[str] = None
    story_points: Optional[float] = None
    subtasks: list["IssueData"] = field(default_factory=list)
    comments: list[dict[str, Any]] = field(default_factory=list)


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
    def update_issue_description(
        self, 
        issue_key: str, 
        description: Any
    ) -> bool:
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
        story_points: Optional[int] = None,
        assignee: Optional[str] = None,
    ) -> Optional[str]:
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
        description: Optional[Any] = None,
        story_points: Optional[int] = None,
        assignee: Optional[str] = None,
    ) -> bool:
        """Update a subtask's fields."""
        ...
    
    @abstractmethod
    def add_comment(
        self, 
        issue_key: str, 
        body: Any
    ) -> bool:
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

