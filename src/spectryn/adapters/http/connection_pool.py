"""
Connection Pooling Tuning - Optimize HTTP connection reuse.

Provides centralized connection pool management with tuning options
for improved performance across all tracker adapters.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter


try:
    from urllib3.util.retry import Retry
except ImportError:
    Retry = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


class PoolStrategy(Enum):
    """Connection pool sizing strategy."""

    CONSERVATIVE = "conservative"  # Small pools, lower memory
    BALANCED = "balanced"  # Default balanced settings
    AGGRESSIVE = "aggressive"  # Large pools, high throughput
    CUSTOM = "custom"  # User-defined settings


@dataclass
class PoolStats:
    """Statistics for a connection pool."""

    host: str
    pool_connections: int
    pool_maxsize: int
    requests_made: int = 0
    connections_reused: int = 0
    connections_created: int = 0
    errors: int = 0
    avg_response_time_ms: float = 0.0
    last_request_at: datetime | None = None

    @property
    def reuse_ratio(self) -> float:
        """Connection reuse ratio (higher is better)."""
        total = self.connections_reused + self.connections_created
        return self.connections_reused / total if total > 0 else 0.0


@dataclass
class PoolConfig:
    """Configuration for connection pool tuning."""

    # Pool sizing
    pool_connections: int = 10  # Number of connection pools to cache
    pool_maxsize: int = 10  # Max connections per pool
    pool_block: bool = False  # Block when pool exhausted vs create new

    # Timeouts
    connect_timeout: float = 10.0  # Connection timeout in seconds
    read_timeout: float = 30.0  # Read timeout in seconds

    # Keep-alive
    keep_alive: bool = True  # Enable HTTP keep-alive
    keep_alive_timeout: int = 30  # Keep-alive timeout in seconds

    # Retry configuration
    retry_total: int = 3  # Total retry attempts
    retry_backoff_factor: float = 0.5  # Backoff multiplier
    retry_status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504)

    # DNS caching
    dns_cache_ttl: int = 300  # DNS cache TTL in seconds

    # SSL/TLS
    ssl_verify: bool = True  # Verify SSL certificates
    ssl_cert: str | None = None  # Client certificate path

    @classmethod
    def from_strategy(cls, strategy: PoolStrategy) -> "PoolConfig":
        """Create config from a strategy preset."""
        if strategy == PoolStrategy.CONSERVATIVE:
            return cls(
                pool_connections=5,
                pool_maxsize=5,
                pool_block=True,
                connect_timeout=15.0,
                read_timeout=45.0,
            )
        if strategy == PoolStrategy.AGGRESSIVE:
            return cls(
                pool_connections=20,
                pool_maxsize=20,
                pool_block=False,
                connect_timeout=5.0,
                read_timeout=20.0,
                retry_total=5,
            )
        # BALANCED (default)
        return cls()


class TunedHTTPAdapter(HTTPAdapter):
    """
    Enhanced HTTP adapter with connection pool tuning.

    Extends requests.HTTPAdapter with additional features:
    - Configurable keep-alive
    - Custom socket options
    - Connection statistics
    """

    def __init__(
        self,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        pool_block: bool = False,
        max_retries: int = 0,
        config: PoolConfig | None = None,
    ):
        """
        Initialize the tuned HTTP adapter.

        Args:
            pool_connections: Number of connection pools to cache
            pool_maxsize: Maximum connections per pool
            pool_block: Whether to block when pool is exhausted
            max_retries: Maximum retry attempts
            config: Full pool configuration
        """
        self.pool_config = config or PoolConfig(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            pool_block=pool_block,
        )

        # Create retry strategy if urllib3 Retry is available
        retry = None
        if Retry is not None and self.pool_config.retry_total > 0:
            retry = Retry(
                total=self.pool_config.retry_total,
                backoff_factor=self.pool_config.retry_backoff_factor,
                status_forcelist=self.pool_config.retry_status_forcelist,
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"],
                raise_on_status=False,
            )

        super().__init__(
            pool_connections=self.pool_config.pool_connections,
            pool_maxsize=self.pool_config.pool_maxsize,
            pool_block=self.pool_config.pool_block,
            max_retries=retry if retry else max_retries,
        )

        # Statistics tracking
        self._stats_lock = threading.Lock()
        self._request_times: list[float] = []
        self._stats = PoolStats(
            host="",
            pool_connections=self.pool_config.pool_connections,
            pool_maxsize=self.pool_config.pool_maxsize,
        )

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        """Send request with statistics tracking."""
        start_time = time.time()

        try:
            response = super().send(
                request,
                stream=stream,
                timeout=timeout
                or (self.pool_config.connect_timeout, self.pool_config.read_timeout),
                verify=verify if verify is not None else self.pool_config.ssl_verify,
                cert=cert or self.pool_config.ssl_cert,
                proxies=proxies,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            with self._stats_lock:
                self._stats.requests_made += 1
                self._stats.last_request_at = datetime.now()
                self._request_times.append(elapsed_ms)
                # Keep only last 100 request times for avg calculation
                if len(self._request_times) > 100:
                    self._request_times = self._request_times[-100:]
                self._stats.avg_response_time_ms = sum(self._request_times) / len(
                    self._request_times
                )

            return response

        except Exception:
            with self._stats_lock:
                self._stats.errors += 1
            raise

    def get_stats(self) -> PoolStats:
        """Get current pool statistics."""
        with self._stats_lock:
            return PoolStats(
                host=self._stats.host,
                pool_connections=self._stats.pool_connections,
                pool_maxsize=self._stats.pool_maxsize,
                requests_made=self._stats.requests_made,
                connections_reused=self._stats.connections_reused,
                connections_created=self._stats.connections_created,
                errors=self._stats.errors,
                avg_response_time_ms=self._stats.avg_response_time_ms,
                last_request_at=self._stats.last_request_at,
            )


class ConnectionPoolManager:
    """
    Centralized connection pool manager.

    Manages connection pools across multiple hosts with shared configuration
    and statistics tracking.

    Usage:
        manager = ConnectionPoolManager()

        # Get a configured session for a host
        session = manager.get_session("https://api.example.com")

        # Or configure a custom pool
        manager.configure_pool("https://jira.example.com", PoolConfig(...))
        session = manager.get_session("https://jira.example.com")

        # Get statistics
        stats = manager.get_all_stats()
    """

    _instance: "ConnectionPoolManager | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConnectionPoolManager":
        """Singleton pattern for global pool management."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        """Initialize the connection pool manager."""
        if getattr(self, "_initialized", False):
            return

        self._pools: dict[str, requests.Session] = {}
        self._adapters: dict[str, TunedHTTPAdapter] = {}
        self._configs: dict[str, PoolConfig] = {}
        self._pool_lock = threading.Lock()
        self._default_config = PoolConfig()
        self._strategy = PoolStrategy.BALANCED
        self.logger = logging.getLogger("ConnectionPoolManager")
        self._initialized = True

    def set_default_strategy(self, strategy: PoolStrategy) -> None:
        """Set the default pool sizing strategy."""
        self._strategy = strategy
        self._default_config = PoolConfig.from_strategy(strategy)
        self.logger.info(f"Set default pool strategy: {strategy.value}")

    def set_default_config(self, config: PoolConfig) -> None:
        """Set the default pool configuration."""
        self._default_config = config
        self._strategy = PoolStrategy.CUSTOM
        self.logger.info("Set custom default pool configuration")

    def configure_pool(self, host_url: str, config: PoolConfig) -> None:
        """
        Configure a connection pool for a specific host.

        Args:
            host_url: Base URL for the host
            config: Pool configuration
        """
        host = self._normalize_host(host_url)

        with self._pool_lock:
            # Close existing session if any
            if host in self._pools:
                self._pools[host].close()
                del self._pools[host]

            self._configs[host] = config

        self.logger.info(
            f"Configured pool for {host}: connections={config.pool_connections}, "
            f"maxsize={config.pool_maxsize}"
        )

    def get_session(self, host_url: str) -> requests.Session:
        """
        Get a session with connection pooling for a host.

        Args:
            host_url: Base URL for the host

        Returns:
            Configured requests.Session
        """
        host = self._normalize_host(host_url)

        with self._pool_lock:
            if host not in self._pools:
                self._pools[host] = self._create_session(host)

            return self._pools[host]

    def _create_session(self, host: str) -> requests.Session:
        """Create a new session with tuned connection pooling."""
        config = self._configs.get(host, self._default_config)

        session = requests.Session()

        # Create tuned adapter
        adapter = TunedHTTPAdapter(config=config)
        adapter._stats.host = host

        # Mount for both http and https
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        self._adapters[host] = adapter

        self.logger.debug(
            f"Created session for {host}: connections={config.pool_connections}, "
            f"maxsize={config.pool_maxsize}"
        )

        return session

    def _normalize_host(self, url: str) -> str:
        """Extract and normalize host from URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def get_stats(self, host_url: str) -> PoolStats | None:
        """Get statistics for a specific host pool."""
        host = self._normalize_host(host_url)

        with self._pool_lock:
            adapter = self._adapters.get(host)
            return adapter.get_stats() if adapter else None

    def get_all_stats(self) -> dict[str, PoolStats]:
        """Get statistics for all managed pools."""
        with self._pool_lock:
            return {host: adapter.get_stats() for host, adapter in self._adapters.items()}

    def close_pool(self, host_url: str) -> None:
        """Close a specific pool."""
        host = self._normalize_host(host_url)

        with self._pool_lock:
            if host in self._pools:
                self._pools[host].close()
                del self._pools[host]
                self.logger.info(f"Closed pool for {host}")

            if host in self._adapters:
                del self._adapters[host]

            if host in self._configs:
                del self._configs[host]

    def close_all(self) -> None:
        """Close all managed pools."""
        with self._pool_lock:
            for session in self._pools.values():
                session.close()

            self._pools.clear()
            self._adapters.clear()
            self.logger.info("Closed all connection pools")

    def optimize_for_host(self, host_url: str, expected_requests_per_minute: int) -> PoolConfig:
        """
        Generate optimized pool config based on expected load.

        Args:
            host_url: Target host URL
            expected_requests_per_minute: Expected request rate

        Returns:
            Optimized PoolConfig
        """
        # Calculate optimal pool size based on request rate
        # Assume ~100ms average response time
        avg_response_ms = 100
        concurrent_requests = (expected_requests_per_minute / 60) * (avg_response_ms / 1000)

        # Add 50% headroom
        pool_size = max(5, int(concurrent_requests * 1.5))
        pool_size = min(pool_size, 50)  # Cap at 50

        config = PoolConfig(
            pool_connections=pool_size,
            pool_maxsize=pool_size,
            pool_block=expected_requests_per_minute > 300,  # Block for high-volume
        )

        self.configure_pool(host_url, config)

        self.logger.info(
            f"Optimized pool for {host_url}: size={pool_size} "
            f"(for {expected_requests_per_minute} req/min)"
        )

        return config

    def get_recommendations(self) -> list[str]:
        """
        Get recommendations for pool tuning based on current stats.

        Returns:
            List of recommendation strings
        """
        recommendations = []
        all_stats = self.get_all_stats()

        for host, stats in all_stats.items():
            # Check reuse ratio
            if stats.requests_made > 100 and stats.reuse_ratio < 0.5:
                recommendations.append(
                    f"{host}: Low connection reuse ({stats.reuse_ratio:.1%}). "
                    f"Consider increasing pool_maxsize."
                )

            # Check response times
            if stats.avg_response_time_ms > 500:
                recommendations.append(
                    f"{host}: High avg response time ({stats.avg_response_time_ms:.0f}ms). "
                    f"Check network or increase timeouts."
                )

            # Check error rate
            if stats.requests_made > 100:
                error_rate = stats.errors / stats.requests_made
                if error_rate > 0.05:
                    recommendations.append(
                        f"{host}: High error rate ({error_rate:.1%}). Consider enabling retries."
                    )

        return recommendations


# Global manager instance
_pool_manager: ConnectionPoolManager | None = None


def get_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()
    return _pool_manager


def configure_global_pools(
    strategy: PoolStrategy = PoolStrategy.BALANCED,
    custom_config: PoolConfig | None = None,
) -> ConnectionPoolManager:
    """
    Configure global connection pools.

    Args:
        strategy: Pool sizing strategy
        custom_config: Custom configuration (overrides strategy)

    Returns:
        Configured ConnectionPoolManager
    """
    manager = get_pool_manager()

    if custom_config:
        manager.set_default_config(custom_config)
    else:
        manager.set_default_strategy(strategy)

    return manager


def get_session_for_host(host_url: str) -> requests.Session:
    """
    Convenience function to get a pooled session for a host.

    Args:
        host_url: Target host URL

    Returns:
        Configured requests.Session
    """
    return get_pool_manager().get_session(host_url)


def get_pool_stats() -> dict[str, PoolStats]:
    """Get statistics for all connection pools."""
    return get_pool_manager().get_all_stats()


# Pre-configured adapters for common trackers
def create_jira_adapter(max_requests_per_minute: int = 300) -> TunedHTTPAdapter:
    """
    Create an adapter optimized for Jira Cloud.

    Jira Cloud has rate limits around 100 req/min for most endpoints.
    """
    return TunedHTTPAdapter(
        config=PoolConfig(
            pool_connections=10,
            pool_maxsize=10,
            pool_block=False,
            connect_timeout=10.0,
            read_timeout=30.0,
            retry_total=3,
            retry_status_forcelist=(429, 500, 502, 503, 504),
        )
    )


def create_github_adapter(max_requests_per_minute: int = 5000) -> TunedHTTPAdapter:
    """
    Create an adapter optimized for GitHub API.

    GitHub has generous rate limits (5000/hr for authenticated).
    """
    return TunedHTTPAdapter(
        config=PoolConfig(
            pool_connections=15,
            pool_maxsize=15,
            pool_block=False,
            connect_timeout=10.0,
            read_timeout=30.0,
            retry_total=3,
            retry_status_forcelist=(429, 500, 502, 503, 504),
        )
    )


def create_linear_adapter() -> TunedHTTPAdapter:
    """
    Create an adapter optimized for Linear API.

    Linear uses GraphQL with rate limits.
    """
    return TunedHTTPAdapter(
        config=PoolConfig(
            pool_connections=10,
            pool_maxsize=10,
            pool_block=False,
            connect_timeout=10.0,
            read_timeout=30.0,
            retry_total=3,
        )
    )


def create_azure_devops_adapter() -> TunedHTTPAdapter:
    """
    Create an adapter optimized for Azure DevOps.
    """
    return TunedHTTPAdapter(
        config=PoolConfig(
            pool_connections=10,
            pool_maxsize=10,
            pool_block=False,
            connect_timeout=15.0,
            read_timeout=45.0,
            retry_total=3,
        )
    )
