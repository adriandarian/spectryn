"""
Rate Limiter Implementations - Token bucket and sliding window rate limiters.

Provides concrete implementations of RateLimiterPort:
- TokenBucketRateLimiter: Classic token bucket algorithm
- SlidingWindowRateLimiter: Sliding window counter algorithm
"""

from __future__ import annotations

import collections
import contextlib
import logging
import threading
import time

from spectra.core.ports.rate_limiting import (
    RateLimitConfig,
    RateLimitContext,
    RateLimiterPort,
    RateLimitStats,
)


class TokenBucketRateLimiter(RateLimiterPort):
    """
    Token bucket rate limiter implementation.

    Uses a token bucket algorithm where:
    - Tokens are added at a steady rate (requests_per_second)
    - Each request consumes one token
    - If no tokens are available, the request waits
    - Bucket has a maximum capacity (burst_size) to allow short bursts

    This is ideal for APIs with burst capacity but sustained rate limits.

    Example:
        >>> config = RateLimitConfig(requests_per_second=5.0, burst_size=10)
        >>> limiter = TokenBucketRateLimiter(config)
        >>> limiter.acquire()  # Blocks until token available
        >>> # Make API request...
        >>> limiter.update_from_response(200, {"X-RateLimit-Remaining": "95"})
    """

    def __init__(
        self,
        config: RateLimitConfig,
        logger_name: str | None = None,
    ):
        """
        Initialize the token bucket rate limiter.

        Args:
            config: Rate limit configuration
            logger_name: Optional custom logger name
        """
        self._config = config
        self._current_rate = config.requests_per_second

        # Token bucket state
        self._tokens = float(config.burst_size)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0
        self._total_retries = 0
        self._rate_limited_count = 0
        self._response_times: list[float] = []
        self._max_response_time = 0.0

        # Rate limit header tracking
        self._remaining: int | None = None
        self._reset_at: float | None = None
        self._limit: int | None = None

        self._logger = logging.getLogger(logger_name or "TokenBucketRateLimiter")

    @property
    def config(self) -> RateLimitConfig:
        """Get the rate limit configuration."""
        return self._config

    def acquire(
        self,
        context: RateLimitContext | None = None,
        timeout: float | None = None,
    ) -> bool:
        """
        Acquire a token, waiting if necessary.

        Args:
            context: Optional context (unused in token bucket)
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if token acquired, False if timeout reached
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill_tokens()

                # Check if we should wait for API-provided reset time
                if self._should_wait_for_api_limit():
                    wait_time = self._api_wait_time()
                    if wait_time > 0:
                        self._logger.warning(
                            f"Rate limit nearly exhausted, waiting {wait_time:.1f}s"
                        )
                        self._total_wait_time += wait_time
                        self._lock.release()
                        try:
                            time.sleep(wait_time)
                        finally:
                            self._lock.acquire()
                        continue

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._total_requests += 1
                    return True

                # Calculate wait time until next token
                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self._current_rate

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0.01:  # Only log if wait is noticeable
                self._logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def try_acquire(self, context: RateLimitContext | None = None) -> bool:
        """
        Try to acquire a token without waiting.

        Args:
            context: Optional context (unused in token bucket)

        Returns:
            True if token acquired, False if not available
        """
        with self._lock:
            self._refill_tokens()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._total_requests += 1
                return True

            return False

    def update_from_response(
        self,
        status_code: int,
        headers: dict[str, str],
        context: RateLimitContext | None = None,
    ) -> None:
        """
        Update rate limiter based on API response.

        Parses rate limit headers and adjusts rate if needed.

        Args:
            status_code: HTTP status code
            headers: Response headers
            context: Request context
        """
        with self._lock:
            # Parse rate limit headers
            remaining = headers.get(self._config.remaining_header)
            if remaining is not None:
                try:
                    self._remaining = int(remaining)
                    if self._remaining <= 5:
                        self._logger.warning(
                            f"Rate limit nearly exhausted: {self._remaining} remaining"
                        )
                except ValueError:
                    pass

            reset = headers.get(self._config.reset_header)
            if reset is not None:
                with contextlib.suppress(ValueError):
                    self._reset_at = float(reset)

            limit = headers.get(self._config.limit_header)
            if limit is not None:
                with contextlib.suppress(ValueError):
                    self._limit = int(limit)

            # Track response time if provided in context
            if context and context.response_time_ms is not None:
                self._response_times.append(context.response_time_ms)
                self._max_response_time = max(self._max_response_time, context.response_time_ms)
                # Keep only last 100 response times
                if len(self._response_times) > 100:
                    self._response_times = self._response_times[-100:]

            # Adaptive rate adjustment on 429
            if status_code == 429 and self._config.adaptive:
                self._rate_limited_count += 1
                old_rate = self._current_rate
                self._current_rate = max(
                    self._config.min_rate,
                    self._current_rate * self._config.rate_reduction_factor,
                )
                self._logger.warning(
                    f"Rate limited (429), reducing rate from "
                    f"{old_rate:.2f} to {self._current_rate:.2f} req/s"
                )

    def get_stats(self) -> RateLimitStats:
        """Get rate limiter statistics."""
        with self._lock:
            avg_response = (
                sum(self._response_times) / len(self._response_times)
                if self._response_times
                else 0.0
            )
            return RateLimitStats(
                total_requests=self._total_requests,
                total_wait_time=self._total_wait_time,
                total_retries=self._total_retries,
                rate_limited_count=self._rate_limited_count,
                current_rate=self._current_rate,
                available_tokens=self._tokens,
                avg_response_time_ms=avg_response,
                max_response_time_ms=self._max_response_time,
            )

    def reset(self) -> None:
        """Reset rate limiter to initial state."""
        with self._lock:
            self._tokens = float(self._config.burst_size)
            self._last_update = time.monotonic()
            self._current_rate = self._config.requests_per_second
            self._total_requests = 0
            self._total_wait_time = 0.0
            self._total_retries = 0
            self._rate_limited_count = 0
            self._response_times = []
            self._max_response_time = 0.0
            self._remaining = None
            self._reset_at = None
            self._limit = None

    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        # Add tokens based on elapsed time
        new_tokens = elapsed * self._current_rate
        self._tokens = min(self._config.burst_size, self._tokens + new_tokens)

    def _should_wait_for_api_limit(self) -> bool:
        """Check if we should wait based on API rate limit headers."""
        if self._remaining is None:
            return False
        return self._remaining <= 5

    def _api_wait_time(self) -> float:
        """Calculate wait time until API rate limit resets."""
        if self._reset_at is None:
            return 60.0  # Default wait if no reset time

        wait_time = self._reset_at - time.time()
        return max(0, wait_time)


class SlidingWindowRateLimiter(RateLimiterPort):
    """
    Sliding window rate limiter implementation.

    Uses a sliding window counter algorithm that tracks requests
    in a time window and blocks when the limit is reached.

    This provides smoother rate limiting than token bucket for
    APIs that use strict per-second or per-minute limits.

    Example:
        >>> config = RateLimitConfig(requests_per_second=10.0, window_seconds=1.0)
        >>> limiter = SlidingWindowRateLimiter(config)
        >>> limiter.acquire()  # Blocks if window limit reached
    """

    def __init__(
        self,
        config: RateLimitConfig,
        logger_name: str | None = None,
    ):
        """
        Initialize the sliding window rate limiter.

        Args:
            config: Rate limit configuration
            logger_name: Optional custom logger name
        """
        self._config = config
        self._current_rate = config.requests_per_second
        self._window_size = int(config.requests_per_second * config.window_seconds)

        # Sliding window state - stores request timestamps
        self._request_times: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0
        self._rate_limited_count = 0
        self._response_times: list[float] = []
        self._max_response_time = 0.0

        # Rate limit header tracking
        self._remaining: int | None = None
        self._reset_at: float | None = None

        self._logger = logging.getLogger(logger_name or "SlidingWindowRateLimiter")

    @property
    def config(self) -> RateLimitConfig:
        """Get the rate limit configuration."""
        return self._config

    def acquire(
        self,
        context: RateLimitContext | None = None,
        timeout: float | None = None,
    ) -> bool:
        """
        Acquire permission to make a request.

        Args:
            context: Optional context
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if acquired, False if timeout reached
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._clean_old_requests()

                if len(self._request_times) < self._window_size:
                    self._request_times.append(time.monotonic())
                    self._total_requests += 1
                    return True

                # Calculate wait time until oldest request expires
                oldest = self._request_times[0]
                wait_time = (oldest + self._config.window_seconds) - time.monotonic()

            if wait_time <= 0:
                continue  # Re-check after cleaning

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0.01:
                self._logger.debug(f"Rate limit: waiting {wait_time:.3f}s")

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def try_acquire(self, context: RateLimitContext | None = None) -> bool:
        """
        Try to acquire without waiting.

        Returns:
            True if acquired, False if not available
        """
        with self._lock:
            self._clean_old_requests()

            if len(self._request_times) < self._window_size:
                self._request_times.append(time.monotonic())
                self._total_requests += 1
                return True

            return False

    def update_from_response(
        self,
        status_code: int,
        headers: dict[str, str],
        context: RateLimitContext | None = None,
    ) -> None:
        """Update rate limiter based on API response."""
        with self._lock:
            # Parse rate limit headers
            remaining = headers.get(self._config.remaining_header)
            if remaining is not None:
                with contextlib.suppress(ValueError):
                    self._remaining = int(remaining)

            reset = headers.get(self._config.reset_header)
            if reset is not None:
                with contextlib.suppress(ValueError):
                    self._reset_at = float(reset)

            # Track response time
            if context and context.response_time_ms is not None:
                self._response_times.append(context.response_time_ms)
                self._max_response_time = max(self._max_response_time, context.response_time_ms)
                if len(self._response_times) > 100:
                    self._response_times = self._response_times[-100:]

            # Adaptive rate adjustment on 429
            if status_code == 429 and self._config.adaptive:
                self._rate_limited_count += 1
                old_size = self._window_size
                self._window_size = max(
                    1,
                    int(self._window_size * self._config.rate_reduction_factor),
                )
                self._logger.warning(
                    f"Rate limited (429), reducing window from "
                    f"{old_size} to {self._window_size} requests"
                )

    def get_stats(self) -> RateLimitStats:
        """Get rate limiter statistics."""
        with self._lock:
            self._clean_old_requests()
            avg_response = (
                sum(self._response_times) / len(self._response_times)
                if self._response_times
                else 0.0
            )
            return RateLimitStats(
                total_requests=self._total_requests,
                total_wait_time=self._total_wait_time,
                rate_limited_count=self._rate_limited_count,
                current_rate=self._current_rate,
                available_tokens=float(self._window_size - len(self._request_times)),
                requests_in_window=len(self._request_times),
                avg_response_time_ms=avg_response,
                max_response_time_ms=self._max_response_time,
            )

    def reset(self) -> None:
        """Reset rate limiter to initial state."""
        with self._lock:
            self._request_times.clear()
            self._window_size = int(self._config.requests_per_second * self._config.window_seconds)
            self._total_requests = 0
            self._total_wait_time = 0.0
            self._rate_limited_count = 0
            self._response_times = []
            self._max_response_time = 0.0
            self._remaining = None
            self._reset_at = None

    def _clean_old_requests(self) -> None:
        """Remove requests outside the time window. Must be called with lock held."""
        cutoff = time.monotonic() - self._config.window_seconds
        while self._request_times and self._request_times[0] < cutoff:
            self._request_times.popleft()
