"""
AI-Generated Sync Summaries - Human-readable summary of sync operations.

Uses LLM providers to generate natural language summaries of:
- What was synced (created, updated, deleted)
- Key changes made
- Issues encountered
- Recommendations for next steps
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


logger = logging.getLogger(__name__)


class SyncAction(Enum):
    """Type of sync action performed."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNCHANGED = "unchanged"


class SyncEntityType(Enum):
    """Type of entity that was synced."""

    STORY = "story"
    EPIC = "epic"
    SUBTASK = "subtask"
    COMMENT = "comment"
    ATTACHMENT = "attachment"
    LABEL = "label"
    SPRINT = "sprint"


@dataclass
class SyncedEntity:
    """Represents an entity that was synced."""

    entity_type: SyncEntityType
    entity_id: str
    title: str
    action: SyncAction
    source: str = ""  # e.g., "markdown", "jira"
    target: str = ""  # e.g., "jira", "github"
    changes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Whether the sync was successful."""
        return self.action not in (SyncAction.FAILED, SyncAction.SKIPPED)


@dataclass
class SyncOperation:
    """Represents a complete sync operation."""

    operation_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    target: str = ""
    entities: list[SyncedEntity] = field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = False

    @property
    def created_count(self) -> int:
        """Count of created entities."""
        return sum(1 for e in self.entities if e.action == SyncAction.CREATED)

    @property
    def updated_count(self) -> int:
        """Count of updated entities."""
        return sum(1 for e in self.entities if e.action == SyncAction.UPDATED)

    @property
    def deleted_count(self) -> int:
        """Count of deleted entities."""
        return sum(1 for e in self.entities if e.action == SyncAction.DELETED)

    @property
    def failed_count(self) -> int:
        """Count of failed entities."""
        return sum(1 for e in self.entities if e.action == SyncAction.FAILED)

    @property
    def total_count(self) -> int:
        """Total entity count."""
        return len(self.entities)

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if not self.entities:
            return 100.0
        successful = sum(1 for e in self.entities if e.is_success)
        return (successful / len(self.entities)) * 100


@dataclass
class SyncSummary:
    """Human-readable sync summary."""

    headline: str = ""
    overview: str = ""
    key_changes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    detailed_changes: dict[str, list[str]] = field(default_factory=dict)
    raw_response: str = ""
    tokens_used: int = 0
    model_used: str = ""
    provider_used: str = ""

    def to_markdown(self) -> str:
        """Convert summary to markdown format."""
        lines = []

        if self.headline:
            lines.append(f"# {self.headline}")
            lines.append("")

        if self.overview:
            lines.append(self.overview)
            lines.append("")

        if self.stats:
            lines.append("## Statistics")
            for key, value in self.stats.items():
                lines.append(f"- **{key}**: {value}")
            lines.append("")

        if self.key_changes:
            lines.append("## Key Changes")
            for change in self.key_changes:
                lines.append(f"- {change}")
            lines.append("")

        if self.issues:
            lines.append("## Issues")
            for issue in self.issues:
                lines.append(f"- ⚠️ {issue}")
            lines.append("")

        if self.recommendations:
            lines.append("## Recommendations")
            for rec in self.recommendations:
                lines.append(f"- 💡 {rec}")
            lines.append("")

        return "\n".join(lines)

    def to_slack(self) -> str:
        """Convert summary to Slack-formatted message."""
        lines = []

        if self.headline:
            lines.append(f"*{self.headline}*")
            lines.append("")

        if self.overview:
            lines.append(self.overview)
            lines.append("")

        if self.stats:
            stats_parts = [f"{k}: {v}" for k, v in self.stats.items()]
            lines.append(f"📊 {' | '.join(stats_parts)}")
            lines.append("")

        if self.key_changes:
            lines.append("*Key Changes:*")
            for change in self.key_changes[:5]:
                lines.append(f"• {change}")
            lines.append("")

        if self.issues:
            lines.append("*Issues:*")
            for issue in self.issues[:3]:
                lines.append(f"⚠️ {issue}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class SummaryOptions:
    """Options for generating sync summaries."""

    include_details: bool = True
    include_recommendations: bool = True
    max_key_changes: int = 10
    format: str = "text"  # text, markdown, slack, json
    audience: str = "technical"  # technical, manager, stakeholder


SUMMARY_SYSTEM_PROMPT = """You are an expert at summarizing software sync operations in clear, human-readable language.

Your task is to take raw sync data and produce a summary that:
1. Clearly states what happened at a high level
2. Highlights the most important changes
3. Notes any issues or failures
4. Provides actionable recommendations

Adjust your language based on the audience:
- Technical: Include IDs, specific changes, technical details
- Manager: Focus on counts, status, blockers
- Stakeholder: High-level progress, business impact

Be concise but informative. Use active voice.
Always respond with valid JSON."""


def build_summary_prompt(
    operation: SyncOperation,
    options: SummaryOptions,
) -> str:
    """Build the prompt for generating a sync summary."""
    # Format entities by action
    entities_by_action: dict[str, list[str]] = {}
    for entity in operation.entities:
        action_key = entity.action.value
        if action_key not in entities_by_action:
            entities_by_action[action_key] = []
        entity_desc = f"{entity.entity_type.value}: {entity.entity_id} - {entity.title}"
        if entity.changes:
            entity_desc += f" (changes: {', '.join(entity.changes[:3])})"
        if entity.error:
            entity_desc += f" [ERROR: {entity.error}]"
        entities_by_action[action_key].append(entity_desc)

    # Format for prompt
    entities_text = []
    for action, items in entities_by_action.items():
        entities_text.append(f"\n### {action.upper()}")
        for item in items[:20]:  # Limit to prevent too long prompts
            entities_text.append(f"- {item}")
        if len(items) > 20:
            entities_text.append(f"- ... and {len(items) - 20} more")

    return f"""Generate a human-readable summary of this sync operation.

## Sync Details
- **Source**: {operation.source}
- **Target**: {operation.target}
- **Timestamp**: {operation.timestamp.isoformat()}
- **Duration**: {operation.duration_seconds:.1f} seconds
- **Dry Run**: {operation.dry_run}

## Statistics
- Created: {operation.created_count}
- Updated: {operation.updated_count}
- Deleted: {operation.deleted_count}
- Failed: {operation.failed_count}
- Total: {operation.total_count}
- Success Rate: {operation.success_rate:.1f}%

## Entities
{chr(10).join(entities_text)}

## Options
- Audience: {options.audience}
- Include details: {options.include_details}
- Max key changes: {options.max_key_changes}

## Output Format
Respond with a JSON object:

```json
{{
  "headline": "Synced 15 stories from Markdown to Jira",
  "overview": "Successfully synchronized user stories with 2 new stories created and 5 updated.",
  "key_changes": [
    "Created US-016: New checkout flow",
    "Updated US-003: Changed priority from Medium to High",
    "Updated US-007: Added 3 new acceptance criteria"
  ],
  "issues": [
    "Failed to sync US-010 due to missing required field"
  ],
  "recommendations": [
    "Review US-010 and add missing description",
    "Consider splitting large story US-015"
  ],
  "stats": {{
    "Created": 2,
    "Updated": 5,
    "Failed": 1
  }},
  "detailed_changes": {{
    "US-016": ["Created new story", "Set priority to High"],
    "US-003": ["Changed priority from Medium to High"]
  }}
}}
```

Generate the summary now:"""


def parse_summary_response(response: str) -> SyncSummary:
    """Parse LLM response into SyncSummary."""
    summary = SyncSummary()

    # Try to extract JSON
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\{[\s\S]*\"headline\"[\s\S]*\}", response)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning("Could not find JSON in response")
            summary.overview = response[:500]  # Use raw response as fallback
            return summary

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        summary.overview = response[:500]
        return summary

    summary.headline = data.get("headline", "")
    summary.overview = data.get("overview", "")
    summary.key_changes = data.get("key_changes", [])
    summary.issues = data.get("issues", [])
    summary.recommendations = data.get("recommendations", [])
    summary.stats = data.get("stats", {})
    summary.detailed_changes = data.get("detailed_changes", {})

    return summary


def generate_summary_fallback(
    operation: SyncOperation,
    options: SummaryOptions,
) -> SyncSummary:
    """Generate a summary without LLM."""
    summary = SyncSummary()

    # Generate headline
    if operation.dry_run:
        summary.headline = f"Dry Run: Would sync {operation.total_count} items from {operation.source} to {operation.target}"
    else:
        summary.headline = (
            f"Synced {operation.total_count} items from {operation.source} to {operation.target}"
        )

    # Generate overview
    parts = []
    if operation.created_count > 0:
        parts.append(f"{operation.created_count} created")
    if operation.updated_count > 0:
        parts.append(f"{operation.updated_count} updated")
    if operation.deleted_count > 0:
        parts.append(f"{operation.deleted_count} deleted")
    if operation.failed_count > 0:
        parts.append(f"{operation.failed_count} failed")

    if parts:
        summary.overview = f"Completed in {operation.duration_seconds:.1f}s: {', '.join(parts)}."
    else:
        summary.overview = "No changes made."

    # Stats
    summary.stats = {
        "Created": operation.created_count,
        "Updated": operation.updated_count,
        "Deleted": operation.deleted_count,
        "Failed": operation.failed_count,
        "Total": operation.total_count,
    }

    # Key changes
    for entity in operation.entities[: options.max_key_changes]:
        if entity.action == SyncAction.CREATED:
            summary.key_changes.append(
                f"Created {entity.entity_type.value} {entity.entity_id}: {entity.title}"
            )
        elif entity.action == SyncAction.UPDATED:
            changes_str = f" ({', '.join(entity.changes[:2])})" if entity.changes else ""
            summary.key_changes.append(f"Updated {entity.entity_id}: {entity.title}{changes_str}")
        elif entity.action == SyncAction.DELETED:
            summary.key_changes.append(f"Deleted {entity.entity_id}: {entity.title}")

    # Issues
    for entity in operation.entities:
        if entity.action == SyncAction.FAILED and entity.error:
            summary.issues.append(f"{entity.entity_id}: {entity.error}")

    # Recommendations
    if operation.failed_count > 0:
        summary.recommendations.append(f"Review and fix {operation.failed_count} failed items")
    if operation.success_rate < 100:
        summary.recommendations.append("Check logs for detailed error information")

    return summary


class AISyncSummaryGenerator:
    """
    Generates human-readable summaries of sync operations.

    Uses LLM analysis to create natural language summaries.
    """

    def __init__(self, options: SummaryOptions | None = None):
        """
        Initialize the generator.

        Args:
            options: Summary options. Uses defaults if not provided.
        """
        self.options = options or SummaryOptions()
        self.logger = logging.getLogger(__name__)

    def generate(
        self,
        operation: SyncOperation,
        options: SummaryOptions | None = None,
    ) -> SyncSummary:
        """
        Generate a summary for a sync operation.

        Args:
            operation: The sync operation to summarize.
            options: Override summary options.

        Returns:
            SyncSummary with human-readable summary.
        """
        from spectra.adapters.llm import create_llm_manager

        opts = options or self.options

        # Try LLM first
        try:
            manager = create_llm_manager()
            if manager.is_available():
                prompt = build_summary_prompt(operation, opts)

                response = manager.prompt(
                    user_message=prompt,
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                )

                summary = parse_summary_response(response.content)
                summary.raw_response = response.content
                summary.tokens_used = response.total_tokens
                summary.model_used = response.model
                summary.provider_used = response.provider

                return summary

        except Exception as e:
            self.logger.warning(f"LLM summary generation failed: {e}")

        # Fallback to template-based summary
        return generate_summary_fallback(operation, opts)

    def generate_from_results(
        self,
        results: list[dict],
        source: str = "markdown",
        target: str = "tracker",
        duration: float = 0.0,
    ) -> SyncSummary:
        """
        Generate a summary from raw sync results.

        Args:
            results: List of sync result dictionaries.
            source: Source of the sync.
            target: Target of the sync.
            duration: Duration in seconds.

        Returns:
            SyncSummary with human-readable summary.
        """
        # Convert results to SyncOperation
        entities = []
        for result in results:
            action = SyncAction.UPDATED
            if result.get("created"):
                action = SyncAction.CREATED
            elif result.get("deleted"):
                action = SyncAction.DELETED
            elif result.get("failed") or result.get("error"):
                action = SyncAction.FAILED

            entity = SyncedEntity(
                entity_type=SyncEntityType.STORY,
                entity_id=result.get("id", ""),
                title=result.get("title", ""),
                action=action,
                source=source,
                target=target,
                changes=result.get("changes", []),
                error=result.get("error"),
            )
            entities.append(entity)

        operation = SyncOperation(
            source=source,
            target=target,
            entities=entities,
            duration_seconds=duration,
        )

        return self.generate(operation)


def generate_sync_summary(
    operation: SyncOperation,
    audience: str = "technical",
) -> SyncSummary:
    """
    Convenience function to generate a sync summary.

    Args:
        operation: The sync operation to summarize.
        audience: Target audience (technical, manager, stakeholder).

    Returns:
        SyncSummary with human-readable summary.
    """
    options = SummaryOptions(audience=audience)
    generator = AISyncSummaryGenerator(options)
    return generator.generate(operation, options)
