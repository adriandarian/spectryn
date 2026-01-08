"""
WebSocket Server Implementations.

Provides WebSocket server adapters for real-time sync updates:
- SimpleWebSocketServer: Lightweight server using standard library (no dependencies)
- AioHttpWebSocketServer: Full-featured async server using aiohttp
- SyncEventBroadcaster: Bridge between EventBus and WebSocket server
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import struct
import threading
from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from typing import Any
from uuid import uuid4

from spectryn.core.domain.events import (
    CommentAdded,
    ConflictDetected,
    ConflictResolved,
    DomainEvent,
    EventBus,
    PullCompleted,
    PullStarted,
    StatusTransitioned,
    StoryMatched,
    StoryUpdated,
    SubtaskCreated,
    SubtaskUpdated,
    SyncCompleted,
    SyncStarted,
)
from spectryn.core.ports.websocket import (
    ConnectionHandler,
    ConnectionInfo,
    MessageHandler,
    MessageType,
    ServerStats,
    WebSocketMessage,
    WebSocketServerPort,
)


logger = logging.getLogger(__name__)


# WebSocket frame opcodes
OPCODE_CONT = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


@dataclass
class WebSocketConnection:
    """Internal representation of a WebSocket connection."""

    connection_id: str
    socket: socket
    info: ConnectionInfo
    buffer: bytes = b""
    closed: bool = False


class SimpleWebSocketServer(WebSocketServerPort):
    """
    Simple WebSocket server using Python's standard library.

    This implementation provides basic WebSocket functionality without
    external dependencies. For production use with high concurrency,
    consider using AioHttpWebSocketServer.

    Features:
    - RFC 6455 compliant WebSocket handshake
    - Text message framing
    - Ping/pong for keep-alive
    - Room-based message routing
    - Thread-safe operations
    """

    WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        heartbeat_interval: float = 30.0,
    ):
        """
        Initialize the WebSocket server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            heartbeat_interval: Seconds between heartbeat pings (0 to disable).
        """
        self._host = host
        self._port = port
        self._heartbeat_interval = heartbeat_interval

        self._connections: dict[str, WebSocketConnection] = {}
        self._rooms: dict[str, set[str]] = {}  # room -> connection_ids
        self._lock = threading.RLock()

        self._server_socket: socket | None = None
        self._running = False
        self._accept_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

        self._on_connect_handlers: list[ConnectionHandler] = []
        self._on_disconnect_handlers: list[ConnectionHandler] = []
        self._message_handlers: dict[str, list[MessageHandler]] = {}

        self._stats = ServerStats()
        self._logger = logging.getLogger("SimpleWebSocketServer")

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._start_sync()

    def _start_sync(self) -> None:
        """Synchronous start implementation."""
        if self._running:
            return

        self._server_socket = socket(AF_INET, SOCK_STREAM)
        self._server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self._server_socket.bind((self._host, self._port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        self._running = True
        self._stats = ServerStats()

        # Start accept thread
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

        # Start heartbeat thread
        if self._heartbeat_interval > 0:
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

        self._logger.info(f"WebSocket server started on ws://{self._host}:{self._port}")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        self._stop_sync()

    def _stop_sync(self) -> None:
        """Synchronous stop implementation."""
        if not self._running:
            return

        self._running = False

        # Close all connections
        with self._lock:
            for conn in list(self._connections.values()):
                self._close_connection(conn, "Server shutting down")

        # Close server socket
        if self._server_socket:
            with contextlib.suppress(Exception):
                self._server_socket.close()
            self._server_socket = None

        self._logger.info("WebSocket server stopped")

    def _accept_loop(self) -> None:
        """Accept incoming connections."""
        while self._running and self._server_socket:
            try:
                client_socket, address = self._server_socket.accept()
                client_socket.settimeout(30.0)

                # Handle handshake in a new thread
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True,
                )
                thread.start()

            except TimeoutError:
                continue
            except OSError:
                if self._running:
                    self._logger.error("Error accepting connection")
                break

    def _handle_client(self, client_socket: socket, address: tuple) -> None:
        """Handle a new client connection."""
        connection_id = str(uuid4())

        try:
            # Perform WebSocket handshake
            if not self._do_handshake(client_socket):
                client_socket.close()
                return

            # Create connection
            conn = WebSocketConnection(
                connection_id=connection_id,
                socket=client_socket,
                info=ConnectionInfo(
                    connection_id=connection_id,
                    metadata={"address": f"{address[0]}:{address[1]}"},
                ),
            )

            with self._lock:
                self._connections[connection_id] = conn
                self._stats.total_connections += 1
                self._stats.active_connections += 1

            self._logger.debug(f"Client connected: {connection_id}")

            # Notify handlers
            self._invoke_connect_handlers(conn.info)

            # Send connected message
            self._send_message_sync(
                conn,
                WebSocketMessage(
                    type=MessageType.CONNECTED,
                    payload={"connectionId": connection_id},
                ),
            )

            # Read loop
            self._read_loop(conn)

        except Exception as e:
            self._logger.error(f"Error handling client {connection_id}: {e}")
        finally:
            self._cleanup_connection(connection_id)

    def _do_handshake(self, client_socket: socket) -> bool:
        """Perform WebSocket handshake."""
        try:
            # Read HTTP request
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = client_socket.recv(1024)
                if not chunk:
                    return False
                request += chunk

            # Parse headers
            request_str = request.decode("utf-8")
            headers = {}
            for line in request_str.split("\r\n")[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key.lower()] = value

            # Validate WebSocket request
            if "sec-websocket-key" not in headers:
                return False

            # Generate accept key
            key = headers["sec-websocket-key"]
            accept = b64encode(hashlib.sha1((key + self.WEBSOCKET_GUID).encode()).digest()).decode()

            # Send response
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            client_socket.send(response.encode())

            return True

        except Exception as e:
            self._logger.error(f"Handshake failed: {e}")
            return False

    def _read_loop(self, conn: WebSocketConnection) -> None:
        """Read messages from a connection."""
        while self._running and not conn.closed:
            try:
                frame = self._read_frame(conn)
                if frame is None:
                    break

                opcode, payload = frame

                if opcode == OPCODE_TEXT:
                    self._handle_message(conn, payload.decode("utf-8"))
                elif opcode == OPCODE_CLOSE:
                    break
                elif opcode == OPCODE_PING:
                    self._send_frame(conn.socket, OPCODE_PONG, payload)
                elif opcode == OPCODE_PONG:
                    conn.info.last_activity = datetime.now()

            except TimeoutError:
                continue
            except Exception as e:
                if self._running and not conn.closed:
                    self._logger.error(f"Error reading from {conn.connection_id}: {e}")
                break

    def _read_frame(self, conn: WebSocketConnection) -> tuple[int, bytes] | None:
        """Read a WebSocket frame."""
        # Read first 2 bytes
        data = self._recv_exact(conn.socket, 2)
        if not data:
            return None

        first_byte, second_byte = data[0], data[1]
        opcode = first_byte & 0x0F
        masked = bool(second_byte & 0x80)
        payload_length = second_byte & 0x7F

        # Extended payload length
        if payload_length == 126:
            data = self._recv_exact(conn.socket, 2)
            if not data:
                return None
            payload_length = struct.unpack(">H", data)[0]
        elif payload_length == 127:
            data = self._recv_exact(conn.socket, 8)
            if not data:
                return None
            payload_length = struct.unpack(">Q", data)[0]

        # Read masking key
        mask: bytes = b""
        if masked:
            mask_data = self._recv_exact(conn.socket, 4)
            if not mask_data:
                return None
            mask = mask_data

        # Read payload
        payload = self._recv_exact(conn.socket, payload_length)
        if payload is None:
            return None

        # Unmask payload
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

        return opcode, payload

    def _recv_exact(self, sock: socket, length: int) -> bytes | None:
        """Receive exact number of bytes."""
        data = b""
        while len(data) < length:
            try:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk
            except TimeoutError:
                if not self._running:
                    return None
                continue
        return data

    def _send_frame(self, sock: socket, opcode: int, payload: bytes) -> bool:
        """Send a WebSocket frame."""
        try:
            frame = bytearray()

            # First byte: FIN + opcode
            frame.append(0x80 | opcode)

            # Second byte: mask bit (0) + payload length
            length = len(payload)
            if length < 126:
                frame.append(length)
            elif length < 65536:
                frame.append(126)
                frame.extend(struct.pack(">H", length))
            else:
                frame.append(127)
                frame.extend(struct.pack(">Q", length))

            # Payload (no masking for server -> client)
            frame.extend(payload)

            sock.send(bytes(frame))
            return True

        except Exception:
            return False

    def _handle_message(self, conn: WebSocketConnection, message: str) -> None:
        """Handle an incoming text message."""
        conn.info.last_activity = datetime.now()
        self._stats.messages_received += 1

        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            # Handle built-in message types
            if msg_type == "subscribe":
                room = data.get("room")
                if room:
                    asyncio.get_event_loop().run_until_complete(
                        self.join_room(conn.connection_id, room)
                    )
            elif msg_type == "unsubscribe":
                room = data.get("room")
                if room:
                    asyncio.get_event_loop().run_until_complete(
                        self.leave_room(conn.connection_id, room)
                    )
            else:
                # Call registered handlers
                for handler in self._message_handlers.get(msg_type, []):
                    try:
                        result = handler(conn.connection_id, data.get("payload", {}))
                        if asyncio.iscoroutine(result):
                            asyncio.get_event_loop().run_until_complete(result)
                    except Exception as e:
                        self._logger.error(f"Message handler error: {e}")

        except json.JSONDecodeError:
            self._logger.warning(f"Invalid JSON from {conn.connection_id}")

    def _send_message_sync(self, conn: WebSocketConnection, message: WebSocketMessage) -> bool:
        """Send a message to a connection synchronously."""
        if conn.closed:
            return False

        try:
            payload = json.dumps(message.to_dict()).encode("utf-8")
            result = self._send_frame(conn.socket, OPCODE_TEXT, payload)
            if result:
                self._stats.messages_sent += 1
            return result
        except Exception:
            return False

    def _close_connection(self, conn: WebSocketConnection, reason: str = "") -> None:
        """Close a connection."""
        if conn.closed:
            return

        conn.closed = True

        # Send close frame
        with contextlib.suppress(Exception):
            payload = struct.pack(">H", 1000) + reason.encode("utf-8")[:123]
            self._send_frame(conn.socket, OPCODE_CLOSE, payload)

        # Close socket
        with contextlib.suppress(Exception):
            conn.socket.close()

    def _cleanup_connection(self, connection_id: str) -> None:
        """Clean up a disconnected connection."""
        with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn:
                conn.closed = True
                self._stats.active_connections -= 1

                # Remove from all rooms
                for room_conns in self._rooms.values():
                    room_conns.discard(connection_id)

                # Update room stats
                self._stats.rooms = {
                    room: len(conns) for room, conns in self._rooms.items() if conns
                }

                # Notify handlers
                self._invoke_disconnect_handlers(conn.info)

                self._logger.debug(f"Client disconnected: {connection_id}")

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to connections."""
        while self._running:
            try:
                # Sleep for interval
                for _ in range(int(self._heartbeat_interval * 10)):
                    if not self._running:
                        return
                    threading.Event().wait(0.1)

                # Send pings
                with self._lock:
                    for conn in list(self._connections.values()):
                        if not conn.closed:
                            self._send_frame(conn.socket, OPCODE_PING, b"")

            except Exception as e:
                self._logger.error(f"Heartbeat error: {e}")

    def _invoke_connect_handlers(self, info: ConnectionInfo) -> None:
        """Invoke connection handlers."""
        for handler in self._on_connect_handlers:
            try:
                result = handler(info)
                if asyncio.iscoroutine(result):
                    asyncio.get_event_loop().run_until_complete(result)
            except Exception as e:
                self._logger.error(f"Connect handler error: {e}")

    def _invoke_disconnect_handlers(self, info: ConnectionInfo) -> None:
        """Invoke disconnection handlers."""
        for handler in self._on_disconnect_handlers:
            try:
                result = handler(info)
                if asyncio.iscoroutine(result):
                    asyncio.get_event_loop().run_until_complete(result)
            except Exception as e:
                self._logger.error(f"Disconnect handler error: {e}")

    async def broadcast(self, message: WebSocketMessage) -> int:
        """Broadcast a message to all connected clients."""
        return self._broadcast_sync(message)

    def _broadcast_sync(self, message: WebSocketMessage) -> int:
        """Synchronous broadcast implementation."""
        sent = 0
        with self._lock:
            for conn in list(self._connections.values()):
                if self._send_message_sync(conn, message):
                    sent += 1
        return sent

    async def send_to_room(self, room: str, message: WebSocketMessage) -> int:
        """Send a message to all clients in a room."""
        return self._send_to_room_sync(room, message)

    def _send_to_room_sync(self, room: str, message: WebSocketMessage) -> int:
        """Synchronous send to room implementation."""
        sent = 0
        with self._lock:
            connection_ids = self._rooms.get(room, set()).copy()

        for conn_id in connection_ids:
            with self._lock:
                conn = self._connections.get(conn_id)
            if conn and self._send_message_sync(conn, message):
                sent += 1

        return sent

    async def send_to_connection(self, connection_id: str, message: WebSocketMessage) -> bool:
        """Send a message to a specific connection."""
        with self._lock:
            conn = self._connections.get(connection_id)
            if conn:
                return self._send_message_sync(conn, message)
        return False

    async def join_room(self, connection_id: str, room: str) -> bool:
        """Add a connection to a room."""
        with self._lock:
            if connection_id not in self._connections:
                return False

            if room not in self._rooms:
                self._rooms[room] = set()

            self._rooms[room].add(connection_id)
            self._connections[connection_id].info.rooms.add(room)
            self._stats.rooms[room] = len(self._rooms[room])

        # Send confirmation
        conn = self._connections.get(connection_id)
        if conn:
            self._send_message_sync(
                conn,
                WebSocketMessage(
                    type=MessageType.SUBSCRIBED,
                    payload={"room": room},
                ),
            )

        self._logger.debug(f"Connection {connection_id} joined room {room}")
        return True

    async def leave_room(self, connection_id: str, room: str) -> bool:
        """Remove a connection from a room."""
        with self._lock:
            if connection_id not in self._connections:
                return False

            if room in self._rooms:
                self._rooms[room].discard(connection_id)
                if not self._rooms[room]:
                    del self._rooms[room]
                    self._stats.rooms.pop(room, None)
                else:
                    self._stats.rooms[room] = len(self._rooms[room])

            self._connections[connection_id].info.rooms.discard(room)

        # Send confirmation
        conn = self._connections.get(connection_id)
        if conn:
            self._send_message_sync(
                conn,
                WebSocketMessage(
                    type=MessageType.UNSUBSCRIBED,
                    payload={"room": room},
                ),
            )

        self._logger.debug(f"Connection {connection_id} left room {room}")
        return True

    def get_connections(self) -> list[ConnectionInfo]:
        """Get information about all active connections."""
        with self._lock:
            return [conn.info for conn in self._connections.values()]

    def get_connection(self, connection_id: str) -> ConnectionInfo | None:
        """Get information about a specific connection."""
        with self._lock:
            conn = self._connections.get(connection_id)
            return conn.info if conn else None

    def get_room_connections(self, room: str) -> list[ConnectionInfo]:
        """Get all connections in a specific room."""
        with self._lock:
            conn_ids = self._rooms.get(room, set())
            return [self._connections[cid].info for cid in conn_ids if cid in self._connections]

    def get_stats(self) -> ServerStats:
        """Get server statistics."""
        return self._stats

    def on_connect(self, handler: ConnectionHandler) -> None:
        """Register a handler for new connections."""
        self._on_connect_handlers.append(handler)

    def on_disconnect(self, handler: ConnectionHandler) -> None:
        """Register a handler for disconnections."""
        self._on_disconnect_handlers.append(handler)

    def on_message(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for incoming messages of a specific type."""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running

    @property
    def address(self) -> tuple[str, int]:
        """Get the server's (host, port) address."""
        return (self._host, self._port)


class AioHttpWebSocketServer(WebSocketServerPort):
    """
    Full-featured async WebSocket server using aiohttp.

    This implementation provides production-ready WebSocket functionality
    with proper async support. Requires the 'async' extra to be installed.

    Features:
    - Full async/await support
    - Automatic connection management
    - Room-based message routing
    - Built-in heartbeat/ping support
    - HTTP endpoints for health checks
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        heartbeat_interval: float = 30.0,
    ):
        """
        Initialize the WebSocket server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            heartbeat_interval: Seconds between heartbeat pings.
        """
        self._host = host
        self._port = port
        self._heartbeat_interval = heartbeat_interval

        self._connections: dict[str, Any] = {}  # connection_id -> (ws, info)
        self._rooms: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

        self._app: Any = None
        self._runner: Any = None
        self._site: Any = None
        self._running = False

        self._on_connect_handlers: list[ConnectionHandler] = []
        self._on_disconnect_handlers: list[ConnectionHandler] = []
        self._message_handlers: dict[str, list[MessageHandler]] = {}

        self._stats = ServerStats()
        self._logger = logging.getLogger("AioHttpWebSocketServer")

    async def start(self) -> None:
        """Start the WebSocket server."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError(
                "aiohttp is required for AioHttpWebSocketServer. "
                "Install with: pip install spectra[async]"
            )

        if self._running:
            return

        # Create aiohttp app
        self._app = web.Application()
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_get("/status", self._status_handler)

        # Start server
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        self._running = True
        self._stats = ServerStats()

        self._logger.info(f"WebSocket server started on ws://{self._host}:{self._port}/ws")

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if not self._running:
            return

        self._running = False

        # Close all connections
        async with self._lock:
            for ws, _info in list(self._connections.values()):
                with contextlib.suppress(Exception):
                    await ws.close()

        # Cleanup runner
        if self._runner:
            await self._runner.cleanup()

        self._logger.info("WebSocket server stopped")

    async def _websocket_handler(self, request: Any) -> Any:
        """Handle WebSocket connections."""
        from aiohttp import WSMsgType, web

        ws = web.WebSocketResponse(heartbeat=self._heartbeat_interval)
        await ws.prepare(request)

        connection_id = str(uuid4())
        info = ConnectionInfo(
            connection_id=connection_id,
            metadata={"remote": str(request.remote)},
        )

        async with self._lock:
            self._connections[connection_id] = (ws, info)
            self._stats.total_connections += 1
            self._stats.active_connections += 1

        self._logger.debug(f"Client connected: {connection_id}")

        # Notify handlers
        await self._invoke_handlers(self._on_connect_handlers, info)

        # Send connected message
        await self._send_to_ws(
            ws,
            WebSocketMessage(
                type=MessageType.CONNECTED,
                payload={"connectionId": connection_id},
            ),
        )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(connection_id, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    self._logger.error(f"WebSocket error: {ws.exception()}")
                    break
        finally:
            await self._cleanup_connection(connection_id, info)

        return ws

    async def _health_handler(self, request: Any) -> Any:
        """Handle health check requests."""
        from aiohttp import web

        return web.json_response({"status": "ok", "service": "spectra-websocket"})

    async def _status_handler(self, request: Any) -> Any:
        """Handle status requests."""
        from aiohttp import web

        return web.json_response(
            {
                "status": "running",
                "uptime": self._stats.uptime_formatted,
                "connections": self._stats.active_connections,
                "messages_sent": self._stats.messages_sent,
                "rooms": self._stats.rooms,
            }
        )

    async def _handle_message(self, connection_id: str, message: str) -> None:
        """Handle an incoming message."""
        self._stats.messages_received += 1

        async with self._lock:
            conn_data = self._connections.get(connection_id)
            if conn_data:
                conn_data[1].last_activity = datetime.now()

        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "subscribe":
                room = data.get("room")
                if room:
                    await self.join_room(connection_id, room)
            elif msg_type == "unsubscribe":
                room = data.get("room")
                if room:
                    await self.leave_room(connection_id, room)
            else:
                for handler in self._message_handlers.get(msg_type, []):
                    try:
                        result = handler(connection_id, data.get("payload", {}))
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        self._logger.error(f"Message handler error: {e}")

        except json.JSONDecodeError:
            self._logger.warning(f"Invalid JSON from {connection_id}")

    async def _cleanup_connection(self, connection_id: str, info: ConnectionInfo) -> None:
        """Clean up a disconnected connection."""
        async with self._lock:
            self._connections.pop(connection_id, None)
            self._stats.active_connections -= 1

            for room_conns in self._rooms.values():
                room_conns.discard(connection_id)

            self._stats.rooms = {room: len(conns) for room, conns in self._rooms.items() if conns}

        await self._invoke_handlers(self._on_disconnect_handlers, info)
        self._logger.debug(f"Client disconnected: {connection_id}")

    async def _send_to_ws(self, ws: Any, message: WebSocketMessage) -> bool:
        """Send a message to a WebSocket."""
        try:
            await ws.send_json(message.to_dict())
            self._stats.messages_sent += 1
            return True
        except Exception:
            return False

    async def _invoke_handlers(
        self, handlers: list[ConnectionHandler], info: ConnectionInfo
    ) -> None:
        """Invoke connection handlers."""
        for handler in handlers:
            try:
                result = handler(info)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self._logger.error(f"Handler error: {e}")

    async def broadcast(self, message: WebSocketMessage) -> int:
        """Broadcast a message to all connected clients."""
        sent = 0
        async with self._lock:
            connections = list(self._connections.values())

        for ws, _ in connections:
            if await self._send_to_ws(ws, message):
                sent += 1

        return sent

    async def send_to_room(self, room: str, message: WebSocketMessage) -> int:
        """Send a message to all clients in a room."""
        sent = 0
        async with self._lock:
            conn_ids = self._rooms.get(room, set()).copy()

        for conn_id in conn_ids:
            async with self._lock:
                conn_data = self._connections.get(conn_id)

            if conn_data:
                ws, _ = conn_data
                if await self._send_to_ws(ws, message):
                    sent += 1

        return sent

    async def send_to_connection(self, connection_id: str, message: WebSocketMessage) -> bool:
        """Send a message to a specific connection."""
        async with self._lock:
            conn_data = self._connections.get(connection_id)

        if conn_data:
            ws, _ = conn_data
            return await self._send_to_ws(ws, message)

        return False

    async def join_room(self, connection_id: str, room: str) -> bool:
        """Add a connection to a room."""
        async with self._lock:
            if connection_id not in self._connections:
                return False

            if room not in self._rooms:
                self._rooms[room] = set()

            self._rooms[room].add(connection_id)
            self._connections[connection_id][1].rooms.add(room)
            self._stats.rooms[room] = len(self._rooms[room])

            ws, _ = self._connections[connection_id]

        await self._send_to_ws(
            ws,
            WebSocketMessage(
                type=MessageType.SUBSCRIBED,
                payload={"room": room},
            ),
        )

        self._logger.debug(f"Connection {connection_id} joined room {room}")
        return True

    async def leave_room(self, connection_id: str, room: str) -> bool:
        """Remove a connection from a room."""
        async with self._lock:
            if connection_id not in self._connections:
                return False

            if room in self._rooms:
                self._rooms[room].discard(connection_id)
                if not self._rooms[room]:
                    del self._rooms[room]
                    self._stats.rooms.pop(room, None)
                else:
                    self._stats.rooms[room] = len(self._rooms[room])

            self._connections[connection_id][1].rooms.discard(room)
            ws, _ = self._connections[connection_id]

        await self._send_to_ws(
            ws,
            WebSocketMessage(
                type=MessageType.UNSUBSCRIBED,
                payload={"room": room},
            ),
        )

        self._logger.debug(f"Connection {connection_id} left room {room}")
        return True

    def get_connections(self) -> list[ConnectionInfo]:
        """Get information about all active connections."""
        return [info for _, info in self._connections.values()]

    def get_connection(self, connection_id: str) -> ConnectionInfo | None:
        """Get information about a specific connection."""
        conn_data = self._connections.get(connection_id)
        return conn_data[1] if conn_data else None

    def get_room_connections(self, room: str) -> list[ConnectionInfo]:
        """Get all connections in a specific room."""
        conn_ids = self._rooms.get(room, set())
        return [self._connections[cid][1] for cid in conn_ids if cid in self._connections]

    def get_stats(self) -> ServerStats:
        """Get server statistics."""
        return self._stats

    def on_connect(self, handler: ConnectionHandler) -> None:
        """Register a handler for new connections."""
        self._on_connect_handlers.append(handler)

    def on_disconnect(self, handler: ConnectionHandler) -> None:
        """Register a handler for disconnections."""
        self._on_disconnect_handlers.append(handler)

    def on_message(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for incoming messages of a specific type."""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)

    @property
    def is_running(self) -> bool:
        """Check if the server is currently running."""
        return self._running

    @property
    def address(self) -> tuple[str, int]:
        """Get the server's (host, port) address."""
        return (self._host, self._port)


class SyncEventBroadcaster:
    """
    Bridge between EventBus and WebSocket server.

    Subscribes to domain events from the EventBus and broadcasts
    them to connected WebSocket clients in real-time.

    Usage:
        broadcaster = SyncEventBroadcaster(ws_server, event_bus)
        broadcaster.start()
        # Events from event_bus are now broadcast to WebSocket clients
    """

    # Mapping from domain events to WebSocket message types
    EVENT_TYPE_MAP: dict[type[DomainEvent], MessageType] = {
        SyncStarted: MessageType.SYNC_STARTED,
        SyncCompleted: MessageType.SYNC_COMPLETED,
        StoryMatched: MessageType.STORY_MATCHED,
        StoryUpdated: MessageType.STORY_UPDATED,
        SubtaskCreated: MessageType.SUBTASK_CREATED,
        SubtaskUpdated: MessageType.SUBTASK_UPDATED,
        StatusTransitioned: MessageType.STATUS_CHANGED,
        CommentAdded: MessageType.COMMENT_ADDED,
        PullStarted: MessageType.PULL_STARTED,
        PullCompleted: MessageType.PULL_COMPLETED,
        ConflictDetected: MessageType.CONFLICT_DETECTED,
        ConflictResolved: MessageType.CONFLICT_RESOLVED,
    }

    def __init__(
        self,
        server: WebSocketServerPort,
        event_bus: EventBus,
        room: str | None = None,
    ):
        """
        Initialize the broadcaster.

        Args:
            server: WebSocket server to broadcast to.
            event_bus: Event bus to subscribe to.
            room: Optional room to broadcast to (None = broadcast to all).
        """
        self.server = server
        self.event_bus = event_bus
        self.room = room
        self._logger = logging.getLogger("SyncEventBroadcaster")

    def start(self) -> None:
        """Start broadcasting events."""
        # Subscribe to all domain events
        self.event_bus.subscribe(DomainEvent, self._handle_event)
        self._logger.info(
            f"Started broadcasting to {'room ' + self.room if self.room else 'all clients'}"
        )

    def _handle_event(self, event: DomainEvent) -> None:
        """Handle a domain event and broadcast it."""
        message_type = self.EVENT_TYPE_MAP.get(type(event))
        if not message_type:
            return

        # Convert event to payload
        payload = self._event_to_payload(event)

        message = WebSocketMessage(
            type=message_type,
            payload=payload,
            room=self.room,
        )

        # Broadcast (fire and forget)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Store task reference to prevent garbage collection
                task = asyncio.create_task(self._broadcast(message))
                # Add done callback to handle any exceptions
                task.add_done_callback(
                    lambda t: t.exception() if t.done() and not t.cancelled() else None
                )
            else:
                loop.run_until_complete(self._broadcast(message))
        except RuntimeError:
            # No event loop, use threading

            if hasattr(self.server, "_broadcast_sync"):
                self.server._broadcast_sync(message)  # type: ignore

    async def _broadcast(self, message: WebSocketMessage) -> None:
        """Broadcast a message."""
        if self.room:
            await self.server.send_to_room(self.room, message)
        else:
            await self.server.broadcast(message)

    def _event_to_payload(self, event: DomainEvent) -> dict[str, Any]:
        """Convert a domain event to a WebSocket payload."""
        from dataclasses import asdict

        payload = asdict(event)

        # Convert datetime to ISO format
        if "timestamp" in payload and isinstance(payload["timestamp"], datetime):
            payload["timestamp"] = payload["timestamp"].isoformat()

        # Convert value objects to strings
        for key, value in list(payload.items()):
            if hasattr(value, "__str__") and not isinstance(
                value, (str, int, float, bool, list, dict, type(None))
            ):
                payload[key] = str(value)

        return payload


class WebSocketBridge:
    """
    High-level interface for WebSocket-based real-time sync.

    Combines WebSocket server, event broadcasting, and progress tracking
    into a single convenient interface.

    Usage:
        bridge = WebSocketBridge(host="0.0.0.0", port=8765)
        await bridge.start()

        # During sync
        bridge.send_progress(0.5, "Processing stories...")

        await bridge.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        use_aiohttp: bool = False,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize the WebSocket bridge.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            use_aiohttp: Use aiohttp server (requires async extra).
            event_bus: Optional event bus to connect for automatic broadcasting.
        """
        if use_aiohttp:
            self.server: WebSocketServerPort = AioHttpWebSocketServer(host, port)
        else:
            self.server = SimpleWebSocketServer(host, port)

        self.event_bus = event_bus
        self._broadcaster: SyncEventBroadcaster | None = None
        self._logger = logging.getLogger("WebSocketBridge")

    async def start(self) -> None:
        """Start the WebSocket server and event broadcaster."""
        await self.server.start()

        if self.event_bus:
            self._broadcaster = SyncEventBroadcaster(self.server, self.event_bus)
            self._broadcaster.start()

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        await self.server.stop()

    def send_progress(
        self,
        progress: float,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Send a progress update to all clients.

        Args:
            progress: Progress value between 0.0 and 1.0.
            message: Human-readable progress message.
            details: Additional details to include.
        """
        payload = {
            "progress": progress,
            "message": message,
            "percentage": int(progress * 100),
            **(details or {}),
        }

        msg = WebSocketMessage(
            type=MessageType.SYNC_PROGRESS,
            payload=payload,
        )

        # Fire and forget
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Store task reference to prevent garbage collection
                task = asyncio.create_task(self.server.broadcast(msg))
                task.add_done_callback(
                    lambda t: t.exception() if t.done() and not t.cancelled() else None
                )
            else:
                loop.run_until_complete(self.server.broadcast(msg))
        except RuntimeError:
            if hasattr(self.server, "_broadcast_sync"):
                self.server._broadcast_sync(msg)  # type: ignore

    async def send_sync_started(
        self,
        epic_key: str,
        markdown_path: str,
        dry_run: bool = True,
    ) -> None:
        """Send sync started notification."""
        await self.server.broadcast(
            WebSocketMessage(
                type=MessageType.SYNC_STARTED,
                payload={
                    "epicKey": epic_key,
                    "markdownPath": markdown_path,
                    "dryRun": dry_run,
                },
            )
        )

    async def send_sync_completed(
        self,
        epic_key: str,
        stories_matched: int = 0,
        stories_updated: int = 0,
        subtasks_created: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        """Send sync completed notification."""
        await self.server.broadcast(
            WebSocketMessage(
                type=MessageType.SYNC_COMPLETED,
                payload={
                    "epicKey": epic_key,
                    "storiesMatched": stories_matched,
                    "storiesUpdated": stories_updated,
                    "subtasksCreated": subtasks_created,
                    "errors": errors or [],
                    "success": not errors,
                },
            )
        )

    async def send_error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Send an error notification."""
        await self.server.broadcast(
            WebSocketMessage(
                type=MessageType.SYNC_ERROR,
                payload={
                    "error": message,
                    **(details or {}),
                },
            )
        )

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self.server.is_running

    @property
    def stats(self) -> ServerStats:
        """Get server statistics."""
        return self.server.get_stats()


def create_websocket_server(
    host: str = "0.0.0.0",
    port: int = 8765,
    use_aiohttp: bool | None = None,
) -> WebSocketServerPort:
    """
    Create a WebSocket server instance.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        use_aiohttp: Use aiohttp server (auto-detected if None).

    Returns:
        WebSocket server instance.
    """
    if use_aiohttp is None:
        try:
            import aiohttp  # noqa: F401

            use_aiohttp = True
        except ImportError:
            use_aiohttp = False

    if use_aiohttp:
        return AioHttpWebSocketServer(host, port)
    return SimpleWebSocketServer(host, port)
