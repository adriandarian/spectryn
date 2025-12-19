"""
Configuration Provider Port - Abstract interface for configuration.

Implementations:
- EnvironmentConfigProvider: Load from env vars and .env
- (Future) FileConfigProvider: Load from YAML/TOML config files
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrackerType(Enum):
    """Supported issue tracker types."""

    JIRA = "jira"
    GITHUB = "github"
    LINEAR = "linear"
    AZURE_DEVOPS = "azure_devops"


@dataclass
class TrackerConfig:
    """Configuration for an issue tracker (Jira)."""

    url: str
    email: str
    api_token: str
    project_key: str | None = None

    # Jira-specific
    story_points_field: str = "customfield_10014"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.url and self.email and self.api_token)


@dataclass
class GitHubConfig:
    """Configuration for GitHub Issues tracker."""

    token: str
    owner: str
    repo: str
    base_url: str = "https://api.github.com"

    # Label configuration
    epic_label: str = "epic"
    story_label: str = "story"
    subtask_label: str = "subtask"

    # Status label mapping
    status_labels: dict[str, str] = field(
        default_factory=lambda: {
            "open": "status:open",
            "in progress": "status:in-progress",
            "done": "status:done",
        }
    )

    # Subtask handling
    subtasks_as_issues: bool = False

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.token and self.owner and self.repo)


@dataclass
class LinearConfig:
    """Configuration for Linear tracker."""

    api_key: str
    team_key: str
    api_url: str = "https://api.linear.app/graphql"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.api_key and self.team_key)


@dataclass
class AzureDevOpsConfig:
    """Configuration for Azure DevOps tracker."""

    organization: str
    project: str
    pat: str  # Personal Access Token
    base_url: str = "https://dev.azure.com"

    # Work item type mappings
    epic_type: str = "Epic"
    story_type: str = "User Story"
    task_type: str = "Task"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.organization and self.project and self.pat)


@dataclass
class SyncConfig:
    """Configuration for sync operations."""

    dry_run: bool = True
    confirm_changes: bool = True
    verbose: bool = False

    # Phase control
    sync_epic: bool = True  # Update epic issue itself from markdown
    create_stories: bool = True  # Create new stories in tracker if they don't exist
    sync_descriptions: bool = True
    sync_subtasks: bool = True
    sync_comments: bool = True
    sync_statuses: bool = True

    # Filters
    story_filter: str | None = None

    # Output
    export_path: str | None = None

    # Backup settings
    backup_enabled: bool = True  # Auto-backup before sync
    backup_dir: str | None = None  # Custom backup directory
    backup_max_count: int = 10  # Max backups to keep per epic
    backup_retention_days: int = 30  # Delete backups older than this

    # Cache settings
    cache_enabled: bool = True  # Enable response caching
    cache_ttl: float = 300.0  # Default cache TTL in seconds (5 min)
    cache_max_size: int = 1000  # Maximum cache entries
    cache_dir: str | None = None  # For file-based cache (None = memory)

    # Incremental sync settings
    incremental: bool = False  # Enable incremental sync (only changed stories)
    incremental_state_dir: str | None = None  # Dir to store sync state
    force_full_sync: bool = False  # Force full sync even if incremental enabled


@dataclass
class AppConfig:
    """Complete application configuration."""

    tracker: TrackerConfig
    sync: SyncConfig

    # Paths
    markdown_path: str | None = None
    epic_key: str | None = None

    def validate(self) -> list[str]:
        """
        Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.tracker.url:
            errors.append("Missing tracker URL (JIRA_URL)")
        if not self.tracker.email:
            errors.append("Missing tracker email (JIRA_EMAIL)")
        if not self.tracker.api_token:
            errors.append("Missing API token (JIRA_API_TOKEN)")

        return errors


class ConfigProviderPort(ABC):
    """
    Abstract interface for configuration providers.

    Configuration can come from various sources:
    - Environment variables
    - .env files
    - YAML/TOML config files
    - Command line arguments
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the provider name."""
        ...

    @abstractmethod
    def load(self) -> AppConfig:
        """
        Load configuration from source.

        Returns:
            Complete application configuration
        """
        ...

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a specific configuration value.

        Args:
            key: Configuration key (dot notation supported)
            default: Default value if not found

        Returns:
            Configuration value
        """
        ...

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        ...

    @abstractmethod
    def validate(self) -> list[str]:
        """
        Validate loaded configuration.

        Returns:
            List of validation errors
        """
        ...
