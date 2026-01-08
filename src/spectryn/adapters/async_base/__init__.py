"""
Async Base - HTTP client infrastructure with rate limiting.

This module provides the foundation for API clients:
- BaseHttpClient: Synchronous HTTP client base with retry and rate limiting
- TokenBucketRateLimiter: Synchronous token bucket rate limiter (base class)
- JiraRateLimiter, GitHubRateLimiter, LinearRateLimiter: API-specific rate limiters
- AsyncRateLimiter: Async-compatible token bucket rate limiter
- AsyncHttpClient: Base async HTTP client with retry and rate limiting
- Parallel execution utilities for batch operations
- Bounded concurrency with per-tracker limits and ordering guarantees

Requires aiohttp for async features: pip install aiohttp
"""

from .bounded_concurrency import (
    DEFAULT_TRACKER_LIMITS,
    AsyncBoundedExecutor,
    BoundedExecutor,
    ConcurrencyStats,
    OrderedTaskQueue,
    PrioritizedTask,
    Priority,
    ResourceLock,
    TrackerSemaphore,
    create_async_bounded_executor,
    create_bounded_executor,
)
from .http_client import AsyncHttpClient
from .http_client_sync import BaseHttpClient
from .parallel import (
    ParallelExecutor,
    ParallelResult,
    batch_execute,
    gather_with_limit,
    run_parallel,
)
from .rate_limiter import AsyncRateLimiter
from .retry_utils import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
    get_retry_after,
    should_retry,
)
from .token_bucket import (
    GitHubRateLimiter,
    JiraRateLimiter,
    LinearRateLimiter,
    TokenBucketRateLimiter,
)


__all__ = [
    "DEFAULT_TRACKER_LIMITS",
    "RETRYABLE_STATUS_CODES",
    "AsyncBoundedExecutor",
    "AsyncHttpClient",
    "AsyncRateLimiter",
    "BaseHttpClient",
    "BoundedExecutor",
    "ConcurrencyStats",
    "GitHubRateLimiter",
    "JiraRateLimiter",
    "LinearRateLimiter",
    "OrderedTaskQueue",
    "ParallelExecutor",
    "ParallelResult",
    "PrioritizedTask",
    "Priority",
    "ResourceLock",
    "TokenBucketRateLimiter",
    "TrackerSemaphore",
    "batch_execute",
    "calculate_delay",
    "create_async_bounded_executor",
    "create_bounded_executor",
    "gather_with_limit",
    "get_retry_after",
    "run_parallel",
    "should_retry",
]
