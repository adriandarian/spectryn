"""
Unit tests for WebSocket server implementations.

Tests for:
- SimpleWebSocketServer (stdlib implementation)
- AioHttpWebSocketServer (aiohttp implementation)
- SyncEventBroadcaster (EventBus -> WebSocket bridge)
- WebSocketBridge (high-level interface)
"""

import asyncio
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from spectryn.adapters.websocket import (
    AioHttpWebSocketServer,
    SimpleWebSocketServer,
    SyncEventBroadcaster,
    WebSocketBridge,
    create_websocket_server,
)
from spectryn.core.domain.events import (
    CommentAdded,
    ConflictDetected,
    DomainEvent,
    EventBus,
    StatusTransitioned,
    StoryMatched,
    StoryUpdated,
    SubtaskCreated,
    SyncCompleted,
    SyncStarted,
)
from spectryn.core.ports.websocket import (
    BroadcastError,
    ConnectionInfo,
    MessageType,
    ServerStats,
    WebSocketError,
    WebSocketMessage,
    WebSocketServerPort,
)


class TestWebSocketMessage:
    """Tests for WebSocketMessage dataclass."""

    def test_create_message(self):
        """Test creating a WebSocket message."""
        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"epicKey": "PROJ-100"},
        )

        assert msg.type == MessageType.SYNC_STARTED
        assert msg.payload == {"epicKey": "PROJ-100"}
        assert msg.room is None
        assert msg.message_id  # Auto-generated

    def test_message_with_room(self):
        """Test creating a message targeted to a room."""
        msg = WebSocketMessage(
            type=MessageType.STORY_UPDATED,
            payload={"key": "PROJ-101"},
            room="epic:PROJ-100",
        )

        assert msg.room == "epic:PROJ-100"

    def test_to_dict(self):
        """Test converting message to dictionary."""
        msg = WebSocketMessage(
            type=MessageType.SYNC_PROGRESS,
            payload={"progress": 0.5},
        )

        data = msg.to_dict()

        assert data["type"] == "sync:progress"
        assert data["payload"] == {"progress": 0.5}
        assert "timestamp" in data
        assert "messageId" in data


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass."""

    def test_create_connection(self):
        """Test creating connection info."""
        conn = ConnectionInfo(
            connection_id="test-123",
            metadata={"address": "127.0.0.1:54321"},
        )

        assert conn.connection_id == "test-123"
        assert conn.metadata["address"] == "127.0.0.1:54321"
        assert len(conn.rooms) == 0

    def test_age_seconds(self):
        """Test connection age calculation."""
        conn = ConnectionInfo(connection_id="test-123")

        # Age should be very small (just created)
        assert conn.age_seconds >= 0
        assert conn.age_seconds < 1

    def test_idle_seconds(self):
        """Test idle time calculation."""
        conn = ConnectionInfo(connection_id="test-123")

        # Should be idle since creation
        assert conn.idle_seconds >= 0
        assert conn.idle_seconds < 1


class TestServerStats:
    """Tests for ServerStats dataclass."""

    def test_default_stats(self):
        """Test default statistics."""
        stats = ServerStats()

        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.errors == 0

    def test_uptime_formatted(self):
        """Test uptime formatting."""
        stats = ServerStats()

        # Just created, should show seconds
        assert "s" in stats.uptime_formatted

    def test_uptime_formatted_minutes(self):
        """Test uptime formatting for minutes."""
        from datetime import timedelta

        stats = ServerStats()
        stats.started_at = datetime.now() - timedelta(minutes=5, seconds=30)

        assert "m" in stats.uptime_formatted
        assert "5m" in stats.uptime_formatted

    def test_uptime_formatted_hours(self):
        """Test uptime formatting for hours."""
        from datetime import timedelta

        stats = ServerStats()
        stats.started_at = datetime.now() - timedelta(hours=2, minutes=30)

        assert "h" in stats.uptime_formatted
        assert "2h" in stats.uptime_formatted


class TestMessageType:
    """Tests for MessageType enum."""

    def test_sync_events(self):
        """Test sync-related message types."""
        assert MessageType.SYNC_STARTED.value == "sync:started"
        assert MessageType.SYNC_PROGRESS.value == "sync:progress"
        assert MessageType.SYNC_COMPLETED.value == "sync:completed"
        assert MessageType.SYNC_ERROR.value == "sync:error"

    def test_story_events(self):
        """Test story-related message types."""
        assert MessageType.STORY_MATCHED.value == "story:matched"
        assert MessageType.STORY_UPDATED.value == "story:updated"
        assert MessageType.STORY_CREATED.value == "story:created"

    def test_connection_events(self):
        """Test connection-related message types."""
        assert MessageType.CONNECTED.value == "connection:connected"
        assert MessageType.DISCONNECTED.value == "connection:disconnected"
        assert MessageType.SUBSCRIBED.value == "connection:subscribed"


class TestSimpleWebSocketServer:
    """Tests for SimpleWebSocketServer."""

    def test_create_server(self):
        """Test creating a server instance."""
        server = SimpleWebSocketServer(host="127.0.0.1", port=9000)

        assert server.address == ("127.0.0.1", 9000)
        assert not server.is_running

    def test_server_stats_initial(self):
        """Test initial server stats."""
        server = SimpleWebSocketServer()
        stats = server.get_stats()

        assert stats.total_connections == 0
        assert stats.active_connections == 0

    def test_get_connections_empty(self):
        """Test getting connections when none exist."""
        server = SimpleWebSocketServer()
        connections = server.get_connections()

        assert connections == []

    def test_get_connection_not_found(self):
        """Test getting a non-existent connection."""
        server = SimpleWebSocketServer()
        conn = server.get_connection("non-existent")

        assert conn is None

    def test_get_room_connections_empty(self):
        """Test getting room connections when room is empty."""
        server = SimpleWebSocketServer()
        connections = server.get_room_connections("some-room")

        assert connections == []

    def test_register_handlers(self):
        """Test registering event handlers."""
        server = SimpleWebSocketServer()

        connect_handler = MagicMock()
        disconnect_handler = MagicMock()
        message_handler = MagicMock()

        server.on_connect(connect_handler)
        server.on_disconnect(disconnect_handler)
        server.on_message("custom", message_handler)

        assert len(server._on_connect_handlers) == 1
        assert len(server._on_disconnect_handlers) == 1
        assert "custom" in server._message_handlers

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        """Test broadcasting with no connections."""
        server = SimpleWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        sent = await server.broadcast(msg)
        assert sent == 0

    @pytest.mark.asyncio
    async def test_send_to_room_no_connections(self):
        """Test sending to room with no connections."""
        server = SimpleWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        sent = await server.send_to_room("test-room", msg)
        assert sent == 0

    @pytest.mark.asyncio
    async def test_send_to_connection_not_found(self):
        """Test sending to non-existent connection."""
        server = SimpleWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        result = await server.send_to_connection("non-existent", msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_join_room_connection_not_found(self):
        """Test joining room with non-existent connection."""
        server = SimpleWebSocketServer()

        result = await server.join_room("non-existent", "test-room")
        assert result is False

    @pytest.mark.asyncio
    async def test_leave_room_connection_not_found(self):
        """Test leaving room with non-existent connection."""
        server = SimpleWebSocketServer()

        result = await server.leave_room("non-existent", "test-room")
        assert result is False


class TestAioHttpWebSocketServer:
    """Tests for AioHttpWebSocketServer."""

    def test_create_server(self):
        """Test creating an aiohttp server instance."""
        server = AioHttpWebSocketServer(host="127.0.0.1", port=9001)

        assert server.address == ("127.0.0.1", 9001)
        assert not server.is_running

    def test_server_stats_initial(self):
        """Test initial server stats."""
        server = AioHttpWebSocketServer()
        stats = server.get_stats()

        assert stats.total_connections == 0
        assert stats.active_connections == 0

    def test_get_connections_empty(self):
        """Test getting connections when none exist."""
        server = AioHttpWebSocketServer()
        connections = server.get_connections()

        assert connections == []

    def test_get_connection_not_found(self):
        """Test getting a non-existent connection."""
        server = AioHttpWebSocketServer()
        conn = server.get_connection("non-existent")

        assert conn is None

    def test_register_handlers(self):
        """Test registering event handlers."""
        server = AioHttpWebSocketServer()

        connect_handler = MagicMock()
        disconnect_handler = MagicMock()
        message_handler = MagicMock()

        server.on_connect(connect_handler)
        server.on_disconnect(disconnect_handler)
        server.on_message("custom", message_handler)

        assert len(server._on_connect_handlers) == 1
        assert len(server._on_disconnect_handlers) == 1
        assert "custom" in server._message_handlers

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        """Test broadcasting with no connections."""
        server = AioHttpWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        sent = await server.broadcast(msg)
        assert sent == 0

    @pytest.mark.asyncio
    async def test_send_to_room_no_connections(self):
        """Test sending to room with no connections."""
        server = AioHttpWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        sent = await server.send_to_room("test-room", msg)
        assert sent == 0

    @pytest.mark.asyncio
    async def test_send_to_connection_not_found(self):
        """Test sending to non-existent connection."""
        server = AioHttpWebSocketServer()

        msg = WebSocketMessage(
            type=MessageType.SYNC_STARTED,
            payload={"test": True},
        )

        result = await server.send_to_connection("non-existent", msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_join_room_connection_not_found(self):
        """Test joining room with non-existent connection."""
        server = AioHttpWebSocketServer()

        result = await server.join_room("non-existent", "test-room")
        assert result is False

    @pytest.mark.asyncio
    async def test_leave_room_connection_not_found(self):
        """Test leaving room with non-existent connection."""
        server = AioHttpWebSocketServer()

        result = await server.leave_room("non-existent", "test-room")
        assert result is False


class TestSyncEventBroadcaster:
    """Tests for SyncEventBroadcaster."""

    def test_create_broadcaster(self):
        """Test creating a broadcaster."""
        server = MagicMock(spec=WebSocketServerPort)
        event_bus = EventBus()

        broadcaster = SyncEventBroadcaster(server, event_bus)

        assert broadcaster.server is server
        assert broadcaster.event_bus is event_bus
        assert broadcaster.room is None

    def test_create_broadcaster_with_room(self):
        """Test creating a broadcaster with a room filter."""
        server = MagicMock(spec=WebSocketServerPort)
        event_bus = EventBus()

        broadcaster = SyncEventBroadcaster(server, event_bus, room="epic:PROJ-100")

        assert broadcaster.room == "epic:PROJ-100"

    def test_event_type_mapping(self):
        """Test domain event to message type mapping."""
        expected_mappings = {
            SyncStarted: MessageType.SYNC_STARTED,
            SyncCompleted: MessageType.SYNC_COMPLETED,
            StoryMatched: MessageType.STORY_MATCHED,
            StoryUpdated: MessageType.STORY_UPDATED,
            SubtaskCreated: MessageType.SUBTASK_CREATED,
            StatusTransitioned: MessageType.STATUS_CHANGED,
            CommentAdded: MessageType.COMMENT_ADDED,
            ConflictDetected: MessageType.CONFLICT_DETECTED,
        }

        for event_type, msg_type in expected_mappings.items():
            assert SyncEventBroadcaster.EVENT_TYPE_MAP[event_type] == msg_type

    def test_event_to_payload(self):
        """Test converting domain event to payload."""
        server = MagicMock(spec=WebSocketServerPort)
        event_bus = EventBus()
        broadcaster = SyncEventBroadcaster(server, event_bus)

        event = SyncStarted(
            epic_key="PROJ-100",
            markdown_path="/path/to/file.md",
            dry_run=True,
        )

        payload = broadcaster._event_to_payload(event)

        assert payload["epic_key"] == "PROJ-100"
        assert payload["markdown_path"] == "/path/to/file.md"
        assert payload["dry_run"] is True


class TestWebSocketBridge:
    """Tests for WebSocketBridge high-level interface."""

    def test_create_bridge_simple(self):
        """Test creating a bridge with simple server."""
        bridge = WebSocketBridge(
            host="127.0.0.1",
            port=9002,
            use_aiohttp=False,
        )

        assert isinstance(bridge.server, SimpleWebSocketServer)
        assert not bridge.is_running

    def test_create_bridge_with_event_bus(self):
        """Test creating a bridge with event bus."""
        event_bus = EventBus()
        bridge = WebSocketBridge(
            host="127.0.0.1",
            port=9003,
            use_aiohttp=False,
            event_bus=event_bus,
        )

        assert bridge.event_bus is event_bus

    def test_stats(self):
        """Test getting bridge stats."""
        bridge = WebSocketBridge(use_aiohttp=False)
        stats = bridge.stats

        assert isinstance(stats, ServerStats)
        assert stats.total_connections == 0

    @pytest.mark.asyncio
    async def test_send_sync_started(self):
        """Test sending sync started notification."""
        bridge = WebSocketBridge(use_aiohttp=False)

        # Mock the server's broadcast method
        bridge.server.broadcast = AsyncMock(return_value=1)

        await bridge.send_sync_started(
            epic_key="PROJ-100",
            markdown_path="/path/to/file.md",
            dry_run=True,
        )

        bridge.server.broadcast.assert_called_once()
        call_args = bridge.server.broadcast.call_args
        msg = call_args[0][0]
        assert msg.type == MessageType.SYNC_STARTED
        assert msg.payload["epicKey"] == "PROJ-100"

    @pytest.mark.asyncio
    async def test_send_sync_completed(self):
        """Test sending sync completed notification."""
        bridge = WebSocketBridge(use_aiohttp=False)
        bridge.server.broadcast = AsyncMock(return_value=1)

        await bridge.send_sync_completed(
            epic_key="PROJ-100",
            stories_matched=5,
            stories_updated=3,
            subtasks_created=10,
        )

        bridge.server.broadcast.assert_called_once()
        call_args = bridge.server.broadcast.call_args
        msg = call_args[0][0]
        assert msg.type == MessageType.SYNC_COMPLETED
        assert msg.payload["storiesMatched"] == 5
        assert msg.payload["success"] is True

    @pytest.mark.asyncio
    async def test_send_error(self):
        """Test sending error notification."""
        bridge = WebSocketBridge(use_aiohttp=False)
        bridge.server.broadcast = AsyncMock(return_value=1)

        await bridge.send_error("Something went wrong", {"code": "ERR001"})

        bridge.server.broadcast.assert_called_once()
        call_args = bridge.server.broadcast.call_args
        msg = call_args[0][0]
        assert msg.type == MessageType.SYNC_ERROR
        assert msg.payload["error"] == "Something went wrong"
        assert msg.payload["code"] == "ERR001"


class TestCreateWebSocketServer:
    """Tests for create_websocket_server factory function."""

    def test_create_simple_server(self):
        """Test creating a simple server explicitly."""
        server = create_websocket_server(
            host="127.0.0.1",
            port=9004,
            use_aiohttp=False,
        )

        assert isinstance(server, SimpleWebSocketServer)
        assert server.address == ("127.0.0.1", 9004)

    def test_create_aiohttp_server_explicit(self):
        """Test creating an aiohttp server explicitly."""
        server = create_websocket_server(
            host="127.0.0.1",
            port=9005,
            use_aiohttp=True,
        )

        assert isinstance(server, AioHttpWebSocketServer)
        assert server.address == ("127.0.0.1", 9005)

    def test_create_server_auto_detect(self):
        """Test auto-detecting aiohttp availability."""
        server = create_websocket_server(
            host="127.0.0.1",
            port=9006,
        )

        # Should be aiohttp if available, simple otherwise
        assert isinstance(server, (SimpleWebSocketServer, AioHttpWebSocketServer))


class TestWebSocketExceptions:
    """Tests for WebSocket exceptions."""

    def test_websocket_error(self):
        """Test base WebSocket error."""
        error = WebSocketError("Test error")
        assert str(error) == "Test error"

    def test_broadcast_error(self):
        """Test broadcast error."""
        error = BroadcastError("Failed to broadcast")
        assert isinstance(error, WebSocketError)

    def test_connection_error(self):
        """Test connection error."""
        from spectryn.core.ports.websocket import ConnectionError as WsConnError

        error = WsConnError("Connection failed")
        assert isinstance(error, WebSocketError)


class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.mark.asyncio
    async def test_event_bus_to_websocket_flow(self):
        """Test the full flow from EventBus to WebSocket broadcast."""
        # Create components
        server = SimpleWebSocketServer()
        event_bus = EventBus()
        broadcaster = SyncEventBroadcaster(server, event_bus)

        # Mock broadcast to capture calls
        broadcast_calls = []

        async def capture_broadcast(msg):
            broadcast_calls.append(msg)
            return 0

        server.broadcast = capture_broadcast
        server._broadcast_sync = lambda msg: broadcast_calls.append(msg) or 0

        # Start broadcasting
        broadcaster.start()

        # Publish an event
        event = SyncStarted(
            epic_key="PROJ-100",
            markdown_path="/test.md",
            dry_run=False,
        )
        event_bus.publish(event)

        # Small delay for async processing
        await asyncio.sleep(0.1)

        # Verify broadcast was called
        assert len(broadcast_calls) >= 1
        msg = broadcast_calls[0]
        assert msg.type == MessageType.SYNC_STARTED

    def test_bridge_progress_tracking(self):
        """Test progress tracking through the bridge."""
        bridge = WebSocketBridge(use_aiohttp=False)

        # Mock broadcast
        broadcast_calls = []
        bridge.server._broadcast_sync = lambda msg: broadcast_calls.append(msg) or 0

        # Send progress
        bridge.send_progress(0.5, "Processing...", {"step": 1})

        # Verify
        assert len(broadcast_calls) == 1
        msg = broadcast_calls[0]
        assert msg.type == MessageType.SYNC_PROGRESS
        assert msg.payload["progress"] == 0.5
        assert msg.payload["message"] == "Processing..."
        assert msg.payload["percentage"] == 50
