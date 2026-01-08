"""
Adapters - Concrete implementations of ports.

Subpackages organized by function:
- Trackers: jira/, github/, azure_devops/, linear/, confluence/
- Parsers: parsers/ (markdown, yaml, notion)
- Formatters: formatters/ (adf, markdown)
- Infrastructure: async_base/, cache/, config/
"""

# Trackers
# Infrastructure - Cache
from .asana import AsanaAdapter
from .cache import (
    CacheBackend,
    CacheEntry,
    CacheKeyBuilder,
    CacheManager,
    CacheStats,
    FileCache,
    MemoryCache,
)

# Infrastructure - Config
from .config import EnvironmentConfigProvider
from .formatters import ADFFormatter
from .jira import BatchOperation, BatchResult, JiraAdapter, JiraBatchClient

# LLM Providers (optional, requires anthropic/openai/google-generativeai)
from .llm import (
    LLMConfig,
    LLMManager,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMRole,
    create_llm_manager,
)

# Parsers & Formatters
from .parsers import MarkdownParser


# Infrastructure - Async (optional, requires aiohttp)
try:
    from .async_base import (
        AsyncHttpClient,
        AsyncRateLimiter,
        ParallelExecutor,
        ParallelResult,
        batch_execute,
        gather_with_limit,
        run_parallel,
    )

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False

# WebSocket (real-time sync updates)
# Resilience (rate limiting, retry, circuit breaker)
from .resilience import (
    CircuitBreaker,
    ResilienceManager,
    RetryPolicy,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    create_resilience_manager,
)
from .websocket import (
    AioHttpWebSocketServer,
    SimpleWebSocketServer,
    SyncEventBroadcaster,
    WebSocketBridge,
    create_websocket_server,
)


__all__ = [
    "ASYNC_AVAILABLE",
    "ADFFormatter",
    # WebSocket
    "AioHttpWebSocketServer",
    "AsanaAdapter",
    "BatchOperation",
    "BatchResult",
    "CacheBackend",
    "CacheEntry",
    "CacheKeyBuilder",
    "CacheManager",
    "CacheStats",
    # Resilience
    "CircuitBreaker",
    # Infrastructure
    "EnvironmentConfigProvider",
    "FileCache",
    # Trackers
    "JiraAdapter",
    "JiraBatchClient",
    # LLM
    "LLMConfig",
    "LLMManager",
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "LLMRole",
    # Parsers & Formatters
    "MarkdownParser",
    "MemoryCache",
    "ResilienceManager",
    "RetryPolicy",
    "SimpleWebSocketServer",
    "SlidingWindowRateLimiter",
    "SyncEventBroadcaster",
    "TokenBucketRateLimiter",
    "WebSocketBridge",
    "create_llm_manager",
    "create_resilience_manager",
    "create_websocket_server",
]
