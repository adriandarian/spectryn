"""Tests for the event sourcing integration module."""

from datetime import datetime, timedelta

import pytest

from spectra.adapters.event_store import MemoryEventStore
from spectra.application.sync.event_sourcing import (
    EpicHistory,
    EpicHistoryProjection,
    EventReplayer,
    EventSourcedBus,
    SyncSessionProjection,
    SyncSessionStats,
    create_event_sourced_bus,
    get_epic_history,
)
from spectra.core.domain.events import (
    CommentAdded,
    ConflictDetected,
    ConflictResolved,
    DomainEvent,
    EventBus,
    StatusTransitioned,
    StoryMatched,
    StoryUpdated,
    SubtaskCreated,
    SyncCompleted,
    SyncStarted,
)
from spectra.core.ports.event_store import make_sync_stream_id


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def event_store() -> MemoryEventStore:
    """Create a fresh memory event store."""
    return MemoryEventStore()


@pytest.fixture
def sample_sync_events() -> list[DomainEvent]:
    """Create a complete set of sync events."""
    return [
        SyncStarted(epic_key="PROJ-100", dry_run=False),
        StoryMatched(story_id="STORY-1", issue_key="JIRA-1"),
        StoryUpdated(
            issue_key="STORY-1", field_name="status", old_value="TODO", new_value="IN_PROGRESS"
        ),
        SubtaskCreated(parent_key="STORY-1", subtask_key="SUB-1", subtask_name="Task 1"),
        CommentAdded(issue_key="STORY-1", comment_type="text"),
        StatusTransitioned(
            issue_key="STORY-1",
            from_status="TODO",
            to_status="IN_PROGRESS",
        ),
        ConflictDetected(
            story_id="STORY-1",
            issue_key="JIRA-1",
            field="description",
            conflict_type="both_modified",
        ),
        ConflictResolved(
            story_id="STORY-1",
            issue_key="JIRA-1",
            field="description",
            resolution="local",
        ),
        SyncCompleted(
            epic_key="PROJ-100",
            stories_matched=1,
            stories_updated=1,
            subtasks_created=1,
            comments_added=1,
            errors=[],
        ),
    ]


# =============================================================================
# EventSourcedBus Tests
# =============================================================================


class TestEventSourcedBus:
    """Tests for the EventSourcedBus class."""

    def test_publish_persists_event(self, event_store: MemoryEventStore) -> None:
        """Test that publishing an event persists it."""
        stream_id = "test-stream"
        bus = EventSourcedBus(event_store, stream_id)

        event = SyncStarted(epic_key="TEST", dry_run=True)
        bus.publish(event)

        # Verify event is in store
        stored = list(event_store.read(stream_id))
        assert len(stored) == 1
        assert stored[0].event_type == "SyncStarted"

    def test_publish_notifies_subscribers(self, event_store: MemoryEventStore) -> None:
        """Test that publishing notifies subscribers."""
        stream_id = "test-stream"
        bus = EventSourcedBus(event_store, stream_id)

        received_events: list[DomainEvent] = []
        bus.subscribe(SyncStarted, lambda e: received_events.append(e))

        event = SyncStarted(epic_key="TEST", dry_run=True)
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0] == event

    def test_publish_batch(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test publishing a batch of events."""
        stream_id = "test-stream"
        bus = EventSourcedBus(event_store, stream_id)

        bus.publish_batch(sample_sync_events[:3])

        stored = list(event_store.read(stream_id))
        assert len(stored) == 3
        assert stored[0].sequence_number == 0
        assert stored[1].sequence_number == 1
        assert stored[2].sequence_number == 2

    def test_sequence_continues_across_publishes(self, event_store: MemoryEventStore) -> None:
        """Test that sequence numbers continue across publishes."""
        stream_id = "test-stream"
        bus = EventSourcedBus(event_store, stream_id)

        event1 = SyncStarted(epic_key="TEST", dry_run=True)
        event2 = SyncCompleted(
            epic_key="TEST",
            stories_matched=0,
            stories_updated=0,
            subtasks_created=0,
            comments_added=0,
            errors=[],
        )

        bus.publish(event1)
        bus.publish(event2)

        stored = list(event_store.read(stream_id))
        assert stored[0].sequence_number == 0
        assert stored[1].sequence_number == 1

    def test_resumes_sequence_from_store(self, event_store: MemoryEventStore) -> None:
        """Test that a new bus instance resumes from stored sequence."""
        stream_id = "test-stream"

        # First bus instance
        bus1 = EventSourcedBus(event_store, stream_id)
        bus1.publish(SyncStarted(epic_key="TEST", dry_run=True))
        bus1.publish(StoryMatched(story_id="S1", issue_key="J1"))

        # Second bus instance (simulating restart)
        bus2 = EventSourcedBus(event_store, stream_id)
        bus2.publish(
            SyncCompleted(
                epic_key="TEST",
                stories_matched=1,
                stories_updated=0,
                subtasks_created=0,
                comments_added=0,
                errors=[],
            )
        )

        stored = list(event_store.read(stream_id))
        assert len(stored) == 3
        assert stored[-1].sequence_number == 2

    def test_metadata_is_attached(self, event_store: MemoryEventStore) -> None:
        """Test that metadata is attached to all events."""
        stream_id = "test-stream"
        metadata = {"user": "test-user", "source": "test"}
        bus = EventSourcedBus(event_store, stream_id, metadata)

        bus.publish(SyncStarted(epic_key="TEST", dry_run=True))

        stored = list(event_store.read(stream_id))
        assert stored[0].metadata == metadata

    def test_stream_id_property(self, event_store: MemoryEventStore) -> None:
        """Test stream_id property."""
        stream_id = "test-stream-123"
        bus = EventSourcedBus(event_store, stream_id)
        assert bus.stream_id == stream_id


# =============================================================================
# EventReplayer Tests
# =============================================================================


class TestEventReplayer:
    """Tests for the EventReplayer class."""

    def test_replay_returns_events(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test basic event replay."""
        stream_id = "test-stream"
        event_store.append(stream_id, sample_sync_events)

        replayer = EventReplayer(event_store)
        events = replayer.replay(stream_id)

        assert len(events) == len(sample_sync_events)
        assert events[0] == sample_sync_events[0]

    def test_replay_from_sequence(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test replay from a specific sequence."""
        stream_id = "test-stream"
        event_store.append(stream_id, sample_sync_events)

        replayer = EventReplayer(event_store)
        events = replayer.replay(stream_id, from_sequence=5)

        assert len(events) == 4  # Last 4 events
        assert isinstance(events[0], StatusTransitioned)

    def test_replay_to_bus(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test replaying events to a bus."""
        stream_id = "test-stream"
        event_store.append(stream_id, sample_sync_events)

        target_bus = EventBus()
        received: list[DomainEvent] = []
        target_bus.subscribe(DomainEvent, lambda e: received.append(e))

        replayer = EventReplayer(event_store)
        count = replayer.replay_to_bus(stream_id, target_bus)

        assert count == len(sample_sync_events)
        assert len(received) == len(sample_sync_events)

    def test_replay_with_projection(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test replay through a projection."""
        stream_id = "test-stream"
        event_store.append(stream_id, sample_sync_events)

        replayer = EventReplayer(event_store)
        projection = SyncSessionProjection()
        stats = replayer.replay_with_projection(stream_id, projection)

        assert stats.stories_matched == 1
        assert stats.stories_updated == 1
        assert stats.subtasks_created == 1
        assert stats.comments_added == 1
        assert stats.status_transitions == 1
        assert stats.conflicts_detected == 1
        assert stats.conflicts_resolved == 1
        assert stats.is_complete

    def test_replay_by_epic(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test replaying all events for an epic."""
        epic_key = "PROJ-100"

        # Create multiple sessions
        event_store.append(make_sync_stream_id(epic_key, "s1"), sample_sync_events[:3])
        event_store.append(make_sync_stream_id(epic_key, "s2"), sample_sync_events[3:6])

        replayer = EventReplayer(event_store)
        stored = replayer.replay_by_epic(epic_key)

        assert len(stored) == 6

    def test_replay_by_epic_with_type_filter(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test replaying epic events with type filter."""
        epic_key = "PROJ-100"
        event_store.append(make_sync_stream_id(epic_key, "s1"), sample_sync_events)

        replayer = EventReplayer(event_store)
        stored = replayer.replay_by_epic(epic_key, event_types=["SyncStarted", "SyncCompleted"])

        assert len(stored) == 2
        assert stored[0].event_type == "SyncStarted"
        assert stored[1].event_type == "SyncCompleted"


# =============================================================================
# Projection Tests
# =============================================================================


class TestSyncSessionProjection:
    """Tests for SyncSessionProjection."""

    def test_sync_started_sets_fields(self) -> None:
        """Test that SyncStarted sets initial fields."""
        projection = SyncSessionProjection()

        event = SyncStarted(epic_key="PROJ-100", dry_run=False)
        projection.apply(event)

        assert projection.state.epic_key == "PROJ-100"
        assert projection.state.started_at == event.timestamp
        assert projection.state.is_dry_run is False

    def test_sync_completed_sets_fields(self) -> None:
        """Test that SyncCompleted sets final fields."""
        projection = SyncSessionProjection()

        event = SyncCompleted(
            epic_key="PROJ-100",
            stories_matched=5,
            stories_updated=3,
            subtasks_created=2,
            comments_added=1,
            errors=["error1"],
        )
        projection.apply(event)

        assert projection.state.is_complete
        assert projection.state.completed_at == event.timestamp
        assert "error1" in projection.state.errors

    def test_increments_counters(self) -> None:
        """Test that events increment appropriate counters."""
        projection = SyncSessionProjection()

        projection.apply(StoryMatched(story_id="S1", issue_key="J1"))
        projection.apply(StoryMatched(story_id="S2", issue_key="J2"))
        projection.apply(StoryUpdated(issue_key="S1", field_name="status", old_value="A", new_value="B"))

        assert projection.state.stories_matched == 2
        assert projection.state.stories_updated == 1


class TestEpicHistoryProjection:
    """Tests for EpicHistoryProjection."""

    def test_tracks_sessions(self, sample_sync_events: list[DomainEvent]) -> None:
        """Test that projection tracks sessions."""
        projection = EpicHistoryProjection("PROJ-100")

        for event in sample_sync_events:
            projection.apply(event)

        assert projection.state.total_sessions == 1
        assert len(projection.state.sessions) == 1

    def test_tracks_multiple_sessions(self) -> None:
        """Test tracking multiple sync sessions."""
        projection = EpicHistoryProjection("PROJ-100")

        # First session
        projection.apply(SyncStarted(epic_key="PROJ-100", dry_run=False))
        projection.apply(
            SyncCompleted(
                epic_key="PROJ-100",
                stories_matched=2,
                stories_updated=1,
                subtasks_created=0,
                comments_added=0,
                errors=[],
            )
        )

        # Second session
        projection.apply(SyncStarted(epic_key="PROJ-100", dry_run=True))
        projection.apply(
            SyncCompleted(
                epic_key="PROJ-100",
                stories_matched=3,
                stories_updated=2,
                subtasks_created=1,
                comments_added=1,
                errors=[],
            )
        )

        assert projection.state.total_sessions == 2
        assert len(projection.state.sessions) == 2
        assert projection.state.sessions[0].stories_matched == 2
        assert projection.state.sessions[1].stories_matched == 3

    def test_first_and_last_sync_timestamps(self) -> None:
        """Test first and last sync timestamps are tracked."""
        projection = EpicHistoryProjection("PROJ-100")

        event1 = SyncStarted(epic_key="PROJ-100", dry_run=False)
        event2 = SyncStarted(epic_key="PROJ-100", dry_run=False)

        projection.apply(event1)
        first_time = projection.state.first_sync_at

        projection.apply(event2)

        assert projection.state.first_sync_at == first_time
        assert projection.state.last_sync_at == event2.timestamp


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_event_sourced_bus(self, event_store: MemoryEventStore) -> None:
        """Test create_event_sourced_bus factory."""
        bus = create_event_sourced_bus(
            event_store,
            epic_key="PROJ-100",
            session_id="session-123",
            user="test-user",
        )

        assert bus.stream_id == "sync:PROJ-100:session-123"

        # Verify metadata
        bus.publish(SyncStarted(epic_key="PROJ-100", dry_run=True))
        stored = list(event_store.read(bus.stream_id))
        assert stored[0].metadata["user"] == "test-user"
        assert stored[0].metadata["epic_key"] == "PROJ-100"

    def test_get_epic_history(
        self, event_store: MemoryEventStore, sample_sync_events: list[DomainEvent]
    ) -> None:
        """Test get_epic_history helper."""
        epic_key = "PROJ-100"
        stream_id = make_sync_stream_id(epic_key, "session-1")
        event_store.append(stream_id, sample_sync_events)

        history = get_epic_history(event_store, epic_key)

        assert history.epic_key == epic_key
        assert history.total_sessions == 1
        assert history.total_events == len(sample_sync_events)
