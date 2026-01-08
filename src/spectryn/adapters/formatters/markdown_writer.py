"""
Markdown Writer - Generate markdown documents from domain entities.

This is the reverse of the MarkdownParser - it takes domain entities
and converts them back to markdown format for bidirectional sync.
"""

from datetime import datetime

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Status
from spectryn.core.domain.value_objects import CommitRef


class MarkdownWriter:
    """
    Writer for generating markdown epic files from domain entities.

    Produces markdown in the same format that MarkdownParser expects,
    enabling round-trip sync between Jira and markdown.
    """

    def __init__(
        self,
        include_epic_header: bool = True,
        include_metadata: bool = True,
        include_subtasks: bool = True,
        include_commits: bool = True,
        include_technical_notes: bool = True,
    ):
        """
        Initialize the writer.

        Args:
            include_epic_header: Whether to include the epic title header.
            include_metadata: Whether to include story metadata table.
            include_subtasks: Whether to include subtasks table.
            include_commits: Whether to include related commits table.
            include_technical_notes: Whether to include technical notes section.
        """
        self.include_epic_header = include_epic_header
        self.include_metadata = include_metadata
        self.include_subtasks = include_subtasks
        self.include_commits = include_commits
        self.include_technical_notes = include_technical_notes

    def write_epic(self, epic: Epic) -> str:
        """
        Generate complete markdown for an epic with all its stories.

        Args:
            epic: Epic entity with stories.

        Returns:
            Complete markdown document as string.
        """
        lines: list[str] = []

        # Epic header
        if self.include_epic_header:
            lines.append(f"# 🚀 {epic.key}: {epic.title}")
            lines.append("")

            if epic.summary:
                lines.append(epic.summary)
                lines.append("")

            if epic.description:
                lines.append(epic.description)
                lines.append("")

            lines.append("---")
            lines.append("")

        # Stories
        for story in epic.stories:
            lines.append(self.write_story(story))
            lines.append("")
            lines.append("---")
            lines.append("")

        # Footer
        lines.append(f"> *Last synced from Jira: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def write_story(self, story: UserStory) -> str:
        """
        Generate markdown for a single user story.

        Args:
            story: UserStory entity.

        Returns:
            Markdown string for the story.
        """
        lines: list[str] = []

        # Story header
        emoji = self._get_status_emoji(story.status)
        lines.append(f"### {emoji} {story.id}: {story.title}")
        lines.append("")

        # Jira link if available
        if story.external_key:
            lines.append(f"> **Jira:** [{story.external_key}]({story.external_url or '#'})")
            lines.append("")

        # Metadata table
        if self.include_metadata:
            lines.extend(self._write_metadata_table(story))
            lines.append("")

        # Description
        lines.append("#### Description")
        lines.append("")
        if story.description:
            lines.append(story.description.to_markdown())
        else:
            lines.append("**As a** user")
            lines.append("**I want** [to be defined]")
            lines.append("**So that** [benefit to be defined]")
        lines.append("")

        # Acceptance Criteria
        if story.acceptance_criteria and len(story.acceptance_criteria) > 0:
            lines.append("#### Acceptance Criteria")
            lines.append("")
            lines.append(story.acceptance_criteria.to_markdown())
            lines.append("")

        # Subtasks
        if self.include_subtasks and story.subtasks:
            lines.extend(self._write_subtasks_table(story.subtasks))
            lines.append("")

        # Related Commits
        if self.include_commits and story.commits:
            lines.extend(self._write_commits_table(story.commits))
            lines.append("")

        # Technical Notes
        if self.include_technical_notes and story.technical_notes:
            lines.append("#### Technical Notes")
            lines.append("")
            lines.append(story.technical_notes)
            lines.append("")

        return "\n".join(lines)

    def write_stories(self, stories: list[UserStory]) -> str:
        """
        Generate markdown for a list of stories without epic header.

        Args:
            stories: List of UserStory entities.

        Returns:
            Markdown string with all stories.
        """
        sections = []
        for story in stories:
            sections.append(self.write_story(story))
            sections.append("")
            sections.append("---")
            sections.append("")

        return "\n".join(sections)

    def _write_metadata_table(self, story: UserStory) -> list[str]:
        """Generate metadata table for a story."""
        lines = [
            "| Field | Value |",
            "|-------|-------|",
            f"| **Story Points** | {story.story_points} |",
            f"| **Priority** | {story.priority.emoji} {story.priority.display_name} |",
            f"| **Status** | {story.status.emoji} {story.status.display_name} |",
        ]

        if story.assignee:
            lines.append(f"| **Assignee** | {story.assignee} |")

        if story.labels:
            lines.append(f"| **Labels** | {', '.join(story.labels)} |")

        return lines

    def _write_subtasks_table(self, subtasks: list[Subtask]) -> list[str]:
        """Generate subtasks table."""
        lines = [
            "#### Subtasks",
            "",
            "| # | Subtask | Description | SP | Status |",
            "|---|---------|-------------|----|---------| ",
        ]

        for i, subtask in enumerate(subtasks, start=1):
            number = subtask.number if subtask.number > 0 else i
            status_text = f"{subtask.status.emoji} {subtask.status.display_name}"

            # Escape pipe characters in name and description
            name = subtask.name.replace("|", "\\|")
            desc = subtask.description.replace("|", "\\|")

            lines.append(f"| {number} | {name} | {desc} | {subtask.story_points} | {status_text} |")

        return lines

    def _write_commits_table(self, commits: list[CommitRef]) -> list[str]:
        """Generate commits table."""
        lines = [
            "#### Related Commits",
            "",
            "| Commit | Message |",
            "|--------|---------|",
        ]

        for commit in commits:
            # Escape pipe characters in message
            message = commit.message.replace("|", "\\|")
            lines.append(f"| `{commit.short_hash}` | {message} |")

        return lines

    def _get_status_emoji(self, status: Status) -> str:
        """Get emoji for story status."""
        return status.emoji


class MarkdownUpdater:
    """
    Updates an existing markdown file with changes from Jira.

    Preserves formatting and sections that exist in the original
    while updating fields that changed in Jira.
    """

    def __init__(self) -> None:
        """Initialize the updater."""
        self.writer = MarkdownWriter()

    def update_story_in_content(
        self,
        content: str,
        story_id: str,
        updated_story: UserStory,
    ) -> str:
        """
        Update a single story within existing markdown content.

        Args:
            content: Original markdown content.
            story_id: Story ID to update (e.g., "STORY-001", "PROJ-123").
            updated_story: Updated story data from Jira.

        Returns:
            Updated markdown content.
        """
        import re

        # Find the story section
        pattern = rf"(### [^\n]+ {re.escape(story_id)}: [^\n]+\n)([\s\S]*?)(?=### [^\n]+ US-\d+:|---\s*$|\Z)"

        def replace_story(match: re.Match) -> str:
            # Generate new story content
            new_content = self.writer.write_story(updated_story)
            return new_content + "\n"

        return re.sub(pattern, replace_story, content)

    def update_field_in_story(
        self,
        content: str,
        story_id: str,
        field: str,
        new_value: str,
    ) -> str:
        """
        Update a specific field within a story.

        Args:
            content: Original markdown content.
            story_id: Story ID to update.
            field: Field name (e.g., "Status", "Story Points").
            new_value: New value for the field.

        Returns:
            Updated markdown content.
        """
        import re

        # Find the story section first
        story_pattern = rf"(### [^\n]+ {re.escape(story_id)}: [^\n]+\n[\s\S]*?)(?=### [^\n]+ US-\d+:|---\s*$|\Z)"

        def update_field(match: re.Match) -> str:
            story_content = match.group(1)

            # Update the field in the metadata table
            field_pattern = rf"\|\s*\*\*{re.escape(field)}\*\*\s*\|\s*[^|]+\s*\|"
            replacement = f"| **{field}** | {new_value} |"

            return re.sub(field_pattern, replacement, story_content)

        return re.sub(story_pattern, update_field, content)

    def append_story(self, content: str, story: UserStory) -> str:
        """
        Append a new story to existing markdown content.

        Args:
            content: Existing markdown content.
            story: New story to append.

        Returns:
            Updated content with new story appended.
        """
        # Find the last --- separator before the footer
        import re

        new_story_md = self.writer.write_story(story)

        # Check if there's a footer we should preserve
        footer_pattern = r"(>\s*\*Last synced[^\n]*\*)\s*$"
        footer_match = re.search(footer_pattern, content)

        if footer_match:
            # Insert before footer
            insert_pos = footer_match.start()
            new_content = (
                content[:insert_pos].rstrip()
                + "\n\n"
                + new_story_md
                + "\n\n---\n\n"
                + content[insert_pos:]
            )
        else:
            # Just append at the end
            new_content = content.rstrip() + "\n\n---\n\n" + new_story_md + "\n"

        return new_content

    def update_stories(
        self,
        content: str,
        updates: dict[str, dict[str, object]],
    ) -> str:
        """
        Update multiple stories with field changes from tracker.

        This is used in bidirectional sync to pull remote changes
        into the markdown file.

        Args:
            content: Original markdown content.
            updates: Dictionary mapping story IDs to field updates.
                     Example: {"US-001": {"status": "Done", "story_points": 5}}

        Returns:
            Updated markdown content with all changes applied.
        """
        import re

        from spectryn.core.domain.enums import Priority, Status

        updated_content = content

        for story_id, field_updates in updates.items():
            for field, value in field_updates.items():
                if field == "status":
                    # Convert status value to display format
                    if isinstance(value, str):
                        status = Status.from_string(value)
                        display_value = f"{status.emoji} {status.display_name}"
                    elif isinstance(value, int):
                        status = Status(value)
                        display_value = f"{status.emoji} {status.display_name}"
                    else:
                        display_value = str(value)
                    updated_content = self.update_field_in_story(
                        updated_content, story_id, "Status", display_value
                    )

                elif field == "story_points":
                    if isinstance(value, (int, float)):
                        sp = int(value)
                    elif value:
                        sp = int(str(value))
                    else:
                        sp = 0
                    updated_content = self.update_field_in_story(
                        updated_content, story_id, "Story Points", str(sp)
                    )

                elif field == "priority":
                    if isinstance(value, str):
                        priority = Priority.from_string(value)
                        display_value = f"{priority.emoji} {priority.display_name}"
                    elif isinstance(value, int):
                        priority = Priority(value)
                        display_value = f"{priority.emoji} {priority.display_name}"
                    else:
                        display_value = str(value)
                    updated_content = self.update_field_in_story(
                        updated_content, story_id, "Priority", display_value
                    )

                elif field == "assignee":
                    updated_content = self.update_field_in_story(
                        updated_content, story_id, "Assignee", str(value) if value else "Unassigned"
                    )

                elif field == "title":
                    # Update story title in header
                    pattern = rf"(### [^\n]+ {re.escape(story_id)}: )[^\n]+"
                    replacement = rf"\g<1>{value}"
                    updated_content = re.sub(pattern, replacement, updated_content)

        # Update the last synced timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer_pattern = r">\s*\*Last synced[^\n]*\*"
        new_footer = f"> *Last synced from Jira: {timestamp}*"
        if re.search(footer_pattern, updated_content):
            updated_content = re.sub(footer_pattern, new_footer, updated_content)

        return updated_content
