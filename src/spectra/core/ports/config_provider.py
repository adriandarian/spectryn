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
    ASANA = "asana"
    GITLAB = "gitlab"
    MONDAY = "monday"
    TRELLO = "trello"
    SHORTCUT = "shortcut"
    CLICKUP = "clickup"


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
class GitLabConfig:
    """Configuration for GitLab Issues tracker."""

    token: str  # Personal Access Token or OAuth token
    project_id: str  # Project ID (numeric or path like 'group/project')
    base_url: str = "https://gitlab.com/api/v4"
    group_id: str | None = None  # Optional group ID for epics (Premium/Ultimate)

    # Label configuration
    epic_label: str = "epic"
    story_label: str = "story"
    subtask_label: str = "subtask"

    # Status label mapping (GitLab only has open/closed, use labels for workflow)
    status_labels: dict[str, str] = field(
        default_factory=lambda: {
            "open": "status:open",
            "in progress": "status:in-progress",
            "done": "status:done",
            "closed": "status:done",
        }
    )

    # Use milestones for epics (default) or epic issue type (Premium/Ultimate)
    use_epics: bool = False  # Set to True if Premium/Ultimate and using Epic issue type

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.token and self.project_id)


@dataclass
class MondayConfig:
    """Configuration for Monday.com tracker."""

    api_token: str
    board_id: str
    workspace_id: str | None = None
    api_url: str = "https://api.monday.com/v2"

    # Column mapping configuration
    status_column_id: str | None = None  # Status column ID (auto-detected if None)
    priority_column_id: str | None = None  # Priority column ID (auto-detected if None)
    story_points_column_id: str | None = None  # Story points column ID (auto-detected if None)

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.api_token and self.board_id)


@dataclass
class TrelloConfig:
    """Configuration for Trello tracker."""

    api_key: str
    api_token: str
    board_id: str
    api_url: str = "https://api.trello.com/1"

    # List mapping configuration (status mapping)
    # Maps status names to list names/IDs
    status_lists: dict[str, str] = field(default_factory=dict)

    # Label mapping for priorities
    priority_labels: dict[str, str] = field(
        default_factory=lambda: {
            "Critical": "red",
            "High": "orange",
            "Medium": "yellow",
            "Low": "green",
        }
    )

    # Subtask handling: "checklist" or "linked_card"
    subtask_mode: str = "checklist"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.api_key and self.api_token and self.board_id)


@dataclass
class ShortcutConfig:
    """Configuration for Shortcut (formerly Clubhouse) tracker."""

    api_token: str
    workspace_id: str
    api_url: str = "https://api.app.shortcut.com/api/v3"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.api_token and self.workspace_id)


@dataclass
class ClickUpConfig:
    """Configuration for ClickUp tracker."""

    api_token: str
    space_id: str | None = None
    folder_id: str | None = None
    list_id: str | None = None
    api_url: str = "https://api.clickup.com/api/v2"

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return bool(self.api_token)


# =============================================================================
# VALIDATION CONFIGURATION - Nested Dataclasses
# =============================================================================


@dataclass
class IssueTypesConfig:
    """Configuration for issue types."""

    allowed: list[str] = field(default_factory=lambda: ["Story", "User Story"])
    default: str = "User Story"
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "story": "User Story",
            "us": "User Story",
            "feature": "Story",
            "bug": "Bug",
            "defect": "Bug",
            "task": "Task",
            "spike": "Spike",
            "research": "Spike",
        }
    )


@dataclass
class NamingConfig:
    """Configuration for ID and naming conventions."""

    allowed_id_prefixes: list[str] = field(default_factory=list)
    id_pattern: str = ""
    require_sequential_ids: bool = False
    normalize_ids_uppercase: bool = True
    epic_id_pattern: str = ""
    title_case: str = ""  # "title", "sentence", "upper", ""


@dataclass
class ContentConfig:
    """Configuration for story content requirements."""

    # Description
    require_description: bool = False
    description_min_length: int = 0
    description_max_length: int = 0

    # User story format
    require_user_story_format: bool = False
    user_story_roles: list[str] = field(default_factory=list)

    # Title
    title_min_length: int = 1
    title_max_length: int = 0
    title_pattern: str = ""
    title_forbidden_words: list[str] = field(default_factory=list)
    title_required_words: list[str] = field(default_factory=list)

    # Acceptance criteria
    require_acceptance_criteria: bool = False
    min_acceptance_criteria: int = 0
    max_acceptance_criteria: int = 0
    ac_format: str = ""  # "given_when_then", "checklist", ""

    # Technical notes
    require_technical_notes: bool = False
    technical_notes_min_length: int = 0

    # Dependencies
    require_dependencies: bool = False
    max_dependencies: int = 0

    # Links
    require_links: bool = False
    min_links: int = 0
    max_links: int = 0
    allowed_link_types: list[str] = field(default_factory=list)

    # Related commits
    require_related_commits: bool = False


@dataclass
class EstimationConfig:
    """Configuration for story points and estimation."""

    require_story_points: bool = False
    min_story_points: int = 0
    max_story_points: int = 0
    allowed_story_points: list[int] = field(default_factory=list)
    fibonacci_only: bool = False
    default_story_points: int = 0

    # Time estimates
    require_time_estimate: bool = False
    time_estimate_unit: str = "hours"  # "hours", "days", "points"
    max_time_estimate: int = 0


@dataclass
class SubtasksConfig:
    """Configuration for subtask constraints."""

    require_subtasks: bool = False
    min_subtasks: int = 0
    max_subtasks: int = 0
    subtask_title_pattern: str = ""
    subtask_title_min_length: int = 1
    subtask_title_max_length: int = 0
    require_subtask_estimates: bool = False
    allowed_subtask_statuses: list[str] = field(default_factory=list)
    require_subtask_assignee: bool = False


@dataclass
class StatusesConfig:
    """Configuration for status values and workflow."""

    allowed: list[str] = field(default_factory=list)
    default: str = "Planned"
    require_status: bool = False
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "todo": "Planned",
            "to do": "Planned",
            "to-do": "Planned",
            "backlog": "Planned",
            "open": "Planned",
            "new": "Planned",
            "wip": "In Progress",
            "working": "In Progress",
            "in development": "In Progress",
            "in review": "In Progress",
            "review": "In Progress",
            "complete": "Done",
            "completed": "Done",
            "finished": "Done",
            "closed": "Done",
            "resolved": "Done",
            "on hold": "Blocked",
            "waiting": "Blocked",
        }
    )
    allowed_transitions: dict[str, list[str]] = field(default_factory=dict)
    require_status_emoji: bool = False


@dataclass
class PrioritiesConfig:
    """Configuration for priority values."""

    allowed: list[str] = field(default_factory=list)
    default: str = "Medium"
    require_priority: bool = False
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "p0": "Critical",
            "p1": "High",
            "p2": "Medium",
            "p3": "Low",
            "p4": "Low",
            "blocker": "Critical",
            "urgent": "Critical",
            "highest": "Critical",
            "major": "High",
            "minor": "Low",
            "trivial": "Low",
            "lowest": "Low",
        }
    )
    require_priority_emoji: bool = False


@dataclass
class LabelsConfig:
    """Configuration for labels and tags."""

    required: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    min_labels: int = 0
    max_labels: int = 0
    label_pattern: str = ""
    label_prefix: str = ""
    case_sensitive: bool = False


@dataclass
class ComponentsConfig:
    """Configuration for components."""

    required: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    min_components: int = 0
    max_components: int = 0
    require_component: bool = False


@dataclass
class AssigneesConfig:
    """Configuration for assignees."""

    require_assignee: bool = False
    allowed: list[str] = field(default_factory=list)
    default: str = ""
    max_assignees: int = 1


@dataclass
class SprintsConfig:
    """Configuration for sprints/iterations."""

    require_sprint: bool = False
    allowed: list[str] = field(default_factory=list)
    default: str = ""
    sprint_pattern: str = ""


@dataclass
class VersionsConfig:
    """Configuration for fix versions."""

    require_version: bool = False
    allowed: list[str] = field(default_factory=list)
    version_pattern: str = ""


@dataclass
class DueDatesConfig:
    """Configuration for due dates."""

    require_due_date: bool = False
    max_days_in_future: int = 0
    min_days_in_future: int = 0
    date_format: str = "YYYY-MM-DD"


@dataclass
class EpicConfig:
    """Configuration for epic-level constraints."""

    max_stories: int = 0
    min_stories: int = 0
    require_summary: bool = False
    require_description: bool = False
    max_total_story_points: int = 0
    require_epic_owner: bool = False
    max_in_progress_stories: int = 0


@dataclass
class CustomFieldsConfig:
    """Configuration for custom fields."""

    mappings: dict[str, str] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(
        default_factory=lambda: {
            "sp": "story_points",
            "pts": "story_points",
            "est": "story_points",
            "points": "story_points",
            "pri": "priority",
            "prio": "priority",
        }
    )


@dataclass
class FormattingConfig:
    """Configuration for markdown formatting."""

    require_status_emoji: bool = False
    require_priority_emoji: bool = False
    allowed_header_levels: list[int] = field(default_factory=lambda: [1, 2, 3])
    require_metadata_table: bool = False
    allowed_markdown_elements: list[str] = field(default_factory=list)
    max_heading_depth: int = 4


@dataclass
class ExternalLinksConfig:
    """Configuration for external links and references."""

    require_external_links: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    forbidden_domains: list[str] = field(default_factory=list)
    require_https: bool = True


@dataclass
class BehaviorConfig:
    """Configuration for validation behavior."""

    strict: bool = False
    fail_fast: bool = False
    ignore_rules: list[str] = field(default_factory=list)
    warning_as_info: list[str] = field(default_factory=list)

    # Auto-fix behavior
    auto_fix_ids: bool = False
    auto_fix_statuses: bool = False
    auto_fix_priorities: bool = False
    auto_fix_case: bool = False
    auto_add_defaults: bool = False

    # Output
    show_suggestions: bool = True
    max_errors_shown: int = 50
    group_by_story: bool = True


@dataclass
class WorkflowConfig:
    """Configuration for workflow and process constraints."""

    definition_of_done: list[str] = field(default_factory=list)
    ready_for_dev_criteria: list[str] = field(default_factory=list)
    require_review: bool = False
    require_qa_signoff: bool = False
    blocked_by_types: list[str] = field(default_factory=list)
    max_blocked_days: int = 0
    require_parent: bool = False
    require_epic_link: bool = False
    allowed_parent_types: list[str] = field(default_factory=list)


@dataclass
class SchedulingConfig:
    """Configuration for time and scheduling constraints."""

    max_story_age_days: int = 0
    stale_after_days: int = 0
    require_start_date: bool = False
    max_duration_days: int = 0
    work_days_only: bool = False
    sla_days: int = 0
    warn_approaching_sla_days: int = 0
    require_end_date: bool = False


@dataclass
class DevelopmentConfig:
    """Configuration for git and development workflow."""

    branch_naming_pattern: str = ""
    require_branch_link: bool = False
    require_pr_link: bool = False
    commit_message_pattern: str = ""
    require_code_review: bool = False
    allowed_branch_prefixes: list[str] = field(default_factory=list)
    require_merge_before_done: bool = False


@dataclass
class QualityConfig:
    """Configuration for testing and quality requirements."""

    require_test_cases: bool = False
    min_test_cases: int = 0
    require_test_plan: bool = False
    bug_severity_levels: list[str] = field(default_factory=list)
    require_reproduction_steps: bool = False
    require_expected_behavior: bool = False
    require_actual_behavior: bool = False
    require_environment_info: bool = False
    require_screenshots: bool = False


@dataclass
class DocumentationConfig:
    """Configuration for documentation requirements."""

    require_api_docs: bool = False
    require_changelog_entry: bool = False
    require_release_notes: bool = False
    documentation_link_required: bool = False
    readme_update_required: bool = False
    require_user_docs: bool = False
    docs_location_pattern: str = ""


@dataclass
class SecurityConfig:
    """Configuration for security and compliance requirements."""

    require_security_review: bool = False
    confidentiality_levels: list[str] = field(default_factory=list)
    require_data_classification: bool = False
    pii_handling_required: bool = False
    require_threat_model: bool = False
    compliance_tags: list[str] = field(default_factory=list)
    require_vulnerability_scan: bool = False
    security_labels: list[str] = field(default_factory=list)


@dataclass
class TemplatesConfig:
    """Configuration for story and epic templates."""

    story_template: str = ""
    bug_template: str = ""
    epic_template: str = ""
    task_template: str = ""
    enforce_template: bool = False
    allowed_sections: list[str] = field(default_factory=list)
    required_sections: list[str] = field(default_factory=list)
    section_order: list[str] = field(default_factory=list)


@dataclass
class AlertsConfig:
    """Configuration for notifications and alerts."""

    alert_on_blocked: bool = False
    alert_on_stale: bool = False
    alert_threshold_days: int = 0
    alert_on_over_estimate: bool = False
    watchers: list[str] = field(default_factory=list)
    alert_on_unassigned: bool = False
    alert_on_no_estimate: bool = False
    notification_channels: list[str] = field(default_factory=list)


@dataclass
class DependenciesConfig:
    """Configuration for dependency management."""

    require_dependency_check: bool = False
    max_dependencies: int = 0
    allow_circular_dependencies: bool = False
    dependency_types: list[str] = field(default_factory=list)
    cross_project_deps_allowed: bool = True
    require_dependency_approval: bool = False
    blocked_dependency_types: list[str] = field(default_factory=list)


@dataclass
class ArchivalConfig:
    """Configuration for archival and cleanup."""

    auto_archive_after_days: int = 0
    archive_cancelled: bool = False
    retention_days: int = 0
    exclude_from_archive: list[str] = field(default_factory=list)
    archive_on_done: bool = False
    cleanup_stale_branches: bool = False


@dataclass
class CapacityConfig:
    """Configuration for capacity and workload management."""

    max_stories_per_assignee: int = 0
    max_points_per_sprint: int = 0
    warn_overload_threshold: int = 0
    require_capacity_check: bool = False
    max_parallel_stories: int = 0
    points_per_day: float = 0.0


@dataclass
class EnvironmentsConfig:
    """Configuration for deployment environments."""

    allowed_environments: list[str] = field(default_factory=list)
    require_environment: bool = False
    environment_order: list[str] = field(default_factory=list)
    require_rollback_plan: bool = False
    require_deployment_notes: bool = False
    production_approval_required: bool = False


@dataclass
class ValidationConfig:
    """Complete validation configuration with all constraint options.

    All fields are optional. If not set, defaults are used.
    If no validation section exists, no constraints are enforced beyond defaults.

    Configuration sections:
    - issue_types: Issue type constraints and aliases
    - naming: ID prefixes, patterns, case normalization
    - content: Description, AC, title, links requirements
    - estimation: Story points, Fibonacci, time estimates
    - subtasks: Subtask count, title patterns, estimates
    - statuses: Allowed statuses, aliases, workflow transitions
    - priorities: Allowed priorities, aliases
    - labels: Required/allowed/forbidden labels
    - components: Component requirements
    - assignees: Assignee requirements
    - sprints: Sprint/iteration settings
    - versions: Fix version settings
    - due_dates: Due date requirements
    - epic: Epic-level constraints
    - custom_fields: Custom field mappings
    - formatting: Markdown formatting rules
    - external_links: Link domain rules
    - behavior: Validation behavior (strict, auto-fix, etc.)
    - workflow: Definition of done, review requirements
    - scheduling: Time constraints, SLAs
    - development: Git/branch requirements
    - quality: Testing requirements
    - documentation: Doc requirements
    - security: Security and compliance
    - templates: Story/epic templates
    - alerts: Notification settings
    - dependencies: Dependency management
    - archival: Cleanup and archival
    - capacity: Workload management
    - environments: Deployment environments
    """

    # Core validation sections
    issue_types: IssueTypesConfig = field(default_factory=IssueTypesConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    content: ContentConfig = field(default_factory=ContentConfig)
    estimation: EstimationConfig = field(default_factory=EstimationConfig)
    subtasks: SubtasksConfig = field(default_factory=SubtasksConfig)
    statuses: StatusesConfig = field(default_factory=StatusesConfig)
    priorities: PrioritiesConfig = field(default_factory=PrioritiesConfig)
    labels: LabelsConfig = field(default_factory=LabelsConfig)
    components: ComponentsConfig = field(default_factory=ComponentsConfig)
    assignees: AssigneesConfig = field(default_factory=AssigneesConfig)
    sprints: SprintsConfig = field(default_factory=SprintsConfig)
    versions: VersionsConfig = field(default_factory=VersionsConfig)
    due_dates: DueDatesConfig = field(default_factory=DueDatesConfig)
    epic: EpicConfig = field(default_factory=EpicConfig)
    custom_fields: CustomFieldsConfig = field(default_factory=CustomFieldsConfig)
    formatting: FormattingConfig = field(default_factory=FormattingConfig)
    external_links: ExternalLinksConfig = field(default_factory=ExternalLinksConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)

    # Extended validation sections
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    development: DevelopmentConfig = field(default_factory=DevelopmentConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    documentation: DocumentationConfig = field(default_factory=DocumentationConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    templates: TemplatesConfig = field(default_factory=TemplatesConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    dependencies: DependenciesConfig = field(default_factory=DependenciesConfig)
    archival: ArchivalConfig = field(default_factory=ArchivalConfig)
    capacity: CapacityConfig = field(default_factory=CapacityConfig)
    environments: EnvironmentsConfig = field(default_factory=EnvironmentsConfig)

    # Legacy fields for backward compatibility (deprecated, use nested configs)
    @property
    def allowed_issue_types(self) -> list[str]:
        """Backward compatible accessor."""
        return self.issue_types.allowed

    @property
    def default_issue_type(self) -> str:
        """Backward compatible accessor."""
        return self.issue_types.default

    @property
    def allowed_id_prefixes(self) -> list[str]:
        """Backward compatible accessor."""
        return self.naming.allowed_id_prefixes

    @property
    def strict(self) -> bool:
        """Backward compatible accessor."""
        return self.behavior.strict

    @property
    def min_story_points(self) -> int:
        """Backward compatible accessor."""
        return self.estimation.min_story_points

    @property
    def max_story_points(self) -> int:
        """Backward compatible accessor."""
        return self.estimation.max_story_points


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

    # Source file update settings
    update_source_file: bool = False  # Write tracker info back to source file


@dataclass
class AppConfig:
    """Complete application configuration."""

    tracker: TrackerConfig
    sync: SyncConfig
    validation: ValidationConfig = field(default_factory=ValidationConfig)

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
