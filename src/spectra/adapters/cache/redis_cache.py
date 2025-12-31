"""
Redis Cache - Redis-based distributed cache for high-concurrency environments.

Provides a distributed cache backend using Redis for scenarios requiring:
- Shared cache across multiple processes/workers
- High-concurrency environments
- Persistent cache that survives process restarts
- Horizontal scaling with Redis Cluster support
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from .backend import CacheBackend, CacheStats


if TYPE_CHECKING:
    from redis import Redis


class RedisCache(CacheBackend):
    """
    Redis-based distributed cache backend.

    Features:
    - Distributed caching across multiple processes/workers
    - High-concurrency support with atomic operations
    - TTL support via Redis EXPIRE
    - Tag-based group invalidation using Redis Sets
    - Configurable key prefix for namespacing
    - Connection pooling via Redis client
    - Serialization using JSON (configurable)

    Requires the `redis` package: pip install redis
    Or install spectra with redis support: pip install spectra[redis]

    Example:
        >>> from redis import Redis
        >>> from spectra.adapters.cache import RedisCache
        >>>
        >>> # Connect to local Redis
        >>> redis_client = Redis(host='localhost', port=6379, db=0)
        >>> cache = RedisCache(redis_client, key_prefix='spectra:')
        >>>
        >>> # Use like any other cache backend
        >>> cache.set("issue:PROJ-123", {"title": "Bug fix"}, ttl=300)
        >>> issue = cache.get("issue:PROJ-123")
        >>>
        >>> # For high-concurrency environments with Redis Cluster
        >>> from redis.cluster import RedisCluster
        >>> cluster = RedisCluster(host='redis-cluster', port=6379)
        >>> cache = RedisCache(cluster, key_prefix='spectra:')
    """

    def __init__(
        self,
        redis_client: Any,  # RedisLike protocol - accepts Redis, RedisCluster, etc.
        key_prefix: str = "spectra:cache:",
        default_ttl: float | None = 300.0,
        stats_key: str | None = None,
    ):
        """
        Initialize the Redis cache.

        Args:
            redis_client: Redis client instance (from redis-py package)
            key_prefix: Prefix for all cache keys (for namespacing)
            default_ttl: Default TTL in seconds (None = no expiry)
            stats_key: Redis key for storing stats (None = in-memory stats only)
        """
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._stats_key = stats_key
        self._stats = CacheStats()
        self._logger = logging.getLogger("RedisCache")

    def _make_key(self, key: str) -> str:
        """Create the full Redis key with prefix."""
        return f"{self._key_prefix}{key}"

    def _make_tag_key(self, tag: str) -> str:
        """Create the Redis key for a tag set."""
        return f"{self._key_prefix}tags:{tag}"

    def _make_metadata_key(self, key: str) -> str:
        """Create the Redis key for entry metadata."""
        return f"{self._key_prefix}meta:{key}"

    def _serialize(self, value: Any) -> str:
        """Serialize a value to JSON string."""
        return json.dumps(value, default=str)

    def _deserialize(self, data: str | bytes | None) -> Any | None:
        """Deserialize a JSON string back to a value."""
        if data is None:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            self._logger.warning(f"Failed to deserialize cache value: {data[:100]}...")
            return None

    def get(self, key: str) -> Any | None:
        """
        Get a value from the cache.

        Returns None if not found or expired (Redis handles TTL automatically).
        """
        redis_key = self._make_key(key)

        try:
            data = self._redis.get(redis_key)
            if data is None:
                self._stats.record_miss()
                return None

            self._stats.record_hit()
            return self._deserialize(data)

        except Exception as e:
            self._logger.error(f"Redis GET error for key '{key}': {e}")
            self._stats.record_miss()
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        tags: set[str] | None = None,
    ) -> None:
        """
        Set a value in the cache.

        Uses Redis SETEX for TTL support. Tags are stored in Redis Sets
        for group invalidation.
        """
        redis_key = self._make_key(key)

        # Determine TTL
        effective_ttl = ttl if ttl is not None else self._default_ttl

        try:
            # Serialize the value
            serialized = self._serialize(value)

            # Set the value with optional TTL
            if effective_ttl is not None:
                # Redis expects integer seconds for SETEX
                ttl_seconds = int(effective_ttl)
                if ttl_seconds > 0:
                    self._redis.setex(redis_key, ttl_seconds, serialized)
                else:
                    # TTL of 0 or less means immediate expiry - just don't set
                    return
            else:
                # No TTL - value persists until explicitly deleted
                self._redis.set(redis_key, serialized)

            # Store tags for group invalidation
            if tags:
                metadata = {"tags": list(tags), "created_at": time.time()}
                meta_key = self._make_metadata_key(key)

                if effective_ttl is not None:
                    self._redis.setex(meta_key, int(effective_ttl), self._serialize(metadata))
                else:
                    self._redis.set(meta_key, self._serialize(metadata))

                # Add key to each tag's set
                for tag in tags:
                    tag_key = self._make_tag_key(tag)
                    self._redis.sadd(tag_key, key)

                    # Set TTL on tag set if applicable
                    if effective_ttl is not None:
                        # Use max TTL for the tag set (extend if needed)
                        current_ttl = self._redis.ttl(tag_key)
                        if current_ttl < effective_ttl:
                            self._redis.expire(tag_key, int(effective_ttl))

            self._stats.record_set()

        except Exception as e:
            self._logger.error(f"Redis SET error for key '{key}': {e}")
            raise

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        redis_key = self._make_key(key)
        meta_key = self._make_metadata_key(key)

        try:
            # Get tags to clean up tag sets
            meta_data = self._redis.get(meta_key)
            if meta_data:
                metadata = self._deserialize(meta_data)
                if metadata and "tags" in metadata:
                    for tag in metadata["tags"]:
                        tag_key = self._make_tag_key(tag)
                        self._redis.srem(tag_key, key)

            # Delete the value and metadata
            deleted = self._redis.delete(redis_key, meta_key)

            if deleted > 0:
                self._stats.record_delete()
                return True
            return False

        except Exception as e:
            self._logger.error(f"Redis DELETE error for key '{key}': {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists (Redis handles TTL automatically)."""
        redis_key = self._make_key(key)

        try:
            return bool(self._redis.exists(redis_key))
        except Exception as e:
            self._logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False

    def clear(self) -> int:
        """
        Clear all entries with the cache prefix.

        Uses SCAN to find keys (memory-efficient for large datasets).
        """
        pattern = f"{self._key_prefix}*"
        count = 0

        try:
            # Use SCAN for memory-efficient iteration
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=1000)
                if keys:
                    count += self._redis.delete(*keys)
                if cursor == 0:
                    break

            return count

        except Exception as e:
            self._logger.error(f"Redis CLEAR error: {e}")
            return count

    def invalidate_by_tag(self, tag: str) -> int:
        """
        Invalidate all entries with a given tag.

        Uses Redis Sets to track which keys have which tags.
        """
        tag_key = self._make_tag_key(tag)
        count = 0

        try:
            # Get all keys with this tag
            keys = self._redis.smembers(tag_key)

            if keys:
                # Delete all the cached values
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    redis_key = self._make_key(key_str)
                    meta_key = self._make_metadata_key(key_str)

                    if self._redis.delete(redis_key, meta_key):
                        count += 1

            # Delete the tag set itself
            self._redis.delete(tag_key)

            return count

        except Exception as e:
            self._logger.error(f"Redis INVALIDATE_BY_TAG error for tag '{tag}': {e}")
            return count

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    @property
    def size(self) -> int:
        """
        Get the approximate number of entries in the cache.

        Uses SCAN to count keys with the cache prefix.
        Note: This can be slow for very large caches.
        """
        pattern = f"{self._key_prefix}*"
        # Exclude tag and metadata keys
        exclude_patterns = [f"{self._key_prefix}tags:", f"{self._key_prefix}meta:"]

        count = 0
        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=1000)
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    if not any(key_str.startswith(p) for p in exclude_patterns):
                        count += 1
                if cursor == 0:
                    break

            return count

        except Exception as e:
            self._logger.error(f"Redis SIZE error: {e}")
            return 0

    def ping(self) -> bool:
        """
        Check if the Redis connection is healthy.

        Useful for health checks.
        """
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def get_info(self) -> dict[str, Any]:
        """
        Get Redis server information.

        Returns connection and memory info for monitoring.
        """
        try:
            info = self._redis.info()
            return {
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "total_connections_received": info.get("total_connections_received"),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "redis_version": info.get("redis_version"),
            }
        except Exception as e:
            self._logger.error(f"Redis INFO error: {e}")
            return {}

    def flush_db(self) -> bool:
        """
        Flush the entire Redis database.

        WARNING: This clears ALL data in the current Redis database,
        not just cache entries. Use with caution!
        """
        try:
            self._redis.flushdb()
            return True
        except Exception as e:
            self._logger.error(f"Redis FLUSHDB error: {e}")
            return False


def create_redis_cache(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: str | None = None,
    key_prefix: str = "spectra:cache:",
    default_ttl: float | None = 300.0,
    socket_timeout: float = 5.0,
    socket_connect_timeout: float = 5.0,
    max_connections: int = 10,
    ssl: bool = False,
    **redis_kwargs: Any,
) -> RedisCache:
    """
    Factory function to create a RedisCache with common options.

    This is a convenience function that creates the Redis client
    and RedisCache instance in one call.

    Args:
        host: Redis host
        port: Redis port
        db: Redis database number
        password: Redis password (optional)
        key_prefix: Prefix for cache keys
        default_ttl: Default TTL in seconds
        socket_timeout: Socket timeout
        socket_connect_timeout: Connection timeout
        max_connections: Max connections in pool
        ssl: Use SSL/TLS connection
        **redis_kwargs: Additional arguments for Redis client

    Returns:
        Configured RedisCache instance

    Example:
        >>> cache = create_redis_cache(
        ...     host='redis.example.com',
        ...     port=6379,
        ...     password='secret',
        ...     key_prefix='myapp:',
        ...     default_ttl=600,
        ... )
    """
    try:
        from redis import ConnectionPool, Redis
    except ImportError as e:
        raise ImportError(
            "Redis support requires the 'redis' package. "
            "Install it with: pip install redis "
            "Or install spectra with redis support: pip install spectra[redis]"
        ) from e

    # Build connection pool kwargs
    pool_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "socket_timeout": socket_timeout,
        "socket_connect_timeout": socket_connect_timeout,
        "max_connections": max_connections,
        "decode_responses": False,  # We handle encoding ourselves
    }
    if ssl:
        pool_kwargs["ssl"] = True
    pool_kwargs.update(redis_kwargs)

    # Create connection pool for efficient connection reuse
    pool = ConnectionPool(**pool_kwargs)

    client: Redis[bytes] = Redis(connection_pool=pool)

    return RedisCache(
        redis_client=client,
        key_prefix=key_prefix,
        default_ttl=default_ttl,
    )


def create_redis_cluster_cache(
    startup_nodes: list[dict[str, Any]],
    password: str | None = None,
    key_prefix: str = "spectra:cache:",
    default_ttl: float | None = 300.0,
    **cluster_kwargs: Any,
) -> RedisCache:
    """
    Factory function to create a RedisCache with Redis Cluster support.

    For high-availability deployments using Redis Cluster.

    Args:
        startup_nodes: List of cluster node dicts with 'host' and 'port'
        password: Redis password (optional)
        key_prefix: Prefix for cache keys
        default_ttl: Default TTL in seconds
        **cluster_kwargs: Additional arguments for RedisCluster

    Returns:
        Configured RedisCache instance

    Example:
        >>> cache = create_redis_cluster_cache(
        ...     startup_nodes=[
        ...         {'host': 'node1.redis.example.com', 'port': 6379},
        ...         {'host': 'node2.redis.example.com', 'port': 6379},
        ...         {'host': 'node3.redis.example.com', 'port': 6379},
        ...     ],
        ...     password='secret',
        ...     key_prefix='spectra:',
        ... )
    """
    try:
        from redis.cluster import ClusterNode, RedisCluster
    except ImportError as e:
        raise ImportError(
            "Redis Cluster support requires the 'redis' package with cluster support. "
            "Install it with: pip install redis "
            "Or install spectra with redis support: pip install spectra[redis]"
        ) from e

    nodes = [ClusterNode(node["host"], node["port"]) for node in startup_nodes]

    cluster: Any = RedisCluster(
        startup_nodes=nodes,
        password=password,
        decode_responses=False,
        **cluster_kwargs,
    )

    return RedisCache(
        redis_client=cluster,
        key_prefix=key_prefix,
        default_ttl=default_ttl,
    )
