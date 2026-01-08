"""Tests for file-based cache backend."""

import json
import time
from pathlib import Path

import pytest

from spectryn.adapters.cache.file_cache import FileCache


class TestFileCacheBasics:
    """Basic tests for FileCache."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        """Create a temporary cache directory."""
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        """Create a FileCache instance."""
        return FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

    def test_init_creates_directories(self, cache_dir: Path) -> None:
        """Test that init creates cache directories."""
        FileCache(cache_dir=cache_dir, cleanup_on_start=False)

        assert (cache_dir / "entries").exists()
        assert (cache_dir / "tags").exists()

    def test_set_and_get(self, cache: FileCache) -> None:
        """Test basic set and get operations."""
        cache.set("test_key", {"value": "test_data"})
        result = cache.get("test_key")

        assert result == {"value": "test_data"}

    def test_get_nonexistent_key(self, cache: FileCache) -> None:
        """Test getting a nonexistent key returns None."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_delete(self, cache: FileCache) -> None:
        """Test deleting a cached value."""
        cache.set("to_delete", "value")
        assert cache.get("to_delete") == "value"

        cache.delete("to_delete")
        assert cache.get("to_delete") is None

    def test_delete_nonexistent_key(self, cache: FileCache) -> None:
        """Test deleting nonexistent key doesn't raise."""
        # Should not raise
        cache.delete("nonexistent")

    def test_clear(self, cache: FileCache) -> None:
        """Test clearing all cached values."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_exists(self, cache: FileCache) -> None:
        """Test checking if key exists."""
        cache.set("exists", "value")

        assert cache.exists("exists") is True
        assert cache.exists("not_exists") is False


class TestFileCacheTTL:
    """Tests for TTL functionality."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    def test_expired_entry_returns_none(self, cache_dir: Path) -> None:
        """Test that expired entries return None."""
        cache = FileCache(cache_dir=cache_dir, default_ttl=0.01, cleanup_on_start=False)
        cache.set("short_lived", "value")

        # Wait for expiration
        time.sleep(0.05)

        result = cache.get("short_lived")
        assert result is None

    def test_custom_ttl_per_entry(self, cache_dir: Path) -> None:
        """Test setting custom TTL per entry."""
        cache = FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

        # Set with very short TTL
        cache.set("short", "value", ttl=0.01)
        cache.set("long", "value", ttl=60.0)

        time.sleep(0.05)

        # Short TTL should be expired
        assert cache.get("short") is None
        # Long TTL should still exist
        assert cache.get("long") == "value"

    def test_none_ttl_means_no_expiration(self, cache_dir: Path) -> None:
        """Test that None TTL means no expiration."""
        cache = FileCache(cache_dir=cache_dir, default_ttl=None, cleanup_on_start=False)
        cache.set("permanent", "value")

        result = cache.get("permanent")
        assert result == "value"


class TestFileCacheTags:
    """Tests for tag-based invalidation."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        return FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

    def test_set_with_tags(self, cache: FileCache) -> None:
        """Test setting entries with tags."""
        cache.set("key1", "value1", tags={"tag_a", "tag_b"})
        cache.set("key2", "value2", tags={"tag_b", "tag_c"})

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"

    def test_invalidate_by_tag(self, cache: FileCache) -> None:
        """Test invalidating entries by tag."""
        cache.set("key1", "value1", tags={"user:123"})
        cache.set("key2", "value2", tags={"user:123", "project:abc"})
        cache.set("key3", "value3", tags={"project:abc"})

        # Invalidate user:123 tag
        cache.invalidate_by_tag("user:123")

        # key1 and key2 should be gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        # key3 should remain
        assert cache.get("key3") == "value3"


class TestFileCacheStats:
    """Tests for cache statistics."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        return FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

    def test_hit_count(self, cache: FileCache) -> None:
        """Test hit count tracking."""
        cache.set("key", "value")

        cache.get("key")
        cache.get("key")
        cache.get("key")

        stats = cache.get_stats()
        assert stats.hits == 3

    def test_miss_count(self, cache: FileCache) -> None:
        """Test miss count tracking."""
        cache.get("nonexistent1")
        cache.get("nonexistent2")

        stats = cache.get_stats()
        assert stats.misses == 2

    def test_hit_rate(self, cache: FileCache) -> None:
        """Test hit rate calculation."""
        cache.set("key", "value")

        cache.get("key")  # hit
        cache.get("key")  # hit
        cache.get("miss")  # miss

        stats = cache.get_stats()
        # 2 hits, 1 miss = 66.67% hit rate
        assert 0.66 < stats.hit_rate < 0.67


class TestFileCacheComplexTypes:
    """Tests for complex data types."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        return FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

    def test_cache_dict(self, cache: FileCache) -> None:
        """Test caching dictionaries."""
        data = {"name": "test", "value": 42, "nested": {"key": "val"}}
        cache.set("dict_key", data)

        result = cache.get("dict_key")
        assert result == data

    def test_cache_list(self, cache: FileCache) -> None:
        """Test caching lists."""
        data = [1, 2, 3, {"nested": True}]
        cache.set("list_key", data)

        result = cache.get("list_key")
        assert result == data

    def test_cache_string(self, cache: FileCache) -> None:
        """Test caching strings."""
        cache.set("string_key", "hello world")
        assert cache.get("string_key") == "hello world"

    def test_cache_number(self, cache: FileCache) -> None:
        """Test caching numbers."""
        cache.set("int_key", 42)
        cache.set("float_key", 3.14)

        assert cache.get("int_key") == 42
        assert cache.get("float_key") == 3.14

    def test_cache_boolean(self, cache: FileCache) -> None:
        """Test caching booleans."""
        cache.set("true_key", True)
        cache.set("false_key", False)

        assert cache.get("true_key") is True
        assert cache.get("false_key") is False

    def test_cache_none(self, cache: FileCache) -> None:
        """Test caching None value."""
        cache.set("none_key", None)
        # None is a valid cached value vs missing key
        assert cache.exists("none_key") is True


class TestFileCacheKeyTransformation:
    """Tests for key path transformation."""

    @pytest.fixture
    def cache_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "cache"

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        return FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

    def test_key_with_slashes(self, cache: FileCache) -> None:
        """Test keys with slashes are handled."""
        cache.set("path/to/resource", "value")
        assert cache.get("path/to/resource") == "value"

    def test_key_with_colons(self, cache: FileCache) -> None:
        """Test keys with colons are handled."""
        cache.set("issue:PROJ-123", "value")
        assert cache.get("issue:PROJ-123") == "value"

    def test_key_with_special_chars(self, cache: FileCache) -> None:
        """Test keys with various special characters."""
        cache.set("key:with/mixed_chars", "value")
        assert cache.get("key:with/mixed_chars") == "value"


class TestFileCachePersistence:
    """Tests for persistence across instances."""

    def test_data_persists_across_instances(self, tmp_path: Path) -> None:
        """Test that cached data survives cache recreation."""
        cache_dir = tmp_path / "cache"

        # Create first cache and set data
        cache1 = FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)
        cache1.set("persistent_key", {"data": "persisted"})

        # Create new cache instance pointing to same directory
        cache2 = FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

        # Data should still be there
        result = cache2.get("persistent_key")
        assert result == {"data": "persisted"}


class TestFileCacheCleanup:
    """Tests for cleanup functionality."""

    def test_cleanup_on_start(self, tmp_path: Path) -> None:
        """Test that expired entries are cleaned on start."""
        cache_dir = tmp_path / "cache"

        # Create cache with short TTL
        cache1 = FileCache(cache_dir=cache_dir, default_ttl=0.01, cleanup_on_start=False)
        cache1.set("short_lived", "value")

        # Wait for expiration
        time.sleep(0.05)

        # Create new cache with cleanup_on_start=True
        cache2 = FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=True)

        # Expired entry should be cleaned up
        assert cache2.get("short_lived") is None

    def test_size_property(self, tmp_path: Path) -> None:
        """Test size returns number of entries."""
        cache_dir = tmp_path / "cache"
        cache = FileCache(cache_dir=cache_dir, default_ttl=60.0, cleanup_on_start=False)

        assert cache.size == 0

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        assert cache.size == 2
