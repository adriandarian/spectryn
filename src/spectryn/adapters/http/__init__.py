"""
HTTP Utilities - Connection pooling, session management, and HTTP optimizations.
"""

from .connection_pool import (
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


__all__ = [
    "ConnectionPoolManager",
    "PoolConfig",
    "PoolStats",
    "PoolStrategy",
    "TunedHTTPAdapter",
    "configure_global_pools",
    "create_azure_devops_adapter",
    "create_github_adapter",
    "create_jira_adapter",
    "create_linear_adapter",
    "get_pool_manager",
    "get_pool_stats",
    "get_session_for_host",
]
