"""
Tests for AzureDevOpsApiClient.

Tests REST API client with mocked HTTP responses.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.azure_devops.client import AzureDevOpsRateLimiter


class TestAzureDevOpsRateLimiter:
    """Tests for AzureDevOpsRateLimiter."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=5.0, burst_size=10)
        assert limiter.requests_per_second == 5.0
        assert limiter.burst_size == 10

    def test_acquire_token(self):
        """Test acquiring a token."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=100.0, burst_size=10)
        result = limiter.acquire(timeout=1.0)
        assert result is True

    def test_acquire_depletes_tokens(self):
        """Test that acquiring depletes tokens."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=100.0, burst_size=5)

        for _ in range(5):
            limiter.acquire(timeout=0.1)

        assert limiter._tokens < 1.0

    def test_stats(self):
        """Test stats property."""
        limiter = AzureDevOpsRateLimiter()
        limiter.acquire()

        stats = limiter.stats
        assert "total_requests" in stats
        assert stats["total_requests"] == 1

    def test_reset(self):
        """Test reset method."""
        limiter = AzureDevOpsRateLimiter(burst_size=10)
        limiter.acquire()
        limiter.acquire()

        limiter.reset()

        assert limiter._tokens == 10.0
        assert limiter._total_requests == 0

    def test_update_from_response(self):
        """Test updating from response with Retry-After."""
        limiter = AzureDevOpsRateLimiter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Retry-After": "60"}

        limiter.update_from_response(mock_response)

        assert limiter._retry_after is not None

    def test_update_from_rate_limit_response(self):
        """Test rate adjustment on 429."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=10.0)
        original_rate = limiter.requests_per_second

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        limiter.update_from_response(mock_response)

        assert limiter.requests_per_second < original_rate

    def test_refill_tokens(self):
        """Test _refill_tokens adds tokens over time."""
        limiter = AzureDevOpsRateLimiter(requests_per_second=1000.0, burst_size=10)
        limiter._tokens = 0.0

        import time

        time.sleep(0.01)
        limiter._refill_tokens()

        assert limiter._tokens > 0


class TestAzureDevOpsApiClientInit:
    """Tests for AzureDevOpsApiClient initialization."""

    def test_init_sets_attributes(self):
        """Test initialization sets basic attributes."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="org",
                project="project",
                pat="pat123",
            )

            assert client.organization == "org"
            assert client.project == "project"
            assert client.dry_run is True

    def test_init_without_rate_limiter(self):
        """Test initialization without rate limiting."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="org",
                project="project",
                pat="pat123",
                requests_per_second=None,
            )

            assert client._rate_limiter is None

    def test_init_with_rate_limiter(self):
        """Test initialization with rate limiting."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="org",
                project="project",
                pat="pat123",
                requests_per_second=5.0,
            )

            assert client._rate_limiter is not None

    def test_build_url_wit(self):
        """Test building Work Item Tracking URL."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="test-org",
                project="test-project",
                pat="pat123",
            )

            url = client._build_url("workItems/123", area="wit")
            assert "test-org" in url
            assert "test-project" in url
            assert "_apis/wit/workItems/123" in url

    def test_build_url_core(self):
        """Test building Core API URL."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="test-org",
                project="test-project",
                pat="pat123",
            )

            url = client._build_url("projects", area="core")
            assert "_apis/projects" in url

    def test_build_url_absolute(self):
        """Test absolute URL pass-through."""
        with patch("spectryn.adapters.azure_devops.client.requests.Session"):
            from spectryn.adapters.azure_devops.client import AzureDevOpsApiClient

            client = AzureDevOpsApiClient(
                organization="test-org",
                project="test-project",
                pat="pat123",
            )

            url = "https://example.com/api/test"
            result = client._build_url(url)
            assert result == url
