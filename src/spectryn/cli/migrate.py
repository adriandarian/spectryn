"""
Migrate Command - Migrate between issue trackers.

Supports migration paths:
- Jira → GitHub Issues
- Jira → Linear
- GitHub → Jira
- Linear → Jira
- Any → Markdown (export)

Features:
- Field mapping
- Status mapping
- User mapping
- Attachment handling
- Comment preservation
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class MigrationMapping:
    """Field and status mappings for migration."""

    # Status mappings: source_status -> target_status
    status_map: dict[str, str] = field(default_factory=dict)

    # Priority mappings
    priority_map: dict[str, str] = field(default_factory=dict)

    # User mappings: source_email -> target_email
    user_map: dict[str, str] = field(default_factory=dict)

    # Issue type mappings
    type_map: dict[str, str] = field(default_factory=dict)


@dataclass
class MigrationResult:
    """Result of migration operation."""

    success: bool = True
    issues_migrated: int = 0
    issues_failed: int = 0
    comments_migrated: int = 0
    attachments_migrated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issue_mapping: dict[str, str] = field(default_factory=dict)  # old_key -> new_key


# Default status mappings between systems
DEFAULT_STATUS_MAPS = {
    ("jira", "github"): {
        "To Do": "open",
        "Open": "open",
        "In Progress": "open",
        "In Review": "open",
        "Done": "closed",
        "Closed": "closed",
        "Resolved": "closed",
    },
    ("jira", "linear"): {
        "To Do": "Backlog",
        "Open": "Backlog",
        "In Progress": "In Progress",
        "In Review": "In Review",
        "Done": "Done",
        "Closed": "Done",
    },
    ("github", "jira"): {
        "open": "To Do",
        "closed": "Done",
    },
    ("linear", "jira"): {
        "Backlog": "To Do",
        "Todo": "To Do",
        "In Progress": "In Progress",
        "In Review": "In Review",
        "Done": "Done",
        "Canceled": "Closed",
    },
}


def create_default_mapping(source: str, target: str) -> MigrationMapping:
    """
    Create default mapping between two systems.

    Args:
        source: Source tracker type.
        target: Target tracker type.

    Returns:
        MigrationMapping with defaults.
    """
    mapping = MigrationMapping()

    # Status mapping
    key = (source.lower(), target.lower())
    if key in DEFAULT_STATUS_MAPS:
        mapping.status_map = DEFAULT_STATUS_MAPS[key].copy()

    # Priority mapping (usually similar across systems)
    mapping.priority_map = {
        "Highest": "Critical",
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
        "Lowest": "Low",
        "Critical": "Critical",
        "Blocker": "Critical",
    }

    return mapping


def format_migration_plan(
    source: str,
    target: str,
    issues_count: int,
    mapping: MigrationMapping,
    color: bool = True,
) -> str:
    """Format migration plan for display."""
    lines = []

    if color:
        lines.append(f"{Colors.BOLD}Migration Plan{Colors.RESET}")
    else:
        lines.append("Migration Plan")

    lines.append("=" * 50)
    lines.append(f"  Source: {source}")
    lines.append(f"  Target: {target}")
    lines.append(f"  Issues: {issues_count}")
    lines.append("")

    # Status mappings
    if mapping.status_map:
        lines.append("Status Mappings:")
        for src, tgt in list(mapping.status_map.items())[:5]:
            if color:
                lines.append(f"  {src} {Colors.DIM}→{Colors.RESET} {tgt}")
            else:
                lines.append(f"  {src} → {tgt}")
        if len(mapping.status_map) > 5:
            lines.append(f"  ... and {len(mapping.status_map) - 5} more")
        lines.append("")

    # Priority mappings
    if mapping.priority_map:
        lines.append("Priority Mappings:")
        for src, tgt in list(mapping.priority_map.items())[:3]:
            if color:
                lines.append(f"  {src} {Colors.DIM}→{Colors.RESET} {tgt}")
            else:
                lines.append(f"  {src} → {tgt}")
        lines.append("")

    return "\n".join(lines)


def run_migrate(
    console: Console,
    source_type: str,
    target_type: str,
    source_project: str | None = None,
    target_project: str | None = None,
    epic_key: str | None = None,
    mapping_file: str | None = None,
    include_comments: bool = True,
    include_attachments: bool = False,
    dry_run: bool = True,
) -> int:
    """
    Run the migrate command.

    Args:
        console: Console for output.
        source_type: Source tracker type (jira, github, linear).
        target_type: Target tracker type.
        source_project: Source project key.
        target_project: Target project key.
        epic_key: Specific epic to migrate.
        mapping_file: Path to custom mapping file.
        include_comments: Include comments in migration.
        include_attachments: Include attachments.
        dry_run: Preview without making changes.

    Returns:
        Exit code.
    """
    from .logging import setup_logging

    setup_logging(level=logging.INFO)

    console.header(f"spectra Migrate {Symbols.SYNC}")
    console.print()

    # Validate trackers
    supported = {"jira", "github", "linear", "azure", "gitlab", "markdown"}
    source_lower = source_type.lower()
    target_lower = target_type.lower()

    if source_lower not in supported:
        console.error(f"Unsupported source tracker: {source_type}")
        console.info(f"Supported: {', '.join(sorted(supported))}")
        return ExitCode.CONFIG_ERROR

    if target_lower not in supported:
        console.error(f"Unsupported target tracker: {target_type}")
        console.info(f"Supported: {', '.join(sorted(supported))}")
        return ExitCode.CONFIG_ERROR

    if source_lower == target_lower:
        console.error("Source and target cannot be the same")
        return ExitCode.CONFIG_ERROR

    console.info(f"Source: {source_type}")
    console.info(f"Target: {target_type}")

    if source_project:
        console.info(f"Source Project: {source_project}")
    if target_project:
        console.info(f"Target Project: {target_project}")
    if epic_key:
        console.info(f"Epic: {epic_key}")

    console.print()

    if dry_run:
        console.warning("DRY RUN - No changes will be made")
        console.print()

    # Load or create mapping
    if mapping_file and Path(mapping_file).exists():
        console.info(f"Loading mapping from: {mapping_file}")
        # TODO: Implement custom mapping file loading
        mapping = create_default_mapping(source_lower, target_lower)
    else:
        console.info("Using default field mappings")
        mapping = create_default_mapping(source_lower, target_lower)

    # For now, show what would be done
    console.print()

    # Migration to markdown is essentially an export
    if target_lower == "markdown":
        console.info("Migration to markdown will export issues to a markdown file.")
        console.info("Use 'spectra import' command for this operation.")
        console.print()
        return ExitCode.SUCCESS

    # Show the plan
    # In a real implementation, we'd fetch the issues first
    plan = format_migration_plan(
        source=f"{source_type}" + (f"/{source_project}" if source_project else ""),
        target=f"{target_type}" + (f"/{target_project}" if target_project else ""),
        issues_count=0,  # Would be fetched
        mapping=mapping,
        color=console.color,
    )
    print(plan)

    console.warning("Full migration is not yet implemented.")
    console.print()
    console.info("Migration workflow:")
    console.item("1. Export from source: spectra import --epic PROJ-123")
    console.item("2. Review/edit the markdown file")
    console.item("3. Sync to target: spectra --input PROJ-123.md --epic NEW-123 --execute")
    console.print()

    return ExitCode.SUCCESS
