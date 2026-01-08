"""
Org-mode Parser - Parse Emacs Org-mode files into domain entities.

Implements the DocumentParserPort interface for Org-mode files.

Org-mode is a powerful outliner and organizational mode for Emacs,
widely used for note-taking, planning, and documentation.
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


class OrgModeParser(DocumentParserPort):
    """
    Parser for Emacs Org-mode epic/story files.

    Supports Org-mode format with structured sections for stories.

    Example Org-mode format:

    ```org
    #+TITLE: Epic Title
    #+EPIC_KEY: PROJ-123

    * PROJ-001: Story Title
    :PROPERTIES:
    :STORY_POINTS: 5
    :PRIORITY: High
    :STATUS: Planned
    :END:

    ** Description
    *As a* user
    *I want* to do something
    *So that* I get benefit

    ** Acceptance Criteria
    - [ ] First criterion
    - [X] Second criterion (done)

    ** Subtasks
    | # | Task            | SP | Status  |
    |---+-----------------+----+---------|
    | 1 | Implement       |  2 | Planned |
    | 2 | Write tests     |  1 | Done    |

    ** Technical Notes
    Implementation details here.

    ** Links
    - blocks :: PROJ-456
    - depends on :: OTHER-789

    ** Comments
    *** @user1 [2025-01-15]
    This is a comment about the story.
    ```
    """

    # Patterns for Org-mode parsing
    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    # Org headings with stars: * PROJ-001: Title
    # Support TODO keywords: * TODO PROJ-001: Title
    STORY_PATTERN = (
        rf"^\*\s+(?:TODO|DONE|NEXT|WAITING|CANCELLED)?\s*({STORY_ID_PATTERN}):\s*([^\n]+)"
    )
    EPIC_TITLE_PATTERN = r"#\+TITLE:\s*(.+)"
    EPIC_KEY_PATTERN = r"#\+EPIC_KEY:\s*([A-Z]+[-_/]\d+)"

    # Org-mode status mappings
    ORG_STATUS_MAP = {
        "TODO": Status.PLANNED,
        "NEXT": Status.IN_PROGRESS,
        "DONE": Status.DONE,
        "WAITING": Status.OPEN,  # On hold/waiting maps to Open
        "CANCELLED": Status.CANCELLED,
    }

    # Org-mode priority mappings ([#A], [#B], [#C])
    ORG_PRIORITY_MAP = {
        "A": Priority.CRITICAL,
        "B": Priority.HIGH,
        "C": Priority.MEDIUM,
    }

    def __init__(self) -> None:
        """Initialize the Org-mode parser."""
        self.logger = logging.getLogger("OrgModeParser")

    @property
    def name(self) -> str:
        return "Org-mode"

    @property
    def supported_extensions(self) -> list[str]:
        return [".org"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid Org-mode file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        return self._looks_like_org(source)

    def _looks_like_org(self, content: str) -> bool:
        """Check if content looks like Org-mode."""
        # Look for Org-specific patterns
        has_org_heading = bool(re.search(r"^\*+\s+", content, re.MULTILINE))
        has_org_keywords = bool(re.search(r"^#\+\w+:", content, re.MULTILINE))
        has_properties = bool(re.search(r":PROPERTIES:", content))
        has_story = bool(re.search(self.STORY_PATTERN, content, re.MULTILINE))

        return has_org_heading or has_org_keywords or has_properties or has_story

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from Org-mode source."""
        content = self._get_content(source)
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from Org-mode source."""
        content = self._get_content(source)

        # Extract epic title from #+TITLE:
        title_match = re.search(self.EPIC_TITLE_PATTERN, content)
        epic_title = title_match.group(1).strip() if title_match else "Untitled Epic"

        # Extract epic key from #+EPIC_KEY:
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
        """Validate Org-mode source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        story_matches = list(re.finditer(self.STORY_PATTERN, content, re.MULTILINE))
        if not story_matches:
            errors.append(
                "No user stories found matching pattern '* ID: Title' "
                "(e.g., * PROJ-001: Story Title)"
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
            # Find next story (same or lower level heading)
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
        # Extract from PROPERTIES drawer
        properties = self._extract_properties(content)

        story_points = properties.get("STORY_POINTS", "0")
        priority = properties.get("PRIORITY", "Medium")
        status = properties.get("STATUS", "Planned")

        # Check for Org-mode priority cookie [#A], [#B], [#C]
        priority_match = re.search(r"\[#([ABC])\]", title)
        if priority_match:
            org_priority = priority_match.group(1)
            priority = self.ORG_PRIORITY_MAP.get(org_priority, Priority.MEDIUM).value

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

    def _extract_properties(self, content: str) -> dict[str, str]:
        """Extract properties from Org-mode PROPERTIES drawer."""
        properties = {}

        drawer_match = re.search(r":PROPERTIES:\s*\n([\s\S]*?):END:", content, re.MULTILINE)
        if drawer_match:
            drawer_content = drawer_match.group(1)
            for match in re.finditer(r":(\w+):\s*(.+)", drawer_content):
                key = match.group(1).upper()
                value = match.group(2).strip()
                properties[key] = value

        return properties

    def _extract_description(self, content: str) -> Description | None:
        """Extract As a/I want/So that description."""
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        # Pattern for Org bold format
        pattern = (
            r"\*As a\*\s+(.+?)(?:\n)\s*"
            r"\*I want\*\s+(.+?)(?:\n)\s*"
            r"\*So that\*\s+(.+?)(?:\n|$)"
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

        # Org checkbox format: - [ ] item or - [X] item
        for match in re.finditer(r"[-+]\s*\[([ xX])\]\s*(.+)", section):
            is_checked = match.group(1).upper() == "X"
            text = match.group(2).strip()
            items.append(text)
            checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from Org table."""
        subtasks = []

        section = self._extract_section(content, "Subtasks")
        if not section:
            return subtasks

        # Parse Org table rows: | # | Task | SP | Status |
        # Skip separator rows (|---+---+---+---|)
        pattern = r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|"
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

        # Parse commit lines: - =abc123= - Message (Org verbatim)
        pattern = r"[-+]\s*=([a-f0-9]+)=\s*[-–—]?\s*(.+)"
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

        # Org description list format: - blocks :: PROJ-456
        issue_key_pattern = r"(?:[A-Z]+[-_/]\d+|#\d+)"
        pattern = rf"[-+]\s*(blocks|blocked by|relates to|depends on|duplicates)\s*::\s*({issue_key_pattern})"
        for match in re.finditer(pattern, section, re.IGNORECASE):
            link_type = match.group(1).strip().lower()
            target = match.group(2).strip()
            links.append((link_type, target))

        return links

    def _extract_comments(self, content: str) -> list[Comment]:
        """Extract comments from subheadings."""
        comments = []

        section = self._extract_section(content, "Comments")
        if not section:
            return comments

        # Parse subheadings: *** @author [date]
        comment_pattern = (
            r"\*{3}\s*@?([^\s\[]+)?\s*(?:\[(\d{4}-\d{2}-\d{2})\])?\s*\n([\s\S]*?)(?=\n\*{3}|$)"
        )
        for match in re.finditer(comment_pattern, section):
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
        """Extract content under an Org heading."""
        # Org subheadings with **
        pattern = rf"^\*\*\s*{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()

        # Find next heading at same or higher level
        next_heading = re.search(r"^\*{1,2}\s+\S", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
