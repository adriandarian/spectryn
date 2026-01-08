"""
WebSocket Port - Abstract interface for real-time communication.

WebSocket support enables real-time sync updates, allowing clients to:
- Subscribe to sync events as they happen
- Receive live progress updates
- Get instant notifications of changes
- Build real-time dashboards

Concepts:
- Connection: A WebSocket client connection
- Room: A logical grouping for targeted broadcasts (e.g., per-epic)
- Message: JSON payload sent to connected clients
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MessageType(Enum):
    """Types of WebSocket messages."""

    # Sync events
    SYNC_STARTED = "sync:started"
    SYNC_PROGRESS = "sync:progress"
    SYNC_COMPLETED = "sync:completed"
    SYNC_ERROR = "sync:error"

    # Story events
    STORY_MATCHED = "story:matched"
    STORY_UPDATED = "story:updated"
    STORY_CREATED = "story:created"

    # Subtask events
    SUBTASK_CREATED = "subtask:created"
    SUBTASK_UPDATED = "subtask:updated"

    # Status events
    STATUS_CHANGED = "status:changed"

    # Comment events
    COMMENT_ADDED = "comment:added"

    # Pull (reverse sync) events
    PULL_STARTED = "pull:started"
    PULL_PROGRESS = "pull:progress"
    PULL_COMPLETED = "pull:completed"

    # Conflict events
    CONFLICT_DETECTED = "conflict:detected"
    CONFLICT_RESOLVED = "conflict:resolved"

    # Connection events
    CONNECTED = "connection:connected"
    DISCONNECTED = "connection:disconnected"
    SUBSCRIBED = "connection:subscribed"
    UNSUBSCRIBED = "connection:unsubscribed"

    # System events
    HEARTBEAT = "system:heartbeat"
    ERROR = "system:error"
    SERVER_SHUTDOWN = "system:shutdown"


@dataclass(frozen=True)
class WebSocketMessage:
    """
    A message to be sent via WebSocket.

    Attributes:
        type: The message type for client routing.
        payload: The message data.
        room: Optional room to target (None = broadcast to all).
        timestamp: When the message was created.
        message_id: Unique identifier for the message.
    """

    type: MessageType
    payload: dict[str, Any] = field(default_factory=dict)
    room: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: "")

    def __post_init__(self) -> None:
        """Generate message ID if not provided."""
        if not self.message_id:
            from uuid import uuid4

            object.__setattr__(self, "message_id", str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "payload": self.payload,
            "room": self.room,
            "timestamp": self.timestamp.isoformat(),
            "messageId": self.message_id,
        }


@dataclass
class ConnectionInfo:
    """
    Information about a WebSocket connection.

    Attributes:
        connection_id: Unique identifier for the connection.
        connected_at: When the connection was established.
        rooms: Rooms the connection is subscribed to.
        metadata: Additional connection metadata (e.g., client info).
        last_activity: Time of last message sent/received.
    """

    connection_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    rooms: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_activity: datetime = field(default_factory=datetime.now)

    @property
    def age_seconds(self) -> float:
        """Get connection age in seconds."""
        return (datetime.now() - self.connected_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        """Get time since last activity in seconds."""
        return (datetime.now() - self.last_activity).total_seconds()


@dataclass
class ServerStats:
    """
    Statistics for the WebSocket server.

    Attributes:
        started_at: When the server started.
        total_connections: Total connections made (including closed).
        active_connections: Currently active connections.
        messages_sent: Total messages sent.
        messages_received: Total messages received.
        rooms: Active rooms and their connection counts.
        errors: Number of errors encountered.
    """

    started_at: datetime = field(default_factory=datetime.now)
    total_connections: int = 0
    active_connections: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    rooms: dict[str, int] = field(default_factory=dict)
    errors: int = 0

    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def uptime_formatted(self) -> str:
        """Get formatted uptime string."""
        seconds = int(self.uptime_seconds)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


# Type aliases for callbacks
MessageHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]
ConnectionHandler = Callable[[ConnectionInfo], Awaitable[None] | None]


class WebSocketServerPort(ABC):
    """
    Abstract interface for WebSocket server implementations.

    WebSocket servers provide real-time bidirectional communication
    with connected clients. This enables live sync updates, progress
    tracking, and real-time collaboration features.

    Example usage:
        # Start server
        await server.start()

        # Broadcast sync progress
        await server.broadcast(WebSocketMessage(
            type=MessageType.SYNC_PROGRESS,
            payload={"progress": 0.5, "stories": 10}
        ))

        # Send to specific room (e.g., epic subscribers)
        await server.send_to_room("epic:PROJ-100", WebSocketMessage(
            type=MessageType.STORY_UPDATED,
            payload={"key": "PROJ-101", "status": "Done"}
        ))

        # Stop server
        await server.stop()
    """

    @abstractmethod
    async def start(self) -> None:
        """
        Start the WebSocket server.

        Should be called before any other operations.
        The server will begin accepting connections.
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the WebSocket server.

        Gracefully closes all connections and stops accepting new ones.
        """

    @abstractmethod
    async def broadcast(self, message: WebSocketMessage) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: The message to broadcast.

        Returns:
            Number of clients the message was sent to.
        """

    @abstractmethod
    async def send_to_room(self, room: str, message: WebSocketMessage) -> int:
        """
        Send a message to all clients in a specific room.

        Args:
            room: The room identifier.
            message: The message to send.

        Returns:
            Number of clients the message was sent to.
        """

    @abstractmethod
    async def send_to_connection(self, connection_id: str, message: WebSocketMessage) -> bool:
        """
        Send a message to a specific connection.

        Args:
            connection_id: The connection identifier.
            message: The message to send.

        Returns:
            True if the message was sent, False if connection not found.
        """

    @abstractmethod
    async def join_room(self, connection_id: str, room: str) -> bool:
        """
        Add a connection to a room.

        Args:
            connection_id: The connection identifier.
            room: The room to join.

        Returns:
            True if successful, False if connection not found.
        """

    @abstractmethod
    async def leave_room(self, connection_id: str, room: str) -> bool:
        """
        Remove a connection from a room.

        Args:
            connection_id: The connection identifier.
            room: The room to leave.

        Returns:
            True if successful, False if connection not found.
        """

    @abstractmethod
    def get_connections(self) -> list[ConnectionInfo]:
        """
        Get information about all active connections.

        Returns:
            List of connection information.
        """

    @abstractmethod
    def get_connection(self, connection_id: str) -> ConnectionInfo | None:
        """
        Get information about a specific connection.

        Args:
            connection_id: The connection identifier.

        Returns:
            Connection info or None if not found.
        """

    @abstractmethod
    def get_room_connections(self, room: str) -> list[ConnectionInfo]:
        """
        Get all connections in a specific room.

        Args:
            room: The room identifier.

        Returns:
            List of connections in the room.
        """

    @abstractmethod
    def get_stats(self) -> ServerStats:
        """
        Get server statistics.

        Returns:
            Current server statistics.
        """

    @abstractmethod
    def on_connect(self, handler: ConnectionHandler) -> None:
        """
        Register a handler for new connections.

        Args:
            handler: Callback invoked when a client connects.
        """

    @abstractmethod
    def on_disconnect(self, handler: ConnectionHandler) -> None:
        """
        Register a handler for disconnections.

        Args:
            handler: Callback invoked when a client disconnects.
        """

    @abstractmethod
    def on_message(self, message_type: str, handler: MessageHandler) -> None:
        """
        Register a handler for incoming messages of a specific type.

        Args:
            message_type: The message type to handle.
            handler: Callback invoked when message is received.
        """

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the server is currently running."""

    @property
    @abstractmethod
    def address(self) -> tuple[str, int]:
        """Get the server's (host, port) address."""


class WebSocketError(Exception):
    """Base exception for WebSocket operations."""


class ConnectionError(WebSocketError):
    """Error related to WebSocket connections."""


class BroadcastError(WebSocketError):
    """Error when broadcasting messages."""


class RoomError(WebSocketError):
    """Error related to room operations."""
