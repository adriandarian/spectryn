"""
Linear Adapter - Integration with Linear.

This module provides the Linear implementation of the IssueTrackerPort,
enabling syncing markdown documents to Linear issues.
"""

from .adapter import LinearAdapter
from .async_adapter import AsyncLinearAdapter
from .batch import BatchOperation, BatchResult, LinearBatchClient
from .client import LinearApiClient
from .plugin import LinearTrackerPlugin


__all__ = [
    "AsyncLinearAdapter",
    "BatchOperation",
    "BatchResult",
    "LinearAdapter",
    "LinearApiClient",
    "LinearBatchClient",
    "LinearTrackerPlugin",
]
