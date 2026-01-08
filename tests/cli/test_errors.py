"""
Tests for CLI error formatting.

Tests the rich error messages, suggestions, and formatting.
"""

from spectryn.cli.errors import (
    ErrorCode,
    ErrorFormatter,
    FormattedError,
    format_config_errors,
    format_connection_error,
    format_error,
)
from spectryn.cli.output import Console
from spectryn.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    ConfigError,
    ConfigFileError,
    ParserError,
    RateLimitError,
    ResourceNotFoundError,
    SpectraError,
    TrackerError,
    TransientError,
    TransitionError,
)


# =============================================================================
# FormattedError Tests
# =============================================================================


class TestFormattedError:
    """Tests for FormattedError dataclass."""

    def test_format_with_color(self):
        """Test formatting with colors enabled."""
        error = FormattedError(
            code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            title="Authentication Failed",
            message="Invalid credentials provided.",
            suggestions=["Check your API token", "Verify your email"],
        )

        result = error.format(color=True)

        # Should contain the title and error code
        assert "Authentication Failed" in result
        assert ErrorCode.AUTH_INVALID_CREDENTIALS.value in result

        # Should contain the message
        assert "Invalid credentials" in result

        # Should contain suggestions
        assert "How to fix:" in result
        assert "Check your API token" in result
        assert "Verify your email" in result

    def test_format_without_color(self):
        """Test formatting with colors disabled."""
        error = FormattedError(
            code=ErrorCode.AUTH_INVALID_CREDENTIALS,
            title="Authentication Failed",
            message="Invalid credentials provided.",
            suggestions=["Check your API token"],
        )

        result = error.format(color=False)

        # Should not contain ANSI codes
        assert "\033[" not in result

        # Should contain plain text
        assert "Authentication Failed" in result
        assert "MD2J-100" in result

    def test_format_with_docs_url(self):
        """Test formatting includes documentation URL."""
        error = FormattedError(
            code=ErrorCode.CONFIG_MISSING_URL,
            title="Missing URL",
            message="No URL configured.",
            docs_url="https://spectra.dev/guide/config",
        )

        result = error.format(color=False)

        assert "https://spectra.dev/guide/config" in result
        assert "Documentation:" in result

    def test_format_with_details(self):
        """Test formatting includes technical details."""
        error = FormattedError(
            code=ErrorCode.RESOURCE_ISSUE_NOT_FOUND,
            title="Issue Not Found",
            message="Cannot find issue.",
            details="Issue: PROJ-123",
        )

        result = error.format(color=False)

        assert "Details:" in result
        assert "PROJ-123" in result


# =============================================================================
# ErrorFormatter Tests
# =============================================================================


class TestErrorFormatter:
    """Tests for ErrorFormatter class."""

    def test_format_auth_error(self):
        """Test formatting authentication errors."""
        exc = AuthenticationError("Invalid API token")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.AUTH_INVALID_CREDENTIALS
        assert result.title == "Authentication Failed"
        assert "token" in result.message.lower() or "token" in str(result.suggestions).lower()
        assert len(result.suggestions) > 0

    def test_format_auth_error_with_401(self):
        """Test formatting 401 authentication errors has specific suggestions."""
        exc = AuthenticationError("401 Unauthorized")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        # Should have suggestion about regenerating token
        suggestions_text = " ".join(result.suggestions)
        assert "token" in suggestions_text.lower()

    def test_format_permission_error(self):
        """Test formatting access denied errors."""
        exc = AccessDeniedError("Cannot edit issue", issue_key="PROJ-123")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.AUTH_PERMISSION_DENIED
        assert result.title == "Permission Denied"
        assert "permission" in " ".join(result.suggestions).lower()

    def test_format_not_found_error_issue(self):
        """Test formatting issue not found errors."""
        exc = ResourceNotFoundError("Issue not found", issue_key="PROJ-123")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.RESOURCE_ISSUE_NOT_FOUND
        assert result.title == "Issue Not Found"
        assert "PROJ-123" in str(result.suggestions)

    def test_format_not_found_error_project(self):
        """Test formatting project not found errors."""
        exc = ResourceNotFoundError("Project UNKNOWN not found")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.RESOURCE_PROJECT_NOT_FOUND
        assert result.title == "Project Not Found"

    def test_format_not_found_error_epic(self):
        """Test formatting epic not found errors."""
        exc = ResourceNotFoundError("Epic does not exist")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.RESOURCE_EPIC_NOT_FOUND
        assert result.title == "Epic Not Found"

    def test_format_rate_limit_error(self):
        """Test formatting rate limit errors."""
        exc = RateLimitError("Too many requests", retry_after=60)
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONN_RATE_LIMITED
        assert result.title == "Rate Limit Exceeded"
        assert "60" in str(result.suggestions)

    def test_format_transient_error(self):
        """Test formatting transient server errors."""
        exc = TransientError("500 Internal Server Error")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONN_TRANSIENT
        assert result.title == "Temporary Server Error"
        assert "retry" in " ".join(result.suggestions).lower()

    def test_format_transition_error(self):
        """Test formatting workflow transition errors."""
        exc = TransitionError("Cannot transition to Done", issue_key="PROJ-123")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.TRANSITION_NOT_ALLOWED
        assert result.title == "Status Transition Failed"
        assert "workflow" in " ".join(result.suggestions).lower()

    def test_format_parser_error(self):
        """Test formatting parser errors."""
        exc = ParserError("Invalid markdown syntax", line_number=42, source="epic.md")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.PARSER_INVALID_MARKDOWN
        assert "42" in str(result.suggestions)
        assert result.details is not None
        assert "epic.md" in result.details

    def test_format_parser_error_yaml(self):
        """Test formatting YAML parser errors."""
        exc = ParserError("Invalid YAML", source="config.yaml")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.PARSER_INVALID_YAML
        assert result.title == "Invalid YAML"

    def test_format_config_error_missing_url(self):
        """Test formatting config errors for missing URL."""
        exc = ConfigError("Missing Jira URL")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONFIG_MISSING_URL
        assert "JIRA_URL" in str(result.suggestions)

    def test_format_config_error_missing_email(self):
        """Test formatting config errors for missing email."""
        exc = ConfigError("Missing Jira email")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONFIG_MISSING_EMAIL
        assert "JIRA_EMAIL" in str(result.suggestions)

    def test_format_config_error_missing_token(self):
        """Test formatting config errors for missing token."""
        exc = ConfigError("Missing API token")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONFIG_MISSING_TOKEN
        assert "JIRA_API_TOKEN" in str(result.suggestions)

    def test_format_config_file_error(self):
        """Test formatting config file parsing errors."""
        exc = ConfigFileError("config.yaml", "Invalid YAML syntax")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONFIG_INVALID_FILE
        assert result.title == "Invalid Config File"

    def test_format_file_not_found(self):
        """Test formatting file not found errors."""
        exc = FileNotFoundError("epic.md")
        exc.filename = "epic.md"
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.FILE_NOT_FOUND
        assert result.title == "File Not Found"
        assert "epic.md" in result.message

    def test_format_connection_error(self):
        """Test formatting connection errors."""
        exc = ConnectionError("Failed to connect to server")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.CONN_FAILED
        assert result.title == "Connection Failed"
        assert "internet" in " ".join(result.suggestions).lower()

    def test_format_generic_tracker_error(self):
        """Test formatting generic tracker errors."""
        exc = TrackerError("Something went wrong", issue_key="PROJ-456")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.title == "Issue Tracker Error"
        assert result.details is not None
        assert "PROJ-456" in result.details

    def test_format_unknown_error(self):
        """Test formatting unknown/unexpected errors."""
        exc = RuntimeError("Unexpected error occurred")
        formatter = ErrorFormatter(color=False)

        result = formatter.format(exc)

        assert result.code == ErrorCode.UNKNOWN
        assert result.title == "Unexpected Error"
        assert "report" in " ".join(result.suggestions).lower()

    def test_verbose_includes_details(self):
        """Test verbose mode includes technical details."""
        cause = ValueError("underlying issue")
        exc = SpectraError("High level error", cause=cause)

        formatter_normal = ErrorFormatter(color=False, verbose=False)
        formatter_verbose = ErrorFormatter(color=False, verbose=True)

        result_normal = formatter_normal.format(exc)
        result_verbose = formatter_verbose.format(exc)

        # Verbose should have more details
        assert result_normal.details is None
        assert result_verbose.details is not None
        assert "underlying issue" in result_verbose.details


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_format_error(self):
        """Test format_error convenience function."""
        exc = AuthenticationError("Invalid token")

        result = format_error(exc, color=False)

        assert "Authentication Failed" in result
        assert "MD2J-100" in result

    def test_format_config_errors_single(self):
        """Test format_config_errors with single error."""
        errors = ["Missing JIRA_URL"]

        result = format_config_errors(errors, color=False)

        assert "Configuration Error" in result
        assert "Missing JIRA_URL" in result
        assert "Getting started:" in result

    def test_format_config_errors_multiple(self):
        """Test format_config_errors with multiple errors."""
        errors = [
            "Missing JIRA_URL",
            "Missing JIRA_EMAIL",
            "Missing JIRA_API_TOKEN",
        ]

        result = format_config_errors(errors, color=False)

        assert "1. Missing JIRA_URL" in result
        assert "2. Missing JIRA_EMAIL" in result
        assert "3. Missing JIRA_API_TOKEN" in result

    def test_format_config_errors_multiline(self):
        """Test format_config_errors with multi-line error messages."""
        errors = ["Missing Jira URL.\nSet via:\n  • Environment: JIRA_URL"]

        result = format_config_errors(errors, color=False)

        assert "Missing Jira URL" in result
        assert "Environment: JIRA_URL" in result

    def test_format_connection_error_with_url(self):
        """Test format_connection_error with URL."""
        result = format_connection_error("https://example.atlassian.net", color=False)

        assert "Connection Failed" in result
        assert "https://example.atlassian.net" in result
        assert "How to fix:" in result
        assert "JIRA_URL" in result

    def test_format_connection_error_without_url(self):
        """Test format_connection_error without URL."""
        result = format_connection_error("", color=False)

        assert "Connection Failed" in result
        assert "Failed to connect to Jira API" in result


# =============================================================================
# Console Integration Tests
# =============================================================================


class TestConsoleErrorMethods:
    """Tests for Console error display methods."""

    def test_console_error_rich(self, capsys):
        """Test Console.error_rich method."""
        console = Console(color=False, json_mode=False)
        exc = AuthenticationError("Invalid token")

        console.error_rich(exc)

        captured = capsys.readouterr()
        assert "Authentication Failed" in captured.out
        assert "MD2J-100" in captured.out

    def test_console_error_rich_json_mode(self):
        """Test Console.error_rich in JSON mode."""
        console = Console(color=False, json_mode=True)
        exc = AuthenticationError("Invalid token")

        console.error_rich(exc)

        assert "Invalid token" in console._json_errors

    def test_console_config_errors(self, capsys):
        """Test Console.config_errors method."""
        console = Console(color=False, json_mode=False)

        console.config_errors(["Missing JIRA_URL", "Missing JIRA_EMAIL"])

        captured = capsys.readouterr()
        assert "Configuration Error" in captured.out
        assert "Missing JIRA_URL" in captured.out
        assert "Missing JIRA_EMAIL" in captured.out

    def test_console_config_errors_json_mode(self):
        """Test Console.config_errors in JSON mode."""
        console = Console(color=False, json_mode=True)

        console.config_errors(["Error 1", "Error 2"])

        assert "Error 1" in console._json_errors
        assert "Error 2" in console._json_errors

    def test_console_connection_error(self, capsys):
        """Test Console.connection_error method."""
        console = Console(color=False, json_mode=False)

        console.connection_error("https://example.atlassian.net")

        captured = capsys.readouterr()
        assert "Connection Failed" in captured.out
        assert "https://example.atlassian.net" in captured.out

    def test_console_connection_error_json_mode(self):
        """Test Console.connection_error in JSON mode."""
        console = Console(color=False, json_mode=True)

        console.connection_error("https://example.atlassian.net")

        assert any("Connection failed" in e for e in console._json_errors)


# =============================================================================
# Error Code Tests
# =============================================================================


class TestErrorCodes:
    """Tests for ErrorCode enum."""

    def test_error_codes_are_unique(self):
        """Test all error codes have unique values."""
        values = [code.value for code in ErrorCode]
        assert len(values) == len(set(values))

    def test_error_codes_follow_format(self):
        """Test error codes follow MD2J-XXX format."""
        for code in ErrorCode:
            assert code.value.startswith("MD2J-")
            # Ensure the numeric part is valid
            number = code.value.split("-")[1]
            assert number.isdigit()

    def test_error_code_categories(self):
        """Test error codes are in expected ranges."""
        for code in ErrorCode:
            number = int(code.value.split("-")[1])

            if "CONFIG" in code.name:
                assert 1 <= number <= 99, f"{code.name} should be in config range"
            elif "AUTH" in code.name:
                assert 100 <= number <= 199, f"{code.name} should be in auth range"
            elif "CONN" in code.name:
                assert 200 <= number <= 299, f"{code.name} should be in conn range"
            elif "RESOURCE" in code.name:
                assert 300 <= number <= 399, f"{code.name} should be in resource range"
            elif "PARSER" in code.name:
                assert 400 <= number <= 499, f"{code.name} should be in parser range"
            elif "TRANSITION" in code.name:
                assert 500 <= number <= 599, f"{code.name} should be in transition range"
            elif "FILE" in code.name:
                assert 600 <= number <= 699, f"{code.name} should be in file range"
