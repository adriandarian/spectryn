"""
Backup Manager - Auto-backup Jira state before modifications.

Captures the current state of issues before sync operations,
allowing recovery if something goes wrong.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectra.core.ports.issue_tracker import IssueData, IssueTrackerPort


logger = logging.getLogger(__name__)


@dataclass
class RestoreOperation:
    """
    Record of a single restore operation.

    Tracks what was restored and whether it succeeded.
    """

    issue_key: str
    field: str  # description, story_points, etc.
    success: bool = True
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "issue_key": self.issue_key,
            "field": self.field,
            "success": self.success,
            "error": self.error,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class RestoreResult:
    """
    Result of a restore operation.

    Tracks all operations performed during restore.
    """

    backup_id: str
    epic_key: str
    dry_run: bool = True
    success: bool = True
    issues_restored: int = 0
    subtasks_restored: int = 0
    operations: list[RestoreOperation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    def add_operation(self, op: RestoreOperation) -> None:
        """Add an operation result."""
        self.operations.append(op)
        if not op.success and not op.skipped:
            self.success = False
            if op.error:
                self.errors.append(f"{op.issue_key} ({op.field}): {op.error}")

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def complete(self) -> None:
        """Mark the restore as complete."""
        self.completed_at = datetime.now().isoformat()

    @property
    def total_operations(self) -> int:
        """Total number of operations attempted."""
        return len(self.operations)

    @property
    def successful_operations(self) -> int:
        """Number of successful operations."""
        return sum(1 for op in self.operations if op.success and not op.skipped)

    @property
    def failed_operations(self) -> int:
        """Number of failed operations."""
        return sum(1 for op in self.operations if not op.success and not op.skipped)

    @property
    def skipped_operations(self) -> int:
        """Number of skipped operations."""
        return sum(1 for op in self.operations if op.skipped)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = []

        if self.dry_run:
            lines.append("DRY RUN - No changes made")

        if self.success:
            lines.append("✓ Restore completed successfully")
        else:
            lines.append(f"✗ Restore completed with errors ({len(self.errors)} failures)")

        lines.append(f"  Backup: {self.backup_id}")
        lines.append(f"  Epic: {self.epic_key}")
        lines.append(f"  Issues restored: {self.issues_restored}")
        lines.append(f"  Subtasks restored: {self.subtasks_restored}")
        lines.append(
            f"  Operations: {self.successful_operations} succeeded, {self.failed_operations} failed, {self.skipped_operations} skipped"
        )

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors[:5]:
                lines.append(f"  • {error}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in self.warnings[:5]:
                lines.append(f"  • {warning}")
            if len(self.warnings) > 5:
                lines.append(f"  ... and {len(self.warnings) - 5} more")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "backup_id": self.backup_id,
            "epic_key": self.epic_key,
            "dry_run": self.dry_run,
            "success": self.success,
            "issues_restored": self.issues_restored,
            "subtasks_restored": self.subtasks_restored,
            "operations": [op.to_dict() for op in self.operations],
            "errors": self.errors,
            "warnings": self.warnings,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class IssueSnapshot:
    """
    Snapshot of a single issue's state.

    Captures all mutable fields that could be modified during sync.
    """

    key: str
    summary: str
    description: Any | None = None
    status: str = ""
    issue_type: str = ""
    assignee: str | None = None
    story_points: float | None = None
    subtasks: list["IssueSnapshot"] = field(default_factory=list)
    comments_count: int = 0
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "summary": self.summary,
            "description": self.description,
            "status": self.status,
            "issue_type": self.issue_type,
            "assignee": self.assignee,
            "story_points": self.story_points,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "comments_count": self.comments_count,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IssueSnapshot":
        """Create from dictionary."""
        subtasks = [cls.from_dict(st) for st in data.get("subtasks", [])]
        return cls(
            key=data["key"],
            summary=data.get("summary", ""),
            description=data.get("description"),
            status=data.get("status", ""),
            issue_type=data.get("issue_type", ""),
            assignee=data.get("assignee"),
            story_points=data.get("story_points"),
            subtasks=subtasks,
            comments_count=data.get("comments_count", 0),
            captured_at=data.get("captured_at", datetime.now().isoformat()),
        )

    @classmethod
    def from_issue_data(cls, issue: "IssueData", comments_count: int = 0) -> "IssueSnapshot":
        """Create snapshot from IssueData."""
        subtasks = [
            cls(
                key=st.key,
                summary=st.summary,
                description=st.description,
                status=st.status,
                issue_type=st.issue_type,
                assignee=st.assignee,
                story_points=st.story_points,
            )
            for st in issue.subtasks
        ]
        return cls(
            key=issue.key,
            summary=issue.summary,
            description=issue.description,
            status=issue.status,
            issue_type=issue.issue_type,
            assignee=issue.assignee,
            story_points=issue.story_points,
            subtasks=subtasks,
            comments_count=comments_count,
        )


@dataclass
class Backup:
    """
    Complete backup of Jira state before a sync operation.

    Contains snapshots of all issues that may be modified,
    along with metadata about when and why the backup was created.
    """

    backup_id: str
    epic_key: str
    markdown_path: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    issues: list[IssueSnapshot] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        """Total number of issues in backup."""
        return len(self.issues)

    @property
    def subtask_count(self) -> int:
        """Total number of subtasks across all issues."""
        return sum(len(issue.subtasks) for issue in self.issues)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "backup_id": self.backup_id,
            "epic_key": self.epic_key,
            "markdown_path": self.markdown_path,
            "created_at": self.created_at,
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Backup":
        """Create from dictionary."""
        issues = [IssueSnapshot.from_dict(i) for i in data.get("issues", [])]
        return cls(
            backup_id=data["backup_id"],
            epic_key=data["epic_key"],
            markdown_path=data.get("markdown_path", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            issues=issues,
            metadata=data.get("metadata", {}),
        )

    def get_issue(self, issue_key: str) -> IssueSnapshot | None:
        """Find an issue snapshot by key."""
        for issue in self.issues:
            if issue.key == issue_key:
                return issue
            # Check subtasks
            for subtask in issue.subtasks:
                if subtask.key == issue_key:
                    return subtask
        return None

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Backup ID: {self.backup_id}",
            f"Epic: {self.epic_key}",
            f"Created: {self.created_at}",
            f"Issues: {self.issue_count}",
            f"Subtasks: {self.subtask_count}",
        ]
        return "\n".join(lines)


class BackupManager:
    """
    Manages automatic backups of Jira state before sync operations.

    Features:
    - Auto-backup before sync (configurable)
    - Backup rotation with configurable retention
    - Backup listing and restoration helpers
    - JSON storage for easy inspection

    Default backup location: ~/.spectra/backups/
    """

    DEFAULT_BACKUP_DIR = Path.home() / ".spectra" / "backups"
    DEFAULT_MAX_BACKUPS = 10
    DEFAULT_RETENTION_DAYS = 30

    def __init__(
        self,
        backup_dir: Path | None = None,
        max_backups: int = DEFAULT_MAX_BACKUPS,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ):
        """
        Initialize the backup manager.

        Args:
            backup_dir: Directory to store backups. Defaults to ~/.spectra/backups/
            max_backups: Maximum number of backups to keep per epic.
            retention_days: Delete backups older than this many days.
        """
        self.backup_dir = backup_dir or self.DEFAULT_BACKUP_DIR
        self.max_backups = max_backups
        self.retention_days = retention_days
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the backup directory exists."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _generate_backup_id(self, epic_key: str) -> str:
        """Generate a unique backup ID."""
        # Include microseconds for uniqueness within same second
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        content = f"{epic_key}:{timestamp}"
        short_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        # Use shorter timestamp format in ID (exclude microseconds for readability)
        short_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{epic_key}_{short_timestamp}_{short_hash}"

    def _backup_file(self, backup_id: str) -> Path:
        """Get the path to a backup file."""
        return self.backup_dir / f"{backup_id}.json"

    def _epic_dir(self, epic_key: str) -> Path:
        """Get the directory for a specific epic's backups."""
        # Sanitize epic key for filesystem
        safe_key = epic_key.replace("/", "_").replace("\\", "_")
        return self.backup_dir / safe_key

    def create_backup(
        self,
        tracker: "IssueTrackerPort",
        epic_key: str,
        markdown_path: str,
        metadata: dict | None = None,
    ) -> Backup:
        """
        Create a backup of the current Jira state for an epic.

        Fetches all children of the epic and captures their current state
        before any modifications are made.

        Args:
            tracker: Issue tracker port to fetch current state.
            epic_key: The epic key to backup.
            markdown_path: Path to the markdown file (for reference).
            metadata: Optional additional metadata to store.

        Returns:
            The created Backup object.
        """
        logger.info(f"Creating backup for epic {epic_key}")

        backup_id = self._generate_backup_id(epic_key)
        backup = Backup(
            backup_id=backup_id,
            epic_key=epic_key,
            markdown_path=markdown_path,
            metadata=metadata or {},
        )

        # Fetch all children of the epic
        try:
            issues = tracker.get_epic_children(epic_key)
            logger.debug(f"Found {len(issues)} issues to backup")

            for issue_data in issues:
                # Get comment count
                try:
                    comments = tracker.get_issue_comments(issue_data.key)
                    comments_count = len(comments)
                except Exception as e:
                    logger.warning(f"Could not fetch comments for {issue_data.key}: {e}")
                    comments_count = 0

                # Create snapshot
                snapshot = IssueSnapshot.from_issue_data(issue_data, comments_count)
                backup.issues.append(snapshot)

        except Exception as e:
            logger.error(f"Failed to fetch issues for backup: {e}")
            raise

        # Save backup
        self.save_backup(backup)

        # Cleanup old backups
        self._cleanup_old_backups(epic_key)

        logger.info(f"Backup created: {backup_id} ({backup.issue_count} issues)")
        return backup

    def save_backup(self, backup: Backup, sanitize: bool = True) -> Path:
        """
        Save a backup to disk.

        Args:
            backup: The backup to save.
            sanitize: Whether to sanitize sensitive data before saving.

        Returns:
            Path to the saved backup file.
        """
        # Use epic-specific subdirectory for organization
        epic_dir = self._epic_dir(backup.epic_key)
        epic_dir.mkdir(parents=True, exist_ok=True)

        backup_file = epic_dir / f"{backup.backup_id}.json"

        # Convert to dict
        data = backup.to_dict()

        # Sanitize to remove any secrets before saving
        if sanitize:
            try:
                from spectra.core.security.backup_sanitizer import BackupSanitizer

                sanitizer = BackupSanitizer()
                result = sanitizer.sanitize_dict(data)
                if result.was_sanitized:
                    logger.info(f"Sanitized {result.fields_sanitized} sensitive fields in backup")
            except ImportError:
                # Security module not available, continue without sanitization
                pass

        with open(backup_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug(f"Saved backup to {backup_file}")
        return backup_file

    def load_backup(self, backup_id: str, epic_key: str | None = None) -> Backup | None:
        """
        Load a backup from disk.

        Args:
            backup_id: The backup ID to load.
            epic_key: Optional epic key to narrow search.

        Returns:
            The loaded Backup, or None if not found.
        """
        # Try direct path first
        if epic_key:
            backup_file = self._epic_dir(epic_key) / f"{backup_id}.json"
            if backup_file.exists():
                return self._load_backup_file(backup_file)

        # Search all epic directories
        for epic_dir in self.backup_dir.iterdir():
            if epic_dir.is_dir():
                backup_file = epic_dir / f"{backup_id}.json"
                if backup_file.exists():
                    return self._load_backup_file(backup_file)

        logger.warning(f"Backup not found: {backup_id}")
        return None

    def _load_backup_file(self, path: Path) -> Backup | None:
        """Load a backup from a specific file."""
        try:
            with open(path) as f:
                data = json.load(f)
            return Backup.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load backup {path}: {e}")
            return None

    def list_backups(self, epic_key: str | None = None) -> list[dict]:
        """
        List all available backups.

        Args:
            epic_key: Optional filter by epic key.

        Returns:
            List of backup summaries (id, epic, created_at, issue_count).
        """
        backups = []

        search_dirs = []
        if epic_key:
            epic_dir = self._epic_dir(epic_key)
            if epic_dir.exists():
                search_dirs.append(epic_dir)
        else:
            search_dirs = [d for d in self.backup_dir.iterdir() if d.is_dir()]

        for epic_dir in search_dirs:
            for backup_file in epic_dir.glob("*.json"):
                try:
                    with open(backup_file) as f:
                        data = json.load(f)

                    backups.append(
                        {
                            "backup_id": data.get("backup_id", backup_file.stem),
                            "epic_key": data.get("epic_key", epic_dir.name),
                            "created_at": data.get("created_at", ""),
                            "issue_count": len(data.get("issues", [])),
                            "path": str(backup_file),
                        }
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

        # Sort by creation time (newest first)
        backups.sort(key=lambda b: b.get("created_at", ""), reverse=True)
        return backups

    def get_latest_backup(self, epic_key: str) -> Backup | None:
        """
        Get the most recent backup for an epic.

        Args:
            epic_key: The epic key.

        Returns:
            The most recent Backup, or None if no backups exist.
        """
        backups = self.list_backups(epic_key)
        if not backups:
            return None

        return self.load_backup(backups[0]["backup_id"], epic_key)

    def delete_backup(self, backup_id: str, epic_key: str | None = None) -> bool:
        """
        Delete a specific backup.

        Args:
            backup_id: The backup ID to delete.
            epic_key: Optional epic key to narrow search.

        Returns:
            True if deleted, False if not found.
        """
        # Search for the backup
        search_dirs = []
        if epic_key:
            epic_dir = self._epic_dir(epic_key)
            if epic_dir.exists():
                search_dirs.append(epic_dir)
        else:
            search_dirs = [d for d in self.backup_dir.iterdir() if d.is_dir()]

        for epic_dir in search_dirs:
            backup_file = epic_dir / f"{backup_id}.json"
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"Deleted backup: {backup_id}")
                return True

        return False

    def _cleanup_old_backups(self, epic_key: str) -> int:
        """
        Clean up old backups for an epic based on retention policy.

        Args:
            epic_key: The epic key.

        Returns:
            Number of backups deleted.
        """
        backups = self.list_backups(epic_key)
        deleted = 0
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        for i, backup in enumerate(backups):
            should_delete = False

            # Delete if over max count (keep only max_backups most recent)
            if i >= self.max_backups:
                should_delete = True
                logger.debug(f"Deleting backup {backup['backup_id']} (over limit)")

            # Delete if over retention period
            elif backup.get("created_at"):
                try:
                    created = datetime.fromisoformat(backup["created_at"])
                    if created < cutoff:
                        should_delete = True
                        logger.debug(f"Deleting backup {backup['backup_id']} (expired)")
                except ValueError:
                    pass

            if should_delete and self.delete_backup(backup["backup_id"], epic_key):
                deleted += 1

        if deleted:
            logger.info(f"Cleaned up {deleted} old backups for {epic_key}")

        return deleted

    def cleanup_all(self) -> int:
        """
        Clean up old backups for all epics.

        Returns:
            Total number of backups deleted.
        """
        total_deleted = 0

        for epic_dir in self.backup_dir.iterdir():
            if epic_dir.is_dir():
                epic_key = epic_dir.name
                total_deleted += self._cleanup_old_backups(epic_key)

        return total_deleted

    def restore_backup(
        self,
        tracker: "IssueTrackerPort",
        backup_id: str,
        epic_key: str | None = None,
        dry_run: bool = True,
        restore_descriptions: bool = True,
        restore_story_points: bool = True,
        issue_filter: list[str] | None = None,
    ) -> RestoreResult:
        """
        Restore Jira issues to a previous state from a backup.

        This will update issue descriptions and story points to match
        the backed-up state. Comments and status are NOT restored
        (comments can't be deleted, status transitions are complex).

        Args:
            tracker: Issue tracker port to update issues.
            backup_id: The backup ID to restore from.
            epic_key: Optional epic key to help find backup.
            dry_run: If True, only simulate the restore.
            restore_descriptions: Whether to restore descriptions.
            restore_story_points: Whether to restore story points.
            issue_filter: Optional list of issue keys to restore (None = all).

        Returns:
            RestoreResult with details of what was restored.
        """
        # Load the backup
        backup = self.load_backup(backup_id, epic_key)
        if not backup:
            result = RestoreResult(
                backup_id=backup_id,
                epic_key=epic_key or "unknown",
                dry_run=dry_run,
                success=False,
            )
            result.errors.append(f"Backup not found: {backup_id}")
            return result

        logger.info(f"Restoring from backup {backup_id} (dry_run={dry_run})")

        result = RestoreResult(
            backup_id=backup_id,
            epic_key=backup.epic_key,
            dry_run=dry_run,
        )

        # Process each issue in the backup
        for snapshot in backup.issues:
            # Apply filter if provided
            if issue_filter and snapshot.key not in issue_filter:
                continue

            self._restore_issue(
                tracker=tracker,
                snapshot=snapshot,
                result=result,
                dry_run=dry_run,
                restore_descriptions=restore_descriptions,
                restore_story_points=restore_story_points,
            )

            # Restore subtasks
            for subtask_snapshot in snapshot.subtasks:
                if issue_filter and subtask_snapshot.key not in issue_filter:
                    continue

                self._restore_subtask(
                    tracker=tracker,
                    snapshot=subtask_snapshot,
                    result=result,
                    dry_run=dry_run,
                    restore_descriptions=restore_descriptions,
                    restore_story_points=restore_story_points,
                )

        result.complete()
        logger.info(
            f"Restore complete: {result.issues_restored} issues, {result.subtasks_restored} subtasks"
        )
        return result

    def _restore_issue(
        self,
        tracker: "IssueTrackerPort",
        snapshot: "IssueSnapshot",
        result: RestoreResult,
        dry_run: bool,
        restore_descriptions: bool,
        restore_story_points: bool,
    ) -> None:
        """
        Restore a single issue from a snapshot.

        Args:
            tracker: Issue tracker port.
            snapshot: The issue snapshot to restore.
            result: RestoreResult to update.
            dry_run: Whether this is a dry run.
            restore_descriptions: Whether to restore description.
            restore_story_points: Whether to restore story points.
        """
        issue_key = snapshot.key
        restored_any = False

        # Restore description
        if restore_descriptions and snapshot.description is not None:
            try:
                if dry_run:
                    logger.info(f"[DRY-RUN] Would restore description for {issue_key}")
                    result.add_operation(
                        RestoreOperation(
                            issue_key=issue_key,
                            field="description",
                            success=True,
                        )
                    )
                else:
                    tracker.update_issue_description(issue_key, snapshot.description)
                    logger.info(f"Restored description for {issue_key}")
                    result.add_operation(
                        RestoreOperation(
                            issue_key=issue_key,
                            field="description",
                            success=True,
                        )
                    )
                restored_any = True
            except Exception as e:
                logger.error(f"Failed to restore description for {issue_key}: {e}")
                result.add_operation(
                    RestoreOperation(
                        issue_key=issue_key,
                        field="description",
                        success=False,
                        error=str(e),
                    )
                )

        # Restore story points for parent issues
        if restore_story_points and snapshot.story_points is not None:
            try:
                if dry_run:
                    logger.info(
                        f"[DRY-RUN] Would restore story points for {issue_key} "
                        f"to {snapshot.story_points}"
                    )
                    result.add_operation(
                        RestoreOperation(
                            issue_key=issue_key,
                            field="story_points",
                            success=True,
                        )
                    )
                else:
                    tracker.update_issue_story_points(issue_key, snapshot.story_points)
                    logger.info(f"Restored story points for {issue_key} to {snapshot.story_points}")
                    result.add_operation(
                        RestoreOperation(
                            issue_key=issue_key,
                            field="story_points",
                            success=True,
                        )
                    )
                restored_any = True
            except Exception as e:
                logger.error(f"Failed to restore story points for {issue_key}: {e}")
                result.add_operation(
                    RestoreOperation(
                        issue_key=issue_key,
                        field="story_points",
                        success=False,
                        error=str(e),
                    )
                )

        if restored_any:
            result.issues_restored += 1

    def _restore_subtask(
        self,
        tracker: "IssueTrackerPort",
        snapshot: "IssueSnapshot",
        result: RestoreResult,
        dry_run: bool,
        restore_descriptions: bool,
        restore_story_points: bool,
    ) -> None:
        """
        Restore a subtask from a snapshot.

        Args:
            tracker: Issue tracker port.
            snapshot: The subtask snapshot to restore.
            result: RestoreResult to update.
            dry_run: Whether this is a dry run.
            restore_descriptions: Whether to restore description.
            restore_story_points: Whether to restore story points.
        """
        issue_key = snapshot.key
        restored_any = False

        # Prepare update fields
        description = snapshot.description if restore_descriptions else None
        story_points = (
            int(snapshot.story_points) if (restore_story_points and snapshot.story_points) else None
        )

        if description is None and story_points is None:
            # Nothing to restore
            result.add_operation(
                RestoreOperation(
                    issue_key=issue_key,
                    field="subtask",
                    skipped=True,
                    skip_reason="No restorable fields",
                )
            )
            return

        try:
            if dry_run:
                fields = []
                if description is not None:
                    fields.append("description")
                if story_points is not None:
                    fields.append("story_points")
                logger.info(f"[DRY-RUN] Would restore {', '.join(fields)} for subtask {issue_key}")
                result.add_operation(
                    RestoreOperation(
                        issue_key=issue_key,
                        field="subtask",
                        success=True,
                    )
                )
            else:
                tracker.update_subtask(
                    issue_key=issue_key,
                    description=description,
                    story_points=story_points,
                )
                logger.info(f"Restored subtask {issue_key}")
                result.add_operation(
                    RestoreOperation(
                        issue_key=issue_key,
                        field="subtask",
                        success=True,
                    )
                )
            restored_any = True
        except Exception as e:
            logger.error(f"Failed to restore subtask {issue_key}: {e}")
            result.add_operation(
                RestoreOperation(
                    issue_key=issue_key,
                    field="subtask",
                    success=False,
                    error=str(e),
                )
            )

        if restored_any:
            result.subtasks_restored += 1


def restore_from_backup(
    tracker: "IssueTrackerPort",
    backup_id: str,
    epic_key: str | None = None,
    dry_run: bool = True,
    backup_dir: Path | None = None,
) -> RestoreResult:
    """
    Convenience function to restore from a backup.

    Args:
        tracker: Issue tracker to update issues.
        backup_id: The backup ID to restore from.
        epic_key: Optional epic key to help find backup.
        dry_run: If True, only simulate the restore.
        backup_dir: Optional custom backup directory.

    Returns:
        RestoreResult with restore details.
    """
    manager = BackupManager(backup_dir=backup_dir)
    return manager.restore_backup(
        tracker=tracker,
        backup_id=backup_id,
        epic_key=epic_key,
        dry_run=dry_run,
    )


def create_pre_sync_backup(
    tracker: "IssueTrackerPort",
    epic_key: str,
    markdown_path: str,
    backup_dir: Path | None = None,
) -> Backup:
    """
    Convenience function to create a backup before sync.

    Args:
        tracker: Issue tracker to fetch current state.
        epic_key: Epic key to backup.
        markdown_path: Path to markdown file.
        backup_dir: Optional custom backup directory.

    Returns:
        The created Backup.
    """
    manager = BackupManager(backup_dir=backup_dir)
    return manager.create_backup(
        tracker=tracker,
        epic_key=epic_key,
        markdown_path=markdown_path,
        metadata={
            "trigger": "pre_sync",
            "sync_mode": "auto",
        },
    )
