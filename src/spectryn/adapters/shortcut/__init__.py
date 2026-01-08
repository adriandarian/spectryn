"""
Shortcut Adapter - Integration with Shortcut (formerly Clubhouse).

This module provides the Shortcut implementation of the IssueTrackerPort,
enabling syncing markdown documents to Shortcut stories.
"""

from .adapter import ShortcutAdapter
from .client import ShortcutApiClient
from .plugin import ShortcutTrackerPlugin


__all__ = [
    "ShortcutAdapter",
    "ShortcutApiClient",
    "ShortcutTrackerPlugin",
]
