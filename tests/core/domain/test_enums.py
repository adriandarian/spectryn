"""
Tests for domain enums.
"""

import pytest

from spectra.core.domain.enums import IssueType, Priority, Status


class TestStatus:
    """Tests for Status enum."""

    def test_all_statuses_defined(self):
        """Test all expected statuses are defined."""
        assert Status.PLANNED
        assert Status.OPEN
        assert Status.IN_PROGRESS
        assert Status.IN_REVIEW
        assert Status.DONE
        assert Status.CANCELLED

    class TestFromString:
        """Tests for Status.from_string()."""

        def test_done_variations(self):
            """Test various done strings."""
            assert Status.from_string("done") == Status.DONE
            assert Status.from_string("Done") == Status.DONE
            assert Status.from_string("DONE") == Status.DONE
            assert Status.from_string("resolved") == Status.DONE
            assert Status.from_string("closed") == Status.DONE
            assert Status.from_string("complete") == Status.DONE
            assert Status.from_string("✅ Done") == Status.DONE

        def test_in_progress_variations(self):
            """Test various in progress strings."""
            assert Status.from_string("in progress") == Status.IN_PROGRESS
            assert Status.from_string("In Progress") == Status.IN_PROGRESS
            assert Status.from_string("in-progress") == Status.IN_PROGRESS
            assert Status.from_string("🔄 In Progress") == Status.IN_PROGRESS
            assert Status.from_string("active") == Status.IN_PROGRESS

        def test_in_review_variations(self):
            """Test various in review strings."""
            assert Status.from_string("in review") == Status.IN_REVIEW
            assert Status.from_string("review") == Status.IN_REVIEW
            assert Status.from_string("testing") == Status.IN_REVIEW

        def test_open_variations(self):
            """Test various open strings."""
            assert Status.from_string("open") == Status.OPEN
            assert Status.from_string("todo") == Status.OPEN
            assert Status.from_string("to do") == Status.OPEN
            assert Status.from_string("new") == Status.OPEN

        def test_cancelled_variations(self):
            """Test various cancelled strings."""
            assert Status.from_string("cancelled") == Status.CANCELLED
            assert Status.from_string("cancel") == Status.CANCELLED
            assert Status.from_string("wontfix") == Status.CANCELLED
            assert Status.from_string("won't fix") == Status.CANCELLED

        def test_planned_variations(self):
            """Test various planned strings."""
            assert Status.from_string("not started") == Status.PLANNED
            assert Status.from_string("🔲 Not Started") == Status.PLANNED
            assert Status.from_string("backlog") == Status.PLANNED

        def test_unknown_defaults_to_planned(self):
            """Test unknown status defaults to planned."""
            assert Status.from_string("unknown") == Status.PLANNED
            assert Status.from_string("") == Status.PLANNED

    class TestEmoji:
        """Tests for Status.emoji property."""

        def test_all_statuses_have_emoji(self):
            """Test all statuses have emoji."""
            assert Status.PLANNED.emoji == "📋"
            assert Status.OPEN.emoji == "📂"
            assert Status.IN_PROGRESS.emoji == "🔄"
            assert Status.IN_REVIEW.emoji == "👀"
            assert Status.DONE.emoji == "✅"
            assert Status.CANCELLED.emoji == "❌"

    class TestDisplayName:
        """Tests for Status.display_name property."""

        def test_all_statuses_have_display_name(self):
            """Test all statuses have display name."""
            assert Status.PLANNED.display_name == "Planned"
            assert Status.OPEN.display_name == "Open"
            assert Status.IN_PROGRESS.display_name == "In Progress"
            assert Status.IN_REVIEW.display_name == "In Review"
            assert Status.DONE.display_name == "Done"
            assert Status.CANCELLED.display_name == "Cancelled"

    class TestStateChecks:
        """Tests for is_complete and is_active methods."""

        def test_is_complete(self):
            """Test is_complete method."""
            assert Status.DONE.is_complete() is True
            assert Status.CANCELLED.is_complete() is True
            assert Status.PLANNED.is_complete() is False
            assert Status.OPEN.is_complete() is False
            assert Status.IN_PROGRESS.is_complete() is False
            assert Status.IN_REVIEW.is_complete() is False

        def test_is_active(self):
            """Test is_active method."""
            assert Status.IN_PROGRESS.is_active() is True
            assert Status.IN_REVIEW.is_active() is True
            assert Status.PLANNED.is_active() is False
            assert Status.OPEN.is_active() is False
            assert Status.DONE.is_active() is False
            assert Status.CANCELLED.is_active() is False


class TestPriority:
    """Tests for Priority enum."""

    def test_all_priorities_defined(self):
        """Test all expected priorities are defined."""
        assert Priority.CRITICAL
        assert Priority.HIGH
        assert Priority.MEDIUM
        assert Priority.LOW

    class TestFromString:
        """Tests for Priority.from_string()."""

        def test_critical_variations(self):
            """Test various critical strings."""
            assert Priority.from_string("critical") == Priority.CRITICAL
            assert Priority.from_string("Critical") == Priority.CRITICAL
            assert Priority.from_string("blocker") == Priority.CRITICAL
            assert Priority.from_string("🔴 Critical") == Priority.CRITICAL
            assert Priority.from_string("p0") == Priority.CRITICAL

        def test_high_variations(self):
            """Test various high strings."""
            assert Priority.from_string("high") == Priority.HIGH
            assert Priority.from_string("High") == Priority.HIGH
            assert Priority.from_string("🟡 High") == Priority.HIGH
            assert Priority.from_string("p1") == Priority.HIGH

        def test_medium_variations(self):
            """Test various medium strings."""
            assert Priority.from_string("medium") == Priority.MEDIUM
            assert Priority.from_string("Medium") == Priority.MEDIUM
            assert Priority.from_string("🟢 Medium") == Priority.MEDIUM
            assert Priority.from_string("p2") == Priority.MEDIUM

        def test_low_variations(self):
            """Test various low strings."""
            assert Priority.from_string("low") == Priority.LOW
            assert Priority.from_string("Low") == Priority.LOW
            assert Priority.from_string("minor") == Priority.LOW
            assert Priority.from_string("p3") == Priority.LOW

        def test_unknown_defaults_to_medium(self):
            """Test unknown priority defaults to medium."""
            assert Priority.from_string("unknown") == Priority.MEDIUM
            assert Priority.from_string("") == Priority.MEDIUM

    class TestEmoji:
        """Tests for Priority.emoji property."""

        def test_all_priorities_have_emoji(self):
            """Test all priorities have emoji."""
            assert Priority.CRITICAL.emoji == "🔴"
            assert Priority.HIGH.emoji == "🟡"
            assert Priority.MEDIUM.emoji == "🟢"
            assert Priority.LOW.emoji == "⚪"

    class TestJiraName:
        """Tests for Priority.jira_name property."""

        def test_all_priorities_have_jira_name(self):
            """Test all priorities have jira name."""
            assert Priority.CRITICAL.jira_name == "Highest"
            assert Priority.HIGH.jira_name == "High"
            assert Priority.MEDIUM.jira_name == "Medium"
            assert Priority.LOW.jira_name == "Low"

    class TestDisplayName:
        """Tests for Priority.display_name property."""

        def test_all_priorities_have_display_name(self):
            """Test all priorities have display name."""
            assert Priority.CRITICAL.display_name == "Critical"
            assert Priority.HIGH.display_name == "High"
            assert Priority.MEDIUM.display_name == "Medium"
            assert Priority.LOW.display_name == "Low"


class TestIssueType:
    """Tests for IssueType enum."""

    def test_all_issue_types_defined(self):
        """Test all expected issue types are defined."""
        assert IssueType.EPIC
        assert IssueType.STORY
        assert IssueType.TASK
        assert IssueType.SUBTASK
        assert IssueType.BUG
        assert IssueType.SPIKE

    class TestFromString:
        """Tests for IssueType.from_string()."""

        def test_epic(self):
            """Test epic parsing."""
            assert IssueType.from_string("epic") == IssueType.EPIC
            assert IssueType.from_string("Epic") == IssueType.EPIC
            assert IssueType.from_string("EPIC") == IssueType.EPIC

        def test_story(self):
            """Test story parsing."""
            assert IssueType.from_string("story") == IssueType.STORY
            assert IssueType.from_string("Story") == IssueType.STORY
            assert IssueType.from_string("userstory") == IssueType.STORY
            assert IssueType.from_string("user story") == IssueType.STORY
            assert IssueType.from_string("User Story") == IssueType.STORY

        def test_task(self):
            """Test task parsing."""
            assert IssueType.from_string("task") == IssueType.TASK
            assert IssueType.from_string("Task") == IssueType.TASK

        def test_subtask(self):
            """Test subtask parsing."""
            assert IssueType.from_string("subtask") == IssueType.SUBTASK
            assert IssueType.from_string("sub-task") == IssueType.SUBTASK
            assert IssueType.from_string("Sub-Task") == IssueType.SUBTASK

        def test_bug(self):
            """Test bug parsing."""
            assert IssueType.from_string("bug") == IssueType.BUG
            assert IssueType.from_string("Bug") == IssueType.BUG
            assert IssueType.from_string("defect") == IssueType.BUG

        def test_spike(self):
            """Test spike parsing."""
            assert IssueType.from_string("spike") == IssueType.SPIKE
            assert IssueType.from_string("Spike") == IssueType.SPIKE
            assert IssueType.from_string("research") == IssueType.SPIKE

        def test_unknown_defaults_to_task(self):
            """Test unknown issue type defaults to task."""
            assert IssueType.from_string("unknown") == IssueType.TASK
            assert IssueType.from_string("") == IssueType.TASK

