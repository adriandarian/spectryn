"""
Plugin Marketplace Adapters.

This package provides implementations of the PluginMarketplacePort interface
for discovering, installing, and publishing spectra plugins.
"""

from .github_registry import GitHubPluginRegistry


__all__ = ["GitHubPluginRegistry"]
