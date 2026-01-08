"""
Tests for GraphQL API adapter.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from spectryn.adapters.graphql_api import (
    SCHEMA_SDL,
    DataStore,
    GraphQLChangeType,
    GraphQLEpic,
    GraphQLPriority,
    GraphQLStatus,
    GraphQLStory,
    GraphQLSubtask,
    GraphQLSyncChange,
    GraphQLSyncOperation,
    GraphQLSyncResult,
    GraphQLWorkspaceStats,
    SimpleResolverRegistry,
    SpectraGraphQLServer,
    convert_epic,
    convert_story,
    convert_subtask,
    create_graphql_server,
)
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.graphql_api import (
    ExecutionContext,
    GraphQLRequest,
    GraphQLResponse,
    ServerConfig,
)


class TestGraphQLSchema:
    """Tests for GraphQL schema definition."""

    def test_schema_contains_types(self):
        """Test that schema contains expected types."""
        assert "type Epic" in SCHEMA_SDL
        assert "type Story" in SCHEMA_SDL
        assert "type Subtask" in SCHEMA_SDL
        assert "type Query" in SCHEMA_SDL
        assert "type Mutation" in SCHEMA_SDL
        assert "type Subscription" in SCHEMA_SDL

    def test_schema_contains_enums(self):
        """Test that schema contains expected enums."""
        assert "enum Status" in SCHEMA_SDL
        assert "enum Priority" in SCHEMA_SDL
        assert "enum TrackerType" in SCHEMA_SDL

    def test_schema_contains_input_types(self):
        """Test that schema contains input types."""
        assert "input EpicFilter" in SCHEMA_SDL
        assert "input StoryFilter" in SCHEMA_SDL
        assert "input CreateStoryInput" in SCHEMA_SDL
        assert "input UpdateStoryInput" in SCHEMA_SDL
        assert "input SyncInput" in SCHEMA_SDL


class TestGraphQLTypeConversion:
    """Tests for domain to GraphQL type conversion."""

    def test_convert_subtask(self):
        """Test converting domain Subtask to GraphQL Subtask."""
        subtask = Subtask(
            id="st-1",
            number=1,
            name="Implement feature",
            description="Feature details",
            story_points=2,
            status=Status.IN_PROGRESS,
            priority=Priority.HIGH,
            assignee="john",
        )

        result = convert_subtask(subtask)

        assert isinstance(result, GraphQLSubtask)
        assert result.id == "st-1"
        assert result.name == "Implement feature"
        assert result.status == GraphQLStatus.IN_PROGRESS
        assert result.priority == GraphQLPriority.HIGH
        assert result.assignee == "john"

    def test_convert_story(self):
        """Test converting domain UserStory to GraphQL Story."""
        story = UserStory(
            id=StoryId("US-001"),
            title="User login",
            description=Description(
                role="user",
                want="to log in securely",
                benefit="I can access my account",
            ),
            story_points=5,
            priority=Priority.HIGH,
            status=Status.PLANNED,
            assignee="jane",
            labels=["auth", "mvp"],
            acceptance_criteria=AcceptanceCriteria.from_list(["AC1", "AC2"]),
        )

        result = convert_story(story)

        assert isinstance(result, GraphQLStory)
        assert result.id == "US-001"
        assert result.title == "User login"
        assert result.story_points == 5
        assert result.priority == GraphQLPriority.HIGH
        assert result.status == GraphQLStatus.PLANNED
        assert "auth" in result.labels

    def test_convert_epic(self):
        """Test converting domain Epic to GraphQL Epic."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            story_points=3,
            status=Status.DONE,
        )
        epic = Epic(
            key=IssueKey("EPIC-1"),
            title="Test Epic",
            summary="Epic summary",
            status=Status.IN_PROGRESS,
            priority=Priority.MEDIUM,
            stories=[story],
        )

        result = convert_epic(epic)

        assert isinstance(result, GraphQLEpic)
        assert result.key == "EPIC-1"
        assert result.title == "Test Epic"
        assert result.status == GraphQLStatus.IN_PROGRESS
        assert len(result.stories) == 1
        assert result.total_story_points == 3
        assert result.completion_percentage == 100.0


class TestGraphQLDataClasses:
    """Tests for GraphQL data classes."""

    def test_graphql_subtask_to_dict(self):
        """Test GraphQL Subtask to_dict method."""
        subtask = GraphQLSubtask(
            id="st-1",
            number=1,
            name="Task",
            description="Desc",
            story_points=1,
            status=GraphQLStatus.PLANNED,
            priority=GraphQLPriority.LOW,
            assignee=None,
        )

        result = subtask.to_dict()

        assert result["id"] == "st-1"
        assert result["status"] == "PLANNED"
        assert result["priority"] == "LOW"

    def test_graphql_story_to_dict(self):
        """Test GraphQL Story to_dict method."""
        story = GraphQLStory(
            id="US-001",
            title="Story",
            description="Desc",
            acceptance_criteria=["AC1"],
            technical_notes="Notes",
            story_points=3,
            priority=GraphQLPriority.HIGH,
            status=GraphQLStatus.IN_PROGRESS,
            assignee="dev",
            labels=["label1"],
            sprint="Sprint 1",
            subtasks=[],
            commits=[],
            comments=[],
            attachments=[],
            external_key="JIRA-123",
            external_url="https://jira.example.com/JIRA-123",
            last_synced=datetime(2024, 1, 1, 12, 0, 0),
            sync_status="synced",
        )

        result = story.to_dict()

        assert result["id"] == "US-001"
        assert result["storyPoints"] == 3
        assert result["externalKey"] == "JIRA-123"
        assert result["lastSynced"] == "2024-01-01T12:00:00"

    def test_graphql_sync_result_to_dict(self):
        """Test GraphQL SyncResult to_dict method."""
        result = GraphQLSyncResult(
            success=True,
            session_id="sess-123",
            operation=GraphQLSyncOperation.PUSH,
            tracker="JIRA",
            epic_key="EPIC-1",
            total_items=10,
            created=2,
            updated=5,
            matched=3,
            skipped=0,
            failed=0,
            changes=[],
            errors=[],
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 1, 0),
            duration_ms=60000,
        )

        dict_result = result.to_dict()

        assert dict_result["success"] is True
        assert dict_result["sessionId"] == "sess-123"
        assert dict_result["operation"] == "PUSH"
        assert dict_result["created"] == 2
        assert dict_result["durationMs"] == 60000

    def test_graphql_workspace_stats_to_dict(self):
        """Test GraphQL WorkspaceStats to_dict method."""
        stats = GraphQLWorkspaceStats(
            total_epics=5,
            total_stories=50,
            total_subtasks=100,
            total_story_points=250,
            completed_story_points=150,
            stories_by_status={"DONE": 30, "IN_PROGRESS": 20},
            stories_by_priority={"HIGH": 15, "MEDIUM": 35},
            average_story_points=5.0,
            completion_percentage=60.0,
        )

        result = stats.to_dict()

        assert result["totalEpics"] == 5
        assert result["completionPercentage"] == 60.0
        assert result["storiesByStatus"]["DONE"] == 30


class TestSimpleResolverRegistry:
    """Tests for SimpleResolverRegistry."""

    def test_register_and_get_query_resolver(self):
        """Test registering and retrieving query resolver."""
        registry = SimpleResolverRegistry()

        def my_resolver():
            return {"data": "test"}

        registry.register_query("testQuery", my_resolver)

        resolver = registry.get_resolver("Query", "testQuery")
        assert resolver is my_resolver

    def test_register_mutation_resolver(self):
        """Test registering mutation resolver."""
        registry = SimpleResolverRegistry()

        def my_mutation():
            return True

        registry.register_mutation("testMutation", my_mutation)

        resolver = registry.get_resolver("Mutation", "testMutation")
        assert resolver is my_mutation

    def test_get_nonexistent_resolver(self):
        """Test getting non-existent resolver returns None."""
        registry = SimpleResolverRegistry()

        resolver = registry.get_resolver("Query", "nonexistent")
        assert resolver is None

    def test_register_type_resolver(self):
        """Test registering type-specific resolver."""
        registry = SimpleResolverRegistry()

        def story_resolver():
            return []

        registry.register_type_resolver("Epic", "stories", story_resolver)

        resolver = registry.get_resolver("Epic", "stories")
        assert resolver is story_resolver


class TestDataStore:
    """Tests for DataStore."""

    def test_empty_data_store(self):
        """Test empty data store."""
        store = DataStore()

        assert store.epics == {}
        assert store.active_syncs == {}
        assert store.sync_history == []

    def test_data_store_with_data(self):
        """Test data store with pre-loaded data."""
        epic = Epic(key=IssueKey("EPIC-1"), title="Test")
        store = DataStore(epics={"EPIC-1": epic})

        assert "EPIC-1" in store.epics
        assert store.epics["EPIC-1"].title == "Test"


class TestSpectraGraphQLServer:
    """Tests for SpectraGraphQLServer."""

    def test_create_server(self):
        """Test creating GraphQL server."""
        server = create_graphql_server(
            host="127.0.0.1",
            port=4000,
            enable_playground=False,
        )

        assert isinstance(server, SpectraGraphQLServer)
        assert server._config.host == "127.0.0.1"
        assert server._config.port == 4000
        assert server._config.enable_playground is False

    def test_server_not_running_initially(self):
        """Test server is not running initially."""
        server = create_graphql_server()

        assert server.is_running() is False

    def test_get_schema_sdl(self):
        """Test getting schema SDL."""
        server = create_graphql_server()

        schema = server.get_schema_sdl()

        assert "type Query" in schema
        assert "type Mutation" in schema

    def test_get_stats(self):
        """Test getting server stats."""
        server = create_graphql_server()

        stats = server.get_stats()

        assert stats.total_requests == 0
        assert stats.successful_requests == 0

    def test_load_epic(self):
        """Test loading epic into server."""
        server = create_graphql_server()
        epic = Epic(key=IssueKey("EPIC-1"), title="Test Epic")

        server.load_epic(epic)

        assert "EPIC-1" in server._data_store.epics

    def test_load_multiple_epics(self):
        """Test loading multiple epics."""
        server = create_graphql_server()
        epics = [
            Epic(key=IssueKey("EPIC-1"), title="Epic 1"),
            Epic(key=IssueKey("EPIC-2"), title="Epic 2"),
        ]

        server.load_epics(epics)

        assert len(server._data_store.epics) == 2

    def test_clear_data(self):
        """Test clearing server data."""
        server = create_graphql_server()
        server.load_epic(Epic(key=IssueKey("EPIC-1"), title="Test"))

        server.clear_data()

        assert len(server._data_store.epics) == 0

    def test_execute_health_query(self):
        """Test executing health query."""
        server = create_graphql_server()
        request = GraphQLRequest(query="{ health { healthy version } }")

        response = server._execute_sync(request)

        assert response.data is not None
        assert response.data["health"]["healthy"] is True

    def test_execute_workspace_stats_query(self):
        """Test executing workspace stats query."""
        server = create_graphql_server()

        # Load some data
        story = UserStory(id=StoryId("US-001"), title="Story", story_points=5)
        epic = Epic(key=IssueKey("EPIC-1"), title="Epic", stories=[story])
        server.load_epic(epic)

        request = GraphQLRequest(query="{ workspaceStats { totalEpics totalStories } }")
        response = server._execute_sync(request)

        assert response.data is not None
        assert response.data["workspaceStats"]["totalEpics"] == 1
        assert response.data["workspaceStats"]["totalStories"] == 1

    def test_execute_epics_query(self):
        """Test executing epics query."""
        server = create_graphql_server()

        # Load test data
        epic1 = Epic(key=IssueKey("EPIC-1"), title="First Epic")
        epic2 = Epic(key=IssueKey("EPIC-2"), title="Second Epic")
        server.load_epics([epic1, epic2])

        request = GraphQLRequest(query="{ epics { edges { node { key title } } } }")
        response = server._execute_sync(request)

        assert response.data is not None
        assert len(response.data["epics"]["edges"]) == 2

    def test_execute_epic_query_by_key(self):
        """Test executing single epic query by key."""
        server = create_graphql_server()
        epic = Epic(key=IssueKey("EPIC-1"), title="Test Epic", summary="Summary")
        server.load_epic(epic)

        request = GraphQLRequest(query='{ epic(key: "EPIC-1") { key title summary } }')
        response = server._execute_sync(request)

        assert response.data is not None
        assert response.data["epic"]["key"] == "EPIC-1"
        assert response.data["epic"]["title"] == "Test Epic"

    def test_execute_stories_query(self):
        """Test executing stories query."""
        server = create_graphql_server()

        story = UserStory(id=StoryId("US-001"), title="Test Story", story_points=3)
        epic = Epic(key=IssueKey("EPIC-1"), title="Epic", stories=[story])
        server.load_epic(epic)

        request = GraphQLRequest(query="{ stories { edges { node { id title } } } }")
        response = server._execute_sync(request)

        assert response.data is not None
        assert len(response.data["stories"]["edges"]) == 1

    def test_execute_story_query_by_id(self):
        """Test executing single story query by ID."""
        server = create_graphql_server()

        story = UserStory(id=StoryId("US-001"), title="Test Story", story_points=5)
        epic = Epic(key=IssueKey("EPIC-1"), title="Epic", stories=[story])
        server.load_epic(epic)

        request = GraphQLRequest(query='{ story(id: "US-001") { id title storyPoints } }')
        response = server._execute_sync(request)

        assert response.data is not None
        assert response.data["story"]["id"] == "US-001"
        assert response.data["story"]["storyPoints"] == 5

    def test_execute_search_stories(self):
        """Test executing story search query."""
        server = create_graphql_server()

        story1 = UserStory(id=StoryId("US-001"), title="Login feature", story_points=3)
        story2 = UserStory(id=StoryId("US-002"), title="Dashboard widget", story_points=5)
        epic = Epic(key=IssueKey("EPIC-1"), title="Epic", stories=[story1, story2])
        server.load_epic(epic)

        request = GraphQLRequest(
            query='{ searchStories(query: "login") { edges { node { title } } } }'
        )
        response = server._execute_sync(request)

        assert response.data is not None
        assert len(response.data["searchStories"]["edges"]) == 1
        assert response.data["searchStories"]["edges"][0]["node"]["title"] == "Login feature"

    def test_execute_sync_mutation(self):
        """Test executing sync mutation."""
        server = create_graphql_server()

        request = GraphQLRequest(
            query="mutation { sync(input: $input) { sessionId success } }",
            variables={
                "input": {
                    "markdownPath": "/path/to/file.md",
                    "tracker": "JIRA",
                }
            },
        )
        response = server._execute_sync(request)

        assert response.data is not None
        assert response.data["sync"]["sessionId"] is not None

    def test_add_request_middleware(self):
        """Test adding request middleware."""
        server = create_graphql_server()

        def middleware(request, context):
            return request

        server.add_request_middleware(middleware)

        assert len(server._request_middlewares) == 1

    def test_add_response_middleware(self):
        """Test adding response middleware."""
        server = create_graphql_server()

        def middleware(response, context):
            return response

        server.add_response_middleware(middleware)

        assert len(server._response_middlewares) == 1


class TestGraphQLSyncTypes:
    """Tests for GraphQL sync-related types."""

    def test_sync_change_to_dict(self):
        """Test SyncChange to_dict method."""
        change = GraphQLSyncChange(
            change_type=GraphQLChangeType.CREATED,
            item_type="Story",
            item_id="US-001",
            item_title="New Story",
            external_key="JIRA-123",
        )

        result = change.to_dict()

        assert result["changeType"] == "CREATED"
        assert result["itemType"] == "Story"
        assert result["externalKey"] == "JIRA-123"

    def test_sync_operations(self):
        """Test sync operation types."""
        assert GraphQLSyncOperation.PUSH.value == "PUSH"
        assert GraphQLSyncOperation.PULL.value == "PULL"
        assert GraphQLSyncOperation.BIDIRECTIONAL.value == "BIDIRECTIONAL"

    def test_change_types(self):
        """Test change types."""
        assert GraphQLChangeType.CREATED.value == "CREATED"
        assert GraphQLChangeType.UPDATED.value == "UPDATED"
        assert GraphQLChangeType.DELETED.value == "DELETED"
        assert GraphQLChangeType.MATCHED.value == "MATCHED"


class TestServerConfig:
    """Tests for ServerConfig in adapter context."""

    def test_config_passed_to_server(self):
        """Test config is properly passed to server."""
        config = ServerConfig(
            host="localhost",
            port=9000,
            path="/api",
            enable_playground=False,
        )

        server = SpectraGraphQLServer(config=config)

        assert server._config.host == "localhost"
        assert server._config.port == 9000
        assert server._config.path == "/api"
        assert server._config.enable_playground is False
