"""
Base Dict Parser - Abstract base class for dict-based document parsers.

Provides common parsing logic for structured data formats (YAML, JSON, TOML)
that parse into Python dictionaries.

Subclasses only need to implement:
- name property
- supported_extensions property
- _load_data() method for format-specific loading
"""

import logging
import re
from abc import abstractmethod
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


# Common date formats for parsing
COMMON_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%fZ",
]

# Regex pattern for valid issue keys
ISSUE_KEY_PATTERN = re.compile(r"^(?:[A-Z]+[-_/]\d+|#?\d+)$")

# Regex pattern for extracting user story description from string
USER_STORY_PATTERN = re.compile(
    r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)


def parse_datetime(value: str | datetime | None) -> datetime | None:
    """
    Parse a datetime from various string formats.

    Args:
        value: String date, datetime object, or None.

    Returns:
        Parsed datetime or None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    for fmt in COMMON_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class BaseDictParser(DocumentParserPort):
    """
    Abstract base class for dict-based document parsers.

    Provides common parsing logic for YAML, JSON, TOML and similar formats
    that parse source content into Python dictionaries.

    Subclasses must implement:
    - name: Parser name (e.g., "YAML", "JSON")
    - supported_extensions: List of file extensions
    - _load_data(): Format-specific loading logic

    Example subclass:
        class YamlParser(BaseDictParser):
            @property
            def name(self) -> str:
                return "YAML"

            @property
            def supported_extensions(self) -> list[str]:
                return [".yaml", ".yml"]

            def _load_data(self, source: str | Path) -> dict[str, Any]:
                content = self._read_source(source)
                return yaml.safe_load(content) or {}
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self.logger = logging.getLogger(self.__class__.__name__)

    # -------------------------------------------------------------------------
    # Abstract Methods - Subclasses Must Implement
    # -------------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the parser name (e.g., 'YAML', 'JSON', 'TOML')."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Get list of supported file extensions (e.g., ['.yaml', '.yml'])."""
        ...

    @abstractmethod
    def _load_data(self, source: str | Path) -> dict[str, Any]:
        """
        Load data from source into a dictionary.

        This is the only format-specific logic subclasses need to implement.

        Args:
            source: File path or content string.

        Returns:
            Parsed dictionary data.

        Raises:
            ParserError: If loading or parsing fails.
        """
        ...

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid file or content for this parser."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Try to parse as content and check for expected structure
        try:
            data = self._load_data(source)
            if isinstance(data, dict):
                return "stories" in data or "epic" in data
            return False
        except (ParserError, Exception):
            return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from source."""
        data = self._load_data(source)

        stories_data = data.get("stories", [])
        if not stories_data:
            return []

        stories = []
        for story_data in stories_data:
            try:
                story = self._parse_story(story_data)
                if story:
                    stories.append(story)
            except Exception as e:
                story_id = story_data.get("id", "unknown")
                self.logger.warning(f"Failed to parse story {story_id}: {e}")

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from source."""
        data = self._load_data(source)

        # Get epic metadata
        epic_data = data.get("epic", {})
        epic_key = epic_data.get("key", "EPIC-0")
        epic_title = epic_data.get("title", "Untitled Epic")
        epic_description = epic_data.get("description", "")

        # Parse stories
        stories = self.parse_stories(source)

        if not stories and not epic_data:
            return None

        return Epic(
            key=IssueKey(epic_key) if self._is_valid_key(epic_key) else IssueKey("EPIC-0"),
            title=epic_title,
            description=epic_description,
            stories=stories,
        )

    def validate(self, source: str | Path) -> list[str]:
        """Validate source without full parsing."""
        errors: list[str] = []

        try:
            data = self._load_data(source)
        except ParserError as e:
            return [str(e)]

        # Validate structure
        if not isinstance(data, dict):
            errors.append("Root element must be a dictionary/object/table")
            return errors

        # Check for required sections
        if "stories" not in data and "epic" not in data:
            errors.append(f"{self.name} must contain 'stories' or 'epic' key")

        # Validate stories
        stories_data = data.get("stories", [])
        if not isinstance(stories_data, list):
            errors.append("'stories' must be a list/array")
        else:
            for i, story in enumerate(stories_data):
                story_errors = self._validate_story(story, i)
                errors.extend(story_errors)

        # Validate epic
        epic_data = data.get("epic", {})
        if epic_data and not isinstance(epic_data, dict):
            errors.append("'epic' must be a dictionary/object/table")
        elif epic_data and not epic_data.get("title"):
            errors.append("Epic missing required field: 'title'")

        return errors

    # -------------------------------------------------------------------------
    # Helper Methods - Reading Source
    # -------------------------------------------------------------------------

    def _read_source(self, source: str | Path) -> str:
        """
        Read content from source (file path or string).

        Args:
            source: File path or content string.

        Returns:
            Content string.
        """
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8")

        # If string, check if it might be a file path
        if isinstance(source, str) and "\n" not in source and len(source) < 4096:
            try:
                path = Path(source)
                if path.exists() and path.suffix.lower() in self.supported_extensions:
                    return path.read_text(encoding="utf-8")
            except OSError:
                pass

        # Return as content string
        return source

    def _is_valid_key(self, key: str) -> bool:
        """
        Check if a string is a valid issue key.

        Supports:
        - PREFIX-NUMBER: PROJ-123 (hyphen)
        - PREFIX_NUMBER: PROJ_123 (underscore)
        - PREFIX/NUMBER: PROJ/123 (forward slash)
        - #NUMBER: #123 (GitHub-style)
        - NUMBER: 123 (purely numeric)
        """
        upper_key = str(key).upper()
        return bool(ISSUE_KEY_PATTERN.match(upper_key))

    # -------------------------------------------------------------------------
    # Story Parsing
    # -------------------------------------------------------------------------

    def _parse_story(self, data: dict[str, Any]) -> UserStory | None:
        """
        Parse a single story from dict data.

        Accepts any PREFIX-NUMBER format for story IDs (e.g., US-001, EU-042, PROJ-123).
        """
        story_id = data.get("id", "STORY-000")
        title = data.get("title", "Untitled Story")

        # Parse nested structures
        description = self._parse_description(data.get("description"))
        acceptance = self._parse_acceptance_criteria(data.get("acceptance_criteria", []))
        subtasks = self._parse_subtasks(data.get("subtasks", []))
        commits = self._parse_commits(data.get("commits", []))
        links = self._parse_links(data.get("links", []))
        comments = self._parse_comments(data.get("comments", []))

        # Get scalar fields
        story_points = int(data.get("story_points", 0))
        priority = Priority.from_string(data.get("priority", "medium"))
        status = Status.from_string(data.get("status", "planned"))
        tech_notes = data.get("technical_notes", "")

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
            commits=commits,
            links=links,
            comments=comments,
        )

    def _parse_description(self, data: Any) -> Description | None:
        """Parse description from data."""
        if data is None:
            return None

        # Support simple string format
        if isinstance(data, str):
            # Try to extract As a/I want/So that from string
            match = USER_STORY_PATTERN.search(data)
            if match:
                return Description(
                    role=match.group(1).strip(),
                    want=match.group(2).strip(),
                    benefit=match.group(3).strip(),
                )
            # Return as simple description
            return Description(role="", want=data, benefit="")

        # Support structured format
        if isinstance(data, dict):
            return Description(
                role=data.get("as_a", data.get("role", "")),
                want=data.get("i_want", data.get("want", "")),
                benefit=data.get("so_that", data.get("benefit", "")),
            )

        return None

    def _parse_acceptance_criteria(self, data: list[Any]) -> AcceptanceCriteria:
        """Parse acceptance criteria from list data."""
        items: list[str] = []
        checked: list[bool] = []

        for item in data:
            if isinstance(item, str):
                items.append(item)
                checked.append(False)
            elif isinstance(item, dict):
                criterion = item.get("criterion", item.get("text", str(item)))
                done = item.get("done", item.get("checked", False))
                items.append(criterion)
                checked.append(bool(done))

        return AcceptanceCriteria.from_list(items, checked)

    def _parse_subtasks(self, data: list[Any]) -> list[Subtask]:
        """Parse subtasks from list data."""
        subtasks = []

        for i, item in enumerate(data):
            if isinstance(item, str):
                # Simple string format
                subtasks.append(
                    Subtask(
                        number=i + 1,
                        name=item,
                        description="",
                        story_points=1,
                        status=Status.PLANNED,
                    )
                )
            elif isinstance(item, dict):
                # Structured format
                subtasks.append(
                    Subtask(
                        number=item.get("number", i + 1),
                        name=item.get("name", item.get("title", "")),
                        description=item.get("description", ""),
                        story_points=int(item.get("story_points", item.get("sp", 1))),
                        status=Status.from_string(item.get("status", "planned")),
                        assignee=item.get("assignee"),
                    )
                )

        return subtasks

    def _parse_commits(self, data: list[Any]) -> list[CommitRef]:
        """Parse commit references from list data."""
        commits = []

        for item in data:
            if isinstance(item, str):
                # Just a hash
                commits.append(CommitRef(hash=item[:8], message=""))
            elif isinstance(item, dict):
                commits.append(
                    CommitRef(
                        hash=item.get("hash", item.get("sha", ""))[:8],
                        message=item.get("message", ""),
                    )
                )

        return commits

    def _parse_links(self, data: list[Any]) -> list[tuple[str, str]]:
        """
        Parse issue links from list data.

        Supports multiple formats:
        - Simple string: "blocks PROJ-123"
        - Structured: {"type": "blocks", "target": "PROJ-123"}
        - Shorthand: {"blocks": "PROJ-123"} or {"blocks": ["A-1", "B-2"]}

        Returns:
            List of (link_type, target_key) tuples.
        """
        links: list[tuple[str, str]] = []

        for item in data:
            if isinstance(item, str):
                # Parse "blocks PROJ-123" format
                parts = item.strip().split(None, 1)
                if len(parts) == 2:
                    link_type = parts[0].lower().replace("_", " ")
                    target = parts[1].strip()
                    links.append((link_type, target))
            elif isinstance(item, dict):
                # Structured format: {"type": "blocks", "target": "PROJ-123"}
                if "type" in item and "target" in item:
                    link_type = str(item["type"]).lower().replace("_", " ")
                    target = str(item["target"])
                    links.append((link_type, target))
                else:
                    # Shorthand format: {"blocks": "PROJ-123"} or {"blocks": ["A-1", "B-2"]}
                    for link_type, targets in item.items():
                        link_type_normalized = str(link_type).lower().replace("_", " ")
                        if isinstance(targets, str):
                            links.append((link_type_normalized, targets))
                        elif isinstance(targets, list):
                            for target in targets:
                                links.append((link_type_normalized, str(target)))

        return links

    def _parse_comments(self, data: list[Any]) -> list[Comment]:
        """
        Parse comments from list data.

        Supports multiple formats:
        - Simple string: "This is a comment"
        - Structured: {"body": "Comment text", "author": "user", "created_at": "2025-01-15"}

        Returns:
            List of Comment objects.
        """
        comments: list[Comment] = []

        for item in data:
            if isinstance(item, str):
                # Simple string format
                comments.append(
                    Comment(
                        body=item,
                        author=None,
                        created_at=None,
                        comment_type="text",
                    )
                )
            elif isinstance(item, dict):
                body = item.get("body", item.get("text", item.get("content", "")))
                author = item.get("author", item.get("user", None))

                # Parse date if provided
                date_val = item.get("created_at", item.get("date", item.get("created", None)))
                created_at = parse_datetime(date_val)

                comment_type = item.get("type", item.get("comment_type", "text"))

                if body:
                    comments.append(
                        Comment(
                            body=body,
                            author=author,
                            created_at=created_at,
                            comment_type=comment_type,
                        )
                    )

        return comments

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def _validate_story(self, story: Any, index: int) -> list[str]:
        """Validate a single story entry."""
        errors: list[str] = []
        prefix = f"stories[{index}]"

        if not isinstance(story, dict):
            errors.append(f"{prefix}: must be a dictionary/object/table")
            return errors

        # Required fields
        if not story.get("id"):
            errors.append(f"{prefix}: missing required field 'id'")
        if not story.get("title"):
            errors.append(f"{prefix}: missing required field 'title'")

        # Validate story points
        sp = story.get("story_points")
        if sp is not None and not isinstance(sp, (int, float)):
            errors.append(f"{prefix}.story_points: must be a number")

        # Validate priority
        priority = story.get("priority")
        if priority is not None:
            valid_priorities = ["low", "medium", "high", "critical"]
            if str(priority).lower() not in valid_priorities:
                errors.append(f"{prefix}.priority: must be one of {valid_priorities}")

        # Validate status
        status = story.get("status")
        if status is not None:
            valid_statuses = ["planned", "in_progress", "done", "blocked"]
            if str(status).lower().replace(" ", "_") not in valid_statuses:
                errors.append(f"{prefix}.status: must be one of {valid_statuses}")

        # Validate list fields
        for field in ["subtasks", "acceptance_criteria", "links", "comments"]:
            field_data = story.get(field, [])
            if field_data and not isinstance(field_data, list):
                errors.append(f"{prefix}.{field}: must be a list/array")

        return errors
