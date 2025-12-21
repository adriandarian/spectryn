"""Tests for the async rate limiter."""

import asyncio
import time

import pytest

from spectra.adapters.async_base.rate_limiter import AsyncRateLimiter


class TestAsyncRateLimiterBasics:
    """Basic tests for AsyncRateLimiter."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        limiter = AsyncRateLimiter()

        assert limiter.requests_per_second == 10.0
        assert limiter.burst_size == 20

    def test_init_custom_values(self) -> None:
        """Test initialization with custom values."""
        limiter = AsyncRateLimiter(requests_per_second=5.0, burst_size=10)

        assert limiter.requests_per_second == 5.0
        assert limiter.burst_size == 10

    def test_burst_size_minimum(self) -> None:
        """Test that burst size has a minimum of 1."""
        limiter = AsyncRateLimiter(burst_size=0)
        assert limiter.burst_size == 1

        limiter2 = AsyncRateLimiter(burst_size=-5)
        assert limiter2.burst_size == 1


class TestAsyncRateLimiterAcquire:
    """Tests for acquire method."""

    @pytest.mark.asyncio
    async def test_acquire_single(self) -> None:
        """Test acquiring a single token."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_burst(self) -> None:
        """Test acquiring tokens in burst."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        # Should be able to acquire burst_size tokens immediately
        for _ in range(5):
            result = await limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_acquire_with_timeout_success(self) -> None:
        """Test acquire with timeout that succeeds."""
        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=10)

        result = await limiter.acquire(timeout=1.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_with_timeout_failure(self) -> None:
        """Test acquire with timeout that fails."""
        limiter = AsyncRateLimiter(requests_per_second=0.1, burst_size=1)

        # Exhaust the initial token
        await limiter.acquire()

        # Next acquire should timeout (need 10 seconds for refill, only wait 0.05)
        result = await limiter.acquire(timeout=0.05)
        assert result is False


class TestAsyncRateLimiterContextManager:
    """Tests for context manager usage."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test using rate limiter as context manager."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        async with limiter:
            # Should execute without raising
            pass

    @pytest.mark.asyncio
    async def test_multiple_context_managers(self) -> None:
        """Test multiple context manager acquisitions."""
        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=10)

        for _ in range(5):
            async with limiter:
                pass


class TestAsyncRateLimiterStatistics:
    """Tests for statistics tracking."""

    @pytest.mark.asyncio
    async def test_total_requests_tracking(self) -> None:
        """Test that total requests are tracked."""
        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=10)

        for _ in range(5):
            await limiter.acquire()

        assert limiter.stats["total_requests"] == 5

    @pytest.mark.asyncio
    async def test_stats_content(self) -> None:
        """Test stats dictionary content."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        await limiter.acquire()

        stats = limiter.stats
        assert "total_requests" in stats
        assert "total_wait_time" in stats
        assert "available_tokens" in stats
        assert "requests_per_second" in stats
        assert "burst_size" in stats
        assert "average_wait_time" in stats


class TestAsyncRateLimiterConcurrency:
    """Tests for concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self) -> None:
        """Test concurrent acquire calls."""
        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=10)

        async def acquire_and_record():
            await limiter.acquire()
            return True

        # Launch multiple concurrent acquires
        tasks = [acquire_and_record() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert all(results)
        assert limiter.stats["total_requests"] == 5


class TestAsyncRateLimiterReset:
    """Tests for reset functionality."""

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        """Test resetting the rate limiter."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        # Use some tokens
        await limiter.acquire()
        await limiter.acquire()

        assert limiter.stats["total_requests"] == 2

        # Reset
        await limiter.reset()

        assert limiter.stats["total_requests"] == 0
        assert limiter.stats["total_wait_time"] == 0.0


class TestAsyncRateLimiterResponseUpdate:
    """Tests for response-based rate adjustment."""

    @pytest.mark.asyncio
    async def test_update_from_429_response(self) -> None:
        """Test rate is reduced on 429 response."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)
        original_rate = limiter.requests_per_second

        await limiter.update_from_response(429)

        # Rate should be reduced
        assert limiter.requests_per_second < original_rate
        assert limiter.requests_per_second == 5.0  # 10 * 0.5

    @pytest.mark.asyncio
    async def test_update_from_200_response(self) -> None:
        """Test no change on 200 response."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)
        original_rate = limiter.requests_per_second

        await limiter.update_from_response(200)

        assert limiter.requests_per_second == original_rate

    @pytest.mark.asyncio
    async def test_update_with_rate_limit_header(self) -> None:
        """Test handling rate limit headers."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        # Should not crash with rate limit headers
        await limiter.update_from_response(200, {"X-RateLimit-Remaining": "3"})


class TestAsyncRateLimiterTryAcquire:
    """Tests for try_acquire method."""

    @pytest.mark.asyncio
    async def test_try_acquire_success(self) -> None:
        """Test try_acquire when token available."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        result = await limiter.try_acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_try_acquire_failure(self) -> None:
        """Test try_acquire when no tokens available."""
        limiter = AsyncRateLimiter(requests_per_second=0.1, burst_size=1)

        # Use the only token
        await limiter.acquire()

        # Try acquire should fail immediately (no waiting)
        result = await limiter.try_acquire()
        assert result is False


class TestAsyncRateLimiterProperties:
    """Tests for properties."""

    def test_available_tokens_property(self) -> None:
        """Test available_tokens property."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        # Initially should have burst_size tokens
        assert limiter.available_tokens == 5.0
