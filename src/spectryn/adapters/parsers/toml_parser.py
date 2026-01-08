"""
TOML Parser - Parse TOML epic/story files into domain entities.

Implements the DocumentParserPort interface for TOML-based specifications.

TOML (Tom's Obvious, Minimal Language) is a configuration file format that's
easy to read and write due to its clear semantics.

Example TOML format:

```toml
[epic]
key = "PROJ-123"
title = "Epic Title"
description = "Epic description"

[[stories]]
id = "STORY-001"
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
```
"""

import sys
from pathlib import Path
from typing import Any


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from spectryn.core.ports.document_parser import ParserError

from .base_dict_parser import BaseDictParser


class TomlParser(BaseDictParser):
    """
    Parser for TOML epic/story specification files.

    Extends BaseDictParser with TOML-specific loading logic.
    All parsing and validation logic is inherited from the base class.
    """

    @property
    def name(self) -> str:
        return "TOML"

    @property
    def supported_extensions(self) -> list[str]:
        return [".toml"]

    def _load_data(self, source: str | Path) -> dict[str, Any]:
        """Load TOML content from file or string."""
        try:
            content = self._read_source(source)
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
