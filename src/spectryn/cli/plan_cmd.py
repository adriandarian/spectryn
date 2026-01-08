"""
Plan Command - Show side-by-side comparison before sync (like Terraform).

Displays:
- What will be created
- What will be updated
- What will remain unchanged
- Resource summary

Inspired by Terraform's plan output for clear change visualization.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class PlannedChange:
    """A planned change to a resource."""

    action: str  # create, update, no-change
    resource_type: str  # story, subtask, comment, status
    resource_id: str
    title: str
    details: list[str] = field(default_factory=list)


@dataclass
class SyncPlan:
    """Complete sync plan."""

    changes: list[PlannedChange] = field(default_factory=list)

    @property
    def to_create(self) -> list[PlannedChange]:
        """Changes that will create resources."""
        return [c for c in self.changes if c.action == "create"]

    @property
    def to_update(self) -> list[PlannedChange]:
        """Changes that will update resources."""
        return [c for c in self.changes if c.action == "update"]

    @property
    def no_change(self) -> list[PlannedChange]:
        """Resources with no changes."""
        return [c for c in self.changes if c.action == "no-change"]

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.to_create) or bool(self.to_update)


def format_plan(plan: SyncPlan, color: bool = True, verbose: bool = False) -> str:
    """
    Format the sync plan for display (Terraform-style).

    Args:
        plan: SyncPlan to format.
        color: Whether to use colors.
        verbose: Show all resources including unchanged.

    Returns:
        Formatted string.
    """
    lines = []

    # Terraform-style header
    if color:
        lines.append(f"{Colors.BOLD}spectra will perform the following actions:{Colors.RESET}")
    else:
        lines.append("spectra will perform the following actions:")
    lines.append("")

    # Group by resource type
    stories_create = [c for c in plan.to_create if c.resource_type == "story"]
    stories_update = [c for c in plan.to_update if c.resource_type == "story"]
    subtasks_create = [c for c in plan.to_create if c.resource_type == "subtask"]
    subtasks_update = [c for c in plan.to_update if c.resource_type == "subtask"]
    comments_create = [c for c in plan.to_create if c.resource_type == "comment"]
    status_update = [c for c in plan.to_update if c.resource_type == "status"]

    # Stories to create
    if stories_create:
        for change in stories_create:
            if color:
                lines.append(f"  {Colors.GREEN}+ story.{change.resource_id}{Colors.RESET}")
                lines.append(f'      title: "{change.title}"')
            else:
                lines.append(f"  + story.{change.resource_id}")
                lines.append(f'      title: "{change.title}"')

            for detail in change.details:
                lines.append(f"      {detail}")
            lines.append("")

    # Stories to update
    if stories_update:
        for change in stories_update:
            if color:
                lines.append(f"  {Colors.YELLOW}~ story.{change.resource_id}{Colors.RESET}")
            else:
                lines.append(f"  ~ story.{change.resource_id}")

            for detail in change.details:
                if "→" in detail and color:
                    # Highlight the change
                    parts = detail.split("→")
                    lines.append(
                        f"      {parts[0].strip()}: "
                        f"{Colors.RED}{parts[0].split(':')[-1].strip()}{Colors.RESET} → "
                        f"{Colors.GREEN}{parts[1].strip()}{Colors.RESET}"
                    )
                else:
                    lines.append(f"      {detail}")
            lines.append("")

    # Subtasks to create
    if subtasks_create:
        if color:
            lines.append(f"  {Colors.GREEN}+ subtasks:{Colors.RESET}")
        else:
            lines.append("  + subtasks:")

        for change in subtasks_create[:10]:  # Limit display
            lines.append(f"      + {change.resource_id}: {change.title[:50]}")

        if len(subtasks_create) > 10:
            lines.append(f"      ... and {len(subtasks_create) - 10} more")
        lines.append("")

    # Subtasks to update
    if subtasks_update:
        if color:
            lines.append(f"  {Colors.YELLOW}~ subtasks:{Colors.RESET}")
        else:
            lines.append("  ~ subtasks:")

        for change in subtasks_update[:10]:
            lines.append(f"      ~ {change.resource_id}: {change.title[:50]}")

        if len(subtasks_update) > 10:
            lines.append(f"      ... and {len(subtasks_update) - 10} more")
        lines.append("")

    # Comments to add
    if comments_create:
        if color:
            lines.append(f"  {Colors.GREEN}+ comments:{Colors.RESET}")
        else:
            lines.append("  + comments:")

        for change in comments_create[:5]:
            lines.append(f"      + {change.resource_id}: {change.title[:40]}...")

        if len(comments_create) > 5:
            lines.append(f"      ... and {len(comments_create) - 5} more")
        lines.append("")

    # Status updates
    if status_update:
        if color:
            lines.append(f"  {Colors.CYAN}↻ status updates:{Colors.RESET}")
        else:
            lines.append("  ↻ status updates:")

        for change in status_update[:10]:
            lines.append(
                f"      {change.resource_id}: {change.details[0] if change.details else ''}"
            )

        if len(status_update) > 10:
            lines.append(f"      ... and {len(status_update) - 10} more")
        lines.append("")

    # Unchanged (only in verbose mode)
    if verbose and plan.no_change:
        if color:
            lines.append(f"  {Colors.DIM}= unchanged:{Colors.RESET}")
        else:
            lines.append("  = unchanged:")

        for change in plan.no_change[:5]:
            lines.append(f"      {change.resource_id}: {change.title[:40]}")

        if len(plan.no_change) > 5:
            lines.append(f"      ... and {len(plan.no_change) - 5} more")
        lines.append("")

    # Summary line (Terraform-style)
    lines.append("-" * 60)

    create_count = len(plan.to_create)
    update_count = len(plan.to_update)
    unchanged_count = len(plan.no_change)

    summary_parts = []
    if create_count:
        if color:
            summary_parts.append(f"{Colors.GREEN}+{create_count} to add{Colors.RESET}")
        else:
            summary_parts.append(f"+{create_count} to add")

    if update_count:
        if color:
            summary_parts.append(f"{Colors.YELLOW}~{update_count} to change{Colors.RESET}")
        else:
            summary_parts.append(f"~{update_count} to change")

    if unchanged_count:
        if color:
            summary_parts.append(f"{Colors.DIM}={unchanged_count} unchanged{Colors.RESET}")
        else:
            summary_parts.append(f"={unchanged_count} unchanged")

    if summary_parts:
        lines.append(f"Plan: {', '.join(summary_parts)}")
    else:
        lines.append("Plan: No changes. Your configuration matches the tracker state.")

    lines.append("")

    return "\n".join(lines)


def run_plan(
    console: Console,
    input_path: str,
    epic_key: str,
    verbose: bool = False,
    output_format: str = "text",
) -> int:
    """
    Run the plan command.

    Args:
        console: Console for output.
        input_path: Path to markdown file.
        epic_key: Epic key in tracker.
        verbose: Show all resources.
        output_format: Output format (text, json).

    Returns:
        Exit code.
    """
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectryn.adapters.parsers import MarkdownParser
    from spectryn.application import SyncOrchestrator

    from .logging import setup_logging

    setup_logging(level=logging.INFO)

    console.header(f"spectra Plan {Symbols.CHART}")
    console.print()

    # Check file exists
    if not Path(input_path).exists():
        console.error(f"File not found: {input_path}")
        return ExitCode.FILE_NOT_FOUND

    console.info(f"Source: {input_path}")
    console.info(f"Target: {epic_key}")
    console.print()

    # Load configuration
    config_provider = EnvironmentConfigProvider()
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = True  # Plan is always dry-run

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.info("Analyzing...")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    # Create orchestrator and analyze
    orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )

    analysis = orchestrator.analyze(input_path, epic_key)
    console.print()

    # Build plan from analysis
    plan = SyncPlan()

    # Stories to create (unmatched in local)
    for story_id in analysis.get("unmatched_stories", []):
        story = next((s for s in analysis.get("local_stories", []) if str(s.id) == story_id), None)
        if story:
            plan.changes.append(
                PlannedChange(
                    action="create",
                    resource_type="story",
                    resource_id=story_id,
                    title=story.title,
                    details=[
                        f"points: {story.story_points or 'TBD'}",
                        f"status: {story.status.value if story.status else 'Planned'}",
                    ],
                )
            )

    # Stories to update (matched with changes)
    for match in analysis.get("matches", []):
        story_id = match.get("story_id")
        remote_key = match.get("remote_key")
        changes = match.get("changes", {})

        story = next((s for s in analysis.get("local_stories", []) if str(s.id) == story_id), None)

        if changes:
            details = []
            for field_name, values in changes.items():
                old_val = values.get("old", "")
                new_val = values.get("new", "")
                details.append(f"{field_name}: {old_val} → {new_val}")

            plan.changes.append(
                PlannedChange(
                    action="update",
                    resource_type="story",
                    resource_id=remote_key or story_id,
                    title=story.title if story else "",
                    details=details,
                )
            )
        elif story:
            plan.changes.append(
                PlannedChange(
                    action="no-change",
                    resource_type="story",
                    resource_id=remote_key or story_id,
                    title=story.title,
                )
            )

    # Subtasks to create
    for story in analysis.get("local_stories", []):
        for subtask in story.subtasks or []:
            # Check if subtask exists
            exists = any(
                st.get("summary") == subtask.name
                for match in analysis.get("matches", [])
                for st in match.get("remote_subtasks", [])
            )
            if not exists:
                plan.changes.append(
                    PlannedChange(
                        action="create",
                        resource_type="subtask",
                        resource_id=f"{story.id}.ST-{subtask.number}",
                        title=subtask.name,
                    )
                )

    # Status updates
    for match in analysis.get("matches", []):
        if match.get("status_change"):
            plan.changes.append(
                PlannedChange(
                    action="update",
                    resource_type="status",
                    resource_id=match.get("remote_key", ""),
                    title="",
                    details=[f"{match['status_change']['old']} → {match['status_change']['new']}"],
                )
            )

    # Output
    if output_format == "json":
        import json

        data = {
            "has_changes": plan.has_changes,
            "summary": {
                "to_create": len(plan.to_create),
                "to_update": len(plan.to_update),
                "no_change": len(plan.no_change),
            },
            "changes": [
                {
                    "action": c.action,
                    "resource_type": c.resource_type,
                    "resource_id": c.resource_id,
                    "title": c.title,
                    "details": c.details,
                }
                for c in plan.changes
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        formatted = format_plan(plan, color=console.color, verbose=verbose)
        print(formatted)

        # Hint about execution
        if plan.has_changes:
            console.info("To apply these changes:")
            console.detail(f"  spectra --input {input_path} --epic {epic_key} --execute")

    return ExitCode.SUCCESS
