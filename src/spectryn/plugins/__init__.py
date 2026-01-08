"""
Plugin System - Extensibility for spectra.

Plugins can extend:
- Parsers: Support new input formats (YAML, JSON, etc.)
- Trackers: Support new issue trackers (GitHub, Linear, etc.)
- Formatters: Support new output formats
- Hooks: Add pre/post processing
"""

from .base import Plugin, PluginMetadata, PluginType
from .hooks import Hook, HookContext, HookManager, HookPoint
from .registry import PluginRegistry


__all__ = [
    "Hook",
    "HookContext",
    "HookManager",
    "HookPoint",
    "Plugin",
    "PluginMetadata",
    "PluginRegistry",
    "PluginType",
]
