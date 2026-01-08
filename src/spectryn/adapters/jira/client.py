"""
Jira API Client - Low-level HTTP client for Jira REST API.

This handles the raw HTTP communication with Jira.
The JiraAdapter uses this to implement the IssueTrackerPort.
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    JiraRateLimiter,
    calculate_delay,
    get_retry_after,
)
from spectryn.core.constants import ContentType, HttpHeader
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class JiraApiClient:
    """
    Low-level Jira REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - Automatic retry with exponential backoff for transient failures
    - Proactive rate limiting using token bucket algorithm
    - Respects Jira API rate limits to prevent 429 errors
    """

    API_VERSION = "3"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0  # seconds
    DEFAULT_MAX_DELAY = 60.0  # seconds
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1  # 10% jitter

    # Default rate limiting configuration
    # Jira Cloud allows ~100 requests/minute for most endpoints
    # We use conservative defaults to avoid hitting limits
    DEFAULT_REQUESTS_PER_SECOND = 5.0  # 300 per minute (safe margin)
    DEFAULT_BURST_SIZE = 10  # Allow short bursts

    # Default connection pool configuration
    DEFAULT_POOL_CONNECTIONS = 10  # Number of connection pools to cache
    DEFAULT_POOL_MAXSIZE = 10  # Max connections per pool
    DEFAULT_POOL_BLOCK = False  # Don't block when pool is exhausted
    DEFAULT_TIMEOUT = 30.0  # Request timeout in seconds

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_second: float | None = DEFAULT_REQUESTS_PER_SECOND,
        burst_size: int = DEFAULT_BURST_SIZE,
        pool_connections: int = DEFAULT_POOL_CONNECTIONS,
        pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
        pool_block: bool = DEFAULT_POOL_BLOCK,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Jira client.

        Args:
            base_url: Jira instance URL (e.g., https://company.atlassian.net)
            email: User email for authentication
            api_token: API token
            dry_run: If True, don't make write operations
            max_retries: Maximum number of retry attempts for transient failures
            initial_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10% variation)
            requests_per_second: Maximum request rate (None to disable rate limiting)
            burst_size: Maximum burst capacity for rate limiting
            pool_connections: Number of connection pools to cache
            pool_maxsize: Maximum connections to save in the pool
            pool_block: Whether to block when pool is full
            timeout: Request timeout in seconds (connect + read)
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/rest/api/{self.API_VERSION}"
        self.auth = (email, api_token)
        self.dry_run = dry_run
        self.logger = logging.getLogger("JiraApiClient")
        self.timeout = timeout

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: JiraRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = JiraRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        self.headers = {
            HttpHeader.ACCEPT: ContentType.JSON,
            HttpHeader.CONTENT_TYPE: ContentType.JSON,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.auth = self.auth
        self._session.headers.update(self.headers)

        # Configure HTTP adapter with connection pooling
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

        self._current_user: dict | None = None

    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make an authenticated request to Jira API with rate limiting and retry logic.

        Applies proactive rate limiting before each request and automatically
        retries on transient failures (connection errors, timeouts, rate limits,
        server errors) using exponential backoff.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., 'issue/PROJ-123')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response as dict

        Raises:
            IssueTrackerError: On API errors after all retries exhausted
            AuthenticationError: On 401 (not retried)
            NotFoundError: On 404 (not retried)
            PermissionError: On 403 (not retried)
            RateLimitError: On 429 after all retries exhausted
            TransientError: On 5xx after all retries exhausted
        """
        url = f"{self.api_url}/{endpoint}"
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting before each request attempt
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                # Apply default timeout if not specified
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout
                response = self._session.request(method, url, **kwargs)

                # Update rate limiter based on response (for dynamic adjustment)
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                # Check for retryable status codes before handling response
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = get_retry_after(response)
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                        retry_after=retry_after,
                    )

                    if attempt < self.max_retries:
                        self.logger.warning(
                            f"Retryable error {response.status_code} on {method} {endpoint}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    # All retries exhausted
                    if response.status_code == 429:
                        raise RateLimitError(
                            f"Rate limit exceeded for {endpoint} after {self.max_retries + 1} attempts",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"Server error {response.status_code} for {endpoint} "
                        f"after {self.max_retries + 1} attempts",
                        issue_key=endpoint,
                    )

                return self._handle_response(response, endpoint)

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                    )
                    self.logger.warning(
                        f"Connection error on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Connection failed after {self.max_retries + 1} attempts: {e}", cause=e
                )

            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
                    )
                    self.logger.warning(
                        f"Timeout on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Request timed out after {self.max_retries + 1} attempts: {e}", cause=e
                )

        # This should never be reached, but just in case
        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """
        Perform a GET request to the Jira API.

        Args:
            endpoint: API endpoint (e.g., 'issue/PROJ-123').
            **kwargs: Additional arguments passed to requests.

        Returns:
            JSON response as dictionary.
        """
        return self.request("GET", endpoint, **kwargs)

    def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Perform a POST request to the Jira API.

        Respects dry_run mode for mutation endpoints (search is allowed).

        Args:
            endpoint: API endpoint.
            json: JSON body to send.
            **kwargs: Additional arguments passed to requests.

        Returns:
            JSON response as dictionary, or empty dict in dry-run mode.
        """
        if self.dry_run and not endpoint.endswith("search/jql"):
            self.logger.info(f"[DRY-RUN] Would POST to {endpoint}")
            return {}
        return self.request("POST", endpoint, json=json, **kwargs)

    def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Perform a PUT request to the Jira API.

        Respects dry_run mode - no changes made in dry-run.

        Args:
            endpoint: API endpoint.
            json: JSON body to send.
            **kwargs: Additional arguments passed to requests.

        Returns:
            JSON response as dictionary, or empty dict in dry-run mode.
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PUT to {endpoint}")
            return {}
        return self.request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """
        Perform a DELETE request to the Jira API.

        Respects dry_run mode - no changes made in dry-run.

        Args:
            endpoint: API endpoint.
            **kwargs: Additional arguments passed to requests.

        Returns:
            JSON response as dictionary, or empty dict in dry-run mode.
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {endpoint}")
            return {}
        return self.request("DELETE", endpoint, **kwargs)

    # -------------------------------------------------------------------------
    # Response Handling
    # -------------------------------------------------------------------------

    def _handle_response(self, response: requests.Response, endpoint: str) -> dict[str, Any]:
        """
        Handle API response and convert errors to typed exceptions.

        Args:
            response: The requests Response object.
            endpoint: The endpoint that was called (for error messages).

        Returns:
            Parsed JSON response as dictionary.

        Raises:
            AuthenticationError: On 401 responses.
            PermissionError: On 403 responses.
            NotFoundError: On 404 responses.
            IssueTrackerError: On other error responses.
        """
        if response.ok:
            if response.text:
                return response.json()
            return {}

        # Handle specific error codes
        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("Authentication failed. Check JIRA_EMAIL and JIRA_API_TOKEN.")

        if status == 403:
            raise PermissionError(f"Permission denied for {endpoint}", issue_key=endpoint)

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        # Generic error
        raise IssueTrackerError(f"API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def get_myself(self) -> dict[str, Any]:
        """
        Get the current authenticated user's information.

        Results are cached after the first call.

        Returns:
            Dictionary with user details (accountId, displayName, etc.).
        """
        if self._current_user is None:
            self._current_user = self.get("myself")
        return self._current_user

    def get_current_user_id(self) -> str:
        """
        Get the current user's Jira account ID.

        Returns:
            The accountId string for the authenticated user.
        """
        return self.get_myself()["accountId"]

    def search_jql(self, jql: str, fields: list[str], max_results: int = 100) -> dict[str, Any]:
        """
        Execute a JQL search query.

        Args:
            jql: The JQL query string.
            fields: List of field names to include in results.
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with 'issues' list and pagination info.
        """
        return self.post(
            "search/jql",
            json={
                "jql": jql,
                "maxResults": max_results,
                "fields": fields,
            },
        )

    def test_connection(self) -> bool:
        """
        Test if the API connection and credentials are valid.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.get_myself()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """
        Check if the client has successfully connected.

        Returns:
            True if user info has been fetched (connection verified).
        """
        return self._current_user is not None

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------

    @property
    def rate_limiter(self) -> JiraRateLimiter | None:
        """Get the rate limiter instance, if rate limiting is enabled."""
        return self._rate_limiter

    @property
    def rate_limit_stats(self) -> dict[str, Any] | None:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with stats, or None if rate limiting is disabled.
            Includes: total_requests, total_wait_time, average_wait_time,
            available_tokens, requests_per_second, burst_size.
        """
        if self._rate_limiter is None:
            return None
        return self._rate_limiter.stats

    @property
    def is_rate_limited(self) -> bool:
        """Check if rate limiting is enabled."""
        return self._rate_limiter is not None

    # -------------------------------------------------------------------------
    # Connection Pooling
    # -------------------------------------------------------------------------

    @property
    def pool_config(self) -> dict[str, Any]:
        """
        Get connection pool configuration.

        Returns:
            Dictionary with pool settings: pool_connections, pool_maxsize,
            pool_block, timeout.
        """
        return {
            "pool_connections": self._pool_connections,
            "pool_maxsize": self._pool_maxsize,
            "pool_block": self._pool_block,
            "timeout": self.timeout,
        }

    def close(self) -> None:
        """
        Close the client and release connection pool resources.

        Should be called when the client is no longer needed to free up
        connections. After calling close(), the client should not be used.
        """
        self._session.close()
        self.logger.debug("Closed HTTP session and released connection pool")

    def __enter__(self) -> "JiraApiClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - closes the client."""
        self.close()

    # -------------------------------------------------------------------------
    # Attachment Operations
    # -------------------------------------------------------------------------

    def get_issue_attachments(self, issue_key: str) -> list[dict[str, Any]]:
        """
        Get all attachments for an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            List of attachment dictionaries
        """
        issue = self.get(f"issue/{issue_key}", params={"fields": "attachment"})
        fields = issue.get("fields", {})
        attachments = fields.get("attachment", [])
        return list(attachments) if isinstance(attachments, list) else []

    def upload_attachment(
        self,
        issue_key: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to an issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary

        Raises:
            NotFoundError: If file doesn't exist
            IssueTrackerError: On upload failure
        """
        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to issue {issue_key}")
            return {"id": "attachment:dry-run", "filename": name or file_path_obj.name}

        attachment_name = name or file_path_obj.name
        url = f"{self.api_url}/issue/{issue_key}/attachments"

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            # Open file and upload using multipart/form-data
            # Jira requires X-Atlassian-Token: no-check header for file uploads
            with open(file_path_obj, "rb") as f:
                files = {"file": (attachment_name, f)}
                headers = dict(self._session.headers)
                headers.pop("Content-Type", None)  # Remove for multipart
                headers["X-Atlassian-Token"] = "no-check"

                response = self._session.post(
                    url,
                    files=files,
                    headers=headers,
                    timeout=self.timeout,
                )

            if not response.ok:
                self._handle_error(response, f"issue/{issue_key}/attachments")

            result = response.json()
            # Jira returns a list of attachments
            if isinstance(result, list) and len(result) > 0:
                return dict(result[0])
            return {"id": "unknown", "filename": attachment_name}

        except requests.RequestException as e:
            raise IssueTrackerError(f"Failed to upload attachment: {e}")

    def download_attachment(
        self,
        attachment_id: str,
        download_url: str,
        download_path: str,
    ) -> bool:
        """
        Download an attachment to a local file.

        Args:
            attachment_id: Attachment ID
            download_url: URL to download the attachment
            download_path: Path to save the file

        Returns:
            True if successful
        """
        from pathlib import Path

        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would download attachment {attachment_id} to {download_path}"
            )
            return True

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            response = self._session.get(download_url, stream=True, timeout=self.timeout)
            response.raise_for_status()

            file_path = Path(download_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.logger.info(f"Downloaded attachment {attachment_id} to {download_path}")
            return True

        except requests.RequestException as e:
            self.logger.error(f"Failed to download attachment: {e}")
            return False

    def delete_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment by ID.

        Args:
            attachment_id: Attachment ID

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id}")
            return True

        try:
            self.delete(f"attachment/{attachment_id}")
            self.logger.info(f"Deleted attachment {attachment_id}")
            return True
        except IssueTrackerError as e:
            self.logger.error(f"Failed to delete attachment: {e}")
            return False
