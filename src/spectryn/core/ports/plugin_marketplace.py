"""
Plugin Marketplace Port - Abstract interface for plugin discovery and installation.

This module defines the contract for plugin marketplace operations including
searching, installing, publishing, and managing community plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class PluginCategory(Enum):
    """Categories for organizing plugins."""

    PARSER = auto()  # Input format parsers
    TRACKER = auto()  # Issue tracker integrations
    FORMATTER = auto()  # Output formatters
    HOOK = auto()  # Processing hooks
    COMMAND = auto()  # Custom CLI commands
    THEME = auto()  # UI themes
    TEMPLATE = auto()  # Project templates
    OTHER = auto()  # Uncategorized


class PluginStatus(Enum):
    """Installation status of a plugin."""

    NOT_INSTALLED = auto()
    INSTALLED = auto()
    UPDATE_AVAILABLE = auto()
    DEPRECATED = auto()


@dataclass
class PluginAuthor:
    """Information about a plugin author."""

    name: str
    email: str | None = None
    url: str | None = None
    github: str | None = None


@dataclass
class PluginVersionInfo:
    """Information about a specific plugin version."""

    version: str
    release_date: datetime
    download_url: str
    checksum: str | None = None
    changelog: str | None = None
    min_spectra_version: str | None = None
    max_spectra_version: str | None = None
    dependencies: list[str] = field(default_factory=list)


@dataclass
class MarketplacePlugin:
    """
    Complete information about a plugin in the marketplace.

    Contains metadata, version history, statistics, and installation state.
    """

    # Core identification
    name: str
    description: str
    category: PluginCategory
    author: PluginAuthor

    # Versioning
    latest_version: str
    versions: list[PluginVersionInfo] = field(default_factory=list)

    # Repository info
    repository_url: str | None = None
    homepage_url: str | None = None
    documentation_url: str | None = None

    # Statistics
    downloads: int = 0
    stars: int = 0
    last_updated: datetime | None = None

    # Keywords for search
    keywords: list[str] = field(default_factory=list)

    # License
    license: str | None = None

    # Current state
    status: PluginStatus = PluginStatus.NOT_INSTALLED
    installed_version: str | None = None

    # Verification
    verified: bool = False
    official: bool = False


@dataclass
class SearchQuery:
    """Query parameters for searching plugins."""

    query: str | None = None
    category: PluginCategory | None = None
    author: str | None = None
    keywords: list[str] = field(default_factory=list)
    verified_only: bool = False
    official_only: bool = False
    sort_by: str = "downloads"  # downloads, stars, updated, name
    sort_order: str = "desc"  # asc, desc
    limit: int = 50
    offset: int = 0


@dataclass
class SearchResult:
    """Results from a plugin search."""

    plugins: list[MarketplacePlugin]
    total_count: int
    query: SearchQuery


@dataclass
class InstallResult:
    """Result of a plugin installation."""

    success: bool
    plugin_name: str
    version: str
    message: str
    installed_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PublishResult:
    """Result of publishing a plugin."""

    success: bool
    plugin_name: str
    version: str
    message: str
    marketplace_url: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class MarketplaceInfo:
    """Information about the marketplace connection."""

    name: str
    url: str
    total_plugins: int
    connected: bool
    last_sync: datetime | None = None
    api_version: str | None = None


class PluginMarketplaceError(Exception):
    """Base exception for marketplace operations."""


class PluginNotFoundError(PluginMarketplaceError):
    """Plugin not found in marketplace."""


class InstallationError(PluginMarketplaceError):
    """Error during plugin installation."""


class PublishError(PluginMarketplaceError):
    """Error during plugin publishing."""


class AuthenticationError(PluginMarketplaceError):
    """Authentication failed for marketplace operations."""


class PluginMarketplacePort(ABC):
    """
    Abstract interface for plugin marketplace operations.

    Implementations can connect to different registries (GitHub, PyPI, custom).
    """

    # -------------------------------------------------------------------------
    # Search & Discovery
    # -------------------------------------------------------------------------

    @abstractmethod
    def search(self, query: SearchQuery) -> SearchResult:
        """
        Search for plugins in the marketplace.

        Args:
            query: Search parameters

        Returns:
            SearchResult with matching plugins

        Raises:
            PluginMarketplaceError: If search fails
        """
        ...

    @abstractmethod
    def get_plugin(self, name: str) -> MarketplacePlugin | None:
        """
        Get detailed information about a specific plugin.

        Args:
            name: Plugin name/identifier

        Returns:
            Plugin info or None if not found
        """
        ...

    @abstractmethod
    def list_categories(self) -> list[tuple[PluginCategory, int]]:
        """
        List all categories with plugin counts.

        Returns:
            List of (category, count) tuples
        """
        ...

    @abstractmethod
    def get_featured(self, limit: int = 10) -> list[MarketplacePlugin]:
        """
        Get featured/recommended plugins.

        Args:
            limit: Maximum plugins to return

        Returns:
            List of featured plugins
        """
        ...

    @abstractmethod
    def get_trending(self, limit: int = 10, period: str = "week") -> list[MarketplacePlugin]:
        """
        Get trending plugins by recent downloads/stars.

        Args:
            limit: Maximum plugins to return
            period: Time period (day, week, month)

        Returns:
            List of trending plugins
        """
        ...

    # -------------------------------------------------------------------------
    # Installation
    # -------------------------------------------------------------------------

    @abstractmethod
    def install(
        self,
        name: str,
        version: str | None = None,
        force: bool = False,
    ) -> InstallResult:
        """
        Install a plugin from the marketplace.

        Args:
            name: Plugin name
            version: Specific version (None for latest)
            force: Force reinstall if already installed

        Returns:
            InstallResult with status and details

        Raises:
            PluginNotFoundError: If plugin doesn't exist
            InstallationError: If installation fails
        """
        ...

    @abstractmethod
    def uninstall(self, name: str) -> bool:
        """
        Uninstall a plugin.

        Args:
            name: Plugin name

        Returns:
            True if uninstalled successfully

        Raises:
            PluginNotFoundError: If plugin not installed
        """
        ...

    @abstractmethod
    def update(self, name: str, version: str | None = None) -> InstallResult:
        """
        Update an installed plugin.

        Args:
            name: Plugin name
            version: Target version (None for latest)

        Returns:
            InstallResult with status

        Raises:
            PluginNotFoundError: If plugin not installed
            InstallationError: If update fails
        """
        ...

    @abstractmethod
    def list_installed(self) -> list[MarketplacePlugin]:
        """
        List all installed plugins with marketplace info.

        Returns:
            List of installed plugins with their status
        """
        ...

    @abstractmethod
    def check_updates(self) -> list[tuple[MarketplacePlugin, str]]:
        """
        Check for available updates.

        Returns:
            List of (plugin, new_version) tuples for plugins with updates
        """
        ...

    # -------------------------------------------------------------------------
    # Publishing
    # -------------------------------------------------------------------------

    @abstractmethod
    def publish(
        self,
        plugin_path: str,
        token: str | None = None,
    ) -> PublishResult:
        """
        Publish a plugin to the marketplace.

        Args:
            plugin_path: Path to plugin directory or package
            token: Authentication token (None to use configured)

        Returns:
            PublishResult with status

        Raises:
            AuthenticationError: If authentication fails
            PublishError: If publishing fails
        """
        ...

    @abstractmethod
    def unpublish(self, name: str, version: str | None = None, token: str | None = None) -> bool:
        """
        Remove a plugin from the marketplace.

        Args:
            name: Plugin name
            version: Specific version (None for all)
            token: Authentication token

        Returns:
            True if removed successfully

        Raises:
            AuthenticationError: If authentication fails
            PluginNotFoundError: If plugin doesn't exist
        """
        ...

    # -------------------------------------------------------------------------
    # Marketplace Info
    # -------------------------------------------------------------------------

    @abstractmethod
    def info(self) -> MarketplaceInfo:
        """
        Get marketplace connection information.

        Returns:
            MarketplaceInfo with status and stats
        """
        ...

    @abstractmethod
    def sync(self) -> bool:
        """
        Synchronize local cache with marketplace.

        Returns:
            True if sync successful
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close marketplace connection and cleanup resources."""
        ...
