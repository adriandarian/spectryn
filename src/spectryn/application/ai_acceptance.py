"""
AI Acceptance Criteria Generation - Generate AC from story descriptions.

Uses LLM providers to analyze user story descriptions and generate
comprehensive, testable acceptance criteria based on:
- User story description (As a... I want... So that...)
- Technical context
- Best practices for AC writing
"""

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class ACStyle(Enum):
    """Styles for acceptance criteria."""

    GIVEN_WHEN_THEN = "gherkin"  # Given/When/Then format
    CHECKLIST = "checklist"  # Simple checkbox list
    NUMBERED = "numbered"  # Numbered list
    BULLET = "bullet"  # Bullet points


class ACCategory(Enum):
    """Categories for acceptance criteria."""

    FUNCTIONAL = "functional"  # Core functionality
    VALIDATION = "validation"  # Input validation
    ERROR_HANDLING = "error_handling"  # Error cases
    EDGE_CASE = "edge_case"  # Edge cases
    SECURITY = "security"  # Security requirements
    PERFORMANCE = "performance"  # Performance requirements
    ACCESSIBILITY = "accessibility"  # A11y requirements
    UX = "ux"  # User experience


@dataclass
class GeneratedAC:
    """A single generated acceptance criterion."""

    text: str
    category: ACCategory = ACCategory.FUNCTIONAL
    is_gherkin: bool = False
    given: str = ""
    when: str = ""
    then: str = ""

    def to_checklist_item(self) -> str:
        """Format as a checklist item."""
        return f"- [ ] {self.text}"

    def to_gherkin(self) -> str:
        """Format as Gherkin syntax."""
        if self.is_gherkin and self.given and self.when and self.then:
            return f"Given {self.given}\nWhen {self.when}\nThen {self.then}"
        return self.text


@dataclass
class ACGenerationSuggestion:
    """AC generation suggestions for a single story."""

    story_id: str
    story_title: str
    current_ac_count: int
    generated_ac: list[GeneratedAC] = field(default_factory=list)
    has_missing_categories: list[ACCategory] = field(default_factory=list)
    explanation: str = ""

    @property
    def num_generated(self) -> int:
        """Number of generated AC."""
        return len(self.generated_ac)

    def get_ac_by_category(self, category: ACCategory) -> list[GeneratedAC]:
        """Get AC for a specific category."""
        return [ac for ac in self.generated_ac if ac.category == category]


@dataclass
class ACGenerationResult:
    """Result of AI AC generation."""

    success: bool = True
    suggestions: list[ACGenerationSuggestion] = field(default_factory=list)
    total_ac_generated: int = 0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def stories_with_new_ac(self) -> int:
        """Count of stories with generated AC."""
        return sum(1 for s in self.suggestions if s.num_generated > 0)


@dataclass
class ACGenerationOptions:
    """Options for AC generation."""

    # Style preferences
    style: ACStyle = ACStyle.CHECKLIST
    use_gherkin: bool = False

    # Content preferences
    include_validation: bool = True
    include_error_handling: bool = True
    include_edge_cases: bool = True
    include_security: bool = False
    include_performance: bool = False
    include_accessibility: bool = False

    # Constraints
    min_ac_count: int = 3
    max_ac_count: int = 8
    keep_existing: bool = True  # Keep existing AC

    # Context
    project_context: str = ""
    tech_stack: str = ""
    domain_terms: list[str] = field(default_factory=list)


AC_GENERATION_SYSTEM_PROMPT = """You are an expert agile coach and QA engineer specializing in writing acceptance criteria.
Your task is to analyze user stories and generate comprehensive, testable acceptance criteria.

Guidelines for good acceptance criteria:
1. **Specific**: Clearly define what "done" looks like
2. **Measurable**: Can be objectively verified
3. **Achievable**: Within scope of the story
4. **Relevant**: Directly related to the user's need
5. **Testable**: Can be verified with a test

Types of AC to consider:
- **Functional**: Core functionality that must work
- **Validation**: Input validation rules
- **Error Handling**: What happens when things go wrong
- **Edge Cases**: Boundary conditions and special scenarios
- **Security**: Authentication, authorization, data protection (when relevant)
- **Performance**: Response times, throughput (when relevant)

AC Formats:
1. **Checklist**: Simple statements that can be checked off
   - User can click the submit button
   - Form shows error for invalid email

2. **Gherkin** (Given/When/Then):
   - Given I am on the login page
   - When I enter valid credentials
   - Then I am redirected to the dashboard

Tips:
- Start with the happy path (main success scenario)
- Cover validation and error cases
- Be specific about expected behavior
- Avoid implementation details
- Use domain language from the story

Always respond with valid JSON."""


def build_ac_generation_prompt(
    stories: list[UserStory],
    options: ACGenerationOptions,
) -> str:
    """Build the prompt for AC generation."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")
    if options.domain_terms:
        context_parts.append(f"Domain Terms: {', '.join(options.domain_terms)}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Build categories to include
    categories = ["functional"]
    if options.include_validation:
        categories.append("validation")
    if options.include_error_handling:
        categories.append("error_handling")
    if options.include_edge_cases:
        categories.append("edge_case")
    if options.include_security:
        categories.append("security")
    if options.include_performance:
        categories.append("performance")
    if options.include_accessibility:
        categories.append("accessibility")

    # Format stories
    stories_text = []
    for story in stories:
        existing_ac = _format_existing_ac(story)
        story_text = f"""
### Story: {story.id} - {story.title}

**Description**:
{_format_description(story)}

**Existing Acceptance Criteria** ({len(story.acceptance_criteria) if story.acceptance_criteria else 0}):
{existing_ac}

**Labels**: {", ".join(story.labels) if story.labels else "(none)"}
**Story Points**: {story.story_points or "Not estimated"}
"""
        stories_text.append(story_text.strip())

    style_instruction = ""
    if options.use_gherkin:
        style_instruction = """
## Format
Use Gherkin (Given/When/Then) format for each AC:
- Given: The precondition or context
- When: The action taken
- Then: The expected outcome
"""
    else:
        style_instruction = """
## Format
Use simple checklist format - clear, concise statements that can be verified.
"""

    return f"""Generate acceptance criteria for the following user stories.

## Context
{context_section}

## Categories to Include
{", ".join(categories)}

## Constraints
- Minimum AC per story: {options.min_ac_count}
- Maximum AC per story: {options.max_ac_count}
- {"Keep existing AC and add new ones" if options.keep_existing else "Generate fresh AC (may replace existing)"}
{style_instruction}
## Stories
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing generated AC:

```json
{{
  "suggestions": [
    {{
      "story_id": "US-001",
      "story_title": "User Login",
      "current_ac_count": 2,
      "explanation": "Added validation and error handling AC",
      "generated_ac": [
        {{
          "text": "User can submit login form with valid email and password",
          "category": "functional",
          "is_gherkin": false
        }},
        {{
          "text": "Form shows error message for invalid email format",
          "category": "validation",
          "is_gherkin": false
        }},
        {{
          "text": "User sees 'Invalid credentials' error for wrong password",
          "category": "error_handling",
          "is_gherkin": false
        }}
      ],
      "has_missing_categories": ["edge_case"]
    }}
  ]
}}
```

For Gherkin format, include given/when/then fields:
```json
{{
  "text": "User login with valid credentials",
  "category": "functional",
  "is_gherkin": true,
  "given": "I am on the login page",
  "when": "I enter valid credentials and click submit",
  "then": "I am redirected to the dashboard"
}}
```

Categories: "functional", "validation", "error_handling", "edge_case", "security", "performance", "accessibility", "ux"

Generate acceptance criteria now:"""


def _format_description(story: UserStory) -> str:
    """Format story description for analysis."""
    if story.description:
        return f"""As a {story.description.role}
I want {story.description.want}
So that {story.description.benefit}"""
    return "(No description provided)"


def _format_existing_ac(story: UserStory) -> str:
    """Format existing acceptance criteria."""
    if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
        lines = []
        for ac, checked in story.acceptance_criteria:
            checkbox = "[x]" if checked else "[ ]"
            lines.append(f"- {checkbox} {ac}")
        return "\n".join(lines)
    return "(No existing acceptance criteria)"


def parse_ac_generation_response(
    response: str,
    stories: list[UserStory],
    options: ACGenerationOptions,
) -> list[ACGenerationSuggestion]:
    """Parse LLM response into ACGenerationSuggestion objects."""
    suggestions: list[ACGenerationSuggestion] = []

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
            return _create_fallback_ac(stories, options)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_ac(stories, options)

    raw_suggestions = data.get("suggestions", [])

    # Create a mapping from story ID to story
    story_map = {str(s.id): s for s in stories}

    for raw in raw_suggestions:
        story_id = raw.get("story_id", "")
        story = story_map.get(story_id)

        if not story:
            continue

        # Parse generated AC
        generated_ac = []
        for raw_ac in raw.get("generated_ac", []):
            try:
                category = ACCategory(raw_ac.get("category", "functional"))
            except ValueError:
                category = ACCategory.FUNCTIONAL

            ac = GeneratedAC(
                text=raw_ac.get("text", ""),
                category=category,
                is_gherkin=raw_ac.get("is_gherkin", False),
                given=raw_ac.get("given", ""),
                when=raw_ac.get("when", ""),
                then=raw_ac.get("then", ""),
            )
            generated_ac.append(ac)

        # Parse missing categories
        missing_categories = []
        for cat_str in raw.get("has_missing_categories", []):
            with contextlib.suppress(ValueError):
                missing_categories.append(ACCategory(cat_str))

        # Apply max constraint
        generated_ac = generated_ac[: options.max_ac_count]

        suggestion = ACGenerationSuggestion(
            story_id=story_id,
            story_title=story.title,
            current_ac_count=len(story.acceptance_criteria) if story.acceptance_criteria else 0,
            generated_ac=generated_ac,
            has_missing_categories=missing_categories,
            explanation=raw.get("explanation", ""),
        )
        suggestions.append(suggestion)

    return suggestions


def _create_fallback_ac(
    stories: list[UserStory],
    options: ACGenerationOptions,
) -> list[ACGenerationSuggestion]:
    """Create basic AC when LLM parsing fails."""
    suggestions = []

    for story in stories:
        generated_ac = []

        # Generate basic AC from description
        if story.description:
            # Happy path
            generated_ac.append(
                GeneratedAC(
                    text=f"User can {story.description.want}",
                    category=ACCategory.FUNCTIONAL,
                )
            )

            # Validation
            if options.include_validation:
                generated_ac.append(
                    GeneratedAC(
                        text="All required fields are validated before submission",
                        category=ACCategory.VALIDATION,
                    )
                )

            # Error handling
            if options.include_error_handling:
                generated_ac.append(
                    GeneratedAC(
                        text="Appropriate error messages are shown for invalid input",
                        category=ACCategory.ERROR_HANDLING,
                    )
                )

            # Success feedback
            generated_ac.append(
                GeneratedAC(
                    text="User receives confirmation when action is completed",
                    category=ACCategory.FUNCTIONAL,
                )
            )

        current_ac_count = len(story.acceptance_criteria) if story.acceptance_criteria else 0

        suggestions.append(
            ACGenerationSuggestion(
                story_id=str(story.id),
                story_title=story.title,
                current_ac_count=current_ac_count,
                generated_ac=generated_ac,
                explanation="Generated from story description (fallback)",
            )
        )

    return suggestions


class AIAcceptanceCriteriaGenerator:
    """
    Generates acceptance criteria for user stories using LLM analysis.

    Analyzes story descriptions and generates comprehensive,
    testable acceptance criteria.
    """

    def __init__(
        self,
        options: ACGenerationOptions | None = None,
    ):
        """
        Initialize the generator.

        Args:
            options: Generation options. Uses defaults if not provided.
        """
        self.options = options or ACGenerationOptions()
        self.logger = logging.getLogger(__name__)

    def generate(
        self,
        stories: list[UserStory],
        options: ACGenerationOptions | None = None,
    ) -> ACGenerationResult:
        """
        Generate acceptance criteria for stories.

        Args:
            stories: List of user stories to generate AC for.
            options: Override generation options.

        Returns:
            ACGenerationResult with suggestions for each story.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = ACGenerationResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for AC generation"
            return result

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            self.logger.warning(f"LLM not available, using fallback generation: {e}")
            result.suggestions = _create_fallback_ac(stories, opts)
            self._update_result_stats(result)
            return result

        if not manager.is_available():
            self.logger.warning("No LLM providers available, using fallback generation")
            result.suggestions = _create_fallback_ac(stories, opts)
            self._update_result_stats(result)
            return result

        # Build prompt
        prompt = build_ac_generation_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=AC_GENERATION_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            self.logger.warning(f"LLM call failed, using fallback generation: {e}")
            result.suggestions = _create_fallback_ac(stories, opts)
            self._update_result_stats(result)
            return result

        # Parse response
        try:
            result.suggestions = parse_ac_generation_response(response.content, stories, opts)

            if not result.suggestions:
                result.success = False
                result.error = "No suggestions could be parsed from the response"
                result.suggestions = _create_fallback_ac(stories, opts)

            self._update_result_stats(result)

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse AC generation response: {e}"
            result.suggestions = _create_fallback_ac(stories, opts)
            self._update_result_stats(result)

        return result

    def _update_result_stats(self, result: ACGenerationResult) -> None:
        """Update result statistics."""
        result.total_ac_generated = sum(s.num_generated for s in result.suggestions)


def generate_acceptance_criteria(
    stories: list[UserStory],
    use_gherkin: bool = False,
    project_context: str = "",
    tech_stack: str = "",
) -> ACGenerationResult:
    """
    Convenience function to generate AC for stories.

    Args:
        stories: List of user stories.
        use_gherkin: Use Given/When/Then format.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.

    Returns:
        ACGenerationResult with generated AC for each story.
    """
    options = ACGenerationOptions(
        use_gherkin=use_gherkin,
        project_context=project_context,
        tech_stack=tech_stack,
    )

    generator = AIAcceptanceCriteriaGenerator(options)
    return generator.generate(stories, options)
