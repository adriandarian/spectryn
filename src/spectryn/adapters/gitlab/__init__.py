"""
GitLab Adapter - Implements IssueTrackerPort for GitLab Issues.

This package provides integration with GitLab Issues API.
Supports both GitLab.com and self-hosted GitLab instances.

Optional: Use python-gitlab SDK by installing: pip install spectra[gitlab]
Then initialize adapter with use_sdk=True.
"""

from .adapter import GitLabAdapter


# Optional SDK support
try:
    from .sdk_client import GITLAB_SDK_AVAILABLE, GitLabSdkClient

    __all__ = ["GITLAB_SDK_AVAILABLE", "GitLabAdapter", "GitLabSdkClient"]
except ImportError:
    __all__ = ["GitLabAdapter"]
