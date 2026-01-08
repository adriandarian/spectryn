"""
Exit Codes - Standard exit codes for spectra CLI.

These exit codes follow Unix conventions and provide clear
feedback about how the program terminated.
"""

from enum import IntEnum


class ExitCode(IntEnum):
    """
    Standard exit codes for spectra CLI.

    Exit codes follow Unix conventions:
    - 0: Success
    - 1-127: Error conditions
    - 128+N: Terminated by signal N

    Usage:
        from spectryn.cli.exit_codes import ExitCode
        sys.exit(ExitCode.SUCCESS)
    """

    # Success
    SUCCESS = 0
    """Operation completed successfully."""

    # General errors (1-63)
    ERROR = 1
    """General error - unspecified failure."""

    CONFIG_ERROR = 2
    """Configuration error - missing or invalid configuration."""

    FILE_NOT_FOUND = 3
    """Input file not found."""

    CONNECTION_ERROR = 4
    """Failed to connect to Jira API."""

    AUTH_ERROR = 5
    """Authentication failed - invalid credentials."""

    VALIDATION_ERROR = 6
    """Input validation failed (e.g., invalid markdown format)."""

    PERMISSION_ERROR = 7
    """Insufficient permissions for operation."""

    API_ERROR = 8
    """Jira API returned an error."""

    SYNC_ERROR = 9
    """Synchronization error - sync operation failed."""

    # Partial success (64-79)
    PARTIAL_SUCCESS = 64
    """Operation completed with some failures (graceful degradation)."""

    # User actions (80-99)
    CANCELLED = 80
    """Operation cancelled by user (via confirmation prompt)."""

    # Signal termination (128+N)
    SIGINT = 130
    """Interrupted by SIGINT (Ctrl+C)."""

    SIGTERM = 143
    """Terminated by SIGTERM."""

    @classmethod
    def from_exception(cls, exc: Exception) -> "ExitCode":
        """
        Determine appropriate exit code from an exception.

        Args:
            exc: The exception that was raised.

        Returns:
            Appropriate ExitCode for the exception type.
        """
        from spectryn.core.ports.issue_tracker import (
            AuthenticationError,
            IssueTrackerError,
            NotFoundError,
            PermissionError,
        )

        if isinstance(exc, KeyboardInterrupt):
            return cls.SIGINT
        if isinstance(exc, AuthenticationError):
            return cls.AUTH_ERROR
        if isinstance(exc, PermissionError):
            return cls.PERMISSION_ERROR
        if isinstance(exc, NotFoundError):
            return cls.FILE_NOT_FOUND
        if isinstance(exc, IssueTrackerError):
            return cls.API_ERROR
        if isinstance(exc, FileNotFoundError):
            return cls.FILE_NOT_FOUND

        return cls.ERROR

    @property
    def description(self) -> str:
        """Get human-readable description of the exit code."""
        descriptions = {
            self.SUCCESS: "Operation completed successfully",
            self.ERROR: "General error occurred",
            self.CONFIG_ERROR: "Configuration error - check environment variables or config file",
            self.FILE_NOT_FOUND: "Input file not found",
            self.CONNECTION_ERROR: "Failed to connect to Jira",
            self.AUTH_ERROR: "Authentication failed - check JIRA_EMAIL and JIRA_API_TOKEN",
            self.VALIDATION_ERROR: "Input validation failed",
            self.PERMISSION_ERROR: "Insufficient permissions for this operation",
            self.API_ERROR: "Jira API returned an error",
            self.SYNC_ERROR: "Synchronization failed",
            self.PARTIAL_SUCCESS: "Completed with some failures",
            self.CANCELLED: "Cancelled by user",
            self.SIGINT: "Interrupted (Ctrl+C)",
            self.SIGTERM: "Terminated",
        }
        return descriptions.get(self, "Unknown exit code")


# Backwards compatibility aliases
EXIT_SUCCESS = ExitCode.SUCCESS
EXIT_ERROR = ExitCode.ERROR
EXIT_CONFIG_ERROR = ExitCode.CONFIG_ERROR
EXIT_SIGINT = ExitCode.SIGINT
