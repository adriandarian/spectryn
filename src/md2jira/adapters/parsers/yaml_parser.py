"""
YAML Parser - Parse YAML epic/story files into domain entities.

Implements the DocumentParserPort interface for YAML-based specifications.

This provides an alternative to markdown for defining epics and stories,
with a more structured, machine-friendly format that's easier to validate
and generate programmatically.
"""

import logging
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from ...core.ports.document_parser import DocumentParserPort, ParserError
from ...core.domain.entities import Epic, UserStory, Subtask
from ...core.domain.value_objects import (
    StoryId,
    IssueKey,
    CommitRef,
    Description,
    AcceptanceCriteria,
)
from ...core.domain.enums import Status, Priority


class YamlParser(DocumentParserPort):
    """
    Parser for YAML epic/story specification files.
    
    Supports a structured YAML format for defining epics, stories,
    subtasks, and all related metadata.
    
    Example YAML format:
    
    ```yaml
    epic:
      key: PROJ-123  # Optional - use existing epic
      title: "Epic Title"
      description: "Epic description"
    
    stories:
      - id: US-001
        title: "Story Title"
        description:
          as_a: "user"
          i_want: "feature"
          so_that: "benefit"
        story_points: 5
        priority: high
        status: planned
        acceptance_criteria:
          - criterion: "First criterion"
            done: false
          - criterion: "Second criterion"
            done: true
        subtasks:
          - name: "Subtask 1"
            description: "Do something"
            story_points: 2
            status: planned
        technical_notes: |
          Some technical details here.
    ```
    """
    
    def __init__(self) -> None:
        """Initialize the YAML parser."""
        self.logger = logging.getLogger("YamlParser")
    
    # -------------------------------------------------------------------------
    # DocumentParserPort Implementation
    # -------------------------------------------------------------------------
    
    @property
    def name(self) -> str:
        return "YAML"
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".yaml", ".yml"]
    
    def can_parse(self, source: Union[str, Path]) -> bool:
        """Check if source is a valid YAML file or content."""
        if isinstance(source, Path):
            return source.suffix.lower() in self.supported_extensions
        
        # Try to parse as YAML and check for expected structure
        try:
            data = yaml.safe_load(source)
            if isinstance(data, dict):
                # Check for expected keys
                return "stories" in data or "epic" in data
            return False
        except yaml.YAMLError:
            return False
    
    def parse_stories(self, source: Union[str, Path]) -> list[UserStory]:
        """Parse user stories from YAML source."""
        data = self._load_yaml(source)
        
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
    
    def parse_epic(self, source: Union[str, Path]) -> Optional[Epic]:
        """Parse an epic with its stories from YAML source."""
        data = self._load_yaml(source)
        
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
    
    def validate(self, source: Union[str, Path]) -> list[str]:
        """Validate YAML source without full parsing."""
        errors: list[str] = []
        
        try:
            data = self._load_yaml(source)
        except ParserError as e:
            return [str(e)]
        
        # Validate structure
        if not isinstance(data, dict):
            errors.append("Root element must be a dictionary")
            return errors
        
        # Check for required sections
        if "stories" not in data and "epic" not in data:
            errors.append("YAML must contain 'stories' or 'epic' key")
        
        # Validate stories
        stories_data = data.get("stories", [])
        if not isinstance(stories_data, list):
            errors.append("'stories' must be a list")
        else:
            for i, story in enumerate(stories_data):
                story_errors = self._validate_story(story, i)
                errors.extend(story_errors)
        
        # Validate epic
        epic_data = data.get("epic", {})
        if epic_data and not isinstance(epic_data, dict):
            errors.append("'epic' must be a dictionary")
        elif epic_data:
            if not epic_data.get("title"):
                errors.append("Epic missing required field: 'title'")
        
        return errors
    
    # -------------------------------------------------------------------------
    # Private Methods - Loading
    # -------------------------------------------------------------------------
    
    def _load_yaml(self, source: Union[str, Path]) -> dict[str, Any]:
        """Load YAML content from file or string."""
        try:
            if isinstance(source, Path):
                content = source.read_text(encoding="utf-8")
            elif isinstance(source, str) and Path(source).exists():
                content = Path(source).read_text(encoding="utf-8")
            else:
                content = source
            
            data = yaml.safe_load(content)
            
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ParserError("YAML root must be a dictionary")
            
            return data
            
        except yaml.YAMLError as e:
            raise ParserError(f"Invalid YAML: {e}")
    
    def _is_valid_key(self, key: str) -> bool:
        """Check if a string is a valid issue key."""
        import re
        return bool(re.match(r"^[A-Z]+-\d+$", str(key).upper()))
    
    # -------------------------------------------------------------------------
    # Private Methods - Parsing
    # -------------------------------------------------------------------------
    
    def _parse_story(self, data: dict[str, Any]) -> Optional[UserStory]:
        """Parse a single story from YAML data."""
        story_id = data.get("id", "US-000")
        title = data.get("title", "Untitled Story")
        
        # Parse description
        description = self._parse_description(data.get("description"))
        
        # Parse acceptance criteria
        acceptance = self._parse_acceptance_criteria(data.get("acceptance_criteria", []))
        
        # Parse subtasks
        subtasks = self._parse_subtasks(data.get("subtasks", []))
        
        # Parse commits
        commits = self._parse_commits(data.get("commits", []))
        
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
        )
    
    def _parse_description(
        self,
        data: Any,
    ) -> Optional[Description]:
        """Parse description from YAML data."""
        if data is None:
            return None
        
        # Support simple string format
        if isinstance(data, str):
            # Try to extract As a/I want/So that from string
            import re
            pattern = r"As a[n]?\s+(.+?),?\s+I want\s+(.+?),?\s+so that\s+(.+)"
            match = re.search(pattern, data, re.IGNORECASE | re.DOTALL)
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
    
    def _parse_acceptance_criteria(
        self,
        data: list[Any],
    ) -> AcceptanceCriteria:
        """Parse acceptance criteria from YAML data."""
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
        """Parse subtasks from YAML data."""
        subtasks = []
        
        for i, item in enumerate(data):
            if isinstance(item, str):
                # Simple string format
                subtasks.append(Subtask(
                    number=i + 1,
                    name=item,
                    description="",
                    story_points=1,
                    status=Status.PLANNED,
                ))
            elif isinstance(item, dict):
                # Structured format
                subtasks.append(Subtask(
                    number=item.get("number", i + 1),
                    name=item.get("name", item.get("title", "")),
                    description=item.get("description", ""),
                    story_points=int(item.get("story_points", item.get("sp", 1))),
                    status=Status.from_string(item.get("status", "planned")),
                    assignee=item.get("assignee"),
                ))
        
        return subtasks
    
    def _parse_commits(self, data: list[Any]) -> list[CommitRef]:
        """Parse commit references from YAML data."""
        commits = []
        
        for item in data:
            if isinstance(item, str):
                # Just a hash
                commits.append(CommitRef(hash=item[:8], message=""))
            elif isinstance(item, dict):
                commits.append(CommitRef(
                    hash=item.get("hash", item.get("sha", ""))[:8],
                    message=item.get("message", ""),
                ))
        
        return commits
    
    # -------------------------------------------------------------------------
    # Private Methods - Validation
    # -------------------------------------------------------------------------
    
    def _validate_story(self, story: Any, index: int) -> list[str]:
        """Validate a single story entry."""
        errors: list[str] = []
        prefix = f"stories[{index}]"
        
        if not isinstance(story, dict):
            errors.append(f"{prefix}: must be a dictionary")
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
        
        # Validate subtasks
        subtasks = story.get("subtasks", [])
        if not isinstance(subtasks, list):
            errors.append(f"{prefix}.subtasks: must be a list")
        
        # Validate acceptance criteria
        ac = story.get("acceptance_criteria", [])
        if not isinstance(ac, list):
            errors.append(f"{prefix}.acceptance_criteria: must be a list")
        
        return errors

