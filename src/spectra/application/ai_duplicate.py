"""
AI Duplicate Detection - Find similar stories across files/trackers.

Uses LLM providers and text similarity to detect:
- Exact duplicates (same story in different places)
- Near-duplicates (slightly modified versions)
- Similar stories (overlapping scope/functionality)
- Related stories (same feature area)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

from spectra.core.domain.entities import UserStory


logger = logging.getLogger(__name__)


class SimilarityLevel(Enum):
    """Level of similarity between stories."""

    EXACT = "exact"  # Identical or nearly identical
    HIGH = "high"  # Very similar, likely duplicates
    MEDIUM = "medium"  # Similar, may overlap
    LOW = "low"  # Some similarity, related topics
    NONE = "none"  # No meaningful similarity


class DuplicateType(Enum):
    """Type of duplicate relationship."""

    EXACT_DUPLICATE = "exact_duplicate"  # Same story
    NEAR_DUPLICATE = "near_duplicate"  # Minor differences
    OVERLAPPING = "overlapping"  # Overlapping scope
    RELATED = "related"  # Same feature area
    SUPERSEDED = "superseded"  # One replaces another


@dataclass
class SimilarityMatch:
    """A similarity match between two stories."""

    story_a_id: str
    story_b_id: str
    story_a_title: str
    story_b_title: str
    similarity_score: float  # 0.0 to 1.0
    similarity_level: SimilarityLevel
    duplicate_type: DuplicateType
    matching_elements: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    recommendation: str = ""
    confidence: str = "medium"  # "high", "medium", "low"

    @property
    def is_likely_duplicate(self) -> bool:
        """Whether this is likely a duplicate."""
        return self.duplicate_type in (
            DuplicateType.EXACT_DUPLICATE,
            DuplicateType.NEAR_DUPLICATE,
        )

    @property
    def percentage(self) -> int:
        """Similarity as percentage."""
        return int(self.similarity_score * 100)


@dataclass
class StoryDuplicates:
    """Duplicate analysis for a single story."""

    story_id: str
    story_title: str
    source: str = ""  # Source file/tracker
    matches: list[SimilarityMatch] = field(default_factory=list)
    has_duplicates: bool = False
    highest_match: SimilarityMatch | None = None

    @property
    def duplicate_count(self) -> int:
        """Count of likely duplicates."""
        return sum(1 for m in self.matches if m.is_likely_duplicate)


@dataclass
class DuplicateResult:
    """Result of duplicate detection."""

    success: bool = True
    story_analyses: list[StoryDuplicates] = field(default_factory=list)
    all_matches: list[SimilarityMatch] = field(default_factory=list)
    duplicate_groups: list[list[str]] = field(default_factory=list)
    total_stories: int = 0
    stories_with_duplicates: int = 0
    raw_response: str = ""
    error: str | None = None
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    @property
    def duplicate_rate(self) -> float:
        """Percentage of stories with duplicates."""
        if self.total_stories == 0:
            return 0.0
        return (self.stories_with_duplicates / self.total_stories) * 100


@dataclass
class DuplicateOptions:
    """Options for duplicate detection."""

    # Similarity thresholds
    exact_threshold: float = 0.95  # Score for exact duplicate
    high_threshold: float = 0.80  # Score for high similarity
    medium_threshold: float = 0.60  # Score for medium similarity
    min_threshold: float = 0.40  # Minimum to report

    # Detection modes
    use_llm: bool = True  # Use LLM for semantic analysis
    use_text_similarity: bool = True  # Use text-based similarity
    compare_ac: bool = True  # Compare acceptance criteria
    compare_descriptions: bool = True  # Compare descriptions

    # Context
    project_context: str = ""


DUPLICATE_SYSTEM_PROMPT = """You are an expert at analyzing software requirements for duplicates and overlaps.
Your task is to compare user stories and identify potential duplicates or similar stories.

Types of duplicates/similarities:
1. **Exact Duplicate**: Same story with identical or nearly identical content
2. **Near Duplicate**: Same story with minor wording differences
3. **Overlapping**: Stories that cover some of the same functionality
4. **Related**: Stories in the same feature area but different functionality
5. **Superseded**: One story replaces or is an updated version of another

Consider when comparing:
- Title similarity
- Description similarity (As a... I want... So that...)
- Acceptance criteria overlap
- Technical scope overlap
- User persona overlap

Be conservative: Only flag as duplicates when clearly similar.
False positives waste time, so prioritize precision over recall.

Always respond with valid JSON."""


def build_duplicate_prompt(
    stories: list[UserStory],
    options: DuplicateOptions,
) -> str:
    """Build the prompt for duplicate detection."""
    # Format stories
    stories_text = []
    for story in stories:
        story_text = f"""
### {story.id}: {story.title}
**Description**: {_format_description(story)}
**AC**: {_format_ac_summary(story)}
**Labels**: {", ".join(story.labels) if story.labels else "(none)"}
"""
        stories_text.append(story_text.strip())

    return f"""Compare the following user stories and identify any duplicates or similar stories.

## Context
{options.project_context or "No additional context provided."}

## Similarity Thresholds
- Exact duplicate: {int(options.exact_threshold * 100)}%+ similarity
- High similarity: {int(options.high_threshold * 100)}%+ similarity
- Medium similarity: {int(options.medium_threshold * 100)}%+ similarity
- Minimum to report: {int(options.min_threshold * 100)}%+ similarity

## Stories to Compare
{chr(10).join(stories_text)}

## Output Format
Respond with a JSON object containing detected similarities:

```json
{{
  "matches": [
    {{
      "story_a_id": "US-001",
      "story_b_id": "US-003",
      "similarity_score": 0.85,
      "similarity_level": "high",
      "duplicate_type": "near_duplicate",
      "matching_elements": ["Same user persona", "Similar functionality", "Overlapping AC"],
      "differences": ["Different priority", "US-003 has more AC"],
      "recommendation": "Consider merging US-001 into US-003",
      "confidence": "high"
    }}
  ],
  "duplicate_groups": [
    ["US-001", "US-003"],
    ["US-002", "US-005", "US-008"]
  ],
  "summary": "Found 2 potential duplicate groups"
}}
```

Similarity levels: "exact", "high", "medium", "low"
Duplicate types: "exact_duplicate", "near_duplicate", "overlapping", "related", "superseded"
Confidence: "high", "medium", "low"

Only include matches with similarity >= {int(options.min_threshold * 100)}%.
Analyze and find duplicates now:"""


def _format_description(story: UserStory) -> str:
    """Format story description for comparison."""
    if story.description:
        return f"As a {story.description.role}, I want {story.description.want}, so that {story.description.benefit}"
    return "(No description)"


def _format_ac_summary(story: UserStory) -> str:
    """Format acceptance criteria summary."""
    if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
        ac_texts = [ac for ac, _ in story.acceptance_criteria]
        if len(ac_texts) <= 3:
            return "; ".join(ac_texts)
        return f"{'; '.join(ac_texts[:3])}... ({len(ac_texts)} total)"
    return "(No AC)"


def calculate_text_similarity(text_a: str, text_b: str) -> float:
    """Calculate similarity between two texts using SequenceMatcher."""
    if not text_a or not text_b:
        return 0.0

    # Normalize texts
    text_a = text_a.lower().strip()
    text_b = text_b.lower().strip()

    if text_a == text_b:
        return 1.0

    return SequenceMatcher(None, text_a, text_b).ratio()


def calculate_story_similarity(story_a: UserStory, story_b: UserStory) -> float:
    """Calculate overall similarity between two stories."""
    scores = []
    weights = []

    # Title similarity (weight: 0.3)
    title_sim = calculate_text_similarity(story_a.title, story_b.title)
    scores.append(title_sim)
    weights.append(0.3)

    # Description similarity (weight: 0.4)
    if story_a.description and story_b.description:
        desc_a = (
            f"{story_a.description.role} {story_a.description.want} {story_a.description.benefit}"
        )
        desc_b = (
            f"{story_b.description.role} {story_b.description.want} {story_b.description.benefit}"
        )
        desc_sim = calculate_text_similarity(desc_a, desc_b)
        scores.append(desc_sim)
        weights.append(0.4)
    elif story_a.description or story_b.description:
        scores.append(0.0)
        weights.append(0.2)

    # AC similarity (weight: 0.3)
    if story_a.acceptance_criteria and story_b.acceptance_criteria:
        ac_a = " ".join(ac for ac, _ in story_a.acceptance_criteria)
        ac_b = " ".join(ac for ac, _ in story_b.acceptance_criteria)
        ac_sim = calculate_text_similarity(ac_a, ac_b)
        scores.append(ac_sim)
        weights.append(0.3)
    elif story_a.acceptance_criteria or story_b.acceptance_criteria:
        scores.append(0.0)
        weights.append(0.15)

    # Weighted average
    if not weights:
        return 0.0

    total_weight = sum(weights)
    weighted_sum = sum(s * w for s, w in zip(scores, weights, strict=False))
    return weighted_sum / total_weight


def get_similarity_level(score: float, options: DuplicateOptions) -> SimilarityLevel:
    """Determine similarity level from score."""
    if score >= options.exact_threshold:
        return SimilarityLevel.EXACT
    if score >= options.high_threshold:
        return SimilarityLevel.HIGH
    if score >= options.medium_threshold:
        return SimilarityLevel.MEDIUM
    if score >= options.min_threshold:
        return SimilarityLevel.LOW
    return SimilarityLevel.NONE


def get_duplicate_type(level: SimilarityLevel) -> DuplicateType:
    """Determine duplicate type from similarity level."""
    if level == SimilarityLevel.EXACT:
        return DuplicateType.EXACT_DUPLICATE
    if level == SimilarityLevel.HIGH:
        return DuplicateType.NEAR_DUPLICATE
    if level == SimilarityLevel.MEDIUM:
        return DuplicateType.OVERLAPPING
    return DuplicateType.RELATED


def parse_duplicate_response(
    response: str,
    stories: list[UserStory],
    options: DuplicateOptions,
) -> tuple[list[SimilarityMatch], list[list[str]]]:
    """Parse LLM response into match objects."""
    matches: list[SimilarityMatch] = []
    groups: list[list[str]] = []

    # Try to extract JSON from the response
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"matches\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            return [], []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return [], []

    # Valid story IDs
    valid_ids = {str(s.id) for s in stories}
    story_map = {str(s.id): s for s in stories}

    # Parse matches
    for raw_match in data.get("matches", []):
        a_id = raw_match.get("story_a_id", "")
        b_id = raw_match.get("story_b_id", "")

        if a_id not in valid_ids or b_id not in valid_ids:
            continue

        if a_id == b_id:
            continue

        # Parse similarity level
        try:
            sim_level = SimilarityLevel(raw_match.get("similarity_level", "medium"))
        except ValueError:
            sim_level = SimilarityLevel.MEDIUM

        # Parse duplicate type
        try:
            dup_type = DuplicateType(raw_match.get("duplicate_type", "related"))
        except ValueError:
            dup_type = DuplicateType.RELATED

        match = SimilarityMatch(
            story_a_id=a_id,
            story_b_id=b_id,
            story_a_title=story_map[a_id].title,
            story_b_title=story_map[b_id].title,
            similarity_score=raw_match.get("similarity_score", 0.5),
            similarity_level=sim_level,
            duplicate_type=dup_type,
            matching_elements=raw_match.get("matching_elements", []),
            differences=raw_match.get("differences", []),
            recommendation=raw_match.get("recommendation", ""),
            confidence=raw_match.get("confidence", "medium"),
        )
        matches.append(match)

    # Parse groups
    for group in data.get("duplicate_groups", []):
        if isinstance(group, list):
            valid_group = [g for g in group if g in valid_ids]
            if len(valid_group) >= 2:
                groups.append(valid_group)

    return matches, groups


def find_duplicates_text_based(
    stories: list[UserStory],
    options: DuplicateOptions,
) -> list[SimilarityMatch]:
    """Find duplicates using text similarity (no LLM)."""
    matches = []

    for i, story_a in enumerate(stories):
        for story_b in stories[i + 1 :]:
            similarity = calculate_story_similarity(story_a, story_b)

            if similarity < options.min_threshold:
                continue

            level = get_similarity_level(similarity, options)
            dup_type = get_duplicate_type(level)

            # Build matching elements
            matching = []
            if calculate_text_similarity(story_a.title, story_b.title) > 0.7:
                matching.append("Similar titles")
            if story_a.description and story_b.description:
                if story_a.description.role == story_b.description.role:
                    matching.append("Same user persona")
                if (
                    calculate_text_similarity(story_a.description.want, story_b.description.want)
                    > 0.6
                ):
                    matching.append("Similar functionality")

            # Build differences
            differences = []
            if story_a.story_points != story_b.story_points:
                differences.append(
                    f"Different points ({story_a.story_points} vs {story_b.story_points})"
                )
            if story_a.priority != story_b.priority:
                differences.append("Different priority")

            match = SimilarityMatch(
                story_a_id=str(story_a.id),
                story_b_id=str(story_b.id),
                story_a_title=story_a.title,
                story_b_title=story_b.title,
                similarity_score=similarity,
                similarity_level=level,
                duplicate_type=dup_type,
                matching_elements=matching,
                differences=differences,
                recommendation=_get_recommendation(level, dup_type),
                confidence="low",  # Text-based is lower confidence
            )
            matches.append(match)

    return matches


def _get_recommendation(level: SimilarityLevel, dup_type: DuplicateType) -> str:
    """Get recommendation based on similarity."""
    if dup_type == DuplicateType.EXACT_DUPLICATE:
        return "Remove one of these duplicate stories"
    if dup_type == DuplicateType.NEAR_DUPLICATE:
        return "Consider merging these stories"
    if dup_type == DuplicateType.OVERLAPPING:
        return "Review for scope overlap, consider splitting or merging"
    if dup_type == DuplicateType.RELATED:
        return "Related stories - ensure they don't overlap"
    return "Review for potential overlap"


def build_duplicate_groups(matches: list[SimilarityMatch]) -> list[list[str]]:
    """Build groups of related/duplicate stories from matches."""
    # Use union-find to group related stories
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Only group high-similarity matches
    for match in matches:
        if match.is_likely_duplicate:
            union(match.story_a_id, match.story_b_id)

    # Build groups
    groups_dict: dict[str, list[str]] = {}
    for story_id in parent:
        root = find(story_id)
        if root not in groups_dict:
            groups_dict[root] = []
        if story_id not in groups_dict[root]:
            groups_dict[root].append(story_id)

    # Return only groups with 2+ members
    return [sorted(g) for g in groups_dict.values() if len(g) >= 2]


class AIDuplicateDetector:
    """
    Detects duplicate and similar stories using LLM analysis.

    Compares stories to find exact duplicates, near-duplicates,
    and overlapping functionality.
    """

    def __init__(
        self,
        options: DuplicateOptions | None = None,
    ):
        """
        Initialize the detector.

        Args:
            options: Detection options. Uses defaults if not provided.
        """
        self.options = options or DuplicateOptions()
        self.logger = logging.getLogger(__name__)

    def detect(
        self,
        stories: list[UserStory],
        options: DuplicateOptions | None = None,
    ) -> DuplicateResult:
        """
        Detect duplicates among stories.

        Args:
            stories: List of user stories to analyze.
            options: Override detection options.

        Returns:
            DuplicateResult with detected duplicates.
        """
        from spectra.adapters.llm import create_llm_manager

        opts = options or self.options
        result = DuplicateResult(total_stories=len(stories))

        if not stories:
            result.success = False
            result.error = "No stories provided for duplicate detection"
            return result

        if len(stories) < 2:
            result.success = False
            result.error = "At least 2 stories required for duplicate detection"
            return result

        # First, try text-based similarity
        text_matches = []
        if opts.use_text_similarity:
            text_matches = find_duplicates_text_based(stories, opts)

        # If LLM is enabled, use it for semantic analysis
        llm_matches: list[SimilarityMatch] = []
        llm_groups: list[list[str]] = []

        if opts.use_llm:
            try:
                manager = create_llm_manager()
                if manager.is_available():
                    prompt = build_duplicate_prompt(stories, opts)

                    response = manager.prompt(
                        user_message=prompt,
                        system_prompt=DUPLICATE_SYSTEM_PROMPT,
                    )

                    result.raw_response = response.content
                    result.tokens_used = response.total_tokens
                    result.model_used = response.model
                    result.provider_used = response.provider

                    llm_matches, llm_groups = parse_duplicate_response(
                        response.content, stories, opts
                    )
            except Exception as e:
                self.logger.warning(f"LLM analysis failed, using text-based only: {e}")

        # Merge results (prefer LLM matches when available)
        if llm_matches:
            result.all_matches = llm_matches
            result.duplicate_groups = llm_groups or build_duplicate_groups(llm_matches)
        else:
            result.all_matches = text_matches
            result.duplicate_groups = build_duplicate_groups(text_matches)

        # Build per-story analysis
        result.story_analyses = self._build_story_analyses(stories, result.all_matches)
        result.stories_with_duplicates = sum(1 for s in result.story_analyses if s.has_duplicates)

        return result

    def _build_story_analyses(
        self,
        stories: list[UserStory],
        matches: list[SimilarityMatch],
    ) -> list[StoryDuplicates]:
        """Build per-story duplicate analysis."""
        analyses: dict[str, StoryDuplicates] = {}

        # Initialize for all stories
        for story in stories:
            sid = str(story.id)
            analyses[sid] = StoryDuplicates(
                story_id=sid,
                story_title=story.title,
            )

        # Add matches
        for match in matches:
            # Add to story A
            if match.story_a_id in analyses:
                analyses[match.story_a_id].matches.append(match)
                if match.is_likely_duplicate:
                    analyses[match.story_a_id].has_duplicates = True

            # Add to story B (with reversed match)
            if match.story_b_id in analyses:
                reversed_match = SimilarityMatch(
                    story_a_id=match.story_b_id,
                    story_b_id=match.story_a_id,
                    story_a_title=match.story_b_title,
                    story_b_title=match.story_a_title,
                    similarity_score=match.similarity_score,
                    similarity_level=match.similarity_level,
                    duplicate_type=match.duplicate_type,
                    matching_elements=match.matching_elements,
                    differences=match.differences,
                    recommendation=match.recommendation,
                    confidence=match.confidence,
                )
                analyses[match.story_b_id].matches.append(reversed_match)
                if match.is_likely_duplicate:
                    analyses[match.story_b_id].has_duplicates = True

        # Set highest match for each story
        for analysis in analyses.values():
            if analysis.matches:
                analysis.highest_match = max(analysis.matches, key=lambda m: m.similarity_score)

        return list(analyses.values())


def detect_duplicates(
    stories: list[UserStory],
    min_similarity: float = 0.40,
    project_context: str = "",
) -> DuplicateResult:
    """
    Convenience function to detect duplicates.

    Args:
        stories: List of user stories to analyze.
        min_similarity: Minimum similarity threshold (0.0-1.0).
        project_context: Optional project context.

    Returns:
        DuplicateResult with detected duplicates.
    """
    options = DuplicateOptions(
        min_threshold=min_similarity,
        project_context=project_context,
    )

    detector = AIDuplicateDetector(options)
    return detector.detect(stories, options)
