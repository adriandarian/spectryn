"""
Tests for the caching layer.

Tests cover:
- MemoryCache: LRU eviction, TTL expiration, tag-based invalidation
- FileCache: Persistence, cleanup, corruption handling
- CacheManager: High-level caching operations
- CacheKeyBuilder: Key generation
- CachedJiraApiClient: Integration with Jira client
"""

import tempfile
import time
from pathlib import Path

import pytest

from spectryn.adapters.cache import (
    CacheEntry,
    CacheKeyBuilder,
    CacheManager,
    CacheStats,
    FileCache,
    MemoryCache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_entry_not_expired_without_ttl(self):
        """Entry without expiration never expires."""
        entry = CacheEntry(value="test", expires_at=None)
        assert not entry.is_expired

    def test_entry_expired_after_ttl(self):
        """Entry expires after TTL passes."""
        entry = CacheEntry(
            value="test",
            expires_at=time.time() - 1,  # Expired 1 second ago
        )
        assert entry.is_expired

    def test_entry_not_expired_within_ttl(self):
        """Entry is not expired within TTL."""
        entry = CacheEntry(
            value="test",
            expires_at=time.time() + 100,  # Expires in 100 seconds
        )
        assert not entry.is_expired

    def test_ttl_remaining(self):
        """Test TTL remaining calculation."""
        entry = CacheEntry(
            value="test",
            expires_at=time.time() + 50,
        )
        remaining = entry.ttl_remaining
        assert remaining is not None
        assert 49 < remaining <= 50

    def test_age_calculation(self):
        """Test age calculation."""
        entry = CacheEntry(
            value="test",
            created_at=time.time() - 10,
        )
        assert 9.9 < entry.age < 10.1

    def test_hit_count_tracking(self):
        """Test hit count tracking."""
        entry = CacheEntry(value="test")
        assert entry.hit_count == 0

        entry.record_hit()
        assert entry.hit_count == 1

        entry.record_hit()
        entry.record_hit()
        assert entry.hit_count == 3


class TestCacheStats:
    """Tests for CacheStats."""

    def test_initial_stats_are_zero(self):
        """New stats should be all zeros."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats()
        stats.hits = 75
        stats.misses = 25
        assert stats.hit_rate == 0.75
        assert stats.miss_rate == 0.25

    def test_recording_methods(self):
        """Test stat recording methods."""
        stats = CacheStats()

        stats.record_hit()
        stats.record_hit()
        stats.record_miss()
        stats.record_set()
        stats.record_delete()
        stats.record_eviction()
        stats.record_expiration()

        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.sets == 1
        assert stats.deletes == 1
        assert stats.evictions == 1
        assert stats.expirations == 1

    def test_reset(self):
        """Test stats reset."""
        stats = CacheStats(hits=100, misses=50)
        stats.reset()
        assert stats.hits == 0
        assert stats.misses == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CacheStats(hits=80, misses=20)
        d = stats.to_dict()
        assert d["hits"] == 80
        assert d["misses"] == 20
        assert d["total_requests"] == 100
        assert d["hit_rate"] == 0.8


class TestMemoryCache:
    """Tests for MemoryCache."""

    @pytest.fixture
    def cache(self):
        """Create a memory cache for testing."""
        return MemoryCache(max_size=10, default_ttl=60.0, cleanup_interval=1.0)

    def test_set_and_get(self, cache):
        """Test basic set and get."""
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_returns_none(self, cache):
        """Getting nonexistent key returns None."""
        assert cache.get("nonexistent") is None

    def test_exists(self, cache):
        """Test exists method."""
        assert not cache.exists("key1")
        cache.set("key1", "value1")
        assert cache.exists("key1")

    def test_delete(self, cache):
        """Test delete method."""
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False  # Already deleted

    def test_clear(self, cache):
        """Test clear method."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        count = cache.clear()
        assert count == 3
        assert cache.size == 0

    def test_ttl_expiration(self, cache):
        """Test that entries expire after TTL."""
        cache.set("key1", "value1", ttl=0.1)  # 100ms TTL

        assert cache.get("key1") == "value1"
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max_size is reached."""
        cache = MemoryCache(max_size=3, default_ttl=None)

        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)

        # Access 'a' to make it recently used
        cache.get("a")

        # Add new entry, should evict 'b' (least recently used)
        cache.set("d", 4)

        assert cache.get("a") == 1  # Still there (recently used)
        assert cache.get("b") is None  # Evicted (LRU)
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_tag_based_invalidation(self, cache):
        """Test invalidating entries by tag."""
        cache.set("issue:1", {"id": 1}, tags={"project:A"})
        cache.set("issue:2", {"id": 2}, tags={"project:A"})
        cache.set("issue:3", {"id": 3}, tags={"project:B"})

        count = cache.invalidate_by_tag("project:A")

        assert count == 2
        assert cache.get("issue:1") is None
        assert cache.get("issue:2") is None
        assert cache.get("issue:3") == {"id": 3}

    def test_stats_tracking(self, cache):
        """Test that stats are tracked correctly."""
        cache.set("key1", "value1")

        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.sets == 1

    def test_size_property(self, cache):
        """Test size property."""
        assert cache.size == 0
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        assert cache.size == 2

    def test_get_or_set(self, cache):
        """Test get_or_set helper."""
        factory_calls = 0

        def factory():
            nonlocal factory_calls
            factory_calls += 1
            return "computed_value"

        # First call should use factory
        value1 = cache.get_or_set("key1", factory)
        assert value1 == "computed_value"
        assert factory_calls == 1

        # Second call should use cache
        value2 = cache.get_or_set("key1", factory)
        assert value2 == "computed_value"
        assert factory_calls == 1  # Factory not called again


class TestFileCache:
    """Tests for FileCache."""

    @pytest.fixture
    def cache_dir(self):
        """Create a temporary directory for cache files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, cache_dir):
        """Create a file cache for testing."""
        return FileCache(
            cache_dir=cache_dir,
            default_ttl=60.0,
            cleanup_on_start=False,
        )

    def test_set_and_get(self, cache):
        """Test basic set and get."""
        cache.set("key1", {"data": "value1"})
        result = cache.get("key1")
        assert result == {"data": "value1"}

    def test_persistence(self, cache_dir):
        """Test that cache persists across instances."""
        cache1 = FileCache(cache_dir=cache_dir, cleanup_on_start=False)
        cache1.set("persistent", "data")

        # Create new cache instance
        cache2 = FileCache(cache_dir=cache_dir, cleanup_on_start=False)
        assert cache2.get("persistent") == "data"

    def test_ttl_expiration(self, cache):
        """Test that entries expire after TTL."""
        cache.set("key1", "value1", ttl=0.1)

        assert cache.get("key1") == "value1"
        time.sleep(0.15)
        assert cache.get("key1") is None

    def test_delete(self, cache):
        """Test delete method."""
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_clear(self, cache):
        """Test clear method."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        count = cache.clear()
        assert count == 2
        assert cache.size == 0

    def test_tag_based_invalidation(self, cache):
        """Test invalidating entries by tag."""
        cache.set("issue:1", {"id": 1}, tags={"project:A"})
        cache.set("issue:2", {"id": 2}, tags={"project:A"})
        cache.set("issue:3", {"id": 3}, tags={"project:B"})

        count = cache.invalidate_by_tag("project:A")

        assert count == 2
        assert cache.get("issue:1") is None
        assert cache.get("issue:2") is None
        assert cache.get("issue:3") == {"id": 3}


class TestCacheKeyBuilder:
    """Tests for CacheKeyBuilder."""

    @pytest.fixture
    def keys(self):
        """Create a key builder for testing."""
        return CacheKeyBuilder(namespace="test")

    def test_issue_key(self, keys):
        """Test issue key generation."""
        key = keys.issue("PROJ-123")
        assert key == "test:issue:PROJ-123"

    def test_issue_key_with_fields(self, keys):
        """Test issue key with fields includes hash."""
        key = keys.issue("PROJ-123", fields=["summary", "status"])
        assert key.startswith("test:issue:PROJ-123:")
        assert len(key.split(":")) == 4  # Has hash suffix

    def test_issue_key_fields_order_independent(self, keys):
        """Test that field order doesn't affect key."""
        key1 = keys.issue("PROJ-123", fields=["status", "summary"])
        key2 = keys.issue("PROJ-123", fields=["summary", "status"])
        assert key1 == key2

    def test_current_user_key(self, keys):
        """Test current user key."""
        key = keys.current_user()
        assert key == "test:user:myself"

    def test_epic_children_key(self, keys):
        """Test epic children key."""
        key = keys.epic_children("PROJ-1")
        assert key == "test:epic_children:PROJ-1"

    def test_search_key(self, keys):
        """Test search key generation."""
        key = keys.search("project = PROJ ORDER BY key")
        assert key.startswith("test:search:")

    def test_tag_for_issue(self, keys):
        """Test tag generation for issue."""
        tag = keys.tag_for_issue("PROJ-123")
        assert tag == "issue:PROJ-123"

    def test_tag_for_project(self, keys):
        """Test tag generation for project."""
        tag = keys.tag_for_project("PROJ")
        assert tag == "project:PROJ"


class TestCacheManager:
    """Tests for CacheManager."""

    @pytest.fixture
    def manager(self):
        """Create a cache manager for testing."""
        return CacheManager(
            backend=MemoryCache(max_size=100, default_ttl=60),
            enabled=True,
        )

    def test_issue_caching(self, manager):
        """Test issue caching methods."""
        issue_data = {"key": "PROJ-123", "fields": {"summary": "Test"}}

        # Set
        manager.set_issue("PROJ-123", issue_data)

        # Get
        cached = manager.get_issue("PROJ-123")
        assert cached == issue_data

    def test_get_or_fetch_issue(self, manager):
        """Test get_or_fetch_issue pattern."""
        fetch_calls = 0

        def fetch_fn():
            nonlocal fetch_calls
            fetch_calls += 1
            return {"key": "PROJ-123", "fields": {}}

        # First call should fetch
        result1 = manager.get_or_fetch_issue("PROJ-123", fetch_fn)
        assert fetch_calls == 1

        # Second call should use cache
        result2 = manager.get_or_fetch_issue("PROJ-123", fetch_fn)
        assert fetch_calls == 1  # Not called again
        assert result1 == result2

    def test_epic_children_caching(self, manager):
        """Test epic children caching."""
        children = [{"key": "PROJ-1"}, {"key": "PROJ-2"}]

        manager.set_epic_children("EPIC-1", children)
        cached = manager.get_epic_children("EPIC-1")
        assert cached == children

    def test_current_user_caching(self, manager):
        """Test current user caching."""
        user_data = {"accountId": "123", "displayName": "Test User"}

        manager.set_current_user(user_data)
        cached = manager.get_current_user()
        assert cached == user_data

    def test_invalidate_issue(self, manager):
        """Test issue invalidation."""
        manager.set_issue("PROJ-123", {"key": "PROJ-123"})
        manager.set_comments("PROJ-123", [{"body": "comment"}])

        count = manager.invalidate_issue("PROJ-123")
        assert count >= 1
        assert manager.get_issue("PROJ-123") is None

    def test_disabled_cache_returns_none(self):
        """Test that disabled cache always returns None."""
        manager = CacheManager(enabled=False)

        manager.set_issue("PROJ-123", {"key": "PROJ-123"})
        assert manager.get_issue("PROJ-123") is None

    def test_stats_and_size(self, manager):
        """Test stats and size properties."""
        manager.set_issue("PROJ-1", {})
        manager.set_issue("PROJ-2", {})
        manager.get_issue("PROJ-1")  # Hit
        manager.get_issue("PROJ-3")  # Miss

        assert manager.size == 2
        stats = manager.get_stats()
        assert stats.hits >= 1
        assert stats.misses >= 1


class TestCachedJiraApiClient:
    """Tests for CachedJiraApiClient."""

    def test_client_initialization(self):
        """Test client can be initialized with cache options."""
        from spectryn.adapters.jira import CachedJiraApiClient

        client = CachedJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
            cache_enabled=True,
            cache_ttl=300,
            cache_max_size=500,
        )

        assert client.cache_enabled is True
        assert client.cache is not None

    def test_cache_disabled(self):
        """Test cache can be disabled."""
        from spectryn.adapters.jira import CachedJiraApiClient

        client = CachedJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
            cache_enabled=False,
        )

        assert client.cache_enabled is False

    def test_cache_stats_property(self):
        """Test cache_stats property."""
        from spectryn.adapters.jira import CachedJiraApiClient

        client = CachedJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token",
        )

        stats = client.cache_stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "size" in stats
        assert "enabled" in stats


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
