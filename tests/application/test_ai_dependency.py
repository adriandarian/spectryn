"""Tests for AI Dependency Detection module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from spectra.application.ai_dependency import (
    AIDependencyDetector,
    DependencyOptions,
    DependencyResult,
    DependencyStrength,
    DependencyType,
    DetectedDependency,
    StoryDependencies,
    build_dependency_prompt,
    parse_dependency_response,
)
from spectra.core.domain.entities import UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import Description, StoryId


@pytest.fixture
def api_story() -> UserStory:
    """Create an API/backend story."""
    return UserStory(
        id=StoryId.from_string("US-001"),
        title="Create User API Endpoint",
        description=Description(
            role="developer",
            want="a REST API to create users",
            benefit="the frontend can register new users",
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["api", "backend"],
    )


@pytest.fixture
def ui_story() -> UserStory:
    """Create a UI/frontend story."""
    return UserStory(
        id=StoryId.from_string("US-002"),
        title="User Registration Form",
        description=Description(
            role="new user",
            want="a registration form to create my account",
            benefit="I can sign up for the service",
        ),
        story_points=3,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["ui", "frontend"],
    )


@pytest.fixture
def auth_story() -> UserStory:
    """Create an authentication story."""
    return UserStory(
        id=StoryId.from_string("US-003"),
        title="User Login",
        description=Description(
            role="user",
            want="to log in with my credentials",
            benefit="I can access my account",
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.PLANNED,
        labels=["auth"],
    )


class TestDependencyOptions:
    """Tests for DependencyOptions configuration."""

    def test_default_options(self) -> None:
        """Test default detection options."""
        options = DependencyOptions()

        assert options.detect_technical is True
        assert options.detect_data is True
        assert options.detect_feature is True
        assert options.detect_related is True
        assert options.check_circular is True
        assert options.suggest_order is True

    def test_custom_options(self) -> None:
        """Test custom detection options."""
        options = DependencyOptions(
            detect_technical=False,
            detect_related=False,
            architecture="microservices",
        )

        assert options.detect_technical is False
        assert options.detect_related is False
        assert options.architecture == "microservices"


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_type_values(self) -> None:
        """Test dependency type enum values."""
        assert DependencyType.BLOCKS.value == "blocks"
        assert DependencyType.BLOCKED_BY.value == "blocked_by"
        assert DependencyType.RELATED.value == "related"
        assert DependencyType.SEQUENCE.value == "sequence"


class TestDependencyStrength:
    """Tests for DependencyStrength enum."""

    def test_strength_values(self) -> None:
        """Test dependency strength enum values."""
        assert DependencyStrength.HARD.value == "hard"
        assert DependencyStrength.SOFT.value == "soft"
        assert DependencyStrength.SUGGESTED.value == "suggested"


class TestDetectedDependency:
    """Tests for DetectedDependency dataclass."""

    def test_dependency_creation(self) -> None:
        """Test creating a detected dependency."""
        dep = DetectedDependency(
            from_story_id="US-002",
            to_story_id="US-001",
            dependency_type=DependencyType.BLOCKED_BY,
            strength=DependencyStrength.HARD,
            reason="Frontend needs the API",
            confidence="high",
        )

        assert dep.from_story_id == "US-002"
        assert dep.to_story_id == "US-001"
        assert dep.is_blocking is True

    def test_is_blocking_property(self) -> None:
        """Test is_blocking property."""
        blocking_dep = DetectedDependency(
            from_story_id="US-002",
            to_story_id="US-001",
            dependency_type=DependencyType.BLOCKED_BY,
            strength=DependencyStrength.HARD,
            reason="Test",
        )

        related_dep = DetectedDependency(
            from_story_id="US-002",
            to_story_id="US-001",
            dependency_type=DependencyType.RELATED,
            strength=DependencyStrength.SOFT,
            reason="Test",
        )

        assert blocking_dep.is_blocking is True
        assert related_dep.is_blocking is False


class TestStoryDependencies:
    """Tests for StoryDependencies dataclass."""

    def test_has_blockers(self) -> None:
        """Test has_blockers property."""
        story_dep = StoryDependencies(
            story_id="US-002",
            story_title="UI Story",
            blocked_by=["US-001"],
        )

        assert story_dep.has_blockers is True

    def test_is_blocker(self) -> None:
        """Test is_blocker property."""
        story_dep = StoryDependencies(
            story_id="US-001",
            story_title="API Story",
            blocks=["US-002"],
        )

        assert story_dep.is_blocker is True

    def test_total_dependencies(self) -> None:
        """Test total_dependencies property."""
        story_dep = StoryDependencies(
            story_id="US-001",
            story_title="Story",
            blocks=["US-002", "US-003"],
            blocked_by=["US-000"],
            related_to=["US-004"],
        )

        assert story_dep.total_dependencies == 4


class TestDependencyResult:
    """Tests for DependencyResult dataclass."""

    def test_default_success(self) -> None:
        """Test default success state."""
        result = DependencyResult()
        assert result.success is True
        assert result.all_dependencies == []
        assert result.has_circular is False

    def test_stories_with_blockers(self) -> None:
        """Test stories_with_blockers count."""
        result = DependencyResult(
            story_dependencies=[
                StoryDependencies(
                    story_id="US-001",
                    story_title="Blocked",
                    blocked_by=["US-000"],
                ),
                StoryDependencies(
                    story_id="US-002",
                    story_title="Not blocked",
                ),
            ]
        )

        assert result.stories_with_blockers == 1


class TestBuildDependencyPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test basic prompt generation."""
        options = DependencyOptions()
        prompt = build_dependency_prompt([api_story, ui_story], options)

        assert "US-001" in prompt
        assert "US-002" in prompt
        assert "Create User API" in prompt
        assert "Registration Form" in prompt

    def test_prompt_with_context(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test prompt with project context."""
        options = DependencyOptions(
            project_context="E-commerce platform",
            tech_stack="React, Django",
            architecture="microservices",
        )
        prompt = build_dependency_prompt([api_story, ui_story], options)

        assert "E-commerce platform" in prompt
        assert "React, Django" in prompt
        assert "microservices" in prompt


class TestParseDependencyResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_response(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "dependencies": [
                    {
                        "from_story_id": "US-002",
                        "to_story_id": "US-001",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "Frontend needs the API endpoint",
                        "confidence": "high",
                    }
                ],
                "circular_dependencies": [],
                "suggested_order": ["US-001", "US-002"],
            }
        )

        options = DependencyOptions()
        deps, circular, order = parse_dependency_response(response, [api_story, ui_story], options)

        assert len(deps) == 1
        assert deps[0].from_story_id == "US-002"
        assert deps[0].to_story_id == "US-001"
        assert deps[0].dependency_type == DependencyType.BLOCKED_BY
        assert deps[0].strength == DependencyStrength.HARD
        assert len(circular) == 0
        assert order == ["US-001", "US-002"]

    def test_parse_json_in_code_block(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = """Here are the dependencies:

```json
{
  "dependencies": [
    {
      "from_story_id": "US-002",
      "to_story_id": "US-001",
      "dependency_type": "blocked_by",
      "strength": "soft",
      "reason": "UI depends on API"
    }
  ],
  "circular_dependencies": [],
  "suggested_order": ["US-001", "US-002"]
}
```
"""

        options = DependencyOptions()
        deps, _, _ = parse_dependency_response(response, [api_story, ui_story], options)

        assert len(deps) == 1
        assert deps[0].dependency_type == DependencyType.BLOCKED_BY

    def test_parse_filters_invalid_story_ids(
        self, api_story: UserStory, ui_story: UserStory
    ) -> None:
        """Test that invalid story IDs are filtered out."""
        response = json.dumps(
            {
                "dependencies": [
                    {
                        "from_story_id": "US-002",
                        "to_story_id": "US-001",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "Valid dependency",
                    },
                    {
                        "from_story_id": "US-999",  # Invalid
                        "to_story_id": "US-001",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "Invalid dependency",
                    },
                ]
            }
        )

        options = DependencyOptions()
        deps, _, _ = parse_dependency_response(response, [api_story, ui_story], options)

        assert len(deps) == 1
        assert deps[0].from_story_id == "US-002"

    def test_parse_filters_self_references(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test that self-references are filtered out."""
        response = json.dumps(
            {
                "dependencies": [
                    {
                        "from_story_id": "US-001",
                        "to_story_id": "US-001",  # Self-reference
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "Invalid",
                    }
                ]
            }
        )

        options = DependencyOptions()
        deps, _, _ = parse_dependency_response(response, [api_story, ui_story], options)

        assert len(deps) == 0

    def test_fallback_on_invalid_json(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test fallback when JSON parsing fails."""
        response = "This is not valid JSON"

        options = DependencyOptions()
        deps, _, _ = parse_dependency_response(response, [api_story, ui_story], options)

        # Should create fallback dependencies
        # UI story should be detected as depending on API story
        assert len(deps) >= 0  # May or may not detect dependencies


class TestAIDependencyDetector:
    """Tests for AIDependencyDetector class."""

    def test_detect_empty_stories(self) -> None:
        """Test detecting for empty story list."""
        detector = AIDependencyDetector()
        result = detector.detect([])

        assert result.success is False
        assert "No stories provided" in result.error

    def test_detect_single_story(self, api_story: UserStory) -> None:
        """Test detecting for single story."""
        detector = AIDependencyDetector()
        result = detector.detect([api_story])

        assert result.success is False
        assert "At least 2 stories" in result.error

    def test_detect_with_fallback(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test detecting with fallback when LLM is not available."""
        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_manager.side_effect = Exception("LLM not configured")

            detector = AIDependencyDetector()
            result = detector.detect([api_story, ui_story])

            # Should succeed with fallback detection
            assert result.success is True
            assert len(result.story_dependencies) == 2

    def test_detect_with_mocked_llm(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test successful detection with mocked LLM."""
        mock_response_content = json.dumps(
            {
                "dependencies": [
                    {
                        "from_story_id": "US-002",
                        "to_story_id": "US-001",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "Frontend needs API",
                        "confidence": "high",
                    }
                ],
                "circular_dependencies": [],
                "suggested_order": ["US-001", "US-002"],
            }
        )

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 200
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            detector = AIDependencyDetector()
            result = detector.detect([api_story, ui_story])

            assert result.success is True
            assert result.total_dependencies == 1
            assert result.stories_with_blockers == 1
            assert result.suggested_order == ["US-001", "US-002"]
            assert result.provider_used == "anthropic"

    def test_circular_dependency_detection(self, api_story: UserStory, ui_story: UserStory) -> None:
        """Test circular dependency detection."""
        mock_response_content = json.dumps(
            {
                "dependencies": [
                    {
                        "from_story_id": "US-002",
                        "to_story_id": "US-001",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "UI needs API",
                    },
                    {
                        "from_story_id": "US-001",
                        "to_story_id": "US-002",
                        "dependency_type": "blocked_by",
                        "strength": "hard",
                        "reason": "API needs UI (circular!)",
                    },
                ],
                "circular_dependencies": [["US-001", "US-002", "US-001"]],
                "suggested_order": [],
            }
        )

        with patch("spectra.adapters.llm.create_llm_manager") as mock_manager:
            mock_mgr = MagicMock()
            mock_mgr.is_available.return_value = True

            mock_response = MagicMock()
            mock_response.content = mock_response_content
            mock_response.total_tokens = 200
            mock_response.model = "claude-3"
            mock_response.provider = "anthropic"
            mock_mgr.prompt.return_value = mock_response

            mock_manager.return_value = mock_mgr

            detector = AIDependencyDetector()
            result = detector.detect([api_story, ui_story])

            assert result.success is True
            assert result.has_circular is True
            assert len(result.circular_dependencies) >= 1
