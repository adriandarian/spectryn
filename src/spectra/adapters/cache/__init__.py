"""
Cache Module - Caching layer for API responses.

Provides caching to reduce API calls and improve performance:
- CacheBackend: Abstract interface for cache storage
- MemoryCache: In-memory LRU cache with TTL support
- FileCache: File-based persistent cache
- RedisCache: Redis-based distributed cache for high-concurrency environments
- CacheManager: High-level cache management

Example:
    >>> from spectra.adapters.cache import MemoryCache, CachedClient
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
    >>> from spectra.adapters.cache import create_redis_cache
    >>>
    >>> cache = create_redis_cache(
    ...     host='localhost',
    ...     port=6379,
    ...     key_prefix='spectra:',
    ...     default_ttl=300,
    ... )
"""

from .backend import CacheBackend, CacheEntry, CacheStats
from .file_cache import FileCache
from .keys import CacheKeyBuilder
from .manager import CacheManager
from .memory import MemoryCache


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
    "CacheBackend",
    "CacheEntry",
    "CacheKeyBuilder",
    "CacheManager",
    "CacheStats",
    "FileCache",
    "MemoryCache",
    # Redis exports (may be None if redis not installed)
    "RedisCache",
    "create_redis_cache",
    "create_redis_cluster_cache",
]


def has_redis_support() -> bool:
    """Check if Redis cache support is available."""
    return _HAS_REDIS
