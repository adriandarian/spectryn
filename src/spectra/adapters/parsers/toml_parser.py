"""
TOML Parser - Parse TOML epic/story files into domain entities.

Implements the DocumentParserPort interface for TOML-based specifications.

TOML (Tom's Obvious, Minimal Language) is a configuration file format that's
easy to read and write due to its clear semantics.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python

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


class TomlParser(DocumentParserPort):
    """
    Parser for TOML epic/story specification files.

    Supports a structured TOML format for defining epics, stories,
    subtasks, and all related metadata.

    Example TOML format:

    ```toml
    [epic]
    key = "PROJ-123"
    title = "Epic Title"
    description = "Epic description"

    [[stories]]
    id = "US-001"
    title = "Story Title"
    story_points = 5
    priority = "high"
    status = "planned"
    technical_notes = "Some technical details here."

    [stories.description]
    as_a = "user"
    i_want = "feature"
    so_that = "benefit"

    [[stories.acceptance_criteria]]
    criterion = "First criterion"
    done = false

    [[stories.subtasks]]
    name = "Subtask 1"
    description = "Do something"
    story_points = 2
    status = "planned"

    [[stories.links]]
    type = "blocks"
    target = "PROJ-456"

    [[stories.comments]]
    body = "This is a comment"
    author = "user"
    created_at = "2025-01-15"
    ```
    """

    def __init__(self) -> None:
        """Initialize the TOML parser."""
        self.logger = logging.getLogger("TomlParser")

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "TOML"

    @property
    def supported_extensions(self) -> list[str]:
        return [".toml"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid TOML file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Try to parse as TOML and check for expected structure
        try:
            data = tomllib.loads(source)
            if isinstance(data, dict):
                return "stories" in data or "epic" in data
            return False
        except Exception:
            return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from TOML source."""
        data = self._load_toml(source)

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
        """Parse an epic with its stories from TOML source."""
        data = self._load_toml(source)

        epic_data = data.get("epic", {})
        epic_key = epic_data.get("key", "EPIC-0")
        epic_title = epic_data.get("title", "Untitled Epic")
        epic_description = epic_data.get("description", "")

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
        """Validate TOML source without full parsing."""
        errors: list[str] = []

        try:
            data = self._load_toml(source)
        except ParserError as e:
            return [str(e)]

        if not isinstance(data, dict):
            errors.append("Root element must be a table")
            return errors

        if "stories" not in data and "epic" not in data:
            errors.append("TOML must contain 'stories' or 'epic' key")

        stories_data = data.get("stories", [])
        if not isinstance(stories_data, list):
            errors.append("'stories' must be an array of tables")
        else:
            for i, story in enumerate(stories_data):
                story_errors = self._validate_story(story, i)
                errors.extend(story_errors)

        epic_data = data.get("epic", {})
        if epic_data and not isinstance(epic_data, dict):
            errors.append("'epic' must be a table")
        elif epic_data and not epic_data.get("title"):
            errors.append("Epic missing required field: 'title'")

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _load_toml(self, source: str | Path) -> dict[str, Any]:
        """Load TOML content from file or string."""
        try:
            if isinstance(source, Path):
                content = source.read_text(encoding="utf-8")
            elif isinstance(source, str):
                content = source
                if "\n" not in source and len(source) < 4096:
                    try:
                        path = Path(source)
                        if path.exists() and path.suffix.lower() == ".toml":
                            content = path.read_text(encoding="utf-8")
                    except OSError:
                        pass
            else:
                content = source

            data = tomllib.loads(content)

            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ParserError("TOML root must be a table")

            return data

        except Exception as e:
            if isinstance(e, ParserError):
                raise
            raise ParserError(f"Invalid TOML: {e}")

    def _is_valid_key(self, key: str) -> bool:
        """Check if a string is a valid issue key."""
        import re
        return bool(re.match(r"^[A-Z]+-\d+$", str(key).upper()))

    def _parse_story(self, data: dict[str, Any]) -> UserStory | None:
        """Parse a single story from TOML data."""
        story_id = data.get("id", "US-000")
        title = data.get("title", "Untitled Story")

        description = self._parse_description(data.get("description"))
        acceptance = self._parse_acceptance_criteria(data.get("acceptance_criteria", []))
        subtasks = self._parse_subtasks(data.get("subtasks", []))
        commits = self._parse_commits(data.get("commits", []))
        links = self._parse_links(data.get("links", []))
        comments = self._parse_comments(data.get("comments", []))

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
        """Parse description from TOML data."""
        if data is None:
            return None

        if isinstance(data, str):
            import re
            pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
            match = re.search(pattern, data, re.IGNORECASE | re.DOTALL)
            if match:
                return Description(
                    role=match.group(1).strip(),
                    want=match.group(2).strip(),
                    benefit=match.group(3).strip(),
                )
            return Description(role="", want=data, benefit="")

        if isinstance(data, dict):
            return Description(
                role=data.get("as_a", data.get("role", "")),
                want=data.get("i_want", data.get("want", "")),
                benefit=data.get("so_that", data.get("benefit", "")),
            )

        return None

    def _parse_acceptance_criteria(self, data: list[Any]) -> AcceptanceCriteria:
        """Parse acceptance criteria from TOML data."""
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
        """Parse subtasks from TOML data."""
        subtasks = []

        for i, item in enumerate(data):
            if isinstance(item, str):
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
        """Parse commit references from TOML data."""
        commits = []

        for item in data:
            if isinstance(item, str):
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
        """Parse issue links from TOML data."""
        links: list[tuple[str, str]] = []

        for item in data:
            if isinstance(item, str):
                parts = item.strip().split(None, 1)
                if len(parts) == 2:
                    link_type = parts[0].lower().replace("_", " ")
                    target = parts[1].strip()
                    links.append((link_type, target))
            elif isinstance(item, dict):
                if "type" in item and "target" in item:
                    link_type = str(item["type"]).lower().replace("_", " ")
                    target = str(item["target"])
                    links.append((link_type, target))
                else:
                    for link_type, targets in item.items():
                        link_type_normalized = str(link_type).lower().replace("_", " ")
                        if isinstance(targets, str):
                            links.append((link_type_normalized, targets))
                        elif isinstance(targets, list):
                            for target in targets:
                                links.append((link_type_normalized, str(target)))

        return links

    def _parse_comments(self, data: list[Any]) -> list[Comment]:
        """Parse comments from TOML data."""
        comments: list[Comment] = []

        for item in data:
            if isinstance(item, str):
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
                created_at = None

                date_val = item.get("created_at", item.get("date", item.get("created", None)))
                if date_val:
                    if isinstance(date_val, datetime):
                        created_at = date_val
                    elif isinstance(date_val, str):
                        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                            try:
                                created_at = datetime.strptime(date_val, fmt)
                                break
                            except ValueError:
                                continue

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

    def _validate_story(self, story: Any, index: int) -> list[str]:
        """Validate a single story entry."""
        errors: list[str] = []
        prefix = f"stories[{index}]"

        if not isinstance(story, dict):
            errors.append(f"{prefix}: must be a table")
            return errors

        if not story.get("id"):
            errors.append(f"{prefix}: missing required field 'id'")
        if not story.get("title"):
            errors.append(f"{prefix}: missing required field 'title'")

        sp = story.get("story_points")
        if sp is not None and not isinstance(sp, (int, float)):
            errors.append(f"{prefix}.story_points: must be a number")

        priority = story.get("priority")
        if priority is not None:
            valid_priorities = ["low", "medium", "high", "critical"]
            if str(priority).lower() not in valid_priorities:
                errors.append(f"{prefix}.priority: must be one of {valid_priorities}")

        status = story.get("status")
        if status is not None:
            valid_statuses = ["planned", "in_progress", "done", "blocked"]
            if str(status).lower().replace(" ", "_") not in valid_statuses:
                errors.append(f"{prefix}.status: must be one of {valid_statuses}")

        return errors

