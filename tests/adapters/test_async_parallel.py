"""
Tests for async parallel API call infrastructure.

Tests cover:
- AsyncRateLimiter token bucket algorithm
- AsyncHttpClient request handling
- Parallel execution utilities (gather, batch, run_parallel)
- AsyncJiraApiClient parallel operations
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


# Skip all tests if aiohttp is not available
pytest.importorskip("aiohttp")


class TestAsyncRateLimiter:
    """Tests for AsyncRateLimiter."""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter with known parameters."""
        from spectryn.adapters.async_base import AsyncRateLimiter

        return AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

    @pytest.mark.asyncio
    async def test_initial_tokens(self, rate_limiter):
        """Test that rate limiter starts with burst_size tokens."""
        assert rate_limiter.available_tokens == 5.0

    @pytest.mark.asyncio
    async def test_acquire_consumes_token(self, rate_limiter):
        """Test that acquire consumes a token."""
        initial_tokens = rate_limiter.available_tokens
        result = await rate_limiter.acquire()

        assert result is True
        assert rate_limiter.available_tokens < initial_tokens

    @pytest.mark.asyncio
    async def test_burst_capacity(self, rate_limiter):
        """Test that burst_size requests can be made immediately."""
        results = []
        for _ in range(5):  # burst_size is 5
            results.append(await rate_limiter.try_acquire())

        # All should succeed immediately
        assert all(results)
        # 6th request should fail immediately (try_acquire doesn't wait)
        assert not await rate_limiter.try_acquire()

    @pytest.mark.asyncio
    async def test_token_refill(self, rate_limiter):
        """Test that tokens refill over time."""
        # Exhaust all tokens
        for _ in range(5):
            await rate_limiter.acquire()

        # Wait for tokens to refill (10 req/s = 0.1s per token)
        await asyncio.sleep(0.15)

        # Should be able to acquire now
        result = await rate_limiter.try_acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_stats_tracking(self, rate_limiter):
        """Test that stats are tracked correctly."""
        await rate_limiter.acquire()
        await rate_limiter.acquire()

        stats = rate_limiter.stats
        assert stats["total_requests"] == 2
        assert stats["requests_per_second"] == 10.0
        assert stats["burst_size"] == 5

    @pytest.mark.asyncio
    async def test_context_manager(self, rate_limiter):
        """Test that rate limiter works as context manager."""
        async with rate_limiter:
            pass  # Token should be acquired

        assert rate_limiter.stats["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_update_from_429_response(self, rate_limiter):
        """Test that rate is reduced on 429 responses."""
        initial_rate = rate_limiter.requests_per_second
        await rate_limiter.update_from_response(429, {})

        # Rate should be halved
        assert rate_limiter.requests_per_second == initial_rate * 0.5


class TestParallelExecutionUtilities:
    """Tests for parallel execution utilities."""

    @pytest.mark.asyncio
    async def test_gather_with_limit_basic(self):
        """Test basic gather_with_limit functionality."""
        from spectryn.adapters.async_base import gather_with_limit

        results = []

        async def task(x: int) -> int:
            results.append(x)
            await asyncio.sleep(0.01)
            return x * 2

        coros = [task(i) for i in range(5)]
        output = await gather_with_limit(coros, limit=2)

        assert len(output) == 5
        assert output == [0, 2, 4, 6, 8]

    @pytest.mark.asyncio
    async def test_gather_with_limit_respects_concurrency(self):
        """Test that gather_with_limit respects the concurrency limit."""
        from spectryn.adapters.async_base import gather_with_limit

        concurrent_count = 0
        max_concurrent = 0

        async def task(x: int) -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return x

        coros = [task(i) for i in range(10)]
        await gather_with_limit(coros, limit=3)

        # Max concurrent should never exceed limit
        assert max_concurrent <= 3

    @pytest.mark.asyncio
    async def test_gather_with_limit_return_exceptions(self):
        """Test that exceptions are returned when return_exceptions=True."""
        from spectryn.adapters.async_base import gather_with_limit

        async def task(x: int) -> int:
            if x == 2:
                raise ValueError("Error at 2")
            return x

        coros = [task(i) for i in range(5)]
        output = await gather_with_limit(coros, limit=2, return_exceptions=True)

        assert len(output) == 5
        assert output[0] == 0
        assert output[1] == 1
        assert isinstance(output[2], ValueError)
        assert output[3] == 3
        assert output[4] == 4

    @pytest.mark.asyncio
    async def test_batch_execute_basic(self):
        """Test basic batch_execute functionality."""
        from spectryn.adapters.async_base import batch_execute

        async def operation(x: int) -> dict:
            return {"value": x * 2}

        items = list(range(10))
        result = await batch_execute(
            items=items,
            operation=operation,
            batch_size=3,
            concurrency=2,
        )

        assert result.total == 10
        assert result.successful == 10
        assert result.failed == 0
        assert len(result.results) == 10

    @pytest.mark.asyncio
    async def test_batch_execute_with_errors(self):
        """Test batch_execute handles errors gracefully."""
        from spectryn.adapters.async_base import batch_execute

        async def operation(x: int) -> dict:
            if x % 3 == 0:
                raise ValueError(f"Error at {x}")
            return {"value": x}

        items = list(range(9))  # 0, 3, 6 will fail
        result = await batch_execute(
            items=items,
            operation=operation,
            batch_size=3,
            concurrency=2,
        )

        assert result.total == 9
        assert result.successful == 6  # 1, 2, 4, 5, 7, 8 succeed
        assert result.failed == 3  # 0, 3, 6 fail
        assert len(result.errors) == 3

    @pytest.mark.asyncio
    async def test_batch_execute_with_progress_callback(self):
        """Test batch_execute calls progress callback."""
        from spectryn.adapters.async_base import batch_execute

        progress_calls = []

        def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        async def operation(x: int) -> dict:
            return {"value": x}

        items = list(range(5))
        await batch_execute(
            items=items,
            operation=operation,
            batch_size=2,
            concurrency=1,
            progress_callback=on_progress,
        )

        # Should have 5 progress calls (one for each item)
        assert len(progress_calls) == 5
        assert progress_calls[-1] == (5, 5)

    @pytest.mark.asyncio
    async def test_run_parallel_basic(self):
        """Test run_parallel with named operations."""
        from spectryn.adapters.async_base import run_parallel

        async def get_user() -> dict:
            return {"name": "Alice"}

        async def get_issues() -> list:
            return [1, 2, 3]

        results = await run_parallel(
            {
                "user": get_user(),
                "issues": get_issues(),
            }
        )

        assert results["user"] == {"name": "Alice"}
        assert results["issues"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_parallel_result_properties(self):
        """Test ParallelResult computed properties."""
        from spectryn.adapters.async_base import ParallelResult

        result = ParallelResult[int]()
        result.total = 10
        result.results = [1, 2, 3, 4, 5, 6, 7]  # 7 successful
        result.errors = [
            (7, ValueError("err1")),
            (8, ValueError("err2")),
            (9, ValueError("err3")),
        ]  # 3 failed

        assert result.successful == 7
        assert result.failed == 3
        assert result.success_rate == 0.7
        assert not result.all_succeeded


class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    @pytest.mark.asyncio
    async def test_executor_map(self):
        """Test ParallelExecutor.map()."""
        from spectryn.adapters.async_base import ParallelExecutor

        async def double(x: int) -> int:
            return x * 2

        async with ParallelExecutor(concurrency=3, batch_size=2) as executor:
            result = await executor.map([1, 2, 3, 4, 5], double)

        assert result.successful == 5
        assert set(result.results) == {2, 4, 6, 8, 10}

    @pytest.mark.asyncio
    async def test_executor_gather(self):
        """Test ParallelExecutor.gather()."""
        from spectryn.adapters.async_base import ParallelExecutor

        async def task(x: int) -> int:
            return x

        async with ParallelExecutor(concurrency=2) as executor:
            results = await executor.gather([task(i) for i in range(5)])

        assert len(results) == 5


class TestAsyncJiraApiClient:
    """Tests for AsyncJiraApiClient."""

    @pytest.fixture
    def mock_aiohttp_session(self):
        """Create a mock aiohttp session."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.ok = True
        mock_response.headers = {}
        mock_response.text = AsyncMock(return_value='{"key": "PROJ-1"}')
        mock_response.json = AsyncMock(return_value={"key": "PROJ-1"})

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=mock_cm)
        mock_session.closed = False
        mock_session.close = AsyncMock()

        return mock_session

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test AsyncJiraApiClient can be initialized."""
        from spectryn.adapters.jira.async_client import AsyncJiraApiClient

        client = AsyncJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

        assert client.dry_run is True
        assert client.concurrency == 5

    @pytest.mark.asyncio
    async def test_dry_run_prevents_writes(self):
        """Test that dry_run prevents write operations."""
        from spectryn.adapters.jira.async_client import AsyncJiraApiClient

        client = AsyncJiraApiClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            dry_run=True,
        )

        # PUT should return empty dict in dry_run mode without making request
        result = await client.put("issue/PROJ-1", json={"fields": {}})
        assert result == {}


class TestParallelSyncOperations:
    """Tests for ParallelSyncOperations high-level interface."""

    @pytest.fixture
    def parallel_ops(self):
        """Create ParallelSyncOperations instance."""
        from spectryn.application.sync.parallel import ParallelSyncOperations

        return ParallelSyncOperations(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            dry_run=True,
            concurrency=3,
        )

    def test_is_parallel_available(self):
        """Test is_parallel_available returns True when aiohttp is installed."""
        from spectryn.application.sync.parallel import is_parallel_available

        assert is_parallel_available() is True

    def test_parallel_sync_result_properties(self):
        """Test ParallelSyncResult properties."""
        from spectryn.application.sync.parallel import (
            EpicProgress,
            ParallelSyncConfig,
            ParallelSyncResult,
        )

        progress = [
            EpicProgress(epic_key="PROJ-1", epic_title="Epic 1", status="completed"),
            EpicProgress(epic_key="PROJ-2", epic_title="Epic 2", status="failed"),
        ]
        result = ParallelSyncResult(
            parallel_config=ParallelSyncConfig(max_workers=4),
            workers_used=4,
            peak_concurrency=2,
            epic_progress=progress,
        )

        assert result.workers_used == 4
        assert result.peak_concurrency == 2
        assert len(result.epic_progress) == 2
        assert "Workers: 4" in result.summary()


class TestRateLimiterIntegration:
    """Integration tests for rate limiting with parallel operations."""

    @pytest.mark.asyncio
    async def test_rate_limiter_with_batch_execute(self):
        """Test that rate limiter is respected during batch execution."""
        from spectryn.adapters.async_base import AsyncRateLimiter, batch_execute

        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=5)
        request_times = []

        async def timed_operation(x: int) -> int:
            request_times.append(time.monotonic())
            return x

        items = list(range(10))
        start = time.monotonic()
        await batch_execute(
            items=items,
            operation=timed_operation,
            batch_size=10,
            concurrency=10,
            rate_limiter=limiter,
        )
        elapsed = time.monotonic() - start

        # All 10 requests should complete
        assert len(request_times) == 10

        # With burst_size=5, first 5 should be instant, remaining 5 need tokens
        # At 100 req/s, that's ~0.05s for 5 more tokens
        # This is a smoke test - just verify it completes in reasonable time
        assert elapsed < 2.0  # Should be much faster, but allow margin


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
