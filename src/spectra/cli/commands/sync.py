"""
Sync command handlers.

This module contains handlers for sync-related commands:
- run_sync: Main sync operation (forwarding stub - implemented in app.py)
- run_sync_links: Sync cross-project links
- run_multi_epic: Multi-epic sync mode
- run_parallel_files: Parallel file processing
- run_multi_tracker_sync: Multi-tracker sync
- run_attachment_sync: Sync file attachments

Note: Watch/schedule/webhook commands are in watch.py
Note: Pull/bidirectional commands are in pull.py
"""

import logging
from pathlib import Path

from spectra.cli.exit_codes import ExitCode
from spectra.cli.output import Console, Symbols


__all__ = [
    "run_attachment_sync",
    "run_multi_epic",
    "run_multi_tracker_sync",
    "run_parallel_files",
    "run_sync",
    "run_sync_links",
]


def run_sync(console, args) -> int:
    """Run the main sync operation."""
    # Import here to avoid circular imports
    from spectra.cli import app as _app

    return _app.run_sync(console, args)


def run_sync_links(args) -> int:
    """
    Run link sync mode.

    Syncs cross-project issue links from markdown to Jira.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync import LinkSyncOrchestrator, SyncOrchestrator
    from spectra.cli.logging import setup_logging

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
    analyze_only = getattr(args, "analyze_links", False)

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Link Sync")

    if analyze_only:
        console.info("Analyze mode - no changes will be made")
    elif dry_run:
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

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Parse stories
    console.section("Parsing Markdown")
    stories = parser.parse_stories(markdown_path)
    console.info(f"Found {len(stories)} stories")

    # Count stories with links
    stories_with_links = [s for s in stories if s.links]
    total_links = sum(len(s.links) for s in stories)
    console.info(f"Stories with links: {len(stories_with_links)}")
    console.info(f"Total links defined: {total_links}")

    if not stories_with_links:
        console.warning("No links found in markdown")
        return ExitCode.SUCCESS

    # Create link sync orchestrator
    link_sync = LinkSyncOrchestrator(
        tracker=tracker,
        dry_run=dry_run,
    )

    # Analyze links
    analysis = link_sync.analyze_links(stories)

    console.section("Link Analysis")
    console.info(f"Cross-project links: {analysis['cross_project_links']}")
    console.info(f"Same-project links: {analysis['same_project_links']}")

    if analysis["link_types"]:
        print()
        console.info("Link types:")
        for link_type, count in analysis["link_types"].items():
            console.item(f"{link_type}: {count}", "info")

    if analysis["target_projects"]:
        print()
        console.info("Target projects:")
        for project, count in analysis["target_projects"].items():
            console.item(f"{project}: {count} links", "info")

    if analyze_only:
        return ExitCode.SUCCESS

    # Match stories to Jira issues
    console.section("Matching Stories to Jira Issues")

    # Create sync orchestrator to match stories
    sync_orchestrator = SyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )
    sync_orchestrator.analyze(markdown_path, epic_key)

    # Update stories with external keys
    matched = 0
    for story in stories:
        if str(story.id) in sync_orchestrator._matches:
            story.external_key = sync_orchestrator._matches[str(story.id)]
            matched += 1

    console.info(f"Matched {matched} stories to Jira issues")

    # Sync links
    console.section("Syncing Links")

    def on_progress(msg: str, current: int, total: int):
        console.info(f"[{current}/{total}] {msg}")

    result = link_sync.sync_all_links(stories, progress_callback=on_progress)

    # Show results
    console.section("Results")
    console.info(f"Stories processed: {result.stories_processed}")
    console.item(
        f"Links created: {result.links_created}", "success" if result.links_created else "info"
    )
    console.item(f"Links unchanged: {result.links_unchanged}", "info")

    if result.links_failed:
        console.item(f"Links failed: {result.links_failed}", "fail")

    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def run_multi_epic(args) -> int:
    """
    Run multi-epic sync mode.

    Syncs multiple epics from a single markdown file.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync import MultiEpicSyncOrchestrator
    from spectra.cli.logging import setup_logging

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
    dry_run = not getattr(args, "execute", False)
    list_only = getattr(args, "list_epics", False)
    epic_filter_str = getattr(args, "epic_filter", None)
    stop_on_error = getattr(args, "stop_on_error", False)

    # Parse epic filter
    epic_filter = None
    if epic_filter_str:
        epic_filter = [k.strip() for k in epic_filter_str.split(",")]

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Multi-Epic Sync")

    # Just list epics
    if list_only:
        parser = MarkdownParser()
        epics = parser.parse_epics(markdown_path)

        console.section(f"Epics in {markdown_path}")
        console.info(f"Found {len(epics)} epics:")
        print()

        for epic in epics:
            stories = len(epic.stories)
            console.item(f"{epic.key}: {epic.title} ({stories} stories)", "info")

        print()
        return ExitCode.SUCCESS

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

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Check if file has multiple epics
    if not parser.is_multi_epic(markdown_path):
        console.warning("File does not appear to contain multiple epics")
        console.info("Expected format: ## Epic: PROJ-100 - Epic Title")
        return ExitCode.VALIDATION_ERROR

    # Create orchestrator
    orchestrator = MultiEpicSyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config.sync,
    )

    # Get summary first
    summary = orchestrator.get_epic_summary(markdown_path)
    console.section(f"Found {summary['total_epics']} epics with {summary['total_stories']} stories")

    for epic_info in summary["epics"]:
        console.item(
            f"{epic_info['key']}: {epic_info['title']} ({epic_info['stories']} stories)", "info"
        )

    print()

    if epic_filter:
        console.info(f"Filter: syncing only {', '.join(epic_filter)}")
        print()

    # Progress callback
    def on_progress(epic_key: str, phase: str, current: int, total: int):
        console.info(f"[{epic_key}] {phase}")

    # Run sync
    console.section("Syncing Epics")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        epic_filter=epic_filter,
        progress_callback=on_progress,
        stop_on_error=stop_on_error,
    )

    # Show results
    console.section("Results")

    for epic_result in result.epic_results:
        status = "success" if epic_result.success else "fail"
        console.item(
            f"{epic_result.epic_key}: {epic_result.stories_matched} matched, "
            f"{epic_result.subtasks_created} subtasks",
            status,
        )

    print()
    console.info(f"Total: {result.epics_synced}/{result.epics_total} epics synced")
    console.info(
        f"Stories: {result.total_stories_matched} matched, {result.total_stories_updated} updated"
    )
    console.info(f"Subtasks: {result.total_subtasks_created} created")

    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def run_parallel_files(args) -> int:
    """
    Run parallel file processing mode.

    Processes multiple markdown files concurrently for improved performance.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider
    from spectra.adapters.parsers import MarkdownParser
    from spectra.adapters.trackers import JiraAdapter
    from spectra.application.sync.parallel_files import (
        ParallelFileProcessor,
        ParallelFilesConfig,
    )
    from spectra.cli.logging import setup_logging

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

    dry_run = not getattr(args, "execute", False)

    console.header("spectra Parallel File Processing")

    if dry_run:
        console.dry_run_banner()

    # Determine files to process
    file_paths: list[str] = []

    # From --input-files
    if getattr(args, "input_files", None):
        file_paths.extend(args.input_files)

    # From --input
    if args.input:
        file_paths.append(args.input)

    # From --input-dir
    input_dir = getattr(args, "input_dir", None)
    directory_mode = bool(input_dir) and not file_paths

    if not file_paths and not directory_mode:
        console.error("No input files specified")
        return ExitCode.FILE_NOT_FOUND

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

    # Create tracker config with project key override
    tracker_config = config.tracker
    if args.epic:
        tracker_config.project_key = args.epic.split("-")[0]

    # Create tracker
    tracker = JiraAdapter(config=tracker_config, dry_run=dry_run)

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create parser and formatter
    parser_inst = MarkdownParser()
    formatter = ADFFormatter()

    # Configure parallel processing
    parallel_config = ParallelFilesConfig(
        max_workers=getattr(args, "workers", 4),
        timeout_per_file=getattr(args, "file_timeout", 600.0),
        fail_fast=getattr(args, "fail_fast", False),
        skip_empty_files=getattr(args, "skip_empty", True),
    )

    # Create processor
    processor = ParallelFileProcessor(
        tracker=tracker,
        parser=parser_inst,
        formatter=formatter,
        config=config.sync,
        parallel_config=parallel_config,
    )

    # Progress callback
    def progress_callback(file_path: str, status: str, progress: float) -> None:
        if not getattr(args, "quiet", False):
            file_name = Path(file_path).name
            if status == "running":
                console.info(f"  Processing: {file_name}")
            elif status == "completed":
                console.success(f"  Completed: {file_name}")
            elif status == "failed":
                console.error(f"  Failed: {file_name}")
            elif status == "skipped":
                console.warning(f"  Skipped: {file_name} (empty)")

    # Execute processing
    console.section("Processing Files")

    if directory_mode:
        console.info(f"Scanning directory: {input_dir}")
        result = processor.process_directory(
            directory=input_dir,
            recursive=True,
            progress_callback=progress_callback,
        )
    else:
        console.info(f"Processing {len(file_paths)} file(s)")
        result = processor.process(
            file_paths=file_paths,
            progress_callback=progress_callback,
        )

    # Display results
    print()
    console.section("Results")

    if result.success:
        console.success("Parallel processing completed successfully!")
    else:
        console.error("Parallel processing completed with errors")

    print()
    console.info(f"Files: {result.files_succeeded}/{result.files_total} succeeded")

    if result.files_failed:
        console.info(f"  Failed: {result.files_failed}")
    if result.files_skipped:
        console.info(f"  Skipped: {result.files_skipped}")

    print()
    console.info(f"Epics: {result.total_epics}")
    console.info(f"Stories: {result.total_stories} total, {result.total_stories_updated} updated")
    console.info(f"Subtasks: {result.total_subtasks_created} created")

    print()
    console.section("Performance")
    console.info(f"Workers: {result.workers_used}")
    console.info(f"Peak concurrency: {result.peak_concurrency}")
    console.info(f"Duration: {result.duration_seconds:.1f}s")

    # Speedup estimate
    if result.file_results:
        sequential_time = sum(r.duration_seconds for r in result.file_results)
        if sequential_time > 0 and result.duration_seconds > 0:
            speedup = sequential_time / result.duration_seconds
            console.info(f"Estimated speedup: {speedup:.1f}x")

    if result.errors:
        print()
        console.error(f"Errors ({len(result.errors)}):")
        for error in result.errors[:5]:
            console.item(error, "fail")
        if len(result.errors) > 5:
            console.info(f"  ... and {len(result.errors) - 5} more")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def run_multi_tracker_sync(args) -> int:
    """
    Run multi-tracker sync mode.

    Syncs the same markdown to multiple issue trackers simultaneously.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync.multi_tracker import (
        MultiTrackerSyncOrchestrator,
        TrackerTarget,
    )
    from spectra.cli.logging import setup_logging

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
    dry_run = not getattr(args, "execute", False)
    trackers_arg = getattr(args, "trackers", None) or []
    primary_tracker = getattr(args, "primary_tracker", None)

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Multi-Tracker Sync")
    console.info(f"Source: {markdown_path}")

    if dry_run:
        console.dry_run_banner()

    # Load configuration
    config_file = Path(args.config) if getattr(args, "config", None) else None
    config_provider = EnvironmentConfigProvider(
        config_file=config_file,
        cli_overrides=vars(args),
    )

    config = config_provider.load()
    config.sync.dry_run = dry_run

    # Parse tracker targets from --trackers arg or config
    # Format: type:epic_key (e.g., jira:PROJ-123 github:1)
    targets_to_create: list[dict] = []

    for tracker_spec in trackers_arg:
        if ":" in tracker_spec:
            parts = tracker_spec.split(":", 1)
            tracker_type = parts[0].lower()
            epic_key = parts[1]
            targets_to_create.append(
                {
                    "type": tracker_type,
                    "epic_key": epic_key,
                    "name": f"{tracker_type.title()} ({epic_key})",
                    "is_primary": (tracker_type == primary_tracker) if primary_tracker else False,
                }
            )
        else:
            console.warning(f"Invalid tracker spec: {tracker_spec} (use format type:epic_key)")

    if not targets_to_create:
        console.error("No tracker targets specified. Use --trackers type:epic_key")
        return ExitCode.CONFIG_ERROR

    # Create orchestrator
    parser = MarkdownParser()
    formatter = ADFFormatter()

    orchestrator = MultiTrackerSyncOrchestrator(
        parser=parser,
        config=config.sync,
        formatter=formatter,
    )

    # Add targets
    console.section("Configuring Trackers")
    for target_config in targets_to_create:
        tracker_type = target_config["type"]
        epic_key = target_config["epic_key"]
        name = target_config["name"]

        try:
            tracker = _create_tracker_for_multi_sync(tracker_type, config, config_provider, dry_run)
            if tracker:
                orchestrator.add_target(
                    TrackerTarget(
                        tracker=tracker,
                        epic_key=epic_key,
                        name=name,
                        is_primary=target_config.get("is_primary", False),
                        formatter=formatter,
                    )
                )
                console.success(f"Added: {name}")
            else:
                console.warning(f"Skipped: {name} (no adapter)")
        except Exception as e:
            console.warning(f"Failed to add {name}: {e}")

    if not orchestrator.targets:
        console.error("No valid tracker targets configured")
        return ExitCode.CONFIG_ERROR

    # Progress callback
    def on_progress(tracker_name: str, phase: str, current: int, total: int) -> None:
        console.progress(current, total, f"{tracker_name}: {phase}")

    # Run sync
    console.section("Syncing")
    result = orchestrator.sync(
        markdown_path=markdown_path,
        progress_callback=on_progress,
    )

    # Show results
    console.print()
    console.section("Results")

    for status in result.tracker_statuses:
        icon = "success" if status.success else "fail"
        console.item(
            f"{status.tracker_name}: {status.stories_synced} synced, "
            f"{status.stories_created} created, {status.stories_updated} updated",
            icon,
        )
        if status.errors:
            for error in status.errors[:3]:
                console.detail(f"  Error: {error}")

    console.print()
    console.info(f"Total: {result.successful_trackers}/{result.total_trackers} trackers synced")

    if result.success:
        console.success("Multi-tracker sync completed successfully!")
    elif result.partial_success:
        console.warning("Multi-tracker sync completed with some failures")
    else:
        console.error("Multi-tracker sync failed")

    return ExitCode.SUCCESS if result.success else ExitCode.SYNC_ERROR


def _create_tracker_for_multi_sync(
    tracker_type: str,
    config: object,
    config_provider: object,
    dry_run: bool,
) -> object | None:
    """Create a tracker adapter for multi-tracker sync."""
    import os

    if tracker_type == "jira":
        from spectra.adapters import ADFFormatter, JiraAdapter

        formatter = ADFFormatter()
        return JiraAdapter(
            config=getattr(config, "tracker", None),
            dry_run=dry_run,
            formatter=formatter,
        )

    if tracker_type == "github":
        from spectra.adapters.github import GitHubAdapter

        return GitHubAdapter(
            token=os.getenv("GITHUB_TOKEN", ""),
            owner=os.getenv("GITHUB_OWNER", ""),
            repo=os.getenv("GITHUB_REPO", ""),
            dry_run=dry_run,
        )

    if tracker_type == "gitlab":
        from spectra.adapters.gitlab import GitLabAdapter

        return GitLabAdapter(
            token=os.getenv("GITLAB_TOKEN", ""),
            project_id=os.getenv("GITLAB_PROJECT_ID", ""),
            dry_run=dry_run,
            base_url=os.getenv("GITLAB_URL", "https://gitlab.com/api/v4"),
        )

    if tracker_type == "linear":
        from spectra.adapters.linear import LinearAdapter

        return LinearAdapter(
            api_key=os.getenv("LINEAR_API_KEY", ""),
            team_key=os.getenv("LINEAR_TEAM_KEY", ""),
            dry_run=dry_run,
        )

    return None


def run_attachment_sync(args) -> int:
    """
    Run attachment sync between markdown and issue tracker.

    Uploads local attachments to tracker and/or downloads remote attachments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code.
    """
    from spectra.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter
    from spectra.adapters.parsers import MarkdownParser
    from spectra.application.sync import AttachmentSyncOrchestrator
    from spectra.cli.logging import setup_logging

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
    mode = getattr(args, "attachment_mode", "upload")

    # Check markdown file exists
    if not Path(markdown_path).exists():
        console.error(f"Markdown file not found: {markdown_path}")
        return ExitCode.FILE_NOT_FOUND

    console.header("spectra Attachment Sync")
    console.info(f"Source: {markdown_path}")
    console.info(f"Mode: {mode}")

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

    # Initialize components
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=dry_run,
        formatter=formatter,
    )
    parser = MarkdownParser()

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Parse stories
    console.section("Parsing Markdown")
    stories = parser.parse_stories(markdown_path)
    console.info(f"Found {len(stories)} stories")

    # Create orchestrator
    orchestrator = AttachmentSyncOrchestrator(
        tracker=tracker,
        parser=parser,
        config=config.sync,
        dry_run=dry_run,
    )

    # Sync attachments
    console.section("Syncing Attachments")
    results = orchestrator.sync_attachments(
        markdown_path=markdown_path,
        epic_key=epic_key,
        mode=mode,
    )

    # Show results
    console.print()
    console.section("Results")

    total_uploaded = 0
    total_downloaded = 0
    total_skipped = 0
    total_errors = 0

    for issue_key, result in results.items():
        total_uploaded += len(result.uploaded)
        total_downloaded += len(result.downloaded)
        total_skipped += result.skipped
        total_errors += len(result.errors)

        if result.uploaded:
            for att in result.uploaded:
                console.item(f"{att.filename} → {issue_key}", "success")

        if result.downloaded:
            for att in result.downloaded:
                console.item(f"{issue_key} → {att.local_path}", "success")

        if result.errors:
            for att, error in result.errors:
                console.item(f"{att.filename}: {error}", "fail")

    # Summary
    console.print()
    console.section("Summary")
    if dry_run:
        console.info(f"{Symbols.DRY_RUN} DRY RUN - no changes made")
    console.info(f"Uploaded: {total_uploaded}")
    console.info(f"Downloaded: {total_downloaded}")
    console.info(f"Skipped: {total_skipped}")
    if total_errors > 0:
        console.error(f"Errors: {total_errors}")
        return ExitCode.ERROR

    return ExitCode.SUCCESS
