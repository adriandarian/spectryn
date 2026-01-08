"""Tests for the EventStorePort and event store implementations."""

import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from spectryn.adapters.event_store import FileEventStore, MemoryEventStore
from spectryn.core.domain.events import (
    DomainEvent,
    StoryMatched,
    StoryUpdated,
    SyncCompleted,
    SyncStarted,
)
from spectryn.core.ports.event_store import (
    ConcurrencyError,
    EventQuery,
    EventStorePort,
    StoredEvent,
    make_epic_stream_id,
    make_sync_stream_id,
    parse_stream_id,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def memory_store() -> MemoryEventStore:
    """Create a fresh memory event store."""
    return MemoryEventStore()


@pytest.fixture
def file_store(tmp_path: Path) -> FileEventStore:
    """Create a file event store in a temp directory."""
    return FileEventStore(tmp_path)


@pytest.fixture
def sample_events() -> list[DomainEvent]:
    """Create sample events for testing."""
    return [
        SyncStarted(
            epic_key="PROJ-100",
            dry_run=False,
        ),
        StoryMatched(
            story_id="STORY-1",
            issue_key="JIRA-1",
        ),
        StoryUpdated(
            issue_key="STORY-1",
            field_name="status",
            old_value="TODO",
            new_value="IN_PROGRESS",
        ),
        SyncCompleted(
            epic_key="PROJ-100",
            stories_matched=1,
            stories_updated=1,
            subtasks_created=0,
            comments_added=0,
            errors=[],
        ),
    ]


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestStreamIdHelpers:
    """Tests for stream ID helper functions."""

    def test_make_sync_stream_id(self) -> None:
        """Test creating sync stream IDs."""
        stream_id = make_sync_stream_id("PROJ-100", "session-123")
        assert stream_id == "sync:PROJ-100:session-123"

    def test_make_epic_stream_id(self) -> None:
        """Test creating epic stream IDs."""
        stream_id = make_epic_stream_id("PROJ-100")
        assert stream_id == "epic:PROJ-100"

    def test_parse_stream_id_sync(self) -> None:
        """Test parsing sync stream IDs."""
        result = parse_stream_id("sync:PROJ-100:session-123")
        assert result == {"type": "sync", "epic_key": "PROJ-100", "session_id": "session-123"}

    def test_parse_stream_id_epic(self) -> None:
        """Test parsing epic stream IDs."""
        result = parse_stream_id("epic:PROJ-100")
        assert result == {"type": "epic", "epic_key": "PROJ-100"}

    def test_parse_stream_id_unknown(self) -> None:
        """Test parsing unknown stream ID format."""
        result = parse_stream_id("unknown-format")
        assert result == {"type": "unknown", "raw": "unknown-format"}


# =============================================================================
# Memory Event Store Tests
# =============================================================================


class TestMemoryEventStore:
    """Tests for the in-memory event store."""

    def test_append_single_event(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test appending a single event."""
        stream_id = "test-stream"
        stored = memory_store.append(stream_id, [sample_events[0]])

        assert len(stored) == 1
        assert stored[0].sequence_number == 0
        assert stored[0].event == sample_events[0]
        assert stored[0].stream_id == stream_id

    def test_append_multiple_events(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test appending multiple events."""
        stream_id = "test-stream"
        stored = memory_store.append(stream_id, sample_events)

        assert len(stored) == 4
        for i, event in enumerate(stored):
            assert event.sequence_number == i

    def test_read_events(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test reading events from a stream."""
        stream_id = "test-stream"
        memory_store.append(stream_id, sample_events)

        events = list(memory_store.read(stream_id))

        assert len(events) == 4
        assert events[0].event == sample_events[0]
        assert events[-1].event == sample_events[-1]

    def test_read_from_sequence(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test reading events from a specific sequence."""
        stream_id = "test-stream"
        memory_store.append(stream_id, sample_events)

        events = list(memory_store.read(stream_id, from_sequence=2))

        assert len(events) == 2
        assert events[0].sequence_number == 2

    def test_read_to_sequence(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test reading events up to a specific sequence."""
        stream_id = "test-stream"
        memory_store.append(stream_id, sample_events)

        events = list(memory_store.read(stream_id, to_sequence=1))

        assert len(events) == 2
        assert events[-1].sequence_number == 1

    def test_read_nonexistent_stream(self, memory_store: MemoryEventStore) -> None:
        """Test reading from a non-existent stream."""
        events = list(memory_store.read("nonexistent"))
        assert events == []

    def test_get_stream_info(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test getting stream info."""
        stream_id = "test-stream"
        memory_store.append(stream_id, sample_events)

        info = memory_store.get_stream_info(stream_id)

        assert info is not None
        assert info.stream_id == stream_id
        assert info.event_count == 4
        assert info.last_sequence == 3

    def test_get_stream_info_nonexistent(self, memory_store: MemoryEventStore) -> None:
        """Test getting info for non-existent stream."""
        info = memory_store.get_stream_info("nonexistent")
        assert info is None

    def test_list_streams(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test listing streams."""
        memory_store.append("sync:PROJ-100:s1", [sample_events[0]])
        memory_store.append("sync:PROJ-100:s2", [sample_events[0]])
        memory_store.append("sync:OTHER:s1", [sample_events[0]])

        streams = memory_store.list_streams("sync:PROJ-100:")
        assert len(streams) == 2
        assert "sync:PROJ-100:s1" in streams
        assert "sync:PROJ-100:s2" in streams

    def test_stream_exists(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test checking if stream exists."""
        stream_id = "test-stream"
        assert not memory_store.stream_exists(stream_id)

        memory_store.append(stream_id, [sample_events[0]])

        assert memory_store.stream_exists(stream_id)

    def test_get_last_event(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test getting the last event in a stream."""
        stream_id = "test-stream"
        memory_store.append(stream_id, sample_events)

        last = memory_store.get_last_event(stream_id)

        assert last is not None
        assert last.event == sample_events[-1]
        assert last.sequence_number == 3

    def test_query_by_event_type(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test querying by event type."""
        memory_store.append("stream", sample_events)

        query = EventQuery(event_types=["SyncStarted", "SyncCompleted"])
        events = list(memory_store.query(query))

        assert len(events) == 2
        assert events[0].event_type == "SyncStarted"
        assert events[1].event_type == "SyncCompleted"

    def test_query_by_time_range(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test querying by time range."""
        memory_store.append("stream", sample_events)

        # Query all events (time range that includes all)
        now = datetime.now()
        query = EventQuery(
            from_time=datetime(2000, 1, 1),
            to_time=now,
        )
        events = list(memory_store.query(query))

        assert len(events) == 4

    def test_query_limit(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test query result limiting."""
        memory_store.append("stream", sample_events)

        query = EventQuery(limit=2)
        events = list(memory_store.query(query))

        assert len(events) == 2

    def test_clear_stream(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test clearing a specific stream."""
        memory_store.append("stream1", sample_events)
        memory_store.append("stream2", sample_events)

        memory_store.clear_stream("stream1")

        assert not memory_store.stream_exists("stream1")
        assert memory_store.stream_exists("stream2")

    def test_clear_all(
        self, memory_store: MemoryEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test clearing all streams."""
        memory_store.append("stream1", sample_events)
        memory_store.append("stream2", sample_events)

        memory_store.clear()

        assert not memory_store.stream_exists("stream1")
        assert not memory_store.stream_exists("stream2")

    def test_optimistic_concurrency(self, memory_store: MemoryEventStore) -> None:
        """Test optimistic concurrency checking."""
        stream_id = "test-stream"
        event = SyncStarted(epic_key="TEST", dry_run=True)

        # First append succeeds
        memory_store.append(stream_id, [event])

        # Append with wrong expected version fails
        with pytest.raises(ConcurrencyError):
            memory_store.append(stream_id, [event], expected_version=5)

        # Append with correct expected version succeeds (current stream length is 1)
        stored = memory_store.append(stream_id, [event], expected_version=1)
        assert len(stored) == 1
        assert stored[0].sequence_number == 1

    def test_metadata_is_stored(self, memory_store: MemoryEventStore) -> None:
        """Test that metadata is stored with events."""
        stream_id = "test-stream"
        event = SyncStarted(epic_key="TEST", dry_run=True)
        metadata = {"user": "test-user", "source": "cli"}

        stored = memory_store.append(stream_id, [event], metadata=metadata)

        assert stored[0].metadata == metadata


# =============================================================================
# File Event Store Tests
# =============================================================================


class TestFileEventStore:
    """Tests for the file-based event store."""

    def test_append_creates_stream_file(
        self, file_store: FileEventStore, sample_events: list[DomainEvent], tmp_path: Path
    ) -> None:
        """Test that appending creates the stream file."""
        stream_id = "sync:PROJ-100:session1"
        file_store.append(stream_id, [sample_events[0]])

        # Check file exists
        stream_file = tmp_path / "sync" / "PROJ-100" / "session1.jsonl"
        assert stream_file.exists()

    def test_append_and_read_roundtrip(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test that events survive write/read cycle."""
        stream_id = "test-stream"
        file_store.append(stream_id, sample_events)

        events = list(file_store.read(stream_id))

        assert len(events) == 4
        # Check event types preserved
        assert events[0].event_type == "SyncStarted"
        assert events[1].event_type == "StoryMatched"
        assert events[2].event_type == "StoryUpdated"
        assert events[3].event_type == "SyncCompleted"

    def test_sequential_appends(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test multiple sequential appends."""
        stream_id = "test-stream"

        for i, event in enumerate(sample_events):
            stored = file_store.append(stream_id, [event])
            assert stored[0].sequence_number == i

        events = list(file_store.read(stream_id))
        assert len(events) == 4

    def test_get_stream_info(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test getting stream info."""
        stream_id = "test-stream"
        file_store.append(stream_id, sample_events)

        info = file_store.get_stream_info(stream_id)

        assert info is not None
        assert info.event_count == 4
        assert info.last_sequence == 3

    def test_list_streams(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test listing streams by prefix."""
        file_store.append("sync:PROJ-100:s1", [sample_events[0]])
        file_store.append("sync:PROJ-100:s2", [sample_events[0]])
        file_store.append("sync:OTHER:s1", [sample_events[0]])

        streams = file_store.list_streams("sync:PROJ-100:")

        assert len(streams) == 2
        assert "sync:PROJ-100:s1" in streams
        assert "sync:PROJ-100:s2" in streams

    def test_stream_persistence(self, tmp_path: Path, sample_events: list[DomainEvent]) -> None:
        """Test that events persist across store instances."""
        stream_id = "test-stream"

        # Write with first store instance
        store1 = FileEventStore(tmp_path)
        store1.append(stream_id, sample_events[:2])

        # Read with new store instance
        store2 = FileEventStore(tmp_path)
        events = list(store2.read(stream_id))

        assert len(events) == 2
        assert events[0].event_type == "SyncStarted"

    def test_delete_stream(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test deleting a stream."""
        stream_id = "test-stream"
        file_store.append(stream_id, sample_events)

        assert file_store.stream_exists(stream_id)

        file_store.delete_stream(stream_id)

        assert not file_store.stream_exists(stream_id)

    def test_query_across_streams(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test querying across multiple streams."""
        file_store.append("sync:PROJ:session1", sample_events[:2])
        file_store.append("sync:PROJ:session2", sample_events[2:])

        query = EventQuery(event_types=["SyncStarted", "SyncCompleted"])
        events = list(file_store.query(query))

        assert len(events) == 2
        assert events[0].event_type == "SyncStarted"
        assert events[1].event_type == "SyncCompleted"

    def test_query_single_stream(
        self, file_store: FileEventStore, sample_events: list[DomainEvent]
    ) -> None:
        """Test querying a single stream."""
        file_store.append("sync:PROJ:target", sample_events)
        file_store.append("sync:PROJ:other", sample_events)

        query = EventQuery(stream_id="sync:PROJ:target", event_types=["StoryMatched"])
        events = list(file_store.query(query))

        assert len(events) == 1
        assert events[0].stream_id == "sync:PROJ:target"

    def test_invalid_json_handling(
        self, file_store: FileEventStore, tmp_path: Path, sample_events: list[DomainEvent]
    ) -> None:
        """Test handling of corrupted JSON in stream file."""
        stream_id = "test-stream"
        file_store.append(stream_id, sample_events[:2])

        # Manually corrupt the file
        stream_path = file_store._stream_to_path(stream_id)
        with open(stream_path, "a") as f:
            f.write("not valid json\n")

        # Append should still work
        file_store.append(stream_id, sample_events[2:3])

        # Read should return valid events + skip invalid
        events = list(file_store.read(stream_id))
        # We should get 2 valid events + 1 more = 3 total
        assert len(events) == 3


# =============================================================================
# StoredEvent Tests
# =============================================================================


class TestStoredEvent:
    """Tests for the StoredEvent wrapper."""

    def test_stored_event_creation(self) -> None:
        """Test creating a StoredEvent."""
        event = SyncStarted(epic_key="TEST", dry_run=True)
        stored = StoredEvent(
            event=event,
            stream_id="test-stream",
            sequence_number=0,
            stored_at=datetime.now(),
        )

        assert stored.stream_id == "test-stream"
        assert stored.sequence_number == 0
        assert stored.event == event
        assert stored.event_type == "SyncStarted"

    def test_stored_event_with_metadata(self) -> None:
        """Test StoredEvent with metadata."""
        event = SyncStarted(epic_key="TEST", dry_run=True)
        metadata = {"user": "tester"}
        stored = StoredEvent(
            event=event,
            stream_id="test-stream",
            sequence_number=0,
            stored_at=datetime.now(),
            metadata=metadata,
        )

        assert stored.metadata == metadata
