"""
Plugin Base Classes - Abstract base for all plugins.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class PluginType(Enum):
    """
    Types of plugins supported by the plugin system.

    Attributes:
        PARSER: Input format parsers (e.g., Markdown, YAML).
        TRACKER: Issue tracker integrations (e.g., Jira, GitHub).
        FORMATTER: Output formatters (e.g., ADF, HTML).
        HOOK: Processing hooks for extensibility.
        COMMAND: Custom CLI commands.
    """

    PARSER = auto()  # Input format parsers
    TRACKER = auto()  # Issue trackers
    FORMATTER = auto()  # Output formatters
    HOOK = auto()  # Processing hooks
    COMMAND = auto()  # Custom commands


@dataclass
class PluginMetadata:
    """
    Metadata describing a plugin.

    Contains identifying information, dependencies, and configuration schema.

    Attributes:
        name: Unique plugin identifier.
        version: Semantic version string.
        description: Human-readable description of what the plugin does.
        author: Optional author name or email.
        plugin_type: The type of plugin (parser, tracker, etc.).
        requires: List of plugin names this plugin depends on.
        config_schema: Optional JSON Schema for config validation.
    """

    name: str
    version: str
    description: str
    author: str | None = None
    plugin_type: PluginType = PluginType.HOOK

    # Dependencies on other plugins
    requires: list[str] = field(default_factory=list)

    # Configuration schema (for validation)
    config_schema: dict[str, Any] | None = None


class Plugin(ABC):
    """
    Abstract base class for all plugins.

    Plugins must implement:
    - metadata property
    - initialize() method
    - Optional: shutdown() method
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize plugin with optional config.

        Args:
            config: Plugin-specific configuration
        """
        self.config: dict[str, Any] = config or {}
        self._initialized = False

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        ...

    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the plugin.

        Called when plugin is loaded. Should set up any resources needed.
        """
        ...

    def shutdown(self) -> None:
        """
        Shutdown the plugin.

        Called when plugin is unloaded. Should clean up resources.
        """

    def validate_config(self) -> list[str]:
        """
        Validate plugin configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        schema = self.metadata.config_schema
        if not schema:
            return errors

        # Check required fields
        for field, field_schema in schema.get("properties", {}).items():
            if field_schema.get("required") and field not in self.config:
                errors.append(f"Missing required config: {field}")

        return errors

    @property
    def is_initialized(self) -> bool:
        """
        Check if the plugin has been initialized.

        Returns:
            True if initialize() has been called successfully.
        """
        return self._initialized


class ParserPlugin(Plugin):
    """
    Base class for document parser plugins.

    Parser plugins provide DocumentParserPort implementations for
    reading different input formats (Markdown, YAML, etc.).
    """

    @property
    def plugin_type(self) -> PluginType:
        """Return the plugin type (always PARSER for this class)."""
        return PluginType.PARSER

    @abstractmethod
    def get_parser(self) -> Any:
        """
        Get the parser instance.

        Returns:
            An object implementing DocumentParserPort.
        """
        ...


class TrackerPlugin(Plugin):
    """
    Base class for issue tracker plugins.

    Tracker plugins provide IssueTrackerPort implementations for
    integrating with issue tracking systems (Jira, GitHub, etc.).
    """

    @property
    def plugin_type(self) -> PluginType:
        """Return the plugin type (always TRACKER for this class)."""
        return PluginType.TRACKER

    @abstractmethod
    def get_tracker(self) -> Any:
        """
        Get the tracker instance.

        Returns:
            An object implementing IssueTrackerPort.
        """
        ...


class FormatterPlugin(Plugin):
    """
    Base class for document formatter plugins.

    Formatter plugins provide DocumentFormatterPort implementations for
    formatting output in different formats (ADF, HTML, etc.).
    """

    @property
    def plugin_type(self) -> PluginType:
        """Return the plugin type (always FORMATTER for this class)."""
        return PluginType.FORMATTER

    @abstractmethod
    def get_formatter(self) -> Any:
        """
        Get the formatter instance.

        Returns:
            An object implementing DocumentFormatterPort.
        """
        ...
