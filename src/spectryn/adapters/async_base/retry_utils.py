"""
Retry Utilities - Shared retry logic for HTTP clients.

Provides common utilities for implementing retry with exponential backoff:
- calculate_delay(): Exponential backoff with jitter
- get_retry_after(): Parse Retry-After header
- RETRYABLE_STATUS_CODES: Standard codes that should trigger retry

These utilities are used by Jira, GitHub, Linear, and other API clients.
"""

import random

import requests


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def calculate_delay(
    attempt: int,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: float = 0.1,
    retry_after: int | None = None,
) -> float:
    """
    Calculate delay before next retry using exponential backoff with jitter.

    Uses the formula: delay = initial_delay * (backoff_factor ^ attempt)
    Then adds random jitter to prevent thundering herd.

    Args:
        attempt: Current attempt number (0-indexed)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        backoff_factor: Multiplier for exponential backoff (default: 2.0)
        jitter: Random jitter factor (0.1 = ±10% variation)
        retry_after: Optional Retry-After header value in seconds

    Returns:
        Delay in seconds (always >= 0)

    Example:
        >>> calculate_delay(0)  # First retry: ~1s
        >>> calculate_delay(1)  # Second retry: ~2s
        >>> calculate_delay(2)  # Third retry: ~4s
    """
    if retry_after is not None:
        # Use Retry-After header if provided, but cap at max_delay
        base_delay = min(retry_after, max_delay)
    else:
        # Exponential backoff: initial_delay * (backoff_factor ^ attempt)
        base_delay = initial_delay * (backoff_factor**attempt)
        base_delay = min(base_delay, max_delay)

    # Add jitter to prevent thundering herd
    jitter_range = base_delay * jitter
    jitter_value = random.uniform(-jitter_range, jitter_range)

    return max(0, base_delay + jitter_value)


def get_retry_after(response: requests.Response) -> int | None:
    """
    Extract Retry-After header value from HTTP response.

    Parses the standard Retry-After header that servers send with 429
    (Too Many Requests) responses to indicate when the client can retry.

    Args:
        response: HTTP response object

    Returns:
        Retry delay in seconds, or None if header not present or invalid

    Example:
        >>> response = requests.get(url)
        >>> retry_after = get_retry_after(response)
        >>> if retry_after:
        ...     time.sleep(retry_after)
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return int(retry_after)
        except ValueError:
            # Could be a date format, but we ignore that for simplicity
            return None
    return None


def should_retry(status_code: int) -> bool:
    """
    Check if an HTTP status code should trigger a retry.

    Retryable codes include:
    - 429: Too Many Requests (rate limited)
    - 500: Internal Server Error
    - 502: Bad Gateway
    - 503: Service Unavailable
    - 504: Gateway Timeout

    Args:
        status_code: HTTP status code

    Returns:
        True if the status code is retryable
    """
    return status_code in RETRYABLE_STATUS_CODES
