"""
Property-based tests for domain entities and value objects.

Tests invariants and edge cases for:
- Value object parsing and normalization
- Entity matching logic
- Subtask fuzzy matching
"""

from hypothesis import assume, given
from hypothesis import strategies as st

from spectryn.core.domain import (
    AcceptanceCriteria,
    IssueKey,
    Priority,
    Status,
    StoryId,
    Subtask,
    UserStory,
)


# =============================================================================
# StoryId Properties
# =============================================================================


class TestStoryIdProperties:
    """Property tests for StoryId value object."""

    @given(st.integers(min_value=1, max_value=9999))
    def test_story_id_from_prefixed_number(self, num):
        """StoryId created from prefixed ID preserves the number."""
        story_id = StoryId.from_string(f"US-{num:03d}")
        assert story_id.number == num

    @given(st.integers(min_value=1, max_value=9999))
    def test_story_id_preserves_prefix(self, num):
        """StoryId preserves any PREFIX-NUMBER format."""
        # Test with various prefixes - now accepts any format
        story_id = StoryId.from_string(f"US-{num:03d}")
        assert str(story_id).startswith("US-")

        story_id = StoryId.from_string(f"PROJ-{num}")
        assert str(story_id).startswith("PROJ-")

        story_id = StoryId.from_string(f"EU-{num:04d}")
        assert str(story_id).startswith("EU-")

    @given(st.integers(min_value=1, max_value=9999))
    def test_story_id_roundtrip(self, num):
        """StoryId can roundtrip through string."""
        original = StoryId.from_string(f"US-{num:03d}")
        roundtrip = StoryId.from_string(str(original))
        assert original.value == roundtrip.value

    @given(st.sampled_from(["US", "PROJ", "EU", "FEAT", "BUG"]))
    def test_story_id_extracts_prefix(self, prefix):
        """StoryId.prefix extracts the prefix portion."""
        story_id = StoryId.from_string(f"{prefix}-001")
        assert story_id.prefix == prefix


# =============================================================================
# IssueKey Properties
# =============================================================================


class TestIssueKeyProperties:
    """Property tests for IssueKey value object."""

    @given(
        st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=10),
        st.integers(min_value=1, max_value=99999),
    )
    def test_issue_key_format(self, project, num):
        """IssueKey maintains PROJECT-NUMBER format."""
        key_str = f"{project}-{num}"
        key = IssueKey(value=key_str)

        assert key.project == project.upper()
        assert key.number == num

    @given(
        st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=10),
        st.integers(min_value=1, max_value=99999),
    )
    def test_issue_key_str_uppercase(self, project, num):
        """IssueKey string representation is uppercase."""
        key_str = f"{project.lower()}-{num}"
        key = IssueKey(value=key_str)

        assert str(key) == str(key).upper()

    @given(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=10),
        st.integers(min_value=1, max_value=99999),
    )
    def test_issue_key_case_insensitive_project(self, project, num):
        """IssueKey project property is always uppercase."""
        key = IssueKey(value=f"{project}-{num}")

        assert key.project == project.upper()


# =============================================================================
# AcceptanceCriteria Properties
# =============================================================================


class TestAcceptanceCriteriaProperties:
    """Property tests for AcceptanceCriteria value object."""

    @given(st.lists(st.text(max_size=100), max_size=20))
    def test_ac_len(self, items):
        """AcceptanceCriteria length matches input."""
        ac = AcceptanceCriteria.from_list(items)
        assert len(ac) == len(items)

    @given(st.lists(st.text(min_size=1, max_size=100), min_size=0, max_size=20))
    def test_ac_bool(self, items):
        """AcceptanceCriteria is truthy iff non-empty."""
        ac = AcceptanceCriteria.from_list(items)
        assert bool(ac) == (len(items) > 0)


# =============================================================================
# Subtask Matching Properties
# =============================================================================


class TestSubtaskMatchingProperties:
    """Property tests for Subtask fuzzy matching."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_subtask_matches_itself(self, name):
        """A subtask matches itself."""
        assume(name.strip())  # Non-empty

        subtask = Subtask(name=name)
        assert subtask.matches(subtask)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_subtask_match_is_symmetric(self, name):
        """Subtask matching is symmetric."""
        assume(name.strip())

        s1 = Subtask(name=name)
        s2 = Subtask(name=name)

        assert s1.matches(s2) == s2.matches(s1)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_subtask_normalize_idempotent(self, name):
        """Normalizing twice gives same result."""
        subtask = Subtask(name=name)

        once = subtask.normalize_name()
        twice = Subtask(name=once).normalize_name()

        assert once == twice

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_subtask_normalize_lowercase(self, name):
        """Normalized name is lowercase."""
        subtask = Subtask(name=name)
        normalized = subtask.normalize_name()

        assert normalized == normalized.lower()


# =============================================================================
# UserStory Matching Properties
# =============================================================================


class TestUserStoryMatchingProperties:
    """Property tests for UserStory title matching."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_story_matches_own_title(self, title):
        """Story matches its own title."""
        assume(title.strip())

        story = UserStory(id=StoryId("US-001"), title=title)
        assert story.matches_title(title)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=100))
    def test_story_normalize_idempotent(self, title):
        """Normalizing title twice gives same result."""
        story = UserStory(id=StoryId("US-001"), title=title)

        once = story.normalize_title()
        twice = UserStory(id=StoryId("US-002"), title=once).normalize_title()

        assert once == twice

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=5, max_size=50))
    def test_story_normalize_strips_future_suffix(self, base):
        """Normalize removes (future) suffix."""
        assume(base.strip())

        title_with_future = f"{base} (future)"
        title_without = base

        story1 = UserStory(id=StoryId("US-001"), title=title_with_future)
        story2 = UserStory(id=StoryId("US-002"), title=title_without)

        # After normalization, they should match if base is the same
        assert story1.normalize_title() == story2.normalize_title()


# =============================================================================
# Status Enum Properties
# =============================================================================


class TestStatusProperties:
    """Property tests for Status enum."""

    @given(st.sampled_from(list(Status)))
    def test_status_active_and_complete_mutually_exclusive(self, status):
        """A status cannot be both active and complete simultaneously."""
        is_active = status.is_active()
        is_complete = status.is_complete()

        # A status can be neither (e.g., PLANNED), but never both
        assert not (is_active and is_complete)

    @given(st.sampled_from(list(Status)))
    def test_status_from_string_roundtrip(self, status):
        """Status can roundtrip through string conversion."""
        status_str = status.name
        parsed = Status[status_str]

        assert parsed == status

    def test_active_statuses(self):
        """Verify which statuses are active."""
        active_statuses = [s for s in Status if s.is_active()]
        assert Status.IN_PROGRESS in active_statuses
        assert Status.IN_REVIEW in active_statuses
        assert Status.PLANNED not in active_statuses
        assert Status.DONE not in active_statuses

    def test_complete_statuses(self):
        """Verify which statuses are complete."""
        complete_statuses = [s for s in Status if s.is_complete()]
        assert Status.DONE in complete_statuses
        assert Status.CANCELLED in complete_statuses
        assert Status.PLANNED not in complete_statuses
        assert Status.IN_PROGRESS not in complete_statuses


# =============================================================================
# Priority Enum Properties
# =============================================================================


class TestPriorityProperties:
    """Property tests for Priority enum."""

    @given(st.sampled_from(list(Priority)))
    def test_priority_display_not_empty(self, priority):
        """Priority display name is not empty."""
        display = priority.display_name
        assert len(display) > 0


# =============================================================================
# Subtask Serialization Properties
# =============================================================================


class TestSubtaskSerializationProperties:
    """Property tests for Subtask serialization."""

    @given(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=100),
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=1, max_value=21),
        st.sampled_from(list(Status)),
    )
    def test_subtask_to_dict_roundtrip(self, name, number, points, status):
        """Subtask to_dict contains all key information."""
        assume(name.strip())

        subtask = Subtask(
            name=name,
            number=number,
            story_points=points,
            status=status,
        )

        d = subtask.to_dict()

        assert d["name"] == name
        assert d["number"] == number
        assert d["story_points"] == points
        assert d["status"] == status.name

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=100))
    def test_subtask_has_id(self, name):
        """Every subtask has a non-empty ID."""
        assume(name.strip())

        subtask = Subtask(name=name)

        assert subtask.id is not None
        assert len(subtask.id) > 0
