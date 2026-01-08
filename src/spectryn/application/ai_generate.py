"""
AI Story Generation - Generate user stories from high-level descriptions.

Uses LLM providers to transform high-level feature descriptions into
properly formatted user stories with acceptance criteria, subtasks,
and story point estimates.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import AcceptanceCriteria, Description, StoryId


logger = logging.getLogger(__name__)


class GenerationStyle(Enum):
    """Style of generated stories."""

    DETAILED = "detailed"  # Full stories with AC, subtasks, technical notes
    STANDARD = "standard"  # Stories with AC, minimal subtasks
    MINIMAL = "minimal"  # Just story title and basic description


@dataclass
class GenerationOptions:
    """Options for AI story generation."""

    # Generation style
    style: GenerationStyle = GenerationStyle.STANDARD

    # Content options
    include_acceptance_criteria: bool = True
    include_subtasks: bool = True
    include_technical_notes: bool = False
    include_story_points: bool = True

    # Story ID configuration
    story_prefix: str = "US"
    starting_number: int = 1

    # Project context (helps LLM generate better stories)
    project_context: str = ""
    tech_stack: str = ""
    target_audience: str = ""

    # Story constraints
    max_stories: int = 10
    max_subtasks_per_story: int = 5
    max_acceptance_criteria: int = 5

    # Estimation
    fibonacci_points: bool = True  # Use 1,2,3,5,8,13 scale


@dataclass
class GeneratedStory:
    """A generated story before conversion to domain entity."""

    title: str
    description_role: str
    description_want: str
    description_benefit: str
    acceptance_criteria: list[str] = field(default_factory=list)
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    story_points: int = 3
    priority: str = "medium"
    labels: list[str] = field(default_factory=list)
    technical_notes: str = ""


@dataclass
class GenerationResult:
    """Result of AI story generation."""

    success: bool = True
    stories: list[UserStory] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""


STORY_GENERATION_SYSTEM_PROMPT = """You are an expert product manager and agile practitioner.
Your task is to break down high-level feature descriptions into well-structured user stories.

Each story should follow the user story format:
- Title: Clear, actionable title describing the feature
- Description: "As a [role], I want [feature], so that [benefit]"
- Acceptance Criteria: Specific, testable conditions for completion
- Subtasks: Technical implementation steps
- Story Points: Effort estimate using Fibonacci scale (1, 2, 3, 5, 8, 13)

Guidelines:
1. Stories should be independent, negotiable, valuable, estimable, small, and testable (INVEST)
2. Each story should be completable in 1-2 sprints
3. Acceptance criteria should be specific and measurable
4. Subtasks should be technical implementation steps
5. Story points should reflect relative complexity

Always respond with valid JSON."""


def build_generation_prompt(
    description: str,
    options: GenerationOptions,
) -> str:
    """Build the prompt for story generation."""
    context_parts = []

    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")
    if options.target_audience:
        context_parts.append(f"Target Audience: {options.target_audience}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    style_instructions = {
        GenerationStyle.DETAILED: "Generate comprehensive stories with detailed acceptance criteria, subtasks with descriptions, and technical notes.",
        GenerationStyle.STANDARD: "Generate stories with acceptance criteria and basic subtasks.",
        GenerationStyle.MINIMAL: "Generate concise stories with just title and description.",
    }

    return f"""Generate user stories from the following high-level description.

## Context
{context_section}

## Feature Description
{description}

## Requirements
- Generate up to {options.max_stories} user stories
- Each story should have up to {options.max_acceptance_criteria} acceptance criteria
- Each story should have up to {options.max_subtasks_per_story} subtasks
- Use {"Fibonacci" if options.fibonacci_points else "linear"} story point scale
- Style: {style_instructions[options.style]}

## Output Format
Respond with a JSON object containing an array of stories:

```json
{{
  "stories": [
    {{
      "title": "Implement User Login",
      "description": {{
        "role": "registered user",
        "want": "to log in with my email and password",
        "benefit": "I can access my personalized dashboard"
      }},
      "acceptance_criteria": [
        "User can enter email and password",
        "Invalid credentials show error message",
        "Successful login redirects to dashboard"
      ],
      "subtasks": [
        {{"name": "Create login form UI", "story_points": 2}},
        {{"name": "Implement authentication API", "story_points": 3}},
        {{"name": "Add session management", "story_points": 2}}
      ],
      "story_points": 5,
      "priority": "high",
      "labels": ["authentication", "security"]
    }}
  ]
}}
```

Generate the stories now:"""


def parse_generated_stories(
    response: str,
    options: GenerationOptions,
) -> list[GeneratedStory]:
    """Parse LLM response into GeneratedStory objects."""
    stories: list[GeneratedStory] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_match = re.search(r"\{[\s\S]*\"stories\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response, attempting full parse")
            json_str = response

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        # Try to extract stories from text format as fallback
        return _parse_stories_from_text(response, options)

    raw_stories = data.get("stories", [])

    for raw_story in raw_stories[: options.max_stories]:
        try:
            desc = raw_story.get("description", {})
            if isinstance(desc, str):
                # Handle string description
                desc = {"role": "user", "want": desc, "benefit": "improved experience"}

            story = GeneratedStory(
                title=raw_story.get("title", "Untitled Story"),
                description_role=desc.get("role", "user"),
                description_want=desc.get("want", ""),
                description_benefit=desc.get("benefit", ""),
                acceptance_criteria=raw_story.get("acceptance_criteria", [])[
                    : options.max_acceptance_criteria
                ],
                subtasks=raw_story.get("subtasks", [])[: options.max_subtasks_per_story],
                story_points=_validate_story_points(
                    raw_story.get("story_points", 3), options.fibonacci_points
                ),
                priority=raw_story.get("priority", "medium"),
                labels=raw_story.get("labels", []),
                technical_notes=raw_story.get("technical_notes", ""),
            )
            stories.append(story)
        except Exception as e:
            logger.warning(f"Failed to parse story: {e}")
            continue

    return stories


def _parse_stories_from_text(response: str, options: GenerationOptions) -> list[GeneratedStory]:
    """Fallback parser for non-JSON responses."""
    stories: list[GeneratedStory] = []

    # Look for story patterns in text
    story_pattern = (
        r"(?:Story|US|User Story)[\s#]*\d*[:\s]*(.+?)(?=(?:Story|US|User Story)[\s#]*\d*[:\s]|$)"
    )
    matches = re.findall(story_pattern, response, re.IGNORECASE | re.DOTALL)

    for i, match in enumerate(matches[: options.max_stories]):
        title_match = re.search(r"^(.+?)(?:\n|$)", match.strip())
        title = title_match.group(1) if title_match else f"Story {i + 1}"

        # Try to extract As a / I want / So that
        desc_match = re.search(
            r"[Aa]s a\s*(.+?)\s*,?\s*[Ii] want\s*(.+?)\s*,?\s*[Ss]o that\s*(.+?)(?:\n|$)",
            match,
            re.DOTALL,
        )

        if desc_match:
            role, want, benefit = desc_match.groups()
        else:
            role, want, benefit = "user", title.lower(), "improved experience"

        stories.append(
            GeneratedStory(
                title=title.strip(),
                description_role=role.strip(),
                description_want=want.strip(),
                description_benefit=benefit.strip(),
            )
        )

    return stories


def _validate_story_points(points: Any, fibonacci: bool) -> int:
    """Validate and normalize story points."""
    try:
        sp = int(points)
    except (ValueError, TypeError):
        return 3

    if fibonacci:
        fibonacci_scale = [1, 2, 3, 5, 8, 13, 21]
        # Find closest fibonacci number
        return min(fibonacci_scale, key=lambda x: abs(x - sp))

    return max(1, min(sp, 21))


def convert_to_user_stories(
    generated: list[GeneratedStory],
    options: GenerationOptions,
) -> list[UserStory]:
    """Convert GeneratedStory objects to domain UserStory entities."""
    stories: list[UserStory] = []

    for i, gen in enumerate(generated):
        story_num = options.starting_number + i
        story_id = StoryId.from_string(f"{options.story_prefix}-{story_num:03d}")

        # Create description
        description = Description(
            role=gen.description_role,
            want=gen.description_want,
            benefit=gen.description_benefit,
        )

        # Create acceptance criteria
        ac = (
            AcceptanceCriteria.from_list(gen.acceptance_criteria)
            if gen.acceptance_criteria
            else AcceptanceCriteria.from_list([])
        )

        # Create subtasks
        subtasks: list[Subtask] = []
        for j, st in enumerate(gen.subtasks):
            subtask_name = st.get("name", st) if isinstance(st, dict) else str(st)
            subtask_sp = st.get("story_points", 1) if isinstance(st, dict) else 1
            subtask_desc = st.get("description", "") if isinstance(st, dict) else ""

            subtasks.append(
                Subtask(
                    number=j + 1,
                    name=subtask_name,
                    description=subtask_desc,
                    story_points=subtask_sp,
                    status=Status.PLANNED,
                )
            )

        # Create user story
        story = UserStory(
            id=story_id,
            title=gen.title,
            description=description,
            acceptance_criteria=ac,
            story_points=gen.story_points,
            priority=Priority.from_string(gen.priority),
            status=Status.PLANNED,
            labels=gen.labels,
            subtasks=subtasks if options.include_subtasks else [],
            technical_notes=gen.technical_notes if options.include_technical_notes else "",
        )
        stories.append(story)

    return stories


class AIStoryGenerator:
    """
    Generates user stories from high-level descriptions using LLM.

    Uses the LLMManager to access available providers (cloud or local).
    """

    def __init__(
        self,
        options: GenerationOptions | None = None,
    ):
        """
        Initialize the story generator.

        Args:
            options: Generation options. Uses defaults if not provided.
        """
        self.options = options or GenerationOptions()
        self.logger = logging.getLogger(__name__)

    def generate(
        self,
        description: str,
        options: GenerationOptions | None = None,
    ) -> GenerationResult:
        """
        Generate user stories from a high-level description.

        Args:
            description: High-level feature description.
            options: Override generation options.

        Returns:
            GenerationResult with generated stories.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = GenerationResult()

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            result.success = False
            result.error = f"Failed to initialize LLM: {e}"
            return result

        if not manager.is_available():
            result.success = False
            result.error = (
                "No LLM providers available. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
                "GOOGLE_API_KEY, or run Ollama locally."
            )
            return result

        # Build prompt
        prompt = build_generation_prompt(description, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=STORY_GENERATION_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            result.success = False
            result.error = f"LLM generation failed: {e}"
            return result

        # Parse response
        try:
            generated = parse_generated_stories(response.content, opts)
            if not generated:
                result.success = False
                result.error = "No stories could be parsed from the response"
                return result

            result.stories = convert_to_user_stories(generated, opts)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse generated stories: {e}"
            return result

        return result

    def generate_to_markdown(
        self,
        description: str,
        options: GenerationOptions | None = None,
    ) -> tuple[str, GenerationResult]:
        """
        Generate stories and return as markdown.

        Args:
            description: High-level feature description.
            options: Override generation options.

        Returns:
            Tuple of (markdown_content, GenerationResult).
        """
        from spectryn.adapters.formatters.markdown_writer import MarkdownWriter

        result = self.generate(description, options)

        if not result.success or not result.stories:
            return "", result

        writer = MarkdownWriter(
            include_epic_header=False,
            include_metadata=True,
            include_subtasks=self.options.include_subtasks,
            include_commits=False,
            include_technical_notes=self.options.include_technical_notes,
        )

        markdown = writer.write_stories(result.stories)
        return markdown, result


def generate_stories_from_description(
    description: str,
    project_context: str = "",
    tech_stack: str = "",
    style: str = "standard",
    max_stories: int = 5,
    story_prefix: str = "US",
) -> GenerationResult:
    """
    Convenience function to generate stories from a description.

    Args:
        description: High-level feature description.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        style: Generation style (detailed, standard, minimal).
        max_stories: Maximum number of stories to generate.
        story_prefix: Prefix for story IDs.

    Returns:
        GenerationResult with generated stories.
    """
    options = GenerationOptions(
        style=GenerationStyle(style),
        project_context=project_context,
        tech_stack=tech_stack,
        max_stories=max_stories,
        story_prefix=story_prefix,
    )

    generator = AIStoryGenerator(options)
    return generator.generate(description, options)
