"""
Tests for RedactingFilter in logging module.

Tests cover:
- Log message redaction
- Log argument redaction
- Exception redaction
- Integration with logging handlers
"""

import logging

import pytest

from spectra.cli.logging import RedactingFilter, setup_secure_logging
from spectra.core.security.redactor import SecretRedactor


class TestRedactingFilter:
    """Tests for RedactingFilter class."""

    def test_init_default(self) -> None:
        """Should initialize with global redactor."""
        filter_ = RedactingFilter()
        assert filter_.redactor is not None

    def test_init_custom_redactor(self) -> None:
        """Should use custom redactor."""
        redactor = SecretRedactor()
        filter_ = RedactingFilter(redactor)
        assert filter_._redactor is redactor

    def test_register_secret(self) -> None:
        """Should register secrets through filter."""
        filter_ = RedactingFilter(SecretRedactor())
        filter_.register_secret("my-secret-token")
        assert filter_.redactor.registered_count == 1

    def test_register_multiple_secrets(self) -> None:
        """Should register multiple secrets."""
        filter_ = RedactingFilter(SecretRedactor())
        filter_.register_secrets("secret1-token", "secret2-password")
        assert filter_.redactor.registered_count == 2


class TestFilterLogRecords:
    """Tests for filtering log records."""

    @pytest.fixture
    def filter_with_secret(self) -> RedactingFilter:
        """Create filter with a registered secret."""
        redactor = SecretRedactor()
        redactor.register_secret("secret-value-123")
        return RedactingFilter(redactor)

    def test_filter_redacts_message(self, filter_with_secret: RedactingFilter) -> None:
        """Should redact secrets in log message."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Using secret-value-123 for auth",
            args=(),
            exc_info=None,
        )

        result = filter_with_secret.filter(record)

        assert result is True  # Always passes
        assert "secret-value-123" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_filter_always_returns_true(self, filter_with_secret: RedactingFilter) -> None:
        """Should always return True (never drops logs)."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        assert filter_with_secret.filter(record) is True

    def test_filter_redacts_string_args(self, filter_with_secret: RedactingFilter) -> None:
        """Should redact secrets in string arguments."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Token: %s",
            args=("secret-value-123",),
            exc_info=None,
        )

        filter_with_secret.filter(record)

        assert "secret-value-123" not in str(record.args)

    def test_filter_redacts_dict_args(self, filter_with_secret: RedactingFilter) -> None:
        """Should redact secrets in dict arguments."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Config: %s",
            args=({"api_token": "secret-value-123"},),
            exc_info=None,
        )

        filter_with_secret.filter(record)

        # Sensitive key should be redacted
        redacted_args = record.args
        # Args may be a dict directly after redaction
        if isinstance(redacted_args, tuple):
            assert redacted_args[0]["api_token"] == "[REDACTED]"
        else:
            assert redacted_args["api_token"] == "[REDACTED]"

    def test_filter_handles_sensitive_keys(self) -> None:
        """Should redact sensitive keys even without registered secrets."""
        filter_ = RedactingFilter(SecretRedactor())
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting",
            args=({"password": "hunter2"},),
            exc_info=None,
        )

        filter_.filter(record)

        redacted_args = record.args
        # Args may be a dict directly after redaction
        if isinstance(redacted_args, tuple):
            assert redacted_args[0]["password"] == "[REDACTED]"
        else:
            assert redacted_args["password"] == "[REDACTED]"


class TestSetupSecureLogging:
    """Tests for setup_secure_logging function."""

    def test_returns_redacting_filter(self) -> None:
        """Should return RedactingFilter instance."""
        filter_ = setup_secure_logging(level=logging.WARNING)
        assert isinstance(filter_, RedactingFilter)

    def test_registers_provided_secrets(self) -> None:
        """Should register provided secrets."""
        filter_ = setup_secure_logging(
            level=logging.WARNING,
            secrets=["secret1-abcd", "secret2-efgh"],
        )
        assert filter_.redactor.registered_count == 2

    def test_filter_added_to_handlers(self) -> None:
        """Should add filter to root logger handlers."""
        setup_secure_logging(level=logging.WARNING)

        root = logging.getLogger()
        # Check that at least one handler has the filter
        has_redacting_filter = False
        for handler in root.handlers:
            for f in handler.filters:
                if isinstance(f, RedactingFilter):
                    has_redacting_filter = True
                    break

        assert has_redacting_filter


class TestLoggingIntegration:
    """Integration tests with actual logging."""

    def test_logging_redacts_registered_secret(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should redact secrets when actually logging."""
        # Create fresh logger to avoid interference
        logger = logging.getLogger("test_redaction")
        logger.handlers = []
        logger.setLevel(logging.DEBUG)

        # Add handler with filter
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)

        redactor = SecretRedactor()
        redactor.register_secret("integration-test-secret")
        filter_ = RedactingFilter(redactor)
        handler.addFilter(filter_)
        logger.addHandler(handler)

        # Log with secret
        with caplog.at_level(logging.DEBUG, logger="test_redaction"):
            logger.info("Using token: integration-test-secret")

        # The logged message should be redacted
        # Note: caplog captures the original message before filtering,
        # but the filter modifies the record in place
        # We need to check the record.msg directly
        for record in caplog.records:
            if record.name == "test_redaction":
                assert "integration-test-secret" not in record.msg

    def test_logging_preserves_safe_messages(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should not modify safe messages."""
        logger = logging.getLogger("test_safe")
        logger.handlers = []
        logger.setLevel(logging.DEBUG)

        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        filter_ = RedactingFilter(SecretRedactor())
        handler.addFilter(filter_)
        logger.addHandler(handler)

        with caplog.at_level(logging.DEBUG, logger="test_safe"):
            logger.info("Normal message without secrets")

        for record in caplog.records:
            if record.name == "test_safe":
                assert record.msg == "Normal message without secrets"
