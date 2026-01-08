"""
Plugin Registry - Manages plugin discovery, loading, and lifecycle.
"""

import logging
from pathlib import Path
from typing import Any

from .base import Plugin, PluginType


class PluginRegistry:
    """
    Central registry for all plugins.

    Handles:
    - Plugin discovery (from directories, entry points)
    - Plugin loading and initialization
    - Plugin lookup by type/name
    - Plugin lifecycle management
    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._plugins: dict[str, Plugin] = {}
        self._by_type: dict[PluginType, list[Plugin]] = {t: [] for t in PluginType}
        self.logger = logging.getLogger("PluginRegistry")

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(self, plugin: Plugin) -> None:
        """
        Register a plugin.

        Args:
            plugin: Plugin instance to register
        """
        name = plugin.metadata.name

        if name in self._plugins:
            self.logger.warning(f"Plugin '{name}' already registered, replacing")

        self._plugins[name] = plugin
        self._by_type[plugin.metadata.plugin_type].append(plugin)

        self.logger.info(f"Registered plugin: {name} v{plugin.metadata.version}")

    def register_class(
        self,
        plugin_class: type[Plugin],
        config: dict[str, Any] | None = None,
    ) -> Plugin:
        """
        Register a plugin by class.

        Args:
            plugin_class: Plugin class
            config: Plugin configuration

        Returns:
            Created plugin instance
        """
        plugin = plugin_class(config)
        self.register(plugin)
        return plugin

    def unregister(self, name: str) -> bool:
        """
        Unregister a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if found and removed
        """
        if name not in self._plugins:
            return False

        plugin = self._plugins[name]

        # Shutdown plugin
        try:
            plugin.shutdown()
        except Exception as e:
            self.logger.error(f"Error shutting down plugin '{name}': {e}")

        # Remove from registries
        del self._plugins[name]
        self._by_type[plugin.metadata.plugin_type].remove(plugin)

        self.logger.info(f"Unregistered plugin: {name}")
        return True

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def discover_from_directory(self, directory: Path) -> list[str]:
        """
        Discover and load plugins from a directory.

        Looks for Python files with a `create_plugin()` function.

        Args:
            directory: Directory to search

        Returns:
            List of loaded plugin names
        """
        loaded: list[str] = []

        if not directory.exists():
            return loaded

        for file in directory.glob("*.py"):
            if file.name.startswith("_"):
                continue

            try:
                plugin = self._load_plugin_file(file)
                if plugin:
                    loaded.append(plugin.metadata.name)
            except Exception as e:
                self.logger.error(f"Failed to load plugin from {file}: {e}")

        return loaded

    def _load_plugin_file(self, file: Path) -> Plugin | None:
        """Load a plugin from a Python file."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(file.stem, file)
        if not spec or not spec.loader:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for create_plugin function
        if hasattr(module, "create_plugin"):
            plugin = module.create_plugin()
            self.register(plugin)
            return plugin

        return None

    def discover_entry_points(self, group: str = "spectryn.plugins") -> list[str]:
        """
        Discover plugins from setuptools entry points.

        Args:
            group: Entry point group name

        Returns:
            List of loaded plugin names
        """
        loaded: list[str] = []

        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=group)
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    plugin = plugin_class()
                    self.register(plugin)
                    loaded.append(plugin.metadata.name)
                except Exception as e:
                    self.logger.error(f"Failed to load entry point {ep.name}: {e}")

        except ImportError:
            self.logger.debug("Entry points not available")

        return loaded

    # -------------------------------------------------------------------------
    # Lookup
    # -------------------------------------------------------------------------

    def get(self, name: str) -> Plugin | None:
        """
        Get a plugin by its name.

        Args:
            name: The plugin name to look up.

        Returns:
            The Plugin instance, or None if not found.
        """
        return self._plugins.get(name)

    def get_by_type(self, plugin_type: PluginType) -> list[Plugin]:
        """
        Get all plugins of a specific type.

        Args:
            plugin_type: The PluginType to filter by.

        Returns:
            List of plugins matching the type (copy of internal list).
        """
        return self._by_type[plugin_type].copy()

    def get_all(self) -> list[Plugin]:
        """
        Get all registered plugins.

        Returns:
            List of all Plugin instances.
        """
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        """
        Check if a plugin is registered.

        Args:
            name: The plugin name to check.

        Returns:
            True if a plugin with this name is registered.
        """
        return name in self._plugins

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def initialize_all(self) -> list[str]:
        """
        Initialize all plugins that haven't been initialized.

        Returns:
            List of plugin names that failed to initialize
        """
        failures: list[str] = []

        for name, plugin in self._plugins.items():
            if plugin.is_initialized:
                continue

            try:
                # Check dependencies
                for dep in plugin.metadata.requires:
                    if not self.has(dep):
                        raise RuntimeError(f"Missing dependency: {dep}")
                    if not self._plugins[dep].is_initialized:
                        raise RuntimeError(f"Dependency not initialized: {dep}")

                # Validate config
                errors = plugin.validate_config()
                if errors:
                    raise RuntimeError(f"Config errors: {errors}")

                # Initialize
                plugin.initialize()
                plugin._initialized = True

                self.logger.info(f"Initialized plugin: {name}")

            except Exception as e:
                self.logger.error(f"Failed to initialize plugin '{name}': {e}")
                failures.append(name)

        return failures

    def shutdown_all(self) -> None:
        """
        Shutdown all registered plugins.

        Plugins are shut down in reverse order of registration to handle
        dependencies correctly. Errors during shutdown are logged but
        don't prevent other plugins from shutting down.
        """
        for name, plugin in reversed(list(self._plugins.items())):
            try:
                plugin.shutdown()
                plugin._initialized = False
            except Exception as e:
                self.logger.error(f"Error shutting down plugin '{name}': {e}")

    # -------------------------------------------------------------------------
    # Info
    # -------------------------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        """
        Get information about all registered plugins.

        Returns:
            List of dictionaries containing plugin metadata:
            - name: Plugin name
            - version: Plugin version
            - type: Plugin type name
            - description: Plugin description
            - initialized: Whether the plugin has been initialized
        """
        return [
            {
                "name": p.metadata.name,
                "version": p.metadata.version,
                "type": p.metadata.plugin_type.name,
                "description": p.metadata.description,
                "initialized": p.is_initialized,
            }
            for p in self._plugins.values()
        ]


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """
    Get the global plugin registry singleton.

    Creates the registry on first call. Subsequent calls return the same instance.

    Returns:
        The global PluginRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
