"""
Token Bucket Rate Limiter - Synchronous rate limiter using token bucket algorithm.

Provides a base implementation that can be extended for API-specific rate limiting.
For async contexts, use AsyncRateLimiter instead.
"""

import contextlib
import logging
import threading
import time
from typing import Any

import requests


class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter for controlling API request rates.

    Uses a token bucket algorithm where:
    - Tokens are added at a steady rate (requests_per_second)
    - Each request consumes one token
    - If no tokens are available, the request waits
    - Bucket has a maximum capacity (burst_size) to allow short bursts

    This is the base class for API-specific rate limiters. Subclasses can override
    `update_from_response()` to handle API-specific rate limit headers.

    Example:
        >>> limiter = TokenBucketRateLimiter(requests_per_second=5.0, burst_size=10)
        >>> limiter.acquire()  # Blocks until token available
        >>> # Make API request...
        >>> limiter.update_from_response(response)

    Subclass example:
        >>> class JiraRateLimiter(TokenBucketRateLimiter):
        ...     def update_from_response(self, response):
        ...         # Handle Jira-specific headers
        ...         super().update_from_response(response)
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
        logger_name: str | None = None,
    ):
        """
        Initialize the rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum tokens in bucket (allows short bursts).
                Should be >= 1. A higher value allows more burst capacity.
            logger_name: Optional custom logger name. Defaults to class name.
        """
        self.requests_per_second = requests_per_second
        self.burst_size = max(1, burst_size)

        # Token bucket state
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0

        self.logger = logging.getLogger(logger_name or self.__class__.__name__)

    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, waiting if necessary.

        Blocks until a token is available or timeout is reached.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if token was acquired, False if timeout was reached.
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill_tokens()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._total_requests += 1
                    return True

                # Calculate wait time until next token
                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self.requests_per_second

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0.01:  # Only log if wait is noticeable
                self.logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def _refill_tokens(self) -> None:
        """
        Refill tokens based on elapsed time.

        Must be called with lock held.
        """
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        # Add tokens based on elapsed time
        new_tokens = elapsed * self.requests_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)

    def try_acquire(self) -> bool:
        """
        Try to acquire a token without waiting.

        Returns:
            True if token was acquired, False if not available.
        """
        with self._lock:
            self._refill_tokens()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._total_requests += 1
                return True

            return False

    @property
    def available_tokens(self) -> float:
        """Get the current number of available tokens."""
        with self._lock:
            self._refill_tokens()
            return self._tokens

    @property
    def stats(self) -> dict[str, Any]:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with stats. Subclasses can extend this by calling
            super().stats and adding additional fields.
        """
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_wait_time": self._total_wait_time,
                "average_wait_time": (
                    self._total_wait_time / self._total_requests
                    if self._total_requests > 0
                    else 0.0
                ),
                "available_tokens": self._tokens,
                "requests_per_second": self.requests_per_second,
                "burst_size": self.burst_size,
            }

    def update_from_response(self, response: requests.Response) -> None:
        """
        Update rate limiter based on API response headers.

        Override this method in subclasses to handle API-specific rate limit
        headers. The base implementation handles common patterns:
        - X-RateLimit-Remaining header warnings
        - 429 status code rate reduction

        Args:
            response: HTTP response to extract rate limit info from.
        """
        with self._lock:
            # Check for common rate limit headers
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                try:
                    remaining_int = int(remaining)
                    if remaining_int <= 5:
                        self.logger.warning(
                            f"Rate limit nearly exhausted: {remaining_int} requests remaining"
                        )
                except ValueError:
                    pass

            # Adjust based on 429 responses (slow down)
            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.5, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited by server, reducing rate from "
                    f"{old_rate:.1f} to {self.requests_per_second:.1f} req/s"
                )

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        with self._lock:
            self._tokens = float(self.burst_size)
            self._last_update = time.monotonic()
            self._total_requests = 0
            self._total_wait_time = 0.0


class JiraRateLimiter(TokenBucketRateLimiter):
    """
    Jira-specific rate limiter.

    Jira Cloud typically allows ~100 requests per minute for most endpoints.
    This implementation uses conservative defaults to avoid hitting limits.
    """

    def __init__(
        self,
        requests_per_second: float = 5.0,
        burst_size: int = 10,
    ):
        """
        Initialize the Jira rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
                Default 5.0 (300/minute) is conservative for Jira Cloud.
            burst_size: Maximum burst capacity.
        """
        super().__init__(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            logger_name="JiraRateLimiter",
        )


class GitHubRateLimiter(TokenBucketRateLimiter):
    """
    GitHub-specific rate limiter with X-RateLimit header awareness.

    GitHub has different rate limits:
    - Authenticated: 5,000 requests/hour
    - With GitHub App installation token: 15,000 requests/hour

    This implementation tracks GitHub's X-RateLimit-* headers for
    proactive rate limiting.
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
    ):
        """
        Initialize the GitHub rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum tokens in bucket.
        """
        super().__init__(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            logger_name="GitHubRateLimiter",
        )

        # GitHub rate limit headers tracking
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: float | None = None

    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, waiting if necessary.

        Extends base class to also check GitHub's X-RateLimit headers.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if token was acquired, False if timeout was reached.
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                self._refill_tokens()

                # Check GitHub rate limit headers
                if self._should_wait_for_github_limit():
                    wait_time = self._github_wait_time()
                    if wait_time > 0:
                        self.logger.warning(
                            f"GitHub rate limit exhausted, waiting {wait_time:.1f}s"
                        )
                        self._total_wait_time += wait_time
                        # Release lock during wait
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
                wait_time = tokens_needed / self.requests_per_second

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0.01:
                self.logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def update_from_response(self, response: requests.Response) -> None:
        """
        Update rate limiter based on GitHub API response headers.

        GitHub provides:
        - X-RateLimit-Limit: Total allowed requests
        - X-RateLimit-Remaining: Remaining requests
        - X-RateLimit-Reset: Unix timestamp when limit resets
        """
        with self._lock:
            # Parse GitHub-specific headers
            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                with contextlib.suppress(ValueError):
                    self._rate_limit_remaining = int(remaining)

            reset = response.headers.get("X-RateLimit-Reset")
            if reset is not None:
                with contextlib.suppress(ValueError):
                    self._rate_limit_reset = float(reset)

            # Warn if running low
            if self._rate_limit_remaining is not None and self._rate_limit_remaining <= 100:
                self.logger.warning(
                    f"GitHub rate limit low: {self._rate_limit_remaining} remaining"
                )

            # Adjust rate on 429
            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.5, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited by GitHub, reducing rate from "
                    f"{old_rate:.1f} to {self.requests_per_second:.1f} req/s"
                )

    def _should_wait_for_github_limit(self) -> bool:
        """Check if we should wait based on GitHub rate limit headers."""
        if self._rate_limit_remaining is None:
            return False
        return self._rate_limit_remaining <= 5

    def _github_wait_time(self) -> float:
        """Calculate wait time until GitHub rate limit resets."""
        if self._rate_limit_reset is None:
            return 60.0  # Default wait if no reset time

        wait_time = self._rate_limit_reset - time.time()
        return max(0, wait_time)

    @property
    def stats(self) -> dict[str, Any]:
        """Get rate limiter statistics including GitHub-specific info."""
        base_stats = super().stats
        with self._lock:
            base_stats.update(
                {
                    "github_remaining": self._rate_limit_remaining,
                    "github_reset": self._rate_limit_reset,
                }
            )
        return base_stats

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        super().reset()
        with self._lock:
            self._rate_limit_remaining = None
            self._rate_limit_reset = None


class LinearRateLimiter(TokenBucketRateLimiter):
    """
    Linear-specific rate limiter.

    Linear has a rate limit of 1,500 requests per hour for the GraphQL API.
    This works out to about 0.4 requests per second sustained.
    We use conservative defaults with burst capacity.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        burst_size: int = 10,
    ):
        """
        Initialize the Linear rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
                Default 1.0 (~3600/hour) is under Linear's 1500 limit.
            burst_size: Maximum burst capacity.
        """
        super().__init__(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            logger_name="LinearRateLimiter",
        )

        # Linear rate limit tracking
        self._requests_remaining: int | None = None
        self._reset_at: float | None = None

    def update_from_response(self, response: requests.Response) -> None:
        """
        Update rate limiter based on Linear API response headers.

        Linear provides:
        - X-RateLimit-Requests-Remaining: Remaining requests
        - X-RateLimit-Requests-Reset: Unix timestamp when limit resets
        """
        with self._lock:
            remaining = response.headers.get("X-RateLimit-Requests-Remaining")
            if remaining is not None:
                with contextlib.suppress(ValueError):
                    self._requests_remaining = int(remaining)
                if self._requests_remaining is not None and self._requests_remaining <= 50:
                    self.logger.warning(
                        f"Linear rate limit low: {self._requests_remaining} remaining"
                    )

            reset = response.headers.get("X-RateLimit-Requests-Reset")
            if reset is not None:
                with contextlib.suppress(ValueError):
                    self._reset_at = float(reset)

            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.1, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited by Linear, reducing rate from "
                    f"{old_rate:.2f} to {self.requests_per_second:.2f} req/s"
                )

    @property
    def stats(self) -> dict[str, Any]:
        """Get rate limiter statistics including Linear-specific info."""
        base_stats = super().stats
        with self._lock:
            base_stats.update(
                {
                    "linear_remaining": self._requests_remaining,
                    "linear_reset_at": self._reset_at,
                }
            )
        return base_stats

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        super().reset()
        with self._lock:
            self._requests_remaining = None
            self._reset_at = None
