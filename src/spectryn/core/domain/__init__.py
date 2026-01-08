"""
Domain module - Core entities and value objects.

These are pure Python classes with no external dependencies.
They represent the core business concepts of the application.
"""

from .entities import Comment, Epic, Subtask, UserStory
from .enums import IssueType, Priority, Status
from .events import DomainEvent, StoryMatched, StoryUpdated, SubtaskCreated
from .value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)


__all__ = [
    "AcceptanceCriteria",
    "Comment",
    "CommitRef",
    "Description",
    # Events
    "DomainEvent",
    # Entities
    "Epic",
    "IssueKey",
    "IssueType",
    "Priority",
    # Enums
    "Status",
    # Value Objects
    "StoryId",
    "StoryMatched",
    "StoryUpdated",
    "Subtask",
    "SubtaskCreated",
    "UserStory",
]
