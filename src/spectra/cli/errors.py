"""
Error Formatting - Rich, actionable error messages for the CLI.

Provides user-friendly error messages with:
- Clear problem description
- Actionable suggestions for resolution
- Links to relevant documentation
- Error codes for searchability
"""

from dataclasses import dataclass, field
from enum import Enum

from spectra.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    ConfigError,
    ConfigFileError,
    ConfigValidationError,
    Md2JiraError,
    OutputAccessDeniedError,
    OutputAuthenticationError,
    OutputNotFoundError,
    OutputRateLimitError,
    ParserError,
    RateLimitError,
    ResourceNotFoundError,
    TrackerError,
    TransientError,
    TransitionError,
)


class ErrorCode(str, Enum):
    """
    Error codes for quick reference and searchability.

    Format: MD2J-XXX where XXX is the error number.
    Users can search for these codes in documentation.
    """

    # Configuration errors (001-099)
    CONFIG_MISSING_URL = "MD2J-001"
    CONFIG_MISSING_EMAIL = "MD2J-002"
    CONFIG_MISSING_TOKEN = "MD2J-003"
    CONFIG_INVALID_FILE = "MD2J-004"
    CONFIG_SYNTAX_ERROR = "MD2J-005"

    # Authentication errors (100-199)
    AUTH_INVALID_CREDENTIALS = "MD2J-100"
    AUTH_TOKEN_EXPIRED = "MD2J-101"
    AUTH_PERMISSION_DENIED = "MD2J-102"

    # Connection errors (200-299)
    CONN_FAILED = "MD2J-200"
    CONN_TIMEOUT = "MD2J-201"
    CONN_RATE_LIMITED = "MD2J-202"
    CONN_TRANSIENT = "MD2J-203"

    # Resource errors (300-399)
    RESOURCE_NOT_FOUND = "MD2J-300"
    RESOURCE_ISSUE_NOT_FOUND = "MD2J-301"
    RESOURCE_PROJECT_NOT_FOUND = "MD2J-302"
    RESOURCE_EPIC_NOT_FOUND = "MD2J-303"

    # Parser errors (400-499)
    PARSER_INVALID_MARKDOWN = "MD2J-400"
    PARSER_NO_STORIES = "MD2J-401"
    PARSER_INVALID_YAML = "MD2J-402"

    # Transition errors (500-599)
    TRANSITION_NOT_ALLOWED = "MD2J-500"
    TRANSITION_INVALID_STATUS = "MD2J-501"

    # File errors (600-699)
    FILE_NOT_FOUND = "MD2J-600"
    FILE_PERMISSION_DENIED = "MD2J-601"

    # General errors (900-999)
    UNKNOWN = "MD2J-999"


@dataclass
class FormattedError:
    """
    A rich, formatted error message with context and suggestions.

    Attributes:
        code: Unique error code for reference.
        title: Short, descriptive title.
        message: Detailed error message.
        suggestions: List of actionable suggestions to resolve the error.
        docs_url: Optional link to relevant documentation.
        details: Optional additional technical details.
        commands: Optional CLI commands to run.
        quick_fix: Optional one-liner fix command.
    """

    code: ErrorCode
    title: str
    message: str
    suggestions: list[str] = field(default_factory=list)
    docs_url: str | None = None
    details: str | None = None
    commands: list[str] = field(default_factory=list)  # CLI commands to try
    quick_fix: str | None = None  # One-liner fix command

    def format(self, color: bool = True) -> str:
        """Format the error for terminal display."""
        from .output import Colors, Symbols

        lines: list[str] = []

        # Title with error code
        if color:
            title_line = (
                f"{Colors.RED}{Colors.BOLD}{Symbols.CROSS} {self.title}{Colors.RESET} "
                f"{Colors.DIM}[{self.code.value}]{Colors.RESET}"
            )
        else:
            title_line = f"✗ {self.title} [{self.code.value}]"
        lines.append(title_line)

        # Message
        lines.append("")
        if color:
            lines.append(f"  {Colors.RED}{self.message}{Colors.RESET}")
        else:
            lines.append(f"  {self.message}")

        # Details (if any)
        if self.details:
            lines.append("")
            if color:
                lines.append(f"  {Colors.DIM}Details: {self.details}{Colors.RESET}")
            else:
                lines.append(f"  Details: {self.details}")

        # Quick fix (prominent single command)
        if self.quick_fix:
            lines.append("")
            if color:
                lines.append(f"  {Colors.GREEN}{Colors.BOLD}⚡ Quick fix:{Colors.RESET}")
                lines.append(f"    {Colors.YELLOW}$ {self.quick_fix}{Colors.RESET}")
            else:
                lines.append("  ⚡ Quick fix:")
                lines.append(f"    $ {self.quick_fix}")

        # Suggestions
        if self.suggestions:
            lines.append("")
            if color:
                lines.append(f"  {Colors.CYAN}{Colors.BOLD}How to fix:{Colors.RESET}")
            else:
                lines.append("  How to fix:")

            for i, suggestion in enumerate(self.suggestions, 1):
                if color:
                    lines.append(f"    {Colors.CYAN}{i}.{Colors.RESET} {suggestion}")
                else:
                    lines.append(f"    {i}. {suggestion}")

        # Commands to try
        if self.commands:
            lines.append("")
            if color:
                lines.append(f"  {Colors.CYAN}{Colors.BOLD}Commands to try:{Colors.RESET}")
            else:
                lines.append("  Commands to try:")

            for cmd in self.commands:
                if color:
                    lines.append(
                        f"    {Colors.DIM}${Colors.RESET} {Colors.YELLOW}{cmd}{Colors.RESET}"
                    )
                else:
                    lines.append(f"    $ {cmd}")

        # Documentation link
        if self.docs_url:
            lines.append("")
            if color:
                lines.append(
                    f"  {Colors.DIM}📖 Documentation: {Colors.RESET}"
                    f"{Colors.BLUE}{self.docs_url}{Colors.RESET}"
                )
            else:
                lines.append(f"  📖 Documentation: {self.docs_url}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/YAML output."""
        return {
            "code": self.code.value,
            "title": self.title,
            "message": self.message,
            "suggestions": self.suggestions,
            "commands": self.commands if self.commands else None,
            "quick_fix": self.quick_fix,
            "docs_url": self.docs_url,
            "details": self.details,
        }


class ErrorFormatter:
    """
    Formats exceptions into rich, user-friendly error messages.

    Provides context-aware formatting with actionable suggestions
    based on the exception type and content.
    """

    # Base documentation URL
    DOCS_BASE = "https://spectra.dev"

    def __init__(self, color: bool = True, verbose: bool = False):
        """
        Initialize the error formatter.

        Args:
            color: Whether to use ANSI color codes.
            verbose: Whether to include technical details.
        """
        self.color = color
        self.verbose = verbose

    def format(self, exc: Exception) -> FormattedError:
        """
        Format an exception into a rich error message.

        Args:
            exc: The exception to format.

        Returns:
            FormattedError with full context and suggestions.
        """
        # Dispatch to specific formatters based on exception type
        if isinstance(exc, AuthenticationError):
            return self._format_auth_error(exc)
        if isinstance(exc, AccessDeniedError):
            return self._format_permission_error(exc)
        if isinstance(exc, ResourceNotFoundError):
            return self._format_not_found_error(exc)
        if isinstance(exc, RateLimitError):
            return self._format_rate_limit_error(exc)
        if isinstance(exc, TransientError):
            return self._format_transient_error(exc)
        if isinstance(exc, TransitionError):
            return self._format_transition_error(exc)
        if isinstance(exc, ParserError):
            return self._format_parser_error(exc)
        if isinstance(exc, ConfigFileError):
            return self._format_config_file_error(exc)
        if isinstance(exc, ConfigValidationError):
            return self._format_config_validation_error(exc)
        if isinstance(exc, ConfigError):
            return self._format_config_error(exc)
        if isinstance(exc, TrackerError):
            return self._format_tracker_error(exc)
        if isinstance(exc, OutputAuthenticationError):
            return self._format_output_auth_error(exc)
        if isinstance(exc, OutputAccessDeniedError):
            return self._format_output_permission_error(exc)
        if isinstance(exc, OutputNotFoundError):
            return self._format_output_not_found_error(exc)
        if isinstance(exc, OutputRateLimitError):
            return self._format_output_rate_limit_error(exc)
        if isinstance(exc, FileNotFoundError):
            return self._format_file_not_found(exc)
        if isinstance(exc, PermissionError):
            return self._format_file_permission_error(exc)
        if isinstance(exc, ConnectionError):
            return self._format_connection_error(exc)
        if isinstance(exc, Md2JiraError):
            return self._format_generic_spectra_error(exc)

        return self._format_unknown_error(exc)

    def format_string(self, exc: Exception) -> str:
        """Format an exception to a string for display."""
        return self.format(exc).format(color=self.color)

    # -------------------------------------------------------------------------
    # Authentication Errors
    # -------------------------------------------------------------------------

    def _format_auth_error(self, exc: AuthenticationError) -> FormattedError:
        """Format authentication error."""
        message = str(exc) if str(exc) else "Failed to authenticate with the issue tracker."

        # Check for specific patterns in the message
        suggestions = []
        if "401" in message.lower() or "unauthorized" in message.lower():
            suggestions = [
                "Verify your API token is correct and hasn't expired",
                "Regenerate your API token at: https://id.atlassian.com/manage-profile/security/api-tokens",
                "Ensure JIRA_EMAIL matches the email associated with the token",
                "Check that your Jira account is active and not suspended",
            ]
        else:
            suggestions = [
                "Check that JIRA_API_TOKEN is set correctly",
                "Verify JIRA_EMAIL matches your Atlassian account email",
                "Ensure your API token hasn't expired",
            ]

        return FormattedError(
            code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            title="Authentication Failed",
            message=message,
            suggestions=suggestions,
            docs_url=f"{self.DOCS_BASE}/guide/configuration#authentication",
            details=self._get_cause_details(exc) if self.verbose else None,
            commands=[
                "spectra --doctor  # Check configuration",
                "spectra --init    # Reconfigure credentials",
            ],
            quick_fix="spectra --doctor",
        )

    def _format_permission_error(self, exc: AccessDeniedError) -> FormattedError:
        """Format permission denied error."""
        message = str(exc) if str(exc) else "Access denied - insufficient permissions."
        issue_key = getattr(exc, "issue_key", None)

        suggestions = [
            "Verify you have the required permissions in the Jira project",
            "Check with your Jira administrator about your role and permissions",
            "Ensure the project hasn't been archived or restricted",
        ]

        if issue_key:
            suggestions.insert(0, f"Verify you have access to issue {issue_key}")

        return FormattedError(
            code=ErrorCode.AUTH_PERMISSION_DENIED,
            title="Permission Denied",
            message=message,
            suggestions=suggestions,
            details=f"Issue: {issue_key}" if issue_key else None,
        )

    # -------------------------------------------------------------------------
    # Resource Not Found Errors
    # -------------------------------------------------------------------------

    def _format_not_found_error(self, exc: ResourceNotFoundError) -> FormattedError:
        """Format resource not found error."""
        message = str(exc) if str(exc) else "The requested resource was not found."
        issue_key = getattr(exc, "issue_key", None)

        # Determine specific error code based on context
        code = ErrorCode.RESOURCE_NOT_FOUND
        title = "Resource Not Found"
        suggestions = []
        commands = []
        quick_fix = None

        if issue_key:
            code = ErrorCode.RESOURCE_ISSUE_NOT_FOUND
            title = "Issue Not Found"
            suggestions = [
                f"Verify issue key '{issue_key}' is correct (check for typos)",
                "Confirm the issue hasn't been deleted or moved",
                "Check that you have permission to view this issue",
                "Try searching for the issue in Jira directly",
            ]
            commands = [
                "# Search for similar issues in your tracker",
            ]
        elif "project" in message.lower():
            code = ErrorCode.RESOURCE_PROJECT_NOT_FOUND
            title = "Project Not Found"
            suggestions = [
                "Verify the project key is correct",
                "Check that the project exists and you have access",
                "Project keys are case-sensitive (e.g., 'PROJ' not 'proj')",
            ]
        elif "epic" in message.lower():
            code = ErrorCode.RESOURCE_EPIC_NOT_FOUND
            title = "Epic Not Found"
            suggestions = [
                "Verify the epic key matches an existing issue",
                "Ensure the issue is actually an Epic type",
                "Check that the epic hasn't been deleted",
            ]
            commands = [
                "spectra --doctor  # Verify connection and permissions",
            ]
            quick_fix = "spectra --doctor"
        else:
            suggestions = [
                "Verify the resource identifier is correct",
                "Check that the resource hasn't been deleted",
                "Confirm you have permission to access this resource",
            ]

        return FormattedError(
            code=code,
            title=title,
            message=message,
            suggestions=suggestions,
            details=f"Issue: {issue_key}" if issue_key else None,
            commands=commands,
            quick_fix=quick_fix,
        )

    # -------------------------------------------------------------------------
    # Connection Errors
    # -------------------------------------------------------------------------

    def _format_rate_limit_error(self, exc: RateLimitError) -> FormattedError:
        """Format rate limit error."""
        retry_after = getattr(exc, "retry_after", None)
        message = str(exc) if str(exc) else "API rate limit exceeded."

        suggestions = [
            "Wait a few minutes before retrying",
            "Reduce the number of concurrent operations",
            "Consider using --incremental to sync only changed items",
        ]

        if retry_after:
            suggestions.insert(0, f"Wait {retry_after} seconds before retrying")

        return FormattedError(
            code=ErrorCode.CONN_RATE_LIMITED,
            title="Rate Limit Exceeded",
            message=message,
            suggestions=suggestions,
            details=f"Retry after: {retry_after}s" if retry_after else None,
        )

    def _format_transient_error(self, exc: TransientError) -> FormattedError:
        """Format transient server error."""
        message = str(exc) if str(exc) else "A temporary server error occurred."

        return FormattedError(
            code=ErrorCode.CONN_TRANSIENT,
            title="Temporary Server Error",
            message=message,
            suggestions=[
                "Wait a few moments and retry the operation",
                "Check Jira status page for ongoing incidents",
                "If the error persists, try with --verbose for more details",
            ],
            details=self._get_cause_details(exc) if self.verbose else None,
        )

    def _format_connection_error(self, exc: Exception) -> FormattedError:
        """Format connection error."""
        message = str(exc) if str(exc) else "Failed to connect to the server."

        return FormattedError(
            code=ErrorCode.CONN_FAILED,
            title="Connection Failed",
            message=message,
            suggestions=[
                "Check your internet connection",
                "Verify JIRA_URL is correct and accessible",
                "Ensure there's no firewall or proxy blocking the connection",
                "Try accessing the Jira URL in your browser",
            ],
            docs_url=f"{self.DOCS_BASE}/guide/configuration#jira-url",
        )

    # -------------------------------------------------------------------------
    # Transition Errors
    # -------------------------------------------------------------------------

    def _format_transition_error(self, exc: TransitionError) -> FormattedError:
        """Format workflow transition error."""
        message = str(exc) if str(exc) else "Failed to transition issue status."
        issue_key = getattr(exc, "issue_key", None)

        suggestions = [
            "Check that the target status exists in the workflow",
            "Verify the transition is allowed from the current status",
            "Some transitions may require specific conditions or permissions",
            "Review the project's workflow configuration in Jira",
        ]

        return FormattedError(
            code=ErrorCode.TRANSITION_NOT_ALLOWED,
            title="Status Transition Failed",
            message=message,
            suggestions=suggestions,
            details=f"Issue: {issue_key}" if issue_key else None,
        )

    # -------------------------------------------------------------------------
    # Parser Errors
    # -------------------------------------------------------------------------

    def _format_parser_error(self, exc: ParserError) -> FormattedError:
        """Format parser error."""
        message = str(exc) if str(exc) else "Failed to parse input file."
        source = getattr(exc, "source", None)
        line_number = getattr(exc, "line_number", None)

        # Determine error type based on source
        code = ErrorCode.PARSER_INVALID_MARKDOWN
        title = "Parse Error"

        if source and ".yaml" in str(source).lower():
            code = ErrorCode.PARSER_INVALID_YAML
            title = "Invalid YAML"

        suggestions = [
            "Check the file syntax for errors",
            "Ensure story headings use the correct format (### 🔧 US-001: Story Title)",
            "Verify subtasks are properly indented with '- [ ] Task'",
            "Use --validate to check the file before syncing",
        ]

        if line_number:
            suggestions.insert(0, f"Check line {line_number} for syntax errors")

        details = None
        if source or line_number:
            parts = []
            if source:
                parts.append(f"File: {source}")
            if line_number:
                parts.append(f"Line: {line_number}")
            details = ", ".join(parts)

        # Build commands based on source file
        commands = []
        quick_fix = None
        if source:
            commands = [
                f"spectra --validate --input {source}  # Validate file",
                f"spectra --suggest-fix --input {source}  # Get AI fix suggestions",
            ]
            quick_fix = f"spectra --validate --input {source}"
        else:
            commands = [
                "spectra --validate --input YOUR_FILE.md  # Validate file",
            ]

        return FormattedError(
            code=code,
            title=title,
            message=message,
            suggestions=suggestions,
            docs_url=f"{self.DOCS_BASE}/guide/schema",
            details=details,
            commands=commands,
            quick_fix=quick_fix,
        )

    # -------------------------------------------------------------------------
    # Configuration Errors
    # -------------------------------------------------------------------------

    def _format_config_error(self, exc: ConfigError) -> FormattedError:
        """Format generic configuration error."""
        message = str(exc) if str(exc) else "Configuration error."
        config_path = getattr(exc, "config_path", None)

        # Detect specific missing config patterns
        code = ErrorCode.CONFIG_SYNTAX_ERROR
        title = "Configuration Error"
        suggestions = []
        commands = []
        quick_fix = None

        message_lower = message.lower()
        if "url" in message_lower:
            code = ErrorCode.CONFIG_MISSING_URL
            title = "Missing Jira URL"
            suggestions = [
                "Set JIRA_URL environment variable",
                "Add 'jira.url' to your config file (.spectra.yaml)",
                "Example: export JIRA_URL='https://your-company.atlassian.net'",
            ]
            commands = [
                "export JIRA_URL='https://your-company.atlassian.net'",
                "spectra --init  # Interactive configuration wizard",
            ]
            quick_fix = "spectra --init"
        elif "email" in message_lower:
            code = ErrorCode.CONFIG_MISSING_EMAIL
            title = "Missing Jira Email"
            suggestions = [
                "Set JIRA_EMAIL environment variable",
                "Add 'jira.email' to your config file (.spectra.yaml)",
                "Use your Atlassian account email address",
            ]
            commands = [
                "export JIRA_EMAIL='your-email@company.com'",
                "spectra --init  # Interactive configuration wizard",
            ]
            quick_fix = "spectra --init"
        elif "token" in message_lower:
            code = ErrorCode.CONFIG_MISSING_TOKEN
            title = "Missing API Token"
            suggestions = [
                "Set JIRA_API_TOKEN environment variable",
                "Add 'jira.api_token' to your config file (.spectra.yaml)",
                "Generate a token at: https://id.atlassian.com/manage-profile/security/api-tokens",
            ]
            commands = [
                "export JIRA_API_TOKEN='your-api-token'",
                "spectra --init  # Interactive configuration wizard",
            ]
            quick_fix = "spectra --init"
        else:
            suggestions = [
                "Check your configuration file syntax",
                "Verify all required settings are provided",
                "Run with --verbose for more details",
            ]
            commands = [
                "spectra --doctor  # Diagnose configuration issues",
                "spectra --init  # Reconfigure from scratch",
            ]
            quick_fix = "spectra --doctor"

        return FormattedError(
            code=code,
            title=title,
            message=message,
            suggestions=suggestions,
            docs_url=f"{self.DOCS_BASE}/guide/configuration",
            details=f"Config file: {config_path}" if config_path else None,
            commands=commands,
            quick_fix=quick_fix,
        )

    def _format_config_file_error(self, exc: ConfigFileError) -> FormattedError:
        """Format config file parsing error."""
        message = str(exc) if str(exc) else "Failed to parse config file."
        config_path = getattr(exc, "config_path", None)

        suggestions = [
            "Check the config file syntax (YAML or TOML)",
            "Ensure proper indentation (use spaces, not tabs)",
            "Validate the file with a YAML/TOML linter",
        ]

        if config_path and str(config_path).endswith(".yaml"):
            suggestions.append("Verify all strings with colons are quoted")

        return FormattedError(
            code=ErrorCode.CONFIG_INVALID_FILE,
            title="Invalid Config File",
            message=message,
            suggestions=suggestions,
            docs_url=f"{self.DOCS_BASE}/guide/configuration#config-files",
            details=f"File: {config_path}" if config_path else None,
        )

    def _format_config_validation_error(self, exc: ConfigValidationError) -> FormattedError:
        """Format config validation error."""
        message = str(exc) if str(exc) else "Configuration validation failed."

        return FormattedError(
            code=ErrorCode.CONFIG_SYNTAX_ERROR,
            title="Invalid Configuration",
            message=message,
            suggestions=[
                "Check that all required values are set",
                "Verify URLs are properly formatted",
                "Ensure environment variables are exported correctly",
            ],
            docs_url=f"{self.DOCS_BASE}/guide/configuration",
        )

    # -------------------------------------------------------------------------
    # File Errors
    # -------------------------------------------------------------------------

    def _format_file_not_found(self, exc: FileNotFoundError) -> FormattedError:
        """Format file not found error."""
        filename = getattr(exc, "filename", None) or str(exc)

        return FormattedError(
            code=ErrorCode.FILE_NOT_FOUND,
            title="File Not Found",
            message=f"Cannot find file: {filename}",
            suggestions=[
                "Check that the file path is correct",
                "Verify the file exists (check for typos)",
                "Use an absolute path if the relative path isn't working",
            ],
            details=f"Path: {filename}" if filename else None,
            commands=[
                f"ls -la {filename}  # Check if file exists",
                "spectra --generate epic  # Generate a template file",
            ],
            quick_fix="spectra --generate epic  # Create a template",
        )

    def _format_file_permission_error(self, exc: PermissionError) -> FormattedError:
        """Format file permission error."""
        filename = getattr(exc, "filename", None) or str(exc)

        return FormattedError(
            code=ErrorCode.FILE_PERMISSION_DENIED,
            title="Permission Denied",
            message=f"Cannot access file: {filename}",
            suggestions=[
                "Check file permissions (use ls -la to view)",
                "Ensure you have read access to the file",
                "Try running with appropriate permissions",
            ],
            details=f"Path: {filename}" if filename else None,
        )

    # -------------------------------------------------------------------------
    # Output Errors (Confluence, etc.)
    # -------------------------------------------------------------------------

    def _format_output_auth_error(self, exc: OutputAuthenticationError) -> FormattedError:
        """Format output system authentication error."""
        message = str(exc) if str(exc) else "Authentication failed for documentation system."

        return FormattedError(
            code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            title="Documentation Auth Failed",
            message=message,
            suggestions=[
                "Verify your Confluence/documentation credentials",
                "Check that your API token is valid and not expired",
                "Ensure the account has access to the target space",
            ],
        )

    def _format_output_permission_error(self, exc: OutputAccessDeniedError) -> FormattedError:
        """Format output system permission error."""
        message = str(exc) if str(exc) else "Permission denied for documentation operation."

        return FormattedError(
            code=ErrorCode.AUTH_PERMISSION_DENIED,
            title="Documentation Permission Denied",
            message=message,
            suggestions=[
                "Verify you have edit permissions in the space",
                "Check space permissions with your administrator",
                "Ensure the page/space isn't restricted",
            ],
        )

    def _format_output_not_found_error(self, exc: OutputNotFoundError) -> FormattedError:
        """Format output system not found error."""
        message = str(exc) if str(exc) else "Documentation page or space not found."

        return FormattedError(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            title="Page Not Found",
            message=message,
            suggestions=[
                "Verify the page/space ID is correct",
                "Check that the page hasn't been deleted",
                "Confirm you have access to view the page",
            ],
        )

    def _format_output_rate_limit_error(self, exc: OutputRateLimitError) -> FormattedError:
        """Format output system rate limit error."""
        retry_after = getattr(exc, "retry_after", None)
        message = str(exc) if str(exc) else "Documentation API rate limit exceeded."

        suggestions = ["Wait a few minutes before retrying"]
        if retry_after:
            suggestions[0] = f"Wait {retry_after} seconds before retrying"

        return FormattedError(
            code=ErrorCode.CONN_RATE_LIMITED,
            title="Rate Limit Exceeded",
            message=message,
            suggestions=suggestions,
            details=f"Retry after: {retry_after}s" if retry_after else None,
        )

    # -------------------------------------------------------------------------
    # Generic Errors
    # -------------------------------------------------------------------------

    def _format_tracker_error(self, exc: TrackerError) -> FormattedError:
        """Format generic tracker error."""
        message = str(exc) if str(exc) else "An issue tracker error occurred."
        issue_key = getattr(exc, "issue_key", None)

        return FormattedError(
            code=ErrorCode.UNKNOWN,
            title="Issue Tracker Error",
            message=message,
            suggestions=[
                "Check the error message for specific details",
                "Verify your Jira configuration is correct",
                "Try running with --verbose for more information",
            ],
            details=f"Issue: {issue_key}" if issue_key else None,
        )

    def _format_generic_spectra_error(self, exc: Md2JiraError) -> FormattedError:
        """Format generic spectra error."""
        message = str(exc) if str(exc) else "An error occurred."

        return FormattedError(
            code=ErrorCode.UNKNOWN,
            title="Error",
            message=message,
            suggestions=[
                "Check the error message for details",
                "Run with --verbose for more information",
                "Check the documentation for troubleshooting tips",
            ],
            docs_url=f"{self.DOCS_BASE}/reference/exit-codes",
            details=self._get_cause_details(exc) if self.verbose else None,
        )

    def _format_unknown_error(self, exc: Exception) -> FormattedError:
        """Format unknown/unexpected error."""
        message = str(exc) if str(exc) else "An unexpected error occurred."

        return FormattedError(
            code=ErrorCode.UNKNOWN,
            title="Unexpected Error",
            message=message,
            suggestions=[
                "This appears to be an unexpected error",
                "Run with --verbose for a full stack trace",
                "Consider reporting this issue on GitHub",
            ],
            details=f"Type: {type(exc).__name__}" if self.verbose else None,
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_cause_details(self, exc: Md2JiraError) -> str | None:
        """Get details about the exception cause."""
        cause = getattr(exc, "cause", None)
        if cause:
            return f"Caused by: {type(cause).__name__}: {cause}"
        return None


# Convenience functions
def format_error(exc: Exception, color: bool = True, verbose: bool = False) -> str:
    """
    Format an exception into a user-friendly error message.

    Args:
        exc: The exception to format.
        color: Whether to use ANSI colors.
        verbose: Whether to include technical details.

    Returns:
        Formatted error string for display.
    """
    formatter = ErrorFormatter(color=color, verbose=verbose)
    return formatter.format_string(exc)


def format_connection_error(url: str = "", color: bool = True) -> str:
    """
    Format a connection failure error with helpful suggestions.

    Args:
        url: The Jira URL that failed to connect.
        color: Whether to use ANSI colors.

    Returns:
        Formatted error string for display.
    """
    from .output import Colors, Symbols

    lines: list[str] = []

    # Title
    if color:
        title = (
            f"{Colors.RED}{Colors.BOLD}{Symbols.CROSS} Connection Failed{Colors.RESET} "
            f"{Colors.DIM}[{ErrorCode.CONN_FAILED.value}]{Colors.RESET}"
        )
    else:
        title = f"✗ Connection Failed [{ErrorCode.CONN_FAILED.value}]"
    lines.append(title)
    lines.append("")

    # Message
    msg = "Failed to connect to Jira API."
    if url:
        msg = f"Failed to connect to Jira at: {url}"

    if color:
        lines.append(f"  {Colors.RED}{msg}{Colors.RESET}")
    else:
        lines.append(f"  {msg}")

    # Suggestions
    lines.append("")
    if color:
        lines.append(f"  {Colors.CYAN}{Colors.BOLD}How to fix:{Colors.RESET}")
        lines.append(
            f"    {Colors.CYAN}1.{Colors.RESET} Verify JIRA_URL is correct (e.g., https://your-company.atlassian.net)"
        )
        lines.append(
            f"    {Colors.CYAN}2.{Colors.RESET} Check that JIRA_EMAIL and JIRA_API_TOKEN are set correctly"
        )
        lines.append(f"    {Colors.CYAN}3.{Colors.RESET} Ensure your API token hasn't expired")
        lines.append(
            f"    {Colors.CYAN}4.{Colors.RESET} Test the URL in your browser to confirm it's accessible"
        )
        lines.append(f"    {Colors.CYAN}5.{Colors.RESET} Check for firewall or proxy issues")
    else:
        lines.append("  How to fix:")
        lines.append("    1. Verify JIRA_URL is correct (e.g., https://your-company.atlassian.net)")
        lines.append("    2. Check that JIRA_EMAIL and JIRA_API_TOKEN are set correctly")
        lines.append("    3. Ensure your API token hasn't expired")
        lines.append("    4. Test the URL in your browser to confirm it's accessible")
        lines.append("    5. Check for firewall or proxy issues")

    # Generate token link
    lines.append("")
    if color:
        lines.append(
            f"  {Colors.DIM}🔑 Generate API token: {Colors.RESET}"
            f"{Colors.BLUE}https://id.atlassian.com/manage-profile/security/api-tokens{Colors.RESET}"
        )
    else:
        lines.append(
            "  🔑 Generate API token: https://id.atlassian.com/manage-profile/security/api-tokens"
        )

    return "\n".join(lines)


def format_config_errors(errors: list[str], color: bool = True) -> str:
    """
    Format a list of configuration errors into a user-friendly message.

    Args:
        errors: List of error messages.
        color: Whether to use ANSI colors.

    Returns:
        Formatted error string for display.
    """
    from .output import Colors, Symbols

    lines: list[str] = []

    # Title
    if color:
        title = (
            f"{Colors.RED}{Colors.BOLD}{Symbols.CROSS} Configuration Error{Colors.RESET} "
            f"{Colors.DIM}[{ErrorCode.CONFIG_SYNTAX_ERROR.value}]{Colors.RESET}"
        )
    else:
        title = f"✗ Configuration Error [{ErrorCode.CONFIG_SYNTAX_ERROR.value}]"
    lines.append(title)
    lines.append("")

    # List each error
    for i, error in enumerate(errors, 1):
        # Split multi-line errors (from the config provider)
        error_lines = error.split("\n")
        main_error = error_lines[0]

        if color:
            lines.append(f"  {Colors.RED}{i}. {main_error}{Colors.RESET}")
        else:
            lines.append(f"  {i}. {main_error}")

        # Add sub-lines with indentation
        for sub_line in error_lines[1:]:
            if sub_line.strip():
                if color:
                    lines.append(f"     {Colors.DIM}{sub_line}{Colors.RESET}")
                else:
                    lines.append(f"     {sub_line}")

    # General suggestions
    lines.append("")
    if color:
        lines.append(f"  {Colors.CYAN}{Colors.BOLD}Getting started:{Colors.RESET}")
        lines.append(
            f"    {Colors.CYAN}1.{Colors.RESET} Copy .env.example to .env and fill in your credentials"
        )
        lines.append(
            f"    {Colors.CYAN}2.{Colors.RESET} Or set environment variables: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN"
        )
        lines.append(f"    {Colors.CYAN}3.{Colors.RESET} Or create a config file: .spectra.yaml")
    else:
        lines.append("  Getting started:")
        lines.append("    1. Copy .env.example to .env and fill in your credentials")
        lines.append("    2. Or set environment variables: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN")
        lines.append("    3. Or create a config file: .spectra.yaml")

    lines.append("")
    if color:
        lines.append(
            f"  {Colors.DIM}📖 Documentation: {Colors.RESET}"
            f"{Colors.BLUE}https://spectra.dev/guide/configuration{Colors.RESET}"
        )
    else:
        lines.append("  📖 Documentation: https://spectra.dev/guide/configuration")

    return "\n".join(lines)
