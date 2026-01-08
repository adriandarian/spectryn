"""
Tests for plugins registry.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.plugins.base import Plugin, PluginMetadata, PluginType
from spectryn.plugins.registry import PluginRegistry, get_registry


class MockPlugin(Plugin):
    """Mock plugin for testing."""

    _default_name = "mock-plugin"
    _default_version = "1.0.0"
    _default_requires: list[str] = []

    def __init__(
        self,
        config: dict | None = None,
        name: str | None = None,
        version: str | None = None,
        requires: list[str] | None = None,
    ) -> None:
        super().__init__(config)
        self._name = name or self._default_name
        self._version = version or self._default_version
        self._requires = requires or self._default_requires

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version=self._version,
            description="A mock plugin for testing",
            plugin_type=PluginType.HOOK,
            requires=self._requires,
        )

    def initialize(self) -> None:
        pass


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass."""

    def test_metadata_creation(self):
        """Test PluginMetadata can be created."""
        meta = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )

        assert meta.name == "test-plugin"
        assert meta.version == "1.0.0"
        assert meta.description == "A test plugin"
        assert meta.plugin_type == PluginType.HOOK

    def test_metadata_with_type(self):
        """Test PluginMetadata with specific type."""
        meta = PluginMetadata(
            name="parser",
            version="0.1.0",
            description="Parser plugin",
            plugin_type=PluginType.PARSER,
        )

        assert meta.plugin_type == PluginType.PARSER

    def test_metadata_with_requires(self):
        """Test PluginMetadata with dependencies."""
        meta = PluginMetadata(
            name="dependent",
            version="1.0.0",
            description="Dependent plugin",
            requires=["base-plugin"],
        )

        assert meta.requires == ["base-plugin"]


class TestPluginRegistry:
    """Tests for PluginRegistry class."""

    def test_registry_init(self):
        """Test registry initialization."""
        registry = PluginRegistry()

        assert registry._plugins == {}
        assert len(registry._by_type) == len(PluginType)

    def test_registry_register_plugin(self):
        """Test registering a plugin."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)

        assert "mock-plugin" in registry._plugins
        assert plugin in registry._by_type[PluginType.HOOK]

    def test_registry_register_replaces_existing(self):
        """Test registering replaces existing plugin."""
        registry = PluginRegistry()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin()

        registry.register(plugin1)
        registry.register(plugin2)

        assert registry._plugins["mock-plugin"] is plugin2

    def test_registry_register_class(self):
        """Test registering a plugin class."""
        registry = PluginRegistry()

        plugin = registry.register_class(MockPlugin, {"key": "value"})

        assert plugin.config == {"key": "value"}
        assert "mock-plugin" in registry._plugins

    def test_registry_get_plugin(self):
        """Test getting a registered plugin."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)
        result = registry.get("mock-plugin")

        assert result is plugin

    def test_registry_get_nonexistent(self):
        """Test getting a non-existent plugin."""
        registry = PluginRegistry()
        result = registry.get("nonexistent")

        assert result is None

    def test_registry_has(self):
        """Test has method."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        assert not registry.has("mock-plugin")

        registry.register(plugin)

        assert registry.has("mock-plugin")

    def test_registry_get_by_type(self):
        """Test getting plugins by type."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)

        hooks = registry.get_by_type(PluginType.HOOK)
        parsers = registry.get_by_type(PluginType.PARSER)

        assert plugin in hooks
        assert plugin not in parsers

    def test_registry_get_all(self):
        """Test getting all plugins."""
        registry = PluginRegistry()
        plugin1 = MockPlugin(None, name="plugin1")
        plugin2 = MockPlugin(None, name="plugin2")

        registry.register(plugin1)
        registry.register(plugin2)

        all_plugins = registry.get_all()

        assert len(all_plugins) == 2
        assert plugin1 in all_plugins
        assert plugin2 in all_plugins

    def test_registry_unregister(self):
        """Test unregistering a plugin."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)
        assert registry.has("mock-plugin")

        result = registry.unregister("mock-plugin")

        assert result is True
        assert not registry.has("mock-plugin")

    def test_registry_unregister_nonexistent(self):
        """Test unregistering non-existent plugin."""
        registry = PluginRegistry()

        result = registry.unregister("nonexistent")

        assert result is False

    def test_registry_list_plugins(self):
        """Test listing plugins."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)

        plugins = registry.list_plugins()

        assert len(plugins) == 1
        assert plugins[0]["name"] == "mock-plugin"
        assert plugins[0]["version"] == "1.0.0"
        assert plugins[0]["type"] == "HOOK"


class TestPluginRegistryLifecycle:
    """Tests for plugin lifecycle methods."""

    def test_initialize_all(self):
        """Test initializing all plugins."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)
        failures = registry.initialize_all()

        assert failures == []
        assert plugin.is_initialized

    def test_initialize_skips_already_initialized(self):
        """Test initialization skips initialized plugins."""
        registry = PluginRegistry()
        plugin = MockPlugin()
        plugin._initialized = True

        registry.register(plugin)
        failures = registry.initialize_all()

        assert failures == []

    def test_initialize_fails_missing_dependency(self):
        """Test initialization fails with missing dependency."""
        registry = PluginRegistry()
        plugin = MockPlugin(None, requires=["missing-dep"])

        registry.register(plugin)
        failures = registry.initialize_all()

        assert "mock-plugin" in failures

    def test_shutdown_all(self):
        """Test shutting down all plugins."""
        registry = PluginRegistry()
        plugin = MockPlugin()
        plugin._initialized = True

        registry.register(plugin)
        registry.shutdown_all()

        assert not plugin.is_initialized


class TestPluginRegistryDiscovery:
    """Tests for plugin discovery methods."""

    def test_discover_from_nonexistent_directory(self):
        """Test discovering from non-existent directory."""
        registry = PluginRegistry()

        loaded = registry.discover_from_directory(Path("/nonexistent"))

        assert loaded == []

    def test_discover_from_empty_directory(self, tmp_path: Path):
        """Test discovering from empty directory."""
        registry = PluginRegistry()

        loaded = registry.discover_from_directory(tmp_path)

        assert loaded == []

    def test_discover_skips_private_files(self, tmp_path: Path):
        """Test discovery skips files starting with underscore."""
        registry = PluginRegistry()

        private_file = tmp_path / "_private.py"
        private_file.write_text("# Private file")

        loaded = registry.discover_from_directory(tmp_path)

        assert loaded == []

    def test_discover_entry_points(self):
        """Test discovering from entry points."""
        registry = PluginRegistry()

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = []
            loaded = registry.discover_entry_points()

            assert loaded == []


class TestGetRegistry:
    """Tests for get_registry singleton."""

    def test_get_registry_singleton(self):
        """Test get_registry returns same instance."""
        # Clear any existing registry
        import spectryn.plugins.registry as reg_module

        reg_module._registry = None

        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_get_registry_creates_instance(self):
        """Test get_registry creates instance if none exists."""
        import spectryn.plugins.registry as reg_module

        reg_module._registry = None

        registry = get_registry()

        assert registry is not None
        assert isinstance(registry, PluginRegistry)
