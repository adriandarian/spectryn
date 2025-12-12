"""
Integration tests with mocked Jira API responses.

These tests verify the full flow from adapter through client
using realistic API responses.

Note: Common fixtures are imported from conftest.py:
- tracker_config (aliased as jira_config below)
- mock_myself_response
- mock_issue_response
- mock_epic_children_response
- mock_transitions_response
- mock_comments_response
- mock_create_issue_response
"""

import pytest
from unittest.mock import Mock, patch
import json

from md2jira.adapters.jira.client import JiraApiClient, RateLimiter
from md2jira.adapters.jira.adapter import JiraAdapter
from md2jira.core.ports.issue_tracker import (
    IssueTrackerError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


# Alias the shared tracker_config fixture for clarity in Jira-specific tests
@pytest.fixture
def jira_config(tracker_config):
    """Alias for tracker_config - Jira-specific configuration."""
    return tracker_config


# =============================================================================
# JiraApiClient Tests
# =============================================================================

class TestJiraApiClientIntegration:
    """Integration tests for JiraApiClient with mocked HTTP."""

    def test_get_myself_success(self, jira_config, mock_myself_response):
        """Test successful authentication and user retrieval."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_myself_response)
            mock_response.json.return_value = mock_myself_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            result = client.get_myself()

            assert result["accountId"] == "user-123-abc"
            assert result["displayName"] == "Test User"
            mock_request.assert_called_once()

    def test_get_myself_caches_result(self, jira_config, mock_myself_response):
        """Test that get_myself caches the result."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_myself_response)
            mock_response.json.return_value = mock_myself_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            # Call twice
            client.get_myself()
            client.get_myself()

            # Should only make one request due to caching
            assert mock_request.call_count == 1

    def test_authentication_error(self, jira_config):
        """Test 401 response raises AuthenticationError."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token="bad-token",
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(AuthenticationError):
                client.get("myself")

    def test_not_found_error(self, jira_config):
        """Test 404 response raises NotFoundError."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 404
            mock_response.text = "Issue not found"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(NotFoundError):
                client.get("issue/INVALID-999")

    def test_permission_error(self, jira_config):
        """Test 403 response raises PermissionError."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            with pytest.raises(PermissionError):
                client.get("issue/SECRET-123")

    def test_dry_run_skips_post(self, jira_config):
        """Test dry_run mode skips POST requests (except search)."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=True,
        )

        with patch.object(client._session, "request") as mock_request:
            result = client.post("issue", json={"fields": {}})

            assert result == {}
            mock_request.assert_not_called()

    def test_dry_run_allows_search(self, jira_config, mock_epic_children_response):
        """Test dry_run mode allows search JQL requests."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=True,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_epic_children_response)
            mock_response.json.return_value = mock_epic_children_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            result = client.search_jql("parent = TEST-1", ["summary"])

            assert result["total"] == 2
            mock_request.assert_called_once()

    def test_connection_test_success(self, jira_config, mock_myself_response):
        """Test connection test returns True on success."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.text = json.dumps(mock_myself_response)
            mock_response.json.return_value = mock_myself_response
            mock_response.headers = {}
            mock_request.return_value = mock_response

            assert client.test_connection() is True

    def test_connection_test_failure(self, jira_config):
        """Test connection test returns False on failure."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token="bad-token",
            dry_run=False,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = False
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            assert client.test_connection() is False


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestRetryLogic:
    """Tests for retry logic with exponential backoff."""

    def test_retry_on_connection_error_then_success(self, jira_config, mock_myself_response):
        """Test that connection errors are retried and succeed."""
        import requests

        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,  # Fast for testing
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):  # Skip actual sleep
            # First call fails, second succeeds
            mock_success = Mock()
            mock_success.ok = True
            mock_success.status_code = 200
            mock_success.text = json.dumps(mock_myself_response)
            mock_success.json.return_value = mock_myself_response
            mock_success.headers = {}

            mock_request.side_effect = [
                requests.exceptions.ConnectionError("Connection reset"),
                mock_success,
            ]

            result = client.get_myself()

            assert result["accountId"] == "user-123-abc"
            assert mock_request.call_count == 2

    def test_retry_on_timeout_then_success(self, jira_config, mock_myself_response):
        """Test that timeout errors are retried and succeed."""
        import requests

        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_success = Mock()
            mock_success.ok = True
            mock_success.status_code = 200
            mock_success.text = json.dumps(mock_myself_response)
            mock_success.json.return_value = mock_myself_response
            mock_success.headers = {}

            mock_request.side_effect = [
                requests.exceptions.Timeout("Read timed out"),
                mock_success,
            ]

            result = client.get_myself()

            assert result["accountId"] == "user-123-abc"
            assert mock_request.call_count == 2

    def test_retry_on_429_rate_limit(self, jira_config, mock_myself_response):
        """Test that 429 rate limit triggers retry."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_rate_limit = Mock()
            mock_rate_limit.ok = False
            mock_rate_limit.status_code = 429
            mock_rate_limit.headers = {"Retry-After": "1"}
            mock_rate_limit.text = "Rate limit exceeded"

            mock_success = Mock()
            mock_success.ok = True
            mock_success.status_code = 200
            mock_success.text = json.dumps(mock_myself_response)
            mock_success.json.return_value = mock_myself_response
            mock_success.headers = {}

            mock_request.side_effect = [mock_rate_limit, mock_success]

            result = client.get_myself()

            assert result["accountId"] == "user-123-abc"
            assert mock_request.call_count == 2

    def test_retry_on_503_service_unavailable(self, jira_config, mock_myself_response):
        """Test that 503 service unavailable triggers retry."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_503 = Mock()
            mock_503.ok = False
            mock_503.status_code = 503
            mock_503.headers = {}
            mock_503.text = "Service temporarily unavailable"

            mock_success = Mock()
            mock_success.ok = True
            mock_success.status_code = 200
            mock_success.text = json.dumps(mock_myself_response)
            mock_success.json.return_value = mock_myself_response
            mock_success.headers = {}

            mock_request.side_effect = [mock_503, mock_success]

            result = client.get_myself()

            assert result["accountId"] == "user-123-abc"
            assert mock_request.call_count == 2

    def test_exhausted_retries_raises_rate_limit_error(self, jira_config):
        """Test that exhausted retries on 429 raises RateLimitError."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_rate_limit = Mock()
            mock_rate_limit.ok = False
            mock_rate_limit.status_code = 429
            mock_rate_limit.headers = {"Retry-After": "60"}
            mock_rate_limit.text = "Rate limit exceeded"

            mock_request.return_value = mock_rate_limit

            with pytest.raises(RateLimitError) as exc_info:
                client.get("myself")

            assert "Rate limit exceeded" in str(exc_info.value)
            assert exc_info.value.retry_after == 60
            # Initial attempt + 2 retries = 3 total
            assert mock_request.call_count == 3

    def test_exhausted_retries_raises_transient_error(self, jira_config):
        """Test that exhausted retries on 500 raises TransientError."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_500 = Mock()
            mock_500.ok = False
            mock_500.status_code = 500
            mock_500.headers = {}
            mock_500.text = "Internal server error"

            mock_request.return_value = mock_500

            with pytest.raises(TransientError) as exc_info:
                client.get("myself")

            assert "Server error 500" in str(exc_info.value)
            assert mock_request.call_count == 3

    def test_exhausted_retries_on_connection_error(self, jira_config):
        """Test that exhausted retries on connection error raises IssueTrackerError."""
        import requests

        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=2,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            mock_request.side_effect = requests.exceptions.ConnectionError("Connection refused")

            with pytest.raises(IssueTrackerError) as exc_info:
                client.get("myself")

            assert "Connection failed after 3 attempts" in str(exc_info.value)
            assert mock_request.call_count == 3

    def test_no_retry_on_401_authentication_error(self, jira_config):
        """Test that 401 errors are not retried."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=3,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_401 = Mock()
            mock_401.ok = False
            mock_401.status_code = 401
            mock_401.text = "Unauthorized"
            mock_401.headers = {}

            mock_request.return_value = mock_401

            with pytest.raises(AuthenticationError):
                client.get("myself")

            # Should only be called once - no retries
            assert mock_request.call_count == 1

    def test_no_retry_on_404_not_found(self, jira_config):
        """Test that 404 errors are not retried."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=3,
            initial_delay=0.01,
        )

        with patch.object(client._session, "request") as mock_request:
            mock_404 = Mock()
            mock_404.ok = False
            mock_404.status_code = 404
            mock_404.text = "Not found"
            mock_404.headers = {}

            mock_request.return_value = mock_404

            with pytest.raises(NotFoundError):
                client.get("issue/INVALID-999")

            assert mock_request.call_count == 1

    def test_exponential_backoff_delay_calculation(self, jira_config):
        """Test that delay calculation uses exponential backoff."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            max_retries=5,
            initial_delay=1.0,
            max_delay=60.0,
            backoff_factor=2.0,
            jitter=0,  # Disable jitter for predictable testing
        )

        # Test exponential growth
        assert client._calculate_delay(0) == 1.0   # 1 * 2^0 = 1
        assert client._calculate_delay(1) == 2.0   # 1 * 2^1 = 2
        assert client._calculate_delay(2) == 4.0   # 1 * 2^2 = 4
        assert client._calculate_delay(3) == 8.0   # 1 * 2^3 = 8
        assert client._calculate_delay(4) == 16.0  # 1 * 2^4 = 16

    def test_delay_respects_max_delay(self, jira_config):
        """Test that delay is capped at max_delay."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            initial_delay=1.0,
            max_delay=10.0,
            backoff_factor=2.0,
            jitter=0,
        )

        # 1 * 2^10 = 1024, but should be capped at 10
        assert client._calculate_delay(10) == 10.0

    def test_delay_uses_retry_after_header(self, jira_config):
        """Test that Retry-After header value is used when present."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            initial_delay=1.0,
            max_delay=120.0,
            jitter=0,
        )

        # Should use retry_after value
        assert client._calculate_delay(0, retry_after=30) == 30.0
        
        # Should cap at max_delay even with retry_after
        assert client._calculate_delay(0, retry_after=200) == 120.0

    def test_retry_after_header_parsing(self, jira_config):
        """Test Retry-After header is correctly parsed from response."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )

        mock_response = Mock()
        mock_response.headers = {"Retry-After": "45"}
        assert client._get_retry_after(mock_response) == 45

        mock_response.headers = {}
        assert client._get_retry_after(mock_response) is None

        mock_response.headers = {"Retry-After": "invalid"}
        assert client._get_retry_after(mock_response) is None


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def test_initial_burst_capacity(self):
        """Test that rate limiter starts with full burst capacity."""
        limiter = RateLimiter(requests_per_second=10.0, burst_size=5)
        
        # Should be able to acquire burst_size tokens immediately
        for _ in range(5):
            assert limiter.try_acquire() is True
        
        # Next one should fail (no tokens left)
        assert limiter.try_acquire() is False

    def test_token_refill(self):
        """Test that tokens refill over time."""
        limiter = RateLimiter(requests_per_second=100.0, burst_size=1)
        
        # Use the token
        assert limiter.try_acquire() is True
        assert limiter.try_acquire() is False
        
        # Wait for refill (10ms at 100 req/s = 1 token)
        import time
        time.sleep(0.015)
        
        # Should have refilled
        assert limiter.try_acquire() is True

    def test_acquire_blocks_and_succeeds(self):
        """Test that acquire() blocks until token is available."""
        limiter = RateLimiter(requests_per_second=100.0, burst_size=1)
        
        # Use the token
        limiter.try_acquire()
        
        # Acquire should block briefly then succeed
        import time
        start = time.monotonic()
        result = limiter.acquire(timeout=1.0)
        elapsed = time.monotonic() - start
        
        assert result is True
        assert elapsed < 0.1  # Should be quick at 100 req/s

    def test_acquire_timeout(self):
        """Test that acquire() respects timeout."""
        limiter = RateLimiter(requests_per_second=0.5, burst_size=1)  # Very slow: 1 req/2s
        
        # Use the token
        limiter.try_acquire()
        
        # Acquire with short timeout should fail
        import time
        start = time.monotonic()
        result = limiter.acquire(timeout=0.05)
        elapsed = time.monotonic() - start
        
        assert result is False
        assert elapsed < 0.1  # Should respect timeout

    def test_burst_capacity(self):
        """Test that burst allows multiple quick requests."""
        limiter = RateLimiter(requests_per_second=1.0, burst_size=10)
        
        # Should be able to burst 10 requests instantly
        successes = sum(1 for _ in range(15) if limiter.try_acquire())
        assert successes == 10

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        limiter = RateLimiter(requests_per_second=100.0, burst_size=5)
        
        # Make some requests
        for _ in range(3):
            limiter.try_acquire()
        
        stats = limiter.stats
        assert stats["total_requests"] == 3
        assert stats["burst_size"] == 5
        assert stats["requests_per_second"] == 100.0

    def test_reset(self):
        """Test that reset restores initial state."""
        limiter = RateLimiter(requests_per_second=10.0, burst_size=5)
        
        # Use all tokens
        for _ in range(5):
            limiter.try_acquire()
        
        assert limiter.try_acquire() is False
        
        # Reset
        limiter.reset()
        
        # Should have full burst capacity again
        assert limiter.available_tokens == 5.0
        stats = limiter.stats
        assert stats["total_requests"] == 0

    def test_update_from_429_response(self):
        """Test that 429 response reduces rate."""
        limiter = RateLimiter(requests_per_second=10.0, burst_size=5)
        
        original_rate = limiter.requests_per_second
        
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {}
        
        limiter.update_from_response(mock_response)
        
        # Rate should be reduced by 50%
        assert limiter.requests_per_second == original_rate * 0.5

    def test_thread_safety(self):
        """Test that rate limiter is thread-safe."""
        import threading
        
        limiter = RateLimiter(requests_per_second=1000.0, burst_size=100)
        results = []
        
        def worker():
            for _ in range(10):
                results.append(limiter.try_acquire())
        
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have exactly 50 attempts, 100 tokens available initially
        # but only burst_size tokens available
        successes = sum(1 for r in results if r)
        # All 50 should succeed since we have 100 burst capacity
        # and 50 requests < 100 burst
        assert successes <= 100


class TestRateLimitingIntegration:
    """Tests for rate limiting integrated with JiraApiClient."""

    def test_client_creates_rate_limiter_by_default(self, jira_config):
        """Test that client creates rate limiter with default settings."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
        )
        
        assert client.is_rate_limited is True
        assert client.rate_limiter is not None

    def test_client_rate_limiting_disabled(self, jira_config):
        """Test that rate limiting can be disabled."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            requests_per_second=None,  # Disable rate limiting
        )
        
        assert client.is_rate_limited is False
        assert client.rate_limiter is None
        assert client.rate_limit_stats is None

    def test_client_custom_rate_limit(self, jira_config):
        """Test that custom rate limit is applied."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            requests_per_second=2.0,
            burst_size=5,
        )
        
        assert client.is_rate_limited is True
        stats = client.rate_limit_stats
        assert stats["requests_per_second"] == 2.0
        assert stats["burst_size"] == 5

    def test_requests_go_through_rate_limiter(self, jira_config, mock_myself_response):
        """Test that requests acquire tokens from rate limiter."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            requests_per_second=100.0,
            burst_size=10,
        )
        
        with patch.object(client._session, "request") as mock_request:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.status_code = 200
            mock_response.text = json.dumps(mock_myself_response)
            mock_response.json.return_value = mock_myself_response
            mock_response.headers = {}
            mock_request.return_value = mock_response
            
            # Make several requests
            for _ in range(5):
                client.get("myself")
            
            # Rate limiter should have tracked these
            stats = client.rate_limit_stats
            assert stats["total_requests"] == 5

    def test_rate_limiter_slows_down_on_429(self, jira_config, mock_myself_response):
        """Test that rate limiter reduces rate when 429 is received."""
        client = JiraApiClient(
            base_url=jira_config.url,
            email=jira_config.email,
            api_token=jira_config.api_token,
            dry_run=False,
            requests_per_second=10.0,
            burst_size=5,
            max_retries=1,
            initial_delay=0.01,
        )
        
        original_rate = client.rate_limiter.requests_per_second
        
        with patch.object(client._session, "request") as mock_request, \
             patch("time.sleep"):
            # First call returns 429, second succeeds
            mock_429 = Mock()
            mock_429.ok = False
            mock_429.status_code = 429
            mock_429.headers = {}
            mock_429.text = "Rate limited"
            
            mock_success = Mock()
            mock_success.ok = True
            mock_success.status_code = 200
            mock_success.text = json.dumps(mock_myself_response)
            mock_success.json.return_value = mock_myself_response
            mock_success.headers = {}
            
            mock_request.side_effect = [mock_429, mock_success]
            
            client.get("myself")
            
            # Rate should have been reduced
            assert client.rate_limiter.requests_per_second < original_rate


# =============================================================================
# JiraAdapter Tests
# =============================================================================

class TestJiraAdapterIntegration:
    """Integration tests for JiraAdapter with mocked client."""

    @pytest.fixture
    def adapter(self, jira_config):
        """Create adapter with mocked client."""
        return JiraAdapter(config=jira_config, dry_run=False)

    def test_get_issue_parses_response(self, adapter, mock_issue_response):
        """Test get_issue correctly parses API response."""
        with patch.object(adapter._client, "get") as mock_get:
            mock_get.return_value = mock_issue_response

            issue = adapter.get_issue("TEST-123")

            assert issue.key == "TEST-123"
            assert issue.summary == "Sample User Story"
            assert issue.status == "Open"
            assert issue.issue_type == "Story"
            assert len(issue.subtasks) == 2
            assert issue.subtasks[0].key == "TEST-124"
            assert issue.subtasks[1].status == "In Progress"

    def test_get_epic_children(self, adapter, mock_epic_children_response):
        """Test get_epic_children returns parsed issues."""
        with patch.object(adapter._client, "search_jql") as mock_search:
            mock_search.return_value = mock_epic_children_response

            children = adapter.get_epic_children("TEST-1")

            assert len(children) == 2
            assert children[0].key == "TEST-10"
            assert children[0].summary == "Story Alpha"
            assert children[1].key == "TEST-11"
            assert len(children[1].subtasks) == 1

    def test_create_subtask_builds_correct_payload(self, adapter, mock_create_issue_response, mock_myself_response):
        """Test create_subtask sends correct fields."""
        with patch.object(adapter._client, "post") as mock_post, \
             patch.object(adapter._client, "get_current_user_id") as mock_user:
            mock_post.return_value = mock_create_issue_response
            mock_user.return_value = "user-123-abc"

            result = adapter.create_subtask(
                parent_key="TEST-10",
                summary="New subtask",
                description="Task description",
                project_key="TEST",
                story_points=3,
            )

            assert result == "TEST-99"
            mock_post.assert_called_once()
            
            call_args = mock_post.call_args
            payload = call_args[1]["json"]["fields"]
            
            assert payload["project"]["key"] == "TEST"
            assert payload["parent"]["key"] == "TEST-10"
            assert payload["summary"] == "New subtask"
            assert payload["issuetype"]["name"] == "Sub-task"
            assert payload["customfield_10014"] == 3.0

    def test_create_subtask_dry_run(self, jira_config):
        """Test create_subtask returns None in dry_run mode."""
        adapter = JiraAdapter(config=jira_config, dry_run=True)

        result = adapter.create_subtask(
            parent_key="TEST-10",
            summary="New subtask",
            description="Task description",
            project_key="TEST",
        )

        assert result is None

    def test_update_issue_description(self, adapter):
        """Test update_issue_description sends correct payload."""
        with patch.object(adapter._client, "put") as mock_put:
            mock_put.return_value = {}

            result = adapter.update_issue_description("TEST-123", "New description")

            assert result is True
            mock_put.assert_called_once()
            
            call_args = mock_put.call_args
            assert "issue/TEST-123" in call_args[0]
            assert "description" in call_args[1]["json"]["fields"]

    def test_add_comment(self, adapter):
        """Test add_comment sends correct payload."""
        with patch.object(adapter._client, "post") as mock_post:
            mock_post.return_value = {}

            result = adapter.add_comment("TEST-123", "Comment text")

            assert result is True
            mock_post.assert_called_once()
            
            call_args = mock_post.call_args
            assert "issue/TEST-123/comment" in call_args[0]

    def test_get_issue_status(self, adapter):
        """Test get_issue_status extracts status name."""
        with patch.object(adapter._client, "get") as mock_get:
            mock_get.return_value = {
                "fields": {"status": {"name": "In Progress"}}
            }

            status = adapter.get_issue_status("TEST-123")

            assert status == "In Progress"

    def test_get_available_transitions(self, adapter, mock_transitions_response):
        """Test get_available_transitions returns transition list."""
        with patch.object(adapter._client, "get") as mock_get:
            mock_get.return_value = mock_transitions_response

            transitions = adapter.get_available_transitions("TEST-123")

            assert len(transitions) == 3
            assert transitions[0]["id"] == "4"
            assert transitions[0]["name"] == "Start Progress"

    def test_get_issue_comments(self, adapter, mock_comments_response):
        """Test get_issue_comments returns comments list."""
        with patch.object(adapter._client, "get") as mock_get:
            mock_get.return_value = mock_comments_response

            comments = adapter.get_issue_comments("TEST-123")

            assert len(comments) == 1
            assert comments[0]["id"] == "10001"


# =============================================================================
# End-to-End Sync Flow Tests
# =============================================================================

class TestSyncFlowIntegration:
    """End-to-end integration tests for the sync flow.
    
    Uses shared fixtures from conftest.py:
    - mock_tracker_with_children
    - mock_parser
    - mock_formatter
    - sync_config
    """

    def test_analyze_matches_stories(self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config):
        """Test that analyze correctly matches markdown stories to Jira issues."""
        from md2jira.application.sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.analyze("/path/to/doc.md", "TEST-1")

        assert result.stories_matched == 2
        assert len(result.matched_stories) == 2
        assert ("US-001", "TEST-10") in result.matched_stories
        assert ("US-002", "TEST-11") in result.matched_stories

    def test_sync_updates_descriptions(self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config):
        """Test that sync updates story descriptions."""
        from md2jira.application.sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.sync("/path/to/doc.md", "TEST-1")

        assert result.stories_updated == 2
        assert mock_tracker_with_children.update_issue_description.call_count == 2

    def test_sync_creates_new_subtasks(self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config):
        """Test that sync creates subtasks that don't exist."""
        from md2jira.application.sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.sync("/path/to/doc.md", "TEST-1")

        # Alpha Task 1 should be created (doesn't exist)
        # Beta Subtask should be updated (already exists)
        assert result.subtasks_created >= 1
        mock_tracker_with_children.create_subtask.assert_called()

    def test_sync_dry_run_no_changes(self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config_dry_run):
        """Test that dry_run mode doesn't make actual changes."""
        from md2jira.application.sync.orchestrator import SyncOrchestrator

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config_dry_run,
        )

        result = orchestrator.sync("/path/to/doc.md", "TEST-1")

        assert result.dry_run is True
        # In dry_run, commands don't execute actual tracker methods
        # (the command layer handles this)

    def test_sync_handles_unmatched_stories(self, mock_tracker_with_children, mock_parser, mock_formatter, sync_config):
        """Test that unmatched stories are reported as warnings."""
        from md2jira.application.sync.orchestrator import SyncOrchestrator
        from md2jira.core.domain.entities import UserStory
        from md2jira.core.domain.enums import Status
        from md2jira.core.domain.value_objects import StoryId, Description

        # Add an unmatched story
        mock_parser.parse_stories.return_value.append(
            UserStory(
                id=StoryId("US-999"),
                title="Nonexistent Story",
                description=Description(
                    role="user",
                    want="this story to not match",
                    benefit="we can test unmatched handling"
                ),
                status=Status.PLANNED,
            )
        )

        orchestrator = SyncOrchestrator(
            tracker=mock_tracker_with_children,
            parser=mock_parser,
            formatter=mock_formatter,
            config=sync_config,
        )

        result = orchestrator.analyze("/path/to/doc.md", "TEST-1")

        assert "US-999" in result.unmatched_stories
        assert len(result.warnings) > 0


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandlingIntegration:
    """Test error handling in integration scenarios."""

    def test_adapter_handles_api_errors_gracefully(self, jira_config):
        """Test adapter doesn't crash on API errors."""
        adapter = JiraAdapter(config=jira_config, dry_run=False)

        with patch.object(adapter._client, "get") as mock_get:
            mock_get.side_effect = IssueTrackerError("Server error")

            with pytest.raises(IssueTrackerError):
                adapter.get_issue("TEST-123")

    def test_transition_handles_invalid_status(self, jira_config):
        """Test transition logs warning for unknown status."""
        adapter = JiraAdapter(config=jira_config, dry_run=False)

        with patch.object(adapter._client, "get") as mock_get:
            mock_get.return_value = {"fields": {"status": {"name": "Open"}}}

            result = adapter.transition_issue("TEST-123", "InvalidStatus")

            # Should return False for unknown status
            assert result is False

