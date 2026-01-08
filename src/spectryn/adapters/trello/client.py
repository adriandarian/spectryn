"""
Trello API Client - REST API client for Trello.

This handles the raw HTTP communication with Trello.
The TrelloAdapter uses this to implement the IssueTrackerPort.

Trello API Documentation: https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/
Rate Limits: 300 requests per 10 seconds per API key
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from spectryn.adapters.async_base import (
    RETRYABLE_STATUS_CODES,
    TokenBucketRateLimiter,
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


class TrelloRateLimiter(TokenBucketRateLimiter):
    """
    Trello-specific rate limiter.

    Trello allows 300 requests per 10 seconds per API key.
    This implementation uses conservative defaults (25 req/s) to avoid hitting limits.
    """

    def __init__(
        self,
        requests_per_second: float = 25.0,  # Conservative: 25 req/s = 250/10s, under 300 limit
        burst_size: int = 50,
    ):
        """
        Initialize the Trello rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate.
                Default 25.0 (250/10s) is conservative for Trello's 300/10s limit.
            burst_size: Maximum burst capacity.
        """
        super().__init__(
            requests_per_second=requests_per_second,
            burst_size=burst_size,
            logger_name="TrelloRateLimiter",
        )


class TrelloApiClient:
    """
    Low-level Trello REST API client.

    Handles authentication, request/response, rate limiting, and error handling.

    Features:
    - OAuth 1.0 authentication (API key + token)
    - Automatic retry with exponential backoff
    - Rate limiting with awareness of Trello's limits (300/10s)
    - Connection pooling
    """

    BASE_URL = "https://api.trello.com/1"

    # Default retry configuration
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_INITIAL_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0
    DEFAULT_BACKOFF_FACTOR = 2.0
    DEFAULT_JITTER = 0.1

    # Default rate limiting (conservative for Trello: 300 requests per 10 seconds)
    DEFAULT_REQUESTS_PER_SECOND = 25.0  # 250/10s, under 300 limit
    DEFAULT_BURST_SIZE = 50

    # Connection pool settings
    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_key: str,
        api_token: str,
        board_id: str,
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
        Initialize the Trello client.

        Args:
            api_key: Trello API key
            api_token: Trello API token
            board_id: Board ID to operate on
            api_url: Trello API base URL
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
        self.api_key = api_key
        self.api_token = api_token
        self.board_id = board_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.logger = logging.getLogger("TrelloApiClient")

        # Retry configuration
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        # Rate limiting
        self._rate_limiter: TrelloRateLimiter | None = None
        if requests_per_second is not None and requests_per_second > 0:
            self._rate_limiter = TrelloRateLimiter(
                requests_per_second=requests_per_second,
                burst_size=burst_size,
            )

        # Authentication parameters (Trello uses query params for OAuth 1.0)
        self.auth_params = {
            "key": api_key,
            "token": api_token,
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._current_user: dict | None = None
        self._board_cache: dict | None = None
        self._lists_cache: dict[str, dict] = {}  # list_id -> list data
        self._labels_cache: dict[str, dict] = {}  # label_id -> label data

    # -------------------------------------------------------------------------
    # Core Request Methods
    # -------------------------------------------------------------------------

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """
        Make an authenticated request to Trello API with rate limiting and retry.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., 'boards/{board_id}')
            params: Query parameters (auth params added automatically)
            json: JSON body for POST/PUT requests
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

        # Merge auth params with provided params
        request_params = {**self.auth_params}
        if params:
            request_params.update(params)

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            # Apply rate limiting
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()

            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(
                    method, url, params=request_params, json=json, **kwargs
                )

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
                            f"Retryable error {response.status_code} on {method} {endpoint}, "
                            f"attempt {attempt + 1}/{self.max_retries + 1}, "
                            f"retrying in {delay:.2f}s"
                        )
                        time.sleep(delay)
                        continue

                    if response.status_code == 429:
                        raise RateLimitError(
                            f"Trello rate limit exceeded for {endpoint}",
                            retry_after=retry_after,
                        )
                    raise TransientError(
                        f"Trello server error {response.status_code} for {endpoint}"
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

    def _handle_response(
        self, response: requests.Response, endpoint: str
    ) -> dict[str, Any] | list[Any]:
        """Handle Trello API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Trello authentication failed. Check your API key and token.")

        if response.status_code == 403:
            raise PermissionError("Permission denied to access Trello resource")

        if response.status_code == 404:
            raise NotFoundError(f"Trello resource not found: {endpoint}")

        if not response.ok:
            error_text = response.text[:500]
            raise IssueTrackerError(
                f"Trello API error {response.status_code} for {endpoint}: {error_text}"
            )

        # Trello returns JSON
        try:
            json_data: dict[str, Any] | list[Any] = response.json()
            return json_data
        except ValueError as e:
            raise IssueTrackerError(f"Invalid JSON response from Trello: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Current User API
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._current_user is None:
            result = self.request("GET", "members/me")
            assert isinstance(result, dict)
            self._current_user = result
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
    # Boards API
    # -------------------------------------------------------------------------

    def get_board(self) -> dict[str, Any]:
        """Get the configured board."""
        if self._board_cache is None:
            result = self.request("GET", f"boards/{self.board_id}")
            assert isinstance(result, dict)
            self._board_cache = result
        return self._board_cache

    def get_board_lists(self, filter: str = "open") -> list[dict[str, Any]]:
        """
        Get all lists on the board.

        Args:
            filter: Filter lists by status ('open', 'closed', 'all')
        """
        cache_key = filter
        if cache_key not in self._lists_cache:
            result = self.request("GET", f"boards/{self.board_id}/lists", params={"filter": filter})
            assert isinstance(result, list)
            lists = result
            self._lists_cache[cache_key] = {list_data["id"]: list_data for list_data in lists}
        return list(self._lists_cache[cache_key].values())

    def get_list_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a list by name (case-insensitive)."""
        lists = self.get_board_lists()
        name_lower = name.lower()
        for list_data in lists:
            if list_data.get("name", "").lower() == name_lower:
                return list_data
        return None

    def create_list(self, name: str, pos: str | int = "bottom") -> dict[str, Any]:
        """Create a new list on the board."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create list '{name}'")
            return {"id": "dry-run-list-id", "name": name}

        result = self.request(
            "POST",
            f"boards/{self.board_id}/lists",
            json={"name": name, "pos": pos},
        )
        assert isinstance(result, dict)
        # Invalidate cache
        self._lists_cache.clear()
        return result

    # -------------------------------------------------------------------------
    # Cards API
    # -------------------------------------------------------------------------

    def get_card(self, card_id: str) -> dict[str, Any]:
        """Get a card by ID."""
        result = self.request("GET", f"cards/{card_id}")
        assert isinstance(result, dict)
        return result

    def get_board_cards(self, filter: str = "open") -> list[dict[str, Any]]:
        """
        Get all cards on the board.

        Args:
            filter: Filter cards ('open', 'closed', 'all', 'visible')
        """
        result = self.request("GET", f"boards/{self.board_id}/cards", params={"filter": filter})
        assert isinstance(result, list)
        return result

    def get_list_cards(self, list_id: str) -> list[dict[str, Any]]:
        """Get all cards in a list."""
        result = self.request("GET", f"lists/{list_id}/cards")
        assert isinstance(result, list)
        return result

    def create_card(
        self,
        name: str,
        list_id: str,
        desc: str | None = None,
        pos: str | int = "bottom",
        due: str | None = None,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new card."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create card '{name}' in list {list_id}")
            return {"id": "dry-run-card-id", "name": name, "idList": list_id}

        json_data: dict[str, Any] = {
            "name": name,
            "idList": list_id,
            "pos": pos,
        }
        if desc:
            json_data["desc"] = desc
        if due:
            json_data["due"] = due
        if label_ids:
            json_data["idLabels"] = label_ids

        result = self.request("POST", "cards", json=json_data)
        assert isinstance(result, dict)
        return result

    def update_card(
        self,
        card_id: str,
        name: str | None = None,
        desc: str | None = None,
        idList: str | None = None,  # noqa: N803
        pos: str | int | None = None,
        due: str | None = None,
        closed: bool | None = None,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing card."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update card {card_id}")
            return {"id": card_id}

        json_data: dict[str, Any] = {}
        if name is not None:
            json_data["name"] = name
        if desc is not None:
            json_data["desc"] = desc
        if idList is not None:
            json_data["idList"] = idList
        if pos is not None:
            json_data["pos"] = pos
        if due is not None:
            json_data["due"] = due
        if closed is not None:
            json_data["closed"] = closed
        if label_ids is not None:
            json_data["idLabels"] = label_ids

        if not json_data:
            return self.get_card(card_id)

        result = self.request("PUT", f"cards/{card_id}", json=json_data)
        assert isinstance(result, dict)
        return result

    def move_card_to_list(self, card_id: str, list_id: str) -> dict[str, Any]:
        """Move a card to a different list."""
        return self.update_card(card_id, idList=list_id)

    # -------------------------------------------------------------------------
    # Checklists API
    # -------------------------------------------------------------------------

    def get_card_checklists(self, card_id: str) -> list[dict[str, Any]]:
        """Get all checklists on a card."""
        result = self.request("GET", f"cards/{card_id}/checklists")
        assert isinstance(result, list)
        return result

    def create_checklist(self, card_id: str, name: str) -> dict[str, Any]:
        """Create a checklist on a card."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create checklist '{name}' on card {card_id}")
            return {"id": "dry-run-checklist-id", "name": name}

        result = self.request("POST", f"cards/{card_id}/checklists", json={"name": name})
        assert isinstance(result, dict)
        return result

    def add_checklist_item(
        self, checklist_id: str, name: str, checked: bool = False
    ) -> dict[str, Any]:
        """Add an item to a checklist."""
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would add checklist item '{name}' to checklist {checklist_id}"
            )
            return {
                "id": "dry-run-item-id",
                "name": name,
                "state": "complete" if checked else "incomplete",
            }

        result = self.request(
            "POST",
            f"checklists/{checklist_id}/checkItems",
            json={"name": name, "checked": checked},
        )
        assert isinstance(result, dict)
        return result

    # -------------------------------------------------------------------------
    # Labels API
    # -------------------------------------------------------------------------

    def get_board_labels(self) -> list[dict[str, Any]]:
        """Get all labels on the board."""
        if not self._labels_cache:
            result = self.request("GET", f"boards/{self.board_id}/labels")
            assert isinstance(result, list)
            labels = result
            self._labels_cache = {label["id"]: label for label in labels}
        return list(self._labels_cache.values())

    def get_label_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a label by name (case-insensitive)."""
        labels = self.get_board_labels()
        name_lower = name.lower()
        for label in labels:
            if label.get("name", "").lower() == name_lower:
                return label
        return None

    def get_label_by_color(self, color: str) -> dict[str, Any] | None:
        """Get a label by color."""
        labels = self.get_board_labels()
        color_lower = color.lower()
        for label in labels:
            if label.get("color", "").lower() == color_lower:
                return label
        return None

    def create_label(self, name: str | None = None, color: str | None = None) -> dict[str, Any]:
        """Create a label on the board."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create label '{name or color}'")
            return {"id": "dry-run-label-id", "name": name, "color": color}

        json_data: dict[str, Any] = {}
        if name:
            json_data["name"] = name
        if color:
            json_data["color"] = color

        result = self.request("POST", f"boards/{self.board_id}/labels", json=json_data)
        assert isinstance(result, dict)
        # Invalidate cache
        self._labels_cache.clear()
        return result

    # -------------------------------------------------------------------------
    # Comments API
    # -------------------------------------------------------------------------

    def get_card_comments(self, card_id: str) -> list[dict[str, Any]]:
        """Get all comments (actions) on a card."""
        result = self.request("GET", f"cards/{card_id}/actions", params={"filter": "commentCard"})
        assert isinstance(result, list)
        actions = result
        return [
            {
                "id": action["id"],
                "text": action["data"].get("text", ""),
                "author": action["memberCreator"].get("fullName", ""),
                "created": action["date"],
            }
            for action in actions
        ]

    def add_comment(self, card_id: str, text: str) -> dict[str, Any]:
        """Add a comment to a card."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to card {card_id}")
            return {"id": "dry-run-comment-id", "text": text}

        result = self.request("POST", f"cards/{card_id}/actions/comments", json={"text": text})
        assert isinstance(result, dict)
        return result

    # -------------------------------------------------------------------------
    # Webhooks API
    # -------------------------------------------------------------------------

    def create_webhook(
        self,
        model_id: str,
        callback_url: str,
        description: str | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        """
        Create a webhook for a board, card, or list.

        Trello webhooks notify when changes occur to the specified model.
        The model can be a board ID, card ID, or list ID.

        Args:
            model_id: ID of the board, card, or list to watch
            callback_url: URL to receive webhook events
            description: Optional description for the webhook
            active: Whether the webhook is active (default: True)

        Returns:
            Webhook data with ID
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would create webhook for model {model_id}")
            return {
                "id": "webhook:dry-run",
                "idModel": model_id,
                "callbackURL": callback_url,
                "active": active,
            }

        json_data: dict[str, Any] = {
            "idModel": model_id,
            "callbackURL": callback_url,
            "active": active,
        }
        if description:
            json_data["description"] = description

        result = self.request("POST", "webhooks", json=json_data)
        assert isinstance(result, dict)
        return result

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        """Get a webhook by ID."""
        result = self.request("GET", f"webhooks/{webhook_id}")
        assert isinstance(result, dict)
        return result

    def update_webhook(
        self,
        webhook_id: str,
        callback_url: str | None = None,
        description: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        """Update a webhook."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would update webhook {webhook_id}")
            return {"id": webhook_id}

        json_data: dict[str, Any] = {}
        if callback_url is not None:
            json_data["callbackURL"] = callback_url
        if description is not None:
            json_data["description"] = description
        if active is not None:
            json_data["active"] = active

        if not json_data:
            return self.get_webhook(webhook_id)

        result = self.request("PUT", f"webhooks/{webhook_id}", json=json_data)
        assert isinstance(result, dict)
        return result

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete webhook {webhook_id}")
            return True

        self.request("DELETE", f"webhooks/{webhook_id}")
        return True

    def list_webhooks(self) -> list[dict[str, Any]]:
        """
        List all webhooks for the authenticated token.

        Returns:
            List of webhook subscriptions
        """
        result = self.request("GET", f"tokens/{self.api_token}/webhooks")
        assert isinstance(result, list)
        return result

    # -------------------------------------------------------------------------
    # Power-Ups & Custom Fields API
    # -------------------------------------------------------------------------

    def get_board_plugins(self) -> list[dict[str, Any]]:
        """
        Get installed Power-Ups (plugins) for the board.

        Returns:
            List of installed Power-Ups
        """
        result = self.request("GET", f"boards/{self.board_id}/plugins")
        assert isinstance(result, list)
        return result

    def get_card_custom_fields(self, card_id: str) -> list[dict[str, Any]]:
        """
        Get custom field values for a card.

        Custom fields are typically added by Power-Ups.
        This requires Power-Ups to be installed on the board.

        Returns:
            List of custom field items
        """
        result = self.request("GET", f"cards/{card_id}/customFieldItems")
        assert isinstance(result, list)
        return result

    def get_custom_field_definition(self, custom_field_id: str) -> dict[str, Any]:
        """
        Get a custom field definition by ID.

        Args:
            custom_field_id: Custom field ID

        Returns:
            Custom field definition
        """
        result = self.request("GET", f"customFields/{custom_field_id}")
        assert isinstance(result, dict)
        return result

    def get_board_custom_fields(self) -> list[dict[str, Any]]:
        """
        Get all custom field definitions for the board.

        Returns:
            List of custom field definitions
        """
        result = self.request("GET", f"boards/{self.board_id}/customFields")
        assert isinstance(result, list)
        return result

    def set_custom_field(
        self,
        card_id: str,
        custom_field_id: str,
        value: str | int | float | bool | list[str] | None,
    ) -> dict[str, Any]:
        """
        Set a custom field value on a card.

        Args:
            card_id: Card ID
            custom_field_id: Custom field ID
            value: Value to set (type depends on custom field type)

        Returns:
            Updated custom field item
        """
        if self.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would set custom field {custom_field_id} on card {card_id}"
            )
            return {"idCustomField": custom_field_id, "value": value}

        # Build value based on type
        json_data: dict[str, Any] = {"idValue": None}
        if isinstance(value, (int, float)):
            json_data["value"] = {"number": str(value)}
        elif isinstance(value, bool):
            json_data["value"] = {"checked": "true" if value else "false"}
        elif isinstance(value, list):
            json_data["idValue"] = value  # List of option IDs
        elif value is not None:
            json_data["value"] = {"text": str(value)}

        result = self.request(
            "PUT",
            f"cards/{card_id}/customField/{custom_field_id}",
            json=json_data,
        )
        assert isinstance(result, dict)
        return result

    def get_plugin_data(self, plugin_id: str) -> dict[str, Any]:
        """
        Get Power-Up (plugin) data for the board.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin data
        """
        result = self.request(
            "GET", f"boards/{self.board_id}/pluginData", params={"idPlugin": plugin_id}
        )
        assert isinstance(result, list)
        # Return first item or empty dict
        return result[0] if result else {}

    # -------------------------------------------------------------------------
    # Attachments API
    # -------------------------------------------------------------------------

    def get_card_attachments(self, card_id: str) -> list[dict[str, Any]]:
        """
        Get all attachments for a card.

        Args:
            card_id: Card ID

        Returns:
            List of attachment dictionaries with id, name, url, etc.
        """
        result = self.request("GET", f"cards/{card_id}/attachments")
        assert isinstance(result, list)
        return result

    def upload_card_attachment(
        self,
        card_id: str,
        file_path: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file attachment to a card.

        Trello attachments use multipart/form-data.

        Args:
            card_id: Card ID
            file_path: Path to file to upload
            name: Optional attachment name (defaults to filename)

        Returns:
            Attachment information dictionary

        Raises:
            NotFoundError: If file doesn't exist
            IssueTrackerError: On upload failure
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload attachment {file_path} to card {card_id}")
            return {"id": "attachment:dry-run", "name": name or file_path}

        from pathlib import Path

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise NotFoundError(f"File not found: {file_path}")

        # Build URL with auth params
        url = f"{self.api_url}/cards/{card_id}/attachments"
        request_params = {**self.auth_params}
        if name:
            request_params["name"] = name

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            # Open file and upload using multipart/form-data
            with open(file_path_obj, "rb") as file_handle:
                files = {"file": (file_path_obj.name, file_handle, "application/octet-stream")}

                response = self._session.post(
                    url,
                    params=request_params,
                    files=files,
                    timeout=self.timeout,
                )

                # Update rate limiter
                if self._rate_limiter is not None:
                    self._rate_limiter.update_from_response(response)

                if response.status_code == 401:
                    raise AuthenticationError(
                        "Trello authentication failed. Check your API key and token."
                    )

                if response.status_code == 403:
                    raise PermissionError("Permission denied")

                if not response.ok:
                    error_text = response.text[:500] if response.text else ""
                    raise IssueTrackerError(
                        f"Trello attachment upload error {response.status_code}: {error_text}"
                    )

                result = response.json()
                assert isinstance(result, dict)
                return result

        except requests.exceptions.RequestException as e:
            raise IssueTrackerError(f"Failed to upload attachment: {e}", cause=e)

    def delete_card_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment.

        Args:
            attachment_id: Attachment ID to delete

        Returns:
            True if successful

        Raises:
            IssueTrackerError: On deletion failure
        """
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] Would delete attachment {attachment_id}")
            return True

        # Build URL with auth params
        url = f"{self.api_url}/attachments/{attachment_id}"
        request_params = {**self.auth_params}

        # Apply rate limiting
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()

        try:
            response = self._session.delete(url, params=request_params, timeout=self.timeout)

            # Update rate limiter
            if self._rate_limiter is not None:
                self._rate_limiter.update_from_response(response)

            if response.status_code == 401:
                raise AuthenticationError(
                    "Trello authentication failed. Check your API key and token."
                )

            if response.status_code == 403:
                raise PermissionError("Permission denied")

            if response.status_code == 404:
                raise NotFoundError(f"Attachment not found: {attachment_id}")

            if not response.ok:
                error_text = response.text[:500] if response.text else ""
                raise IssueTrackerError(
                    f"Trello attachment deletion error {response.status_code}: {error_text}"
                )

            return True

        except requests.exceptions.RequestException as e:
            raise IssueTrackerError(f"Failed to delete attachment: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Resource Cleanup
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()
        self.logger.debug("Closed HTTP session")

    def __enter__(self) -> "TrelloApiClient":
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
