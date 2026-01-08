"""
YAML Parser - Parse YAML epic/story files into domain entities.

Implements the DocumentParserPort interface for YAML-based specifications.

This provides an alternative to markdown for defining epics and stories,
with a more structured, machine-friendly format that's easier to validate
and generate programmatically.

Example YAML format:

```yaml
epic:
  key: PROJ-123
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
    subtasks:
      - name: "Subtask 1"
        description: "Do something"
        story_points: 2
```
"""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from spectryn.core.ports.document_parser import ParserError

from .base_dict_parser import BaseDictParser


class YamlParser(BaseDictParser):
    """
    Parser for YAML epic/story specification files.

    Extends BaseDictParser with YAML-specific loading logic.
    All parsing and validation logic is inherited from the base class.
    """

    @property
    def name(self) -> str:
        return "YAML"

    @property
    def supported_extensions(self) -> list[str]:
        return [".yaml", ".yml"]

    def _load_data(self, source: str | Path) -> dict[str, Any]:
        """Load YAML content from file or string."""
        try:
            content = self._read_source(source)
            data = yaml.safe_load(content)

            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ParserError("YAML root must be a dictionary")

            return data

        except yaml.YAMLError as e:
            raise ParserError(f"Invalid YAML: {e}")
