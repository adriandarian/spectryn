"""
Pivotal Tracker API Client - REST client for Pivotal Tracker API v5.

This handles the raw HTTP communication with Pivotal Tracker.
The PivotalAdapter uses this to implement the IssueTrackerPort.

Pivotal Tracker API Documentation: https://www.pivotaltracker.com/help/api/rest/v5
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
    get_retry_after,
)
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class PivotalRateLimiter:
    """
    Rate limiter for Pivotal Tracker API.

    Pivotal Tracker has a rate limit of 400 requests per 15 minutes (~0.44 req/sec).
    We'll be conservative and use 0.4 req/sec.
    """

    def __init__(
        self,
        requests_per_second: float = 0.4,  # ~24/min, under 400/15min limit
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

        self.logger = logging.getLogger("PivotalRateLimiter")

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
        """Update rate limiter based on Pivotal response headers."""
        with self._lock:
            # Check for Retry-After header
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                import contextlib

                with contextlib.suppress(ValueError):
                    self._retry_after = time.time() + float(retry_after)

            if response.status_code == 429:
                old_rate = self.requests_per_second
                self.requests_per_second = max(0.1, self.requests_per_second * 0.5)
                self.logger.warning(
                    f"Rate limited, reducing rate from "
                    f"{old_rate:.2f} to {self.requests_per_second:.2f} req/s"
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


class PivotalApiClient:
    """
    Low-level Pivotal Tracker REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - REST API v5 with automatic retry
    - API token authentication
    - Automatic retry with exponential backoff
    - Rate limiting aware of Pivotal's 400 req/15min limit
    - Connection pooling
    """

    BASE_URL = "https://www.pivotaltracker.com/services/v5"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Pivotal Tracker)
    DEFAULT_REQUESTS_PER_SECOND = 0.4  # ~24/min, under 400/15min limit
    DEFAULT_BURST_SIZE = 10

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_token: str,
        project_id: str,
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
        Initialize the Pivotal Tracker client.

        Args:
            api_token: Pivotal Tracker API token
            project_id: Pivotal Tracker project ID
            api_url: Pivotal Tracker API base URL
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
        self.project_id = project_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("PivotalApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: PivotalRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = PivotalRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for Pivotal Tracker API
        self.headers = {
            "Content-Type": "application/json",
            "X-TrackerToken": api_token,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

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
        Make an authenticated request to Pivotal Tracker API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., '/projects/:id/stories')
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
                            "Pivotal Tracker rate limit exceeded",
                            retry_after=int(delay),
                        )
                    raise TransientError(f"Pivotal Tracker server error {response.status_code}")

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
            raise AuthenticationError(
                "Pivotal Tracker authentication failed. Check your API token."
            )

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if response.status_code == 404:
            raise NotFoundError("Resource not found")

        if not response.ok:
            error_text = response.text[:500] if response.text else ""
            raise IssueTrackerError(
                f"Pivotal Tracker API error {response.status_code}: {error_text}"
            )

        # Handle empty responses (e.g., DELETE)
        if not response.text:
            return {}

        # Pivotal Tracker returns JSON
        try:
            json_data: dict[str, Any] | list[Any] = response.json()
            return json_data
        except ValueError as e:
            raise IssueTrackerError(f"Invalid JSON response: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Current User API
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._current_user is None:
            data = self.request("GET", "/me")
            if isinstance(data, dict):
                self._current_user = data
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
    # Projects API
    # -------------------------------------------------------------------------

    def get_project(self) -> dict[str, Any]:
        """Get the current project details."""
        result = self.request("GET", f"/projects/{self.project_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    # -------------------------------------------------------------------------
    # Epics API
    # -------------------------------------------------------------------------

    def get_epic(self, epic_id: int) -> dict[str, Any]:
        """Get an epic by ID."""
        result = self.request("GET", f"/projects/{self.project_id}/epics/{epic_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def list_epics(self) -> list[dict[str, Any]]:
        """List all epics in the project."""
        data = self.request("GET", f"/projects/{self.project_id}/epics")
        return data if isinstance(data, list) else []

    def get_epic_stories(self, epic_id: int) -> list[dict[str, Any]]:
        """Get all stories in an epic."""
        data = self.request(
            "GET",
            f"/projects/{self.project_id}/stories",
            params={"filter": f"epic:{epic_id}"},
        )
        return data if isinstance(data, list) else []

    def create_epic(
        self,
        name: str,
        description: str | None = None,
        label_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Create a new epic."""
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        if label_ids:
            payload["label_ids"] = label_ids

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/epics",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    def update_epic(
        self,
        epic_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing epic."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description

        if not payload:
            return {}

        result = self.request(
            "PUT",
            f"/projects/{self.project_id}/epics/{epic_id}",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Stories API
    # -------------------------------------------------------------------------

    def get_story(self, story_id: int) -> dict[str, Any]:
        """Get a story by ID."""
        result = self.request("GET", f"/projects/{self.project_id}/stories/{story_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def create_story(
        self,
        name: str,
        description: str | None = None,
        story_type: str = "feature",
        current_state: str | None = None,
        estimate: int | None = None,
        owner_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
        epic_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Create a new story.

        Args:
            name: Story title
            description: Story description
            story_type: One of: feature, bug, chore, release
            current_state: Story state (unscheduled, unstarted, started, finished, etc.)
            estimate: Story points estimate
            owner_ids: List of owner person IDs
            label_ids: List of label IDs
            epic_id: Epic ID to associate with

        Returns:
            Created story data
        """
        payload: dict[str, Any] = {
            "name": name,
            "story_type": story_type,
        }
        if description:
            payload["description"] = description
        if current_state:
            payload["current_state"] = current_state
        if estimate is not None:
            payload["estimate"] = estimate
        if owner_ids:
            payload["owner_ids"] = owner_ids
        if label_ids:
            payload["label_ids"] = label_ids

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/stories",
            json=payload,
        )
        story = result if isinstance(result, dict) else {}

        # Associate with epic if provided (via label)
        if epic_id and story.get("id"):
            self._add_story_to_epic(story["id"], epic_id)

        return story

    def _add_story_to_epic(self, story_id: int, epic_id: int) -> None:
        """Associate a story with an epic by getting the epic's label."""
        try:
            epic = self.get_epic(epic_id)
            label = epic.get("label", {})
            if label and label.get("id"):
                # Get current labels and add epic label
                story = self.get_story(story_id)
                current_labels = [lbl["id"] for lbl in story.get("labels", [])]
                if label["id"] not in current_labels:
                    current_labels.append(label["id"])
                    self.update_story(story_id, label_ids=current_labels)
        except (IssueTrackerError, KeyError):
            self.logger.warning(f"Could not associate story {story_id} with epic {epic_id}")

    def update_story(
        self,
        story_id: int,
        name: str | None = None,
        description: str | None = None,
        current_state: str | None = None,
        estimate: int | None = None,
        owner_ids: list[int] | None = None,
        label_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Update an existing story."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if current_state is not None:
            payload["current_state"] = current_state
        if estimate is not None:
            payload["estimate"] = estimate
        if owner_ids is not None:
            payload["owner_ids"] = owner_ids
        if label_ids is not None:
            payload["label_ids"] = label_ids

        if not payload:
            return {}

        result = self.request(
            "PUT",
            f"/projects/{self.project_id}/stories/{story_id}",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    def search_stories(
        self,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search for stories."""
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["filter"] = query

        data = self.request(
            "GET",
            f"/projects/{self.project_id}/stories",
            params=params,
        )
        return data if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Tasks API (Subtasks)
    # -------------------------------------------------------------------------

    def get_story_tasks(self, story_id: int) -> list[dict[str, Any]]:
        """Get all tasks for a story."""
        data = self.request(
            "GET",
            f"/projects/{self.project_id}/stories/{story_id}/tasks",
        )
        return data if isinstance(data, list) else []

    def create_task(
        self,
        story_id: int,
        description: str,
        complete: bool = False,
        position: int | None = None,
    ) -> dict[str, Any]:
        """Create a new task (subtask) within a story."""
        payload: dict[str, Any] = {
            "description": description,
            "complete": complete,
        }
        if position is not None:
            payload["position"] = position

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/stories/{story_id}/tasks",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    def update_task(
        self,
        story_id: int,
        task_id: int,
        description: str | None = None,
        complete: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing task."""
        payload: dict[str, Any] = {}
        if description is not None:
            payload["description"] = description
        if complete is not None:
            payload["complete"] = complete

        if not payload:
            return {}

        result = self.request(
            "PUT",
            f"/projects/{self.project_id}/stories/{story_id}/tasks/{task_id}",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    def delete_task(self, story_id: int, task_id: int) -> bool:
        """Delete a task."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete task {task_id} from story {story_id}")
            return True

        self.request(
            "DELETE",
            f"/projects/{self.project_id}/stories/{story_id}/tasks/{task_id}",
        )
        return True

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    def get_story_comments(self, story_id: int) -> list[dict[str, Any]]:
        """Get all comments on a story."""
        data = self.request(
            "GET",
            f"/projects/{self.project_id}/stories/{story_id}/comments",
        )
        return data if isinstance(data, list) else []

    def create_comment(
        self,
        story_id: int,
        text: str,
        person_id: int | None = None,
    ) -> dict[str, Any]:
        """Add a comment to a story."""
        payload: dict[str, Any] = {"text": text}
        if person_id:
            payload["person_id"] = person_id

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/stories/{story_id}/comments",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def list_labels(self) -> list[dict[str, Any]]:
        """List all labels in the project."""
        data = self.request("GET", f"/projects/{self.project_id}/labels")
        return data if isinstance(data, list) else []

    def create_label(self, name: str) -> dict[str, Any]:
        """Create a new label."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create label '{name}'")
            return {"id": 0, "name": name}

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/labels",
            json={"name": name},
        )
        if isinstance(result, dict):
            return result
        return {}

    def get_or_create_label(self, name: str) -> dict[str, Any]:
        """Get a label by name, creating it if it doesn't exist."""
        labels = self.list_labels()
        for label in labels:
            if label.get("name", "").lower() == name.lower():
                return label
        return self.create_label(name)

    # -------------------------------------------------------------------------
    # Iterations (Sprints) API
    # -------------------------------------------------------------------------

    def list_iterations(
        self,
        scope: str = "current",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        List iterations for the project.

        Args:
            scope: One of: done, current, backlog, current_backlog
            limit: Maximum iterations to return
        """
        data = self.request(
            "GET",
            f"/projects/{self.project_id}/iterations",
            params={"scope": scope, "limit": limit},
        )
        return data if isinstance(data, list) else []

    def get_iteration(self, iteration_number: int) -> dict[str, Any]:
        """Get an iteration by number."""
        result = self.request(
            "GET",
            f"/projects/{self.project_id}/iterations/{iteration_number}",
        )
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    # -------------------------------------------------------------------------
    # Webhooks API
    # -------------------------------------------------------------------------

    def list_webhooks(self) -> list[dict[str, Any]]:
        """List webhooks for the project."""
        data = self.request("GET", f"/projects/{self.project_id}/webhooks")
        return data if isinstance(data, list) else []

    def create_webhook(
        self,
        url: str,
        webhook_version: str = "v5",
    ) -> dict[str, Any]:
        """Create a webhook for the project."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {"id": 0, "url": url}

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/webhooks",
            json={"webhook_url": url, "webhook_version": webhook_version},
        )
        if isinstance(result, dict):
            return result
        return {}

    def delete_webhook(self, webhook_id: int) -> bool:
        """Delete a webhook."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        self.request(
            "DELETE",
            f"/projects/{self.project_id}/webhooks/{webhook_id}",
        )
        return True

    # -------------------------------------------------------------------------
    # File Attachments API
    # -------------------------------------------------------------------------

    def get_story_attachments(self, story_id: int) -> list[dict[str, Any]]:
        """Get file attachments for a story (via comments with attachments)."""
        comments = self.get_story_comments(story_id)
        attachments = []
        for comment in comments:
            for attachment in comment.get("file_attachments", []):
                attachments.append(attachment)
        return attachments

    def upload_file(
        self,
        file_path: str,
    ) -> dict[str, Any]:
        """
        Upload a file to Pivotal Tracker.

        Args:
            file_path: Path to file to upload

        Returns:
            File information dictionary with id, filename, etc.
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload file {file_path}")
            return {"id": "file:dry-run", "filename": file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        url = f"{self.api_url}/projects/{self.project_id}/uploads"

        # Pivotal Tracker uses multipart form upload
        with open(file_path_obj, "rb") as f:
            files = {"file": (file_path_obj.name, f)}

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
            return dict(result) if isinstance(result, dict) else {"id": "unknown"}
        except ValueError:
            return {"id": "unknown"}

    def add_attachment_to_comment(
        self,
        story_id: int,
        file_attachment_ids: list[int],
        text: str = "",
    ) -> dict[str, Any]:
        """Add file attachments to a story via a comment."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would attach files to story {story_id}")
            return {"id": 0}

        result = self.request(
            "POST",
            f"/projects/{self.project_id}/stories/{story_id}/comments",
            json={"text": text, "file_attachment_ids": file_attachment_ids},
        )
        if isinstance(result, dict):
            return result
        return {}

    # -------------------------------------------------------------------------
    # Activity API
    # -------------------------------------------------------------------------

    def get_project_activity(
        self,
        limit: int = 25,
        since_version: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get activity feed for the project."""
        params: dict[str, Any] = {"limit": limit}
        if since_version:
            params["since_version"] = since_version

        data = self.request(
            "GET",
            f"/projects/{self.project_id}/activity",
            params=params,
        )
        return data if isinstance(data, list) else []

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "PivotalApiClient":
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
