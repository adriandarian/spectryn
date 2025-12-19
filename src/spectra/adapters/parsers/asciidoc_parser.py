"""
AsciiDoc Parser - Parse AsciiDoc files into domain entities.

Implements the DocumentParserPort interface for AsciiDoc specifications.

AsciiDoc is a text document format similar to Markdown but with richer
semantic capabilities, commonly used in technical documentation.
"""

import logging
import re
from pathlib import Path

from spectra.core.domain.entities import Comment, Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort


class AsciiDocParser(DocumentParserPort):
    """
    Parser for AsciiDoc epic/story files.

    Supports AsciiDoc format with structured sections for stories.

    Example AsciiDoc format:

    ```asciidoc
    = Epic Title
    :epic-key: PROJ-123

    == US-001: Story Title

    [cols="1,1"]
    |===
    | *Story Points* | 5
    | *Priority* | High
    | *Status* | Planned
    |===

    === Description

    *As a* user +
    *I want* to do something +
    *So that* I get benefit

    === Acceptance Criteria

    * [ ] First criterion
    * [x] Second criterion (done)

    === Subtasks

    [cols="1,3,1,1"]
    |===
    | # | Task | SP | Status

    | 1 | Implement feature | 2 | Planned
    | 2 | Write tests | 1 | Done
    |===

    === Technical Notes

    Implementation details here.

    === Links

    * blocks: PROJ-456
    * depends on: OTHER-789

    === Comments

    [quote, @user1, 2025-01-15]
    ____
    This is a comment about the story.
    ____
    ```
    """

    # Patterns for AsciiDoc parsing
    STORY_PATTERN = r"^==\s+(?:.*?)?(US-\d+):\s*([^\n]+)"
    EPIC_TITLE_PATTERN = r"^=\s+([^\n]+)"
    EPIC_KEY_PATTERN = r":epic-key:\s*([A-Z]+-\d+)"

    def __init__(self) -> None:
        """Initialize the AsciiDoc parser."""
        self.logger = logging.getLogger("AsciiDocParser")

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "AsciiDoc"

    @property
    def supported_extensions(self) -> list[str]:
        return [".adoc", ".asciidoc", ".asc"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid AsciiDoc file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Check for AsciiDoc-like content
        # Look for AsciiDoc headings (= Title) or attributes (:key: value)
        has_adoc_heading = bool(re.search(r"^=+\s+\S", source, re.MULTILINE))
        has_attributes = bool(re.search(r"^:\w+:", source, re.MULTILINE))
        has_story = bool(re.search(self.STORY_PATTERN, source, re.MULTILINE))

        return has_adoc_heading or has_attributes or has_story

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from AsciiDoc source."""
        content = self._get_content(source)
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from AsciiDoc source."""
        content = self._get_content(source)

        # Extract epic title from first heading
        title_match = re.search(self.EPIC_TITLE_PATTERN, content, re.MULTILINE)
        epic_title = title_match.group(1).strip() if title_match else "Untitled Epic"

        # Extract epic key from attribute
        key_match = re.search(self.EPIC_KEY_PATTERN, content)
        epic_key = key_match.group(1) if key_match else "EPIC-0"

        stories = self._parse_all_stories(content)

        if not stories:
            return None

        return Epic(
            key=IssueKey(epic_key),
            title=epic_title,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate AsciiDoc source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        story_matches = list(re.finditer(self.STORY_PATTERN, content, re.MULTILINE))
        if not story_matches:
            errors.append("No user stories found matching pattern '== US-XXX: Title'")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _get_content(self, source: str | Path) -> str:
        """Get content from file path or string."""
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8")
        if isinstance(source, str):
            if "\n" not in source and len(source) < 4096:
                try:
                    path = Path(source)
                    if path.exists():
                        return path.read_text(encoding="utf-8")
                except OSError:
                    pass
        return source

    def _parse_all_stories(self, content: str) -> list[UserStory]:
        """Parse all stories from content."""
        stories = []

        story_matches = list(re.finditer(self.STORY_PATTERN, content, re.MULTILINE))
        self.logger.debug(f"Found {len(story_matches)} stories")

        for i, match in enumerate(story_matches):
            story_id = match.group(1)
            title = match.group(2).strip()

            # Get content until next story or end
            start = match.end()
            end = story_matches[i + 1].start() if i + 1 < len(story_matches) else len(content)
            story_content = content[start:end]

            try:
                story = self._parse_story(story_id, title, story_content)
                if story:
                    stories.append(story)
            except Exception as e:
                self.logger.warning(f"Failed to parse {story_id}: {e}")

        return stories

    def _parse_story(self, story_id: str, title: str, content: str) -> UserStory | None:
        """Parse a single story from content block."""
        # Extract metadata from table or attributes
        story_points = self._extract_field(content, "Story Points", "0")
        priority = self._extract_field(content, "Priority", "Medium")
        status = self._extract_field(content, "Status", "Planned")

        # Extract sections
        description = self._extract_description(content)
        acceptance = self._extract_acceptance_criteria(content)
        subtasks = self._extract_subtasks(content)
        tech_notes = self._extract_section(content, "Technical Notes")
        links = self._extract_links(content)
        comments = self._extract_comments(content)
        commits = self._extract_commits(content)

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=tech_notes or "",
            story_points=int(story_points) if story_points.isdigit() else 0,
            priority=Priority.from_string(priority),
            status=Status.from_string(status),
            subtasks=subtasks,
            commits=commits,
            links=links,
            comments=comments,
        )

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """Extract field value from AsciiDoc table or attribute."""
        # Try table format: | *Field* | Value |
        table_pattern = rf"\|\s*\*{field_name}\*\s*\|\s*([^|\n]+)"
        match = re.search(table_pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Try attribute format: :field: value
        attr_pattern = rf":{field_name.lower().replace(' ', '-')}:\s*(.+)"
        match = re.search(attr_pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return default

    def _extract_description(self, content: str) -> Description | None:
        """Extract As a/I want/So that description."""
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        # Pattern for AsciiDoc format with line continuations (+)
        pattern = r"\*As a\*\s+(.+?)(?:\s*\+\s*|\n)\s*\*I want\*\s+(.+?)(?:\s*\+\s*|\n)\s*\*So that\*\s+(.+?)(?:\n|$)"
        match = re.search(pattern, section, re.IGNORECASE | re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip().rstrip("+"),
                want=match.group(2).strip().rstrip("+"),
                benefit=match.group(3).strip(),
            )

        # Try simpler format
        simple_pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
        match = re.search(simple_pattern, section, re.IGNORECASE | re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        return None

    def _extract_acceptance_criteria(self, content: str) -> AcceptanceCriteria:
        """Extract acceptance criteria from checkboxes."""
        items: list[str] = []
        checked: list[bool] = []

        section = self._extract_section(content, "Acceptance Criteria")
        if not section:
            return AcceptanceCriteria.from_list([], [])

        # AsciiDoc checkbox format: * [ ] item or * [x] item
        for match in re.finditer(r"\*\s*\[([ xX])\]\s*(.+)", section):
            is_checked = match.group(1).lower() == "x"
            text = match.group(2).strip()
            items.append(text)
            checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from table."""
        subtasks = []

        section = self._extract_section(content, "Subtasks")
        if not section:
            return subtasks

        # Parse table rows: | # | Task | SP | Status |
        pattern = r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|\n]+)"
        for match in re.finditer(pattern, section):
            subtasks.append(
                Subtask(
                    number=int(match.group(1)),
                    name=match.group(2).strip(),
                    description="",
                    story_points=int(match.group(3)),
                    status=Status.from_string(match.group(4).strip()),
                )
            )

        return subtasks

    def _extract_commits(self, content: str) -> list[CommitRef]:
        """Extract commits from section."""
        commits = []

        section = self._extract_section(content, "Commits")
        if not section:
            section = self._extract_section(content, "Related Commits")

        if not section:
            return commits

        # Parse commit lines: * `abc123` - Message
        pattern = r"\*\s*`([a-f0-9]+)`\s*[-–—]?\s*(.+)"
        for match in re.finditer(pattern, section):
            commits.append(
                CommitRef(
                    hash=match.group(1)[:8],
                    message=match.group(2).strip(),
                )
            )

        return commits

    def _extract_links(self, content: str) -> list[tuple[str, str]]:
        """Extract issue links from content."""
        links = []

        section = self._extract_section(content, "Links")
        if not section:
            section = self._extract_section(content, "Dependencies")

        if not section:
            return links

        # Parse bullet list: * blocks: PROJ-123
        pattern = r"\*\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+([A-Z]+-\d+)"
        for match in re.finditer(pattern, section, re.IGNORECASE):
            link_type = match.group(1).strip().lower()
            target = match.group(2).strip()
            links.append((link_type, target))

        return links

    def _extract_comments(self, content: str) -> list[Comment]:
        """Extract comments from quote blocks."""
        from datetime import datetime

        comments = []

        section = self._extract_section(content, "Comments")
        if not section:
            return comments

        # Parse AsciiDoc quote blocks:
        # [quote, @author, date]
        # ____
        # Comment text
        # ____
        quote_pattern = (
            r"\[quote(?:,\s*@?([^,\]]+))?(?:,\s*(\d{4}-\d{2}-\d{2}))?\]\s*\n____\n([\s\S]*?)____"
        )
        for match in re.finditer(quote_pattern, section):
            author = match.group(1).strip() if match.group(1) else None
            date_str = match.group(2)
            body = match.group(3).strip()

            created_at = None
            if date_str:
                try:
                    created_at = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

            if body:
                comments.append(
                    Comment(
                        body=body,
                        author=author,
                        created_at=created_at,
                        comment_type="text",
                    )
                )

        # Also parse simple bullet comments
        for match in re.finditer(r"\*\s+(.+)", section):
            text = match.group(1).strip()
            # Skip if it looks like a link
            if re.match(r"(blocks|depends|relates)", text, re.IGNORECASE):
                continue
            # Skip if already captured in quote block
            if any(text in c.body for c in comments):
                continue
            comments.append(
                Comment(
                    body=text,
                    author=None,
                    created_at=None,
                    comment_type="text",
                )
            )

        return comments

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a heading."""
        # AsciiDoc uses === for subsections
        pattern = rf"^===\s*{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()

        # Find next heading at same or higher level
        next_heading = re.search(r"^={2,3}\s+\S", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
