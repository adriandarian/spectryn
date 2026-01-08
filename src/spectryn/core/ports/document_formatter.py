"""
Document Formatter Port - Abstract interface for output formatting.

Implementations:
- ADFFormatter: Atlassian Document Format (for Jira)
- (Future) HTMLFormatter: HTML output
- (Future) MarkdownFormatter: Markdown output
"""

from abc import ABC, abstractmethod
from typing import Any

from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.value_objects import CommitRef


class DocumentFormatterPort(ABC):
    """
    Abstract interface for document formatters.

    Formatters convert domain entities into tracker-specific formats.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the formatter name (e.g., 'ADF', 'HTML')."""
        ...

    @abstractmethod
    def format_text(self, text: str) -> Any:
        """
        Convert plain/markdown text to output format.

        Args:
            text: Input text (may contain markdown)

        Returns:
            Formatted output
        """
        ...

    @abstractmethod
    def format_story_description(self, story: UserStory) -> Any:
        """
        Format a story's full description.

        Includes As a/I want/So that, acceptance criteria, etc.

        Args:
            story: UserStory entity

        Returns:
            Formatted description
        """
        ...

    @abstractmethod
    def format_subtask_description(self, subtask: Subtask) -> Any:
        """
        Format a subtask's description.

        Args:
            subtask: Subtask entity

        Returns:
            Formatted description
        """
        ...

    @abstractmethod
    def format_commits_table(self, commits: list[CommitRef]) -> Any:
        """
        Format a table of commits for a comment.

        Args:
            commits: List of CommitRef value objects

        Returns:
            Formatted table
        """
        ...

    @abstractmethod
    def format_heading(self, text: str, level: int = 2) -> Any:
        """Format a heading."""
        ...

    @abstractmethod
    def format_list(self, items: list[str], ordered: bool = False) -> Any:
        """Format a list of items."""
        ...

    @abstractmethod
    def format_task_list(self, items: list[tuple[str, bool]]) -> Any:
        """
        Format a task/checkbox list.

        Args:
            items: List of (text, is_checked) tuples

        Returns:
            Formatted task list
        """
        ...
