"""
Tests for async HTTP client infrastructure.

These tests cover:
- src/spectra/adapters/async_base/http_client.py
- src/spectra/adapters/async_base/http_client_sync.py
"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest


# =============================================================================
# Async HTTP Client Tests
# =============================================================================


class TestAsyncHttpClientWithoutAiohttp:
    """Test async client behavior when aiohttp is not available."""

    def test_import_error_when_aiohttp_missing(self) -> None:
        """Test that ImportError is raised when aiohttp is not installed."""
        from spectryn.adapters.async_base import http_client

        original = http_client.AIOHTTP_AVAILABLE

        try:
            http_client.AIOHTTP_AVAILABLE = False

            with pytest.raises(ImportError, match="aiohttp"):
                http_client.AsyncHttpClient(
                    base_url="https://api.example.com",
                )
        finally:
            http_client.AIOHTTP_AVAILABLE = original


@pytest.mark.asyncio
class TestAsyncHttpClient:
    """Tests for AsyncHttpClient."""

    @pytest.fixture
    def client(self):
        """Create an async HTTP client."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.async_base.http_client import AsyncHttpClient

        return AsyncHttpClient(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer test-token"},
            max_retries=2,
            initial_delay=0.01,
            timeout=5.0,
        )

    def test_init_defaults(self) -> None:
        """Test initialization with defaults."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.async_base.http_client import AsyncHttpClient

        client = AsyncHttpClient(base_url="https://api.example.com")

        assert client.base_url == "https://api.example.com"
        assert client.max_retries == 3
        assert client.initial_delay == 1.0
        assert client.max_delay == 60.0
        assert client._rate_limiter is not None

    def test_init_with_custom_config(self) -> None:
        """Test initialization with custom config."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.async_base.http_client import AsyncHttpClient

        client = AsyncHttpClient(
            base_url="https://api.example.com/",  # Trailing slash stripped
            headers={"X-Custom": "header"},
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            backoff_factor=3.0,
            jitter=0.2,
            timeout=60.0,
            requests_per_second=2.0,
            burst_size=5,
        )

        assert client.base_url == "https://api.example.com"
        assert client.max_retries == 5
        assert client.initial_delay == 2.0
        assert client.max_delay == 120.0
        assert client.backoff_factor == 3.0
        assert client.jitter == 0.2

    def test_init_no_rate_limiting(self) -> None:
        """Test initialization without rate limiting."""
        pytest.importorskip("aiohttp")
        from spectryn.adapters.async_base.http_client import AsyncHttpClient

        client = AsyncHttpClient(
            base_url="https://api.example.com",
            requests_per_second=None,
        )

        assert client._rate_limiter is None

    async def test_context_manager(self, client) -> None:
        """Test async context manager."""
        async with client:
            assert client._session is not None
            assert not client._session.closed

        # Session should be closed after context
        assert client._session is None or client._session.closed

    async def test_close(self, client) -> None:
        """Test close method."""
        # Get session first
        await client._get_session()
        assert client._session is not None

        # Close
        await client.close()
        # Session should be closed (but may still exist)
        assert client._session is None or client._session.closed

    def test_calculate_delay_no_retry_after(self, client) -> None:
        """Test delay calculation without Retry-After header."""
        # First attempt
        delay = client._calculate_delay(0)
        assert delay >= client.initial_delay * 0.9
        assert delay <= client.initial_delay * 1.1

        # Second attempt (with backoff)
        delay2 = client._calculate_delay(1)
        expected = client.initial_delay * client.backoff_factor
        assert delay2 >= expected * 0.9
        assert delay2 <= expected * 1.1

    def test_calculate_delay_with_retry_after(self, client) -> None:
        """Test delay calculation with Retry-After header."""
        delay = client._calculate_delay(0, retry_after=30)
        # Should use retry_after value
        assert delay >= 27  # Allow some jitter
        assert delay <= 33

    def test_calculate_delay_respects_max(self, client) -> None:
        """Test delay is capped at max_delay."""
        # Very high attempt number would exceed max
        delay = client._calculate_delay(100)
        assert delay <= client.max_delay * 1.1  # Allow jitter

    def test_get_retry_after_valid(self, client) -> None:
        """Test parsing valid Retry-After header."""
        headers = {"Retry-After": "30"}
        assert client._get_retry_after(headers) == 30

    def test_get_retry_after_missing(self, client) -> None:
        """Test missing Retry-After header."""
        assert client._get_retry_after({}) is None

    def test_get_retry_after_invalid(self, client) -> None:
        """Test invalid Retry-After header."""
        assert client._get_retry_after({"Retry-After": "invalid"}) is None


# =============================================================================
# Base HTTP Client (Sync) Tests
# =============================================================================


class TestBaseHttpClientSync:
    """Tests for BaseHttpClient (synchronous)."""

    @pytest.fixture
    def client_class(self):
        """Get a concrete implementation for testing."""
        from spectryn.adapters.async_base.http_client_sync import BaseHttpClient

        class ConcreteHttpClient(BaseHttpClient):
            """Concrete implementation for testing."""

            def _create_rate_limiter(self, rps: float, burst: int):
                from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

                return TokenBucketRateLimiter(requests_per_second=rps, burst_size=burst)

            def _get_logger_name(self) -> str:
                return "TestClient"

        return ConcreteHttpClient

    @pytest.fixture
    def client(self, client_class):
        """Create a test client."""
        return client_class(
            base_url="https://api.example.com",
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
            timeout=5.0,
        )

    def test_init_defaults(self, client_class) -> None:
        """Test initialization with defaults."""
        client = client_class(base_url="https://api.example.com")

        assert client.base_url == "https://api.example.com"
        assert client.dry_run is True  # Default
        assert client.max_retries == 3
        assert client.initial_delay == 1.0
        assert client._rate_limiter is not None

    def test_init_custom_config(self, client_class) -> None:
        """Test initialization with custom config."""
        client = client_class(
            base_url="https://api.example.com/",  # Trailing slash stripped
            dry_run=False,
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            backoff_factor=3.0,
            jitter=0.2,
            requests_per_second=2.0,
            burst_size=5,
        )

        assert client.base_url == "https://api.example.com"
        assert client.dry_run is False
        assert client.max_retries == 5
        assert client.initial_delay == 2.0
        assert client.max_delay == 120.0

    def test_init_no_rate_limiting(self, client_class) -> None:
        """Test initialization without rate limiting."""
        client = client_class(
            base_url="https://api.example.com",
            requests_per_second=0,  # 0 disables rate limiting
        )

        assert client._rate_limiter is None

    def test_pool_config(self, client_class) -> None:
        """Test custom pool configuration."""
        client = client_class(
            base_url="https://api.example.com",
            pool_connections=5,
            pool_maxsize=20,
            pool_block=True,
            timeout=60.0,
        )

        assert client._pool_connections == 5
        assert client._pool_maxsize == 20
        assert client._pool_block is True
        assert client.timeout == 60.0

    def test_calculate_delay(self, client) -> None:
        """Test delay calculation."""
        # First attempt
        delay = client._calculate_delay(0)
        assert delay >= client.initial_delay * 0.9
        assert delay <= client.initial_delay * 1.1

        # With backoff
        delay2 = client._calculate_delay(1)
        expected = client.initial_delay * client.backoff_factor
        assert delay2 >= expected * 0.9
        assert delay2 <= expected * 1.1

    def test_calculate_delay_with_retry_after(self, client) -> None:
        """Test delay with Retry-After."""
        delay = client._calculate_delay(0, retry_after=30)
        assert delay >= 27
        assert delay <= 33

    def test_calculate_delay_capped(self, client) -> None:
        """Test delay is capped."""
        delay = client._calculate_delay(100)
        assert delay <= client.max_delay * 1.1

    def test_get_retry_after(self, client) -> None:
        """Test parsing Retry-After header."""
        mock_response = Mock()

        # Valid
        mock_response.headers = {"Retry-After": "30"}
        assert client._get_retry_after(mock_response) == 30

        # Missing
        mock_response.headers = {}
        assert client._get_retry_after(mock_response) is None

        # Invalid
        mock_response.headers = {"Retry-After": "not-a-number"}
        assert client._get_retry_after(mock_response) is None

    def test_is_rate_limited_true(self, client) -> None:
        """Test rate limiting check when enabled."""
        # Default client has rate limiting
        assert client._rate_limiter is not None

    def test_rate_limiter_stats(self, client) -> None:
        """Test rate limiter stats."""
        if client._rate_limiter is not None:
            stats = client._rate_limiter.stats
            assert stats is not None
            assert "requests_per_second" in stats

    def test_close(self, client) -> None:
        """Test close method."""
        # Should not raise
        client.close()

    def test_context_manager(self, client_class) -> None:
        """Test context manager usage."""
        with client_class(base_url="https://api.example.com") as client:
            assert client is not None


# =============================================================================
# Retry Utils Tests
# =============================================================================


class TestRetryUtils:
    """Tests for retry utility functions."""

    def test_calculate_delay(self) -> None:
        """Test calculate_delay function."""
        from spectryn.adapters.async_base.retry_utils import calculate_delay

        # Basic calculation
        delay = calculate_delay(0, initial_delay=1.0, max_delay=60.0)
        assert delay >= 0.9
        assert delay <= 1.1

        # With backoff
        delay = calculate_delay(2, initial_delay=1.0, max_delay=60.0, backoff_factor=2.0, jitter=0)
        assert delay == 4.0  # 1 * 2^2

        # Capped at max
        delay = calculate_delay(10, initial_delay=1.0, max_delay=10.0, backoff_factor=2.0, jitter=0)
        assert delay == 10.0

        # With retry_after
        delay = calculate_delay(0, initial_delay=1.0, max_delay=60.0, retry_after=30, jitter=0)
        assert delay == 30.0

    def test_get_retry_after(self) -> None:
        """Test get_retry_after function."""
        from spectryn.adapters.async_base.retry_utils import get_retry_after

        mock_response = Mock()

        # Valid
        mock_response.headers = {"Retry-After": "45"}
        assert get_retry_after(mock_response) == 45

        # Missing
        mock_response.headers = {}
        assert get_retry_after(mock_response) is None

        # Invalid
        mock_response.headers = {"Retry-After": "invalid"}
        assert get_retry_after(mock_response) is None


# =============================================================================
# Token Bucket Rate Limiter Tests
# =============================================================================


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    def test_initial_burst_capacity(self) -> None:
        """Test initial burst capacity."""
        from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(requests_per_second=10.0, burst_size=5)

        # Should be able to acquire burst_size tokens immediately
        for _ in range(5):
            assert limiter.try_acquire() is True

        # Next one should fail
        assert limiter.try_acquire() is False

    def test_token_refill(self) -> None:
        """Test tokens refill over time."""
        from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(requests_per_second=100.0, burst_size=1)

        # Use the token
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False

        # Wait for refill
        time.sleep(0.015)

        # Should have refilled
        assert limiter.try_acquire() is True

    def test_stats(self) -> None:
        """Test stats tracking."""
        from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(requests_per_second=10.0, burst_size=5)

        # Make some requests
        for _ in range(3):
            limiter.try_acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 3
        assert stats["burst_size"] == 5

    def test_reset(self) -> None:
        """Test reset restores initial state."""
        from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(requests_per_second=10.0, burst_size=5)

        # Use all tokens
        for _ in range(5):
            limiter.try_acquire()

        assert limiter.try_acquire() is False

        # Reset
        limiter.reset()

        # Should have full burst again
        assert limiter.available_tokens == 5.0

    def test_available_tokens(self) -> None:
        """Test available_tokens property."""
        from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(requests_per_second=10.0, burst_size=5)

        assert limiter.available_tokens == 5.0

        limiter.try_acquire()
        assert limiter.available_tokens < 5.0


# =============================================================================
# Async Rate Limiter Tests
# =============================================================================


@pytest.mark.asyncio
class TestAsyncRateLimiter:
    """Tests for AsyncRateLimiter."""

    async def test_acquire(self) -> None:
        """Test acquire method."""
        from spectryn.adapters.async_base.rate_limiter import AsyncRateLimiter

        limiter = AsyncRateLimiter(requests_per_second=100.0, burst_size=5)

        # Should acquire quickly
        await limiter.acquire()
        await limiter.acquire()

    async def test_update_from_response_success(self) -> None:
        """Test update from successful response."""
        from spectryn.adapters.async_base.rate_limiter import AsyncRateLimiter

        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)
        original_rate = limiter.requests_per_second

        await limiter.update_from_response(200, {})

        # Rate should not change on success
        assert limiter.requests_per_second == original_rate

    async def test_update_from_response_rate_limit(self) -> None:
        """Test update from 429 response."""
        from spectryn.adapters.async_base.rate_limiter import AsyncRateLimiter

        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)
        original_rate = limiter.requests_per_second

        await limiter.update_from_response(429, {})

        # Rate should be reduced
        assert limiter.requests_per_second < original_rate

    def test_stats(self) -> None:
        """Test stats property."""
        from spectryn.adapters.async_base.rate_limiter import AsyncRateLimiter

        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_size=5)

        stats = limiter.stats
        assert "requests_per_second" in stats
        assert "burst_size" in stats
