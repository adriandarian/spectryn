"""
Confluence Cloud API Parser - Parse Confluence pages into domain entities.

Implements the DocumentParserPort interface for Confluence Cloud content.

This parser connects to Confluence Cloud via REST API to fetch pages
and convert them into Spectra domain entities.
"""

import contextlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import Comment, Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort, ParserError


class ConfluenceParser(DocumentParserPort):
    """
    Parser for Confluence Cloud pages.

    Fetches content from Confluence Cloud API and parses structured pages
    into domain entities.

    Configuration via environment variables or constructor:
    - CONFLUENCE_URL: Base URL (e.g., https://company.atlassian.net/wiki)
    - CONFLUENCE_USERNAME: Username or email
    - CONFLUENCE_API_TOKEN: API token for authentication

    Expected page structure:

    ```
    Page Title: PROJ-123 - Epic Title

    Properties table or panel:
    | Property | Value |
    | Epic Key | PROJ-123 |

    Child pages for stories:
    PROJ-001: Story Title
    - Story Points: 5
    - Priority: High
    - Status: Planned

    Description section with user story format
    Acceptance Criteria section with checkboxes
    ```
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
    ) -> None:
        """
        Initialize the Confluence parser.

        Args:
            base_url: Confluence instance URL (or CONFLUENCE_URL env var)
            username: Confluence username/email (or CONFLUENCE_USERNAME env var)
            api_token: Confluence API token (or CONFLUENCE_API_TOKEN env var)
        """
        import os

        self.logger = logging.getLogger("ConfluenceParser")
        self.base_url = base_url or os.environ.get("CONFLUENCE_URL", "")
        self.username = username or os.environ.get("CONFLUENCE_USERNAME", "")
        self.api_token = api_token or os.environ.get("CONFLUENCE_API_TOKEN", "")

        # Cache for API responses
        self._page_cache: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "Confluence"

    @property
    def supported_extensions(self) -> list[str]:
        # Confluence uses page IDs or URLs, not file extensions
        return []

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a Confluence page URL or ID."""
        if isinstance(source, Path):
            return False

        if isinstance(source, str):
            # Check for Confluence URL patterns
            if "atlassian.net/wiki" in source or "/confluence/" in source:
                return True
            # Check for page ID format (numeric)
            if source.isdigit():
                return True
            # Check for space/page path format
            if re.match(r"^[A-Z]+/", source):
                return True

        return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from a Confluence page."""
        if isinstance(source, Path):
            raise ParserError("Confluence parser requires URL or page ID, not file path")

        content = self._fetch_page_content(str(source))
        return self._parse_stories_from_html(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from a Confluence page."""
        if isinstance(source, Path):
            raise ParserError("Confluence parser requires URL or page ID, not file path")

        page = self._fetch_page(str(source))
        if not page:
            return None

        title = page.get("title", "Untitled Epic")
        content = page.get("body", {}).get("storage", {}).get("value", "")

        # Extract epic key from title or properties
        epic_key = self._extract_epic_key(title, content)

        # Parse stories from page content
        stories = self._parse_stories_from_html(content)

        # Also fetch child pages as stories
        page_id = page.get("id")
        if page_id:
            child_stories = self._fetch_child_page_stories(page_id)
            stories.extend(child_stories)

        if not stories:
            return None

        return Epic(
            key=IssueKey(epic_key),
            title=self._clean_title(title),
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate Confluence connection and page access."""
        errors: list[str] = []

        if not self.base_url:
            errors.append("CONFLUENCE_URL not configured")
        if not self.username:
            errors.append("CONFLUENCE_USERNAME not configured")
        if not self.api_token:
            errors.append("CONFLUENCE_API_TOKEN not configured")

        if errors:
            return errors

        try:
            if isinstance(source, Path):
                errors.append("Confluence parser requires URL or page ID, not file path")
            else:
                page = self._fetch_page(str(source))
                if not page:
                    errors.append(f"Page not found: {source}")
        except Exception as e:
            errors.append(f"Failed to fetch page: {e}")

        return errors

    def _fetch_page(self, source: str) -> dict | None:
        """Fetch a Confluence page by ID or URL."""
        try:
            import requests
        except ImportError:
            self.logger.warning("requests library not available for Confluence API")
            return None

        page_id = self._extract_page_id(source)
        if not page_id:
            return None

        if page_id in self._page_cache:
            return self._page_cache[page_id]

        url = f"{self.base_url}/rest/api/content/{page_id}"
        params = {"expand": "body.storage,children.page"}

        try:
            response = requests.get(
                url,
                params=params,
                auth=(self.username, self.api_token),
                timeout=30,
            )
            response.raise_for_status()
            page = response.json()
            self._page_cache[page_id] = page
            return page
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch Confluence page: {e}")
            return None

    def _fetch_page_content(self, source: str) -> str:
        """Fetch page content as HTML."""
        page = self._fetch_page(source)
        if not page:
            return ""
        return page.get("body", {}).get("storage", {}).get("value", "")

    def _fetch_child_page_stories(self, parent_id: str) -> list[UserStory]:
        """Fetch stories from child pages."""
        stories = []

        try:
            import requests
        except ImportError:
            return stories

        url = f"{self.base_url}/rest/api/content/{parent_id}/child/page"
        params = {"expand": "body.storage"}

        try:
            response = requests.get(
                url,
                params=params,
                auth=(self.username, self.api_token),
                timeout=30,
            )
            response.raise_for_status()
            children = response.json().get("results", [])

            for child in children:
                title = child.get("title", "")
                content = child.get("body", {}).get("storage", {}).get("value", "")

                # Check if child page is a story
                story_match = re.match(rf"({self.STORY_ID_PATTERN}):\s*(.+)", title)
                if story_match:
                    story_id = story_match.group(1)
                    story_title = story_match.group(2)
                    story = self._parse_story_from_html(story_id, story_title, content)
                    if story:
                        stories.append(story)

        except Exception as e:
            self.logger.warning(f"Failed to fetch child pages: {e}")

        return stories

    def _extract_page_id(self, source: str) -> str | None:
        """Extract page ID from URL or direct ID."""
        # Direct numeric ID
        if source.isdigit():
            return source

        # URL format: .../pages/12345/...
        match = re.search(r"/pages/(\d+)", source)
        if match:
            return match.group(1)

        # URL format: pageId=12345
        match = re.search(r"pageId=(\d+)", source)
        if match:
            return match.group(1)

        return None

    def _extract_epic_key(self, title: str, content: str) -> str:
        """Extract epic key from title or content."""
        # From title: PROJ-123: Epic Title or PROJ-123 - Epic Title
        match = re.match(rf"({self.STORY_ID_PATTERN})[:\-–]\s*", title)
        if match:
            return match.group(1)

        # From properties table
        match = re.search(r"Epic\s*Key[^<]*?([A-Z]+[-_/]\d+)", content, re.IGNORECASE)
        if match:
            return match.group(1)

        return "EPIC-0"

    def _clean_title(self, title: str) -> str:
        """Remove epic key prefix from title."""
        return re.sub(rf"^{self.STORY_ID_PATTERN}[:\-–]\s*", "", title)

    def _parse_stories_from_html(self, html: str) -> list[UserStory]:
        """Parse stories from Confluence HTML content."""
        stories = []

        # Convert HTML to text for parsing
        text = self._html_to_text(html)

        # Find story patterns in text
        story_pattern = rf"({self.STORY_ID_PATTERN}):\s*([^\n]+)"
        for match in re.finditer(story_pattern, text):
            story_id = match.group(1)
            title = match.group(2).strip()

            # Get content after this match until next story or end
            start = match.end()
            next_match = re.search(story_pattern, text[start:])
            end = start + next_match.start() if next_match else len(text)
            story_content = text[start:end]

            story = self._parse_story_from_text(story_id, title, story_content)
            if story:
                stories.append(story)

        return stories

    def _parse_story_from_html(self, story_id: str, title: str, html: str) -> UserStory | None:
        """Parse a single story from HTML content."""
        text = self._html_to_text(html)
        return self._parse_story_from_text(story_id, title, text)

    def _parse_story_from_text(self, story_id: str, title: str, content: str) -> UserStory | None:
        """Parse a single story from text content."""
        story_points = self._extract_field(content, "Story Points", "0")
        priority = self._extract_field(content, "Priority", "Medium")
        status = self._extract_field(content, "Status", "Planned")

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

    def _html_to_text(self, html: str) -> str:
        """Convert Confluence HTML to plain text."""
        try:
            from html.parser import HTMLParser
        except ImportError:
            # Fallback: strip tags with regex
            text = re.sub(r"<[^>]+>", "", html)
            return re.sub(r"\s+", " ", text).strip()

        class TextExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.text_parts: list[str] = []
                self.in_table_cell = False

            def handle_starttag(self, tag: str, attrs: Any) -> None:
                if tag in ("td", "th"):
                    self.in_table_cell = True
                elif tag in ("br", "p", "div", "tr", "li"):
                    self.text_parts.append("\n")
                elif tag == "checkbox":
                    # Confluence checkbox
                    is_checked = any(a[0] == "checked" for a in attrs)
                    self.text_parts.append("[x] " if is_checked else "[ ] ")

            def handle_endtag(self, tag: str) -> None:
                if tag in ("td", "th"):
                    self.in_table_cell = False
                    self.text_parts.append(" | ")
                elif tag == "tr":
                    self.text_parts.append("\n")

            def handle_data(self, data: str) -> None:
                self.text_parts.append(data)

        extractor = TextExtractor()
        extractor.feed(html)
        return "".join(extractor.text_parts)

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """Extract field value from table or inline format."""
        # Table format: | Field | Value |
        pattern = rf"\|\s*{field_name}\s*\|\s*([^|\n]+)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Inline format: Field: Value
        pattern = rf"{field_name}\s*[:\-]\s*(.+?)(?:\n|$)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return default

    def _extract_description(self, content: str) -> Description | None:
        """Extract user story description."""
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
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
        # If no section found, search the entire content
        search_content = section if section else content

        for match in re.finditer(r"\[([ xX])\]\s*(.+)", search_content):
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

        pattern = r"([a-f0-9]{7,40})\s*[-–—]?\s*(.+)"
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
            rf"(blocks|blocked by|relates to|depends on|duplicates)[:\s]+({issue_key_pattern})"
        )
        for match in re.finditer(pattern, section, re.IGNORECASE):
            links.append((match.group(1).lower(), match.group(2)))

        return links

    def _extract_comments(self, content: str) -> list[Comment]:
        """Extract comments from section."""
        comments = []

        section = self._extract_section(content, "Comments")
        if not section:
            return comments

        # Parse comment blocks: @author (date): Comment
        pattern = r"@(\w+)\s*(?:\((\d{4}-\d{2}-\d{2})\))?[:\s]+(.+?)(?=@\w+|$)"
        for match in re.finditer(pattern, section, re.DOTALL):
            author = match.group(1)
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
        # Match various heading formats
        patterns = [
            rf"^#+\s*{re.escape(heading)}\s*$",  # Markdown-style
            rf"^{re.escape(heading)}\s*$",  # Plain heading
            rf"<h\d[^>]*>\s*{re.escape(heading)}\s*</h\d>",  # HTML heading
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                start = match.end()
                # Find next heading
                next_heading = re.search(
                    r"^#+\s+|^[A-Z][^:\n]+:\s*$|<h\d", content[start:], re.MULTILINE
                )
                end = start + next_heading.start() if next_heading else len(content)
                return content[start:end].strip()

        return None
