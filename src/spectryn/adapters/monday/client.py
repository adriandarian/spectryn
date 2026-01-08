"""
Monday.com API Client - GraphQL client for Monday.com API.

This handles the raw HTTP/GraphQL communication with Monday.com.
The MondayAdapter uses this to implement the IssueTrackerPort.

Monday.com API Documentation: https://developer.monday.com/api-reference/docs
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    calculate_delay,
)
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
)


class MondayRateLimiter:
    """
    Rate limiter for Monday.com API.

    Monday.com rate limits: 500 requests per 10 seconds per API token.
    """

    def __init__(self, requests_per_10s: float = 500.0):
        """
        Initialize rate limiter.

        Args:
            requests_per_10s: Maximum requests per 10 seconds
        """
        self.requests_per_10s = requests_per_10s
        self.request_times: list[float] = []
        self.logger = logging.getLogger("MondayRateLimiter")

    def acquire(self) -> None:
        """Acquire permission to make a request."""
        now = time.time()

        # Remove requests older than 10 seconds
        self.request_times = [t for t in self.request_times if now - t < 10.0]

        # If we're at the limit, wait
        if len(self.request_times) >= self.requests_per_10s:
            oldest_request = min(self.request_times)
            wait_time = 10.0 - (now - oldest_request) + 0.1  # Add small buffer
            if wait_time > 0:
                self.logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                self.request_times = [t for t in self.request_times if now - t < 10.0]

        self.request_times.append(time.time())

    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter state from response headers."""
        # Monday.com doesn't expose rate limit headers in v2 API


class MondayApiClient:
    """
    Low-level Monday.com GraphQL API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - GraphQL API with automatic query building
    - API token authentication
    - Automatic retry with exponential backoff
    - Rate limiting with awareness of Monday.com's limits (500 req/10s)
    - Connection pooling
    """

    API_URL = "https://api.monday.com/v2"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Monday.com)
    DEFAULT_REQUESTS_PER_10S = 450.0  # Under 500 limit
    DEFAULT_BURST_SIZE = 50

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_token: str,
        api_url: str = API_URL,
        dry_run: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_delay: float = DEFAULT_INITIAL_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        jitter: float = DEFAULT_JITTER,
        requests_per_10s: float | None = DEFAULT_REQUESTS_PER_10S,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Monday.com client.

        Args:
            api_token: Monday.com API token (v2)
            api_url: Monday.com GraphQL API URL
            dry_run: If True, don't make write operations
            max_retries: Maximum retry attempts for transient failures
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            backoff_factor: Multiplier for exponential backoff
            jitter: Random jitter factor (0.1 = 10%)
            requests_per_10s: Maximum request rate per 10 seconds (None to disable)
            timeout: Request timeout in seconds
        """
        self.api_token = api_token
        self.api_url = api_url
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("MondayApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: MondayRateLimiter | None = None
        if requests_per_10s is not None and requests_per_10s > 0:
            self._rate_limiter = MondayRateLimiter(requests_per_10s=requests_per_10s)

        # Headers for Monday.com API
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": api_token,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)

        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._viewer: dict | None = None
        self._board_cache: dict[str, dict] = {}
        self._column_cache: dict[str, dict] = {}

    # -------------------------------------------------------------------------
    # Core GraphQL Methods
    # -------------------------------------------------------------------------

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL query/mutation.

        Args:
            query: GraphQL query or mutation
            variables: Query variables
            operation_name: Optional operation name

        Returns:
            GraphQL response data

        Raises:
            IssueTrackerError: On API errors
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                response = self._session.post(
                    self.api_url,
                    json=payload,
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
                        raise RateLimitError(
                            "Monday.com rate limit exceeded",
                            retry_after=int(delay),
                        )
                    raise TransientError(f"Monday.com server error {response.status_code}")

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

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query (read operation)."""
        return self.execute(query, variables)

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a GraphQL mutation (write operation).

        Respects dry_run mode.
        """
        if self.dry_run:
            self.logger.info("[DRY-RUN] Would execute mutation")
            return {}
        return self.execute(mutation, variables)

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        """Handle GraphQL response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Monday.com authentication failed. Check your API token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied")

        if not response.ok:
            raise IssueTrackerError(
                f"Monday.com API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            errors = data["errors"]
            error_messages = [e.get("message", str(e)) for e in errors]

            # Check for specific error types
            for error in errors:
                error_code = error.get("error_code", "")
                error_message = error.get("message", "").lower()

                if "authentication" in error_message or error_code == "AuthenticationError":
                    raise AuthenticationError(error_messages[0])
                if "permission" in error_message or error_code == "PermissionError":
                    raise PermissionError(error_messages[0])
                if "not found" in error_message or error_code == "NotFoundError":
                    raise NotFoundError(error_messages[0])

            raise IssueTrackerError(f"GraphQL errors: {'; '.join(error_messages)}")

        return data.get("data", {})

    # -------------------------------------------------------------------------
    # Viewer (Current User) API
    # -------------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Check if client is connected (has valid token)."""
        return bool(self.api_token)

    def test_connection(self) -> bool:
        """Test connection by fetching viewer info."""
        try:
            self.get_viewer()
            return True
        except (AuthenticationError, IssueTrackerError):
            return False

    def get_viewer(self) -> dict[str, Any]:
        """Get current authenticated user."""
        if self._viewer is None:
            query = """
            query {
                me {
                    id
                    name
                    email
                }
            }
            """
            data = self.query(query)
            self._viewer = data.get("me", {})
        return self._viewer

    # -------------------------------------------------------------------------
    # Board API
    # -------------------------------------------------------------------------

    def get_board(self, board_id: str) -> dict[str, Any]:
        """
        Get board information.

        Args:
            board_id: Board ID

        Returns:
            Board data with columns, groups, items
        """
        if board_id in self._board_cache:
            return self._board_cache[board_id]

        query = """
        query GetBoard($boardId: [ID!]!) {
            boards(ids: $boardId) {
                id
                name
                description
                workspace {
                    id
                    name
                }
                groups {
                    id
                    title
                }
                columns {
                    id
                    title
                    type
                    settings_str
                }
            }
        }
        """
        data = self.query(query, {"boardId": [board_id]})
        boards = data.get("boards", [])
        if not boards:
            raise NotFoundError(f"Board not found: {board_id}")

        board = boards[0]
        self._board_cache[board_id] = board
        return board

    def get_board_items(
        self,
        board_id: str,
        group_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get items (stories) from a board.

        Args:
            board_id: Board ID
            group_id: Optional group ID to filter by
            limit: Maximum items to return

        Returns:
            List of items
        """
        query = """
        query GetBoardItems($boardId: [ID!]!, $limit: Int) {
            boards(ids: $boardId) {
                items_page(limit: $limit) {
                    items {
                        id
                        name
                        group {
                            id
                            title
                        }
                        column_values {
                            id
                            type
                            text
                            value
                        }
                        subitems {
                            id
                            name
                        }
                        updates {
                            id
                            body
                            created_at
                            creator {
                                name
                                email
                            }
                        }
                    }
                }
            }
        }
        """
        variables: dict[str, Any] = {"boardId": [board_id], "limit": limit}
        data = self.query(query, variables)
        boards = data.get("boards", [])
        if not boards:
            return []

        items_page = boards[0].get("items_page", {})
        items = items_page.get("items", [])

        # Filter by group if specified
        if group_id:
            items = [item for item in items if item.get("group", {}).get("id") == group_id]

        return items

    def get_item(self, item_id: str) -> dict[str, Any]:
        """
        Get a single item by ID.

        Args:
            item_id: Item ID

        Returns:
            Item data
        """
        query = """
        query GetItem($itemId: [ID!]!) {
            items(ids: $itemId) {
                id
                name
                group {
                    id
                    title
                }
                board {
                    id
                    name
                }
                column_values {
                    id
                    type
                    text
                    value
                }
                subitems {
                    id
                    name
                }
                updates {
                    id
                    body
                    created_at
                    creator {
                        name
                        email
                    }
                }
            }
        }
        """
        data = self.query(query, {"itemId": [item_id]})
        items = data.get("items", [])
        if not items:
            raise NotFoundError(f"Item not found: {item_id}")
        return items[0]

    # -------------------------------------------------------------------------
    # Item Mutations
    # -------------------------------------------------------------------------

    def create_item(
        self,
        board_id: str,
        group_id: str,
        item_name: str,
        column_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new item (story) on a board.

        Args:
            board_id: Board ID
            group_id: Group ID (epic)
            item_name: Item name/title
            column_values: Optional column values dict (column_id -> value)

        Returns:
            Created item data
        """
        mutation = """
        mutation CreateItem($boardId: ID!, $groupId: String!, $itemName: String!, $columnValues: JSON) {
            create_item(
                board_id: $boardId,
                group_id: $groupId,
                item_name: $itemName,
                column_values: $columnValues
            ) {
                id
                name
            }
        }
        """
        variables: dict[str, Any] = {
            "boardId": board_id,
            "groupId": group_id,
            "itemName": item_name,
        }
        if column_values:
            import json

            variables["columnValues"] = json.dumps(column_values)

        data = self.mutate(mutation, variables)
        return data.get("create_item", {})

    def update_item(
        self,
        item_id: str,
        column_values: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an item.

        Args:
            item_id: Item ID
            column_values: Column values to update (column_id -> value)
            name: Optional new name

        Returns:
            Updated item data
        """
        mutation = """
        mutation UpdateItem($itemId: ID!, $columnValues: JSON, $name: String) {
            change_multiple_column_values(
                item_id: $itemId,
                column_values: $columnValues
            ) {
                id
            }
        }
        """
        variables: dict[str, Any] = {"itemId": item_id}
        if column_values:
            import json

            variables["columnValues"] = json.dumps(column_values)

        data = self.mutate(mutation, variables)

        # Update name separately if needed
        if name:
            name_mutation = """
            mutation UpdateItemName($itemId: ID!, $name: String!) {
                change_simple_column_value(
                    item_id: $itemId,
                    column_id: "name",
                    value: $name
                ) {
                    id
                }
            }
            """
            self.mutate(name_mutation, {"itemId": item_id, "name": name})

        return data.get("change_multiple_column_values", {})

    def create_subitem(
        self,
        parent_item_id: str,
        subitem_name: str,
        column_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a subitem (subtask).

        Args:
            parent_item_id: Parent item ID
            subitem_name: Subitem name
            column_values: Optional column values

        Returns:
            Created subitem data
        """
        mutation = """
        mutation CreateSubitem($parentItemId: ID!, $subitemName: String!, $columnValues: JSON) {
            create_subitem(
                parent_item_id: $parentItemId,
                item_name: $subitemName,
                column_values: $columnValues
            ) {
                id
                name
            }
        }
        """
        variables: dict[str, Any] = {
            "parentItemId": parent_item_id,
            "subitemName": subitem_name,
        }
        if column_values:
            import json

            variables["columnValues"] = json.dumps(column_values)

        data = self.mutate(mutation, variables)
        return data.get("create_subitem", {})

    def add_update(self, item_id: str, body: str) -> dict[str, Any]:
        """
        Add an update (comment) to an item.

        Args:
            item_id: Item ID
            body: Update/comment body

        Returns:
            Created update data
        """
        mutation = """
        mutation CreateUpdate($itemId: ID!, $body: String!) {
            create_update(
                item_id: $itemId,
                body: $body
            ) {
                id
                body
            }
        }
        """
        data = self.mutate(mutation, {"itemId": item_id, "body": body})
        return data.get("create_update", {})

    def upload_file(
        self,
        item_id: str,
        file_path: str,
        column_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file to an item.

        Monday.com file uploads require a multipart/form-data request.
        Files can be uploaded to file columns or as attachments.

        Args:
            item_id: Item ID
            file_path: Path to file to upload
            column_id: Optional file column ID (if None, uploads as attachment)

        Returns:
            Upload result with file information
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload file {file_path} to item {item_id}")
            return {"id": "file:dry-run"}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        # Monday.com file upload uses multipart/form-data
        # We need to use the file upload API endpoint
        upload_url = "https://api.monday.com/v2/file"

        data: dict[str, Any] = {"itemId": item_id}
        if column_id:
            data["columnId"] = column_id

        # Use context manager for file handling
        with open(file_path_obj, "rb") as file_handle:
            files = {"file": (file_path_obj.name, file_handle)}

            # File uploads use a different endpoint and format
            response = self._session.post(
                upload_url,
                files=files,
                data=data,
                headers={"Authorization": self.api_token},
                timeout=self.timeout,
            )

            if response.status_code == 401:
                raise AuthenticationError("Monday.com authentication failed. Check your API token.")

            if response.status_code == 403:
                raise PermissionError("Permission denied")

            if not response.ok:
                raise IssueTrackerError(
                    f"Monday.com file upload error {response.status_code}: {response.text[:500]}"
                )

            result = response.json()
            return result.get("data", {})

    def get_item_files(self, item_id: str) -> list[dict[str, Any]]:
        """
        Get all files attached to an item.

        Args:
            item_id: Item ID

        Returns:
            List of file information dictionaries
        """
        query = """
        query GetItemFiles($itemId: [ID!]!) {
            items(ids: $itemId) {
                assets {
                    id
                    name
                    url
                    file_extension
                    file_size
                    created_at
                }
            }
        }
        """
        data = self.query(query, {"itemId": [item_id]})
        items = data.get("items", [])
        if not items:
            return []
        return items[0].get("assets", [])

    def update_timeline_dates(
        self,
        item_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        timeline_column_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Update timeline/date columns for an item.

        Args:
            item_id: Item ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            timeline_column_id: Timeline column ID (for timeline view)

        Returns:
            Updated item data
        """
        column_values: dict[str, Any] = {}

        # Update timeline column if provided
        if timeline_column_id and start_date and end_date:
            import json

            timeline_value = json.dumps(
                {
                    "from": start_date,
                    "to": end_date,
                }
            )
            column_values[timeline_column_id] = timeline_value

        # Update individual date columns if provided
        if start_date or end_date:
            # Find date columns
            item = self.get_item(item_id)
            board = self.get_board(item.get("board", {}).get("id", ""))
            columns = board.get("columns", [])

            for col in columns:
                col_type = col.get("type", "")
                col_title = col.get("title", "").lower()

                if (
                    start_date
                    and col_type == "date"
                    and ("start" in col_title or "begin" in col_title)
                ):
                    column_values[col["id"]] = start_date

                if (
                    end_date
                    and col_type == "date"
                    and ("end" in col_title or "finish" in col_title or "due" in col_title)
                ):
                    column_values[col["id"]] = end_date

        if column_values:
            return self.update_item(item_id, column_values=column_values)

        return {}

    def get_timeline_dates(self, item_id: str) -> dict[str, str | None]:
        """
        Get timeline dates from an item.

        Args:
            item_id: Item ID

        Returns:
            Dictionary with 'start_date' and 'end_date' keys
        """
        item = self.get_item(item_id)
        board = self.get_board(item.get("board", {}).get("id", ""))
        columns = board.get("columns", [])

        start_date: str | None = None
        end_date: str | None = None

        # Check timeline column first
        timeline_col = None
        for col in columns:
            if col.get("type") == "timeline":
                timeline_col = col
                break

        if timeline_col:
            col_id = timeline_col["id"]
            for col_val in item.get("column_values", []):
                if col_val.get("id") == col_id:
                    import json

                    try:
                        timeline_data = json.loads(col_val.get("value", "{}"))
                        start_date = timeline_data.get("from")
                        end_date = timeline_data.get("to")
                    except (json.JSONDecodeError, TypeError):
                        pass
                    break

        # Fallback to individual date columns
        if not start_date or not end_date:
            for col in columns:
                col_type = col.get("type", "")
                col_title = col.get("title", "").lower()

                if col_type == "date":
                    col_id = col["id"]
                    for col_val in item.get("column_values", []):
                        if col_val.get("id") == col_id:
                            date_value = col_val.get("text", "")
                            if date_value:
                                if "start" in col_title or "begin" in col_title:
                                    start_date = date_value
                                elif (
                                    "end" in col_title
                                    or "finish" in col_title
                                    or "due" in col_title
                                ):
                                    end_date = date_value
                            break

        return {"start_date": start_date, "end_date": end_date}

    # -------------------------------------------------------------------------
    # Webhook Management
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        board_id: str,
        url: str,
        event: str = "change_column_value",
    ) -> dict[str, Any]:
        """
        Create a webhook subscription for a board.

        Monday.com webhooks notify when items on a board change.
        Supported events:
        - change_column_value: When a column value changes
        - create_item: When a new item is created
        - create_update: When an update/comment is created
        - change_status: When status changes
        - change_name: When item name changes
        - create_subitem: When a subitem is created

        Args:
            board_id: Board ID to subscribe to
            url: Webhook URL to receive events
            event: Event type to subscribe to (default: change_column_value)

        Returns:
            Webhook subscription data
        """
        mutation = """
        mutation CreateWebhook($boardId: ID!, $url: String!, $event: WebhookEventType!) {
            create_webhook(
                board_id: $boardId,
                url: $url,
                event: $event
            ) {
                id
                board_id
                url
                event
            }
        }
        """
        variables = {
            "boardId": board_id,
            "url": url,
            "event": event,
        }
        data = self.mutate(mutation, variables)
        return data.get("create_webhook", {})

    def list_webhooks(self, board_id: str | None = None) -> list[dict[str, Any]]:
        """
        List webhook subscriptions.

        Args:
            board_id: Optional board ID to filter by

        Returns:
            List of webhook subscriptions
        """
        query = """
        query ListWebhooks($boardId: ID) {
            webhooks(board_id: $boardId) {
                id
                board_id
                url
                event
                config
            }
        }
        """
        variables: dict[str, Any] = {}
        if board_id:
            variables["boardId"] = board_id

        data = self.query(query, variables)
        return data.get("webhooks", [])

    def delete_webhook(self, webhook_id: str) -> bool:
        """
        Delete a webhook subscription.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            True if successful
        """
        mutation = """
        mutation DeleteWebhook($webhookId: ID!) {
            delete_webhook(webhook_id: $webhookId) {
                id
            }
        }
        """
        data = self.mutate(mutation, {"webhookId": webhook_id})
        return bool(data.get("delete_webhook", {}))

    def verify_webhook(self, webhook_id: str) -> dict[str, Any]:
        """
        Verify a webhook subscription.

        Args:
            webhook_id: Webhook ID to verify

        Returns:
            Webhook verification data
        """
        query = """
        query GetWebhook($webhookId: ID!) {
            webhooks(ids: [$webhookId]) {
                id
                board_id
                url
                event
                config
            }
        }
        """
        data = self.query(query, {"webhookId": webhook_id})
        webhooks = data.get("webhooks", [])
        if not webhooks:
            raise NotFoundError(f"Webhook not found: {webhook_id}")
        return webhooks[0]

    def close(self) -> None:
        """Close the HTTP session."""
        if hasattr(self, "_session"):
            self._session.close()
