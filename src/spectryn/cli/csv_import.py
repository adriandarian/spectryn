"""
CSV Import - Import from Jira CSV, GitHub CSV, and other tracker exports.

Supports importing stories from CSV exports of various tools:
- Jira CSV export (via Issues > Export > CSV)
- GitHub Issues CSV (via third-party exporters)
- Generic CSV with standard columns
"""

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from spectryn.core.domain.entities import Epic, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)


logger = logging.getLogger(__name__)


@dataclass
class CsvImportOptions:
    """Options for CSV import."""

    # Format detection
    format: str = "auto"  # auto, jira, github, linear, generic

    # Column mappings (override auto-detection)
    id_column: str | None = None
    title_column: str | None = None
    description_column: str | None = None
    status_column: str | None = None
    priority_column: str | None = None
    story_points_column: str | None = None
    assignee_column: str | None = None
    labels_column: str | None = None
    epic_column: str | None = None

    # Import options
    skip_header: bool = True
    delimiter: str = ","
    encoding: str = "utf-8"

    # Story generation
    id_prefix: str = "STORY"
    starting_number: int = 1


@dataclass
class CsvImportResult:
    """Result of CSV import operation."""

    success: bool = True
    stories_imported: int = 0
    stories_skipped: int = 0
    epics_created: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Column name mappings for different CSV formats
JIRA_COLUMNS = {
    "id": ["Issue key", "Key", "Issue ID"],
    "title": ["Summary"],
    "description": ["Description"],
    "status": ["Status"],
    "priority": ["Priority"],
    "story_points": ["Story Points", "Custom field (Story Points)", "Story point estimate"],
    "assignee": ["Assignee"],
    "labels": ["Labels"],
    "epic": ["Epic Link", "Parent", "Epic Name"],
    "type": ["Issue Type", "Type"],
    "created": ["Created"],
    "updated": ["Updated"],
    "resolution": ["Resolution"],
    "sprint": ["Sprint"],
    "components": ["Components"],
}

GITHUB_COLUMNS = {
    "id": ["Number", "#", "Issue Number"],
    "title": ["Title", "Issue Title"],
    "description": ["Body", "Description"],
    "status": ["State", "Status"],
    "priority": ["Priority", "Labels"],  # GitHub uses labels for priority
    "story_points": ["Story Points", "Points", "Estimate"],
    "assignee": ["Assignees", "Assigned To"],
    "labels": ["Labels"],
    "milestone": ["Milestone"],
    "created": ["Created At", "Created"],
    "updated": ["Updated At", "Updated"],
    "closed": ["Closed At", "Closed"],
}

LINEAR_COLUMNS = {
    "id": ["Identifier", "ID"],
    "title": ["Title"],
    "description": ["Description"],
    "status": ["Status", "State"],
    "priority": ["Priority"],
    "story_points": ["Estimate", "Points"],
    "assignee": ["Assignee"],
    "labels": ["Labels"],
    "project": ["Project"],
    "cycle": ["Cycle"],
    "created": ["Created At"],
    "updated": ["Updated At"],
}

GENERIC_COLUMNS = {
    "id": ["id", "issue_id", "story_id", "key", "number", "#"],
    "title": ["title", "summary", "name", "subject"],
    "description": ["description", "body", "details", "content"],
    "status": ["status", "state", "stage"],
    "priority": ["priority", "prio", "p"],
    "story_points": ["story_points", "points", "sp", "estimate"],
    "assignee": ["assignee", "assigned_to", "owner"],
    "labels": ["labels", "tags"],
    "epic": ["epic", "parent", "epic_link"],
}


class CsvImporter:
    """Import stories from various CSV formats."""

    def __init__(self, options: CsvImportOptions | None = None):
        """
        Initialize the CSV importer.

        Args:
            options: Import options.
        """
        self.options = options or CsvImportOptions()
        self.logger = logging.getLogger(__name__)

    def detect_format(self, headers: list[str]) -> str:
        """
        Detect the CSV format based on column headers.

        Args:
            headers: List of column headers.

        Returns:
            Detected format: 'jira', 'github', 'linear', or 'generic'.
        """
        headers_lower = [h.lower().strip() for h in headers]

        # Check for Jira-specific columns
        jira_indicators = ["issue key", "issue type", "epic link", "sprint"]
        if any(ind in headers_lower for ind in jira_indicators):
            return "jira"

        # Check for GitHub-specific columns
        github_indicators = ["number", "state", "milestone", "assignees"]
        if any(ind in headers_lower for ind in github_indicators):
            return "github"

        # Check for Linear-specific columns
        linear_indicators = ["identifier", "cycle", "project"]
        if any(ind in headers_lower for ind in linear_indicators):
            return "linear"

        return "generic"

    def get_column_mappings(self, format_type: str) -> dict[str, list[str]]:
        """Get column mappings for a format type."""
        mappings = {
            "jira": JIRA_COLUMNS,
            "github": GITHUB_COLUMNS,
            "linear": LINEAR_COLUMNS,
            "generic": GENERIC_COLUMNS,
        }
        return mappings.get(format_type, GENERIC_COLUMNS)

    def find_column(
        self, headers: list[str], field_name: str, mappings: dict[str, list[str]]
    ) -> str | None:
        """
        Find the column name for a field.

        Args:
            headers: CSV headers.
            field_name: Field to find.
            mappings: Column name mappings.

        Returns:
            Matching column name or None.
        """
        # Check explicit option override
        override = getattr(self.options, f"{field_name}_column", None)
        if override and override in headers:
            return override

        # Check mappings
        possible_names = mappings.get(field_name, [])
        headers_lower = {h.lower().strip(): h for h in headers}

        for name in possible_names:
            if name.lower() in headers_lower:
                return headers_lower[name.lower()]

        return None

    def import_file(self, path: Path | str) -> tuple[list[UserStory], CsvImportResult]:
        """
        Import stories from a CSV file.

        Args:
            path: Path to CSV file.

        Returns:
            Tuple of (stories list, import result).
        """
        path = Path(path)
        result = CsvImportResult()

        if not path.exists():
            result.success = False
            result.errors.append(f"File not found: {path}")
            return [], result

        try:
            content = path.read_text(encoding=self.options.encoding)
            return self.import_content(content)
        except UnicodeDecodeError:
            # Try alternative encodings
            for enc in ["utf-8-sig", "latin-1", "cp1252"]:
                try:
                    content = path.read_text(encoding=enc)
                    return self.import_content(content)
                except UnicodeDecodeError:
                    continue

            result.success = False
            result.errors.append("Could not decode file with supported encodings")
            return [], result

    def import_content(self, content: str) -> tuple[list[UserStory], CsvImportResult]:
        """
        Import stories from CSV content.

        Args:
            content: CSV content string.

        Returns:
            Tuple of (stories list, import result).
        """
        result = CsvImportResult()
        stories = []

        try:
            # Parse CSV
            reader = csv.DictReader(
                io.StringIO(content),
                delimiter=self.options.delimiter,
            )

            headers = reader.fieldnames or []
            if not headers:
                result.success = False
                result.errors.append("No headers found in CSV")
                return [], result

            # Detect format
            format_type = self.options.format
            if format_type == "auto":
                format_type = self.detect_format(headers)
                self.logger.info(f"Detected CSV format: {format_type}")

            mappings = self.get_column_mappings(format_type)

            # Find columns
            id_col = self.find_column(headers, "id", mappings)
            title_col = self.find_column(headers, "title", mappings)
            desc_col = self.find_column(headers, "description", mappings)
            status_col = self.find_column(headers, "status", mappings)
            priority_col = self.find_column(headers, "priority", mappings)
            points_col = self.find_column(headers, "story_points", mappings)
            assignee_col = self.find_column(headers, "assignee", mappings)
            labels_col = self.find_column(headers, "labels", mappings)

            if not title_col:
                result.success = False
                result.errors.append("Could not find title column")
                return [], result

            # Parse rows
            story_num = self.options.starting_number
            for i, row in enumerate(reader):
                try:
                    story = self._parse_row(
                        row=row,
                        row_num=i + 2,  # Account for header
                        story_num=story_num,
                        id_col=id_col,
                        title_col=title_col,
                        desc_col=desc_col,
                        status_col=status_col,
                        priority_col=priority_col,
                        points_col=points_col,
                        assignee_col=assignee_col,
                        labels_col=labels_col,
                        format_type=format_type,
                    )

                    if story:
                        stories.append(story)
                        result.stories_imported += 1
                        story_num += 1
                    else:
                        result.stories_skipped += 1
                        result.warnings.append(f"Row {i + 2}: Skipped (no title)")

                except Exception as e:
                    result.warnings.append(f"Row {i + 2}: Error parsing - {e}")
                    result.stories_skipped += 1

        except csv.Error as e:
            result.success = False
            result.errors.append(f"CSV parsing error: {e}")
            return [], result

        result.success = len(stories) > 0 or not result.errors
        return stories, result

    def _parse_row(
        self,
        row: dict[str, str],
        row_num: int,
        story_num: int,
        id_col: str | None,
        title_col: str | None,
        desc_col: str | None,
        status_col: str | None,
        priority_col: str | None,
        points_col: str | None,
        assignee_col: str | None,
        labels_col: str | None,
        format_type: str,
    ) -> UserStory | None:
        """Parse a single CSV row into a UserStory."""
        # Get title (required)
        title = row.get(title_col, "").strip() if title_col else ""
        if not title:
            return None

        # Get or generate ID
        story_id = ""
        if id_col:
            raw_id = row.get(id_col, "").strip()
            if raw_id:
                # Normalize ID formats
                if format_type == "github" and raw_id.isdigit():
                    story_id = f"#{raw_id}"
                elif format_type == "jira" and "-" in raw_id:
                    story_id = raw_id
                else:
                    story_id = raw_id

        if not story_id:
            story_id = f"{self.options.id_prefix}-{story_num:03d}"

        # Parse description
        description = None
        if desc_col:
            desc_text = row.get(desc_col, "").strip()
            if desc_text:
                description = self._parse_description(desc_text)

        # Parse status
        status = Status.PLANNED
        if status_col:
            raw_status = row.get(status_col, "").strip()
            status = self._parse_status(raw_status, format_type)

        # Parse priority
        priority = Priority.MEDIUM
        if priority_col:
            raw_priority = row.get(priority_col, "").strip()
            priority = self._parse_priority(raw_priority, format_type)

        # Parse story points
        story_points = 0
        if points_col:
            raw_points = row.get(points_col, "").strip()
            story_points = self._parse_int(raw_points)

        # Parse assignee
        assignee = None
        if assignee_col:
            assignee = row.get(assignee_col, "").strip() or None

        # Parse labels
        labels = []
        if labels_col:
            raw_labels = row.get(labels_col, "").strip()
            if raw_labels:
                # Handle various label formats
                if "," in raw_labels:
                    labels = [l.strip() for l in raw_labels.split(",") if l.strip()]
                elif ";" in raw_labels:
                    labels = [l.strip() for l in raw_labels.split(";") if l.strip()]
                else:
                    labels = [raw_labels]

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=AcceptanceCriteria.from_list([], []),
            story_points=story_points,
            priority=priority,
            status=status,
            assignee=assignee,
            labels=labels,
            subtasks=[],
            commits=[],
            links=[],
            comments=[],
        )

    def _parse_description(self, text: str) -> Description | None:
        """Parse description text into Description object."""
        if not text:
            return None

        # Try to extract As a/I want/So that format
        pattern = r"[Aa]s a[n]?\s+(.+?),?\s+[Ii] want\s+(.+?),?\s+[Ss]o that\s+(.+)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        # Fall back to plain text
        return Description(role="", want=text, benefit="")

    def _parse_status(self, status: str, format_type: str) -> Status:
        """Parse status string to Status enum."""
        if not status:
            return Status.PLANNED

        status_lower = status.lower().strip()

        # Jira status mappings
        jira_done = {"done", "closed", "resolved", "complete", "completed"}
        jira_progress = {"in progress", "in development", "in review", "in testing"}

        # GitHub status mappings
        github_done = {"closed"}
        github_open = {"open"}

        if format_type == "github":
            if status_lower in github_done:
                return Status.DONE
            if status_lower in github_open:
                return Status.PLANNED
        elif status_lower in jira_done:
            return Status.DONE
        elif status_lower in jira_progress:
            return Status.IN_PROGRESS

        # Use generic parsing
        return Status.from_string(status)

    def _parse_priority(self, priority: str, format_type: str) -> Priority:
        """Parse priority string to Priority enum."""
        if not priority:
            return Priority.MEDIUM

        priority_lower = priority.lower().strip()

        # Handle numbered priorities (Jira: 1=Highest, 5=Lowest)
        if priority_lower.isdigit():
            num = int(priority_lower)
            if num <= 2:
                return Priority.HIGH
            if num >= 4:
                return Priority.LOW
            return Priority.MEDIUM

        # Handle labels as priority (GitHub)
        if format_type == "github":
            if any(p in priority_lower for p in ["critical", "urgent", "p0", "p1"]):
                return Priority.HIGH
            if any(p in priority_lower for p in ["low", "minor", "p3", "p4"]):
                return Priority.LOW

        return Priority.from_string(priority)

    def _parse_int(self, value: str) -> int:
        """Parse integer from string."""
        if not value:
            return 0

        # Remove non-numeric characters except minus
        cleaned = re.sub(r"[^\d.-]", "", value)

        try:
            return int(float(cleaned)) if cleaned else 0
        except ValueError:
            return 0

    def to_epic(
        self, stories: list[UserStory], epic_key: str = "CSV-IMPORT", title: str = "CSV Import"
    ) -> Epic:
        """
        Wrap imported stories in an Epic.

        Args:
            stories: List of imported stories.
            epic_key: Epic key/ID.
            title: Epic title.

        Returns:
            Epic containing the stories.
        """
        return Epic(
            key=IssueKey(epic_key),
            title=title,
            stories=stories,
        )

    def to_markdown(self, stories: list[UserStory], epic_title: str = "Imported Stories") -> str:
        """
        Convert imported stories to markdown format.

        Args:
            stories: List of stories.
            epic_title: Title for the markdown document.

        Returns:
            Markdown content.
        """
        lines = [
            f"# 📋 {epic_title}",
            "",
            f"> Imported from CSV on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## User Stories",
            "",
            f"**Total Stories:** {len(stories)} | "
            f"**Total Points:** {sum(s.story_points or 0 for s in stories)}",
            "",
        ]

        for story in stories:
            lines.append(f"### 🔧 {story.id}: {story.title}")
            lines.append("")

            # Metadata table
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| **Story Points** | {story.story_points or 0} |")
            lines.append(f"| **Priority** | {story.priority.display_name} |")
            lines.append(f"| **Status** | {story.status.display_name} |")
            if story.assignee:
                lines.append(f"| **Assignee** | {story.assignee} |")
            lines.append("")

            # Description
            if story.description:
                lines.append("#### Description")
                lines.append("")
                if story.description.role:
                    lines.append(f"**As a** {story.description.role}")
                    lines.append(f"**I want** {story.description.want}")
                    lines.append(f"**So that** {story.description.benefit}")
                else:
                    lines.append(story.description.want)
                lines.append("")

            # Labels
            if story.labels:
                lines.append(f"**Labels:** {', '.join(story.labels)}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)


def import_csv(
    path: str | Path,
    format_type: str = "auto",
    output: str | Path | None = None,
    id_prefix: str = "STORY",
) -> tuple[list[UserStory], CsvImportResult]:
    """
    Import stories from a CSV file.

    Args:
        path: Path to CSV file.
        format_type: CSV format (auto, jira, github, linear, generic).
        output: Optional output markdown file path.
        id_prefix: Prefix for generated story IDs.

    Returns:
        Tuple of (stories, import result).
    """
    options = CsvImportOptions(format=format_type, id_prefix=id_prefix)
    importer = CsvImporter(options)

    stories, result = importer.import_file(path)

    if output and stories:
        md_content = importer.to_markdown(stories)
        output_path = Path(output)
        output_path.write_text(md_content, encoding="utf-8")
        logger.info(f"Wrote {len(stories)} stories to {output_path}")

    return stories, result
