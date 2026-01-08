"""Issue tracker adapters - implementations for various platforms."""

from spectryn.adapters.asana import AsanaAdapter
from spectryn.adapters.azure_devops import AzureDevOpsAdapter
from spectryn.adapters.confluence import ConfluenceAdapter
from spectryn.adapters.github import GitHubAdapter
from spectryn.adapters.gitlab import GitLabAdapter
from spectryn.adapters.jira import JiraAdapter
from spectryn.adapters.linear import LinearAdapter


__all__ = [
    "AsanaAdapter",
    "AzureDevOpsAdapter",
    "ConfluenceAdapter",
    "GitHubAdapter",
    "GitLabAdapter",
    "JiraAdapter",
    "LinearAdapter",
]
