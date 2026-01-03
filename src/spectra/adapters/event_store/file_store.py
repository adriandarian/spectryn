"""
File-based Event Store - Persist events to local JSON files.

Stores events in append-only JSON files, one file per stream.
This provides durable event storage without requiring a database.

File structure:
    .spectra/events/
        sync/
            PROJ-100/
                session-abc123.jsonl
                session-def456.jsonl
        epic/
            PROJ-100.jsonl
            PROJ-200.jsonl
        _global_index.json  # Optional global position tracking
"""

import contextlib
import fcntl
import json
import logging
import os
import re
from collections.abc import Iterator
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from spectra.core.domain.events import DomainEvent
from spectra.core.ports.event_store import (
    ConcurrencyError,
    EventQuery,
    EventStorePort,
    StoredEvent,
    StreamInfo,
)


logger = logging.getLogger(__name__)


class FileEventStore(EventStorePort):
    """
    File-based event store implementation.

    Stores events in JSON Lines format (.jsonl) for efficient appending.
    Each stream gets its own file organized by type.

    Features:
    - Append-only writes for durability
    - File locking for concurrency safety
    - JSON Lines format for streaming reads
    - Organized directory structure
    - Automatic directory creation

    Example:
        store = FileEventStore(Path(".spectra/events"))
        store.append("sync:PROJ-100:session1", [event])
    """

    def __init__(
        self,
        base_path: Path | str,
        create_dirs: bool = True,
    ):
        """
        Initialize the file event store.

        Args:
            base_path: Base directory for event files.
            create_dirs: Whether to create directories if they don't exist.
        """
        self.base_path = Path(base_path)
        self._global_position = 0
        self._global_position_file = self.base_path / "_global_position.txt"

        if create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)
            self._load_global_position()

    def _load_global_position(self) -> None:
        """Load the global position counter from disk."""
        if self._global_position_file.exists():
            try:
                self._global_position = int(self._global_position_file.read_text().strip())
            except (ValueError, OSError):
                self._global_position = 0

    def _save_global_position(self) -> None:
        """Save the global position counter to disk."""
        try:
            self._global_position_file.write_text(str(self._global_position))
        except OSError as e:
            logger.warning(f"Failed to save global position: {e}")

    def _stream_to_path(self, stream_id: str) -> Path:
        """
        Convert a stream ID to a file path.

        Args:
            stream_id: Stream identifier (e.g., "sync:PROJ-100:session1").

        Returns:
            Path to the stream file.
        """
        # Parse stream ID and create organized structure
        parts = stream_id.split(":")

        if len(parts) >= 2:
            stream_type = parts[0]
            if stream_type == "sync" and len(parts) >= 3:
                # sync:EPIC-KEY:session -> sync/EPIC-KEY/session.jsonl
                epic_key = self._sanitize_filename(parts[1])
                session_id = self._sanitize_filename(parts[2])
                return self.base_path / "sync" / epic_key / f"{session_id}.jsonl"
            if stream_type == "epic":
                # epic:EPIC-KEY -> epic/EPIC-KEY.jsonl
                epic_key = self._sanitize_filename(parts[1])
                return self.base_path / "epic" / f"{epic_key}.jsonl"

        # Fallback: sanitize and use as filename
        safe_name = self._sanitize_filename(stream_id)
        return self.base_path / "other" / f"{safe_name}.jsonl"

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use as a filename.

        Args:
            name: The string to sanitize.

        Returns:
            Safe filename string.
        """
        # Replace invalid characters with underscore
        return re.sub(r'[<>:"/\\|?*]', "_", name)

    def _serialize_event(self, event: DomainEvent) -> dict[str, Any]:
        """
        Serialize a domain event to a dictionary.

        Args:
            event: The event to serialize.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        data = asdict(event)

        # Convert datetime to ISO format
        if "timestamp" in data and isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        return data

    def _deserialize_event(self, data: dict[str, Any]) -> DomainEvent:
        """
        Deserialize a dictionary to a domain event.

        Args:
            data: The dictionary to deserialize.

        Returns:
            The reconstructed DomainEvent.
        """
        from spectra.core.domain.events import (
            CommentAdded,
            ConflictCheckCompleted,
            ConflictDetected,
            ConflictResolved,
            MarkdownUpdated,
            PullCompleted,
            PullStarted,
            StatusTransitioned,
            StoryMatched,
            StoryPulled,
            StoryUpdated,
            SubtaskCreated,
            SubtaskUpdated,
            SyncCompleted,
            SyncStarted,
        )

        event_type = data.get("event_type", "DomainEvent")
        event_data = data.get("event_data", data)

        # Parse timestamp back to datetime
        if "timestamp" in event_data and isinstance(event_data["timestamp"], str):
            with contextlib.suppress(ValueError):
                event_data["timestamp"] = datetime.fromisoformat(event_data["timestamp"])

        # Map event type to class
        event_classes: dict[str, type[DomainEvent]] = {
            "StoryMatched": StoryMatched,
            "StoryUpdated": StoryUpdated,
            "SubtaskCreated": SubtaskCreated,
            "SubtaskUpdated": SubtaskUpdated,
            "StatusTransitioned": StatusTransitioned,
            "CommentAdded": CommentAdded,
            "SyncStarted": SyncStarted,
            "SyncCompleted": SyncCompleted,
            "PullStarted": PullStarted,
            "PullCompleted": PullCompleted,
            "StoryPulled": StoryPulled,
            "MarkdownUpdated": MarkdownUpdated,
            "ConflictDetected": ConflictDetected,
            "ConflictResolved": ConflictResolved,
            "ConflictCheckCompleted": ConflictCheckCompleted,
        }

        event_class = event_classes.get(event_type, DomainEvent)

        # Filter to only valid fields for the event class
        import dataclasses

        valid_fields = {f.name for f in dataclasses.fields(event_class)}
        filtered_data = {k: v for k, v in event_data.items() if k in valid_fields}

        try:
            return event_class(**filtered_data)
        except TypeError:
            # Fallback to base DomainEvent
            return DomainEvent(
                event_id=event_data.get("event_id", ""),
                timestamp=event_data.get("timestamp", datetime.now()),
            )

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

        file_path = self._stream_to_path(stream_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        stored_events: list[StoredEvent] = []

        # Use file locking for concurrency safety
        mode = "a+" if file_path.exists() else "w+"

        with open(file_path, mode, encoding="utf-8") as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

            try:
                # Get current sequence number
                f.seek(0)
                lines = f.readlines()
                current_sequence = len(lines)

                # Check expected version for optimistic concurrency
                if expected_version is not None and current_sequence != expected_version:
                    raise ConcurrencyError(stream_id, expected_version, current_sequence)

                # Append events
                now = datetime.now()
                for event in events:
                    self._global_position += 1
                    sequence = current_sequence
                    current_sequence += 1

                    stored = StoredEvent(
                        event=event,
                        stream_id=stream_id,
                        sequence_number=sequence,
                        global_position=self._global_position,
                        stored_at=now,
                        metadata=metadata or {},
                    )

                    # Write JSON line
                    line = json.dumps(stored.to_dict(), default=str) + "\n"
                    f.write(line)

                    stored_events.append(stored)

                f.flush()
                os.fsync(f.fileno())  # Ensure durability

            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Save global position periodically
        if self._global_position % 100 == 0:
            self._save_global_position()

        logger.debug(
            f"Appended {len(events)} events to stream '{stream_id}' "
            f"(sequences {stored_events[0].sequence_number}-{stored_events[-1].sequence_number})"
        )

        return stored_events

    def read(
        self,
        stream_id: str,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> Iterator[StoredEvent]:
        """Read events from a stream."""
        file_path = self._stream_to_path(stream_id)

        if not file_path.exists():
            return

        with open(file_path, encoding="utf-8") as f:
            # Acquire shared lock for reading
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)

            try:
                for line_num, line in enumerate(f):
                    if line_num < from_sequence:
                        continue
                    if to_sequence is not None and line_num > to_sequence:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        event = self._deserialize_event(data)

                        # Parse stored_at back to datetime
                        stored_at = data.get("stored_at")
                        if isinstance(stored_at, str):
                            try:
                                stored_at = datetime.fromisoformat(stored_at)
                            except ValueError:
                                stored_at = datetime.now()
                        elif not isinstance(stored_at, datetime):
                            stored_at = datetime.now()

                        yield StoredEvent(
                            event=event,
                            stream_id=data.get("stream_id", stream_id),
                            sequence_number=data.get("sequence_number", line_num),
                            global_position=data.get("global_position"),
                            stored_at=stored_at,
                            metadata=data.get("metadata", {}),
                        )
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse event at line {line_num}: {e}")
                        continue

            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def query(self, query: EventQuery) -> Iterator[StoredEvent]:
        """Query events across streams."""
        # If specific stream requested, just read that stream
        if query.stream_id:
            for event in self.read(
                query.stream_id,
                from_sequence=query.from_sequence or 0,
                to_sequence=query.to_sequence,
            ):
                if self._matches_query(event, query):
                    yield event
            return

        # Otherwise, scan all streams
        streams = self.list_streams()
        if query.reverse:
            streams = list(reversed(streams))

        count = 0
        for stream_id in streams:
            for event in self.read(stream_id):
                if self._matches_query(event, query):
                    yield event
                    count += 1
                    if query.limit and count >= query.limit:
                        return

    def _matches_query(self, event: StoredEvent, query: EventQuery) -> bool:
        """Check if an event matches query criteria."""
        # Filter by event type
        if query.event_types and event.event_type not in query.event_types:
            return False

        # Filter by time range
        if query.from_time and event.stored_at < query.from_time:
            return False
        return not (query.to_time and event.stored_at > query.to_time)

    def get_stream_info(self, stream_id: str) -> StreamInfo | None:
        """Get information about a stream."""
        file_path = self._stream_to_path(stream_id)

        if not file_path.exists():
            return None

        event_count = 0
        first_event_at: datetime | None = None
        last_event_at: datetime | None = None

        for event in self.read(stream_id):
            event_count += 1
            if first_event_at is None:
                first_event_at = event.stored_at
            last_event_at = event.stored_at

        return StreamInfo(
            stream_id=stream_id,
            event_count=event_count,
            first_event_at=first_event_at,
            last_event_at=last_event_at,
            last_sequence=event_count - 1 if event_count > 0 else 0,
        )

    def list_streams(self, prefix: str | None = None) -> list[str]:
        """List all stream IDs."""
        streams: list[str] = []

        if not self.base_path.exists():
            return streams

        # Walk the directory structure
        for jsonl_file in self.base_path.rglob("*.jsonl"):
            # Reconstruct stream ID from path
            rel_path = jsonl_file.relative_to(self.base_path)
            parts = list(rel_path.parts)

            if len(parts) >= 2 and parts[0] == "sync":
                # sync/EPIC-KEY/session.jsonl -> sync:EPIC-KEY:session
                epic_key = parts[1]
                session = parts[2].replace(".jsonl", "")
                stream_id = f"sync:{epic_key}:{session}"
            elif len(parts) >= 1 and parts[0] == "epic":
                # epic/EPIC-KEY.jsonl -> epic:EPIC-KEY
                epic_key = parts[-1].replace(".jsonl", "")
                stream_id = f"epic:{epic_key}"
            else:
                # Fallback
                stream_id = str(rel_path).replace("/", ":").replace(".jsonl", "")

            if prefix is None or stream_id.startswith(prefix):
                streams.append(stream_id)

        return sorted(streams)

    def stream_exists(self, stream_id: str) -> bool:
        """Check if a stream exists."""
        return self._stream_to_path(stream_id).exists()

    def get_last_event(self, stream_id: str) -> StoredEvent | None:
        """Get the last event in a stream (optimized)."""
        file_path = self._stream_to_path(stream_id)

        if not file_path.exists():
            return None

        # Read last line efficiently
        with open(file_path, "rb") as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()

            if file_size == 0:
                return None

            # Read backwards to find last newline
            buffer_size = min(4096, file_size)
            f.seek(max(0, file_size - buffer_size))
            last_lines = f.read().decode("utf-8").strip().split("\n")

            if not last_lines:
                return None

            last_line = last_lines[-1]

        try:
            data = json.loads(last_line)
            event = self._deserialize_event(data)

            stored_at = data.get("stored_at")
            if isinstance(stored_at, str):
                stored_at = datetime.fromisoformat(stored_at)
            elif not isinstance(stored_at, datetime):
                stored_at = datetime.now()

            return StoredEvent(
                event=event,
                stream_id=data.get("stream_id", stream_id),
                sequence_number=data.get("sequence_number", 0),
                global_position=data.get("global_position"),
                stored_at=stored_at,
                metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def delete_stream(self, stream_id: str) -> bool:
        """
        Delete a stream and all its events.

        Note: This violates event sourcing principles and should
        only be used for cleanup/maintenance.

        Args:
            stream_id: The stream to delete.

        Returns:
            True if stream was deleted, False if it didn't exist.
        """
        file_path = self._stream_to_path(stream_id)

        if not file_path.exists():
            return False

        file_path.unlink()
        logger.info(f"Deleted stream '{stream_id}'")

        # Clean up empty directories
        with contextlib.suppress(OSError):
            file_path.parent.rmdir()

        return True

    def compact_stream(self, stream_id: str) -> int:
        """
        Compact a stream by removing corrupted lines.

        Args:
            stream_id: The stream to compact.

        Returns:
            Number of events after compaction.
        """
        file_path = self._stream_to_path(stream_id)

        if not file_path.exists():
            return 0

        # Read all valid events
        valid_events: list[str] = []

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    valid_events.append(line)
                except json.JSONDecodeError:
                    logger.warning(f"Removing corrupted line from {stream_id}")

        # Rewrite file with valid events only
        with open(file_path, "w", encoding="utf-8") as f:
            for line in valid_events:
                f.write(line + "\n")

        return len(valid_events)
