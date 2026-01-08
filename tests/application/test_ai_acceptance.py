"""Tests for AI Acceptance Criteria Generation module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_acceptance import (
    ACCategory,
    ACGenerationOptions,
    ACGenerationResult,
    ACGenerationSuggestion,
    ACStyle,
    AIAcceptanceCriteriaGenerator,
    GeneratedAC,
    build_ac_generation_prompt,
    parse_ac_generation_response,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


@pytest.fixture
def story_without_ac() -> UserStory:
    """Create a story without acceptance criteria."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="User Login",
        description=Description(
            role="registered user",
            want="to log in with my email and password",
            benefit="I can access my account",
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth", "frontend"],
    )


@pytest.fixture
def story_with_ac() -> UserStory:
    """Create a story with existing acceptance criteria."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="Password Reset",
        description=Description(
            role="user who forgot password",
            want="to reset my password via email",
            benefit="I can regain access to my account",
        ),
        acceptance_criteria=AcceptanceCriteria.from_list(
            [
                "Can request password reset from login page",
                "Receives email with reset link",
            ]
        ),
        story_points=3,
        priority=Priority.MEDIUM,
        status=Status.PLANNED,
        labels=["auth"],
    )


class TestACGenerationOptions:
    """Tests for ACGenerationOptions configuration."""

    def test_default_options(self) -> None:
        """Test default generation options."""
        options = ACGenerationOptions()

        assert options.style == ACStyle.CHECKLIST
        assert options.use_gherkin is False
        assert options.include_validation is True
        assert options.include_error_handling is True
        assert options.include_edge_cases is True
        assert options.include_security is False
        assert options.min_ac_count == 3
        assert options.max_ac_count == 8
        assert options.keep_existing is True

    def test_custom_options(self) -> None:
        """Test custom generation options."""
        options = ACGenerationOptions(
            use_gherkin=True,
            include_security=True,
            min_ac_count=5,
            max_ac_count=10,
        )

        assert options.use_gherkin is True
        assert options.include_security is True
        assert options.min_ac_count == 5
        assert options.max_ac_count == 10


class TestACStyle:
    """Tests for ACStyle enum."""

    def test_style_values(self) -> None:
        """Test AC style enum values."""
        assert ACStyle.GIVEN_WHEN_THEN.value == "gherkin"
        assert ACStyle.CHECKLIST.value == "checklist"
        assert ACStyle.NUMBERED.value == "numbered"
        assert ACStyle.BULLET.value == "bullet"


class TestACCategory:
    """Tests for ACCategory enum."""

    def test_category_values(self) -> None:
        """Test AC category enum values."""
        assert ACCategory.FUNCTIONAL.value == "functional"
        assert ACCategory.VALIDATION.value == "validation"
        assert ACCategory.ERROR_HANDLING.value == "error_handling"
        assert ACCategory.EDGE_CASE.value == "edge_case"
        assert ACCategory.SECURITY.value == "security"


class TestGeneratedAC:
    """Tests for GeneratedAC dataclass."""

    def test_ac_creation(self) -> None:
        """Test creating a generated AC."""
        ac = GeneratedAC(
            text="User can submit the login form",
            category=ACCategory.FUNCTIONAL,
            is_gherkin=False,
        )

        assert ac.text == "User can submit the login form"
        assert ac.category == ACCategory.FUNCTIONAL
        assert ac.is_gherkin is False

    def test_to_checklist_item(self) -> None:
        """Test converting to checklist item."""
        ac = GeneratedAC(
            text="User can submit the login form",
            category=ACCategory.FUNCTIONAL,
        )

        assert ac.to_checklist_item() == "- [ ] User can submit the login form"

    def test_gherkin_ac(self) -> None:
        """Test Gherkin format AC."""
        ac = GeneratedAC(
            text="User login with valid credentials",
            category=ACCategory.FUNCTIONAL,
            is_gherkin=True,
            given="I am on the login page",
            when="I enter valid credentials and click submit",
            then="I am redirected to the dashboard",
        )

        assert ac.is_gherkin is True
        gherkin = ac.to_gherkin()
        assert "Given I am on the login page" in gherkin
        assert "When I enter valid credentials" in gherkin
        assert "Then I am redirected to the dashboard" in gherkin


class TestACGenerationSuggestion:
    """Tests for ACGenerationSuggestion dataclass."""

    def test_num_generated(self) -> None:
        """Test num_generated property."""
        suggestion = ACGenerationSuggestion(
            story_id="US-001",
            story_title="Login",
            current_ac_count=0,
            generated_ac=[
                GeneratedAC(text="AC 1", category=ACCategory.FUNCTIONAL),
                GeneratedAC(text="AC 2", category=ACCategory.VALIDATION),
                GeneratedAC(text="AC 3", category=ACCategory.ERROR_HANDLING),
            ],
        )

        assert suggestion.num_generated == 3

    def test_get_ac_by_category(self) -> None:
        """Test filtering AC by category."""
        suggestion = ACGenerationSuggestion(
            story_id="US-001",
            story_title="Login",
            current_ac_count=0,
            generated_ac=[
                GeneratedAC(text="AC 1", category=ACCategory.FUNCTIONAL),
                GeneratedAC(text="AC 2", category=ACCategory.VALIDATION),
                GeneratedAC(text="AC 3", category=ACCategory.FUNCTIONAL),
            ],
        )

        functional = suggestion.get_ac_by_category(ACCategory.FUNCTIONAL)
        assert len(functional) == 2


class TestACGenerationResult:
    """Tests for ACGenerationResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = ACGenerationResult()
        assert result.success is True
        assert result.suggestions == []
        assert result.total_ac_generated == 0

    def test_stories_with_new_ac(self) -> None:
        """Test stories_with_new_ac count."""
        result = ACGenerationResult(
            suggestions=[
                ACGenerationSuggestion(
                    story_id="US-001",
                    story_title="With AC",
                    current_ac_count=0,
                    generated_ac=[GeneratedAC(text="AC", category=ACCategory.FUNCTIONAL)],
                ),
                ACGenerationSuggestion(
                    story_id="US-002",
                    story_title="No AC",
                    current_ac_count=2,
                    generated_ac=[],
                ),
            ]
        )

        assert result.stories_with_new_ac == 1


class TestBuildACGenerationPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, story_without_ac: UserStory) -> None:
        """Test basic prompt generation."""
        options = ACGenerationOptions()
        prompt = build_ac_generation_prompt([story_without_ac], options)

        assert "US-001" in prompt
        assert "User Login" in prompt
        assert "log in with my email and password" in prompt
        assert "functional" in prompt.lower()

    def test_prompt_with_gherkin(self, story_without_ac: UserStory) -> None:
        """Test prompt with Gherkin format."""
        options = ACGenerationOptions(use_gherkin=True)
        prompt = build_ac_generation_prompt([story_without_ac], options)

        assert "Gherkin" in prompt or "Given/When/Then" in prompt

    def test_prompt_with_context(self, story_without_ac: UserStory) -> None:
        """Test prompt with project context."""
        options = ACGenerationOptions(
            project_context="E-commerce platform",
            tech_stack="React, Django",
        )
        prompt = build_ac_generation_prompt([story_without_ac], options)

        assert "E-commerce platform" in prompt
        assert "React, Django" in prompt

    def test_prompt_includes_existing_ac(self, story_with_ac: UserStory) -> None:
        """Test that prompt includes existing AC."""
        options = ACGenerationOptions()
        prompt = build_ac_generation_prompt([story_with_ac], options)

        assert "request password reset" in prompt
        assert "reset link" in prompt


class TestParseACGenerationResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, story_without_ac: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "story_title": "User Login",
                        "current_ac_count": 0,
                        "explanation": "Added functional and validation AC",
                        "generated_ac": [
                            {
                                "text": "User can submit login form with email and password",
                                "category": "functional",
                                "is_gherkin": False,
                            },
                            {
                                "text": "Form shows error for invalid email format",
                                "category": "validation",
                                "is_gherkin": False,
                            },
                            {
                                "text": "User sees error for incorrect password",
                                "category": "error_handling",
                                "is_gherkin": False,
                            },
                        ],
                        "has_missing_categories": ["edge_case"],
                    }
                ]
            }
        )

        options = ACGenerationOptions()
        suggestions = parse_ac_generation_response(response, [story_without_ac], options)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.story_id == "US-001"
        assert s.num_generated == 3
        assert s.generated_ac[0].category == ACCategory.FUNCTIONAL
        assert s.generated_ac[1].category == ACCategory.VALIDATION
        assert ACCategory.EDGE_CASE in s.has_missing_categories

    def test_parse_gherkin_response(self, story_without_ac: UserStory) -> None:
        """Test parsing Gherkin format response."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "story_title": "User Login",
                        "current_ac_count": 0,
                        "generated_ac": [
                            {
                                "text": "User login with valid credentials",
                                "category": "functional",
                                "is_gherkin": True,
                                "given": "I am on the login page",
                                "when": "I enter valid email and password",
                                "then": "I am redirected to dashboard",
                            }
                        ],
                    }
                ]
            }
        )

        options = ACGenerationOptions(use_gherkin=True)
        suggestions = parse_ac_generation_response(response, [story_without_ac], options)

        assert len(suggestions) == 1
        ac = suggestions[0].generated_ac[0]
        assert ac.is_gherkin is True
        assert ac.given == "I am on the login page"
        assert ac.when == "I enter valid email and password"
        assert ac.then == "I am redirected to dashboard"

    def test_parse_respects_max_ac(self, story_without_ac: UserStory) -> None:
        """Test that max AC constraint is respected."""
        response = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "story_title": "Login",
                        "current_ac_count": 0,
                        "generated_ac": [
                            {"text": f"AC {i}", "category": "functional", "is_gherkin": False}
                            for i in range(10)
                        ],
                    }
                ]
            }
        )

        options = ACGenerationOptions(max_ac_count=5)
        suggestions = parse_ac_generation_response(response, [story_without_ac], options)

        assert suggestions[0].num_generated == 5

    def test_fallback_on_invalid_json(self, story_without_ac: UserStory) -> None:
        """Test fallback when JSON parsing fails."""
        response = "This is not valid JSON"

        options = ACGenerationOptions()
        suggestions = parse_ac_generation_response(response, [story_without_ac], options)

        # Should create fallback suggestions
        assert len(suggestions) == 1
        assert suggestions[0].num_generated > 0


class TestAIAcceptanceCriteriaGenerator:
    """Tests for AIAcceptanceCriteriaGenerator class."""

    def test_generate_empty_stories(self) -> None:
        """Test generating for empty story list."""
        generator = AIAcceptanceCriteriaGenerator()
        result = generator.generate([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_generate_with_fallback(self, story_without_ac: UserStory) -> None:
        """Test generating with fallback when LLM is not available."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            generator = AIAcceptanceCriteriaGenerator()
            result = generator.generate([story_without_ac])

            # Should succeed with fallback generation
            assert result.success is True
            assert len(result.suggestions) == 1
            assert result.suggestions[0].num_generated > 0

    def test_generate_with_mocked_llm(self, story_without_ac: UserStory) -> None:
        """Test successful generation with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "suggestions": [
                    {
                        "story_id": "US-001",
                        "story_title": "User Login",
                        "current_ac_count": 0,
                        "generated_ac": [
                            {
                                "text": "User can log in",
                                "category": "functional",
                                "is_gherkin": False,
                            },
                            {
                                "text": "Shows error for invalid email",
                                "category": "validation",
                                "is_gherkin": False,
                            },
                        ],
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

            generator = AIAcceptanceCriteriaGenerator()
            result = generator.generate([story_without_ac])

            assert result.success is True
            assert result.total_ac_generated == 2
            assert result.provider_used == "openai"

    def test_generate_with_existing_ac(self, story_with_ac: UserStory) -> None:
        """Test generating for story that already has AC."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            generator = AIAcceptanceCriteriaGenerator()
            result = generator.generate([story_with_ac])

            # Should still generate suggestions
            assert result.success is True
            assert len(result.suggestions) == 1
            # The suggestion should note existing AC count
            assert result.suggestions[0].current_ac_count == 2
