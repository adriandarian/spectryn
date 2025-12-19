"""
TOON Parser - Parse TOON (Token-Oriented Object Notation) files into domain entities.

Implements the DocumentParserPort interface for TOON-based specifications.

TOON is a compact, human-readable serialization format designed to reduce
token usage in Large Language Model (LLM) prompts while maintaining readability.
It's similar to JSON but with a more compact syntax.

TOON Syntax:
- Unquoted strings (quotes only needed for special characters)
- Colons for key-value pairs
- Indentation or braces for nesting
- Brackets for arrays
- No trailing commas needed
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

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


class ToonParser(DocumentParserPort):
    """
    Parser for TOON (Token-Oriented Object Notation) files.

    TOON is a compact format optimized for LLM token efficiency.
    It uses a simplified syntax compared to JSON.

    Example TOON format:

    ```toon
    epic:
      key: PROJ-123
      title: Epic Title
      description: Epic description

    stories:
      - id: US-001
        title: Story Title
        description:
          as_a: user
          i_want: feature
          so_that: benefit
        story_points: 5
        priority: high
        status: planned
        acceptance_criteria:
          - criterion: First criterion
            done: false
          - criterion: Second criterion
            done: true
        subtasks:
          - name: Subtask 1
            description: Do something
            story_points: 2
            status: planned
        technical_notes: Some technical details here
        links:
          - type: blocks
            target: PROJ-456
        comments:
          - body: This is a comment
            author: user
            created_at: 2025-01-15
    ```

    Alternative compact format:

    ```toon
    epic{key:PROJ-123 title:Epic Title}
    stories[
      {id:US-001 title:Story Title story_points:5 priority:high}
      {id:US-002 title:Another Story story_points:3}
    ]
    ```
    """

    def __init__(self) -> None:
        """Initialize the TOON parser."""
        self.logger = logging.getLogger("ToonParser")

    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "TOON"

    @property
    def supported_extensions(self) -> list[str]:
        return [".toon"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid TOON file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Try to parse as TOON and check for expected structure
        try:
            data = self._parse_toon(source)
            if isinstance(data, dict):
                return "stories" in data or "epic" in data
            return False
        except Exception:
            return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from TOON source."""
        data = self._load_toon(source)

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
                story_id = (
                    story_data.get("id", "unknown") if isinstance(story_data, dict) else "unknown"
                )
                self.logger.warning(f"Failed to parse story {story_id}: {e}")

        return stories

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic with its stories from TOON source."""
        data = self._load_toon(source)

        epic_data = data.get("epic", {})
        epic_key = epic_data.get("key", "EPIC-0") if isinstance(epic_data, dict) else "EPIC-0"
        epic_title = (
            epic_data.get("title", "Untitled Epic")
            if isinstance(epic_data, dict)
            else "Untitled Epic"
        )
        epic_description = epic_data.get("description", "") if isinstance(epic_data, dict) else ""

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
        """Validate TOON source without full parsing."""
        errors: list[str] = []

        try:
            data = self._load_toon(source)
        except ParserError as e:
            return [str(e)]

        if not isinstance(data, dict):
            errors.append("Root element must be an object")
            return errors

        if "stories" not in data and "epic" not in data:
            errors.append("TOON must contain 'stories' or 'epic' key")

        stories_data = data.get("stories", [])
        if not isinstance(stories_data, list):
            errors.append("'stories' must be an array")
        else:
            for i, story in enumerate(stories_data):
                story_errors = self._validate_story(story, i)
                errors.extend(story_errors)

        return errors

    # -------------------------------------------------------------------------
    # Private Methods - TOON Parsing
    # -------------------------------------------------------------------------

    def _load_toon(self, source: str | Path) -> dict[str, Any]:
        """Load TOON content from file or string."""
        try:
            if isinstance(source, Path):
                content = source.read_text(encoding="utf-8")
            elif isinstance(source, str):
                content = source
                if "\n" not in source and len(source) < 4096:
                    try:
                        path = Path(source)
                        if path.exists() and path.suffix.lower() == ".toon":
                            content = path.read_text(encoding="utf-8")
                    except OSError:
                        pass
            else:
                content = source

            return self._parse_toon(content)

        except Exception as e:
            if isinstance(e, ParserError):
                raise
            raise ParserError(f"Invalid TOON: {e}")

    def _parse_toon(self, content: str) -> dict[str, Any]:
        """
        Parse TOON content into a dictionary.

        TOON format is similar to YAML but more compact:
        - key: value pairs
        - Indentation for nesting
        - Arrays with - prefix or [brackets]
        - Objects with {braces} for inline
        """
        content = content.strip()

        if not content:
            return {}

        # Try to parse as YAML-like format first (most common TOON style)
        try:
            return self._parse_yaml_style(content)
        except Exception:
            pass

        # Try compact brace format
        try:
            return self._parse_compact_style(content)
        except Exception:
            pass

        raise ParserError("Unable to parse TOON content")

    def _parse_yaml_style(self, content: str) -> dict[str, Any]:
        """Parse YAML-style TOON content."""
        import yaml

        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                return data
            raise ValueError("Root must be a dict")
        except Exception as e:
            raise ParserError(f"YAML-style parsing failed: {e}")

    def _parse_compact_style(self, content: str) -> dict[str, Any]:
        """Parse compact brace-style TOON content."""
        result: dict[str, Any] = {}

        # Pattern for top-level key{...} or key[...]
        top_level_pattern = r"(\w+)\s*([{\[])"

        pos = 0
        while pos < len(content):
            match = re.search(top_level_pattern, content[pos:])
            if not match:
                break

            key = match.group(1)
            bracket_type = match.group(2)
            start = pos + match.end() - 1

            # Find matching closing bracket
            end = self._find_matching_bracket(content, start)
            if end == -1:
                raise ParserError(f"Unmatched bracket for key '{key}'")

            inner = content[start + 1 : end].strip()

            if bracket_type == "{":
                result[key] = self._parse_inline_object(inner)
            else:  # [
                result[key] = self._parse_inline_array(inner)

            pos = end + 1

        return result

    def _find_matching_bracket(self, content: str, start: int) -> int:
        """Find the matching closing bracket."""
        open_char = content[start]
        close_char = "}" if open_char == "{" else "]"

        depth = 1
        pos = start + 1
        in_string = False
        string_char = None

        while pos < len(content) and depth > 0:
            char = content[pos]

            if not in_string:
                if char in "\"'":
                    in_string = True
                    string_char = char
                elif char == open_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1
            elif char == string_char and content[pos - 1] != "\\":
                in_string = False

            pos += 1

        return pos - 1 if depth == 0 else -1

    def _parse_inline_object(self, content: str) -> dict[str, Any]:
        """Parse inline object: key:value key2:value2"""
        result: dict[str, Any] = {}

        # Match key:value pairs
        pattern = r"(\w+)\s*:\s*([^\s:]+(?:\s+[^\s:]+)*?)(?=\s+\w+:|$)"

        for match in re.finditer(pattern, content):
            key = match.group(1)
            value = match.group(2).strip()
            result[key] = self._parse_value(value)

        return result

    def _parse_inline_array(self, content: str) -> list[Any]:
        """Parse inline array of objects."""
        result: list[Any] = []

        # Find all {...} objects
        pos = 0
        while pos < len(content):
            # Skip whitespace
            while pos < len(content) and content[pos] in " \t\n":
                pos += 1

            if pos >= len(content):
                break

            if content[pos] == "{":
                end = self._find_matching_bracket(content, pos)
                if end != -1:
                    inner = content[pos + 1 : end].strip()
                    result.append(self._parse_inline_object(inner))
                    pos = end + 1
                else:
                    break
            else:
                pos += 1

        return result

    def _parse_value(self, value: str) -> Any:
        """Parse a scalar value."""
        value = value.strip()

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # Null
        if value.lower() in ("null", "none", "~"):
            return None

        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # String (remove quotes if present)
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]

        return value

    def _is_valid_key(self, key: str) -> bool:
        """Check if a string is a valid issue key."""
        return bool(re.match(r"^[A-Z]+-\d+$", str(key).upper()))

    # -------------------------------------------------------------------------
    # Private Methods - Story Parsing
    # -------------------------------------------------------------------------

    def _parse_story(self, data: dict[str, Any]) -> UserStory | None:
        """Parse a single story from TOON data."""
        if not isinstance(data, dict):
            return None

        story_id = data.get("id", "US-000")
        title = data.get("title", "Untitled Story")

        description = self._parse_description(data.get("description"))
        acceptance = self._parse_acceptance_criteria(data.get("acceptance_criteria", []))
        subtasks = self._parse_subtasks(data.get("subtasks", []))
        commits = self._parse_commits(data.get("commits", []))
        links = self._parse_links(data.get("links", []))
        comments = self._parse_comments(data.get("comments", []))

        story_points = int(data.get("story_points", 0))
        priority = Priority.from_string(str(data.get("priority", "medium")))
        status = Status.from_string(str(data.get("status", "planned")))
        tech_notes = data.get("technical_notes", "")

        return UserStory(
            id=StoryId(str(story_id)),
            title=str(title),
            description=description,
            acceptance_criteria=acceptance,
            technical_notes=str(tech_notes) if tech_notes else "",
            story_points=story_points,
            priority=priority,
            status=status,
            subtasks=subtasks,
            commits=commits,
            links=links,
            comments=comments,
        )

    def _parse_description(self, data: Any) -> Description | None:
        """Parse description from TOON data."""
        if data is None:
            return None

        if isinstance(data, str):
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
                role=str(data.get("as_a", data.get("role", ""))),
                want=str(data.get("i_want", data.get("want", ""))),
                benefit=str(data.get("so_that", data.get("benefit", ""))),
            )

        return None

    def _parse_acceptance_criteria(self, data: list[Any]) -> AcceptanceCriteria:
        """Parse acceptance criteria from TOON data."""
        if not isinstance(data, list):
            return AcceptanceCriteria.from_list([], [])

        items: list[str] = []
        checked: list[bool] = []

        for item in data:
            if isinstance(item, str):
                items.append(item)
                checked.append(False)
            elif isinstance(item, dict):
                criterion = str(item.get("criterion", item.get("text", "")))
                done = bool(item.get("done", item.get("checked", False)))
                if criterion:
                    items.append(criterion)
                    checked.append(done)

        return AcceptanceCriteria.from_list(items, checked)

    def _parse_subtasks(self, data: list[Any]) -> list[Subtask]:
        """Parse subtasks from TOON data."""
        if not isinstance(data, list):
            return []

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
                        number=int(item.get("number", i + 1)),
                        name=str(item.get("name", item.get("title", ""))),
                        description=str(item.get("description", "")),
                        story_points=int(item.get("story_points", item.get("sp", 1))),
                        status=Status.from_string(str(item.get("status", "planned"))),
                        assignee=item.get("assignee"),
                    )
                )

        return subtasks

    def _parse_commits(self, data: list[Any]) -> list[CommitRef]:
        """Parse commit references from TOON data."""
        if not isinstance(data, list):
            return []

        commits = []

        for item in data:
            if isinstance(item, str):
                commits.append(CommitRef(hash=item[:8], message=""))
            elif isinstance(item, dict):
                commits.append(
                    CommitRef(
                        hash=str(item.get("hash", item.get("sha", "")))[:8],
                        message=str(item.get("message", "")),
                    )
                )

        return commits

    def _parse_links(self, data: list[Any]) -> list[tuple[str, str]]:
        """Parse issue links from TOON data."""
        if not isinstance(data, list):
            return []

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
        """Parse comments from TOON data."""
        if not isinstance(data, list):
            return []

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
                body = str(item.get("body", item.get("text", item.get("content", ""))))
                author = item.get("author", item.get("user"))
                created_at = None

                date_val = item.get("created_at", item.get("date", item.get("created")))
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

                comment_type = str(item.get("type", item.get("comment_type", "text")))

                if body:
                    comments.append(
                        Comment(
                            body=body,
                            author=str(author) if author else None,
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
            errors.append(f"{prefix}: must be an object")
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
