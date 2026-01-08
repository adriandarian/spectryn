"""
ADF Formatter - Atlassian Document Format for Jira.

Converts markdown and domain entities to Jira's ADF format.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.value_objects import CommitRef
from spectryn.core.ports.document_formatter import DocumentFormatterPort


@dataclass
class _ParserState:
    """Internal state for the markdown-to-ADF parser."""

    content: list = field(default_factory=list)
    current_list: dict | None = None
    current_list_type: str | None = None

    def reset_list(self) -> None:
        """Reset list context (called on empty line or non-list element)."""
        self.current_list = None
        self.current_list_type = None


class ADFFormatter(DocumentFormatterPort):
    """
    Atlassian Document Format formatter.

    Converts markdown/text to ADF for Jira API.
    Reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
    """

    @property
    def name(self) -> str:
        return "ADF"

    # -------------------------------------------------------------------------
    # DocumentFormatterPort Implementation
    # -------------------------------------------------------------------------

    def format_text(self, text: str) -> dict[str, Any]:
        """Convert markdown text to ADF."""
        parser_state = _ParserState()

        for line in text.split("\n"):
            self._process_line(line, parser_state)

        return self._doc(parser_state.content)

    def _process_line(self, line: str, state: "_ParserState") -> None:
        """Process a single line and update parser state."""
        # Empty line resets list context
        if not line.strip():
            state.reset_list()
            return

        # Try each line type handler in order
        if self._try_heading(line, state):
            return
        if self._try_task_list(line, state):
            return
        if self._try_bullet_list(line, state):
            return
        if self._try_table_row(line, state):
            return

        # Default: paragraph
        state.reset_list()
        state.content.append({"type": "paragraph", "content": self._parse_inline(line)})

    def _try_heading(self, line: str, state: "_ParserState") -> bool:
        """Try to parse line as a heading. Returns True if matched."""
        # Markdown headings
        for prefix, level in [("### ", 3), ("## ", 2), ("# ", 1)]:
            if line.startswith(prefix):
                state.reset_list()
                state.content.append(self._heading(line[len(prefix) :], level=level))
                return True

        # Jira wiki headings (h2. h3.)
        for prefix, level in [("h3. ", 3), ("h2. ", 2)]:
            if line.startswith(prefix):
                state.reset_list()
                state.content.append(self._heading(line[len(prefix) :], level=level))
                return True

        return False

    def _try_task_list(self, line: str, state: "_ParserState") -> bool:
        """Try to parse line as a task list item. Returns True if matched."""
        if not re.match(r"^- \[[ x]\] ", line):
            return False

        is_checked = line[3] == "x"
        item_text = line[6:]

        # Start new task list if needed
        if state.current_list_type != "task":
            state.current_list = {"type": "taskList", "attrs": {"localId": ""}, "content": []}
            state.current_list_type = "task"
            state.content.append(state.current_list)

        state.current_list["content"].append(
            {
                "type": "taskItem",
                "attrs": {"localId": "", "state": "DONE" if is_checked else "TODO"},
                "content": self._parse_inline(item_text),
            }
        )
        return True

    def _try_bullet_list(self, line: str, state: "_ParserState") -> bool:
        """Try to parse line as a bullet list item. Returns True if matched."""
        is_bullet = line.startswith("* ") or (line.startswith("- ") and not line.startswith("- ["))
        if not is_bullet:
            return False

        item_text = line[2:]

        # Start new bullet list if needed
        if state.current_list_type != "bullet":
            state.current_list = {"type": "bulletList", "content": []}
            state.current_list_type = "bullet"
            state.content.append(state.current_list)

        state.current_list["content"].append(
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": self._parse_inline(item_text)}],
            }
        )
        return True

    def _try_table_row(self, line: str, state: "_ParserState") -> bool:
        """Try to parse line as a table row (skip it). Returns True if matched."""
        if line.startswith("|"):
            state.reset_list()
            return True  # Skip table rows
        return False

    def format_story_description(self, story: UserStory) -> dict[str, Any]:
        """Format a story's complete description."""
        return self.format_text(story.get_full_description())

    def format_subtask_description(self, subtask: Subtask) -> dict[str, Any]:
        """Format a subtask's description."""
        text = f"{subtask.description}\n\nStory Points: {subtask.story_points}"
        return self.format_text(text)

    def format_commits_table(self, commits: list[CommitRef]) -> dict[str, Any]:
        """Format commits as a table."""
        # Header row
        rows = [
            self._table_row(
                [
                    self._table_header("Commit"),
                    self._table_header("Message"),
                ]
            )
        ]

        # Data rows
        for commit in commits:
            rows.append(
                self._table_row(
                    [
                        self._table_cell([self._code_text(commit.short_hash)]),
                        self._table_cell([self._text(commit.message)]),
                    ]
                )
            )

        return self._doc(
            [
                self._heading("Related Commits", level=3),
                {
                    "type": "table",
                    "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                    "content": rows,
                },
            ]
        )

    def format_heading(self, text: str, level: int = 2) -> dict[str, Any]:
        """Format a heading."""
        return self._doc([self._heading(text, level)])

    def format_list(self, items: list[str], ordered: bool = False) -> dict[str, Any]:
        """Format a list."""
        list_type = "orderedList" if ordered else "bulletList"
        list_items = []

        for item in items:
            list_items.append(
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": self._parse_inline(item)}],
                }
            )

        return self._doc([{"type": list_type, "content": list_items}])

    def format_task_list(self, items: list[tuple[str, bool]]) -> dict[str, Any]:
        """Format a task/checkbox list."""
        task_items = []

        for text, is_checked in items:
            task_items.append(
                {
                    "type": "taskItem",
                    "attrs": {"localId": "", "state": "DONE" if is_checked else "TODO"},
                    "content": self._parse_inline(text),
                }
            )

        return self._doc([{"type": "taskList", "attrs": {"localId": ""}, "content": task_items}])

    # -------------------------------------------------------------------------
    # Private Helper Methods
    # -------------------------------------------------------------------------

    def _doc(self, content: list) -> dict[str, Any]:
        """Create ADF document wrapper."""
        if not content:
            content = [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}]

        return {"type": "doc", "version": 1, "content": content}

    def _heading(self, text: str, level: int = 2) -> dict[str, Any]:
        """Create heading node."""
        return {
            "type": "heading",
            "attrs": {"level": level},
            "content": [{"type": "text", "text": text}],
        }

    def _text(self, text: str) -> dict[str, Any]:
        """Create plain text node."""
        return {"type": "text", "text": text}

    def _bold_text(self, text: str) -> dict[str, Any]:
        """Create bold text node."""
        return {"type": "text", "text": text, "marks": [{"type": "strong"}]}

    def _code_text(self, text: str) -> dict[str, Any]:
        """Create inline code node."""
        return {"type": "text", "text": text, "marks": [{"type": "code"}]}

    def _italic_text(self, text: str) -> dict[str, Any]:
        """Create italic text node."""
        return {"type": "text", "text": text, "marks": [{"type": "em"}]}

    def _parse_inline(self, text: str) -> list[dict[str, Any]]:
        """Parse inline formatting: **bold**, *italic*, `code`."""
        content = []
        pattern = r"(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)"
        last_end = 0

        for match in re.finditer(pattern, text):
            # Add preceding text
            if match.start() > last_end:
                plain = text[last_end : match.start()]
                if plain:
                    content.append(self._text(plain))

            full = match.group(0)

            if full.startswith("**"):
                content.append(self._bold_text(match.group(2)))
            elif full.startswith("`"):
                content.append(self._code_text(match.group(4)))
            elif full.startswith("*"):
                content.append(self._italic_text(match.group(3)))

            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                content.append(self._text(remaining))

        return content if content else [self._text(text)]

    def _table_row(self, cells: list[dict]) -> dict[str, Any]:
        """Create table row."""
        return {"type": "tableRow", "content": cells}

    def _table_header(self, text: str) -> dict[str, Any]:
        """Create table header cell."""
        return {
            "type": "tableHeader",
            "attrs": {},
            "content": [{"type": "paragraph", "content": [self._bold_text(text)]}],
        }

    def _table_cell(self, content: list[dict]) -> dict[str, Any]:
        """Create table cell."""
        return {
            "type": "tableCell",
            "attrs": {},
            "content": [{"type": "paragraph", "content": content}],
        }
