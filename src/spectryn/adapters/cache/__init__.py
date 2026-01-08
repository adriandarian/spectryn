"""
Cache Module - Caching layer for API responses.

Provides caching to reduce API calls and improve performance:
- CacheBackend: Abstract interface for cache storage
- MemoryCache: In-memory LRU cache with TTL support
- FileCache: File-based persistent cache
- RedisCache: Redis-based distributed cache for high-concurrency environments
- CacheManager: High-level cache management
- MetadataCache: Smart caching for tracker metadata with aggressive TTLs

Example:
    >>> from spectryn.adapters.cache import MemoryCache, CachedClient
    >>>
    >>> cache = MemoryCache(max_size=1000, default_ttl=300)
    >>> client = CachedClient(jira_client, cache)
    >>>
    >>> # First call hits API
    >>> issue = client.get_issue("PROJ-123")
    >>>
    >>> # Second call uses cache
    >>> issue = client.get_issue("PROJ-123")

For high-concurrency environments, use RedisCache:
    >>> from spectryn.adapters.cache import create_redis_cache
    >>>
    >>> cache = create_redis_cache(
    ...     host='localhost',
    ...     port=6379,
    ...     key_prefix='spectra:',
    ...     default_ttl=300,
    ... )

For smart metadata caching with type-specific TTLs:
    >>> from spectryn.adapters.cache import MetadataCache, MetadataType
    >>>
    >>> cache = MetadataCache(tracker="jira")
    >>>
    >>> # Cache workflow states (1 hour TTL by default)
    >>> states = cache.get_or_fetch_states(
    ...     fetch_fn=lambda: client.get_states(),
    ... )
    >>>
    >>> # Warm up cache at startup
    >>> cache.warm_up({
    ...     MetadataType.STATES: lambda: client.get_states(),
    ...     MetadataType.PRIORITIES: lambda: client.get_priorities(),
    ... })
"""

from .backend import CacheBackend, CacheEntry, CacheStats
from .file_cache import FileCache
from .keys import CacheKeyBuilder
from .manager import CacheManager
from .memory import MemoryCache
from .metadata import (
    DEFAULT_METADATA_TTLS,
    MetadataCache,
    MetadataCacheEntry,
    MetadataCacheStats,
    MetadataType,
    create_metadata_cache,
)


# Redis cache is optional - import only if redis is available
try:
    from .redis_cache import RedisCache, create_redis_cache, create_redis_cluster_cache

    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    RedisCache = None  # type: ignore[misc,assignment]
    create_redis_cache = None  # type: ignore[misc,assignment]
    create_redis_cluster_cache = None  # type: ignore[misc,assignment]

__all__ = [
    "DEFAULT_METADATA_TTLS",
    "CacheBackend",
    "CacheEntry",
    "CacheKeyBuilder",
    "CacheManager",
    "CacheStats",
    "FileCache",
    "MemoryCache",
    "MetadataCache",
    "MetadataCacheEntry",
    "MetadataCacheStats",
    "MetadataType",
    "RedisCache",
    "create_metadata_cache",
    "create_redis_cache",
    "create_redis_cluster_cache",
]


def has_redis_support() -> bool:
    """Check if Redis cache support is available."""
    return _HAS_REDIS
