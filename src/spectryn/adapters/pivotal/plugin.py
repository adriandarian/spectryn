"""
Pivotal Tracker Plugin - Plugin wrapper for Pivotal Tracker adapter.

This module provides the plugin interface for the Pivotal Tracker adapter,
enabling it to be discovered and loaded through the plugin system.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import PivotalAdapter


class PivotalTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the Pivotal Tracker adapter.

    Enables Pivotal Tracker integration through the spectra plugin system.

    Configuration options:
    - api_token: Pivotal Tracker API token (required, or use PIVOTAL_API_TOKEN env)
    - project_id: Project ID (required, or use PIVOTAL_PROJECT_ID env)
    - api_url: Pivotal Tracker API URL (optional, defaults to production)
    - dry_run: If True, don't make changes (default: True)
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_token": {
                "type": "string",
                "description": "Pivotal Tracker API token",
                "required": False,  # Can come from env
            },
            "project_id": {
                "type": "string",
                "description": "Pivotal Tracker project ID",
                "required": False,  # Can come from env
            },
            "api_url": {
                "type": "string",
                "description": "Pivotal Tracker API URL",
                "default": "https://www.pivotaltracker.com/services/v5",
            },
            "dry_run": {
                "type": "boolean",
                "description": "If True, don't make changes",
                "default": True,
            },
        },
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the Pivotal Tracker plugin.

        Configuration can be passed directly or loaded from environment variables:
        - PIVOTAL_API_TOKEN: API token
        - PIVOTAL_PROJECT_ID: Project ID
        - PIVOTAL_API_URL: API URL (optional)
        """
        super().__init__(config)
        self._adapter: PivotalAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="pivotal",
            version="1.0.0",
            description="Pivotal Tracker integration for spectra",
            author="spectra contributors",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """
        Initialize the plugin.

        Creates the Pivotal Tracker adapter with configuration from config dict
        or environment variables.
        """
        # Get config values with env fallbacks
        api_token = self.config.get("api_token") or os.getenv("PIVOTAL_API_TOKEN", "")
        project_id = self.config.get("project_id") or os.getenv("PIVOTAL_PROJECT_ID", "")
        api_url_str = self.config.get("api_url") or os.getenv(
            "PIVOTAL_API_URL", "https://www.pivotaltracker.com/services/v5"
        )
        api_url = str(api_url_str) if api_url_str else "https://www.pivotaltracker.com/services/v5"

        if not api_token:
            raise ValueError(
                "Pivotal Tracker API token is required. "
                "Set 'api_token' in config or PIVOTAL_API_TOKEN env var."
            )
        if not project_id:
            raise ValueError(
                "Project ID is required. Set 'project_id' in config or PIVOTAL_PROJECT_ID env var."
            )

        # Create the adapter
        self._adapter = PivotalAdapter(
            api_token=api_token,
            project_id=project_id,
            api_url=api_url,
            dry_run=self.config.get("dry_run", True),
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
        Get the Pivotal Tracker instance.

        Returns:
            PivotalAdapter implementing IssueTrackerPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Pivotal Tracker plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = super().validate_config()

        # Check required fields (either in config or env)
        api_token = self.config.get("api_token") or os.getenv("PIVOTAL_API_TOKEN")
        project_id = self.config.get("project_id") or os.getenv("PIVOTAL_PROJECT_ID")

        if not api_token:
            errors.append(
                "Missing Pivotal Tracker API token (set 'api_token' or PIVOTAL_API_TOKEN)"
            )
        if not project_id:
            errors.append("Missing project ID (set 'project_id' or PIVOTAL_PROJECT_ID)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> PivotalTrackerPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured PivotalTrackerPlugin instance
    """
    return PivotalTrackerPlugin(config)
