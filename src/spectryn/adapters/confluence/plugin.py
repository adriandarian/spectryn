"""
Confluence Plugin - Plugin wrapper for Confluence adapter.

Provides plugin system integration for publishing to Confluence.
"""

import os
from dataclasses import dataclass
from typing import Any

from spectryn.core.ports.document_output import DocumentOutputPort
from spectryn.plugins.base import Plugin, PluginMetadata, PluginType

from .adapter import ConfluenceAdapter
from .client import ConfluenceClient, ConfluenceConfig


@dataclass
class ConfluencePluginConfig:
    """Configuration for Confluence plugin."""

    base_url: str
    username: str
    api_token: str
    is_cloud: bool = True
    default_space: str | None = None
    timeout: int = 30


class ConfluencePlugin(Plugin):
    """
    Plugin wrapper for Confluence adapter.

    Configuration via environment variables:
    - CONFLUENCE_URL: Base URL (e.g., https://company.atlassian.net/wiki)
    - CONFLUENCE_USERNAME: Username/email
    - CONFLUENCE_API_TOKEN: API token (Cloud) or password (Server)
    - CONFLUENCE_SPACE: Default space key
    - CONFLUENCE_IS_CLOUD: "true" for Cloud, "false" for Server

    Or via config dict:
    {
        "base_url": "https://company.atlassian.net/wiki",
        "username": "user@example.com",
        "api_token": "xxx",
        "is_cloud": true,
        "default_space": "DEV"
    }
    """

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "base_url": {"type": "string", "description": "Confluence base URL"},
            "username": {"type": "string", "description": "Username or email"},
            "api_token": {"type": "string", "description": "API token or password"},
            "is_cloud": {"type": "boolean", "description": "True for Cloud, False for Server"},
            "default_space": {"type": "string", "description": "Default space key"},
            "timeout": {"type": "integer", "description": "Request timeout in seconds"},
        },
        "required": ["base_url", "username", "api_token"],
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the Confluence plugin.

        Args:
            config: Optional configuration dict
        """
        super().__init__(config)
        self._adapter: ConfluenceAdapter | None = None
        self._config: ConfluencePluginConfig | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="confluence",
            version="1.0.0",
            description="Publish epics and stories to Confluence pages",
            author="spectra contributors",
            plugin_type=PluginType.FORMATTER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """Initialize the plugin and connect to Confluence."""
        # Build config from environment and provided config
        config = self._build_config()

        # Create client and adapter
        client_config = ConfluenceConfig(
            base_url=config.base_url,
            username=config.username,
            api_token=config.api_token,
            is_cloud=config.is_cloud,
            timeout=config.timeout,
        )

        client = ConfluenceClient(client_config)
        self._adapter = ConfluenceAdapter(client)
        self._adapter.connect()
        self._config = config
        self._initialized = True

    def shutdown(self) -> None:
        """Disconnect and cleanup."""
        if self._adapter:
            self._adapter.disconnect()
            self._adapter = None
        self._config = None
        self._initialized = False

    def _build_config(self) -> ConfluencePluginConfig:
        """Build configuration from environment and provided config."""
        provided = self.config or {}

        base_url = provided.get("base_url") or os.environ.get("CONFLUENCE_URL")
        username = provided.get("username") or os.environ.get("CONFLUENCE_USERNAME")
        api_token = provided.get("api_token") or os.environ.get("CONFLUENCE_API_TOKEN")

        if not base_url:
            raise ValueError("Confluence URL required (base_url or CONFLUENCE_URL)")
        if not username:
            raise ValueError("Confluence username required (username or CONFLUENCE_USERNAME)")
        if not api_token:
            raise ValueError("Confluence API token required (api_token or CONFLUENCE_API_TOKEN)")

        # Determine if Cloud or Server
        is_cloud_str = provided.get("is_cloud")
        if is_cloud_str is None:
            is_cloud_str = os.environ.get("CONFLUENCE_IS_CLOUD", "true")

        if isinstance(is_cloud_str, bool):
            is_cloud = is_cloud_str
        else:
            is_cloud = str(is_cloud_str).lower() in ("true", "1", "yes")

        return ConfluencePluginConfig(
            base_url=base_url,
            username=username,
            api_token=api_token,
            is_cloud=is_cloud,
            default_space=provided.get("default_space") or os.environ.get("CONFLUENCE_SPACE"),
            timeout=int(provided.get("timeout", os.environ.get("CONFLUENCE_TIMEOUT", 30))),
        )

    def get_adapter(self) -> DocumentOutputPort:
        """
        Get the Confluence adapter.

        Returns:
            ConfluenceAdapter implementing DocumentOutputPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Confluence plugin not initialized. Call initialize() first.")
        return self._adapter

    @property
    def default_space(self) -> str | None:
        """Get the configured default space key."""
        return self._config.default_space if self._config else None


def create_plugin(config: dict[str, Any] | None = None) -> ConfluencePlugin:
    """
    Factory function for plugin discovery.

    Args:
        config: Optional configuration dict

    Returns:
        Configured ConfluencePlugin instance
    """
    return ConfluencePlugin(config)
