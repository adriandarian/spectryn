"""
Centralized exception hierarchy for spectra.

This module defines a consistent exception hierarchy for all error conditions
in the application. All custom exceptions inherit from SpectraError.

Exception Hierarchy:
    SpectraError (base)
    ├── TrackerError (issue tracker operations)
    │   ├── AuthenticationError
    │   │   ├── InvalidCredentialsError
    │   │   └── TokenExpiredError
    │   ├── ResourceNotFoundError
    │   │   ├── IssueNotFoundError
    │   │   ├── ProjectNotFoundError
    │   │   ├── EpicNotFoundError
    │   │   └── UserNotFoundError
    │   ├── AccessDeniedError
    │   │   ├── ReadOnlyAccessError
    │   │   └── InsufficientScopeError
    │   ├── TransitionError
    │   │   ├── InvalidStatusError
    │   │   └── WorkflowViolationError
    │   ├── RateLimitError
    │   │   └── QuotaExceededError
    │   ├── TransientError
    │   │   ├── ServiceUnavailableError
    │   │   └── GatewayError
    │   ├── ConnectionError (network issues)
    │   │   ├── TimeoutError
    │   │   ├── NetworkUnreachableError
    │   │   └── SSLError
    │   ├── ValidationError (data validation)
    │   │   ├── InvalidFieldError
    │   │   └── RequiredFieldError
    │   └── ConflictError (concurrent modification)
    │       └── StaleDataError
    ├── ParserError (document parsing)
    │   ├── SyntaxError
    │   ├── StructureError
    │   └── EncodingError
    ├── OutputError (document output/wiki)
    │   └── (similar subtypes as TrackerError)
    └── ConfigError (configuration)
        ├── ConfigFileError
        ├── ConfigValidationError
        └── MissingConfigError
"""


class SpectraError(Exception):
    """
    Base exception for all spectra errors.

    All custom exceptions in the application should inherit from this class.
    This allows catching all application errors with a single except clause.

    Attributes:
        message: Human-readable error description
        cause: Original exception that caused this error (for chaining)
    """

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


# =============================================================================
# Tracker Errors - Issue tracker operations (Jira, GitHub, Linear, etc.)
# =============================================================================


class TrackerError(SpectraError):
    """
    Base exception for issue tracker errors.

    Raised when operations with issue trackers (Jira, GitHub, Linear, Azure DevOps)
    fail. Subclasses provide more specific error categorization.

    Attributes:
        issue_key: The issue key/ID involved in the error (e.g., "PROJ-123")
    """

    def __init__(self, message: str, issue_key: str | None = None, cause: Exception | None = None):
        super().__init__(message, cause)
        self.issue_key = issue_key


class AuthenticationError(TrackerError):
    """
    Authentication failed.

    Raised when API credentials are invalid, expired, or missing.
    This includes API tokens, OAuth tokens, and basic auth credentials.
    """


class InvalidCredentialsError(AuthenticationError):
    """
    Credentials are invalid or malformed.

    Raised when API tokens, passwords, or other credentials are incorrect.
    This is a permanent error - the credentials need to be fixed.
    """


class TokenExpiredError(AuthenticationError):
    """
    Authentication token has expired.

    Raised when an OAuth or API token has expired and needs to be refreshed.
    Unlike InvalidCredentialsError, this may be recoverable by refreshing the token.
    """


class ResourceNotFoundError(TrackerError):
    """
    Requested resource was not found.

    Raised when an issue, project, user, or other resource doesn't exist.
    Typically corresponds to HTTP 404 responses.

    Note: Named ResourceNotFoundError to avoid confusion with similar exceptions
    in other contexts (e.g., file not found).
    """


class IssueNotFoundError(ResourceNotFoundError):
    """
    Issue was not found.

    Raised when attempting to access an issue that doesn't exist.
    The issue_key attribute contains the missing issue identifier.
    """


class ProjectNotFoundError(ResourceNotFoundError):
    """
    Project was not found.

    Raised when attempting to access a project that doesn't exist
    or the user doesn't have access to.

    Attributes:
        project_key: The project key or ID that was not found.
    """

    def __init__(
        self,
        message: str,
        project_key: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.project_key = project_key


class EpicNotFoundError(ResourceNotFoundError):
    """
    Epic was not found.

    Raised when attempting to access an epic that doesn't exist
    or link issues to a non-existent epic.

    Attributes:
        epic_key: The epic key or ID that was not found.
    """

    def __init__(
        self,
        message: str,
        epic_key: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.epic_key = epic_key


class UserNotFoundError(ResourceNotFoundError):
    """
    User was not found.

    Raised when attempting to assign an issue to a user that doesn't exist
    or reference an unknown user.

    Attributes:
        username: The username or user ID that was not found.
    """

    def __init__(
        self,
        message: str,
        username: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.username = username


class AccessDeniedError(TrackerError):
    """
    Insufficient permissions for the requested operation.

    Raised when the authenticated user lacks permission to perform the action.
    Typically corresponds to HTTP 403 responses.

    Note: Named AccessDeniedError instead of PermissionError to avoid
    shadowing Python's built-in PermissionError.
    """


class ReadOnlyAccessError(AccessDeniedError):
    """
    User has read-only access to the resource.

    Raised when attempting to modify a resource the user can view
    but not edit.
    """


class InsufficientScopeError(AccessDeniedError):
    """
    API token lacks required scope/permissions.

    Raised when an API token doesn't have the necessary OAuth scopes
    or permissions for the requested operation.

    Attributes:
        required_scope: The scope or permission that is missing.
    """

    def __init__(
        self,
        message: str,
        required_scope: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.required_scope = required_scope


class TransitionError(TrackerError):
    """
    Failed to transition issue status.

    Raised when a status transition is not allowed by the workflow,
    or when the transition doesn't exist.
    """


class InvalidStatusError(TransitionError):
    """
    The target status is invalid.

    Raised when attempting to transition to a status that doesn't exist
    or is not valid for the issue type.

    Attributes:
        status: The invalid status that was requested.
        valid_statuses: List of valid statuses (if known).
    """

    def __init__(
        self,
        message: str,
        status: str | None = None,
        valid_statuses: list[str] | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.status = status
        self.valid_statuses = valid_statuses


class WorkflowViolationError(TransitionError):
    """
    Transition violates workflow rules.

    Raised when a transition is blocked by workflow rules,
    required fields, or conditions.

    Attributes:
        from_status: Current status of the issue.
        to_status: Target status of the transition.
        reason: Specific reason the transition is blocked.
    """

    def __init__(
        self,
        message: str,
        from_status: str | None = None,
        to_status: str | None = None,
        reason: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.from_status = from_status
        self.to_status = to_status
        self.reason = reason


class RateLimitError(TrackerError):
    """
    Rate limit exceeded.

    Raised when the API rate limit is exceeded. The retry_after attribute
    indicates how many seconds to wait before retrying.

    Attributes:
        retry_after: Seconds to wait before retrying (from Retry-After header)
    """

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.retry_after = retry_after


class TransientError(TrackerError):
    """
    Transient server error that may succeed on retry.

    Raised for temporary server errors (5xx HTTP status codes).
    These operations should be retried with exponential backoff.
    """


class QuotaExceededError(RateLimitError):
    """
    API quota has been exceeded.

    Raised when the API quota (daily, monthly, etc.) is exhausted.
    Unlike RateLimitError, this typically requires waiting longer
    or upgrading the plan.

    Attributes:
        quota_type: Type of quota exceeded (e.g., "daily", "monthly").
        reset_time: When the quota resets (ISO 8601 timestamp).
    """

    def __init__(
        self,
        message: str,
        quota_type: str | None = None,
        reset_time: str | None = None,
        retry_after: int | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, retry_after, issue_key, cause)
        self.quota_type = quota_type
        self.reset_time = reset_time


class ServiceUnavailableError(TransientError):
    """
    Service is temporarily unavailable.

    Raised when the tracker service is down for maintenance
    or experiencing issues (HTTP 503).
    """


class GatewayError(TransientError):
    """
    Gateway or proxy error.

    Raised when there's an issue with the gateway or proxy
    (HTTP 502 Bad Gateway or 504 Gateway Timeout).

    Attributes:
        gateway: The gateway/proxy that reported the error.
    """

    def __init__(
        self,
        message: str,
        gateway: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.gateway = gateway


# =============================================================================
# Connection Errors - Network and connectivity issues
# =============================================================================


class ConnectionError(TrackerError):
    """
    Network connection error.

    Base class for network-related errors that prevent communication
    with the tracker API.

    Note: This intentionally shadows the built-in ConnectionError
    for consistency within the spectra exception hierarchy.
    """


class TimeoutError(ConnectionError):
    """
    Request timed out.

    Raised when a request takes longer than the configured timeout.
    May succeed on retry if the service is slow.

    Attributes:
        timeout_seconds: The timeout value that was exceeded.
        operation: The operation that timed out.
    """

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        operation: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.timeout_seconds = timeout_seconds
        self.operation = operation


class NetworkUnreachableError(ConnectionError):
    """
    Network is unreachable.

    Raised when the network or host cannot be reached.
    Typically indicates DNS failure or network configuration issues.

    Attributes:
        host: The host that could not be reached.
    """

    def __init__(
        self,
        message: str,
        host: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.host = host


class SSLError(ConnectionError):
    """
    SSL/TLS certificate error.

    Raised when SSL certificate validation fails or there's
    a TLS handshake error.

    Attributes:
        cert_error: Description of the certificate error.
    """

    def __init__(
        self,
        message: str,
        cert_error: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.cert_error = cert_error


# =============================================================================
# Validation Errors - Data validation issues
# =============================================================================


class ValidationError(TrackerError):
    """
    Data validation failed.

    Base class for errors where the input data doesn't meet
    the requirements of the tracker.
    """


class InvalidFieldError(ValidationError):
    """
    Field value is invalid.

    Raised when a field value doesn't meet validation rules
    (wrong type, invalid format, out of range, etc.).

    Attributes:
        field_name: Name of the invalid field.
        field_value: The invalid value (sanitized).
        expected: Description of expected value.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        field_value: str | None = None,
        expected: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.field_name = field_name
        self.field_value = field_value
        self.expected = expected


class RequiredFieldError(ValidationError):
    """
    Required field is missing.

    Raised when a mandatory field is not provided.

    Attributes:
        field_name: Name of the missing required field.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.field_name = field_name


# =============================================================================
# Conflict Errors - Concurrent modification issues
# =============================================================================


class ConflictError(TrackerError):
    """
    Resource conflict detected.

    Base class for errors where concurrent modification or
    stale data causes a conflict.
    """


class StaleDataError(ConflictError):
    """
    Data is stale and was modified by another process.

    Raised when attempting to update a resource that has been
    modified since it was last fetched (optimistic locking failure).

    Attributes:
        current_version: Current version of the resource.
        expected_version: Version the client expected.
    """

    def __init__(
        self,
        message: str,
        current_version: str | None = None,
        expected_version: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.current_version = current_version
        self.expected_version = expected_version


class DuplicateResourceError(ConflictError):
    """
    Attempted to create a duplicate resource.

    Raised when attempting to create a resource that already exists.

    Attributes:
        existing_id: ID of the existing resource.
    """

    def __init__(
        self,
        message: str,
        existing_id: str | None = None,
        issue_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, issue_key, cause)
        self.existing_id = existing_id


# =============================================================================
# Parser Errors - Document parsing operations
# =============================================================================


class ParserError(SpectraError):
    """
    Error during document parsing.

    Raised when parsing markdown, YAML, or other input formats fails.
    Provides context about where the error occurred.

    Attributes:
        line_number: Line number where the error occurred (1-indexed)
        source: Source file path or identifier
    """

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, cause)
        self.line_number = line_number
        self.source = source

    def __str__(self) -> str:
        parts = [self.message]
        if self.source:
            parts.insert(0, f"{self.source}")
        if self.line_number:
            parts.insert(1 if self.source else 0, f"line {self.line_number}")
        if self.cause:
            parts.append(f"(caused by: {self.cause})")
        return ": ".join(parts) if len(parts) > 1 else parts[0]


class ParserSyntaxError(ParserError):
    """
    Syntax error in the document.

    Raised when the document contains invalid syntax that prevents parsing.
    For example, invalid markdown formatting or malformed YAML.

    Attributes:
        expected: What was expected at this position.
        actual: What was actually found.
    """

    def __init__(
        self,
        message: str,
        expected: str | None = None,
        actual: str | None = None,
        line_number: int | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, line_number, source, cause)
        self.expected = expected
        self.actual = actual


class StructureError(ParserError):
    """
    Document structure is invalid.

    Raised when the document structure doesn't match expectations.
    For example, missing required sections, invalid hierarchy, or
    missing epic/story/subtask structure.

    Attributes:
        section: The section where the error occurred.
        expected_structure: Description of expected structure.
    """

    def __init__(
        self,
        message: str,
        section: str | None = None,
        expected_structure: str | None = None,
        line_number: int | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, line_number, source, cause)
        self.section = section
        self.expected_structure = expected_structure


class EncodingError(ParserError):
    """
    File encoding error.

    Raised when the document cannot be decoded due to encoding issues.

    Attributes:
        detected_encoding: The encoding that was detected or attempted.
        expected_encoding: The encoding that was expected.
    """

    def __init__(
        self,
        message: str,
        detected_encoding: str | None = None,
        expected_encoding: str | None = None,
        line_number: int | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, line_number, source, cause)
        self.detected_encoding = detected_encoding
        self.expected_encoding = expected_encoding


class InvalidFieldValueError(ParserError):
    """
    Field value in the document is invalid.

    Raised when a parsed field value doesn't match expected format.
    For example, invalid priority value or malformed ID.

    Attributes:
        field_name: Name of the field with invalid value.
        field_value: The invalid value.
        valid_values: List of valid values if known.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        field_value: str | None = None,
        valid_values: list[str] | None = None,
        line_number: int | None = None,
        source: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, line_number, source, cause)
        self.field_name = field_name
        self.field_value = field_value
        self.valid_values = valid_values


# =============================================================================
# Output Errors - Document output operations (Confluence, etc.)
# =============================================================================


class OutputError(SpectraError):
    """
    Base exception for document output errors.

    Raised when operations with documentation systems (Confluence, Notion, etc.)
    fail. Uses the same error types as TrackerError for consistency.

    Attributes:
        page_id: The page/document ID involved in the error
    """

    def __init__(self, message: str, page_id: str | None = None, cause: Exception | None = None):
        super().__init__(message, cause)
        self.page_id = page_id


class OutputAuthenticationError(OutputError):
    """Authentication failed for document output system."""


class OutputNotFoundError(OutputError):
    """Page or space not found in document output system."""


class OutputAccessDeniedError(OutputError):
    """Insufficient permissions for document output operation."""


class OutputRateLimitError(OutputError):
    """Rate limit exceeded for document output system."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        page_id: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, page_id, cause)
        self.retry_after = retry_after


# =============================================================================
# Config Errors - Configuration and settings
# =============================================================================


class ConfigError(SpectraError):
    """
    Base exception for configuration errors.

    Raised when loading or parsing configuration fails.

    Attributes:
        config_path: Path to the configuration file (if applicable)
    """

    def __init__(
        self, message: str, config_path: str | None = None, cause: Exception | None = None
    ):
        super().__init__(message, cause)
        self.config_path = config_path

    def __str__(self) -> str:
        if self.config_path:
            return f"{self.config_path}: {self.message}"
        return self.message


class ConfigFileError(ConfigError):
    """
    Configuration file parsing failed.

    Raised when a YAML, TOML, or other config file cannot be parsed.
    """


class ConfigValidationError(ConfigError):
    """
    Configuration validation failed.

    Raised when configuration values are invalid or missing required fields.

    Attributes:
        field_name: The field that failed validation.
        field_value: The invalid value.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        field_value: str | None = None,
        config_path: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, config_path, cause)
        self.field_name = field_name
        self.field_value = field_value


class MissingConfigError(ConfigError):
    """
    Required configuration is missing.

    Raised when a required configuration file or value is not found.

    Attributes:
        missing_key: The configuration key that is missing.
        env_var: Environment variable that could provide the value.
    """

    def __init__(
        self,
        message: str,
        missing_key: str | None = None,
        env_var: str | None = None,
        config_path: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, config_path, cause)
        self.missing_key = missing_key
        self.env_var = env_var


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================

# These aliases maintain backward compatibility with existing code
# that imports from the old locations. They should be considered
# deprecated and new code should use the canonical names.

# For issue_tracker module compatibility
IssueTrackerError = TrackerError
NotFoundError = ResourceNotFoundError
PermissionError = AccessDeniedError  # Shadows built-in intentionally for compat

# For document_output module compatibility
DocumentOutputError = OutputError


__all__ = [
    "AccessDeniedError",
    "AuthenticationError",
    # Config errors
    "ConfigError",
    "ConfigFileError",
    "ConfigValidationError",
    # Conflict errors
    "ConflictError",
    # Connection errors
    "ConnectionError",
    "DocumentOutputError",
    "DuplicateResourceError",
    # Parser errors
    "EncodingError",
    "EpicNotFoundError",
    "GatewayError",
    "InsufficientScopeError",
    "InvalidCredentialsError",
    "InvalidFieldError",
    "InvalidFieldValueError",
    "InvalidStatusError",
    # Backward compatibility aliases
    "IssueNotFoundError",
    "IssueTrackerError",
    "MissingConfigError",
    "NetworkUnreachableError",
    "NotFoundError",
    "OutputAccessDeniedError",
    "OutputAuthenticationError",
    # Output errors
    "OutputError",
    "OutputNotFoundError",
    "OutputRateLimitError",
    "ParserError",
    "ParserSyntaxError",
    "PermissionError",
    "ProjectNotFoundError",
    "QuotaExceededError",
    "RateLimitError",
    "ReadOnlyAccessError",
    "RequiredFieldError",
    "ResourceNotFoundError",
    "SSLError",
    "ServiceUnavailableError",
    # New base class
    "SpectraError",
    "StaleDataError",
    "StructureError",
    "TimeoutError",
    "TokenExpiredError",
    # Tracker errors (primary names)
    "TrackerError",
    "TransientError",
    "TransitionError",
    "UserNotFoundError",
    # Validation errors
    "ValidationError",
    "WorkflowViolationError",
]
