"""
Tests for structured logging functionality.
"""

import json
import logging
import sys
from io import StringIO
from unittest.mock import patch

from spectryn.cli.logging import (
    ContextLogger,
    JSONFormatter,
    TextFormatter,
    get_logger,
    setup_logging,
)


# =============================================================================
# JSONFormatter Tests
# =============================================================================


class TestJSONFormatter:
    """Tests for the JSON log formatter."""

    def test_basic_format(self):
        """Test basic JSON log output format."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "TestLogger"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_json_format_with_args(self):
        """Test JSON format with message formatting args."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Processing %s items",
            args=(5,),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["message"] == "Processing 5 items"

    def test_json_format_with_exception(self):
        """Test JSON format includes exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            record = logging.LogRecord(
                name="TestLogger",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="An error occurred",
                args=(),
                exc_info=sys.exc_info(),
            )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert parsed["exception"]["type"] == "ValueError"
        assert parsed["exception"]["message"] == "Test error"
        assert "traceback" in parsed["exception"]

    def test_json_format_with_extra_fields(self):
        """Test JSON format includes extra context fields."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "abc123"
        record.user_id = 42

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "context" in parsed
        assert parsed["context"]["request_id"] == "abc123"
        assert parsed["context"]["user_id"] == 42

    def test_json_format_with_static_fields(self):
        """Test JSON format includes static fields."""
        formatter = JSONFormatter(static_fields={"service": "spectra", "version": "2.0.0"})
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["service"] == "spectra"
        assert parsed["version"] == "2.0.0"

    def test_json_format_with_location(self):
        """Test JSON format includes location info when enabled."""
        formatter = JSONFormatter(include_location=True)
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        record.filename = "test.py"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "location" in parsed
        assert parsed["location"]["line"] == 42
        assert parsed["location"]["function"] == "test_function"

    def test_json_format_without_optional_fields(self):
        """Test JSON format respects field exclusions."""
        formatter = JSONFormatter(
            include_timestamp=False,
            include_level=False,
            include_logger=False,
        )
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "timestamp" not in parsed
        assert "level" not in parsed
        assert "logger" not in parsed
        assert parsed["message"] == "Test message"

    def test_timestamp_format_is_iso8601(self):
        """Test that timestamp is in ISO8601 format with UTC."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        # Check ISO8601 format with Z suffix (UTC)
        timestamp = parsed["timestamp"]
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        # Should match pattern like 2024-01-15T10:30:00.123Z
        assert len(timestamp) == 24


# =============================================================================
# TextFormatter Tests
# =============================================================================


class TestTextFormatter:
    """Tests for the text log formatter."""

    def test_basic_format(self):
        """Test basic text log output."""
        formatter = TextFormatter(use_colors=False)
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "TestLogger" in output
        assert "INFO" in output
        assert "Test message" in output

    def test_format_with_context(self):
        """Test text format includes context when enabled."""
        formatter = TextFormatter(use_colors=False, include_context=True)
        record = logging.LogRecord(
            name="TestLogger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.request_id = "abc123"

        output = formatter.format(record)

        assert "request_id=" in output
        assert "abc123" in output


# =============================================================================
# ContextLogger Tests
# =============================================================================


class TestContextLogger:
    """Tests for the context logger wrapper."""

    def test_context_logger_adds_context(self):
        """Test that ContextLogger adds context to log records."""
        with patch("logging.Logger.log") as mock_log:
            logger = ContextLogger("TestLogger", {"request_id": "abc123"})
            logger.info("Test message")

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert "extra" in call_kwargs
            assert call_kwargs["extra"]["request_id"] == "abc123"

    def test_context_logger_bind_creates_new_logger(self):
        """Test that bind() creates a new logger with merged context."""
        original = ContextLogger("TestLogger", {"request_id": "abc123"})
        bound = original.bind(user_id=42)

        # Original should not have user_id
        assert "user_id" not in original._context

        # Bound should have both
        assert bound._context["request_id"] == "abc123"
        assert bound._context["user_id"] == 42

    def test_context_logger_all_levels(self):
        """Test that all log levels work correctly."""
        with patch("logging.Logger.log") as mock_log:
            logger = ContextLogger("TestLogger", {})

            logger.debug("debug message")
            logger.info("info message")
            logger.warning("warning message")
            logger.error("error message")
            logger.critical("critical message")

            assert mock_log.call_count == 5

            # Check levels were called correctly
            levels = [call[0][0] for call in mock_log.call_args_list]
            assert logging.DEBUG in levels
            assert logging.INFO in levels
            assert logging.WARNING in levels
            assert logging.ERROR in levels
            assert logging.CRITICAL in levels


# =============================================================================
# setup_logging Tests
# =============================================================================


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def teardown_method(self):
        """Reset logging configuration after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    def test_setup_text_logging(self):
        """Test setting up text logging."""
        setup_logging(level=logging.INFO, log_format="text")

        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, TextFormatter)

    def test_setup_json_logging(self):
        """Test setting up JSON logging."""
        setup_logging(level=logging.DEBUG, log_format="json")

        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_setup_logging_with_static_fields(self):
        """Test that static fields are passed to JSON formatter."""
        setup_logging(log_format="json", static_fields={"service": "test"})

        root = logging.getLogger()
        formatter = root.handlers[0].formatter
        assert isinstance(formatter, JSONFormatter)
        assert formatter.static_fields["service"] == "test"

    def test_setup_logging_suppresses_noisy_loggers(self):
        """Test that noisy loggers are suppressed."""
        setup_logging(log_format="text")

        urllib3_logger = logging.getLogger("urllib3")
        assert urllib3_logger.level == logging.WARNING

    def test_setup_logging_replaces_existing_handlers(self):
        """Test that setup_logging removes existing handlers."""
        root = logging.getLogger()

        # Store initial handler count (pytest adds its own handlers)
        initial_handlers = len(root.handlers)

        # Add two more handlers
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        assert len(root.handlers) == initial_handlers + 2

        setup_logging(log_format="text")

        # Should have exactly 1 handler after setup
        assert len(root.handlers) == 1

    def test_setup_logging_with_log_file(self, tmp_path):
        """Test setting up logging with file output."""
        log_file = tmp_path / "test.log"

        setup_logging(
            level=logging.INFO,
            log_format="text",
            log_file=str(log_file),
        )

        root = logging.getLogger()
        # Should have 2 handlers: console + file
        assert len(root.handlers) == 2

        # Check one is a FileHandler
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_file)

    def test_log_file_receives_logs(self, tmp_path):
        """Test that logs are actually written to the file."""
        log_file = tmp_path / "test.log"

        setup_logging(
            level=logging.INFO,
            log_format="text",
            log_file=str(log_file),
        )

        logger = logging.getLogger("TestFileLogger")
        logger.info("Test message to file")

        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = log_file.read_text()
        assert "Test message to file" in content
        assert "TestFileLogger" in content

    def test_log_file_with_json_format(self, tmp_path):
        """Test JSON format in log file."""
        log_file = tmp_path / "test.json.log"

        setup_logging(
            level=logging.INFO,
            log_format="json",
            log_file=str(log_file),
        )

        logger = logging.getLogger("JSONFileLogger")
        logger.info("JSON test message")

        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = log_file.read_text().strip()
        parsed = json.loads(content)

        assert parsed["message"] == "JSON test message"
        assert parsed["logger"] == "JSONFileLogger"
        assert parsed["level"] == "INFO"

    def test_log_file_no_colors(self, tmp_path):
        """Test that file logs don't contain ANSI color codes."""
        log_file = tmp_path / "test.log"

        setup_logging(
            level=logging.INFO,
            log_format="text",
            log_file=str(log_file),
        )

        logger = logging.getLogger("NoColorLogger")
        logger.warning("Warning message")

        # Flush handlers
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = log_file.read_text()
        # Should not contain ANSI escape sequences
        assert "\033[" not in content
        assert "Warning message" in content


# =============================================================================
# get_logger Tests
# =============================================================================


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_context_logger(self):
        """Test that get_logger returns a ContextLogger."""
        logger = get_logger("TestLogger")
        assert isinstance(logger, ContextLogger)

    def test_get_logger_with_context(self):
        """Test that get_logger accepts context kwargs."""
        logger = get_logger("TestLogger", request_id="abc123", user_id=42)

        assert logger._context["request_id"] == "abc123"
        assert logger._context["user_id"] == 42


# =============================================================================
# Integration Tests
# =============================================================================


class TestLoggingIntegration:
    """Integration tests for the logging system."""

    def teardown_method(self):
        """Reset logging configuration after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    def test_json_logging_end_to_end(self, capsys):
        """Test complete JSON logging flow."""
        # Capture stderr
        stderr_capture = StringIO()
        handler = logging.StreamHandler(stderr_capture)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("IntegrationTest")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test message", extra={"key": "value"})

        output = stderr_capture.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "IntegrationTest"
        assert parsed["message"] == "Test message"
        assert parsed["context"]["key"] == "value"

    def test_context_logger_with_json_formatter(self):
        """Test ContextLogger with JSON formatter."""
        stderr_capture = StringIO()
        handler = logging.StreamHandler(stderr_capture)
        handler.setFormatter(JSONFormatter())

        base_logger = logging.getLogger("ContextTest")
        base_logger.handlers = []
        base_logger.addHandler(handler)
        base_logger.setLevel(logging.INFO)

        ctx_logger = ContextLogger("ContextTest", {"session_id": "sess123"})
        ctx_logger.info("Processing request", extra={"action": "sync"})

        output = stderr_capture.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["context"]["session_id"] == "sess123"
        assert parsed["context"]["action"] == "sync"
