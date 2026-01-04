"""
Ports - Abstract interfaces for external dependencies.

Ports define the contracts that adapters must implement.
This enables dependency inversion and easy testing.
"""

from .async_tracker import AsyncIssueTrackerPort
from .config_provider import ConfigProviderPort
from .document_formatter import DocumentFormatterPort
from .document_output import (
    AuthenticationError as OutputAuthenticationError,
)
from .document_output import (
    DocumentOutputError,
    DocumentOutputPort,
)
from .document_output import (
    NotFoundError as OutputNotFoundError,
)
from .document_output import (
    PermissionError as OutputPermissionError,
)
from .document_output import (
    RateLimitError as OutputRateLimitError,
)
from .document_parser import DocumentParserPort, ParserError
from .graphql_api import (
    Connection,
    Edge,
    ExecutionContext,
    GraphQLError,
    GraphQLRequest,
    GraphQLResponse,
    GraphQLServerPort,
    OperationType,
    PageInfo,
    ResolverRegistry,
    SubscriptionEvent,
)
from .graphql_api import (
    ErrorCode as GraphQLErrorCode,
)
from .graphql_api import (
    ServerConfig as GraphQLServerConfig,
)
from .graphql_api import (
    ServerStats as GraphQLServerStats,
)
from .issue_tracker import (
    AuthenticationError,
    IssueTrackerError,
    IssueTrackerPort,
    NotFoundError,
    PermissionError,
    RateLimitError,
    TransientError,
    TransitionError,
)
from .plugin_marketplace import (
    AuthenticationError as MarketplaceAuthError,
)
from .plugin_marketplace import (
    InstallationError,
    InstallResult,
    MarketplaceInfo,
    MarketplacePlugin,
    PluginAuthor,
    PluginCategory,
    PluginMarketplaceError,
    PluginMarketplacePort,
    PluginNotFoundError,
    PluginStatus,
    PluginVersionInfo,
    PublishError,
    PublishResult,
    SearchQuery,
    SearchResult,
)
from .rate_limiting import (
    TRACKER_PRESETS,
    CircuitBreakerConfig,
    CircuitBreakerPort,
    CircuitOpenError,
    CircuitState,
    RateLimitConfig,
    RateLimitContext,
    RateLimiterPort,
    RateLimitScope,
    RateLimitStats,
    ResiliencePort,
    RetryAttempt,
    RetryConfig,
    RetryExhaustedError,
    RetryPolicyPort,
    RetryStrategy,
    TrackerRateLimits,
    calculate_backoff_delay,
    get_preset_for_name,
    get_tracker_preset,
    is_retryable_exception,
    is_retryable_status_code,
    parse_retry_after,
)
from .rate_limiting import (
    RateLimitError as ResilienceRateLimitError,
)
from .rate_limiting import (
    TrackerType as ResilienceTrackerType,
)
from .rest_api import (
    ConflictError as RestConflictError,
)
from .rest_api import (
    ErrorCode as RestErrorCode,
)
from .rest_api import (
    HttpMethod,
    HttpStatus,
    PagedResponse,
    RestApiError,
    RestApiServerPort,
    RestError,
    RestRequest,
    RestResponse,
    RouteInfo,
)
from .rest_api import (
    NotFoundError as RestNotFoundError,
)
from .rest_api import (
    ServerConfig as RestServerConfig,
)
from .rest_api import (
    ServerStats as RestServerStats,
)
from .rest_api import (
    ValidationError as RestValidationError,
)
from .state_store import (
    ConnectionError as StateConnectionError,
)
from .state_store import (
    MigrationError,
    QuerySortField,
    QuerySortOrder,
    StateQuery,
    StateStoreError,
    StateStorePort,
    StateSummary,
    StoreInfo,
)
from .state_store import (
    TransactionError as StateTransactionError,
)
from .sync_history import (
    ChangeRecord,
    HistoryQuery,
    HistoryStoreInfo,
    RollbackError,
    SyncHistoryEntry,
    SyncHistoryError,
    SyncHistoryPort,
    SyncOutcome,
    SyncStatistics,
    VelocityMetrics,
)
from .websocket import (
    BroadcastError,
    ConnectionInfo,
    MessageType,
    RoomError,
    ServerStats,
    WebSocketError,
    WebSocketMessage,
    WebSocketServerPort,
)
from .websocket import (
    ConnectionError as WebSocketConnectionError,
)


__all__ = [
    "AsyncIssueTrackerPort",
    "AuthenticationError",
    "ConfigProviderPort",
    "DocumentFormatterPort",
    # Output exceptions
    "DocumentOutputError",
    "DocumentOutputPort",
    "DocumentParserPort",
    # Issue tracker exceptions
    "IssueTrackerError",
    # Ports
    "IssueTrackerPort",
    "MigrationError",
    "NotFoundError",
    "OutputAuthenticationError",
    "OutputNotFoundError",
    "OutputPermissionError",
    "OutputRateLimitError",
    # Parser exceptions
    "ParserError",
    "PermissionError",
    "QuerySortField",
    "QuerySortOrder",
    "RateLimitError",
    # State store
    "StateConnectionError",
    "StateQuery",
    "StateStoreError",
    "StateStorePort",
    "StateSummary",
    "StateTransactionError",
    "StoreInfo",
    # Sync history
    "ChangeRecord",
    "HistoryQuery",
    "HistoryStoreInfo",
    "RollbackError",
    "SyncHistoryEntry",
    "SyncHistoryError",
    "SyncHistoryPort",
    "SyncOutcome",
    "SyncStatistics",
    "VelocityMetrics",
    # Plugin marketplace
    "InstallationError",
    "InstallResult",
    "MarketplaceAuthError",
    "MarketplaceInfo",
    "MarketplacePlugin",
    "PluginAuthor",
    "PluginCategory",
    "PluginMarketplaceError",
    "PluginMarketplacePort",
    "PluginNotFoundError",
    "PluginStatus",
    "PluginVersionInfo",
    "PublishError",
    "PublishResult",
    "SearchQuery",
    "SearchResult",
    "TransientError",
    "TransitionError",
    # WebSocket
    "BroadcastError",
    "ConnectionInfo",
    "MessageType",
    "RoomError",
    "ServerStats",
    "WebSocketConnectionError",
    "WebSocketError",
    "WebSocketMessage",
    "WebSocketServerPort",
    # GraphQL API
    "Connection",
    "Edge",
    "ExecutionContext",
    "GraphQLError",
    "GraphQLErrorCode",
    "GraphQLRequest",
    "GraphQLResponse",
    "GraphQLServerConfig",
    "GraphQLServerPort",
    "GraphQLServerStats",
    "OperationType",
    "PageInfo",
    "ResolverRegistry",
    "SubscriptionEvent",
    # REST API
    "HttpMethod",
    "HttpStatus",
    "PagedResponse",
    "RestApiError",
    "RestApiServerPort",
    "RestConflictError",
    "RestError",
    "RestErrorCode",
    "RestNotFoundError",
    "RestRequest",
    "RestResponse",
    "RestServerConfig",
    "RestServerStats",
    "RestValidationError",
    "RouteInfo",
    # Rate Limiting & Resilience
    "CircuitBreakerConfig",
    "CircuitBreakerPort",
    "CircuitOpenError",
    "CircuitState",
    "RateLimitConfig",
    "RateLimitContext",
    "RateLimiterPort",
    "RateLimitScope",
    "RateLimitStats",
    "ResiliencePort",
    "ResilienceRateLimitError",
    "ResilienceTrackerType",
    "RetryAttempt",
    "RetryConfig",
    "RetryExhaustedError",
    "RetryPolicyPort",
    "RetryStrategy",
    "TRACKER_PRESETS",
    "TrackerRateLimits",
    "calculate_backoff_delay",
    "get_preset_for_name",
    "get_tracker_preset",
    "is_retryable_exception",
    "is_retryable_status_code",
    "parse_retry_after",
]
