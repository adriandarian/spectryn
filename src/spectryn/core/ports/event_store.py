"""
Event Store Port - Abstract interface for event sourcing persistence.

Event sourcing stores all changes as a sequence of events. This enables:
- Complete audit trail
- Time-travel debugging
- Replay to reconstruct state
- Analytics on historical data

Concepts:
- Stream: A sequence of events for a logical aggregate (e.g., an Epic sync)
- Event: An immutable record of something that happened
- Snapshot: A materialized view at a point in time for faster replay
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from spectryn.core.domain.events import DomainEvent


@dataclass(frozen=True)
class StoredEvent:
    """
    An event as stored in the event store.

    Wraps a DomainEvent with storage metadata.

    Attributes:
        event: The domain event data.
        stream_id: Identifier for the event stream (e.g., "sync:PROJ-100:2024-01-03").
        sequence_number: Position in the stream (for ordering).
        global_position: Global position across all streams (optional).
        stored_at: When the event was persisted.
        metadata: Additional storage metadata (e.g., user, correlation_id).
    """

    event: DomainEvent
    stream_id: str
    sequence_number: int
    global_position: int | None = None
    stored_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        """Get the event type name."""
        return self.event.event_type

    @property
    def event_id(self) -> str:
        """Get the event ID."""
        return self.event.event_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        from dataclasses import asdict

        event_data = asdict(self.event)
        # Convert datetime to ISO format for JSON serialization
        if "timestamp" in event_data and isinstance(event_data["timestamp"], datetime):
            event_data["timestamp"] = event_data["timestamp"].isoformat()

        return {
            "event_type": self.event_type,
            "event_id": self.event_id,
            "event_data": event_data,
            "stream_id": self.stream_id,
            "sequence_number": self.sequence_number,
            "global_position": self.global_position,
            "stored_at": self.stored_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class StreamInfo:
    """
    Information about an event stream.

    Attributes:
        stream_id: The stream identifier.
        event_count: Number of events in the stream.
        first_event_at: Timestamp of first event.
        last_event_at: Timestamp of last event.
        last_sequence: Last sequence number.
    """

    stream_id: str
    event_count: int = 0
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    last_sequence: int = 0


@dataclass
class EventQuery:
    """
    Query parameters for reading events.

    Attributes:
        stream_id: Filter by stream (None = all streams).
        event_types: Filter by event types (None = all types).
        from_sequence: Start from this sequence number (inclusive).
        to_sequence: End at this sequence number (inclusive).
        from_time: Events after this timestamp.
        to_time: Events before this timestamp.
        limit: Maximum events to return.
        reverse: Read in reverse order (newest first).
    """

    stream_id: str | None = None
    event_types: list[str] | None = None
    from_sequence: int | None = None
    to_sequence: int | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int | None = None
    reverse: bool = False


class EventStorePort(ABC):
    """
    Abstract interface for event store implementations.

    Event stores persist domain events in append-only streams.
    This enables event sourcing patterns for complete audit trails
    and state reconstruction.

    Example usage:
        # Append events to a stream
        store.append("sync:PROJ-100:session-1", [event1, event2])

        # Read events from a stream
        for stored_event in store.read("sync:PROJ-100:session-1"):
            print(stored_event.event)

        # Query across streams
        query = EventQuery(event_types=["SyncCompleted"], limit=10)
        for stored_event in store.query(query):
            print(stored_event)
    """

    @abstractmethod
    def append(
        self,
        stream_id: str,
        events: list[DomainEvent],
        expected_version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[StoredEvent]:
        """
        Append events to a stream.

        Args:
            stream_id: The stream to append to.
            events: Events to append.
            expected_version: Expected last sequence number for optimistic concurrency.
                              If provided and doesn't match, raises ConcurrencyError.
            metadata: Optional metadata to attach to all events.

        Returns:
            List of stored events with assigned sequence numbers.

        Raises:
            ConcurrencyError: If expected_version doesn't match current version.
        """
        ...

    @abstractmethod
    def read(
        self,
        stream_id: str,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> Iterator[StoredEvent]:
        """
        Read events from a stream.

        Args:
            stream_id: The stream to read from.
            from_sequence: Start from this sequence (inclusive, default 0).
            to_sequence: End at this sequence (inclusive, default all).

        Yields:
            StoredEvent objects in sequence order.
        """
        ...

    @abstractmethod
    def query(self, query: EventQuery) -> Iterator[StoredEvent]:
        """
        Query events across streams.

        Args:
            query: Query parameters.

        Yields:
            Matching StoredEvent objects.
        """
        ...

    @abstractmethod
    def get_stream_info(self, stream_id: str) -> StreamInfo | None:
        """
        Get information about a stream.

        Args:
            stream_id: The stream identifier.

        Returns:
            StreamInfo or None if stream doesn't exist.
        """
        ...

    @abstractmethod
    def list_streams(self, prefix: str | None = None) -> list[str]:
        """
        List all stream IDs.

        Args:
            prefix: Optional prefix filter (e.g., "sync:PROJ-100:").

        Returns:
            List of stream IDs.
        """
        ...

    @abstractmethod
    def stream_exists(self, stream_id: str) -> bool:
        """
        Check if a stream exists.

        Args:
            stream_id: The stream identifier.

        Returns:
            True if stream has any events.
        """
        ...

    def get_last_event(self, stream_id: str) -> StoredEvent | None:
        """
        Get the last event in a stream.

        Default implementation reads all events. Implementations
        should override for efficiency.

        Args:
            stream_id: The stream identifier.

        Returns:
            Last StoredEvent or None if stream is empty.
        """
        info = self.get_stream_info(stream_id)
        if info is None or info.event_count == 0:
            return None

        # Read just the last event
        events = list(self.read(stream_id, from_sequence=info.last_sequence))
        return events[0] if events else None


class ConcurrencyError(Exception):
    """
    Raised when optimistic concurrency check fails.

    This happens when expected_version doesn't match the actual
    stream version, indicating another process wrote to the stream.
    """

    def __init__(self, stream_id: str, expected: int, actual: int):
        self.stream_id = stream_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Concurrency error on stream '{stream_id}': "
            f"expected version {expected}, actual {actual}"
        )


# =============================================================================
# Stream ID Helpers
# =============================================================================


def make_sync_stream_id(epic_key: str, session_id: str) -> str:
    """
    Create a stream ID for a sync session.

    Args:
        epic_key: The epic being synced.
        session_id: The sync session ID.

    Returns:
        Stream ID like "sync:PROJ-100:abc123"
    """
    return f"sync:{epic_key}:{session_id}"


def make_epic_stream_id(epic_key: str) -> str:
    """
    Create a stream ID for all events related to an epic.

    Args:
        epic_key: The epic key.

    Returns:
        Stream ID like "epic:PROJ-100"
    """
    return f"epic:{epic_key}"


def parse_stream_id(stream_id: str) -> dict[str, str]:
    """
    Parse a stream ID into its components.

    Args:
        stream_id: The stream ID to parse.

    Returns:
        Dictionary with stream type and components.
    """
    parts = stream_id.split(":")
    if len(parts) >= 2:
        stream_type = parts[0]
        if stream_type == "sync" and len(parts) >= 3:
            return {
                "type": "sync",
                "epic_key": parts[1],
                "session_id": parts[2],
            }
        if stream_type == "epic":
            return {
                "type": "epic",
                "epic_key": parts[1],
            }
    return {"type": "unknown", "raw": stream_id}
