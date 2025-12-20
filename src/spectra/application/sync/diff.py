"""
Diff - Compare Jira state between backup and current state.

Provides visual diff output showing before/after changes.
"""

import difflib
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectra.core.ports.issue_tracker import IssueData, IssueTrackerPort

    from .backup import Backup, IssueSnapshot


logger = logging.getLogger(__name__)


@dataclass
class FieldDiff:
    """
    Difference for a single field.

    Tracks what changed between old and new values.
    """

    field_name: str
    old_value: Any | None = None
    new_value: Any | None = None
    changed: bool = False

    @property
    def added(self) -> bool:
        """Field was added (old is None, new is not)."""
        return self.old_value is None and self.new_value is not None

    @property
    def removed(self) -> bool:
        """Field was removed (old is not None, new is None)."""
        return self.old_value is not None and self.new_value is None

    @property
    def modified(self) -> bool:
        """Field was modified (both exist but different)."""
        return self.old_value is not None and self.new_value is not None and self.changed


@dataclass
class IssueDiff:
    """
    Differences for a single issue.

    Contains all field changes between backup and current state.
    """

    issue_key: str
    summary: str
    fields: list[FieldDiff] = field(default_factory=list)
    is_new: bool = False  # Issue exists now but not in backup
    is_deleted: bool = False  # Issue existed in backup but not now
    subtask_diffs: list["IssueDiff"] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        if self.is_new or self.is_deleted:
            return True
        if any(f.changed for f in self.fields):
            return True
        return bool(any(st.has_changes for st in self.subtask_diffs))

    @property
    def change_count(self) -> int:
        """Count number of changed fields."""
        count = sum(1 for f in self.fields if f.changed)
        for st in self.subtask_diffs:
            count += st.change_count
        return count

    def add_field_diff(
        self,
        field_name: str,
        old_value: Any,
        new_value: Any,
    ) -> FieldDiff:
        """
        Add a field diff, automatically detecting if changed.

        Args:
            field_name: Name of the field.
            old_value: Value in backup.
            new_value: Current value.

        Returns:
            The created FieldDiff.
        """
        # Normalize values for comparison
        old_normalized = self._normalize_value(old_value)
        new_normalized = self._normalize_value(new_value)

        changed = old_normalized != new_normalized

        diff = FieldDiff(
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed=changed,
        )
        self.fields.append(diff)
        return diff

    def _normalize_value(self, value: Any) -> Any:
        """Normalize a value for comparison."""
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            # For ADF descriptions, compare the JSON
            return json.dumps(value, sort_keys=True)
        return value


@dataclass
class DiffResult:
    """
    Complete diff result between two states.

    Contains all issue diffs and summary statistics.
    """

    backup_id: str
    epic_key: str
    issue_diffs: list[IssueDiff] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        """Total number of issues compared."""
        return len(self.issue_diffs)

    @property
    def changed_issues(self) -> int:
        """Number of issues with changes."""
        return sum(1 for d in self.issue_diffs if d.has_changes)

    @property
    def unchanged_issues(self) -> int:
        """Number of issues without changes."""
        return sum(1 for d in self.issue_diffs if not d.has_changes)

    @property
    def total_changes(self) -> int:
        """Total number of field changes."""
        return sum(d.change_count for d in self.issue_diffs)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return any(d.has_changes for d in self.issue_diffs)

    def get_changed_issues(self) -> list[IssueDiff]:
        """Get only issues with changes."""
        return [d for d in self.issue_diffs if d.has_changes]


class DiffCalculator:
    """
    Calculates differences between backup state and current Jira state.
    """

    def compare_backup_to_current(
        self,
        tracker: "IssueTrackerPort",
        backup: "Backup",
    ) -> DiffResult:
        """
        Compare a backup to the current Jira state.

        Args:
            tracker: Issue tracker to fetch current state.
            backup: The backup to compare against.

        Returns:
            DiffResult with all differences.
        """
        result = DiffResult(
            backup_id=backup.backup_id,
            epic_key=backup.epic_key,
        )

        # Fetch current state
        try:
            current_issues = tracker.get_epic_children(backup.epic_key)
            current_by_key = {issue.key: issue for issue in current_issues}
        except Exception as e:
            logger.error(f"Failed to fetch current issues: {e}")
            return result

        # Build set of all keys
        backup_keys = {issue.key for issue in backup.issues}
        current_keys = set(current_by_key.keys())

        # Process issues in backup
        for snapshot in backup.issues:
            if snapshot.key in current_by_key:
                # Issue exists in both - compare
                current = current_by_key[snapshot.key]
                diff = self._compare_issue(snapshot, current)
                result.issue_diffs.append(diff)
            else:
                # Issue deleted (in backup but not current)
                diff = IssueDiff(
                    issue_key=snapshot.key,
                    summary=snapshot.summary,
                    is_deleted=True,
                )
                result.issue_diffs.append(diff)

        # Check for new issues (in current but not backup)
        for key in current_keys - backup_keys:
            current = current_by_key[key]
            diff = IssueDiff(
                issue_key=key,
                summary=current.summary,
                is_new=True,
            )
            result.issue_diffs.append(diff)

        return result

    def compare_snapshots(
        self,
        old_snapshot: "IssueSnapshot",
        new_snapshot: "IssueSnapshot",
    ) -> IssueDiff:
        """
        Compare two issue snapshots directly.

        Args:
            old_snapshot: The older/backup snapshot.
            new_snapshot: The newer/current snapshot.

        Returns:
            IssueDiff with all differences.
        """
        diff = IssueDiff(
            issue_key=old_snapshot.key,
            summary=old_snapshot.summary,
        )

        # Compare description
        diff.add_field_diff("description", old_snapshot.description, new_snapshot.description)

        # Compare status
        diff.add_field_diff("status", old_snapshot.status, new_snapshot.status)

        # Compare story points
        diff.add_field_diff("story_points", old_snapshot.story_points, new_snapshot.story_points)

        # Compare subtask count (high-level)
        diff.add_field_diff("subtask_count", len(old_snapshot.subtasks), len(new_snapshot.subtasks))

        return diff

    def _compare_issue(
        self,
        snapshot: "IssueSnapshot",
        current: "IssueData",
    ) -> IssueDiff:
        """
        Compare a snapshot to current issue data.

        Args:
            snapshot: The backup snapshot.
            current: Current issue from tracker.

        Returns:
            IssueDiff with differences.
        """
        diff = IssueDiff(
            issue_key=snapshot.key,
            summary=snapshot.summary,
        )

        # Compare description
        diff.add_field_diff("description", snapshot.description, current.description)

        # Compare status
        diff.add_field_diff("status", snapshot.status, current.status)

        # Compare story points (if available)
        diff.add_field_diff("story_points", snapshot.story_points, current.story_points)

        # Compare subtasks
        backup_subtasks = {st.key: st for st in snapshot.subtasks}
        current_subtasks = {st.key: st for st in current.subtasks}

        for key, backup_st in backup_subtasks.items():
            if key in current_subtasks:
                current_st = current_subtasks[key]
                st_diff = IssueDiff(
                    issue_key=key,
                    summary=backup_st.summary,
                )
                st_diff.add_field_diff("status", backup_st.status, current_st.status)
                st_diff.add_field_diff(
                    "story_points", backup_st.story_points, current_st.story_points
                )
                if st_diff.has_changes:
                    diff.subtask_diffs.append(st_diff)
            else:
                # Subtask deleted
                st_diff = IssueDiff(
                    issue_key=key,
                    summary=backup_st.summary,
                    is_deleted=True,
                )
                diff.subtask_diffs.append(st_diff)

        # New subtasks
        for key in set(current_subtasks.keys()) - set(backup_subtasks.keys()):
            current_st = current_subtasks[key]
            st_diff = IssueDiff(
                issue_key=key,
                summary=current_st.summary,
                is_new=True,
            )
            diff.subtask_diffs.append(st_diff)

        return diff


class DiffFormatter:
    """
    Formats diff results for terminal output.

    Provides colorized, human-readable diff output.
    """

    # ANSI color codes
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, color: bool = True, max_line_length: int = 80):
        """
        Initialize the diff formatter.

        Args:
            color: Whether to use ANSI colors.
            max_line_length: Maximum line length for truncation.
        """
        self.color = color
        self.max_line_length = max_line_length

    def _c(self, text: str, *codes: str) -> str:
        """Apply color codes to text."""
        if not self.color:
            return text
        return "".join(codes) + text + self.RESET

    def format_diff_result(self, result: DiffResult) -> str:
        """
        Format a complete diff result.

        Args:
            result: The DiffResult to format.

        Returns:
            Formatted string for terminal output.
        """
        lines = []

        # Header
        lines.append(self._c(f"Diff: Backup {result.backup_id}", self.BOLD, self.CYAN))
        lines.append(self._c(f"Epic: {result.epic_key}", self.DIM))
        lines.append("")

        # Summary
        if not result.has_changes:
            lines.append(self._c("No changes detected", self.GREEN))
            return "\n".join(lines)

        lines.append(
            f"Changed: {result.changed_issues}/{result.total_issues} issues ({result.total_changes} field changes)"
        )
        lines.append("")

        # Issue diffs
        for issue_diff in result.get_changed_issues():
            lines.extend(self.format_issue_diff(issue_diff))
            lines.append("")

        return "\n".join(lines)

    def format_issue_diff(self, diff: IssueDiff, indent: int = 0) -> list[str]:
        """
        Format a single issue diff.

        Args:
            diff: The IssueDiff to format.
            indent: Indentation level.

        Returns:
            List of formatted lines.
        """
        lines = []
        prefix = "  " * indent

        # Issue header
        if diff.is_new:
            lines.append(
                f"{prefix}{self._c('+ NEW:', self.GREEN)} {diff.issue_key} - {diff.summary}"
            )
        elif diff.is_deleted:
            lines.append(
                f"{prefix}{self._c('- DELETED:', self.RED)} {diff.issue_key} - {diff.summary}"
            )
        else:
            lines.append(
                f"{prefix}{self._c('~', self.YELLOW)} {self._c(diff.issue_key, self.BOLD)} - {diff.summary}"
            )

        # Field diffs
        for field_diff in diff.fields:
            if field_diff.changed:
                lines.extend(self.format_field_diff(field_diff, indent + 1))

        # Subtask diffs
        if diff.subtask_diffs:
            lines.append(f"{prefix}  Subtasks:")
            for st_diff in diff.subtask_diffs:
                lines.extend(self.format_issue_diff(st_diff, indent + 2))

        return lines

    def format_field_diff(self, diff: FieldDiff, indent: int = 0) -> list[str]:
        """
        Format a single field diff.

        Args:
            diff: The FieldDiff to format.
            indent: Indentation level.

        Returns:
            List of formatted lines.
        """
        lines = []
        prefix = "  " * indent

        if diff.added:
            lines.append(
                f"{prefix}{self._c('+', self.GREEN)} {diff.field_name}: {self._format_value(diff.new_value)}"
            )
        elif diff.removed:
            lines.append(
                f"{prefix}{self._c('-', self.RED)} {diff.field_name}: {self._format_value(diff.old_value)}"
            )
        elif diff.modified:
            # Show before/after
            if diff.field_name == "description":
                # For descriptions, show a summary
                lines.append(f"{prefix}{self._c('~', self.YELLOW)} {diff.field_name}:")
                lines.append(
                    f"{prefix}  {self._c('- (backup):', self.RED)} {self._format_description_summary(diff.old_value)}"
                )
                lines.append(
                    f"{prefix}  {self._c('+ (current):', self.GREEN)} {self._format_description_summary(diff.new_value)}"
                )
            else:
                old_str = self._format_value(diff.old_value)
                new_str = self._format_value(diff.new_value)
                lines.append(
                    f"{prefix}{self._c('~', self.YELLOW)} {diff.field_name}: {self._c(old_str, self.RED)} → {self._c(new_str, self.GREEN)}"
                )

        return lines

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return self._c("(none)", self.DIM)
        if isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:47]}..."'
            return f'"{value}"'
        if isinstance(value, dict):
            return self._format_description_summary(value)
        return str(value)

    def _format_description_summary(self, desc: Any) -> str:
        """Format a description for summary display."""
        if desc is None:
            return self._c("(empty)", self.DIM)

        if isinstance(desc, dict):
            # ADF format - extract text content
            text = self._extract_adf_text(desc)
            if len(text) > 60:
                return f'"{text[:57]}..."'
            return f'"{text}"' if text else self._c("(empty ADF)", self.DIM)

        if isinstance(desc, str):
            if len(desc) > 60:
                return f'"{desc[:57]}..."'
            return f'"{desc}"'

        return str(desc)

    def _extract_adf_text(self, adf: dict) -> str:
        """Extract plain text from ADF document."""
        text_parts = []

        def extract(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                for child in node.get("content", []):
                    extract(child)
            elif isinstance(node, list):
                for item in node:
                    extract(item)

        extract(adf)
        return " ".join(text_parts)

    def format_text_diff(self, old_text: str, new_text: str) -> list[str]:
        """
        Format a unified diff between two text strings.

        Args:
            old_text: Original text.
            new_text: New text.

        Returns:
            List of diff lines with colors.
        """
        lines = []

        old_lines = (old_text or "").splitlines(keepends=True)
        new_lines = (new_text or "").splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile="backup", tofile="current", lineterm=""
        )

        for line in diff:
            if line.startswith(("+++", "---")):
                lines.append(self._c(line.rstrip(), self.BOLD))
            elif line.startswith("@@"):
                lines.append(self._c(line.rstrip(), self.CYAN))
            elif line.startswith("+"):
                lines.append(self._c(line.rstrip(), self.GREEN))
            elif line.startswith("-"):
                lines.append(self._c(line.rstrip(), self.RED))
            else:
                lines.append(line.rstrip())

        return lines


def compare_backup_to_current(
    tracker: "IssueTrackerPort",
    backup: "Backup",
    color: bool = True,
) -> tuple[DiffResult, str]:
    """
    Convenience function to compare a backup to current state.

    Args:
        tracker: Issue tracker to fetch current state.
        backup: The backup to compare against.
        color: Whether to use colors in output.

    Returns:
        Tuple of (DiffResult, formatted_output_string).
    """
    calculator = DiffCalculator()
    result = calculator.compare_backup_to_current(tracker, backup)

    formatter = DiffFormatter(color=color)
    output = formatter.format_diff_result(result)

    return result, output
