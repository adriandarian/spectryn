"""
Tests for rate limiting port interfaces.

Tests the data classes, enums, and utility functions in the rate_limiting port.
"""

import pytest

from spectryn.core.ports.rate_limiting import (
    TRACKER_PRESETS,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    RateLimitConfig,
    RateLimitContext,
    RateLimitError,
    RateLimitScope,
    RateLimitStats,
    RetryAttempt,
    RetryConfig,
    RetryExhaustedError,
    RetryStrategy,
    TrackerRateLimits,
    TrackerType,
    calculate_backoff_delay,
    get_preset_for_name,
    get_tracker_preset,
    is_retryable_exception,
    is_retryable_status_code,
    parse_retry_after,
)


class TestRetryStrategy:
    """Tests for RetryStrategy enum."""

    def test_exponential_strategy(self):
        """Test exponential strategy value."""
        assert RetryStrategy.EXPONENTIAL.value == "exponential"

    def test_linear_strategy(self):
        """Test linear strategy value."""
        assert RetryStrategy.LINEAR.value == "linear"

    def test_constant_strategy(self):
        """Test constant strategy value."""
        assert RetryStrategy.CONSTANT.value == "constant"

    def test_fibonacci_strategy(self):
        """Test fibonacci strategy value."""
        assert RetryStrategy.FIBONACCI.value == "fibonacci"

    def test_decorrelated_jitter_strategy(self):
        """Test decorrelated jitter strategy value."""
        assert RetryStrategy.DECORRELATED_JITTER.value == "decorrelated_jitter"


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_closed_state(self):
        """Test closed state value."""
        assert CircuitState.CLOSED.value == "closed"

    def test_open_state(self):
        """Test open state value."""
        assert CircuitState.OPEN.value == "open"

    def test_half_open_state(self):
        """Test half-open state value."""
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestRateLimitScope:
    """Tests for RateLimitScope enum."""

    def test_global_scope(self):
        """Test global scope value."""
        assert RateLimitScope.GLOBAL.value == "global"

    def test_per_endpoint_scope(self):
        """Test per-endpoint scope value."""
        assert RateLimitScope.PER_ENDPOINT.value == "per_endpoint"


class TestTrackerType:
    """Tests for TrackerType enum."""

    def test_jira_type(self):
        """Test Jira tracker type."""
        assert TrackerType.JIRA.value == "jira"

    def test_github_type(self):
        """Test GitHub tracker type."""
        assert TrackerType.GITHUB.value == "github"

    def test_all_tracker_types_have_presets(self):
        """Test that all tracker types have presets."""
        for tracker_type in TrackerType:
            preset = get_tracker_preset(tracker_type)
            assert preset is not None
            assert preset.tracker_type == tracker_type


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0
        assert config.jitter == 0.1
        assert config.strategy == RetryStrategy.EXPONENTIAL

    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=0.5,
            strategy=RetryStrategy.LINEAR,
        )
        assert config.max_retries == 5
        assert config.initial_delay == 0.5
        assert config.strategy == RetryStrategy.LINEAR

    def test_retryable_status_codes(self):
        """Test default retryable status codes."""
        config = RetryConfig()
        assert 429 in config.retryable_status_codes
        assert 500 in config.retryable_status_codes
        assert 502 in config.retryable_status_codes
        assert 503 in config.retryable_status_codes
        assert 504 in config.retryable_status_codes
        assert 200 not in config.retryable_status_codes

    def test_with_updates(self):
        """Test creating new config with updates."""
        config = RetryConfig(max_retries=3)
        new_config = config.with_updates(max_retries=5, initial_delay=2.0)
        assert new_config.max_retries == 5
        assert new_config.initial_delay == 2.0
        # Original unchanged
        assert config.max_retries == 3


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_config(self):
        """Test default rate limit configuration."""
        config = RateLimitConfig()
        assert config.requests_per_second == 10.0
        assert config.burst_size == 20
        assert config.scope == RateLimitScope.GLOBAL
        assert config.adaptive is True

    def test_custom_config(self):
        """Test custom rate limit configuration."""
        config = RateLimitConfig(
            requests_per_second=5.0,
            burst_size=10,
            adaptive=False,
        )
        assert config.requests_per_second == 5.0
        assert config.burst_size == 10
        assert config.adaptive is False

    def test_with_updates(self):
        """Test creating new config with updates."""
        config = RateLimitConfig(requests_per_second=10.0)
        new_config = config.with_updates(requests_per_second=5.0)
        assert new_config.requests_per_second == 5.0
        assert config.requests_per_second == 10.0


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig dataclass."""

    def test_default_config(self):
        """Test default circuit breaker configuration."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.reset_timeout == 30.0
        assert config.half_open_max_calls == 3

    def test_failure_status_codes(self):
        """Test default failure status codes."""
        config = CircuitBreakerConfig()
        assert 500 in config.failure_status_codes
        assert 502 in config.failure_status_codes
        assert 429 not in config.failure_status_codes  # Rate limit not a failure

    def test_with_updates(self):
        """Test creating new config with updates."""
        config = CircuitBreakerConfig(failure_threshold=5)
        new_config = config.with_updates(failure_threshold=10)
        assert new_config.failure_threshold == 10
        assert config.failure_threshold == 5


class TestRateLimitContext:
    """Tests for RateLimitContext dataclass."""

    def test_default_context(self):
        """Test default context."""
        context = RateLimitContext()
        assert context.endpoint == ""
        assert context.operation == ""
        assert context.status_code is None

    def test_custom_context(self):
        """Test custom context."""
        context = RateLimitContext(
            endpoint="/api/issues",
            operation="read",
            resource_type="issue",
        )
        assert context.endpoint == "/api/issues"
        assert context.operation == "read"
        assert context.resource_type == "issue"


class TestRateLimitStats:
    """Tests for RateLimitStats dataclass."""

    def test_default_stats(self):
        """Test default stats."""
        stats = RateLimitStats()
        assert stats.total_requests == 0
        assert stats.total_wait_time == 0.0
        assert stats.circuit_state == CircuitState.CLOSED


class TestRetryAttempt:
    """Tests for RetryAttempt dataclass."""

    def test_create_attempt(self):
        """Test creating a retry attempt."""
        attempt = RetryAttempt(
            attempt=0,
            delay=1.5,
            reason="Connection error",
        )
        assert attempt.attempt == 0
        assert attempt.delay == 1.5
        assert attempt.reason == "Connection error"
        assert attempt.timestamp is not None


class TestTrackerRateLimits:
    """Tests for TrackerRateLimits dataclass."""

    def test_create_preset(self):
        """Test creating a tracker preset."""
        preset = TrackerRateLimits(
            tracker_type=TrackerType.JIRA,
            rate_limit=RateLimitConfig(requests_per_second=5.0),
            retry=RetryConfig(max_retries=3),
            description="Test preset",
        )
        assert preset.tracker_type == TrackerType.JIRA
        assert preset.rate_limit.requests_per_second == 5.0
        assert preset.retry.max_retries == 3


class TestExceptions:
    """Tests for exception classes."""

    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert "Rate limit exceeded" in str(error)
        assert error.retry_after == 60

    def test_circuit_open_error(self):
        """Test CircuitOpenError exception."""
        error = CircuitOpenError("Circuit is open")
        assert "Circuit is open" in str(error)

    def test_retry_exhausted_error(self):
        """Test RetryExhaustedError exception."""
        attempts = [RetryAttempt(attempt=0, delay=1.0, reason="Error")]
        error = RetryExhaustedError("All retries failed", attempts=attempts)
        assert "All retries failed" in str(error)
        assert len(error.attempts) == 1


class TestCalculateBackoffDelay:
    """Tests for calculate_backoff_delay function."""

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            initial_delay=1.0,
            backoff_factor=2.0,
            jitter=0.0,  # Disable jitter for predictable tests
            strategy=RetryStrategy.EXPONENTIAL,
        )
        # Attempt 0: 1.0 * 2^0 = 1.0
        delay = calculate_backoff_delay(0, config)
        assert delay == pytest.approx(1.0, abs=0.01)
        # Attempt 1: 1.0 * 2^1 = 2.0
        delay = calculate_backoff_delay(1, config)
        assert delay == pytest.approx(2.0, abs=0.01)
        # Attempt 2: 1.0 * 2^2 = 4.0
        delay = calculate_backoff_delay(2, config)
        assert delay == pytest.approx(4.0, abs=0.01)

    def test_linear_backoff(self):
        """Test linear backoff calculation."""
        config = RetryConfig(
            initial_delay=1.0,
            linear_increment=1.0,
            jitter=0.0,
            strategy=RetryStrategy.LINEAR,
        )
        # Attempt 0: 1.0 + 0 = 1.0
        delay = calculate_backoff_delay(0, config)
        assert delay == pytest.approx(1.0, abs=0.01)
        # Attempt 1: 1.0 + 1 = 2.0
        delay = calculate_backoff_delay(1, config)
        assert delay == pytest.approx(2.0, abs=0.01)

    def test_constant_backoff(self):
        """Test constant backoff calculation."""
        config = RetryConfig(
            initial_delay=2.0,
            jitter=0.0,
            strategy=RetryStrategy.CONSTANT,
        )
        delay = calculate_backoff_delay(0, config)
        assert delay == pytest.approx(2.0, abs=0.01)
        delay = calculate_backoff_delay(5, config)
        assert delay == pytest.approx(2.0, abs=0.01)

    def test_max_delay_cap(self):
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=10.0,
            backoff_factor=10.0,
            jitter=0.0,
            strategy=RetryStrategy.EXPONENTIAL,
        )
        # Attempt 3: 1.0 * 10^3 = 1000, but capped at 10
        delay = calculate_backoff_delay(3, config)
        assert delay == pytest.approx(10.0, abs=0.01)

    def test_retry_after_header(self):
        """Test that Retry-After header is respected."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=60.0,
            jitter=0.0,
        )
        delay = calculate_backoff_delay(0, config, retry_after=30)
        assert delay == pytest.approx(30.0, abs=0.01)

    def test_retry_after_capped(self):
        """Test that Retry-After is capped at max_delay."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=10.0,
            jitter=0.0,
        )
        delay = calculate_backoff_delay(0, config, retry_after=60)
        assert delay == pytest.approx(10.0, abs=0.01)

    def test_jitter_adds_variance(self):
        """Test that jitter adds variance to delay."""
        config = RetryConfig(
            initial_delay=10.0,
            jitter=0.1,  # 10% jitter
            strategy=RetryStrategy.CONSTANT,
        )
        delays = [calculate_backoff_delay(0, config) for _ in range(100)]
        # All delays should be within 10% of 10.0
        assert all(9.0 <= d <= 11.0 for d in delays)
        # There should be some variance
        assert len(set(delays)) > 1


class TestParseRetryAfter:
    """Tests for parse_retry_after function."""

    def test_parse_integer(self):
        """Test parsing integer Retry-After."""
        headers = {"Retry-After": "60"}
        assert parse_retry_after(headers) == 60

    def test_parse_missing_header(self):
        """Test parsing when header is missing."""
        headers = {}
        assert parse_retry_after(headers) is None

    def test_parse_invalid_value(self):
        """Test parsing invalid value."""
        headers = {"Retry-After": "invalid"}
        assert parse_retry_after(headers) is None

    def test_parse_lowercase_header(self):
        """Test parsing lowercase header name."""
        headers = {"retry-after": "30"}
        assert parse_retry_after(headers) == 30


class TestIsRetryableStatusCode:
    """Tests for is_retryable_status_code function."""

    def test_429_is_retryable(self):
        """Test that 429 is retryable."""
        assert is_retryable_status_code(429) is True

    def test_500_is_retryable(self):
        """Test that 500 is retryable."""
        assert is_retryable_status_code(500) is True

    def test_502_is_retryable(self):
        """Test that 502 is retryable."""
        assert is_retryable_status_code(502) is True

    def test_200_not_retryable(self):
        """Test that 200 is not retryable."""
        assert is_retryable_status_code(200) is False

    def test_404_not_retryable(self):
        """Test that 404 is not retryable."""
        assert is_retryable_status_code(404) is False

    def test_custom_config(self):
        """Test with custom retryable codes."""
        config = RetryConfig(retryable_status_codes=frozenset({418}))
        assert is_retryable_status_code(418, config) is True
        assert is_retryable_status_code(429, config) is False


class TestIsRetryableException:
    """Tests for is_retryable_exception function."""

    def test_connection_error_retryable(self):
        """Test that ConnectionError is retryable."""
        assert is_retryable_exception(ConnectionError()) is True

    def test_timeout_error_retryable(self):
        """Test that TimeoutError is retryable."""
        assert is_retryable_exception(TimeoutError()) is True

    def test_value_error_not_retryable(self):
        """Test that ValueError is not retryable."""
        assert is_retryable_exception(ValueError()) is False


class TestGetTrackerPreset:
    """Tests for get_tracker_preset function."""

    def test_get_jira_preset(self):
        """Test getting Jira preset."""
        preset = get_tracker_preset(TrackerType.JIRA)
        assert preset.tracker_type == TrackerType.JIRA
        assert preset.rate_limit.requests_per_second == 5.0

    def test_get_github_preset(self):
        """Test getting GitHub preset."""
        preset = get_tracker_preset(TrackerType.GITHUB)
        assert preset.tracker_type == TrackerType.GITHUB
        assert preset.rate_limit.requests_per_second == 10.0

    def test_get_linear_preset(self):
        """Test getting Linear preset."""
        preset = get_tracker_preset(TrackerType.LINEAR)
        assert preset.tracker_type == TrackerType.LINEAR
        assert preset.rate_limit.requests_per_second == 1.0

    def test_get_custom_returns_default(self):
        """Test that custom type returns default preset."""
        preset = get_tracker_preset(TrackerType.CUSTOM)
        assert preset.tracker_type == TrackerType.CUSTOM


class TestGetPresetForName:
    """Tests for get_preset_for_name function."""

    def test_get_by_lowercase_name(self):
        """Test getting preset by lowercase name."""
        preset = get_preset_for_name("jira")
        assert preset.tracker_type == TrackerType.JIRA

    def test_get_by_uppercase_name(self):
        """Test getting preset by uppercase name."""
        preset = get_preset_for_name("GITHUB")
        assert preset.tracker_type == TrackerType.GITHUB

    def test_unknown_name_returns_custom(self):
        """Test that unknown name returns custom preset."""
        preset = get_preset_for_name("unknown_tracker")
        assert preset.tracker_type == TrackerType.CUSTOM


class TestTrackerPresets:
    """Tests for TRACKER_PRESETS constant."""

    def test_all_trackers_have_presets(self):
        """Test that all tracker types have presets defined."""
        for tracker_type in TrackerType:
            assert tracker_type in TRACKER_PRESETS

    def test_preset_has_rate_limit(self):
        """Test that all presets have rate limit config."""
        for preset in TRACKER_PRESETS.values():
            assert preset.rate_limit is not None
            assert preset.rate_limit.requests_per_second > 0

    def test_preset_has_retry(self):
        """Test that all presets have retry config."""
        for preset in TRACKER_PRESETS.values():
            assert preset.retry is not None
            assert preset.retry.max_retries >= 0

    def test_jira_preset_values(self):
        """Test specific Jira preset values."""
        preset = TRACKER_PRESETS[TrackerType.JIRA]
        assert preset.rate_limit.requests_per_second == 5.0
        assert preset.retry.max_retries == 3
        assert preset.circuit_breaker is not None
        assert preset.circuit_breaker.failure_threshold == 5

    def test_github_preset_values(self):
        """Test specific GitHub preset values."""
        preset = TRACKER_PRESETS[TrackerType.GITHUB]
        assert preset.rate_limit.requests_per_second == 10.0
        assert preset.retry.max_delay == 120.0  # GitHub has longer waits
