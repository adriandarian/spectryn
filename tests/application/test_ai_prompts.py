"""Tests for AI Custom Prompts module."""

import json
import tempfile
from pathlib import Path

import pytest

from spectra.application.ai_prompts import (
    DEFAULT_PROMPTS,
    PromptConfig,
    PromptManager,
    PromptTemplate,
    PromptType,
    PromptVariable,
    get_custom_prompt,
    get_prompt_manager,
    render_prompt,
    set_prompt_manager,
)


class TestPromptType:
    """Tests for PromptType enum."""

    def test_prompt_type_values(self) -> None:
        """Test prompt type enum values."""
        assert PromptType.STORY_GENERATION.value == "story_generation"
        assert PromptType.STORY_REFINEMENT.value == "story_refinement"
        assert PromptType.QUALITY_SCORING.value == "quality_scoring"
        assert PromptType.GAP_ANALYSIS.value == "gap_analysis"
        assert PromptType.ACCEPTANCE_CRITERIA.value == "acceptance_criteria"
        assert PromptType.CUSTOM.value == "custom"


class TestPromptVariable:
    """Tests for PromptVariable dataclass."""

    def test_variable_creation(self) -> None:
        """Test creating a prompt variable."""
        var = PromptVariable(
            name="description",
            description="The feature description",
            required=True,
            default="",
            example="User authentication feature",
        )

        assert var.name == "description"
        assert var.required is True
        assert var.example == "User authentication feature"

    def test_optional_variable(self) -> None:
        """Test optional variable with default."""
        var = PromptVariable(
            name="style",
            description="Generation style",
            required=False,
            default="detailed",
        )

        assert var.required is False
        assert var.default == "detailed"


class TestPromptTemplate:
    """Tests for PromptTemplate dataclass."""

    @pytest.fixture
    def sample_template(self) -> PromptTemplate:
        """Create a sample template."""
        return PromptTemplate(
            name="test_prompt",
            prompt_type=PromptType.STORY_GENERATION,
            description="Test prompt for generation",
            system_prompt="You are a $role assistant.",
            user_prompt="Generate $count stories about: $topic",
            variables=[
                PromptVariable("role", "Assistant role", True),
                PromptVariable("count", "Number of stories", False, "5"),
                PromptVariable("topic", "Story topic", True),
            ],
            version="1.0",
            author="test",
            tags=["test", "generation"],
        )

    def test_template_creation(self, sample_template: PromptTemplate) -> None:
        """Test creating a template."""
        assert sample_template.name == "test_prompt"
        assert sample_template.prompt_type == PromptType.STORY_GENERATION
        assert len(sample_template.variables) == 3

    def test_render_with_all_variables(self, sample_template: PromptTemplate) -> None:
        """Test rendering with all variables."""
        system, user = sample_template.render(
            role="product manager",
            count="3",
            topic="user authentication",
        )

        assert "product manager" in system
        assert "3 stories" in user
        assert "user authentication" in user

    def test_render_with_defaults(self, sample_template: PromptTemplate) -> None:
        """Test rendering with default values."""
        _system, user = sample_template.render(
            role="engineer",
            topic="payment processing",
        )

        # count should use default "5"
        assert "5 stories" in user

    def test_render_missing_required(self, sample_template: PromptTemplate) -> None:
        """Test rendering fails with missing required variable."""
        with pytest.raises(ValueError, match="Missing required variables"):
            sample_template.render(role="assistant")  # Missing 'topic'

    def test_get_variable_names(self, sample_template: PromptTemplate) -> None:
        """Test extracting variable names."""
        names = sample_template.get_variable_names()

        assert "role" in names
        assert "count" in names
        assert "topic" in names

    def test_to_dict(self, sample_template: PromptTemplate) -> None:
        """Test converting to dictionary."""
        data = sample_template.to_dict()

        assert data["name"] == "test_prompt"
        assert data["prompt_type"] == "story_generation"
        assert len(data["variables"]) == 3
        assert data["version"] == "1.0"

    def test_from_dict(self) -> None:
        """Test creating from dictionary."""
        data = {
            "name": "loaded_prompt",
            "prompt_type": "quality_scoring",
            "system_prompt": "Score stories.",
            "user_prompt": "Analyze: $stories",
            "description": "Quality scoring prompt",
            "variables": [{"name": "stories", "description": "Stories to score", "required": True}],
            "version": "2.0",
        }

        template = PromptTemplate.from_dict(data)

        assert template.name == "loaded_prompt"
        assert template.prompt_type == PromptType.QUALITY_SCORING
        assert len(template.variables) == 1
        assert template.version == "2.0"


class TestPromptConfig:
    """Tests for PromptConfig dataclass."""

    def test_empty_config(self) -> None:
        """Test empty configuration."""
        config = PromptConfig()

        assert len(config.prompts) == 0
        assert config.use_defaults is True

    def test_add_prompt(self) -> None:
        """Test adding a prompt."""
        config = PromptConfig()
        prompt = PromptTemplate(
            name="custom",
            prompt_type=PromptType.CUSTOM,
            system_prompt="Custom prompt",
            user_prompt="Do: $task",
        )

        config.add_prompt(prompt)

        assert "custom" in config.prompts
        assert config.get_prompt(PromptType.CUSTOM, "custom") == prompt

    def test_remove_prompt(self) -> None:
        """Test removing a prompt."""
        config = PromptConfig()
        config.add_prompt(
            PromptTemplate(
                name="to_remove",
                prompt_type=PromptType.CUSTOM,
                system_prompt="",
                user_prompt="",
            )
        )

        assert config.remove_prompt("to_remove") is True
        assert "to_remove" not in config.prompts
        assert config.remove_prompt("nonexistent") is False

    def test_list_prompts(self) -> None:
        """Test listing prompts."""
        config = PromptConfig()
        config.add_prompt(
            PromptTemplate(
                name="p1",
                prompt_type=PromptType.STORY_GENERATION,
                system_prompt="",
                user_prompt="",
            )
        )
        config.add_prompt(
            PromptTemplate(
                name="p2",
                prompt_type=PromptType.QUALITY_SCORING,
                system_prompt="",
                user_prompt="",
            )
        )

        all_prompts = config.list_prompts()
        assert len(all_prompts) == 2

        gen_prompts = config.list_prompts(PromptType.STORY_GENERATION)
        assert len(gen_prompts) == 1
        assert gen_prompts[0].name == "p1"

    def test_to_dict_and_from_dict(self) -> None:
        """Test serialization round-trip."""
        config = PromptConfig(use_defaults=False)
        config.add_prompt(
            PromptTemplate(
                name="test",
                prompt_type=PromptType.ESTIMATION,
                system_prompt="Estimate.",
                user_prompt="Stories: $stories",
            )
        )

        data = config.to_dict()
        loaded = PromptConfig.from_dict(data)

        assert loaded.use_defaults is False
        assert "test" in loaded.prompts
        assert loaded.prompts["test"].prompt_type == PromptType.ESTIMATION


class TestPromptManager:
    """Tests for PromptManager class."""

    def test_manager_defaults(self) -> None:
        """Test manager provides defaults."""
        manager = PromptManager(use_defaults=True)

        prompt = manager.get_prompt(PromptType.STORY_GENERATION)
        assert prompt is not None
        assert prompt.name == "default_story_generation"

    def test_manager_custom_override(self) -> None:
        """Test custom prompt overrides default."""
        manager = PromptManager(use_defaults=True)

        # Add custom prompt
        custom = PromptTemplate(
            name="my_generation",
            prompt_type=PromptType.STORY_GENERATION,
            system_prompt="My custom system prompt",
            user_prompt="Generate: $description",
        )
        manager.add_prompt(custom)

        prompt = manager.get_prompt(PromptType.STORY_GENERATION, "my_generation")
        assert prompt.name == "my_generation"
        assert "custom system prompt" in prompt.system_prompt

    def test_save_and_load(self) -> None:
        """Test saving and loading prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "prompts.json"

            # Create and save
            manager = PromptManager()
            manager.create_prompt(
                name="saved_prompt",
                prompt_type=PromptType.LABELING,
                system_prompt="Label stories",
                user_prompt="Stories: $stories",
                description="Test saved prompt",
            )
            assert manager.save(path) is True

            # Load in new manager
            new_manager = PromptManager(config_path=path)
            assert "saved_prompt" in new_manager.config.prompts
            prompt = new_manager.get_prompt(PromptType.LABELING, "saved_prompt")
            assert prompt.description == "Test saved prompt"

    def test_export_defaults(self) -> None:
        """Test exporting default prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "defaults.json"

            manager = PromptManager()
            assert manager.export_defaults(path) is True

            # Verify file contains defaults
            with open(path) as f:
                data = json.load(f)

            assert "prompts" in data
            assert len(data["prompts"]) > 0

    def test_list_prompts_includes_defaults(self) -> None:
        """Test listing includes defaults."""
        manager = PromptManager(use_defaults=True)

        prompts = manager.list_prompts(include_defaults=True)
        assert len(prompts) >= len(DEFAULT_PROMPTS)

    def test_create_prompt(self) -> None:
        """Test creating a prompt programmatically."""
        manager = PromptManager()

        prompt = manager.create_prompt(
            name="programmatic",
            prompt_type=PromptType.CUSTOM,
            system_prompt="System",
            user_prompt="User: $input",
            description="Created programmatically",
            variables=[{"name": "input", "description": "User input", "required": True}],
        )

        assert prompt.name == "programmatic"
        assert len(prompt.variables) == 1
        assert "programmatic" in manager.config.prompts


class TestDefaultPrompts:
    """Tests for default prompts."""

    def test_all_types_have_defaults(self) -> None:
        """Test that common types have defaults."""
        required_types = [
            PromptType.STORY_GENERATION,
            PromptType.STORY_REFINEMENT,
            PromptType.QUALITY_SCORING,
            PromptType.GAP_ANALYSIS,
            PromptType.ACCEPTANCE_CRITERIA,
            PromptType.ESTIMATION,
            PromptType.SYNC_SUMMARY,
        ]

        for ptype in required_types:
            assert ptype in DEFAULT_PROMPTS, f"Missing default for {ptype}"

    def test_defaults_have_required_fields(self) -> None:
        """Test default prompts have required fields."""
        for prompt in DEFAULT_PROMPTS.values():
            assert prompt.name
            assert prompt.system_prompt
            assert prompt.user_prompt
            assert prompt.prompt_type in PromptType


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_prompt_manager(self) -> None:
        """Test getting global manager."""
        manager = get_prompt_manager()
        assert manager is not None
        assert isinstance(manager, PromptManager)

    def test_set_prompt_manager(self) -> None:
        """Test setting custom manager."""
        custom_manager = PromptManager(use_defaults=False)
        set_prompt_manager(custom_manager)

        retrieved = get_prompt_manager()
        assert retrieved.config.use_defaults is False

        # Reset for other tests
        set_prompt_manager(PromptManager())

    def test_get_custom_prompt(self) -> None:
        """Test getting prompt via convenience function."""
        prompt = get_custom_prompt(PromptType.STORY_GENERATION)
        assert prompt is not None
        assert prompt.prompt_type == PromptType.STORY_GENERATION

    def test_render_prompt(self) -> None:
        """Test rendering prompt via convenience function."""
        system, user = render_prompt(
            PromptType.STORY_GENERATION,
            description="User login feature",
            project_context="Web app",
            tech_stack="React, Node.js",
            style="detailed",
            max_stories="3",
        )

        assert system  # Non-empty
        assert "User login feature" in user
        assert "Web app" in user
