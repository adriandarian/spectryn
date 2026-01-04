"""
Rate Limiting Port - Centralized backoff strategy per adapter.

Provides a unified interface for rate limiting and retry strategies:
- RateLimiterPort: Abstract interface for rate limiters
- RetryPolicy: Configurable retry strategies (exponential, linear, constant)
- CircuitBreaker: Fault tolerance with circuit breaker pattern
- TrackerRateLimits: Preset rate limits per tracker type
- RateLimitContext: Request context for intelligent rate limiting

This port allows adapters to share consistent rate limiting behavior
while supporting tracker-specific configurations and strategies.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar


# Type variable for generic return types
T = TypeVar("T")


# =============================================================================
# Enums
# =============================================================================


class RetryStrategy(Enum):
    """Retry backoff strategy types."""

    EXPONENTIAL = "exponential"  # delay = initial * (factor ^ attempt)
    LINEAR = "linear"  # delay = initial + (increment * attempt)
    CONSTANT = "constant"  # delay = initial (fixed)
    FIBONACCI = "fibonacci"  # delay follows fibonacci sequence
    DECORRELATED_JITTER = "decorrelated_jitter"  # AWS-style decorrelated jitter


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class RateLimitScope(Enum):
    """Scope of rate limiting."""

    GLOBAL = "global"  # Across all operations
    PER_ENDPOINT = "per_endpoint"  # Per API endpoint
    PER_OPERATION = "per_operation"  # Per operation type (read/write)
    PER_RESOURCE = "per_resource"  # Per resource type (issue, epic, etc.)


class TrackerType(Enum):
    """Tracker types for preset configurations."""

    JIRA = "jira"
    GITHUB = "github"
    GITLAB = "gitlab"
    LINEAR = "linear"
    TRELLO = "trello"
    ASANA = "asana"
    MONDAY = "monday"
    CLICKUP = "clickup"
    SHORTCUT = "shortcut"
    YOUTRACK = "youtrack"
    BITBUCKET = "bitbucket"
    AZURE_DEVOPS = "azure_devops"
    PLANE = "plane"
    PIVOTAL = "pivotal"
    BASECAMP = "basecamp"
    CONFLUENCE = "confluence"
    GOOGLE_SHEETS = "google_sheets"
    CUSTOM = "custom"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    backoff_factor: float = 2.0  # for exponential
    linear_increment: float = 1.0  # for linear
    jitter: float = 0.1  # 10% jitter
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL

    # Retryable conditions
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (ConnectionError, TimeoutError)
    )

    # Timeout configuration
    timeout: float = 30.0  # request timeout
    connect_timeout: float = 10.0  # connection timeout

    def with_updates(self, **kwargs: Any) -> RetryConfig:
        """Create a new config with updated values."""
        from dataclasses import replace

        return replace(self, **kwargs)


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_second: float = 10.0
    burst_size: int = 20
    scope: RateLimitScope = RateLimitScope.GLOBAL

    # Time window for sliding window rate limiting
    window_seconds: float = 1.0

    # Adaptive rate limiting
    adaptive: bool = True  # Adjust rate based on responses
    min_rate: float = 0.5  # Minimum rate when adapting
    rate_reduction_factor: float = 0.5  # How much to reduce on 429

    # Headers to parse for rate limit info
    remaining_header: str = "X-RateLimit-Remaining"
    reset_header: str = "X-RateLimit-Reset"
    limit_header: str = "X-RateLimit-Limit"

    def with_updates(self, **kwargs: Any) -> RateLimitConfig:
        """Create a new config with updated values."""
        from dataclasses import replace

        return replace(self, **kwargs)


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open to close
    reset_timeout: float = 30.0  # Seconds before trying again (open -> half-open)
    half_open_max_calls: int = 3  # Max calls in half-open state

    # What counts as failure
    failure_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({500, 502, 503, 504})
    )
    count_rate_limit_as_failure: bool = False  # 429 doesn't trip circuit

    def with_updates(self, **kwargs: Any) -> CircuitBreakerConfig:
        """Create a new config with updated values."""
        from dataclasses import replace

        return replace(self, **kwargs)


@dataclass
class RateLimitContext:
    """Context for a rate-limited request."""

    endpoint: str = ""
    operation: str = ""  # read, write, delete
    resource_type: str = ""  # issue, epic, comment
    resource_id: str = ""
    priority: int = 0  # Higher = more important

    # Request metadata
    idempotency_key: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    # Response tracking (filled after request)
    status_code: int | None = None
    response_time_ms: float | None = None
    retry_after: int | None = None


@dataclass
class RetryAttempt:
    """Information about a retry attempt."""

    attempt: int
    delay: float
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RateLimitStats:
    """Statistics for rate limiting."""

    total_requests: int = 0
    total_wait_time: float = 0.0
    total_retries: int = 0
    rate_limited_count: int = 0
    circuit_breaker_rejections: int = 0
    current_rate: float = 0.0
    available_tokens: float = 0.0

    # Response time tracking
    avg_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0

    # Circuit breaker state
    circuit_state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    # Time window stats
    requests_in_window: int = 0
    window_start: datetime | None = None


@dataclass(frozen=True)
class TrackerRateLimits:
    """Preset rate limits for a tracker type."""

    tracker_type: TrackerType
    rate_limit: RateLimitConfig
    retry: RetryConfig
    circuit_breaker: CircuitBreakerConfig | None = None
    description: str = ""


# =============================================================================
# Exceptions
# =============================================================================


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        context: RateLimitContext | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.context = context


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(
        self,
        message: str,
        reset_time: datetime | None = None,
    ):
        super().__init__(message)
        self.reset_time = reset_time


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(
        self,
        message: str,
        attempts: list[RetryAttempt] | None = None,
        last_exception: Exception | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts or []
        self.last_exception = last_exception


# =============================================================================
# Port Interfaces
# =============================================================================


class RateLimiterPort(ABC):
    """
    Abstract interface for rate limiters.

    Implementations handle:
    - Token bucket or sliding window rate limiting
    - Adaptive rate adjustment based on responses
    - Per-endpoint or global rate limits
    """

    @abstractmethod
    def acquire(
        self,
        context: RateLimitContext | None = None,
        timeout: float | None = None,
    ) -> bool:
        """
        Acquire permission to make a request.

        Blocks until a token is available or timeout is reached.

        Args:
            context: Optional context for scoped rate limiting
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if acquired, False if timeout reached
        """
        ...

    @abstractmethod
    def try_acquire(self, context: RateLimitContext | None = None) -> bool:
        """
        Try to acquire without waiting.

        Args:
            context: Optional context for scoped rate limiting

        Returns:
            True if acquired, False if not available
        """
        ...

    @abstractmethod
    def update_from_response(
        self,
        status_code: int,
        headers: dict[str, str],
        context: RateLimitContext | None = None,
    ) -> None:
        """
        Update rate limiter based on API response.

        Args:
            status_code: HTTP status code
            headers: Response headers
            context: Request context
        """
        ...

    @abstractmethod
    def get_stats(self) -> RateLimitStats:
        """Get rate limiter statistics."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset rate limiter to initial state."""
        ...

    @property
    @abstractmethod
    def config(self) -> RateLimitConfig:
        """Get the rate limit configuration."""
        ...


class RetryPolicyPort(ABC):
    """
    Abstract interface for retry policies.

    Implementations handle:
    - Calculating retry delays
    - Determining if retry is appropriate
    - Tracking retry attempts
    """

    @abstractmethod
    def should_retry(
        self,
        status_code: int | None = None,
        exception: Exception | None = None,
        attempt: int = 0,
    ) -> bool:
        """
        Determine if a request should be retried.

        Args:
            status_code: HTTP status code (if available)
            exception: Exception that occurred (if any)
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry, False otherwise
        """
        ...

    @abstractmethod
    def get_delay(
        self,
        attempt: int,
        retry_after: int | None = None,
    ) -> float:
        """
        Calculate delay before next retry.

        Args:
            attempt: Current attempt number (0-indexed)
            retry_after: Retry-After header value (if present)

        Returns:
            Delay in seconds
        """
        ...

    @abstractmethod
    def record_attempt(self, attempt: RetryAttempt) -> None:
        """Record a retry attempt for statistics."""
        ...

    @abstractmethod
    def get_attempts(self) -> list[RetryAttempt]:
        """Get all recorded retry attempts."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset retry state for new request."""
        ...

    @property
    @abstractmethod
    def config(self) -> RetryConfig:
        """Get the retry configuration."""
        ...


class CircuitBreakerPort(ABC):
    """
    Abstract interface for circuit breakers.

    Implements the circuit breaker pattern for fault tolerance:
    - CLOSED: Normal operation
    - OPEN: Failing fast, rejecting requests
    - HALF_OPEN: Testing if service recovered
    """

    @abstractmethod
    def allow_request(self) -> bool:
        """
        Check if a request should be allowed.

        Returns:
            True if request allowed, False if circuit is open

        Raises:
            CircuitOpenError: If circuit is open and request rejected
        """
        ...

    @abstractmethod
    def record_success(self) -> None:
        """Record a successful request."""
        ...

    @abstractmethod
    def record_failure(self, status_code: int | None = None) -> None:
        """
        Record a failed request.

        Args:
            status_code: HTTP status code (to check if it counts as failure)
        """
        ...

    @abstractmethod
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        ...

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        ...

    @property
    @abstractmethod
    def config(self) -> CircuitBreakerConfig:
        """Get the circuit breaker configuration."""
        ...


class ResiliencePort(ABC):
    """
    Unified interface combining rate limiting, retry, and circuit breaker.

    This is the main interface adapters should use for resilient HTTP requests.
    """

    @abstractmethod
    def execute(
        self,
        operation: Callable[[], T],
        context: RateLimitContext | None = None,
    ) -> T:
        """
        Execute an operation with full resilience (rate limit + retry + circuit breaker).

        Args:
            operation: Callable that performs the actual request
            context: Request context

        Returns:
            Result from the operation

        Raises:
            RateLimitError: If rate limit timeout exceeded
            CircuitOpenError: If circuit breaker is open
            RetryExhaustedError: If all retries exhausted
        """
        ...

    @abstractmethod
    def get_rate_limiter(self) -> RateLimiterPort:
        """Get the underlying rate limiter."""
        ...

    @abstractmethod
    def get_retry_policy(self) -> RetryPolicyPort:
        """Get the underlying retry policy."""
        ...

    @abstractmethod
    def get_circuit_breaker(self) -> CircuitBreakerPort | None:
        """Get the circuit breaker (if configured)."""
        ...

    @abstractmethod
    def get_stats(self) -> RateLimitStats:
        """Get combined statistics."""
        ...


# =============================================================================
# Preset Configurations
# =============================================================================


# Default tracker presets
TRACKER_PRESETS: dict[TrackerType, TrackerRateLimits] = {
    TrackerType.JIRA: TrackerRateLimits(
        tracker_type=TrackerType.JIRA,
        rate_limit=RateLimitConfig(
            requests_per_second=5.0,  # ~300/min, Jira allows ~100/min
            burst_size=10,
            remaining_header="X-RateLimit-Remaining",
            reset_header="X-RateLimit-Reset",
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=60.0,
            backoff_factor=2.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=30.0,
        ),
        description="Jira Cloud API - 100 req/min typical limit",
    ),
    TrackerType.GITHUB: TrackerRateLimits(
        tracker_type=TrackerType.GITHUB,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # 5000/hour = ~1.4/sec, we use 10 with burst
            burst_size=20,
            remaining_header="X-RateLimit-Remaining",
            reset_header="X-RateLimit-Reset",
            limit_header="X-RateLimit-Limit",
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=120.0,  # GitHub can have long waits
            backoff_factor=2.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=5,
            reset_timeout=60.0,
        ),
        description="GitHub API - 5000 req/hour authenticated",
    ),
    TrackerType.GITLAB: TrackerRateLimits(
        tracker_type=TrackerType.GITLAB,
        rate_limit=RateLimitConfig(
            requests_per_second=5.0,  # ~300/min, GitLab varies by tier
            burst_size=10,
            remaining_header="RateLimit-Remaining",
            reset_header="RateLimit-Reset",
            limit_header="RateLimit-Limit",
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=60.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="GitLab API - varies by tier",
    ),
    TrackerType.LINEAR: TrackerRateLimits(
        tracker_type=TrackerType.LINEAR,
        rate_limit=RateLimitConfig(
            requests_per_second=1.0,  # 1500/hour = ~0.4/sec
            burst_size=10,
            remaining_header="X-RateLimit-Requests-Remaining",
            reset_header="X-RateLimit-Requests-Reset",
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=2.0,  # Linear is slower
            max_delay=60.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Linear GraphQL API - 1500 req/hour",
    ),
    TrackerType.TRELLO: TrackerRateLimits(
        tracker_type=TrackerType.TRELLO,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # 100 req/10sec = 10/sec
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Trello API - 100 req/10sec, 300 req/10sec token",
    ),
    TrackerType.ASANA: TrackerRateLimits(
        tracker_type=TrackerType.ASANA,
        rate_limit=RateLimitConfig(
            requests_per_second=25.0,  # 1500/min = 25/sec
            burst_size=50,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=0.5,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Asana API - 1500 req/min",
    ),
    TrackerType.MONDAY: TrackerRateLimits(
        tracker_type=TrackerType.MONDAY,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # Based on complexity budget
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Monday.com API - complexity-based limits",
    ),
    TrackerType.CLICKUP: TrackerRateLimits(
        tracker_type=TrackerType.CLICKUP,
        rate_limit=RateLimitConfig(
            requests_per_second=1.67,  # 100 req/min = 1.67/sec
            burst_size=10,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="ClickUp API - 100 req/min",
    ),
    TrackerType.SHORTCUT: TrackerRateLimits(
        tracker_type=TrackerType.SHORTCUT,
        rate_limit=RateLimitConfig(
            requests_per_second=3.33,  # 200 req/min = 3.33/sec
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Shortcut API - 200 req/min",
    ),
    TrackerType.YOUTRACK: TrackerRateLimits(
        tracker_type=TrackerType.YOUTRACK,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # Conservative default
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="YouTrack API - varies by deployment",
    ),
    TrackerType.BITBUCKET: TrackerRateLimits(
        tracker_type=TrackerType.BITBUCKET,
        rate_limit=RateLimitConfig(
            requests_per_second=16.67,  # 1000 req/hour = 0.28/sec, but we use burst
            burst_size=30,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Bitbucket API - 1000 req/hour",
    ),
    TrackerType.AZURE_DEVOPS: TrackerRateLimits(
        tracker_type=TrackerType.AZURE_DEVOPS,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # Varies by organization
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Azure DevOps API - varies by organization",
    ),
    TrackerType.PLANE: TrackerRateLimits(
        tracker_type=TrackerType.PLANE,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # Conservative default
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Plane API",
    ),
    TrackerType.PIVOTAL: TrackerRateLimits(
        tracker_type=TrackerType.PIVOTAL,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,  # Conservative default
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Pivotal Tracker API",
    ),
    TrackerType.BASECAMP: TrackerRateLimits(
        tracker_type=TrackerType.BASECAMP,
        rate_limit=RateLimitConfig(
            requests_per_second=8.33,  # 500 req/min = 8.33/sec
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Basecamp API - 500 req/10sec",
    ),
    TrackerType.CONFLUENCE: TrackerRateLimits(
        tracker_type=TrackerType.CONFLUENCE,
        rate_limit=RateLimitConfig(
            requests_per_second=5.0,  # Similar to Jira
            burst_size=10,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Confluence API",
    ),
    TrackerType.GOOGLE_SHEETS: TrackerRateLimits(
        tracker_type=TrackerType.GOOGLE_SHEETS,
        rate_limit=RateLimitConfig(
            requests_per_second=1.67,  # 100 req/min per user
            burst_size=10,
        ),
        retry=RetryConfig(
            max_retries=5,  # Google can be flaky
            initial_delay=1.0,
            max_delay=120.0,
            strategy=RetryStrategy.DECORRELATED_JITTER,
        ),
        description="Google Sheets API - 100 req/min per user",
    ),
    TrackerType.CUSTOM: TrackerRateLimits(
        tracker_type=TrackerType.CUSTOM,
        rate_limit=RateLimitConfig(
            requests_per_second=10.0,
            burst_size=20,
        ),
        retry=RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            strategy=RetryStrategy.EXPONENTIAL,
        ),
        description="Custom tracker with default limits",
    ),
}


def get_tracker_preset(tracker_type: TrackerType) -> TrackerRateLimits:
    """
    Get preset rate limit configuration for a tracker type.

    Args:
        tracker_type: The tracker type

    Returns:
        TrackerRateLimits with preset configuration
    """
    return TRACKER_PRESETS.get(tracker_type, TRACKER_PRESETS[TrackerType.CUSTOM])


def get_preset_for_name(name: str) -> TrackerRateLimits:
    """
    Get preset by tracker name string.

    Args:
        name: Tracker name (case-insensitive)

    Returns:
        TrackerRateLimits for the tracker
    """
    try:
        tracker_type = TrackerType(name.lower())
    except ValueError:
        tracker_type = TrackerType.CUSTOM
    return get_tracker_preset(tracker_type)


# =============================================================================
# Utility Functions
# =============================================================================


def calculate_backoff_delay(
    attempt: int,
    config: RetryConfig,
    retry_after: int | None = None,
) -> float:
    """
    Calculate delay before next retry based on strategy.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        retry_after: Optional Retry-After header value

    Returns:
        Delay in seconds
    """
    # Respect Retry-After header if provided (no jitter, server specified exact time)
    if retry_after is not None:
        return min(float(retry_after), config.max_delay)

    # Calculate based on strategy
    if config.strategy == RetryStrategy.EXPONENTIAL:
        base_delay = config.initial_delay * (config.backoff_factor**attempt)
    elif config.strategy == RetryStrategy.LINEAR:
        base_delay = config.initial_delay + (config.linear_increment * attempt)
    elif config.strategy == RetryStrategy.CONSTANT:
        base_delay = config.initial_delay
    elif config.strategy == RetryStrategy.FIBONACCI:
        base_delay = config.initial_delay * _fibonacci(attempt + 1)
    elif config.strategy == RetryStrategy.DECORRELATED_JITTER:
        # AWS-style: delay = random(initial, prev_delay * 3)
        # For first attempt, use initial_delay
        if attempt == 0:
            base_delay = config.initial_delay
        else:
            prev_delay = config.initial_delay * (config.backoff_factor ** (attempt - 1))
            base_delay = random.uniform(config.initial_delay, prev_delay * 3)
    else:
        base_delay = config.initial_delay

    base_delay = min(base_delay, config.max_delay)

    # Add jitter (except for decorrelated_jitter which has built-in randomness)
    if config.strategy != RetryStrategy.DECORRELATED_JITTER:
        jitter_range = base_delay * config.jitter
        jitter_value = random.uniform(-jitter_range, jitter_range)
        base_delay = base_delay + jitter_value

    return max(0.0, base_delay)


def _fibonacci(n: int) -> int:
    """Calculate nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def parse_retry_after(headers: dict[str, str]) -> int | None:
    """
    Parse Retry-After header from response headers.

    Args:
        headers: Response headers dict

    Returns:
        Retry delay in seconds, or None if not present
    """
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after is not None:
        try:
            return int(retry_after)
        except ValueError:
            # Could be HTTP-date format, ignore for simplicity
            return None
    return None


def is_retryable_status_code(
    status_code: int,
    config: RetryConfig | None = None,
) -> bool:
    """
    Check if a status code should trigger a retry.

    Args:
        status_code: HTTP status code
        config: Optional retry config (uses default if None)

    Returns:
        True if retryable
    """
    retryable = config.retryable_status_codes if config else frozenset({429, 500, 502, 503, 504})
    return status_code in retryable


def is_retryable_exception(
    exception: Exception,
    config: RetryConfig | None = None,
) -> bool:
    """
    Check if an exception should trigger a retry.

    Args:
        exception: The exception
        config: Optional retry config

    Returns:
        True if retryable
    """
    retryable = config.retryable_exceptions if config else (ConnectionError, TimeoutError)
    return isinstance(exception, retryable)


# =============================================================================
# Public API
# =============================================================================


__all__ = [
    "TRACKER_PRESETS",
    "CircuitBreakerConfig",
    "CircuitBreakerPort",
    "CircuitOpenError",
    "CircuitState",
    "RateLimitConfig",
    "RateLimitContext",
    "RateLimitError",
    "RateLimitScope",
    "RateLimitStats",
    "RateLimiterPort",
    "ResiliencePort",
    "RetryAttempt",
    "RetryConfig",
    "RetryExhaustedError",
    "RetryPolicyPort",
    "RetryStrategy",
    "TrackerRateLimits",
    "TrackerType",
    "calculate_backoff_delay",
    "get_preset_for_name",
    "get_tracker_preset",
    "is_retryable_exception",
    "is_retryable_status_code",
    "parse_retry_after",
]
