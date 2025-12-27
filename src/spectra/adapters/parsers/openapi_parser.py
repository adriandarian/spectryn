"""
OpenAPI/Swagger Parser - Parse OpenAPI spec files into domain entities.

Implements the DocumentParserPort interface for OpenAPI specifications.

Extracts user stories from OpenAPI operation descriptions and x-spectra extensions.
"""

import contextlib
import logging
import re
from pathlib import Path

import yaml

from spectra.core.domain.entities import Epic, Subtask, UserStory
from spectra.core.domain.enums import Priority, Status
from spectra.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectra.core.ports.document_parser import DocumentParserPort


class OpenAPIParser(DocumentParserPort):
    """
    Parser for OpenAPI/Swagger specification files.

    Extracts stories from operation descriptions and custom extensions.

    Supports:
    - OpenAPI 3.x (YAML/JSON)
    - Swagger 2.0 (YAML/JSON)
    - x-spectra-* custom extensions

    Example OpenAPI format:

    ```yaml
    openapi: "3.0.0"
    info:
      title: User API
      x-spectra-epic-key: PROJ-123

    paths:
      /users:
        post:
          operationId: createUser
          summary: Create a new user
          x-spectra-story-id: PROJ-001
          x-spectra-story-points: 5
          x-spectra-priority: High
          x-spectra-status: Planned
          description: |
            As a client application
            I want to create new users
            So that users can register

            ## Acceptance Criteria
            - [ ] Validates email format
            - [x] Returns user ID
          responses:
            201:
              description: User created
    ```
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    def __init__(self) -> None:
        """Initialize the OpenAPI parser."""
        self.logger = logging.getLogger("OpenAPIParser")

    @property
    def name(self) -> str:
        return "OpenAPI"

    @property
    def supported_extensions(self) -> list[str]:
        return [".yaml", ".yml", ".json"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid OpenAPI file or content."""
        if isinstance(source, Path):
            if source.suffix.lower() not in self.supported_extensions:
                return False
            try:
                content = source.read_text(encoding="utf-8")
                return self._is_openapi(content)
            except Exception:
                return False

        return self._is_openapi(source)

    def _is_openapi(self, content: str) -> bool:
        """Check if content is OpenAPI/Swagger."""
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return False
            # Check for OpenAPI 3.x or Swagger 2.0
            return "openapi" in data or "swagger" in data
        except Exception:
            return False

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from OpenAPI source."""
        content = self._get_content(source)
        spec = self._parse_spec(content)
        if not spec:
            return []
        return self._extract_stories(spec)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic from OpenAPI source."""
        content = self._get_content(source)
        spec = self._parse_spec(content)
        if not spec:
            return None

        # Extract epic info from info section
        info = spec.get("info", {})
        epic_key = info.get("x-spectra-epic-key", "EPIC-0")
        epic_title = info.get("title", "Untitled API")

        stories = self._extract_stories(spec)

        if not stories:
            return None

        return Epic(key=IssueKey(epic_key), title=epic_title, stories=stories)

    def validate(self, source: str | Path) -> list[str]:
        """Validate OpenAPI source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        if not self._is_openapi(content):
            errors.append("Not a valid OpenAPI/Swagger specification")
            return errors

        spec = self._parse_spec(content)
        if not spec:
            errors.append("Failed to parse specification")
            return errors

        # Check for operations with story extensions
        has_stories = False
        paths = spec.get("paths", {})
        for path_ops in paths.values():
            if isinstance(path_ops, dict):
                for op in path_ops.values():
                    if isinstance(op, dict) and "x-spectra-story-id" in op:
                        has_stories = True
                        break
            if has_stories:
                break

        if not has_stories:
            errors.append("No operations with x-spectra-story-id found")

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

    def _parse_spec(self, content: str) -> dict | None:
        """Parse OpenAPI spec from YAML/JSON content."""
        with contextlib.suppress(Exception):
            return yaml.safe_load(content)
        return None

    def _extract_stories(self, spec: dict) -> list[UserStory]:
        """Extract stories from OpenAPI spec."""
        stories = []

        paths = spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method.startswith("x-") or not isinstance(operation, dict):
                    continue

                story = self._extract_story_from_operation(path, method, operation)
                if story:
                    stories.append(story)

        return stories

    def _extract_story_from_operation(
        self, path: str, method: str, operation: dict
    ) -> UserStory | None:
        """Extract a story from an operation."""
        # Check for story ID in extension or generate from operationId
        story_id = operation.get("x-spectra-story-id")
        if not story_id:
            # Skip operations without explicit story ID
            return None

        title = operation.get("summary", f"{method.upper()} {path}")
        description_text = operation.get("description", "")

        # Extract from extensions
        story_points = str(operation.get("x-spectra-story-points", 0))
        priority = str(operation.get("x-spectra-priority", "Medium"))
        status = str(operation.get("x-spectra-status", "Planned"))

        description = self._extract_description(description_text)
        acceptance = self._extract_acceptance_criteria(description_text)
        subtasks = self._extract_subtasks_from_operation(operation)
        tech_notes = self._extract_section(description_text, "Technical Notes")

        # Also check x-spectra-acceptance-criteria
        if not acceptance.items and "x-spectra-acceptance-criteria" in operation:
            criteria = operation["x-spectra-acceptance-criteria"]
            if isinstance(criteria, list):
                acceptance = AcceptanceCriteria.from_list(criteria, [False] * len(criteria))

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
        """Extract acceptance criteria from description."""
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

    def _extract_subtasks_from_operation(self, operation: dict) -> list[Subtask]:
        """Extract subtasks from operation extensions."""
        subtasks = []

        # Check for x-spectra-subtasks extension
        ext_subtasks = operation.get("x-spectra-subtasks", [])
        if isinstance(ext_subtasks, list):
            for i, st in enumerate(ext_subtasks, 1):
                if isinstance(st, str):
                    subtasks.append(Subtask(number=i, name=st, description=""))
                elif isinstance(st, dict):
                    subtasks.append(
                        Subtask(
                            number=st.get("number", i),
                            name=st.get("name", ""),
                            description=st.get("description", ""),
                            story_points=st.get("story_points", 0),
                            status=Status.from_string(st.get("status", "Planned")),
                        )
                    )

        return subtasks

    def _extract_section(self, content: str, heading: str) -> str | None:
        """Extract content under a markdown heading."""
        pattern = rf"^##\s*{re.escape(heading)}\s*$"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)

        if not match:
            return None

        start = match.end()
        next_heading = re.search(r"^##\s+", content[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(content)

        return content[start:end].strip()
