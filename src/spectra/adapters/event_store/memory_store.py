"""
In-Memory Event Store - For testing and development.

Stores events in memory with no persistence. Useful for:
- Unit tests
- Development/experimentation
- Scenarios where persistence isn't needed
"""

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from spectra.core.domain.events import DomainEvent
from spectra.core.ports.event_store import (
    ConcurrencyError,
    EventQuery,
    EventStorePort,
    StoredEvent,
    StreamInfo,
)


class MemoryEventStore(EventStorePort):
    """
    In-memory event store implementation.

    All events are stored in memory and lost when the process ends.
    Primarily used for testing.

    Example:
        store = MemoryEventStore()
        store.append("test-stream", [event1, event2])
        events = list(store.read("test-stream"))
    """

    def __init__(self) -> None:
        """Initialize the in-memory store."""
        self._streams: dict[str, list[StoredEvent]] = defaultdict(list)
        self._global_position = 0

    def append(
        self,
        stream_id: str,
        events: list[DomainEvent],
        expected_version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[StoredEvent]:
        """Append events to a stream."""
        if not events:
            return []

        stream = self._streams[stream_id]
        current_version = len(stream)

        # Check expected version
        if expected_version is not None and current_version != expected_version:
            raise ConcurrencyError(stream_id, expected_version, current_version)

        stored_events: list[StoredEvent] = []
        now = datetime.now()

        for event in events:
            self._global_position += 1
            sequence = len(stream)

            stored = StoredEvent(
                event=event,
                stream_id=stream_id,
                sequence_number=sequence,
                global_position=self._global_position,
                stored_at=now,
                metadata=metadata or {},
            )

            stream.append(stored)
            stored_events.append(stored)

        return stored_events

    def read(
        self,
        stream_id: str,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> Iterator[StoredEvent]:
        """Read events from a stream."""
        stream = self._streams.get(stream_id, [])

        for event in stream:
            if event.sequence_number < from_sequence:
                continue
            if to_sequence is not None and event.sequence_number > to_sequence:
                break
            yield event

    def query(self, query: EventQuery) -> Iterator[StoredEvent]:
        """Query events across streams."""
        # Determine which streams to search
        streams_to_search = [query.stream_id] if query.stream_id else list(self._streams.keys())

        if query.reverse:
            streams_to_search = list(reversed(streams_to_search))

        count = 0
        for stream_id in streams_to_search:
            events = list(
                self.read(
                    stream_id,
                    from_sequence=query.from_sequence or 0,
                    to_sequence=query.to_sequence,
                )
            )

            if query.reverse:
                events = list(reversed(events))

            for event in events:
                if self._matches_query(event, query):
                    yield event
                    count += 1
                    if query.limit and count >= query.limit:
                        return

    def _matches_query(self, event: StoredEvent, query: EventQuery) -> bool:
        """Check if an event matches query criteria."""
        if query.event_types and event.event_type not in query.event_types:
            return False

        if query.from_time and event.stored_at < query.from_time:
            return False
        return not (query.to_time and event.stored_at > query.to_time)

    def get_stream_info(self, stream_id: str) -> StreamInfo | None:
        """Get information about a stream."""
        stream = self._streams.get(stream_id)

        if stream is None or len(stream) == 0:
            return None

        return StreamInfo(
            stream_id=stream_id,
            event_count=len(stream),
            first_event_at=stream[0].stored_at,
            last_event_at=stream[-1].stored_at,
            last_sequence=len(stream) - 1,
        )

    def list_streams(self, prefix: str | None = None) -> list[str]:
        """List all stream IDs."""
        streams = list(self._streams.keys())

        if prefix:
            streams = [s for s in streams if s.startswith(prefix)]

        return sorted(streams)

    def stream_exists(self, stream_id: str) -> bool:
        """Check if a stream exists."""
        return stream_id in self._streams and len(self._streams[stream_id]) > 0

    def get_last_event(self, stream_id: str) -> StoredEvent | None:
        """Get the last event in a stream."""
        stream = self._streams.get(stream_id)

        if not stream:
            return None

        return stream[-1]

    def clear(self) -> None:
        """Clear all events (for testing)."""
        self._streams.clear()
        self._global_position = 0

    def clear_stream(self, stream_id: str) -> None:
        """Clear a specific stream (for testing)."""
        if stream_id in self._streams:
            del self._streams[stream_id]
