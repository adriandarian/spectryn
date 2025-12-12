"""
Jira API Client - Low-level HTTP client for Jira REST API.

This handles the raw HTTP communication with Jira.
The JiraAdapter uses this to implement the IssueTrackerPort.
"""

import logging
import random
import time
from typing import Any, Optional

import requests

from ...core.ports.issue_tracker import (
    IssueTrackerError,
    AuthenticationError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class JiraApiClient:
    """
    Low-level Jira REST API client.
    
    Handles authentication, request/response, and error handling.
    """
    
    API_VERSION = "3"
    
    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0  # seconds
    DEFAULT_MAX_DELAY = 60.0  # seconds
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1  # 10% jitter
    
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
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/rest/api/{self.API_VERSION}"
        self.auth = (email, api_token)
        self.dry_run = dry_run
        self.logger = logging.getLogger("JiraApiClient")
        
        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        self._session = requests.Session()
        self._session.auth = self.auth
        self._session.headers.update(self.headers)
        
        self._current_user: Optional[dict] = None
    
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
        Make an authenticated request to Jira API with retry logic.
        
        Automatically retries on transient failures (connection errors,
        timeouts, rate limits, server errors) using exponential backoff.
        
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
            try:
                response = self._session.request(method, url, **kwargs)
                
                # Check for retryable status codes before handling response
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = self._get_retry_after(response)
                    delay = self._calculate_delay(attempt, retry_after)
                    
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
                    else:
                        raise TransientError(
                            f"Server error {response.status_code} for {endpoint} "
                            f"after {self.max_retries + 1} attempts",
                            issue_key=endpoint,
                        )
                
                return self._handle_response(response, endpoint)
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Connection error on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Connection failed after {self.max_retries + 1} attempts: {e}",
                    cause=e
                )
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    self.logger.warning(
                        f"Timeout on {method} {endpoint}, "
                        f"attempt {attempt + 1}/{self.max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(
                    f"Request timed out after {self.max_retries + 1} attempts: {e}",
                    cause=e
                )
        
        # This should never be reached, but just in case
        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts",
            cause=last_exception
        )
    
    def _calculate_delay(
        self,
        attempt: int,
        retry_after: int | None = None
    ) -> float:
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
            base_delay = self.initial_delay * (self.backoff_factor ** attempt)
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
        json: Optional[dict[str, Any]] = None,
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
        json: Optional[dict[str, Any]] = None,
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
    
    def _handle_response(
        self,
        response: requests.Response,
        endpoint: str
    ) -> dict[str, Any]:
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
            raise AuthenticationError(
                "Authentication failed. Check JIRA_EMAIL and JIRA_API_TOKEN."
            )
        
        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}",
                issue_key=endpoint
            )
        
        if status == 404:
            raise NotFoundError(
                f"Not found: {endpoint}",
                issue_key=endpoint
            )
        
        # Generic error
        raise IssueTrackerError(
            f"API error {status}: {error_body}",
            issue_key=endpoint
        )
    
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
    
    def search_jql(
        self,
        jql: str,
        fields: list[str],
        max_results: int = 100
    ) -> dict[str, Any]:
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
            }
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

