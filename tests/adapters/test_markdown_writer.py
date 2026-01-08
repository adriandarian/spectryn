"""Tests for the markdown writer/generator."""

import pytest

from spectryn.adapters.formatters.markdown_writer import MarkdownUpdater, MarkdownWriter
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, CommitRef, Description, StoryId


class TestMarkdownWriter:
    """Tests for MarkdownWriter class."""

    @pytest.fixture
    def writer(self) -> MarkdownWriter:
        """Create a markdown writer instance."""
        return MarkdownWriter()

    @pytest.fixture
    def sample_story(self) -> UserStory:
        """Create a sample user story."""
        return UserStory(
            id=StoryId.from_string("US-001"),
            title="Test Story",
            story_points=5,
            priority=Priority.HIGH,
            status=Status.IN_PROGRESS,
            description=Description(
                role="developer",
                want="to test the writer",
                benefit="it generates correct markdown",
            ),
            acceptance_criteria=AcceptanceCriteria.from_list(["Criterion 1", "Criterion 2"]),
            technical_notes="Some technical notes",
        )

    @pytest.fixture
    def sample_epic(self, sample_story: UserStory) -> Epic:
        """Create a sample epic with stories."""
        return Epic(
            key=StoryId.from_string("PROJ-100"),
            title="Test Epic",
            summary="Epic summary",
            description="Epic description",
            stories=[sample_story],
        )

    def test_write_story_basic(self, writer: MarkdownWriter, sample_story: UserStory) -> None:
        """Test writing a basic story."""
        result = writer.write_story(sample_story)

        assert "US-001" in result
        assert "Test Story" in result
        assert "Story Points" in result
        assert "5" in result
        assert "Priority" in result
        assert "High" in result
        assert "Status" in result

    def test_write_story_with_description(
        self, writer: MarkdownWriter, sample_story: UserStory
    ) -> None:
        """Test writing a story with user story format description."""
        result = writer.write_story(sample_story)

        assert "**As a**" in result
        assert "developer" in result
        assert "**I want**" in result
        assert "**So that**" in result

    def test_write_story_without_description(self, writer: MarkdownWriter) -> None:
        """Test writing a story without description uses placeholder."""
        story = UserStory(
            id=StoryId.from_string("US-002"),
            title="No Description Story",
            story_points=3,
            priority=Priority.MEDIUM,
            status=Status.PLANNED,
            description=None,
        )

        result = writer.write_story(story)

        assert "[to be defined]" in result

    def test_write_story_with_acceptance_criteria(
        self, writer: MarkdownWriter, sample_story: UserStory
    ) -> None:
        """Test writing a story with acceptance criteria."""
        result = writer.write_story(sample_story)

        assert "Acceptance Criteria" in result
        assert "Criterion 1" in result
        assert "Criterion 2" in result

    def test_write_story_with_subtasks(self, writer: MarkdownWriter) -> None:
        """Test writing a story with subtasks."""
        story = UserStory(
            id=StoryId.from_string("US-003"),
            title="Story with Subtasks",
            story_points=8,
            priority=Priority.HIGH,
            status=Status.IN_PROGRESS,
            subtasks=[
                Subtask(number=1, name="Subtask 1", description="Do thing 1", story_points=2),
                Subtask(number=2, name="Subtask 2", description="Do thing 2", story_points=3),
            ],
        )

        result = writer.write_story(story)

        assert "Subtasks" in result
        assert "Subtask 1" in result
        assert "Subtask 2" in result
        assert "Do thing 1" in result

    def test_write_story_with_commits(self, writer: MarkdownWriter) -> None:
        """Test writing a story with related commits."""
        story = UserStory(
            id=StoryId.from_string("US-004"),
            title="Story with Commits",
            story_points=5,
            priority=Priority.MEDIUM,
            status=Status.DONE,
            commits=[
                CommitRef(hash="abc1234567890def", message="feat: add feature"),
                CommitRef(hash="def0987654321abc", message="fix: bug fix"),
            ],
        )

        result = writer.write_story(story)

        assert "Related Commits" in result
        assert "abc1234" in result
        assert "feat: add feature" in result

    def test_write_story_with_technical_notes(
        self, writer: MarkdownWriter, sample_story: UserStory
    ) -> None:
        """Test writing a story with technical notes."""
        result = writer.write_story(sample_story)

        assert "Technical Notes" in result
        assert "Some technical notes" in result

    def test_write_story_with_external_key(self, writer: MarkdownWriter) -> None:
        """Test writing a story with Jira link."""
        story = UserStory(
            id=StoryId.from_string("US-005"),
            title="Story with External Key",
            story_points=3,
            priority=Priority.LOW,
            status=Status.PLANNED,
            external_key="PROJ-456",
            external_url="https://jira.example.com/browse/PROJ-456",
        )

        result = writer.write_story(story)

        assert "PROJ-456" in result
        assert "https://jira.example.com/browse/PROJ-456" in result

    def test_write_story_with_assignee(self, writer: MarkdownWriter) -> None:
        """Test writing a story with assignee."""
        story = UserStory(
            id=StoryId.from_string("US-006"),
            title="Assigned Story",
            story_points=3,
            priority=Priority.MEDIUM,
            status=Status.IN_PROGRESS,
            assignee="developer@example.com",
        )

        result = writer.write_story(story)

        assert "Assignee" in result
        assert "developer@example.com" in result

    def test_write_story_with_labels(self, writer: MarkdownWriter) -> None:
        """Test writing a story with labels."""
        story = UserStory(
            id=StoryId.from_string("US-007"),
            title="Labeled Story",
            story_points=2,
            priority=Priority.LOW,
            status=Status.PLANNED,
            labels=["backend", "api", "urgent"],
        )

        result = writer.write_story(story)

        assert "Labels" in result
        assert "backend" in result
        assert "api" in result
        assert "urgent" in result

    def test_write_epic(self, writer: MarkdownWriter, sample_epic: Epic) -> None:
        """Test writing a complete epic."""
        result = writer.write_epic(sample_epic)

        assert "PROJ-100" in result
        assert "Test Epic" in result
        assert "Epic summary" in result
        assert "Epic description" in result
        assert "US-001" in result  # Story included
        assert "Last synced" in result

    def test_write_epic_without_header(self, sample_epic: Epic) -> None:
        """Test writing an epic without header."""
        writer = MarkdownWriter(include_epic_header=False)
        result = writer.write_epic(sample_epic)

        # Should not have epic title as header
        assert not result.startswith("# 🚀 PROJ-100")
        # But should still have stories
        assert "US-001" in result

    def test_write_stories_list(self, writer: MarkdownWriter, sample_story: UserStory) -> None:
        """Test writing multiple stories without epic header."""
        stories = [sample_story]
        result = writer.write_stories(stories)

        assert "US-001" in result
        assert "---" in result  # Story separator

    def test_writer_options(self) -> None:
        """Test writer initialization options."""
        writer = MarkdownWriter(
            include_epic_header=False,
            include_metadata=False,
            include_subtasks=False,
            include_commits=False,
            include_technical_notes=False,
        )

        story = UserStory(
            id=StoryId.from_string("US-008"),
            title="Minimal Story",
            story_points=1,
            priority=Priority.LOW,
            status=Status.PLANNED,
            subtasks=[Subtask(number=1, name="Sub", description="Desc")],
            commits=[CommitRef(hash="abc123", message="msg")],
            technical_notes="Notes",
        )

        result = writer.write_story(story)

        # Should not include optional sections
        assert "Story Points" not in result  # No metadata
        assert "Subtasks" not in result
        assert "Related Commits" not in result
        assert "Technical Notes" not in result

    def test_subtask_with_pipe_character(self, writer: MarkdownWriter) -> None:
        """Test that pipe characters in subtask names are escaped."""
        story = UserStory(
            id=StoryId.from_string("US-009"),
            title="Story with Pipe",
            story_points=1,
            priority=Priority.LOW,
            status=Status.PLANNED,
            subtasks=[
                Subtask(number=1, name="Task with | pipe", description="Description | here"),
            ],
        )

        result = writer.write_story(story)

        assert "\\|" in result  # Pipe should be escaped

    def test_status_emoji(self, writer: MarkdownWriter) -> None:
        """Test that status emojis are included."""
        for status in [Status.PLANNED, Status.IN_PROGRESS, Status.DONE]:
            story = UserStory(
                id=StoryId.from_string("US-010"),
                title="Test",
                story_points=1,
                priority=Priority.LOW,
                status=status,
            )

            result = writer.write_story(story)
            assert status.emoji in result


class TestMarkdownUpdater:
    """Tests for MarkdownUpdater class."""

    @pytest.fixture
    def updater(self) -> MarkdownUpdater:
        """Create a markdown updater instance."""
        return MarkdownUpdater()

    @pytest.fixture
    def sample_content(self) -> str:
        """Create sample markdown content."""
        return """# 🚀 PROJ-100: Test Epic

---

### 📋 US-001: First Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | To Do |

#### Description

**As a** user
**I want** to test
**So that** it works

---

### 📋 US-002: Second Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Status** | In Progress |

#### Description

**As a** developer
**I want** something
**So that** benefit

---

> *Last synced from Jira: 2025-01-15 10:00:00*
"""

    def test_update_field_in_story(self, updater: MarkdownUpdater, sample_content: str) -> None:
        """Test updating a single field in a story."""
        result = updater.update_field_in_story(
            sample_content,
            story_id="US-001",
            field="Status",
            new_value="✅ Done",
        )

        # The new value should be present
        assert "Done" in result

    def test_append_story(self, updater: MarkdownUpdater, sample_content: str) -> None:
        """Test appending a new story."""
        new_story = UserStory(
            id=StoryId.from_string("US-003"),
            title="New Story",
            story_points=8,
            priority=Priority.HIGH,
            status=Status.PLANNED,
        )

        result = updater.append_story(sample_content, new_story)

        assert "US-003" in result
        assert "New Story" in result
        # Footer should still be at end
        assert "Last synced" in result

    def test_append_story_without_footer(self, updater: MarkdownUpdater) -> None:
        """Test appending a story to content without footer."""
        content = """### 📋 US-001: Story

| **Story Points** | 3 |

Description here.
"""

        new_story = UserStory(
            id=StoryId.from_string("US-002"),
            title="New Story",
            story_points=5,
            priority=Priority.MEDIUM,
            status=Status.PLANNED,
        )

        result = updater.append_story(content, new_story)

        assert "US-002" in result
        assert "New Story" in result
