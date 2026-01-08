"""
Plugin Templates - Scaffolding for new spectra plugins.

This package provides templates for creating different types of plugins:
- Parser plugins (new input formats)
- Tracker plugins (new issue tracker integrations)
- Formatter plugins (new output formats)
- Hook plugins (processing hooks)
- Command plugins (custom CLI commands)
"""

from .scaffold import (
    PluginScaffold,
    PluginTemplateType,
    scaffold_plugin,
)


__all__ = [
    "PluginScaffold",
    "PluginTemplateType",
    "scaffold_plugin",
]
