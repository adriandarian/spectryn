"""
Tests for LinearApiClient.

Tests GraphQL API client with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.linear.client import LinearRateLimiter


class TestLinearRateLimiter:
    """Tests for LinearRateLimiter."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = LinearRateLimiter(requests_per_second=1.0, burst_size=10)
        assert limiter.requests_per_second == 1.0
        assert limiter.burst_size == 10

    def test_acquire_token(self):
        """Test acquiring a token."""
        limiter = LinearRateLimiter(requests_per_second=100.0, burst_size=10)
        result = limiter.acquire(timeout=1.0)
        assert result is True

    def test_acquire_depletes_tokens(self):
        """Test that acquiring depletes tokens."""
        limiter = LinearRateLimiter(requests_per_second=100.0, burst_size=5)

        for _ in range(5):
            limiter.acquire(timeout=0.1)

        assert limiter._tokens < 1.0

    def test_update_from_response(self):
        """Test updating from Linear response headers."""
        limiter = LinearRateLimiter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-RateLimit-Requests-Remaining": "1450",
            "X-RateLimit-Requests-Reset": "1234567890",
        }

        limiter.update_from_response(mock_response)

        assert limiter._requests_remaining == 1450

    def test_update_from_rate_limit_response(self):
        """Test rate adjustment on 429."""
        limiter = LinearRateLimiter(requests_per_second=1.0)
        original_rate = limiter.requests_per_second

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        limiter.update_from_response(mock_response)

        assert limiter.requests_per_second < original_rate

    def test_refill_tokens(self):
        """Test _refill_tokens adds tokens over time."""
        limiter = LinearRateLimiter(requests_per_second=1000.0, burst_size=10)
        limiter._tokens = 0.0

        import time

        time.sleep(0.01)
        limiter._refill_tokens()

        assert limiter._tokens > 0


class TestLinearApiClientInit:
    """Tests for LinearApiClient initialization."""

    def test_init_sets_attributes(self):
        """Test initialization sets basic attributes."""
        with patch("spectryn.adapters.linear.client.requests.Session"):
            from spectryn.adapters.linear.client import LinearApiClient

            client = LinearApiClient(
                api_key="lin_api_test",
            )

            assert client.api_key == "lin_api_test"
            assert client.dry_run is True

    def test_init_without_rate_limiter(self):
        """Test initialization without rate limiting."""
        with patch("spectryn.adapters.linear.client.requests.Session"):
            from spectryn.adapters.linear.client import LinearApiClient

            client = LinearApiClient(
                api_key="lin_api_test",
                requests_per_second=None,
            )

            assert client._rate_limiter is None

    def test_init_with_rate_limiter(self):
        """Test initialization with rate limiting."""
        with patch("spectryn.adapters.linear.client.requests.Session"):
            from spectryn.adapters.linear.client import LinearApiClient

            client = LinearApiClient(
                api_key="lin_api_test",
                requests_per_second=1.0,
            )

            assert client._rate_limiter is not None
