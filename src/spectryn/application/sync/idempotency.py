"""
Idempotency Guarantees - Ensure re-running produces no unintended edits.

Provides guarantees that running the same sync multiple times will not:
- Create duplicate updates
- Apply changes that are already in sync
- Modify fields that haven't actually changed
- Generate unnecessary API calls

Components:
- IdempotencyGuard: Main guard class for idempotent operations
- ContentHasher: Computes hashes for content comparison
- IdempotencyCheck: Result of an idempotency check
- IdempotencyLog: Tracks operations to prevent duplicates
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.core.domain.entities import UserStory
    from spectryn.core.ports.issue_tracker import IssueData


logger = logging.getLogger(__name__)


class IdempotencyStatus(Enum):
    """Status of an idempotency check."""

    UNCHANGED = "unchanged"  # No changes needed, already in sync
    CHANGED = "changed"  # Changes detected, update needed
    NEW = "new"  # New item, create needed
    DELETED = "deleted"  # Item was deleted
    CONFLICT = "conflict"  # Both sides changed differently
    UNKNOWN = "unknown"  # Could not determine status


@dataclass
class IdempotencyCheck:
    """
    Result of checking if an operation is idempotent.

    Determines if a sync operation would actually make changes.
    """

    story_id: str
    field: str
    status: IdempotencyStatus
    local_hash: str = ""
    remote_hash: str = ""
    baseline_hash: str = ""
    message: str = ""

    @property
    def needs_sync(self) -> bool:
        """Check if sync is actually needed."""
        return self.status in (IdempotencyStatus.CHANGED, IdempotencyStatus.NEW)

    @property
    def is_unchanged(self) -> bool:
        """Check if content is unchanged."""
        return self.status == IdempotencyStatus.UNCHANGED

    def __str__(self) -> str:
        return f"{self.story_id}.{self.field}: {self.status.value} - {self.message}"


@dataclass
class IdempotencyResult:
    """Result of a full idempotency analysis."""

    total_fields_checked: int = 0
    fields_unchanged: int = 0
    fields_need_sync: int = 0
    fields_new: int = 0
    fields_conflict: int = 0

    checks: list[IdempotencyCheck] = field(default_factory=list)

    # Stories summary
    stories_unchanged: int = 0
    stories_need_sync: int = 0
    stories_fully_unchanged: set[str] = field(default_factory=set)

    @property
    def is_fully_idempotent(self) -> bool:
        """Check if running sync would be a no-op."""
        return self.fields_need_sync == 0 and self.fields_new == 0

    @property
    def skip_percentage(self) -> float:
        """Get percentage of operations that can be skipped."""
        if self.total_fields_checked == 0:
            return 100.0
        return (self.fields_unchanged / self.total_fields_checked) * 100

    @property
    def summary(self) -> str:
        """Get summary message."""
        if self.is_fully_idempotent:
            return f"✓ All {self.total_fields_checked} fields already in sync - no changes needed"
        return (
            f"Idempotency: {self.fields_unchanged}/{self.total_fields_checked} unchanged "
            f"({self.skip_percentage:.0f}% skipped), "
            f"{self.fields_need_sync} need sync, {self.fields_new} new"
        )


class ContentHasher:
    """
    Computes content hashes for idempotency comparison.

    Uses consistent hashing that normalizes content for comparison:
    - Strips whitespace
    - Normalizes line endings
    - Sorts keys in objects
    - Handles None values
    """

    @staticmethod
    def hash_text(text: str | None) -> str:
        """Hash text content."""
        if text is None:
            return "null"
        # Normalize: strip, lowercase for comparison, normalize line endings
        normalized = text.strip().replace("\r\n", "\n")
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def hash_text_strict(text: str | None) -> str:
        """Hash text content strictly (no normalization)."""
        if text is None:
            return "null"
        return hashlib.md5(text.encode()).hexdigest()[:16]

    @staticmethod
    def hash_value(value: Any) -> str:
        """Hash any value."""
        if value is None:
            return "null"
        try:
            content = json.dumps(value, sort_keys=True, default=str)
            return hashlib.md5(content.encode()).hexdigest()[:16]
        except (TypeError, ValueError):
            return hashlib.md5(str(value).encode()).hexdigest()[:16]

    @staticmethod
    def hash_list(items: list[Any]) -> str:
        """Hash a list of items."""
        if not items:
            return "empty"
        # Sort for consistent ordering
        try:
            sorted_items = sorted(str(item) for item in items)
        except TypeError:
            sorted_items = [str(item) for item in items]
        content = json.dumps(sorted_items)
        return hashlib.md5(content.encode()).hexdigest()[:16]

    @staticmethod
    def hash_status(status: Any) -> str:
        """Hash status value."""
        if status is None:
            return "null"
        status_str = str(status).lower().strip()
        return hashlib.md5(status_str.encode()).hexdigest()[:8]

    @staticmethod
    def hash_numeric(value: int | float | None) -> str:
        """Hash numeric value."""
        if value is None:
            return "null"
        return hashlib.md5(str(value).encode()).hexdigest()[:8]


@dataclass
class OperationKey:
    """Unique key for an operation to prevent duplicates."""

    epic_key: str
    issue_key: str
    operation_type: str
    field: str
    content_hash: str

    @property
    def key(self) -> str:
        """Get unique key string."""
        return f"{self.epic_key}:{self.issue_key}:{self.operation_type}:{self.field}:{self.content_hash}"


class IdempotencyLog:
    """
    Tracks executed operations to prevent duplicates.

    Stores operation keys with their content hashes to detect
    if the same operation has already been applied.
    """

    DEFAULT_DIR = Path.home() / ".spectra" / "idempotency"

    def __init__(self, log_dir: Path | None = None):
        """
        Initialize the idempotency log.

        Args:
            log_dir: Directory to store operation logs.
        """
        self.log_dir = log_dir or self.DEFAULT_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._operations: dict[str, dict] = {}
        self._current_session: str = ""
        self.logger = logging.getLogger("IdempotencyLog")

    def _get_log_path(self, epic_key: str) -> Path:
        """Get log file path for an epic."""
        return self.log_dir / f"{epic_key}_operations.json"

    def load(self, epic_key: str) -> int:
        """
        Load previous operations for an epic.

        Returns:
            Number of operations loaded.
        """
        log_path = self._get_log_path(epic_key)
        if not log_path.exists():
            self._operations = {}
            return 0

        try:
            data = json.loads(log_path.read_text())
            self._operations = data.get("operations", {})
            return len(self._operations)
        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning(f"Failed to load idempotency log: {e}")
            self._operations = {}
            return 0

    def save(self, epic_key: str) -> None:
        """Save current operations to log."""
        log_path = self._get_log_path(epic_key)
        data = {
            "epic_key": epic_key,
            "updated_at": datetime.now().isoformat(),
            "operations": self._operations,
        }
        log_path.write_text(json.dumps(data, indent=2))

    def record_operation(
        self,
        issue_key: str,
        operation_type: str,
        field: str,
        content_hash: str,
        epic_key: str = "",
    ) -> None:
        """Record an executed operation."""
        op_key = OperationKey(
            epic_key=epic_key,
            issue_key=issue_key,
            operation_type=operation_type,
            field=field,
            content_hash=content_hash,
        )
        self._operations[op_key.key] = {
            "issue_key": issue_key,
            "operation_type": operation_type,
            "field": field,
            "content_hash": content_hash,
            "executed_at": datetime.now().isoformat(),
        }

    def was_executed(
        self,
        issue_key: str,
        operation_type: str,
        field: str,
        content_hash: str,
        epic_key: str = "",
    ) -> bool:
        """Check if an operation was already executed with same content."""
        op_key = OperationKey(
            epic_key=epic_key,
            issue_key=issue_key,
            operation_type=operation_type,
            field=field,
            content_hash=content_hash,
        )
        return op_key.key in self._operations

    def clear(self, epic_key: str) -> bool:
        """Clear operation log for an epic."""
        log_path = self._get_log_path(epic_key)
        if log_path.exists():
            log_path.unlink()
            self._operations = {}
            return True
        return False


class IdempotencyGuard:
    """
    Guards sync operations to ensure idempotency.

    Checks if operations would actually make changes before executing,
    preventing unnecessary API calls and duplicate updates.

    Features:
    - Content hash comparison (local vs remote)
    - Operation deduplication
    - Skip unchanged fields
    - Detailed change detection report

    Example:
        >>> guard = IdempotencyGuard(tracker)
        >>>
        >>> # Check if description update is needed
        >>> check = guard.check_field(
        ...     story=my_story,
        ...     issue=jira_issue,
        ...     field="description"
        ... )
        >>>
        >>> if check.needs_sync:
        ...     tracker.update_description(issue.key, new_desc)
        ...     guard.record_synced(story_id, "description", new_hash)
    """

    def __init__(
        self,
        log: IdempotencyLog | None = None,
        strict_comparison: bool = False,
    ):
        """
        Initialize the guard.

        Args:
            log: Optional idempotency log for operation tracking.
            strict_comparison: If True, use strict content comparison.
        """
        self.log = log or IdempotencyLog()
        self.strict_comparison = strict_comparison
        self.hasher = ContentHasher()
        self.logger = logging.getLogger("IdempotencyGuard")

        self._checks: list[IdempotencyCheck] = []

    def check_field(
        self,
        story: UserStory,
        issue: IssueData,
        field: str,
    ) -> IdempotencyCheck:
        """
        Check if a field needs to be synced.

        Args:
            story: Local story.
            issue: Remote issue.
            field: Field to check.

        Returns:
            IdempotencyCheck with result.
        """
        story_id = str(story.id)
        local_value = self._get_local_value(story, field)
        remote_value = self._get_remote_value(issue, field)

        local_hash = self._compute_hash(local_value, field)
        remote_hash = self._compute_hash(remote_value, field)

        check = IdempotencyCheck(
            story_id=story_id,
            field=field,
            status=IdempotencyStatus.UNKNOWN,
            local_hash=local_hash,
            remote_hash=remote_hash,
        )

        # Compare hashes
        if local_hash == remote_hash:
            check.status = IdempotencyStatus.UNCHANGED
            check.message = "Content identical, no sync needed"
        else:
            check.status = IdempotencyStatus.CHANGED
            check.message = f"Content differs (local: {local_hash[:8]}, remote: {remote_hash[:8]})"

        self._checks.append(check)
        return check

    def check_story(
        self,
        story: UserStory,
        issue: IssueData | None,
        fields: list[str] | None = None,
    ) -> list[IdempotencyCheck]:
        """
        Check all fields of a story for idempotency.

        Args:
            story: Local story.
            issue: Remote issue (None if new).
            fields: Fields to check (default: all syncable fields).

        Returns:
            List of IdempotencyCheck for each field.
        """
        if fields is None:
            fields = ["description", "story_points", "status", "title"]

        checks = []

        if issue is None:
            # New story - all fields need sync
            for fld in fields:
                check = IdempotencyCheck(
                    story_id=str(story.id),
                    field=fld,
                    status=IdempotencyStatus.NEW,
                    message="New story, sync required",
                )
                checks.append(check)
                self._checks.append(check)
        else:
            for fld in fields:
                check = self.check_field(story, issue, fld)
                checks.append(check)

        return checks

    def analyze_sync(
        self,
        stories: list[UserStory],
        issues: list[IssueData],
        matches: dict[str, str],
    ) -> IdempotencyResult:
        """
        Analyze entire sync for idempotency.

        Args:
            stories: Local stories.
            issues: Remote issues.
            matches: Story ID to issue key mapping.

        Returns:
            IdempotencyResult with analysis.
        """
        result = IdempotencyResult()
        issues_by_key = {issue.key: issue for issue in issues}

        for story in stories:
            story_id = str(story.id)
            issue_key = matches.get(story_id)
            issue = issues_by_key.get(issue_key) if issue_key else None

            checks = self.check_story(story, issue)

            story_unchanged = True
            for check in checks:
                result.total_fields_checked += 1
                result.checks.append(check)

                if check.status == IdempotencyStatus.UNCHANGED:
                    result.fields_unchanged += 1
                elif check.status == IdempotencyStatus.CHANGED:
                    result.fields_need_sync += 1
                    story_unchanged = False
                elif check.status == IdempotencyStatus.NEW:
                    result.fields_new += 1
                    story_unchanged = False
                elif check.status == IdempotencyStatus.CONFLICT:
                    result.fields_conflict += 1
                    story_unchanged = False

            if story_unchanged:
                result.stories_unchanged += 1
                result.stories_fully_unchanged.add(story_id)
            else:
                result.stories_need_sync += 1

        return result

    def _get_local_value(self, story: UserStory, field: str) -> Any:
        """Get field value from local story."""
        if field == "description":
            return story.description.to_markdown() if story.description else None
        if field == "story_points":
            return story.story_points
        if field == "status":
            return story.status.value if story.status else None
        if field == "title":
            return story.title
        if field == "priority":
            return story.priority.value if story.priority else None
        return None

    def _get_remote_value(self, issue: IssueData, field: str) -> Any:
        """Get field value from remote issue."""
        if field == "description":
            return issue.description
        if field == "story_points":
            return issue.story_points
        if field == "status":
            return issue.status
        if field == "title":
            return issue.summary
        if field == "priority":
            return getattr(issue, "priority", None)
        return None

    def _compute_hash(self, value: Any, field: str) -> str:
        """Compute hash for a field value."""
        if field == "description":
            if self.strict_comparison:
                return self.hasher.hash_text_strict(value)
            return self.hasher.hash_text(value)
        if field == "story_points":
            return self.hasher.hash_numeric(value)
        if field == "status":
            return self.hasher.hash_status(value)
        return self.hasher.hash_value(value)

    def get_unchanged_story_ids(self) -> set[str]:
        """Get story IDs that are fully unchanged."""
        unchanged: dict[str, bool] = {}
        for check in self._checks:
            if check.story_id not in unchanged:
                unchanged[check.story_id] = True
            if check.status != IdempotencyStatus.UNCHANGED:
                unchanged[check.story_id] = False
        return {sid for sid, is_unchanged in unchanged.items() if is_unchanged}

    def get_fields_needing_sync(self, story_id: str) -> list[str]:
        """Get list of fields that need sync for a story."""
        return [
            check.field for check in self._checks if check.story_id == story_id and check.needs_sync
        ]

    def clear(self) -> None:
        """Clear all checks."""
        self._checks = []


def check_idempotency(
    stories: list[UserStory],
    issues: list[IssueData],
    matches: dict[str, str],
) -> IdempotencyResult:
    """
    Convenience function to check idempotency for a sync operation.

    Args:
        stories: Local stories.
        issues: Remote issues.
        matches: Story ID to issue key mapping.

    Returns:
        IdempotencyResult with analysis.
    """
    guard = IdempotencyGuard()
    return guard.analyze_sync(stories, issues, matches)


def is_content_unchanged(
    local_content: str | None,
    remote_content: str | None,
) -> bool:
    """
    Quick check if content is unchanged.

    Args:
        local_content: Local content string.
        remote_content: Remote content string.

    Returns:
        True if content is equivalent.
    """
    hasher = ContentHasher()
    return hasher.hash_text(local_content) == hasher.hash_text(remote_content)
