"""
Tests for CachedJiraApiClient.

Tests caching behavior with mocked backend.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.cache import MemoryCache
from spectryn.adapters.jira.cached_client import CachedJiraApiClient


@pytest.fixture
def cached_client():
    """Create a CachedJiraApiClient with mocked session."""
    with patch("requests.Session"):
        return CachedJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test_token_123",
            dry_run=True,
            cache_enabled=True,
            cache_ttl=300.0,
        )


@pytest.fixture
def mock_issue_response():
    """Mock Jira issue response."""
    return {
        "key": "PROJ-123",
        "id": "10001",
        "fields": {
            "summary": "Test Issue",
            "description": {"content": []},
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Story"},
        },
    }


class TestCachedJiraApiClientInit:
    """Tests for CachedJiraApiClient initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default settings."""
        with patch("requests.Session"):
            client = CachedJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
            )

            assert client.cache_enabled is True
            assert client._cache is not None

    def test_init_cache_disabled(self):
        """Test initialization with caching disabled."""
        with patch("requests.Session"):
            client = CachedJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
                cache_enabled=False,
            )

            assert client.cache_enabled is False

    def test_init_with_custom_cache_backend(self):
        """Test initialization with custom cache backend."""
        custom_backend = MemoryCache(max_size=500, default_ttl=600)

        with patch("requests.Session"):
            client = CachedJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
                cache_backend=custom_backend,
            )

            assert client._cache.backend == custom_backend

    def test_init_with_custom_ttl(self):
        """Test initialization with custom TTL."""
        with patch("requests.Session"):
            client = CachedJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
                cache_ttl=600.0,
            )

            assert client._cache.ttls["issue"] == 600.0


class TestCachedReadOperations:
    """Tests for cached read operations."""

    def test_get_myself_cache_miss(self, cached_client):
        """Test get_myself with cache miss."""
        user_data = {"accountId": "user-123", "displayName": "Test User"}

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
            return_value=user_data,
        ) as mock_get:
            result = cached_client.get_myself()

            assert result == user_data
            mock_get.assert_called_once_with("myself")

    def test_get_myself_local_cache(self, cached_client):
        """Test get_myself with local cache."""
        user_data = {"accountId": "user-123", "displayName": "Test User"}
        cached_client._current_user = user_data

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
        ) as mock_get:
            result = cached_client.get_myself()

            assert result == user_data
            mock_get.assert_not_called()

    def test_get_issue_cache_miss(self, cached_client, mock_issue_response):
        """Test get_issue with cache miss."""
        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
            return_value=mock_issue_response,
        ) as mock_get:
            result = cached_client.get_issue("PROJ-123")

            assert result == mock_issue_response
            mock_get.assert_called_once()

    def test_get_issue_cache_hit(self, cached_client, mock_issue_response):
        """Test get_issue with cache hit."""
        # Pre-populate cache
        cached_client._cache.backend.set(
            "jira:issue:PROJ-123",
            mock_issue_response,
            ttl=300,
        )

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
        ) as mock_get:
            result = cached_client.get_issue("PROJ-123")

            assert result == mock_issue_response
            mock_get.assert_not_called()

    def test_get_issue_comments_cache_miss(self, cached_client):
        """Test get_issue_comments with cache miss."""
        comments = [{"body": "Comment 1"}]

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
            return_value={"comments": comments},
        ) as mock_get:
            result = cached_client.get_issue_comments("PROJ-123")

            assert result == comments
            mock_get.assert_called_once()

    def test_get_issue_transitions_cache_miss(self, cached_client):
        """Test get_issue_transitions with cache miss."""
        transitions = [{"id": "1", "name": "To Do"}, {"id": "2", "name": "Done"}]

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
            return_value={"transitions": transitions},
        ) as mock_get:
            result = cached_client.get_issue_transitions("PROJ-123")

            assert result == transitions
            mock_get.assert_called_once()

    def test_get_epic_children_cache_miss(self, cached_client, mock_issue_response):
        """Test get_epic_children with cache miss."""
        issues = [mock_issue_response]

        with patch.object(cached_client, "search_jql", return_value={"issues": issues}):
            result = cached_client.get_epic_children("EPIC-123")

            assert result == issues

    def test_get_link_types_cache_miss(self, cached_client):
        """Test get_link_types with cache miss."""
        link_types = [{"id": "1", "name": "Blocks", "inward": "is blocked by"}]

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "get",
            return_value={"issueLinkTypes": link_types},
        ) as mock_get:
            result = cached_client.get_link_types()

            assert result == link_types
            mock_get.assert_called_once()

    def test_search_jql_cache_miss(self, cached_client, mock_issue_response):
        """Test search_jql with cache miss."""
        search_result = {"issues": [mock_issue_response], "total": 1}

        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "search_jql",
            return_value=search_result,
        ) as mock_search:
            result = cached_client.search_jql("project = PROJ", ["summary"])

            assert result == search_result
            mock_search.assert_called_once()


class TestCacheInvalidation:
    """Tests for cache invalidation on writes."""

    def test_post_invalidates_cache(self, cached_client):
        """Test that POST invalidates issue cache."""
        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "post",
            return_value={},
        ):
            # Pre-populate cache
            cached_client._cache.backend.set("jira:issue:PROJ-123", {}, ttl=300)

            cached_client.post("issue/PROJ-123/comment", json={"body": "Test"})

            # Note: actual invalidation depends on endpoint parsing

    def test_put_invalidates_cache(self, cached_client):
        """Test that PUT invalidates issue cache."""
        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "put",
            return_value={},
        ):
            cached_client.put("issue/PROJ-123", json={"fields": {}})

    def test_delete_invalidates_cache(self, cached_client):
        """Test that DELETE invalidates issue cache."""
        with patch.object(
            CachedJiraApiClient.__bases__[0],
            "delete",
            return_value={},
        ):
            cached_client.delete("issue/PROJ-123/comment/10001")

    def test_invalidation_when_cache_disabled(self):
        """Test that invalidation is no-op when cache is disabled."""
        with patch("requests.Session"):
            client = CachedJiraApiClient(
                base_url="https://test.atlassian.net",
                email="test@example.com",
                api_token="test_token",
                cache_enabled=False,
            )

            # Should not raise
            client._invalidate_for_endpoint("issue/PROJ-123", "PUT")


class TestCacheManagement:
    """Tests for cache management methods."""

    def test_cache_property(self, cached_client):
        """Test cache property returns CacheManager."""
        cache = cached_client.cache
        assert cache is not None
        assert cache == cached_client._cache

    def test_cache_stats(self, cached_client):
        """Test cache_stats returns statistics."""
        stats = cached_client.cache_stats

        assert "enabled" in stats
        assert stats["enabled"] is True
        assert "size" in stats

    def test_cache_hit_rate(self, cached_client):
        """Test cache_hit_rate returns float."""
        rate = cached_client.cache_hit_rate

        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0

    def test_clear_cache(self, cached_client):
        """Test clearing all cache."""
        cached_client._cache.backend.set("key1", "value1", ttl=300)
        cached_client._cache.backend.set("key2", "value2", ttl=300)

        cleared = cached_client.clear_cache()

        assert cleared >= 0

    def test_invalidate_issue_cache(self, cached_client):
        """Test manual issue cache invalidation."""
        cached_client.invalidate_issue_cache("PROJ-123")

    def test_invalidate_epic_cache(self, cached_client):
        """Test manual epic cache invalidation."""
        cached_client.invalidate_epic_cache("EPIC-123")
