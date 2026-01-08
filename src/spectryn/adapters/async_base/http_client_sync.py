"""
Base HTTP Client - Synchronous HTTP client with retry and rate limiting.

Provides common infrastructure for API clients:
- Connection pooling via requests Session
- Retry configuration with exponential backoff and jitter
- Rate limiter integration
- Common utility methods

Subclasses implement API-specific request handling.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base.token_bucket import TokenBucketRateLimiter
from spectryn.core.ports.issue_tracker import (
    IssueTrackerError,
    RateLimitError,
    TransientError,
)


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class BaseHttpClient(ABC):
    """
    Abstract base class for synchronous HTTP API clients.

    Provides common infrastructure:
    - Session with connection pooling
    - Retry configuration (exponential backoff with jitter)
    - Rate limiter integration
    - Utility methods for delay calculation and retry headers

    Subclasses must implement:
    - `_create_rate_limiter()`: Create API-specific rate limiter
    - `_get_logger_name()`: Return the logger name for this client
    """

    # Default retry configuration - subclasses can override
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0  # seconds
    DEFAULT_MAX_DELAY = 60.0  # seconds
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1  # 10% jitter

    # Default connection pool configuration
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_POOL_BLOCK = False
    DEFAULT_TIMEOUT = 30.0

    # Default rate limiting - subclasses should override
    DEFAULT_REQUESTS_PER_SECOND = 10.0
    DEFAULT_BURST_SIZE = 20

    def __init__(
        self,
        base_url: str,
        dry_run: bool = True,
        max_retries: int | None = None,
        initial_delay: float | None = None,
        max_delay: float | None = None,
        backoff_factor: float | None = None,
        jitter: float | None = None,
        requests_per_second: float | None = None,
        burst_size: int | None = None,
        pool_connections: int | None = None,
        pool_maxsize: int | None = None,
        pool_block: bool | None = None,
        timeout: float | None = None,
    ):
        """
        Initialize the HTTP client.

        Args:
            base_url: Base URL for API requests
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_second: Maximum request rate (None to disable)
            burst_size: Maximum burst capacity for rate limiting
            pool_connections: Number of connection pools to cache
            pool_maxsize: Maximum connections per pool
            pool_block: Whether to block when pool is full
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run

        # Use defaults if not provided
        self.max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        self.initial_delay = (
            initial_delay if initial_delay is not None else self.DEFAULT_INITIAL_DELAY
        )
        self.max_delay = max_delay if max_delay is not None else self.DEFAULT_MAX_DELAY
        self.backoff_factor = (
            backoff_factor if backoff_factor is not None else self.DEFAULT_BACKOFF_FACTOR
        )
        self.jitter = jitter if jitter is not None else self.DEFAULT_JITTER
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

        pool_connections = (
            pool_connections if pool_connections is not None else self.DEFAULT_POOL_CONNECTIONS
        )
        pool_maxsize = pool_maxsize if pool_maxsize is not None else self.DEFAULT_POOL_MAXSIZE
        pool_block = pool_block if pool_block is not None else self.DEFAULT_POOL_BLOCK

        # Setup logger
        self.logger = logging.getLogger(self._get_logger_name())

        # Rate limiting
        rps = (
            requests_per_second
            if requests_per_second is not None
            else self.DEFAULT_REQUESTS_PER_SECOND
        )
        burst = burst_size if burst_size is not None else self.DEFAULT_BURST_SIZE
        self._rate_limiter: TokenBucketRateLimiter | None = None
        if rps is not None and rps > 0:
            self._rate_limiter = self._create_rate_limiter(rps, burst)

        # Configure session with connection pooling
        self._session = requests.Session()

        adapter = HTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            pool_block=pool_block,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        # Store pool config for stats
        self._pool_connections = pool_connections
        self._pool_maxsize = pool_maxsize
        self._pool_block = pool_block

    @abstractmethod
    def _get_logger_name(self) -> str:
        """Return the logger name for this client."""
        ...

    @abstractmethod
    def _create_rate_limiter(
        self, requests_per_second: float, burst_size: int
    ) -> TokenBucketRateLimiter:
        """
        Create the API-specific rate limiter.

        Subclasses should return the appropriate rate limiter type.
        """
        ...

    def _calculate_delay(self, attempt: int, retry_after: int | None = None) -> float:
        """
        Calculate delay before next retry using exponential backoff with jitter.

        Args:
            attempt: Current attempt number (0-indexed)
            retry_after: Optional Retry-After header value in seconds

        Returns:
            Delay in seconds
        """
        if retry_after is not None:
            # Use Retry-After header if provided, but cap at max_delay
            base_delay = min(retry_after, self.max_delay)
        else:
            # Exponential backoff: initial_delay * (backoff_factor ^ attempt)
            base_delay = self.initial_delay * (self.backoff_factor**attempt)
            base_delay = min(base_delay, self.max_delay)

        # Add jitter to prevent thundering herd
        jitter_range = base_delay * self.jitter
        jitter_value = random.uniform(-jitter_range, jitter_range)

        return max(0, base_delay + jitter_value)

    def _get_retry_after(self, response: requests.Response) -> int | None:
        """
        Extract Retry-After header value from response.

        Args:
            response: HTTP response

        Returns:
            Retry delay in seconds, or None if header not present
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return int(retry_after)
            except ValueError:
                # Could be a date, but we'll ignore that for simplicity
                return None
        return None

    def _should_retry(self, status_code: int) -> bool:
        """Check if the status code should trigger a retry."""
        return status_code in RETRYABLE_STATUS_CODES

    def _execute_with_retry(
        self,
        request_func: Any,
        context: str = "",
    ) -> requests.Response:
        """
        Execute a request function with retry logic.

        This is a helper for subclasses to use in their request methods.

        Args:
            request_func: Callable that returns a requests.Response
            context: Description of the request for error messages

        Returns:
            Response from the successful request

        Raises:
            IssueTrackerError: On failure after all retries
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting before each request
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                response = request_func()

                # Update rate limiter based on response
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                # Check for retryable status codes
                if self._should_retry(response.status_code):
                    retry_after = self._get_retry_after(response)
                    delay = self._calculate_delay(attempt, retry_after)

                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"Retryable error {response.status_code} on {context}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    # All retries exhausted
                    if response.status_code == 429:
                        raise RateLimitError(
                            f"Rate limit exceeded for {context} after {self.max_retries + 1} attempts",
                            retry_after=retry_after,
                            issue_key=context,
                        )
                    raise TransientError(
                        f"Server error {response.status_code} for {context} "
                        f"after {self.max_retries + 1} attempts",
                        issue_key=context,
                    )

                return response

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Connection error on {context}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Connection failed after {self.max_retries + 1} attempts: {e}",
                    cause=e,
                )

            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Timeout on {context}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Request timed out after {self.max_retries + 1} attempts: {e}",
                    cause=e,
                )

        # This should never be reached, but just in case
        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts",
            cause=last_exception,
        )

    def close(self) -> None:
        """Close the HTTP session and release resources."""
        self._session.close()

    def __enter__(self) -> "BaseHttpClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - close session."""
        self.close()

    @property
    def stats(self) -> dict[str, Any]:
        """
        Get client statistics.

        Returns:
            Dictionary with client stats including rate limiter stats if available.
        """
        stats: dict[str, Any] = {
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "pool_connections": self._pool_connections,
            "pool_maxsize": self._pool_maxsize,
        }

        if self._rate_limiter is not None:
            stats["rate_limiter"] = self._rate_limiter.stats

        return stats
