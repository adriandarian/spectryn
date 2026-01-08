"""
ReStructuredText Parser - Parse RST files into domain entities.

Implements the DocumentParserPort interface for reStructuredText files.

reStructuredText is the Python documentation standard format, commonly used
in Sphinx documentation and Python project documentation.
"""

import contextlib
import logging
import re
from datetime import datetime
from pathlib import Path

from spectryn.core.domain.entities import Comment, Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort


class RstParser(DocumentParserPort):
    """
    Parser for reStructuredText epic/story files.

    Supports RST format with structured sections for stories.

    Example RST format:

    ```rst
    ============
    Epic Title
    ============

    :epic-key: PROJ-123

    PROJ-001: Story Title
    ---------------------

    :story-points: 5
    :priority: High
    :status: Planned

    Description
    ^^^^^^^^^^^

    **As a** user
    **I want** to do something
    **So that** I get benefit

    Acceptance Criteria
    ^^^^^^^^^^^^^^^^^^^

    - [ ] First criterion
    - [x] Second criterion (done)

    Subtasks
    ^^^^^^^^

    .. list-table::
       :header-rows: 1

       * - #
         - Task
         - SP
         - Status
       * - 1
         - Implement feature
         - 2
         - Planned

    Technical Notes
    ^^^^^^^^^^^^^^^

    Implementation details here.

    Links
    ^^^^^

    * blocks: PROJ-456
    * depends on: OTHER-789

    Comments
    ^^^^^^^^

    .. note:: @user1 (2025-01-15)

       This is a comment about the story.
    ```
    """

    # Patterns for RST parsing
    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    # RST section underlines use consistent characters
    # Title underline can be =, -, ^, ", etc.
    STORY_PATTERN = rf"^({STORY_ID_PATTERN}):\s*([^\n]+)\n[-=^\"~`]+\s*$"
    EPIC_TITLE_PATTERN = r"^[=]+\n([^\n]+)\n[=]+\s*$"
    EPIC_KEY_PATTERN = r":epic-key:\s*([A-Z]+[-_/]\d+)"

    def __init__(self) -> None:
        """Initialize the RST parser."""
        self.logger = logging.getLogger("RstParser")

    @property
    def name(self) -> str:
        return "ReStructuredText"

    @property
    def supported_extensions(self) -> list[str]:
        return [".rst", ".rest", ".txt"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid RST file or content."""
        if isinstance(source, Path):
            # .txt could be many formats, be more careful
            if source.suffix.lower() == ".txt":
                try:
                    content = source.read_text(encoding="utf-8")
                    return self._looks_like_rst(content)
                except Exception:
                    return False
            return source.suffix.lower() in [".rst", ".rest"]

        return self._looks_like_rst(source)

    def _looks_like_rst(self, content: str) -> bool:
        """Check if content looks like RST."""
        # Look for RST-specific patterns
        has_rst_heading = bool(
            re.search(r"^[=\-^\"~`]+\n.+\n[=\-^\"~`]+\s*$", content, re.MULTILINE)
        )
        has_directives = bool(re.search(r"^\.\.\s+\w+::", content, re.MULTILINE))
        has_field_list = bool(re.search(r"^:\w+:", content, re.MULTILINE))
        has_story = bool(re.search(self.STORY_PATTERN, content, re.MULTILINE))

        return has_rst_heading or has_directives or has_field_list or has_story

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from RST source."""
        content = self._get_content(source)
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from RST source."""
        content = self._get_content(source)

        # Extract epic title from over/underlined heading
        title_match = re.search(self.EPIC_TITLE_PATTERN, content, re.MULTILINE)
        epic_title = title_match.group(1).strip() if title_match else "Untitled Epic"

        # Extract epic key from field list
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
        """Validate RST source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        story_matches = list(re.finditer(self.STORY_PATTERN, content, re.MULTILINE))
        if not story_matches:
            errors.append(
                "No user stories found matching pattern 'ID: Title' with underline "
                "(e.g., PROJ-001, US_123, FEAT/001, #123)"
            )

        return errors

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
        story_points = self._extract_field(content, "story-points", "0")
        priority = self._extract_field(content, "priority", "Medium")
        status = self._extract_field(content, "status", "Planned")

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
        """Extract field value from RST field list."""
        # RST field list format: :field-name: value
        pattern = rf":{field_name}:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return default

    def _extract_description(self, content: str) -> Description | None:
        """Extract As a/I want/So that description."""
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        # Pattern for RST format
        pattern = (
            r"\*\*As a\*\*\s+(.+?)(?:\n)\s*"
            r"\*\*I want\*\*\s+(.+?)(?:\n)\s*"
            r"\*\*So that\*\*\s+(.+?)(?:\n|$)"
        )
        match = re.search(pattern, section, re.IGNORECASE | re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        # Plain text format
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

        # RST checkbox format: - [ ] item or - [x] item
        for match in re.finditer(r"[-*]\s*\[([ xX])\]\s*(.+)", section):
            is_checked = match.group(1).lower() == "x"
            text = match.group(2).strip()
            items.append(text)
            checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from list-table directive."""
        subtasks = []

        section = self._extract_section(content, "Subtasks")
        if not section:
            return subtasks

        # Parse list-table rows: * - # - Task - SP - Status
        pattern = r"\*\s+-\s+(\d+)\s+-\s+([^\n]+?)\s+-\s+(\d+)\s+-\s+([^\n]+)"
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

        # Parse commit lines: * ``abc123`` - Message
        pattern = r"\*\s*``([a-f0-9]+)``\s*[-–—]?\s*(.+)"
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

        issue_key_pattern = r"(?:[A-Z]+[-_/]\d+|#\d+)"
        pattern = (
            rf"\*\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+({issue_key_pattern})"
        )
        for match in re.finditer(pattern, section, re.IGNORECASE):
            link_type = match.group(1).strip().lower()
            target = match.group(2).strip()
            links.append((link_type, target))

        return links

    def _extract_comments(self, content: str) -> list[Comment]:
        """Extract comments from note directives."""
        comments = []

        section = self._extract_section(content, "Comments")
        if not section:
            return comments

        # Parse RST note directives with author info:
        # .. note:: @author (date)
        #
        #    Comment body
        note_pattern = r"\.\.\s*note::\s*@?([^\s(]+)?\s*(?:\((\d{4}-\d{2}-\d{2})\))?\s*\n\n\s+(.+?)(?=\n\n\.\.|$)"
        for match in re.finditer(note_pattern, section, re.DOTALL):
            author = match.group(1).strip() if match.group(1) else None
            date_str = match.group(2)
            body = match.group(3).strip()

            created_at = None
            if date_str:
                with contextlib.suppress(ValueError):
                    created_at = datetime.strptime(date_str, "%Y-%m-%d")

            if body:
                comments.append(
                    Comment(
                        body=body,
                        author=author,
                        created_at=created_at,
                        comment_type="text",
                    )
                )

        return comments

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a heading."""
        # RST subsection headings use underlines like ^^^^ or ~~~~
        pattern = rf"^{re.escape(heading)}\s*\n[=\-^\"~`]+\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()

        # Find next heading (any underlined text)
        next_heading = re.search(r"^.+\n[=\-^\"~`]+\s*$", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
