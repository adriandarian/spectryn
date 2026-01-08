"""
Import Command - Import from tracker to create initial markdown.

Creates markdown files from existing issues in:
- Jira
- GitHub Issues
- Linear
- Azure DevOps
- GitLab

Supports:
- Single epic import
- Project-wide import
- Custom templates
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .exit_codes import ExitCode
from .output import Console, Symbols


@dataclass
class ImportOptions:
    """Options for import operation."""

    include_subtasks: bool = True
    include_comments: bool = False
    include_attachments: bool = False
    include_links: bool = True
    template: str | None = None
    output_dir: str = "."
    single_file: bool = True  # All stories in one file vs separate files


@dataclass
class ImportResult:
    """Result of import operation."""

    success: bool = True
    epics_imported: int = 0
    stories_imported: int = 0
    subtasks_imported: int = 0
    files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def generate_markdown_content(epic_data: dict, stories: list[dict], options: ImportOptions) -> str:
    """
    Generate markdown content from epic and stories data.

    Args:
        epic_data: Epic information.
        stories: List of story data.
        options: Import options.

    Returns:
        Markdown content string.
    """
    lines = []

    # Epic header
    epic_key = epic_data.get("key", "EPIC-000")
    epic_title = epic_data.get("summary", "Imported Epic")
    epic_status = epic_data.get("status", {}).get("name", "To Do")

    lines.append(f"# 🚀 {epic_key}: {epic_title}")
    lines.append("")

    # Epic metadata
    lines.append("## Epic Overview")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|----------|-------|")
    lines.append(f"| **Epic Key** | {epic_key} |")
    lines.append(f"| **Status** | {epic_status} |")

    if epic_data.get("priority"):
        lines.append(f"| **Priority** | {epic_data['priority'].get('name', 'Medium')} |")

    if epic_data.get("assignee"):
        assignee = epic_data["assignee"].get("displayName", "Unassigned")
        lines.append(f"| **Owner** | {assignee} |")

    lines.append("")

    # Epic description
    if epic_data.get("description"):
        lines.append("## Description")
        lines.append("")
        # Handle ADF or plain text description
        desc = epic_data["description"]
        if isinstance(desc, dict):
            # ADF format - extract text
            desc = _extract_text_from_adf(desc)
        lines.append(desc)
        lines.append("")

    # Stories section
    lines.append("## User Stories")
    lines.append("")

    total_points = sum(s.get("storyPoints", 0) or 0 for s in stories)
    lines.append(f"**Total Stories:** {len(stories)} | **Total Points:** {total_points}")
    lines.append("")

    # Individual stories
    for story in stories:
        story_key = story.get("key", "")
        story_title = story.get("summary", "")
        story_status = story.get("status", {}).get("name", "To Do")
        story_points = story.get("storyPoints") or story.get("customfield_10016") or 0
        story_priority = story.get("priority", {}).get("name", "Medium")

        lines.append(f"### 🔧 {story_key}: {story_title}")
        lines.append("")

        # Metadata table
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        lines.append(f"| **Story Points** | {story_points} |")
        lines.append(f"| **Priority** | {story_priority} |")
        lines.append(f"| **Status** | {story_status} |")

        if story.get("assignee"):
            assignee = story["assignee"].get("displayName", "Unassigned")
            lines.append(f"| **Assignee** | {assignee} |")

        lines.append("")

        # Description
        if story.get("description"):
            desc = story["description"]
            if isinstance(desc, dict):
                desc = _extract_text_from_adf(desc)

            # Try to extract As a/I want/So that format
            lines.append("#### Description")
            lines.append("")
            lines.append(desc)
            lines.append("")

        # Acceptance criteria (from description or custom field)
        ac_field = story.get("customfield_10017") or story.get("acceptanceCriteria")
        if ac_field:
            lines.append("#### Acceptance Criteria")
            lines.append("")
            if isinstance(ac_field, list):
                for ac in ac_field:
                    lines.append(f"- [ ] {ac}")
            else:
                for ac_line in str(ac_field).split("\n"):
                    if ac_line.strip():
                        lines.append(f"- [ ] {ac_line.strip()}")
            lines.append("")

        # Subtasks
        if options.include_subtasks and story.get("subtasks"):
            lines.append("#### Subtasks")
            lines.append("")
            for subtask in story["subtasks"]:
                st_title = subtask.get("summary", subtask.get("fields", {}).get("summary", ""))
                st_status = subtask.get("status", subtask.get("fields", {}).get("status", {})).get(
                    "name", ""
                )
                is_done = st_status.lower() in ("done", "closed", "resolved")
                checkbox = "[x]" if is_done else "[ ]"
                lines.append(f"- {checkbox} {st_title}")
            lines.append("")

        # Links
        if options.include_links and story.get("issuelinks"):
            links = story["issuelinks"]
            if links:
                lines.append("#### Related Issues")
                lines.append("")
                for link in links:
                    link_type = link.get("type", {}).get("name", "relates to")
                    if link.get("outwardIssue"):
                        related = link["outwardIssue"]
                        lines.append(f"- {link_type}: {related.get('key')}")
                    elif link.get("inwardIssue"):
                        related = link["inwardIssue"]
                        lines.append(
                            f"- {link.get('type', {}).get('inward', 'related')}: {related.get('key')}"
                        )
                lines.append("")

        # Story separator
        lines.append("---")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Imported from Jira on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def _extract_text_from_adf(adf: dict) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not isinstance(adf, dict):
        return str(adf)

    text_parts = []

    def extract(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                text_parts.append(node.get("text", ""))
            elif node.get("content"):
                for child in node["content"]:
                    extract(child)
        elif isinstance(node, list):
            for item in node:
                extract(item)

    extract(adf)
    return " ".join(text_parts)


def run_import(
    console: Console,
    epic_key: str | None = None,
    project_key: str | None = None,
    output_path: str | None = None,
    output_dir: str | None = None,
    include_subtasks: bool = True,
    include_comments: bool = False,
    single_file: bool = True,
    dry_run: bool = False,
) -> int:
    """
    Run the import command.

    Args:
        console: Console for output.
        epic_key: Epic key to import.
        project_key: Project key for project-wide import.
        output_path: Output file path.
        output_dir: Output directory for multiple files.
        include_subtasks: Include subtasks.
        include_comments: Include comments.
        single_file: All stories in one file.
        dry_run: Preview without writing files.

    Returns:
        Exit code.
    """
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter

    from .logging import setup_logging

    setup_logging(level=logging.INFO)

    console.header(f"spectra Import {Symbols.DOWNLOAD}")
    console.print()

    if not epic_key and not project_key:
        console.error("Either --epic or --project must be specified")
        return ExitCode.CONFIG_ERROR

    # Load configuration
    config_provider = EnvironmentConfigProvider()
    errors = config_provider.validate()

    if errors:
        console.config_errors(errors)
        return ExitCode.CONFIG_ERROR

    config = config_provider.load()

    # Initialize tracker
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,  # Import is read-only from tracker
        formatter=formatter,
    )

    # Test connection
    console.info("Connecting to tracker...")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as {user.get('displayName', 'Unknown')}")
    console.print()

    result = ImportResult()
    options = ImportOptions(
        include_subtasks=include_subtasks,
        include_comments=include_comments,
        single_file=single_file,
        output_dir=output_dir or ".",
    )

    if epic_key:
        # Import single epic
        console.info(f"Importing epic: {epic_key}")

        try:
            # Fetch epic details
            epic_data = tracker.get_issue(epic_key)
            if not epic_data:
                console.error(f"Epic not found: {epic_key}")
                return ExitCode.FILE_NOT_FOUND

            epic_fields = epic_data.get("fields", {})
            epic_info = {
                "key": epic_key,
                "summary": epic_fields.get("summary", ""),
                "description": epic_fields.get("description"),
                "status": epic_fields.get("status"),
                "priority": epic_fields.get("priority"),
                "assignee": epic_fields.get("assignee"),
            }

            console.info(f"Epic: {epic_info['summary']}")

            # Fetch stories under epic
            stories_data = tracker.get_epic_issues(epic_key)
            console.info(f"Found {len(stories_data)} stories")

            # Process stories
            stories = []
            for issue in stories_data:
                # Skip subtasks in the main list
                issue_type = issue.get("fields", {}).get("issuetype", {})
                if issue_type.get("subtask"):
                    continue

                story = {
                    "key": issue.get("key"),
                    "summary": issue.get("fields", {}).get("summary"),
                    "description": issue.get("fields", {}).get("description"),
                    "status": issue.get("fields", {}).get("status"),
                    "priority": issue.get("fields", {}).get("priority"),
                    "assignee": issue.get("fields", {}).get("assignee"),
                    "storyPoints": issue.get("fields", {}).get("customfield_10016"),
                    "issuelinks": issue.get("fields", {}).get("issuelinks", []),
                    "subtasks": [],
                }

                # Fetch subtasks if needed
                if options.include_subtasks:
                    subtasks = issue.get("fields", {}).get("subtasks", [])
                    story["subtasks"] = subtasks

                stories.append(story)
                result.stories_imported += 1

            result.epics_imported = 1

            # Generate markdown
            markdown_content = generate_markdown_content(epic_info, stories, options)

            # Determine output path
            out_file = Path(output_path) if output_path else Path(f"{epic_key}.md")

            if dry_run:
                console.print()
                console.info("Preview (dry-run):")
                console.print()
                # Show first 50 lines
                preview_lines = markdown_content.split("\n")[:50]
                for line in preview_lines:
                    print(f"  {line}")
                if len(markdown_content.split("\n")) > 50:
                    console.info("  ... (truncated)")
                console.print()
                console.info(f"Would write to: {out_file}")
            else:
                out_file.write_text(markdown_content, encoding="utf-8")
                result.files_created.append(str(out_file))
                console.success(f"Created: {out_file}")

        except Exception as e:
            console.error(f"Import failed: {e}")
            result.errors.append(str(e))
            result.success = False

    elif project_key:
        # Import all epics from project
        console.info(f"Importing project: {project_key}")
        console.warning("Project-wide import not yet implemented")
        console.info("Use --epic to import a specific epic")
        return ExitCode.CONFIG_ERROR

    # Summary
    console.print()
    if result.success:
        console.success("Import completed!")
        console.info(f"  Epics: {result.epics_imported}")
        console.info(f"  Stories: {result.stories_imported}")
        if result.files_created:
            console.info("  Files created:")
            for f in result.files_created:
                console.item(f)
    else:
        console.error("Import failed")
        for error in result.errors:
            console.item(error, "fail")

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR
