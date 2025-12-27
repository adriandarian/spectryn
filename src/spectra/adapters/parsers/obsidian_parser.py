"""
Obsidian-flavored Markdown Parser - Parse Obsidian MD files into domain entities.

Implements the DocumentParserPort interface for Obsidian Markdown files.

Obsidian extends standard Markdown with wikilinks, dataview syntax,
frontmatter YAML, callouts, and other features for knowledge management.
"""

import contextlib
import logging
import re
from datetime import datetime
from pathlib import Path

import yaml

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


class ObsidianParser(DocumentParserPort):
    """
    Parser for Obsidian-flavored Markdown epic/story files.

    Supports Obsidian features:
    - YAML frontmatter for metadata
    - Wikilinks: [[link]] and [[link|alias]]
    - Dataview inline fields: Field:: Value
    - Callouts: > [!note] and > [!tip]
    - Tags: #tag and nested #parent/child

    Example Obsidian format:

    ```markdown
    ---
    epic-key: PROJ-123
    title: Epic Title
    tags: [epic, project]
    ---

    # Epic Title

    ## PROJ-001: Story Title

    Story Points:: 5
    Priority:: High
    Status:: Planned
    Blocks:: [[PROJ-456]]
    Depends On:: [[OTHER-789]]

    ### Description

    **As a** user
    **I want** to do something
    **So that** I get benefit

    ### Acceptance Criteria

    - [ ] First criterion
    - [x] Second criterion (done)

    ### Subtasks

    | # | Task | SP | Status |
    |---|------|----|----|
    | 1 | Implement feature | 2 | Planned |
    | 2 | Write tests | 1 | Done |

    ### Technical Notes

    > [!note]
    > Implementation details here.

    ### Comments

    > [!comment] @user1 (2025-01-15)
    > This is a comment about the story.
    ```
    """

    # Patterns for Obsidian parsing
    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"
    STORY_PATTERN = rf"^##\s+({STORY_ID_PATTERN}):\s*([^\n]+)"
    WIKILINK_PATTERN = r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]"

    def __init__(self) -> None:
        """Initialize the Obsidian parser."""
        self.logger = logging.getLogger("ObsidianParser")

    @property
    def name(self) -> str:
        return "Obsidian"

    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is an Obsidian-flavored Markdown file."""
        if isinstance(source, Path):
            if source.suffix.lower() not in self.supported_extensions:
                return False
            try:
                content = source.read_text(encoding="utf-8")
                return self._is_obsidian_markdown(content)
            except Exception:
                return False

        return self._is_obsidian_markdown(source)

    def _is_obsidian_markdown(self, content: str) -> bool:
        """Check if content has Obsidian-specific features."""
        # Look for Obsidian-specific patterns
        has_frontmatter = content.strip().startswith("---")
        has_wikilinks = bool(re.search(self.WIKILINK_PATTERN, content))
        has_dataview_fields = bool(re.search(r"^\w+::\s*", content, re.MULTILINE))
        has_callouts = bool(re.search(r">\s*\[!\w+\]", content))

        return has_frontmatter or has_wikilinks or has_dataview_fields or has_callouts

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from Obsidian source."""
        content = self._get_content(source)
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from Obsidian source."""
        content = self._get_content(source)

        # Extract frontmatter
        frontmatter = self._extract_frontmatter(content)

        epic_key = (
            frontmatter.get("epic-key")
            or frontmatter.get("epic_key")
            or frontmatter.get("epicKey")
            or frontmatter.get("epic key")
            or "EPIC-0"
        )
        epic_title = frontmatter.get("title", "Untitled Epic")

        # If no title in frontmatter, try h1 heading
        if epic_title == "Untitled Epic":
            title_match = re.search(r"^#\s+([^\n]+)", content, re.MULTILINE)
            if title_match:
                epic_title = title_match.group(1).strip()

        stories = self._parse_all_stories(content)

        if not stories:
            return None

        return Epic(
            key=IssueKey(epic_key),
            title=epic_title,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate Obsidian source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        story_matches = list(re.finditer(self.STORY_PATTERN, content, re.MULTILINE))
        if not story_matches:
            errors.append(
                "No user stories found matching pattern '## ID: Title' "
                "(e.g., ## PROJ-001: Story Title)"
            )

        # Validate frontmatter YAML if present
        if content.strip().startswith("---"):
            try:
                self._extract_frontmatter(content)
            except Exception as e:
                errors.append(f"Invalid YAML frontmatter: {e}")

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

    def _extract_frontmatter(self, content: str) -> dict:
        """Extract YAML frontmatter from content."""
        # Strip leading whitespace before checking for frontmatter
        stripped = content.lstrip()
        if not stripped.startswith("---"):
            return {}

        # Use regex on the stripped content
        match = re.match(r"^---\s*\n([\s\S]*?)\n---", stripped)
        if not match:
            return {}

        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from content."""
        if not content.strip().startswith("---"):
            return content

        match = re.match(r"^---\s*\n[\s\S]*?\n---\s*\n?", content)
        if match:
            return content[match.end() :]
        return content

    def _parse_all_stories(self, content: str) -> list[UserStory]:
        """Parse all stories from content."""
        stories = []

        # Strip frontmatter for story parsing
        content = self._strip_frontmatter(content)

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
        # Extract dataview inline fields
        dataview_fields = self._extract_dataview_fields(content)

        story_points = dataview_fields.get("Story Points", dataview_fields.get("Points", "0"))
        priority = dataview_fields.get("Priority", "Medium")
        status = dataview_fields.get("Status", "Planned")

        description = self._extract_description(content)
        acceptance = self._extract_acceptance_criteria(content)
        subtasks = self._extract_subtasks(content)
        tech_notes = self._extract_section(content, "Technical Notes")
        links = self._extract_links(content, dataview_fields)
        comments = self._extract_comments(content)
        commits = self._extract_commits(content)

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=tech_notes or "",
            story_points=int(story_points) if str(story_points).isdigit() else 0,
            priority=Priority.from_string(str(priority)),
            status=Status.from_string(str(status)),
            subtasks=subtasks,
            commits=commits,
            links=links,
            comments=comments,
        )

    def _extract_dataview_fields(self, content: str) -> dict[str, str]:
        """Extract Dataview inline fields (Field:: Value)."""
        fields = {}

        # Match Field:: Value pattern (case insensitive keys)
        for match in re.finditer(r"^(\w+(?:\s+\w+)?)::\s*(.+?)$", content, re.MULTILINE):
            key = match.group(1).strip()
            value = match.group(2).strip()
            # Resolve wikilinks in values
            value = self._resolve_wikilinks(value)
            fields[key] = value

        return fields

    def _resolve_wikilinks(self, text: str) -> str:
        """Convert wikilinks to plain text."""

        # [[link|alias]] -> alias
        # [[link]] -> link
        def replace_link(match: re.Match) -> str:
            link = match.group(1)
            alias = match.group(2)
            return alias if alias else link

        return re.sub(self.WIKILINK_PATTERN, replace_link, text)

    def _extract_description(self, content: str) -> Description | None:
        """Extract As a/I want/So that description."""
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        # Standard bold format
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

        return None

    def _extract_acceptance_criteria(self, content: str) -> AcceptanceCriteria:
        """Extract acceptance criteria from checkboxes."""
        items: list[str] = []
        checked: list[bool] = []

        section = self._extract_section(content, "Acceptance Criteria")
        if not section:
            return AcceptanceCriteria.from_list([], [])

        for match in re.finditer(r"[-*]\s*\[([ xX])\]\s*(.+)", section):
            is_checked = match.group(1).lower() == "x"
            text = self._resolve_wikilinks(match.group(2).strip())
            items.append(text)
            checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from table."""
        subtasks = []

        section = self._extract_section(content, "Subtasks")
        if not section:
            return subtasks

        pattern = r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|"
        for match in re.finditer(pattern, section):
            subtasks.append(
                Subtask(
                    number=int(match.group(1)),
                    name=self._resolve_wikilinks(match.group(2).strip()),
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

        pattern = r"[-*]\s*`([a-f0-9]+)`\s*[-–—]?\s*(.+)"
        for match in re.finditer(pattern, section):
            commits.append(
                CommitRef(
                    hash=match.group(1)[:8],
                    message=match.group(2).strip(),
                )
            )

        return commits

    def _extract_links(
        self, content: str, dataview_fields: dict[str, str]
    ) -> list[tuple[str, str]]:
        """Extract issue links from content and dataview fields."""
        links = []

        # From dataview fields: Blocks:: [[PROJ-456]]
        link_types = {
            "Blocks": "blocks",
            "Blocked By": "blocked by",
            "Depends On": "depends on",
            "Related To": "relates to",
            "Duplicates": "duplicates",
        }

        issue_key_pattern = r"(?:[A-Z]+[-_/]\d+|#\d+)"

        for field_name, link_type in link_types.items():
            if field_name in dataview_fields:
                value = dataview_fields[field_name]
                # Extract issue keys from wikilinks or plain text
                for key in re.findall(issue_key_pattern, value):
                    links.append((link_type, key))

        # From Links section
        section = self._extract_section(content, "Links")
        if not section:
            section = self._extract_section(content, "Dependencies")

        if section:
            pattern = rf"[-*]\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+\[\[?({issue_key_pattern})"
            for match in re.finditer(pattern, section, re.IGNORECASE):
                link_type = match.group(1).strip().lower()
                target = match.group(2).strip()
                links.append((link_type, target))

        return links

    def _extract_comments(self, content: str) -> list[Comment]:
        """Extract comments from callouts."""
        comments = []

        section = self._extract_section(content, "Comments")
        if not section:
            return comments

        # Parse callout format: > [!comment] @author (date)
        callout_pattern = r">\s*\[!comment\]\s*@?([^\s(]+)?\s*(?:\((\d{4}-\d{2}-\d{2})\))?\s*\n((?:>\s*[^\n]*\n?)+)"
        for match in re.finditer(callout_pattern, section, re.IGNORECASE):
            author = match.group(1).strip() if match.group(1) else None
            date_str = match.group(2)
            body_lines = match.group(3)
            # Strip > prefix from body lines
            body = "\n".join(
                line.lstrip("> ").strip() for line in body_lines.split("\n") if line.strip()
            ).strip()

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

        # Also parse simple blockquote comments
        for match in re.finditer(r">\s*\*\*@([^\*]+)\*\*[:\s]*([^\n]+(?:\n>[^\n]*)*)", section):
            author = match.group(1).strip()
            body = match.group(2).strip()
            body = re.sub(r"\n>\s*", "\n", body).strip()

            comments.append(
                Comment(
                    body=body,
                    author=author,
                    created_at=None,
                    comment_type="text",
                )
            )

        return comments

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a heading."""
        pattern = rf"^###\s*{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()

        # Find next heading at same or higher level
        next_heading = re.search(r"^#{1,3}\s+\S", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
