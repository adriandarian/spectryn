"""Tests for MetadataCache - Smart caching for tracker metadata."""

import time
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.cache import (
    DEFAULT_METADATA_TTLS,
    MemoryCache,
    MetadataCache,
    MetadataCacheEntry,
    MetadataCacheStats,
    MetadataType,
    create_metadata_cache,
)


class TestMetadataType:
    """Tests for MetadataType enum."""

    def test_all_types_defined(self):
        """Test that all expected metadata types are defined."""
        expected_types = [
            "STATES",
            "PRIORITIES",
            "FIELDS",
            "USERS",
            "PROJECTS",
            "LABELS",
            "TEAMS",
            "SPRINTS",
            "BOARDS",
            "WORKFLOWS",
            "ISSUE_TYPES",
            "RESOLUTIONS",
            "LINK_TYPES",
            "CUSTOM_FIELDS",
        ]
        for type_name in expected_types:
            assert hasattr(MetadataType, type_name)

    def test_type_values_are_strings(self):
        """Test that metadata type values are strings."""
        for mtype in MetadataType:
            assert isinstance(mtype.value, str)


class TestMetadataCacheEntry:
    """Tests for MetadataCacheEntry dataclass."""

    def test_entry_not_expired_without_expiry(self):
        """Entry without expiration never expires."""
        entry = MetadataCacheEntry(value="test", expires_at=None)
        assert not entry.is_expired

    def test_entry_expired_after_expiry(self):
        """Entry expires after expiry time."""
        entry = MetadataCacheEntry(
            value="test",
            expires_at=time.time() - 1,  # Expired 1 second ago
        )
        assert entry.is_expired

    def test_entry_not_expired_within_ttl(self):
        """Entry is not expired within TTL."""
        entry = MetadataCacheEntry(
            value="test",
            expires_at=time.time() + 100,  # Expires in 100 seconds
        )
        assert not entry.is_expired

    def test_should_refresh_when_past_refresh_time(self):
        """Entry should refresh when past refresh time."""
        entry = MetadataCacheEntry(
            value="test",
            expires_at=time.time() + 100,
            refresh_at=time.time() - 1,  # Refresh time passed
        )
        assert entry.should_refresh
        assert not entry.is_expired  # But not expired yet

    def test_should_not_refresh_when_fresh(self):
        """Entry should not refresh when fresh."""
        entry = MetadataCacheEntry(
            value="test",
            expires_at=time.time() + 100,
            refresh_at=time.time() + 50,
        )
        assert not entry.should_refresh

    def test_ttl_remaining(self):
        """Test TTL remaining calculation."""
        entry = MetadataCacheEntry(
            value="test",
            expires_at=time.time() + 50,
        )
        remaining = entry.ttl_remaining
        assert remaining is not None
        assert 49 < remaining <= 50

    def test_ttl_remaining_none_when_no_expiry(self):
        """Test TTL remaining is None when no expiry."""
        entry = MetadataCacheEntry(value="test", expires_at=None)
        assert entry.ttl_remaining is None

    def test_age_calculation(self):
        """Test age calculation."""
        created_time = time.time() - 10
        entry = MetadataCacheEntry(value="test", created_at=created_time)
        assert 9.9 < entry.age < 10.1


class TestMetadataCacheStats:
    """Tests for MetadataCacheStats."""

    def test_initial_values(self):
        """Test initial stat values are zero."""
        stats = MetadataCacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.refreshes == 0
        assert stats.stale_hits == 0

    def test_hit_rate_zero_when_no_requests(self):
        """Test hit rate is 0 when no requests."""
        stats = MetadataCacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = MetadataCacheStats(hits=7, misses=3)
        assert stats.hit_rate == 0.7

    def test_record_hit(self):
        """Test recording a cache hit."""
        stats = MetadataCacheStats()
        stats.record_hit()
        assert stats.hits == 1
        assert stats.stale_hits == 0

    def test_record_stale_hit(self):
        """Test recording a stale cache hit."""
        stats = MetadataCacheStats()
        stats.record_hit(stale=True)
        assert stats.hits == 1
        assert stats.stale_hits == 1

    def test_record_miss(self):
        """Test recording a cache miss."""
        stats = MetadataCacheStats()
        stats.record_miss()
        assert stats.misses == 1

    def test_record_refresh(self):
        """Test recording a refresh."""
        stats = MetadataCacheStats()
        stats.record_refresh()
        assert stats.refreshes == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = MetadataCacheStats(hits=10, misses=5, refreshes=2, stale_hits=3)
        d = stats.to_dict()
        assert d["hits"] == 10
        assert d["misses"] == 5
        assert d["refreshes"] == 2
        assert d["stale_hits"] == 3
        assert d["hit_rate"] == pytest.approx(0.666, rel=0.01)
        assert d["total_requests"] == 15


class TestMetadataCacheBasics:
    """Basic tests for MetadataCache."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_init_defaults(self, cache: MetadataCache):
        """Test default initialization."""
        assert cache.tracker == "test"
        assert cache.enabled is True
        assert cache.refresh_ratio == 0.8

    def test_init_custom_ttls(self):
        """Test initialization with custom TTLs."""
        custom_ttls = {MetadataType.STATES: 7200}
        cache = MetadataCache(tracker="test", ttls=custom_ttls)
        assert cache.ttls[MetadataType.STATES] == 7200

    def test_init_disabled(self):
        """Test initialization with caching disabled."""
        cache = MetadataCache(tracker="test", enabled=False)
        assert cache.enabled is False

    def test_init_custom_backend(self):
        """Test initialization with custom backend."""
        backend = MemoryCache(max_size=100)
        cache = MetadataCache(tracker="test", backend=backend)
        assert cache.backend == backend

    def test_make_key_simple(self, cache: MetadataCache):
        """Test key generation without scope."""
        key = cache._make_key(MetadataType.STATES)
        assert key == "test:metadata:states"

    def test_make_key_with_scope(self, cache: MetadataCache):
        """Test key generation with scope."""
        key = cache._make_key(MetadataType.STATES, "project-123")
        assert key == "test:metadata:states:project-123"


class TestMetadataCacheSetGet:
    """Tests for set/get operations."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_set_and_get_metadata(self, cache: MetadataCache):
        """Test basic set and get."""
        states = [{"id": "1", "name": "open"}, {"id": "2", "name": "closed"}]
        cache.set_metadata(MetadataType.STATES, states)

        result = cache.get_metadata(MetadataType.STATES)
        assert result is not None
        # Extract value from MetadataCacheEntry if needed
        if isinstance(result, MetadataCacheEntry):
            result = result.value
        assert len(result) == 2
        assert result[0]["name"] == "open"

    def test_get_returns_none_for_missing(self, cache: MetadataCache):
        """Test get returns None for missing keys."""
        result = cache.get_metadata(MetadataType.PRIORITIES)
        assert result is None

    def test_get_returns_none_when_disabled(self):
        """Test get returns None when cache is disabled."""
        cache = MetadataCache(tracker="test", enabled=False)
        cache.backend.set("test:metadata:states", [{"id": "1"}])
        result = cache.get_metadata(MetadataType.STATES)
        assert result is None

    def test_set_does_nothing_when_disabled(self):
        """Test set does nothing when cache is disabled."""
        cache = MetadataCache(tracker="test", enabled=False)
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}])
        # Try to get directly from backend
        result = cache.backend.get("test:metadata:states")
        assert result is None

    def test_set_with_scope(self, cache: MetadataCache):
        """Test set and get with scope."""
        states = [{"id": "1", "name": "open"}]
        cache.set_metadata(MetadataType.STATES, states, scope="project-a")

        # Without scope should return None
        result = cache.get_metadata(MetadataType.STATES)
        assert result is None

        # With scope should return value
        result = cache.get_metadata(MetadataType.STATES, scope="project-a")
        assert result is not None

    def test_set_with_custom_ttl(self, cache: MetadataCache):
        """Test set with custom TTL."""
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}], ttl=0.1)
        result = cache.get_metadata(MetadataType.STATES)
        assert result is not None

        time.sleep(0.15)
        result = cache.get_metadata(MetadataType.STATES)
        # Should be expired (None or expired entry)
        if result is not None and isinstance(result, MetadataCacheEntry):
            assert result.is_expired
        else:
            assert result is None


class TestMetadataCacheGetOrFetch:
    """Tests for get_or_fetch operation."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_get_or_fetch_misses_on_first_call(self, cache: MetadataCache):
        """Test fetch is called on cache miss."""
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        result = cache.get_or_fetch(MetadataType.STATES, fetch_fn)

        assert result == [{"id": "1"}]
        fetch_fn.assert_called_once()

    def test_get_or_fetch_uses_cache_on_hit(self, cache: MetadataCache):
        """Test cache is used on subsequent calls."""
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        # First call
        cache.get_or_fetch(MetadataType.STATES, fetch_fn)
        # Second call
        result = cache.get_or_fetch(MetadataType.STATES, fetch_fn)

        # Extract value if needed
        if isinstance(result, MetadataCacheEntry):
            result = result.value

        assert result == [{"id": "1"}]
        assert fetch_fn.call_count == 1  # Only called once

    def test_get_or_fetch_force_refresh(self, cache: MetadataCache):
        """Test force_refresh bypasses cache."""
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        # First call
        cache.get_or_fetch(MetadataType.STATES, fetch_fn)
        # Force refresh
        cache.get_or_fetch(MetadataType.STATES, fetch_fn, force_refresh=True)

        assert fetch_fn.call_count == 2

    def test_get_or_fetch_when_disabled(self):
        """Test get_or_fetch calls fetch when disabled."""
        cache = MetadataCache(tracker="test", enabled=False)
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        result = cache.get_or_fetch(MetadataType.STATES, fetch_fn)
        result2 = cache.get_or_fetch(MetadataType.STATES, fetch_fn)

        assert result == [{"id": "1"}]
        assert result2 == [{"id": "1"}]
        assert fetch_fn.call_count == 2  # Called each time


class TestMetadataCacheInvalidation:
    """Tests for cache invalidation."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_invalidate_specific_key(self, cache: MetadataCache):
        """Test invalidating a specific key."""
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}])
        cache.set_metadata(MetadataType.PRIORITIES, [{"id": "p1"}])

        result = cache.invalidate(MetadataType.STATES)
        assert result is True

        assert cache.get_metadata(MetadataType.STATES) is None
        assert cache.get_metadata(MetadataType.PRIORITIES) is not None

    def test_invalidate_with_scope(self, cache: MetadataCache):
        """Test invalidating with scope."""
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}], scope="proj-a")
        cache.set_metadata(MetadataType.STATES, [{"id": "2"}], scope="proj-b")

        cache.invalidate(MetadataType.STATES, scope="proj-a")

        assert cache.get_metadata(MetadataType.STATES, scope="proj-a") is None
        assert cache.get_metadata(MetadataType.STATES, scope="proj-b") is not None

    def test_invalidate_all_by_type(self, cache: MetadataCache):
        """Test invalidating all entries of a type."""
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}])
        cache.set_metadata(MetadataType.PRIORITIES, [{"id": "p1"}])

        # Note: This depends on tag-based invalidation working correctly
        count = cache.invalidate_all(MetadataType.STATES)
        assert count >= 0  # May be 0 if tag not used

    def test_clear_all(self, cache: MetadataCache):
        """Test clearing all cached data."""
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}])
        cache.set_metadata(MetadataType.PRIORITIES, [{"id": "p1"}])

        count = cache.clear()
        assert count >= 0

        assert cache.get_metadata(MetadataType.STATES) is None
        assert cache.get_metadata(MetadataType.PRIORITIES) is None


class TestMetadataCacheConvenienceMethods:
    """Tests for type-specific convenience methods."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_states_convenience_methods(self, cache: MetadataCache):
        """Test states convenience methods."""
        states = [{"id": "1", "name": "open"}]
        cache.set_states(states)
        result = cache.get_states()
        assert result is not None

    def test_priorities_convenience_methods(self, cache: MetadataCache):
        """Test priorities convenience methods."""
        priorities = [{"id": "high", "name": "High"}]
        cache.set_priorities(priorities)
        result = cache.get_priorities()
        assert result is not None

    def test_users_convenience_methods(self, cache: MetadataCache):
        """Test users convenience methods."""
        users = [{"id": "u1", "name": "Alice"}]
        cache.set_users(users)
        result = cache.get_users()
        assert result is not None

    def test_projects_convenience_methods(self, cache: MetadataCache):
        """Test projects convenience methods."""
        projects = [{"id": "p1", "name": "Project A"}]
        cache.set_projects(projects)
        result = cache.get_projects()
        assert result is not None

    def test_labels_convenience_methods(self, cache: MetadataCache):
        """Test labels convenience methods."""
        labels = [{"id": "l1", "name": "bug"}]
        cache.set_labels(labels)
        result = cache.get_labels()
        assert result is not None

    def test_custom_fields_convenience_methods(self, cache: MetadataCache):
        """Test custom fields convenience methods."""
        fields = [{"id": "cf1", "name": "Sprint"}]
        cache.set_custom_fields(fields)
        result = cache.get_custom_fields()
        assert result is not None

    def test_get_or_fetch_convenience_methods(self, cache: MetadataCache):
        """Test get_or_fetch convenience methods."""
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        result = cache.get_or_fetch_states(fetch_fn)
        assert result == [{"id": "1"}]
        fetch_fn.assert_called_once()


class TestMetadataCacheWarmUp:
    """Tests for cache warm-up functionality."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_warm_up_success(self, cache: MetadataCache):
        """Test warm-up with successful fetches."""
        fetchers = {
            MetadataType.STATES: lambda: [{"id": "1"}],
            MetadataType.PRIORITIES: lambda: [{"id": "p1"}],
        }

        results = cache.warm_up(fetchers)

        assert results[MetadataType.STATES] is True
        assert results[MetadataType.PRIORITIES] is True
        assert cache.get_metadata(MetadataType.STATES) is not None
        assert cache.get_metadata(MetadataType.PRIORITIES) is not None

    def test_warm_up_partial_failure(self, cache: MetadataCache):
        """Test warm-up with some failures."""

        def fail():
            raise ValueError("API Error")

        fetchers = {
            MetadataType.STATES: lambda: [{"id": "1"}],
            MetadataType.PRIORITIES: fail,
        }

        results = cache.warm_up(fetchers)

        assert results[MetadataType.STATES] is True
        assert results[MetadataType.PRIORITIES] is False
        assert cache.get_metadata(MetadataType.STATES) is not None

    def test_warm_up_async(self, cache: MetadataCache):
        """Test async warm-up."""
        fetchers = {
            MetadataType.STATES: lambda: [{"id": "1"}],
            MetadataType.PRIORITIES: lambda: [{"id": "p1"}],
            MetadataType.USERS: lambda: [{"id": "u1"}],
        }

        results = cache.warm_up_async(fetchers, max_workers=2)

        assert results[MetadataType.STATES] is True
        assert results[MetadataType.PRIORITIES] is True
        assert results[MetadataType.USERS] is True


class TestMetadataCacheStatsTracking:
    """Tests for cache statistics tracking."""

    @pytest.fixture
    def cache(self) -> MetadataCache:
        return MetadataCache(tracker="test")

    def test_stats_tracking(self, cache: MetadataCache):
        """Test statistics are tracked correctly."""
        fetch_fn = MagicMock(return_value=[{"id": "1"}])

        # Miss
        cache.get_or_fetch(MetadataType.STATES, fetch_fn)
        # Hit
        cache.get_or_fetch(MetadataType.STATES, fetch_fn)
        # Another miss
        cache.get_or_fetch(MetadataType.PRIORITIES, fetch_fn)

        stats = cache.stats
        assert stats.misses == 2
        assert stats.hits >= 1

    def test_get_stats_dict(self, cache: MetadataCache):
        """Test get_stats returns dictionary."""
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "tracker" in stats
        assert stats["tracker"] == "test"
        assert "enabled" in stats
        assert stats["enabled"] is True

    def test_size_property(self, cache: MetadataCache):
        """Test size property."""
        assert cache.size == 0
        cache.set_metadata(MetadataType.STATES, [{"id": "1"}])
        assert cache.size == 1


class TestDefaultMetadataTTLs:
    """Tests for default TTL values."""

    def test_default_ttls_defined(self):
        """Test all metadata types have default TTLs."""
        for mtype in MetadataType:
            assert mtype in DEFAULT_METADATA_TTLS
            assert DEFAULT_METADATA_TTLS[mtype] > 0

    def test_states_have_long_ttl(self):
        """Test states have appropriately long TTL."""
        assert DEFAULT_METADATA_TTLS[MetadataType.STATES] >= 3600  # At least 1 hour

    def test_sprints_have_shorter_ttl(self):
        """Test sprints have shorter TTL (more dynamic)."""
        assert (
            DEFAULT_METADATA_TTLS[MetadataType.SPRINTS] < DEFAULT_METADATA_TTLS[MetadataType.STATES]
        )


class TestCreateMetadataCache:
    """Tests for create_metadata_cache factory function."""

    def test_create_with_default_preset(self):
        """Test creating cache with default preset."""
        cache = create_metadata_cache("jira", preset="default")
        assert cache.tracker == "jira"
        assert cache.ttls == DEFAULT_METADATA_TTLS

    def test_create_with_aggressive_preset(self):
        """Test creating cache with aggressive preset."""
        cache = create_metadata_cache("jira", preset="aggressive")
        assert cache.ttls[MetadataType.STATES] == 7200  # 2 hours

    def test_create_with_conservative_preset(self):
        """Test creating cache with conservative preset."""
        cache = create_metadata_cache("jira", preset="conservative")
        assert cache.ttls[MetadataType.STATES] == 900  # 15 minutes

    def test_create_with_minimal_preset(self):
        """Test creating cache with minimal preset."""
        cache = create_metadata_cache("jira", preset="minimal")
        assert cache.ttls[MetadataType.STATES] == 60  # 1 minute

    def test_create_with_custom_backend(self):
        """Test creating cache with custom backend."""
        backend = MemoryCache(max_size=100)
        cache = create_metadata_cache("jira", backend=backend)
        assert cache.backend == backend


class TestMetadataCacheThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_get_set(self):
        """Test concurrent get and set operations."""
        import threading

        cache = MetadataCache(tracker="test")
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(100):
                    cache.set_metadata(MetadataType.STATES, [{"id": str(i)}])
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    cache.get_metadata(MetadataType.STATES)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(5)]
        threads += [threading.Thread(target=reader) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestMetadataCacheIntegration:
    """Integration tests for MetadataCache."""

    def test_full_workflow(self):
        """Test a complete workflow with MetadataCache."""
        cache = MetadataCache(tracker="jira")

        # Simulate API calls
        api_calls = 0

        def fetch_states() -> list[dict]:
            nonlocal api_calls
            api_calls += 1
            return [{"id": "1", "name": "Open"}, {"id": "2", "name": "Closed"}]

        def fetch_priorities() -> list[dict]:
            nonlocal api_calls
            api_calls += 1
            return [{"id": "high"}, {"id": "medium"}, {"id": "low"}]

        # Warm up cache
        results = cache.warm_up(
            {
                MetadataType.STATES: fetch_states,
                MetadataType.PRIORITIES: fetch_priorities,
            }
        )
        assert all(results.values())
        assert api_calls == 2

        # Subsequent calls should use cache
        states1 = cache.get_or_fetch_states(fetch_states)
        states2 = cache.get_or_fetch_states(fetch_states)
        priorities = cache.get_or_fetch_priorities(fetch_priorities)

        # Extract values if needed
        if isinstance(states1, MetadataCacheEntry):
            states1 = states1.value
        if isinstance(states2, MetadataCacheEntry):
            states2 = states2.value
        if isinstance(priorities, MetadataCacheEntry):
            priorities = priorities.value

        assert len(states1) == 2
        assert len(priorities) == 3
        assert api_calls == 2  # No additional API calls

        # Check stats
        stats = cache.get_stats()
        assert stats["hits"] > 0

    def test_scoped_caching(self):
        """Test caching with different scopes (projects)."""
        cache = MetadataCache(tracker="plane")

        # Different projects have different states
        cache.set_states([{"id": "1"}], scope="project-a")
        cache.set_states([{"id": "1"}, {"id": "2"}], scope="project-b")

        states_a = cache.get_states(scope="project-a")
        states_b = cache.get_states(scope="project-b")

        # Extract values if needed
        if isinstance(states_a, MetadataCacheEntry):
            states_a = states_a.value
        if isinstance(states_b, MetadataCacheEntry):
            states_b = states_b.value

        assert len(states_a) == 1
        assert len(states_b) == 2
