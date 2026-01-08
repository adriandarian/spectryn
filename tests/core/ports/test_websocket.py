"""
Unit tests for WebSocket port interface.

Tests for the WebSocket port definitions including:
- MessageType enum
- WebSocketMessage dataclass
- ConnectionInfo dataclass
- ServerStats dataclass
- WebSocketServerPort interface
"""

from datetime import datetime, timedelta

import pytest

from spectryn.core.ports.websocket import (
    BroadcastError,
    ConnectionInfo,
    MessageType,
    RoomError,
    ServerStats,
    WebSocketError,
    WebSocketMessage,
    WebSocketServerPort,
)
from spectryn.core.ports.websocket import (
    ConnectionError as WsConnectionError,
)


class TestMessageTypeEnum:
    """Tests for MessageType enum."""

    def test_all_sync_types(self):
        """Test all sync-related message types exist."""
        sync_types = [
            MessageType.SYNC_STARTED,
            MessageType.SYNC_PROGRESS,
            MessageType.SYNC_COMPLETED,
            MessageType.SYNC_ERROR,
        ]
        for msg_type in sync_types:
            assert msg_type.value.startswith("sync:")

    def test_all_story_types(self):
        """Test all story-related message types exist."""
        story_types = [
            MessageType.STORY_MATCHED,
            MessageType.STORY_UPDATED,
            MessageType.STORY_CREATED,
        ]
        for msg_type in story_types:
            assert msg_type.value.startswith("story:")

    def test_all_subtask_types(self):
        """Test all subtask-related message types exist."""
        subtask_types = [
            MessageType.SUBTASK_CREATED,
            MessageType.SUBTASK_UPDATED,
        ]
        for msg_type in subtask_types:
            assert msg_type.value.startswith("subtask:")

    def test_all_pull_types(self):
        """Test all pull (reverse sync) message types exist."""
        pull_types = [
            MessageType.PULL_STARTED,
            MessageType.PULL_PROGRESS,
            MessageType.PULL_COMPLETED,
        ]
        for msg_type in pull_types:
            assert msg_type.value.startswith("pull:")

    def test_all_conflict_types(self):
        """Test all conflict-related message types exist."""
        conflict_types = [
            MessageType.CONFLICT_DETECTED,
            MessageType.CONFLICT_RESOLVED,
        ]
        for msg_type in conflict_types:
            assert msg_type.value.startswith("conflict:")

    def test_all_connection_types(self):
        """Test all connection-related message types exist."""
        conn_types = [
            MessageType.CONNECTED,
            MessageType.DISCONNECTED,
            MessageType.SUBSCRIBED,
            MessageType.UNSUBSCRIBED,
        ]
        for msg_type in conn_types:
            assert msg_type.value.startswith("connection:")

    def test_all_system_types(self):
        """Test all system-related message types exist."""
        system_types = [
            MessageType.HEARTBEAT,
            MessageType.ERROR,
            MessageType.SERVER_SHUTDOWN,
        ]
        for msg_type in system_types:
            assert msg_type.value.startswith("system:")


class TestWebSocketMessage:
    """Tests for WebSocketMessage dataclass."""

    def test_create_minimal(self):
        """Test creating a minimal message."""
        msg = WebSocketMessage(type=MessageType.HEARTBEAT)

        assert msg.type == MessageType.HEARTBEAT
        assert msg.payload == {}
        assert msg.room is None
        assert msg.message_id  # Should be auto-generated

    def test_create_with_all_fields(self):
        """Test creating a message with all fields."""
        timestamp = datetime.now()
        msg = WebSocketMessage(
            type=MessageType.SYNC_PROGRESS,
            payload={"progress": 0.75, "message": "Almost done"},
            room="epic:PROJ-100",
            timestamp=timestamp,
            message_id="custom-id-123",
        )

        assert msg.type == MessageType.SYNC_PROGRESS
        assert msg.payload["progress"] == 0.75
        assert msg.room == "epic:PROJ-100"
        assert msg.timestamp == timestamp
        assert msg.message_id == "custom-id-123"

    def test_frozen_dataclass(self):
        """Test that message is frozen (immutable)."""
        msg = WebSocketMessage(type=MessageType.HEARTBEAT)

        with pytest.raises(AttributeError):
            msg.type = MessageType.ERROR

    def test_to_dict_format(self):
        """Test to_dict format for JSON serialization."""
        msg = WebSocketMessage(
            type=MessageType.STORY_CREATED,
            payload={"key": "PROJ-101", "title": "New Story"},
            room="project:PROJ",
        )

        data = msg.to_dict()

        assert data["type"] == "story:created"
        assert data["payload"]["key"] == "PROJ-101"
        assert data["room"] == "project:PROJ"
        assert "timestamp" in data
        assert "messageId" in data

    def test_message_id_uniqueness(self):
        """Test that auto-generated message IDs are unique."""
        messages = [WebSocketMessage(type=MessageType.HEARTBEAT) for _ in range(100)]
        ids = [msg.message_id for msg in messages]

        assert len(ids) == len(set(ids)), "Message IDs should be unique"


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass."""

    def test_create_minimal(self):
        """Test creating minimal connection info."""
        conn = ConnectionInfo(connection_id="conn-123")

        assert conn.connection_id == "conn-123"
        assert len(conn.rooms) == 0
        assert conn.metadata == {}

    def test_create_full(self):
        """Test creating connection info with all fields."""
        now = datetime.now()
        conn = ConnectionInfo(
            connection_id="conn-456",
            connected_at=now,
            rooms={"room1", "room2"},
            metadata={"user": "test", "ip": "127.0.0.1"},
            last_activity=now,
        )

        assert conn.connection_id == "conn-456"
        assert conn.connected_at == now
        assert "room1" in conn.rooms
        assert conn.metadata["user"] == "test"

    def test_age_seconds(self):
        """Test age calculation."""
        past = datetime.now() - timedelta(seconds=30)
        conn = ConnectionInfo(connection_id="test", connected_at=past)

        age = conn.age_seconds
        assert 29 <= age <= 31, f"Expected ~30 seconds, got {age}"

    def test_idle_seconds(self):
        """Test idle time calculation."""
        past = datetime.now() - timedelta(seconds=10)
        conn = ConnectionInfo(connection_id="test", last_activity=past)

        idle = conn.idle_seconds
        assert 9 <= idle <= 11, f"Expected ~10 seconds, got {idle}"

    def test_rooms_mutable(self):
        """Test that rooms set is mutable."""
        conn = ConnectionInfo(connection_id="test")

        conn.rooms.add("new-room")
        assert "new-room" in conn.rooms

        conn.rooms.discard("new-room")
        assert "new-room" not in conn.rooms


class TestServerStats:
    """Tests for ServerStats dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = ServerStats()

        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.rooms == {}
        assert stats.errors == 0

    def test_uptime_calculation(self):
        """Test uptime calculation."""
        past = datetime.now() - timedelta(hours=1, minutes=30)
        stats = ServerStats(started_at=past)

        uptime = stats.uptime_seconds
        expected = 1 * 3600 + 30 * 60  # 1.5 hours in seconds
        assert expected - 1 <= uptime <= expected + 1

    def test_uptime_formatted_seconds(self):
        """Test uptime formatting for seconds."""
        past = datetime.now() - timedelta(seconds=45)
        stats = ServerStats(started_at=past)

        formatted = stats.uptime_formatted
        assert "s" in formatted
        assert "m" not in formatted or formatted.count("m") == 0 or "45s" in formatted

    def test_uptime_formatted_minutes(self):
        """Test uptime formatting for minutes."""
        past = datetime.now() - timedelta(minutes=15, seconds=30)
        stats = ServerStats(started_at=past)

        formatted = stats.uptime_formatted
        assert "m" in formatted
        assert "15m" in formatted

    def test_uptime_formatted_hours(self):
        """Test uptime formatting for hours."""
        past = datetime.now() - timedelta(hours=3, minutes=45)
        stats = ServerStats(started_at=past)

        formatted = stats.uptime_formatted
        assert "h" in formatted
        assert "3h" in formatted

    def test_uptime_formatted_days(self):
        """Test uptime formatting for days."""
        past = datetime.now() - timedelta(days=2, hours=5, minutes=30)
        stats = ServerStats(started_at=past)

        formatted = stats.uptime_formatted
        assert "d" in formatted
        assert "2d" in formatted


class TestWebSocketExceptions:
    """Tests for WebSocket exception classes."""

    def test_base_exception(self):
        """Test WebSocketError base class."""
        error = WebSocketError("Base error")
        assert str(error) == "Base error"
        assert isinstance(error, Exception)

    def test_connection_error(self):
        """Test ConnectionError subclass."""
        error = WsConnectionError("Connection failed")
        assert isinstance(error, WebSocketError)
        assert str(error) == "Connection failed"

    def test_broadcast_error(self):
        """Test BroadcastError subclass."""
        error = BroadcastError("Broadcast failed")
        assert isinstance(error, WebSocketError)
        assert str(error) == "Broadcast failed"

    def test_room_error(self):
        """Test RoomError subclass."""
        error = RoomError("Room not found")
        assert isinstance(error, WebSocketError)
        assert str(error) == "Room not found"


class TestWebSocketServerPortInterface:
    """Tests to verify WebSocketServerPort interface contract."""

    def test_interface_is_abstract(self):
        """Test that WebSocketServerPort cannot be instantiated."""
        with pytest.raises(TypeError):
            WebSocketServerPort()

    def test_interface_methods_defined(self):
        """Test that all required methods are defined."""
        required_methods = [
            "start",
            "stop",
            "broadcast",
            "send_to_room",
            "send_to_connection",
            "join_room",
            "leave_room",
            "get_connections",
            "get_connection",
            "get_room_connections",
            "get_stats",
            "on_connect",
            "on_disconnect",
            "on_message",
        ]

        for method in required_methods:
            assert hasattr(WebSocketServerPort, method), f"Missing method: {method}"

    def test_interface_properties_defined(self):
        """Test that all required properties are defined."""
        required_properties = ["is_running", "address"]

        for prop in required_properties:
            assert hasattr(WebSocketServerPort, prop), f"Missing property: {prop}"
