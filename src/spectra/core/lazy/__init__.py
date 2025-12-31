"""
Lazy Loading - Load story details only when needed.

Provides lazy proxies and collections for deferred loading of
expensive data like comments, attachments, and related issues.
"""

from .cache import (
    CacheEntry,
    CacheStats,
    FieldCache,
)
from .collections import (
    LazyCollection,
    LazyDict,
    LazyList,
    PaginatedCollection,
)
from .proxy import (
    LazyField,
    LazyLoader,
    LazyLoadingConfig,
    LazyProxy,
    LazyStory,
)


__all__ = [
    "CacheEntry",
    "CacheStats",
    "FieldCache",
    "LazyCollection",
    "LazyDict",
    "LazyField",
    "LazyList",
    "LazyLoader",
    "LazyLoadingConfig",
    "LazyProxy",
    "LazyStory",
    "PaginatedCollection",
]
