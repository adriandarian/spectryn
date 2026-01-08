"""Tests for AI Story Generation module."""

import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.ai_generate import (
    AIStoryGenerator,
    GeneratedStory,
    GenerationOptions,
    GenerationResult,
    GenerationStyle,
    build_generation_prompt,
    convert_to_user_stories,
    parse_generated_stories,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status


class TestGenerationOptions:
    """Tests for GenerationOptions configuration."""

    def test_default_options(self) -> None:
        """Test default generation options."""
        options = GenerationOptions()

        assert options.style == GenerationStyle.STANDARD
        assert options.include_acceptance_criteria is True
        assert options.include_subtasks is True
        assert options.include_technical_notes is False
        assert options.include_story_points is True
        assert options.story_prefix == "US"
        assert options.starting_number == 1
        assert options.max_stories == 10
        assert options.max_subtasks_per_story == 5
        assert options.max_acceptance_criteria == 5
        assert options.fibonacci_points is True

    def test_custom_options(self) -> None:
        """Test custom generation options."""
        options = GenerationOptions(
            style=GenerationStyle.DETAILED,
            story_prefix="STORY",
            max_stories=3,
            project_context="E-commerce platform",
            tech_stack="React, Python, PostgreSQL",
        )

        assert options.style == GenerationStyle.DETAILED
        assert options.story_prefix == "STORY"
        assert options.max_stories == 3
        assert options.project_context == "E-commerce platform"
        assert options.tech_stack == "React, Python, PostgreSQL"


class TestBuildGenerationPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self) -> None:
        """Test basic prompt generation."""
        options = GenerationOptions()
        prompt = build_generation_prompt("Build a user login feature", options)

        assert "Build a user login feature" in prompt
        assert "up to 10 user stories" in prompt
        assert "up to 5 acceptance criteria" in prompt
        assert "Fibonacci" in prompt

    def test_prompt_with_context(self) -> None:
        """Test prompt with project context."""
        options = GenerationOptions(
            project_context="Mobile banking app",
            tech_stack="React Native, Node.js",
            target_audience="Banking customers",
        )
        prompt = build_generation_prompt("Implement transfers", options)

        assert "Mobile banking app" in prompt
        assert "React Native, Node.js" in prompt
        assert "Banking customers" in prompt

    def test_detailed_style_prompt(self) -> None:
        """Test prompt for detailed style."""
        options = GenerationOptions(style=GenerationStyle.DETAILED)
        prompt = build_generation_prompt("Create dashboard", options)

        assert "comprehensive stories" in prompt.lower() or "detailed" in prompt.lower()


class TestParseGeneratedStories:
    """Tests for parsing LLM responses."""

    def test_parse_valid_json_response(self) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "stories": [
                    {
                        "title": "User Login",
                        "description": {
                            "role": "registered user",
                            "want": "to log in with my credentials",
                            "benefit": "I can access my account",
                        },
                        "acceptance_criteria": [
                            "Can enter email",
                            "Can enter password",
                            "Shows error on invalid credentials",
                        ],
                        "subtasks": [
                            {"name": "Create login form", "story_points": 2},
                            {"name": "Add validation", "story_points": 1},
                        ],
                        "story_points": 5,
                        "priority": "high",
                        "labels": ["auth"],
                    }
                ]
            }
        )

        options = GenerationOptions()
        stories = parse_generated_stories(response, options)

        assert len(stories) == 1
        story = stories[0]
        assert story.title == "User Login"
        assert story.description_role == "registered user"
        assert story.description_want == "to log in with my credentials"
        assert story.description_benefit == "I can access my account"
        assert len(story.acceptance_criteria) == 3
        assert len(story.subtasks) == 2
        assert story.story_points == 5
        assert story.priority == "high"

    def test_parse_json_in_code_block(self) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are the generated stories:

```json
{
  "stories": [
    {
      "title": "Password Reset",
      "description": {
        "role": "user",
        "want": "to reset my password",
        "benefit": "I can recover my account"
      },
      "acceptance_criteria": ["Email sent with reset link"],
      "subtasks": [],
      "story_points": 3,
      "priority": "medium",
      "labels": []
    }
  ]
}
```

Hope this helps!"""

        options = GenerationOptions()
        stories = parse_generated_stories(response, options)

        assert len(stories) == 1
        assert stories[0].title == "Password Reset"
        assert stories[0].story_points == 3

    def test_parse_respects_max_stories(self) -> None:
        """Test that max_stories limit is respected."""
        stories_data = [
            {
                "title": f"Story {i}",
                "description": {"role": "user", "want": "something", "benefit": "value"},
                "story_points": 3,
            }
            for i in range(10)
        ]
        response = json.dumps({"stories": stories_data})

        options = GenerationOptions(max_stories=3)
        stories = parse_generated_stories(response, options)

        assert len(stories) == 3

    def test_parse_normalizes_fibonacci_points(self) -> None:
        """Test that story points are normalized to Fibonacci scale."""
        response = json.dumps(
            {
                "stories": [
                    {
                        "title": "Story",
                        "description": {"role": "user", "want": "x", "benefit": "y"},
                        "story_points": 7,  # Should normalize to 8 (closest Fibonacci)
                    }
                ]
            }
        )

        options = GenerationOptions(fibonacci_points=True)
        stories = parse_generated_stories(response, options)

        assert stories[0].story_points == 8  # Closest Fibonacci number

    def test_parse_handles_string_description(self) -> None:
        """Test handling of string description instead of object."""
        response = json.dumps(
            {
                "stories": [
                    {
                        "title": "Simple Story",
                        "description": "A simple feature description",
                        "story_points": 2,
                    }
                ]
            }
        )

        options = GenerationOptions()
        stories = parse_generated_stories(response, options)

        assert len(stories) == 1
        assert stories[0].description_want == "A simple feature description"


class TestConvertToUserStories:
    """Tests for converting generated stories to domain entities."""

    def test_convert_basic_story(self) -> None:
        """Test converting a basic generated story."""
        generated = [
            GeneratedStory(
                title="User Dashboard",
                description_role="logged-in user",
                description_want="to see my dashboard",
                description_benefit="I can view my activity",
                acceptance_criteria=["Shows recent activity"],
                subtasks=[{"name": "Create dashboard component", "story_points": 3}],
                story_points=5,
                priority="high",
                labels=["frontend", "dashboard"],
            )
        ]

        options = GenerationOptions(story_prefix="US", starting_number=1)
        stories = convert_to_user_stories(generated, options)

        assert len(stories) == 1
        story = stories[0]
        assert isinstance(story, UserStory)
        assert str(story.id) == "US-001"
        assert story.title == "User Dashboard"
        assert story.description is not None
        assert story.description.role == "logged-in user"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.PLANNED
        assert len(story.subtasks) == 1
        assert story.subtasks[0].name == "Create dashboard component"

    def test_convert_multiple_stories_with_custom_prefix(self) -> None:
        """Test converting multiple stories with custom prefix."""
        generated = [
            GeneratedStory(
                title="Story One",
                description_role="user",
                description_want="feature one",
                description_benefit="benefit one",
            ),
            GeneratedStory(
                title="Story Two",
                description_role="admin",
                description_want="feature two",
                description_benefit="benefit two",
            ),
        ]

        options = GenerationOptions(story_prefix="PROJ", starting_number=10)
        stories = convert_to_user_stories(generated, options)

        assert len(stories) == 2
        assert str(stories[0].id) == "PROJ-010"
        assert str(stories[1].id) == "PROJ-011"

    def test_convert_respects_subtask_option(self) -> None:
        """Test that subtasks are excluded when option is disabled."""
        generated = [
            GeneratedStory(
                title="Story",
                description_role="user",
                description_want="feature",
                description_benefit="benefit",
                subtasks=[{"name": "Task 1"}, {"name": "Task 2"}],
            )
        ]

        options = GenerationOptions(include_subtasks=False)
        stories = convert_to_user_stories(generated, options)

        assert len(stories[0].subtasks) == 0


class TestAIStoryGenerator:
    """Tests for AIStoryGenerator class."""

    def test_generate_without_llm_provider(self) -> None:
        """Test generation fails gracefully without LLM provider."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = False
            mock_manager.return_value = mock_mgr

            generator = AIStoryGenerator()
            result = generator.generate("Build a feature")

            assert result.success is False
            assert "No LLM providers available" in result.error

    def test_generate_with_mocked_llm(self) -> None:
        """Test successful generation with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "stories": [
                    {
                        "title": "User Authentication",
                        "description": {
                            "role": "visitor",
                            "want": "to create an account",
                            "benefit": "I can access the platform",
                        },
                        "acceptance_criteria": ["Email validation works"],
                        "subtasks": [{"name": "Add signup form", "story_points": 2}],
                        "story_points": 5,
                        "priority": "high",
                    }
                ]
            }
        )

        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 500
            mock_response.model = "gpt-4"
            mock_response.provider = "openai"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            generator = AIStoryGenerator()
            result = generator.generate("Build user authentication")

            assert result.success is True
            assert len(result.stories) == 1
            assert result.stories[0].title == "User Authentication"
            assert result.tokens_used == 500
            assert result.model_used == "gpt-4"
            assert result.provider_used == "openai"

    def test_generate_handles_llm_error(self) -> None:
        """Test handling of LLM errors."""
        with patch("spectryn.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True
            mock_mgr.prompt.side_effect = Exception("API rate limit exceeded")
            mock_manager.return_value = mock_mgr

            generator = AIStoryGenerator()
            result = generator.generate("Build a feature")

            assert result.success is False
            assert "API rate limit exceeded" in result.error


class TestGeneratedStory:
    """Tests for GeneratedStory dataclass."""

    def test_default_values(self) -> None:
        """Test default values for GeneratedStory."""
        story = GeneratedStory(
            title="Test Story",
            description_role="user",
            description_want="feature",
            description_benefit="value",
        )

        assert story.story_points == 3
        assert story.priority == "medium"
        assert story.acceptance_criteria == []
        assert story.subtasks == []
        assert story.labels == []
        assert story.technical_notes == ""


class TestGenerationResult:
    """Tests for GenerationResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = GenerationResult()
        assert result.success is True
        assert result.stories == []
        assert result.error is None

    def test_failure_state(self) -> None:
        """Test failure state."""
        result = GenerationResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"
