"""
Async HTTP Client - Base async HTTP client with retry and rate limiting.

Provides a foundation for async API clients with:
- Automatic retry with exponential backoff
- Rate limiting integration
- Connection pooling via aiohttp
- Typed error handling
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Any


try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

if TYPE_CHECKING:
    import aiohttp

from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)

from .rate_limiter import AsyncRateLimiter


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class AsyncHttpClient:
    """
    Base async HTTP client with retry logic and rate limiting.

    Designed to be subclassed by specific API clients (Jira, GitHub, etc.).
    Uses aiohttp for async HTTP requests with connection pooling.

    Features:
    - Automatic retry with exponential backoff and jitter
    - Proactive rate limiting to prevent 429 errors
    - Connection pooling for performance
    - Configurable timeouts
    - Typed exception handling

    Example:
        >>> client = AsyncHttpClient(
        ...     base_url="https://api.example.com",
        ...     headers={"Authorization": "Bearer token"},
        ... )
        >>> async with client:
        ...     data = await client.get("/users/me")
    """

    # Default configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_REQUESTS_PER_SECOND = 5.0
    DEFAULT_BURST_SIZE = 10

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        timeout: float = DEFAULT_TIMEOUT,
        requests_per_second: float | None = DEFAULT_REQUESTS_PER_SECOND,
        burst_size: int = DEFAULT_BURST_SIZE,
        connector_limit: int = 100,
        connector_limit_per_host: int = 10,
    ):
        """
        Initialize the async HTTP client.

        Args:
            base_url: Base URL for all requests
            headers: Default headers for all requests
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            timeout: Request timeout in seconds
            requests_per_second: Maximum request rate (None to disable)
            burst_size: Maximum burst capacity for rate limiting
            connector_limit: Total connection pool limit
            connector_limit_per_host: Per-host connection limit
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp is required for async operations. Install with: pip install aiohttp"
            )

        self.base_url = base_url.rstrip("/")
        self.default_headers = headers or {}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Connection pool configuration
        self._connector_limit = connector_limit
        self._connector_limit_per_host = connector_limit_per_host

        # Rate limiting
        self._rate_limiter: AsyncRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = AsyncRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Session (created lazily)
        self._session: aiohttp.ClientSession | None = None
        self._connector: aiohttp.TCPConnector | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=self._connector_limit,
                limit_per_host=self._connector_limit_per_host,
            )
            self._session = aiohttp.ClientSession(
                connector=self._connector,
                headers=self.default_headers,
                timeout=self.timeout,
            )
        return self._session

    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an async HTTP request with rate limiting and retry.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (appended to base_url)
            **kwargs: Additional arguments for aiohttp

        Returns:
            JSON response as dict or list

        Raises:
            IssueTrackerError: On API errors after all retries exhausted
        """
        # Build URL
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        elif endpoint.startswith("/"):
            url = f"{self.base_url}{endpoint}"
        else:
            url = f"{self.base_url}/{endpoint}"

        session = await self._get_session()
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting
            if self._rate_limiter is not None:
                await self._rate_limiter.acquire()

            try:
                async with session.request(method, url, **kwargs) as response:
                    # Update rate limiter from response
                    if self._rate_limiter is not None:
                        await self._rate_limiter.update_from_response(
                            response.status,
                            dict(response.headers),
                        )

                    # Check for retryable status codes
                    if response.status in RETRYABLE_STATUS_CODES:
                        retry_after = self._get_retry_after(response.headers)
                        delay = self._calculate_delay(attempt, retry_after)

                        if attempt < self.max_retries:
                            self.logger.warning(
                                f"Retryable error {response.status} on {method} {endpoint}, "
                                f"attempt {attempt + 1}/{self.max_retries + 1}, "
                                f"retrying in {delay:.2f}s"
                            )
                            await asyncio.sleep(delay)
                            continue

                        # All retries exhausted
                        if response.status == 429:
                            raise RateLimitError(
                                f"Rate limit exceeded for {endpoint} after {self.max_retries + 1} attempts",
                                retry_after=retry_after,
                                issue_key=endpoint,
                            )
                        raise TransientError(
                            f"Server error {response.status} for {endpoint} "
                            f"after {self.max_retries + 1} attempts",
                            issue_key=endpoint,
                        )

                    return await self._handle_response(response, endpoint)

            except aiohttp.ClientConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Connection error on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Connection failed after {self.max_retries + 1} attempts: {e}", cause=e
                ) from e

            except asyncio.TimeoutError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Timeout on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Request timed out after {self.max_retries + 1} attempts", cause=e
                ) from e

        # Should never reach here
        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def _calculate_delay(self, attempt: int, retry_after: int | None = None) -> float:
        """Calculate delay before next retry using exponential backoff."""
        if retry_after is not None:
            base_delay = min(retry_after, self.max_delay)
        else:
            base_delay = self.initial_delay * (self.backoff_factor**attempt)
            base_delay = min(base_delay, self.max_delay)

        # Add jitter
        jitter_range = base_delay * self.jitter
        jitter_value = random.uniform(-jitter_range, jitter_range)

        return max(0, base_delay + jitter_value)

    def _get_retry_after(self, headers: Any) -> int | None:
        """Extract Retry-After header value."""
        retry_after = headers.get("Retry-After")
        if retry_after is not None:
            try:
                return int(retry_after)
            except ValueError:
                return None
        return None

    async def _handle_response(
        self,
        response: aiohttp.ClientResponse,
        endpoint: str,
    ) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors to typed exceptions."""
        if response.ok:
            text = await response.text()
            if text:
                return await response.json()
            return {}

        status = response.status
        error_body = (await response.text())[:500]

        if status == 401:
            raise AuthenticationError("Authentication failed. Check credentials.")

        if status == 403:
            raise PermissionError(f"Permission denied for {endpoint}", issue_key=endpoint)

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"API error {status}: {error_body}", issue_key=endpoint)

    # Convenience methods

    async def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a GET request."""
        return await self.request("GET", endpoint, **kwargs)

    async def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a POST request."""
        return await self.request("POST", endpoint, json=json, **kwargs)

    async def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PUT request."""
        return await self.request("PUT", endpoint, json=json, **kwargs)

    async def patch(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PATCH request."""
        return await self.request("PATCH", endpoint, json=json, **kwargs)

    async def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a DELETE request."""
        return await self.request("DELETE", endpoint, **kwargs)

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.debug("Closed async HTTP session")

    async def __aenter__(self) -> "AsyncHttpClient":
        """Context manager entry."""
        await self._get_session()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - closes the client."""
        await self.close()

    @property
    def rate_limiter(self) -> AsyncRateLimiter | None:
        """Get the rate limiter instance."""
        return self._rate_limiter

    @property
    def rate_limit_stats(self) -> dict[str, Any] | None:
        """Get rate limiter statistics."""
        if self._rate_limiter is None:
            return None
        return self._rate_limiter.stats
