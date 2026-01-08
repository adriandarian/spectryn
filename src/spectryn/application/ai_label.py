"""
AI Labeling/Auto-categorization - Suggest labels/categories based on content.

Uses LLM providers to analyze user stories and suggest appropriate
labels and categories based on:
- Story content and description
- Technical aspects mentioned
- Feature area
- User personas
- Non-functional requirements (security, performance, etc.)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class LabelCategory(Enum):
    """Categories for labels."""

    FEATURE = "feature"  # Feature area (auth, payments, etc.)
    COMPONENT = "component"  # Technical component (frontend, backend, db)
    TYPE = "type"  # Work type (bug, enhancement, tech-debt)
    PRIORITY = "priority"  # Priority indicators
    PERSONA = "persona"  # User type (admin, customer, developer)
    NFR = "nfr"  # Non-functional requirements (security, performance)
    TEAM = "team"  # Team ownership
    EPIC = "epic"  # Epic/initiative grouping
    CUSTOM = "custom"  # Custom/other labels


@dataclass
class SuggestedLabel:
    """A single suggested label."""

    name: str
    category: LabelCategory
    confidence: str  # "high", "medium", "low"
    reasoning: str
    is_new: bool = False  # True if this is a new label not in current set


@dataclass
class LabelingSuggestion:
    """Labeling suggestions for a single story."""

    story_id: str
    story_title: str
    current_labels: list[str]
    suggested_labels: list[SuggestedLabel] = field(default_factory=list)
    labels_to_add: list[str] = field(default_factory=list)
    labels_to_remove: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Whether any label changes are suggested."""
        return bool(self.labels_to_add or self.labels_to_remove)

    @property
    def final_labels(self) -> list[str]:
        """Final label set after applying suggestions."""
        current = set(self.current_labels)
        current.update(self.labels_to_add)
        current -= set(self.labels_to_remove)
        return sorted(current)


@dataclass
class LabelingResult:
    """Result of AI labeling analysis."""

    success: bool = True
    suggestions: list[LabelingSuggestion] = field(default_factory=list)
    all_labels_used: list[str] = field(default_factory=list)  # All unique labels
    new_labels_suggested: list[str] = field(default_factory=list)  # New labels
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def stories_with_changes(self) -> int:
        """Count of stories with label changes."""
        return sum(1 for s in self.suggestions if s.has_changes)


@dataclass
class LabelingOptions:
    """Options for AI labeling."""

    # Existing labels to consider/prefer
    existing_labels: list[str] = field(default_factory=list)

    # Label categories to suggest
    suggest_features: bool = True
    suggest_components: bool = True
    suggest_types: bool = True
    suggest_personas: bool = False
    suggest_nfr: bool = True

    # Constraints
    max_labels_per_story: int = 5
    allow_new_labels: bool = True
    prefer_existing_labels: bool = True

    # Context
    project_context: str = ""
    tech_stack: str = ""

    # Label conventions
    label_style: str = "kebab-case"  # "kebab-case", "snake_case", "camelCase"


LABELING_SYSTEM_PROMPT = """You are an expert at organizing and categorizing software requirements.
Your task is to analyze user stories and suggest appropriate labels/tags.

Label categories to consider:
1. **Feature Area**: Core functional areas (auth, payments, notifications, dashboard, etc.)
2. **Component**: Technical components (frontend, backend, api, database, mobile, etc.)
3. **Type**: Work type (feature, enhancement, bug-fix, tech-debt, refactor, etc.)
4. **NFR**: Non-functional requirements (security, performance, accessibility, i18n, etc.)
5. **Persona**: User types when relevant (admin, customer, developer, etc.)

Guidelines:
- Use lowercase, kebab-case labels (e.g., "user-auth", "api-integration")
- Be specific but not overly granular
- Prefer existing labels when they fit
- Suggest 2-5 labels per story
- Only suggest removing labels that are clearly wrong
- Provide reasoning for each suggestion

Always respond with valid JSON."""


def build_labeling_prompt(
    stories: list[UserStory],
    options: LabelingOptions,
) -> str:
    """Build the prompt for label suggestions."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format existing labels
    existing_labels_section = ""
    if options.existing_labels:
        existing_labels_section = f"""
## Existing Labels (prefer these when appropriate)
{", ".join(sorted(options.existing_labels))}
"""

    # Format stories
    stories_text = []
    for story in stories:
        current_labels = ", ".join(story.labels) if story.labels else "(none)"

        story_text = f"""
### Story: {story.id} - {story.title}
**Current Labels**: {current_labels}
**Priority**: {story.priority.display_name}

**Description**:
{_format_description(story)}

**Acceptance Criteria**:
{_format_acceptance_criteria(story)}
"""
        stories_text.append(story_text.strip())

    categories = []
    if options.suggest_features:
        categories.append("feature areas")
    if options.suggest_components:
        categories.append("technical components")
    if options.suggest_types:
        categories.append("work types")
    if options.suggest_nfr:
        categories.append("non-functional requirements")
    if options.suggest_personas:
        categories.append("user personas")

    categories_text = ", ".join(categories) if categories else "all categories"

    return f"""Analyze the following user stories and suggest appropriate labels.

## Context
{context_section}

## Label Style
Use {options.label_style} format (e.g., user-auth, api-integration)

## Categories to Consider
{categories_text}

## Constraints
- Maximum {options.max_labels_per_story} labels per story
- {"Prefer existing labels when they fit" if options.prefer_existing_labels else "Suggest best-fit labels"}
- {"New labels allowed" if options.allow_new_labels else "Only use existing labels"}
{existing_labels_section}
## Stories to Label
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing label suggestions:

```json
{{
  "suggestions": [
    {{
      "story_id": "US-001",
      "current_labels": ["frontend"],
      "suggested_labels": [
        {{
          "name": "user-auth",
          "category": "feature",
          "confidence": "high",
          "reasoning": "Story is about user authentication flow"
        }},
        {{
          "name": "security",
          "category": "nfr",
          "confidence": "medium",
          "reasoning": "Authentication implies security considerations"
        }}
      ],
      "labels_to_add": ["user-auth", "security"],
      "labels_to_remove": []
    }}
  ],
  "new_labels_suggested": ["user-auth"]
}}
```

Categories: "feature", "component", "type", "priority", "persona", "nfr", "team", "epic", "custom"
Confidence: "high", "medium", "low"

Analyze and suggest labels now:"""


def _format_description(story: UserStory) -> str:
    """Format story description for analysis."""
    if story.description:
        return f"""As a {story.description.role}
I want {story.description.want}
So that {story.description.benefit}"""
    return "(No description provided)"


def _format_acceptance_criteria(story: UserStory) -> str:
    """Format acceptance criteria for analysis."""
    if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
        lines = []
        for ac, checked in story.acceptance_criteria:
            checkbox = "[x]" if checked else "[ ]"
            lines.append(f"- {checkbox} {ac}")
        return "\n".join(lines)
    return "(No acceptance criteria)"


def parse_labeling_response(
    response: str,
    stories: list[UserStory],
    options: LabelingOptions,
) -> tuple[list[LabelingSuggestion], list[str]]:
    """Parse LLM response into LabelingSuggestion objects."""
    suggestions: list[LabelingSuggestion] = []
    new_labels: list[str] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"suggestions\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return _create_fallback_labels(stories, options), []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_labels(stories, options), []

    raw_suggestions = data.get("suggestions", [])
    new_labels = data.get("new_labels_suggested", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}
    existing_labels_set = set(options.existing_labels)

    for raw in raw_suggestions:
        story_id = raw.get("story_id", "")
        story = story_map.get(story_id)

        if not story:
            continue

        # Parse suggested labels
        suggested_labels = []
        for raw_label in raw.get("suggested_labels", []):
            try:
                category = LabelCategory(raw_label.get("category", "custom"))
            except ValueError:
                category = LabelCategory.CUSTOM

            label_name = _normalize_label(raw_label.get("name", ""), options.label_style)
            is_new = label_name not in existing_labels_set

            suggested_labels.append(
                SuggestedLabel(
                    name=label_name,
                    category=category,
                    confidence=raw_label.get("confidence", "medium"),
                    reasoning=raw_label.get("reasoning", ""),
                    is_new=is_new,
                )
            )

        # Apply constraints
        labels_to_add = raw.get("labels_to_add", [])
        labels_to_add = [_normalize_label(l, options.label_style) for l in labels_to_add]
        labels_to_add = labels_to_add[: options.max_labels_per_story]

        if not options.allow_new_labels:
            labels_to_add = [l for l in labels_to_add if l in existing_labels_set]

        labels_to_remove = raw.get("labels_to_remove", [])
        labels_to_remove = [_normalize_label(l, options.label_style) for l in labels_to_remove]

        suggestion = LabelingSuggestion(
            story_id=story_id,
            story_title=story.title,
            current_labels=list(story.labels) if story.labels else [],
            suggested_labels=suggested_labels,
            labels_to_add=labels_to_add,
            labels_to_remove=labels_to_remove,
        )
        suggestions.append(suggestion)

    return suggestions, new_labels


def _normalize_label(label: str, style: str) -> str:
    """Normalize label to the specified style."""
    # Clean up the label
    label = label.strip().lower()
    label = re.sub(r"[^\w\s-]", "", label)
    words = label.split()

    if style == "snake_case":
        return "_".join(words)
    if style == "camelCase":
        if not words:
            return ""
        return words[0] + "".join(w.capitalize() for w in words[1:])
    # kebab-case (default)
    return "-".join(words)


def _create_fallback_labels(
    stories: list[UserStory],
    options: LabelingOptions,
) -> list[LabelingSuggestion]:
    """Create basic label suggestions when LLM parsing fails."""
    suggestions = []

    # Common keywords to label mappings
    keyword_labels = {
        "login": "auth",
        "authentication": "auth",
        "password": "auth",
        "api": "api",
        "database": "database",
        "frontend": "frontend",
        "backend": "backend",
        "security": "security",
        "performance": "performance",
        "test": "testing",
        "admin": "admin",
        "user": "user-facing",
        "mobile": "mobile",
        "notification": "notifications",
        "email": "email",
        "payment": "payments",
        "search": "search",
    }

    for story in stories:
        detected_labels = []

        # Check title and description for keywords
        content = story.title.lower()
        if story.description:
            content += f" {story.description.want.lower()}"

        for keyword, label in keyword_labels.items():
            if keyword in content and label not in detected_labels:
                detected_labels.append(label)

        # Limit to max labels
        detected_labels = detected_labels[: options.max_labels_per_story]

        # Determine which are new
        labels_to_add = [l for l in detected_labels if l not in (story.labels or [])]

        suggestions.append(
            LabelingSuggestion(
                story_id=str(story.id),
                story_title=story.title,
                current_labels=list(story.labels) if story.labels else [],
                suggested_labels=[
                    SuggestedLabel(
                        name=l,
                        category=LabelCategory.FEATURE,
                        confidence="low",
                        reasoning="Detected from keyword matching",
                    )
                    for l in detected_labels
                ],
                labels_to_add=labels_to_add,
                labels_to_remove=[],
            )
        )

    return suggestions


class AILabeler:
    """
    Suggests labels for user stories using LLM analysis.

    Analyzes story content and suggests appropriate labels based on
    feature areas, components, work types, and more.
    """

    def __init__(
        self,
        options: LabelingOptions | None = None,
    ):
        """
        Initialize the labeler.

        Args:
            options: Labeling options. Uses defaults if not provided.
        """
        self.options = options or LabelingOptions()
        self.logger = logging.getLogger(__name__)

    def label(
        self,
        stories: list[UserStory],
        options: LabelingOptions | None = None,
    ) -> LabelingResult:
        """
        Analyze stories and suggest labels.

        Args:
            stories: List of user stories to label.
            options: Override labeling options.

        Returns:
            LabelingResult with suggestions for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = LabelingResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for labeling"
            return result

        # Collect existing labels from stories
        all_existing = set(opts.existing_labels)
        for story in stories:
            if story.labels:
                all_existing.update(story.labels)
        opts.existing_labels = sorted(all_existing)

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            self.logger.warning(f"LLM not available, using fallback labeling: {e}")
            result.suggestions = _create_fallback_labels(stories, opts)
            result.all_labels_used = _collect_all_labels(result.suggestions)
            return result

        if not manager.is_available():
            self.logger.warning("No LLM providers available, using fallback labeling")
            result.suggestions = _create_fallback_labels(stories, opts)
            result.all_labels_used = _collect_all_labels(result.suggestions)
            return result

        # Build prompt
        prompt = build_labeling_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=LABELING_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            self.logger.warning(f"LLM call failed, using fallback labeling: {e}")
            result.suggestions = _create_fallback_labels(stories, opts)
            result.all_labels_used = _collect_all_labels(result.suggestions)
            return result

        # Parse response
        try:
            result.suggestions, result.new_labels_suggested = parse_labeling_response(
                response.content, stories, opts
            )
            result.all_labels_used = _collect_all_labels(result.suggestions)

            if not result.suggestions:
                result.success = False
                result.error = "No suggestions could be parsed from the response"
                result.suggestions = _create_fallback_labels(stories, opts)
                result.all_labels_used = _collect_all_labels(result.suggestions)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse labeling response: {e}"
            result.suggestions = _create_fallback_labels(stories, opts)
            result.all_labels_used = _collect_all_labels(result.suggestions)

        return result

    def label_from_markdown(
        self,
        markdown_path: str,
        options: LabelingOptions | None = None,
    ) -> LabelingResult:
        """
        Label stories from a markdown file.

        Args:
            markdown_path: Path to markdown file containing stories.
            options: Override labeling options.

        Returns:
            LabelingResult with suggestions for each story.
        """
        from pathlib import Path

        from spectryn.adapters import MarkdownParser

        result = LabelingResult()

        try:
            parser = MarkdownParser()
            stories = parser.parse_stories(Path(markdown_path))
        except Exception as e:
            result.success = False
            result.error = f"Failed to parse markdown file: {e}"
            return result

        if not stories:
            result.success = False
            result.error = "No stories found in the markdown file"
            return result

        return self.label(stories, options)


def _collect_all_labels(suggestions: list[LabelingSuggestion]) -> list[str]:
    """Collect all unique labels from suggestions."""
    all_labels = set()
    for s in suggestions:
        all_labels.update(s.current_labels)
        all_labels.update(s.labels_to_add)
    return sorted(all_labels)


def label_stories(
    stories: list[UserStory],
    project_context: str = "",
    tech_stack: str = "",
    existing_labels: list[str] | None = None,
) -> LabelingResult:
    """
    Convenience function to suggest labels for stories.

    Args:
        stories: List of user stories to label.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.
        existing_labels: Optional list of existing labels to prefer.

    Returns:
        LabelingResult with suggestions for each story.
    """
    options = LabelingOptions(
        project_context=project_context,
        tech_stack=tech_stack,
        existing_labels=existing_labels or [],
    )

    labeler = AILabeler(options)
    return labeler.label(stories, options)
