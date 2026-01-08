"""Tests for AI Story Quality Scoring module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_quality import (
    AIQualityScorer,
    DimensionScore,
    QualityDimension,
    QualityLevel,
    QualityOptions,
    QualityResult,
    StoryQualityScore,
    build_quality_prompt,
    parse_quality_response,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def well_written_story() -> UserStory:
    """Create a well-written story for testing."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login with Email",
        description=Description(
            role="registered user",
            want="to log in with my email and password",
            benefit="I can access my personalized dashboard",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "User can enter email and password",
                "Form validates email format",
                "Form shows error for invalid credentials",
                "User is redirected to dashboard on success",
                "Remember me option persists session",
            ]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth", "frontend"],
    )


@pytest.fixture
def poor_story() -> UserStory:
    """Create a poorly written story for testing."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="Fix the thing",
        description=None,
        story_points=0,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=[],
    )


@pytest.fixture
def incomplete_story() -> UserStory:
    """Create an incomplete story for testing."""
    return UserStory(
        id=StoryId.from_string("US-003"),
        title="User Profile",
        description=Description(
            role="user",
            want="profile",
            benefit="manage settings",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can view profile",
            ]
        ),
        story_points=13,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
    )


class TestQualityOptions:
    """Tests for QualityOptions configuration."""

    def test_default_options(self) -> None:
        """Test default quality options."""
        options = QualityOptions()

        assert options.score_invest is True
        assert options.score_clarity is True
        assert options.score_completeness is True
        assert options.score_ac_quality is True
        assert options.min_passing_score == 50

    def test_custom_options(self) -> None:
        """Test custom quality options."""
        options = QualityOptions(
            score_invest=False,
            min_passing_score=70,
            project_context="E-commerce",
        )

        assert options.score_invest is False
        assert options.min_passing_score == 70
        assert options.project_context == "E-commerce"


class TestQualityDimension:
    """Tests for QualityDimension enum."""

    def test_invest_dimensions(self) -> None:
        """Test INVEST dimension values."""
        assert QualityDimension.INDEPENDENT.value == "independent"
        assert QualityDimension.NEGOTIABLE.value == "negotiable"
        assert QualityDimension.VALUABLE.value == "valuable"
        assert QualityDimension.ESTIMABLE.value == "estimable"
        assert QualityDimension.SMALL.value == "small"
        assert QualityDimension.TESTABLE.value == "testable"

    def test_additional_dimensions(self) -> None:
        """Test additional dimension values."""
        assert QualityDimension.CLARITY.value == "clarity"
        assert QualityDimension.COMPLETENESS.value == "completeness"
        assert QualityDimension.AC_QUALITY.value == "ac_quality"


class TestQualityLevel:
    """Tests for QualityLevel enum."""

    def test_level_values(self) -> None:
        """Test quality level enum values."""
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.FAIR.value == "fair"
        assert QualityLevel.POOR.value == "poor"
        assert QualityLevel.NEEDS_WORK.value == "needs_work"


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_score_creation(self) -> None:
        """Test creating a dimension score."""
        score = DimensionScore(
            dimension=QualityDimension.TESTABLE,
            score=85,
            feedback="Good acceptance criteria",
            suggestions=[],
        )

        assert score.dimension == QualityDimension.TESTABLE
        assert score.score == 85
        assert score.level == "good"

    def test_level_property(self) -> None:
        """Test level property for various scores."""
        excellent = DimensionScore(dimension=QualityDimension.CLARITY, score=95, feedback="")
        good = DimensionScore(dimension=QualityDimension.CLARITY, score=75, feedback="")
        fair = DimensionScore(dimension=QualityDimension.CLARITY, score=55, feedback="")
        poor = DimensionScore(dimension=QualityDimension.CLARITY, score=35, feedback="")
        needs_work = DimensionScore(dimension=QualityDimension.CLARITY, score=20, feedback="")

        assert excellent.level == "excellent"
        assert good.level == "good"
        assert fair.level == "fair"
        assert poor.level == "poor"
        assert needs_work.level == "needs_work"


class TestStoryQualityScore:
    """Tests for StoryQualityScore dataclass."""

    def test_is_passing(self) -> None:
        """Test is_passing property."""
        passing = StoryQualityScore(
            story_id="US-001",
            story_title="Good Story",
            overall_score=75,
            overall_level=QualityLevel.GOOD,
        )
        failing = StoryQualityScore(
            story_id="US-002",
            story_title="Poor Story",
            overall_score=35,
            overall_level=QualityLevel.POOR,
        )

        assert passing.is_passing is True
        assert failing.is_passing is False

    def test_lowest_dimension(self) -> None:
        """Test lowest_dimension property."""
        score = StoryQualityScore(
            story_id="US-001",
            story_title="Story",
            overall_score=60,
            overall_level=QualityLevel.FAIR,
            dimension_scores=[
                DimensionScore(dimension=QualityDimension.TESTABLE, score=80, feedback=""),
                DimensionScore(dimension=QualityDimension.CLARITY, score=40, feedback=""),
                DimensionScore(dimension=QualityDimension.SMALL, score=70, feedback=""),
            ],
        )

        lowest = score.lowest_dimension
        assert lowest is not None
        assert lowest.dimension == QualityDimension.CLARITY
        assert lowest.score == 40

    def test_highest_dimension(self) -> None:
        """Test highest_dimension property."""
        score = StoryQualityScore(
            story_id="US-001",
            story_title="Story",
            overall_score=60,
            overall_level=QualityLevel.FAIR,
            dimension_scores=[
                DimensionScore(dimension=QualityDimension.TESTABLE, score=90, feedback=""),
                DimensionScore(dimension=QualityDimension.CLARITY, score=40, feedback=""),
            ],
        )

        highest = score.highest_dimension
        assert highest is not None
        assert highest.dimension == QualityDimension.TESTABLE
        assert highest.score == 90


class TestQualityResult:
    """Tests for QualityResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = QualityResult()
        assert result.success is True
        assert result.scores == []
        assert result.average_score == 0.0

    def test_pass_rate(self) -> None:
        """Test pass_rate property."""
        result = QualityResult(
            scores=[
                StoryQualityScore(
                    story_id="US-001",
                    story_title="Pass",
                    overall_score=75,
                    overall_level=QualityLevel.GOOD,
                ),
                StoryQualityScore(
                    story_id="US-002",
                    story_title="Fail",
                    overall_score=35,
                    overall_level=QualityLevel.POOR,
                ),
                StoryQualityScore(
                    story_id="US-003",
                    story_title="Pass",
                    overall_score=60,
                    overall_level=QualityLevel.FAIR,
                ),
            ],
            passing_count=2,
            failing_count=1,
        )

        assert result.pass_rate == pytest.approx(66.67, rel=0.1)


class TestBuildQualityPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, well_written_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = QualityOptions()
        prompt = build_quality_prompt([well_written_story], options)

        assert "US-001" in prompt
        assert "User Login with Email" in prompt
        assert "5" in prompt  # Story points
        assert "independent" in prompt.lower()
        assert "testable" in prompt.lower()

    def test_prompt_with_context(self, well_written_story: UserStory) -> None:
        """Test prompt with project context."""
        options = QualityOptions(
            project_context="Banking application",
            tech_stack="React, Python",
        )
        prompt = build_quality_prompt([well_written_story], options)

        assert "Banking application" in prompt
        assert "React, Python" in prompt

    def test_prompt_includes_ac(self, well_written_story: UserStory) -> None:
        """Test that prompt includes acceptance criteria."""
        options = QualityOptions()
        prompt = build_quality_prompt([well_written_story], options)

        assert "validates email format" in prompt
        assert "Remember me" in prompt


class TestParseQualityResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, well_written_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "scores": [
                    {
                        "story_id": "US-001",
                        "story_title": "User Login with Email",
                        "overall_score": 85,
                        "overall_level": "good",
                        "invest_score": 82,
                        "dimension_scores": [
                            {
                                "dimension": "testable",
                                "score": 90,
                                "feedback": "Excellent acceptance criteria",
                                "suggestions": [],
                            },
                            {
                                "dimension": "small",
                                "score": 80,
                                "feedback": "Appropriate size",
                                "suggestions": [],
                            },
                        ],
                        "strengths": ["Clear AC", "Good description"],
                        "weaknesses": [],
                        "improvement_suggestions": [],
                    }
                ]
            }
        )

        options = QualityOptions()
        scores = parse_quality_response(response, [well_written_story], options)

        assert len(scores) == 1
        assert scores[0].story_id == "US-001"
        assert scores[0].overall_score == 85
        assert scores[0].overall_level == QualityLevel.GOOD
        assert len(scores[0].dimension_scores) == 2
        assert scores[0].dimension_scores[0].dimension == QualityDimension.TESTABLE

    def test_parse_json_in_code_block(self, well_written_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are the quality scores:

```json
{
  "scores": [
    {
      "story_id": "US-001",
      "story_title": "Login",
      "overall_score": 75,
      "overall_level": "good",
      "dimension_scores": [],
      "strengths": [],
      "weaknesses": []
    }
  ]
}
```
"""

        options = QualityOptions()
        scores = parse_quality_response(response, [well_written_story], options)

        assert len(scores) == 1
        assert scores[0].overall_score == 75

    def test_fallback_on_invalid_json(self, poor_story: UserStory) -> None:
        """Test fallback when JSON parsing fails."""
        response = "This is not valid JSON"

        options = QualityOptions()
        scores = parse_quality_response(response, [poor_story], options)

        # Should create fallback scores
        assert len(scores) == 1
        # Poor story should have low score
        assert scores[0].overall_score < 70


class TestAIQualityScorer:
    """Tests for AIQualityScorer class."""

    def test_score_empty_stories(self) -> None:
        """Test scoring empty story list."""
        scorer = AIQualityScorer()
        result = scorer.score([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_score_with_fallback(self, well_written_story: UserStory) -> None:
        """Test scoring with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            scorer = AIQualityScorer()
            result = scorer.score([well_written_story])

            # Should succeed with fallback scoring
            assert result.success is True
            assert len(result.scores) == 1
            # Well-written story should have decent fallback score
            assert result.scores[0].overall_score > 0

    def test_score_with_mocked_llm(self, well_written_story: UserStory) -> None:
        """Test successful scoring with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "scores": [
                    {
                        "story_id": "US-001",
                        "story_title": "User Login",
                        "overall_score": 88,
                        "overall_level": "good",
                        "invest_score": 85,
                        "dimension_scores": [
                            {
                                "dimension": "testable",
                                "score": 95,
                                "feedback": "Excellent AC",
                                "suggestions": [],
                            }
                        ],
                        "strengths": ["Clear description"],
                        "weaknesses": [],
                        "improvement_suggestions": [],
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
            mock_response.model = "gpt-4"
            mock_response.provider = "openai"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            scorer = AIQualityScorer()
            result = scorer.score([well_written_story])

            assert result.success is True
            assert result.average_score == 88
            assert result.passing_count == 1
            assert result.failing_count == 0
            assert result.provider_used == "openai"

    def test_fallback_poor_story(self, poor_story: UserStory) -> None:
        """Test that poor stories get low fallback scores."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            scorer = AIQualityScorer()
            result = scorer.score([poor_story])

            assert result.success is True
            assert len(result.scores) == 1
            # Poor story (no description, no AC, no points) should score low
            assert result.scores[0].overall_score < 50

    def test_fallback_incomplete_story(self, incomplete_story: UserStory) -> None:
        """Test that incomplete stories get medium fallback scores."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            scorer = AIQualityScorer()
            result = scorer.score([incomplete_story])

            assert result.success is True
            # Incomplete story should score somewhere in the middle
            # It has description and AC but is large (13 points)
            score = result.scores[0].overall_score
            assert 30 <= score <= 70
