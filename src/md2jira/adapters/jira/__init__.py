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
from .client import JiraApiClient
from .cached_client import CachedJiraApiClient
from .batch import JiraBatchClient, BatchResult, BatchOperation

# Async adapter and client are optional (requires aiohttp)
try:
    from .async_client import AsyncJiraApiClient
    from .async_adapter import AsyncJiraAdapter, is_async_available
    ASYNC_AVAILABLE = True
except ImportError:
    AsyncJiraApiClient = None  # type: ignore[misc, assignment]
    AsyncJiraAdapter = None  # type: ignore[misc, assignment]
    ASYNC_AVAILABLE = False
    
    def is_async_available() -> bool:  # type: ignore[misc]
        return False

__all__ = [
    # Adapters
    "JiraAdapter",
    "AsyncJiraAdapter",
    # HTTP Clients
    "JiraApiClient",
    "CachedJiraApiClient",
    "AsyncJiraApiClient",
    # Batch
    "JiraBatchClient",
    "BatchResult",
    "BatchOperation",
    # Utilities
    "ASYNC_AVAILABLE",
    "is_async_available",
]

