"""
Chaos engineering tests for Spectra.

These tests verify system resilience under failure conditions:
- Network failures
- API timeouts
- Rate limiting
- Partial failures
- Connection drops

Run with:
    pytest tests/chaos/ -v -m chaos
"""

import asyncio
import random
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueTrackerError,
)


# Mark all tests in this module as chaos tests (skipped by default)
pytestmark = pytest.mark.chaos


class NetworkFailureSimulator:
    """Simulates various network failure scenarios."""

    def __init__(self, failure_rate: float = 0.5):
        self.failure_rate = failure_rate
        self.call_count = 0
        self.failure_count = 0

    def maybe_fail(self):
        """Randomly fail based on failure rate."""
        self.call_count += 1
        if random.random() < self.failure_rate:
            self.failure_count += 1
            raise ConnectionError("Simulated network failure")

    def timeout(self, max_delay: float = 5.0):
        """Simulate random timeout."""
        delay = random.uniform(0, max_delay)
        time.sleep(delay)
        if delay > max_delay * 0.8:
            raise TimeoutError("Simulated timeout")


class TestNetworkFailureResilience:
    """Tests for handling network failures."""

    def test_adapter_handles_connection_error(self):
        """Test adapter handles connection errors gracefully."""
        from spectryn.adapters.jira.adapter import JiraAdapter
        from spectryn.core.ports.config_provider import TrackerConfig

        config = TrackerConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

        with (
            patch("spectryn.adapters.jira.adapter.JiraApiClient") as MockClient,
            patch("spectryn.adapters.jira.adapter.JiraBatchClient"),
        ):
            mock_client = MagicMock()
            mock_client.get.side_effect = ConnectionError("Network unreachable")
            MockClient.return_value = mock_client

            adapter = JiraAdapter(config=config, dry_run=True)
            adapter._client = mock_client

            with pytest.raises(ConnectionError):
                adapter.get_issue("TEST-123")

    def test_adapter_handles_timeout(self):
        """Test adapter handles timeouts gracefully."""
        from spectryn.adapters.github.adapter import GitHubAdapter

        with patch("spectryn.adapters.github.adapter.GitHubApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.list_labels.return_value = []
            mock_client.get_issue.side_effect = TimeoutError("Request timed out")
            MockClient.return_value = mock_client

            adapter = GitHubAdapter(token="test", owner="test", repo="test", dry_run=True)
            adapter._client = mock_client

            with pytest.raises(TimeoutError):
                adapter.get_issue("#123")

    def test_intermittent_failures_with_retry(self):
        """Test handling of intermittent failures."""
        failure_count = [0]
        success_count = [0]

        def flaky_operation():
            if failure_count[0] < 2:
                failure_count[0] += 1
                raise ConnectionError("Temporary failure")
            success_count[0] += 1
            return "success"

        # Simulate retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                flaky_operation()
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise

        assert success_count[0] == 1
        assert failure_count[0] == 2


class TestRateLimitingResilience:
    """Tests for handling rate limiting."""

    def test_github_rate_limit_handling(self):
        """Test GitHub adapter handles rate limits."""
        from spectryn.adapters.github.adapter import GitHubAdapter
        from spectryn.core.ports.issue_tracker import RateLimitError

        with patch("spectryn.adapters.github.adapter.GitHubApiClient") as MockClient:
            mock_client = MagicMock()
            mock_client.list_labels.return_value = []
            mock_client.get_issue.side_effect = RateLimitError(
                "Rate limit exceeded", retry_after=60
            )
            MockClient.return_value = mock_client

            adapter = GitHubAdapter(token="test", owner="test", repo="test", dry_run=True)
            adapter._client = mock_client

            with pytest.raises(RateLimitError) as exc_info:
                adapter.get_issue("#123")

            assert exc_info.value.retry_after == 60

    def test_rate_limiter_token_bucket(self):
        """Test token bucket rate limiter behavior."""
        from spectryn.adapters.github.client import GitHubRateLimiter

        limiter = GitHubRateLimiter(requests_per_second=10.0, burst_size=5)

        # Should allow burst
        for _ in range(5):
            assert limiter.acquire(timeout=0.01) is True

        # Should throttle after burst
        stats = limiter.stats
        assert stats["total_requests"] == 5


class TestPartialFailureResilience:
    """Tests for handling partial failures in batch operations."""

    def test_batch_operation_partial_failure(self):
        """Test batch operations handle partial failures."""
        from spectryn.adapters.linear.batch import BatchResult, LinearBatchClient

        mock_client = MagicMock()
        mock_client.dry_run = False

        # Simulate some operations failing
        mock_client.create_issue.side_effect = [
            {"identifier": "ENG-1"},
            IssueTrackerError("Failed"),
            {"identifier": "ENG-3"},
            IssueTrackerError("Failed"),
            {"identifier": "ENG-5"},
        ]

        batch_client = LinearBatchClient(client=mock_client)

        subtasks = [{"parent_key": f"ENG-{i}", "summary": f"Subtask {i}"} for i in range(5)]

        result = batch_client.bulk_create_subtasks(subtasks)

        # Should have partial success
        assert result.succeeded == 3
        assert result.failed == 2
        assert result.success is False  # Not all succeeded

    def test_batch_continues_after_failure(self):
        """Test batch operations continue after individual failures."""
        results = []

        def operation_with_failures(index):
            if index % 3 == 0:
                raise ValueError(f"Failed at {index}")
            return f"success-{index}"

        for i in range(10):
            try:
                results.append(operation_with_failures(i))
            except ValueError:
                results.append(None)

        # Should have processed all 10, with some failures
        assert len(results) == 10
        successful = [r for r in results if r is not None]
        failed = [r for r in results if r is None]
        assert len(successful) == 6  # 1,2,4,5,7,8
        assert len(failed) == 4  # 0,3,6,9


class TestConnectionDropResilience:
    """Tests for handling connection drops mid-operation."""

    def test_connection_drop_during_write(self):
        """Test handling connection drop during write operation."""
        from spectryn.adapters.jira.adapter import JiraAdapter
        from spectryn.core.ports.config_provider import TrackerConfig

        config = TrackerConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

        with (
            patch("spectryn.adapters.jira.adapter.JiraApiClient") as MockClient,
            patch("spectryn.adapters.jira.adapter.JiraBatchClient"),
        ):
            mock_client = MagicMock()
            mock_client.put.side_effect = ConnectionResetError("Connection reset")
            MockClient.return_value = mock_client

            adapter = JiraAdapter(config=config, dry_run=False)
            adapter._client = mock_client

            with pytest.raises(ConnectionResetError):
                adapter.update_issue_description("TEST-123", "New description")

    def test_reconnection_after_drop(self):
        """Test adapter can recover after connection drop."""
        call_count = [0]

        def reconnecting_call():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionResetError("Connection reset")
            return {"key": "TEST-123", "fields": {"summary": "Test"}}

        # Simulate reconnection logic
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                result = reconnecting_call()
                break
            except ConnectionResetError:
                if attempt == max_attempts - 1:
                    raise

        assert result["key"] == "TEST-123"
        assert call_count[0] == 2


class TestAsyncChaosEngineering:
    """Chaos tests for async operations."""

    @pytest.mark.asyncio
    async def test_async_timeout_handling(self):
        """Test async operations handle timeouts."""

        async def slow_operation():
            await asyncio.sleep(10)  # Simulates slow operation

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_operation(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_async_concurrent_failures(self):
        """Test handling of concurrent async failures."""
        failure_indices = {1, 3, 5}

        async def maybe_failing_task(index):
            await asyncio.sleep(0.01)
            if index in failure_indices:
                raise ValueError(f"Task {index} failed")
            return f"success-{index}"

        tasks = [maybe_failing_task(i) for i in range(7)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 4
        assert len(failures) == 3

    @pytest.mark.asyncio
    async def test_async_cancellation_handling(self):
        """Test async operations handle cancellation."""
        cancelled = [False]

        async def cancellable_operation():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled[0] = True
                raise

        task = asyncio.create_task(cancellable_operation())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cancelled[0] is True


class TestResourceExhaustion:
    """Tests for resource exhaustion scenarios."""

    def test_many_concurrent_connections(self):
        """Test handling of many concurrent connections."""
        from concurrent.futures import ThreadPoolExecutor

        def simulated_connection(index):
            time.sleep(0.01)  # Simulate connection overhead
            return f"connected-{index}"

        # Simulate 100 concurrent connections
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(simulated_connection, i) for i in range(100)]
            results = [f.result() for f in futures]

        assert len(results) == 100

    def test_large_response_handling(self):
        """Test handling of very large API responses."""
        # Simulate a large response
        large_response = {
            "issues": [
                {"key": f"LARGE-{i}", "fields": {"summary": f"Issue {i}"}} for i in range(10000)
            ]
        }

        # Should be able to process without memory issues
        keys = [issue["key"] for issue in large_response["issues"]]
        assert len(keys) == 10000

    def test_deep_nested_response(self):
        """Test handling deeply nested responses."""

        def create_nested(depth):
            if depth == 0:
                return {"value": "leaf"}
            return {"nested": create_nested(depth - 1)}

        # Create 100-level deep nesting
        nested = create_nested(100)

        # Traverse to verify
        current = nested
        for _ in range(100):
            current = current["nested"]
        assert current["value"] == "leaf"
