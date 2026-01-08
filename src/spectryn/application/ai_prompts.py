"""
Custom Prompts Configuration - Let users customize AI prompts.

Provides a system for users to:
- Override default AI prompts for any feature
- Create custom prompt templates with variables
- Load prompts from configuration files
- Manage prompt versions
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from string import Template
from typing import Any


logger = logging.getLogger(__name__)


class PromptType(Enum):
    """Types of prompts available for customization."""

    # Story operations
    STORY_GENERATION = "story_generation"
    STORY_REFINEMENT = "story_refinement"
    STORY_SPLITTING = "story_splitting"

    # Analysis
    QUALITY_SCORING = "quality_scoring"
    GAP_ANALYSIS = "gap_analysis"
    DUPLICATE_DETECTION = "duplicate_detection"
    DEPENDENCY_DETECTION = "dependency_detection"

    # Generation
    ACCEPTANCE_CRITERIA = "acceptance_criteria"
    ESTIMATION = "estimation"
    LABELING = "labeling"

    # Sync
    SYNC_SUMMARY = "sync_summary"

    # Custom
    CUSTOM = "custom"


@dataclass
class PromptVariable:
    """A variable that can be used in prompts."""

    name: str
    description: str
    required: bool = True
    default: str = ""
    example: str = ""


@dataclass
class PromptTemplate:
    """A customizable prompt template."""

    name: str
    prompt_type: PromptType
    system_prompt: str
    user_prompt: str
    description: str = ""
    variables: list[PromptVariable] = field(default_factory=list)
    version: str = "1.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)

    def render(self, **kwargs: Any) -> tuple[str, str]:
        """
        Render the prompt with provided variables.

        Args:
            **kwargs: Variable values to substitute.

        Returns:
            Tuple of (system_prompt, user_prompt) with variables substituted.
        """
        # Apply defaults for missing optional variables
        for var in self.variables:
            if var.name not in kwargs and not var.required:
                kwargs[var.name] = var.default

        # Validate required variables
        missing = []
        for var in self.variables:
            if var.required and var.name not in kwargs:
                missing.append(var.name)

        if missing:
            raise ValueError(f"Missing required variables: {', '.join(missing)}")

        # Render using safe substitution
        try:
            system = Template(self.system_prompt).safe_substitute(**kwargs)
            user = Template(self.user_prompt).safe_substitute(**kwargs)
            return system, user
        except Exception as e:
            raise ValueError(f"Failed to render prompt: {e}") from e

    def get_variable_names(self) -> list[str]:
        """Extract variable names from prompts."""
        pattern = r"\$\{?(\w+)\}?"
        names = set()
        names.update(re.findall(pattern, self.system_prompt))
        names.update(re.findall(pattern, self.user_prompt))
        return sorted(names)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "prompt_type": self.prompt_type.value,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "description": self.description,
            "variables": [
                {
                    "name": v.name,
                    "description": v.description,
                    "required": v.required,
                    "default": v.default,
                    "example": v.example,
                }
                for v in self.variables
            ],
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptTemplate":
        """Create from dictionary."""
        variables = [
            PromptVariable(
                name=v["name"],
                description=v.get("description", ""),
                required=v.get("required", True),
                default=v.get("default", ""),
                example=v.get("example", ""),
            )
            for v in data.get("variables", [])
        ]

        try:
            prompt_type = PromptType(data.get("prompt_type", "custom"))
        except ValueError:
            prompt_type = PromptType.CUSTOM

        return cls(
            name=data["name"],
            prompt_type=prompt_type,
            system_prompt=data.get("system_prompt", ""),
            user_prompt=data.get("user_prompt", ""),
            description=data.get("description", ""),
            variables=variables,
            version=data.get("version", "1.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
        )


@dataclass
class PromptConfig:
    """Configuration for custom prompts."""

    prompts: dict[str, PromptTemplate] = field(default_factory=dict)
    config_path: Path | None = None
    use_defaults: bool = True  # Fall back to defaults if custom not found

    def get_prompt(
        self,
        prompt_type: PromptType,
        name: str | None = None,
    ) -> PromptTemplate | None:
        """
        Get a prompt by type and optional name.

        Args:
            prompt_type: Type of prompt to retrieve.
            name: Optional specific prompt name.

        Returns:
            PromptTemplate if found, None otherwise.
        """
        if name and name in self.prompts:
            return self.prompts[name]

        # Find by type
        for prompt in self.prompts.values():
            if prompt.prompt_type == prompt_type:
                return prompt

        return None

    def add_prompt(self, prompt: PromptTemplate) -> None:
        """Add a prompt to the configuration."""
        self.prompts[prompt.name] = prompt

    def remove_prompt(self, name: str) -> bool:
        """Remove a prompt by name."""
        if name in self.prompts:
            del self.prompts[name]
            return True
        return False

    def list_prompts(
        self,
        prompt_type: PromptType | None = None,
    ) -> list[PromptTemplate]:
        """List all prompts, optionally filtered by type."""
        if prompt_type:
            return [p for p in self.prompts.values() if p.prompt_type == prompt_type]
        return list(self.prompts.values())

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "prompts": {name: p.to_dict() for name, p in self.prompts.items()},
            "use_defaults": self.use_defaults,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptConfig":
        """Create from dictionary."""
        prompts = {}
        for name, prompt_data in data.get("prompts", {}).items():
            prompts[name] = PromptTemplate.from_dict(prompt_data)

        return cls(
            prompts=prompts,
            use_defaults=data.get("use_defaults", True),
        )


# Default prompts for each type
DEFAULT_PROMPTS: dict[PromptType, PromptTemplate] = {
    PromptType.STORY_GENERATION: PromptTemplate(
        name="default_story_generation",
        prompt_type=PromptType.STORY_GENERATION,
        description="Generate user stories from high-level descriptions",
        system_prompt="""You are an expert product manager who creates clear, actionable user stories.
Follow the INVEST principles: Independent, Negotiable, Valuable, Estimable, Small, Testable.
Always respond with valid JSON.""",
        user_prompt="""Generate user stories from this description:

$description

Project context: $project_context
Tech stack: $tech_stack
Style: $style

Generate $max_stories stories in JSON format.""",
        variables=[
            PromptVariable("description", "High-level feature description", True),
            PromptVariable("project_context", "Project context", False, ""),
            PromptVariable("tech_stack", "Technology stack", False, ""),
            PromptVariable("style", "Generation style", False, "detailed"),
            PromptVariable("max_stories", "Maximum stories to generate", False, "5"),
        ],
    ),
    PromptType.STORY_REFINEMENT: PromptTemplate(
        name="default_story_refinement",
        prompt_type=PromptType.STORY_REFINEMENT,
        description="Analyze and refine user stories for quality issues",
        system_prompt="""You are an expert agile coach analyzing user stories for quality.
Check for: ambiguity, missing acceptance criteria, scope issues, testability.
Always respond with valid JSON.""",
        user_prompt="""Analyze these user stories for quality issues:

$stories

Check for:
- Ambiguity in requirements
- Missing or weak acceptance criteria
- Scope that's too large
- Testability issues

Respond with JSON containing issues and suggestions.""",
        variables=[
            PromptVariable("stories", "Stories to analyze", True),
        ],
    ),
    PromptType.QUALITY_SCORING: PromptTemplate(
        name="default_quality_scoring",
        prompt_type=PromptType.QUALITY_SCORING,
        description="Score user stories on INVEST and other quality dimensions",
        system_prompt="""You are an expert at evaluating user story quality.
Score stories on INVEST dimensions and overall clarity.
Always respond with valid JSON.""",
        user_prompt="""Score these user stories on quality dimensions:

$stories

Dimensions to score: $dimensions

Provide scores (1-10) for each dimension with explanations.""",
        variables=[
            PromptVariable("stories", "Stories to score", True),
            PromptVariable("dimensions", "Dimensions to score", False, "INVEST"),
        ],
    ),
    PromptType.GAP_ANALYSIS: PromptTemplate(
        name="default_gap_analysis",
        prompt_type=PromptType.GAP_ANALYSIS,
        description="Identify gaps in requirements coverage",
        system_prompt="""You are an expert requirements analyst.
Identify missing personas, functionality, NFRs, and edge cases.
Always respond with valid JSON.""",
        user_prompt="""Analyze these stories for requirement gaps:

$stories

Context: $context
Industry: $industry

Identify missing requirements and suggest stories to fill gaps.""",
        variables=[
            PromptVariable("stories", "Stories to analyze", True),
            PromptVariable("context", "Project context", False, ""),
            PromptVariable("industry", "Industry context", False, ""),
        ],
    ),
    PromptType.ACCEPTANCE_CRITERIA: PromptTemplate(
        name="default_acceptance_criteria",
        prompt_type=PromptType.ACCEPTANCE_CRITERIA,
        description="Generate acceptance criteria for user stories",
        system_prompt="""You are an expert at writing clear, testable acceptance criteria.
Use Given/When/Then format when appropriate.
Always respond with valid JSON.""",
        user_prompt="""Generate acceptance criteria for this story:

$story

Style: $style
Categories: $categories
Min criteria: $min_ac
Max criteria: $max_ac

Provide clear, testable acceptance criteria.""",
        variables=[
            PromptVariable("story", "Story to generate AC for", True),
            PromptVariable("style", "AC style (gherkin, simple)", False, "simple"),
            PromptVariable("categories", "AC categories to include", False, "functional"),
            PromptVariable("min_ac", "Minimum criteria", False, "3"),
            PromptVariable("max_ac", "Maximum criteria", False, "7"),
        ],
    ),
    PromptType.ESTIMATION: PromptTemplate(
        name="default_estimation",
        prompt_type=PromptType.ESTIMATION,
        description="Estimate story points for user stories",
        system_prompt="""You are an expert at estimating software development effort.
Use Fibonacci scale and consider complexity factors.
Always respond with valid JSON.""",
        user_prompt="""Estimate story points for these stories:

$stories

Scale: $scale
Team velocity context: $velocity_context

Provide estimates with rationale.""",
        variables=[
            PromptVariable("stories", "Stories to estimate", True),
            PromptVariable("scale", "Estimation scale", False, "fibonacci"),
            PromptVariable("velocity_context", "Team velocity context", False, ""),
        ],
    ),
    PromptType.SYNC_SUMMARY: PromptTemplate(
        name="default_sync_summary",
        prompt_type=PromptType.SYNC_SUMMARY,
        description="Generate human-readable sync summaries",
        system_prompt="""You are an expert at summarizing software sync operations.
Create clear, actionable summaries for the target audience.
Always respond with valid JSON.""",
        user_prompt="""Summarize this sync operation:

$sync_details

Audience: $audience

Provide headline, overview, key changes, issues, and recommendations.""",
        variables=[
            PromptVariable("sync_details", "Sync operation details", True),
            PromptVariable("audience", "Target audience", False, "technical"),
        ],
    ),
}


class PromptManager:
    """
    Manages custom prompts configuration.

    Loads, saves, and provides prompts for AI features.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        use_defaults: bool = True,
    ):
        """
        Initialize the prompt manager.

        Args:
            config_path: Path to prompts configuration file.
            use_defaults: Fall back to defaults if custom not found.
        """
        self.config = PromptConfig(use_defaults=use_defaults)
        self.config_path = Path(config_path) if config_path else None
        self.logger = logging.getLogger(__name__)

        # Load from file if provided
        if self.config_path and self.config_path.exists():
            self.load()

        # Check environment variable
        env_path = os.environ.get("SPECTRA_PROMPTS_CONFIG")
        if env_path and not self.config_path:
            self.config_path = Path(env_path)
            if self.config_path.exists():
                self.load()

    def load(self, path: Path | str | None = None) -> bool:
        """
        Load prompts from configuration file.

        Args:
            path: Optional path override.

        Returns:
            True if loaded successfully.
        """
        load_path = Path(path) if path else self.config_path
        if not load_path or not load_path.exists():
            return False

        try:
            with open(load_path) as f:
                if load_path.suffix in (".yaml", ".yml"):
                    try:
                        import yaml

                        data = yaml.safe_load(f)
                    except ImportError:
                        self.logger.warning("YAML support requires PyYAML")
                        return False
                else:
                    data = json.load(f)

            self.config = PromptConfig.from_dict(data)
            self.config.config_path = load_path
            self.logger.info(f"Loaded {len(self.config.prompts)} custom prompts")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load prompts: {e}")
            return False

    def save(self, path: Path | str | None = None) -> bool:
        """
        Save prompts to configuration file.

        Args:
            path: Optional path override.

        Returns:
            True if saved successfully.
        """
        save_path = Path(path) if path else self.config_path
        if not save_path:
            save_path = Path(".spectra-prompts.json")

        try:
            data = self.config.to_dict()

            with open(save_path, "w") as f:
                if save_path.suffix in (".yaml", ".yml"):
                    try:
                        import yaml

                        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                    except ImportError:
                        json.dump(data, f, indent=2)
                else:
                    json.dump(data, f, indent=2)

            self.config_path = save_path
            self.logger.info(f"Saved {len(self.config.prompts)} prompts to {save_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save prompts: {e}")
            return False

    def get_prompt(
        self,
        prompt_type: PromptType,
        name: str | None = None,
    ) -> PromptTemplate:
        """
        Get a prompt, falling back to defaults if needed.

        Args:
            prompt_type: Type of prompt.
            name: Optional specific prompt name.

        Returns:
            PromptTemplate for the requested type.
        """
        # Try custom first
        prompt = self.config.get_prompt(prompt_type, name)
        if prompt:
            return prompt

        # Fall back to default if enabled
        if self.config.use_defaults and prompt_type in DEFAULT_PROMPTS:
            return DEFAULT_PROMPTS[prompt_type]

        # Return empty template if nothing found
        return PromptTemplate(
            name="empty",
            prompt_type=prompt_type,
            system_prompt="",
            user_prompt="",
        )

    def add_prompt(self, prompt: PromptTemplate) -> None:
        """Add a custom prompt."""
        self.config.add_prompt(prompt)

    def remove_prompt(self, name: str) -> bool:
        """Remove a custom prompt."""
        return self.config.remove_prompt(name)

    def list_prompts(
        self,
        prompt_type: PromptType | None = None,
        include_defaults: bool = True,
    ) -> list[PromptTemplate]:
        """List all available prompts."""
        prompts = self.config.list_prompts(prompt_type)

        if include_defaults:
            for ptype, default in DEFAULT_PROMPTS.items():
                if prompt_type is None or ptype == prompt_type:
                    # Only include default if no custom override
                    if not any(p.prompt_type == ptype for p in prompts):
                        prompts.append(default)

        return prompts

    def create_prompt(
        self,
        name: str,
        prompt_type: PromptType,
        system_prompt: str,
        user_prompt: str,
        description: str = "",
        variables: list[dict] | None = None,
    ) -> PromptTemplate:
        """
        Create and add a new prompt.

        Args:
            name: Prompt name.
            prompt_type: Type of prompt.
            system_prompt: System prompt text.
            user_prompt: User prompt text.
            description: Optional description.
            variables: Optional variable definitions.

        Returns:
            Created PromptTemplate.
        """
        var_list = []
        if variables:
            for v in variables:
                var_list.append(
                    PromptVariable(
                        name=v["name"],
                        description=v.get("description", ""),
                        required=v.get("required", True),
                        default=v.get("default", ""),
                        example=v.get("example", ""),
                    )
                )

        prompt = PromptTemplate(
            name=name,
            prompt_type=prompt_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            description=description,
            variables=var_list,
        )

        self.add_prompt(prompt)
        return prompt

    def export_defaults(self, path: Path | str) -> bool:
        """
        Export default prompts to a file for customization.

        Args:
            path: Path to export to.

        Returns:
            True if exported successfully.
        """
        try:
            data = {
                "prompts": {p.name: p.to_dict() for p in DEFAULT_PROMPTS.values()},
                "use_defaults": True,
            }

            export_path = Path(path)
            with open(export_path, "w") as f:
                if export_path.suffix in (".yaml", ".yml"):
                    try:
                        import yaml

                        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                    except ImportError:
                        json.dump(data, f, indent=2)
                else:
                    json.dump(data, f, indent=2)

            return True
        except Exception as e:
            self.logger.error(f"Failed to export defaults: {e}")
            return False


# Global prompt manager instance
_prompt_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """Get the global prompt manager instance."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager


def set_prompt_manager(manager: PromptManager) -> None:
    """Set the global prompt manager instance."""
    global _prompt_manager
    _prompt_manager = manager


def get_custom_prompt(
    prompt_type: PromptType,
    name: str | None = None,
) -> PromptTemplate:
    """
    Get a custom or default prompt.

    Args:
        prompt_type: Type of prompt.
        name: Optional specific prompt name.

    Returns:
        PromptTemplate for the requested type.
    """
    return get_prompt_manager().get_prompt(prompt_type, name)


def render_prompt(
    prompt_type: PromptType,
    name: str | None = None,
    **kwargs: Any,
) -> tuple[str, str]:
    """
    Render a prompt with variables.

    Args:
        prompt_type: Type of prompt.
        name: Optional specific prompt name.
        **kwargs: Variable values.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    prompt = get_custom_prompt(prompt_type, name)
    return prompt.render(**kwargs)
