"""
Structured Logging - JSON and text logging formatters for spectra.

Provides flexible logging configuration with support for:
- Text format: Human-readable output for terminal usage
- JSON format: Structured output for log aggregation (ELK, Splunk, CloudWatch, etc.)
"""

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs log records as JSON objects with consistent fields for easy
    parsing by log aggregation systems.

    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.000Z",
        "level": "INFO",
        "logger": "JiraAdapter",
        "message": "Created issue PROJ-123",
        "context": { ... }  // Optional extra fields
    }
    """

    # Fields to exclude from the extra context (they're handled separately)
    RESERVED_ATTRS = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    def __init__(
        self,
        *,
        include_timestamp: bool = True,
        include_level: bool = True,
        include_logger: bool = True,
        include_location: bool = False,
        include_process: bool = False,
        include_thread: bool = False,
        static_fields: dict[str, Any] | None = None,
    ):
        """
        Initialize the JSON formatter.

        Args:
            include_timestamp: Include ISO8601 timestamp (default: True)
            include_level: Include log level (default: True)
            include_logger: Include logger name (default: True)
            include_location: Include file/line/function info (default: False)
            include_process: Include process ID (default: False)
            include_thread: Include thread name (default: False)
            static_fields: Static fields to add to every log record
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_logger = include_logger
        self.include_location = include_location
        self.include_process = include_process
        self.include_thread = include_thread
        self.static_fields = static_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_obj: dict[str, Any] = {}

        # Add timestamp first for consistent field ordering
        if self.include_timestamp:
            log_obj["timestamp"] = self._format_timestamp(record)

        # Add core fields
        if self.include_level:
            log_obj["level"] = record.levelname

        if self.include_logger:
            log_obj["logger"] = record.name

        # Add the message
        log_obj["message"] = record.getMessage()

        # Add location info if enabled
        if self.include_location:
            log_obj["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add process/thread info if enabled
        if self.include_process:
            log_obj["process"] = {
                "id": record.process,
                "name": record.processName,
            }

        if self.include_thread:
            log_obj["thread"] = {
                "id": record.thread,
                "name": record.threadName,
            }

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self._format_exception(record)

        # Add static fields
        if self.static_fields:
            log_obj.update(self.static_fields)

        # Add extra fields from the record
        extra = self._extract_extra(record)
        if extra:
            log_obj["context"] = extra

        return json.dumps(log_obj, default=str, ensure_ascii=False)

    def _format_timestamp(self, record: logging.LogRecord) -> str:
        """Format timestamp as ISO8601 with milliseconds in UTC."""
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"

    def _format_exception(self, record: logging.LogRecord) -> dict[str, Any]:
        """Format exception info as a structured object."""
        exc_type, exc_value, exc_tb = record.exc_info  # type: ignore

        result: dict[str, Any] = {}

        if exc_type:
            result["type"] = exc_type.__name__

        if exc_value:
            result["message"] = str(exc_value)

        if exc_tb:
            result["traceback"] = traceback.format_exception(exc_type, exc_value, exc_tb)

        return result

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract extra fields added via the extra= parameter."""
        extra = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS:
                extra[key] = value
        return extra


class TextFormatter(logging.Formatter):
    """
    Enhanced text formatter for human-readable terminal output.

    Provides colored output when writing to a TTY, with configurable
    format and optional context fields.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        use_colors: bool = True,
        include_context: bool = False,
    ):
        """
        Initialize the text formatter.

        Args:
            fmt: Log format string (uses default if not specified)
            datefmt: Date format string
            use_colors: Enable colored output (auto-detected for TTY)
            include_context: Include extra context fields
        """
        if fmt is None:
            fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_colors = use_colors and sys.stderr.isatty()
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with optional colors and context."""
        # Apply colors if enabled
        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            record.name = f"{self.DIM}{record.name}{self.RESET}"

        # Format the base message
        formatted = super().format(record)

        # Append context if enabled
        if self.include_context:
            extra = self._extract_extra(record)
            if extra:
                context_str = " ".join(f"{k}={v!r}" for k, v in extra.items())
                formatted = f"{formatted} [{context_str}]"

        return formatted

    def _extract_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract extra fields from the log record."""
        reserved = JSONFormatter.RESERVED_ATTRS
        return {k: v for k, v in record.__dict__.items() if k not in reserved}


def setup_logging(
    level: int = logging.INFO,
    log_format: str = "text",
    log_file: str | None = None,
    include_location: bool = False,
    static_fields: dict[str, Any] | None = None,
    noisy_loggers: list[str] | None = None,
) -> None:
    """
    Configure the root logger with the specified format.

    Args:
        level: Log level (e.g., logging.DEBUG, logging.INFO)
        log_format: Output format - "text" or "json"
        log_file: Path to log file (if provided, logs are written to file)
        include_location: Include file/line info in JSON logs
        static_fields: Static fields to add to every JSON log record
        noisy_loggers: Logger names to suppress to WARNING level

    Examples:
        # Basic text logging
        setup_logging(level=logging.DEBUG)

        # JSON logging for log aggregation
        setup_logging(
            level=logging.INFO,
            log_format="json",
            static_fields={"service": "spectra", "version": "2.0.0"}
        )

        # Log to file
        setup_logging(
            level=logging.DEBUG,
            log_file="/var/log/spectra.log",
            log_format="json"
        )
    """
    # Remove existing handlers
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Create formatter based on format type
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter(
            include_location=include_location,
            static_fields=static_fields,
        )
    else:
        formatter = TextFormatter(
            use_colors=(log_file is None),  # No colors when writing to file
            include_context=(level <= logging.DEBUG),
        )

    # Create console handler (always output to stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Create file handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)

        # File logs always use JSON format for better parsing, or text without colors
        if log_format == "json":
            file_formatter: logging.Formatter = JSONFormatter(
                include_location=include_location,
                static_fields=static_fields,
            )
        else:
            file_formatter = TextFormatter(
                use_colors=False,  # Never use colors in file output
                include_context=(level <= logging.DEBUG),
            )

        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)

    # Configure root logger
    root.setLevel(level)

    # Suppress noisy loggers
    default_noisy = ["urllib3", "requests", "httpcore", "httpx"]
    for logger_name in noisy_loggers or default_noisy:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(
    name: str,
    **extra: Any,
) -> "ContextLogger":
    """
    Get a logger with optional persistent context.

    Args:
        name: Logger name
        **extra: Extra context fields to include in all log records

    Returns:
        ContextLogger instance

    Examples:
        logger = get_logger("JiraAdapter", request_id="abc123")
        logger.info("Processing request")  # Includes request_id in context
    """
    return ContextLogger(name, extra)


class ContextLogger:
    """
    Logger wrapper that adds persistent context to all log records.

    Useful for adding request IDs, session IDs, or other context
    that should be included in all log messages.
    """

    def __init__(self, name: str, context: dict[str, Any]):
        """Initialize with logger name and context."""
        self._logger = logging.getLogger(name)
        self._context = context

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """Internal logging method that adds context."""
        extra = kwargs.pop("extra", {})
        extra.update(self._context)
        kwargs["extra"] = extra
        self._logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log exception with traceback."""
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)

    def bind(self, **extra: Any) -> "ContextLogger":
        """
        Create a new logger with additional context.

        Args:
            **extra: Additional context fields

        Returns:
            New ContextLogger with merged context
        """
        merged = {**self._context, **extra}
        return ContextLogger(self._logger.name, merged)


class SuppressLogsForProgress:
    """
    Context manager to suppress INFO logs during progress bar display.

    Temporarily raises log level to WARNING for specified loggers
    to prevent log messages from interfering with progress bar output.

    Usage:
        with SuppressLogsForProgress():
            # Progress bar updates here won't be interrupted by logs
            for item in items:
                progress.update()

        # Logs resume normally after the context
    """

    DEFAULT_LOGGERS = [
        "JiraAdapter",
        "SyncOrchestrator",
        "MarkdownParser",
        "spectra.application.sync.backup",
        "spectra.adapters.jira",
    ]

    def __init__(
        self,
        logger_names: list[str] | None = None,
        suppress_level: int = logging.WARNING,
    ):
        """
        Initialize the context manager.

        Args:
            logger_names: Names of loggers to suppress. Uses defaults if not specified.
            suppress_level: Minimum level to show during suppression (default: WARNING).
        """
        self.logger_names = logger_names or self.DEFAULT_LOGGERS
        self.suppress_level = suppress_level
        self._original_levels: dict[str, int] = {}

    def __enter__(self) -> "SuppressLogsForProgress":
        """Suppress logs by raising log levels."""
        for name in self.logger_names:
            logger = logging.getLogger(name)
            self._original_levels[name] = logger.level
            logger.setLevel(self.suppress_level)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Restore original log levels."""
        for name, level in self._original_levels.items():
            logging.getLogger(name).setLevel(level)


def suppress_logs_for_progress(
    logger_names: list[str] | None = None,
) -> SuppressLogsForProgress:
    """
    Convenience function to create a log suppression context.

    Args:
        logger_names: Optional list of logger names to suppress.

    Returns:
        SuppressLogsForProgress context manager.

    Example:
        with suppress_logs_for_progress():
            run_sync_with_progress_bar()
    """
    return SuppressLogsForProgress(logger_names=logger_names)
