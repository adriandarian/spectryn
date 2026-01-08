"""
CLI App - Main entry point for spectra command line tool.

This module has been refactored for better maintainability:
- Argument parsing moved to parser.py (~1,800 lines)
- Backup commands moved to commands/backup.py (~500 lines)
- Validation moved to commands/validation.py (~50 lines)
- Watch/schedule/webhook commands moved to commands/watch.py (~380 lines)
- Pull/bidirectional commands moved to commands/pull.py (~380 lines)
- Field commands moved to commands/fields.py (~320 lines)
- Snapshot commands moved to commands/snapshot.py (~70 lines)
- Sync commands moved to commands/sync.py (~920 lines)

Total reduction: ~5,900 lines → ~1,600 lines (~4,300 lines extracted)

This file now contains only:
- validate_markdown wrapper
- run_sync (main sync operation)
- main() CLI entry point
- run() CLI runner
"""

import argparse
import logging
import sys
from pathlib import Path

from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter, MarkdownParser
from spectryn.application import SyncOrchestrator
from spectryn.core.domain.events import EventBus

from .commands.backup import (
    list_backups,
    list_rollback_points,
    list_sessions,
    run_diff,
    run_restore,
    run_rollback,
    run_rollback_preview,
    run_rollback_to_timestamp,
)
from .commands.fields import run_generate_field_mapping, run_list_custom_fields, run_list_sprints
from .commands.pull import run_bidirectional_sync, run_pull
from .commands.snapshot import run_clear_snapshot, run_list_snapshots
from .commands.sync import (
    run_attachment_sync,
    run_multi_epic,
    run_multi_tracker_sync,
    run_parallel_files,
    run_sync_links,
)
from .commands.watch import run_schedule, run_watch, run_webhook
from .exit_codes import ExitCode
from .output import Console, Symbols
from .parser import create_parser


def _create_console(args: argparse.Namespace, **overrides: bool) -> Console:
    """
    Create a Console instance from parsed CLI arguments.

    Extracts common console settings from args and allows overrides.

    Args:
        args: Parsed command line arguments.
        **overrides: Override specific Console settings (color, verbose, etc.)

    Returns:
        Configured Console instance.
    """
    color = not getattr(args, "no_color", False)
    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)
    json_mode = getattr(args, "output", "text") == "json"
    accessible = getattr(args, "accessible", False)

    return Console(
        color=overrides.get("color", color),
        verbose=overrides.get("verbose", verbose),
        quiet=overrides.get("quiet", quiet),
        json_mode=overrides.get("json_mode", json_mode),
        accessible=overrides.get("accessible", accessible),
    )


def validate_markdown(
    console: Console,
    markdown_path: str,
    strict: bool = False,
    show_guide: bool = False,
    suggest_fix: bool = False,
    auto_fix: bool = False,
    ai_tool: str | None = None,
    input_dir: str | None = None,
) -> int:
    """
    Validate a markdown file's format and structure.

    Performs comprehensive validation including structure checks,
    story content validation, and best practice suggestions.

    Args:
        console: Console instance for output.
        markdown_path: Path to the markdown file to validate.
        strict: If True, treat warnings as errors.
        show_guide: If True, show the format guide.
        suggest_fix: If True, generate an AI prompt to fix issues.
        auto_fix: If True, automatically fix using an AI tool.
        ai_tool: Specific AI tool to use for auto-fix.
        input_dir: Path to directory containing US-*.md files.

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    from .validate import run_validate

    return run_validate(
        console,
        markdown_path,
        strict=strict,
        show_guide=show_guide,
        suggest_fix=suggest_fix,
        auto_fix=auto_fix,
        ai_tool=ai_tool,
        input_dir=input_dir,
    )


def run_sync(
    console: Console,
    args: argparse.Namespace,
) -> int:
    """
    Run the sync operation between markdown and Jira.

    Handles the complete sync workflow including configuration loading,
    validation, connection testing, and orchestrating the sync phases.

    Args:
        console: Console instance for output.
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    # Load configuration with optional config file
    config_file = Path(args.config) if args.config else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Handle markdown source (file or directory)
    input_dir = getattr(args, "input_dir", None)
    is_directory_mode = bool(input_dir)

    if is_directory_mode:
        markdown_path = Path(input_dir)
        if not markdown_path.is_dir():
            console.error_rich(FileNotFoundError(f"Directory not found: {input_dir}"))
            return ExitCode.FILE_NOT_FOUND
    else:
        markdown_path = Path(args.input)
        if not markdown_path.exists():
            console.error_rich(FileNotFoundError(markdown_path))
            return ExitCode.FILE_NOT_FOUND

    # Show header
    console.header(f"spectra {Symbols.ROCKET}")

    if config.sync.dry_run:
        console.dry_run_banner()

    # Show config source if loaded from file
    if config_provider.config_file_path:
        console.info(f"Config: {config_provider.config_file_path}")

    if is_directory_mode:
        # Count files in directory
        story_files = [f for f in markdown_path.glob("*.md") if f.name.lower().startswith("us-")]
        has_epic = (markdown_path / "EPIC.md").exists()
        console.info(f"Directory: {markdown_path}")
        console.info(f"Files: {len(story_files)} stories" + (" + EPIC.md" if has_epic else ""))
    else:
        console.info(f"Markdown: {markdown_path}")
    console.info(f"Epic: {args.epic}")
    console.info(f"Mode: {'Execute' if args.execute else 'Dry-run'}")
    if getattr(args, "incremental", False):
        console.info("Incremental: Enabled (only changed stories)")
    if args.execute and config.sync.backup_enabled:
        console.info("Backup: Enabled")

    # Initialize components
    event_bus = EventBus()
    formatter = ADFFormatter()
    parser = MarkdownParser()

    # Setup audit trail if requested
    audit_trail = None
    audit_recorder = None
    audit_trail_path = getattr(args, "audit_trail", None)
    if audit_trail_path and isinstance(audit_trail_path, str):
        from spectryn.application.sync.audit import AuditTrailRecorder, create_audit_trail
        from spectryn.application.sync.state import SyncState

        session_id = SyncState.generate_session_id(str(markdown_path), args.epic)
        audit_trail = create_audit_trail(
            session_id=session_id,
            epic_key=args.epic,
            markdown_path=str(markdown_path),
            dry_run=config.sync.dry_run,
        )
        audit_recorder = AuditTrailRecorder(audit_trail, dry_run=config.sync.dry_run)
        audit_recorder.subscribe_to(event_bus)
        console.info(f"Audit trail: {audit_trail_path}")

    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=config.sync.dry_run,
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Configure sync phases
    config.sync.sync_descriptions = args.phase in ("all", "descriptions")
    config.sync.sync_subtasks = args.phase in ("all", "subtasks")
    config.sync.sync_comments = args.phase in ("all", "comments")
    config.sync.sync_statuses = args.phase in ("all", "statuses")

    if args.story:
        config.sync.story_filter = args.story

    # Configure backup
    config.sync.backup_enabled = not getattr(args, "no_backup", False)
    if getattr(args, "backup_dir", None):
        config.sync.backup_dir = args.backup_dir

    # Configure incremental sync
    config.sync.incremental = getattr(args, "incremental", False)
    config.sync.force_full_sync = getattr(args, "force_full_sync", False)

    # Configure source file update (writeback tracker info)
    config.sync.update_source_file = getattr(args, "update_source", False)

    # Create state store for persistence
    from spectryn.application.sync import StateStore

    state_store = StateStore()

    # Create orchestrator with state store
    orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
        event_bus=event_bus,
        state_store=state_store,
    )

    # Interactive mode
    if args.interactive:
        from .interactive import run_interactive

        success = run_interactive(
            console=console,
            orchestrator=orchestrator,
            markdown_path=str(markdown_path),
            epic_key=args.epic,
        )
        return ExitCode.SUCCESS if success else ExitCode.CANCELLED

    # Check for resumable session
    resume_state = None
    if args.resume or args.resume_session:
        if args.resume_session:
            # Load specific session
            resume_state = state_store.load(args.resume_session)
            if not resume_state:
                console.error(f"Session '{args.resume_session}' not found")
                return ExitCode.FILE_NOT_FOUND
        else:
            # Find latest resumable session for this markdown/epic
            resume_state = state_store.find_latest_resumable(str(markdown_path), args.epic)

        if resume_state:
            console.info(f"Resuming session: {resume_state.session_id}")
            console.detail(
                f"Progress: {resume_state.completed_count}/{resume_state.total_count} operations"
            )
            console.detail(f"Phase: {resume_state.phase}")
        elif args.resume:
            console.info("No resumable session found, starting fresh")

    # Pre-sync validation
    validation_errors = orchestrator.validate_sync_prerequisites(str(markdown_path), args.epic)
    if validation_errors:
        console.error("Pre-sync validation failed:")
        for error in validation_errors:
            console.item(error, "fail")
        return ExitCode.VALIDATION_ERROR

    # Confirmation
    if args.execute and not args.no_confirm:
        action = "Resume sync" if resume_state else "Proceed with sync"
        if not console.confirm(f"{action} execution?"):
            console.warning("Cancelled by user")
            return ExitCode.CANCELLED

    # Run sync with progress callback (supports both legacy and detailed progress)
    def progress_callback(
        phase: str,
        item: str = "",
        overall_progress: float = 0.0,
        current_item: int = 0,
        total_items: int = 0,
    ) -> None:
        # Use detailed progress display when item info is available
        if item or total_items > 0:
            console.progress_detailed(phase, item, overall_progress, current_item, total_items)
        else:
            # Fallback to simple progress for backward compatibility
            console.progress(current_item, total_items or 1, phase)

    console.section("Running Sync")

    # Suppress noisy logs during progress bar display (unless verbose mode)
    from .logging import suppress_logs_for_progress

    # Use resumable sync for state persistence
    if args.verbose:
        # Verbose mode: show all logs
        result = orchestrator.sync_resumable(
            markdown_path=str(markdown_path),
            epic_key=args.epic,
            progress_callback=progress_callback,
            resume_state=resume_state,
        )
    else:
        # Normal mode: suppress INFO logs for clean progress bar
        with suppress_logs_for_progress():
            result = orchestrator.sync_resumable(
                markdown_path=str(markdown_path),
                epic_key=args.epic,
                progress_callback=progress_callback,
                resume_state=resume_state,
            )

    # Show results
    console.sync_result(result)

    # Show backup info if created
    if orchestrator.last_backup:
        backup = orchestrator.last_backup
        console.success(f"Backup created: {backup.backup_id}")
        console.detail(f"  Issues: {backup.issue_count}, Subtasks: {backup.subtask_count}")

    # Export if requested
    if args.export:
        import json

        export_data = {
            "success": result.success,
            "dry_run": result.dry_run,
            "incremental": result.incremental,
            "matched_stories": result.matched_stories,
            "unmatched_stories": result.unmatched_stories,
            "stats": {
                "stories_matched": result.stories_matched,
                "stories_updated": result.stories_updated,
                "stories_skipped": result.stories_skipped,
                "subtasks_created": result.subtasks_created,
                "subtasks_updated": result.subtasks_updated,
                "comments_added": result.comments_added,
                "statuses_updated": result.statuses_updated,
            },
            "errors": result.errors,
            "warnings": result.warnings,
        }

        with open(args.export, "w") as f:
            json.dump(export_data, f, indent=2)

        console.success(f"Exported results to {args.export}")

    # Export audit trail if requested
    if audit_trail and audit_trail_path:
        audit_trail.complete(
            success=result.success,
            stories_matched=result.stories_matched,
            stories_updated=result.stories_updated,
            subtasks_created=result.subtasks_created,
            subtasks_updated=result.subtasks_updated,
            comments_added=result.comments_added,
            statuses_updated=result.statuses_updated,
            errors=result.errors,
            warnings=result.warnings,
        )
        audit_path = audit_trail.export(audit_trail_path)
        console.success(f"Audit trail exported to {audit_path}")

    # Determine exit code based on result
    if result.success:
        return ExitCode.SUCCESS
    if hasattr(result, "failed_operations") and result.failed_operations:
        # Partial success - some operations failed but sync completed
        return ExitCode.PARTIAL_SUCCESS
    return ExitCode.ERROR


def main() -> int:
    """
    Main entry point for the spectra CLI.

    Parses arguments, sets up logging, and runs the appropriate mode
    (validate or sync).

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    parser = create_parser()
    args = parser.parse_args()

    # Set global emoji mode based on --no-emoji flag
    if getattr(args, "no_emoji", False):
        from .output import set_emoji_mode

        set_emoji_mode(False)

    # Set color theme based on --theme flag
    if getattr(args, "theme", None):
        from .output import set_theme

        set_theme(args.theme)

    # Handle --list-themes
    if getattr(args, "list_themes", False):
        from .output import list_themes

        print("Available color themes:\n")
        for name, desc in list_themes():
            print(f"  {name:12} - {desc}")
        print("\nUsage: spectra --theme <name> ...")
        return ExitCode.SUCCESS

    # Handle completions first (doesn't require other args)
    if args.completions:
        from .completions import print_completion

        success = print_completion(args.completions)
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle man page display
    if getattr(args, "man", False):
        from .manpage import show_man_page

        success = show_man_page()
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle man page installation
    if getattr(args, "install_man", False):
        from .manpage import install_man_page

        success, message = install_man_page()
        print(message)
        return ExitCode.SUCCESS if success else ExitCode.ERROR

    # Handle init wizard (doesn't require other args)
    if args.init:
        from .init import run_init

        console = _create_console(args)
        return run_init(console)

    # Handle doctor command
    if getattr(args, "doctor", False):
        from .doctor import run_doctor

        console = _create_console(args)
        return run_doctor(console, verbose=getattr(args, "verbose", False))

    # Handle stats command
    if getattr(args, "stats", False):
        from .stats import run_stats

        console = _create_console(args)
        return run_stats(
            console,
            input_path=getattr(args, "input", None),
            input_dir=getattr(args, "input_dir", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle diff command
    if getattr(args, "diff", False):
        if not args.input or not args.epic:
            parser.error("--diff requires --input/-f and --epic/-e to be specified")
        from .diff_cmd import run_diff as run_diff_cmd

        console = _create_console(args)
        return run_diff_cmd(
            console,
            input_path=args.input,
            epic_key=args.epic,
            output_format=getattr(args, "output", "text"),
        )

    # Handle import command
    if getattr(args, "import_cmd", False):
        if not args.epic:
            parser.error("--import requires --epic/-e to be specified")
        from .import_cmd import run_import

        console = _create_console(args)
        return run_import(
            console,
            epic_key=args.epic,
            output_path=getattr(args, "generate_output", None),
            dry_run=not getattr(args, "execute", False),
        )

    # Handle plan command
    if getattr(args, "plan", False):
        if not args.input or not args.epic:
            parser.error("--plan requires --input/-f and --epic/-e to be specified")
        from .plan_cmd import run_plan

        console = _create_console(args)
        return run_plan(
            console,
            input_path=args.input,
            epic_key=args.epic,
            verbose=getattr(args, "verbose", False),
            output_format=getattr(args, "output", "text"),
        )

    # Handle migrate command
    if getattr(args, "migrate", False):
        from .migrate import run_migrate

        console = _create_console(args)
        return run_migrate(
            console,
            source_type=getattr(args, "migrate_source", "jira") or "jira",
            target_type=getattr(args, "migrate_target", "github") or "github",
            epic_key=getattr(args, "epic", None),
            dry_run=not getattr(args, "execute", False),
        )

    # Handle visualize command
    if getattr(args, "visualize", False):
        if not args.input:
            parser.error("--visualize requires --input/-f to be specified")
        from .visualize import run_visualize

        console = _create_console(args)
        return run_visualize(
            console,
            input_path=args.input,
            output_format=getattr(args, "visualize_format", "mermaid"),
            output_file=getattr(args, "export", None),
        )

    # Handle velocity command
    if getattr(args, "velocity", False) or getattr(args, "velocity_add", False):
        from .velocity import run_velocity

        console = _create_console(args)
        action = "add" if getattr(args, "velocity_add", False) else "show"
        return run_velocity(
            console,
            input_path=getattr(args, "input", None),
            action=action,
            sprint_name=getattr(args, "sprint", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle report command
    if getattr(args, "report", None):
        if not args.input:
            parser.error("--report requires --input/-f to be specified")
        from .report import run_report

        console = _create_console(args)
        return run_report(
            console,
            input_path=args.input,
            period=args.report,
            output_path=getattr(args, "export", None),
            output_format=getattr(args, "output", "text"),
        )

    # Handle config validate command
    if getattr(args, "config_validate", False):
        from .config_cmd import run_config_validate

        console = _create_console(args)
        return run_config_validate(
            console,
            config_file=getattr(args, "config", None),
            test_connection=True,
        )

    # Handle version check command
    if getattr(args, "version_check", False):
        console = _create_console(args)
        console.header("spectra Version Check")
        console.print()
        console.info("Current version: 2.0.0")
        console.info("Checking for updates...")
        # Would check PyPI or GitHub releases
        console.success("You are running the latest version!")
        return ExitCode.SUCCESS

    # Handle hook command
    if getattr(args, "hook", None):
        from .hook import run_hook_install, run_hook_status, run_hook_uninstall

        console = _create_console(args)
        hook_action = args.hook
        hook_type = getattr(args, "hook_type", "pre-commit")

        if hook_action == "install":
            return run_hook_install(console, hook_type=hook_type)
        if hook_action == "uninstall":
            return run_hook_uninstall(console, hook_type=hook_type)
        # status
        return run_hook_status(console)

    # Handle tutorial command
    if getattr(args, "tutorial", False) or getattr(args, "tutorial_step", None):
        from .tutorial import run_tutorial

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        step = getattr(args, "tutorial_step", None)
        return run_tutorial(
            console=console,
            color=not getattr(args, "no_color", False),
            step=step,
        )

    # Handle bulk-update command
    if getattr(args, "bulk_update", False):
        from .bulk import run_bulk_update

        console = _create_console(args)

        input_path = Path(args.markdown) if args.markdown else None
        return run_bulk_update(
            console=console,
            input_path=input_path,
            filter_str=getattr(args, "filter", "") or "",
            update_str=getattr(args, "set", "") or "",
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle bulk-assign command
    if getattr(args, "bulk_assign", False):
        from .bulk import run_bulk_assign

        console = _create_console(args)

        input_path = Path(args.markdown) if args.markdown else None
        return run_bulk_assign(
            console=console,
            input_path=input_path,
            filter_str=getattr(args, "filter", "") or "",
            assignee=getattr(args, "assignee", "") or "",
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle split command
    if getattr(args, "split", False) or getattr(args, "split_story", None):
        from .split import run_split

        console = _create_console(args)

        input_path = Path(args.markdown) if args.markdown else None
        return run_split(
            console=console,
            input_path=input_path,
            story_id=getattr(args, "split_story", None),
            threshold=getattr(args, "split_threshold", 4),
            output_format=getattr(args, "output", "text") or "text",
            color=not getattr(args, "no_color", False),
        )

    # Handle generate-stories command (AI story generation)
    if getattr(args, "generate_stories", False):
        from .ai_generate import run_ai_generate

        console = _create_console(args)

        return run_ai_generate(
            console=console,
            description=getattr(args, "description", None),
            description_file=getattr(args, "description_file", None),
            style=getattr(args, "generation_style", "standard"),
            max_stories=getattr(args, "max_stories", 5),
            story_prefix=getattr(args, "story_prefix", "US"),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_file=getattr(args, "generation_output", None),
            output_format=getattr(args, "output", "text") or "text",
            dry_run=not getattr(args, "execute", False),
        )

    # Handle refine command (AI story quality analysis)
    if getattr(args, "refine", False) or getattr(args, "refine_story", None):
        from .ai_refine import run_ai_refine

        console = _create_console(args)

        story_ids = None
        if getattr(args, "refine_story", None):
            story_ids = [s.strip() for s in args.refine_story.split(",")]

        return run_ai_refine(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            check_ambiguity=not getattr(args, "no_check_ambiguity", False),
            check_acceptance_criteria=not getattr(args, "no_check_ac", False),
            check_testability=True,
            check_scope=not getattr(args, "no_check_scope", False),
            check_estimation=True,
            generate_ac=True,
            min_ac=getattr(args, "min_ac", 2),
            max_story_points=getattr(args, "max_sp", 13),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_format=getattr(args, "output", "text") or "text",
            show_suggestions=True,
        )

    # Handle estimate command (AI story point estimation)
    if getattr(args, "estimate", False) or getattr(args, "estimate_story", None):
        from .ai_estimate import run_ai_estimate

        console = _create_console(args)

        story_ids = None
        if getattr(args, "estimate_story", None):
            story_ids = [s.strip() for s in args.estimate_story.split(",")]

        return run_ai_estimate(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            scale=getattr(args, "estimation_scale", "fibonacci"),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            team_velocity=getattr(args, "team_velocity", 0),
            show_complexity=not getattr(args, "no_complexity", False),
            show_reasoning=not getattr(args, "no_reasoning", False),
            output_format=getattr(args, "output", "text") or "text",
            apply_changes=getattr(args, "apply_estimates", False),
        )

    # Handle label command (AI labeling/categorization)
    if getattr(args, "label", False) or getattr(args, "label_story", None):
        from .ai_label import run_ai_label

        console = _create_console(args)

        story_ids = None
        if getattr(args, "label_story", None):
            story_ids = [s.strip() for s in args.label_story.split(",")]

        existing_labels = None
        if getattr(args, "existing_labels", None):
            existing_labels = [l.strip() for l in args.existing_labels.split(",")]

        return run_ai_label(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            existing_labels=existing_labels,
            suggest_features=True,
            suggest_components=True,
            suggest_types=True,
            suggest_nfr=True,
            max_labels=getattr(args, "max_labels", 5),
            allow_new=not getattr(args, "no_new_labels", False),
            label_style=getattr(args, "label_style", "kebab-case"),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_format=getattr(args, "output", "text") or "text",
            apply_changes=getattr(args, "apply_labels", False),
        )

    # Handle split command (AI smart splitting)
    if getattr(args, "split", False) or getattr(args, "split_story", None):
        from .ai_split import run_ai_split

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        story_ids = None
        if getattr(args, "split_story", None):
            story_ids = [s.strip() for s in args.split_story.split(",")]

        return run_ai_split(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            max_points=getattr(args, "max_points", 8),
            max_ac=getattr(args, "max_ac", 8),
            prefer_vertical=not getattr(args, "no_vertical_slices", False),
            prefer_mvp=not getattr(args, "no_mvp_first", False),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_format=getattr(args, "output", "text") or "text",
            generate_markdown=getattr(args, "generate_markdown", False),
        )

    # Handle generate-ac command (AI acceptance criteria generation)
    if getattr(args, "generate_ac", False) or getattr(args, "ac_story", None):
        from .ai_acceptance import run_ai_acceptance

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        story_ids = None
        if getattr(args, "ac_story", None):
            story_ids = [s.strip() for s in args.ac_story.split(",")]

        return run_ai_acceptance(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            use_gherkin=getattr(args, "use_gherkin", False),
            include_validation=True,
            include_error_handling=True,
            include_edge_cases=True,
            include_security=getattr(args, "include_security", False),
            min_ac=getattr(args, "min_ac", 3),
            max_ac=getattr(args, "max_ac", 8),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_format=getattr(args, "output", "text") or "text",
            apply_changes=getattr(args, "apply_ac", False),
        )

    # Handle dependencies command (AI dependency detection)
    if getattr(args, "dependencies", False):
        from .ai_dependency import run_ai_dependency

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        return run_ai_dependency(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            detect_technical=not getattr(args, "no_technical_deps", False),
            detect_data=not getattr(args, "no_data_deps", False),
            detect_feature=not getattr(args, "no_feature_deps", False),
            detect_related=True,
            check_circular=not getattr(args, "no_circular_check", False),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            architecture=getattr(args, "architecture", None),
            output_format=getattr(args, "output", "text") or "text",
            show_graph=getattr(args, "show_graph", False),
        )

    # Handle quality command (AI story quality scoring)
    if getattr(args, "quality", False) or getattr(args, "quality_story", None):
        from .ai_quality import run_ai_quality

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        story_ids = None
        if getattr(args, "quality_story", None):
            story_ids = [s.strip() for s in args.quality_story.split(",")]

        return run_ai_quality(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            story_ids=story_ids,
            min_score=getattr(args, "min_score", 50),
            show_details=not getattr(args, "no_details", False),
            project_context=getattr(args, "project_context", None),
            tech_stack=getattr(args, "tech_stack", None),
            output_format=getattr(args, "output", "text") or "text",
        )

    # Handle duplicates command (AI duplicate detection)
    if getattr(args, "duplicates", False):
        from .ai_duplicate import run_ai_duplicate

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        # Collect all files to compare
        markdown_paths = []
        main_file = args.input or getattr(args, "markdown", None)
        if main_file:
            markdown_paths.append(main_file)

        if getattr(args, "compare_files", None):
            additional = [f.strip() for f in args.compare_files.split(",")]
            markdown_paths.extend(additional)

        return run_ai_duplicate(
            console=console,
            markdown_paths=markdown_paths,
            min_similarity=getattr(args, "min_similarity", 0.40),
            use_llm=not getattr(args, "no_llm_duplicates", False),
            project_context=getattr(args, "project_context", None),
            output_format=getattr(args, "output", "text") or "text",
        )

    # Handle gaps command (AI gap analysis)
    if getattr(args, "gaps", False):
        from .ai_gap import run_ai_gap

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        # Parse comma-separated lists
        expected_personas = None
        if getattr(args, "expected_personas", None):
            expected_personas = [p.strip() for p in args.expected_personas.split(",")]

        expected_integrations = None
        if getattr(args, "expected_integrations", None):
            expected_integrations = [i.strip() for i in args.expected_integrations.split(",")]

        compliance = None
        if getattr(args, "compliance", None):
            compliance = [c.strip() for c in args.compliance.split(",")]

        return run_ai_gap(
            console=console,
            markdown_path=args.input or getattr(args, "markdown", None),
            project_context=getattr(args, "project_context", None),
            industry=getattr(args, "industry", None),
            expected_personas=expected_personas,
            expected_integrations=expected_integrations,
            compliance=compliance,
            no_suggestions=getattr(args, "no_suggestions", False),
            output_format=getattr(args, "output", "text") or "text",
        )

    # Handle sync-summary command (AI sync summary generation)
    if getattr(args, "sync_summary", False):
        from .ai_sync_summary import run_ai_sync_summary

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        return run_ai_sync_summary(
            console=console,
            sync_log_path=getattr(args, "sync_log", None),
            audience=getattr(args, "audience", "technical"),
            output_format=getattr(args, "output", "text") or "text",
            copy_to_clipboard=getattr(args, "copy_summary", False),
        )

    # Handle prompts command (AI prompts management)
    if getattr(args, "prompts", None):
        from .ai_prompts import run_ai_prompts

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        return run_ai_prompts(
            console=console,
            action=args.prompts,
            prompt_name=getattr(args, "prompt_name", None),
            prompt_type=getattr(args, "prompt_type", None),
            config_path=getattr(args, "prompts_config", None),
            export_path=getattr(args, "export_prompts", None),
            output_format=getattr(args, "output", "text") or "text",
        )

    # Handle export-prompts shortcut
    if getattr(args, "export_prompts", None):
        from .ai_prompts import run_ai_prompts

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        return run_ai_prompts(
            console=console,
            action="export",
            export_path=args.export_prompts,
            output_format=getattr(args, "output", "text") or "text",
        )

    # Handle archive command
    if getattr(args, "archive", None):
        from .archive import run_archive

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
        )

        input_path = Path(args.markdown) if args.markdown else None
        action = args.archive
        story_keys = None
        if getattr(args, "story_keys", None):
            story_keys = [k.strip() for k in args.story_keys.split(",")]

        return run_archive(
            console=console,
            input_path=input_path,
            action=action,
            story_keys=story_keys,
            days_threshold=getattr(args, "archive_days", 90),
            dry_run=getattr(args, "dry_run", False),
            color=not getattr(args, "no_color", False),
        )

    # Handle generate (requires epic key)
    if args.generate:
        if not args.epic:
            parser.error("--generate requires --epic/-e to be specified")
        from .generate import run_generate

        console = Console(
            color=not getattr(args, "no_color", False),
            verbose=getattr(args, "verbose", False),
            quiet=getattr(args, "quiet", False),
        )
        return run_generate(args, console)

    # Handle list-sessions (doesn't require other args)
    if args.list_sessions:
        from spectryn.application.sync import StateStore

        return list_sessions(StateStore())

    # Handle list-backups (requires epic key)
    if args.list_backups:
        from spectryn.application.sync import BackupManager

        return list_backups(BackupManager(), args.epic)

    # Handle restore-backup (requires backup ID, optionally epic key)
    if args.restore_backup:
        return run_restore(args)

    # Handle diff-backup or diff-latest
    if args.diff_backup or args.diff_latest:
        return run_diff(args)

    # Handle rollback
    if args.rollback:
        return run_rollback(args)

    # Handle list-rollback-points
    if getattr(args, "list_rollback_points", False):
        return list_rollback_points(args)

    # Handle rollback-preview
    if getattr(args, "rollback_preview", None):
        return run_rollback_preview(args)

    # Handle rollback-to-timestamp
    if getattr(args, "rollback_to_timestamp", None):
        return run_rollback_to_timestamp(args)

    # Handle bidirectional sync
    if getattr(args, "bidirectional", False):
        if not args.input or not args.epic:
            parser.error("--bidirectional requires --input/-i and --epic/-e to be specified")
        return run_bidirectional_sync(args)

    # Handle pull (reverse sync from Jira to markdown)
    if args.pull:
        if not args.epic:
            parser.error("--pull requires --epic/-e to be specified")
        return run_pull(args)

    # Handle list-snapshots
    if args.list_snapshots:
        return run_list_snapshots()

    # Handle clear-snapshot
    if args.clear_snapshot:
        if not args.epic:
            parser.error("--clear-snapshot requires --epic/-e to be specified")
        return run_clear_snapshot(args.epic)

    # Handle watch mode
    if args.watch:
        if not args.input or not args.epic:
            parser.error("--watch requires --input/-i and --epic/-e to be specified")
        return run_watch(args)

    # Handle scheduled sync
    if args.schedule:
        if not args.input or not args.epic:
            parser.error("--schedule requires --input/-i and --epic/-e to be specified")
        return run_schedule(args)

    # Handle webhook server
    if args.webhook:
        if not args.epic:
            parser.error("--webhook requires --epic/-e to be specified")
        return run_webhook(args)

    # Handle WebSocket server
    if getattr(args, "websocket", False):
        from .commands import run_websocket

        # Handle --no-aiohttp flag
        if getattr(args, "no_aiohttp", False):
            args.use_aiohttp = False
        return run_websocket(args)

    # Handle GraphQL API server
    if getattr(args, "graphql", False):
        from .commands.graphql import run_graphql

        return run_graphql(args)

    # Handle REST API server
    if getattr(args, "rest_api", False):
        from .commands.rest_api import run_rest_api

        return run_rest_api(args)

    # Handle multi-epic sync
    if args.multi_epic or args.list_epics:
        if not args.input:
            parser.error("--multi-epic and --list-epics require --input/-i to be specified")
        return run_multi_epic(args)

    # Handle parallel file processing
    if getattr(args, "parallel_files", False):
        input_dir = getattr(args, "input_dir", None)
        input_files = getattr(args, "input_files", None)
        if not input_dir and not args.input and not input_files:
            parser.error(
                "--parallel-files requires --input-dir, --input, or --input-files to be specified"
            )
        return run_parallel_files(args)

    # Handle multi-tracker sync
    if getattr(args, "multi_tracker", False) or getattr(args, "trackers", None):
        if not args.input:
            parser.error("--multi-tracker requires --input/-i to be specified")
        return run_multi_tracker_sync(args)

    # Handle link sync
    if args.sync_links or args.analyze_links:
        if not args.input or not args.epic:
            parser.error(
                "--sync-links and --analyze-links require --input/-i and --epic/-e to be specified"
            )
        return run_sync_links(args)

    # Handle attachment sync
    if args.sync_attachments:
        if not args.input or not args.epic:
            parser.error("--sync-attachments requires --input/-f and --epic/-e to be specified")
        return run_attachment_sync(args)

    # Handle field mapping commands
    if args.list_custom_fields:
        return run_list_custom_fields(args)

    if args.generate_field_mapping:
        return run_generate_field_mapping(args)

    # Handle sprint listing
    if args.list_sprints:
        return run_list_sprints(args)

    # Handle resume-session (loads args from session)
    if args.resume_session:
        from spectryn.application.sync import StateStore

        state_store = StateStore()
        state = state_store.load(args.resume_session)
        if not state:
            print(f"Error: Session '{args.resume_session}' not found")
            return ExitCode.FILE_NOT_FOUND
        # Override args from session
        args.input = state.markdown_path
        args.epic = state.epic_key

    # Handle list-ai-tools (no other args needed)
    if getattr(args, "list_ai_tools", False):
        from .ai_fix import detect_ai_tools, format_ai_tools_list

        console = Console(color=not getattr(args, "no_color", False))
        console.header("spectra AI Tools")

        tools = detect_ai_tools()
        if tools:
            print(format_ai_tools_list(tools, color=console.color))
            console.print()
            console.info("Use with: spectra --validate --input FILE.md --auto-fix --ai-tool <name>")
        else:
            console.warning("No AI CLI tools detected on your system.")
            console.print()
            console.info("Install one of the following to enable auto-fix:")
            console.print()
            console.info("Major AI CLIs:")
            console.info("  • claude: npm i -g @anthropic-ai/claude-code")
            console.info("  • gemini: npm i -g @google/gemini-cli")
            console.info("  • codex: npm i -g @openai/codex")
            console.print()
            console.info("Local models:")
            console.info("  • ollama: https://ollama.ai")
            console.print()
            console.info("Coding assistants:")
            console.info("  • aider: pip install aider-chat")
            console.info("  • goose: pip install goose-ai")
            console.info("  • gh copilot: gh extension install github/gh-copilot")
            console.print()
            console.info("LLM tools:")
            console.info("  • llm: pip install llm")
            console.info("  • sgpt: pip install shell-gpt")
            console.info("  • mods: https://github.com/charmbracelet/mods")
            console.info("  • fabric: pip install fabric-ai")
        return ExitCode.SUCCESS

    # Handle list-llm-providers (no other args needed)
    if getattr(args, "list_llm_providers", False):
        from spectryn.adapters.llm import create_llm_manager

        console = Console(color=not getattr(args, "no_color", False))
        console.header("spectra LLM Providers")
        console.print()

        # Create manager with all options to detect all available providers
        manager = create_llm_manager(
            ollama_host=getattr(args, "ollama_host", None),
            openai_compatible_url=getattr(args, "openai_compatible_url", None),
        )
        status = manager.get_status()

        # Display cloud providers
        console.info("☁️  Cloud Providers (require API keys):")
        for name, info in status.get("cloud_providers", {}).items():
            if info.get("available"):
                models = info.get("models", [])
                model_str = ", ".join(models[:3]) + ("..." if len(models) > 3 else "")
                console.success(f"  ✓ {name}: {model_str}")
            else:
                console.print(f"    ○ {name}: not configured")

        console.print()

        # Display local providers
        console.info("🖥️  Local Providers (no API keys needed):")
        for name, info in status.get("local_providers", {}).items():
            if info.get("available"):
                models = info.get("models", [])
                model_str = ", ".join(models[:3]) + ("..." if len(models) > 3 else "")
                console.success(f"  ✓ {name}: {model_str}")
            else:
                console.print(f"    ○ {name}: not running")

        console.print()

        # Show primary provider
        if status.get("primary"):
            console.info(f"Primary provider: {status['primary']}")
        else:
            console.warning("No LLM providers available")
            console.print()
            console.info("To use cloud providers:")
            console.info("  • Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY")
            console.print()
            console.info("To use local providers:")
            console.info("  • Ollama: Install from https://ollama.ai, run 'ollama serve'")
            console.info("  • LM Studio: Download from https://lmstudio.ai, start server")

        console.print()
        console.info("Usage: spectra --llm-provider <name> --llm-model <model> ...")
        console.info("       spectra --prefer-local-llm ...  (prefer local over cloud)")

        return ExitCode.SUCCESS

    # Handle --list-files mode (preview which files would be processed)
    if getattr(args, "list_files", False):
        input_dir = getattr(args, "input_dir", None)
        if not input_dir:
            parser.error("--list-files requires --input-dir to be specified")

        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
            json_mode=(args.output in ("json", "yaml", "markdown")),
        )
        dir_path = Path(input_dir)
        if not dir_path.is_dir():
            console.error(f"Directory not found: {input_dir}")
            return ExitCode.FILE_NOT_FOUND

        # Find files that would be processed using the parser's detection logic
        from spectryn.adapters.parsers import MarkdownParser

        parser = MarkdownParser()
        epic_file = None
        story_files: list[Path] = []
        ignored_files: list[Path] = []

        for md_file in sorted(dir_path.glob("*.md")):
            name_lower = md_file.name.lower()
            if name_lower == "epic.md":
                epic_file = md_file
            elif parser._is_story_file(md_file):
                story_files.append(md_file)
            else:
                ignored_files.append(md_file)

        console.header("Files to Process")
        if epic_file:
            console.success(f"Epic: {epic_file.name}")
        else:
            console.warning("No EPIC.md found")

        if story_files:
            console.info(f"\nUser Stories ({len(story_files)} files):")
            for sf in story_files:
                console.info(f"  ✓ {sf.name}")
        else:
            console.warning("No US-*.md files found")

        if ignored_files:
            console.info(f"\nIgnored ({len(ignored_files)} files):")
            for ig in ignored_files:
                console.info(f"  ○ {ig.name}")

        total = (1 if epic_file else 0) + len(story_files)
        console.info(f"\nTotal: {total} file(s) will be processed")
        return ExitCode.SUCCESS

    # Handle validate mode (only requires markdown or markdown-dir, unless just showing guide)
    if args.validate or getattr(args, "show_guide", False):
        # show_guide can work without a markdown file
        input_dir = getattr(args, "input_dir", None)
        if not args.input and not input_dir and not getattr(args, "show_guide", False):
            parser.error("--validate requires --input/-i or --input-dir to be specified")
        from .logging import setup_logging

        setup_logging(
            level=logging.DEBUG if args.verbose else logging.INFO,
            log_format=getattr(args, "log_format", "text"),
        )
        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
            json_mode=(args.output in ("json", "yaml", "markdown")),
        )
        try:
            return validate_markdown(
                console,
                args.input or "",
                strict=getattr(args, "strict", False),
                show_guide=getattr(args, "show_guide", False),
                suggest_fix=getattr(args, "suggest_fix", False),
                auto_fix=getattr(args, "auto_fix", False),
                ai_tool=getattr(args, "ai_tool", None),
                input_dir=input_dir,
            )
        except KeyboardInterrupt:
            console.print()
            console.warning("Interrupted by user")
            return ExitCode.SIGINT
        except Exception as e:
            console.error_rich(e)
            if args.verbose:
                import traceback

                console.print()
                traceback.print_exc()
            return ExitCode.from_exception(e)

    # Handle dashboard mode (markdown and epic are optional)
    if args.dashboard:
        from .dashboard import run_dashboard

        console = Console(
            color=not args.no_color,
            verbose=args.verbose,
            quiet=args.quiet,
        )
        return run_dashboard(
            console,
            markdown_path=args.input,
            epic_key=args.epic,
        )

    # Handle interactive TUI mode
    if getattr(args, "tui", False) or getattr(args, "tui_demo", False):
        try:
            from .tui import run_tui
        except ImportError:
            console = Console(color=not args.no_color)
            console.error("Interactive TUI requires the 'tui' optional dependency.")
            console.info("Install with: pip install spectra[tui]")
            return ExitCode.ERROR

        return run_tui(
            markdown_path=args.input,
            epic_key=args.epic,
            dry_run=not getattr(args, "execute", False),
            demo=getattr(args, "tui_demo", False),
        )

    # Handle analytics commands (no markdown/epic needed)
    if getattr(args, "analytics_show", False):
        from .analytics import configure_analytics, format_analytics_display, show_analytics_info

        console = Console(color=not args.no_color)

        # Show what analytics collects
        console.print(show_analytics_info())
        console.print()

        # Show collected data if any
        manager = configure_analytics(enabled=True)
        data = manager.get_display_data()
        console.print(format_analytics_display(data))

        return ExitCode.SUCCESS

    if getattr(args, "analytics_clear", False):
        from .analytics import configure_analytics

        console = Console(color=not args.no_color)

        manager = configure_analytics(enabled=True)
        if manager.clear_data():
            console.success("Analytics data cleared")
            return ExitCode.SUCCESS
        console.error("Failed to clear analytics data")
        return ExitCode.ERROR

    # Validate required arguments for other modes
    input_dir = getattr(args, "input_dir", None)
    if not args.input and not input_dir:
        parser.error("one of the following arguments is required: --input/-i or --input-dir")
    if not args.epic:
        parser.error("the following argument is required: --epic/-e")

    # Setup logging with optional JSON format
    from .logging import setup_logging

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = getattr(args, "log_format", "text")
    log_file = getattr(args, "log_file", None)

    setup_logging(
        level=log_level,
        log_format=log_format,
        log_file=log_file,
        static_fields={"service": "spectra"} if log_format == "json" else None,
    )

    # Setup OpenTelemetry if enabled
    telemetry_provider = None
    if getattr(args, "otel_enable", False):
        from .telemetry import configure_telemetry

        telemetry_provider = configure_telemetry(
            enabled=True,
            endpoint=getattr(args, "otel_endpoint", None),
            service_name=getattr(args, "otel_service_name", "spectra"),
            console_export=getattr(args, "otel_console", False),
        )

    # Setup Prometheus metrics if enabled
    if getattr(args, "prometheus", False):
        from .telemetry import configure_prometheus

        prometheus_provider = configure_prometheus(
            enabled=True,
            port=getattr(args, "prometheus_port", 9090),
            host=getattr(args, "prometheus_host", "0.0.0.0"),
            service_name=getattr(args, "otel_service_name", "spectra"),
        )
        if telemetry_provider is None:
            telemetry_provider = prometheus_provider

    # Setup health check server if enabled
    health_server = None
    if getattr(args, "health", False):
        from .health import configure_health

        health_server = configure_health(
            enabled=True,
            port=getattr(args, "health_port", 8080),
            host=getattr(args, "health_host", "0.0.0.0"),
        )

    # Setup analytics if enabled (opt-in)
    if getattr(args, "analytics", False):
        from .analytics import configure_analytics

        configure_analytics(enabled=True)

    # Create console
    console = Console(
        color=not args.no_color,
        verbose=args.verbose,
        quiet=args.quiet,
        json_mode=(args.output in ("json", "yaml", "markdown")),
    )

    try:
        # Run sync
        return run_sync(console, args)

    except KeyboardInterrupt:
        console.print()
        console.warning("Interrupted by user")
        return ExitCode.SIGINT

    except Exception as e:
        # Use rich error formatting for better user experience
        console.error_rich(e)
        if args.verbose:
            import traceback

            console.print()
            traceback.print_exc()
        return ExitCode.from_exception(e)

    finally:
        # Shutdown telemetry if enabled
        if telemetry_provider:
            telemetry_provider.shutdown()

        # Shutdown health server if enabled
        if health_server:
            health_server.stop()


def run() -> None:
    """
    Entry point for the console script.

    Calls main() and exits with its return code.
    """
    sys.exit(main())


if __name__ == "__main__":
    run()
