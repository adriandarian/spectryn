"""
YouTrack API Client - Low-level HTTP client for YouTrack REST API.

This handles the raw HTTP communication with YouTrack.
The YouTrackAdapter uses this to implement the IssueTrackerPort.

YouTrack REST API documentation:
https://www.jetbrains.com/help/youtrack/server/rest-api.html
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectra.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
    get_retry_after,
)
from spectra.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class YouTrackApiClient:
    """
    Low-level YouTrack REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - Permanent Token authentication
    - Automatic retry with exponential backoff for transient failures
    - Rate limiting support
    - Connection pooling for performance
    """

    API_VERSION = "2023.2"  # YouTrack API version

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative)
    DEFAULT_REQUESTS_PER_SECOND = 10.0
    DEFAULT_BURST_SIZE = 20

    # Connection pool settings
    DEFAULT_POOL_CONNECTIONS = 10
    DEFAULT_POOL_MAXSIZE = 10
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        url: str,
        token: str,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the YouTrack client.

        Args:
            url: YouTrack instance URL (e.g., https://youtrack.example.com)
            token: Permanent Token for authentication
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            timeout: Request timeout in seconds
        """
        self.base_url = url.rstrip("/")
        self.api_url = f"{self.base_url}/api"
        self.token = token
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("YouTrackApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Headers for YouTrack API
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(
            pool_connections=self.DEFAULT_POOL_CONNECTIONS,
            pool_maxsize=self.DEFAULT_POOL_MAXSIZE,
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        # Cache
        self._current_user: dict | None = None

    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an authenticated request to YouTrack API with retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'issues')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and relative endpoints
        if endpoint.startswith("/"):
            url = f"{self.api_url}{endpoint}"
        elif endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.api_url}/{endpoint}"

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, **kwargs)

                # Check for retryable status codes
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

                    if response.status_code == 429:
                        raise RateLimitError(
                            f"YouTrack rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                            issue_key=endpoint,
                        )
                    raise TransientError(
                        f"YouTrack server error {response.status_code} for {endpoint}",
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
                        f"Connection error on {method} {endpoint}, retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Connection failed: {e}", cause=e)

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
                    self.logger.warning(f"Timeout on {method} {endpoint}, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Request timed out: {e}", cause=e)

        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a GET request."""
        return self.request("GET", endpoint, **kwargs)

    def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a POST request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would POST to {endpoint}")
            return {}
        return self.request("POST", endpoint, json=json, **kwargs)

    def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PUT request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PUT to {endpoint}")
            return {}
        return self.request("PUT", endpoint, json=json, **kwargs)

    def patch(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Perform a PATCH request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PATCH {endpoint}")
            return {}
        return self.request("PATCH", endpoint, json=json, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
        """Perform a DELETE request. Respects dry_run mode."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {endpoint}")
            return {}
        return self.request("DELETE", endpoint, **kwargs)

    # -------------------------------------------------------------------------
    # Response Handling
    # -------------------------------------------------------------------------

    def _handle_response(
        self, response: requests.Response, endpoint: str
    ) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors to typed exceptions."""
        if response.ok:
            if response.text:
                try:
                    json_data = response.json()
                    # Ensure we return the correct type
                    if isinstance(json_data, (dict, list)):
                        return json_data
                    return {}
                except ValueError:
                    # Some endpoints return empty responses
                    return {}
            return {}

        status = response.status_code
        error_body = response.text[:500] if response.text else ""

        if status == 401:
            raise AuthenticationError("YouTrack authentication failed. Check your token.")

        if status == 403:
            raise PermissionError(
                f"Permission denied for {endpoint}. Check token permissions.", issue_key=endpoint
            )

        if status == 404:
            raise NotFoundError(f"Not found: {endpoint}", issue_key=endpoint)

        raise IssueTrackerError(f"YouTrack API error {status}: {error_body}", issue_key=endpoint)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the currently authenticated user."""
        if self._current_user is None:
            result = self.get("users/me")
            if isinstance(result, dict):
                self._current_user = result
            else:
                self._current_user = {}
        return self._current_user

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_current_user()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_user is not None

    # -------------------------------------------------------------------------
    # Issues API
    # -------------------------------------------------------------------------

    def get_issue(self, issue_id: str, fields: str | None = None) -> dict[str, Any]:
        """
        Get a single issue by ID.

        Args:
            issue_id: Issue ID (e.g., "PROJ-123")
            fields: Optional comma-separated list of fields to return
        """
        params = {}
        if fields:
            params["fields"] = fields
        result = self.get(f"issues/{issue_id}", params=params)
        return result if isinstance(result, dict) else {}

    def create_issue(
        self,
        project_id: str,
        summary: str,
        issue_type: str,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            project_id: Project ID
            summary: Issue summary/title
            issue_type: Issue type (e.g., "Task", "Epic", "Subtask")
            description: Issue description
            **kwargs: Additional fields (priority, assignee, etc.)
        """
        data: dict[str, Any] = {
            "project": {"id": project_id},
            "summary": summary,
            "type": {"name": issue_type},
        }
        if description:
            data["description"] = description

        # Add additional fields
        data.update(kwargs)

        result = self.post("issues", json=data)
        return result if isinstance(result, dict) else {}

    def update_issue(
        self,
        issue_id: str,
        summary: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Update an existing issue.

        Args:
            issue_id: Issue ID
            summary: New summary (optional)
            description: New description (optional)
            **kwargs: Additional fields to update
        """
        data: dict[str, Any] = {}
        if summary is not None:
            data["summary"] = summary
        if description is not None:
            data["description"] = description
        data.update(kwargs)

        result = self.put(f"issues/{issue_id}", json=data)
        return result if isinstance(result, dict) else {}

    def get_issue_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all comments on an issue."""
        result = self.get(f"issues/{issue_id}/comments")
        return result if isinstance(result, list) else []

    def add_comment(self, issue_id: str, text: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        result = self.post(f"issues/{issue_id}/comments", json={"text": text})
        return result if isinstance(result, dict) else {}

    def get_issue_links(self, issue_id: str) -> list[dict[str, Any]]:
        """Get all links for an issue."""
        result = self.get(f"issues/{issue_id}/links")
        return result if isinstance(result, list) else []

    def create_link(
        self,
        source_id: str,
        target_id: str,
        link_type: str,
    ) -> dict[str, Any]:
        """
        Create a link between two issues.

        Args:
            source_id: Source issue ID
            target_id: Target issue ID
            link_type: Link type (e.g., "depends on", "relates to")
        """
        data = {
            "target": {"id": target_id},
            "linkType": {"name": link_type},
        }
        result = self.post(f"issues/{source_id}/links", json=data)
        return result if isinstance(result, dict) else {}

    def search_issues(
        self,
        query: str,
        fields: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Search for issues using YouTrack Query Language (YQL).

        Args:
            query: YQL query (e.g., "project: PROJ State: Open")
            fields: Optional comma-separated list of fields to return
            max_results: Maximum results to return
        """
        params: dict[str, Any] = {"query": query, "max": max_results}
        if fields:
            params["fields"] = fields

        result = self.get("issues", params=params)
        return result if isinstance(result, list) else []

    def get_project_issues(
        self,
        project_id: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Get all issues in a project."""
        return self.search_issues(f"project: {project_id}", max_results=max_results)

    def get_epic_children(self, epic_id: str) -> list[dict[str, Any]]:
        """
        Get all children of an epic.

        Args:
            epic_id: Epic issue ID
        """
        # YouTrack uses links to connect epics to their children
        # Search for issues linked to this epic
        return self.search_issues(f"issue: {epic_id} and has: {epic_id}", max_results=1000)

    def get_available_states(self, project_id: str) -> list[dict[str, Any]]:
        """Get available states for a project."""
        result = self.get(f"admin/projects/{project_id}/customFields/State")
        if isinstance(result, dict):
            # Extract states from custom field definition
            states = result.get("values", [])
            return states if isinstance(states, list) else []
        return []

    def get_available_priorities(self) -> list[dict[str, Any]]:
        """Get available priorities."""
        result = self.get("admin/customFieldSettings/bundles/priority")
        if isinstance(result, dict):
            values = result.get("values", [])
            return values if isinstance(values, list) else []
        return []

    def transition_issue(
        self,
        issue_id: str,
        state: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """
        Transition an issue to a new state.

        Args:
            issue_id: Issue ID
            state: Target state name
            comment: Optional comment for the transition
        """
        data: dict[str, Any] = {"state": {"name": state}}
        if comment:
            data["comment"] = comment

        result = self.post(f"issues/{issue_id}/executeCommand", json=data)
        return result if isinstance(result, dict) else {}

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release connection pool resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "YouTrackApiClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        self.close()
