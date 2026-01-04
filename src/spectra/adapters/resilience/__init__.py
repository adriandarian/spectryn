"""
Resilience Adapters - Rate limiting, retry, and circuit breaker implementations.

Provides concrete implementations of the rate limiting port interfaces:
- TokenBucketRateLimiter: Token bucket algorithm rate limiter
- SlidingWindowRateLimiter: Sliding window rate limiter
- RetryPolicy: Configurable retry with multiple strategies
- CircuitBreaker: Circuit breaker for fault tolerance
- ResilienceManager: Unified facade combining all resilience features

These implementations work together to provide robust, centralized
resilience for HTTP API adapters.
"""

from .circuit_breaker import CircuitBreaker
from .rate_limiter import SlidingWindowRateLimiter, TokenBucketRateLimiter
from .resilience_manager import ResilienceManager, create_resilience_manager
from .retry_policy import RetryPolicy


__all__ = [
    # Circuit breaker
    "CircuitBreaker",
    # Unified manager
    "ResilienceManager",
    # Retry
    "RetryPolicy",
    # Rate limiters
    "SlidingWindowRateLimiter",
    "TokenBucketRateLimiter",
    "create_resilience_manager",
]
