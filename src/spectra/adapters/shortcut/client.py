"""
Shortcut API Client - REST client for Shortcut (formerly Clubhouse) API.

This handles the raw HTTP communication with Shortcut.
The ShortcutAdapter uses this to implement the IssueTrackerPort.

Shortcut API Documentation: https://shortcut.com/api/rest/v3
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


class ShortcutRateLimiter:
    """
    Rate limiter for Shortcut API.

    Shortcut has a rate limit of 200 requests per minute.
    """

    def __init__(
        self,
        requests_per_second: float = 3.0,  # ~180/min, under 200/min limit
        burst_size: int = 10,
    ):
        """
        Initialize the rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
            burst_size: Maximum tokens in bucket (allows short bursts).
        """
        self.requests_per_second = requests_per_second
        self.burst_size = max(1, burst_size)

        # Token bucket state
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = __import__("threading").Lock()

        # Rate limit tracking from headers
        self._retry_after: float | None = None

        # Statistics
        self._total_requests = 0
        self._total_wait_time = 0.0

        self.logger = logging.getLogger("ShortcutRateLimiter")

    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire a token, waiting if necessary.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if token was acquired, False if timeout was reached.
        """
        start_time = time.monotonic()

        while True:
            with self._lock:
                # Check if we need to wait due to rate limit response
                if self._retry_after is not None:
                    wait_time = self._retry_after - time.time()
                    if wait_time > 0:
                        self.logger.warning(f"Rate limit: waiting {wait_time:.1f}s")
                        self._total_wait_time += wait_time
                        self._lock.release()
                        try:
                            time.sleep(wait_time)
                        finally:
                            self._lock.acquire()
                        self._retry_after = None
                        continue
                    self._retry_after = None

                self._refill_tokens()

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._total_requests += 1
                    return True

                tokens_needed = 1.0 - self._tokens
                wait_time = tokens_needed / self.requests_per_second

            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0.01:
                self.logger.debug(f"Rate limit: waiting {wait_time:.3f}s for token")

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        new_tokens = elapsed * self.requests_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)

    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter based on Shortcut response headers."""
        with self._lock:
            # Check for Retry-After header
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                import contextlib

                with contextlib.suppress(ValueError):
                    self._retry_after = time.time() + float(retry_after)

            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.5, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited, reducing rate from "
                    f"{old_rate:.1f} to {self.requests_per_second:.1f} req/s"
                )

    @property
    def stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_wait_time": self._total_wait_time,
                "current_tokens": self._tokens,
                "requests_per_second": self.requests_per_second,
            }


class ShortcutApiClient:
    """
    Low-level Shortcut REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - REST API with automatic retry
    - API token authentication
    - Automatic retry with exponential backoff
    - Rate limiting aware of Shortcut's 200 req/min limit
    - Connection pooling
    """

    BASE_URL = "https://api.app.shortcut.com/api/v3"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Shortcut)
    DEFAULT_REQUESTS_PER_SECOND = 3.0  # ~180/min, under 200/min limit
    DEFAULT_BURST_SIZE = 10

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_token: str,
        workspace_id: str,
        api_url: str = BASE_URL,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_second: float | None = DEFAULT_REQUESTS_PER_SECOND,
        burst_size: int = DEFAULT_BURST_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Shortcut client.

        Args:
            api_token: Shortcut API token
            workspace_id: Shortcut workspace ID
            api_url: Shortcut API base URL
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_second: Maximum request rate (None to disable)
            burst_size: Maximum burst capacity
            timeout: Request timeout in seconds
        """
        self.api_token = api_token
        self.workspace_id = workspace_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("ShortcutApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: ShortcutRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = ShortcutRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for Shortcut API
        self.headers = {
            "Content-Type": "application/json",
            "Shortcut-Token": api_token,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._current_member: dict | None = None

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
        Make an authenticated request to Shortcut API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., '/stories')
            **kwargs: Additional arguments for requests

        Returns:
            JSON response (dict or list)

        Raises:
            IssueTrackerError: On API errors
        """
        # Support both absolute endpoints and relative endpoints
        if endpoint.startswith("/"):
            url = f"{self.api_url}{endpoint}"
        else:
            url = f"{self.api_url}/{endpoint}"

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, **kwargs)

                # Update rate limiter from response headers
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

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
                            f"Retryable error {response.status_code}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    if response.status_code == 429:
                        raise RateLimitError(
                            "Shortcut rate limit exceeded",
                            retry_after=int(delay),
                        )
                    raise TransientError(f"Shortcut server error {response.status_code}")

                return self._handle_response(response)

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
                    self.logger.warning(f"Connection error, retrying in {delay:.2f}s")
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
                    self.logger.warning(f"Timeout, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    continue
                raise IssueTrackerError(f"Request timed out: {e}", cause=e)

        raise IssueTrackerError(
            f"Request failed after {self.max_retries + 1} attempts", cause=last_exception
        )

    def _handle_response(self, response: requests.Response) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Shortcut authentication failed. Check your API token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if response.status_code == 404:
            raise NotFoundError("Resource not found")

        if not response.ok:
            error_text = response.text[:500] if response.text else ""
            raise IssueTrackerError(f"Shortcut API error {response.status_code}: {error_text}")

        # Shortcut returns JSON
        try:
            json_data: dict[str, Any] | list[Any] = response.json()
            return json_data
        except ValueError as e:
            raise IssueTrackerError(f"Invalid JSON response: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Current User API
    # -------------------------------------------------------------------------

    def get_current_member(self) -> dict[str, Any]:
        """Get the current authenticated member."""
        if self._current_member is None:
            data = self.request("GET", "/member")
            if isinstance(data, dict):
                self._current_member = data
            else:
                self._current_member = {}
        return self._current_member

    def test_connection(self) -> bool:
        """Test if the API connection and credentials are valid."""
        try:
            self.get_current_member()
            return True
        except IssueTrackerError:
            return False

    @property
    def is_connected(self) -> bool:
        """Check if the client has successfully connected."""
        return self._current_member is not None

    # -------------------------------------------------------------------------
    # Epics API
    # -------------------------------------------------------------------------

    def get_epic(self, epic_id: int) -> dict[str, Any]:
        """Get an epic by ID."""
        result = self.request("GET", f"/epics/{epic_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def get_epic_stories(self, epic_id: int) -> list[dict[str, Any]]:
        """Get all stories in an epic."""
        data = self.request("GET", f"/epics/{epic_id}/stories")
        return data if isinstance(data, list) else []

    def create_epic(
        self,
        name: str,
        description: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Create a new epic."""
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        if state:
            payload["state"] = state

        result = self.request("POST", "/epics", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def update_epic(
        self,
        epic_id: int,
        name: str | None = None,
        description: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing epic."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if state is not None:
            payload["state"] = state

        if not payload:
            return {}

        result = self.request("PUT", f"/epics/{epic_id}", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Stories API
    # -------------------------------------------------------------------------

    def get_story(self, story_id: int) -> dict[str, Any]:
        """Get a story by ID."""
        result = self.request("GET", f"/stories/{story_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def create_story(
        self,
        name: str,
        description: str | None = None,
        epic_id: int | None = None,
        story_type: str = "feature",
        workflow_state_id: int | None = None,
        estimate: int | None = None,
        priority: str | None = None,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new story."""
        payload: dict[str, Any] = {
            "name": name,
            "story_type": story_type,
        }
        if description:
            payload["description"] = description
        if epic_id:
            payload["epic_id"] = epic_id
        if workflow_state_id:
            payload["workflow_state_id"] = workflow_state_id
        if estimate:
            payload["estimate"] = estimate
        if priority:
            payload["priority"] = priority
        if owner_ids:
            payload["owner_ids"] = owner_ids

        result = self.request("POST", "/stories", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def update_story(
        self,
        story_id: int,
        name: str | None = None,
        description: str | None = None,
        epic_id: int | None = None,
        workflow_state_id: int | None = None,
        estimate: int | None = None,
        priority: str | None = None,
        owner_ids: list[str] | None = None,
        depends_on: list[int] | None = None,
        iteration_id: int | None = None,
        file_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Update an existing story."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if epic_id is not None:
            payload["epic_id"] = epic_id
        if workflow_state_id is not None:
            payload["workflow_state_id"] = workflow_state_id
        if estimate is not None:
            payload["estimate"] = estimate
        if priority is not None:
            payload["priority"] = priority
        if owner_ids is not None:
            payload["owner_ids"] = owner_ids
        if depends_on is not None:
            payload["depends_on"] = depends_on
        if iteration_id is not None:
            payload["iteration_id"] = iteration_id
        if file_ids is not None:
            payload["file_ids"] = file_ids

        if not payload:
            return {}

        result = self.request("PUT", f"/stories/{story_id}", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def search_stories(
        self,
        query: str | None = None,
        epic_id: int | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search for stories."""
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if epic_id:
            params["epic_id"] = epic_id

        data = self.request("GET", "/stories", params=params)
        return data if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Tasks API
    # -------------------------------------------------------------------------

    def get_story_tasks(self, story_id: int) -> list[dict[str, Any]]:
        """Get all tasks for a story."""
        data = self.request("GET", f"/stories/{story_id}/tasks")
        return data if isinstance(data, list) else []

    def create_task(
        self,
        story_id: int,
        description: str,
        complete: bool = False,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        payload: dict[str, Any] = {
            "description": description,
            "complete": complete,
        }
        if owner_ids:
            payload["owner_ids"] = owner_ids

        result = self.request("POST", f"/stories/{story_id}/tasks", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def update_task(
        self,
        story_id: int,
        task_id: int,
        description: str | None = None,
        complete: bool | None = None,
        owner_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing task."""
        payload: dict[str, Any] = {}
        if description is not None:
            payload["description"] = description
        if complete is not None:
            payload["complete"] = complete
        if owner_ids is not None:
            payload["owner_ids"] = owner_ids

        if not payload:
            return {}

        result = self.request("PUT", f"/stories/{story_id}/tasks/{task_id}", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Workflow States API
    # -------------------------------------------------------------------------

    def get_workflow_states(self) -> list[dict[str, Any]]:
        """Get all workflow states."""
        data = self.request("GET", "/workflows")
        # Shortcut returns workflows, each with states
        workflows = data if isinstance(data, list) else []
        states = []
        for workflow in workflows:
            states.extend(workflow.get("states", []))
        return states

    def get_workflow_state_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a workflow state by name."""
        states = self.get_workflow_states()
        name_lower = name.lower()
        for state in states:
            if state.get("name", "").lower() == name_lower:
                return state
        return None

    # -------------------------------------------------------------------------
    # Dependencies API
    # -------------------------------------------------------------------------

    def get_story_dependencies(self, story_id: int) -> list[int]:
        """Get all story IDs that this story depends on."""
        story = self.get_story(story_id)
        depends_on = story.get("depends_on", [])
        if isinstance(depends_on, list):
            # Extract story IDs from dependency objects
            dep_ids = []
            for dep in depends_on:
                if not dep:
                    continue
                dep_id = dep.get("id") if isinstance(dep, dict) else dep
                if dep_id is not None:
                    dep_ids.append(int(dep_id))
            return dep_ids
        return []

    def add_story_dependency(
        self,
        story_id: int,
        depends_on_story_id: int,
    ) -> dict[str, Any]:
        """Add a dependency: story_id depends on depends_on_story_id."""
        story = self.get_story(story_id)
        current_deps = story.get("depends_on", [])

        # Convert to list of IDs if needed
        dep_ids = []
        for dep in current_deps:
            if not dep:
                continue
            dep_id = dep.get("id") if isinstance(dep, dict) else dep
            if dep_id is not None:
                dep_ids.append(int(dep_id))

        # Add new dependency if not already present
        if depends_on_story_id not in dep_ids:
            dep_ids.append(depends_on_story_id)

        # Update story with new dependencies
        return self.update_story(story_id, depends_on=dep_ids)

    def remove_story_dependency(
        self,
        story_id: int,
        depends_on_story_id: int,
    ) -> dict[str, Any]:
        """Remove a dependency: story_id no longer depends on depends_on_story_id."""
        story = self.get_story(story_id)
        current_deps = story.get("depends_on", [])

        # Convert to list of IDs if needed
        dep_ids = []
        for dep in current_deps:
            if not dep:
                continue
            dep_id = dep.get("id") if isinstance(dep, dict) else dep
            if dep_id is not None and dep_id != depends_on_story_id:
                dep_ids.append(int(dep_id))

        # Update story with remaining dependencies
        return self.update_story(story_id, depends_on=dep_ids)

    # -------------------------------------------------------------------------
    # Webhooks API
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a webhook subscription.

        Shortcut webhooks notify when changes occur in the workspace.
        Supported events include: story.create, story.update, story.delete,
        epic.create, epic.update, etc.

        Args:
            url: Webhook URL to receive events
            events: Optional list of event types to subscribe to (defaults to all)
            description: Optional description for the webhook

        Returns:
            Webhook subscription data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {"id": "webhook:dry-run", "url": url, "events": events or []}

        payload: dict[str, Any] = {"url": url}
        if events:
            payload["events"] = events
        if description:
            payload["description"] = description

        result = self.request("POST", "/webhooks", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Get a webhook by ID."""
        result = self.request("GET", f"/webhooks/{webhook_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List all webhooks for the workspace."""
        data = self.request("GET", "/webhooks")
        return data if isinstance(data, list) else []

    def update_webhook(
        self,
        webhook_id: str,
        url: str | None = None,
        events: list[str] | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Update a webhook subscription."""
        payload: dict[str, Any] = {}
        if url is not None:
            payload["url"] = url
        if events is not None:
            payload["events"] = events
        if description is not None:
            payload["description"] = description
        if enabled is not None:
            payload["enabled"] = enabled

        if not payload:
            return {}

        result = self.request("PUT", f"/webhooks/{webhook_id}", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook subscription."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        self.request("DELETE", f"/webhooks/{webhook_id}")
        return True

    # -------------------------------------------------------------------------
    # Iterations (Sprints) API
    # -------------------------------------------------------------------------

    def list_iterations(self) -> list[dict[str, Any]]:
        """List all iterations (sprints) for the workspace."""
        data = self.request("GET", "/iterations")
        return data if isinstance(data, list) else []

    def get_iteration(self, iteration_id: int) -> dict[str, Any]:
        """Get an iteration by ID."""
        result = self.request("GET", f"/iterations/{iteration_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def create_iteration(
        self,
        name: str,
        start_date: str,
        end_date: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new iteration (sprint).

        Args:
            name: Iteration name
            start_date: Start date (ISO 8601 format: YYYY-MM-DD)
            end_date: End date (ISO 8601 format: YYYY-MM-DD)
            description: Optional description

        Returns:
            Created iteration data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create iteration '{name}'")
            return {
                "id": 0,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            }

        payload: dict[str, Any] = {
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
        }
        if description:
            payload["description"] = description

        result = self.request("POST", "/iterations", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def update_iteration(
        self,
        iteration_id: int,
        name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an iteration."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if start_date is not None:
            payload["start_date"] = start_date
        if end_date is not None:
            payload["end_date"] = end_date
        if description is not None:
            payload["description"] = description

        if not payload:
            return self.get_iteration(iteration_id)

        result = self.request("PUT", f"/iterations/{iteration_id}", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    def delete_iteration(self, iteration_id: int) -> bool:
        """Delete an iteration."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete iteration {iteration_id}")
            return True

        self.request("DELETE", f"/iterations/{iteration_id}")
        return True

    def get_iteration_stories(self, iteration_id: int) -> list[dict[str, Any]]:
        """Get all stories assigned to an iteration."""
        data = self.request("GET", f"/iterations/{iteration_id}/stories")
        return data if isinstance(data, list) else []

    def assign_story_to_iteration(self, story_id: int, iteration_id: int) -> dict[str, Any]:
        """Assign a story to an iteration."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would assign story {story_id} to iteration {iteration_id}")
            return {"id": story_id, "iteration_id": iteration_id}

        # Update story with iteration_id
        return self.update_story(story_id, iteration_id=iteration_id)

    def remove_story_from_iteration(self, story_id: int) -> dict[str, Any]:
        """Remove a story from its iteration."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would remove story {story_id} from iteration")
            return {"id": story_id, "iteration_id": None}

        # Update story to remove iteration_id (set to None)
        return self.update_story(story_id, iteration_id=None)

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    def get_story_comments(self, story_id: int) -> list[dict[str, Any]]:
        """Get all comments on a story."""
        data = self.request("GET", f"/stories/{story_id}/comments")
        return data if isinstance(data, list) else []

    def create_comment(
        self,
        story_id: int,
        text: str,
        author_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a story."""
        payload: dict[str, Any] = {"text": text}
        if author_id:
            payload["author_id"] = author_id

        result = self.request("POST", f"/stories/{story_id}/comments", json=payload)
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Files/Attachments API
    # -------------------------------------------------------------------------

    def get_story_files(self, story_id: int) -> list[dict[str, Any]]:
        """
        Get all files attached to a story.

        Args:
            story_id: Story ID

        Returns:
            List of file dictionaries
        """
        story = self.get_story(story_id)
        files = story.get("files", [])
        return files if isinstance(files, list) else []

    def upload_file(
        self,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file to Shortcut.

        Args:
            file_path: Path to file to upload
            name: Optional file name (defaults to filename)

        Returns:
            File information dictionary with id, url, etc.

        Raises:
            NotFoundError: If file doesn't exist
            IssueTrackerError: On upload failure
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload file {file_path}")
            return {"id": "file:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        file_name = name or file_path_obj.name
        url = f"{self.api_url}/files"

        # Shortcut uses multipart form upload
        with open(file_path_obj, "rb") as f:
            files = {"file": (file_name, f)}

            # Remove Content-Type header for multipart upload
            headers = dict(self._session.headers)
            headers.pop("Content-Type", None)

            response = self._session.post(
                url,
                files=files,
                headers=headers,
                timeout=self.timeout,
            )

        if not response.ok:
            raise IssueTrackerError(
                f"Failed to upload file: {response.status_code} - {response.text[:500]}"
            )

        try:
            result = response.json()
            # Shortcut returns a list with one file
            if isinstance(result, list) and len(result) > 0:
                first = result[0]
                return (
                    dict(first) if isinstance(first, dict) else {"id": "unknown", "name": file_name}
                )
            return (
                dict(result) if isinstance(result, dict) else {"id": "unknown", "name": file_name}
            )
        except ValueError:
            return {"id": "unknown", "name": file_name}

    def link_file_to_story(
        self,
        story_id: int,
        file_id: int,
    ) -> dict[str, Any]:
        """
        Link an uploaded file to a story.

        Args:
            story_id: Story ID
            file_id: File ID to link

        Returns:
            Updated story data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would link file {file_id} to story {story_id}")
            return {"id": story_id}

        # Get current file IDs and add the new one
        story = self.get_story(story_id)
        current_files = story.get("file_ids", [])
        if file_id not in current_files:
            current_files.append(file_id)

        return self.update_story(story_id, file_ids=current_files)

    def unlink_file_from_story(
        self,
        story_id: int,
        file_id: int,
    ) -> dict[str, Any]:
        """
        Unlink a file from a story.

        Args:
            story_id: Story ID
            file_id: File ID to unlink

        Returns:
            Updated story data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would unlink file {file_id} from story {story_id}")
            return {"id": story_id}

        # Get current file IDs and remove the one
        story = self.get_story(story_id)
        current_files = story.get("file_ids", [])
        if file_id in current_files:
            current_files.remove(file_id)

        return self.update_story(story_id, file_ids=current_files)

    def delete_file(self, file_id: int) -> bool:
        """
        Delete a file from Shortcut.

        Args:
            file_id: File ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete file {file_id}")
            return True

        self.request("DELETE", f"/files/{file_id}")
        return True

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "ShortcutApiClient":
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

    @property
    def rate_limit_stats(self) -> dict[str, Any] | None:
        """Get rate limiter statistics."""
        if self._rate_limiter is None:
            return None
        return self._rate_limiter.stats
