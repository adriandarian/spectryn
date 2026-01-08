"""
Markdown Parser - Parse markdown epic files into domain entities.

Implements the DocumentParserPort interface.
Supports both single-epic and multi-epic formats.

Enhanced with tolerant parsing for:
- Multiple formatting variants (table, inline, blockquote)
- Case-insensitive field and section names
- Field name aliases (Story Points / Points / SP)
- Flexible whitespace handling
- Precise parse error reporting with line numbers
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    CommitRef,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort

from .parser_utils import parse_blockquote_comments
from .tolerant_markdown import (
    ParseErrorCode,
    ParseErrorInfo,
    ParseLocation,
    ParseResult,
    ParseWarning,
    TolerantFieldExtractor,
    TolerantPatterns,
    TolerantSectionExtractor,
    get_context_lines,
    get_line_number,
    location_from_match,
    parse_checkboxes_tolerant,
    parse_description_tolerant,
    parse_inline_subtasks,
)


class MarkdownParser(DocumentParserPort):
    """
    Parser for markdown epic files.

    Supports multiple markdown formats with auto-detection.
    Story IDs can use any PREFIX-NUMBER format (e.g., US-001, EU-042, PROJ-123, FEAT-001).

    FORMAT A (Table-based metadata):
    --------------------------------
    ### [emoji] PROJ-001: Title

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
    ### PROJ-001: Title

    **Priority**: P0
    **Story Points**: 5
    **Status**: ✅ Complete

    #### User Story
    > **As a** role,
    > **I want** feature,
    > **So that** benefit.

    FORMAT C (Standalone file with h1 header and blockquote metadata):
    ------------------------------------------------------------------
    # PROJ-001: Title [emoji]

    > **Story ID**: PROJ-001
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
    ### PROJ-001: Title
    ...

    Multi-File Format:
    ------------------
    A directory containing:
    - EPIC.md (optional, with epic metadata)
    - PROJ-001-*.md, PROJ-002-*.md, etc. (individual story files)

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

    # Generic story ID pattern supporting multiple formats:
    # - PREFIX-NUMBER: US-001, EU-042, PROJ-123, FEAT-001 (hyphen separator)
    # - PREFIX_NUMBER: PROJ_001, US_123 (underscore separator)
    # - PREFIX/NUMBER: PROJ/001, US/123 (forward slash separator)
    # - #NUMBER: #123, #42 (GitHub-style numeric IDs)
    # - NUMBER: 123, 42 (purely numeric IDs) - only in specific contexts
    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    # Extended pattern that also accepts purely numeric IDs (for h1/standalone files)
    STORY_ID_PATTERN_EXTENDED = r"(?:[A-Z]+[-_/]\d+|#?\d+)"

    # Story patterns - flexible to match multiple header levels and formats
    # Matches: ### ✅ PROJ-001: Title  OR  ### US-001: Title (h3)
    STORY_PATTERN = rf"### (?:[^\n]+ )?({STORY_ID_PATTERN}): ([^\n]+)\n"
    STORY_PATTERN_FLEXIBLE = rf"### (?:.*?)?({STORY_ID_PATTERN}):\s*([^\n]+)\n"

    # Standalone story pattern for h1 headers: # PROJ-001: Title [emoji] or # US-001: Title
    # Also supports #123 and purely numeric IDs in standalone files
    STORY_PATTERN_H1 = (
        rf"^#\s+(?:.*?)?({STORY_ID_PATTERN_EXTENDED}):\s*([^\n]+?)(?:\s*[✅🔲🟡⏸️]+)?\s*$"
    )

    EPIC_TITLE_PATTERN = r"^#\s+[^\n]+\s+([^\n]+)$"
    # Multi-epic pattern: ## Epic: PROJ-100 - Epic Title or ## Epic: PROJ-100
    # Supports custom separators: PROJ-100, PROJ_100, PROJ/100
    MULTI_EPIC_PATTERN = r"^##\s+Epic:\s*([A-Z]+[-_/]\d+)(?:\s*[-–—]\s*(.+))?$"

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
        """Return the parser name for display purposes."""
        return "Markdown"

    @property
    def supported_extensions(self) -> list[str]:
        """Return list of file extensions this parser can handle."""
        return [".md", ".markdown"]

    def can_parse(self, source: str | Path) -> bool:
        """
        Check if this parser can handle the given source.

        Args:
            source: File path or content string to check.

        Returns:
            True if the source is a markdown file or contains story patterns.
        """
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
        # Check for standalone file format (h1 header with PREFIX-NUMBER story ID)
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
        """
        Parse user stories from a markdown source.

        Supports both single files and directories containing multiple story files.

        Args:
            source: File path, directory path, or markdown content string.

        Returns:
            List of parsed UserStory objects.
        """
        # Handle directory input - parse all US-*.md files
        # Only try path operations if source is already a Path or looks like a valid path
        # (short string without newlines - actual content has newlines)
        if isinstance(source, Path):
            if source.is_dir():
                return self._parse_stories_from_directory(source)
        elif isinstance(source, str) and "\n" not in source and len(source) < 4096:
            try:
                source_path = Path(source)
                if source_path.is_dir():
                    return self._parse_stories_from_directory(source_path)
            except OSError:
                # Invalid path characters or other OS-level path issues
                pass

        content = self._get_content(source)
        self._detected_format = self._detect_format(content)
        self.logger.debug(f"Detected markdown format: {self._detected_format}")
        return self._parse_all_stories(content)

    def parse_stories_tolerant(
        self, source: str | Path, source_name: str | None = None
    ) -> ParseResult:
        """
        Parse user stories with tolerant parsing and detailed error reporting.

        This method is more forgiving of formatting variants and provides
        precise error locations for debugging. Use this when you want
        detailed diagnostics about the parse process.

        Args:
            source: File path, directory path, or markdown content string.
            source_name: Optional name for error reporting (defaults to file path).

        Returns:
            ParseResult with stories, errors, and warnings.

        Example:
            >>> parser = MarkdownParser()
            >>> result = parser.parse_stories_tolerant("# Epic\\n### US-001: Story...")
            >>> if result.errors:
            ...     for error in result.errors:
            ...         print(f"Line {error.line}: {error.message}")
            >>> stories = result.stories
        """
        # Determine source name for error reporting
        if source_name is None:
            if isinstance(source, Path):
                source_name = str(source)
            elif isinstance(source, str) and "\n" not in source and len(source) < 256:
                source_name = source  # Likely a file path

        content = self._get_content(source)
        self._detected_format = self._detect_format(content)

        return self._parse_all_stories_tolerant(content, source_name)

    def _parse_all_stories_tolerant(self, content: str, source: str | None = None) -> ParseResult:
        """
        Parse all stories with tolerant parsing and error collection.

        Args:
            content: Markdown content to parse
            source: Source file path for error reporting

        Returns:
            ParseResult with stories, errors, and warnings
        """
        result = ParseResult(source=source)

        # Detect format
        detected_format = self._detect_format(content)
        self.logger.debug(f"Detected format: {detected_format} for tolerant parse")

        # Find all story headers
        story_matches: list[tuple[re.Match[str], str]] = []

        if detected_format == self.FORMAT_STANDALONE:
            # Try h1 pattern for standalone files
            for match in TolerantPatterns.STORY_HEADER_H1.finditer(content):
                story_matches.append((match, "h1"))
        else:
            # Try h3 patterns
            for match in TolerantPatterns.STORY_HEADER.finditer(content):
                story_matches.append((match, "h3"))

        if not story_matches:
            result.errors.append(
                ParseErrorInfo(
                    message="No user stories found in document",
                    location=ParseLocation(line=1, source=source),
                    context=get_context_lines(content, 1, before=0, after=3),
                    suggestion="Stories should start with '### STORY-ID: Title' (e.g., ### US-001: My Story)",
                    code=ParseErrorCode.NO_STORIES,
                )
            )
            return result

        # Track seen story IDs for duplicate detection
        seen_ids: dict[str, int] = {}

        # Parse each story
        for i, (match, _header_type) in enumerate(story_matches):
            story_id = match.group(1)
            title = match.group(2).strip()

            # Clean title of trailing emoji/status
            title = re.sub(r"\s*[✅🔲🟡⏸️🔄📋]+\s*$", "", title).strip()

            # Check for duplicates
            if story_id in seen_ids:
                location = location_from_match(content, match, source)
                result.warnings.append(
                    ParseWarning(
                        message=f"Duplicate story ID '{story_id}' (first seen at line {seen_ids[story_id]})",
                        location=location,
                        suggestion="Use a unique story ID",
                        code=ParseErrorCode.DUPLICATE_STORY_ID,
                    )
                )
            else:
                seen_ids[story_id] = get_line_number(content, match.start())

            # Determine content boundaries
            start = match.end()
            end = story_matches[i + 1][0].start() if i + 1 < len(story_matches) else len(content)
            story_content = content[start:end]

            # Parse story with tolerant methods
            try:
                story, story_warnings = self._parse_story_tolerant(
                    story_id, title, story_content, source
                )
                if story:
                    result.stories.append(story)
                result.warnings.extend(story_warnings)
            except Exception as e:
                location = location_from_match(content, match, source)
                result.errors.append(
                    ParseErrorInfo(
                        message=f"Failed to parse story '{story_id}': {e}",
                        location=location,
                        context=get_context_lines(content, location.line),
                        code="PARSE_EXCEPTION",
                    )
                )

        return result

    def _parse_story_tolerant(
        self, story_id: str, title: str, content: str, source: str | None = None
    ) -> tuple[UserStory | None, list[ParseWarning]]:
        """
        Parse a single story with tolerant extraction and warning collection.

        Args:
            story_id: Story identifier
            title: Story title
            content: Story content block
            source: Source file for error reporting

        Returns:
            Tuple of (UserStory or None, list of warnings)
        """
        warnings: list[ParseWarning] = []

        # Use tolerant field extractor
        field_extractor = TolerantFieldExtractor(content, source)

        # Extract fields with tolerance
        story_points_str, _ = field_extractor.extract_field("Story Points", "0")
        priority_str, _ = field_extractor.extract_field("Priority", "Medium")
        status_str, _ = field_extractor.extract_field("Status", "Planned")
        warnings.extend(field_extractor.warnings)

        # Parse story points with validation
        try:
            story_points = int(story_points_str) if story_points_str.isdigit() else 0
        except ValueError:
            warnings.append(
                ParseWarning(
                    message=f"Invalid story points value '{story_points_str}', using 0",
                    location=ParseLocation(line=1, source=source),
                    suggestion="Story Points should be a number (e.g., 3, 5, 8)",
                    code=ParseErrorCode.INVALID_STORY_POINTS,
                )
            )
            story_points = 0

        # Extract description with tolerance
        desc_dict, desc_warnings = parse_description_tolerant(content, source)
        warnings.extend(desc_warnings)

        description = None
        if desc_dict:
            description = Description(
                role=desc_dict.get("role", ""),
                want=desc_dict.get("want", ""),
                benefit=desc_dict.get("benefit", ""),
            )

        # Extract acceptance criteria with tolerance
        section_extractor = TolerantSectionExtractor(content, source)
        ac_content, _ = section_extractor.extract_section("Acceptance Criteria")
        warnings.extend(section_extractor.warnings)

        ac_items, ac_warnings = (
            parse_checkboxes_tolerant(ac_content, source) if ac_content else ([], [])
        )
        warnings.extend(ac_warnings)

        acceptance = AcceptanceCriteria.from_list(
            [item[0] for item in ac_items],
            [item[1] for item in ac_items],
        )

        # Extract subtasks (use existing method)
        subtasks = self._extract_subtasks(content)

        # Extract commits (use existing method)
        commits = self._extract_commits(content)

        # Extract technical notes (use existing method)
        tech_notes = self._extract_technical_notes(content)

        # Extract links (use existing method)
        links = self._extract_links(content)

        # Extract comments (use existing method)
        comments = self._extract_comments(content)

        # Extract tracker info (use existing method)
        external_key, external_url, last_synced, sync_status, content_hash = (
            self._extract_tracker_info(content)
        )

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=tech_notes,
            story_points=story_points,
            priority=Priority.from_string(priority_str),
            status=Status.from_string(status_str),
            subtasks=subtasks,
            commits=commits,
            links=links,
            comments=comments,
            external_key=IssueKey(external_key) if external_key else None,
            external_url=external_url,
            last_synced=last_synced,
            sync_status=sync_status,
            content_hash=content_hash,
        ), warnings

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

        # Filename pattern match (fast path) - any PREFIX-SEPARATOR-NUMBER format
        # Matches: us-001.md, eu_042.md, proj-123.md, story_001.md, etc.
        # Also matches purely numeric: 123.md
        if re.match(r"^(?:[a-z]+[-_]\d+|\d+)", name_lower):
            return True

        # Content-based detection (slower but more reliable)
        try:
            content = file_path.read_text(encoding="utf-8")
            # Check for story header patterns
            # Support custom separators: PREFIX-NUM, PREFIX_NUM, PREFIX/NUM, #NUM
            story_markers = [
                r"^#{1,3}\s+.*(?:[A-Z]+[-_/]\d+|#\d+):",  # Story ID header
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
        """
        Parse a single epic from markdown source.

        Extracts epic title from the first H1 heading and parses all user stories
        within. If the source contains multiple epics, returns only the first one.

        Args:
            source: File path or markdown content string.

        Returns:
            Epic object if stories are found, None otherwise.

        Example:
            >>> parser = MarkdownParser()
            >>> epic = parser.parse_epic("# PROJ-100 My Epic\\n### STORY-001...")
        """
        content = self._get_content(source)

        # Check if this is a multi-epic file
        if self.is_multi_epic(content):
            epics = self.parse_epics(content)
            return epics[0] if epics else None

        # Extract epic title from first heading
        # Supports custom separators: PROJ-123, PROJ_123, PROJ/123, #123
        title_match = re.search(r"^#\s+[^\n]*?([A-Z]+[-_/]\d+|#\d+)?.*$", content, re.MULTILINE)
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
        ### STORY-001: Story 1
        ...

        ## Epic: PROJ-200 - Epic Title 2
        ### STORY-002: Story 2
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
            # Supports custom separators: PROJ-123, PROJ_123, PROJ/123
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
        """
        Validate markdown source for structural correctness.

        Checks for:
        - At least one user story present
        - Required fields (Story Points, description with "As a")

        Args:
            source: File path or markdown content string.

        Returns:
            List of validation error messages. Empty list if valid.

        Example:
            >>> parser = MarkdownParser()
            >>> errors = parser.validate("# Empty file")
            >>> len(errors) > 0
            True
        """
        content = self._get_content(source)
        errors = []

        # Check for story pattern using flexible pattern
        story_matches = list(re.finditer(self.STORY_PATTERN_FLEXIBLE, content))
        if not story_matches:
            story_matches = list(re.finditer(self.STORY_PATTERN, content))

        if not story_matches:
            errors.append(
                "No user stories found matching pattern '### [emoji] ID: Title' "
                "(e.g., US-001, PROJ_123, FEAT/001, #123)"
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

    def validate_detailed(
        self, source: str | Path, source_name: str | None = None
    ) -> tuple[list[ParseErrorInfo], list[ParseWarning]]:
        """
        Validate markdown source with precise error locations.

        Enhanced validation that provides line numbers, column positions,
        and context for each error or warning.

        Args:
            source: File path or markdown content string.
            source_name: Optional source identifier for error reporting.

        Returns:
            Tuple of (errors, warnings) with detailed location information.

        Example:
            >>> parser = MarkdownParser()
            >>> errors, warnings = parser.validate_detailed("# Empty file")
            >>> for error in errors:
            ...     print(f"Line {error.line}: {error.message}")
        """
        content = self._get_content(source)

        # Determine source name
        if source_name is None:
            if isinstance(source, Path):
                source_name = str(source)

        errors: list[ParseErrorInfo] = []
        warnings: list[ParseWarning] = []

        # Check for story pattern using tolerant patterns
        story_matches = list(TolerantPatterns.STORY_HEADER.finditer(content))
        if not story_matches:
            story_matches = list(TolerantPatterns.STORY_HEADER_H1.finditer(content))

        if not story_matches:
            errors.append(
                ParseErrorInfo(
                    message="No user stories found in document",
                    location=ParseLocation(line=1, source=source_name),
                    context=get_context_lines(content, 1, before=0, after=5),
                    suggestion=(
                        "Add a story header like '### US-001: Story Title' or "
                        "'# PROJ-001: Story Title' for standalone files"
                    ),
                    code=ParseErrorCode.NO_STORIES,
                )
            )
            return errors, warnings

        # Validate each story
        for i, match in enumerate(story_matches):
            story_id = match.group(1)
            story_line = get_line_number(content, match.start())
            start = match.end()
            end = story_matches[i + 1].start() if i + 1 < len(story_matches) else len(content)
            story_content = content[start:end]

            # Use tolerant extractor to check fields
            extractor = TolerantFieldExtractor(story_content, source_name)

            # Check Story Points
            points_value, points_location = extractor.extract_field("Story Points")
            if not points_value:
                errors.append(
                    ParseErrorInfo(
                        message=f"Missing Story Points field in story '{story_id}'",
                        location=ParseLocation(line=story_line, source=source_name),
                        context=get_context_lines(content, story_line, after=5),
                        suggestion=(
                            "Add '| **Story Points** | 3 |' in a table or "
                            "'**Story Points**: 3' inline"
                        ),
                        code=ParseErrorCode.MISSING_REQUIRED_FIELD,
                    )
                )
            elif not points_value.isdigit():
                line = points_location.line if points_location else story_line
                warnings.append(
                    ParseWarning(
                        message=f"Story Points '{points_value}' is not a valid number in '{story_id}'",
                        location=ParseLocation(line=line, source=source_name),
                        suggestion="Story Points should be a whole number (e.g., 1, 2, 3, 5, 8)",
                        code=ParseErrorCode.INVALID_STORY_POINTS,
                    )
                )

            # Check description
            desc_dict, desc_warnings = parse_description_tolerant(story_content, source_name)
            if not desc_dict:
                warnings.append(
                    ParseWarning(
                        message=f"Missing user story description in '{story_id}'",
                        location=ParseLocation(line=story_line, source=source_name),
                        suggestion=(
                            "Add '**As a** [role] **I want** [feature] **So that** [benefit]'"
                        ),
                        code=ParseErrorCode.INCOMPLETE_DESCRIPTION,
                    )
                )
            else:
                warnings.extend(desc_warnings)

            # Collect extractor warnings
            warnings.extend(extractor.warnings)

        return errors, warnings

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _get_content(self, source: str | Path) -> str:
        """
        Get content from file path or raw string.

        Automatically detects whether source is a file path or raw content.
        If source is a Path or a short string without newlines that exists
        as a file, reads and returns file contents.

        Args:
            source: File path (Path or str) or raw markdown content.

        Returns:
            Raw markdown content string.

        Raises:
            OSError: If file path exists but cannot be read.
        """
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
        """
        Parse all user stories from markdown content.

        Detects the markdown format (table, inline, standalone) and uses
        the appropriate parsing strategy. Handles both H1 and H3 story headers.

        Args:
            content: Raw markdown content containing story definitions.

        Returns:
            List of parsed UserStory objects. May be empty if no stories found.
        """
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
        """
        Parse a single user story from a content block.

        Extracts all story fields including metadata, acceptance criteria,
        subtasks, commits, technical notes, links, comments, and sync info.

        Args:
            story_id: The story identifier (e.g., "US-001", "PROJ_123").
            title: The story title from the header.
            content: The markdown content block for this story.

        Returns:
            Fully populated UserStory object, or None if parsing fails.
        """
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

        # Extract tracker info (external key, URL, sync metadata)
        external_key, external_url, last_synced, sync_status, content_hash = (
            self._extract_tracker_info(content)
        )

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
            external_key=IssueKey(external_key) if external_key else None,
            external_url=external_url,
            last_synced=last_synced,
            sync_status=sync_status,
            content_hash=content_hash,
        )

    def _extract_field(self, content: str, field_name: str, default: str = "") -> str:
        """
        Extract field value from markdown content.

        Supports multiple formats:
        - Table format: | **Field** | Value |
        - Inline format: **Field**: Value
        - Blockquote format: > **Field**: Value

        Also handles field aliases (e.g., "Story Points" / "Points").

        Args:
            content: Markdown content to search.
            field_name: Name of the field to extract.
            default: Default value if field is not found.

        Returns:
            Extracted field value, or default if not found.
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
        """Extract subtasks from table or inline checkboxes.

        Supports multiple formats:
        - Table Format A: | # | Subtask | Description | SP | Status |
        - Table Format B: | ID | Task | Status | Deliverable |
        - Table Format C: | ID | Task | Status | Notes |
        - Inline Format: - [ ] Task name or - [x] Completed task

        Inline checkbox format supports:
        - [ ] Task name
        - [x] Completed task (status = Done)
        - [ ] Task name (2 SP) - with story points
        - [ ] Task name - description text
        """
        subtasks: list[Subtask] = []

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

        # First, try to extract from table formats
        table_subtasks = self._extract_subtasks_from_table(section_content)
        if table_subtasks:
            return table_subtasks

        # If no table subtasks found, try inline checkbox format
        inline_subtasks = self._extract_subtasks_from_checkboxes(section_content)
        if inline_subtasks:
            return inline_subtasks

        return subtasks

    def _extract_subtasks_from_table(self, section_content: str) -> list[Subtask]:
        """Extract subtasks from table format.

        Supports:
        - Format A: | # | Subtask | Description | SP | Status |
        - Format B: | ID | Task | Status | Est. |
        - Format C: | ID | Task | Status | Notes |
        """
        subtasks: list[Subtask] = []

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
        # ID format: STORY-001-01 or just 01
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

    def _extract_subtasks_from_checkboxes(self, section_content: str) -> list[Subtask]:
        """Extract subtasks from inline checkbox format.

        Supports:
        - [ ] Task name
        - [x] Completed task
        - [ ] Task name (2 SP)
        - [ ] Task name - description text
        - [ ] **Bold task name**
        """
        subtasks: list[Subtask] = []

        inline_subtask_infos, _warnings = parse_inline_subtasks(section_content)

        for idx, info in enumerate(inline_subtask_infos, start=1):
            # Map checkbox status to Status enum
            status = Status.DONE if info.checked else Status.PLANNED

            subtasks.append(
                Subtask(
                    number=idx,
                    name=info.name,
                    description=info.description,
                    story_points=info.story_points,
                    status=status,
                )
            )

        return subtasks

    def _extract_commits(self, content: str) -> list[CommitRef]:
        """
        Extract commit references from a "Related Commits" section.

        Looks for a table with format: | `hash` | message |

        Args:
            content: Markdown content to search.

        Returns:
            List of CommitRef objects with hash and message.
        """
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
        """
        Extract technical notes section content.

        Looks for a "#### Technical Notes" section.

        Args:
            content: Markdown content to search.

        Returns:
            Technical notes text, or empty string if not found.
        """
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

        # Issue key pattern supporting all separator types and numeric IDs
        issue_key_pattern = r"(?:[A-Z]+[-_/]\d+|#\d+)"

        if section:
            section_content = section.group(1)
            # Parse table rows: | link_type | target_key |
            # Support custom separators: PROJ-123, PROJ_123, PROJ/123, #123
            table_pattern = rf"\|\s*([^|]+)\s*\|\s*({issue_key_pattern})\s*\|"
            for match in re.finditer(table_pattern, section_content):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                if target_key and not link_type.startswith("-"):
                    links.append((link_type, target_key))

            # Parse bullet list: - blocks: PROJ-123
            bullet_pattern = rf"[-*]\s*(blocks|blocked by|relates to|depends on|duplicates)[:\s]+({issue_key_pattern})"
            for match in re.finditer(bullet_pattern, section_content, re.IGNORECASE):
                link_type = match.group(1).strip().lower()
                target_key = match.group(2).strip()
                links.append((link_type, target_key))

        # Pattern for inline links: **Blocks:** PROJ-123, PROJ-456
        # Support custom separators and #123 format
        inline_patterns = [
            (
                rf"\*\*Blocks[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "blocks",
            ),
            (
                rf"\*\*Blocked by[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "blocked by",
            ),
            (
                rf"\*\*Depends on[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "depends on",
            ),
            (
                rf"\*\*Related to[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "relates to",
            ),
            (
                rf"\*\*Relates to[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "relates to",
            ),
            (
                rf"\*\*Duplicates[:\s]*\*\*\s*({issue_key_pattern}(?:\s*,\s*{issue_key_pattern})*)",
                "duplicates",
            ),
        ]

        for pattern, link_type in inline_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                keys_str = match.group(1)
                for key in re.findall(issue_key_pattern, keys_str):
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
        section = re.search(r"#### Comments\n([\s\S]*?)(?=####|\n---|\Z)", content)

        if not section:
            return []

        # Use shared utility for parsing blockquote comments
        return parse_blockquote_comments(section.group(1))

    def _extract_tracker_info(
        self, content: str
    ) -> tuple[str | None, str | None, datetime | None, str | None, str | None]:
        """
        Extract tracker information from story content.

        Parses external issue key, URL, and sync metadata from blockquote metadata.

        Supported formats:
        - > **Tracker:** jira
          > **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)
          > **Last Synced:** 2025-01-15 14:30 UTC
          > **Sync Status:** ✅ Synced
          > **Content Hash:** `a1b2c3d4`
        - > **Jira:** [PROJ-123](https://url)  (legacy/shorthand)
        - > **GitHub:** [#123](https://url)
        - > **Linear:** [TEAM-123](https://url)
        - > **Azure:** [123](https://url)

        Args:
            content: Story content block to parse.

        Returns:
            Tuple of (issue_key, issue_url, last_synced, sync_status, content_hash)
            Missing values are None.
        """
        issue_key: str | None = None
        issue_url: str | None = None
        last_synced: datetime | None = None
        sync_status: str | None = None
        content_hash: str | None = None

        # Pattern 1: Explicit Issue field with markdown link
        # > **Issue:** [PROJ-123](https://url)
        # Note: colon is inside the bold markers (**Issue:**)
        issue_match = re.search(
            r">\s*\*\*Issue:\*\*\s*\[([^\]]+)\]\(([^)]+)\)",
            content,
            re.IGNORECASE,
        )
        if issue_match:
            issue_key = issue_match.group(1).strip()
            issue_url = issue_match.group(2).strip()

        # Pattern 2: Tracker-specific shorthand (Jira, GitHub, Linear, Azure)
        # > **Jira:** [PROJ-123](https://url)
        # Note: colon is inside the bold markers (**Jira:**)
        if not issue_key:
            tracker_shorthand = re.search(
                r">\s*\*\*(?:Jira|GitHub|Linear|Azure(?:\s*DevOps)?):\*\*\s*\[([^\]]+)\]\(([^)]+)\)",
                content,
                re.IGNORECASE,
            )
            if tracker_shorthand:
                issue_key = tracker_shorthand.group(1).strip()
                issue_url = tracker_shorthand.group(2).strip()

        # Pattern 3: Just the issue key without link (for manual entries)
        # > **Issue:** PROJ-123 or PROJ_123 or PROJ/123 or #123 or 123
        if not issue_key:
            key_only_match = re.search(
                r">\s*\*\*Issue:\*\*\s*([A-Z]+[-_/]\d+|#?\d+)",
                content,
                re.IGNORECASE,
            )
            if key_only_match:
                issue_key = key_only_match.group(1).strip()

        # Extract Last Synced timestamp
        # > **Last Synced:** 2025-01-15 14:30 UTC
        synced_match = re.search(
            r">\s*\*\*Last Synced:\*\*\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?:\s*UTC)?)",
            content,
            re.IGNORECASE,
        )
        if synced_match:
            try:
                timestamp_str = synced_match.group(1).strip()
                # Parse with or without UTC suffix
                if "UTC" in timestamp_str.upper():
                    timestamp_str = timestamp_str.replace("UTC", "").replace("utc", "").strip()
                last_synced = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            except ValueError:
                pass  # Invalid timestamp format

        # Extract Sync Status
        # > **Sync Status:** ✅ Synced
        # Match optional emoji(s) followed by status word
        status_match = re.search(
            r">\s*\*\*Sync Status:\*\*\s*(?:\S+\s+)?(\w+)",
            content,
            re.IGNORECASE,
        )
        if status_match:
            sync_status = status_match.group(1).strip().lower()

        # Extract Content Hash
        # > **Content Hash:** `a1b2c3d4`
        hash_match = re.search(
            r">\s*\*\*Content Hash:\*\*\s*`([a-f0-9]+)`",
            content,
            re.IGNORECASE,
        )
        if hash_match:
            content_hash = hash_match.group(1).strip()

        return issue_key, issue_url, last_synced, sync_status, content_hash

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
