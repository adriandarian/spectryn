"""
ClickUp Adapter - Implements IssueTrackerPort for ClickUp.

This module provides integration with ClickUp's issue tracking system.
Maps the generic IssueTrackerPort interface to ClickUp's task model.

Key mappings:
- Epic -> Goal or Folder
- Story -> Task
- Subtask -> Subtask or Checklist item
- Status -> Status (custom statuses)
- Story Points -> Story points field
"""

from .adapter import ClickUpAdapter
from .client import ClickUpApiClient


__all__ = ["ClickUpAdapter", "ClickUpApiClient"]
