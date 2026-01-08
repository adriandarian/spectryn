"""Tests for connection pooling tuning."""

import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.http.connection_pool import (
    ConnectionPoolManager,
    PoolConfig,
    PoolStats,
    PoolStrategy,
    TunedHTTPAdapter,
    configure_global_pools,
    create_azure_devops_adapter,
    create_github_adapter,
    create_jira_adapter,
    create_linear_adapter,
    get_pool_manager,
    get_pool_stats,
    get_session_for_host,
)


class TestPoolStrategy:
    """Tests for PoolStrategy enum."""

    def test_strategy_values(self):
        """Test strategy enum values."""
        assert PoolStrategy.CONSERVATIVE.value == "conservative"
        assert PoolStrategy.BALANCED.value == "balanced"
        assert PoolStrategy.AGGRESSIVE.value == "aggressive"
        assert PoolStrategy.CUSTOM.value == "custom"


class TestPoolConfig:
    """Tests for PoolConfig dataclass."""

    def test_default_values(self):
        """Test default configuration."""
        config = PoolConfig()

        assert config.pool_connections == 10
        assert config.pool_maxsize == 10
        assert config.pool_block is False
        assert config.connect_timeout == 10.0
        assert config.read_timeout == 30.0
        assert config.keep_alive is True
        assert config.retry_total == 3
        assert config.ssl_verify is True

    def test_custom_values(self):
        """Test custom configuration."""
        config = PoolConfig(
            pool_connections=20,
            pool_maxsize=20,
            pool_block=True,
            connect_timeout=5.0,
        )

        assert config.pool_connections == 20
        assert config.pool_block is True
        assert config.connect_timeout == 5.0

    def test_from_strategy_conservative(self):
        """Test conservative strategy config."""
        config = PoolConfig.from_strategy(PoolStrategy.CONSERVATIVE)

        assert config.pool_connections == 5
        assert config.pool_maxsize == 5
        assert config.pool_block is True
        assert config.connect_timeout == 15.0

    def test_from_strategy_aggressive(self):
        """Test aggressive strategy config."""
        config = PoolConfig.from_strategy(PoolStrategy.AGGRESSIVE)

        assert config.pool_connections == 20
        assert config.pool_maxsize == 20
        assert config.pool_block is False
        assert config.connect_timeout == 5.0
        assert config.retry_total == 5

    def test_from_strategy_balanced(self):
        """Test balanced strategy config."""
        config = PoolConfig.from_strategy(PoolStrategy.BALANCED)

        assert config.pool_connections == 10
        assert config.pool_maxsize == 10


class TestPoolStats:
    """Tests for PoolStats dataclass."""

    def test_default_values(self):
        """Test default stats values."""
        stats = PoolStats(host="https://example.com", pool_connections=10, pool_maxsize=10)

        assert stats.host == "https://example.com"
        assert stats.requests_made == 0
        assert stats.connections_reused == 0
        assert stats.errors == 0
        assert stats.avg_response_time_ms == 0.0

    def test_reuse_ratio_no_requests(self):
        """Test reuse ratio with no requests."""
        stats = PoolStats(host="https://example.com", pool_connections=10, pool_maxsize=10)

        assert stats.reuse_ratio == 0.0

    def test_reuse_ratio_all_reused(self):
        """Test reuse ratio when all connections reused."""
        stats = PoolStats(
            host="https://example.com",
            pool_connections=10,
            pool_maxsize=10,
            connections_reused=100,
            connections_created=0,
        )

        assert stats.reuse_ratio == 1.0

    def test_reuse_ratio_mixed(self):
        """Test reuse ratio with mixed connections."""
        stats = PoolStats(
            host="https://example.com",
            pool_connections=10,
            pool_maxsize=10,
            connections_reused=75,
            connections_created=25,
        )

        assert stats.reuse_ratio == 0.75


class TestTunedHTTPAdapter:
    """Tests for TunedHTTPAdapter."""

    def test_initialization_defaults(self):
        """Test adapter with default settings."""
        adapter = TunedHTTPAdapter()

        assert adapter.pool_config.pool_connections == 10
        assert adapter.pool_config.pool_maxsize == 10
        assert adapter.pool_config.pool_block is False

    def test_initialization_custom(self):
        """Test adapter with custom settings."""
        adapter = TunedHTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            pool_block=True,
        )

        assert adapter.pool_config.pool_connections == 20
        assert adapter.pool_config.pool_block is True

    def test_initialization_with_config(self):
        """Test adapter with PoolConfig."""
        config = PoolConfig(
            pool_connections=15,
            pool_maxsize=15,
            retry_total=5,
        )
        adapter = TunedHTTPAdapter(config=config)

        assert adapter.pool_config.pool_connections == 15
        assert adapter.pool_config.retry_total == 5

    def test_get_stats(self):
        """Test getting adapter stats."""
        adapter = TunedHTTPAdapter()
        stats = adapter.get_stats()

        assert isinstance(stats, PoolStats)
        assert stats.requests_made == 0
        assert stats.errors == 0


class TestConnectionPoolManager:
    """Tests for ConnectionPoolManager."""

    @pytest.fixture
    def fresh_manager(self):
        """Create a fresh manager instance for testing."""
        # Reset singleton
        ConnectionPoolManager._instance = None
        manager = ConnectionPoolManager()
        yield manager
        # Cleanup
        manager.close_all()
        ConnectionPoolManager._instance = None

    def test_singleton_pattern(self, fresh_manager):
        """Test that manager is a singleton."""
        manager1 = ConnectionPoolManager()
        manager2 = ConnectionPoolManager()

        assert manager1 is manager2

    def test_set_default_strategy(self, fresh_manager):
        """Test setting default strategy."""
        fresh_manager.set_default_strategy(PoolStrategy.AGGRESSIVE)

        assert fresh_manager._strategy == PoolStrategy.AGGRESSIVE
        assert fresh_manager._default_config.pool_connections == 20

    def test_set_default_config(self, fresh_manager):
        """Test setting custom default config."""
        custom_config = PoolConfig(pool_connections=25)
        fresh_manager.set_default_config(custom_config)

        assert fresh_manager._strategy == PoolStrategy.CUSTOM
        assert fresh_manager._default_config.pool_connections == 25

    def test_get_session(self, fresh_manager):
        """Test getting a session for a host."""
        session = fresh_manager.get_session("https://api.example.com")

        assert session is not None
        # Session should be reused
        session2 = fresh_manager.get_session("https://api.example.com")
        assert session is session2

    def test_get_session_different_hosts(self, fresh_manager):
        """Test sessions for different hosts are separate."""
        session1 = fresh_manager.get_session("https://api1.example.com")
        session2 = fresh_manager.get_session("https://api2.example.com")

        assert session1 is not session2

    def test_configure_pool(self, fresh_manager):
        """Test configuring a specific pool."""
        config = PoolConfig(pool_connections=30)
        fresh_manager.configure_pool("https://custom.example.com", config)

        # Get session uses custom config
        session = fresh_manager.get_session("https://custom.example.com")
        assert session is not None

    def test_normalize_host(self, fresh_manager):
        """Test host normalization."""
        # Same host with different paths should be same pool
        session1 = fresh_manager.get_session("https://api.example.com/v1/resource")
        session2 = fresh_manager.get_session("https://api.example.com/v2/other")

        assert session1 is session2

    def test_close_pool(self, fresh_manager):
        """Test closing a specific pool."""
        fresh_manager.get_session("https://api.example.com")
        assert "https://api.example.com" in fresh_manager._pools

        fresh_manager.close_pool("https://api.example.com")
        assert "https://api.example.com" not in fresh_manager._pools

    def test_close_all(self, fresh_manager):
        """Test closing all pools."""
        fresh_manager.get_session("https://api1.example.com")
        fresh_manager.get_session("https://api2.example.com")
        assert len(fresh_manager._pools) == 2

        fresh_manager.close_all()
        assert len(fresh_manager._pools) == 0

    def test_get_stats(self, fresh_manager):
        """Test getting stats for a host."""
        fresh_manager.get_session("https://api.example.com")
        stats = fresh_manager.get_stats("https://api.example.com")

        assert stats is not None
        assert stats.host == "https://api.example.com"

    def test_get_stats_nonexistent(self, fresh_manager):
        """Test getting stats for nonexistent host."""
        stats = fresh_manager.get_stats("https://nonexistent.example.com")

        assert stats is None

    def test_get_all_stats(self, fresh_manager):
        """Test getting all stats."""
        fresh_manager.get_session("https://api1.example.com")
        fresh_manager.get_session("https://api2.example.com")

        all_stats = fresh_manager.get_all_stats()

        assert len(all_stats) == 2
        assert "https://api1.example.com" in all_stats
        assert "https://api2.example.com" in all_stats

    def test_optimize_for_host_low_volume(self, fresh_manager):
        """Test optimization for low volume."""
        config = fresh_manager.optimize_for_host("https://api.example.com", 60)

        assert config.pool_connections >= 5
        assert config.pool_block is False  # Low volume doesn't block

    def test_optimize_for_host_high_volume(self, fresh_manager):
        """Test optimization for high volume."""
        config = fresh_manager.optimize_for_host("https://api.example.com", 600)

        assert config.pool_connections >= 5
        assert config.pool_block is True  # High volume blocks

    def test_get_recommendations_empty(self, fresh_manager):
        """Test recommendations with no data."""
        recommendations = fresh_manager.get_recommendations()

        assert recommendations == []

    def test_thread_safety(self, fresh_manager):
        """Test thread-safe access to manager."""
        results = []

        def get_session(host: str):
            session = fresh_manager.get_session(host)
            results.append(session is not None)

        threads = [
            threading.Thread(target=get_session, args=(f"https://api{i}.example.com",))
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert all(results)
        assert len(fresh_manager._pools) == 10


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global manager before each test."""
        import spectryn.adapters.http.connection_pool as module

        module._pool_manager = None
        yield
        if module._pool_manager:
            module._pool_manager.close_all()
        module._pool_manager = None

    def test_get_pool_manager(self):
        """Test getting global pool manager."""
        manager = get_pool_manager()

        assert manager is not None
        assert isinstance(manager, ConnectionPoolManager)

    def test_configure_global_pools_strategy(self):
        """Test configuring global pools with strategy."""
        manager = configure_global_pools(strategy=PoolStrategy.AGGRESSIVE)

        assert manager._strategy == PoolStrategy.AGGRESSIVE

    def test_configure_global_pools_custom(self):
        """Test configuring global pools with custom config."""
        config = PoolConfig(pool_connections=25)
        manager = configure_global_pools(custom_config=config)

        assert manager._default_config.pool_connections == 25

    def test_get_session_for_host(self):
        """Test convenience function for getting session."""
        session = get_session_for_host("https://api.example.com")

        assert session is not None

    def test_get_pool_stats(self):
        """Test convenience function for getting stats."""
        get_session_for_host("https://api.example.com")
        stats = get_pool_stats()

        assert len(stats) >= 1


class TestTrackerAdapters:
    """Tests for pre-configured tracker adapters."""

    def test_create_jira_adapter(self):
        """Test Jira adapter creation."""
        adapter = create_jira_adapter()

        assert adapter.pool_config.pool_connections == 10
        assert adapter.pool_config.retry_total == 3
        assert 429 in adapter.pool_config.retry_status_forcelist

    def test_create_github_adapter(self):
        """Test GitHub adapter creation."""
        adapter = create_github_adapter()

        assert adapter.pool_config.pool_connections == 15
        assert adapter.pool_config.retry_total == 3

    def test_create_linear_adapter(self):
        """Test Linear adapter creation."""
        adapter = create_linear_adapter()

        assert adapter.pool_config.pool_connections == 10
        assert adapter.pool_config.retry_total == 3

    def test_create_azure_devops_adapter(self):
        """Test Azure DevOps adapter creation."""
        adapter = create_azure_devops_adapter()

        assert adapter.pool_config.pool_connections == 10
        assert adapter.pool_config.read_timeout == 45.0
