"""
Retry Policy Implementation - Configurable retry with multiple strategies.

Provides a concrete implementation of RetryPolicyPort with support for:
- Exponential backoff
- Linear backoff
- Constant delay
- Fibonacci sequence
- AWS-style decorrelated jitter
"""

from __future__ import annotations

import logging

from spectra.core.ports.rate_limiting import (
    RetryAttempt,
    RetryConfig,
    RetryPolicyPort,
    calculate_backoff_delay,
)


class RetryPolicy(RetryPolicyPort):
    """
    Configurable retry policy implementation.

    Supports multiple backoff strategies and tracks retry attempts
    for debugging and statistics.

    Example:
        >>> config = RetryConfig(
        ...     max_retries=3,
        ...     initial_delay=1.0,
        ...     strategy=RetryStrategy.EXPONENTIAL,
        ... )
        >>> policy = RetryPolicy(config)
        >>>
        >>> for attempt in range(config.max_retries + 1):
        ...     try:
        ...         result = make_request()
        ...         break
        ...     except Exception as e:
        ...         if not policy.should_retry(exception=e, attempt=attempt):
        ...             raise
        ...         delay = policy.get_delay(attempt)
        ...         policy.record_attempt(RetryAttempt(
        ...             attempt=attempt,
        ...             delay=delay,
        ...             reason=str(e),
        ...         ))
        ...         time.sleep(delay)
    """

    def __init__(
        self,
        config: RetryConfig,
        logger_name: str | None = None,
    ):
        """
        Initialize the retry policy.

        Args:
            config: Retry configuration
            logger_name: Optional custom logger name
        """
        self._config = config
        self._attempts: list[RetryAttempt] = []
        self._prev_delay: float = config.initial_delay  # For decorrelated jitter
        self._logger = logging.getLogger(logger_name or "RetryPolicy")

    @property
    def config(self) -> RetryConfig:
        """Get the retry configuration."""
        return self._config

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
        # Check if max retries exceeded
        if attempt >= self._config.max_retries:
            self._logger.debug(
                f"Max retries ({self._config.max_retries}) exceeded at attempt {attempt}"
            )
            return False

        # Check status code
        if status_code is not None:
            if status_code in self._config.retryable_status_codes:
                self._logger.debug(f"Status code {status_code} is retryable, will retry")
                return True
            # Non-retryable status code
            return False

        # Check exception
        if exception is not None:
            if isinstance(exception, self._config.retryable_exceptions):
                self._logger.debug(f"Exception {type(exception).__name__} is retryable, will retry")
                return True
            # Non-retryable exception
            return False

        # No status code or exception provided, don't retry
        return False

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
        delay = calculate_backoff_delay(
            attempt=attempt,
            config=self._config,
            retry_after=retry_after,
        )

        # Store for decorrelated jitter
        self._prev_delay = delay

        self._logger.debug(
            f"Retry delay for attempt {attempt}: {delay:.2f}s "
            f"(strategy={self._config.strategy.value})"
        )

        return delay

    def record_attempt(self, attempt: RetryAttempt) -> None:
        """Record a retry attempt for statistics."""
        self._attempts.append(attempt)
        self._logger.info(
            f"Retry attempt {attempt.attempt}: delay={attempt.delay:.2f}s, reason={attempt.reason}"
        )

    def get_attempts(self) -> list[RetryAttempt]:
        """Get all recorded retry attempts."""
        return self._attempts.copy()

    def reset(self) -> None:
        """Reset retry state for new request."""
        self._attempts = []
        self._prev_delay = self._config.initial_delay

    def get_total_retry_time(self) -> float:
        """Calculate total time spent in retries."""
        return sum(a.delay for a in self._attempts)

    def get_retry_count(self) -> int:
        """Get number of retry attempts made."""
        return len(self._attempts)


class AdaptiveRetryPolicy(RetryPolicy):
    """
    Adaptive retry policy that adjusts based on success/failure patterns.

    Extends RetryPolicy with:
    - Success rate tracking
    - Dynamic backoff adjustment based on recent failures
    - Cooldown period after multiple failures
    """

    def __init__(
        self,
        config: RetryConfig,
        success_window: int = 100,
        min_success_rate: float = 0.5,
        cooldown_multiplier: float = 2.0,
        logger_name: str | None = None,
    ):
        """
        Initialize the adaptive retry policy.

        Args:
            config: Retry configuration
            success_window: Number of recent requests to track
            min_success_rate: Minimum success rate before increasing backoff
            cooldown_multiplier: Multiplier for backoff when success rate is low
            logger_name: Optional custom logger name
        """
        super().__init__(config, logger_name)
        self._success_window = success_window
        self._min_success_rate = min_success_rate
        self._cooldown_multiplier = cooldown_multiplier
        self._results: list[bool] = []  # True = success, False = failure

    def record_success(self) -> None:
        """Record a successful request."""
        self._results.append(True)
        if len(self._results) > self._success_window:
            self._results = self._results[-self._success_window :]

    def record_failure(self) -> None:
        """Record a failed request."""
        self._results.append(False)
        if len(self._results) > self._success_window:
            self._results = self._results[-self._success_window :]

    def get_success_rate(self) -> float:
        """Calculate current success rate."""
        if not self._results:
            return 1.0
        return sum(1 for r in self._results if r) / len(self._results)

    def get_delay(
        self,
        attempt: int,
        retry_after: int | None = None,
    ) -> float:
        """
        Calculate delay, adjusting based on success rate.

        If success rate is below threshold, increases delay.
        """
        base_delay = super().get_delay(attempt, retry_after)

        success_rate = self.get_success_rate()
        if success_rate < self._min_success_rate:
            adjusted_delay = base_delay * self._cooldown_multiplier
            self._logger.warning(
                f"Low success rate ({success_rate:.1%}), "
                f"increasing delay from {base_delay:.2f}s to {adjusted_delay:.2f}s"
            )
            return min(adjusted_delay, self._config.max_delay)

        return base_delay

    def reset(self) -> None:
        """Reset retry state including success history."""
        super().reset()
        self._results = []
