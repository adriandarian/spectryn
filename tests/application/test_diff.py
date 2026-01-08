"""Tests for diff functionality."""

from unittest.mock import MagicMock

import pytest

from spectryn.application.sync.backup import Backup, IssueSnapshot
from spectryn.application.sync.diff import (
    DiffCalculator,
    DiffFormatter,
    DiffResult,
    FieldDiff,
    IssueDiff,
    compare_backup_to_current,
)
from spectryn.core.ports.issue_tracker import IssueData


class TestFieldDiff:
    """Tests for FieldDiff class."""

    def test_added_detection(self):
        """Should detect when field was added."""
        diff = FieldDiff(
            field_name="description",
            old_value=None,
            new_value="New description",
            changed=True,
        )
        assert diff.added is True
        assert diff.removed is False
        assert diff.modified is False

    def test_removed_detection(self):
        """Should detect when field was removed."""
        diff = FieldDiff(
            field_name="description",
            old_value="Old description",
            new_value=None,
            changed=True,
        )
        assert diff.added is False
        assert diff.removed is True
        assert diff.modified is False

    def test_modified_detection(self):
        """Should detect when field was modified."""
        diff = FieldDiff(
            field_name="status",
            old_value="Open",
            new_value="In Progress",
            changed=True,
        )
        assert diff.added is False
        assert diff.removed is False
        assert diff.modified is True


class TestIssueDiff:
    """Tests for IssueDiff class."""

    def test_has_changes_with_field_changes(self):
        """Should detect changes from fields."""
        diff = IssueDiff(
            issue_key="PROJ-100",
            summary="Test Story",
        )
        diff.add_field_diff("status", "Open", "In Progress")

        assert diff.has_changes is True
        assert diff.change_count == 1

    def test_has_changes_when_new(self):
        """Should detect changes when issue is new."""
        diff = IssueDiff(
            issue_key="PROJ-100",
            summary="Test Story",
            is_new=True,
        )
        assert diff.has_changes is True

    def test_has_changes_when_deleted(self):
        """Should detect changes when issue is deleted."""
        diff = IssueDiff(
            issue_key="PROJ-100",
            summary="Test Story",
            is_deleted=True,
        )
        assert diff.has_changes is True

    def test_no_changes(self):
        """Should detect when no changes."""
        diff = IssueDiff(
            issue_key="PROJ-100",
            summary="Test Story",
        )
        diff.add_field_diff("status", "Open", "Open")  # Same value

        assert diff.has_changes is False
        assert diff.change_count == 0

    def test_add_field_diff_auto_detect(self):
        """Should auto-detect if values are different."""
        diff = IssueDiff(issue_key="PROJ-100", summary="Test")

        # Same values - not changed
        field1 = diff.add_field_diff("status", "Open", "Open")
        assert field1.changed is False

        # Different values - changed
        field2 = diff.add_field_diff("priority", "High", "Low")
        assert field2.changed is True

    def test_subtask_changes_counted(self):
        """Should count subtask changes in total."""
        diff = IssueDiff(issue_key="PROJ-100", summary="Story")

        subtask_diff = IssueDiff(issue_key="PROJ-101", summary="Subtask")
        subtask_diff.add_field_diff("status", "Todo", "Done")
        diff.subtask_diffs.append(subtask_diff)

        assert diff.has_changes is True
        assert diff.change_count == 1  # From subtask


class TestDiffResult:
    """Tests for DiffResult class."""

    def test_statistics(self):
        """Should calculate correct statistics."""
        result = DiffResult(backup_id="test", epic_key="PROJ-1")

        # Add unchanged issue
        unchanged = IssueDiff(issue_key="PROJ-100", summary="Unchanged")
        unchanged.add_field_diff("status", "Open", "Open")
        result.issue_diffs.append(unchanged)

        # Add changed issue
        changed = IssueDiff(issue_key="PROJ-101", summary="Changed")
        changed.add_field_diff("status", "Open", "Done")
        changed.add_field_diff("priority", "High", "Low")
        result.issue_diffs.append(changed)

        assert result.total_issues == 2
        assert result.changed_issues == 1
        assert result.unchanged_issues == 1
        assert result.total_changes == 2
        assert result.has_changes is True

    def test_get_changed_issues(self):
        """Should return only changed issues."""
        result = DiffResult(backup_id="test", epic_key="PROJ-1")

        unchanged = IssueDiff(issue_key="PROJ-100", summary="Unchanged")
        result.issue_diffs.append(unchanged)

        changed = IssueDiff(issue_key="PROJ-101", summary="Changed", is_new=True)
        result.issue_diffs.append(changed)

        changed_only = result.get_changed_issues()
        assert len(changed_only) == 1
        assert changed_only[0].issue_key == "PROJ-101"


class TestDiffCalculator:
    """Tests for DiffCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create a DiffCalculator instance."""
        return DiffCalculator()

    @pytest.fixture
    def backup_with_issues(self):
        """Create a backup with test issues."""
        return Backup(
            backup_id="test_backup",
            epic_key="PROJ-1",
            markdown_path="/test.md",
            issues=[
                IssueSnapshot(
                    key="PROJ-100",
                    summary="Story 1",
                    description="Original description",
                    status="Open",
                    story_points=5.0,
                    subtasks=[
                        IssueSnapshot(
                            key="PROJ-101",
                            summary="Subtask 1",
                            status="Todo",
                            story_points=2.0,
                        ),
                    ],
                ),
                IssueSnapshot(
                    key="PROJ-200",
                    summary="Story 2",
                    status="In Progress",
                ),
            ],
        )

    def test_compare_no_changes(self, calculator, backup_with_issues):
        """Should detect no changes when current matches backup."""
        # Create tracker that returns same data
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                description="Original description",
                status="Open",
                story_points=5.0,
                subtasks=[
                    IssueData(key="PROJ-101", summary="Subtask 1", status="Todo", story_points=2.0),
                ],
            ),
            IssueData(
                key="PROJ-200",
                summary="Story 2",
                status="In Progress",
            ),
        ]

        result = calculator.compare_backup_to_current(tracker, backup_with_issues)

        assert result.has_changes is False
        assert result.total_issues == 2

    def test_compare_with_status_change(self, calculator, backup_with_issues):
        """Should detect status changes."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                description="Original description",
                status="Done",  # Changed from Open
                story_points=5.0,
                subtasks=[
                    IssueData(key="PROJ-101", summary="Subtask 1", status="Todo", story_points=2.0),
                ],
            ),
            IssueData(
                key="PROJ-200",
                summary="Story 2",
                status="In Progress",
            ),
        ]

        result = calculator.compare_backup_to_current(tracker, backup_with_issues)

        assert result.has_changes is True
        assert result.changed_issues == 1

        changed = result.get_changed_issues()[0]
        assert changed.issue_key == "PROJ-100"

        status_diff = next(f for f in changed.fields if f.field_name == "status")
        assert status_diff.old_value == "Open"
        assert status_diff.new_value == "Done"

    def test_compare_with_deleted_issue(self, calculator, backup_with_issues):
        """Should detect deleted issues."""
        tracker = MagicMock()
        # Only return one issue - PROJ-200 is "deleted"
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                description="Original description",
                status="Open",
                story_points=5.0,
                subtasks=[
                    IssueData(key="PROJ-101", summary="Subtask 1", status="Todo", story_points=2.0),
                ],
            ),
        ]

        result = calculator.compare_backup_to_current(tracker, backup_with_issues)

        assert result.has_changes is True

        deleted = [d for d in result.issue_diffs if d.is_deleted]
        assert len(deleted) == 1
        assert deleted[0].issue_key == "PROJ-200"

    def test_compare_with_new_issue(self, calculator, backup_with_issues):
        """Should detect new issues."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-100",
                summary="Story 1",
                description="Original description",
                status="Open",
                story_points=5.0,
                subtasks=[
                    IssueData(key="PROJ-101", summary="Subtask 1", status="Todo", story_points=2.0),
                ],
            ),
            IssueData(
                key="PROJ-200",
                summary="Story 2",
                status="In Progress",
            ),
            IssueData(
                key="PROJ-300",
                summary="New Story",  # This is new
                status="Open",
            ),
        ]

        result = calculator.compare_backup_to_current(tracker, backup_with_issues)

        assert result.has_changes is True

        new_issues = [d for d in result.issue_diffs if d.is_new]
        assert len(new_issues) == 1
        assert new_issues[0].issue_key == "PROJ-300"


class TestDiffFormatter:
    """Tests for DiffFormatter class."""

    @pytest.fixture
    def formatter(self):
        """Create a DiffFormatter without colors for testing."""
        return DiffFormatter(color=False)

    def test_format_no_changes(self, formatter):
        """Should format result with no changes."""
        result = DiffResult(backup_id="test123", epic_key="PROJ-1")

        output = formatter.format_diff_result(result)

        assert "test123" in output
        assert "No changes detected" in output

    def test_format_with_changes(self, formatter):
        """Should format result with changes."""
        result = DiffResult(backup_id="test123", epic_key="PROJ-1")

        diff = IssueDiff(issue_key="PROJ-100", summary="Test Story")
        diff.add_field_diff("status", "Open", "Done")
        result.issue_diffs.append(diff)

        output = formatter.format_diff_result(result)

        assert "PROJ-100" in output
        assert "status" in output
        assert "Open" in output
        assert "Done" in output

    def test_format_new_issue(self, formatter):
        """Should format new issue."""
        result = DiffResult(backup_id="test123", epic_key="PROJ-1")

        diff = IssueDiff(issue_key="PROJ-100", summary="New Story", is_new=True)
        result.issue_diffs.append(diff)

        output = formatter.format_diff_result(result)

        assert "NEW" in output
        assert "PROJ-100" in output

    def test_format_deleted_issue(self, formatter):
        """Should format deleted issue."""
        result = DiffResult(backup_id="test123", epic_key="PROJ-1")

        diff = IssueDiff(issue_key="PROJ-100", summary="Deleted Story", is_deleted=True)
        result.issue_diffs.append(diff)

        output = formatter.format_diff_result(result)

        assert "DELETED" in output
        assert "PROJ-100" in output

    def test_format_field_diff(self, formatter):
        """Should format individual field diff."""
        diff = FieldDiff(
            field_name="priority",
            old_value="High",
            new_value="Low",
            changed=True,
        )

        lines = formatter.format_field_diff(diff)

        output = "\n".join(lines)
        assert "priority" in output
        assert "High" in output
        assert "Low" in output

    def test_format_with_colors(self):
        """Should include color codes when enabled."""
        formatter = DiffFormatter(color=True)

        diff = FieldDiff(
            field_name="status",
            old_value="Open",
            new_value="Done",
            changed=True,
        )

        lines = formatter.format_field_diff(diff)
        output = "\n".join(lines)

        # Should contain ANSI escape codes
        assert "\033[" in output

    def test_extract_adf_text(self, formatter):
        """Should extract text from ADF document."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "World"},
                    ],
                },
            ],
        }

        text = formatter._extract_adf_text(adf)
        assert text == "Hello  World"

    def test_format_text_diff(self, formatter):
        """Should format unified diff for text changes."""
        old_text = "Line 1\nLine 2\nLine 3"
        new_text = "Line 1\nLine 2 Modified\nLine 3\nLine 4"

        diff_lines = formatter.format_text_diff(old_text, new_text)

        assert len(diff_lines) > 0
        # Should contain diff markers
        assert any("+++" in line or "---" in line or "@@" in line for line in diff_lines)

    def test_format_field_diff_with_description(self, formatter):
        """Should format description field with unified diff for multi-line."""
        diff = FieldDiff(
            field_name="description",
            old_value="Old line 1\nOld line 2",
            new_value="New line 1\nNew line 2",
            changed=True,
        )

        lines = formatter.format_field_diff(diff)
        assert len(lines) > 0
        assert "description" in lines[0]

    def test_format_field_diff_status_priority(self, formatter):
        """Should format status/priority fields with enhanced styling."""
        diff = FieldDiff(
            field_name="status",
            old_value="Open",
            new_value="Done",
            changed=True,
        )

        lines = formatter.format_field_diff(diff)
        assert len(lines) > 0
        assert "status" in lines[0]
        assert "Open" in lines[0] or "Done" in lines[0]

    def test_format_field_diff_added(self, formatter):
        """Should format added fields."""
        diff = FieldDiff(
            field_name="priority",
            old_value=None,
            new_value="High",
            changed=True,
        )

        lines = formatter.format_field_diff(diff)
        assert len(lines) > 0
        assert "priority" in lines[0]
        assert "High" in lines[0]

    def test_format_field_diff_removed(self, formatter):
        """Should format removed fields."""
        diff = FieldDiff(
            field_name="assignee",
            old_value="John Doe",
            new_value=None,
            changed=True,
        )

        lines = formatter.format_field_diff(diff)
        assert len(lines) > 0
        assert "assignee" in lines[0]
        assert "John Doe" in lines[0]

    def test_extract_text_from_value(self, formatter):
        """Should extract text from various value types."""
        # String value
        assert formatter._extract_text_from_value("Hello") == "Hello"

        # ADF value
        adf = {"type": "doc", "content": [{"type": "text", "text": "Test"}]}
        assert formatter._extract_text_from_value(adf) == "Test"

        # None value
        assert formatter._extract_text_from_value(None) == ""

        # Other types
        assert formatter._extract_text_from_value(123) == "123"


class TestCompareBackupToCurrentFunction:
    """Tests for compare_backup_to_current convenience function."""

    def test_returns_result_and_output(self):
        """Should return both result and formatted output."""
        tracker = MagicMock()
        tracker.get_epic_children.return_value = []

        backup = Backup(
            backup_id="test",
            epic_key="PROJ-1",
            markdown_path="/test.md",
            issues=[],
        )

        result, output = compare_backup_to_current(
            tracker=tracker,
            backup=backup,
            color=False,
        )

        assert isinstance(result, DiffResult)
        assert isinstance(output, str)
        assert result.backup_id == "test"
