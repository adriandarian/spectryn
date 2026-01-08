"""Tests for AI Estimation module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_estimate import (
    AIEstimator,
    ComplexityBreakdown,
    EstimationOptions,
    EstimationResult,
    EstimationScale,
    EstimationSuggestion,
    build_estimation_prompt,
    parse_estimation_response,
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
        acceptance_criteria=AcceptanceCriteria.from_list(
            ["Can enter email", "Can enter password", "Shows error on invalid login"]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        subtasks=[
            Subtask(name="Create login form", story_points=2),
            Subtask(name="Add validation", story_points=1),
        ],
    )


@pytest.fixture
def simple_story() -> UserStory:
    """Create a simple story for testing."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="Update Button Color",
        description=Description(
            role="user",
            want="a blue submit button",
            benefit="it matches the brand colors",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(["Button is blue"]),
        story_points=1,
        priority=Priority.LOW,
        status=Status.PLANNED,
    )


class TestEstimationOptions:
    """Tests for EstimationOptions configuration."""

    def test_default_options(self) -> None:
        """Test default estimation options."""
        options = EstimationOptions()

        assert options.scale == EstimationScale.FIBONACCI
        assert options.valid_points == [1, 2, 3, 5, 8, 13, 21]
        assert options.consider_technical_complexity is True
        assert options.consider_scope is True
        assert options.consider_uncertainty is True
        assert options.consider_dependencies is True

    def test_custom_options(self) -> None:
        """Test custom estimation options."""
        options = EstimationOptions(
            scale=EstimationScale.LINEAR,
            valid_points=[1, 2, 3, 4, 5, 6, 7, 8],
            project_context="E-commerce platform",
            team_velocity=40,
        )

        assert options.scale == EstimationScale.LINEAR
        assert options.valid_points == [1, 2, 3, 4, 5, 6, 7, 8]
        assert options.project_context == "E-commerce platform"
        assert options.team_velocity == 40


class TestComplexityBreakdown:
    """Tests for ComplexityBreakdown dataclass."""

    def test_default_complexity(self) -> None:
        """Test default complexity values."""
        complexity = ComplexityBreakdown()

        assert complexity.technical == 3
        assert complexity.scope == 3
        assert complexity.uncertainty == 3
        assert complexity.dependencies == 1
        assert complexity.testing == 2
        assert complexity.integration == 2

    def test_average_calculation(self) -> None:
        """Test average complexity calculation."""
        complexity = ComplexityBreakdown(
            technical=4,
            scope=4,
            uncertainty=2,
            dependencies=2,
            testing=3,
            integration=3,
        )

        # (4 + 4 + 2 + 2 + 3 + 3) / 6 = 3.0
        assert complexity.average == 3.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        complexity = ComplexityBreakdown(technical=5, scope=3)
        result = complexity.to_dict()

        assert result["technical"] == 5
        assert result["scope"] == 3
        assert "average" in result


class TestEstimationSuggestion:
    """Tests for EstimationSuggestion dataclass."""

    def test_points_changed_true(self) -> None:
        """Test points_changed when different."""
        suggestion = EstimationSuggestion(
            story_id="US-001",
            story_title="Test",
            current_points=3,
            suggested_points=5,
            confidence="high",
            reasoning="More complex than initially thought",
        )

        assert suggestion.points_changed is True
        assert suggestion.change_direction == "increase"
        assert suggestion.points_difference == 2

    def test_points_changed_false(self) -> None:
        """Test points_changed when same."""
        suggestion = EstimationSuggestion(
            story_id="US-001",
            story_title="Test",
            current_points=5,
            suggested_points=5,
            confidence="high",
            reasoning="Estimate looks correct",
        )

        assert suggestion.points_changed is False
        assert suggestion.change_direction == "same"
        assert suggestion.points_difference == 0

    def test_points_decrease(self) -> None:
        """Test points decrease suggestion."""
        suggestion = EstimationSuggestion(
            story_id="US-001",
            story_title="Test",
            current_points=8,
            suggested_points=5,
            confidence="medium",
            reasoning="Simpler than expected",
        )

        assert suggestion.points_changed is True
        assert suggestion.change_direction == "decrease"
        assert suggestion.points_difference == -3


class TestBuildEstimationPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, sample_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = EstimationOptions()
        prompt = build_estimation_prompt([sample_story], options)

        assert "US-001" in prompt
        assert "User Login" in prompt
        assert "registered user" in prompt
        assert "fibonacci" in prompt.lower()
        assert "[1, 2, 3, 5, 8, 13, 21]" in prompt

    def test_prompt_with_context(self, sample_story: UserStory) -> None:
        """Test prompt with project context."""
        options = EstimationOptions(
            project_context="Mobile banking app",
            tech_stack="React Native, Node.js",
            team_velocity=35,
        )
        prompt = build_estimation_prompt([sample_story], options)

        assert "Mobile banking app" in prompt
        assert "React Native, Node.js" in prompt
        assert "35 points/sprint" in prompt

    def test_prompt_with_reference_stories(self, sample_story: UserStory) -> None:
        """Test prompt with reference stories."""
        options = EstimationOptions(
            reference_stories=[
                ("Simple button change", 1),
                ("API integration", 8),
            ]
        )
        prompt = build_estimation_prompt([sample_story], options)

        assert "Simple button change: 1 points" in prompt
        assert "API integration: 8 points" in prompt


class TestParseEstimationResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, sample_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_points": 5,
                        "suggested_points": 8,
                        "confidence": "high",
                        "reasoning": "Integration complexity is high",
                        "complexity": {
                            "technical": 4,
                            "scope": 3,
                            "uncertainty": 2,
                            "dependencies": 4,
                            "testing": 3,
                            "integration": 5,
                        },
                        "risk_factors": ["External API changes"],
                        "comparison_notes": "Similar to OAuth implementation",
                    }
                ]
            }
        )

        options = EstimationOptions()
        suggestions = parse_estimation_response(response, [sample_story], options)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.story_id == "US-001"
        assert s.suggested_points == 8
        assert s.confidence == "high"
        assert s.complexity.technical == 4
        assert s.complexity.integration == 5
        assert len(s.risk_factors) == 1

    def test_parse_json_in_code_block(self, sample_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are the estimates:

```json
{
  "suggestions": [
    {
      "story_id": "US-001",
      "current_points": 5,
      "suggested_points": 5,
      "confidence": "high",
      "reasoning": "Estimate looks correct"
    }
  ]
}
```
"""

        options = EstimationOptions()
        suggestions = parse_estimation_response(response, [sample_story], options)

        assert len(suggestions) == 1
        assert suggestions[0].suggested_points == 5

    def test_parse_normalizes_to_scale(self, sample_story: UserStory) -> None:
        """Test that points are normalized to the scale."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_points": 5,
                        "suggested_points": 7,  # Not in Fibonacci
                        "confidence": "medium",
                        "reasoning": "Test",
                    }
                ]
            }
        )

        options = EstimationOptions(valid_points=[1, 2, 3, 5, 8, 13])
        suggestions = parse_estimation_response(response, [sample_story], options)

        # 7 should normalize to 8 (closest)
        assert suggestions[0].suggested_points == 8

    def test_fallback_on_invalid_json(self, sample_story: UserStory) -> None:
        """Test fallback estimation when JSON parsing fails."""
        response = "This is not valid JSON"

        options = EstimationOptions()
        suggestions = parse_estimation_response(response, [sample_story], options)

        # Should create fallback estimates
        assert len(suggestions) == 1
        assert suggestions[0].confidence == "low"


class TestEstimationResult:
    """Tests for EstimationResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = EstimationResult()
        assert result.success is True
        assert result.suggestions == []
        assert result.error is None

    def test_stories_changed_count(self) -> None:
        """Test stories_changed count."""
        result = EstimationResult(
            suggestions=[
                EstimationSuggestion(
                    story_id="US-001",
                    story_title="Changed",
                    current_points=3,
                    suggested_points=5,
                    confidence="high",
                    reasoning="Test",
                ),
                EstimationSuggestion(
                    story_id="US-002",
                    story_title="Unchanged",
                    current_points=3,
                    suggested_points=3,
                    confidence="high",
                    reasoning="Test",
                ),
            ],
            total_current_points=6,
            total_suggested_points=8,
        )

        assert result.stories_changed == 1
        assert result.points_difference == 2


class TestAIEstimator:
    """Tests for AIEstimator class."""

    def test_estimate_empty_stories(self) -> None:
        """Test estimating empty story list."""
        estimator = AIEstimator()
        result = estimator.estimate([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_estimate_with_fallback(self, sample_story: UserStory) -> None:
        """Test estimating with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            estimator = AIEstimator()
            result = estimator.estimate([sample_story])

            # Should succeed with fallback estimation
            assert result.success is True
            assert len(result.suggestions) == 1
            assert result.suggestions[0].confidence == "low"

    def test_estimate_with_mocked_llm(self, sample_story: UserStory) -> None:
        """Test successful estimation with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_points": 5,
                        "suggested_points": 8,
                        "confidence": "high",
                        "reasoning": "Complex integration",
                        "complexity": {
                            "technical": 4,
                            "scope": 4,
                            "uncertainty": 2,
                            "dependencies": 3,
                            "testing": 3,
                            "integration": 4,
                        },
                    }
                ]
            }
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 250
            mock_response.model = "gpt-4"
            mock_response.provider = "openai"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            estimator = AIEstimator()
            result = estimator.estimate([sample_story])

            assert result.success is True
            assert len(result.suggestions) == 1
            assert result.suggestions[0].suggested_points == 8
            assert result.provider_used == "openai"

    def test_estimate_llm_not_available(self, sample_story: UserStory) -> None:
        """Test estimation when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = False
            mock_manager.return_value = mock_mgr

            estimator = AIEstimator()
            result = estimator.estimate([sample_story])

            # Should use fallback estimation
            assert result.success is True
            assert len(result.suggestions) == 1


class TestEstimationScale:
    """Tests for EstimationScale enum."""

    def test_scale_values(self) -> None:
        """Test scale enum values."""
        assert EstimationScale.FIBONACCI.value == "fibonacci"
        assert EstimationScale.LINEAR.value == "linear"
        assert EstimationScale.TSHIRT.value == "tshirt"
