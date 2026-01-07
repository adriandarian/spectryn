"""
Tests for resilience adapters.

Tests the concrete implementations:
- TokenBucketRateLimiter
- SlidingWindowRateLimiter
- RetryPolicy
- CircuitBreaker
- ResilienceManager
"""

import contextlib
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spectra.adapters.resilience import (
    CircuitBreaker,
    ResilienceManager,
    RetryPolicy,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
    create_resilience_manager,
)
from spectra.core.ports.rate_limiting import (
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    RateLimitConfig,
    RateLimitContext,
    RetryAttempt,
    RetryConfig,
    RetryExhaustedError,
    RetryStrategy,
    TrackerType,
)


class TestTokenBucketRateLimiter:
    """Tests for TokenBucketRateLimiter."""

    @pytest.fixture
    def config(self):
        """Create a test rate limit config."""
        return RateLimitConfig(
            requests_per_second=10.0,
            burst_size=5,
            adaptive=True,
        )

    @pytest.fixture
    def limiter(self, config):
        """Create a test rate limiter."""
        return TokenBucketRateLimiter(config)

    def test_acquire_succeeds_with_tokens(self, limiter):
        """Test that acquire succeeds when tokens available."""
        assert limiter.acquire() is True

    def test_try_acquire_succeeds(self, limiter):
        """Test that try_acquire succeeds when tokens available."""
        assert limiter.try_acquire() is True

    def test_try_acquire_depletes_tokens(self, limiter):
        """Test that try_acquire depletes tokens."""
        # Deplete all burst tokens
        for _ in range(5):
            assert limiter.try_acquire() is True
        # Next should fail (no waiting)
        assert limiter.try_acquire() is False

    def test_acquire_with_timeout(self, config):
        """Test acquire with timeout when no tokens."""
        # Create limiter with no initial tokens
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_second=0.1,  # Very slow refill
                burst_size=1,
            )
        )
        # Use the one token
        limiter.acquire()
        # Next should timeout
        start = time.monotonic()
        result = limiter.acquire(timeout=0.1)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed >= 0.09

    def test_tokens_refill(self, limiter):
        """Test that tokens refill over time."""
        # Deplete all tokens
        for _ in range(5):
            limiter.try_acquire()
        assert limiter.try_acquire() is False

        # Wait for refill (at 10/sec, should get a token in ~0.1s)
        time.sleep(0.15)
        assert limiter.try_acquire() is True

    def test_update_from_response_429(self, limiter):
        """Test that 429 response reduces rate."""
        original_rate = limiter.get_stats().current_rate
        limiter.update_from_response(429, {})
        new_rate = limiter.get_stats().current_rate
        assert new_rate < original_rate

    def test_update_from_response_parses_headers(self, limiter):
        """Test that headers are parsed correctly."""
        headers = {
            "X-RateLimit-Remaining": "10",
            "X-RateLimit-Reset": str(time.time() + 60),
        }
        limiter.update_from_response(200, headers)
        # Headers should be parsed without error

    def test_get_stats(self, limiter):
        """Test getting statistics."""
        limiter.acquire()
        stats = limiter.get_stats()
        assert stats.total_requests == 1
        assert stats.current_rate == 10.0

    def test_reset(self, limiter):
        """Test reset clears state."""
        for _ in range(5):
            limiter.try_acquire()
        limiter.reset()
        stats = limiter.get_stats()
        assert stats.total_requests == 0
        assert stats.available_tokens == 5.0

    def test_config_property(self, limiter, config):
        """Test config property."""
        assert limiter.config == config


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    @pytest.fixture
    def config(self):
        """Create a test rate limit config."""
        return RateLimitConfig(
            requests_per_second=10.0,
            window_seconds=1.0,
            adaptive=True,
        )

    @pytest.fixture
    def limiter(self, config):
        """Create a test rate limiter."""
        return SlidingWindowRateLimiter(config)

    def test_acquire_succeeds(self, limiter):
        """Test that acquire succeeds."""
        assert limiter.acquire() is True

    def test_try_acquire_succeeds(self, limiter):
        """Test that try_acquire succeeds."""
        assert limiter.try_acquire() is True

    def test_window_limit_enforced(self, limiter):
        """Test that window limit is enforced."""
        # Use all 10 requests in window
        for _ in range(10):
            assert limiter.try_acquire() is True
        # Next should fail
        assert limiter.try_acquire() is False

    def test_window_slides(self, limiter):
        """Test that window slides to allow new requests."""
        # Use all requests
        for _ in range(10):
            limiter.try_acquire()
        assert limiter.try_acquire() is False

        # Wait for window to slide
        time.sleep(1.1)
        assert limiter.try_acquire() is True

    def test_get_stats(self, limiter):
        """Test getting statistics."""
        limiter.acquire()
        limiter.acquire()
        stats = limiter.get_stats()
        assert stats.total_requests == 2
        assert stats.requests_in_window == 2

    def test_reset(self, limiter):
        """Test reset clears state."""
        for _ in range(5):
            limiter.try_acquire()
        limiter.reset()
        stats = limiter.get_stats()
        assert stats.total_requests == 0
        assert stats.requests_in_window == 0


class TestRetryPolicy:
    """Tests for RetryPolicy."""

    @pytest.fixture
    def config(self):
        """Create a test retry config."""
        return RetryConfig(
            max_retries=3,
            initial_delay=0.1,
            max_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        )

    @pytest.fixture
    def policy(self, config):
        """Create a test retry policy."""
        return RetryPolicy(config)

    def test_should_retry_on_429(self, policy):
        """Test that 429 triggers retry."""
        assert policy.should_retry(status_code=429, attempt=0) is True

    def test_should_retry_on_500(self, policy):
        """Test that 500 triggers retry."""
        assert policy.should_retry(status_code=500, attempt=0) is True

    def test_should_not_retry_on_200(self, policy):
        """Test that 200 does not trigger retry."""
        assert policy.should_retry(status_code=200, attempt=0) is False

    def test_should_not_retry_on_404(self, policy):
        """Test that 404 does not trigger retry."""
        assert policy.should_retry(status_code=404, attempt=0) is False

    def test_should_retry_on_connection_error(self, policy):
        """Test that ConnectionError triggers retry."""
        assert policy.should_retry(exception=ConnectionError(), attempt=0) is True

    def test_should_not_retry_after_max_attempts(self, policy):
        """Test that retry stops after max attempts."""
        assert policy.should_retry(status_code=500, attempt=3) is False

    def test_get_delay_exponential(self, config):
        """Test exponential backoff delay."""
        policy = RetryPolicy(
            RetryConfig(
                initial_delay=1.0,
                backoff_factor=2.0,
                jitter=0.0,
                strategy=RetryStrategy.EXPONENTIAL,
            )
        )
        assert policy.get_delay(0) == pytest.approx(1.0, abs=0.01)
        assert policy.get_delay(1) == pytest.approx(2.0, abs=0.01)
        assert policy.get_delay(2) == pytest.approx(4.0, abs=0.01)

    def test_get_delay_respects_retry_after(self, policy):
        """Test that Retry-After header is respected (within max_delay bounds)."""
        # retry_after=30 but max_delay=1.0, so should be capped at 1.0
        delay = policy.get_delay(0, retry_after=30)
        assert delay == pytest.approx(1.0, rel=0.01)

        # Also test retry_after within max_delay bounds
        delay2 = policy.get_delay(0, retry_after=0.5)
        assert delay2 == pytest.approx(0.5, rel=0.01)

    def test_record_attempt(self, policy):
        """Test recording retry attempts."""
        attempt = RetryAttempt(attempt=0, delay=1.0, reason="Error")
        policy.record_attempt(attempt)
        assert len(policy.get_attempts()) == 1
        assert policy.get_attempts()[0].reason == "Error"

    def test_reset(self, policy):
        """Test reset clears attempts."""
        policy.record_attempt(RetryAttempt(attempt=0, delay=1.0, reason="Error"))
        policy.reset()
        assert len(policy.get_attempts()) == 0


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def config(self):
        """Create a test circuit breaker config."""
        return CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            reset_timeout=0.5,  # Fast for tests
            half_open_max_calls=2,
        )

    @pytest.fixture
    def breaker(self, config):
        """Create a test circuit breaker."""
        return CircuitBreaker(config)

    def test_initial_state_closed(self, breaker):
        """Test that initial state is closed."""
        assert breaker.get_state() == CircuitState.CLOSED

    def test_allow_request_when_closed(self, breaker):
        """Test that requests are allowed when closed."""
        assert breaker.allow_request() is True

    def test_opens_after_failures(self, breaker):
        """Test that circuit opens after failure threshold."""
        for _ in range(3):
            breaker.record_failure(500)
        assert breaker.get_state() == CircuitState.OPEN

    def test_rejects_when_open(self, breaker):
        """Test that requests are rejected when open."""
        for _ in range(3):
            breaker.record_failure(500)
        with pytest.raises(CircuitOpenError):
            breaker.allow_request()

    def test_transitions_to_half_open(self, breaker):
        """Test transition to half-open after reset timeout."""
        for _ in range(3):
            breaker.record_failure(500)
        assert breaker.get_state() == CircuitState.OPEN

        # Wait for reset timeout
        time.sleep(0.6)
        assert breaker.get_state() == CircuitState.HALF_OPEN

    def test_closes_after_successes_in_half_open(self, breaker):
        """Test that circuit closes after successes in half-open."""
        # Open the circuit
        for _ in range(3):
            breaker.record_failure(500)
        time.sleep(0.6)  # Wait for half-open

        # Record successes
        breaker.allow_request()
        breaker.record_success()
        breaker.allow_request()
        breaker.record_success()

        assert breaker.get_state() == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self, breaker):
        """Test that circuit reopens on failure in half-open."""
        # Open the circuit
        for _ in range(3):
            breaker.record_failure(500)
        time.sleep(0.6)  # Wait for half-open

        # Record failure
        breaker.allow_request()
        breaker.record_failure(500)

        assert breaker.get_state() == CircuitState.OPEN

    def test_rate_limit_not_failure(self, config):
        """Test that 429 doesn't count as failure by default."""
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=3,
                count_rate_limit_as_failure=False,
            )
        )
        for _ in range(5):
            breaker.record_failure(429)
        assert breaker.get_state() == CircuitState.CLOSED

    def test_get_stats(self, breaker):
        """Test getting statistics."""
        breaker.record_success()
        breaker.record_failure(500)
        stats = breaker.get_stats()
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1

    def test_reset(self, breaker):
        """Test reset returns to closed state."""
        for _ in range(3):
            breaker.record_failure(500)
        assert breaker.get_state() == CircuitState.OPEN

        breaker.reset()
        assert breaker.get_state() == CircuitState.CLOSED


class TestResilienceManager:
    """Tests for ResilienceManager."""

    @pytest.fixture
    def manager(self):
        """Create a test resilience manager."""
        return create_resilience_manager(
            TrackerType.CUSTOM,
            rate_limit_config=RateLimitConfig(
                requests_per_second=100.0,  # Fast for tests
                burst_size=100,
            ),
            retry_config=RetryConfig(
                max_retries=2,
                initial_delay=0.01,
            ),
            circuit_breaker_config=CircuitBreakerConfig(
                failure_threshold=3,
                reset_timeout=0.5,
            ),
        )

    def test_execute_success(self, manager):
        """Test successful execution."""
        result = manager.execute(lambda: "success")
        assert result == "success"

    def test_execute_with_context(self, manager):
        """Test execution with context."""
        context = RateLimitContext(endpoint="/api/test")
        result = manager.execute(lambda: "success", context)
        assert result == "success"

    def test_execute_retries_on_failure(self, manager):
        """Test that execution retries on failure."""
        call_count = 0

        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                error = Exception("Transient error")
                error.status_code = 500
                raise error
            return "success"

        result = manager.execute(flaky_operation)
        assert result == "success"
        assert call_count == 2

    def test_execute_exhausts_retries(self, manager):
        """Test that execution raises after exhausting retries."""

        def always_fail():
            error = Exception("Always fails")
            error.status_code = 500
            raise error

        with pytest.raises(RetryExhaustedError):
            manager.execute(always_fail)

    def test_execute_respects_circuit_breaker(self, manager):
        """Test that circuit breaker is respected."""

        def fail():
            error = Exception("Server error")
            error.status_code = 500
            raise error

        # Trip the circuit breaker
        for _ in range(3):
            with contextlib.suppress(Exception, RetryExhaustedError):
                manager.execute(fail)

        # Circuit should be open now
        with pytest.raises(CircuitOpenError):
            manager.execute(lambda: "test")

    def test_get_stats(self, manager):
        """Test getting combined statistics."""
        manager.execute(lambda: "success")
        stats = manager.get_stats()
        assert stats.total_requests >= 1

    def test_get_detailed_stats(self, manager):
        """Test getting detailed statistics."""
        manager.execute(lambda: "success")
        stats = manager.get_detailed_stats()
        assert "manager" in stats
        assert "rate_limiter" in stats
        assert "retry_policy" in stats
        assert "circuit_breaker" in stats

    def test_reset(self, manager):
        """Test reset clears all state."""
        manager.execute(lambda: "success")
        manager.reset()
        stats = manager.get_detailed_stats()
        assert stats["manager"]["total_executions"] == 0


class TestCreateResilienceManager:
    """Tests for create_resilience_manager factory."""

    def test_create_from_tracker_type(self):
        """Test creating manager from tracker type."""
        manager = create_resilience_manager(TrackerType.JIRA)
        assert manager is not None
        assert manager.get_rate_limiter().config.requests_per_second == 5.0

    def test_create_from_string(self):
        """Test creating manager from string name."""
        manager = create_resilience_manager("github")
        assert manager is not None
        assert manager.get_rate_limiter().config.requests_per_second == 10.0

    def test_create_with_custom_rate_limit(self):
        """Test creating with custom rate limit config."""
        config = RateLimitConfig(requests_per_second=50.0)
        manager = create_resilience_manager(TrackerType.JIRA, rate_limit_config=config)
        assert manager.get_rate_limiter().config.requests_per_second == 50.0

    def test_create_with_sliding_window(self):
        """Test creating with sliding window rate limiter."""
        manager = create_resilience_manager(
            TrackerType.JIRA,
            use_sliding_window=True,
        )
        assert isinstance(manager.get_rate_limiter(), SlidingWindowRateLimiter)

    def test_create_without_circuit_breaker(self):
        """Test creating without circuit breaker."""
        manager = create_resilience_manager(
            TrackerType.JIRA,
            enable_circuit_breaker=False,
        )
        assert manager.get_circuit_breaker() is None

    def test_create_unknown_tracker_uses_custom(self):
        """Test that unknown tracker name uses custom preset."""
        manager = create_resilience_manager("unknown_tracker")
        assert manager is not None


class TestThreadSafety:
    """Tests for thread safety of rate limiter."""

    def test_concurrent_acquire(self):
        """Test concurrent acquire calls."""
        limiter = TokenBucketRateLimiter(
            RateLimitConfig(
                requests_per_second=100.0,
                burst_size=50,
            )
        )
        results = []
        errors = []

        def acquire_token():
            try:
                result = limiter.acquire(timeout=1.0)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=acquire_token) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(results)

    def test_concurrent_circuit_breaker(self):
        """Test concurrent circuit breaker operations."""
        breaker = CircuitBreaker(
            CircuitBreakerConfig(
                failure_threshold=100,  # High to avoid tripping
            )
        )
        errors = []

        def record_operations():
            try:
                for _ in range(10):
                    breaker.allow_request()
                    breaker.record_success()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_operations) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert breaker.get_stats()["total_successes"] == 100
