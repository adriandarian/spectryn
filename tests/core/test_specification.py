"""Tests for the Specification pattern."""

from dataclasses import dataclass

from spectryn.core.specification import (
    AllSubtasksMatchSpec,
    AlwaysFalse,
    AlwaysTrue,
    AnySubtaskMatchesSpec,
    AttributeContains,
    AttributeIn,
    AttributeMatches,
    HasAttribute,
    HasDescriptionSpec,
    HasKeySpec,
    HasSubtasksSpec,
    IssueTypeSpec,
    KeyPrefixSpec,
    MatchedSpec,
    PredicateSpec,
    StatusSpec,
    StoryPointsSpec,
    TitleMatchesSpec,
    UnmatchedSpec,
    all_of,
    any_of,
    none_of,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockIssue:
    """Mock issue for testing specifications."""

    key: str
    title: str
    status: str
    issue_type: str = "Story"
    description: str | None = None
    story_points: int | None = None
    subtasks: list | None = None
    external_key: str | None = None


@dataclass
class MockSubtask:
    """Mock subtask for testing."""

    key: str
    title: str
    status: str


# =============================================================================
# Base Specification Tests
# =============================================================================


class TestSpecificationComposition:
    """Test and/or/not composition."""

    def test_and_both_true(self):
        spec = AlwaysTrue().and_(AlwaysTrue())
        assert spec.is_satisfied_by(None)

    def test_and_one_false(self):
        spec = AlwaysTrue().and_(AlwaysFalse())
        assert not spec.is_satisfied_by(None)

    def test_or_one_true(self):
        spec = AlwaysTrue().or_(AlwaysFalse())
        assert spec.is_satisfied_by(None)

    def test_or_both_false(self):
        spec = AlwaysFalse().or_(AlwaysFalse())
        assert not spec.is_satisfied_by(None)

    def test_not_true(self):
        spec = AlwaysTrue().not_()
        assert not spec.is_satisfied_by(None)

    def test_not_false(self):
        spec = AlwaysFalse().not_()
        assert spec.is_satisfied_by(None)

    def test_operator_and(self):
        spec = AlwaysTrue() & AlwaysTrue()
        assert spec.is_satisfied_by(None)

    def test_operator_or(self):
        spec = AlwaysFalse() | AlwaysTrue()
        assert spec.is_satisfied_by(None)

    def test_operator_not(self):
        spec = ~AlwaysTrue()
        assert not spec.is_satisfied_by(None)

    def test_complex_composition(self):
        # (True AND False) OR (NOT False)
        spec = (AlwaysTrue() & AlwaysFalse()) | (~AlwaysFalse())
        assert spec.is_satisfied_by(None)


class TestSpecificationCollection:
    """Test collection operations."""

    def test_filter(self):
        issues = [
            MockIssue("A-1", "Task 1", "Done"),
            MockIssue("A-2", "Task 2", "Open"),
            MockIssue("A-3", "Task 3", "Done"),
        ]

        done_spec = StatusSpec("Done")
        done_issues = done_spec.filter(issues)

        assert len(done_issues) == 2
        assert all(i.status == "Done" for i in done_issues)

    def test_any_satisfy(self):
        issues = [
            MockIssue("A-1", "Task 1", "Open"),
            MockIssue("A-2", "Task 2", "Done"),
        ]

        assert StatusSpec("Done").any_satisfy(issues)
        assert not StatusSpec("Cancelled").any_satisfy(issues)

    def test_all_satisfy(self):
        issues = [
            MockIssue("A-1", "Task 1", "Done"),
            MockIssue("A-2", "Task 2", "Done"),
        ]

        assert StatusSpec("Done").all_satisfy(issues)

        issues.append(MockIssue("A-3", "Task 3", "Open"))
        assert not StatusSpec("Done").all_satisfy(issues)

    def test_count(self):
        issues = [
            MockIssue("A-1", "Task 1", "Done"),
            MockIssue("A-2", "Task 2", "Open"),
            MockIssue("A-3", "Task 3", "Done"),
        ]

        assert StatusSpec("Done").count(issues) == 2

    def test_first(self):
        issues = [
            MockIssue("A-1", "Task 1", "Open"),
            MockIssue("A-2", "Task 2", "Done"),
            MockIssue("A-3", "Task 3", "Done"),
        ]

        first_done = StatusSpec("Done").first(issues)
        assert first_done is not None
        assert first_done.key == "A-2"

    def test_first_not_found(self):
        issues = [
            MockIssue("A-1", "Task 1", "Open"),
        ]

        result = StatusSpec("Done").first(issues)
        assert result is None


# =============================================================================
# Factory Specification Tests
# =============================================================================


class TestPredicateSpec:
    """Test predicate-based specifications."""

    def test_predicate_true(self):
        is_positive = PredicateSpec(lambda x: x > 0, "is_positive")
        assert is_positive.is_satisfied_by(5)

    def test_predicate_false(self):
        is_positive = PredicateSpec(lambda x: x > 0, "is_positive")
        assert not is_positive.is_satisfied_by(-5)

    def test_repr(self):
        spec = PredicateSpec(lambda x: x > 0, "is_positive")
        assert "is_positive" in repr(spec)


# =============================================================================
# Attribute Specification Tests
# =============================================================================


class TestHasAttribute:
    """Test HasAttribute specification."""

    def test_matches(self):
        issue = MockIssue("A-1", "Task", "Done")
        spec = HasAttribute("status", "Done")
        assert spec.is_satisfied_by(issue)

    def test_no_match(self):
        issue = MockIssue("A-1", "Task", "Open")
        spec = HasAttribute("status", "Done")
        assert not spec.is_satisfied_by(issue)

    def test_missing_attribute(self):
        issue = MockIssue("A-1", "Task", "Done")
        spec = HasAttribute("priority", "High")
        assert not spec.is_satisfied_by(issue)


class TestAttributeIn:
    """Test AttributeIn specification."""

    def test_in_set(self):
        issue = MockIssue("A-1", "Task", "Done")
        spec = AttributeIn("status", ["Done", "Closed", "Resolved"])
        assert spec.is_satisfied_by(issue)

    def test_not_in_set(self):
        issue = MockIssue("A-1", "Task", "Open")
        spec = AttributeIn("status", ["Done", "Closed", "Resolved"])
        assert not spec.is_satisfied_by(issue)


class TestAttributeMatches:
    """Test AttributeMatches specification."""

    def test_regex_match(self):
        issue = MockIssue("PROJ-123", "Task", "Done")
        spec = AttributeMatches("key", r"PROJ-\d+")
        assert spec.is_satisfied_by(issue)

    def test_regex_no_match(self):
        issue = MockIssue("OTHER-123", "Task", "Done")
        spec = AttributeMatches("key", r"PROJ-\d+")
        assert not spec.is_satisfied_by(issue)

    def test_case_insensitive(self):
        issue = MockIssue("proj-123", "Task", "Done")
        spec = AttributeMatches("key", r"PROJ-\d+")
        assert spec.is_satisfied_by(issue)


class TestAttributeContains:
    """Test AttributeContains specification."""

    def test_contains(self):
        issue = MockIssue("A-1", "Authentication Task", "Done")
        spec = AttributeContains("title", "auth")
        assert spec.is_satisfied_by(issue)

    def test_not_contains(self):
        issue = MockIssue("A-1", "Database Task", "Done")
        spec = AttributeContains("title", "auth")
        assert not spec.is_satisfied_by(issue)

    def test_case_sensitive(self):
        issue = MockIssue("A-1", "Authentication Task", "Done")
        spec = AttributeContains("title", "AUTH", case_sensitive=True)
        assert not spec.is_satisfied_by(issue)


# =============================================================================
# Issue/Story Specification Tests
# =============================================================================


class TestStatusSpec:
    """Test StatusSpec."""

    def test_single_status(self):
        issue = MockIssue("A-1", "Task", "Done")
        assert StatusSpec("Done").is_satisfied_by(issue)
        assert not StatusSpec("Open").is_satisfied_by(issue)

    def test_multiple_statuses(self):
        spec = StatusSpec("Done", "Closed", "Resolved")

        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "Done"))
        assert spec.is_satisfied_by(MockIssue("A-2", "Task", "Closed"))
        assert not spec.is_satisfied_by(MockIssue("A-3", "Task", "Open"))

    def test_case_insensitive(self):
        spec = StatusSpec("Done")
        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "DONE"))
        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "done"))


class TestIssueTypeSpec:
    """Test IssueTypeSpec."""

    def test_single_type(self):
        issue = MockIssue("A-1", "Task", "Open", issue_type="Bug")
        assert IssueTypeSpec("Bug").is_satisfied_by(issue)
        assert not IssueTypeSpec("Story").is_satisfied_by(issue)

    def test_multiple_types(self):
        spec = IssueTypeSpec("Story", "User Story")
        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "Open", issue_type="Story"))
        assert spec.is_satisfied_by(MockIssue("A-2", "Task", "Open", issue_type="User Story"))


class TestHasSubtasksSpec:
    """Test HasSubtasksSpec."""

    def test_has_subtasks(self):
        issue = MockIssue(
            "A-1",
            "Task",
            "Open",
            subtasks=[
                MockSubtask("A-1-1", "Subtask 1", "Open"),
            ],
        )
        assert HasSubtasksSpec().is_satisfied_by(issue)

    def test_no_subtasks(self):
        issue = MockIssue("A-1", "Task", "Open", subtasks=[])
        assert not HasSubtasksSpec().is_satisfied_by(issue)

    def test_none_subtasks(self):
        issue = MockIssue("A-1", "Task", "Open", subtasks=None)
        assert not HasSubtasksSpec().is_satisfied_by(issue)


class TestSubtaskSpecs:
    """Test AllSubtasksMatchSpec and AnySubtaskMatchesSpec."""

    def test_all_subtasks_match(self):
        issue = MockIssue(
            "A-1",
            "Task",
            "Open",
            subtasks=[
                MockSubtask("A-1-1", "Sub 1", "Done"),
                MockSubtask("A-1-2", "Sub 2", "Done"),
            ],
        )

        spec = AllSubtasksMatchSpec(StatusSpec("Done"))
        assert spec.is_satisfied_by(issue)

    def test_not_all_subtasks_match(self):
        issue = MockIssue(
            "A-1",
            "Task",
            "Open",
            subtasks=[
                MockSubtask("A-1-1", "Sub 1", "Done"),
                MockSubtask("A-1-2", "Sub 2", "Open"),
            ],
        )

        spec = AllSubtasksMatchSpec(StatusSpec("Done"))
        assert not spec.is_satisfied_by(issue)

    def test_any_subtask_matches(self):
        issue = MockIssue(
            "A-1",
            "Task",
            "Open",
            subtasks=[
                MockSubtask("A-1-1", "Sub 1", "Open"),
                MockSubtask("A-1-2", "Sub 2", "Done"),
            ],
        )

        spec = AnySubtaskMatchesSpec(StatusSpec("Done"))
        assert spec.is_satisfied_by(issue)

    def test_no_subtask_matches(self):
        issue = MockIssue(
            "A-1",
            "Task",
            "Open",
            subtasks=[
                MockSubtask("A-1-1", "Sub 1", "Open"),
                MockSubtask("A-1-2", "Sub 2", "Open"),
            ],
        )

        spec = AnySubtaskMatchesSpec(StatusSpec("Done"))
        assert not spec.is_satisfied_by(issue)


class TestTitleMatchesSpec:
    """Test TitleMatchesSpec."""

    def test_contains_match(self):
        issue = MockIssue("A-1", "User Authentication Feature", "Open")
        spec = TitleMatchesSpec("authentication")
        assert spec.is_satisfied_by(issue)

    def test_exact_match(self):
        issue = MockIssue("A-1", "User Authentication", "Open")
        spec = TitleMatchesSpec("user authentication", exact=True)
        assert spec.is_satisfied_by(issue)

    def test_exact_no_match(self):
        issue = MockIssue("A-1", "User Authentication Feature", "Open")
        spec = TitleMatchesSpec("User Authentication", exact=True)
        assert not spec.is_satisfied_by(issue)

    def test_normalizes_whitespace(self):
        issue = MockIssue("A-1", "  User   Authentication  ", "Open")
        spec = TitleMatchesSpec("user authentication", exact=True)
        assert spec.is_satisfied_by(issue)


class TestHasKeySpec:
    """Test HasKeySpec."""

    def test_matches(self):
        issue = MockIssue("PROJ-123", "Task", "Open")
        assert HasKeySpec("PROJ-123").is_satisfied_by(issue)

    def test_case_insensitive(self):
        issue = MockIssue("PROJ-123", "Task", "Open")
        assert HasKeySpec("proj-123").is_satisfied_by(issue)

    def test_no_match(self):
        issue = MockIssue("PROJ-123", "Task", "Open")
        assert not HasKeySpec("PROJ-456").is_satisfied_by(issue)


class TestKeyPrefixSpec:
    """Test KeyPrefixSpec."""

    def test_matches_prefix(self):
        issue = MockIssue("PROJ-123", "Task", "Open")
        assert KeyPrefixSpec("PROJ").is_satisfied_by(issue)

    def test_no_match(self):
        issue = MockIssue("OTHER-123", "Task", "Open")
        assert not KeyPrefixSpec("PROJ").is_satisfied_by(issue)


class TestHasDescriptionSpec:
    """Test HasDescriptionSpec."""

    def test_has_description(self):
        issue = MockIssue("A-1", "Task", "Open", description="Some description")
        assert HasDescriptionSpec().is_satisfied_by(issue)

    def test_no_description(self):
        issue = MockIssue("A-1", "Task", "Open", description=None)
        assert not HasDescriptionSpec().is_satisfied_by(issue)

    def test_empty_description(self):
        issue = MockIssue("A-1", "Task", "Open", description="   ")
        assert not HasDescriptionSpec().is_satisfied_by(issue)


class TestStoryPointsSpec:
    """Test StoryPointsSpec."""

    def test_min_points(self):
        spec = StoryPointsSpec(min_points=3)

        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "Open", story_points=5))
        assert spec.is_satisfied_by(MockIssue("A-2", "Task", "Open", story_points=3))
        assert not spec.is_satisfied_by(MockIssue("A-3", "Task", "Open", story_points=2))

    def test_max_points(self):
        spec = StoryPointsSpec(max_points=5)

        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "Open", story_points=3))
        assert spec.is_satisfied_by(MockIssue("A-2", "Task", "Open", story_points=5))
        assert not spec.is_satisfied_by(MockIssue("A-3", "Task", "Open", story_points=8))

    def test_range(self):
        spec = StoryPointsSpec(min_points=3, max_points=8)

        assert spec.is_satisfied_by(MockIssue("A-1", "Task", "Open", story_points=5))
        assert not spec.is_satisfied_by(MockIssue("A-2", "Task", "Open", story_points=1))
        assert not spec.is_satisfied_by(MockIssue("A-3", "Task", "Open", story_points=13))

    def test_no_points(self):
        spec = StoryPointsSpec(min_points=1)
        assert not spec.is_satisfied_by(MockIssue("A-1", "Task", "Open", story_points=None))


class TestMatchedSpec:
    """Test MatchedSpec and UnmatchedSpec."""

    def test_matched(self):
        issue = MockIssue("A-1", "Task", "Open", external_key="JIRA-123")
        assert MatchedSpec().is_satisfied_by(issue)
        assert not UnmatchedSpec().is_satisfied_by(issue)

    def test_unmatched(self):
        issue = MockIssue("A-1", "Task", "Open", external_key=None)
        assert UnmatchedSpec().is_satisfied_by(issue)
        assert not MatchedSpec().is_satisfied_by(issue)


# =============================================================================
# Builder Helper Tests
# =============================================================================


class TestBuilderHelpers:
    """Test all_of, any_of, none_of helpers."""

    def test_all_of(self):
        issue = MockIssue("A-1", "Auth Task", "Done", description="Details")

        spec = all_of(
            StatusSpec("Done"),
            HasDescriptionSpec(),
            TitleMatchesSpec("auth"),
        )

        assert spec.is_satisfied_by(issue)

    def test_all_of_one_fails(self):
        issue = MockIssue("A-1", "Auth Task", "Open", description="Details")

        spec = all_of(
            StatusSpec("Done"),
            HasDescriptionSpec(),
        )

        assert not spec.is_satisfied_by(issue)

    def test_any_of(self):
        issue = MockIssue("A-1", "Task", "Blocked")

        spec = any_of(
            StatusSpec("Blocked"),
            StatusSpec("On Hold"),
            StatusSpec("Cancelled"),
        )

        assert spec.is_satisfied_by(issue)

    def test_any_of_none_match(self):
        issue = MockIssue("A-1", "Task", "Open")

        spec = any_of(
            StatusSpec("Blocked"),
            StatusSpec("On Hold"),
        )

        assert not spec.is_satisfied_by(issue)

    def test_none_of(self):
        issue = MockIssue("A-1", "Task", "Open")

        spec = none_of(
            StatusSpec("Blocked"),
            StatusSpec("Cancelled"),
        )

        assert spec.is_satisfied_by(issue)

    def test_none_of_one_matches(self):
        issue = MockIssue("A-1", "Task", "Blocked")

        spec = none_of(
            StatusSpec("Blocked"),
            StatusSpec("Cancelled"),
        )

        assert not spec.is_satisfied_by(issue)

    def test_empty_all_of(self):
        spec = all_of()
        assert spec.is_satisfied_by(None)

    def test_empty_any_of(self):
        spec = any_of()
        assert not spec.is_satisfied_by(None)


# =============================================================================
# Realistic Example Tests
# =============================================================================


class TestRealisticExamples:
    """Test realistic use cases."""

    def test_ready_for_release_spec(self):
        """Issues ready for release: Done, has description, all subtasks done."""

        ready_for_release = all_of(
            StatusSpec("Done"),
            HasDescriptionSpec(),
            AllSubtasksMatchSpec(StatusSpec("Done")),
        )

        # Ready issue
        ready_issue = MockIssue(
            "A-1",
            "Feature",
            "Done",
            description="Complete feature",
            subtasks=[
                MockSubtask("A-1-1", "Sub 1", "Done"),
                MockSubtask("A-1-2", "Sub 2", "Done"),
            ],
        )
        assert ready_for_release.is_satisfied_by(ready_issue)

        # Not ready - subtask incomplete
        not_ready = MockIssue(
            "A-2",
            "Feature",
            "Done",
            description="Complete feature",
            subtasks=[
                MockSubtask("A-2-1", "Sub 1", "Done"),
                MockSubtask("A-2-2", "Sub 2", "Open"),
            ],
        )
        assert not ready_for_release.is_satisfied_by(not_ready)

    def test_needs_attention_spec(self):
        """Issues needing attention: Open bugs or blocked stories."""

        needs_attention = (IssueTypeSpec("Bug") & ~StatusSpec("Done", "Closed")) | (
            IssueTypeSpec("Story") & StatusSpec("Blocked")
        )

        open_bug = MockIssue("A-1", "Bug", "Open", issue_type="Bug")
        assert needs_attention.is_satisfied_by(open_bug)

        blocked_story = MockIssue("A-2", "Story", "Blocked", issue_type="Story")
        assert needs_attention.is_satisfied_by(blocked_story)

        closed_bug = MockIssue("A-3", "Bug", "Closed", issue_type="Bug")
        assert not needs_attention.is_satisfied_by(closed_bug)

        open_story = MockIssue("A-4", "Story", "Open", issue_type="Story")
        assert not needs_attention.is_satisfied_by(open_story)

    def test_filter_and_count(self):
        """Filter issues and count by category."""

        issues = [
            MockIssue("A-1", "Task 1", "Done"),
            MockIssue("A-2", "Task 2", "Open"),
            MockIssue("A-3", "Task 3", "Done"),
            MockIssue("A-4", "Task 4", "In Progress"),
            MockIssue("A-5", "Task 5", "Done"),
        ]

        done_spec = StatusSpec("Done")
        in_progress_spec = StatusSpec("In Progress", "Open")

        done_issues = done_spec.filter(issues)
        assert len(done_issues) == 3

        active_count = in_progress_spec.count(issues)
        assert active_count == 2
