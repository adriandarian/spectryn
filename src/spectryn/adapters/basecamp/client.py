"""
Basecamp API Client - REST client for Basecamp 3 API.

This handles the raw HTTP communication with Basecamp 3.
The BasecampAdapter uses this to implement the IssueTrackerPort.

Basecamp 3 API Documentation: https://github.com/basecamp/bc3-api
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


class BasecampRateLimiter:
    """
    Rate limiter for Basecamp API.

    Basecamp has a rate limit of 40 requests per 10 seconds.
    """

    def __init__(
        self,
        requests_per_second: float = 3.5,  # ~35/10s, under 40/10s limit
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

        self.logger = logging.getLogger("BasecampRateLimiter")

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
        """Update rate limiter based on Basecamp response headers."""
        with self._lock:
            # Check for Retry-After header
            retry_after = get_retry_after(response)
            if retry_after is not None:
                self._retry_after = time.time() + retry_after

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


class BasecampApiClient:
    """
    Low-level Basecamp 3 REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - REST API with automatic retry
    - OAuth 2.0 Bearer token authentication
    - Automatic retry with exponential backoff
    - Rate limiting aware of Basecamp's 40 req/10s limit
    - Connection pooling
    """

    BASE_URL = "https://3.basecampapi.com"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Basecamp)
    DEFAULT_REQUESTS_PER_SECOND = 3.5  # ~35/10s, under 40/10s limit
    DEFAULT_BURST_SIZE = 10

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        access_token: str,
        account_id: str,
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
        Initialize the Basecamp client.

        Args:
            access_token: OAuth 2.0 access token
            account_id: Basecamp account ID
            project_id: Basecamp project ID
            api_url: Basecamp API base URL
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
        self.access_token = access_token
        self.account_id = account_id
        self.project_id = project_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("BasecampApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: BasecampRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = BasecampRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Headers for Basecamp API
        # Basecamp requires User-Agent header
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Spectra/1.0 (https://github.com/spectra)",
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._current_user: dict | None = None
        self._project_cache: dict | None = None
        self._todolists_cache: dict[str, dict] = {}  # todolist_id -> todolist data

    # -------------------------------------------------------------------------
    # Core HTTP Methods
    # -------------------------------------------------------------------------

    def _build_url(self, path: str) -> str:
        """Build full URL for API endpoint."""
        # Basecamp API format: /{account_id}/projects/{project_id}/...
        if path.startswith("/"):
            path = path[1:]
        if not path.startswith(f"{self.account_id}/"):
            path = f"{self.account_id}/{path}"
        return f"{self.api_url}/{path}"

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: str | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (relative to account)
            params: Query parameters
            json: JSON body
            data: Raw body data

        Returns:
            Response JSON data

        Raises:
            IssueTrackerError: On API errors
        """
        url = self._build_url(path)
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    data=data,
                    timeout=self.timeout,
                )

                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    delay = calculate_delay(
                        attempt,
                        initial_delay=self.initial_delay,
                        max_delay=self.max_delay,
                        backoff_factor=self.backoff_factor,
                        jitter=self.jitter,
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
                        retry_after = get_retry_after(response) or delay
                        raise RateLimitError(
                            "Basecamp rate limit exceeded",
                            retry_after=int(retry_after),
                        )
                    raise TransientError(f"Basecamp server error {response.status_code}")

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

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        """Handle HTTP response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Basecamp authentication failed. Check your access token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if response.status_code == 404:
            raise NotFoundError(f"Resource not found: {response.url}")

        if not response.ok:
            error_text = response.text[:500]
            raise IssueTrackerError(f"Basecamp API error {response.status_code}: {error_text}")

        # Basecamp returns empty body for some operations (e.g., DELETE)
        if not response.text:
            return {}

        try:
            data: dict[str, Any] = response.json()
            return data
        except ValueError:
            return {}

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request."""
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: str | None = None,
    ) -> dict[str, Any]:
        """Make a POST request."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would POST to {path}")
            return {}
        return self._request("POST", path, json=json, data=data)

    def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: str | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would PUT to {path}")
            return {}
        return self._request("PUT", path, json=json, data=data)

    def delete(self, path: str) -> dict[str, Any]:
        """Make a DELETE request."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would DELETE {path}")
            return {}
        return self._request("DELETE", path)

    # -------------------------------------------------------------------------
    # Current User API
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._current_user is None:
            # Basecamp uses /people/me.json for current user
            self._current_user = self.get("people/me.json")
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
        """Get the configured project."""
        if self._project_cache is None:
            self._project_cache = self.get(f"projects/{self.project_id}.json")
        return self._project_cache

    # -------------------------------------------------------------------------
    # Todo Lists API
    # -------------------------------------------------------------------------

    def get_todolists(self) -> list[dict[str, Any]]:
        """Get all todo lists in the project."""
        path = f"projects/{self.project_id}/todosets.json"
        response = self.get(path)
        # Basecamp returns a list directly
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        # Or wrapped in a key
        todosets = response.get("todosets", [])
        if isinstance(todosets, list):
            return todosets  # type: ignore[return-value]
        return []

    def get_todolist(self, todolist_id: str) -> dict[str, Any]:
        """Get a specific todo list."""
        if todolist_id in self._todolists_cache:
            return self._todolists_cache[todolist_id]

        path = f"projects/{self.project_id}/todosets/{todolist_id}.json"
        todolist = self.get(path)
        self._todolists_cache[todolist_id] = todolist
        return todolist

    def get_todos(self, todolist_id: str) -> list[dict[str, Any]]:
        """Get all todos in a todo list."""
        path = f"projects/{self.project_id}/todosets/{todolist_id}/todos.json"
        response = self.get(path)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        todos = response.get("todos", [])
        if isinstance(todos, list):
            return todos  # type: ignore[return-value]
        return []

    def get_todo(self, todo_id: str) -> dict[str, Any]:
        """Get a specific todo."""
        path = f"projects/{self.project_id}/todos/{todo_id}.json"
        return self.get(path)

    def create_todo(
        self,
        todolist_id: str,
        content: str,
        notes: str | None = None,
        assignee_ids: list[int] | None = None,
        due_on: str | None = None,
    ) -> dict[str, Any]:
        """Create a new todo."""
        path = f"projects/{self.project_id}/todosets/{todolist_id}/todos.json"
        payload: dict[str, Any] = {"content": content}
        if notes:
            payload["notes"] = notes
        if assignee_ids:
            payload["assignee_ids"] = assignee_ids
        if due_on:
            payload["due_on"] = due_on
        return self.post(path, json=payload)

    def update_todo(
        self,
        todo_id: str,
        content: str | None = None,
        notes: str | None = None,
        completed: bool | None = None,
        assignee_ids: list[int] | None = None,
        due_on: str | None = None,
    ) -> dict[str, Any]:
        """Update a todo."""
        path = f"projects/{self.project_id}/todos/{todo_id}.json"
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if notes is not None:
            payload["notes"] = notes
        if completed is not None:
            payload["completed"] = completed
        if assignee_ids is not None:
            payload["assignee_ids"] = assignee_ids
        if due_on is not None:
            payload["due_on"] = due_on
        return self.put(path, json=payload)

    def complete_todo(self, todo_id: str) -> dict[str, Any]:
        """Mark a todo as completed."""
        return self.update_todo(todo_id, completed=True)

    def uncomplete_todo(self, todo_id: str) -> dict[str, Any]:
        """Mark a todo as not completed."""
        return self.update_todo(todo_id, completed=False)

    # -------------------------------------------------------------------------
    # Messages API
    # -------------------------------------------------------------------------

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all messages in the project."""
        path = f"projects/{self.project_id}/messages.json"
        response = self.get(path)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        messages = response.get("messages", [])
        if isinstance(messages, list):
            return messages  # type: ignore[return-value]
        return []

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Get a specific message."""
        path = f"projects/{self.project_id}/messages/{message_id}.json"
        return self.get(path)

    def create_message(
        self,
        subject: str,
        content: str,
        category_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new message."""
        path = f"projects/{self.project_id}/messages.json"
        payload: dict[str, Any] = {
            "subject": subject,
            "content": content,
        }
        if category_id is not None:
            payload["category_id"] = category_id
        return self.post(path, json=payload)

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    def get_comments(self, recording_id: str, recording_type: str) -> list[dict[str, Any]]:
        """
        Get comments for a recording (todo or message).

        Args:
            recording_id: ID of the recording
            recording_type: Type of recording ('Todo' or 'Message')
        """
        path = f"projects/{self.project_id}/recordings/{recording_id}/comments.json"
        params = {"type": recording_type}
        response = self.get(path, params=params)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        comments = response.get("comments", [])
        if isinstance(comments, list):
            return comments  # type: ignore[return-value]
        return []

    def create_comment(
        self,
        recording_id: str,
        recording_type: str,
        content: str,
    ) -> dict[str, Any]:
        """Create a comment on a recording."""
        path = f"projects/{self.project_id}/recordings/{recording_id}/comments.json"
        payload = {
            "content": content,
            "type": recording_type,
        }
        return self.post(path, json=payload)

    # -------------------------------------------------------------------------
    # Campfire (Chat) API
    # -------------------------------------------------------------------------

    def get_campfires(self) -> list[dict[str, Any]]:
        """
        Get all Campfire chats for the project.

        Returns:
            List of Campfire chat data
        """
        path = f"projects/{self.project_id}/chats.json"
        response = self.get(path)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        chats = response.get("chats", [])
        if isinstance(chats, list):
            return chats  # type: ignore[return-value]
        return []

    def get_campfire(self, chat_id: str) -> dict[str, Any]:
        """
        Get a specific Campfire chat.

        Args:
            chat_id: Campfire chat ID

        Returns:
            Campfire chat data
        """
        path = f"projects/{self.project_id}/chats/{chat_id}.json"
        return self.get(path)

    def get_campfire_lines(
        self,
        chat_id: str,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get chat messages (lines) from a Campfire.

        Args:
            chat_id: Campfire chat ID
            since: Optional ISO 8601 timestamp to get messages since
            limit: Optional maximum number of messages to return

        Returns:
            List of chat message (line) data
        """
        path = f"projects/{self.project_id}/chats/{chat_id}/lines.json"
        params: dict[str, Any] = {}
        if since:
            params["since"] = since
        if limit:
            params["limit"] = limit

        response = self.get(path, params=params if params else None)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        lines = response.get("lines", [])
        if isinstance(lines, list):
            return lines  # type: ignore[return-value]
        return []

    def send_campfire_message(
        self,
        chat_id: str,
        content: str,
    ) -> dict[str, Any]:
        """
        Send a message to a Campfire chat.

        Args:
            chat_id: Campfire chat ID
            content: Message content

        Returns:
            Created message (line) data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would send message to Campfire {chat_id}")
            return {
                "id": "line:dry-run",
                "content": content,
                "chat_id": chat_id,
            }

        path = f"projects/{self.project_id}/chats/{chat_id}/lines.json"
        payload = {"content": content}
        return self.post(path, json=payload)

    def create_campfire(
        self,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new Campfire chat in the project.

        Args:
            name: Optional name for the Campfire (defaults to "Campfire")

        Returns:
            Created Campfire chat data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create Campfire '{name or 'Campfire'}'")
            return {
                "id": "chat:dry-run",
                "name": name or "Campfire",
                "project_id": self.project_id,
            }

        path = f"projects/{self.project_id}/chats.json"
        payload: dict[str, Any] = {}
        if name:
            payload["name"] = name
        return self.post(path, json=payload)

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
        Create a webhook subscription for the project.

        Basecamp webhooks notify when changes occur in the project.
        Supported events include:
        - todo.created, todo.updated, todo.completed, todo.uncompleted
        - message.created, message.updated
        - comment.created, comment.updated
        - todo_list.created, todo_list.updated

        Args:
            url: Webhook URL to receive events (must be HTTPS)
            events: Optional list of event types to subscribe to (defaults to all)
            description: Optional description for the webhook

        Returns:
            Webhook subscription data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for URL {url}")
            return {
                "id": "webhook:dry-run",
                "url": url,
                "events": events or [],
                "project_id": self.project_id,
            }

        path = f"projects/{self.project_id}/webhooks.json"
        payload: dict[str, Any] = {"url": url}
        if events:
            payload["events"] = events
        if description:
            payload["description"] = description

        return self.post(path, json=payload)

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Get a webhook by ID.

        Args:
            webhook_id: Webhook ID to retrieve

        Returns:
            Webhook data
        """
        path = f"projects/{self.project_id}/webhooks/{webhook_id}.json"
        return self.get(path)

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List all webhooks for the project.

        Returns:
            List of webhook subscriptions
        """
        path = f"projects/{self.project_id}/webhooks.json"
        response = self.get(path)
        if isinstance(response, list):
            return response  # type: ignore[return-value]
        webhooks = response.get("webhooks", [])
        if isinstance(webhooks, list):
            return webhooks  # type: ignore[return-value]
        return []

    def update_webhook(
        self,
        webhook_id: str,
        url: str | None = None,
        events: list[str] | None = None,
        description: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a webhook subscription.

        Args:
            webhook_id: Webhook ID to update
            url: Optional new webhook URL
            events: Optional new list of event types
            description: Optional new description
            enabled: Optional enable/disable flag

        Returns:
            Updated webhook data
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        path = f"projects/{self.project_id}/webhooks/{webhook_id}.json"
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
            return self.get_webhook(webhook_id)

        return self.put(path, json=payload)

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            True if successful
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        path = f"projects/{self.project_id}/webhooks/{webhook_id}.json"
        self.delete(path)
        return True

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "BasecampApiClient":
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
