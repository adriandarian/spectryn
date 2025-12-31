"""
Tests for Redis Cache Backend.

Tests cover:
- Basic CRUD operations (set, get, delete, exists)
- TTL expiration
- Tag-based invalidation
- Statistics tracking
- Factory functions for easy setup
- Error handling
- Cluster support
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.cache import has_redis_support


# Skip all tests if redis is not installed
pytestmark = pytest.mark.skipif(
    not has_redis_support(),
    reason="Redis support not installed. Install with: pip install spectra[redis]",
)


class TestRedisCacheBasics:
    """Basic tests for RedisCache operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = None
        mock.set.return_value = True
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.exists.return_value = False
        mock.scan.return_value = (0, [])
        mock.sadd.return_value = 1
        mock.smembers.return_value = set()
        mock.srem.return_value = 1
        mock.ttl.return_value = -1
        mock.expire.return_value = True
        mock.ping.return_value = True
        mock.info.return_value = {}
        mock.flushdb.return_value = True
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_init(self, mock_redis):
        """Test initialization with custom settings."""
        from spectra.adapters.cache.redis_cache import RedisCache

        cache = RedisCache(
            redis_client=mock_redis,
            key_prefix="custom:",
            default_ttl=600.0,
        )
        assert cache._key_prefix == "custom:"
        assert cache._default_ttl == 600.0

    def test_set_and_get(self, cache, mock_redis):
        """Test basic set and get operations."""
        import json

        # Setup mock for get
        mock_redis.get.return_value = json.dumps({"title": "Test Issue"}).encode()

        # Set a value
        cache.set("issue:123", {"title": "Test Issue"})

        # Verify setex was called with correct arguments
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "test:issue:123"
        assert call_args[0][1] == 300  # default TTL

        # Get the value
        result = cache.get("issue:123")
        assert result == {"title": "Test Issue"}

    def test_get_nonexistent_key(self, cache, mock_redis):
        """Test getting a nonexistent key returns None."""
        mock_redis.get.return_value = None

        result = cache.get("nonexistent")
        assert result is None

    def test_delete(self, cache, mock_redis):
        """Test deleting a key."""
        mock_redis.delete.return_value = 1

        result = cache.delete("issue:123")
        assert result is True
        mock_redis.delete.assert_called()

    def test_delete_nonexistent(self, cache, mock_redis):
        """Test deleting nonexistent key returns False."""
        mock_redis.delete.return_value = 0

        result = cache.delete("nonexistent")
        assert result is False

    def test_exists(self, cache, mock_redis):
        """Test checking if key exists."""
        mock_redis.exists.return_value = 1

        assert cache.exists("issue:123") is True

        mock_redis.exists.return_value = 0
        assert cache.exists("issue:456") is False

    def test_clear(self, cache, mock_redis):
        """Test clearing all cache entries."""
        # Simulate SCAN returning some keys then finishing
        mock_redis.scan.side_effect = [
            (1, [b"test:key1", b"test:key2"]),
            (0, [b"test:key3"]),
        ]
        mock_redis.delete.return_value = 2

        cache.clear()

        assert mock_redis.scan.call_count == 2
        assert mock_redis.delete.call_count == 2


class TestRedisCacheTTL:
    """Tests for TTL functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = None
        mock.set.return_value = True
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.ttl.return_value = -1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_set_with_default_ttl(self, cache, mock_redis):
        """Test that default TTL is applied."""
        cache.set("key1", "value1")

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 300  # default TTL

    def test_set_with_custom_ttl(self, cache, mock_redis):
        """Test setting custom TTL per entry."""
        cache.set("key1", "value1", ttl=600)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 600  # custom TTL

    def test_set_without_ttl(self, mock_redis):
        """Test setting value with no TTL (persistent)."""
        from spectra.adapters.cache.redis_cache import RedisCache

        cache = RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=None,  # No default TTL
        )

        cache.set("key1", "value1")

        # Should use SET instead of SETEX when no TTL
        mock_redis.set.assert_called_once()
        mock_redis.setex.assert_not_called()


class TestRedisCacheTags:
    """Tests for tag-based invalidation."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = None
        mock.set.return_value = True
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.sadd.return_value = 1
        mock.smembers.return_value = set()
        mock.srem.return_value = 1
        mock.ttl.return_value = -1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_set_with_tags(self, cache, mock_redis):
        """Test setting entries with tags."""
        cache.set("key1", "value1", tags={"project:ABC", "type:issue"})

        # Should add key to tag sets
        assert mock_redis.sadd.call_count == 2

    def test_invalidate_by_tag(self, cache, mock_redis):
        """Test invalidating entries by tag."""
        mock_redis.smembers.return_value = {b"key1", b"key2"}

        cache.invalidate_by_tag("project:ABC")

        # Should delete all keys with the tag
        assert mock_redis.delete.call_count >= 2  # Values + tag set


class TestRedisCacheStats:
    """Tests for statistics tracking."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = None
        mock.setex.return_value = True
        mock.delete.return_value = 1
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_hit_tracking(self, cache, mock_redis):
        """Test hit count tracking."""
        import json

        mock_redis.get.return_value = json.dumps("value").encode()

        cache.get("key1")
        cache.get("key2")
        cache.get("key3")

        stats = cache.get_stats()
        assert stats.hits == 3

    def test_miss_tracking(self, cache, mock_redis):
        """Test miss count tracking."""
        mock_redis.get.return_value = None

        cache.get("nonexistent1")
        cache.get("nonexistent2")

        stats = cache.get_stats()
        assert stats.misses == 2

    def test_set_tracking(self, cache, mock_redis):
        """Test set count tracking."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        stats = cache.get_stats()
        assert stats.sets == 2

    def test_delete_tracking(self, cache, mock_redis):
        """Test delete count tracking."""
        mock_redis.delete.return_value = 1

        cache.delete("key1")

        stats = cache.get_stats()
        assert stats.deletes == 1


class TestRedisCacheSize:
    """Tests for size calculation."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_size_empty(self, cache, mock_redis):
        """Test size of empty cache."""
        mock_redis.scan.return_value = (0, [])

        assert cache.size == 0

    def test_size_with_entries(self, cache, mock_redis):
        """Test size with entries (excluding tags and metadata)."""
        mock_redis.scan.side_effect = [
            (1, [b"test:key1", b"test:key2", b"test:tags:project"]),
            (0, [b"test:key3", b"test:meta:key1"]),
        ]

        # Should count only data keys, not tags or metadata
        size = cache.size
        assert size == 3  # key1, key2, key3


class TestRedisCacheHealthCheck:
    """Tests for health check functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.ping.return_value = True
        mock.info.return_value = {
            "connected_clients": 5,
            "used_memory_human": "10.5M",
            "redis_version": "7.0.0",
        }
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_ping_healthy(self, cache, mock_redis):
        """Test ping returns True when healthy."""
        assert cache.ping() is True

    def test_ping_unhealthy(self, cache, mock_redis):
        """Test ping returns False when unhealthy."""
        mock_redis.ping.side_effect = Exception("Connection refused")

        assert cache.ping() is False

    def test_get_info(self, cache, mock_redis):
        """Test getting Redis info."""
        info = cache.get_info()

        assert info["connected_clients"] == 5
        assert info["used_memory_human"] == "10.5M"
        assert info["redis_version"] == "7.0.0"


class TestRedisCacheErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return MagicMock()

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_get_handles_redis_error(self, cache, mock_redis):
        """Test that get handles Redis errors gracefully."""
        mock_redis.get.side_effect = Exception("Connection refused")

        result = cache.get("key1")
        assert result is None

    def test_delete_handles_redis_error(self, cache, mock_redis):
        """Test that delete handles Redis errors gracefully."""
        mock_redis.delete.side_effect = Exception("Connection refused")

        result = cache.delete("key1")
        assert result is False

    def test_exists_handles_redis_error(self, cache, mock_redis):
        """Test that exists handles Redis errors gracefully."""
        mock_redis.exists.side_effect = Exception("Connection refused")

        result = cache.exists("key1")
        assert result is False

    def test_set_propagates_error(self, cache, mock_redis):
        """Test that set propagates Redis errors."""
        mock_redis.setex.side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            cache.set("key1", "value1")

    def test_deserialize_handles_invalid_json(self, cache, mock_redis):
        """Test that invalid JSON is handled gracefully."""
        mock_redis.get.return_value = b"not valid json {"

        result = cache.get("key1")
        # Should return None and log warning, not raise
        assert result is None


class TestCreateRedisCache:
    """Tests for the create_redis_cache factory function."""

    def test_create_redis_cache(self):
        """Test factory function creates cache correctly."""
        from spectra.adapters.cache.redis_cache import create_redis_cache

        with (
            patch("redis.Redis") as mock_redis_class,
            patch("redis.ConnectionPool") as mock_pool_class,
        ):
            mock_pool = MagicMock()
            mock_pool_class.return_value = mock_pool
            mock_redis_class.return_value = MagicMock()

            cache = create_redis_cache(
                host="localhost",
                port=6379,
                db=0,
                password="secret",
                key_prefix="app:",
                default_ttl=600,
            )

            # Verify pool was created with correct args
            mock_pool_class.assert_called_once()
            pool_kwargs = mock_pool_class.call_args[1]
            assert pool_kwargs["host"] == "localhost"
            assert pool_kwargs["port"] == 6379
            assert pool_kwargs["db"] == 0
            assert pool_kwargs["password"] == "secret"

            # Verify cache was created
            assert cache._key_prefix == "app:"
            assert cache._default_ttl == 600

    def test_create_redis_cache_with_ssl(self):
        """Test factory function creates cache with SSL correctly."""
        from spectra.adapters.cache.redis_cache import create_redis_cache

        with (
            patch("redis.Redis") as mock_redis_class,
            patch("redis.ConnectionPool") as mock_pool_class,
        ):
            mock_pool = MagicMock()
            mock_pool_class.return_value = mock_pool
            mock_redis_class.return_value = MagicMock()

            cache = create_redis_cache(
                host="redis.example.com",
                port=6380,
                ssl=True,
                key_prefix="ssl:",
            )

            # Verify SSL was passed
            pool_kwargs = mock_pool_class.call_args[1]
            assert pool_kwargs["ssl"] is True

            assert cache._key_prefix == "ssl:"


class TestCreateRedisClusterCache:
    """Tests for the create_redis_cluster_cache factory function."""

    def test_create_redis_cluster_cache(self):
        """Test factory function creates cluster cache correctly."""
        from spectra.adapters.cache.redis_cache import create_redis_cluster_cache

        with (
            patch("redis.cluster.RedisCluster") as mock_cluster_class,
            patch("redis.cluster.ClusterNode") as mock_node_class,
        ):
            mock_cluster = MagicMock()
            mock_cluster_class.return_value = mock_cluster

            cache = create_redis_cluster_cache(
                startup_nodes=[
                    {"host": "node1.redis.example.com", "port": 6379},
                    {"host": "node2.redis.example.com", "port": 6379},
                ],
                password="secret",
                key_prefix="cluster:",
            )

            # Verify cluster nodes were created
            assert mock_node_class.call_count == 2

            # Verify cluster was created
            mock_cluster_class.assert_called_once()

            # Verify cache was created
            assert cache._key_prefix == "cluster:"


class TestRedisCacheIntegration:
    """Integration-style tests using a mock that behaves more like real Redis."""

    @pytest.fixture
    def redis_like_mock(self):
        """Create a mock that behaves more like real Redis."""
        storage = {}
        ttls = {}
        tag_sets = {}

        mock = MagicMock()

        def mock_get(key):
            if key not in storage:
                return None
            # Check TTL
            if key in ttls and ttls[key] < time.time():
                del storage[key]
                del ttls[key]
                return None
            return storage[key]

        def mock_set(key, value):
            storage[key] = value
            return True

        def mock_setex(key, ttl, value):
            storage[key] = value
            ttls[key] = time.time() + ttl
            return True

        def mock_delete(*keys):
            count = 0
            for key in keys:
                if key in storage:
                    del storage[key]
                    count += 1
                ttls.pop(key, None)
            return count

        def mock_exists(key):
            if key not in storage:
                return 0
            if key in ttls and ttls[key] < time.time():
                del storage[key]
                del ttls[key]
                return 0
            return 1

        def mock_sadd(key, value):
            if key not in tag_sets:
                tag_sets[key] = set()
            tag_sets[key].add(value)
            return 1

        def mock_smembers(key):
            return tag_sets.get(key, set())

        def mock_srem(key, value):
            if key in tag_sets and value in tag_sets[key]:
                tag_sets[key].remove(value)
                return 1
            return 0

        def mock_scan(cursor, match=None, count=1000):
            # Simple implementation - return all matching keys
            pattern = match.replace("*", "") if match else ""
            matching = [
                k.encode() if isinstance(k, str) else k
                for k in storage
                if pattern in (k if isinstance(k, str) else k.decode())
            ]
            return (0, matching)

        def mock_ttl(key):
            if key not in ttls:
                return -1
            remaining = ttls[key] - time.time()
            return int(remaining) if remaining > 0 else -2

        def mock_expire(key, ttl):
            if key in storage:
                ttls[key] = time.time() + ttl
                return True
            return False

        mock.get.side_effect = mock_get
        mock.set.side_effect = mock_set
        mock.setex.side_effect = mock_setex
        mock.delete.side_effect = mock_delete
        mock.exists.side_effect = mock_exists
        mock.sadd.side_effect = mock_sadd
        mock.smembers.side_effect = mock_smembers
        mock.srem.side_effect = mock_srem
        mock.scan.side_effect = mock_scan
        mock.ttl.side_effect = mock_ttl
        mock.expire.side_effect = mock_expire
        mock.ping.return_value = True
        mock.info.return_value = {}
        mock.flushdb.return_value = True

        return mock

    @pytest.fixture
    def cache(self, redis_like_mock):
        """Create a RedisCache with redis-like mock."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=redis_like_mock,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_full_crud_cycle(self, cache):
        """Test complete CRUD cycle."""
        # Create
        cache.set("issue:123", {"title": "Test", "status": "open"})

        # Read
        result = cache.get("issue:123")
        assert result == {"title": "Test", "status": "open"}

        # Update (by setting again)
        cache.set("issue:123", {"title": "Updated", "status": "closed"})
        result = cache.get("issue:123")
        assert result == {"title": "Updated", "status": "closed"}

        # Delete
        assert cache.delete("issue:123") is True
        assert cache.get("issue:123") is None

    def test_cache_miss_then_hit(self, cache):
        """Test cache miss followed by hit."""
        # Miss
        assert cache.get("new_key") is None
        stats = cache.get_stats()
        assert stats.misses == 1
        assert stats.hits == 0

        # Set and hit
        cache.set("new_key", "value")
        result = cache.get("new_key")
        assert result == "value"

        stats = cache.get_stats()
        assert stats.hits == 1

    def test_multiple_entries(self, cache):
        """Test handling multiple entries."""
        # Set multiple entries
        for i in range(10):
            cache.set(f"key:{i}", {"index": i})

        # Verify all can be retrieved
        for i in range(10):
            result = cache.get(f"key:{i}")
            assert result == {"index": i}

        # Verify stats
        stats = cache.get_stats()
        assert stats.sets == 10
        assert stats.hits == 10


class TestRedisCacheBackendInterface:
    """Tests verifying RedisCache implements CacheBackend correctly."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = None
        mock.setex.return_value = True
        mock.delete.return_value = 1
        mock.exists.return_value = 0
        mock.scan.return_value = (0, [])
        mock.smembers.return_value = set()
        mock.ttl.return_value = -1
        mock.expire.return_value = True
        return mock

    @pytest.fixture
    def cache(self, mock_redis):
        """Create a RedisCache with mocked client."""
        from spectra.adapters.cache.redis_cache import RedisCache

        return RedisCache(
            redis_client=mock_redis,
            key_prefix="test:",
            default_ttl=300.0,
        )

    def test_is_cache_backend(self, cache):
        """Test that RedisCache is a CacheBackend."""
        from spectra.adapters.cache import CacheBackend

        assert isinstance(cache, CacheBackend)

    def test_has_all_required_methods(self, cache):
        """Test that all required methods exist."""
        assert hasattr(cache, "get")
        assert hasattr(cache, "set")
        assert hasattr(cache, "delete")
        assert hasattr(cache, "exists")
        assert hasattr(cache, "clear")
        assert hasattr(cache, "invalidate_by_tag")
        assert hasattr(cache, "get_stats")
        assert hasattr(cache, "size")

    def test_get_or_set_inherited(self, cache, mock_redis):
        """Test that get_or_set from base class works."""
        import json

        mock_redis.get.return_value = None
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return "computed_value"

        # First call - should compute
        result = cache.get_or_set("compute_key", factory)

        # Factory should have been called
        assert len(factory_calls) == 1

        # Now mock a cache hit
        mock_redis.get.return_value = json.dumps("computed_value").encode()

        # Second call - should use cache
        result = cache.get_or_set("compute_key", factory)
        assert result == "computed_value"

        # Factory should NOT have been called again
        assert len(factory_calls) == 1


class TestHasRedisSupport:
    """Tests for the has_redis_support function."""

    def test_has_redis_support_returns_bool(self):
        """Test that has_redis_support returns a boolean."""
        from spectra.adapters.cache import has_redis_support

        result = has_redis_support()
        assert isinstance(result, bool)
