"""
Circuit Breaker Implementation - Fault tolerance with circuit breaker pattern.

Implements the circuit breaker pattern:
- CLOSED: Normal operation, requests allowed
- OPEN: Failing fast, requests blocked
- HALF_OPEN: Testing if service recovered
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from spectra.core.ports.rate_limiting import (
    CircuitBreakerConfig,
    CircuitBreakerPort,
    CircuitOpenError,
    CircuitState,
)


class CircuitBreaker(CircuitBreakerPort):
    """
    Circuit breaker implementation for fault tolerance.

    Prevents cascading failures by "opening" the circuit when too many
    failures occur, blocking subsequent requests until a reset timeout
    allows testing if the service has recovered.

    State transitions:
    - CLOSED -> OPEN: When failure_threshold consecutive failures occur
    - OPEN -> HALF_OPEN: After reset_timeout seconds
    - HALF_OPEN -> CLOSED: After success_threshold successes
    - HALF_OPEN -> OPEN: On any failure

    Example:
        >>> config = CircuitBreakerConfig(
        ...     failure_threshold=5,
        ...     reset_timeout=30.0,
        ...     success_threshold=2,
        ... )
        >>> breaker = CircuitBreaker(config)
        >>>
        >>> if breaker.allow_request():
        ...     try:
        ...         result = make_request()
        ...         breaker.record_success()
        ...     except Exception:
        ...         breaker.record_failure()
        ...         raise
    """

    def __init__(
        self,
        config: CircuitBreakerConfig,
        logger_name: str | None = None,
    ):
        """
        Initialize the circuit breaker.

        Args:
            config: Circuit breaker configuration
            logger_name: Optional custom logger name
        """
        self._config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float | None = None
        self._opened_at: float | None = None
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._total_rejections = 0
        self._total_failures = 0
        self._total_successes = 0
        self._state_changes: list[tuple[datetime, CircuitState, CircuitState]] = []

        self._logger = logging.getLogger(logger_name or "CircuitBreaker")

    @property
    def config(self) -> CircuitBreakerConfig:
        """Get the circuit breaker configuration."""
        return self._config

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed.

        Returns:
            True if request allowed, False if circuit is open

        Raises:
            CircuitOpenError: If circuit is open and request rejected
        """
        with self._lock:
            self._total_requests += 1

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if reset timeout has passed
                if self._opened_at is not None:
                    elapsed = time.monotonic() - self._opened_at
                    if elapsed >= self._config.reset_timeout:
                        self._transition_to(CircuitState.HALF_OPEN)
                        return self._allow_half_open()

                # Still open, reject request
                self._total_rejections += 1
                reset_time = None
                if self._opened_at is not None:
                    remaining = self._config.reset_timeout - (time.monotonic() - self._opened_at)
                    if remaining > 0:
                        reset_time = datetime.now() + timedelta(seconds=remaining)

                raise CircuitOpenError(
                    f"Circuit breaker is open. Resets at {reset_time}",
                    reset_time=reset_time,
                )

            if self._state == CircuitState.HALF_OPEN:
                return self._allow_half_open()

            return True

    def _allow_half_open(self) -> bool:
        """Check if a request is allowed in half-open state. Must hold lock."""
        if self._half_open_calls >= self._config.half_open_max_calls:
            # Too many concurrent calls in half-open
            self._total_rejections += 1
            raise CircuitOpenError("Circuit breaker half-open: max concurrent calls reached")
        self._half_open_calls += 1
        return True

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)

                if self._success_count >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self, status_code: int | None = None) -> None:
        """
        Record a failed request.

        Args:
            status_code: HTTP status code to check if it counts as failure
        """
        with self._lock:
            # Check if this status code should count as a failure
            if status_code is not None:
                if status_code == 429 and not self._config.count_rate_limit_as_failure:
                    # Rate limit doesn't count as circuit breaker failure
                    self._logger.debug("Rate limit (429) not counted as circuit failure")
                    return

                if status_code not in self._config.failure_status_codes:
                    # Not a failure status code
                    return

            self._total_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens the circuit
                self._half_open_calls = max(0, self._half_open_calls - 1)
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1

                if self._failure_count >= self._config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            # Check for automatic transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._config.reset_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_requests": self._total_requests,
                "total_rejections": self._total_rejections,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "state_changes": [
                    {"time": t.isoformat(), "from": f.value, "to": to.value}
                    for t, f, to in self._state_changes[-10:]
                ],
                "last_failure_time": self._last_failure_time,
                "opened_at": self._opened_at,
                "time_until_reset": self._time_until_reset(),
            }

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED, force=True)
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
            self._opened_at = None

    def force_open(self) -> None:
        """Force the circuit to open state (for testing or manual override)."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)

    def force_close(self) -> None:
        """Force the circuit to closed state (for manual override)."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED, force=True)

    def _transition_to(self, new_state: CircuitState, force: bool = False) -> None:
        """
        Transition to a new state. Must be called with lock held.

        Args:
            new_state: The new state to transition to
            force: If True, allow any transition (for reset)
        """
        if self._state == new_state:
            return

        old_state = self._state
        self._state = new_state

        # Record state change
        self._state_changes.append((datetime.now(), old_state, new_state))
        if len(self._state_changes) > 100:
            self._state_changes = self._state_changes[-100:]

        # Handle state-specific initialization
        if new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._success_count = 0
            self._logger.warning(
                f"Circuit breaker OPENED after {self._failure_count} failures. "
                f"Will retry in {self._config.reset_timeout}s"
            )
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
            self._logger.info("Circuit breaker entering HALF_OPEN state")
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_calls = 0
            self._logger.info("Circuit breaker CLOSED")

    def _time_until_reset(self) -> float | None:
        """Calculate time until the circuit resets. Must hold lock."""
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return None
        elapsed = time.monotonic() - self._opened_at
        remaining = self._config.reset_timeout - elapsed
        return max(0, remaining)
