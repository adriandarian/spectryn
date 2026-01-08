"""Tests for AI Story Refiner module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_refine import (
    AIStoryRefiner,
    IssueCategory,
    IssueSeverity,
    QualityIssue,
    RefinementOptions,
    RefinementResult,
    StoryAnalysis,
    build_refinement_prompt,
    parse_refinement_response,
)
from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def sample_story() -> UserStory:
    """Create a sample user story for testing."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login",
        description=Description(
            role="registered user",
            want="to log in with my credentials",
            benefit="I can access my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(["Can enter email", "Can enter password"]),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
    )


@pytest.fixture
def incomplete_story() -> UserStory:
    """Create an incomplete story for testing."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="Feature X",
        description=None,
        acceptance_criteria=AcceptanceCriteria.from_list([]),
        story_points=21,  # Very high - should be flagged
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
    )


class TestRefinementOptions:
    """Tests for RefinementOptions configuration."""

    def test_default_options(self) -> None:
        """Test default refinement options."""
        options = RefinementOptions()

        assert options.check_ambiguity is True
        assert options.check_acceptance_criteria is True
        assert options.check_testability is True
        assert options.check_scope is True
        assert options.check_estimation is True
        assert options.generate_missing_ac is True
        assert options.min_acceptance_criteria == 2
        assert options.max_story_points == 13

    def test_custom_options(self) -> None:
        """Test custom refinement options."""
        options = RefinementOptions(
            check_ambiguity=False,
            min_acceptance_criteria=3,
            max_story_points=8,
            project_context="E-commerce platform",
        )

        assert options.check_ambiguity is False
        assert options.min_acceptance_criteria == 3
        assert options.max_story_points == 8
        assert options.project_context == "E-commerce platform"


class TestBuildRefinementPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, sample_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = RefinementOptions()
        prompt = build_refinement_prompt([sample_story], options)

        assert "US-001" in prompt
        assert "User Login" in prompt
        assert "registered user" in prompt
        assert "Check for ambiguous language" in prompt

    def test_prompt_with_context(self, sample_story: UserStory) -> None:
        """Test prompt with project context."""
        options = RefinementOptions(
            project_context="Mobile banking app",
            tech_stack="React Native, Node.js",
        )
        prompt = build_refinement_prompt([sample_story], options)

        assert "Mobile banking app" in prompt
        assert "React Native, Node.js" in prompt

    def test_prompt_with_incomplete_story(self, incomplete_story: UserStory) -> None:
        """Test prompt with incomplete story."""
        options = RefinementOptions()
        prompt = build_refinement_prompt([incomplete_story], options)

        assert "US-002" in prompt
        assert "(No description provided)" in prompt
        assert "(No acceptance criteria)" in prompt


class TestParseRefinementResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, sample_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "analyses": [
                    {
                        "story_id": "US-001",
                        "quality_score": 85,
                        "issues": [
                            {
                                "severity": "warning",
                                "category": "acceptance_criteria",
                                "message": "Could use more specific AC",
                                "suggestion": "Add error handling criteria",
                            }
                        ],
                        "suggested_acceptance_criteria": [
                            "Shows error on invalid credentials",
                            "Redirects to dashboard on success",
                        ],
                        "estimated_effort_accuracy": "appropriate",
                        "suggested_improvements": ["Add rate limiting"],
                    }
                ]
            }
        )

        analyses = parse_refinement_response(response, [sample_story])

        assert len(analyses) == 1
        analysis = analyses[0]
        assert analysis.story_id == "US-001"
        assert analysis.quality_score == 85
        assert len(analysis.issues) == 1
        assert analysis.issues[0].severity == IssueSeverity.WARNING
        assert analysis.issues[0].category == IssueCategory.ACCEPTANCE_CRITERIA
        assert len(analysis.suggested_acceptance_criteria) == 2
        assert analysis.estimated_effort_accuracy == "appropriate"

    def test_parse_json_in_code_block(self, sample_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here's the analysis:

```json
{
  "analyses": [
    {
      "story_id": "US-001",
      "quality_score": 90,
      "issues": [],
      "suggested_acceptance_criteria": [],
      "estimated_effort_accuracy": "appropriate"
    }
  ]
}
```

The story looks good!"""

        analyses = parse_refinement_response(response, [sample_story])

        assert len(analyses) == 1
        assert analyses[0].quality_score == 90
        assert len(analyses[0].issues) == 0

    def test_parse_critical_issues(self, sample_story: UserStory) -> None:
        """Test parsing critical issues."""
        response = json.dumps(
            {
                "analyses": [
                    {
                        "story_id": "US-001",
                        "quality_score": 40,
                        "issues": [
                            {
                                "severity": "critical",
                                "category": "ambiguity",
                                "message": "Story is very ambiguous",
                                "suggestion": "Clarify requirements",
                            },
                            {
                                "severity": "critical",
                                "category": "scope",
                                "message": "Story is too large",
                                "suggestion": "Split into smaller stories",
                            },
                        ],
                    }
                ]
            }
        )

        analyses = parse_refinement_response(response, [sample_story])

        assert len(analyses) == 1
        assert analyses[0].critical_count == 2
        assert not analyses[0].is_ready

    def test_fallback_on_invalid_json(self, incomplete_story: UserStory) -> None:
        """Test fallback analysis when JSON parsing fails."""
        response = "This is not valid JSON at all"

        analyses = parse_refinement_response(response, [incomplete_story])

        # Should create fallback analyses
        assert len(analyses) == 1
        # Fallback should detect missing description and AC
        assert any(i.category == IssueCategory.DESCRIPTION for i in analyses[0].issues)
        assert any(i.category == IssueCategory.ACCEPTANCE_CRITERIA for i in analyses[0].issues)


class TestStoryAnalysis:
    """Tests for StoryAnalysis dataclass."""

    def test_is_ready_no_critical(self) -> None:
        """Test is_ready when no critical issues."""
        analysis = StoryAnalysis(
            story_id="US-001",
            story_title="Test",
            issues=[
                QualityIssue(
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.AMBIGUITY,
                    message="Minor issue",
                    suggestion="Fix it",
                )
            ],
        )

        assert analysis.is_ready is True
        assert analysis.critical_count == 0
        assert analysis.warning_count == 1

    def test_is_ready_with_critical(self) -> None:
        """Test is_ready when has critical issues."""
        analysis = StoryAnalysis(
            story_id="US-001",
            story_title="Test",
            issues=[
                QualityIssue(
                    severity=IssueSeverity.CRITICAL,
                    category=IssueCategory.ACCEPTANCE_CRITERIA,
                    message="No AC",
                    suggestion="Add AC",
                )
            ],
        )

        assert analysis.is_ready is False
        assert analysis.critical_count == 1


class TestQualityIssue:
    """Tests for QualityIssue dataclass."""

    def test_issue_creation(self) -> None:
        """Test creating a quality issue."""
        issue = QualityIssue(
            severity=IssueSeverity.WARNING,
            category=IssueCategory.AMBIGUITY,
            message="Term 'fast' is ambiguous",
            suggestion="Define specific performance requirement",
            original_text="should be fast",
            suggested_text="should respond within 200ms",
        )

        assert issue.severity == IssueSeverity.WARNING
        assert issue.category == IssueCategory.AMBIGUITY
        assert issue.original_text == "should be fast"
        assert issue.suggested_text == "should respond within 200ms"


class TestRefinementResult:
    """Tests for RefinementResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = RefinementResult()
        assert result.success is True
        assert result.analyses == []
        assert result.error is None

    def test_stories_ready_count(self) -> None:
        """Test stories_ready count."""
        result = RefinementResult(
            analyses=[
                StoryAnalysis(story_id="US-001", story_title="Ready", issues=[]),
                StoryAnalysis(
                    story_id="US-002",
                    story_title="Not Ready",
                    issues=[
                        QualityIssue(
                            severity=IssueSeverity.CRITICAL,
                            category=IssueCategory.SCOPE,
                            message="Too big",
                            suggestion="Split",
                        )
                    ],
                ),
            ]
        )

        assert result.stories_ready == 1
        assert result.stories_need_work == 1


class TestAIStoryRefiner:
    """Tests for AIStoryRefiner class."""

    def test_refine_empty_stories(self) -> None:
        """Test refining empty story list."""
        refiner = AIStoryRefiner()
        result = refiner.refine([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_refine_with_fallback(self, incomplete_story: UserStory) -> None:
        """Test refining with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            refiner = AIStoryRefiner()
            result = refiner.refine([incomplete_story])

            # Should succeed with fallback analysis
            assert result.success is True
            assert len(result.analyses) == 1
            # Fallback should detect issues
            assert result.analyses[0].critical_count > 0

    def test_refine_with_mocked_llm(self, sample_story: UserStory) -> None:
        """Test successful refinement with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "analyses": [
                    {
                        "story_id": "US-001",
                        "quality_score": 92,
                        "issues": [],
                        "suggested_acceptance_criteria": [],
                        "estimated_effort_accuracy": "appropriate",
                        "suggested_improvements": [],
                    }
                ]
            }
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 300
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            refiner = AIStoryRefiner()
            result = refiner.refine([sample_story])

            assert result.success is True
            assert len(result.analyses) == 1
            assert result.analyses[0].quality_score == 92
            assert result.provider_used == "anthropic"

    def test_refine_llm_not_available(self, sample_story: UserStory) -> None:
        """Test refinement when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = False
            mock_manager.return_value = mock_mgr

            refiner = AIStoryRefiner()
            result = refiner.refine([sample_story])

            # Should use fallback analysis
            assert result.success is True
            assert len(result.analyses) == 1


class TestIssueSeverity:
    """Tests for IssueSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert IssueSeverity.CRITICAL.value == "critical"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.SUGGESTION.value == "suggestion"


class TestIssueCategory:
    """Tests for IssueCategory enum."""

    def test_category_values(self) -> None:
        """Test category enum values."""
        assert IssueCategory.AMBIGUITY.value == "ambiguity"
        assert IssueCategory.ACCEPTANCE_CRITERIA.value == "acceptance_criteria"
        assert IssueCategory.DESCRIPTION.value == "description"
        assert IssueCategory.TESTABILITY.value == "testability"
        assert IssueCategory.SCOPE.value == "scope"
        assert IssueCategory.ESTIMATION.value == "estimation"
