"""
Markdown Parser - Parse markdown epic files into domain entities.

Implements the DocumentParserPort interface.
Supports both single-epic and multi-epic formats.
"""

import logging
import re
from pathlib import Path

from spectra.core.domain.entities import Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort


class MarkdownParser(DocumentParserPort):
    """
    Parser for markdown epic files.

    Supports multiple markdown formats with auto-detection:

    FORMAT A (Table-based metadata):
    --------------------------------
    ### [emoji] US-XXX: Title

    | Field | Value |
    |-------|-------|
    | **Story Points** | X |
    | **Priority** | emoji Priority |
    | **Status** | emoji Status |

    #### Description
    **As a** role
    **I want** feature
    **So that** benefit

    FORMAT B (Inline metadata):
    ---------------------------
    ### US-XXX: Title

    **Priority**: P0
    **Story Points**: 5
    **Status**: ✅ Complete

    #### User Story
    > **As a** role,
    > **I want** feature,
    > **So that** benefit.

    Multi-Epic Format (both formats):
    ---------------------------------
    # Project: Project Title

    ## Epic: PROJ-100 - Epic Title 1
    ### US-XXX: Title
    ...

    Common sections (both formats):
    - #### Acceptance Criteria
    - #### Subtasks
    - #### Related Commits
    - #### Technical Notes
    - #### Dependencies
    """

    # Format detection patterns
    FORMAT_TABLE = "table"  # Table-based metadata
    FORMAT_INLINE = "inline"  # Inline key: value metadata

    # Story patterns - flexible to match both formats
    # Matches: ### ✅ US-001: Title  OR  ### US-001: Title
    STORY_PATTERN = r"### (?:[^\n]+ )?(US-\d+): ([^\n]+)\n"
    STORY_PATTERN_FLEXIBLE = r"### (?:.*?)?(US-\d+):\s*([^\n]+)\n"
    EPIC_TITLE_PATTERN = r"^#\s+[^\n]+\s+([^\n]+)$"
    # Multi-epic pattern: ## Epic: PROJ-100 - Epic Title or ## Epic: PROJ-100
    MULTI_EPIC_PATTERN = r"^##\s+Epic:\s*([A-Z]+-\d+)(?:\s*[-–—]\s*(.+))?$"

    # Inline metadata patterns (Format B)
    INLINE_FIELD_PATTERN = r"\*\*{field}\*\*:\s*(.+?)(?:\s*$|\s{2,})"

    def __init__(self, story_pattern: str | None = None):
        """
        Initialize parser.

        Args:
            story_pattern: Optional custom regex for story detection
        """
        self.logger = logging.getLogger("MarkdownParser")
        self._detected_format: str | None = None

        if story_pattern:
            self.STORY_PATTERN = story_pattern

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "Markdown"

    @property
    def supported_extensions(self) -> list[str]:
        return [".md", ".markdown"]

    def can_parse(self, source: str | Path) -> bool:
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Check if content looks like markdown with either pattern
        return bool(
            re.search(self.STORY_PATTERN, source)
            or re.search(self.STORY_PATTERN_FLEXIBLE, source)
        )

    def _detect_format(self, content: str) -> str:
        """
        Detect which markdown format is being used.

        Args:
            content: Markdown content to analyze

        Returns:
            FORMAT_TABLE or FORMAT_INLINE
        """
        # Look for table-based metadata (| **Field** | Value |)
        has_table_metadata = bool(re.search(r"\|\s*\*\*Story Points\*\*\s*\|", content))

        # Look for inline metadata (**Field**: Value)
        has_inline_metadata = bool(re.search(r"\*\*(?:Priority|Story Points|Status)\*\*:\s*", content))

        if has_table_metadata and not has_inline_metadata:
            return self.FORMAT_TABLE
        if has_inline_metadata and not has_table_metadata:
            return self.FORMAT_INLINE

        # Default to table format for backward compatibility
        return self.FORMAT_TABLE

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        content = self._get_content(source)
        self._detected_format = self._detect_format(content)
        self.logger.debug(f"Detected markdown format: {self._detected_format}")
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        content = self._get_content(source)

        # Check if this is a multi-epic file
        if self.is_multi_epic(content):
            epics = self.parse_epics(content)
            return epics[0] if epics else None

        # Extract epic title from first heading
        title_match = re.search(r"^#\s+[^\n]*?([A-Z]+-\d+)?.*$", content, re.MULTILINE)
        title = title_match.group(0) if title_match else "Untitled Epic"

        # Parse all stories
        stories = self._parse_all_stories(content)

        if not stories:
            return None

        # Create epic (key will be set when syncing)
        return Epic(
            key=IssueKey("EPIC-0"),  # Placeholder
            title=title.strip("# "),
            stories=stories,
        )

    def is_multi_epic(self, source: str | Path) -> bool:
        """
        Check if source contains multiple epics.

        Args:
            source: File path or content string

        Returns:
            True if multiple epics are found
        """
        content = self._get_content(source)
        epic_matches = re.findall(self.MULTI_EPIC_PATTERN, content, re.MULTILINE)
        return len(epic_matches) >= 1

    def parse_epics(self, source: str | Path) -> list[Epic]:
        """
        Parse multiple epics from source.

        Expected format:
        ## Epic: PROJ-100 - Epic Title 1
        ### US-001: Story 1
        ...

        ## Epic: PROJ-200 - Epic Title 2
        ### US-002: Story 2
        ...

        Args:
            source: File path or content string

        Returns:
            List of Epic entities
        """
        content = self._get_content(source)
        epics = []

        # Find all epic headers
        epic_matches = list(re.finditer(self.MULTI_EPIC_PATTERN, content, re.MULTILINE))

        if not epic_matches:
            # Fall back to single epic parsing
            single_epic = self.parse_epic(source)
            return [single_epic] if single_epic else []

        self.logger.info(f"Found {len(epic_matches)} epics in file")

        for i, match in enumerate(epic_matches):
            epic_key = match.group(1)
            epic_title = match.group(2).strip() if match.group(2) else f"Epic {epic_key}"

            # Get content from this epic header to the next (or end)
            start = match.end()
            end = epic_matches[i + 1].start() if i + 1 < len(epic_matches) else len(content)
            epic_content = content[start:end]

            # Parse stories within this epic section
            stories = self._parse_all_stories(epic_content)

            self.logger.debug(f"Epic {epic_key}: {len(stories)} stories")

            epic = Epic(
                key=IssueKey(epic_key),
                title=epic_title,
                stories=stories,
            )
            epics.append(epic)

        return epics

    def get_epic_keys(self, source: str | Path) -> list[str]:
        """
        Get list of epic keys from a multi-epic file.

        Args:
            source: File path or content string

        Returns:
            List of epic keys (e.g., ["PROJ-100", "PROJ-200"])
        """
        content = self._get_content(source)
        matches = re.findall(self.MULTI_EPIC_PATTERN, content, re.MULTILINE)
        return [match[0] for match in matches]

    def validate(self, source: str | Path) -> list[str]:
        content = self._get_content(source)
        errors = []

        # Detect format for appropriate validation
        detected_format = self._detect_format(content)

        # Check for story pattern using flexible pattern
        story_matches = list(re.finditer(self.STORY_PATTERN_FLEXIBLE, content))
        if not story_matches:
            story_matches = list(re.finditer(self.STORY_PATTERN, content))

        if not story_matches:
            errors.append("No user stories found matching pattern '### [emoji] US-XXX: Title' or '### US-XXX: Title'")

        # Validate each story
        for i, match in enumerate(story_matches):
            story_id = match.group(1)
            start = match.end()
            end = story_matches[i + 1].start() if i + 1 < len(story_matches) else len(content)
            story_content = content[start:end]

            # Check for required fields - both formats accepted
            has_story_points_table = bool(re.search(r"\|\s*\*\*Story Points\*\*\s*\|", story_content))
            has_story_points_inline = bool(re.search(r"\*\*Story Points\*\*:\s*\d+", story_content))
            if not has_story_points_table and not has_story_points_inline:
                errors.append(f"{story_id}: Missing Story Points field")

            # Check for description in either format
            has_description = bool(re.search(r"\*\*As a\*\*", story_content))
            if not has_description:
                errors.append(f"{story_id}: Missing 'As a' description")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _get_content(self, source: str | Path) -> str:
        """Get content from file path or string."""
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8")
        if isinstance(source, str):
            # Only try to treat as file path if it's short enough and doesn't contain newlines
            # (file paths don't have newlines and have OS-specific length limits)
            if "\n" not in source and len(source) < 4096:
                try:
                    path = Path(source)
                    if path.exists():
                        return path.read_text(encoding="utf-8")
                except OSError:
                    # Invalid path characters or other OS-level path issues
                    pass
        return source

    def _parse_all_stories(self, content: str) -> list[UserStory]:
        """Parse all stories from content."""
        stories = []

        # Try flexible pattern first, then fall back to strict pattern
        story_matches = list(re.finditer(self.STORY_PATTERN_FLEXIBLE, content))
        if not story_matches:
            story_matches = list(re.finditer(self.STORY_PATTERN, content))

        self.logger.debug(f"Found {len(story_matches)} stories")

        for i, match in enumerate(story_matches):
            story_id = match.group(1)
            title = match.group(2).strip()

            # Get content until next story or end
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
        # Extract metadata
        story_points = self._extract_field(content, "Story Points", "0")
        priority = self._extract_field(content, "Priority", "Medium")
        status = self._extract_field(content, "Status", "Planned")

        # Extract description
        description = self._extract_description(content)

        # Extract acceptance criteria
        acceptance = self._extract_acceptance_criteria(content)

        # Extract subtasks
        subtasks = self._extract_subtasks(content)

        # Extract commits
        commits = self._extract_commits(content)

        # Extract technical notes
        tech_notes = self._extract_technical_notes(content)

        # Extract links (cross-project)
        links = self._extract_links(content)

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=tech_notes,
            story_points=int(story_points) if story_points.isdigit() else 0,
            priority=Priority.from_string(priority),
            status=Status.from_string(status),
            subtasks=subtasks,
            commits=commits,
            links=links,
        )

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """
        Extract field value from markdown - supports both table and inline formats.

        Format A (Table): | **Field** | Value |
        Format B (Inline): **Field**: Value
        """
        # Try table format first: | **Field** | Value |
        table_pattern = rf"\|\s*\*\*{field_name}\*\*\s*\|\s*([^|]+)\s*\|"
        match = re.search(table_pattern, content)
        if match:
            return match.group(1).strip()

        # Try inline format: **Field**: Value or **Field**: Value (with trailing spaces)
        inline_pattern = rf"\*\*{field_name}\*\*:\s*(.+?)(?:\s*$|\s{{2,}}|\n)"
        match = re.search(inline_pattern, content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        return default

    def _extract_description(self, content: str) -> Description | None:
        """
        Extract As a/I want/So that description.

        Supports multiple formats:
        - Direct format: **As a** role **I want** feature **So that** benefit
        - Blockquote format: > **As a** role, > **I want** feature, > **So that** benefit
        - User Story section: #### User Story with blockquotes
        """
        # First try to find a dedicated User Story section (Format B)
        user_story_section = re.search(
            r"#### User Story\n([\s\S]*?)(?=####|\n---|\Z)", content
        )

        search_content = user_story_section.group(1) if user_story_section else content

        # Pattern for blockquote format (with optional commas and line continuations)
        # > **As a** role,
        # > **I want** feature,
        # > **So that** benefit.
        blockquote_pattern = (
            r">\s*\*\*As a\*\*\s*(.+?)(?:,\s*\n|\n)"
            r"(?:>\s*)?\*\*I want\*\*\s*(.+?)(?:,\s*\n|\n)"
            r"(?:>\s*)?\*\*So that\*\*\s*(.+?)(?:\.|$)"
        )
        match = re.search(blockquote_pattern, search_content, re.DOTALL | re.IGNORECASE)

        if match:
            return Description(
                role=match.group(1).strip().rstrip(","),
                want=match.group(2).strip().rstrip(","),
                benefit=match.group(3).strip().rstrip("."),
            )

        # Standard format (direct, no blockquotes)
        pattern = (
            r"\*\*As a\*\*\s*(.+?)\s*\n\s*"
            r"\*\*I want\*\*\s*(.+?)\s*\n\s*"
            r"\*\*So that\*\*\s*(.+?)(?:\n|$)"
        )
        match = re.search(pattern, search_content, re.DOTALL)

        if match:
            return Description(
                role=match.group(1).strip(),
                want=match.group(2).strip(),
                benefit=match.group(3).strip(),
            )

        # Try a more lenient blockquote pattern for multi-line
        lenient_blockquote = (
            r">\s*\*\*As a\*\*\s*([^,\n]+)"
            r"[\s\S]*?"
            r"\*\*I want\*\*\s*([^,\n]+)"
            r"[\s\S]*?"
            r"\*\*So that\*\*\s*([^.\n]+)"
        )
        match = re.search(lenient_blockquote, search_content, re.IGNORECASE)

        if match:
            return Description(
                role=match.group(1).strip().rstrip(","),
                want=match.group(2).strip().rstrip(","),
                benefit=match.group(3).strip().rstrip("."),
            )

        return None

    def _extract_acceptance_criteria(self, content: str) -> AcceptanceCriteria:
        """Extract acceptance criteria checkboxes."""
        items = []
        checked = []

        section = re.search(r"#### Acceptance Criteria\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if section:
            for match in re.finditer(r"- \[([ x])\]\s*(.+)", section.group(1)):
                checked.append(match.group(1).lower() == "x")
                items.append(match.group(2).strip())

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from table."""
        subtasks = []

        section = re.search(r"#### Subtasks\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if section:
            # Parse table rows: | # | Subtask | Description | SP | Status |
            pattern = r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|"

            for match in re.finditer(pattern, section.group(1)):
                subtasks.append(
                    Subtask(
                        number=int(match.group(1)),
                        name=match.group(2).strip(),
                        description=match.group(3).strip(),
                        story_points=int(match.group(4)),
                        status=Status.from_string(match.group(5)),
                    )
                )

        return subtasks

    def _extract_commits(self, content: str) -> list[CommitRef]:
        """Extract commits from table."""
        commits = []

        section = re.search(r"#### Related Commits\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if section:
            pattern = r"\|\s*`([^`]+)`\s*\|\s*([^|]+)\s*\|"

            for match in re.finditer(pattern, section.group(1)):
                commits.append(
                    CommitRef(
                        hash=match.group(1).strip(),
                        message=match.group(2).strip(),
                    )
                )

        return commits

    def _extract_technical_notes(self, content: str) -> str:
        """Extract technical notes section."""
        section = re.search(r"#### Technical Notes\n([\s\S]*?)(?=####|\Z)", content)

        if section:
            return section.group(1).strip()
        return ""

    def _extract_links(self, content: str) -> list[tuple[str, str]]:
        """
        Extract issue links from content.

        Supported formats:
        - #### Links section with table: | blocks | PROJ-123 |
        - Inline: **Blocks:** PROJ-123, PROJ-456
        - Inline: **Depends on:** OTHER-789
        - Bullet list: - blocks: PROJ-123

        Returns:
            List of (link_type, target_key) tuples
        """
        links = []

        # Pattern for Links section table
        section = re.search(
            r"#### (?:Links|Related Issues|Dependencies)\n([\s\S]*?)(?=####|\n---|\Z)", content
        )

        if section:
            section_content = section.group(1)
            # Parse table rows: | link_type | target_key |
            table_pattern = r"\|\s*([^|]+)\s*\|\s*([A-Z]+-\d+)\s*\|"
            for match in re.finditer(table_pattern, section_content):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                if target_key and not link_type.startswith("-"):
                    links.append((link_type, target_key))

            # Parse bullet list: - blocks: PROJ-123
            bullet_pattern = (
                r"[-*]\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+([A-Z]+-\d+)"
            )
            for match in re.finditer(bullet_pattern, section_content, re.IGNORECASE):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                links.append((link_type, target_key))

        # Pattern for inline links: **Blocks:** PROJ-123, PROJ-456
        inline_patterns = [
            (r"\*\*Blocks[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "blocks"),
            (r"\*\*Blocked by[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "blocked by"),
            (r"\*\*Depends on[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "depends on"),
            (r"\*\*Related to[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "relates to"),
            (r"\*\*Relates to[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "relates to"),
            (r"\*\*Duplicates[:\s]*\*\*\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)", "duplicates"),
        ]

        for pattern, link_type in inline_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                keys_str = match.group(1)
                for key in re.findall(r"[A-Z]+-\d+", keys_str):
                    links.append((link_type, key))

        return links
