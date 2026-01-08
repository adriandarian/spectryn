"""
Confluence Adapter - Sync epics and stories to Confluence pages.
"""

from .adapter import ConfluenceAdapter
from .client import ConfluenceClient
from .plugin import ConfluencePlugin, create_plugin


__all__ = [
    "ConfluenceAdapter",
    "ConfluenceClient",
    "ConfluencePlugin",
    "create_plugin",
]
