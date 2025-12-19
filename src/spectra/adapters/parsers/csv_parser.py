"""
CSV Parser - Parse CSV files into domain entities.

Implements the DocumentParserPort interface for CSV-based specifications.

CSV (Comma-Separated Values) is a universal spreadsheet format that's
easy to export from tools like Excel, Google Sheets, and project management software.
"""

import csv
import io
import logging
from pathlib import Path

from spectra.core.domain.entities import Comment, Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort, ParserError


class CsvParser(DocumentParserPort):
    """
    Parser for CSV story specification files.

    Supports spreadsheet-style CSV format where each row is a story
    and columns represent fields.

    Expected CSV format:

    ```csv
    id,title,description,story_points,priority,status,acceptance_criteria,subtasks,technical_notes,links
    US-001,"Story Title","As a user, I want feature, so that benefit",5,high,planned,"AC1;AC2;AC3","Task1;Task2","Tech notes","blocks:PROJ-123"
    US-002,"Another Story","Simple description",3,medium,in_progress,"AC1","","","depends_on:OTHER-456"
    ```

    Column mappings (case-insensitive, flexible):
    - id, story_id, story id → Story ID
    - title, name, story → Title
    - description, desc, user_story → Description
    - story_points, points, sp → Story Points
    - priority → Priority
    - status → Status
    - acceptance_criteria, ac, criteria → Acceptance Criteria (semicolon-separated)
    - subtasks, tasks → Subtasks (semicolon-separated)
    - technical_notes, notes, tech_notes → Technical Notes
    - links, related → Links (semicolon-separated, format: "type:target")
    - comments → Comments (semicolon-separated)
    """

    # Column name mappings
    COLUMN_MAPPINGS = {
        "id": ["id", "story_id", "story id", "story-id", "issue_id"],
        "title": ["title", "name", "story", "summary", "story_title"],
        "description": ["description", "desc", "user_story", "user story", "as_a"],
        "story_points": ["story_points", "story points", "points", "sp", "estimate"],
        "priority": ["priority", "prio", "p"],
        "status": ["status", "state", "stage"],
        "acceptance_criteria": ["acceptance_criteria", "acceptance criteria", "ac", "criteria"],
        "subtasks": ["subtasks", "tasks", "sub_tasks", "sub-tasks"],
        "technical_notes": [
            "technical_notes",
            "technical notes",
            "notes",
            "tech_notes",
            "tech notes",
        ],
        "links": ["links", "related", "dependencies", "relations"],
        "comments": ["comments", "notes", "discussion"],
        "assignee": ["assignee", "assigned", "owner", "assigned_to"],
        "labels": ["labels", "tags"],
    }

    def __init__(self, delimiter: str = ",") -> None:
        """
        Initialize the CSV parser.

        Args:
            delimiter: CSV field delimiter (default: comma)
        """
        self.logger = logging.getLogger("CsvParser")
        self.delimiter = delimiter

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "CSV"

    @property
    def supported_extensions(self) -> list[str]:
        return [".csv", ".tsv"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid CSV file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Try to parse as CSV and check for expected headers
        try:
            reader = csv.reader(io.StringIO(source))
            headers = next(reader, [])
            if not headers:
                return False

            # Check if any expected column exists
            headers_lower = [h.lower().strip() for h in headers]
            expected_columns = ["id", "title", "name", "story", "story_id"]
            return any(col in headers_lower for col in expected_columns)
        except Exception:
            return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from CSV source."""
        rows = self._load_csv(source)

        if not rows:
            return []

        stories = []
        for i, row in enumerate(rows):
            try:
                story = self._parse_row(row, i)
                if story:
                    stories.append(story)
            except Exception as e:
                story_id = row.get("id", f"row-{i}")
                self.logger.warning(f"Failed to parse story {story_id}: {e}")

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from CSV source."""
        stories = self.parse_stories(source)

        if not stories:
            return None

        # Try to get epic title from filename
        epic_title = "CSV Import"
        if isinstance(source, Path):
            epic_title = source.stem

        return Epic(
            key=IssueKey("EPIC-0"),
            title=epic_title,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate CSV source without full parsing."""
        errors: list[str] = []

        try:
            rows = self._load_csv(source)
        except ParserError as e:
            return [str(e)]

        if not rows:
            errors.append("No data rows found in CSV")
            return errors

        for i, row in enumerate(rows):
            if not row.get("id") and not row.get("title"):
                errors.append(f"Row {i + 1}: missing both 'id' and 'title'")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _load_csv(self, source: str | Path) -> list[dict[str, str]]:
        """Load CSV content from file or string."""
        try:
            if isinstance(source, Path):
                content = source.read_text(encoding="utf-8")
                # Use tab delimiter for TSV files
                if source.suffix.lower() == ".tsv":
                    self.delimiter = "\t"
            elif isinstance(source, str):
                content = source
                if "\n" not in source and len(source) < 4096:
                    try:
                        path = Path(source)
                        if path.exists() and path.suffix.lower() in self.supported_extensions:
                            content = path.read_text(encoding="utf-8")
                            if path.suffix.lower() == ".tsv":
                                self.delimiter = "\t"
                    except OSError:
                        pass
            else:
                content = source

            reader = csv.DictReader(io.StringIO(content), delimiter=self.delimiter)

            # Normalize headers
            rows = []
            for row in reader:
                normalized = self._normalize_row(row)
                rows.append(normalized)

            return rows

        except Exception as e:
            raise ParserError(f"Invalid CSV: {e}")

    def _normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        """Normalize column names to standard field names."""
        normalized: dict[str, str] = {}

        for standard_name, aliases in self.COLUMN_MAPPINGS.items():
            for key, value in row.items():
                if key.lower().strip() in aliases:
                    normalized[standard_name] = value.strip() if value else ""
                    break

        # Keep any unmapped columns
        for key, value in row.items():
            key_lower = key.lower().strip()
            is_mapped = any(key_lower in aliases for aliases in self.COLUMN_MAPPINGS.values())
            if not is_mapped and value:
                normalized[key_lower] = value.strip()

        return normalized

    def _parse_row(self, row: dict[str, str], index: int) -> UserStory | None:
        """Parse a single CSV row into a UserStory."""
        story_id = row.get("id", f"US-{index + 1:03d}")
        if not story_id.upper().startswith(("US-", "STORY-")):
            story_id = f"US-{story_id}"

        title = row.get("title", "").strip()
        if not title:
            return None

        # Parse description
        description = self._parse_description(row.get("description", ""))

        # Parse story points
        sp_str = row.get("story_points", "0")
        story_points = self._parse_int(sp_str)

        # Parse priority and status
        priority = Priority.from_string(row.get("priority", "medium"))
        status = Status.from_string(row.get("status", "planned"))

        # Parse semicolon-separated fields
        acceptance = self._parse_acceptance_criteria(row.get("acceptance_criteria", ""))
        subtasks = self._parse_subtasks(row.get("subtasks", ""))
        links = self._parse_links(row.get("links", ""))
        comments = self._parse_comments(row.get("comments", ""))

        tech_notes = row.get("technical_notes", "")
        assignee = row.get("assignee") or None
        labels = [l.strip() for l in row.get("labels", "").split(";") if l.strip()]

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=tech_notes,
            story_points=story_points,
            priority=priority,
            status=status,
            subtasks=subtasks,
            commits=[],
            links=links,
            comments=comments,
            assignee=assignee,
            labels=labels,
        )

    def _parse_description(self, text: str) -> Description | None:
        """Parse description from text."""
        if not text:
            return None

        import re

        pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        return Description(role="", want=text, benefit="")

    def _parse_acceptance_criteria(self, text: str) -> AcceptanceCriteria:
        """Parse semicolon-separated acceptance criteria."""
        if not text:
            return AcceptanceCriteria.from_list([], [])

        items = [item.strip() for item in text.split(";") if item.strip()]
        checked = [False] * len(items)

        return AcceptanceCriteria.from_list(items, checked)

    def _parse_subtasks(self, text: str) -> list[Subtask]:
        """Parse semicolon-separated subtasks."""
        if not text:
            return []

        subtasks = []
        items = [item.strip() for item in text.split(";") if item.strip()]

        for i, item in enumerate(items):
            subtasks.append(
                Subtask(
                    number=i + 1,
                    name=item,
                    description="",
                    story_points=1,
                    status=Status.PLANNED,
                )
            )

        return subtasks

    def _parse_links(self, text: str) -> list[tuple[str, str]]:
        """Parse semicolon-separated links in format 'type:target'."""
        if not text:
            return []

        links = []
        items = [item.strip() for item in text.split(";") if item.strip()]

        for item in items:
            if ":" in item:
                parts = item.split(":", 1)
                link_type = parts[0].strip().lower().replace("_", " ")
                target = parts[1].strip()
                if target:
                    links.append((link_type, target))

        return links

    def _parse_comments(self, text: str) -> list[Comment]:
        """Parse semicolon-separated comments."""
        if not text:
            return []

        comments = []
        items = [item.strip() for item in text.split(";") if item.strip()]

        for item in items:
            comments.append(
                Comment(
                    body=item,
                    author=None,
                    created_at=None,
                    comment_type="text",
                )
            )

        return comments

    def _parse_int(self, value: str) -> int:
        """Parse integer from string."""
        if not value:
            return 0

        import re

        cleaned = re.sub(r"[^\d-]", "", str(value))

        try:
            return int(cleaned) if cleaned else 0
        except ValueError:
            return 0
