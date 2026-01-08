"""
Shortcut Tracker Plugin - Plugin wrapper for Shortcut adapter.

This module provides the plugin interface for the Shortcut adapter,
enabling it to be discovered and loaded through the plugin system.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import ShortcutAdapter


class ShortcutTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the Shortcut adapter.

    Enables Shortcut integration through the spectra plugin system.

    Configuration options:
    - api_token: Shortcut API token (required, or use SHORTCUT_API_TOKEN env)
    - workspace_id: Workspace ID (required, or use SHORTCUT_WORKSPACE_ID env)
    - api_url: Shortcut API URL (optional, defaults to production)
    - dry_run: If True, don't make changes (default: True)
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_token": {
                "type": "string",
                "description": "Shortcut API token",
                "required": False,  # Can come from env
            },
            "workspace_id": {
                "type": "string",
                "description": "Shortcut workspace ID",
                "required": False,  # Can come from env
            },
            "api_url": {
                "type": "string",
                "description": "Shortcut API URL",
                "default": "https://api.app.shortcut.com/api/v3",
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
        Initialize the Shortcut tracker plugin.

        Configuration can be passed directly or loaded from environment variables:
        - SHORTCUT_API_TOKEN: API token
        - SHORTCUT_WORKSPACE_ID: Workspace ID
        - SHORTCUT_API_URL: API URL (optional)
        """
        super().__init__(config)
        self._adapter: ShortcutAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="shortcut",
            version="1.0.0",
            description="Shortcut (formerly Clubhouse) integration for spectra",
            author="spectra contributors",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """
        Initialize the plugin.

        Creates the Shortcut adapter with configuration from config dict
        or environment variables.
        """
        # Get config values with env fallbacks
        api_token = self.config.get("api_token") or os.getenv("SHORTCUT_API_TOKEN", "")
        workspace_id = self.config.get("workspace_id") or os.getenv("SHORTCUT_WORKSPACE_ID", "")
        api_url_str = self.config.get("api_url") or os.getenv(
            "SHORTCUT_API_URL", "https://api.app.shortcut.com/api/v3"
        )
        api_url = str(api_url_str) if api_url_str else "https://api.app.shortcut.com/api/v3"

        if not api_token:
            raise ValueError(
                "Shortcut API token is required. "
                "Set 'api_token' in config or SHORTCUT_API_TOKEN env var."
            )
        if not workspace_id:
            raise ValueError(
                "Workspace ID is required. "
                "Set 'workspace_id' in config or SHORTCUT_WORKSPACE_ID env var."
            )

        # Create the adapter
        self._adapter = ShortcutAdapter(
            api_token=api_token,
            workspace_id=workspace_id,
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
        Get the Shortcut tracker instance.

        Returns:
            ShortcutAdapter implementing IssueTrackerPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Shortcut plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = super().validate_config()

        # Check required fields (either in config or env)
        api_token = self.config.get("api_token") or os.getenv("SHORTCUT_API_TOKEN")
        workspace_id = self.config.get("workspace_id") or os.getenv("SHORTCUT_WORKSPACE_ID")

        if not api_token:
            errors.append("Missing Shortcut API token (set 'api_token' or SHORTCUT_API_TOKEN)")
        if not workspace_id:
            errors.append("Missing workspace ID (set 'workspace_id' or SHORTCUT_WORKSPACE_ID)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> ShortcutTrackerPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured ShortcutTrackerPlugin instance
    """
    return ShortcutTrackerPlugin(config)
