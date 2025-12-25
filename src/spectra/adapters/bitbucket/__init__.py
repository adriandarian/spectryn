"""
Bitbucket Issues Adapter - Integration with Bitbucket Cloud/Server Issues.

This module provides the Bitbucket implementation of the IssueTrackerPort,
enabling syncing markdown documents to Bitbucket Issues.

Optional dependency: atlassian-python-api for enhanced Server support.
Install with: pip install spectra[bitbucket]
"""

from .adapter import BitbucketAdapter
from .client import BitbucketApiClient


# Optional Server client
try:
    from .server_client import (
        ATLASSIAN_API_AVAILABLE,
        BitbucketServerClient,
        is_server_url,
    )

    __all__ = [
        "ATLASSIAN_API_AVAILABLE",
        "BitbucketAdapter",
        "BitbucketApiClient",
        "BitbucketServerClient",
        "is_server_url",
    ]
except ImportError:
    ATLASSIAN_API_AVAILABLE = False
    BitbucketServerClient = None  # type: ignore[assignment, misc]

    def is_server_url(url: str) -> bool:  # type: ignore[misc]
        """Fallback implementation."""
        return False

    __all__ = [
        "ATLASSIAN_API_AVAILABLE",
        "BitbucketAdapter",
        "BitbucketApiClient",
    ]
