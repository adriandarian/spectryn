"""
Async Rate Limiter - Token bucket rate limiter compatible with asyncio.

Uses asyncio primitives for non-blocking rate limiting in concurrent contexts.
"""

import asyncio
import logging
import time
from typing import Any


class AsyncRateLimiter:
    """
    Asyncio-compatible token bucket rate limiter.

    Uses asyncio.Lock and asyncio.sleep for non-blocking rate limiting.
    Allows multiple concurrent tasks to share rate limiting without blocking
    the event loop.

    Features:
    - Token bucket algorithm with configurable rate and burst size
    - Non-blocking async acquire
    - Thread-safe via asyncio.Lock
    - Statistics tracking
    - Dynamic rate adjustment based on API responses

    Example:
        >>> limiter = AsyncRateLimiter(requests_per_second=5.0, burst_size=10)
        >>> async with limiter:
        ...     await make_api_call()
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 20,
    ):
        """
        Initialize the async rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum tokens in bucket (allows short bursts).
        """
        self.requests_per_second = requests_per_second
        self.burst_size = max(1, burst_size)

        # Token bucket state
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0

        self.logger = logging.getLogger("AsyncRateLimiter")

    async def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, waiting asynchronously if necessary.

        This is non-blocking - it uses asyncio.sleep to wait,
        allowing other coroutines to run.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if token was acquired, False if timeout was reached.
        """
        start_time = time.monotonic()

        while True:
            async with self._lock:
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

            if wait_time > 0.01:
                self.logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")

            self._total_wait_time += wait_time
            await asyncio.sleep(wait_time)

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

    async def try_acquire(self) -> bool:
        """
        Try to acquire a token without waiting.

        Returns:
            True if token was acquired, False if not available.
        """
        async with self._lock:
            self._refill_tokens()

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._total_requests += 1
                return True

            return False

    async def update_from_response(
        self,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Update rate limiter based on API response.

        Dynamically adjusts rate based on 429 responses and
        rate limit headers.

        Args:
            status_code: HTTP status code
            headers: Response headers (optional)
        """
        headers = headers or {}

        async with self._lock:
            # Check for common rate limit headers
            remaining = headers.get("X-RateLimit-Remaining")
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
            if status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.5, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited by server, reducing rate from "
                    f"{old_rate:.1f} to {self.requests_per_second:.1f} req/s"
                )

    @property
    def available_tokens(self) -> float:
        """Get the approximate number of available tokens (not thread-safe)."""
        return self._tokens

    @property
    def stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "total_requests": self._total_requests,
            "total_wait_time": self._total_wait_time,
            "average_wait_time": (
                self._total_wait_time / self._total_requests if self._total_requests > 0 else 0.0
            ),
            "available_tokens": self._tokens,
            "requests_per_second": self.requests_per_second,
            "burst_size": self.burst_size,
        }

    async def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        async with self._lock:
            self._tokens = float(self.burst_size)
            self._last_update = time.monotonic()
            self._total_requests = 0
            self._total_wait_time = 0.0

    async def __aenter__(self) -> "AsyncRateLimiter":
        """Context manager entry - acquires a token."""
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        # Nothing to do on exit
