"""
AI Smart Splitting - Suggest splitting large stories into smaller ones.

Uses LLM providers to analyze user stories and suggest how to split
large/complex stories into smaller, more manageable pieces based on:
- Story point thresholds
- Number of acceptance criteria
- Technical complexity indicators
- Independent deliverable chunks
"""

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    StoryId,
)


logger = logging.getLogger(__name__)


class SplitReason(Enum):
    """Reasons why a story should be split."""

    TOO_LARGE = "too_large"  # Too many story points
    TOO_MANY_AC = "too_many_ac"  # Too many acceptance criteria
    MULTIPLE_FEATURES = "multiple_features"  # Contains multiple distinct features
    MULTIPLE_PERSONAS = "multiple_personas"  # Serves multiple user types
    TECH_COMPLEXITY = "tech_complexity"  # Multiple complex technical areas
    UNCLEAR_SCOPE = "unclear_scope"  # Scope is too broad/vague
    LONG_IMPLEMENTATION = "long_implementation"  # Would take too long


@dataclass
class SplitStory:
    """A suggested split story."""

    title: str
    description: Description | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    suggested_points: int = 0
    rationale: str = ""
    inherited_labels: list[str] = field(default_factory=list)
    technical_notes: str = ""

    def to_user_story(self, story_id: str) -> UserStory:
        """Convert to a UserStory entity."""
        return UserStory(
            id=StoryId.from_string(story_id),
            title=self.title,
            description=self.description,
            acceptance_criteria=AcceptanceCriteria.from_list(self.acceptance_criteria),
            story_points=self.suggested_points,
            priority=Priority.MEDIUM,
            status=Status.PLANNED,
            labels=self.inherited_labels,
        )


@dataclass
class SplitSuggestion:
    """Splitting suggestion for a single story."""

    original_story_id: str
    original_title: str
    original_points: int
    should_split: bool = False
    split_reasons: list[SplitReason] = field(default_factory=list)
    confidence: str = "medium"  # "high", "medium", "low"
    suggested_stories: list[SplitStory] = field(default_factory=list)
    total_suggested_points: int = 0
    explanation: str = ""

    @property
    def num_splits(self) -> int:
        """Number of stories this would be split into."""
        return len(self.suggested_stories)

    @property
    def point_change(self) -> int:
        """Change in total points after split."""
        return self.total_suggested_points - self.original_points


@dataclass
class SplitResult:
    """Result of AI splitting analysis."""

    success: bool = True
    suggestions: list[SplitSuggestion] = field(default_factory=list)
    stories_to_split: int = 0
    total_new_stories: int = 0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def stories_ok(self) -> int:
        """Count of stories that don't need splitting."""
        return len([s for s in self.suggestions if not s.should_split])


@dataclass
class SplitOptions:
    """Options for AI story splitting."""

    # Thresholds for suggesting splits
    max_story_points: int = 8  # Stories above this should be split
    max_acceptance_criteria: int = 8  # Stories with more AC should be split
    min_split_points: int = 1  # Minimum points for split stories

    # Splitting preferences
    prefer_vertical_slices: bool = True  # Prefer end-to-end slices
    prefer_mvp_first: bool = True  # Suggest MVP version first
    maintain_independence: bool = True  # Each split should be independently valuable

    # Context
    project_context: str = ""
    tech_stack: str = ""
    team_size: int = 0

    # ID generation
    id_prefix: str = ""  # Auto-detect from original story if empty
    id_suffix_style: str = "letter"  # "letter" (a,b,c) or "number" (1,2,3)


SPLITTING_SYSTEM_PROMPT = """You are an expert agile coach specializing in user story refinement.
Your task is to analyze user stories and suggest how to split large/complex stories into smaller ones.

INVEST Principles for good stories:
- Independent: Can be developed without dependencies on other stories
- Negotiable: Details can be discussed, not a rigid contract
- Valuable: Delivers value to the user or business
- Estimable: Team can estimate the effort required
- Small: Can be completed in one sprint (typically 1-8 points)
- Testable: Has clear acceptance criteria

Splitting strategies:
1. **Vertical slices**: Split by end-to-end functionality (preferred)
2. **Workflow steps**: Split by user workflow stages
3. **Business rules**: Split by different business rules/variations
4. **Data variations**: Split by data types or sources
5. **Operations**: Split by CRUD operations
6. **Personas**: Split by user types if very different
7. **Platform**: Split by platform (web, mobile, API)

Guidelines:
- Each split story should be independently valuable
- Maintain roughly equal size across splits
- First split can be MVP, others add features
- Keep acceptance criteria specific and testable
- Total points of splits may exceed original (that's okay)

Always respond with valid JSON."""


def build_splitting_prompt(
    stories: list[UserStory],
    options: SplitOptions,
) -> str:
    """Build the prompt for splitting suggestions."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")
    if options.team_size > 0:
        context_parts.append(f"Team Size: {options.team_size} developers")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format stories
    stories_text = []
    for story in stories:
        ac_list = _format_acceptance_criteria(story)
        ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0

        story_text = f"""
### Story: {story.id} - {story.title}
**Story Points**: {story.story_points or "Not estimated"}
**Acceptance Criteria Count**: {ac_count}
**Priority**: {story.priority.display_name}

**Description**:
{_format_description(story)}

**Acceptance Criteria**:
{ac_list}

**Labels**: {", ".join(story.labels) if story.labels else "(none)"}
"""
        stories_text.append(story_text.strip())

    return f"""Analyze the following user stories and suggest which ones should be split into smaller stories.

## Context
{context_section}

## Splitting Thresholds
- Maximum story points before splitting: {options.max_story_points}
- Maximum acceptance criteria before splitting: {options.max_acceptance_criteria}
- Minimum points per split story: {options.min_split_points}

## Splitting Preferences
- Prefer vertical slices (end-to-end): {"Yes" if options.prefer_vertical_slices else "No"}
- Suggest MVP version first: {"Yes" if options.prefer_mvp_first else "No"}
- Ensure independent value: {"Yes" if options.maintain_independence else "No"}

## Stories to Analyze
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing splitting suggestions:

```json
{{
  "suggestions": [
    {{
      "original_story_id": "US-001",
      "original_title": "Large Story Title",
      "original_points": 13,
      "should_split": true,
      "split_reasons": ["too_large", "multiple_features"],
      "confidence": "high",
      "explanation": "This story contains both API and UI work that can be delivered independently.",
      "suggested_stories": [
        {{
          "title": "API endpoint for feature X",
          "description": {{
            "role": "API consumer",
            "want": "an endpoint to do X",
            "benefit": "I can integrate with the system"
          }},
          "acceptance_criteria": [
            "Endpoint returns 200 on success",
            "Returns proper error codes"
          ],
          "suggested_points": 5,
          "rationale": "Backend work can be completed and tested independently",
          "inherited_labels": ["api", "backend"],
          "technical_notes": "Uses existing auth middleware"
        }},
        {{
          "title": "UI for feature X",
          "description": {{
            "role": "end user",
            "want": "a UI to do X",
            "benefit": "I can use the feature visually"
          }},
          "acceptance_criteria": [
            "Form validates input",
            "Shows success/error messages"
          ],
          "suggested_points": 5,
          "rationale": "Frontend work depends on API but has independent value for demo",
          "inherited_labels": ["ui", "frontend"],
          "technical_notes": "Can use mock data initially"
        }}
      ],
      "total_suggested_points": 10
    }},
    {{
      "original_story_id": "US-002",
      "original_title": "Small Story",
      "original_points": 3,
      "should_split": false,
      "split_reasons": [],
      "confidence": "high",
      "explanation": "Story is appropriately sized and focused.",
      "suggested_stories": [],
      "total_suggested_points": 3
    }}
  ]
}}
```

Split reasons: "too_large", "too_many_ac", "multiple_features", "multiple_personas", "tech_complexity", "unclear_scope", "long_implementation"
Confidence: "high", "medium", "low"

Analyze and suggest splits now:"""


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


def parse_splitting_response(
    response: str,
    stories: list[UserStory],
    options: SplitOptions,
) -> list[SplitSuggestion]:
    """Parse LLM response into SplitSuggestion objects."""
    suggestions: list[SplitSuggestion] = []

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
            return _create_fallback_suggestions(stories, options)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_suggestions(stories, options)

    raw_suggestions = data.get("suggestions", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}

    for raw in raw_suggestions:
        story_id = raw.get("original_story_id", "")
        story = story_map.get(story_id)

        if not story:
            continue

        # Parse split reasons
        split_reasons = []
        for reason_str in raw.get("split_reasons", []):
            with contextlib.suppress(ValueError):
                split_reasons.append(SplitReason(reason_str))

        # Parse suggested stories
        suggested_stories = []
        for raw_story in raw.get("suggested_stories", []):
            desc = None
            if raw_story.get("description"):
                desc_data = raw_story["description"]
                desc = Description(
                    role=desc_data.get("role", "user"),
                    want=desc_data.get("want", ""),
                    benefit=desc_data.get("benefit", ""),
                )

            split_story = SplitStory(
                title=raw_story.get("title", ""),
                description=desc,
                acceptance_criteria=raw_story.get("acceptance_criteria", []),
                suggested_points=raw_story.get("suggested_points", 0),
                rationale=raw_story.get("rationale", ""),
                inherited_labels=raw_story.get("inherited_labels", []),
                technical_notes=raw_story.get("technical_notes", ""),
            )
            suggested_stories.append(split_story)

        suggestion = SplitSuggestion(
            original_story_id=story_id,
            original_title=story.title,
            original_points=story.story_points or 0,
            should_split=raw.get("should_split", False),
            split_reasons=split_reasons,
            confidence=raw.get("confidence", "medium"),
            suggested_stories=suggested_stories,
            total_suggested_points=raw.get("total_suggested_points", 0),
            explanation=raw.get("explanation", ""),
        )
        suggestions.append(suggestion)

    return suggestions


def _create_fallback_suggestions(
    stories: list[UserStory],
    options: SplitOptions,
) -> list[SplitSuggestion]:
    """Create basic split suggestions when LLM parsing fails."""
    suggestions = []

    for story in stories:
        points = story.story_points or 0
        ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0

        should_split = False
        split_reasons = []

        # Check thresholds
        if points > options.max_story_points:
            should_split = True
            split_reasons.append(SplitReason.TOO_LARGE)

        if ac_count > options.max_acceptance_criteria:
            should_split = True
            split_reasons.append(SplitReason.TOO_MANY_AC)

        # Simple heuristic split
        suggested_stories = []
        if should_split and story.acceptance_criteria:
            # Split by acceptance criteria groups
            ac_list = list(story.acceptance_criteria)
            mid = len(ac_list) // 2

            # First split
            split1 = SplitStory(
                title=f"{story.title} - Part 1",
                description=story.description,
                acceptance_criteria=[ac for ac, _ in ac_list[:mid]],
                suggested_points=max(options.min_split_points, points // 2),
                rationale="First half of acceptance criteria",
                inherited_labels=list(story.labels) if story.labels else [],
            )
            suggested_stories.append(split1)

            # Second split
            split2 = SplitStory(
                title=f"{story.title} - Part 2",
                description=story.description,
                acceptance_criteria=[ac for ac, _ in ac_list[mid:]],
                suggested_points=max(options.min_split_points, points - points // 2),
                rationale="Second half of acceptance criteria",
                inherited_labels=list(story.labels) if story.labels else [],
            )
            suggested_stories.append(split2)

        total_points = sum(s.suggested_points for s in suggested_stories)

        suggestions.append(
            SplitSuggestion(
                original_story_id=str(story.id),
                original_title=story.title,
                original_points=points,
                should_split=should_split,
                split_reasons=split_reasons,
                confidence="low",
                suggested_stories=suggested_stories,
                total_suggested_points=total_points if suggested_stories else points,
                explanation="Based on size thresholds"
                if should_split
                else "Story is appropriately sized",
            )
        )

    return suggestions


class AIStorySplitter:
    """
    Suggests splitting large user stories using LLM analysis.

    Analyzes story size, complexity, and scope to suggest how to
    break down large stories into smaller, more manageable pieces.
    """

    def __init__(
        self,
        options: SplitOptions | None = None,
    ):
        """
        Initialize the splitter.

        Args:
            options: Splitting options. Uses defaults if not provided.
        """
        self.options = options or SplitOptions()
        self.logger = logging.getLogger(__name__)

    def analyze(
        self,
        stories: list[UserStory],
        options: SplitOptions | None = None,
    ) -> SplitResult:
        """
        Analyze stories and suggest splits.

        Args:
            stories: List of user stories to analyze.
            options: Override splitting options.

        Returns:
            SplitResult with suggestions for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = SplitResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for splitting analysis"
            return result

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            self.logger.warning(f"LLM not available, using fallback analysis: {e}")
            result.suggestions = _create_fallback_suggestions(stories, opts)
            self._update_result_stats(result)
            return result

        if not manager.is_available():
            self.logger.warning("No LLM providers available, using fallback analysis")
            result.suggestions = _create_fallback_suggestions(stories, opts)
            self._update_result_stats(result)
            return result

        # Build prompt
        prompt = build_splitting_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=SPLITTING_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            self.logger.warning(f"LLM call failed, using fallback analysis: {e}")
            result.suggestions = _create_fallback_suggestions(stories, opts)
            self._update_result_stats(result)
            return result

        # Parse response
        try:
            result.suggestions = parse_splitting_response(response.content, stories, opts)

            if not result.suggestions:
                result.success = False
                result.error = "No suggestions could be parsed from the response"
                result.suggestions = _create_fallback_suggestions(stories, opts)

            self._update_result_stats(result)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse splitting response: {e}"
            result.suggestions = _create_fallback_suggestions(stories, opts)
            self._update_result_stats(result)

        return result

    def _update_result_stats(self, result: SplitResult) -> None:
        """Update result statistics."""
        result.stories_to_split = sum(1 for s in result.suggestions if s.should_split)
        result.total_new_stories = sum(s.num_splits for s in result.suggestions if s.should_split)

    def generate_split_ids(
        self,
        original_id: str,
        num_splits: int,
        options: SplitOptions | None = None,
    ) -> list[str]:
        """
        Generate IDs for split stories.

        Args:
            original_id: Original story ID (e.g., "US-001")
            num_splits: Number of splits needed
            options: Override splitting options

        Returns:
            List of new IDs (e.g., ["US-001a", "US-001b"])
        """
        opts = options or self.options

        if opts.id_suffix_style == "number":
            return [f"{original_id}.{i + 1}" for i in range(num_splits)]
        # letter
        letters = "abcdefghijklmnopqrstuvwxyz"
        return [f"{original_id}{letters[i]}" for i in range(min(num_splits, 26))]


def suggest_splits(
    stories: list[UserStory],
    max_points: int = 8,
    project_context: str = "",
    tech_stack: str = "",
) -> SplitResult:
    """
    Convenience function to suggest story splits.

    Args:
        stories: List of user stories to analyze.
        max_points: Maximum story points before suggesting split.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.

    Returns:
        SplitResult with suggestions for each story.
    """
    options = SplitOptions(
        max_story_points=max_points,
        project_context=project_context,
        tech_stack=tech_stack,
    )

    splitter = AIStorySplitter(options)
    return splitter.analyze(stories, options)
