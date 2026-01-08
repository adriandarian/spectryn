"""
Pull and bidirectional sync command handlers.

This module contains handlers for pull-related commands:
- run_pull: Pull changes from Jira to markdown
- run_bidirectional_sync: Two-way sync with conflict detection
"""

import logging
from pathlib import Path

from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
from spectryn.adapters.formatters import MarkdownWriter
from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.logging import setup_logging
from spectryn.cli.output import Console


__all__ = [
    "run_bidirectional_sync",
    "run_pull",
]


def run_pull(args) -> int:
    """
    Run the pull operation to sync from Jira to markdown.

    This is the reverse of the normal sync - it fetches issue data
    from Jira and generates/updates a markdown file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectryn.application.sync import ReverseSyncOrchestrator

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    epic_key = args.epic
    output_path = getattr(args, "pull_output", None)
    existing_markdown = getattr(args, "markdown", None)
    preview_only = getattr(args, "preview", False)
    update_existing = getattr(args, "update_existing", False)
    dry_run = not getattr(args, "execute", False)

    # Determine output path
    if not output_path:
        if existing_markdown and update_existing:
            output_path = existing_markdown
        else:
            output_path = f"{epic_key}.md"

    console.header("spectra Pull (Reverse Sync)")
    console.info(f"Epic: {epic_key}")
    console.info(f"Output: {output_path}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,  # Pull is read-only from Jira
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create orchestrator
    orchestrator = ReverseSyncOrchestrator(
        tracker=tracker,
        config=config.sync,
        writer=MarkdownWriter(),
    )

    # Preview mode
    if preview_only:
        console.section("Previewing Changes")
        changes = orchestrator.preview(
            epic_key=epic_key,
            existing_markdown=existing_markdown if update_existing else None,
        )

        if not changes.has_changes:
            console.success("No changes detected")
            return ExitCode.SUCCESS

        console.info(f"Changes detected: {changes.total_changes}")
        console.print()

        if changes.new_stories:
            console.info(f"New stories ({len(changes.new_stories)}):")
            for story in changes.new_stories:
                console.item(f"{story.external_key}: {story.title}", "add")

        if changes.updated_stories:
            console.info(f"Updated stories ({len(changes.updated_stories)}):")
            for story, details in changes.updated_stories:
                console.item(f"{story.external_key}: {story.title}", "change")
                for detail in details:
                    console.detail(f"  {detail.field}: {detail.old_value} → {detail.new_value}")

        return ExitCode.SUCCESS

    # Confirmation
    if not dry_run and not getattr(args, "no_confirm", False):
        if not console.confirm(f"Pull from Jira and write to {output_path}?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run pull
    console.section("Pulling from Jira")

    def progress_callback(phase: str, current: int, total: int) -> None:
        console.progress(current, total, phase)

    result = orchestrator.pull(
        epic_key=epic_key,
        output_path=output_path,
        existing_markdown=existing_markdown if update_existing else None,
        progress_callback=progress_callback,
    )

    # Show results
    console.print()

    if result.success:
        if dry_run:
            console.success("Pull preview completed (dry-run)")
            console.info("Use --execute to write the markdown file")
        else:
            console.success("Pull completed successfully!")
            console.success(f"Markdown written to: {result.output_path}")
    else:
        console.error("Pull completed with errors")

    console.detail(f"Stories pulled: {result.stories_pulled}")
    console.detail(f"  - New: {result.stories_created}")
    console.detail(f"  - Updated: {result.stories_updated}")
    console.detail(f"Subtasks: {result.subtasks_pulled}")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings[:5]:
            console.item(warning, "warn")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR


def run_bidirectional_sync(args) -> int:
    """
    Run bidirectional sync - push changes to tracker AND pull changes back.

    This is a two-way sync that:
    1. Detects what changed locally (markdown) since last sync
    2. Detects what changed remotely (tracker) since last sync
    3. Detects conflicts (both sides changed)
    4. Resolves conflicts based on strategy
    5. Pushes local changes to tracker
    6. Pulls remote changes to markdown

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectryn.application.sync.bidirectional import BidirectionalSyncOrchestrator
    from spectryn.application.sync.conflict import Conflict, ResolutionStrategy

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    # Create console
    console = Console(
        color=not getattr(args, "no_color", False),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    markdown_path = args.input
    epic_key = args.epic
    dry_run = not getattr(args, "execute", False)
    strategy_str = getattr(args, "conflict_strategy", "ask")

    # Map strategy string to enum
    strategy_map = {
        "ask": ResolutionStrategy.ASK,
        "force-local": ResolutionStrategy.FORCE_LOCAL,
        "force-remote": ResolutionStrategy.FORCE_REMOTE,
        "skip": ResolutionStrategy.SKIP,
        "abort": ResolutionStrategy.ABORT,
    }
    resolution_strategy = strategy_map.get(strategy_str, ResolutionStrategy.ASK)

    console.header("spectra Bidirectional Sync")
    console.info(f"Markdown: {markdown_path}")
    console.info(f"Epic: {epic_key}")
    console.info(f"Conflict strategy: {strategy_str}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create orchestrator
    orchestrator = BidirectionalSyncOrchestrator(
        tracker=tracker,
        config=config.sync,
    )

    # Interactive conflict resolver
    def resolve_conflict_interactively(conflict: Conflict) -> str:
        """Prompt user to resolve a conflict."""
        console.print()
        console.warning(f"Conflict detected: {conflict.story_id} ({conflict.jira_key})")
        console.detail(f"Field: {conflict.field}")
        console.detail(f"Local value: {conflict.local_value}")
        console.detail(f"Remote value: {conflict.remote_value}")
        console.detail(f"Base value: {conflict.base_value}")
        console.print()

        while True:
            choice = input("Resolve with [l]ocal, [r]emote, [s]kip? ").lower().strip()
            if choice in ("l", "local"):
                return "local"
            if choice in ("r", "remote"):
                return "remote"
            if choice in ("s", "skip"):
                return "skip"
            console.warning("Invalid choice. Enter 'l', 'r', or 's'.")

    # Progress callback
    def progress_callback(phase: str, current: int, total: int) -> None:
        console.progress(current, total, phase)

    # Determine resolver function
    conflict_resolver = (
        resolve_conflict_interactively if resolution_strategy == ResolutionStrategy.ASK else None
    )

    # Run bidirectional sync
    console.section("Syncing bidirectionally")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        epic_key=epic_key,
        resolution_strategy=resolution_strategy,
        conflict_resolver=conflict_resolver,
        progress_callback=progress_callback,
    )

    # Show results
    console.print()
    console.section("Sync Results")

    # Push results
    console.info("Push (Markdown → Jira):")
    console.detail(f"  Stories: {result.stories_pushed}")
    console.detail(f"    Created: {result.stories_created}")
    console.detail(f"    Updated: {result.stories_updated}")
    console.detail(f"  Subtasks: {result.subtasks_synced}")

    # Pull results
    console.info("Pull (Jira → Markdown):")
    console.detail(f"  Stories pulled: {result.stories_pulled}")
    console.detail(f"  Fields updated: {result.fields_updated_locally}")

    # Conflict results
    if result.conflicts_detected > 0:
        console.print()
        console.info("Conflicts:")
        console.detail(f"  Detected: {result.conflicts_detected}")
        console.detail(f"  Resolved: {result.conflicts_resolved}")
        console.detail(f"  Skipped: {result.conflicts_skipped}")

    if result.success:
        console.print()
        if dry_run:
            console.success("Bidirectional sync preview completed (dry-run)")
            console.info("Use --execute to apply changes")
        else:
            console.success("Bidirectional sync completed successfully!")
            if result.markdown_updated:
                console.success(f"Markdown updated: {result.output_path}")
    else:
        console.print()
        console.error("Bidirectional sync completed with errors")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors[:10]:
            console.item(error, "fail")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings[:5]:
            console.item(warning, "warn")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR
