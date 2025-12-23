"""
Tests for plugin base classes.
"""

from typing import Any

import pytest

from spectra.plugins.base import (
    FormatterPlugin,
    ParserPlugin,
    Plugin,
    PluginMetadata,
    PluginType,
    TrackerPlugin,
)


class TestPluginType:
    """Tests for PluginType enum."""

    def test_plugin_types_exist(self):
        """Test all expected plugin types exist."""
        assert PluginType.PARSER
        assert PluginType.TRACKER
        assert PluginType.FORMATTER
        assert PluginType.HOOK
        assert PluginType.COMMAND

    def test_plugin_type_count(self):
        """Test expected number of plugin types."""
        assert len(PluginType) == 5


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_create_minimal(self):
        """Test creating metadata with minimal fields."""
        meta = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test plugin",
        )

        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.description == "Test plugin"
        assert meta.author is None
        assert meta.plugin_type == PluginType.HOOK
        assert meta.requires == []
        assert meta.config_schema is None

    def test_create_full(self):
        """Test creating metadata with all fields."""
        schema = {"type": "object"}
        meta = PluginMetadata(
            name="full",
            version="2.0.0",
            description="Full plugin",
            author="Test Author",
            plugin_type=PluginType.PARSER,
            requires=["dep1", "dep2"],
            config_schema=schema,
        )

        assert meta.name == "full"
        assert meta.author == "Test Author"
        assert meta.plugin_type == PluginType.PARSER
        assert meta.requires == ["dep1", "dep2"]
        assert meta.config_schema == schema


class ConcretePlugin(Plugin):
    """Concrete implementation for testing."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="concrete",
            version="1.0.0",
            description="Concrete plugin",
            config_schema={
                "properties": {
                    "required_field": {"required": True},
                    "optional_field": {"required": False},
                }
            },
        )

    def initialize(self) -> None:
        pass


class TestPlugin:
    """Tests for Plugin abstract base class."""

    def test_init_without_config(self):
        """Test initialization without config."""
        plugin = ConcretePlugin()

        assert plugin.config == {}
        assert not plugin.is_initialized

    def test_init_with_config(self):
        """Test initialization with config."""
        plugin = ConcretePlugin({"key": "value"})

        assert plugin.config == {"key": "value"}

    def test_is_initialized_property(self):
        """Test is_initialized property."""
        plugin = ConcretePlugin()

        assert not plugin.is_initialized

        plugin._initialized = True

        assert plugin.is_initialized

    def test_shutdown_default_impl(self):
        """Test default shutdown implementation."""
        plugin = ConcretePlugin()

        # Should not raise
        plugin.shutdown()

    def test_validate_config_no_schema(self):
        """Test validate_config with no schema."""

        class NoSchemaPlugin(Plugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    name="no-schema",
                    version="1.0.0",
                    description="No schema",
                )

            def initialize(self) -> None:
                pass

        plugin = NoSchemaPlugin()
        errors = plugin.validate_config()

        assert errors == []

    def test_validate_config_missing_required(self):
        """Test validate_config with missing required field."""
        plugin = ConcretePlugin()
        errors = plugin.validate_config()

        assert "Missing required config: required_field" in errors

    def test_validate_config_has_required(self):
        """Test validate_config with required field present."""
        plugin = ConcretePlugin({"required_field": "value"})
        errors = plugin.validate_config()

        assert errors == []


class ConcreteParserPlugin(ParserPlugin):
    """Concrete parser plugin for testing."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="parser",
            version="1.0.0",
            description="Parser plugin",
            plugin_type=PluginType.PARSER,
        )

    def initialize(self) -> None:
        pass

    def get_parser(self) -> Any:
        return "mock_parser"


class TestParserPlugin:
    """Tests for ParserPlugin base class."""

    def test_plugin_type(self):
        """Test parser plugin type property."""
        plugin = ConcreteParserPlugin()

        assert plugin.plugin_type == PluginType.PARSER

    def test_get_parser(self):
        """Test get_parser method."""
        plugin = ConcreteParserPlugin()

        assert plugin.get_parser() == "mock_parser"


class ConcreteTrackerPlugin(TrackerPlugin):
    """Concrete tracker plugin for testing."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="tracker",
            version="1.0.0",
            description="Tracker plugin",
            plugin_type=PluginType.TRACKER,
        )

    def initialize(self) -> None:
        pass

    def get_tracker(self) -> Any:
        return "mock_tracker"


class TestTrackerPlugin:
    """Tests for TrackerPlugin base class."""

    def test_plugin_type(self):
        """Test tracker plugin type property."""
        plugin = ConcreteTrackerPlugin()

        assert plugin.plugin_type == PluginType.TRACKER

    def test_get_tracker(self):
        """Test get_tracker method."""
        plugin = ConcreteTrackerPlugin()

        assert plugin.get_tracker() == "mock_tracker"


class ConcreteFormatterPlugin(FormatterPlugin):
    """Concrete formatter plugin for testing."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="formatter",
            version="1.0.0",
            description="Formatter plugin",
            plugin_type=PluginType.FORMATTER,
        )

    def initialize(self) -> None:
        pass

    def get_formatter(self) -> Any:
        return "mock_formatter"


class TestFormatterPlugin:
    """Tests for FormatterPlugin base class."""

    def test_plugin_type(self):
        """Test formatter plugin type property."""
        plugin = ConcreteFormatterPlugin()

        assert plugin.plugin_type == PluginType.FORMATTER

    def test_get_formatter(self):
        """Test get_formatter method."""
        plugin = ConcreteFormatterPlugin()

        assert plugin.get_formatter() == "mock_formatter"

