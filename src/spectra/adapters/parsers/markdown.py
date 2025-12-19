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

    FORMAT C (Standalone file with h1 header and blockquote metadata):
    ------------------------------------------------------------------
    # US-XXX: Title [emoji]

    > **Story ID**: US-XXX
    > **Status**: ✅ Done
    > **Points**: 8
    > **Priority**: P0 - Critical

    ## User Story
    **As a** role
    **I want** feature
    **So that** benefit

    Multi-Epic Format (both formats):
    ---------------------------------
    # Project: Project Title

    ## Epic: PROJ-100 - Epic Title 1
    ### US-XXX: Title
    ...

    Multi-File Format:
    ------------------
    A directory containing:
    - EPIC.md (optional, with epic metadata)
    - US-001-*.md, US-002-*.md, etc. (individual story files)

    Common sections (all formats):
    - #### Acceptance Criteria / ## Acceptance Criteria
    - #### Subtasks / ## Subtasks
    - #### Related Commits
    - #### Technical Notes / ## Technical Notes
    - #### Dependencies / ## Dependencies
    """

    # Format detection patterns
    FORMAT_TABLE = "table"  # Table-based metadata
    FORMAT_INLINE = "inline"  # Inline key: value metadata
    FORMAT_BLOCKQUOTE = "blockquote"  # Blockquote metadata (> **Field**: Value)
    FORMAT_STANDALONE = "standalone"  # Standalone file with h1 header

    # Story patterns - flexible to match multiple header levels and formats
    # Matches: ### ✅ US-001: Title  OR  ### US-001: Title (h3)
    STORY_PATTERN = r"### (?:[^\n]+ )?(US-\d+): ([^\n]+)\n"
    STORY_PATTERN_FLEXIBLE = r"### (?:.*?)?(US-\d+):\s*([^\n]+)\n"

    # Standalone story pattern for h1 headers: # US-001: Title [emoji] or # US-001: Title
    STORY_PATTERN_H1 = r"^#\s+(?:.*?)?(US-\d+):\s*([^\n]+?)(?:\s*[✅🔲🟡⏸️]+)?\s*$"

    EPIC_TITLE_PATTERN = r"^#\s+[^\n]+\s+([^\n]+)$"
    # Multi-epic pattern: ## Epic: PROJ-100 - Epic Title or ## Epic: PROJ-100
    MULTI_EPIC_PATTERN = r"^##\s+Epic:\s*([A-Z]+-\d+)(?:\s*[-–—]\s*(.+))?$"

    # Inline metadata patterns (Format B)
    INLINE_FIELD_PATTERN = r"\*\*{field}\*\*:\s*(.+?)(?:\s*$|\s{2,})"

    # Blockquote metadata pattern (Format C): > **Field**: Value
    BLOCKQUOTE_FIELD_PATTERN = r">\s*\*\*{field}\*\*:\s*(.+?)(?:\s*$)"

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
            re.search(self.STORY_PATTERN, source) or re.search(self.STORY_PATTERN_FLEXIBLE, source)
        )

    def _detect_format(self, content: str) -> str:
        """
        Detect which markdown format is being used.

        Args:
            content: Markdown content to analyze

        Returns:
            FORMAT_TABLE, FORMAT_INLINE, FORMAT_BLOCKQUOTE, or FORMAT_STANDALONE
        """
        # Check for standalone file format (h1 header with US-XXX)
        has_h1_story = bool(re.search(self.STORY_PATTERN_H1, content, re.MULTILINE))

        # Look for blockquote metadata (> **Field**: Value)
        has_blockquote_metadata = bool(
            re.search(r">\s*\*\*(?:Priority|Points|Status|Story\s*ID)\*\*:\s*", content)
        )

        # Look for table-based metadata (| **Field** | Value |)
        has_table_metadata = bool(
            re.search(r"\|\s*\*\*(?:Story\s*)?Points\*\*\s*\|", content, re.IGNORECASE)
        )

        # Look for inline metadata (**Field**: Value) - not in blockquotes
        has_inline_metadata = bool(
            re.search(
                r"^(?!>)\s*\*\*(?:Priority|Story\s*Points|Points|Status)\*\*:\s*",
                content,
                re.MULTILINE,
            )
        )

        if has_h1_story and has_blockquote_metadata:
            return self.FORMAT_STANDALONE
        if has_blockquote_metadata and not has_table_metadata:
            return self.FORMAT_BLOCKQUOTE
        if has_table_metadata and not has_inline_metadata:
            return self.FORMAT_TABLE
        if has_inline_metadata:
            return self.FORMAT_INLINE

        # Default to table format for backward compatibility
        return self.FORMAT_TABLE

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        # Handle directory input - parse all US-*.md files
        source_path = Path(source) if isinstance(source, str) else source
        if isinstance(source_path, Path) and source_path.is_dir():
            return self._parse_stories_from_directory(source_path)

        content = self._get_content(source)
        self._detected_format = self._detect_format(content)
        self.logger.debug(f"Detected markdown format: {self._detected_format}")
        return self._parse_all_stories(content)

    def _is_story_file(self, file_path: Path) -> bool:
        """
        Detect if a markdown file contains user story content.

        Uses both filename patterns and content detection for reliability.

        Args:
            file_path: Path to the markdown file.

        Returns:
            True if the file appears to be a user story file.
        """
        name_lower = file_path.name.lower()

        # Skip known non-story files
        skip_patterns = {
            "readme.md",
            "changelog.md",
            "contributing.md",
            "license.md",
            "architecture.md",
            "development.md",
            "setup.md",
            "index.md",
            "summary.md",
            "glossary.md",
            "faq.md",
            "troubleshooting.md",
        }
        if name_lower in skip_patterns:
            return False

        # Filename pattern match (fast path)
        if name_lower.startswith("us-") or name_lower.startswith("story-"):
            return True

        # Content-based detection (slower but more reliable)
        try:
            content = file_path.read_text(encoding="utf-8")
            # Check for story header patterns
            story_markers = [
                r"^#{1,3}\s+.*(?:US-\d+|[A-Z]+-\d+):",  # Story ID header
                r"\*\*As a\*\*.*\*\*I want\*\*",  # User story format
                r">\s*\*\*Story ID\*\*:",  # Blockquote metadata
                r"\|\s*\*\*Story Points\*\*\s*\|",  # Table metadata
            ]
            for pattern in story_markers:
                if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
                    return True
        except Exception:
            pass

        return False

    def _parse_stories_from_directory(self, directory: Path) -> list[UserStory]:
        """
        Parse all user story files from a directory.

        Uses smart detection to find story files:
        1. EPIC.md - parsed for epic info + inline story summaries
        2. US-*.md or story-*.md - explicit story files (filename match)
        3. Other .md files - checked for story content markers

        Args:
            directory: Path to directory containing markdown files.

        Returns:
            List of UserStory entities from all files.
        """
        all_stories: list[UserStory] = []
        story_by_id: dict[str, UserStory] = {}

        # First parse EPIC.md if it exists (may contain inline story summaries)
        epic_file = directory / "EPIC.md"
        if epic_file.exists():
            content = epic_file.read_text(encoding="utf-8")
            self._detected_format = self._detect_format(content)
            epic_stories = self._parse_all_stories(content)
            for story in epic_stories:
                story_id = str(story.id) if story.id else ""
                if story_id:
                    story_by_id[story_id] = story
            self.logger.debug(f"Parsed {len(epic_stories)} stories from EPIC.md")

        # Find story files using smart detection
        story_files = sorted(
            f
            for f in directory.glob("*.md")
            if f.name.lower() != "epic.md" and self._is_story_file(f)
        )

        for story_file in story_files:
            content = story_file.read_text(encoding="utf-8")
            self._detected_format = self._detect_format(content)
            stories_in_file = self._parse_all_stories(content)

            for story in stories_in_file:
                story_id = str(story.id) if story.id else ""
                if story_id:
                    # Individual file takes precedence over EPIC.md
                    story_by_id[story_id] = story
                else:
                    # No ID, just add it
                    all_stories.append(story)

            self.logger.debug(f"Parsed {len(stories_in_file)} stories from {story_file.name}")

        # Combine: stories with IDs from dict + stories without IDs
        all_stories = list(story_by_id.values()) + all_stories
        self.logger.debug(f"Total: {len(all_stories)} unique stories from directory")
        return all_stories

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

    def parse_directory(self, directory: str | Path) -> list[UserStory]:
        """
        Parse all user story files from a directory.

        Looks for files matching patterns:
        - US-*.md (individual story files)
        - EPIC.md (optional, for epic metadata)

        The EPIC.md file, if present, is parsed first to extract any inline
        story summaries, but individual US-*.md files take precedence.

        Args:
            directory: Path to directory containing markdown files

        Returns:
            List of UserStory entities from all files
        """
        dir_path = Path(directory) if isinstance(directory, str) else directory

        if not dir_path.is_dir():
            self.logger.error(f"Not a directory: {dir_path}")
            return []

        stories: list[UserStory] = []
        story_ids_seen: set[str] = set()

        # Find all US-*.md files
        story_files = sorted(dir_path.glob("US-*.md"))
        self.logger.info(f"Found {len(story_files)} story files in {dir_path}")

        # Parse each story file
        for story_file in story_files:
            self.logger.debug(f"Parsing {story_file.name}")
            file_stories = self.parse_stories(story_file)

            for story in file_stories:
                if str(story.id) not in story_ids_seen:
                    stories.append(story)
                    story_ids_seen.add(str(story.id))
                else:
                    self.logger.warning(
                        f"Duplicate story {story.id} in {story_file.name}, skipping"
                    )

        # If no individual story files found, try EPIC.md
        if not stories:
            epic_file = dir_path / "EPIC.md"
            if epic_file.exists():
                self.logger.info("No US-*.md files found, parsing EPIC.md")
                stories = self.parse_stories(epic_file)

        self.logger.info(f"Parsed {len(stories)} stories from directory")
        return stories

    def parse_epic_directory(self, directory: str | Path) -> Epic | None:
        """
        Parse an epic and its stories from a directory.

        Looks for:
        - EPIC.md for epic metadata (title, description)
        - US-*.md files for individual stories

        Args:
            directory: Path to directory containing markdown files

        Returns:
            Epic entity with all parsed stories, or None if no stories found
        """
        dir_path = Path(directory) if isinstance(directory, str) else directory

        if not dir_path.is_dir():
            self.logger.error(f"Not a directory: {dir_path}")
            return None

        # Try to parse epic metadata from EPIC.md
        epic_title = "Untitled Epic"
        epic_key = IssueKey("EPIC-0")
        epic_summary = ""
        epic_description = ""

        epic_file = dir_path / "EPIC.md"
        if epic_file.exists():
            content = epic_file.read_text(encoding="utf-8")

            # Extract epic title from first heading
            title_match = re.search(r"^#\s+(?:Epic:\s*)?(.+)$", content, re.MULTILINE)
            if title_match:
                epic_title = title_match.group(1).strip()

            # Try to extract epic ID from metadata
            # Format: > **Epic ID**: NDP-OC-001 or **Epic ID**: NDP-OC-001
            id_match = re.search(r"(?:>\s*)?\*\*Epic\s*ID\*\*:\s*(\S+)", content, re.IGNORECASE)
            if id_match:
                epic_key = IssueKey(id_match.group(1).strip())

            # Extract Epic Name as summary
            name_match = re.search(
                r"(?:>\s*)?\*\*Epic\s*Name\*\*:\s*(.+?)(?:\s*$|\n)", content, re.IGNORECASE
            )
            if name_match:
                epic_summary = name_match.group(1).strip()

            # Extract Epic Description section (everything between ## Epic Description and next ##)
            desc_match = re.search(
                r"##\s*Epic\s*Description\s*\n(.*?)(?=\n##\s|\Z)",
                content,
                re.IGNORECASE | re.DOTALL,
            )
            if desc_match:
                epic_description = desc_match.group(1).strip()

        # Parse all stories from directory
        stories = self.parse_directory(dir_path)

        if not stories:
            return None

        return Epic(
            key=epic_key,
            title=epic_title,
            summary=epic_summary,
            description=epic_description,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        content = self._get_content(source)
        errors = []

        # Check for story pattern using flexible pattern
        story_matches = list(re.finditer(self.STORY_PATTERN_FLEXIBLE, content))
        if not story_matches:
            story_matches = list(re.finditer(self.STORY_PATTERN, content))

        if not story_matches:
            errors.append(
                "No user stories found matching pattern '### [emoji] US-XXX: Title' or '### US-XXX: Title'"
            )

        # Validate each story
        for i, match in enumerate(story_matches):
            story_id = match.group(1)
            start = match.end()
            end = story_matches[i + 1].start() if i + 1 < len(story_matches) else len(content)
            story_content = content[start:end]

            # Check for required fields - both formats accepted
            has_story_points_table = bool(
                re.search(r"\|\s*\*\*Story Points\*\*\s*\|", story_content)
            )
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

        # Detect format to choose appropriate pattern
        detected_format = self._detect_format(content)

        # For standalone files with h1 headers, try h1 pattern first
        if detected_format == self.FORMAT_STANDALONE:
            story_matches = list(re.finditer(self.STORY_PATTERN_H1, content, re.MULTILINE))
            if story_matches:
                self.logger.debug(f"Found {len(story_matches)} stories using h1 pattern")
                for match in story_matches:
                    story_id = match.group(1)
                    title = match.group(2).strip()
                    # Remove trailing emoji/status indicators from title
                    title = re.sub(r"\s*[✅🔲🟡⏸️]+\s*$", "", title).strip()

                    # For h1 files, content is everything after the header
                    start = match.end()
                    end = len(content)  # h1 stories are typically one per file
                    story_content = content[start:end]

                    try:
                        story = self._parse_story(story_id, title, story_content)
                        if story:
                            stories.append(story)
                    except Exception as e:
                        self.logger.warning(f"Failed to parse {story_id}: {e}")

                return stories

        # Try flexible h3 pattern first, then fall back to strict pattern
        story_matches = list(re.finditer(self.STORY_PATTERN_FLEXIBLE, content))
        if not story_matches:
            story_matches = list(re.finditer(self.STORY_PATTERN, content))

        self.logger.debug(f"Found {len(story_matches)} stories using h3 pattern")

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

        # Extract comments
        comments = self._extract_comments(content)

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
            comments=comments,
        )

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """
        Extract field value from markdown - supports table, inline, and blockquote formats.

        Format A (Table): | **Field** | Value |
        Format B (Inline): **Field**: Value
        Format C (Blockquote): > **Field**: Value
        """
        # Build list of field name variants to try
        field_variants = [field_name]

        # Add alias for Story Points -> Points
        if field_name == "Story Points":
            field_variants.append("Points")
        elif field_name == "Points":
            field_variants.append("Story Points")

        for variant in field_variants:
            # Try table format first: | **Field** | Value |
            table_pattern = rf"\|\s*\*\*{variant}\*\*\s*\|\s*([^|]+)\s*\|"
            match = re.search(table_pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()

            # Try blockquote format: > **Field**: Value
            blockquote_pattern = rf">\s*\*\*{variant}\*\*:\s*(.+?)(?:\s*$)"
            match = re.search(blockquote_pattern, content, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()

            # Try inline format: **Field**: Value (not in blockquote)
            inline_pattern = rf"(?<!>)\s*\*\*{variant}\*\*:\s*(.+?)(?:\s*$|\s{{2,}}|\n)"
            match = re.search(inline_pattern, content, re.MULTILINE | re.IGNORECASE)
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
        user_story_section = re.search(r"#### User Story\n([\s\S]*?)(?=####|\n---|\Z)", content)

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
        """Extract acceptance criteria checkboxes.

        Supports multiple section header levels:
        - #### Acceptance Criteria (h4)
        - ### Acceptance Criteria (h3)
        - ## Acceptance Criteria (h2)
        """
        items = []
        checked = []

        # Try different header levels (h4, h3, h2)
        section = None
        for pattern in [
            r"#{2,4}\s*Acceptance Criteria\n([\s\S]*?)(?=#{2,4}|\n---|\Z)",
        ]:
            section = re.search(pattern, content, re.IGNORECASE)
            if section:
                break

        if section:
            for match in re.finditer(r"- \[([ xX])\]\s*(.+)", section.group(1)):
                checked.append(match.group(1).lower() == "x")
                items.append(match.group(2).strip())

        return AcceptanceCriteria.from_list(items, checked)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks from table.

        Supports multiple table formats:
        - Format A: | # | Subtask | Description | SP | Status |
        - Format B: | ID | Task | Status | Deliverable |
        - Format C: | ID | Task | Status | Notes |
        """
        subtasks = []

        # Try different header levels (h4, h3, h2)
        section = None
        for pattern in [
            r"#{2,4}\s*Subtasks\n([\s\S]*?)(?=#{2,4}|\n---|\Z)",
        ]:
            section = re.search(pattern, content, re.IGNORECASE)
            if section:
                break

        if not section:
            return subtasks

        section_content = section.group(1)

        # Format A: | # | Subtask | Description | SP | Status |
        pattern_a = r"\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\s*\|"
        matches_a = list(re.finditer(pattern_a, section_content))
        if matches_a:
            for match in matches_a:
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

        # Format B: | ID | Task | Status | Est. | (Est. is story points)
        # ID format: US-001-01 or just 01
        # Check if header contains "Est" to detect this format
        has_est_column = re.search(r"\|\s*Est\.?\s*\|", section_content, re.IGNORECASE)
        pattern_b = r"\|\s*(?:US-\d+-)?(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|"
        matches_b = list(re.finditer(pattern_b, section_content))
        if matches_b:
            for match in matches_b:
                number_str = match.group(1)
                # Skip header row (if number is not numeric)
                if not number_str.isdigit():
                    continue

                col4 = match.group(4).strip()

                # Determine if 4th column is story points or description
                if has_est_column and col4.isdigit():
                    # Est. column = story points
                    subtasks.append(
                        Subtask(
                            number=int(number_str),
                            name=match.group(2).strip(),
                            description="",  # No description in this format
                            story_points=int(col4),
                            status=Status.from_string(match.group(3)),
                        )
                    )
                else:
                    # Notes/Deliverable column = description
                    subtasks.append(
                        Subtask(
                            number=int(number_str),
                            name=match.group(2).strip(),
                            description=col4,
                            story_points=0,
                            status=Status.from_string(match.group(3)),
                        )
                    )
            return subtasks

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

    def _extract_comments(self, content: str) -> list["Comment"]:
        """
        Extract comments from the Comments section.

        Supported formats:
        > **@username** (2025-01-15):
        > Comment body that can span
        > multiple lines.

        > Comment without author/date

        Returns:
            List of Comment objects
        """
        from datetime import datetime

        from spectra.core.domain.entities import Comment

        comments = []

        section = re.search(r"#### Comments\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if not section:
            return comments

        section_content = section.group(1)

        # Split into individual comment blocks (separated by blank lines or new blockquotes)
        # Pattern: blockquote blocks starting with >
        comment_blocks = re.split(r"\n\s*\n(?=>)", section_content.strip())

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

            # Try to extract author and date from first line
            # Format: **@username** (YYYY-MM-DD):
            author = None
            created_at = None
            body = full_text

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

    def _extract_attachments(self, content: str) -> list[str]:
        """
        Extract attachment references from the Attachments section.

        Format:
        #### Attachments
        - [filename.png](./path/to/file.png)
        - [doc.pdf](attachments/doc.pdf)

        Returns:
            List of file paths
        """
        attachments = []

        section = re.search(r"#### Attachments\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if section:
            # Match markdown links: [name](path)
            pattern = r"[-*]\s*\[([^\]]+)\]\(([^)]+)\)"
            for match in re.finditer(pattern, section.group(1)):
                path = match.group(2).strip()
                attachments.append(path)

        return attachments
