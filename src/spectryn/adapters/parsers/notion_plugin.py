"""
Notion Parser Plugin - Plugin wrapper for Notion parser.

This module provides the plugin interface for the Notion parser,
enabling it to be discovered and loaded through the plugin system.
"""

from typing import Any

from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.plugins.base import ParserPlugin, PluginMetadata, PluginType

from .notion_parser import NotionParser


class NotionParserPlugin(ParserPlugin):
    """
    Plugin wrapper for the Notion parser.

    Enables parsing of Notion exports through the spectra plugin system.

    Supports:
    - Single page markdown exports
    - Database CSV exports
    - Full workspace folder exports

    Configuration options:
    - None currently (parser is stateless)
    """

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the Notion parser plugin.

        Args:
            config: Optional plugin configuration
        """
        super().__init__(config)
        self._parser: NotionParser | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="notion-parser",
            version="1.0.0",
            description="Notion export parser for spectra",
            author="spectra contributors",
            plugin_type=PluginType.PARSER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """Initialize the plugin."""
        self._parser = NotionParser()
        self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        self._parser = None
        self._initialized = False

    def get_parser(self) -> DocumentParserPort:
        """
        Get the Notion parser instance.

        Returns:
            NotionParser implementing DocumentParserPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._parser is None:
            raise RuntimeError("Notion parser plugin not initialized. Call initialize() first.")
        return self._parser


def create_plugin(config: dict[str, Any] | None = None) -> NotionParserPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured NotionParserPlugin instance
    """
    return NotionParserPlugin(config)
