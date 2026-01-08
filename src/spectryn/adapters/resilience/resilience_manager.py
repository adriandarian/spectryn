"""
Resilience Manager - Unified facade combining rate limiting, retry, and circuit breaker.

Provides a single interface for adapters to use all resilience features together:
- Rate limiting with token bucket or sliding window
- Retry with configurable backoff strategies
- Circuit breaker for fault tolerance

This is the main class adapters should use for resilient HTTP requests.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar

from spectryn.core.ports.rate_limiting import (
    CircuitBreakerConfig,
    CircuitBreakerPort,
    CircuitOpenError,
    CircuitState,
    RateLimitConfig,
    RateLimitContext,
    RateLimiterPort,
    RateLimitError,
    RateLimitStats,
    ResiliencePort,
    RetryAttempt,
    RetryConfig,
    RetryExhaustedError,
    RetryPolicyPort,
    TrackerRateLimits,
    TrackerType,
    get_tracker_preset,
    parse_retry_after,
)

from .circuit_breaker import CircuitBreaker
from .rate_limiter import SlidingWindowRateLimiter, TokenBucketRateLimiter
from .retry_policy import RetryPolicy


# Type variable for generic return types
T = TypeVar("T")


class ResilienceManager(ResiliencePort):
    """
    Unified resilience manager combining rate limiting, retry, and circuit breaker.

    This is the main interface adapters should use for resilient HTTP requests.
    It coordinates all three resilience mechanisms to provide robust API interaction.

    Order of operations for each request:
    1. Circuit breaker check (fail fast if open)
    2. Rate limiter acquisition (wait for token)
    3. Execute request
    4. Update circuit breaker (success/failure)
    5. Update rate limiter (from response headers)
    6. Retry if needed (with backoff)

    Example:
        >>> from spectryn.core.ports.rate_limiting import TrackerType
        >>>
        >>> # Create from tracker preset
        >>> manager = create_resilience_manager(TrackerType.JIRA)
        >>>
        >>> # Execute a request with full resilience
        >>> def make_request():
        ...     response = requests.get(url)
        ...     if not response.ok:
        ...         raise RequestError(response.status_code)
        ...     return response.json()
        >>>
        >>> result = manager.execute(make_request)

    The manager handles:
    - Waiting for rate limit tokens
    - Retrying on transient failures
    - Opening circuit on repeated failures
    - Adjusting rate based on 429 responses
    """

    def __init__(
        self,
        rate_limiter: RateLimiterPort,
        retry_policy: RetryPolicyPort,
        circuit_breaker: CircuitBreakerPort | None = None,
        logger_name: str | None = None,
    ):
        """
        Initialize the resilience manager.

        Args:
            rate_limiter: Rate limiter implementation
            retry_policy: Retry policy implementation
            circuit_breaker: Optional circuit breaker
            logger_name: Optional custom logger name
        """
        self._rate_limiter = rate_limiter
        self._retry_policy = retry_policy
        self._circuit_breaker = circuit_breaker
        self._logger = logging.getLogger(logger_name or "ResilienceManager")

        # Statistics
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0
        self._circuit_rejections = 0

    def execute(
        self,
        operation: Callable[[], T],
        context: RateLimitContext | None = None,
    ) -> T:
        """
        Execute an operation with full resilience.

        Applies rate limiting, retry with backoff, and circuit breaker
        protection to the operation.

        Args:
            operation: Callable that performs the actual request.
                Should raise an exception on failure, return result on success.
            context: Optional request context for logging and stats

        Returns:
            Result from the operation

        Raises:
            CircuitOpenError: If circuit breaker is open
            RateLimitError: If rate limit timeout exceeded
            RetryExhaustedError: If all retries exhausted
        """
        self._total_executions += 1
        self._retry_policy.reset()

        # Create context if not provided
        if context is None:
            context = RateLimitContext()

        # Phase 1: Circuit breaker check
        if self._circuit_breaker is not None:
            try:
                if not self._circuit_breaker.allow_request():
                    self._circuit_rejections += 1
                    raise CircuitOpenError("Circuit breaker is open")
            except CircuitOpenError:
                self._circuit_rejections += 1
                raise

        last_exception: Exception | None = None

        for attempt in range(self._retry_policy.config.max_retries + 1):
            # Phase 2: Rate limiting
            acquired = self._rate_limiter.acquire(
                context=context,
                timeout=self._retry_policy.config.timeout,
            )
            if not acquired:
                raise RateLimitError(
                    "Rate limit acquisition timeout",
                    context=context,
                )

            # Phase 3: Execute request
            start_time = time.monotonic()
            try:
                result = operation()

                # Success!
                elapsed_ms = (time.monotonic() - start_time) * 1000
                context.response_time_ms = elapsed_ms

                # Update circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_success()

                self._successful_executions += 1
                return result

            except Exception as e:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                context.response_time_ms = elapsed_ms

                # Extract status code if available
                status_code = getattr(e, "status_code", None)
                if status_code is None:
                    status_code = getattr(e, "response", {})
                    if hasattr(status_code, "status_code"):
                        status_code = status_code.status_code
                    else:
                        status_code = None

                last_exception = e

                # Update rate limiter with response info
                headers = getattr(e, "headers", {}) or {}
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    headers = dict(e.response.headers)

                self._rate_limiter.update_from_response(
                    status_code=status_code or 500,
                    headers=headers,
                    context=context,
                )

                # Update circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure(status_code)

                # Check if this is the last attempt (max retries exceeded)
                is_last_attempt = attempt >= self._retry_policy.config.max_retries

                # Check if we should retry
                if not self._retry_policy.should_retry(
                    status_code=status_code,
                    exception=e,
                    attempt=attempt,
                ):
                    self._failed_executions += 1
                    # If max retries exhausted, raise RetryExhaustedError
                    if is_last_attempt:
                        raise RetryExhaustedError(
                            f"All {self._retry_policy.config.max_retries + 1} attempts failed",
                            attempts=self._retry_policy.get_attempts(),
                            last_exception=e,
                        )
                    # Otherwise it's a non-retryable error, re-raise original
                    raise

                # Calculate retry delay
                retry_after = parse_retry_after(headers) if headers else None
                delay = self._retry_policy.get_delay(attempt, retry_after)

                # Record retry attempt
                self._retry_policy.record_attempt(
                    RetryAttempt(
                        attempt=attempt,
                        delay=delay,
                        reason=str(e),
                        timestamp=datetime.now(),
                    )
                )

                self._logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s..."
                )

                # Wait before retry
                time.sleep(delay)

        # All retries exhausted
        self._failed_executions += 1
        raise RetryExhaustedError(
            f"All {self._retry_policy.config.max_retries + 1} attempts failed",
            attempts=self._retry_policy.get_attempts(),
            last_exception=last_exception,
        )

    def get_rate_limiter(self) -> RateLimiterPort:
        """Get the underlying rate limiter."""
        return self._rate_limiter

    def get_retry_policy(self) -> RetryPolicyPort:
        """Get the underlying retry policy."""
        return self._retry_policy

    def get_circuit_breaker(self) -> CircuitBreakerPort | None:
        """Get the circuit breaker (if configured)."""
        return self._circuit_breaker

    def get_stats(self) -> RateLimitStats:
        """Get combined statistics."""
        stats = self._rate_limiter.get_stats()

        # Add manager-level stats
        stats.total_retries = len(self._retry_policy.get_attempts())

        if self._circuit_breaker is not None:
            cb_stats = self._circuit_breaker.get_stats()
            stats.circuit_state = CircuitState(cb_stats["state"])
            stats.circuit_breaker_rejections = cb_stats["total_rejections"]
            stats.consecutive_failures = cb_stats["failure_count"]
            stats.consecutive_successes = cb_stats["success_count"]

        return stats

    def get_detailed_stats(self) -> dict[str, Any]:
        """Get detailed statistics from all components."""
        result: dict[str, Any] = {
            "manager": {
                "total_executions": self._total_executions,
                "successful_executions": self._successful_executions,
                "failed_executions": self._failed_executions,
                "circuit_rejections": self._circuit_rejections,
                "success_rate": (
                    self._successful_executions / self._total_executions
                    if self._total_executions > 0
                    else 0.0
                ),
            },
            "rate_limiter": {
                "type": type(self._rate_limiter).__name__,
                "config": {
                    "requests_per_second": self._rate_limiter.config.requests_per_second,
                    "burst_size": self._rate_limiter.config.burst_size,
                    "adaptive": self._rate_limiter.config.adaptive,
                },
                "stats": {
                    "total_requests": self._rate_limiter.get_stats().total_requests,
                    "total_wait_time": self._rate_limiter.get_stats().total_wait_time,
                    "rate_limited_count": self._rate_limiter.get_stats().rate_limited_count,
                    "current_rate": self._rate_limiter.get_stats().current_rate,
                },
            },
            "retry_policy": {
                "config": {
                    "max_retries": self._retry_policy.config.max_retries,
                    "initial_delay": self._retry_policy.config.initial_delay,
                    "max_delay": self._retry_policy.config.max_delay,
                    "strategy": self._retry_policy.config.strategy.value,
                },
                "attempts": [
                    {
                        "attempt": a.attempt,
                        "delay": a.delay,
                        "reason": a.reason,
                        "timestamp": a.timestamp.isoformat(),
                    }
                    for a in self._retry_policy.get_attempts()
                ],
            },
        }

        if self._circuit_breaker is not None:
            result["circuit_breaker"] = self._circuit_breaker.get_stats()

        return result

    def reset(self) -> None:
        """Reset all components to initial state."""
        self._rate_limiter.reset()
        self._retry_policy.reset()
        if self._circuit_breaker is not None:
            self._circuit_breaker.reset()
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0
        self._circuit_rejections = 0


def create_resilience_manager(
    tracker_type: TrackerType | str,
    rate_limit_config: RateLimitConfig | None = None,
    retry_config: RetryConfig | None = None,
    circuit_breaker_config: CircuitBreakerConfig | None = None,
    use_sliding_window: bool = False,
    enable_circuit_breaker: bool = True,
    logger_name: str | None = None,
) -> ResilienceManager:
    """
    Create a ResilienceManager from tracker type or custom config.

    This is the recommended way to create a resilience manager, as it
    uses sensible defaults for known trackers while allowing customization.

    Args:
        tracker_type: Tracker type (TrackerType enum or string name)
        rate_limit_config: Override rate limit config (uses preset if None)
        retry_config: Override retry config (uses preset if None)
        circuit_breaker_config: Override circuit breaker config (uses preset if None)
        use_sliding_window: Use sliding window instead of token bucket
        enable_circuit_breaker: Whether to enable circuit breaker
        logger_name: Optional custom logger name

    Returns:
        Configured ResilienceManager

    Example:
        >>> # Use preset for Jira
        >>> manager = create_resilience_manager(TrackerType.JIRA)
        >>>
        >>> # Use preset with custom retry
        >>> manager = create_resilience_manager(
        ...     TrackerType.GITHUB,
        ...     retry_config=RetryConfig(max_retries=5),
        ... )
        >>>
        >>> # Fully custom configuration
        >>> manager = create_resilience_manager(
        ...     TrackerType.CUSTOM,
        ...     rate_limit_config=RateLimitConfig(requests_per_second=20.0),
        ...     retry_config=RetryConfig(strategy=RetryStrategy.LINEAR),
        ...     circuit_breaker_config=CircuitBreakerConfig(failure_threshold=10),
        ... )
    """
    # Get preset for tracker type
    if isinstance(tracker_type, str):
        try:
            tracker_type = TrackerType(tracker_type.lower())
        except ValueError:
            tracker_type = TrackerType.CUSTOM

    preset = get_tracker_preset(tracker_type)

    # Use provided configs or fall back to preset
    rate_config = rate_limit_config or preset.rate_limit
    r_config = retry_config or preset.retry
    cb_config = circuit_breaker_config or preset.circuit_breaker

    # Create rate limiter
    if use_sliding_window:
        rate_limiter: RateLimiterPort = SlidingWindowRateLimiter(
            rate_config,
            logger_name=f"{logger_name or tracker_type.value}.RateLimiter",
        )
    else:
        rate_limiter = TokenBucketRateLimiter(
            rate_config,
            logger_name=f"{logger_name or tracker_type.value}.RateLimiter",
        )

    # Create retry policy
    retry_policy = RetryPolicy(
        r_config,
        logger_name=f"{logger_name or tracker_type.value}.Retry",
    )

    # Create circuit breaker if enabled
    circuit_breaker: CircuitBreakerPort | None = None
    if enable_circuit_breaker and cb_config is not None:
        circuit_breaker = CircuitBreaker(
            cb_config,
            logger_name=f"{logger_name or tracker_type.value}.CircuitBreaker",
        )

    return ResilienceManager(
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
        logger_name=logger_name or f"{tracker_type.value}.Resilience",
    )


def create_from_preset(preset: TrackerRateLimits) -> ResilienceManager:
    """
    Create a ResilienceManager directly from a preset configuration.

    Args:
        preset: TrackerRateLimits preset

    Returns:
        Configured ResilienceManager
    """
    rate_limiter: RateLimiterPort = TokenBucketRateLimiter(preset.rate_limit)
    retry_policy = RetryPolicy(preset.retry)

    circuit_breaker: CircuitBreakerPort | None = None
    if preset.circuit_breaker is not None:
        circuit_breaker = CircuitBreaker(preset.circuit_breaker)

    return ResilienceManager(
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        circuit_breaker=circuit_breaker,
    )
