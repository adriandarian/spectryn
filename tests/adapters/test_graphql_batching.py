"""Tests for GraphQL batching."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from spectryn.adapters.graphql.batching import (
    BatchedQuery,
    BatchedQueryResult,
    BatchExecutionMode,
    BatchResult,
    GraphQLBatcher,
    GraphQLBatcherConfig,
    create_github_batcher,
    create_linear_batcher,
)


class TestBatchExecutionMode:
    """Tests for BatchExecutionMode enum."""

    def test_mode_values(self):
        """Test execution mode values."""
        assert BatchExecutionMode.COMBINED.value == "combined"
        assert BatchExecutionMode.PARALLEL.value == "parallel"
        assert BatchExecutionMode.SEQUENTIAL.value == "sequential"


class TestBatchedQuery:
    """Tests for BatchedQuery dataclass."""

    def test_default_values(self):
        """Test default query values."""
        query = BatchedQuery(query="{ viewer { login } }")

        assert query.query == "{ viewer { login } }"
        assert query.variables == {}
        assert query.operation_name is None
        assert query.alias is None
        assert query.priority == 0

    def test_with_variables(self):
        """Test query with variables."""
        query = BatchedQuery(
            query="query GetIssue($id: ID!) { issue(id: $id) { title } }",
            variables={"id": "123"},
            operation_name="GetIssue",
            alias="issue_1",
        )

        assert query.variables == {"id": "123"}
        assert query.operation_name == "GetIssue"
        assert query.alias == "issue_1"

    def test_query_hash(self):
        """Test query hash generation."""
        query1 = BatchedQuery(query="{ viewer { login } }")
        query2 = BatchedQuery(query="{ viewer { login } }")
        query3 = BatchedQuery(query="{ viewer { name } }")

        assert query1.query_hash == query2.query_hash
        assert query1.query_hash != query3.query_hash


class TestBatchedQueryResult:
    """Tests for BatchedQueryResult dataclass."""

    def test_default_values(self):
        """Test default result values."""
        result = BatchedQueryResult(alias="test")

        assert result.alias == "test"
        assert result.success is True
        assert result.data == {}
        assert result.errors == []
        assert result.execution_time_ms == 0.0

    def test_has_errors(self):
        """Test error detection."""
        result_ok = BatchedQueryResult(alias="ok")
        result_err = BatchedQueryResult(alias="err", errors=[{"message": "Something went wrong"}])

        assert result_ok.has_errors is False
        assert result_err.has_errors is True


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_default_values(self):
        """Test default batch result values."""
        result = BatchResult()

        assert result.success is True
        assert result.results == []
        assert result.total_queries == 0
        assert result.successful_queries == 0
        assert result.failed_queries == 0
        assert result.batches_executed == 0

    def test_get_result(self):
        """Test getting result by alias."""
        result = BatchResult(
            results=[
                BatchedQueryResult(alias="q1", data={"key": "value1"}),
                BatchedQueryResult(alias="q2", data={"key": "value2"}),
            ]
        )

        q1 = result.get_result("q1")
        assert q1 is not None
        assert q1.data == {"key": "value1"}

        q3 = result.get_result("q3")
        assert q3 is None

    def test_get_data(self):
        """Test getting data by alias."""
        result = BatchResult(
            results=[
                BatchedQueryResult(alias="q1", data={"viewer": {"login": "test"}}),
            ]
        )

        data = result.get_data("q1")
        assert data == {"viewer": {"login": "test"}}

        data_missing = result.get_data("q99")
        assert data_missing is None


class TestGraphQLBatcherConfig:
    """Tests for GraphQLBatcherConfig dataclass."""

    def test_default_values(self):
        """Test default configuration."""
        config = GraphQLBatcherConfig()

        assert config.max_queries_per_batch == 10
        assert config.max_batch_size_bytes == 100 * 1024
        assert config.default_mode == BatchExecutionMode.COMBINED
        assert config.parallel_workers == 4
        assert config.timeout_per_query == 30.0
        assert config.max_retries == 3

    def test_custom_values(self):
        """Test custom configuration."""
        config = GraphQLBatcherConfig(
            max_queries_per_batch=5,
            parallel_workers=8,
            api_endpoint="https://custom.api/graphql",
            headers={"Authorization": "Bearer token"},
        )

        assert config.max_queries_per_batch == 5
        assert config.parallel_workers == 8
        assert config.api_endpoint == "https://custom.api/graphql"


class TestGraphQLBatcher:
    """Tests for GraphQLBatcher."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return GraphQLBatcherConfig(
            api_endpoint="https://api.test.com/graphql",
            headers={"Authorization": "Bearer test-token"},
        )

    @pytest.fixture
    def batcher(self, config):
        """Create batcher instance."""
        return GraphQLBatcher(config)

    def test_add_query(self, batcher):
        """Test adding a query."""
        alias = batcher.add_query("{ viewer { login } }")

        assert alias == "q1"
        assert batcher.pending_count == 1

    def test_add_query_with_alias(self, batcher):
        """Test adding a query with custom alias."""
        alias = batcher.add_query("{ viewer { login } }", alias="my_query")

        assert alias == "my_query"
        assert batcher.pending_count == 1

    def test_add_multiple_queries(self, batcher):
        """Test adding multiple queries."""
        alias1 = batcher.add_query("{ viewer { login } }")
        alias2 = batcher.add_query("{ viewer { name } }")
        alias3 = batcher.add_query("{ viewer { email } }")

        assert alias1 == "q1"
        assert alias2 == "q2"
        assert alias3 == "q3"
        assert batcher.pending_count == 3

    def test_add_mutation(self, batcher):
        """Test adding a mutation."""
        batcher.add_mutation(
            "mutation CreateIssue($input: CreateIssueInput!) { createIssue(input: $input) { id } }",
            variables={"input": {"title": "Test"}},
        )

        assert batcher.pending_count == 1
        # Mutations should have lower priority (higher number)
        assert batcher._queries[0].priority == 100

    def test_clear(self, batcher):
        """Test clearing pending queries."""
        batcher.add_query("{ viewer { login } }")
        batcher.add_query("{ viewer { name } }")
        assert batcher.pending_count == 2

        batcher.clear()
        assert batcher.pending_count == 0

    def test_execute_empty(self, batcher):
        """Test executing with no queries."""
        result = batcher.execute()

        assert result.total_queries == 0
        assert result.success is True

    @patch("requests.Session.post")
    def test_execute_single_query(self, mock_post, batcher):
        """Test executing a single query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"viewer": {"login": "testuser"}}}
        mock_post.return_value = mock_response

        batcher.add_query("{ viewer { login } }", alias="viewer")
        result = batcher.execute()

        assert result.total_queries == 1
        assert result.successful_queries == 1
        assert result.failed_queries == 0
        assert result.success is True

        viewer_data = result.get_data("viewer")
        assert viewer_data is not None

    @patch("requests.Session.post")
    def test_execute_multiple_queries_sequential(self, mock_post, batcher):
        """Test executing multiple queries sequentially."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"result": "ok"}}
        mock_post.return_value = mock_response

        batcher.add_query("{ query1 }", alias="q1")
        batcher.add_query("{ query2 }", alias="q2")
        batcher.add_query("{ query3 }", alias="q3")

        result = batcher.execute(mode=BatchExecutionMode.SEQUENTIAL)

        assert result.total_queries == 3
        assert result.successful_queries == 3
        assert result.batches_executed == 3  # One request per query
        assert mock_post.call_count == 3

    @patch("requests.Session.post")
    def test_execute_with_error(self, mock_post, batcher):
        """Test handling query errors."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": None,
            "errors": [{"message": "Query failed"}],
        }
        mock_post.return_value = mock_response

        batcher.add_query("{ invalid }", alias="bad_query")
        result = batcher.execute()

        assert result.total_queries == 1
        assert result.failed_queries == 1
        assert result.success is False

        bad_result = result.get_result("bad_query")
        assert bad_result is not None
        assert bad_result.success is False
        assert len(bad_result.errors) > 0

    @patch("requests.Session.post")
    def test_execute_with_http_error(self, mock_post, batcher):
        """Test handling HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        batcher.add_query("{ viewer }", alias="test")
        result = batcher.execute()

        assert result.success is False
        assert result.failed_queries == 1

    @patch("requests.Session.post")
    def test_execute_parallel(self, mock_post, batcher):
        """Test parallel execution."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"result": "ok"}}
        mock_post.return_value = mock_response

        for i in range(5):
            batcher.add_query(f"{{ query{i} }}", alias=f"q{i}")

        result = batcher.execute(mode=BatchExecutionMode.PARALLEL)

        assert result.total_queries == 5
        assert result.successful_queries == 5
        assert result.batches_executed == 5

    def test_thread_safety(self, batcher):
        """Test thread-safe query addition."""
        results = []

        def add_queries(start: int):
            for i in range(10):
                alias = batcher.add_query(f"{{ query{start + i} }}")
                results.append(alias)

        threads = [threading.Thread(target=add_queries, args=(i * 10,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert batcher.pending_count == 50
        assert len(results) == 50


class TestBatching:
    """Tests for batch creation and execution."""

    @pytest.fixture
    def config(self):
        """Create config with small batch limits."""
        return GraphQLBatcherConfig(
            api_endpoint="https://api.test.com/graphql",
            max_queries_per_batch=3,
            max_batch_size_bytes=1000,
        )

    @pytest.fixture
    def batcher(self, config):
        """Create batcher."""
        return GraphQLBatcher(config)

    def test_batch_splitting_by_count(self, batcher):
        """Test batches are split by query count."""
        for i in range(7):
            batcher.add_query(f"{{ q{i} }}")

        # Access internal method to test batching
        queries = list(batcher._queries)
        batches = batcher._create_batches(queries)

        # Should create 3 batches: 3 + 3 + 1
        assert len(batches) == 3
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3
        assert len(batches[2]) == 1

    def test_batch_splitting_by_size(self, batcher):
        """Test batches are split by size."""
        # Add large queries that exceed size limit
        large_query = "{ " + "x" * 400 + " }"  # ~400 bytes each

        for i in range(5):
            batcher.add_query(large_query, alias=f"large_{i}")

        queries = list(batcher._queries)
        batches = batcher._create_batches(queries)

        # Should split into multiple batches due to size
        assert len(batches) >= 2


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_github_batcher(self):
        """Test GitHub batcher creation."""
        batcher = create_github_batcher("test-token")

        assert batcher.config.api_endpoint == "https://api.github.com/graphql"
        assert "Authorization" in batcher.config.headers
        assert batcher.config.default_mode == BatchExecutionMode.COMBINED

    def test_create_github_batcher_custom(self):
        """Test GitHub batcher with custom settings."""
        batcher = create_github_batcher(
            token="test-token",
            max_queries_per_batch=5,
            parallel_workers=8,
        )

        assert batcher.config.max_queries_per_batch == 5
        assert batcher.config.parallel_workers == 8

    def test_create_linear_batcher(self):
        """Test Linear batcher creation."""
        batcher = create_linear_batcher("lin_api_key")

        assert batcher.config.api_endpoint == "https://api.linear.app/graphql"
        assert batcher.config.default_mode == BatchExecutionMode.PARALLEL
        assert batcher.config.requests_per_second == 1.0  # More conservative

    def test_create_linear_batcher_custom(self):
        """Test Linear batcher with custom settings."""
        batcher = create_linear_batcher(
            api_key="lin_api_key",
            max_queries_per_batch=3,
            parallel_workers=4,
        )

        assert batcher.config.max_queries_per_batch == 3
        assert batcher.config.parallel_workers == 4


class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limit_applied(self):
        """Test that rate limiting is applied."""
        config = GraphQLBatcherConfig(
            api_endpoint="https://api.test.com/graphql",
            requests_per_second=10.0,  # 100ms between requests
        )
        batcher = GraphQLBatcher(config)

        # Simulate rate limiting
        batcher._last_request_time = time.time()
        start = time.time()
        batcher._apply_rate_limit()
        elapsed = time.time() - start

        # Should have waited approximately 100ms
        assert elapsed >= 0.09  # Allow some tolerance

    def test_rate_limit_disabled(self):
        """Test that rate limiting can be disabled."""
        config = GraphQLBatcherConfig(
            api_endpoint="https://api.test.com/graphql",
            requests_per_second=None,  # Disabled
        )
        batcher = GraphQLBatcher(config)

        start = time.time()
        batcher._apply_rate_limit()
        elapsed = time.time() - start

        # Should not wait
        assert elapsed < 0.01


class TestQueryCombination:
    """Tests for query combination functionality."""

    @pytest.fixture
    def batcher(self):
        """Create batcher for combination tests."""
        config = GraphQLBatcherConfig(
            api_endpoint="https://api.test.com/graphql",
        )
        return GraphQLBatcher(config)

    def test_add_alias_to_query(self, batcher):
        """Test alias addition to queries."""
        query = "query { viewer { login } }"
        aliased = batcher._add_alias_to_query(query, "_q0")

        assert "_q0_" in aliased

    def test_combine_queries(self, batcher):
        """Test query combination."""
        queries = [
            BatchedQuery(query="{ viewer { login } }", alias="q1"),
            BatchedQuery(query="{ viewer { name } }", alias="q2"),
        ]

        combined, alias_map = batcher._combine_queries(queries)

        assert "BatchedQuery" in combined
        assert "_q0" in alias_map
        assert "_q1" in alias_map
        assert alias_map["_q0"] == "q1"
        assert alias_map["_q1"] == "q2"
