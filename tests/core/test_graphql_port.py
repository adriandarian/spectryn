"""
Tests for GraphQL API port interface.
"""

from datetime import datetime

import pytest

from spectryn.core.ports.graphql_api import (
    Connection,
    Edge,
    ErrorCode,
    ExecutionContext,
    GraphQLError,
    GraphQLRequest,
    GraphQLResponse,
    OperationType,
    PageInfo,
    ServerConfig,
    ServerStats,
    SubscriptionEvent,
)


class TestGraphQLError:
    """Tests for GraphQLError dataclass."""

    def test_default_error(self):
        """Test creating error with default code."""
        error = GraphQLError(message="Something went wrong")

        assert error.message == "Something went wrong"
        assert error.code == ErrorCode.INTERNAL_ERROR
        assert error.path is None
        assert error.locations is None
        assert error.extensions == {}

    def test_error_with_all_fields(self):
        """Test creating error with all fields."""
        error = GraphQLError(
            message="Invalid input",
            code=ErrorCode.INVALID_INPUT,
            path=["mutation", "createStory", "title"],
            locations=[{"line": 3, "column": 5}],
            extensions={"field": "title", "reason": "too short"},
        )

        assert error.message == "Invalid input"
        assert error.code == ErrorCode.INVALID_INPUT
        assert error.path == ["mutation", "createStory", "title"]
        assert error.locations == [{"line": 3, "column": 5}]
        assert error.extensions == {"field": "title", "reason": "too short"}

    def test_to_dict(self):
        """Test converting error to dictionary."""
        error = GraphQLError(
            message="Not found",
            code=ErrorCode.NOT_FOUND,
            path=["query", "epic"],
        )

        result = error.to_dict()

        assert result["message"] == "Not found"
        assert result["path"] == ["query", "epic"]
        assert result["extensions"]["code"] == "NOT_FOUND"


class TestGraphQLRequest:
    """Tests for GraphQLRequest dataclass."""

    def test_basic_request(self):
        """Test creating basic request."""
        request = GraphQLRequest(query="{ health { healthy } }")

        assert request.query == "{ health { healthy } }"
        assert request.operation_name is None
        assert request.variables == {}
        assert request.extensions == {}

    def test_request_with_variables(self):
        """Test request with variables."""
        request = GraphQLRequest(
            query="query GetEpic($key: ID!) { epic(key: $key) { title } }",
            operation_name="GetEpic",
            variables={"key": "EPIC-1"},
        )

        assert request.operation_name == "GetEpic"
        assert request.variables == {"key": "EPIC-1"}

    def test_from_dict(self):
        """Test creating request from dictionary."""
        data = {
            "query": "{ stories { edges { node { title } } } }",
            "operationName": "GetStories",
            "variables": {"limit": 10},
        }

        request = GraphQLRequest.from_dict(data)

        assert request.query == data["query"]
        assert request.operation_name == "GetStories"
        assert request.variables == {"limit": 10}

    def test_from_dict_minimal(self):
        """Test creating request from minimal dictionary."""
        data = {"query": "{ health { healthy } }"}

        request = GraphQLRequest.from_dict(data)

        assert request.query == data["query"]
        assert request.operation_name is None
        assert request.variables == {}

    def test_to_dict(self):
        """Test converting request to dictionary."""
        request = GraphQLRequest(
            query="query { epics { edges { node { key } } } }",
            operation_name="GetEpics",
            variables={"first": 5},
        )

        result = request.to_dict()

        assert result["query"] == request.query
        assert result["operationName"] == "GetEpics"
        assert result["variables"] == {"first": 5}


class TestGraphQLResponse:
    """Tests for GraphQLResponse dataclass."""

    def test_success_response(self):
        """Test creating successful response."""
        response = GraphQLResponse(data={"epic": {"key": "EPIC-1", "title": "Test Epic"}})

        assert response.data == {"epic": {"key": "EPIC-1", "title": "Test Epic"}}
        assert response.errors == []
        assert response.is_success is True
        assert response.has_errors is False

    def test_error_response(self):
        """Test creating error response."""
        error = GraphQLError(message="Not found", code=ErrorCode.NOT_FOUND)
        response = GraphQLResponse(errors=[error])

        assert response.data is None
        assert len(response.errors) == 1
        assert response.is_success is False
        assert response.has_errors is True

    def test_partial_response(self):
        """Test response with data and errors."""
        error = GraphQLError(message="Field error")
        response = GraphQLResponse(
            data={"epic": {"key": "EPIC-1"}},
            errors=[error],
        )

        assert response.data is not None
        assert response.has_errors is True
        # Still not fully successful because there are errors
        assert response.is_success is False

    def test_error_factory(self):
        """Test error factory method."""
        response = GraphQLResponse.error("Something failed", ErrorCode.INTERNAL_ERROR)

        assert response.data is None
        assert len(response.errors) == 1
        assert response.errors[0].message == "Something failed"

    def test_success_factory(self):
        """Test success factory method."""
        response = GraphQLResponse.success({"healthy": True})

        assert response.data == {"healthy": True}
        assert response.errors == []
        assert response.is_success is True

    def test_to_dict(self):
        """Test converting response to dictionary."""
        response = GraphQLResponse(
            data={"key": "value"},
            extensions={"timing": {"durationMs": 15}},
        )

        result = response.to_dict()

        assert result["data"] == {"key": "value"}
        assert "errors" not in result
        assert result["extensions"]["timing"]["durationMs"] == 15


class TestPageInfo:
    """Tests for PageInfo dataclass."""

    def test_default_page_info(self):
        """Test default page info."""
        page_info = PageInfo()

        assert page_info.has_next_page is False
        assert page_info.has_previous_page is False
        assert page_info.start_cursor is None
        assert page_info.end_cursor is None
        assert page_info.total_count is None

    def test_page_info_with_values(self):
        """Test page info with values."""
        page_info = PageInfo(
            has_next_page=True,
            has_previous_page=False,
            start_cursor="cursor1",
            end_cursor="cursor10",
            total_count=50,
        )

        assert page_info.has_next_page is True
        assert page_info.start_cursor == "cursor1"
        assert page_info.total_count == 50

    def test_to_dict(self):
        """Test converting page info to dictionary."""
        page_info = PageInfo(
            has_next_page=True,
            start_cursor="abc",
            end_cursor="xyz",
            total_count=100,
        )

        result = page_info.to_dict()

        assert result["hasNextPage"] is True
        assert result["hasPreviousPage"] is False
        assert result["startCursor"] == "abc"
        assert result["endCursor"] == "xyz"
        assert result["totalCount"] == 100


class TestEdgeAndConnection:
    """Tests for Edge and Connection dataclasses."""

    def test_edge(self):
        """Test creating an edge."""
        edge = Edge(node={"id": "1", "title": "Story"}, cursor="cursor1")

        assert edge.node == {"id": "1", "title": "Story"}
        assert edge.cursor == "cursor1"

    def test_edge_to_dict(self):
        """Test converting edge to dictionary."""
        edge = Edge(node={"id": "1"}, cursor="c1")

        result = edge.to_dict(lambda x: x)

        assert result["node"] == {"id": "1"}
        assert result["cursor"] == "c1"

    def test_connection(self):
        """Test creating a connection."""
        edges = [
            Edge(node={"id": "1"}, cursor="c1"),
            Edge(node={"id": "2"}, cursor="c2"),
        ]
        page_info = PageInfo(has_next_page=True, total_count=10)

        connection = Connection(edges=edges, page_info=page_info)

        assert len(connection.edges) == 2
        assert connection.page_info.total_count == 10

    def test_connection_to_dict(self):
        """Test converting connection to dictionary."""
        edges = [Edge(node={"id": "1"}, cursor="c1")]
        page_info = PageInfo(has_next_page=False, total_count=1)
        connection = Connection(edges=edges, page_info=page_info)

        result = connection.to_dict(lambda x: x)

        assert len(result["edges"]) == 1
        assert result["pageInfo"]["totalCount"] == 1


class TestSubscriptionEvent:
    """Tests for SubscriptionEvent dataclass."""

    def test_subscription_event(self):
        """Test creating subscription event."""
        event = SubscriptionEvent(
            subscription_id="sub-123",
            event_type="storyUpdated",
            data={"id": "story-1", "title": "Updated Story"},
        )

        assert event.subscription_id == "sub-123"
        assert event.event_type == "storyUpdated"
        assert event.data["title"] == "Updated Story"
        assert isinstance(event.timestamp, datetime)

    def test_to_dict(self):
        """Test converting event to dictionary."""
        event = SubscriptionEvent(
            subscription_id="sub-1",
            event_type="syncProgress",
            data={"progress": 50},
        )

        result = event.to_dict()

        assert result["subscriptionId"] == "sub-1"
        assert result["eventType"] == "syncProgress"
        assert result["data"]["progress"] == 50
        assert "timestamp" in result


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_execution_context(self):
        """Test creating execution context."""
        request = GraphQLRequest(query="{ health { healthy } }")
        context = ExecutionContext(
            request=request,
            user={"id": "user-1", "role": "admin"},
        )

        assert context.request == request
        assert context.user["id"] == "user-1"
        assert context.request_id != ""  # Auto-generated
        assert isinstance(context.start_time, datetime)

    def test_auto_generated_request_id(self):
        """Test that request ID is auto-generated."""
        request = GraphQLRequest(query="{ }")
        context = ExecutionContext(request=request)

        assert len(context.request_id) == 36  # UUID length


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_default_config(self):
        """Test default server configuration."""
        config = ServerConfig()

        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.path == "/graphql"
        assert config.enable_playground is True
        assert config.enable_introspection is True
        assert config.timeout == 30.0
        assert config.enable_subscriptions is True

    def test_custom_config(self):
        """Test custom server configuration."""
        config = ServerConfig(
            host="127.0.0.1",
            port=4000,
            path="/api/graphql",
            enable_playground=False,
            max_query_depth=10,
        )

        assert config.host == "127.0.0.1"
        assert config.port == 4000
        assert config.path == "/api/graphql"
        assert config.enable_playground is False
        assert config.max_query_depth == 10


class TestServerStats:
    """Tests for ServerStats dataclass."""

    def test_default_stats(self):
        """Test default server statistics."""
        stats = ServerStats()

        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0
        assert stats.active_subscriptions == 0
        assert stats.average_response_time_ms == 0.0
        assert isinstance(stats.started_at, datetime)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_codes_exist(self):
        """Test that all expected error codes exist."""
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.UNAUTHORIZED.value == "UNAUTHORIZED"
        assert ErrorCode.NOT_FOUND.value == "NOT_FOUND"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
        assert ErrorCode.SYNC_IN_PROGRESS.value == "SYNC_IN_PROGRESS"


class TestOperationType:
    """Tests for OperationType enum."""

    def test_operation_types(self):
        """Test operation types."""
        assert OperationType.QUERY.value == "query"
        assert OperationType.MUTATION.value == "mutation"
        assert OperationType.SUBSCRIPTION.value == "subscription"
