# Adapter Development Guide

This guide explains how to create a new issue tracker adapter for Spectra. Whether you're adding support for a popular tracker or integrating your company's internal tool, this document provides everything you need.

## Overview

Spectra uses a **Hexagonal Architecture** (Ports & Adapters pattern) which makes adding new trackers straightforward:

1. **Port**: `IssueTrackerPort` - The interface all trackers must implement
2. **Adapter**: Your implementation that translates between Spectra and your tracker's API
3. **Plugin**: Optional plugin wrapper for the plugin system

```
┌─────────────────────────────────────────────────────────────┐
│                     Spectra Core                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Domain    │    │   Ports     │    │ Application │     │
│  │  Entities   │◄───│ (Interfaces)│◄───│  Use Cases  │     │
│  └─────────────┘    └──────┬──────┘    └─────────────┘     │
│                            │                                │
└────────────────────────────┼────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │   Jira    │  │  GitHub   │  │  YOUR     │
        │  Adapter  │  │  Adapter  │  │  ADAPTER  │
        └───────────┘  └───────────┘  └───────────┘
```

## Quick Start

### 1. Create the Directory Structure

```bash
mkdir -p src/spectryn/adapters/mytracker
touch src/spectryn/adapters/mytracker/__init__.py
touch src/spectryn/adapters/mytracker/client.py
touch src/spectryn/adapters/mytracker/adapter.py
touch src/spectryn/adapters/mytracker/plugin.py
touch tests/adapters/test_mytracker_adapter.py
```

### 2. Add TrackerType Enum

Edit `src/spectryn/core/ports/config_provider.py`:

```python
class TrackerType(Enum):
    """Supported issue tracker types."""
    # ... existing types ...
    MYTRACKER = "mytracker"  # Add your tracker
```

### 3. Implement the Adapter

See detailed implementation sections below.

---

## Implementation Guide

### Step 1: API Client (`client.py`)

The API client handles low-level HTTP communication with your tracker's API.

```python
"""
MyTracker API Client - REST client for MyTracker API.

This handles the raw HTTP communication with MyTracker.
The MyTrackerAdapter uses this to implement the IssueTrackerPort.

API Documentation: https://docs.mytracker.com/api
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


class MyTrackerRateLimiter:
    """
    Rate limiter for MyTracker API.

    Adjust these values based on your tracker's rate limits.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,  # Adjust based on API limits
        burst_size: int = 10,
    ):
        self.requests_per_second = requests_per_second
        self.burst_size = max(1, burst_size)
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = __import__("threading").Lock()
        self._retry_after: float | None = None
        self._total_requests = 0
        self._total_wait_time = 0.0
        self.logger = logging.getLogger("MyTrackerRateLimiter")

    def acquire(self, timeout: float | None = None) -> bool:
        """Acquire a token, waiting if necessary."""
        start_time = time.monotonic()

        while True:
            with self._lock:
                if self._retry_after is not None:
                    wait_time = self._retry_after - time.time()
                    if wait_time > 0:
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

            self._total_wait_time += wait_time
            time.sleep(wait_time)

    def _refill_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now
        new_tokens = elapsed * self.requests_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)

    def update_from_response(self, response: requests.Response) -> None:
        """Update rate limiter based on response headers."""
        with self._lock:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                import contextlib
                with contextlib.suppress(ValueError):
                    self._retry_after = time.time() + float(retry_after)

            if response.status_code == 429:
                self.requests_per_second = max(0.1, self.requests_per_second * 0.5)

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_wait_time": self._total_wait_time,
                "current_tokens": self._tokens,
                "requests_per_second": self.requests_per_second,
            }


class MyTrackerApiClient:
    """
    Low-level MyTracker REST API client.

    Features:
    - REST API with automatic retry
    - Token authentication
    - Automatic retry with exponential backoff
    - Rate limiting
    - Connection pooling
    """

    BASE_URL = "https://api.mytracker.com/v1"  # Your API base URL

    def __init__(
        self,
        api_token: str,
        project_id: str,
        api_url: str = BASE_URL,
        dry_run: bool = True,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        self.api_token = api_token
        self.project_id = project_id
        self.api_url = api_url.rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger("MyTrackerApiClient")

        # Rate limiting
        self._rate_limiter = MyTrackerRateLimiter()

        # Headers - adjust based on your API's auth method
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",  # Or "X-API-Token", etc.
        }

        # Configure session with connection pooling
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self._session.mount("https://", adapter)

        # Cache
        self._current_user: dict | None = None

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make an authenticated request with rate limiting and retry."""
        url = f"{self.api_url}{endpoint}" if endpoint.startswith("/") else f"{self.api_url}/{endpoint}"

        for attempt in range(self.max_retries + 1):
            self._rate_limiter.acquire()

            try:
                if "timeout" not in kwargs:
                    kwargs["timeout"] = self.timeout

                response = self._session.request(method, url, **kwargs)
                self._rate_limiter.update_from_response(response)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        delay = calculate_delay(attempt)
                        time.sleep(delay)
                        continue
                    if response.status_code == 429:
                        raise RateLimitError("Rate limit exceeded")
                    raise TransientError(f"Server error {response.status_code}")

                return self._handle_response(response)

            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries:
                    time.sleep(calculate_delay(attempt))
                    continue
                raise IssueTrackerError(f"Connection failed: {e}", cause=e)

        raise IssueTrackerError(f"Request failed after {self.max_retries + 1} attempts")

    def _handle_response(self, response: requests.Response) -> dict[str, Any] | list[Any]:
        """Handle API response and convert errors."""
        if response.status_code == 401:
            raise AuthenticationError("Authentication failed. Check your API token.")
        if response.status_code == 403:
            raise PermissionError("Permission denied")
        if response.status_code == 404:
            raise NotFoundError("Resource not found")
        if not response.ok:
            raise IssueTrackerError(f"API error {response.status_code}: {response.text[:500]}")

        if not response.text:
            return {}

        try:
            return response.json()
        except ValueError as e:
            raise IssueTrackerError(f"Invalid JSON response: {e}", cause=e)

    # -------------------------------------------------------------------------
    # Implement your API methods here
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        if self._current_user is None:
            data = self.request("GET", "/me")
            self._current_user = data if isinstance(data, dict) else {}
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
        return self._current_user is not None

    def get_issue(self, issue_id: int) -> dict[str, Any]:
        """Get an issue by ID."""
        result = self.request("GET", f"/projects/{self.project_id}/issues/{issue_id}")
        if isinstance(result, dict):
            return result
        raise IssueTrackerError(f"Unexpected response type: {type(result)}")

    def create_issue(self, title: str, description: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create a new issue."""
        payload = {"title": title}
        if description:
            payload["description"] = description
        payload.update(kwargs)

        result = self.request("POST", f"/projects/{self.project_id}/issues", json=payload)
        return result if isinstance(result, dict) else {}

    def update_issue(self, issue_id: int, **kwargs: Any) -> dict[str, Any]:
        """Update an existing issue."""
        if not kwargs:
            return {}
        result = self.request("PUT", f"/projects/{self.project_id}/issues/{issue_id}", json=kwargs)
        return result if isinstance(result, dict) else {}

    def search_issues(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Search for issues."""
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        data = self.request("GET", f"/projects/{self.project_id}/issues", params=params)
        return data if isinstance(data, list) else []

    def get_comments(self, issue_id: int) -> list[dict[str, Any]]:
        """Get comments on an issue."""
        data = self.request("GET", f"/projects/{self.project_id}/issues/{issue_id}/comments")
        return data if isinstance(data, list) else []

    def add_comment(self, issue_id: int, text: str) -> dict[str, Any]:
        """Add a comment to an issue."""
        result = self.request(
            "POST",
            f"/projects/{self.project_id}/issues/{issue_id}/comments",
            json={"text": text},
        )
        return result if isinstance(result, dict) else {}

    # Add more API methods as needed...

    def close(self) -> None:
        """Close the client and release resources."""
        self._session.close()

    def __enter__(self) -> "MyTrackerApiClient":
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> None:
        self.close()
```

### Step 2: Adapter (`adapter.py`)

The adapter implements `IssueTrackerPort` and translates between Spectra's domain model and your tracker's model.

```python
"""
MyTracker Adapter - Implements IssueTrackerPort for MyTracker.

Key mappings:
- Epic → [Your epic equivalent]
- Story → Issue
- Subtask → [Your subtask equivalent]
- Status → [Your status field]
- Priority → [Your priority field]
- Story Points → [Your estimate field]
"""

import logging
from typing import Any

from spectryn.core.ports.issue_tracker import (
    IssueData,
    IssueLink,
    IssueTrackerError,
    IssueTrackerPort,
    LinkType,
    NotFoundError,
    TransitionError,
)

from .client import MyTrackerApiClient


class MyTrackerAdapter(IssueTrackerPort):
    """
    MyTracker implementation of the IssueTrackerPort.

    Translates between domain entities and MyTracker's REST API.
    """

    def __init__(
        self,
        api_token: str,
        project_id: str,
        dry_run: bool = True,
        api_url: str = "https://api.mytracker.com/v1",
    ):
        self._dry_run = dry_run
        self.project_id = project_id
        self.logger = logging.getLogger("MyTrackerAdapter")

        self._client = MyTrackerApiClient(
            api_token=api_token,
            project_id=project_id,
            api_url=api_url,
            dry_run=dry_run,
        )

    def _parse_issue_id(self, issue_key: str) -> int:
        """Parse issue ID from key (e.g., 'MT-123' or '123')."""
        if "-" in issue_key:
            try:
                return int(issue_key.split("-")[-1])
            except ValueError:
                pass
        try:
            return int(issue_key)
        except ValueError:
            raise NotFoundError(f"Invalid issue ID format: {issue_key}")

    # -------------------------------------------------------------------------
    # Status Mapping - Customize for your tracker
    # -------------------------------------------------------------------------

    def _map_status_from_tracker(self, tracker_status: str) -> str:
        """Map tracker status to Spectra display status."""
        mapping = {
            "open": "Open",
            "in_progress": "In Progress",
            "review": "In Review",
            "done": "Done",
            "closed": "Done",
        }
        return mapping.get(tracker_status.lower(), tracker_status.capitalize())

    def _map_status_to_tracker(self, spectryn_status: str) -> str:
        """Map Spectra status to tracker status."""
        status_lower = spectryn_status.lower()
        if any(x in status_lower for x in ["done", "closed", "complete"]):
            return "done"
        if any(x in status_lower for x in ["review"]):
            return "review"
        if any(x in status_lower for x in ["progress", "started"]):
            return "in_progress"
        return "open"

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Properties
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "MyTracker"

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    def test_connection(self) -> bool:
        return self._client.test_connection()

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Read Operations
    # -------------------------------------------------------------------------

    def get_current_user(self) -> dict[str, Any]:
        return self._client.get_current_user()

    def get_issue(self, issue_key: str) -> IssueData:
        issue_id = self._parse_issue_id(issue_key)
        data = self._client.get_issue(issue_id)
        return self._parse_issue(data)

    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        # Implement based on your tracker's epic/parent concept
        epic_id = self._parse_issue_id(epic_key)
        issues = self._client.search_issues(query=f"parent:{epic_id}")
        return [self._parse_issue(issue) for issue in issues]

    def get_issue_comments(self, issue_key: str) -> list[dict]:
        issue_id = self._parse_issue_id(issue_key)
        comments = self._client.get_comments(issue_id)
        return [
            {
                "id": c.get("id"),
                "body": c.get("text", ""),
                "author": c.get("author", {}).get("name"),
                "created": c.get("created_at"),
            }
            for c in comments
        ]

    def get_issue_status(self, issue_key: str) -> str:
        issue_id = self._parse_issue_id(issue_key)
        issue = self._client.get_issue(issue_id)
        return self._map_status_from_tracker(issue.get("status", "open"))

    def search_issues(self, query: str, max_results: int = 50) -> list[IssueData]:
        issues = self._client.search_issues(query=query, limit=max_results)
        return [self._parse_issue(issue) for issue in issues]

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Write Operations
    # -------------------------------------------------------------------------

    def update_issue_description(self, issue_key: str, description: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update description for {issue_key}")
            return True

        issue_id = self._parse_issue_id(issue_key)
        desc_str = description if isinstance(description, str) else str(description)
        self._client.update_issue(issue_id, description=desc_str)
        return True

    def update_issue_story_points(self, issue_key: str, story_points: float) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update story points for {issue_key}")
            return True

        issue_id = self._parse_issue_id(issue_key)
        # Adjust field name based on your tracker
        self._client.update_issue(issue_id, estimate=int(story_points))
        return True

    def create_subtask(
        self,
        parent_key: str,
        summary: str,
        description: Any,
        project_key: str,
        story_points: int | None = None,
        assignee: str | None = None,
        priority: str | None = None,
    ) -> str | None:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would create subtask under {parent_key}")
            return None

        parent_id = self._parse_issue_id(parent_key)
        desc_str = description if isinstance(description, str) else str(description)

        result = self._client.create_issue(
            title=summary,
            description=desc_str,
            parent_id=parent_id,  # Adjust based on your API
        )

        if result.get("id"):
            return str(result["id"])
        return None

    def update_subtask(
        self,
        issue_key: str,
        description: Any | None = None,
        story_points: int | None = None,
        assignee: str | None = None,
        priority_id: str | None = None,
    ) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would update subtask {issue_key}")
            return True

        issue_id = self._parse_issue_id(issue_key)
        updates: dict[str, Any] = {}

        if description is not None:
            updates["description"] = str(description)
        if story_points is not None:
            updates["estimate"] = story_points

        if updates:
            self._client.update_issue(issue_id, **updates)

        return True

    def add_comment(self, issue_key: str, body: Any) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would add comment to {issue_key}")
            return True

        issue_id = self._parse_issue_id(issue_key)
        comment_body = body if isinstance(body, str) else str(body)
        self._client.add_comment(issue_id, comment_body)
        return True

    def transition_issue(self, issue_key: str, target_status: str) -> bool:
        if self._dry_run:
            self.logger.info(f"[DRY-RUN] Would transition {issue_key} to {target_status}")
            return True

        try:
            issue_id = self._parse_issue_id(issue_key)
            tracker_status = self._map_status_to_tracker(target_status)
            self._client.update_issue(issue_id, status=tracker_status)
            return True
        except IssueTrackerError as e:
            raise TransitionError(
                f"Failed to transition {issue_key}: {e}",
                issue_key=issue_key,
                cause=e,
            )

    # -------------------------------------------------------------------------
    # IssueTrackerPort Implementation - Utility
    # -------------------------------------------------------------------------

    def get_available_transitions(self, issue_key: str) -> list[dict]:
        # Return available status transitions
        return [
            {"id": "open", "name": "Open"},
            {"id": "in_progress", "name": "In Progress"},
            {"id": "review", "name": "In Review"},
            {"id": "done", "name": "Done"},
        ]

    def format_description(self, markdown: str) -> Any:
        """Convert markdown to tracker-specific format."""
        # Most trackers support Markdown natively
        return markdown

    # -------------------------------------------------------------------------
    # Link Operations (Optional)
    # -------------------------------------------------------------------------

    def get_issue_links(self, issue_key: str) -> list[IssueLink]:
        # Implement if your tracker supports issue linking
        return []

    def create_link(self, source_key: str, target_key: str, link_type: LinkType) -> bool:
        # Implement if your tracker supports issue linking
        return False

    def delete_link(self, source_key: str, target_key: str, link_type: LinkType | None = None) -> bool:
        # Implement if your tracker supports issue linking
        return False

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _parse_issue(self, data: dict) -> IssueData:
        """Parse tracker issue into IssueData."""
        return IssueData(
            key=str(data.get("id", "")),
            summary=data.get("title", ""),
            description=data.get("description"),
            status=self._map_status_from_tracker(data.get("status", "open")),
            issue_type=data.get("type", "Story"),
            assignee=data.get("assignee", {}).get("name"),
            story_points=float(data["estimate"]) if data.get("estimate") else None,
            subtasks=[],  # Populate if needed
            comments=[],  # Populate if needed
            links=[],
        )
```

### Step 3: Plugin (`plugin.py`)

The plugin enables discovery through Spectra's plugin system.

```python
"""
MyTracker Plugin - Plugin wrapper for MyTracker adapter.
"""

import os
from typing import Any

from spectryn.core.ports.issue_tracker import IssueTrackerPort
from spectryn.plugins.base import PluginMetadata, PluginType, TrackerPlugin

from .adapter import MyTrackerAdapter


class MyTrackerPlugin(TrackerPlugin):
    """
    Plugin wrapper for the MyTracker adapter.

    Configuration options:
    - api_token: API token (required, or use MYTRACKER_API_TOKEN env)
    - project_id: Project ID (required, or use MYTRACKER_PROJECT_ID env)
    - api_url: API URL (optional)
    - dry_run: If True, don't make changes (default: True)
    """

    CONFIG_SCHEMA = {
        "type": "object",
        "properties": {
            "api_token": {"type": "string", "description": "API token"},
            "project_id": {"type": "string", "description": "Project ID"},
            "api_url": {"type": "string", "description": "API URL"},
            "dry_run": {"type": "boolean", "default": True},
        },
    }

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._adapter: MyTrackerAdapter | None = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mytracker",
            version="1.0.0",
            description="MyTracker integration for spectryn",
            author="Your Name/Company",
            plugin_type=PluginType.TRACKER,
            requires=[],
            config_schema=self.CONFIG_SCHEMA,
        )

    def initialize(self) -> None:
        api_token = self.config.get("api_token") or os.getenv("MYTRACKER_API_TOKEN", "")
        project_id = self.config.get("project_id") or os.getenv("MYTRACKER_PROJECT_ID", "")
        api_url = self.config.get("api_url") or os.getenv(
            "MYTRACKER_API_URL", "https://api.mytracker.com/v1"
        )

        if not api_token:
            raise ValueError(
                "API token is required. Set 'api_token' in config or MYTRACKER_API_TOKEN env var."
            )
        if not project_id:
            raise ValueError(
                "Project ID is required. Set 'project_id' in config or MYTRACKER_PROJECT_ID env var."
            )

        self._adapter = MyTrackerAdapter(
            api_token=api_token,
            project_id=project_id,
            api_url=str(api_url),
            dry_run=self.config.get("dry_run", True),
        )
        self._initialized = True

    def shutdown(self) -> None:
        if self._adapter is not None:
            self._adapter._client.close()
            self._adapter = None
        self._initialized = False

    def get_tracker(self) -> IssueTrackerPort:
        if not self.is_initialized or self._adapter is None:
            raise RuntimeError("Plugin not initialized. Call initialize() first.")
        return self._adapter

    def validate_config(self) -> list[str]:
        errors = super().validate_config()

        api_token = self.config.get("api_token") or os.getenv("MYTRACKER_API_TOKEN")
        project_id = self.config.get("project_id") or os.getenv("MYTRACKER_PROJECT_ID")

        if not api_token:
            errors.append("Missing API token (set 'api_token' or MYTRACKER_API_TOKEN)")
        if not project_id:
            errors.append("Missing project ID (set 'project_id' or MYTRACKER_PROJECT_ID)")

        return errors


def create_plugin(config: dict[str, Any] | None = None) -> MyTrackerPlugin:
    """Factory function for plugin discovery."""
    return MyTrackerPlugin(config)
```

### Step 4: Module Exports (`__init__.py`)

```python
"""
MyTracker Adapter - Integration with MyTracker.
"""

from .adapter import MyTrackerAdapter
from .client import MyTrackerApiClient
from .plugin import MyTrackerPlugin

__all__ = [
    "MyTrackerAdapter",
    "MyTrackerApiClient",
    "MyTrackerPlugin",
]
```

---

## Testing Guide

### Step 5: Unit Tests (`test_mytracker_adapter.py`)

```python
"""
Tests for MyTracker Adapter.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.mytracker.adapter import MyTrackerAdapter
from spectryn.adapters.mytracker.client import MyTrackerApiClient
from spectryn.adapters.mytracker.plugin import MyTrackerPlugin, create_plugin
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,
    NotFoundError,
)


class TestMyTrackerApiClient:
    """Tests for MyTrackerApiClient."""

    @pytest.fixture
    def mock_session(self):
        with patch("spectryn.adapters.mytracker.client.requests.Session") as mock:
            session = MagicMock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def client(self, mock_session):
        return MyTrackerApiClient(
            api_token="test_token",
            project_id="12345",
            dry_run=False,
        )

    def test_initialization(self, mock_session):
        client = MyTrackerApiClient(api_token="test_token", project_id="12345")
        assert client.dry_run is True  # Default

    def test_get_issue(self, client, mock_session):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123, "title": "Test Issue"}
        mock_response.headers = {}
        mock_response.text = '{"id": 123}'
        mock_session.request.return_value = mock_response

        result = client.get_issue(123)

        assert result["id"] == 123
        mock_session.request.assert_called_once()

    def test_authentication_error(self, client, mock_session):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_session.request.return_value = mock_response

        with pytest.raises(AuthenticationError):
            client.request("GET", "/me")

    def test_not_found_error(self, client, mock_session):
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_session.request.return_value = mock_response

        with pytest.raises(NotFoundError):
            client.request("GET", "/issues/999")


class TestMyTrackerAdapter:
    """Tests for MyTrackerAdapter."""

    @pytest.fixture
    def mock_client(self):
        return MagicMock(spec=MyTrackerApiClient)

    @pytest.fixture
    def adapter(self, mock_client):
        adapter = MyTrackerAdapter(
            api_token="test_token",
            project_id="12345",
            dry_run=False,
        )
        adapter._client = mock_client
        return adapter

    def test_name(self, adapter):
        assert adapter.name == "MyTracker"

    def test_get_issue(self, adapter, mock_client):
        mock_client.get_issue.return_value = {
            "id": 123,
            "title": "Test Issue",
            "status": "in_progress",
            "type": "Story",
        }

        result = adapter.get_issue("123")

        assert result.key == "123"
        assert result.summary == "Test Issue"
        assert result.status == "In Progress"

    def test_add_comment(self, adapter, mock_client):
        adapter.add_comment("123", "Test comment")
        mock_client.add_comment.assert_called_once_with(123, "Test comment")

    def test_dry_run_no_changes(self, adapter, mock_client):
        adapter._dry_run = True

        result = adapter.update_issue_description("123", "New desc")

        assert result is True
        mock_client.update_issue.assert_not_called()


class TestMyTrackerPlugin:
    """Tests for MyTrackerPlugin."""

    def test_metadata(self):
        from spectryn.plugins.base import PluginType

        plugin = MyTrackerPlugin()
        assert plugin.metadata.name == "mytracker"
        assert plugin.metadata.plugin_type == PluginType.TRACKER

    @patch.dict("os.environ", {"MYTRACKER_API_TOKEN": "token", "MYTRACKER_PROJECT_ID": "123"})
    def test_initialize_from_env(self):
        plugin = MyTrackerPlugin()
        plugin.config = {}

        with patch("spectryn.adapters.mytracker.plugin.MyTrackerAdapter") as mock:
            mock.return_value = MagicMock()
            plugin.initialize()
            mock.assert_called_once()

    def test_validate_config_missing_token(self):
        plugin = MyTrackerPlugin()
        plugin.config = {}

        errors = plugin.validate_config()

        assert len(errors) > 0
        assert any("token" in e.lower() for e in errors)

    def test_create_plugin(self):
        plugin = create_plugin({"api_token": "test", "project_id": "123"})
        assert isinstance(plugin, MyTrackerPlugin)
```

---

## Validation Checklist

Before submitting your adapter, ensure:

### Code Quality
```bash
# Format code
ruff format src/spectryn/adapters/mytracker tests/adapters/test_mytracker_adapter.py

# Lint and fix
ruff check src/spectryn/adapters/mytracker tests/adapters/test_mytracker_adapter.py --fix

# Type checking
mypy src/spectryn/adapters/mytracker

# Run tests
pytest tests/adapters/test_mytracker_adapter.py -v
```

### Interface Compliance

Verify all `IssueTrackerPort` methods are implemented:

| Method | Required | Description |
|--------|----------|-------------|
| `name` | ✅ | Tracker display name |
| `is_connected` | ✅ | Connection status |
| `test_connection()` | ✅ | Test API connectivity |
| `get_current_user()` | ✅ | Get authenticated user |
| `get_issue()` | ✅ | Fetch single issue |
| `get_epic_children()` | ✅ | Get epic's child issues |
| `get_issue_comments()` | ✅ | Get issue comments |
| `get_issue_status()` | ✅ | Get issue status |
| `search_issues()` | ✅ | Search issues |
| `update_issue_description()` | ✅ | Update description |
| `update_issue_story_points()` | ✅ | Update story points |
| `create_subtask()` | ✅ | Create subtask |
| `update_subtask()` | ✅ | Update subtask |
| `add_comment()` | ✅ | Add comment |
| `transition_issue()` | ✅ | Change issue status |
| `get_available_transitions()` | ✅ | Get available statuses |
| `format_description()` | ✅ | Format markdown |
| `get_issue_links()` | Optional | Get issue links |
| `create_link()` | Optional | Create issue link |
| `delete_link()` | Optional | Delete issue link |

---

## Best Practices

### 1. Rate Limiting
Always implement rate limiting to avoid API bans:

```python
# Conservative defaults
requests_per_second = 0.5  # Start low
burst_size = 10            # Allow small bursts
```

### 2. Dry Run Mode
Always check `_dry_run` before making changes:

```python
def update_issue(self, key: str, **kwargs) -> bool:
    if self._dry_run:
        self.logger.info(f"[DRY-RUN] Would update {key}")
        return True
    # Actual update logic
```

### 3. Error Handling
Use Spectra's exception types:

```python
from spectryn.core.ports.issue_tracker import (
    AuthenticationError,    # 401 errors
    PermissionError,        # 403 errors
    NotFoundError,          # 404 errors
    RateLimitError,         # 429 errors
    TransientError,         # 5xx errors (retryable)
    TransitionError,        # Status change failures
    IssueTrackerError,      # Generic errors
)
```

### 4. Logging
Use structured logging:

```python
self.logger = logging.getLogger("MyTrackerAdapter")
self.logger.info(f"Created issue {issue_key}")
self.logger.warning(f"Rate limited, backing off")
self.logger.error(f"Failed to update {key}: {error}")
```

### 5. Status Mapping
Create clear bidirectional status mappings:

```python
TRACKER_TO_SPECTRA = {
    "todo": "Open",
    "doing": "In Progress",
    "done": "Done",
}

SPECTRA_TO_TRACKER = {
    "open": "todo",
    "in progress": "doing",
    "done": "done",
}
```

---

## Optional Features

### Async Adapter

For high-performance scenarios:

```python
# async_adapter.py
import aiohttp

class AsyncMyTrackerAdapter:
    async def get_issue(self, key: str) -> IssueData:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.api_url}/issues/{key}") as resp:
                data = await resp.json()
                return self._parse_issue(data)
```

### Batch Operations

For bulk updates:

```python
# batch.py
class MyTrackerBatchClient:
    def batch_update(self, updates: list[dict]) -> list[dict]:
        # Send multiple updates in one request if API supports it
        return self._client.request("POST", "/batch", json={"updates": updates})
```

### Caching

For frequently accessed data:

```python
from spectryn.adapters.cache import CacheManager

class CachedMyTrackerAdapter(MyTrackerAdapter):
    def __init__(self, *args, cache_ttl: int = 300, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = CacheManager(ttl=cache_ttl)

    def get_issue(self, key: str) -> IssueData:
        cached = self._cache.get(f"issue:{key}")
        if cached:
            return cached
        result = super().get_issue(key)
        self._cache.set(f"issue:{key}", result)
        return result
```

---

## Documentation Template

Create `docs/guide/mytracker.md`:

```markdown
# MyTracker Integration

This guide covers setting up Spectra with MyTracker.

## Prerequisites

- MyTracker account with API access
- API token with read/write permissions

## Configuration

### Environment Variables

```bash
export MYTRACKER_API_TOKEN="your-api-token"
export MYTRACKER_PROJECT_ID="your-project-id"
```

### Configuration File

```yaml
# .spectryn.yaml
tracker:
  type: mytracker
  api_token: ${MYTRACKER_API_TOKEN}
  project_id: "12345"
```

## Usage

```bash
spectryn --tracker mytracker --markdown EPIC.md --validate
spectryn --tracker mytracker --markdown EPIC.md --execute
```

## Status Mapping

| Spectra Status | MyTracker Status |
|----------------|------------------|
| Open           | todo             |
| In Progress    | doing            |
| In Review      | review           |
| Done           | done             |

## Troubleshooting

### Authentication Failed
Verify your API token has the required permissions.

### Rate Limiting
If you see 429 errors, the adapter will automatically back off.
```

---

## Submitting Your Adapter

1. **Fork** the Spectra repository
2. **Create** your adapter following this guide
3. **Add tests** with good coverage (aim for 80%+)
4. **Run validation** commands
5. **Update** `IMPROVEMENTS-CHECKLIST.md` if adding a listed tracker
6. **Submit** a pull request

### PR Checklist

- [ ] All `IssueTrackerPort` methods implemented
- [ ] Rate limiting implemented
- [ ] Dry-run mode works correctly
- [ ] Unit tests pass (50+ tests recommended)
- [ ] Type hints on all functions
- [ ] Docstrings on public methods
- [ ] `ruff format` passes
- [ ] `ruff check` passes
- [ ] `mypy` passes (no new errors)
- [ ] Documentation added

---

## Getting Help

- **Examples**: See existing adapters in `src/spectryn/adapters/` (Shortcut, Trello, Pivotal are good templates)
- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue

Happy building! 🚀

