"""Tests for domain entities and value objects."""

import pytest

from spectra.core.domain import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    Epic,
    IssueKey,
    Priority,
    Status,
    StoryId,
    Subtask,
    UserStory,
)


class TestStatus:
    """Tests for Status enum."""

    def test_from_string_done(self):
        assert Status.from_string("Done") == Status.DONE
        assert Status.from_string("resolved") == Status.DONE
        assert Status.from_string("✅ Complete") == Status.DONE

    def test_from_string_in_progress(self):
        assert Status.from_string("In Progress") == Status.IN_PROGRESS
        assert Status.from_string("🔄 Active") == Status.IN_PROGRESS

    def test_from_string_default(self):
        assert Status.from_string("unknown") == Status.PLANNED

    def test_is_complete(self):
        assert Status.DONE.is_complete()
        assert Status.CANCELLED.is_complete()
        assert not Status.IN_PROGRESS.is_complete()

    def test_emoji(self):
        assert Status.DONE.emoji == "✅"
        assert Status.IN_PROGRESS.emoji == "🔄"


class TestPriority:
    """Tests for Priority enum."""

    def test_from_string(self):
        assert Priority.from_string("High") == Priority.HIGH
        assert Priority.from_string("🔴 Critical") == Priority.CRITICAL
        assert Priority.from_string("low") == Priority.LOW
        assert Priority.from_string("unknown") == Priority.MEDIUM


class TestStoryId:
    """Tests for StoryId value object."""

    def test_from_string(self):
        sid = StoryId.from_string("us-001")
        assert str(sid) == "US-001"

    def test_number(self):
        sid = StoryId("US-042")
        assert sid.number == 42

    def test_prefix_property(self):
        """Test extracting prefix from story ID."""
        sid = StoryId("PROJ-123")
        assert sid.prefix == "PROJ"

    def test_flexible_prefix_eu(self):
        """Test EU- prefix for regional stories."""
        sid = StoryId.from_string("EU-042")
        assert str(sid) == "EU-042"
        assert sid.prefix == "EU"
        assert sid.number == 42

    def test_flexible_prefix_proj(self):
        """Test PROJ- prefix for project-based stories."""
        sid = StoryId.from_string("proj-123")
        assert str(sid) == "PROJ-123"
        assert sid.prefix == "PROJ"

    def test_flexible_prefix_feat(self):
        """Test FEAT- prefix for feature-based stories."""
        sid = StoryId.from_string("FEAT-001")
        assert str(sid) == "FEAT-001"
        assert sid.prefix == "FEAT"

    def test_flexible_prefix_na(self):
        """Test NA- prefix for North America stories."""
        sid = StoryId("NA-999")
        assert str(sid) == "NA-999"
        assert sid.prefix == "NA"
        assert sid.number == 999

    def test_flexible_prefix_long(self):
        """Test long prefix."""
        sid = StoryId("VERYLONGPREFIX-12345")
        assert str(sid) == "VERYLONGPREFIX-12345"
        assert sid.prefix == "VERYLONGPREFIX"
        assert sid.number == 12345

    def test_flexible_prefix_short(self):
        """Test single-letter prefix."""
        sid = StoryId("A-1")
        assert str(sid) == "A-1"
        assert sid.prefix == "A"
        assert sid.number == 1

    def test_normalizes_to_uppercase(self):
        """Test that story IDs are normalized to uppercase."""
        sid = StoryId.from_string("proj-123")
        assert str(sid) == "PROJ-123"

        sid2 = StoryId("feat-042")
        # Post-init normalizes
        assert str(sid2) == "FEAT-042"


class TestIssueKey:
    """Tests for IssueKey value object."""

    def test_valid_key(self):
        key = IssueKey("PROJ-123")
        assert key.project == "PROJ"
        assert key.number == 123

    def test_invalid_key(self):
        with pytest.raises(ValueError):
            IssueKey("invalid")


class TestCommitRef:
    """Tests for CommitRef value object."""

    def test_short_hash(self):
        commit = CommitRef(hash="abc1234567890", message="Fix bug")
        assert commit.short_hash == "abc1234"

    def test_str(self):
        commit = CommitRef(hash="abc1234", message="Fix bug")
        assert str(commit) == "abc1234: Fix bug"


class TestDescription:
    """Tests for Description value object."""

    def test_from_markdown(self):
        md = """
        **As a** developer
        **I want** tests
        **So that** code works
        """
        desc = Description.from_markdown(md)
        assert desc is not None
        assert desc.role == "developer"
        assert desc.want == "tests"
        assert desc.benefit == "code works"

    def test_to_markdown(self):
        desc = Description(role="user", want="feature", benefit="value")
        md = desc.to_markdown()
        assert "**As a** user" in md
        assert "**I want** feature" in md
        assert "**So that** value" in md


class TestAcceptanceCriteria:
    """Tests for AcceptanceCriteria value object."""

    def test_from_list(self):
        ac = AcceptanceCriteria.from_list(["Item 1", "Item 2"], [True, False])
        assert len(ac) == 2
        assert ac.completion_ratio == 0.5

    def test_to_markdown(self):
        ac = AcceptanceCriteria.from_list(["Done", "Todo"], [True, False])
        md = ac.to_markdown()
        assert "- [x] Done" in md
        assert "- [ ] Todo" in md


class TestUserStory:
    """Tests for UserStory entity."""

    def test_normalize_title(self):
        story = UserStory(id=StoryId("US-001"), title="GUI - State Management (Future)")
        normalized = story.normalize_title()
        assert "gui" in normalized
        assert "state" in normalized
        assert "future" not in normalized

    def test_matches_title(self):
        story = UserStory(id=StoryId("US-001"), title="GUI State Management")
        assert story.matches_title("GUI - State Management")
        assert story.matches_title("gui state management")
        assert not story.matches_title("Something else")

    def test_find_subtask(self):
        story = UserStory(
            id=StoryId("US-001"),
            title="Test",
            subtasks=[
                Subtask(name="Create component"),
                Subtask(name="Add tests"),
            ],
        )
        found = story.find_subtask("create component")
        assert found is not None
        assert found.name == "Create component"


class TestSubtask:
    """Tests for Subtask entity."""

    def test_normalize_name(self):
        st = Subtask(name="Create Component - Part 1")
        normalized = st.normalize_name()
        assert "create" in normalized
        assert "-" not in normalized

    def test_matches(self):
        st1 = Subtask(name="Create React Component")
        st2 = Subtask(name="Create React component")
        assert st1.matches(st2)


class TestEpic:
    """Tests for Epic entity."""

    def test_find_story_by_title(self):
        epic = Epic(
            key=IssueKey("PROJ-1"),
            title="Test Epic",
            stories=[
                UserStory(id=StoryId("US-001"), title="First Story"),
                UserStory(id=StoryId("US-002"), title="Second Story"),
            ],
        )
        found = epic.find_story_by_title("First Story")
        assert found is not None
        assert str(found.id) == "US-001"

    def test_completion_percentage(self):
        epic = Epic(
            key=IssueKey("PROJ-1"),
            title="Test",
            stories=[
                UserStory(id=StoryId("US-001"), title="Done", status=Status.DONE),
                UserStory(id=StoryId("US-002"), title="Open", status=Status.OPEN),
            ],
        )
        assert epic.completion_percentage == 50.0

    def test_epic_with_story_id_key(self):
        """Test Epic can use StoryId as key."""
        epic = Epic(
            key=StoryId("EPIC-100"),
            title="Test Epic",
        )
        assert str(epic.key) == "EPIC-100"

    def test_epic_find_story_not_found(self):
        """Test finding non-existent story returns None."""
        epic = Epic(
            key=IssueKey("PROJ-1"),
            title="Test Epic",
            stories=[UserStory(id=StoryId("US-001"), title="Only Story")],
        )
        found = epic.find_story_by_title("Nonexistent")
        assert found is None

    def test_epic_total_story_points(self):
        """Test calculating total story points."""
        epic = Epic(
            key=IssueKey("PROJ-1"),
            title="Test Epic",
            stories=[
                UserStory(id=StoryId("US-001"), title="S1", story_points=3),
                UserStory(id=StoryId("US-002"), title="S2", story_points=5),
                UserStory(id=StoryId("US-003"), title="S3", story_points=8),
            ],
        )
        assert epic.total_story_points == 16

    def test_epic_empty_stories_completion(self):
        """Test completion percentage with no stories."""
        epic = Epic(
            key=IssueKey("PROJ-1"),
            title="Empty Epic",
            stories=[],
        )
        # Empty epic returns 0.0 completion
        assert epic.completion_percentage == 0.0


class TestStoryIdAdvanced:
    """Additional tests for StoryId edge cases."""

    def test_story_id_underscore_separator(self):
        """Test underscore separator."""
        sid = StoryId("PROJ_123")
        assert sid.prefix == "PROJ"
        assert sid.separator == "_"
        assert sid.number == 123

    def test_story_id_slash_separator(self):
        """Test slash separator."""
        sid = StoryId("PROJ/456")
        assert sid.prefix == "PROJ"
        assert sid.separator == "/"
        assert sid.number == 456

    def test_story_id_numeric(self):
        """Test purely numeric story ID."""
        sid = StoryId("123")
        assert sid.is_numeric is True
        assert sid.prefix == ""
        assert sid.number == 123

    def test_story_id_github_style(self):
        """Test GitHub-style #123 format."""
        sid = StoryId("#42")
        assert sid.is_numeric is True
        assert sid.number == 42

    def test_story_id_no_separator(self):
        """Test story ID with no separator character."""
        sid = StoryId("123")
        assert sid.separator == ""


class TestIssueKeyAdvanced:
    """Additional tests for IssueKey edge cases."""

    def test_issue_key_underscore_separator(self):
        """Test underscore separator."""
        key = IssueKey("PROJ_123")
        assert key.project == "PROJ"
        assert key.separator == "_"
        assert key.number == 123

    def test_issue_key_slash_separator(self):
        """Test slash separator."""
        key = IssueKey("PROJ/456")
        assert key.project == "PROJ"
        assert key.separator == "/"
        assert key.number == 456

    def test_issue_key_numeric(self):
        """Test purely numeric issue key (Azure DevOps style)."""
        key = IssueKey("789")
        assert key.is_numeric is True
        assert key.project == ""
        assert key.number == 789

    def test_issue_key_github_style(self):
        """Test GitHub-style #123 format."""
        key = IssueKey("#42")
        assert key.is_numeric is True
        assert key.number == 42

    def test_issue_key_str_uppercase(self):
        """Test string representation is uppercase."""
        key = IssueKey("proj-123")
        assert str(key) == "PROJ-123"

    def test_issue_key_numeric_str(self):
        """Test numeric key string representation."""
        key = IssueKey("#99")
        assert str(key) == "#99"


class TestAcceptanceCriteriaAdvanced:
    """Additional tests for AcceptanceCriteria."""

    def test_empty_criteria(self):
        """Test empty acceptance criteria."""
        ac = AcceptanceCriteria.from_list([])
        assert len(ac) == 0
        assert ac.completion_ratio == 1.0

    def test_all_checked(self):
        """Test all criteria checked."""
        ac = AcceptanceCriteria.from_list(["A", "B", "C"], [True, True, True])
        assert ac.completion_ratio == 1.0

    def test_iteration(self):
        """Test iterating over criteria."""
        ac = AcceptanceCriteria.from_list(["A", "B"], [True, False])
        items = list(ac)
        assert items[0] == ("A", True)
        assert items[1] == ("B", False)


class TestDescriptionAdvanced:
    """Additional tests for Description."""

    def test_from_markdown_no_match(self):
        """Test from_markdown with non-matching content."""
        desc = Description.from_markdown("Just some text")
        assert desc is None

    def test_to_plain_text(self):
        """Test to_plain_text conversion."""
        desc = Description(role="user", want="a feature", benefit="I can do stuff")
        plain = desc.to_plain_text()
        assert "As a user" in plain
        assert "I want a feature" in plain
        assert "so that I can do stuff" in plain

    def test_description_str(self):
        """Test string representation."""
        desc = Description(role="dev", want="code", benefit="it works")
        assert str(desc) == desc.to_plain_text()

    def test_to_markdown_with_additional_context(self):
        """Test to_markdown with additional context."""
        desc = Description(
            role="user",
            want="feature",
            benefit="value",
            additional_context="Extra notes here",
        )
        md = desc.to_markdown()
        assert "Extra notes here" in md


class TestUserStoryAdvanced:
    """Additional tests for UserStory."""

    def test_find_subtask_not_found(self):
        """Test find_subtask when not found."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test",
            subtasks=[Subtask(name="Existing")],
        )
        found = story.find_subtask("Nonexistent")
        assert found is None

    def test_story_with_external_key(self):
        """Test story with external key."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Story",
            external_key="PROJ-123",
            external_url="https://jira.example.com/browse/PROJ-123",
        )
        assert story.external_key == "PROJ-123"
        assert "jira.example.com" in story.external_url

    def test_story_with_labels(self):
        """Test story with labels."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Labeled Story",
            labels=["backend", "api", "urgent"],
        )
        assert len(story.labels) == 3
        assert "backend" in story.labels


class TestSubtaskAdvanced:
    """Additional tests for Subtask."""

    def test_subtask_with_all_fields(self):
        """Test subtask with all fields."""
        st = Subtask(
            number=1,
            name="Test Subtask",
            description="Description here",
            story_points=3,
            status=Status.IN_PROGRESS,
            assignee="user@example.com",
            external_key="PROJ-456",
        )
        assert st.number == 1
        assert st.story_points == 3
        assert st.status == Status.IN_PROGRESS
        assert st.external_key == "PROJ-456"

    def test_subtask_default_status(self):
        """Test subtask default status is PLANNED."""
        st = Subtask(name="Test")
        assert st.status == Status.PLANNED
