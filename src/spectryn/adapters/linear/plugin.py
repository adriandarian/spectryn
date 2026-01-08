"""
Linear Tracker Plugin - Plugin wrapper for Linear adapter.

This module provides the plugin interface for the Linear adapter,
enabling it to be discovered and loaded through the plugin system.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import LinearAdapter


class LinearTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the Linear adapter.

    Enables Linear integration through the spectra plugin system.

    Configuration options:
    - api_key: Linear API key (required, or use LINEAR_API_KEY env)
    - team_key: Team key like 'ENG' (required, or use LINEAR_TEAM_KEY env)
    - api_url: Linear GraphQL API URL (optional, defaults to production)
    - dry_run: If True, don't make changes (default: True)
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "description": "Linear API key",
                "required": False,  # Can come from env
            },
            "team_key": {
                "type": "string",
                "description": "Team key (e.g., 'ENG')",
                "required": False,  # Can come from env
            },
            "api_url": {
                "type": "string",
                "description": "Linear GraphQL API URL",
                "default": "https://api.linear.app/graphql",
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
        Initialize the Linear tracker plugin.

        Configuration can be passed directly or loaded from environment variables:
        - LINEAR_API_KEY: API key
        - LINEAR_TEAM_KEY: Team key (e.g., 'ENG')
        - LINEAR_API_URL: API URL (optional)
        """
        super().__init__(config)
        self._adapter: LinearAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="linear",
            version="1.0.0",
            description="Linear integration for spectra",
            author="spectra contributors",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """
        Initialize the plugin.

        Creates the Linear adapter with configuration from config dict
        or environment variables.
        """
        # Get config values with env fallbacks
        api_key = self.config.get("api_key") or os.getenv("LINEAR_API_KEY", "")
        team_key = self.config.get("team_key") or os.getenv("LINEAR_TEAM_KEY", "")
        api_url = self.config.get("api_url") or os.getenv(
            "LINEAR_API_URL", "https://api.linear.app/graphql"
        )

        if not api_key:
            raise ValueError(
                "Linear API key is required. Set 'api_key' in config or LINEAR_API_KEY env var."
            )
        if not team_key:
            raise ValueError(
                "Team key is required. Set 'team_key' in config or LINEAR_TEAM_KEY env var."
            )

        # Create the adapter
        self._adapter = LinearAdapter(
            api_key=api_key,
            team_key=team_key,
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
        Get the Linear tracker instance.

        Returns:
            LinearAdapter implementing IssueTrackerPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Linear plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = super().validate_config()

        # Check required fields (either in config or env)
        api_key = self.config.get("api_key") or os.getenv("LINEAR_API_KEY")
        team_key = self.config.get("team_key") or os.getenv("LINEAR_TEAM_KEY")

        if not api_key:
            errors.append("Missing Linear API key (set 'api_key' or LINEAR_API_KEY)")
        if not team_key:
            errors.append("Missing team key (set 'team_key' or LINEAR_TEAM_KEY)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> LinearTrackerPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured LinearTrackerPlugin instance
    """
    return LinearTrackerPlugin(config)
