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
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from spectryn.core.ports.document_parser import ParserError

from .base_dict_parser import BaseDictParser


class ToonParser(BaseDictParser):
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
      - id: STORY-001  # Any PREFIX-NUMBER format (US-001, PROJ-123, etc.)
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
      {id:STORY-001 title:Story Title story_points:5 priority:high}
      {id:STORY-002 title:Another Story story_points:3}
    ]
    ```
    """

    def __init__(self) -> None:
        """Initialize the TOON parser."""
        super().__init__()
        self.logger = logging.getLogger("ToonParser")

    # -------------------------------------------------------------------------
    # BaseDictParser Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "TOON"

    @property
    def supported_extensions(self) -> list[str]:
        return [".toon"]

    def _load_data(self, source: str | Path) -> dict[str, Any]:
        """Load TOON content from file or string and parse to dict."""
        try:
            content = self._read_source(source)
            return self._parse_toon(content)

        except Exception as e:
            if isinstance(e, ParserError):
                raise
            raise ParserError(f"Invalid TOON: {e}")

    def _format_error_message(self, error: Exception) -> str:
        return f"Invalid TOON: {error}"

    # -------------------------------------------------------------------------
    # TOON-Specific Parsing
    # -------------------------------------------------------------------------

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

            # Handle string content
            if char in "\"'" and (pos == 0 or content[pos - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False

            if not in_string:
                if char == open_char:
                    depth += 1
                elif char == close_char:
                    depth -= 1

            pos += 1

        return pos - 1 if depth == 0 else -1

    def _parse_inline_object(self, content: str) -> dict[str, Any]:
        """Parse inline object content."""
        result: dict[str, Any] = {}

        # Pattern for key:value pairs
        pattern = r"(\w+)\s*:\s*"

        pos = 0
        while pos < len(content):
            match = re.search(pattern, content[pos:])
            if not match:
                break

            key = match.group(1)
            value_start = pos + match.end()

            # Determine where value ends (next key: or end)
            next_key = re.search(pattern, content[value_start:])
            value_end = value_start + next_key.start() if next_key else len(content)

            value = content[value_start:value_end].strip()

            # Parse the value
            result[key] = self._parse_value(value)

            pos = value_end

        return result

    def _parse_inline_array(self, content: str) -> list[Any]:
        """Parse inline array content."""
        result: list[Any] = []

        # Split by objects
        pos = 0
        while pos < len(content):
            # Skip whitespace
            while pos < len(content) and content[pos] in " \t\n":
                pos += 1

            if pos >= len(content):
                break

            if content[pos] == "{":
                # Find matching }
                end = self._find_matching_bracket(content, pos)
                if end == -1:
                    break
                inner = content[pos + 1 : end].strip()
                result.append(self._parse_inline_object(inner))
                pos = end + 1
            else:
                # Read until next { or end
                end = content.find("{", pos)
                if end == -1:
                    end = len(content)
                # Skip any non-object content
                pos = end

        return result

    def _parse_value(self, value: str) -> Any:
        """Parse a single value."""
        value = value.strip()

        if not value:
            return ""

        # Check for nested structures
        if value.startswith("{"):
            end = self._find_matching_bracket(value, 0)
            if end > 0:
                return self._parse_inline_object(value[1:end])

        if value.startswith("["):
            end = self._find_matching_bracket(value, 0)
            if end > 0:
                return self._parse_inline_array(value[1:end])

        # Try numeric
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # String (remove quotes if present)
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            return value[1:-1]

        return value
