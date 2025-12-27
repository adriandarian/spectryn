"""
Google Docs Parser - Parse Google Docs into domain entities.

Implements the DocumentParserPort interface for Google Docs.

This parser connects to Google Docs via the Google Docs API to fetch
documents and convert them into Spectra domain entities.
"""

import contextlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from spectra.core.domain.entities import Comment, Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort, ParserError


class GoogleDocsParser(DocumentParserPort):
    """
    Parser for Google Docs documents.

    Fetches content from Google Docs API and parses structured documents
    into domain entities.

    Configuration:
    - GOOGLE_CREDENTIALS_FILE: Path to service account JSON file
    - Or provide credentials directly to constructor

    Expected document structure:

    ```
    Epic Title

    Epic Key: PROJ-123

    PROJ-001: Story Title

    Story Points: 5
    Priority: High
    Status: Planned

    Description

    As a user
    I want to do something
    So that I get benefit

    Acceptance Criteria

    ☐ First criterion
    ☑ Second criterion (done)

    Subtasks

    # | Task | SP | Status
    1 | Implement feature | 2 | Planned
    2 | Write tests | 1 | Done

    Technical Notes

    Implementation details here.
    ```
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    def __init__(
        self,
        credentials_file: str | Path | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the Google Docs parser.

        Args:
            credentials_file: Path to service account JSON file
            credentials: Service account credentials dict
        """
        import os

        self.logger = logging.getLogger("GoogleDocsParser")
        self.credentials_file = credentials_file or os.environ.get("GOOGLE_CREDENTIALS_FILE")
        self.credentials = credentials
        self._service: Any = None

    @property
    def name(self) -> str:
        return "GoogleDocs"

    @property
    def supported_extensions(self) -> list[str]:
        # Google Docs uses document IDs or URLs, not file extensions
        return []

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a Google Docs URL or document ID."""
        if isinstance(source, Path):
            return False

        if isinstance(source, str):
            # Check for Google Docs URL patterns
            if "docs.google.com/document" in source:
                return True
            # Check for document ID format (long alphanumeric string)
            if re.match(r"^[a-zA-Z0-9_-]{25,}$", source):
                return True

        return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from a Google Doc."""
        if isinstance(source, Path):
            raise ParserError("Google Docs parser requires URL or document ID, not file path")

        content = self._fetch_document_content(str(source))
        return self._parse_stories_from_text(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from a Google Doc."""
        if isinstance(source, Path):
            raise ParserError("Google Docs parser requires URL or document ID, not file path")

        document = self._fetch_document(str(source))
        if not document:
            return None

        title = document.get("title", "Untitled Epic")
        content = self._extract_text_from_document(document)

        # Extract epic key from content
        epic_key = self._extract_epic_key(content)

        # Parse stories from document content
        stories = self._parse_stories_from_text(content)

        if not stories:
            return None

        return Epic(
            key=IssueKey(epic_key),
            title=title,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate Google Docs connection and document access."""
        errors: list[str] = []

        if not self.credentials_file and not self.credentials:
            errors.append("Google credentials not configured")
            return errors

        try:
            if isinstance(source, Path):
                errors.append("Google Docs parser requires URL or document ID")
            else:
                document = self._fetch_document(str(source))
                if not document:
                    errors.append(f"Document not found: {source}")
        except Exception as e:
            errors.append(f"Failed to fetch document: {e}")

        return errors

    def _get_service(self) -> Any:
        """Get or create Google Docs API service."""
        if self._service:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            self.logger.warning("google-api-python-client not available for Google Docs API")
            return None

        try:
            if self.credentials:
                creds = service_account.Credentials.from_service_account_info(
                    self.credentials,
                    scopes=["https://www.googleapis.com/auth/documents.readonly"],
                )
            elif self.credentials_file:
                creds = service_account.Credentials.from_service_account_file(
                    str(self.credentials_file),
                    scopes=["https://www.googleapis.com/auth/documents.readonly"],
                )
            else:
                return None

            self._service = build("docs", "v1", credentials=creds)
            return self._service
        except Exception as e:
            self.logger.error(f"Failed to create Google Docs service: {e}")
            return None

    def _fetch_document(self, source: str) -> dict | None:
        """Fetch a Google Doc by ID or URL."""
        service = self._get_service()
        if not service:
            return None

        doc_id = self._extract_document_id(source)
        if not doc_id:
            return None

        try:
            return service.documents().get(documentId=doc_id).execute()
        except Exception as e:
            self.logger.error(f"Failed to fetch Google Doc: {e}")
            return None

    def _fetch_document_content(self, source: str) -> str:
        """Fetch document content as plain text."""
        document = self._fetch_document(source)
        if not document:
            return ""
        return self._extract_text_from_document(document)

    def _extract_document_id(self, source: str) -> str | None:
        """Extract document ID from URL or direct ID."""
        # Direct ID format
        if re.match(r"^[a-zA-Z0-9_-]{25,}$", source):
            return source

        # URL format: /document/d/{docId}/
        match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", source)
        if match:
            return match.group(1)

        return None

    def _extract_text_from_document(self, document: dict) -> str:
        """Extract plain text from Google Docs document structure."""
        text_parts: list[str] = []

        body = document.get("body", {})
        content = body.get("content", [])

        for element in content:
            if "paragraph" in element:
                paragraph = element["paragraph"]
                para_text = self._extract_paragraph_text(paragraph)
                text_parts.append(para_text)
            elif "table" in element:
                table = element["table"]
                table_text = self._extract_table_text(table)
                text_parts.append(table_text)

        return "\n".join(text_parts)

    def _extract_paragraph_text(self, paragraph: dict) -> str:
        """Extract text from a paragraph element."""
        text_parts: list[str] = []

        elements = paragraph.get("elements", [])
        for element in elements:
            if "textRun" in element:
                text = element["textRun"].get("content", "")
                text_parts.append(text)

        return "".join(text_parts).rstrip("\n")

    def _extract_table_text(self, table: dict) -> str:
        """Extract text from a table element."""
        rows: list[str] = []

        table_rows = table.get("tableRows", [])
        for table_row in table_rows:
            cells: list[str] = []
            table_cells = table_row.get("tableCells", [])

            for cell in table_cells:
                cell_content = cell.get("content", [])
                cell_text_parts: list[str] = []

                for element in cell_content:
                    if "paragraph" in element:
                        para_text = self._extract_paragraph_text(element["paragraph"])
                        cell_text_parts.append(para_text)

                cells.append(" ".join(cell_text_parts).strip())

            rows.append("| " + " | ".join(cells) + " |")

        return "\n".join(rows)

    def _extract_epic_key(self, content: str) -> str:
        """Extract epic key from content."""
        match = re.search(
            rf"Epic\s*Key\s*[:\-]\s*({self.STORY_ID_PATTERN})", content, re.IGNORECASE
        )
        if match:
            return match.group(1)
        return "EPIC-0"

    def _parse_stories_from_text(self, content: str) -> list[UserStory]:
        """Parse stories from document text."""
        stories = []

        # Allow optional leading whitespace before story ID
        story_pattern = rf"^\s*({self.STORY_ID_PATTERN}):\s*([^\n]+)"
        matches = list(re.finditer(story_pattern, content, re.MULTILINE))

        for i, match in enumerate(matches):
            story_id = match.group(1)
            title = match.group(2).strip()

            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            story_content = content[start:end]

            story = self._parse_story(story_id, title, story_content)
            if story:
                stories.append(story)

        return stories

    def _parse_story(self, story_id: str, title: str, content: str) -> UserStory | None:
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

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """Extract field value from content."""
        # Table format
        pattern = rf"\|\s*{field_name}\s*\|\s*([^|\n]+)"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Inline format
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

        # Google Docs checkbox characters
        for match in re.finditer(r"[☐☑✓✗]\s*(.+)", search_content):
            checkbox = match.group(0)[0]
            is_checked = checkbox in ("☑", "✓")
            text = match.group(1).strip()
            items.append(text)
            checked.append(is_checked)

        # Also try standard format
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
        pattern = rf"^{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()
        # Find next heading (capitalized line)
        next_heading = re.search(r"^[A-Z][a-zA-Z\s]+$", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
