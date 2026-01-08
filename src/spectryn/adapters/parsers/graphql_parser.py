"""
GraphQL Schema Parser - Parse GraphQL schema files into domain entities.

Implements the DocumentParserPort interface for .graphql files.

Extracts user stories from GraphQL schema descriptions and comments.
"""

import logging
import re
from pathlib import Path

from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    IssueKey,
    StoryId,
)
from spectryn.core.ports.document_parser import DocumentParserPort


class GraphQLParser(DocumentParserPort):
    """
    Parser for GraphQL schema (.graphql, .gql) files.

    Extracts stories from descriptions (docstrings) in GraphQL schemas.

    Example GraphQL format:

    ```graphql
    # Epic: PROJ-123 - User API
    # Epic Key: PROJ-123

    \"\"\"
    PROJ-001: Create User Mutation
    Story Points: 5
    Priority: High
    Status: Planned

    Description:
    As a client application
    I want to create users via GraphQL
    So that I can onboard new users

    Acceptance Criteria:
    - [ ] Validates email format
    - [x] Returns user ID
    \"\"\"
    type Mutation {
        createUser(input: CreateUserInput!): User!
    }

    \"\"\"
    PROJ-002: Query Users
    Story Points: 3
    Priority: Medium
    Status: Done
    \"\"\"
    type Query {
        users(filter: UserFilter): [User!]!
        user(id: ID!): User
    }
    ```
    """

    STORY_ID_PATTERN = r"(?:[A-Z]+[-_/]\d+|#\d+)"

    def __init__(self) -> None:
        """Initialize the GraphQL parser."""
        self.logger = logging.getLogger("GraphQLParser")

    @property
    def name(self) -> str:
        return "GraphQL"

    @property
    def supported_extensions(self) -> list[str]:
        return [".graphql", ".gql"]

    def can_parse(self, source: str | Path) -> bool:
        """Check if source is a valid GraphQL file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions

        # Check for GraphQL-like content
        has_type = bool(re.search(r"type\s+\w+\s*\{", source))
        has_query = bool(re.search(r"type\s+Query\s*\{", source))
        has_mutation = bool(re.search(r"type\s+Mutation\s*\{", source))
        has_schema = bool(re.search(r"schema\s*\{", source))

        return has_type or has_query or has_mutation or has_schema

    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """Parse user stories from GraphQL source."""
        content = self._get_content(source)
        return self._parse_all_stories(content)

    def parse_epic(self, source: str | Path) -> Epic | None:
        """Parse an epic from GraphQL source."""
        content = self._get_content(source)

        # Extract epic info from file-level comments
        epic_key = "EPIC-0"
        epic_title = "Untitled Epic"

        key_match = re.search(r"#\s*Epic\s*Key:\s*([A-Z]+[-_/]\d+)", content)
        if key_match:
            epic_key = key_match.group(1)

        title_match = re.search(r"#\s*Epic:\s*([^\n]+)", content)
        if title_match:
            epic_title = title_match.group(1).strip()
            epic_title = re.sub(rf"^{self.STORY_ID_PATTERN}\s*[-–—]\s*", "", epic_title)

        stories = self._parse_all_stories(content)

        if not stories:
            return None

        return Epic(key=IssueKey(epic_key), title=epic_title, stories=stories)

    def validate(self, source: str | Path) -> list[str]:
        """Validate GraphQL source without full parsing."""
        errors: list[str] = []

        try:
            content = self._get_content(source)
        except Exception as e:
            return [str(e)]

        # Check for type definitions
        if not re.search(r"type\s+\w+\s*\{", content):
            errors.append("No type definitions found")

        # Check for story docstrings
        story_pattern = rf'"""\s*{self.STORY_ID_PATTERN}:'
        if not re.search(story_pattern, content):
            errors.append("No user stories found in docstrings")

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

    def _parse_all_stories(self, content: str) -> list[UserStory]:
        """Parse all stories from GraphQL docstrings."""
        stories = []

        # Find triple-quoted docstrings before type/field definitions
        docstring_pattern = r'"""([\s\S]*?)"""'
        for match in re.finditer(docstring_pattern, content):
            docstring = match.group(1)
            story = self._parse_story_from_docstring(docstring)
            if story:
                stories.append(story)

        return stories

    def _parse_story_from_docstring(self, docstring: str) -> UserStory | None:
        """Parse a story from a docstring."""
        # Extract story ID and title from first line
        header_match = re.search(rf"({self.STORY_ID_PATTERN}):\s*([^\n]+)", docstring)
        if not header_match:
            return None

        story_id = header_match.group(1)
        title = header_match.group(2).strip()
        content = docstring

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
        section = self._extract_section(content, "Description")
        if not section:
            section = content

        pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
        match = re.search(pattern, section, re.IGNORECASE | re.DOTALL)

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
