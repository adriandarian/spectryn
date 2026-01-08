"""
YAML Parser Plugin - Plugin wrapper for YAML parser.

This module provides the plugin interface for the YAML parser,
enabling it to be discovered and loaded through the plugin system.
"""

from typing import Any

from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.plugins.base import ParserPlugin, PluginMetadata, PluginType

from .yaml_parser import YamlParser


class YamlParserPlugin(ParserPlugin):
    """
    Plugin wrapper for the YAML parser.

    Enables YAML document parsing through the spectra plugin system.

    This provides an alternative to markdown for defining epics and stories,
    with a more structured, machine-friendly format.

    Configuration options:
    - strict: Enable strict validation mode (default: False)
    """

    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "strict": {
                "type": "boolean",
                "description": "Enable strict validation mode",
                "default": False,
            },
        },
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize the YAML parser plugin.

        Args:
            config: Optional plugin configuration
        """
        super().__init__(config)
        self._parser: YamlParser | None = None

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return PluginMetadata(
            name="yaml-parser",
            version="1.0.0",
            description="YAML document parser for spectra",
            author="spectra contributors",
            plugin_type=PluginType.PARSER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        """Initialize the plugin."""
        self._parser = YamlParser()
        self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the plugin."""
        self._parser = None
        self._initialized = False

    def get_parser(self) -> DocumentParserPort:
        """
        Get the YAML parser instance.

        Returns:
            YamlParser implementing DocumentParserPort

        Raises:
            RuntimeError: If plugin not initialized
        """
        if not self.is_initialized or self._parser is None:
            raise RuntimeError("YAML parser plugin not initialized. Call initialize() first.")
        return self._parser


def create_plugin(config: dict[str, Any] | None = None) -> YamlParserPlugin:
    """
    Factory function for plugin discovery.

    This function is called by the plugin registry when discovering
    plugins from files.

    Args:
        config: Optional plugin configuration

    Returns:
        Configured YamlParserPlugin instance
    """
    return YamlParserPlugin(config)
