"""
Ports - Abstract interfaces for external dependencies.

Ports define the contracts that adapters must implement.
This enables dependency inversion and easy testing.
"""

from .issue_tracker import (
    IssueTrackerPort,
    IssueTrackerError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    TransitionError,
    RateLimitError,
    TransientError,
)
from .async_tracker import AsyncIssueTrackerPort
from .document_parser import DocumentParserPort, ParserError
from .document_output import (
    DocumentOutputPort,
    DocumentOutputError,
    AuthenticationError as OutputAuthenticationError,
    NotFoundError as OutputNotFoundError,
    PermissionError as OutputPermissionError,
    RateLimitError as OutputRateLimitError,
)
from .document_formatter import DocumentFormatterPort
from .config_provider import ConfigProviderPort

__all__ = [
    # Ports
    "IssueTrackerPort",
    "AsyncIssueTrackerPort",
    "DocumentParserPort",
    "DocumentOutputPort",
    "DocumentFormatterPort",
    "ConfigProviderPort",
    # Issue tracker exceptions
    "IssueTrackerError",
    "AuthenticationError",
    "NotFoundError",
    "PermissionError",
    "TransitionError",
    "RateLimitError",
    "TransientError",
    # Parser exceptions
    "ParserError",
    # Output exceptions
    "DocumentOutputError",
    "OutputAuthenticationError",
    "OutputNotFoundError",
    "OutputPermissionError",
    "OutputRateLimitError",
]

