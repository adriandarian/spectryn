"""
GraphQL API Adapter Package.

Provides a GraphQL API server for Spectra, enabling:
- Query epics, stories, and subtasks with filtering/pagination
- Execute sync operations via mutations
- Subscribe to real-time updates
- Interactive GraphQL Playground

Usage:
    from spectryn.adapters.graphql_api import create_graphql_server

    # Create and start server
    server = create_graphql_server(port=8080)
    await server.start()

    # Load data
    server.load_epics(epics)

    # Execute queries programmatically
    response = await server.execute(GraphQLRequest(
        query='query { epics { edges { node { key title } } } }'
    ))

    # Stop server
    await server.stop()
"""

from .schema import (
    SCHEMA_SDL,
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
)
from .server import (
    DataStore,
    SimpleResolverRegistry,
    SpectraGraphQLServer,
    convert_epic,
    convert_story,
    convert_subtask,
    create_graphql_server,
)


__all__ = [
    # Schema
    "SCHEMA_SDL",
    # Server
    "DataStore",
    "GraphQLChangeType",
    "GraphQLEpic",
    "GraphQLPriority",
    "GraphQLStatus",
    "GraphQLStory",
    "GraphQLSubtask",
    "GraphQLSyncChange",
    "GraphQLSyncOperation",
    "GraphQLSyncResult",
    "GraphQLWorkspaceStats",
    "SimpleResolverRegistry",
    "SpectraGraphQLServer",
    "convert_epic",
    "convert_story",
    "convert_subtask",
    "create_graphql_server",
]
