"""Asana Adapter - Implementation of IssueTrackerPort for Asana tasks."""

from .adapter import AsanaAdapter
from .batch import AsanaBatchClient, BatchOperation, BatchResult
from .cached_adapter import CachedAsanaAdapter


# Conditional async exports
try:
    from .async_adapter import ASYNC_AVAILABLE, AsyncAsanaAdapter, is_async_available
except ImportError:
    ASYNC_AVAILABLE = False
    AsyncAsanaAdapter = None  # type: ignore
    is_async_available = lambda: False  # noqa: E731


__all__ = [
    "ASYNC_AVAILABLE",
    "AsanaAdapter",
    "AsanaBatchClient",
    "AsyncAsanaAdapter",
    "BatchOperation",
    "BatchResult",
    "CachedAsanaAdapter",
    "is_async_available",
]
