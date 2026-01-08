"""
JSON Parser - Parse JSON epic/story files into domain entities.

Implements the DocumentParserPort interface for JSON-based specifications.

This provides an alternative to markdown/YAML for defining epics and stories,
with a structured, machine-friendly format that's easy to generate from
other tools and APIs.

Example JSON format:

```json
{
  "epic": {
    "key": "PROJ-123",
    "title": "Epic Title",
    "description": "Epic description"
  },
  "stories": [
    {
      "id": "STORY-001",
      "title": "Story Title",
      "description": {
        "as_a": "user",
        "i_want": "feature",
        "so_that": "benefit"
      },
      "story_points": 5,
      "priority": "high",
      "status": "planned",
      "acceptance_criteria": [
        {"criterion": "First criterion", "done": false}
      ],
      "subtasks": [
        {"name": "Subtask 1", "description": "Do something", "story_points": 2}
      ]
    }
  ]
}
```
"""

import json
from pathlib import Path
from typing import Any

from spectryn.core.ports.document_parser import ParserError

from .base_dict_parser import BaseDictParser


class JsonParser(BaseDictParser):
    """
    Parser for JSON epic/story specification files.

    Extends BaseDictParser with JSON-specific loading logic.
    All parsing and validation logic is inherited from the base class.
    """

    @property
    def name(self) -> str:
        return "JSON"

    @property
    def supported_extensions(self) -> list[str]:
        return [".json"]

    def _load_data(self, source: str | Path) -> dict[str, Any]:
        """Load JSON content from file or string."""
        try:
            content = self._read_source(source)
            data = json.loads(content)

            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ParserError("JSON root must be an object")

            return data

        except json.JSONDecodeError as e:
            raise ParserError(f"Invalid JSON: {e}")
