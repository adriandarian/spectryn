"""
Notion Parser - Parse Notion exports into domain entities.

Implements the DocumentParserPort interface for Notion export files.

Notion exports markdown files with specific formatting:
- Properties as key-value pairs at the top
- Callout blocks with emoji prefixes
- Toggle blocks
- Database tables
- Nested page structure
"""

import contextlib
import csv
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


class NotionParser(DocumentParserPort):
    """
    Parser for Notion export files.

    Handles both single-page exports and database exports.

    Notion exports have specific characteristics:
    - Properties block at the top (key: value format)
    - Callout blocks: > emoji text
    - Toggle blocks: <details><summary>
    - Tables for databases/subtasks
    - Nested structure via folders

    Expected Notion page structure for stories:

    ```
    # Story Title

    Status: In Progress
    Priority: High
    Story Points: 5
    Assignee: @user

    ## Description

    > 👤 As a user, I want to do something so that I get benefit

    ## Acceptance Criteria

    - [ ] First criterion
    - [x] Completed criterion

    ## Subtasks

    | Task | Description | Points | Status |
    |------|-------------|--------|--------|
    | Task 1 | Do thing | 2 | Done |

    ## Technical Notes

    Implementation details here.

    ## Links

    | Link Type | Target |
    |-----------|--------|
    | blocks | PROJ-123 |
    | depends on | OTHER-456 |

    ## Comments

    > **@username** (2025-01-15):
    > This is a comment about the story.

    > Another comment without author metadata.
    ```
    """

    # Story ID patterns (flexible)
    STORY_ID_PATTERNS = [
        r"(?:US|STORY|S)-?\d{3,}",  # US-001, STORY-123, S001
        r"#\d+",  # #123
        r"\[([A-Z]+-\d+)\]",  # [PROJ-123]
    ]

    # Property patterns
    PROPERTY_PATTERN = r"^([A-Za-z][A-Za-z\s]*?):\s*(.+)$"

    def __init__(self) -> None:
        """Initialize the Notion parser."""
        self.logger = logging.getLogger("NotionParser")

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Notion"

    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown", ".csv"]

    def can_parse(self, source: str | Path) -> bool:
        """
        Check if source looks like a Notion export.

        Notion exports have specific patterns:
        - Properties at top of file
        - Callout blocks with emojis
        - Specific heading structure
        """
        if isinstance(source, Path):
            # Check if it's a Notion export folder structure
            if source.is_dir():
                # Notion exports have UUID suffixes in folder names
                return bool(re.search(r"[a-f0-9]{32}", str(source)))

            if source.suffix.lower() == ".csv":
                return self._is_notion_database_csv(source)

            if source.suffix.lower() not in self.supported_extensions:
                return False

            content = source.read_text(encoding="utf-8")
        else:
            content = source

        return self._looks_like_notion(content)

    def _looks_like_notion(self, content: str) -> bool:
        """Check if content has Notion-like characteristics."""
        # Check for property block at top
        lines = content.strip().split("\n")
        property_count = 0

        for line in lines[:20]:  # Check first 20 lines
            if re.match(self.PROPERTY_PATTERN, line.strip()):
                property_count += 1
            if line.startswith("# "):
                break

        if property_count >= 2:
            return True

        # Check for Notion callout pattern
        if re.search(r"^>\s*[🔥📌💡⚠️❗ℹ️✅❌👤🎯📋💻🔧]", content, re.MULTILINE):
            return True

        # Check for Notion-style toggle
        return bool("<details>" in content and "<summary>" in content)

    def _is_notion_database_csv(self, path: Path) -> bool:
        """Check if CSV looks like a Notion database export."""
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                # Notion databases typically have Name/Title as first column
                if headers and headers[0].lower() in ["name", "title", "task", "story"]:
                    return True
        except Exception:
            pass
        return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from Notion export."""
        if isinstance(source, Path):
            if source.suffix.lower() == ".csv":
                return self._parse_database_csv(source)
            if source.is_dir():
                return self._parse_notion_folder(source)
            content = source.read_text(encoding="utf-8")
        elif isinstance(source, str):
            content = source
            # Only try to treat as file path if it's short enough and doesn't contain newlines
            if "\n" not in source and len(source) < 4096:
                try:
                    path = Path(source)
                    if path.exists():
                        if path.suffix.lower() == ".csv":
                            return self._parse_database_csv(path)
                        if path.is_dir():
                            return self._parse_notion_folder(path)
                        content = path.read_text(encoding="utf-8")
                except OSError:
                    pass
        else:
            content = source

        return self._parse_notion_page(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from Notion export."""
        stories = self.parse_stories(source)

        if not stories:
            return None

        # Try to get epic title from content
        epic_title = "Notion Import"

        if isinstance(source, Path):
            # Use folder/file name as epic title
            epic_title = source.stem
            # Remove Notion UUID suffix if present
            epic_title = re.sub(r"\s+[a-f0-9]{32}$", "", epic_title)
        elif isinstance(source, str):
            # Check if it's a file path or content
            is_file_path = False
            if "\n" not in source and len(source) < 4096:
                with contextlib.suppress(OSError):
                    is_file_path = Path(source).exists()
            if not is_file_path:
                # Extract first heading from content
                match = re.search(r"^#\s+(.+)$", source, re.MULTILINE)
                if match:
                    epic_title = match.group(1).strip()

        return Epic(
            key=IssueKey("EPIC-0"),
            title=epic_title,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate Notion export source."""
        errors: list[str] = []

        try:
            if isinstance(source, Path):
                if source.is_dir():
                    # Validate folder has markdown files
                    md_files = list(source.rglob("*.md"))
                    if not md_files:
                        errors.append("No markdown files found in Notion export folder")
                    return errors

                if not source.exists():
                    errors.append(f"File not found: {source}")
                    return errors

                content = source.read_text(encoding="utf-8")
            elif isinstance(source, str):
                content = source
                # Only try to treat as file path if it's short enough and doesn't contain newlines
                if "\n" not in source and len(source) < 4096:
                    try:
                        path = Path(source)
                        if path.exists():
                            content = path.read_text(encoding="utf-8")
                    except OSError:
                        pass
            else:
                content = source

            # Check for at least one story-like structure
            if not self._looks_like_notion(content):
                errors.append("Content doesn't appear to be a Notion export")

            # Try to parse and collect any errors
            try:
                stories = self._parse_notion_page(content)
                if not stories:
                    errors.append("No stories could be parsed from content")
            except Exception as e:
                errors.append(f"Parse error: {e}")

        except Exception as e:
            errors.append(f"Validation error: {e}")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods - Notion Page Parsing
    # -------------------------------------------------------------------------

    def _parse_notion_page(self, content: str) -> list[UserStory]:
        """Parse a Notion page export into stories."""
        stories = []

        # Check if this is a multi-story page or single story
        story_sections = self._split_into_stories(content)

        for section in story_sections:
            try:
                story = self._parse_single_story(section)
                if story:
                    stories.append(story)
            except Exception as e:
                self.logger.warning(f"Failed to parse story section: {e}")

        return stories

    def _split_into_stories(self, content: str) -> list[str]:
        """Split content into individual story sections."""
        # Count H1 headings - looking for actual headings, not just any # character
        h1_matches = list(re.finditer(r"^# [^#\n]+$", content, flags=re.MULTILINE))

        if len(h1_matches) > 1:
            # Multiple H1 headings - split at each one
            sections = []
            for i, match in enumerate(h1_matches):
                start = match.start()
                end = h1_matches[i + 1].start() if i + 1 < len(h1_matches) else len(content)
                section = content[start:end].strip()
                if section:
                    sections.append(section)
            return sections

        # Check for H2 with story IDs (for epic pages with sub-stories)
        h2_pattern = r"^## .*(?:US-\d+|STORY-\d+|#\d+)"
        h2_matches = list(re.finditer(h2_pattern, content, flags=re.MULTILINE | re.IGNORECASE))

        if len(h2_matches) > 1:
            sections = []
            for i, match in enumerate(h2_matches):
                start = match.start()
                end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(content)
                section = content[start:end].strip()
                if section:
                    sections.append(section)
            return sections

        # Single story page - include any properties at the top
        return [content] if content.strip() else []

    def _parse_single_story(self, content: str) -> UserStory | None:
        """Parse a single story from Notion content."""
        # Extract title and ID
        title, story_id = self._extract_title_and_id(content)

        if not title or title == "Untitled Story":
            # No valid title found - this is probably not a story
            # Check if there's at least a heading
            if not re.search(r"^##?\s+.+$", content, re.MULTILINE):
                return None

        # Extract properties block (may be before or after heading)
        properties = self._extract_properties(content)

        # Extract description from callout or section
        description = self._extract_description(content)

        # Extract acceptance criteria
        acceptance = self._extract_acceptance_criteria(content)

        # Extract subtasks from table
        subtasks = self._extract_subtasks(content)

        # Extract technical notes
        tech_notes = self._extract_technical_notes(content)

        # Extract comments
        comments = self._extract_comments(content)

        # Extract links
        links = self._extract_links(content, properties)

        # Map properties to story fields
        story_points = self._parse_int(
            properties.get("story points", properties.get("points", "0"))
        )
        priority = Priority.from_string(properties.get("priority", "medium"))
        status = Status.from_string(properties.get("status", "planned"))

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
            comments=comments,
            links=links,
        )

    def _extract_title_and_id(self, content: str) -> tuple[str, str]:
        """Extract story title and ID from content."""
        # Try H1 heading first
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)

        if h1_match:
            title = h1_match.group(1).strip()
        else:
            # Try H2 heading
            h2_match = re.search(r"^##\s+(.+)$", content, re.MULTILINE)
            title = h2_match.group(1).strip() if h2_match else "Untitled Story"

        # Extract story ID from title or properties
        story_id = self._extract_story_id(title + "\n" + content)

        # Clean title (remove ID if present)
        title = re.sub(r"\s*\[?(?:US|STORY|S)-?\d+\]?\s*:?\s*", "", title)
        title = re.sub(r"\s*#\d+\s*:?\s*", "", title)

        return title.strip(), story_id

    def _extract_story_id(self, content: str) -> str:
        """Extract story ID from content."""
        for pattern in self.STORY_ID_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                id_str = match.group(0).strip("[]#").upper()
                if not id_str.startswith("US-") and not id_str.startswith("STORY-"):
                    id_str = f"US-{id_str.lstrip('S-')}"
                return id_str

        # Generate ID from title hash
        return f"US-{abs(hash(content[:100])) % 1000:03d}"

    def _extract_properties(self, content: str) -> dict[str, str]:
        """Extract Notion property block."""
        properties: dict[str, str] = {}

        lines = content.split("\n")
        in_property_block = True

        for line in lines:
            line = line.strip()

            # Stop at first heading or empty line after properties
            if line.startswith("#") or (not line and properties):
                if properties:
                    break
                continue

            match = re.match(self.PROPERTY_PATTERN, line)
            if match:
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                # Remove Notion-style formatting
                value = re.sub(r"^@", "", value)  # @mentions
                value = re.sub(r"^\[(.+)\]$", r"\1", value)  # [links]
                properties[key] = value
            elif line and in_property_block:
                # Non-property line in expected property area
                in_property_block = False

        return properties

    def _extract_description(self, content: str) -> Description | None:
        """Extract user story description."""
        # Look for callout-style description with user emoji
        callout_pattern = r">\s*(?:👤|🙋|👨‍💻|👩‍💻)?\s*(?:As a[n]?|I am a[n]?)\s+(.+?)(?:,\s*)?(?:I want|I need)\s+(.+?)(?:,\s*)?(?:so that|in order to)\s+(.+?)(?:\n|$)"
        match = re.search(callout_pattern, content, re.IGNORECASE | re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip().rstrip(","),
                want=match.group(2).strip().rstrip(","),
                benefit=match.group(3).strip().rstrip("."),
            )

        # Look for Description section
        section = self._extract_section(content, "Description")
        if section:
            # Try to parse structured description
            as_a_match = re.search(
                r"(?:As a[n]?)\s+(.+?)(?:,\s*)?(?:I want|I need)\s+(.+?)(?:,\s*)?(?:so that|in order to)\s+(.+)",
                section,
                re.IGNORECASE | re.DOTALL,
            )
            if as_a_match:
                return Description(
                    role=as_a_match.group(1).strip().rstrip(","),
                    want=as_a_match.group(2).strip().rstrip(","),
                    benefit=as_a_match.group(3).strip(),
                )

            # Return as simple description
            return Description(role="", want=section.strip(), benefit="")

        return None

    def _extract_acceptance_criteria(self, content: str) -> AcceptanceCriteria:
        """Extract acceptance criteria from checkboxes."""
        items: list[str] = []
        checked: list[bool] = []

        # Find Acceptance Criteria section
        section = self._extract_section(content, "Acceptance Criteria")

        if not section:
            # Try alternate names
            for name in ["Acceptance", "Criteria", "Requirements", "AC"]:
                section = self._extract_section(content, name)
                if section:
                    break

        if section:
            # Parse checkboxes
            for match in re.finditer(r"[-*]\s*\[([ xX✓✔])\]\s*(.+)", section):
                is_checked = match.group(1).lower() in ["x", "✓", "✔"]
                text = match.group(2).strip()
                items.append(text)
                checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from table."""
        subtasks = []

        # Find Subtasks/Tasks section
        section = self._extract_section(content, "Subtasks")
        if not section:
            section = self._extract_section(content, "Tasks")

        if not section:
            return subtasks

        # Parse markdown table
        table_rows = self._parse_markdown_table(section)

        for i, row in enumerate(table_rows):
            if not row:
                continue

            # Try to match columns
            name = row.get("task", row.get("name", row.get("title", "")))
            description = row.get("description", row.get("desc", ""))
            points = self._parse_int(row.get("points", row.get("sp", row.get("story points", "1"))))
            status = Status.from_string(row.get("status", "planned"))
            assignee = row.get("assignee", row.get("owner", None))

            if name:
                subtasks.append(
                    Subtask(
                        number=i + 1,
                        name=name,
                        description=description,
                        story_points=points,
                        status=status,
                        assignee=assignee,
                    )
                )

        return subtasks

    def _extract_technical_notes(self, content: str) -> str:
        """Extract technical notes section."""
        section = self._extract_section(content, "Technical Notes")
        if not section:
            section = self._extract_section(content, "Technical Details")
        if not section:
            section = self._extract_section(content, "Implementation")

        return section.strip() if section else ""

    def _extract_comments(self, content: str) -> list[Comment]:
        """
        Extract comments from Notion content.

        Supported formats:
        - ## Comments section with blockquotes
        - Callout blocks with comment indicator

        Returns:
            List of Comment objects
        """
        from datetime import datetime

        comments: list[Comment] = []

        # Find Comments section
        section = self._extract_section(content, "Comments")
        if not section:
            section = self._extract_section(content, "Discussion")
        if not section:
            section = self._extract_section(content, "Notes")

        if not section:
            return comments

        # Split into individual comment blocks (blockquotes or paragraphs)
        # Pattern: blockquote blocks starting with >
        comment_blocks = re.split(r"\n\s*\n(?=>)", section.strip())

        for block in comment_blocks:
            if not block.strip():
                continue

            # Extract blockquote content (remove > prefixes)
            lines = []
            for line in block.strip().split("\n"):
                # Remove leading > and optional space
                cleaned = re.sub(r"^>\s?", "", line)
                lines.append(cleaned)

            if not lines:
                continue

            full_text = "\n".join(lines).strip()
            if not full_text:
                continue

            # Try to extract author and date
            # Format: **@username** (YYYY-MM-DD): or @username (date):
            author = None
            created_at = None
            body = full_text

            # Try structured format: **@username** (YYYY-MM-DD):
            header_match = re.match(
                r"\*\*@([^*]+)\*\*\s*(?:\((\d{4}-\d{2}-\d{2})\))?:?\s*(.*)",
                full_text,
                re.DOTALL,
            )

            if header_match:
                author = header_match.group(1).strip()
                date_str = header_match.group(2)
                if date_str:
                    try:
                        created_at = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        pass
                body = header_match.group(3).strip()
            else:
                # Check for simpler format: @username: comment
                simple_match = re.match(r"@([^\s:]+):?\s*(.*)", full_text, re.DOTALL)
                if simple_match:
                    author = simple_match.group(1).strip()
                    body = simple_match.group(2).strip()

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

    def _extract_links(
        self, content: str, properties: dict[str, str]
    ) -> list[tuple[str, str]]:
        """
        Extract issue links from Notion content.

        Supported formats:
        - ## Links/Related/Dependencies section with table or list
        - Properties: Blocks: PROJ-123, Depends on: OTHER-456
        - Inline mentions: blocks PROJ-123

        Returns:
            List of (link_type, target_key) tuples
        """
        links: list[tuple[str, str]] = []

        # Check properties first
        link_property_map = {
            "blocks": "blocks",
            "blocked by": "blocked by",
            "depends on": "depends on",
            "related to": "relates to",
            "relates to": "relates to",
            "duplicates": "duplicates",
            "parent": "parent of",
            "child of": "child of",
        }

        for prop_name, link_type in link_property_map.items():
            value = properties.get(prop_name, "")
            if value:
                # Parse comma-separated keys
                for key in re.findall(r"[A-Z]+-\d+", value):
                    links.append((link_type, key))

        # Find Links/Related/Dependencies section
        section = self._extract_section(content, "Links")
        if not section:
            section = self._extract_section(content, "Related")
        if not section:
            section = self._extract_section(content, "Dependencies")
        if not section:
            section = self._extract_section(content, "Related Issues")

        if section:
            # Parse table rows: | link_type | target_key |
            table_pattern = r"\|\s*([^|]+)\s*\|\s*([A-Z]+-\d+)\s*\|"
            for match in re.finditer(table_pattern, section):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                if target_key and not link_type.startswith("-"):
                    links.append((link_type, target_key))

            # Parse bullet list: - blocks: PROJ-123 or - blocks PROJ-123
            bullet_pattern = (
                r"[-*]\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+([A-Z]+-\d+)"
            )
            for match in re.finditer(bullet_pattern, section, re.IGNORECASE):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                links.append((link_type, target_key))

        return links

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a heading."""
        # Match heading at any level
        pattern = rf"^#+\s*{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()

        # Find next heading at same or higher level
        heading_level = len(re.match(r"^#+", match.group(0)).group(0))
        next_heading = re.search(rf"^#{{{1},{heading_level}}}\s", content[start:], re.MULTILINE)

        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()

    def _parse_markdown_table(self, content: str) -> list[dict[str, str]]:
        """Parse a markdown table into list of dicts."""
        rows: list[dict[str, str]] = []

        lines = content.strip().split("\n")
        headers: list[str] = []

        for line in lines:
            line = line.strip()
            if not line.startswith("|"):
                continue

            # Parse cells
            cells = [c.strip() for c in line.strip("|").split("|")]

            if not headers:
                # First row is headers
                headers = [h.lower().strip() for h in cells]
            elif all(c.replace("-", "").replace(":", "") == "" for c in cells):
                # Separator row
                continue
            else:
                # Data row
                row = {}
                for i, cell in enumerate(cells):
                    if i < len(headers):
                        row[headers[i]] = cell
                if any(row.values()):
                    rows.append(row)

        return rows

    def _parse_int(self, value: str) -> int:
        """Parse integer from string, handling various formats."""
        if not value:
            return 0

        # Remove non-numeric chars except minus
        cleaned = re.sub(r"[^\d-]", "", str(value))

        try:
            return int(cleaned) if cleaned else 0
        except ValueError:
            return 0

    # -------------------------------------------------------------------------
    # Private Methods - Database/Folder Parsing
    # -------------------------------------------------------------------------

    def _parse_database_csv(self, path: Path) -> list[UserStory]:
        """Parse a Notion database CSV export."""
        stories = []

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for i, row in enumerate(reader):
                    story = self._parse_csv_row(row, i)
                    if story:
                        stories.append(story)

        except Exception as e:
            self.logger.error(f"Failed to parse CSV: {e}")

        return stories

    def _parse_csv_row(self, row: dict[str, str], index: int) -> UserStory | None:
        """Parse a CSV row into a UserStory."""
        # Normalize keys to lowercase
        row = {k.lower(): v for k, v in row.items()}

        # Get title (try various column names)
        title = (
            row.get("name") or row.get("title") or row.get("story") or row.get("task") or ""
        ).strip()

        if not title:
            return None

        # Get ID
        story_id = row.get("id", row.get("story id", f"US-{index + 1:03d}"))
        if not story_id.startswith("US-"):
            story_id = f"US-{story_id}"

        # Parse fields
        story_points = self._parse_int(
            row.get("story points", row.get("points", row.get("sp", "0")))
        )
        priority = Priority.from_string(row.get("priority", "medium"))
        status = Status.from_string(row.get("status", "planned"))

        # Build description
        description = None
        desc_text = row.get("description", "")
        if desc_text:
            description = Description(role="", want=desc_text, benefit="")

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=AcceptanceCriteria.from_list([], []),
            technical_notes=row.get("notes", row.get("technical notes", "")),
            story_points=story_points,
            priority=priority,
            status=status,
            subtasks=[],
            commits=[],
            comments=[],
            links=[],
        )

    def _parse_notion_folder(self, folder: Path) -> list[UserStory]:
        """Parse a Notion export folder structure."""
        stories = []

        # Find all markdown files
        for md_file in sorted(folder.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                page_stories = self._parse_notion_page(content)
                stories.extend(page_stories)
            except Exception as e:
                self.logger.warning(f"Failed to parse {md_file}: {e}")

        # Also check for CSV files (database exports)
        for csv_file in folder.rglob("*.csv"):
            try:
                csv_stories = self._parse_database_csv(csv_file)
                stories.extend(csv_stories)
            except Exception as e:
                self.logger.warning(f"Failed to parse {csv_file}: {e}")

        return stories
