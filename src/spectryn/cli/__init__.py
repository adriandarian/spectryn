"""
CLI Module - Command Line Interface for spectra.
"""

from .app import main, run
from .completions import SUPPORTED_SHELLS, get_completion_script
from .exit_codes import ExitCode
from .interactive import InteractiveSession, run_interactive
from .logging import (
    ContextLogger,
    JSONFormatter,
    TextFormatter,
    get_logger,
    setup_logging,
)


__all__ = [
    "SUPPORTED_SHELLS",
    "ContextLogger",
    "ExitCode",
    "InteractiveSession",
    # Logging
    "JSONFormatter",
    "TextFormatter",
    "get_completion_script",
    "get_logger",
    "main",
    "run",
    "run_interactive",
    "setup_logging",
]
