"""
Parallel Execution Utilities - Tools for running async operations in parallel.

Provides controlled parallel execution with:
- Concurrency limits to prevent overwhelming APIs
- Batch processing for large operation sets
- Result collection with error handling
- Progress tracking
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .rate_limiter import AsyncRateLimiter


logger = logging.getLogger("parallel")

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class ParallelResult(Generic[T]):
    """
    Result of a parallel operation batch.

    Contains both successful results and any errors that occurred.
    Provides summary statistics for the batch execution.

    Attributes:
        results: List of successful results
        errors: List of (index, exception) tuples for failed operations
        total: Total number of operations attempted
        successful: Number of successful operations
        failed: Number of failed operations
    """

    results: list[T] = field(default_factory=list)
    errors: list[tuple[int, Exception]] = field(default_factory=list)
    total: int = 0

    @property
    def successful(self) -> int:
        """Number of successful operations."""
        return len(self.results)

    @property
    def failed(self) -> int:
        """Number of failed operations."""
        return len(self.errors)

    @property
    def success_rate(self) -> float:
        """Success rate as a fraction (0.0 to 1.0)."""
        if self.total == 0:
            return 1.0
        return self.successful / self.total

    @property
    def all_succeeded(self) -> bool:
        """Check if all operations succeeded."""
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return (
            f"ParallelResult(total={self.total}, "
            f"successful={self.successful}, failed={self.failed})"
        )


async def gather_with_limit(
    coros: list[Coroutine[Any, Any, T]],
    limit: int = 10,
    return_exceptions: bool = False,
) -> list[T | Exception]:
    """
    Run coroutines concurrently with a concurrency limit.

    Similar to asyncio.gather but limits the number of concurrent
    operations to prevent overwhelming the API or running out of
    connections.

    Args:
        coros: List of coroutines to execute
        limit: Maximum number of concurrent operations
        return_exceptions: If True, exceptions are returned in the list
                          instead of being raised

    Returns:
        List of results in the same order as input coroutines.
        If return_exceptions=True, exceptions appear in the list.

    Raises:
        First exception encountered if return_exceptions=False

    Example:
        >>> async def fetch(url):
        ...     async with aiohttp.get(url) as resp:
        ...         return await resp.json()
        >>>
        >>> urls = ["http://api.example.com/item/1", ...]
        >>> results = await gather_with_limit(
        ...     [fetch(url) for url in urls],
        ...     limit=5,
        ... )
    """
    semaphore = asyncio.Semaphore(limit)

    async def bounded_coro(coro: Coroutine[Any, Any, T]) -> T:
        async with semaphore:
            return await coro

    if return_exceptions:
        return await asyncio.gather(
            *[bounded_coro(coro) for coro in coros],
            return_exceptions=True,
        )
    return list(
        await asyncio.gather(
            *[bounded_coro(coro) for coro in coros],
        )
    )


async def batch_execute(
    items: list[T],
    operation: Callable[[T], Coroutine[Any, Any, R]],
    batch_size: int = 10,
    concurrency: int = 5,
    rate_limiter: AsyncRateLimiter | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ParallelResult[R]:
    """
    Execute an operation on items in batches with controlled concurrency.

    Processes items in batches, with each batch running operations
    concurrently up to the concurrency limit. Includes rate limiting
    and progress tracking.

    Args:
        items: List of items to process
        operation: Async function to apply to each item
        batch_size: Number of items per batch
        concurrency: Max concurrent operations within a batch
        rate_limiter: Optional rate limiter for API calls
        progress_callback: Optional callback(completed, total) for progress

    Returns:
        ParallelResult containing successful results and any errors

    Example:
        >>> async def update_issue(issue_key: str) -> dict:
        ...     return await client.update_issue(issue_key, status="Done")
        >>>
        >>> issue_keys = ["PROJ-1", "PROJ-2", "PROJ-3", ...]
        >>> result = await batch_execute(
        ...     items=issue_keys,
        ...     operation=update_issue,
        ...     batch_size=20,
        ...     concurrency=5,
        ... )
        >>> print(f"Updated {result.successful} issues, {result.failed} failed")
    """
    result = ParallelResult[R]()
    result.total = len(items)

    if not items:
        return result

    completed = 0

    # Process in batches
    for batch_start in range(0, len(items), batch_size):
        batch_end = min(batch_start + batch_size, len(items))
        batch = items[batch_start:batch_end]

        # Create tasks for this batch
        async def execute_with_rate_limit(
            idx: int,
            item: T,
        ) -> tuple[int, R | Exception]:
            """Execute operation with rate limiting and error capture."""
            if rate_limiter is not None:
                await rate_limiter.acquire()

            try:
                r = await operation(item)
                return (idx, r)
            except Exception as e:
                return (idx, e)

        # Execute batch concurrently
        semaphore = asyncio.Semaphore(concurrency)

        async def bounded_execute(idx: int, item: T) -> tuple[int, R | Exception]:
            async with semaphore:
                return await execute_with_rate_limit(idx, item)

        tasks = [bounded_execute(batch_start + i, item) for i, item in enumerate(batch)]

        batch_results = await asyncio.gather(*tasks)

        # Process batch results
        for idx, res in batch_results:
            if isinstance(res, Exception):
                result.errors.append((idx, res))
                logger.debug(f"Operation {idx} failed: {res}")
            else:
                result.results.append(res)

            completed += 1
            if progress_callback:
                progress_callback(completed, result.total)

    return result


async def run_parallel(
    operations: dict[str, Coroutine[Any, Any, T]],
    concurrency: int = 10,
    fail_fast: bool = False,
) -> dict[str, T | Exception]:
    """
    Run named operations in parallel and return results by name.

    Useful when you need to identify which operation produced
    which result.

    Args:
        operations: Dict mapping names to coroutines
        concurrency: Maximum concurrent operations
        fail_fast: If True, cancel remaining operations on first error

    Returns:
        Dict mapping names to results (or exceptions if fail_fast=False)

    Raises:
        First exception if fail_fast=True

    Example:
        >>> results = await run_parallel({
        ...     "user": client.get_user(user_id),
        ...     "issues": client.get_issues(project_key),
        ...     "comments": client.get_comments(issue_key),
        ... })
        >>> user = results["user"]
        >>> issues = results["issues"]
    """
    if not operations:
        return {}

    names = list(operations.keys())
    coros = list(operations.values())

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_coro(name: str, coro: Coroutine[Any, Any, T]) -> tuple[str, T | Exception]:
        async with semaphore:
            try:
                result = await coro
                return (name, result)
            except Exception as e:
                if fail_fast:
                    raise
                return (name, e)

    tasks = [bounded_coro(name, coro) for name, coro in zip(names, coros, strict=False)]

    if fail_fast:
        # Use gather without return_exceptions to propagate first error
        results_list = await asyncio.gather(*tasks)
    else:
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Build results dict
    results: dict[str, T | Exception] = {}
    for item in results_list:
        if isinstance(item, Exception):
            # This happens when fail_fast=False and gather returns the exception
            continue
        name, value = item
        results[name] = value

    return results


class ParallelExecutor:
    """
    Reusable parallel executor with shared configuration.

    Provides a convenient way to run multiple parallel operations
    with consistent settings.

    Example:
        >>> executor = ParallelExecutor(concurrency=5, rate_limit=10.0)
        >>> async with executor:
        ...     results = await executor.map(items, process_item)
    """

    def __init__(
        self,
        concurrency: int = 10,
        batch_size: int = 50,
        rate_limit: float | None = None,
        burst_size: int = 20,
    ):
        """
        Initialize the parallel executor.

        Args:
            concurrency: Maximum concurrent operations
            batch_size: Default batch size for batch_execute
            rate_limit: Optional requests per second limit
            burst_size: Burst size for rate limiter
        """
        self.concurrency = concurrency
        self.batch_size = batch_size

        self._rate_limiter: AsyncRateLimiter | None = None
        if rate_limit is not None and rate_limit > 0:
            self._rate_limiter = AsyncRateLimiter(
                requests_per_second=rate_limit,
                burst_size=burst_size,
            )

    async def map(
        self,
        items: list[T],
        operation: Callable[[T], Coroutine[Any, Any, R]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ParallelResult[R]:
        """
        Apply an operation to all items in parallel.

        Args:
            items: Items to process
            operation: Async function to apply
            progress_callback: Optional progress callback

        Returns:
            ParallelResult with results and errors
        """
        return await batch_execute(
            items=items,
            operation=operation,
            batch_size=self.batch_size,
            concurrency=self.concurrency,
            rate_limiter=self._rate_limiter,
            progress_callback=progress_callback,
        )

    async def gather(
        self,
        coros: list[Coroutine[Any, Any, T]],
        return_exceptions: bool = False,
    ) -> list[T | Exception]:
        """
        Run coroutines concurrently with concurrency limit.

        Args:
            coros: Coroutines to execute
            return_exceptions: Whether to return exceptions in list

        Returns:
            List of results
        """
        return await gather_with_limit(
            coros=coros,
            limit=self.concurrency,
            return_exceptions=return_exceptions,
        )

    async def run_named(
        self,
        operations: dict[str, Coroutine[Any, Any, T]],
        fail_fast: bool = False,
    ) -> dict[str, T | Exception]:
        """
        Run named operations in parallel.

        Args:
            operations: Dict of name -> coroutine
            fail_fast: Cancel on first error

        Returns:
            Dict of name -> result/exception
        """
        return await run_parallel(
            operations=operations,
            concurrency=self.concurrency,
            fail_fast=fail_fast,
        )

    @property
    def stats(self) -> dict[str, Any] | None:
        """Get rate limiter statistics if available."""
        if self._rate_limiter is None:
            return None
        return self._rate_limiter.stats

    async def __aenter__(self) -> "ParallelExecutor":
        """Context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
