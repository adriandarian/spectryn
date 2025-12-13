"""
Domain Events - Things that happened in the domain.

Events are immutable records of something that occurred.
They enable loose coupling and audit trails.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Union
from uuid import uuid4

from .value_objects import StoryId, IssueKey


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events."""
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def event_type(self) -> str:
        """Get the event type name."""
        return self.__class__.__name__


@dataclass(frozen=True)
class StoryMatched(DomainEvent):
    """Event: A markdown story was matched to a Jira issue."""
    
    story_id: Optional[StoryId] = None
    issue_key: Optional[Union[str, IssueKey]] = None
    match_confidence: float = 1.0  # 0.0 to 1.0
    match_method: str = "title"  # title, id, manual


@dataclass(frozen=True)
class StoryUpdated(DomainEvent):
    """Event: A story's description was updated."""
    
    issue_key: Optional[Union[str, IssueKey]] = None
    field_name: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None


@dataclass(frozen=True)
class SubtaskCreated(DomainEvent):
    """Event: A new subtask was created."""
    
    parent_key: Optional[Union[str, IssueKey]] = None
    subtask_key: Optional[Union[str, IssueKey]] = None
    subtask_name: str = ""
    story_points: int = 0


@dataclass(frozen=True)
class SubtaskUpdated(DomainEvent):
    """Event: A subtask was updated."""
    
    subtask_key: Optional[Union[str, IssueKey]] = None
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StatusTransitioned(DomainEvent):
    """Event: An issue's status changed."""
    
    issue_key: Optional[Union[str, IssueKey]] = None
    from_status: str = ""
    to_status: str = ""
    transition_id: Optional[str] = None


@dataclass(frozen=True)
class CommentAdded(DomainEvent):
    """Event: A comment was added to an issue."""
    
    issue_key: Optional[Union[str, IssueKey]] = None
    comment_type: str = "text"  # text, commits
    commit_count: int = 0


@dataclass(frozen=True)
class SyncStarted(DomainEvent):
    """Event: A sync operation started."""
    
    epic_key: Optional[Union[str, IssueKey]] = None
    markdown_path: str = ""
    dry_run: bool = True


@dataclass(frozen=True)
class SyncCompleted(DomainEvent):
    """Event: A sync operation completed."""
    
    epic_key: Optional[Union[str, IssueKey]] = None
    stories_matched: int = 0
    stories_updated: int = 0
    subtasks_created: int = 0
    comments_added: int = 0
    errors: list[str] = field(default_factory=list)


# -------------------------------------------------------------------------
# Reverse Sync (Pull) Events
# -------------------------------------------------------------------------


@dataclass(frozen=True)
class PullStarted(DomainEvent):
    """Event: A pull (reverse sync) operation started."""
    
    epic_key: Optional[Union[str, IssueKey]] = None
    output_path: str = ""
    dry_run: bool = True


@dataclass(frozen=True)
class PullCompleted(DomainEvent):
    """Event: A pull (reverse sync) operation completed."""
    
    epic_key: Optional[Union[str, IssueKey]] = None
    stories_pulled: int = 0
    stories_created: int = 0
    stories_updated: int = 0
    output_path: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StoryPulled(DomainEvent):
    """Event: A story was pulled from Jira."""
    
    issue_key: Optional[Union[str, IssueKey]] = None
    story_id: Optional[StoryId] = None
    is_new: bool = False
    changes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarkdownUpdated(DomainEvent):
    """Event: Markdown file was updated from Jira."""
    
    file_path: str = ""
    stories_added: int = 0
    stories_modified: int = 0


class EventBus:
    """
    Simple event bus for publishing and subscribing to domain events.
    
    This enables loose coupling between components.
    """
    
    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Callable[[DomainEvent], None]]] = {}
        self._history: list[DomainEvent] = []
    
    def subscribe(
        self,
        event_type: type[DomainEvent],
        handler: Callable[[DomainEvent], None],
    ) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers."""
        self._history.append(event)
        
        # Call specific handlers
        for handler in self._handlers.get(type(event), []):
            handler(event)
        
        # Call catch-all handlers
        for handler in self._handlers.get(DomainEvent, []):
            handler(event)
    
    def get_history(self) -> list[DomainEvent]:
        """Get all published events."""
        return self._history.copy()
    
    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()

