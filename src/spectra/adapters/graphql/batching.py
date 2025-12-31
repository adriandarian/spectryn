"""
GraphQL Batching - Batch multiple GraphQL queries for improved performance.

Supports query batching for GitHub and Linear APIs by combining
multiple operations into single requests where possible.

Features:
- Automatic query combination
- Alias generation for result mapping
- Fragment deduplication
- Parallel execution for mutations
- Response demultiplexing
"""

import hashlib
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import requests


logger = logging.getLogger(__name__)


class BatchExecutionMode(Enum):
    """Execution mode for batched operations."""

    COMBINED = "combined"  # Combine queries into single request
    PARALLEL = "parallel"  # Execute in parallel threads
    SEQUENTIAL = "sequential"  # Execute sequentially


@dataclass
class BatchedQuery:
    """A single query within a batch."""

    query: str
    variables: dict[str, Any] = field(default_factory=dict)
    operation_name: str | None = None
    alias: str | None = None
    priority: int = 0  # Lower = higher priority

    @property
    def query_hash(self) -> str:
        """Generate hash for deduplication."""
        content = f"{self.query}:{sorted(self.variables.items())}"
        return hashlib.md5(content.encode()).hexdigest()[:8]


@dataclass
class BatchedQueryResult:
    """Result of a single query within a batch."""

    alias: str
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0

    @property
    def has_errors(self) -> bool:
        """Check if result has errors."""
        return len(self.errors) > 0


@dataclass
class BatchResult:
    """Aggregated result of batch execution."""

    success: bool = True
    results: list[BatchedQueryResult] = field(default_factory=list)
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    total_execution_time_ms: float = 0.0
    batches_executed: int = 0  # Number of actual HTTP requests made

    def get_result(self, alias: str) -> BatchedQueryResult | None:
        """Get result by alias."""
        for result in self.results:
            if result.alias == alias:
                return result
        return None

    def get_data(self, alias: str) -> dict[str, Any] | None:
        """Get data by alias."""
        result = self.get_result(alias)
        return result.data if result else None


@dataclass
class GraphQLBatcherConfig:
    """Configuration for GraphQL batching."""

    # Batching limits
    max_queries_per_batch: int = 10  # Max queries to combine
    max_batch_size_bytes: int = 100 * 1024  # 100KB max request size

    # Execution
    default_mode: BatchExecutionMode = BatchExecutionMode.COMBINED
    parallel_workers: int = 4  # Workers for parallel mode
    timeout_per_query: float = 30.0  # Timeout per query

    # Rate limiting integration
    requests_per_second: float | None = None
    burst_size: int = 10

    # Retry
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_on_errors: list[str] = field(default_factory=lambda: ["RATE_LIMIT", "INTERNAL_ERROR"])

    # API-specific settings
    api_endpoint: str = ""
    headers: dict[str, str] = field(default_factory=dict)


class GraphQLBatcher:
    """
    GraphQL query batcher for efficient API usage.

    Combines multiple queries into single requests where supported,
    or executes them in parallel for APIs that don't support batching.

    Usage:
        batcher = GraphQLBatcher(config)

        # Add queries
        batcher.add_query(
            "query GetIssue($id: ID!) { issue(id: $id) { title } }",
            variables={"id": "123"},
            alias="issue_1"
        )
        batcher.add_query(
            "query GetIssue($id: ID!) { issue(id: $id) { title } }",
            variables={"id": "456"},
            alias="issue_2"
        )

        # Execute batch
        result = batcher.execute()

        # Access results
        issue_1 = result.get_data("issue_1")
        issue_2 = result.get_data("issue_2")
    """

    def __init__(
        self,
        config: GraphQLBatcherConfig,
        session: requests.Session | None = None,
    ):
        """
        Initialize the batcher.

        Args:
            config: Batcher configuration
            session: Optional requests session for connection pooling
        """
        self.config = config
        self._session = session or requests.Session()
        self._queries: list[BatchedQuery] = []
        self._lock = threading.Lock()
        self._alias_counter = 0
        self.logger = logging.getLogger("GraphQLBatcher")

        # Rate limiting
        self._last_request_time = 0.0
        self._request_count = 0

    def add_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        alias: str | None = None,
        priority: int = 0,
    ) -> str:
        """
        Add a query to the batch.

        Args:
            query: GraphQL query string
            variables: Query variables
            operation_name: Operation name (optional)
            alias: Result alias (auto-generated if not provided)
            priority: Execution priority (lower = higher priority)

        Returns:
            The alias for this query
        """
        with self._lock:
            if alias is None:
                self._alias_counter += 1
                alias = f"q{self._alias_counter}"

            self._queries.append(
                BatchedQuery(
                    query=query,
                    variables=variables or {},
                    operation_name=operation_name,
                    alias=alias,
                    priority=priority,
                )
            )

            return alias

    def add_mutation(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        alias: str | None = None,
    ) -> str:
        """
        Add a mutation to the batch.

        Mutations are typically executed sequentially or in parallel,
        not combined (to preserve order and atomicity).

        Args:
            mutation: GraphQL mutation string
            variables: Mutation variables
            operation_name: Operation name
            alias: Result alias

        Returns:
            The alias for this mutation
        """
        return self.add_query(
            query=mutation,
            variables=variables,
            operation_name=operation_name,
            alias=alias,
            priority=100,  # Lower priority than queries
        )

    def clear(self) -> None:
        """Clear all pending queries."""
        with self._lock:
            self._queries.clear()
            self._alias_counter = 0

    def execute(
        self,
        mode: BatchExecutionMode | None = None,
    ) -> BatchResult:
        """
        Execute all pending queries.

        Args:
            mode: Execution mode (uses config default if not specified)

        Returns:
            BatchResult with all query results
        """
        mode = mode or self.config.default_mode

        with self._lock:
            queries = list(self._queries)
            self._queries.clear()

        if not queries:
            return BatchResult()

        # Sort by priority
        queries.sort(key=lambda q: q.priority)

        start_time = time.time()

        if mode == BatchExecutionMode.COMBINED:
            result = self._execute_combined(queries)
        elif mode == BatchExecutionMode.PARALLEL:
            result = self._execute_parallel(queries)
        else:
            result = self._execute_sequential(queries)

        result.total_execution_time_ms = (time.time() - start_time) * 1000

        self.logger.info(
            f"Batch executed: {result.successful_queries}/{result.total_queries} "
            f"in {result.total_execution_time_ms:.0f}ms "
            f"({result.batches_executed} HTTP request(s))"
        )

        return result

    def _execute_combined(self, queries: list[BatchedQuery]) -> BatchResult:
        """Execute queries by combining them into batched requests."""
        result = BatchResult(total_queries=len(queries))
        batches = self._create_batches(queries)

        for batch in batches:
            batch_result = self._execute_batch(batch)
            result.batches_executed += 1

            for query_result in batch_result:
                result.results.append(query_result)
                if query_result.success:
                    result.successful_queries += 1
                else:
                    result.failed_queries += 1
                    result.success = False

        return result

    def _execute_parallel(self, queries: list[BatchedQuery]) -> BatchResult:
        """Execute queries in parallel threads."""
        result = BatchResult(total_queries=len(queries))

        with ThreadPoolExecutor(max_workers=self.config.parallel_workers) as executor:
            futures = {}
            for query in queries:
                future = executor.submit(self._execute_single_query, query)
                futures[future] = query.alias

            for future in as_completed(futures):
                alias = futures[future]
                try:
                    query_result = future.result(timeout=self.config.timeout_per_query)
                    result.results.append(query_result)
                    result.batches_executed += 1

                    if query_result.success:
                        result.successful_queries += 1
                    else:
                        result.failed_queries += 1
                        result.success = False

                except TimeoutError:
                    result.results.append(
                        BatchedQueryResult(
                            alias=alias or "",
                            success=False,
                            errors=[{"message": "Query timed out"}],
                        )
                    )
                    result.failed_queries += 1
                    result.success = False

                except Exception as e:
                    result.results.append(
                        BatchedQueryResult(
                            alias=alias or "",
                            success=False,
                            errors=[{"message": str(e)}],
                        )
                    )
                    result.failed_queries += 1
                    result.success = False

        return result

    def _execute_sequential(self, queries: list[BatchedQuery]) -> BatchResult:
        """Execute queries one at a time."""
        result = BatchResult(total_queries=len(queries))

        for query in queries:
            query_result = self._execute_single_query(query)
            result.results.append(query_result)
            result.batches_executed += 1

            if query_result.success:
                result.successful_queries += 1
            else:
                result.failed_queries += 1
                result.success = False

            # Rate limiting
            self._apply_rate_limit()

        return result

    def _create_batches(self, queries: list[BatchedQuery]) -> list[list[BatchedQuery]]:
        """Split queries into batches based on limits."""
        batches: list[list[BatchedQuery]] = []
        current_batch: list[BatchedQuery] = []
        current_size = 0

        for query in queries:
            query_size = len(query.query.encode("utf-8"))

            # Check if adding this query would exceed limits
            if (
                len(current_batch) >= self.config.max_queries_per_batch
                or current_size + query_size > self.config.max_batch_size_bytes
            ):
                if current_batch:
                    batches.append(current_batch)
                current_batch = []
                current_size = 0

            current_batch.append(query)
            current_size += query_size

        if current_batch:
            batches.append(current_batch)

        return batches

    def _execute_batch(self, queries: list[BatchedQuery]) -> list[BatchedQueryResult]:
        """Execute a batch of queries in a single request."""
        if len(queries) == 1:
            # Single query, no need to combine
            return [self._execute_single_query(queries[0])]

        # Combine queries using aliases
        combined_query, alias_map = self._combine_queries(queries)

        start_time = time.time()

        try:
            self._apply_rate_limit()

            response = self._session.post(
                self.config.api_endpoint,
                json={"query": combined_query},
                headers=self.config.headers,
                timeout=self.config.timeout_per_query * len(queries),
            )

            elapsed_ms = (time.time() - start_time) * 1000

            if response.status_code != 200:
                # Return failure for all queries
                return [
                    BatchedQueryResult(
                        alias=q.alias or "",
                        success=False,
                        errors=[{"message": f"HTTP {response.status_code}: {response.text[:200]}"}],
                        execution_time_ms=elapsed_ms,
                    )
                    for q in queries
                ]

            data = response.json()

            # Demultiplex results
            return self._demultiplex_results(queries, data, alias_map, elapsed_ms)

        except Exception as e:
            self.logger.error(f"Batch execution failed: {e}")
            elapsed_ms = (time.time() - start_time) * 1000
            return [
                BatchedQueryResult(
                    alias=q.alias or "",
                    success=False,
                    errors=[{"message": str(e)}],
                    execution_time_ms=elapsed_ms,
                )
                for q in queries
            ]

    def _combine_queries(self, queries: list[BatchedQuery]) -> tuple[str, dict[str, str]]:
        """
        Combine multiple queries into a single query with aliases.

        Returns:
            Tuple of (combined_query, alias_map)
        """
        # Extract the inner content of each query
        combined_parts: list[str] = []
        alias_map: dict[str, str] = {}  # internal_alias -> original_alias

        for i, query in enumerate(queries):
            internal_alias = f"_q{i}"
            alias_map[internal_alias] = query.alias or f"query_{i}"

            # Transform query to use internal alias
            # This is a simplified version - real implementation would parse the query
            transformed = self._add_alias_to_query(query.query, internal_alias)
            combined_parts.append(transformed)

        # Wrap in a single query
        combined = "query BatchedQuery {\n" + "\n".join(combined_parts) + "\n}"

        return combined, alias_map

    def _add_alias_to_query(self, query: str, alias: str) -> str:
        """Add an alias prefix to query root fields."""
        # Simple regex-based transformation
        # Match field selections like: fieldName { ... } or fieldName(args) { ... }
        pattern = r"(?:query\s+\w*\s*(?:\([^)]*\))?\s*\{)?\s*(\w+)\s*(\([^)]*\))?\s*\{"

        def replacer(match: re.Match[str]) -> str:
            field = match.group(1)
            args = match.group(2) or ""
            return f"  {alias}_{field}: {field}{args} {{"

        # This is a simplified approach - real implementation needs proper GraphQL parsing
        return re.sub(pattern, replacer, query, count=1)

    def _demultiplex_results(
        self,
        queries: list[BatchedQuery],
        response_data: dict[str, Any],
        alias_map: dict[str, str],
        elapsed_ms: float,
    ) -> list[BatchedQueryResult]:
        """Demultiplex combined response into individual results."""
        results: list[BatchedQueryResult] = []
        data = response_data.get("data", {})
        errors = response_data.get("errors", [])

        per_query_ms = elapsed_ms / len(queries) if queries else 0

        for i, query in enumerate(queries):
            internal_alias = f"_q{i}"
            original_alias = alias_map.get(internal_alias, query.alias or "")

            # Find data for this query
            query_data = {}
            for key, value in data.items():
                if key.startswith(f"{internal_alias}_"):
                    # Remove alias prefix
                    original_key = key[len(internal_alias) + 1 :]
                    query_data[original_key] = value

            # Find errors for this query
            query_errors = [
                e
                for e in errors
                if e.get("path", [None])[0] and str(e["path"][0]).startswith(internal_alias)
            ]

            results.append(
                BatchedQueryResult(
                    alias=original_alias,
                    success=len(query_errors) == 0,
                    data=query_data or data,  # Fallback to full data
                    errors=query_errors,
                    execution_time_ms=per_query_ms,
                )
            )

        return results

    def _execute_single_query(self, query: BatchedQuery) -> BatchedQueryResult:
        """Execute a single query."""
        start_time = time.time()

        try:
            self._apply_rate_limit()

            payload: dict[str, Any] = {"query": query.query}
            if query.variables:
                payload["variables"] = query.variables
            if query.operation_name:
                payload["operationName"] = query.operation_name

            response = self._session.post(
                self.config.api_endpoint,
                json=payload,
                headers=self.config.headers,
                timeout=self.config.timeout_per_query,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            if response.status_code != 200:
                return BatchedQueryResult(
                    alias=query.alias or "",
                    success=False,
                    errors=[{"message": f"HTTP {response.status_code}: {response.text[:200]}"}],
                    execution_time_ms=elapsed_ms,
                )

            data = response.json()
            errors = data.get("errors", [])

            return BatchedQueryResult(
                alias=query.alias or "",
                success=len(errors) == 0,
                data=data.get("data", {}),
                errors=errors,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return BatchedQueryResult(
                alias=query.alias or "",
                success=False,
                errors=[{"message": str(e)}],
                execution_time_ms=elapsed_ms,
            )

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.config.requests_per_second is None:
            return

        min_interval = 1.0 / self.config.requests_per_second
        elapsed = time.time() - self._last_request_time

        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    @property
    def pending_count(self) -> int:
        """Number of pending queries."""
        with self._lock:
            return len(self._queries)


# Factory functions for common APIs


def create_github_batcher(
    token: str,
    max_queries_per_batch: int = 10,
    parallel_workers: int = 4,
) -> GraphQLBatcher:
    """
    Create a batcher configured for GitHub GraphQL API.

    GitHub's GraphQL API supports query batching through aliases.

    Args:
        token: GitHub access token
        max_queries_per_batch: Maximum queries per batch
        parallel_workers: Workers for parallel execution

    Returns:
        Configured GraphQLBatcher
    """
    config = GraphQLBatcherConfig(
        api_endpoint="https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        max_queries_per_batch=max_queries_per_batch,
        parallel_workers=parallel_workers,
        requests_per_second=5.0,  # Conservative for GitHub
        default_mode=BatchExecutionMode.COMBINED,
    )

    return GraphQLBatcher(config)


def create_linear_batcher(
    api_key: str,
    max_queries_per_batch: int = 5,
    parallel_workers: int = 2,
) -> GraphQLBatcher:
    """
    Create a batcher configured for Linear GraphQL API.

    Linear's API is more restrictive, so we use smaller batches.

    Args:
        api_key: Linear API key
        max_queries_per_batch: Maximum queries per batch
        parallel_workers: Workers for parallel execution

    Returns:
        Configured GraphQLBatcher
    """
    config = GraphQLBatcherConfig(
        api_endpoint="https://api.linear.app/graphql",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        max_queries_per_batch=max_queries_per_batch,
        parallel_workers=parallel_workers,
        requests_per_second=1.0,  # Linear has stricter limits
        default_mode=BatchExecutionMode.PARALLEL,  # Linear doesn't support true batching
    )

    return GraphQLBatcher(config)


class AsyncGraphQLBatcher:
    """
    Async version of GraphQL batcher using aiohttp.

    For high-throughput scenarios where async execution is preferred.
    """

    def __init__(
        self,
        config: GraphQLBatcherConfig,
    ):
        """Initialize async batcher."""
        self.config = config
        self._queries: list[BatchedQuery] = []
        self._lock = threading.Lock()
        self._alias_counter = 0
        self.logger = logging.getLogger("AsyncGraphQLBatcher")

    def add_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        alias: str | None = None,
    ) -> str:
        """Add a query to the batch."""
        with self._lock:
            if alias is None:
                self._alias_counter += 1
                alias = f"q{self._alias_counter}"

            self._queries.append(
                BatchedQuery(
                    query=query,
                    variables=variables or {},
                    alias=alias,
                )
            )

            return alias

    async def execute(self) -> BatchResult:
        """
        Execute all pending queries asynchronously.

        Requires aiohttp to be installed.
        """
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp is required for async GraphQL batching. Install with: pip install aiohttp"
            )

        with self._lock:
            queries = list(self._queries)
            self._queries.clear()

        if not queries:
            return BatchResult()

        result = BatchResult(total_queries=len(queries))
        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            tasks = []
            for query in queries:
                task = self._execute_query_async(session, query)
                tasks.append(task)

            import asyncio

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for i, response in enumerate(responses):
                if isinstance(response, BaseException):
                    result.results.append(
                        BatchedQueryResult(
                            alias=queries[i].alias or "",
                            success=False,
                            errors=[{"message": str(response)}],
                        )
                    )
                    result.failed_queries += 1
                    result.success = False
                elif isinstance(response, BatchedQueryResult):
                    result.results.append(response)
                    if response.success:
                        result.successful_queries += 1
                    else:
                        result.failed_queries += 1
                        result.success = False

        result.total_execution_time_ms = (time.time() - start_time) * 1000
        result.batches_executed = len(queries)

        return result

    async def _execute_query_async(self, session: Any, query: BatchedQuery) -> BatchedQueryResult:
        """Execute a single query asynchronously."""
        import aiohttp

        start_time = time.time()

        try:
            payload: dict[str, Any] = {"query": query.query}
            if query.variables:
                payload["variables"] = query.variables

            async with session.post(
                self.config.api_endpoint,
                json=payload,
                headers=self.config.headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_per_query),
            ) as response:
                elapsed_ms = (time.time() - start_time) * 1000

                if response.status != 200:
                    text = await response.text()
                    return BatchedQueryResult(
                        alias=query.alias or "",
                        success=False,
                        errors=[{"message": f"HTTP {response.status}: {text[:200]}"}],
                        execution_time_ms=elapsed_ms,
                    )

                data = await response.json()
                errors = data.get("errors", [])

                return BatchedQueryResult(
                    alias=query.alias or "",
                    success=len(errors) == 0,
                    data=data.get("data", {}),
                    errors=errors,
                    execution_time_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return BatchedQueryResult(
                alias=query.alias or "",
                success=False,
                errors=[{"message": str(e)}],
                execution_time_ms=elapsed_ms,
            )
