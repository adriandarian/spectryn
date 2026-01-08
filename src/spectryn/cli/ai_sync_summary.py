"""
AI Sync Summary CLI - Command handler for generating sync summaries.

Generates human-readable summaries of sync operations using LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


if TYPE_CHECKING:
    from spectryn.application.ai_sync_summary import SyncOperation


def run_ai_sync_summary(
    console: Console,
    sync_log_path: str | None = None,
    sync_data: dict | None = None,
    audience: str = "technical",
    output_format: str = "text",
    copy_to_clipboard: bool = False,
) -> int:
    """
    Run the AI sync summary command.

    Args:
        console: Console for output.
        sync_log_path: Path to sync log file (JSON).
        sync_data: Direct sync data dictionary.
        audience: Target audience (technical, manager, stakeholder).
        output_format: Output format (text, markdown, slack, json).
        copy_to_clipboard: Copy summary to clipboard.

    Returns:
        Exit code.
    """
    from spectryn.application.ai_sync_summary import (
        AISyncSummaryGenerator,
        SummaryOptions,
    )

    console.header(f"spectra Sync Summary {Symbols.SYNC}")

    # Load sync data
    operation = None

    if sync_log_path:
        if not Path(sync_log_path).exists():
            console.error(f"Sync log file not found: {sync_log_path}")
            return ExitCode.ERROR

        try:
            with open(sync_log_path) as f:
                log_data = json.load(f)
            operation = _parse_sync_log(log_data)
            console.success(f"Loaded sync log from {Path(sync_log_path).name}")
        except Exception as e:
            console.error(f"Failed to load sync log: {e}")
            return ExitCode.ERROR

    elif sync_data:
        operation = _parse_sync_log(sync_data)
    else:
        console.error("No sync log provided. Use --sync-log or pipe sync data")
        return ExitCode.CONFIG_ERROR

    if not operation:
        console.error("Failed to parse sync data")
        return ExitCode.ERROR

    # Show operation details
    console.section("Sync Operation")
    console.detail(f"Source: {operation.source}")
    console.detail(f"Target: {operation.target}")
    console.detail(f"Entities: {operation.total_count}")
    console.detail(f"Duration: {operation.duration_seconds:.1f}s")

    # Generate summary
    console.section("Generating Summary")
    console.info(f"Target audience: {audience}")

    options = SummaryOptions(
        audience=audience,
        format=output_format,
    )

    generator = AISyncSummaryGenerator(options)
    summary = generator.generate(operation, options)

    # Show LLM info
    if summary.provider_used:
        console.detail(f"Provider: {summary.provider_used}")
        console.detail(f"Model: {summary.model_used}")

    # Output based on format
    if output_format == "json":
        output = _format_json(summary)
        print(output)
    elif output_format == "markdown":
        output = summary.to_markdown()
        print(output)
    elif output_format == "slack":
        output = summary.to_slack()
        print(output)
    else:
        _format_text(summary, console)

    # Copy to clipboard if requested
    if copy_to_clipboard:
        try:
            import subprocess

            output_text = summary.to_markdown() if output_format == "text" else output
            subprocess.run(
                ["pbcopy"],
                input=output_text.encode(),
                check=True,
            )
            console.success("Summary copied to clipboard")
        except Exception:
            console.warning("Could not copy to clipboard")

    return ExitCode.SUCCESS


def _parse_sync_log(data: dict) -> SyncOperation:
    """Parse sync log data into SyncOperation."""
    from datetime import datetime

    from spectryn.application.ai_sync_summary import (
        SyncAction,
        SyncedEntity,
        SyncEntityType,
        SyncOperation,
    )

    entities = []

    # Handle different log formats
    items = data.get("items", data.get("entities", data.get("results", [])))

    for item in items:
        # Determine action
        action_str = item.get("action", "").lower()
        if action_str == "created" or item.get("created"):
            action = SyncAction.CREATED
        elif action_str == "updated" or item.get("updated"):
            action = SyncAction.UPDATED
        elif action_str == "deleted" or item.get("deleted"):
            action = SyncAction.DELETED
        elif action_str == "failed" or item.get("error"):
            action = SyncAction.FAILED
        elif action_str == "skipped" or item.get("skipped"):
            action = SyncAction.SKIPPED
        else:
            action = SyncAction.UNCHANGED

        # Determine entity type
        type_str = item.get("type", "story").lower()
        try:
            entity_type = SyncEntityType(type_str)
        except ValueError:
            entity_type = SyncEntityType.STORY

        entity = SyncedEntity(
            entity_type=entity_type,
            entity_id=item.get("id", item.get("key", "")),
            title=item.get("title", item.get("summary", "")),
            action=action,
            source=item.get("source", ""),
            target=item.get("target", ""),
            changes=item.get("changes", []),
            error=item.get("error"),
        )
        entities.append(entity)

    # Parse timestamp
    timestamp_str = data.get("timestamp", "")
    try:
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
    except ValueError:
        timestamp = datetime.now()

    return SyncOperation(
        operation_id=data.get("operation_id", ""),
        timestamp=timestamp,
        source=data.get("source", "markdown"),
        target=data.get("target", "tracker"),
        entities=entities,
        duration_seconds=data.get("duration", data.get("duration_seconds", 0.0)),
        dry_run=data.get("dry_run", False),
    )


def _format_text(summary, console: Console) -> None:
    """Format sync summary as human-readable text."""
    console.section("Sync Summary")
    console.print()

    # Headline
    if summary.headline:
        console.print(f"  {Colors.BOLD}{summary.headline}{Colors.RESET}")
        console.print()

    # Overview
    if summary.overview:
        console.print(f"  {summary.overview}")
        console.print()

    # Stats
    if summary.stats:
        console.section("Statistics")
        for key, value in summary.stats.items():
            if value > 0:
                color = (
                    Colors.GREEN
                    if key in ("Created", "Updated")
                    else (Colors.RED if key == "Failed" else Colors.RESET)
                )
                console.print(f"  {color}{key}:{Colors.RESET} {value}")
        console.print()

    # Key changes
    if summary.key_changes:
        console.section("Key Changes")
        for change in summary.key_changes[:10]:
            console.print(f"  • {change}")
        if len(summary.key_changes) > 10:
            console.print(f"  ... and {len(summary.key_changes) - 10} more")
        console.print()

    # Issues
    if summary.issues:
        console.section(f"{Colors.YELLOW}Issues{Colors.RESET}")
        for issue in summary.issues:
            console.print(f"  {Colors.YELLOW}⚠{Colors.RESET} {issue}")
        console.print()

    # Recommendations
    if summary.recommendations:
        console.section("Recommendations")
        for rec in summary.recommendations:
            console.print(f"  {Colors.CYAN}💡{Colors.RESET} {rec}")
        console.print()


def _format_json(summary) -> str:
    """Format sync summary as JSON."""
    data = {
        "headline": summary.headline,
        "overview": summary.overview,
        "stats": summary.stats,
        "key_changes": summary.key_changes,
        "issues": summary.issues,
        "recommendations": summary.recommendations,
        "detailed_changes": summary.detailed_changes,
        "provider": summary.provider_used,
        "model": summary.model_used,
    }
    return json.dumps(data, indent=2)
