"""Tests for AI Labeling module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_label import (
    AILabeler,
    LabelCategory,
    LabelingOptions,
    LabelingResult,
    LabelingSuggestion,
    SuggestedLabel,
    build_labeling_prompt,
    parse_labeling_response,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def sample_story() -> UserStory:
    """Create a sample user story for testing."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login with OAuth",
        description=Description(
            role="registered user",
            want="to log in with my Google account",
            benefit="I don't have to remember another password",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            ["Can click Google login button", "Redirects to Google", "Returns to app after auth"]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["frontend"],
    )


@pytest.fixture
def unlabeled_story() -> UserStory:
    """Create an unlabeled story for testing."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="API Rate Limiting",
        description=Description(
            role="API consumer",
            want="rate limits on API endpoints",
            benefit="the system remains stable under load",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            ["Returns 429 when limit exceeded", "Includes retry-after header"]
        ),
        story_points=3,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=[],
    )


class TestLabelingOptions:
    """Tests for LabelingOptions configuration."""

    def test_default_options(self) -> None:
        """Test default labeling options."""
        options = LabelingOptions()

        assert options.suggest_features is True
        assert options.suggest_components is True
        assert options.suggest_types is True
        assert options.suggest_nfr is True
        assert options.suggest_personas is False
        assert options.max_labels_per_story == 5
        assert options.allow_new_labels is True
        assert options.prefer_existing_labels is True
        assert options.label_style == "kebab-case"

    def test_custom_options(self) -> None:
        """Test custom labeling options."""
        options = LabelingOptions(
            existing_labels=["auth", "api", "frontend"],
            max_labels_per_story=3,
            allow_new_labels=False,
            label_style="snake_case",
        )

        assert options.existing_labels == ["auth", "api", "frontend"]
        assert options.max_labels_per_story == 3
        assert options.allow_new_labels is False
        assert options.label_style == "snake_case"


class TestSuggestedLabel:
    """Tests for SuggestedLabel dataclass."""

    def test_label_creation(self) -> None:
        """Test creating a suggested label."""
        label = SuggestedLabel(
            name="user-auth",
            category=LabelCategory.FEATURE,
            confidence="high",
            reasoning="Story is about user authentication",
            is_new=True,
        )

        assert label.name == "user-auth"
        assert label.category == LabelCategory.FEATURE
        assert label.confidence == "high"
        assert label.is_new is True


class TestLabelingSuggestion:
    """Tests for LabelingSuggestion dataclass."""

    def test_has_changes_true(self) -> None:
        """Test has_changes when there are changes."""
        suggestion = LabelingSuggestion(
            story_id="US-001",
            story_title="Test",
            current_labels=["frontend"],
            labels_to_add=["auth", "security"],
            labels_to_remove=[],
        )

        assert suggestion.has_changes is True

    def test_has_changes_false(self) -> None:
        """Test has_changes when no changes."""
        suggestion = LabelingSuggestion(
            story_id="US-001",
            story_title="Test",
            current_labels=["frontend", "auth"],
            labels_to_add=[],
            labels_to_remove=[],
        )

        assert suggestion.has_changes is False

    def test_final_labels(self) -> None:
        """Test final_labels calculation."""
        suggestion = LabelingSuggestion(
            story_id="US-001",
            story_title="Test",
            current_labels=["frontend", "old-label"],
            labels_to_add=["auth", "security"],
            labels_to_remove=["old-label"],
        )

        assert suggestion.final_labels == ["auth", "frontend", "security"]


class TestBuildLabelingPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, sample_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = LabelingOptions()
        prompt = build_labeling_prompt([sample_story], options)

        assert "US-001" in prompt
        assert "User Login with OAuth" in prompt
        assert "Google account" in prompt
        assert "kebab-case" in prompt.lower()

    def test_prompt_with_existing_labels(self, sample_story: UserStory) -> None:
        """Test prompt with existing labels."""
        options = LabelingOptions(
            existing_labels=["auth", "api", "security", "frontend"],
        )
        prompt = build_labeling_prompt([sample_story], options)

        assert "Existing Labels" in prompt
        assert "auth" in prompt
        assert "api" in prompt

    def test_prompt_with_context(self, sample_story: UserStory) -> None:
        """Test prompt with project context."""
        options = LabelingOptions(
            project_context="Mobile banking app",
            tech_stack="React Native, Node.js",
        )
        prompt = build_labeling_prompt([sample_story], options)

        assert "Mobile banking app" in prompt
        assert "React Native, Node.js" in prompt


class TestParseLabelingResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, sample_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_labels": ["frontend"],
                        "suggested_labels": [
                            {
                                "name": "user-auth",
                                "category": "feature",
                                "confidence": "high",
                                "reasoning": "OAuth authentication flow",
                            },
                            {
                                "name": "security",
                                "category": "nfr",
                                "confidence": "medium",
                                "reasoning": "Authentication implies security",
                            },
                        ],
                        "labels_to_add": ["user-auth", "security"],
                        "labels_to_remove": [],
                    }
                ],
                "new_labels_suggested": ["user-auth"],
            }
        )

        options = LabelingOptions()
        suggestions, new_labels = parse_labeling_response(response, [sample_story], options)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.story_id == "US-001"
        assert len(s.suggested_labels) == 2
        assert s.suggested_labels[0].name == "user-auth"
        assert s.suggested_labels[0].category == LabelCategory.FEATURE
        assert "user-auth" in s.labels_to_add
        assert "user-auth" in new_labels

    def test_parse_json_in_code_block(self, sample_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are the label suggestions:

```json
{
  "suggestions": [
    {
      "story_id": "US-001",
      "current_labels": ["frontend"],
      "suggested_labels": [
        {
          "name": "oauth",
          "category": "feature",
          "confidence": "high",
          "reasoning": "Uses OAuth"
        }
      ],
      "labels_to_add": ["oauth"],
      "labels_to_remove": []
    }
  ],
  "new_labels_suggested": ["oauth"]
}
```
"""

        options = LabelingOptions()
        suggestions, _ = parse_labeling_response(response, [sample_story], options)

        assert len(suggestions) == 1
        assert "oauth" in suggestions[0].labels_to_add

    def test_parse_respects_max_labels(self, sample_story: UserStory) -> None:
        """Test that max_labels constraint is respected."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_labels": [],
                        "suggested_labels": [],
                        "labels_to_add": ["a", "b", "c", "d", "e", "f"],
                        "labels_to_remove": [],
                    }
                ]
            }
        )

        options = LabelingOptions(max_labels_per_story=3)
        suggestions, _ = parse_labeling_response(response, [sample_story], options)

        assert len(suggestions[0].labels_to_add) == 3

    def test_parse_filters_new_labels_when_not_allowed(self, sample_story: UserStory) -> None:
        """Test that new labels are filtered when not allowed."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_labels": [],
                        "suggested_labels": [],
                        "labels_to_add": ["existing-label", "new-label"],
                        "labels_to_remove": [],
                    }
                ]
            }
        )

        options = LabelingOptions(
            existing_labels=["existing-label"],
            allow_new_labels=False,
        )
        suggestions, _ = parse_labeling_response(response, [sample_story], options)

        assert suggestions[0].labels_to_add == ["existing-label"]
        assert "new-label" not in suggestions[0].labels_to_add

    def test_fallback_on_invalid_json(self, sample_story: UserStory) -> None:
        """Test fallback labeling when JSON parsing fails."""
        response = "This is not valid JSON"

        options = LabelingOptions()
        suggestions, _ = parse_labeling_response(response, [sample_story], options)

        # Should create fallback suggestions
        assert len(suggestions) == 1
        # Fallback should detect "login" keyword and suggest "auth"
        labels = [sl.name for sl in suggestions[0].suggested_labels]
        assert "auth" in labels  # "login" in title should map to "auth"


class TestLabelingResult:
    """Tests for LabelingResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = LabelingResult()
        assert result.success is True
        assert result.suggestions == []
        assert result.error is None

    def test_stories_with_changes(self) -> None:
        """Test stories_with_changes count."""
        result = LabelingResult(
            suggestions=[
                LabelingSuggestion(
                    story_id="US-001",
                    story_title="Changed",
                    current_labels=[],
                    labels_to_add=["new-label"],
                ),
                LabelingSuggestion(
                    story_id="US-002",
                    story_title="Unchanged",
                    current_labels=["existing"],
                    labels_to_add=[],
                ),
            ]
        )

        assert result.stories_with_changes == 1


class TestAILabeler:
    """Tests for AILabeler class."""

    def test_label_empty_stories(self) -> None:
        """Test labeling empty story list."""
        labeler = AILabeler()
        result = labeler.label([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_label_with_fallback(self, unlabeled_story: UserStory) -> None:
        """Test labeling with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            labeler = AILabeler()
            result = labeler.label([unlabeled_story])

            # Should succeed with fallback labeling
            assert result.success is True
            assert len(result.suggestions) == 1

    def test_label_with_mocked_llm(self, sample_story: UserStory) -> None:
        """Test successful labeling with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "current_labels": ["frontend"],
                        "suggested_labels": [
                            {
                                "name": "oauth",
                                "category": "feature",
                                "confidence": "high",
                                "reasoning": "Uses Google OAuth",
                            }
                        ],
                        "labels_to_add": ["oauth"],
                        "labels_to_remove": [],
                    }
                ],
                "new_labels_suggested": ["oauth"],
            }
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 200
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            labeler = AILabeler()
            result = labeler.label([sample_story])

            assert result.success is True
            assert len(result.suggestions) == 1
            assert "oauth" in result.suggestions[0].labels_to_add
            assert result.provider_used == "anthropic"

    def test_label_llm_not_available(self, sample_story: UserStory) -> None:
        """Test labeling when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = False
            mock_manager.return_value = mock_mgr

            labeler = AILabeler()
            result = labeler.label([sample_story])

            # Should use fallback labeling
            assert result.success is True
            assert len(result.suggestions) == 1


class TestLabelCategory:
    """Tests for LabelCategory enum."""

    def test_category_values(self) -> None:
        """Test category enum values."""
        assert LabelCategory.FEATURE.value == "feature"
        assert LabelCategory.COMPONENT.value == "component"
        assert LabelCategory.TYPE.value == "type"
        assert LabelCategory.NFR.value == "nfr"
        assert LabelCategory.PERSONA.value == "persona"
        assert LabelCategory.CUSTOM.value == "custom"
