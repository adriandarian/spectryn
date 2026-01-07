"""
Tests for reverse sync (pull from Jira to markdown).
"""

from unittest.mock import Mock

import pytest

from spectra.adapters.formatters.markdown_writer import MarkdownUpdater, MarkdownWriter
from spectra.application.sync.reverse_sync import (
    ChangeDetail,
    PullChanges,
    PullResult,
    ReverseSyncOrchestrator,
)
from spectra.core.domain.entities import Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.config_provider import SyncConfig
from spectra.core.ports.issue_tracker import IssueData


class TestMarkdownWriter:
    """Tests for MarkdownWriter class."""

    def test_write_story_basic(self):
        """Test writing a basic story to markdown."""
        writer = MarkdownWriter()

        story = UserStory(
            id=StoryId("US-001"),
            title="User authentication",
            description=Description(
                role="user",
                want="to log in securely",
                benefit="I can access my account",
            ),
            story_points=5,
            priority=Priority.HIGH,
            status=Status.IN_PROGRESS,
            external_key=IssueKey("PROJ-123"),
        )

        result = writer.write_story(story)

        assert "### 🔄 US-001: User authentication" in result
        assert "**Story Points** | 5" in result
        assert "**Priority** | 🟡 High" in result
        assert "**Status** | 🔄 In Progress" in result
        assert "**As a** user" in result
        assert "**I want** to log in securely" in result
        assert "**So that** I can access my account" in result

    def test_write_story_with_subtasks(self):
        """Test writing a story with subtasks."""
        writer = MarkdownWriter()

        story = UserStory(
            id=StoryId("US-002"),
            title="Payment processing",
            story_points=8,
            status=Status.PLANNED,
            subtasks=[
                Subtask(
                    number=1,
                    name="Implement payment API",
                    description="Connect to Stripe",
                    story_points=3,
                    status=Status.DONE,
                ),
                Subtask(
                    number=2,
                    name="Add payment form",
                    description="Create UI",
                    story_points=2,
                    status=Status.IN_PROGRESS,
                ),
            ],
        )

        result = writer.write_story(story)

        assert "#### Subtasks" in result
        assert "Implement payment API" in result
        assert "Connect to Stripe" in result
        assert "✅ Done" in result
        assert "Add payment form" in result
        assert "🔄 In Progress" in result

    def test_write_epic(self):
        """Test writing a complete epic with stories."""
        writer = MarkdownWriter()

        epic = Epic(
            key=IssueKey("PROJ-100"),
            title="Authentication System",
            summary="Implement user authentication",
            stories=[
                UserStory(
                    id=StoryId("US-001"),
                    title="Login form",
                    story_points=3,
                    status=Status.DONE,
                ),
                UserStory(
                    id=StoryId("US-002"),
                    title="Password reset",
                    story_points=5,
                    status=Status.PLANNED,
                ),
            ],
        )

        result = writer.write_epic(epic)

        assert "# 🚀 PROJ-100: Authentication System" in result
        assert "Implement user authentication" in result
        assert "### ✅ US-001: Login form" in result
        assert "### 📋 US-002: Password reset" in result
        assert "Last synced from Jira:" in result

    def test_write_story_without_description(self):
        """Test writing a story without a description."""
        writer = MarkdownWriter()

        story = UserStory(
            id=StoryId("US-003"),
            title="Empty story",
            story_points=1,
            status=Status.PLANNED,
        )

        result = writer.write_story(story)

        assert "#### Description" in result
        assert "**As a** user" in result
        assert "[to be defined]" in result

    def test_write_story_with_acceptance_criteria(self):
        """Test writing a story with acceptance criteria."""
        writer = MarkdownWriter()

        story = UserStory(
            id=StoryId("US-004"),
            title="Feature with criteria",
            story_points=3,
            status=Status.PLANNED,
            acceptance_criteria=AcceptanceCriteria.from_list(
                ["Criterion 1", "Criterion 2", "Criterion 3"],
                [True, False, False],
            ),
        )

        result = writer.write_story(story)

        assert "#### Acceptance Criteria" in result
        assert "- [x] Criterion 1" in result
        assert "- [ ] Criterion 2" in result
        assert "- [ ] Criterion 3" in result


class TestMarkdownUpdater:
    """Tests for MarkdownUpdater class."""

    def test_update_field_in_story(self):
        """Test updating a single field in a story."""
        updater = MarkdownUpdater()

        content = """
### 🔄 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟢 Medium |
| **Status** | 🔄 In Progress |

---
"""

        result = updater.update_field_in_story(
            content=content,
            story_id="US-001",
            field="Status",
            new_value="✅ Done",
        )

        assert "| **Status** | ✅ Done |" in result
        assert "🔄 In Progress" not in result

    def test_append_story(self):
        """Test appending a new story to content."""
        updater = MarkdownUpdater()

        content = """
### ✅ US-001: Existing Story

#### Description
**As a** user
**I want** something
**So that** benefit

---

> *Last synced from Jira: 2025-01-01*
"""

        new_story = UserStory(
            id=StoryId("US-002"),
            title="New Story",
            story_points=3,
            status=Status.PLANNED,
        )

        result = updater.append_story(content, new_story)

        assert "US-001" in result
        assert "US-002" in result
        assert "New Story" in result
        assert "Last synced from Jira" in result


class TestReverseSyncOrchestrator:
    """Tests for ReverseSyncOrchestrator class."""

    @pytest.fixture
    def mock_tracker(self):
        """Create a mock issue tracker."""
        tracker = Mock()
        tracker.name = "Jira"
        tracker.is_connected = True
        tracker.test_connection.return_value = True
        return tracker

    @pytest.fixture
    def config(self):
        """Create a sync config."""
        return SyncConfig(dry_run=True)

    def test_pull_basic(self, mock_tracker, config, tmp_path):
        """Test basic pull operation."""
        # Setup mock responses
        mock_tracker.get_issue.return_value = IssueData(
            key="PROJ-100",
            summary="Test Epic",
            description=None,
            status="Open",
            issue_type="Epic",
        )

        mock_tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-101",
                summary="US-001: First Story",
                description=None,
                status="In Progress",
                issue_type="Story",
                subtasks=[],
            ),
            IssueData(
                key="PROJ-102",
                summary="US-002: Second Story",
                description=None,
                status="Done",
                issue_type="Story",
                subtasks=[],
            ),
        ]

        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        result = orchestrator.pull(
            epic_key="PROJ-100",
            output_path=str(tmp_path / "test.md"),
        )

        assert result.stories_pulled == 2
        assert result.success
        assert len(result.pulled_stories) == 2

    def test_pull_with_subtasks(self, mock_tracker, config, tmp_path):
        """Test pull operation with subtasks."""
        mock_tracker.get_issue.return_value = IssueData(
            key="PROJ-100",
            summary="Test Epic",
            status="Open",
        )

        mock_tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-101",
                summary="US-001: Story with subtasks",
                status="In Progress",
                subtasks=[
                    IssueData(
                        key="PROJ-110",
                        summary="Subtask 1",
                        status="Done",
                        issue_type="Sub-task",
                    ),
                    IssueData(
                        key="PROJ-111",
                        summary="Subtask 2",
                        status="Open",
                        issue_type="Sub-task",
                    ),
                ],
            ),
        ]

        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        result = orchestrator.pull(
            epic_key="PROJ-100",
            output_path=str(tmp_path / "test.md"),
        )

        assert result.stories_pulled == 1
        assert result.subtasks_pulled == 2

    def test_pull_no_stories(self, mock_tracker, config, tmp_path):
        """Test pull when no stories are found."""
        mock_tracker.get_issue.return_value = IssueData(
            key="PROJ-100",
            summary="Empty Epic",
            status="Open",
        )
        mock_tracker.get_epic_children.return_value = []

        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        result = orchestrator.pull(
            epic_key="PROJ-100",
            output_path=str(tmp_path / "test.md"),
        )

        assert result.stories_pulled == 0
        assert len(result.warnings) > 0

    def test_preview_changes(self, mock_tracker, config):
        """Test previewing changes before pull."""
        mock_tracker.get_issue.return_value = IssueData(
            key="PROJ-100",
            summary="Test Epic",
            status="Open",
        )

        mock_tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-101",
                summary="US-001: New Story",
                status="Open",
                subtasks=[],
            ),
        ]

        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        changes = orchestrator.preview(epic_key="PROJ-100")

        assert changes.has_changes
        assert len(changes.new_stories) == 1

    def test_adf_to_text(self, mock_tracker, config):
        """Test converting ADF to plain text."""
        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        adf = {
            "version": 1,
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

        result = orchestrator._adf_to_text(adf)

        assert "Hello" in result
        assert "World" in result

    def test_extract_story_id(self, mock_tracker, config):
        """Test extracting story ID from summary."""
        orchestrator = ReverseSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
        )

        assert orchestrator._extract_story_id("US-001: Test story") == "US-001"
        assert orchestrator._extract_story_id("US-042 Some title") == "US-042"
        assert orchestrator._extract_story_id("Just a title") is None


class TestPullResult:
    """Tests for PullResult dataclass."""

    def test_add_error(self):
        """Test adding an error."""
        result = PullResult()
        result.add_error("Something failed")

        assert not result.success
        assert len(result.errors) == 1

    def test_add_warning(self):
        """Test adding a warning."""
        result = PullResult()
        result.add_warning("Be careful")

        assert result.success  # Warnings don't fail
        assert len(result.warnings) == 1

    def test_has_changes(self):
        """Test has_changes property."""
        result = PullResult()
        assert not result.has_changes

        result.stories_created = 1
        assert result.has_changes

    def test_summary(self):
        """Test summary generation."""
        result = PullResult(
            dry_run=False,
            stories_pulled=5,
            stories_created=2,
            stories_updated=3,
            subtasks_pulled=10,
            output_path="/path/to/file.md",
        )

        summary = result.summary

        assert "Stories pulled: 5" in summary
        assert "New: 2" in summary
        assert "Updated: 3" in summary
        assert "Subtasks: 10" in summary
        assert "/path/to/file.md" in summary


class TestPullChanges:
    """Tests for PullChanges dataclass."""

    def test_has_changes_empty(self):
        """Test has_changes when empty."""
        changes = PullChanges()
        assert not changes.has_changes

    def test_has_changes_with_new_stories(self):
        """Test has_changes with new stories."""
        changes = PullChanges(
            new_stories=[
                UserStory(
                    id=StoryId("US-001"),
                    title="New",
                    status=Status.PLANNED,
                )
            ]
        )
        assert changes.has_changes
        assert changes.total_changes == 1

    def test_total_changes(self):
        """Test total_changes calculation."""
        changes = PullChanges(
            new_stories=[UserStory(id=StoryId("US-001"), title="New", status=Status.PLANNED)],
            updated_stories=[
                (UserStory(id=StoryId("US-002"), title="Updated", status=Status.DONE), []),
            ],
            deleted_stories=["US-003"],
        )

        assert changes.total_changes == 3


class TestChangeDetail:
    """Tests for ChangeDetail dataclass."""

    def test_str(self):
        """Test string representation."""
        detail = ChangeDetail(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            old_value="Open",
            new_value="Done",
        )

        result = str(detail)

        assert "US-001" in result
        assert "PROJ-123" in result
        assert "status" in result
