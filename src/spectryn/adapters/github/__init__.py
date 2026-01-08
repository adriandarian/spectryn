"""
GitHub Issues Adapter - Integration with GitHub Issues.

This module provides the GitHub Issues implementation of the IssueTrackerPort,
enabling syncing markdown documents to GitHub Issues.
"""

from .adapter import GitHubAdapter
from .client import GitHubApiClient
from .plugin import GitHubTrackerPlugin


__all__ = [
    "GitHubAdapter",
    "GitHubApiClient",
    "GitHubTrackerPlugin",
]
