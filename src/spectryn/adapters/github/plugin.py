"""
GitHub Issues Tracker Plugin - Plugin wrapper for GitHub adapter.

This module provides the plugin interface for the GitHub Issues adapter,
enabling it to be discovered and loaded through the plugin system.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import GitHubAdapter


class GitHubTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the GitHub Issues adapter.

    Enables GitHub Issues integration through the spectra plugin system.

    Configuration options:
    - token: GitHub Personal Access Token (required, or use GITHUB_TOKEN env)
    - owner: Repository owner (required, or use GITHUB_OWNER env)
    - repo: Repository name (required, or use GITHUB_REPO env)
    - base_url: GitHub API URL (optional, for GitHub Enterprise)
    - dry_run: If True, don't make changes (default: True)
    - epic_label: Label for epic issues (default: "epic")
    - story_label: Label for story issues (default: "story")
    - subtask_label: Label for subtask issues (default: "subtask")
    - subtasks_as_issues: Create subtasks as separate issues (default: False)
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "GitHub Personal Access Token",
                "required": False,  # Can come from env
            },
            "owner": {
                "type": "string",
                "description": "Repository owner (user or organization)",
                "required": False,  # Can come from env
            },
            "repo": {
                "type": "string",
                "description": "Repository name",
                "required": False,  # Can come from env
            },
            "base_url": {
                "type": "string",
                "description": "GitHub API base URL (for GitHub Enterprise)",
                "default": "https://api.github.com",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If True, don't make changes",
                "default": True,
            },
            "epic_label": {
                "type": "string",
                "description": "Label used to identify epic issues",
                "default": "epic",
            },
            "story_label": {
                "type": "string",
                "description": "Label used to identify story issues",
                "default": "story",
            },
            "subtask_label": {
                "type": "string",
                "description": "Label used to identify subtask issues",
                "default": "subtask",
            },
            "subtasks_as_issues": {
                "type": "boolean",
                "description": "Create subtasks as separate issues instead of task lists",
                "default": False,
            },
        },
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the GitHub tracker plugin.

        Configuration can be passed directly or loaded from environment variables:
        - GITHUB_TOKEN: Personal Access Token
        - GITHUB_OWNER: Repository owner
        - GITHUB_REPO: Repository name
        - GITHUB_API_URL: API base URL (for GitHub Enterprise)
        """
        super().__init__(config)
        self._adapter: GitHubAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="github-issues",
            version="1.0.0",
            description="GitHub Issues integration for spectra",
            author="spectra contributors",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """
        Initialize the plugin.

        Creates the GitHub adapter with configuration from config dict
        or environment variables.
        """
        # Get config values with env fallbacks
        token = self.config.get("token") or os.getenv("GITHUB_TOKEN", "")
        owner = self.config.get("owner") or os.getenv("GITHUB_OWNER", "")
        repo = self.config.get("repo") or os.getenv("GITHUB_REPO", "")
        base_url = self.config.get("base_url") or os.getenv(
            "GITHUB_API_URL", "https://api.github.com"
        )

        if not token:
            raise ValueError(
                "GitHub token is required. Set 'token' in config or GITHUB_TOKEN env var."
            )
        if not owner:
            raise ValueError(
                "Repository owner is required. Set 'owner' in config or GITHUB_OWNER env var."
            )
        if not repo:
            raise ValueError(
                "Repository name is required. Set 'repo' in config or GITHUB_REPO env var."
            )

        # Create the adapter
        self._adapter = GitHubAdapter(
            token=token,
            owner=owner,
            repo=repo,
            base_url=base_url,
            dry_run=self.config.get("dry_run", True),
            epic_label=self.config.get("epic_label", "epic"),
            story_label=self.config.get("story_label", "story"),
            subtask_label=self.config.get("subtask_label", "subtask"),
            subtasks_as_issues=self.config.get("subtasks_as_issues", False),
        )

        self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the plugin and cleanup resources."""
        if self._adapter is not None:
            self._adapter._client.close()
            self._adapter = None
        self._initialized = False

    def get_tracker(self) -> IssueTrackerPort:
        """
        Get the GitHub tracker instance.

        Returns:
            GitHubAdapter implementing IssueTrackerPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("GitHub plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = super().validate_config()

        # Check required fields (either in config or env)
        token = self.config.get("token") or os.getenv("GITHUB_TOKEN")
        owner = self.config.get("owner") or os.getenv("GITHUB_OWNER")
        repo = self.config.get("repo") or os.getenv("GITHUB_REPO")

        if not token:
            errors.append("Missing GitHub token (set 'token' or GITHUB_TOKEN)")
        if not owner:
            errors.append("Missing repository owner (set 'owner' or GITHUB_OWNER)")
        if not repo:
            errors.append("Missing repository name (set 'repo' or GITHUB_REPO)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> GitHubTrackerPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured GitHubTrackerPlugin instance
    """
    return GitHubTrackerPlugin(config)
