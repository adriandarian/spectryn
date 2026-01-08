"""
AI Dependency Detection - Identify blocked-by relationships between stories.

Uses LLM providers to analyze user stories and detect dependencies based on:
- Technical dependencies (API before UI, backend before frontend)
- Data dependencies (data model before CRUD operations)
- Feature dependencies (login before authenticated features)
- Logical ordering (setup before configuration)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from spectryn.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of dependencies between stories."""

    BLOCKS = "blocks"  # This story blocks another
    BLOCKED_BY = "blocked_by"  # This story is blocked by another
    RELATED = "related"  # Stories are related but not blocking
    PARENT_CHILD = "parent_child"  # Hierarchical relationship
    SEQUENCE = "sequence"  # Should be done in sequence


class DependencyStrength(Enum):
    """Strength of the dependency relationship."""

    HARD = "hard"  # Must be completed first
    SOFT = "soft"  # Should be completed first, but not required
    SUGGESTED = "suggested"  # Recommended ordering


@dataclass
class DetectedDependency:
    """A detected dependency between two stories."""

    from_story_id: str
    to_story_id: str
    dependency_type: DependencyType
    strength: DependencyStrength
    reason: str
    confidence: str = "medium"  # "high", "medium", "low"

    @property
    def is_blocking(self) -> bool:
        """Whether this is a blocking dependency."""
        return self.dependency_type in (DependencyType.BLOCKS, DependencyType.BLOCKED_BY)


@dataclass
class StoryDependencies:
    """Dependencies for a single story."""

    story_id: str
    story_title: str
    blocks: list[str] = field(default_factory=list)  # Stories this blocks
    blocked_by: list[str] = field(default_factory=list)  # Stories blocking this
    related_to: list[str] = field(default_factory=list)  # Related stories
    dependencies: list[DetectedDependency] = field(default_factory=list)

    @property
    def has_blockers(self) -> bool:
        """Whether this story has blocking dependencies."""
        return len(self.blocked_by) > 0

    @property
    def is_blocker(self) -> bool:
        """Whether this story blocks others."""
        return len(self.blocks) > 0

    @property
    def total_dependencies(self) -> int:
        """Total number of dependencies."""
        return len(self.blocks) + len(self.blocked_by) + len(self.related_to)


@dataclass
class DependencyResult:
    """Result of AI dependency detection."""

    success: bool = True
    story_dependencies: list[StoryDependencies] = field(default_factory=list)
    all_dependencies: list[DetectedDependency] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    suggested_order: list[str] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def total_dependencies(self) -> int:
        """Total number of dependencies detected."""
        return len(self.all_dependencies)

    @property
    def stories_with_blockers(self) -> int:
        """Count of stories that are blocked."""
        return sum(1 for s in self.story_dependencies if s.has_blockers)

    @property
    def has_circular(self) -> bool:
        """Whether circular dependencies were detected."""
        return len(self.circular_dependencies) > 0


@dataclass
class DependencyOptions:
    """Options for dependency detection."""

    # Detection preferences
    detect_technical: bool = True  # Technical dependencies
    detect_data: bool = True  # Data model dependencies
    detect_feature: bool = True  # Feature-level dependencies
    detect_related: bool = True  # Non-blocking relationships

    # Analysis
    check_circular: bool = True  # Check for circular dependencies
    suggest_order: bool = True  # Suggest execution order

    # Context
    project_context: str = ""
    tech_stack: str = ""
    architecture: str = ""  # e.g., "microservices", "monolith"


DEPENDENCY_SYSTEM_PROMPT = """You are an expert software architect specializing in project planning and dependency analysis.
Your task is to analyze user stories and identify dependencies between them.

Types of dependencies to look for:

1. **Technical Dependencies**:
   - Backend before frontend
   - API before UI that consumes it
   - Database schema before CRUD operations
   - Authentication before protected features
   - Core libraries before features using them

2. **Data Dependencies**:
   - Data model before operations on that data
   - Import before processing
   - Configuration before features using it

3. **Feature Dependencies**:
   - User registration before user profile
   - Basic features before advanced features
   - Core functionality before extensions

4. **Infrastructure Dependencies**:
   - Setup before configuration
   - Environment before deployment features
   - Monitoring before alerting

Guidelines:
- Only identify meaningful dependencies
- Avoid over-linking stories
- Consider the "could this be done in parallel?" test
- Hard dependencies: MUST be done first
- Soft dependencies: SHOULD be done first but could work around
- Focus on blocked_by relationships (what must be done before this story)

Always respond with valid JSON."""


def build_dependency_prompt(
    stories: list[UserStory],
    options: DependencyOptions,
) -> str:
    """Build the prompt for dependency detection."""
    context_parts = []
    if options.project_context:
        context_parts.append(f"Project Context: {options.project_context}")
    if options.tech_stack:
        context_parts.append(f"Tech Stack: {options.tech_stack}")
    if options.architecture:
        context_parts.append(f"Architecture: {options.architecture}")

    context_section = (
        "\n".join(context_parts) if context_parts else "No additional context provided."
    )

    # Format stories
    stories_text = []
    for story in stories:
        story_text = f"""
### {story.id}: {story.title}
**Description**: {_format_description(story)}
**Labels**: {", ".join(story.labels) if story.labels else "(none)"}
**Story Points**: {story.story_points or "Not estimated"}
"""
        stories_text.append(story_text.strip())

    # Build detection categories
    categories = []
    if options.detect_technical:
        categories.append("technical (backend/frontend, API/UI)")
    if options.detect_data:
        categories.append("data (models, schemas, imports)")
    if options.detect_feature:
        categories.append("feature (core before advanced)")
    if options.detect_related:
        categories.append("related (non-blocking connections)")

    return f"""Analyze the following user stories and identify dependencies between them.

## Context
{context_section}

## Dependency Categories to Detect
{", ".join(categories)}

## Stories to Analyze
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing detected dependencies:

```json
{{
  "dependencies": [
    {{
      "from_story_id": "US-001",
      "to_story_id": "US-002",
      "dependency_type": "blocked_by",
      "strength": "hard",
      "reason": "US-001 requires the API from US-002 to be completed first",
      "confidence": "high"
    }},
    {{
      "from_story_id": "US-003",
      "to_story_id": "US-001",
      "dependency_type": "related",
      "strength": "soft",
      "reason": "Both stories modify the user profile, may cause conflicts",
      "confidence": "medium"
    }}
  ],
  "circular_dependencies": [],
  "suggested_order": ["US-002", "US-001", "US-003"],
  "analysis_notes": "US-002 should be done first as it provides the core API"
}}
```

Dependency types: "blocks", "blocked_by", "related", "sequence"
Strength: "hard" (must be first), "soft" (should be first), "suggested" (recommended)
Confidence: "high", "medium", "low"

Analyze dependencies now:"""


def _format_description(story: UserStory) -> str:
    """Format story description for analysis."""
    if story.description:
        return f"As a {story.description.role}, I want {story.description.want}, so that {story.description.benefit}"
    return "(No description)"


def parse_dependency_response(
    response: str,
    stories: list[UserStory],
    options: DependencyOptions,
) -> tuple[list[DetectedDependency], list[list[str]], list[str]]:
    """Parse LLM response into dependency objects."""
    dependencies: list[DetectedDependency] = []
    circular: list[list[str]] = []
    suggested_order: list[str] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"dependencies\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return _create_fallback_dependencies(stories, options), [], []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return _create_fallback_dependencies(stories, options), [], []

    # Valid story IDs
    valid_ids = {str(s.id) for s in stories}

    # Parse dependencies
    for raw_dep in data.get("dependencies", []):
        from_id = raw_dep.get("from_story_id", "")
        to_id = raw_dep.get("to_story_id", "")

        # Validate story IDs
        if from_id not in valid_ids or to_id not in valid_ids:
            continue

        # Skip self-references
        if from_id == to_id:
            continue

        # Parse type
        try:
            dep_type = DependencyType(raw_dep.get("dependency_type", "related"))
        except ValueError:
            dep_type = DependencyType.RELATED

        # Parse strength
        try:
            strength = DependencyStrength(raw_dep.get("strength", "soft"))
        except ValueError:
            strength = DependencyStrength.SOFT

        dep = DetectedDependency(
            from_story_id=from_id,
            to_story_id=to_id,
            dependency_type=dep_type,
            strength=strength,
            reason=raw_dep.get("reason", ""),
            confidence=raw_dep.get("confidence", "medium"),
        )
        dependencies.append(dep)

    # Parse circular dependencies
    for cycle in data.get("circular_dependencies", []):
        if isinstance(cycle, list) and all(c in valid_ids for c in cycle):
            circular.append(cycle)

    # Parse suggested order
    order = data.get("suggested_order", [])
    suggested_order = [o for o in order if o in valid_ids]

    return dependencies, circular, suggested_order


def _create_fallback_dependencies(
    stories: list[UserStory],
    options: DependencyOptions,
) -> list[DetectedDependency]:
    """Create basic dependencies when LLM parsing fails."""
    dependencies = []

    # Simple keyword-based detection
    backend_keywords = ["api", "backend", "database", "db", "server", "endpoint"]
    frontend_keywords = ["ui", "frontend", "page", "screen", "component", "view"]
    auth_keywords = ["login", "auth", "authentication", "register", "signup"]

    # Find potential backend stories
    backend_stories = []
    frontend_stories = []
    auth_stories = []

    for story in stories:
        content = story.title.lower()
        if story.description:
            content += f" {story.description.want.lower()}"

        labels_str = " ".join(story.labels).lower() if story.labels else ""
        content += f" {labels_str}"

        if any(kw in content for kw in backend_keywords):
            backend_stories.append(str(story.id))
        if any(kw in content for kw in frontend_keywords):
            frontend_stories.append(str(story.id))
        if any(kw in content for kw in auth_keywords):
            auth_stories.append(str(story.id))

    # Frontend depends on backend
    for fe_id in frontend_stories:
        for be_id in backend_stories:
            if fe_id != be_id:
                dependencies.append(
                    DetectedDependency(
                        from_story_id=fe_id,
                        to_story_id=be_id,
                        dependency_type=DependencyType.BLOCKED_BY,
                        strength=DependencyStrength.SOFT,
                        reason="Frontend typically depends on backend API",
                        confidence="low",
                    )
                )
                break  # Only one dependency per frontend story

    # Other features may depend on auth
    if auth_stories:
        auth_id = auth_stories[0]
        for story in stories:
            sid = str(story.id)
            if sid != auth_id and sid not in auth_stories:
                content = story.title.lower()
                if story.description:
                    content += f" {story.description.want.lower()}"
                # Check if story seems to require authentication
                if any(kw in content for kw in ["user", "profile", "account", "dashboard"]):
                    dependencies.append(
                        DetectedDependency(
                            from_story_id=sid,
                            to_story_id=auth_id,
                            dependency_type=DependencyType.BLOCKED_BY,
                            strength=DependencyStrength.SUGGESTED,
                            reason="May require authentication to be implemented first",
                            confidence="low",
                        )
                    )

    return dependencies


def _build_story_dependencies(
    stories: list[UserStory],
    dependencies: list[DetectedDependency],
) -> list[StoryDependencies]:
    """Build StoryDependencies objects from detected dependencies."""
    story_deps: dict[str, StoryDependencies] = {}

    # Initialize for all stories
    for story in stories:
        sid = str(story.id)
        story_deps[sid] = StoryDependencies(
            story_id=sid,
            story_title=story.title,
        )

    # Process dependencies
    for dep in dependencies:
        from_deps = story_deps.get(dep.from_story_id)
        to_deps = story_deps.get(dep.to_story_id)

        if not from_deps or not to_deps:
            continue

        from_deps.dependencies.append(dep)

        if dep.dependency_type == DependencyType.BLOCKED_BY:
            if dep.to_story_id not in from_deps.blocked_by:
                from_deps.blocked_by.append(dep.to_story_id)
            if dep.from_story_id not in to_deps.blocks:
                to_deps.blocks.append(dep.from_story_id)
        elif dep.dependency_type == DependencyType.BLOCKS:
            if dep.to_story_id not in from_deps.blocks:
                from_deps.blocks.append(dep.to_story_id)
            if dep.from_story_id not in to_deps.blocked_by:
                to_deps.blocked_by.append(dep.from_story_id)
        elif dep.dependency_type == DependencyType.RELATED:
            if dep.to_story_id not in from_deps.related_to:
                from_deps.related_to.append(dep.to_story_id)

    return list(story_deps.values())


def _build_dependency_graph(dependencies: list[DetectedDependency]) -> dict[str, list[str]]:
    """Build a graph representation of dependencies."""
    graph: dict[str, list[str]] = {}

    for dep in dependencies:
        if dep.dependency_type in (DependencyType.BLOCKED_BY, DependencyType.SEQUENCE):
            # from_story depends on to_story
            if dep.from_story_id not in graph:
                graph[dep.from_story_id] = []
            if dep.to_story_id not in graph[dep.from_story_id]:
                graph[dep.from_story_id].append(dep.to_story_id)

    return graph


def _detect_circular_dependencies(graph: dict[str, list[str]]) -> list[list[str]]:
    """Detect circular dependencies in the graph."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                cycles.append(cycle)
                return True

        path.pop()
        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            dfs(node)

    return cycles


class AIDependencyDetector:
    """
    Detects dependencies between user stories using LLM analysis.

    Analyzes story content to identify blocking relationships,
    related stories, and suggested execution order.
    """

    def __init__(
        self,
        options: DependencyOptions | None = None,
    ):
        """
        Initialize the detector.

        Args:
            options: Detection options. Uses defaults if not provided.
        """
        self.options = options or DependencyOptions()
        self.logger = logging.getLogger(__name__)

    def detect(
        self,
        stories: list[UserStory],
        options: DependencyOptions | None = None,
    ) -> DependencyResult:
        """
        Detect dependencies between stories.

        Args:
            stories: List of user stories to analyze.
            options: Override detection options.

        Returns:
            DependencyResult with detected dependencies.
        """
        from spectryn.adapters.llm import create_llm_manager

        opts = options or self.options
        result = DependencyResult()

        if not stories:
            result.success = False
            result.error = "No stories provided for dependency detection"
            return result

        if len(stories) < 2:
            result.success = False
            result.error = "At least 2 stories required for dependency detection"
            return result

        # Get LLM manager
        try:
            manager = create_llm_manager()
        except Exception as e:
            self.logger.warning(f"LLM not available, using fallback detection: {e}")
            return self._build_result_from_fallback(stories, opts)

        if not manager.is_available():
            self.logger.warning("No LLM providers available, using fallback detection")
            return self._build_result_from_fallback(stories, opts)

        # Build prompt
        prompt = build_dependency_prompt(stories, opts)

        # Generate
        try:
            response = manager.prompt(
                user_message=prompt,
                system_prompt=DEPENDENCY_SYSTEM_PROMPT,
            )

            result.raw_response = response.content
            result.tokens_used = response.total_tokens
            result.model_used = response.model
            result.provider_used = response.provider

        except Exception as e:
            self.logger.warning(f"LLM call failed, using fallback detection: {e}")
            return self._build_result_from_fallback(stories, opts)

        # Parse response
        try:
            deps, circular, order = parse_dependency_response(response.content, stories, opts)
            result.all_dependencies = deps
            result.circular_dependencies = circular
            result.suggested_order = order
            result.story_dependencies = _build_story_dependencies(stories, deps)
            result.dependency_graph = _build_dependency_graph(deps)

            # Check for circular if not already detected
            if opts.check_circular and not result.circular_dependencies:
                result.circular_dependencies = _detect_circular_dependencies(
                    result.dependency_graph
                )

            if not result.all_dependencies:
                # No dependencies found - that's okay, not an error
                result.story_dependencies = _build_story_dependencies(stories, [])

        except Exception as e:
            result.success = False
            result.error = f"Failed to parse dependency response: {e}"
            return self._build_result_from_fallback(stories, opts)

        return result

    def _build_result_from_fallback(
        self,
        stories: list[UserStory],
        options: DependencyOptions,
    ) -> DependencyResult:
        """Build result from fallback detection."""
        deps = _create_fallback_dependencies(stories, options)
        result = DependencyResult(
            all_dependencies=deps,
            story_dependencies=_build_story_dependencies(stories, deps),
            dependency_graph=_build_dependency_graph(deps),
        )

        if options.check_circular:
            result.circular_dependencies = _detect_circular_dependencies(result.dependency_graph)

        return result


def detect_dependencies(
    stories: list[UserStory],
    project_context: str = "",
    tech_stack: str = "",
) -> DependencyResult:
    """
    Convenience function to detect dependencies between stories.

    Args:
        stories: List of user stories to analyze.
        project_context: Optional project context.
        tech_stack: Optional tech stack info.

    Returns:
        DependencyResult with detected dependencies.
    """
    options = DependencyOptions(
        project_context=project_context,
        tech_stack=tech_stack,
    )

    detector = AIDependencyDetector(options)
    return detector.detect(stories, options)
