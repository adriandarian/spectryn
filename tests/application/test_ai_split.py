"""Tests for AI Smart Splitting module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_split import (
    AIStorySplitter,
    SplitOptions,
    SplitReason,
    SplitResult,
    SplitStory,
    SplitSuggestion,
    build_splitting_prompt,
    parse_splitting_response,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def large_story() -> UserStory:
    """Create a large story that should be split."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="Complete User Management System",
        description=Description(
            role="admin",
            want="to manage all user accounts including creation, updating, deletion, and role assignments",
            benefit="I can control system access",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can create new user accounts",
                "Can update user profiles",
                "Can delete user accounts",
                "Can assign roles to users",
                "Can view user activity logs",
                "Can bulk import users",
                "Can export user data",
                "Can reset user passwords",
                "Can enable/disable accounts",
                "Can configure 2FA settings",
            ]
        ),
        story_points=13,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["backend", "admin"],
    )


@pytest.fixture
def small_story() -> UserStory:
    """Create a small story that doesn't need splitting."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="Add Password Reset",
        description=Description(
            role="user",
            want="to reset my password via email",
            benefit="I can regain access to my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can request password reset",
                "Receives email with reset link",
                "Can set new password",
            ]
        ),
        story_points=3,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=["auth"],
    )


class TestSplitOptions:
    """Tests for SplitOptions configuration."""

    def test_default_options(self) -> None:
        """Test default splitting options."""
        options = SplitOptions()

        assert options.max_story_points == 8
        assert options.max_acceptance_criteria == 8
        assert options.min_split_points == 1
        assert options.prefer_vertical_slices is True
        assert options.prefer_mvp_first is True
        assert options.maintain_independence is True
        assert options.id_suffix_style == "letter"

    def test_custom_options(self) -> None:
        """Test custom splitting options."""
        options = SplitOptions(
            max_story_points=5,
            max_acceptance_criteria=6,
            prefer_vertical_slices=False,
            id_suffix_style="number",
        )

        assert options.max_story_points == 5
        assert options.max_acceptance_criteria == 6
        assert options.prefer_vertical_slices is False
        assert options.id_suffix_style == "number"


class TestSplitReason:
    """Tests for SplitReason enum."""

    def test_reason_values(self) -> None:
        """Test split reason enum values."""
        assert SplitReason.TOO_LARGE.value == "too_large"
        assert SplitReason.TOO_MANY_AC.value == "too_many_ac"
        assert SplitReason.MULTIPLE_FEATURES.value == "multiple_features"
        assert SplitReason.TECH_COMPLEXITY.value == "tech_complexity"


class TestSplitStory:
    """Tests for SplitStory dataclass."""

    def test_split_story_creation(self) -> None:
        """Test creating a split story."""
        split = SplitStory(
            title="User Creation API",
            description=Description(
                role="admin",
                want="API to create users",
                benefit="users can be created programmatically",
            ),
            acceptance_criteria=["Returns 201 on success", "Validates email format"],
            suggested_points=5,
            rationale="Backend work can be delivered independently",
            inherited_labels=["backend", "api"],
        )

        assert split.title == "User Creation API"
        assert split.suggested_points == 5
        assert len(split.acceptance_criteria) == 2
        assert "backend" in split.inherited_labels

    def test_to_user_story(self) -> None:
        """Test converting SplitStory to UserStory."""
        split = SplitStory(
            title="User Creation API",
            description=Description(
                role="admin",
                want="API to create users",
                benefit="automated user management",
            ),
            acceptance_criteria=["Returns 201 on success"],
            suggested_points=5,
            inherited_labels=["backend"],
        )

        story = split.to_user_story("US-001a")
        assert str(story.id) == "US-001A"
        assert story.title == "User Creation API"
        assert story.story_points == 5
        assert "backend" in story.labels


class TestSplitSuggestion:
    """Tests for SplitSuggestion dataclass."""

    def test_num_splits(self) -> None:
        """Test num_splits property."""
        suggestion = SplitSuggestion(
            original_story_id="US-001",
            original_title="Large Story",
            original_points=13,
            should_split=True,
            suggested_stories=[
                SplitStory(title="Split 1", suggested_points=5),
                SplitStory(title="Split 2", suggested_points=5),
                SplitStory(title="Split 3", suggested_points=3),
            ],
            total_suggested_points=13,
        )

        assert suggestion.num_splits == 3

    def test_point_change(self) -> None:
        """Test point_change property."""
        suggestion = SplitSuggestion(
            original_story_id="US-001",
            original_title="Large Story",
            original_points=13,
            should_split=True,
            total_suggested_points=15,
        )

        assert suggestion.point_change == 2


class TestSplitResult:
    """Tests for SplitResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = SplitResult()
        assert result.success is True
        assert result.suggestions == []
        assert result.stories_to_split == 0

    def test_stories_ok(self) -> None:
        """Test stories_ok count."""
        result = SplitResult(
            suggestions=[
                SplitSuggestion(
                    original_story_id="US-001",
                    original_title="Large",
                    original_points=13,
                    should_split=True,
                ),
                SplitSuggestion(
                    original_story_id="US-002",
                    original_title="Small",
                    original_points=3,
                    should_split=False,
                ),
            ]
        )

        assert result.stories_ok == 1


class TestBuildSplittingPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, large_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = SplitOptions()
        prompt = build_splitting_prompt([large_story], options)

        assert "US-001" in prompt
        assert "Complete User Management System" in prompt
        assert "13" in prompt  # Story points
        assert "8" in prompt  # Max threshold

    def test_prompt_with_context(self, large_story: UserStory) -> None:
        """Test prompt with project context."""
        options = SplitOptions(
            project_context="HR Management System",
            tech_stack="Django, PostgreSQL",
        )
        prompt = build_splitting_prompt([large_story], options)

        assert "HR Management System" in prompt
        assert "Django, PostgreSQL" in prompt

    def test_prompt_includes_ac(self, large_story: UserStory) -> None:
        """Test that prompt includes acceptance criteria."""
        options = SplitOptions()
        prompt = build_splitting_prompt([large_story], options)

        assert "create new user accounts" in prompt
        assert "delete user accounts" in prompt


class TestParseSplittingResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, large_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "original_story_id": "US-001",
                        "original_title": "Complete User Management System",
                        "original_points": 13,
                        "should_split": True,
                        "split_reasons": ["too_large", "multiple_features"],
                        "confidence": "high",
                        "explanation": "Story contains multiple distinct features",
                        "suggested_stories": [
                            {
                                "title": "User CRUD Operations",
                                "description": {
                                    "role": "admin",
                                    "want": "basic CRUD for users",
                                    "benefit": "manage users",
                                },
                                "acceptance_criteria": [
                                    "Create users",
                                    "Update users",
                                    "Delete users",
                                ],
                                "suggested_points": 5,
                                "rationale": "Core functionality",
                                "inherited_labels": ["backend"],
                            },
                            {
                                "title": "User Role Management",
                                "acceptance_criteria": ["Assign roles", "Remove roles"],
                                "suggested_points": 5,
                                "rationale": "Role-specific work",
                            },
                        ],
                        "total_suggested_points": 10,
                    }
                ]
            }
        )

        options = SplitOptions()
        suggestions = parse_splitting_response(response, [large_story], options)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.original_story_id == "US-001"
        assert s.should_split is True
        assert SplitReason.TOO_LARGE in s.split_reasons
        assert len(s.suggested_stories) == 2
        assert s.suggested_stories[0].title == "User CRUD Operations"
        assert s.suggested_stories[0].suggested_points == 5

    def test_parse_json_in_code_block(self, large_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are my suggestions:

```json
{
  "suggestions": [
    {
      "original_story_id": "US-001",
      "original_title": "Large Story",
      "original_points": 13,
      "should_split": true,
      "split_reasons": ["too_large"],
      "confidence": "high",
      "explanation": "Too many points",
      "suggested_stories": [
        {
          "title": "Part 1",
          "acceptance_criteria": ["AC 1"],
          "suggested_points": 5
        }
      ],
      "total_suggested_points": 5
    }
  ]
}
```
"""

        options = SplitOptions()
        suggestions = parse_splitting_response(response, [large_story], options)

        assert len(suggestions) == 1
        assert suggestions[0].should_split is True

    def test_parse_no_split_needed(self, small_story: UserStory) -> None:
        """Test parsing when no split is needed."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "original_story_id": "US-002",
                        "original_title": "Add Password Reset",
                        "original_points": 3,
                        "should_split": False,
                        "split_reasons": [],
                        "confidence": "high",
                        "explanation": "Story is appropriately sized",
                        "suggested_stories": [],
                        "total_suggested_points": 3,
                    }
                ]
            }
        )

        options = SplitOptions()
        suggestions = parse_splitting_response(response, [small_story], options)

        assert len(suggestions) == 1
        assert suggestions[0].should_split is False
        assert len(suggestions[0].suggested_stories) == 0

    def test_fallback_on_invalid_json(self, large_story: UserStory) -> None:
        """Test fallback when JSON parsing fails."""
        response = "This is not valid JSON"

        options = SplitOptions(max_story_points=8)
        suggestions = parse_splitting_response(response, [large_story], options)

        # Should create fallback suggestions based on thresholds
        assert len(suggestions) == 1
        # Large story with 13 points should be flagged for splitting
        assert suggestions[0].should_split is True
        assert SplitReason.TOO_LARGE in suggestions[0].split_reasons


class TestAIStorySplitter:
    """Tests for AIStorySplitter class."""

    def test_analyze_empty_stories(self) -> None:
        """Test analyzing empty story list."""
        splitter = AIStorySplitter()
        result = splitter.analyze([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_analyze_with_fallback(self, large_story: UserStory) -> None:
        """Test analyzing with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            splitter = AIStorySplitter()
            result = splitter.analyze([large_story])

            # Should succeed with fallback analysis
            assert result.success is True
            assert len(result.suggestions) == 1
            # Large story should be flagged
            assert result.suggestions[0].should_split is True

    def test_analyze_with_mocked_llm(self, large_story: UserStory) -> None:
        """Test successful analysis with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "suggestions": [
                    {
                        "original_story_id": "US-001",
                        "original_title": "Large Story",
                        "original_points": 13,
                        "should_split": True,
                        "split_reasons": ["too_large"],
                        "confidence": "high",
                        "explanation": "Story is too large",
                        "suggested_stories": [
                            {
                                "title": "Part 1",
                                "acceptance_criteria": ["AC 1"],
                                "suggested_points": 5,
                            },
                            {
                                "title": "Part 2",
                                "acceptance_criteria": ["AC 2"],
                                "suggested_points": 5,
                            },
                        ],
                        "total_suggested_points": 10,
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

            splitter = AIStorySplitter()
            result = splitter.analyze([large_story])

            assert result.success is True
            assert result.stories_to_split == 1
            assert result.total_new_stories == 2
            assert result.provider_used == "anthropic"

    def test_generate_split_ids_letter(self) -> None:
        """Test generating split IDs with letter suffix."""
        splitter = AIStorySplitter()
        ids = splitter.generate_split_ids("US-001", 3)

        assert ids == ["US-001a", "US-001b", "US-001c"]

    def test_generate_split_ids_number(self) -> None:
        """Test generating split IDs with number suffix."""
        options = SplitOptions(id_suffix_style="number")
        splitter = AIStorySplitter(options)
        ids = splitter.generate_split_ids("US-001", 3, options)

        assert ids == ["US-001.1", "US-001.2", "US-001.3"]

    def test_small_story_not_split(self, small_story: UserStory) -> None:
        """Test that small stories are not flagged for splitting."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            splitter = AIStorySplitter()
            result = splitter.analyze([small_story])

            assert result.success is True
            assert result.stories_to_split == 0
            assert result.suggestions[0].should_split is False
