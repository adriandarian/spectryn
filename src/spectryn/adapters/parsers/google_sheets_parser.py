"""
Google Sheets Parser - Parse Google Sheets into domain entities.

Implements the DocumentParserPort interface for Google Sheets.

This parser connects to Google Sheets via the Sheets API to fetch
spreadsheet data and convert it into Spectra domain entities.
"""

import logging
import re
from pathlib import Path
from typing import Any

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort, ParserError


class GoogleSheetsParser(DocumentParserPort):
    """
    Parser for Google Sheets spreadsheets.

    Fetches data from Google Sheets API and parses structured sheets
    into domain entities.

    Configuration:
    - GOOGLE_CREDENTIALS_FILE: Path to service account JSON file
    - Or provide credentials directly to constructor

    Expected sheet structure:

    Sheet: Stories
    | Story ID | Title | Story Points | Priority | Status | As a | I want | So that |
    |----------|-------|--------------|----------|--------|------|--------|---------|
    | PROJ-001 | Title | 5            | High     | Planned| user | feature| benefit |

    Sheet: Epic (optional)
    | Property | Value |
    |----------|-------|
    | Epic Key | PROJ-123 |
    | Title    | Epic Title |

    Sheet: Acceptance Criteria (optional)
    | Story ID | Criterion | Done |
    |----------|-----------|------|
    | PROJ-001 | First AC  | No   |
    | PROJ-001 | Second AC | Yes  |

    Sheet: Subtasks (optional)
    | Story ID | # | Task | SP | Status |
    |----------|---|------|----|--------|
    | PROJ-001 | 1 | Task | 2  | Planned|
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    # Column name mappings (case-insensitive)
    COLUMN_MAPPINGS = {
        "story_id": ["story id", "id", "story", "key", "issue"],
        "title": ["title", "name", "summary", "description"],
        "story_points": ["story points", "points", "sp", "estimate"],
        "priority": ["priority", "pri", "importance"],
        "status": ["status", "state", "stage"],
        "as_a": ["as a", "role", "persona", "user"],
        "i_want": ["i want", "want", "feature", "goal"],
        "so_that": ["so that", "benefit", "value", "reason"],
    }

    def __init__(
        self,
        credentials_file: str | Path | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the Google Sheets parser.

        Args:
            credentials_file: Path to service account JSON file
            credentials: Service account credentials dict
        """
        import os

        self.logger = logging.getLogger("GoogleSheetsParser")
        self.credentials_file = credentials_file or os.environ.get("GOOGLE_CREDENTIALS_FILE")
        self.credentials = credentials
        self._service: Any = None

    @property
    def name(self) -> str:
        return "GoogleSheets"

    @property
    def supported_extensions(self) -> list[str]:
        # Google Sheets uses spreadsheet IDs or URLs
        return []

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a Google Sheets URL or spreadsheet ID."""
        if isinstance(source, Path):
            return False

        if isinstance(source, str):
            # Check for Google Sheets URL patterns
            if "docs.google.com/spreadsheets" in source:
                return True
            # Check for spreadsheet ID format
            if re.match(r"^[a-zA-Z0-9_-]{25,}$", source):
                return True

        return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from a Google Sheet."""
        if isinstance(source, Path):
            raise ParserError("Google Sheets parser requires URL or ID, not file path")

        spreadsheet_id = self._extract_spreadsheet_id(str(source))
        if not spreadsheet_id:
            return []

        # Read stories sheet
        stories_data = self._fetch_sheet_data(spreadsheet_id, "Stories")
        if not stories_data:
            # Try alternate sheet names
            for name in ["User Stories", "Backlog", "Issues", "Sheet1"]:
                stories_data = self._fetch_sheet_data(spreadsheet_id, name)
                if stories_data:
                    break

        if not stories_data:
            return []

        # Parse stories from rows
        stories = self._parse_stories_from_rows(stories_data)

        # Enrich with acceptance criteria if available
        ac_data = self._fetch_sheet_data(spreadsheet_id, "Acceptance Criteria")
        if ac_data:
            self._enrich_stories_with_ac(stories, ac_data)

        # Enrich with subtasks if available
        subtasks_data = self._fetch_sheet_data(spreadsheet_id, "Subtasks")
        if subtasks_data:
            self._enrich_stories_with_subtasks(stories, subtasks_data)

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from a Google Sheet."""
        if isinstance(source, Path):
            raise ParserError("Google Sheets parser requires URL or ID")

        spreadsheet_id = self._extract_spreadsheet_id(str(source))
        if not spreadsheet_id:
            return None

        # Get spreadsheet metadata for title
        metadata = self._fetch_spreadsheet_metadata(spreadsheet_id)
        epic_title = metadata.get("title", "Untitled Epic") if metadata else "Untitled"

        # Try to get epic info from Epic sheet
        epic_key = "EPIC-0"
        epic_data = self._fetch_sheet_data(spreadsheet_id, "Epic")
        if epic_data:
            epic_info = self._parse_key_value_sheet(epic_data)
            epic_key = epic_info.get("epic key", epic_info.get("key", "EPIC-0"))
            epic_title = epic_info.get("title", epic_title)

        stories = self.parse_stories(source)

        if not stories:
            return None

        return Epic(key=IssueKey(epic_key), title=epic_title, stories=stories)

    def validate(self, source: str | Path) -> list[str]:
        """Validate Google Sheets connection and spreadsheet access."""
        errors: list[str] = []

        if not self.credentials_file and not self.credentials:
            errors.append("Google credentials not configured")
            return errors

        try:
            if isinstance(source, Path):
                errors.append("Google Sheets parser requires URL or spreadsheet ID")
            else:
                spreadsheet_id = self._extract_spreadsheet_id(str(source))
                if not spreadsheet_id:
                    errors.append("Invalid spreadsheet URL or ID")
                else:
                    metadata = self._fetch_spreadsheet_metadata(spreadsheet_id)
                    if not metadata:
                        errors.append(f"Spreadsheet not found: {source}")
        except Exception as e:
            errors.append(f"Failed to access spreadsheet: {e}")

        return errors

    def _get_service(self) -> Any:
        """Get or create Google Sheets API service."""
        if self._service:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            self.logger.warning("google-api-python-client not available for Sheets API")
            return None

        try:
            if self.credentials:
                creds = service_account.Credentials.from_service_account_info(
                    self.credentials,
                    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
                )
            elif self.credentials_file:
                creds = service_account.Credentials.from_service_account_file(
                    str(self.credentials_file),
                    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
                )
            else:
                return None

            self._service = build("sheets", "v4", credentials=creds)
            return self._service
        except Exception as e:
            self.logger.error(f"Failed to create Sheets service: {e}")
            return None

    def _extract_spreadsheet_id(self, source: str) -> str | None:
        """Extract spreadsheet ID from URL or direct ID."""
        if re.match(r"^[a-zA-Z0-9_-]{25,}$", source):
            return source

        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", source)
        if match:
            return match.group(1)

        return None

    def _fetch_spreadsheet_metadata(self, spreadsheet_id: str) -> dict | None:
        """Fetch spreadsheet metadata."""
        service = self._get_service()
        if not service:
            return None

        try:
            result = (
                service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id, fields="properties.title")
                .execute()
            )
            return {"title": result.get("properties", {}).get("title", "")}
        except Exception as e:
            self.logger.error(f"Failed to fetch spreadsheet metadata: {e}")
            return None

    def _fetch_sheet_data(self, spreadsheet_id: str, sheet_name: str) -> list[list[str]] | None:
        """Fetch data from a specific sheet."""
        service = self._get_service()
        if not service:
            return None

        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=sheet_name)
                .execute()
            )
            return result.get("values", [])
        except Exception:
            return None

    def _find_column_index(self, headers: list[str], column_type: str) -> int:
        """Find column index by matching against known names."""
        mappings = self.COLUMN_MAPPINGS.get(column_type, [column_type])
        headers_lower = [h.lower().strip() for h in headers]

        for mapping in mappings:
            if mapping.lower() in headers_lower:
                return headers_lower.index(mapping.lower())
        return -1

    def _parse_stories_from_rows(self, data: list[list[str]]) -> list[UserStory]:
        """Parse stories from spreadsheet rows."""
        if not data or len(data) < 2:
            return []

        headers = data[0]
        stories = []

        # Find column indices
        cols = {
            col_type: self._find_column_index(headers, col_type)
            for col_type in self.COLUMN_MAPPINGS
        }

        for row in data[1:]:
            if not row:
                continue

            def get_cell(col_type: str) -> str:
                idx = cols.get(col_type, -1)
                if idx >= 0 and idx < len(row):
                    return str(row[idx]).strip()
                return ""

            story_id = get_cell("story_id")
            if not story_id or not re.match(self.STORY_ID_PATTERN, story_id):
                continue

            title = get_cell("title")
            story_points = get_cell("story_points")
            priority = get_cell("priority")
            status = get_cell("status")
            as_a = get_cell("as_a")
            i_want = get_cell("i_want")
            so_that = get_cell("so_that")

            description = None
            if as_a and i_want and so_that:
                description = Description(role=as_a, want=i_want, benefit=so_that)

            stories.append(
                UserStory(
                    id=StoryId(story_id),
                    title=title,
                    description=description,
                    story_points=int(story_points) if story_points.isdigit() else 0,
                    priority=Priority.from_string(priority) if priority else Priority.MEDIUM,
                    status=Status.from_string(status) if status else Status.PLANNED,
                )
            )

        return stories

    def _parse_key_value_sheet(self, data: list[list[str]]) -> dict[str, str]:
        """Parse a key-value style sheet."""
        result = {}
        for row in data:
            if len(row) >= 2:
                key = str(row[0]).lower().strip()
                value = str(row[1]).strip()
                result[key] = value
        return result

    def _enrich_stories_with_ac(self, stories: list[UserStory], ac_data: list[list[str]]) -> None:
        """Add acceptance criteria to stories from AC sheet."""
        if not ac_data or len(ac_data) < 2:
            return

        headers = ac_data[0]
        story_id_idx = self._find_column_index(headers, "story_id")
        criterion_idx = next(
            (
                i
                for i, h in enumerate(headers)
                if h.lower() in ("criterion", "criteria", "description", "text")
            ),
            1,
        )
        done_idx = next(
            (i for i, h in enumerate(headers) if h.lower() in ("done", "complete", "checked")),
            -1,
        )

        # Group by story ID
        ac_by_story: dict[str, list[tuple[str, bool]]] = {}
        for row in ac_data[1:]:
            if len(row) <= max(story_id_idx, criterion_idx):
                continue
            sid = row[story_id_idx] if story_id_idx >= 0 else ""
            criterion = row[criterion_idx] if criterion_idx < len(row) else ""
            is_done = (
                row[done_idx].lower() in ("yes", "true", "x", "1", "done")
                if done_idx >= 0 and done_idx < len(row)
                else False
            )
            if sid and criterion:
                if sid not in ac_by_story:
                    ac_by_story[sid] = []
                ac_by_story[sid].append((criterion, is_done))

        # Apply to stories
        for story in stories:
            sid = str(story.id)
            if sid in ac_by_story:
                items = [c[0] for c in ac_by_story[sid]]
                checked = [c[1] for c in ac_by_story[sid]]
                story.acceptance_criteria = AcceptanceCriteria.from_list(items, checked)

    def _enrich_stories_with_subtasks(
        self, stories: list[UserStory], subtasks_data: list[list[str]]
    ) -> None:
        """Add subtasks to stories from Subtasks sheet."""
        if not subtasks_data or len(subtasks_data) < 2:
            return

        headers = subtasks_data[0]
        story_id_idx = self._find_column_index(headers, "story_id")
        num_idx = next(
            (i for i, h in enumerate(headers) if h.lower() in ("#", "number", "num")), -1
        )
        task_idx = next(
            (i for i, h in enumerate(headers) if h.lower() in ("task", "name", "title")), 1
        )
        sp_idx = next(
            (i for i, h in enumerate(headers) if h.lower() in ("sp", "points", "story points")),
            -1,
        )
        status_idx = next(
            (i for i, h in enumerate(headers) if h.lower() in ("status", "state")), -1
        )

        # Group by story ID
        subtasks_by_story: dict[str, list[Subtask]] = {}
        for row in subtasks_data[1:]:
            if len(row) <= max(story_id_idx, task_idx):
                continue

            sid = row[story_id_idx] if story_id_idx >= 0 else ""
            if not sid:
                continue

            num = (
                int(row[num_idx])
                if num_idx >= 0 and num_idx < len(row) and row[num_idx].isdigit()
                else 0
            )
            task = row[task_idx] if task_idx < len(row) else ""
            sp = (
                int(row[sp_idx])
                if sp_idx >= 0 and sp_idx < len(row) and row[sp_idx].isdigit()
                else 0
            )
            status = row[status_idx] if status_idx >= 0 and status_idx < len(row) else "Planned"

            if task:
                if sid not in subtasks_by_story:
                    subtasks_by_story[sid] = []
                subtasks_by_story[sid].append(
                    Subtask(
                        number=num or len(subtasks_by_story[sid]) + 1,
                        name=task,
                        description="",
                        story_points=sp,
                        status=Status.from_string(status),
                    )
                )

        # Apply to stories
        for story in stories:
            sid = str(story.id)
            if sid in subtasks_by_story:
                story.subtasks = subtasks_by_story[sid]
