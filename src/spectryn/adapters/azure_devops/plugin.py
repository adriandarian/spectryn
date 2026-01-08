"""
Azure DevOps Tracker Plugin - Plugin wrapper for Azure DevOps adapter.

This module provides the plugin interface for the Azure DevOps adapter,
enabling it to be discovered and loaded through the plugin system.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import AzureDevOpsAdapter


class AzureDevOpsTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the Azure DevOps adapter.

    Enables Azure DevOps integration through the spectra plugin system.

    Configuration options:
    - organization: Azure DevOps organization (required, or AZURE_DEVOPS_ORG env)
    - project: Project name (required, or AZURE_DEVOPS_PROJECT env)
    - pat: Personal Access Token (required, or AZURE_DEVOPS_PAT env)
    - base_url: Azure DevOps URL (optional, defaults to https://dev.azure.com)
    - dry_run: If True, don't make changes (default: True)
    - epic_type: Work item type for epics (default: "Epic")
    - story_type: Work item type for stories (default: "User Story")
    - task_type: Work item type for tasks (default: "Task")
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "organization": {
                "type": "string",
                "description": "Azure DevOps organization name",
                "required": False,
            },
            "project": {
                "type": "string",
                "description": "Project name",
                "required": False,
            },
            "pat": {
                "type": "string",
                "description": "Personal Access Token",
                "required": False,
            },
            "base_url": {
                "type": "string",
                "description": "Azure DevOps base URL",
                "default": "https://dev.azure.com",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If True, don't make changes",
                "default": True,
            },
            "epic_type": {
                "type": "string",
                "description": "Work item type for epics",
                "default": "Epic",
            },
            "story_type": {
                "type": "string",
                "description": "Work item type for user stories",
                "default": "User Story",
            },
            "task_type": {
                "type": "string",
                "description": "Work item type for tasks",
                "default": "Task",
            },
        },
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the Azure DevOps tracker plugin.

        Configuration can be passed directly or loaded from environment variables:
        - AZURE_DEVOPS_ORG: Organization name
        - AZURE_DEVOPS_PROJECT: Project name
        - AZURE_DEVOPS_PAT: Personal Access Token
        - AZURE_DEVOPS_URL: Base URL (optional)
        """
        super().__init__(config)
        self._adapter: AzureDevOpsAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="azure-devops",
            version="1.0.0",
            description="Azure DevOps integration for spectra",
            author="spectra contributors",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """
        Initialize the plugin.

        Creates the Azure DevOps adapter with configuration from config dict
        or environment variables.
        """
        # Get config values with env fallbacks
        organization = self.config.get("organization") or os.getenv("AZURE_DEVOPS_ORG", "")
        project = self.config.get("project") or os.getenv("AZURE_DEVOPS_PROJECT", "")
        pat = self.config.get("pat") or os.getenv("AZURE_DEVOPS_PAT", "")
        base_url = self.config.get("base_url") or os.getenv(
            "AZURE_DEVOPS_URL", "https://dev.azure.com"
        )

        if not organization:
            raise ValueError(
                "Azure DevOps organization is required. "
                "Set 'organization' in config or AZURE_DEVOPS_ORG env var."
            )
        if not project:
            raise ValueError(
                "Project name is required. Set 'project' in config or AZURE_DEVOPS_PROJECT env var."
            )
        if not pat:
            raise ValueError(
                "Personal Access Token is required. "
                "Set 'pat' in config or AZURE_DEVOPS_PAT env var."
            )

        # Create the adapter
        self._adapter = AzureDevOpsAdapter(
            organization=organization,
            project=project,
            pat=pat,
            base_url=base_url,
            dry_run=self.config.get("dry_run", True),
            epic_type=self.config.get("epic_type", "Epic"),
            story_type=self.config.get("story_type", "User Story"),
            task_type=self.config.get("task_type", "Task"),
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
        Get the Azure DevOps tracker instance.

        Returns:
            AzureDevOpsAdapter implementing IssueTrackerPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Azure DevOps plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = super().validate_config()

        # Check required fields (either in config or env)
        organization = self.config.get("organization") or os.getenv("AZURE_DEVOPS_ORG")
        project = self.config.get("project") or os.getenv("AZURE_DEVOPS_PROJECT")
        pat = self.config.get("pat") or os.getenv("AZURE_DEVOPS_PAT")

        if not organization:
            errors.append("Missing organization (set 'organization' or AZURE_DEVOPS_ORG)")
        if not project:
            errors.append("Missing project (set 'project' or AZURE_DEVOPS_PROJECT)")
        if not pat:
            errors.append("Missing PAT (set 'pat' or AZURE_DEVOPS_PAT)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> AzureDevOpsTrackerPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured AzureDevOpsTrackerPlugin instance
    """
    return AzureDevOpsTrackerPlugin(config)
