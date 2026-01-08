"""
Centralized constants for spectra.

This module defines all magic strings, numeric constants, and configuration
defaults used throughout the application. Organizing constants here:

1. Makes the codebase more maintainable
2. Prevents typos in string literals
3. Provides a single source of truth for default values
4. Makes it easier to change values across the codebase
"""

from typing import Final


# =============================================================================
# Application Metadata
# =============================================================================

APP_NAME: Final[str] = "spectra"
APP_VERSION: Final[str] = "2.0.0"
APP_DESCRIPTION: Final[str] = "Sync markdown documentation with issue trackers"


# =============================================================================
# HTTP Constants
# =============================================================================


class ContentType:
    """HTTP Content-Type header values."""

    JSON: Final[str] = "application/json"
    FORM: Final[str] = "application/x-www-form-urlencoded"
    TEXT: Final[str] = "text/plain"
    HTML: Final[str] = "text/html"


class HttpHeader:
    """HTTP header names."""

    CONTENT_TYPE: Final[str] = "Content-Type"
    ACCEPT: Final[str] = "Accept"
    AUTHORIZATION: Final[str] = "Authorization"
    RETRY_AFTER: Final[str] = "Retry-After"
    USER_AGENT: Final[str] = "User-Agent"


class HttpMethod:
    """HTTP methods."""

    GET: Final[str] = "GET"
    POST: Final[str] = "POST"
    PUT: Final[str] = "PUT"
    DELETE: Final[str] = "DELETE"
    PATCH: Final[str] = "PATCH"


# =============================================================================
# API Defaults
# =============================================================================


class ApiDefaults:
    """Default values for API clients."""

    # Timeouts (seconds)
    TIMEOUT: Final[float] = 30.0
    CONNECT_TIMEOUT: Final[float] = 10.0
    READ_TIMEOUT: Final[float] = 30.0

    # Retry configuration
    MAX_RETRIES: Final[int] = 3
    INITIAL_DELAY: Final[float] = 1.0
    MAX_DELAY: Final[float] = 30.0
    BACKOFF_FACTOR: Final[float] = 2.0
    JITTER: Final[float] = 0.1

    # Rate limiting
    REQUESTS_PER_SECOND: Final[float] = 10.0
    BURST_SIZE: Final[int] = 10

    # Connection pooling
    POOL_CONNECTIONS: Final[int] = 10
    POOL_MAXSIZE: Final[int] = 10
    POOL_BLOCK: Final[bool] = False

    # Batch operations
    BATCH_SIZE: Final[int] = 50
    MAX_CONCURRENT: Final[int] = 5


# =============================================================================
# Jira Constants
# =============================================================================


class JiraApi:
    """Jira API constants."""

    # API version
    VERSION: Final[str] = "3"

    # API path prefix
    REST_PATH: Final[str] = "/rest/api"

    # Endpoints
    ISSUE_ENDPOINT: Final[str] = "issue"
    ISSUE_BULK_ENDPOINT: Final[str] = "issue/bulk"
    SEARCH_ENDPOINT: Final[str] = "search"
    MYSELF_ENDPOINT: Final[str] = "myself"
    TRANSITIONS_ENDPOINT: Final[str] = "transitions"
    ISSUELINK_ENDPOINT: Final[str] = "issueLink"
    PROJECT_ENDPOINT: Final[str] = "project"


class JiraField:
    """Jira issue field names."""

    # Core fields
    KEY: Final[str] = "key"
    ID: Final[str] = "id"
    SELF: Final[str] = "self"
    FIELDS: Final[str] = "fields"

    # Issue fields
    SUMMARY: Final[str] = "summary"
    DESCRIPTION: Final[str] = "description"
    STATUS: Final[str] = "status"
    ISSUETYPE: Final[str] = "issuetype"
    PROJECT: Final[str] = "project"
    PARENT: Final[str] = "parent"
    SUBTASKS: Final[str] = "subtasks"
    ASSIGNEE: Final[str] = "assignee"
    REPORTER: Final[str] = "reporter"
    PRIORITY: Final[str] = "priority"
    LABELS: Final[str] = "labels"
    COMPONENTS: Final[str] = "components"
    FIX_VERSIONS: Final[str] = "fixVersions"
    CREATED: Final[str] = "created"
    UPDATED: Final[str] = "updated"
    RESOLUTION: Final[str] = "resolution"
    RESOLUTIONDATE: Final[str] = "resolutiondate"
    COMMENT: Final[str] = "comment"

    # Custom fields (common defaults, can be overridden)
    STORY_POINTS: Final[str] = "customfield_10014"
    EPIC_LINK: Final[str] = "customfield_10008"
    SPRINT: Final[str] = "customfield_10007"

    # Nested field accessors
    NAME: Final[str] = "name"
    ACCOUNT_ID: Final[str] = "accountId"
    EMAIL_ADDRESS: Final[str] = "emailAddress"
    DISPLAY_NAME: Final[str] = "displayName"

    # Standard field sets for API calls
    BASIC_FIELDS: Final[tuple[str, ...]] = ("summary", "description", "status", "issuetype")
    ISSUE_WITH_SUBTASKS: Final[tuple[str, ...]] = (
        "summary",
        "description",
        "status",
        "issuetype",
        "subtasks",
    )
    ALL_CORE_FIELDS: Final[tuple[str, ...]] = (
        "summary",
        "description",
        "status",
        "issuetype",
        "subtasks",
        "assignee",
        "reporter",
        "priority",
        "labels",
        "created",
        "updated",
    )


class IssueTypeName:
    """Standard issue type name strings for API compatibility."""

    EPIC: Final[str] = "Epic"
    STORY: Final[str] = "Story"
    SUBTASK: Final[str] = "Sub-task"
    TASK: Final[str] = "Task"
    BUG: Final[str] = "Bug"
    FEATURE: Final[str] = "Feature"
    IMPROVEMENT: Final[str] = "Improvement"

    # Jira-specific subtask name
    JIRA_SUBTASK: Final[str] = "Sub-task"


# Backwards compatibility alias
IssueType = IssueTypeName


# =============================================================================
# GitHub Constants
# =============================================================================


class GitHubApi:
    """GitHub API constants."""

    BASE_URL: Final[str] = "https://api.github.com"
    VERSION: Final[str] = "2022-11-28"

    # Endpoints
    ISSUES_ENDPOINT: Final[str] = "issues"
    REPOS_ENDPOINT: Final[str] = "repos"
    USER_ENDPOINT: Final[str] = "user"


class GitHubLabel:
    """GitHub label constants."""

    EPIC: Final[str] = "epic"
    STORY: Final[str] = "story"
    SUBTASK: Final[str] = "subtask"
    SPECTRA: Final[str] = "spectra"


# =============================================================================
# Linear Constants
# =============================================================================


class LinearApi:
    """Linear API constants."""

    GRAPHQL_URL: Final[str] = "https://api.linear.app/graphql"


# =============================================================================
# Azure DevOps Constants
# =============================================================================


class AzureDevOpsApi:
    """Azure DevOps API constants."""

    VERSION: Final[str] = "7.0"


class AzureWorkItemType:
    """Azure DevOps work item types."""

    EPIC: Final[str] = "Epic"
    FEATURE: Final[str] = "Feature"
    USER_STORY: Final[str] = "User Story"
    TASK: Final[str] = "Task"
    BUG: Final[str] = "Bug"


# =============================================================================
# Confluence Constants
# =============================================================================


class ConfluenceApi:
    """Confluence API constants."""

    # API paths
    CLOUD_PATH: Final[str] = "/wiki/rest/api"
    SERVER_PATH: Final[str] = "/rest/api"

    # Endpoints
    CONTENT_ENDPOINT: Final[str] = "content"
    SPACE_ENDPOINT: Final[str] = "space"


class ConfluenceLabel:
    """Confluence label constants."""

    EPIC: Final[str] = "epic"
    STORY: Final[str] = "story"
    SPECTRA: Final[str] = "spectra"


# =============================================================================
# File and Path Constants
# =============================================================================


class ConfigFile:
    """Configuration file names and paths."""

    # Config file names (searched in order)
    YAML_NAME: Final[str] = ".spectra.yaml"
    YML_NAME: Final[str] = ".spectra.yml"
    TOML_NAME: Final[str] = ".spectra.toml"
    PYPROJECT: Final[str] = "pyproject.toml"

    # State directory
    STATE_DIR: Final[str] = ".spectra"
    STATE_FILE: Final[str] = "state.json"
    BACKUP_DIR: Final[str] = "backups"
    CACHE_DIR: Final[str] = "cache"

    # pyproject.toml section
    PYPROJECT_SECTION: Final[str] = "tool.spectra"


class FileExtension:
    """File extensions."""

    MARKDOWN: Final[tuple[str, ...]] = (".md", ".markdown")
    YAML: Final[tuple[str, ...]] = (".yaml", ".yml")
    TOML: Final[tuple[str, ...]] = (".toml",)
    JSON: Final[tuple[str, ...]] = (".json",)


# =============================================================================
# Markdown Parser Constants
# =============================================================================


class MarkdownPattern:
    """Markdown parsing patterns and markers."""

    # Headers
    H1_PREFIX: Final[str] = "# "
    H2_PREFIX: Final[str] = "## "
    H3_PREFIX: Final[str] = "### "

    # Special markers
    ACCEPTANCE_CRITERIA_HEADER: Final[str] = "Acceptance Criteria"
    TECHNICAL_NOTES_HEADER: Final[str] = "Technical Notes"
    SUBTASKS_HEADER: Final[str] = "Subtasks"

    # Status markers
    TODO_MARKER: Final[str] = "[ ]"
    DONE_MARKER: Final[str] = "[x]"
    IN_PROGRESS_MARKER: Final[str] = "[-]"


# =============================================================================
# Sync Constants
# =============================================================================


class SyncDefaults:
    """Default values for sync operations."""

    # Backup retention
    MAX_BACKUPS: Final[int] = 10
    BACKUP_RETENTION_DAYS: Final[int] = 30

    # Incremental sync
    FINGERPRINT_ALGORITHM: Final[str] = "sha256"

    # Watch mode
    DEBOUNCE_SECONDS: Final[float] = 2.0
    POLL_INTERVAL_SECONDS: Final[float] = 1.0


# =============================================================================
# Logging Constants
# =============================================================================


class LogFormat:
    """Logging format constants."""

    # Format types
    TEXT: Final[str] = "text"
    JSON: Final[str] = "json"

    # Log levels
    DEBUG: Final[str] = "DEBUG"
    INFO: Final[str] = "INFO"
    WARNING: Final[str] = "WARNING"
    ERROR: Final[str] = "ERROR"

    # Service identifier for structured logging
    SERVICE_NAME: Final[str] = APP_NAME


# =============================================================================
# Exit Codes (reference only - canonical definitions in cli/exit_codes.py)
# =============================================================================


class ExitCode:
    """Exit code constants."""

    SUCCESS: Final[int] = 0
    GENERAL_ERROR: Final[int] = 1
    CONFIG_ERROR: Final[int] = 2
    AUTH_ERROR: Final[int] = 3
    NOT_FOUND: Final[int] = 4
    PERMISSION_ERROR: Final[int] = 5
    VALIDATION_ERROR: Final[int] = 6
    NETWORK_ERROR: Final[int] = 7
    RATE_LIMIT: Final[int] = 8
    SYNC_ERROR: Final[int] = 10
    PARSE_ERROR: Final[int] = 11
    USER_CANCELLED: Final[int] = 130


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "APP_DESCRIPTION",
    # App metadata
    "APP_NAME",
    "APP_VERSION",
    # API defaults
    "ApiDefaults",
    # Azure DevOps
    "AzureDevOpsApi",
    "AzureWorkItemType",
    # Files
    "ConfigFile",
    # Confluence
    "ConfluenceApi",
    "ConfluenceLabel",
    # HTTP
    "ContentType",
    # Exit codes
    "ExitCode",
    "FileExtension",
    # GitHub
    "GitHubApi",
    "GitHubLabel",
    "HttpHeader",
    "HttpMethod",
    "IssueType",
    # Jira
    "JiraApi",
    "JiraField",
    # Linear
    "LinearApi",
    # Logging
    "LogFormat",
    # Markdown
    "MarkdownPattern",
    # Sync
    "SyncDefaults",
]
