"""
Document Output Port - Abstract interface for documentation systems.

Implementations:
- ConfluenceAdapter: Atlassian Confluence pages (Cloud & Server)

Future implementations:
- NotionAdapter: Notion pages (output)
- GoogleDocsAdapter: Google Docs
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from spectryn.core.domain.entities import Epic, UserStory

# Import exceptions from centralized module and re-export for backward compatibility
from spectryn.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    OutputError,
    RateLimitError,
    ResourceNotFoundError,
)


# Re-export with backward-compatible aliases
DocumentOutputError = OutputError
NotFoundError = ResourceNotFoundError
PermissionError = AccessDeniedError

__all__ = [
    # Re-exported exceptions (backward compatibility)
    "AuthenticationError",
    "DocumentOutputError",
    "DocumentOutputPort",
    "NotFoundError",
    # Module types
    "PageData",
    "PermissionError",
    "RateLimitError",
    "SpaceData",
]


@dataclass
class PageData:
    """
    Generic page data for documentation systems.

    Represents a document/page in wiki systems like Confluence.
    """

    id: str
    title: str
    content: str = ""  # HTML or storage format
    space_key: str | None = None
    parent_id: str | None = None
    version: int = 1
    url: str | None = None
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpaceData:
    """
    Wiki space/container data.
    """

    key: str
    name: str
    type: str = "global"  # global, personal
    url: str | None = None


class DocumentOutputPort(ABC):
    """
    Abstract interface for documentation output systems.

    Adapters convert domain entities (Epics, Stories) into
    documentation pages in systems like Confluence.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the adapter name (e.g., 'Confluence')."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the documentation system.

        Raises:
            AuthenticationError: If authentication fails
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection resources."""
        ...

    # -------------------------------------------------------------------------
    # Space/Container Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_space(self, space_key: str) -> SpaceData:
        """
        Get space/container information.

        Args:
            space_key: Space identifier

        Returns:
            SpaceData with space info

        Raises:
            NotFoundError: If space doesn't exist
        """
        ...

    @abstractmethod
    def list_spaces(self) -> list[SpaceData]:
        """
        List available spaces.

        Returns:
            List of SpaceData
        """
        ...

    # -------------------------------------------------------------------------
    # Page Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_page(self, page_id: str) -> PageData:
        """
        Get a page by ID.

        Args:
            page_id: Page identifier

        Returns:
            PageData with page content

        Raises:
            NotFoundError: If page doesn't exist
        """
        ...

    @abstractmethod
    def get_page_by_title(self, space_key: str, title: str) -> PageData | None:
        """
        Find a page by title in a space.

        Args:
            space_key: Space to search in
            title: Page title

        Returns:
            PageData if found, None otherwise
        """
        ...

    @abstractmethod
    def create_page(
        self,
        space_key: str,
        title: str,
        content: str,
        parent_id: str | None = None,
        labels: list[str] | None = None,
    ) -> PageData:
        """
        Create a new page.

        Args:
            space_key: Target space
            title: Page title
            content: Page content (HTML/storage format)
            parent_id: Optional parent page ID
            labels: Optional labels to apply

        Returns:
            Created PageData with ID
        """
        ...

    @abstractmethod
    def update_page(
        self,
        page_id: str,
        title: str,
        content: str,
        version: int,
        labels: list[str] | None = None,
    ) -> PageData:
        """
        Update an existing page.

        Args:
            page_id: Page to update
            title: New title
            content: New content
            version: Current version number (for conflict detection)
            labels: Optional new labels

        Returns:
            Updated PageData
        """
        ...

    @abstractmethod
    def delete_page(self, page_id: str) -> None:
        """
        Delete a page.

        Args:
            page_id: Page to delete
        """
        ...

    # -------------------------------------------------------------------------
    # Epic/Story Publishing
    # -------------------------------------------------------------------------

    @abstractmethod
    def publish_epic(
        self,
        epic: Epic,
        space_key: str,
        parent_id: str | None = None,
        update_existing: bool = True,
    ) -> PageData:
        """
        Publish an epic as a documentation page.

        Creates a page for the epic with child pages for each story,
        or updates existing pages if update_existing is True.

        Args:
            epic: Epic to publish
            space_key: Target space
            parent_id: Optional parent page
            update_existing: Update if pages exist

        Returns:
            Created/updated epic PageData
        """
        ...

    @abstractmethod
    def publish_story(
        self,
        story: UserStory,
        space_key: str,
        parent_id: str | None = None,
        update_existing: bool = True,
    ) -> PageData:
        """
        Publish a story as a documentation page.

        Args:
            story: Story to publish
            space_key: Target space
            parent_id: Optional parent page
            update_existing: Update if page exists

        Returns:
            Created/updated story PageData
        """
        ...

    # -------------------------------------------------------------------------
    # Content Formatting
    # -------------------------------------------------------------------------

    @abstractmethod
    def format_epic_content(self, epic: Epic) -> str:
        """
        Format epic as page content.

        Args:
            epic: Epic to format

        Returns:
            Formatted content string
        """
        ...

    @abstractmethod
    def format_story_content(self, story: UserStory) -> str:
        """
        Format story as page content.

        Args:
            story: Story to format

        Returns:
            Formatted content string
        """
        ...
