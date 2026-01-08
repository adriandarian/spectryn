"""
Jira Adapter - Implementation of IssueTrackerPort for Atlassian Jira.

Includes multiple client options:
- JiraAdapter: Main synchronous adapter implementing IssueTrackerPort
- AsyncJiraAdapter: Async adapter implementing AsyncIssueTrackerPort (requires aiohttp)
- JiraApiClient: Basic synchronous HTTP client
- CachedJiraApiClient: Client with response caching
- AsyncJiraApiClient: Async HTTP client with parallel support (requires aiohttp)
- JiraBatchClient: Batch operations using bulk APIs
"""

from .adapter import JiraAdapter
from .batch import BatchOperation, BatchResult, JiraBatchClient
from .cached_client import CachedJiraApiClient
from .client import JiraApiClient


# Async adapter and client are optional (requires aiohttp)
try:
    from .async_adapter import AsyncJiraAdapter, is_async_available
    from .async_client import AsyncJiraApiClient

    ASYNC_AVAILABLE = True
except ImportError:
    AsyncJiraApiClient = None  # type: ignore[misc, assignment]
    AsyncJiraAdapter = None  # type: ignore[misc, assignment]
    ASYNC_AVAILABLE = False

    def is_async_available() -> bool:  # type: ignore[misc]
        return False


__all__ = [
    # Utilities
    "ASYNC_AVAILABLE",
    "AsyncJiraAdapter",
    "AsyncJiraApiClient",
    "BatchOperation",
    "BatchResult",
    "CachedJiraApiClient",
    # Adapters
    "JiraAdapter",
    # HTTP Clients
    "JiraApiClient",
    # Batch
    "JiraBatchClient",
    "is_async_available",
]
