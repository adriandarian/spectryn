"""Tests for the spectra exception hierarchy.

This module tests the exception hierarchy defined in spectra.core.exceptions.
It verifies that:
- All exceptions have the correct inheritance
- Exceptions properly chain causes
- Attributes are correctly stored
- String representations are correct
"""

import pytest

from spectryn.core.exceptions import (
    AccessDeniedError,
    AuthenticationError,
    # Config errors
    ConfigError,
    ConfigFileError,
    ConfigValidationError,
    # Conflict errors
    ConflictError,
    # Connection errors
    ConnectionError,
    DocumentOutputError,
    DuplicateResourceError,
    EncodingError,
    EpicNotFoundError,
    GatewayError,
    InsufficientScopeError,
    InvalidCredentialsError,
    InvalidFieldError,
    InvalidFieldValueError,
    InvalidStatusError,
    IssueNotFoundError,
    # Backward compatibility aliases
    IssueTrackerError,
    MissingConfigError,
    NetworkUnreachableError,
    NotFoundError,
    OutputAccessDeniedError,
    OutputAuthenticationError,
    # Output errors
    OutputError,
    OutputNotFoundError,
    OutputRateLimitError,
    # Parser errors
    ParserError,
    ParserSyntaxError,
    PermissionError,
    ProjectNotFoundError,
    QuotaExceededError,
    RateLimitError,
    ReadOnlyAccessError,
    RequiredFieldError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    # Base
    SpectraError,
    SSLError,
    StaleDataError,
    StructureError,
    TimeoutError,
    TokenExpiredError,
    # Tracker errors
    TrackerError,
    TransientError,
    TransitionError,
    UserNotFoundError,
    # Validation errors
    ValidationError,
    WorkflowViolationError,
)


# =============================================================================
# Base Exception Tests
# =============================================================================


class TestSpectraError:
    """Tests for the base SpectraError class."""

    def test_basic_message(self):
        """Test basic error message."""
        error = SpectraError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.cause is None

    def test_with_cause(self):
        """Test error with a cause."""
        cause = ValueError("Original error")
        error = SpectraError("Wrapper error", cause=cause)
        assert "Wrapper error" in str(error)
        assert "caused by" in str(error)
        assert error.cause is cause

    def test_exception_inheritance(self):
        """Test that SpectraError inherits from Exception."""
        error = SpectraError("test")
        assert isinstance(error, Exception)


# =============================================================================
# Tracker Error Tests
# =============================================================================


class TestTrackerError:
    """Tests for TrackerError and its subclasses."""

    def test_basic_tracker_error(self):
        """Test basic TrackerError."""
        error = TrackerError("API call failed")
        assert str(error) == "API call failed"
        assert error.issue_key is None

    def test_with_issue_key(self):
        """Test TrackerError with issue key."""
        error = TrackerError("Failed to update", issue_key="PROJ-123")
        assert error.issue_key == "PROJ-123"

    def test_inheritance(self):
        """Test that TrackerError inherits from SpectraError."""
        error = TrackerError("test")
        assert isinstance(error, SpectraError)


class TestAuthenticationErrors:
    """Tests for authentication error types."""

    def test_authentication_error(self):
        """Test basic AuthenticationError."""
        error = AuthenticationError("Invalid token")
        assert isinstance(error, TrackerError)
        assert "Invalid token" in str(error)

    def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError."""
        error = InvalidCredentialsError("API key is malformed")
        assert isinstance(error, AuthenticationError)
        assert isinstance(error, TrackerError)

    def test_token_expired_error(self):
        """Test TokenExpiredError."""
        error = TokenExpiredError("OAuth token expired")
        assert isinstance(error, AuthenticationError)


class TestResourceNotFoundErrors:
    """Tests for resource not found error types."""

    def test_resource_not_found_error(self):
        """Test basic ResourceNotFoundError."""
        error = ResourceNotFoundError("Resource missing", issue_key="PROJ-123")
        assert isinstance(error, TrackerError)
        assert error.issue_key == "PROJ-123"

    def test_issue_not_found_error(self):
        """Test IssueNotFoundError."""
        error = IssueNotFoundError("Issue does not exist", issue_key="PROJ-456")
        assert isinstance(error, ResourceNotFoundError)
        assert error.issue_key == "PROJ-456"

    def test_project_not_found_error(self):
        """Test ProjectNotFoundError with project_key."""
        error = ProjectNotFoundError(
            "Project not found", project_key="MYPROJ", issue_key="MYPROJ-1"
        )
        assert isinstance(error, ResourceNotFoundError)
        assert error.project_key == "MYPROJ"
        assert error.issue_key == "MYPROJ-1"

    def test_epic_not_found_error(self):
        """Test EpicNotFoundError with epic_key."""
        error = EpicNotFoundError("Epic not found", epic_key="EPIC-100")
        assert isinstance(error, ResourceNotFoundError)
        assert error.epic_key == "EPIC-100"

    def test_user_not_found_error(self):
        """Test UserNotFoundError with username."""
        error = UserNotFoundError("User not found", username="john.doe")
        assert isinstance(error, ResourceNotFoundError)
        assert error.username == "john.doe"


class TestAccessDeniedErrors:
    """Tests for access denied error types."""

    def test_access_denied_error(self):
        """Test basic AccessDeniedError."""
        error = AccessDeniedError("Permission denied")
        assert isinstance(error, TrackerError)

    def test_read_only_access_error(self):
        """Test ReadOnlyAccessError."""
        error = ReadOnlyAccessError("Cannot modify read-only resource")
        assert isinstance(error, AccessDeniedError)

    def test_insufficient_scope_error(self):
        """Test InsufficientScopeError with required_scope."""
        error = InsufficientScopeError("Token lacks required scope", required_scope="write:issues")
        assert isinstance(error, AccessDeniedError)
        assert error.required_scope == "write:issues"


class TestTransitionErrors:
    """Tests for transition error types."""

    def test_transition_error(self):
        """Test basic TransitionError."""
        error = TransitionError("Cannot transition", issue_key="PROJ-123")
        assert isinstance(error, TrackerError)
        assert error.issue_key == "PROJ-123"

    def test_invalid_status_error(self):
        """Test InvalidStatusError with status details."""
        error = InvalidStatusError(
            "Invalid status",
            status="InvalidStatus",
            valid_statuses=["To Do", "In Progress", "Done"],
            issue_key="PROJ-123",
        )
        assert isinstance(error, TransitionError)
        assert error.status == "InvalidStatus"
        assert error.valid_statuses == ["To Do", "In Progress", "Done"]

    def test_workflow_violation_error(self):
        """Test WorkflowViolationError with transition details."""
        error = WorkflowViolationError(
            "Workflow violation",
            from_status="To Do",
            to_status="Done",
            reason="Must go through In Progress first",
            issue_key="PROJ-123",
        )
        assert isinstance(error, TransitionError)
        assert error.from_status == "To Do"
        assert error.to_status == "Done"
        assert error.reason == "Must go through In Progress first"


class TestRateLimitErrors:
    """Tests for rate limit error types."""

    def test_rate_limit_error(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert isinstance(error, TrackerError)
        assert error.retry_after == 60

    def test_quota_exceeded_error(self):
        """Test QuotaExceededError with quota details."""
        error = QuotaExceededError(
            "Monthly quota exceeded",
            quota_type="monthly",
            reset_time="2024-02-01T00:00:00Z",
            retry_after=86400,
        )
        assert isinstance(error, RateLimitError)
        assert error.quota_type == "monthly"
        assert error.reset_time == "2024-02-01T00:00:00Z"
        assert error.retry_after == 86400


class TestTransientErrors:
    """Tests for transient error types."""

    def test_transient_error(self):
        """Test basic TransientError."""
        error = TransientError("Server error")
        assert isinstance(error, TrackerError)

    def test_service_unavailable_error(self):
        """Test ServiceUnavailableError."""
        error = ServiceUnavailableError("Service under maintenance")
        assert isinstance(error, TransientError)

    def test_gateway_error(self):
        """Test GatewayError with gateway details."""
        error = GatewayError("Bad gateway", gateway="nginx")
        assert isinstance(error, TransientError)
        assert error.gateway == "nginx"


# =============================================================================
# Connection Error Tests
# =============================================================================


class TestConnectionErrors:
    """Tests for connection error types."""

    def test_connection_error(self):
        """Test basic ConnectionError."""
        error = ConnectionError("Connection failed")
        assert isinstance(error, TrackerError)

    def test_timeout_error(self):
        """Test TimeoutError with timeout details."""
        error = TimeoutError("Request timed out", timeout_seconds=30.0, operation="create_issue")
        assert isinstance(error, ConnectionError)
        assert error.timeout_seconds == 30.0
        assert error.operation == "create_issue"

    def test_network_unreachable_error(self):
        """Test NetworkUnreachableError with host."""
        error = NetworkUnreachableError("Cannot reach host", host="api.example.com")
        assert isinstance(error, ConnectionError)
        assert error.host == "api.example.com"

    def test_ssl_error(self):
        """Test SSLError with certificate error."""
        error = SSLError("SSL verification failed", cert_error="Certificate expired")
        assert isinstance(error, ConnectionError)
        assert error.cert_error == "Certificate expired"


# =============================================================================
# Validation Error Tests
# =============================================================================


class TestValidationErrors:
    """Tests for validation error types."""

    def test_validation_error(self):
        """Test basic ValidationError."""
        error = ValidationError("Validation failed")
        assert isinstance(error, TrackerError)

    def test_invalid_field_error(self):
        """Test InvalidFieldError with field details."""
        error = InvalidFieldError(
            "Invalid field value",
            field_name="priority",
            field_value="SuperHigh",
            expected="One of: Low, Medium, High, Critical",
        )
        assert isinstance(error, ValidationError)
        assert error.field_name == "priority"
        assert error.field_value == "SuperHigh"
        assert error.expected == "One of: Low, Medium, High, Critical"

    def test_required_field_error(self):
        """Test RequiredFieldError with field name."""
        error = RequiredFieldError("Required field missing", field_name="summary")
        assert isinstance(error, ValidationError)
        assert error.field_name == "summary"


# =============================================================================
# Conflict Error Tests
# =============================================================================


class TestConflictErrors:
    """Tests for conflict error types."""

    def test_conflict_error(self):
        """Test basic ConflictError."""
        error = ConflictError("Conflict detected")
        assert isinstance(error, TrackerError)

    def test_stale_data_error(self):
        """Test StaleDataError with version details."""
        error = StaleDataError(
            "Data was modified",
            current_version="v5",
            expected_version="v3",
            issue_key="PROJ-123",
        )
        assert isinstance(error, ConflictError)
        assert error.current_version == "v5"
        assert error.expected_version == "v3"

    def test_duplicate_resource_error(self):
        """Test DuplicateResourceError with existing ID."""
        error = DuplicateResourceError("Resource already exists", existing_id="existing-123")
        assert isinstance(error, ConflictError)
        assert error.existing_id == "existing-123"


# =============================================================================
# Parser Error Tests
# =============================================================================


class TestParserErrors:
    """Tests for parser error types."""

    def test_parser_error_basic(self):
        """Test basic ParserError."""
        error = ParserError("Parse failed")
        assert isinstance(error, SpectraError)
        assert str(error) == "Parse failed"

    def test_parser_error_with_location(self):
        """Test ParserError with source and line number."""
        error = ParserError("Invalid markdown", line_number=42, source="stories.md")
        assert "stories.md" in str(error)
        assert "line 42" in str(error)
        assert error.line_number == 42
        assert error.source == "stories.md"

    def test_parser_syntax_error(self):
        """Test ParserSyntaxError with expected/actual."""
        error = ParserSyntaxError(
            "Syntax error",
            expected="heading",
            actual="paragraph",
            line_number=10,
            source="test.md",
        )
        assert isinstance(error, ParserError)
        assert error.expected == "heading"
        assert error.actual == "paragraph"

    def test_structure_error(self):
        """Test StructureError with section details."""
        error = StructureError(
            "Invalid structure",
            section="epic",
            expected_structure="Epic must contain stories",
        )
        assert isinstance(error, ParserError)
        assert error.section == "epic"
        assert error.expected_structure == "Epic must contain stories"

    def test_encoding_error(self):
        """Test EncodingError with encoding details."""
        error = EncodingError(
            "Cannot decode file",
            detected_encoding="latin-1",
            expected_encoding="utf-8",
            source="data.txt",
        )
        assert isinstance(error, ParserError)
        assert error.detected_encoding == "latin-1"
        assert error.expected_encoding == "utf-8"

    def test_invalid_field_value_error(self):
        """Test InvalidFieldValueError with value details."""
        error = InvalidFieldValueError(
            "Invalid priority",
            field_name="Priority",
            field_value="SUPER_HIGH",
            valid_values=["Low", "Medium", "High"],
            line_number=25,
        )
        assert isinstance(error, ParserError)
        assert error.field_name == "Priority"
        assert error.field_value == "SUPER_HIGH"
        assert error.valid_values == ["Low", "Medium", "High"]


# =============================================================================
# Output Error Tests
# =============================================================================


class TestOutputErrors:
    """Tests for output error types."""

    def test_output_error(self):
        """Test basic OutputError."""
        error = OutputError("Output failed", page_id="12345")
        assert isinstance(error, SpectraError)
        assert error.page_id == "12345"

    def test_output_authentication_error(self):
        """Test OutputAuthenticationError."""
        error = OutputAuthenticationError("Auth failed")
        assert isinstance(error, OutputError)

    def test_output_not_found_error(self):
        """Test OutputNotFoundError."""
        error = OutputNotFoundError("Page not found", page_id="99999")
        assert isinstance(error, OutputError)
        assert error.page_id == "99999"

    def test_output_access_denied_error(self):
        """Test OutputAccessDeniedError."""
        error = OutputAccessDeniedError("No write access")
        assert isinstance(error, OutputError)

    def test_output_rate_limit_error(self):
        """Test OutputRateLimitError with retry_after."""
        error = OutputRateLimitError("Rate limited", retry_after=120, page_id="12345")
        assert isinstance(error, OutputError)
        assert error.retry_after == 120


# =============================================================================
# Config Error Tests
# =============================================================================


class TestConfigErrors:
    """Tests for config error types."""

    def test_config_error_basic(self):
        """Test basic ConfigError."""
        error = ConfigError("Config invalid")
        assert isinstance(error, SpectraError)
        assert str(error) == "Config invalid"

    def test_config_error_with_path(self):
        """Test ConfigError with config_path."""
        error = ConfigError("Invalid syntax", config_path=".spectra.yaml")
        assert ".spectra.yaml" in str(error)
        assert error.config_path == ".spectra.yaml"

    def test_config_file_error(self):
        """Test ConfigFileError."""
        error = ConfigFileError("YAML parse error", config_path="config.yaml")
        assert isinstance(error, ConfigError)
        assert error.config_path == "config.yaml"

    def test_config_validation_error(self):
        """Test ConfigValidationError with field details."""
        error = ConfigValidationError(
            "Invalid value",
            field_name="tracker_type",
            field_value="invalid",
            config_path=".spectra.yaml",
        )
        assert isinstance(error, ConfigError)
        assert error.field_name == "tracker_type"
        assert error.field_value == "invalid"

    def test_missing_config_error(self):
        """Test MissingConfigError with missing key and env var."""
        error = MissingConfigError(
            "API token required",
            missing_key="jira.api_token",
            env_var="JIRA_API_TOKEN",
        )
        assert isinstance(error, ConfigError)
        assert error.missing_key == "jira.api_token"
        assert error.env_var == "JIRA_API_TOKEN"


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""

    def test_issue_tracker_error_alias(self):
        """Test that IssueTrackerError is an alias for TrackerError."""
        assert IssueTrackerError is TrackerError

    def test_not_found_error_alias(self):
        """Test that NotFoundError is an alias for ResourceNotFoundError."""
        assert NotFoundError is ResourceNotFoundError

    def test_permission_error_alias(self):
        """Test that PermissionError is an alias for AccessDeniedError."""
        assert PermissionError is AccessDeniedError

    def test_document_output_error_alias(self):
        """Test that DocumentOutputError is an alias for OutputError."""
        assert DocumentOutputError is OutputError


# =============================================================================
# Exception Chaining Tests
# =============================================================================


class TestExceptionChaining:
    """Tests for exception chaining behavior."""

    def test_tracker_error_with_cause(self):
        """Test TrackerError with chained cause."""
        original = ValueError("original error")
        error = TrackerError("wrapper", cause=original)
        assert error.cause is original
        assert "caused by" in str(error)

    def test_nested_exception_chain(self):
        """Test multiple levels of exception chaining."""
        level1 = ValueError("level 1")
        level2 = TrackerError("level 2", cause=level1)
        level3 = AuthenticationError("level 3", cause=level2)

        assert level3.cause is level2
        assert level2.cause is level1

    def test_exception_chain_str(self):
        """Test string representation of chained exceptions."""
        cause = RuntimeError("connection refused")
        error = ConnectionError("Failed to connect", cause=cause)
        error_str = str(error)
        assert "Failed to connect" in error_str
        assert "caused by" in error_str


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestExceptionHierarchy:
    """Tests verifying the exception class hierarchy."""

    def test_all_tracker_errors_are_spectra_errors(self):
        """Test that all tracker errors inherit from SpectraError."""
        tracker_errors = [
            TrackerError("test"),
            AuthenticationError("test"),
            InvalidCredentialsError("test"),
            TokenExpiredError("test"),
            ResourceNotFoundError("test"),
            IssueNotFoundError("test"),
            ProjectNotFoundError("test"),
            EpicNotFoundError("test"),
            UserNotFoundError("test"),
            AccessDeniedError("test"),
            ReadOnlyAccessError("test"),
            InsufficientScopeError("test"),
            TransitionError("test"),
            InvalidStatusError("test"),
            WorkflowViolationError("test"),
            RateLimitError("test"),
            QuotaExceededError("test"),
            TransientError("test"),
            ServiceUnavailableError("test"),
            GatewayError("test"),
            ConnectionError("test"),
            TimeoutError("test"),
            NetworkUnreachableError("test"),
            SSLError("test"),
            ValidationError("test"),
            InvalidFieldError("test"),
            RequiredFieldError("test"),
            ConflictError("test"),
            StaleDataError("test"),
            DuplicateResourceError("test"),
        ]

        for error in tracker_errors:
            assert isinstance(error, SpectraError), (
                f"{type(error).__name__} should inherit from SpectraError"
            )
            assert isinstance(error, TrackerError), (
                f"{type(error).__name__} should inherit from TrackerError"
            )

    def test_all_parser_errors_are_spectra_errors(self):
        """Test that all parser errors inherit from SpectraError."""
        parser_errors = [
            ParserError("test"),
            ParserSyntaxError("test"),
            StructureError("test"),
            EncodingError("test"),
            InvalidFieldValueError("test"),
        ]

        for error in parser_errors:
            assert isinstance(error, SpectraError), (
                f"{type(error).__name__} should inherit from SpectraError"
            )
            assert isinstance(error, ParserError), (
                f"{type(error).__name__} should inherit from ParserError"
            )

    def test_all_config_errors_are_spectra_errors(self):
        """Test that all config errors inherit from SpectraError."""
        config_errors = [
            ConfigError("test"),
            ConfigFileError("test"),
            ConfigValidationError("test"),
            MissingConfigError("test"),
        ]

        for error in config_errors:
            assert isinstance(error, SpectraError), (
                f"{type(error).__name__} should inherit from SpectraError"
            )
            assert isinstance(error, ConfigError), (
                f"{type(error).__name__} should inherit from ConfigError"
            )

    def test_all_output_errors_are_spectra_errors(self):
        """Test that all output errors inherit from SpectraError."""
        output_errors = [
            OutputError("test"),
            OutputAuthenticationError("test"),
            OutputNotFoundError("test"),
            OutputAccessDeniedError("test"),
            OutputRateLimitError("test"),
        ]

        for error in output_errors:
            assert isinstance(error, SpectraError), (
                f"{type(error).__name__} should inherit from SpectraError"
            )
            assert isinstance(error, OutputError), (
                f"{type(error).__name__} should inherit from OutputError"
            )
