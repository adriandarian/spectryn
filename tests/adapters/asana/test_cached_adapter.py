"""
Tests for CachedAsanaAdapter.

Tests caching behavior with mocked backend.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.asana.cached_adapter import CachedAsanaAdapter
from spectryn.adapters.cache import MemoryCache
from spectryn.core.ports.config_provider import TrackerConfig
from spectryn.core.ports.issue_tracker import IssueData


@pytest.fixture
def mock_config():
    """Create a mock TrackerConfig."""
    return TrackerConfig(
        url="https://app.asana.com/api/1.0",
        email="test@example.com",
        api_token="test_token_123",
        project_key="1234567890",
    )


@pytest.fixture
def mock_issue_data():
    """Create mock IssueData."""
    return IssueData(
        key="task-123",
        summary="Test Task",
        description="Description",
        status="In Progress",
        issue_type="task",
        assignee="user-123",
        story_points=5.0,
        comments=[],
        links=[],
    )


@pytest.fixture
def cached_adapter(mock_config):
    """Create a CachedAsanaAdapter with mocked session."""
    with patch("requests.Session"):
        return CachedAsanaAdapter(
            config=mock_config,
            dry_run=True,
            cache_enabled=True,
            cache_ttl=300.0,
        )


class TestCachedAsanaAdapterInit:
    """Tests for CachedAsanaAdapter initialization."""

    def test_init_with_defaults(self, mock_config):
        """Test initialization with default settings."""
        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(config=mock_config)

            assert adapter.cache_enabled is True
            assert adapter._cache is not None

    def test_init_cache_disabled(self, mock_config):
        """Test initialization with caching disabled."""
        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(
                config=mock_config,
                cache_enabled=False,
            )

            assert adapter.cache_enabled is False

    def test_init_with_custom_cache_backend(self, mock_config):
        """Test initialization with custom cache backend."""
        custom_backend = MemoryCache(max_size=500, default_ttl=600)

        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(
                config=mock_config,
                cache_backend=custom_backend,
            )

            assert adapter._cache.backend == custom_backend

    def test_init_with_custom_ttl(self, mock_config):
        """Test initialization with custom TTL."""
        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(
                config=mock_config,
                cache_ttl=600.0,
            )

            assert adapter._cache.ttls["issue"] == 600.0


class TestCachedReadOperations:
    """Tests for cached read operations."""

    def test_get_issue_cache_miss(self, cached_adapter, mock_issue_data):
        """Test get_issue with cache miss."""
        with patch.object(
            CachedAsanaAdapter.__bases__[0],  # AsanaAdapter
            "get_issue",
            return_value=mock_issue_data,
        ) as mock_get:
            result = cached_adapter.get_issue("task-123")

            assert result == mock_issue_data
            mock_get.assert_called_once_with("task-123")

    def test_get_issue_cache_hit(self, cached_adapter, mock_issue_data):
        """Test get_issue with cache hit."""
        # Pre-populate cache
        cached_adapter._cache.backend.set(
            "asana:issue:task-123",
            mock_issue_data,
            ttl=300,
        )

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_issue",
        ) as mock_get:
            result = cached_adapter.get_issue("task-123")

            assert result == mock_issue_data
            mock_get.assert_not_called()

    def test_get_issue_cache_disabled(self, mock_config, mock_issue_data):
        """Test get_issue with caching disabled."""
        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(
                config=mock_config,
                cache_enabled=False,
            )

            with patch.object(
                CachedAsanaAdapter.__bases__[0],
                "get_issue",
                return_value=mock_issue_data,
            ) as mock_get:
                result = adapter.get_issue("task-123")

                assert result == mock_issue_data
                mock_get.assert_called_once()

    def test_get_epic_children_cache_miss(self, cached_adapter, mock_issue_data):
        """Test get_epic_children with cache miss."""
        children = [mock_issue_data]

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_epic_children",
            return_value=children,
        ) as mock_get:
            result = cached_adapter.get_epic_children("project-123")

            assert result == children
            mock_get.assert_called_once()

    def test_get_epic_children_cache_hit(self, cached_adapter, mock_issue_data):
        """Test get_epic_children with cache hit."""
        children = [mock_issue_data]
        cached_adapter._cache.backend.set(
            "asana:epic_children:project-123",
            children,
            ttl=300,
        )

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_epic_children",
        ) as mock_get:
            result = cached_adapter.get_epic_children("project-123")

            assert result == children
            mock_get.assert_not_called()

    def test_get_issue_comments_cache_miss(self, cached_adapter):
        """Test get_issue_comments with cache miss."""
        comments = [{"text": "Comment 1"}]

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_issue_comments",
            return_value=comments,
        ) as mock_get:
            result = cached_adapter.get_issue_comments("task-123")

            assert result == comments
            mock_get.assert_called_once()

    def test_get_issue_comments_cache_hit(self, cached_adapter):
        """Test get_issue_comments with cache hit."""
        comments = [{"text": "Comment 1"}]
        cached_adapter._cache.backend.set(
            "asana:comments:task-123",
            comments,
            ttl=600,
        )

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_issue_comments",
        ) as mock_get:
            result = cached_adapter.get_issue_comments("task-123")

            assert result == comments
            mock_get.assert_not_called()

    def test_search_issues_cache_miss(self, cached_adapter, mock_issue_data):
        """Test search_issues with cache miss."""
        results = [mock_issue_data]

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "search_issues",
            return_value=results,
        ) as mock_search:
            result = cached_adapter.search_issues("test query", max_results=10)

            assert result == results
            mock_search.assert_called_once_with("test query", 10)

    def test_search_issues_cache_hit(self, cached_adapter, mock_issue_data):
        """Test search_issues with cache hit."""
        results = [mock_issue_data]
        cached_adapter._cache.backend.set(
            "asana:search:test query:10",
            results,
            ttl=100,
        )

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "search_issues",
        ) as mock_search:
            result = cached_adapter.search_issues("test query", max_results=10)

            assert result == results
            mock_search.assert_not_called()

    def test_get_current_user_cache_miss(self, cached_adapter):
        """Test get_current_user with cache miss."""
        user_data = {"gid": "user-123", "name": "Test User"}

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_current_user",
            return_value=user_data,
        ) as mock_get:
            result = cached_adapter.get_current_user()

            assert result == user_data
            mock_get.assert_called_once()

    def test_get_current_user_local_cache(self, cached_adapter):
        """Test get_current_user with local cache."""
        user_data = {"gid": "user-123", "name": "Test User"}
        cached_adapter._current_user = user_data

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "get_current_user",
        ) as mock_get:
            result = cached_adapter.get_current_user()

            assert result == user_data
            mock_get.assert_not_called()


class TestCacheInvalidation:
    """Tests for cache invalidation on writes."""

    def test_update_issue_description_invalidates_cache(self, cached_adapter):
        """Test that update_issue_description invalidates task cache."""
        # Pre-populate cache
        cached_adapter._cache.backend.set("asana:issue:task-123", {}, ttl=300)

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "update_issue_description",
            return_value=True,
        ):
            cached_adapter.update_issue_description("task-123", "New description")

            # Cache should be invalidated
            assert cached_adapter._cache.backend.get("asana:issue:task-123") is None

    def test_create_subtask_invalidates_cache(self, cached_adapter):
        """Test that create_subtask invalidates parent and project cache."""
        cached_adapter._cache.backend.set("asana:issue:parent-123", {}, ttl=300)
        cached_adapter._cache.backend.set("asana:epic_children:project-456", [], ttl=300)

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "create_subtask",
            return_value="new-subtask-gid",
        ):
            cached_adapter.create_subtask(
                parent_key="parent-123",
                summary="New Subtask",
                description="Description",
                project_key="project-456",
            )

            # Both caches should be invalidated
            assert cached_adapter._cache.backend.get("asana:issue:parent-123") is None
            assert cached_adapter._cache.backend.get("asana:epic_children:project-456") is None

    def test_update_subtask_invalidates_cache(self, cached_adapter):
        """Test that update_subtask invalidates task cache."""
        cached_adapter._cache.backend.set("asana:issue:task-123", {}, ttl=300)

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "update_subtask",
            return_value=True,
        ):
            cached_adapter.update_subtask("task-123", description="Updated")

            assert cached_adapter._cache.backend.get("asana:issue:task-123") is None

    def test_add_comment_invalidates_cache(self, cached_adapter):
        """Test that add_comment invalidates comments cache."""
        cached_adapter._cache.backend.set("asana:comments:task-123", [], ttl=600)

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "add_comment",
            return_value=True,
        ):
            cached_adapter.add_comment("task-123", "New comment")

            assert cached_adapter._cache.backend.get("asana:comments:task-123") is None

    def test_transition_issue_invalidates_cache(self, cached_adapter):
        """Test that transition_issue invalidates task cache."""
        cached_adapter._cache.backend.set("asana:issue:task-123", {}, ttl=300)

        with patch.object(
            CachedAsanaAdapter.__bases__[0],
            "transition_issue",
            return_value=True,
        ):
            cached_adapter.transition_issue("task-123", "done")

            assert cached_adapter._cache.backend.get("asana:issue:task-123") is None

    def test_invalidation_when_cache_disabled(self, mock_config):
        """Test that invalidation is no-op when cache is disabled."""
        with patch("requests.Session"):
            adapter = CachedAsanaAdapter(
                config=mock_config,
                cache_enabled=False,
            )

            # Should not raise
            adapter._invalidate_task("task-123")
            adapter._invalidate_comments("task-123")
            adapter._invalidate_project("project-123")


class TestCacheManagement:
    """Tests for cache management methods."""

    def test_cache_property(self, cached_adapter):
        """Test cache property returns CacheManager."""
        cache = cached_adapter.cache
        assert cache is not None
        assert cache == cached_adapter._cache

    def test_cache_stats(self, cached_adapter):
        """Test cache_stats returns statistics."""
        stats = cached_adapter.cache_stats

        assert "enabled" in stats
        assert stats["enabled"] is True
        assert "size" in stats

    def test_cache_hit_rate(self, cached_adapter):
        """Test cache_hit_rate returns float."""
        rate = cached_adapter.cache_hit_rate

        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0

    def test_clear_cache(self, cached_adapter):
        """Test clearing all cache."""
        # Add some entries
        cached_adapter._cache.backend.set("key1", "value1", ttl=300)
        cached_adapter._cache.backend.set("key2", "value2", ttl=300)

        cleared = cached_adapter.clear_cache()

        assert cleared >= 0  # Returns number of cleared entries

    def test_invalidate_task_cache_manual(self, cached_adapter):
        """Test manual task cache invalidation."""
        cached_adapter._cache.backend.set("asana:issue:task-123", {}, ttl=300)
        cached_adapter._cache.backend.set("asana:comments:task-123", [], ttl=600)

        cached_adapter.invalidate_task_cache("task-123")

        assert cached_adapter._cache.backend.get("asana:issue:task-123") is None
        assert cached_adapter._cache.backend.get("asana:comments:task-123") is None

    def test_invalidate_project_cache_manual(self, cached_adapter):
        """Test manual project cache invalidation."""
        cached_adapter._cache.backend.set("asana:epic_children:project-123", [], ttl=300)

        cached_adapter.invalidate_project_cache("project-123")

        assert cached_adapter._cache.backend.get("asana:epic_children:project-123") is None
