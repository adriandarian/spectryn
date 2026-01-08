"""
Generate - Create markdown templates from Jira epics.

This module provides functionality to generate markdown epic files
from existing Jira epics, bootstrapping the sync process.
"""

import logging
from argparse import Namespace
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from spectryn.core.ports.issue_tracker import IssueData, IssueTrackerPort

from .exit_codes import ExitCode
from .output import Console, Symbols


@dataclass
class GenerateResult:
    """
    Result of a generate operation.

    Attributes:
        success: Whether generation completed successfully.
        output_path: Path where the markdown was written.
        epic_key: The epic key that was fetched.
        epic_title: Title of the epic.
        stories_count: Number of stories included.
        subtasks_count: Total number of subtasks across all stories.
        warnings: Any warnings generated.
        errors: Any errors encountered.
    """

    success: bool = True
    output_path: str = ""
    epic_key: str = ""
    epic_title: str = ""
    stories_count: int = 0
    subtasks_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.success = False


class TemplateGenerator:
    """
    Generates markdown templates from Jira epics.

    Fetches epic and story data from Jira and produces a properly
    formatted markdown file ready for editing and sync.
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        console: Console,
        include_subtasks: bool = True,
        include_descriptions: bool = True,
        include_acceptance_criteria: bool = True,
        template_style: str = "full",  # "full", "minimal", "skeleton"
    ) -> None:
        """
        Initialize the template generator.

        Args:
            tracker: Issue tracker adapter for Jira API.
            console: Console for output.
            include_subtasks: Include existing subtasks from Jira.
            include_descriptions: Include story descriptions.
            include_acceptance_criteria: Include acceptance criteria as subtasks.
            template_style: Style of template ("full", "minimal", "skeleton").
        """
        self.tracker: IssueTrackerPort = tracker
        self.console = console
        self.include_subtasks = include_subtasks
        self.include_descriptions = include_descriptions
        self.include_acceptance_criteria = include_acceptance_criteria
        self.template_style = template_style
        self.logger = logging.getLogger(__name__)

    def generate(
        self,
        epic_key: str,
        output_path: str | None = None,
        dry_run: bool = True,
    ) -> GenerateResult:
        """
        Generate a markdown template from a Jira epic.

        Args:
            epic_key: Jira epic key (e.g., "PROJ-123").
            output_path: Path for output file (defaults to EPIC_KEY.md).
            dry_run: If True, don't write the file.

        Returns:
            GenerateResult with operation details.
        """
        result = GenerateResult(epic_key=epic_key)

        if not output_path:
            output_path = f"{epic_key}.md"
        result.output_path = output_path

        try:
            # Fetch epic data
            self.console.info(f"Fetching epic {epic_key}...")
            epic_data = self._fetch_epic(epic_key, result)
            if not epic_data:
                return result

            result.epic_title = epic_data.get("fields", {}).get("summary", "Untitled Epic")

            # Fetch child stories
            self.console.info("Fetching stories...")
            stories = self._fetch_stories(epic_key, result)
            result.stories_count = len(stories)

            if not stories:
                result.add_warning(f"No stories found under epic {epic_key}")

            # Count subtasks
            for story in stories:
                subtasks = story.get("fields", {}).get("subtasks", [])
                result.subtasks_count += len(subtasks)

            # Generate markdown
            self.console.info("Generating markdown...")
            markdown = self._generate_markdown(epic_data, stories, result)

            # Write file (unless dry run)
            if not dry_run:
                self._write_file(output_path, markdown, result)
            else:
                result.output_path = output_path

            return result

        except Exception as e:
            result.add_error(str(e))
            self.logger.exception("Failed to generate template")
            return result

    def preview(self, epic_key: str) -> str | None:
        """
        Generate and return markdown without writing to file.

        Args:
            epic_key: Jira epic key.

        Returns:
            Generated markdown content, or None on error.
        """
        result = self.generate(epic_key, dry_run=True)

        if not result.success:
            return None

        # Re-generate to get content
        epic_data = self._fetch_epic(epic_key, GenerateResult())
        if not epic_data:
            return None

        stories = self._fetch_stories(epic_key, GenerateResult())
        return self._generate_markdown(epic_data, stories, GenerateResult())

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _fetch_epic(self, epic_key: str, result: GenerateResult) -> dict[str, Any] | None:
        """Fetch epic data from Jira."""
        try:
            issue = self.tracker.get_issue(epic_key)
            return self._normalize_issue(issue)
        except Exception as e:
            result.add_error(f"Failed to fetch epic {epic_key}: {e}")
            return None

    def _fetch_stories(self, epic_key: str, result: GenerateResult) -> list[dict[str, Any]]:
        """Fetch stories under the epic."""
        try:
            return [
                self._normalize_issue(issue) for issue in self.tracker.get_epic_children(epic_key)
            ]
        except Exception as e:
            result.add_error(f"Failed to fetch stories: {e}")
            return []

    def _generate_markdown(
        self,
        epic_data: dict[str, Any],
        stories: list[dict[str, Any]],
        result: GenerateResult,
    ) -> str:
        """Generate markdown content from Jira data."""
        lines: list[str] = []

        epic_key = epic_data.get("key", "EPIC-XXX")
        epic_fields = epic_data.get("fields", {})
        epic_title = epic_fields.get("summary", "Epic Title")
        epic_description = self._extract_description(epic_fields.get("description"))

        # Epic header
        lines.append(f"# {Symbols.ROCKET} {epic_key}: {epic_title}")
        lines.append("")

        if epic_description and self.include_descriptions:
            lines.append(epic_description)
            lines.append("")

        lines.append("---")
        lines.append("")

        # Stories section
        lines.append("## Stories")
        lines.append("")

        if not stories:
            # Add placeholder story
            lines.extend(self._generate_placeholder_story())
        else:
            for i, story in enumerate(stories):
                story_md = self._generate_story(story, i + 1)
                lines.extend(story_md)
                lines.append("")
                lines.append("---")
                lines.append("")

        # Footer
        lines.append("")
        lines.append(f"> Generated from Jira epic {epic_key}")
        lines.append(
            "> Edit this file and sync back with: spectra --input {file} --epic {epic_key} --execute"
        )

        return "\n".join(lines)

    def _generate_story(self, story_data: dict, index: int) -> list[str]:
        """Generate markdown for a single story."""
        lines: list[str] = []

        story_key = story_data.get("key", f"STORY-{index}")
        fields = story_data.get("fields", {})
        title = fields.get("summary", "Story Title")
        status = self._get_status_name(fields.get("status", {}))
        story_points = fields.get("customfield_10014") or 0  # Common story points field
        priority = self._get_priority_name(fields.get("priority", {}))
        description = self._extract_description(fields.get("description"))

        # Generate story ID
        story_id = f"US-{index:03d}"

        # Status emoji
        status_emoji = self._get_status_emoji(status)

        # Story header
        lines.append(f"### {status_emoji} {story_id}: {title}")
        lines.append("")

        # Jira link
        jira_url = self.tracker.config.url if hasattr(self.tracker, "config") else ""
        if jira_url:
            lines.append(f"> **Jira:** [{story_key}]({jira_url}/browse/{story_key})")
            lines.append("")

        # Metadata table
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Story Points** | {story_points or 0} |")
        lines.append(f"| **Priority** | {priority} |")
        lines.append(f"| **Status** | {status} |")
        lines.append("")

        # Description
        lines.append("#### Description")
        lines.append("")

        if self.include_descriptions and description:
            # Try to parse as user story format
            if "as a" in description.lower() or "i want" in description.lower():
                lines.append(description)
            else:
                # Convert to user story format
                lines.append("**As a** user")
                lines.append(f"**I want** {title.lower()}")
                lines.append("**So that** [benefit to be defined]")
                lines.append("")
                if description:
                    lines.append("**Details:**")
                    lines.append(description)
        else:
            lines.append("**As a** user")
            lines.append(f"**I want** {title.lower()}")
            lines.append("**So that** [benefit to be defined]")
        lines.append("")

        # Acceptance Criteria / Subtasks
        subtasks = fields.get("subtasks", [])

        if self.include_subtasks and subtasks:
            lines.append("#### Subtasks")
            lines.append("")
            for subtask in subtasks:
                subtask_name = subtask.get("fields", {}).get("summary", "Subtask")
                subtask_status = self._get_status_name(subtask.get("fields", {}).get("status", {}))
                checkbox = "[x]" if subtask_status.lower() == "done" else "[ ]"
                lines.append(f"- {checkbox} {subtask_name}")
            lines.append("")
        elif self.include_acceptance_criteria:
            # Add placeholder acceptance criteria
            lines.append("#### Acceptance Criteria")
            lines.append("")
            lines.append("- [ ] Criterion 1: [Define acceptance criterion]")
            lines.append("- [ ] Criterion 2: [Define acceptance criterion]")
            lines.append("- [ ] Criterion 3: [Define acceptance criterion]")
            lines.append("")

        return lines

    def _generate_placeholder_story(self) -> list[str]:
        """Generate a placeholder story template."""
        return [
            "### 📋 STORY-001: Sample Story",
            "",
            "| Field | Value |",
            "|-------|-------|",
            "| **Story Points** | 3 |",
            "| **Priority** | Medium |",
            "| **Status** | To Do |",
            "",
            "#### Description",
            "",
            "**As a** user",
            "**I want** [describe the feature]",
            "**So that** [describe the benefit]",
            "",
            "#### Acceptance Criteria",
            "",
            "- [ ] Criterion 1: [Define]",
            "- [ ] Criterion 2: [Define]",
            "- [ ] Criterion 3: [Define]",
            "",
        ]

    def _extract_description(self, description: Any) -> str:
        """Extract plain text from Jira description (ADF or plain text)."""
        if not description:
            return ""

        if isinstance(description, str):
            return description

        if isinstance(description, dict):
            # ADF format - extract text content
            return self._extract_text_from_adf(description)

        return str(description)

    def _normalize_issue(self, issue: IssueData | dict[str, Any]) -> dict[str, Any]:
        """Convert IssueData objects to dictionaries for rendering."""
        if isinstance(issue, IssueData):
            return asdict(issue)
        return issue

    def _extract_text_from_adf(self, adf: dict) -> str:
        """Extract plain text from Atlassian Document Format."""
        if not isinstance(adf, dict):
            return str(adf) if adf else ""

        content = adf.get("content", [])
        text_parts: list[str] = []

        for block in content:
            if block.get("type") == "paragraph":
                para_text = self._extract_text_from_content(block.get("content", []))
                if para_text:
                    text_parts.append(para_text)
            elif block.get("type") == "bulletList":
                for item in block.get("content", []):
                    item_text = self._extract_text_from_content(
                        item.get("content", [{}])[0].get("content", [])
                    )
                    if item_text:
                        text_parts.append(f"- {item_text}")

        return "\n".join(text_parts)

    def _extract_text_from_content(self, content: list) -> str:
        """Extract text from ADF content array."""
        parts: list[str] = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif item.get("type") == "hardBreak":
                parts.append("\n")
        return "".join(parts)

    def _get_status_name(self, status: dict) -> str:
        """Get status name from Jira status object."""
        return status.get("name", "To Do") if status else "To Do"

    def _get_priority_name(self, priority: dict) -> str:
        """Get priority name from Jira priority object."""
        return priority.get("name", "Medium") if priority else "Medium"

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for status."""
        status_lower = status.lower()

        if status_lower in ("done", "closed", "resolved"):
            return "✅"
        if status_lower in ("in progress", "in review", "in development"):
            return "🔄"
        if status_lower in ("blocked", "on hold"):
            return "🚫"
        if status_lower in ("ready", "ready for dev"):
            return "📋"
        return "📋"

    def _write_file(self, path: str, content: str, result: GenerateResult) -> None:
        """Write content to file."""
        try:
            Path(path).write_text(content, encoding="utf-8")
            self.console.success(f"Written to {path}")
        except Exception as e:
            result.add_error(f"Failed to write file: {e}")


def run_generate(args: Namespace, console: Console) -> int:
    """
    Run the generate command.

    Args:
        args: Parsed command-line arguments.
        console: Console for output.

    Returns:
        Exit code.
    """
    from spectryn.adapters import ADFFormatter, EnvironmentConfigProvider, JiraAdapter

    from .logging import setup_logging

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    log_format = getattr(args, "log_format", "text")
    setup_logging(level=log_level, log_format=log_format)

    epic_key = args.epic
    output_path = getattr(args, "generate_output", None) or getattr(args, "output_file", None)
    dry_run = not getattr(args, "execute", False)
    preview_only = getattr(args, "preview", False)

    # Determine output path
    if not output_path:
        output_path = f"{epic_key}.md"

    # Check if output file already exists
    if Path(output_path).exists() and not dry_run and not preview_only:
        if not getattr(args, "force", False):
            if not console.confirm(f"{output_path} already exists. Overwrite?"):
                console.warning("Cancelled by user")
                return ExitCode.CANCELLED

    console.header(f"spectra Generate {Symbols.FILE}")
    console.info(f"Epic: {epic_key}")
    console.info(f"Output: {output_path}")

    if dry_run and not preview_only:
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

    # Initialize Jira adapter
    formatter = ADFFormatter()
    tracker = JiraAdapter(
        config=config.tracker,
        dry_run=True,  # Always dry run for read operations
        formatter=formatter,
    )

    # Test connection
    console.section("Connecting to Jira")
    if not tracker.test_connection():
        console.connection_error(config.tracker.url)
        return ExitCode.CONNECTION_ERROR

    user = tracker.get_current_user()
    console.success(f"Connected as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    # Create generator
    generator = TemplateGenerator(
        tracker=tracker,
        console=console,
        include_subtasks=not getattr(args, "no_subtasks", False),
        include_descriptions=not getattr(args, "no_descriptions", False),
    )

    # Preview mode
    if preview_only:
        console.section("Preview")
        content = generator.preview(epic_key)
        if content:
            console.print()
            console.print("-" * 60)
            print(content)
            console.print("-" * 60)
            console.print()
            console.info(f"Use --execute to write to {output_path}")
            return ExitCode.SUCCESS
        console.error("Failed to generate preview")
        return ExitCode.ERROR

    # Generate
    console.section("Generating Template")
    result = generator.generate(
        epic_key=epic_key,
        output_path=output_path,
        dry_run=dry_run,
    )

    # Show result
    console.print()

    if result.success:
        if dry_run:
            console.success(f"Would generate: {result.output_path}")
            console.info("Use --execute to create the file")
        else:
            console.success(f"Generated: {result.output_path}")

        console.detail(f"Epic: {result.epic_key} - {result.epic_title}")
        console.detail(f"Stories: {result.stories_count}")
        console.detail(f"Subtasks: {result.subtasks_count}")
    else:
        console.error("Generation failed")

    if result.warnings:
        console.print()
        console.warning("Warnings:")
        for warning in result.warnings:
            console.item(warning, "warn")

    if result.errors:
        console.print()
        console.error("Errors:")
        for error in result.errors:
            console.item(error, "fail")

    # Next steps
    if result.success and not dry_run:
        console.print()
        console.info("Next steps:")
        console.item(f"Edit {result.output_path} to refine the content")
        console.item(
            f"Sync changes: spectra --input {result.output_path} --epic {epic_key} --execute"
        )

    return ExitCode.SUCCESS if result.success else ExitCode.ERROR
