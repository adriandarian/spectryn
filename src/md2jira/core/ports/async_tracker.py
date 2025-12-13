"""
Async Issue Tracker Port - Async interface for issue tracking systems.

This module defines the async version of IssueTrackerPort for high-performance
parallel operations. Implementations can use aiohttp or other async HTTP clients.

Usage:
    # Async context manager pattern
    async with tracker as t:
        issues = await t.get_issues_async(["PROJ-1", "PROJ-2", "PROJ-3"])
        
    # Or manually manage lifecycle
    await tracker.connect()
    try:
        issue = await tracker.get_issue_async("PROJ-123")
    finally:
        await tracker.disconnect()
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence

from .issue_tracker import IssueData


class AsyncIssueTrackerPort(ABC):
    """
    Abstract async interface for issue tracking systems.
    
    Provides async versions of core operations for parallel execution.
    Implementations should use this alongside the sync IssueTrackerPort.
    
    The interface is designed to work as an async context manager for
    proper resource cleanup (connection pools, etc.).
    """
    
    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Establish async connection to the tracker.
        
        Creates HTTP session, connection pool, etc.
        """
        ...
    
    @abstractmethod
    async def disconnect(self) -> None:
        """
        Close async connection and cleanup resources.
        
        Closes HTTP sessions, releases connection pool, etc.
        """
        ...
    
    async def __aenter__(self) -> "AsyncIssueTrackerPort":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()
    
    # -------------------------------------------------------------------------
    # Async Read Operations
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def get_issue_async(self, issue_key: str) -> IssueData:
        """
        Fetch a single issue asynchronously.
        
        Args:
            issue_key: The issue key (e.g., 'PROJ-123')
            
        Returns:
            IssueData with issue details
        """
        ...
    
    @abstractmethod
    async def get_issues_async(self, issue_keys: Sequence[str]) -> list[IssueData]:
        """
        Fetch multiple issues in parallel.
        
        Args:
            issue_keys: List of issue keys to fetch
            
        Returns:
            List of IssueData (order matches input keys, None for not found)
        """
        ...
    
    @abstractmethod
    async def get_epic_children_async(self, epic_key: str) -> list[IssueData]:
        """
        Fetch all children of an epic asynchronously.
        
        Args:
            epic_key: The epic's key
            
        Returns:
            List of child issues
        """
        ...
    
    @abstractmethod
    async def search_issues_async(
        self, query: str, max_results: int = 50
    ) -> list[IssueData]:
        """
        Search for issues asynchronously.
        
        Args:
            query: Search query (e.g., JQL for Jira)
            max_results: Maximum results to return
            
        Returns:
            List of matching issues
        """
        ...
    
    # -------------------------------------------------------------------------
    # Async Write Operations
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def update_descriptions_async(
        self,
        updates: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, Optional[str]]]:
        """
        Update multiple issue descriptions in parallel.
        
        Args:
            updates: List of (issue_key, description) tuples
            
        Returns:
            List of (issue_key, success, error_message) tuples
        """
        ...
    
    @abstractmethod
    async def create_subtasks_async(
        self,
        subtasks: Sequence[dict[str, Any]],
    ) -> list[tuple[Optional[str], bool, Optional[str]]]:
        """
        Create multiple subtasks in parallel.
        
        Args:
            subtasks: List of subtask dictionaries with:
                - parent_key: Parent issue key
                - project_key: Project key
                - summary: Subtask title
                - description: Subtask description
                - story_points: Optional story points
                
        Returns:
            List of (created_key_or_none, success, error_message) tuples
        """
        ...
    
    @abstractmethod
    async def transition_issues_async(
        self,
        transitions: Sequence[tuple[str, str]],
    ) -> list[tuple[str, bool, Optional[str]]]:
        """
        Transition multiple issues in parallel.
        
        Args:
            transitions: List of (issue_key, target_status) tuples
            
        Returns:
            List of (issue_key, success, error_message) tuples
        """
        ...
    
    # -------------------------------------------------------------------------
    # Batch Operations
    # -------------------------------------------------------------------------
    
    @abstractmethod
    async def add_comments_async(
        self,
        comments: Sequence[tuple[str, Any]],
    ) -> list[tuple[str, bool, Optional[str]]]:
        """
        Add comments to multiple issues in parallel.
        
        Args:
            comments: List of (issue_key, comment_body) tuples
            
        Returns:
            List of (issue_key, success, error_message) tuples
        """
        ...


__all__ = ["AsyncIssueTrackerPort"]

