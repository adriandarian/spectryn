"""
PlantUML/Mermaid Diagram Parser - Parse diagram files into domain entities.

Implements the DocumentParserPort interface for diagram-based requirements.

Extracts user stories from PlantUML and Mermaid diagram comments/notes.
"""

import logging
import re
from pathlib import Path

from spectra.core.domain.entities import Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort


class DiagramParser(DocumentParserPort):
    """
    Parser for PlantUML and Mermaid diagram files.

    Extracts stories from notes and comments in diagram syntax.

    Example PlantUML format:

    ```plantuml
    @startuml
    ' Epic: PROJ-123 - User Flow
    ' Epic Key: PROJ-123

    title User Registration Flow

    actor User
    participant "Web App" as App
    participant "API" as API
    database "DB" as DB

    note over App
    PROJ-001: User Registration
    Story Points: 5
    Priority: High
    Status: Planned

    As a user
    I want to register an account
    So that I can access the system

    Acceptance Criteria:
    - [ ] Email validation
    - [x] Password strength check
    end note

    User -> App: Submit form
    App -> API: POST /register
    API -> DB: Create user
    @enduml
    ```

    Example Mermaid format:

    ```mermaid
    %%{ Epic: PROJ-123 - User Flow }%%
    %%{ Epic Key: PROJ-123 }%%

    sequenceDiagram
        %% PROJ-001: User Registration
        %% Story Points: 5
        %% Priority: High
        %% Status: Planned

        Note over App: As a user I want to register
        User->>App: Submit form
        App->>API: POST /register
    ```
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    def __init__(self) -> None:
        """Initialize the diagram parser."""
        self.logger = logging.getLogger("DiagramParser")

    @property
    def name(self) -> str:
        return "Diagram"

    @property
    def supported_extensions(self) -> list[str]:
        return [".puml", ".plantuml", ".pu", ".mmd", ".mermaid"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid diagram file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Check for PlantUML or Mermaid content
        is_plantuml = bool(re.search(r"@start(uml|mindmap|gantt)", source))
        is_mermaid = bool(
            re.search(
                r"(sequenceDiagram|flowchart|classDiagram|stateDiagram|erDiagram|gantt)",
                source,
            )
        )

        return is_plantuml or is_mermaid

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from diagram source."""
        content = self._get_content(source)

        if self._is_plantuml(content):
            return self._parse_plantuml_stories(content)
        if self._is_mermaid(content):
            return self._parse_mermaid_stories(content)
        return []

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic from diagram source."""
        content = self._get_content(source)

        # Extract epic info from comments
        epic_key = "EPIC-0"
        epic_title = "Untitled Epic"

        # PlantUML style: ' Epic Key: PROJ-123
        key_match = re.search(r"['\"]?\s*Epic\s*Key:\s*([A-Z]+[-_/]\d+)", content)
        if key_match:
            epic_key = key_match.group(1)

        title_match = re.search(r"['\"]?\s*Epic:\s*([^\n]+)", content)
        if title_match:
            epic_title = title_match.group(1).strip()
            epic_title = re.sub(rf"^{self.STORY_ID_PATTERN}\s*[-–—]\s*", "", epic_title)

        # Mermaid style: %%{ Epic Key: PROJ-123 }%%
        if epic_key == "EPIC-0":
            key_match = re.search(r"%%\{\s*Epic\s*Key:\s*([A-Z]+[-_/]\d+)", content)
            if key_match:
                epic_key = key_match.group(1)

        if epic_title == "Untitled Epic":
            title_match = re.search(r"%%\{\s*Epic:\s*([^}]+)", content)
            if title_match:
                epic_title = title_match.group(1).strip()

        stories = self.parse_stories(source)

        if not stories:
            return None

        return Epic(key=IssueKey(epic_key), title=epic_title, stories=stories)

    def validate(self, source: str | Path) -> list[str]:
        """Validate diagram source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        if not self._is_plantuml(content) and not self._is_mermaid(content):
            errors.append("Not a valid PlantUML or Mermaid diagram")

        # Check for story definitions
        story_pattern = rf"({self.STORY_ID_PATTERN}):\s*"
        if not re.search(story_pattern, content):
            errors.append("No user stories found in diagram")

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

    def _is_plantuml(self, content: str) -> bool:
        """Check if content is PlantUML."""
        return bool(re.search(r"@start(uml|mindmap|gantt)", content))

    def _is_mermaid(self, content: str) -> bool:
        """Check if content is Mermaid."""
        return bool(
            re.search(
                r"(sequenceDiagram|flowchart|classDiagram|stateDiagram|erDiagram|gantt)",
                content,
            )
        )

    def _parse_plantuml_stories(self, content: str) -> list[UserStory]:
        """Parse stories from PlantUML notes and comments."""
        stories = []

        # Extract notes: note over/left/right ... end note
        note_pattern = r"note\s+(?:over|left|right)[^\n]*\n([\s\S]*?)end note"
        for match in re.finditer(note_pattern, content):
            note_content = match.group(1)
            story = self._parse_story_from_text(note_content)
            if story:
                stories.append(story)

        # Extract from comment blocks: ' comments
        comment_block_pattern = r"((?:'[^\n]*\n)+)(?=\s*(?:actor|participant|database|note|@end))"
        for match in re.finditer(comment_block_pattern, content):
            block = match.group(1)
            # Strip comment markers
            lines = [line.lstrip("' ").strip() for line in block.split("\n") if line.strip()]
            text = "\n".join(lines)
            story = self._parse_story_from_text(text)
            if story:
                stories.append(story)

        return stories

    def _parse_mermaid_stories(self, content: str) -> list[UserStory]:
        """Parse stories from Mermaid comments."""
        stories = []

        # Collect all %% comment lines into blocks by story
        all_comment_lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("%%"):
                # Strip %% prefix and any { } wrapper
                comment = stripped.lstrip("%").strip()
                comment = re.sub(r"^\{\s*", "", comment)
                comment = re.sub(r"\s*\}$", "", comment)
                if comment:
                    all_comment_lines.append(comment)

        # Join all comment lines and parse
        if all_comment_lines:
            text = "\n".join(all_comment_lines)
            story = self._parse_story_from_text(text)
            if story:
                stories.append(story)

        # Extract from Note elements
        note_pattern = r"Note\s+(?:over|left|right)[^\n:]*:\s*(.+)"
        for match in re.finditer(note_pattern, content):
            note_text = match.group(1)
            story = self._parse_story_from_text(note_text)
            if story:
                stories.append(story)

        return stories

    def _parse_story_from_text(self, content: str) -> UserStory | None:
        """Parse a story from text content."""
        header_match = re.search(rf"({self.STORY_ID_PATTERN}):\s*([^\n]+)", content)
        if not header_match:
            return None

        story_id = header_match.group(1)
        title = header_match.group(2).strip()

        # Extract fields
        story_points = self._extract_field(content, "Story Points", "0")
        priority = self._extract_field(content, "Priority", "Medium")
        status = self._extract_field(content, "Status", "Planned")

        description = self._extract_description(content)
        acceptance = self._extract_acceptance_criteria(content)
        subtasks = self._extract_subtasks(content)
        tech_notes = self._extract_section(content, "Technical Notes")

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
        )

    def _extract_field(self, content: str, field: str, default: str = "") -> str:
        """Extract field value from content."""
        match = re.search(rf"{field}\s*:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
        return match.group(1).strip() if match else default

    def _extract_description(self, content: str) -> Description | None:
        """Extract As a/I want/So that description."""
        pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

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
            items.append(match.group(2).strip())
            checked.append(is_checked)

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from section."""
        subtasks = []
        section = self._extract_section(content, "Subtasks")
        if not section:
            return subtasks

        for i, match in enumerate(re.finditer(r"[-*]\s*(.+)", section), 1):
            subtasks.append(Subtask(number=i, name=match.group(1).strip(), description=""))
        return subtasks

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a heading."""
        pattern = rf"^{re.escape(heading)}:\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()
        next_heading = re.search(r"^[A-Z][a-zA-Z\s]+:\s*$", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
