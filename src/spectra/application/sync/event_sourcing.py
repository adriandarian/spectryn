"""
Event Sourcing Integration - Connect EventBus to EventStore.

This module provides:
- EventSourcedBus: An EventBus that persists events to an EventStore
- EventReplayer: Replay events to reconstruct state
- Projection helpers for building read models from events
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

from spectra.core.domain.events import DomainEvent, EventBus
from spectra.core.ports.event_store import (
    EventStorePort,
    StoredEvent,
    make_epic_stream_id,
    make_sync_stream_id,
)


logger = logging.getLogger(__name__)


T = TypeVar("T")


class EventSourcedBus(EventBus):
    """
    An EventBus that persists events to an EventStore.

    Extends the standard EventBus to automatically save all published
    events to a durable event store. This enables event sourcing patterns.

    Example:
        store = FileEventStore(".spectra/events")
        bus = EventSourcedBus(store, stream_id="sync:PROJ-100:session1")

        bus.publish(SyncStarted(...))  # Automatically persisted

        # Later, replay events
        replayer = EventReplayer(store)
        events = replayer.replay("sync:PROJ-100:session1")
    """

    def __init__(
        self,
        event_store: EventStorePort,
        stream_id: str,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize the event-sourced bus.

        Args:
            event_store: The event store to persist to.
            stream_id: The stream ID for this session.
            metadata: Optional metadata to attach to all events.
        """
        super().__init__()
        self._store = event_store
        self._stream_id = stream_id
        self._metadata = metadata or {}
        self._sequence = 0

        # Load current sequence from store
        info = self._store.get_stream_info(stream_id)
        if info:
            self._sequence = info.last_sequence + 1

    @property
    def stream_id(self) -> str:
        """Get the stream ID for this bus."""
        return self._stream_id

    def publish(self, event: DomainEvent) -> None:
        """
        Publish an event to subscribers and persist to store.

        Args:
            event: The event to publish.
        """
        # Persist to store first (for durability)
        stored = self._store.append(
            self._stream_id,
            [event],
            metadata=self._metadata,
        )

        if stored:
            self._sequence = stored[-1].sequence_number + 1

        # Then notify subscribers
        super().publish(event)

    def publish_batch(self, events: list[DomainEvent]) -> None:
        """
        Publish multiple events atomically.

        All events are persisted together, then subscribers notified.

        Args:
            events: Events to publish.
        """
        if not events:
            return

        # Persist all events atomically
        stored = self._store.append(
            self._stream_id,
            events,
            metadata=self._metadata,
        )

        if stored:
            self._sequence = stored[-1].sequence_number + 1

        # Notify subscribers
        for event in events:
            super().publish(event)


class EventReplayer:
    """
    Replay events from an EventStore.

    Enables reconstructing state by replaying historical events.

    Example:
        replayer = EventReplayer(store)

        # Replay all events in a stream
        for event in replayer.replay("sync:PROJ-100:session1"):
            process(event)

        # Replay with projection
        stats = replayer.replay_with_projection(
            "sync:PROJ-100:session1",
            SyncStatsProjection()
        )
    """

    def __init__(self, event_store: EventStorePort):
        """
        Initialize the replayer.

        Args:
            event_store: The event store to replay from.
        """
        self._store = event_store

    def replay(
        self,
        stream_id: str,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> list[DomainEvent]:
        """
        Replay events from a stream.

        Args:
            stream_id: The stream to replay.
            from_sequence: Start from this sequence (inclusive).
            to_sequence: End at this sequence (inclusive).

        Returns:
            List of domain events in order.
        """
        events: list[DomainEvent] = []

        for stored in self._store.read(stream_id, from_sequence, to_sequence):
            events.append(stored.event)

        return events

    def replay_to_bus(
        self,
        stream_id: str,
        event_bus: EventBus,
        from_sequence: int = 0,
    ) -> int:
        """
        Replay events by publishing to an EventBus.

        Useful for re-hydrating handlers with historical events.

        Args:
            stream_id: The stream to replay.
            event_bus: The bus to publish events to.
            from_sequence: Start from this sequence.

        Returns:
            Number of events replayed.
        """
        count = 0

        for stored in self._store.read(stream_id, from_sequence):
            event_bus.publish(stored.event)
            count += 1

        logger.info(f"Replayed {count} events from stream '{stream_id}'")
        return count

    def replay_with_projection(
        self,
        stream_id: str,
        projection: "Projection[T]",
        from_sequence: int = 0,
    ) -> T:
        """
        Replay events through a projection to build state.

        Args:
            stream_id: The stream to replay.
            projection: The projection to apply events to.
            from_sequence: Start from this sequence.

        Returns:
            The final projection state.
        """
        for stored in self._store.read(stream_id, from_sequence):
            projection.apply(stored.event)

        return projection.state

    def replay_by_epic(
        self,
        epic_key: str,
        event_types: list[str] | None = None,
    ) -> list[StoredEvent]:
        """
        Replay all events related to an epic across all sessions.

        Args:
            epic_key: The epic key to find events for.
            event_types: Optional filter by event types.

        Returns:
            List of stored events ordered by time.
        """
        # Find all sync streams for this epic
        prefix = f"sync:{epic_key}:"
        streams = self._store.list_streams(prefix)

        # Also check the epic stream
        epic_stream = make_epic_stream_id(epic_key)
        if self._store.stream_exists(epic_stream):
            streams.append(epic_stream)

        all_events: list[StoredEvent] = []

        for stream_id in streams:
            for stored in self._store.read(stream_id):
                if event_types and stored.event_type not in event_types:
                    continue
                all_events.append(stored)

        # Sort by global position or stored_at
        all_events.sort(key=lambda e: e.global_position or 0)

        return all_events


@dataclass
class Projection(Generic[T]):
    """
    Base class for event projections.

    A projection transforms a stream of events into a read model.
    Override the `apply` method to handle specific event types.

    Example:
        @dataclass
        class SyncStats:
            total_syncs: int = 0
            stories_updated: int = 0

        class SyncStatsProjection(Projection[SyncStats]):
            def __init__(self):
                super().__init__(SyncStats())

            def apply(self, event: DomainEvent) -> None:
                if isinstance(event, SyncCompleted):
                    self.state.total_syncs += 1
                    self.state.stories_updated += event.stories_updated
    """

    state: T

    def apply(self, event: DomainEvent) -> None:
        """
        Apply an event to update the projection state.

        Override this method to handle specific event types.

        Args:
            event: The event to apply.
        """


# =============================================================================
# Built-in Projections
# =============================================================================


@dataclass
class SyncSessionStats:
    """Statistics for a sync session."""

    session_id: str = ""
    epic_key: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stories_matched: int = 0
    stories_updated: int = 0
    subtasks_created: int = 0
    comments_added: int = 0
    status_transitions: int = 0
    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    errors: list[str] = field(default_factory=list)
    is_dry_run: bool = True
    is_complete: bool = False


class SyncSessionProjection(Projection[SyncSessionStats]):
    """
    Project a sync stream into session statistics.

    Example:
        projection = SyncSessionProjection()
        replayer = EventReplayer(store)
        stats = replayer.replay_with_projection(stream_id, projection)
        print(f"Updated {stats.stories_updated} stories")
    """

    def __init__(self) -> None:
        from spectra.core.domain.events import (
            CommentAdded,
            ConflictDetected,
            ConflictResolved,
            StatusTransitioned,
            StoryMatched,
            StoryUpdated,
            SubtaskCreated,
            SyncCompleted,
            SyncStarted,
        )

        super().__init__(SyncSessionStats())
        self._event_handlers: dict[type, Callable[[DomainEvent], None]] = {
            SyncStarted: self._handle_sync_started,
            SyncCompleted: self._handle_sync_completed,
            StoryMatched: self._handle_story_matched,
            StoryUpdated: self._handle_story_updated,
            SubtaskCreated: self._handle_subtask_created,
            CommentAdded: self._handle_comment_added,
            StatusTransitioned: self._handle_status_transitioned,
            ConflictDetected: self._handle_conflict_detected,
            ConflictResolved: self._handle_conflict_resolved,
        }

    def apply(self, event: DomainEvent) -> None:
        """Apply an event to update statistics."""
        handler = self._event_handlers.get(type(event))
        if handler:
            handler(event)

    def _handle_sync_started(self, event: DomainEvent) -> None:
        from spectra.core.domain.events import SyncStarted

        if isinstance(event, SyncStarted):
            self.state.epic_key = str(event.epic_key) if event.epic_key else ""
            self.state.started_at = event.timestamp
            self.state.is_dry_run = event.dry_run

    def _handle_sync_completed(self, event: DomainEvent) -> None:
        from spectra.core.domain.events import SyncCompleted

        if isinstance(event, SyncCompleted):
            self.state.completed_at = event.timestamp
            self.state.is_complete = True
            if event.errors:
                self.state.errors.extend(event.errors)

    def _handle_story_matched(self, event: DomainEvent) -> None:
        self.state.stories_matched += 1

    def _handle_story_updated(self, event: DomainEvent) -> None:
        self.state.stories_updated += 1

    def _handle_subtask_created(self, event: DomainEvent) -> None:
        self.state.subtasks_created += 1

    def _handle_comment_added(self, event: DomainEvent) -> None:
        self.state.comments_added += 1

    def _handle_status_transitioned(self, event: DomainEvent) -> None:
        self.state.status_transitions += 1

    def _handle_conflict_detected(self, event: DomainEvent) -> None:
        self.state.conflicts_detected += 1

    def _handle_conflict_resolved(self, event: DomainEvent) -> None:
        self.state.conflicts_resolved += 1


@dataclass
class EpicHistory:
    """Historical record of all sync operations for an epic."""

    epic_key: str = ""
    total_sessions: int = 0
    total_events: int = 0
    first_sync_at: datetime | None = None
    last_sync_at: datetime | None = None
    sessions: list[SyncSessionStats] = field(default_factory=list)


class EpicHistoryProjection(Projection[EpicHistory]):
    """
    Project all events for an epic into a history view.

    Aggregates data across multiple sync sessions.
    """

    def __init__(self, epic_key: str) -> None:
        super().__init__(EpicHistory(epic_key=epic_key))
        self._current_session: SyncSessionStats | None = None

    def apply(self, event: DomainEvent) -> None:
        from spectra.core.domain.events import SyncCompleted, SyncStarted

        self.state.total_events += 1

        if isinstance(event, SyncStarted):
            # Start new session
            self._current_session = SyncSessionStats(
                epic_key=str(event.epic_key) if event.epic_key else "",
                started_at=event.timestamp,
                is_dry_run=event.dry_run,
            )
            self.state.total_sessions += 1

            if self.state.first_sync_at is None:
                self.state.first_sync_at = event.timestamp
            self.state.last_sync_at = event.timestamp

        elif isinstance(event, SyncCompleted):
            if self._current_session:
                self._current_session.completed_at = event.timestamp
                self._current_session.is_complete = True
                self._current_session.stories_matched = event.stories_matched
                self._current_session.stories_updated = event.stories_updated
                self._current_session.subtasks_created = event.subtasks_created
                self._current_session.comments_added = event.comments_added
                if event.errors:
                    self._current_session.errors = list(event.errors)

                self.state.sessions.append(self._current_session)
                self._current_session = None


# =============================================================================
# Factory Functions
# =============================================================================


def create_event_sourced_bus(
    event_store: EventStorePort,
    epic_key: str,
    session_id: str,
    user: str | None = None,
) -> EventSourcedBus:
    """
    Create an event-sourced bus for a sync session.

    Args:
        event_store: The event store to use.
        epic_key: The epic being synced.
        session_id: The sync session ID.
        user: Optional username for metadata.

    Returns:
        Configured EventSourcedBus.
    """
    stream_id = make_sync_stream_id(epic_key, session_id)

    metadata: dict[str, Any] = {
        "epic_key": epic_key,
        "session_id": session_id,
    }
    if user:
        metadata["user"] = user

    return EventSourcedBus(event_store, stream_id, metadata)


def get_epic_history(
    event_store: EventStorePort,
    epic_key: str,
) -> EpicHistory:
    """
    Get the complete sync history for an epic.

    Args:
        event_store: The event store to query.
        epic_key: The epic key.

    Returns:
        EpicHistory with all sessions.
    """
    replayer = EventReplayer(event_store)
    projection = EpicHistoryProjection(epic_key)

    # Replay all events for this epic
    for stored in replayer.replay_by_epic(epic_key):
        projection.apply(stored.event)

    return projection.state
