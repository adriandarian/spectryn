"""
Parser Utilities - Shared parsing utilities for document parsers.

Contains common parsing functions used across multiple parser implementations:
- parse_blockquote_comments: Extract comments from markdown blockquotes
- parse_datetime: Parse datetime from various formats (re-exported from base_dict_parser)
"""

import contextlib
import re
from datetime import datetime

from spectryn.core.domain.entities import Comment

from .base_dict_parser import COMMON_DATE_FORMATS, parse_datetime


# Regex pattern for structured comment header: **@username** (YYYY-MM-DD):
COMMENT_HEADER_PATTERN = re.compile(
    r"\*\*@([^*]+)\*\*\s*(?:\((\d{4}-\d{2}-\d{2})\))?:?\s*(.*)",
    re.DOTALL,
)

# Regex pattern for simple comment header: @username: comment
SIMPLE_COMMENT_PATTERN = re.compile(r"@([^\s:]+):?\s*(.*)", re.DOTALL)


def parse_blockquote_comments(section_content: str) -> list[Comment]:
    """
    Parse blockquote-formatted comments from a section of text.

    Extracts comments from markdown blockquote blocks (lines starting with >).
    Supports two formats for author/date:
    - Structured: **@username** (YYYY-MM-DD): comment body
    - Simple: @username: comment body

    Args:
        section_content: Text content containing blockquote comments.
            Can include multiple blockquote blocks separated by blank lines.

    Returns:
        List of Comment objects parsed from the blockquotes.

    Example:
        >>> content = '''
        ... > **@alice** (2025-01-15):
        ... > This is a comment
        ...
        ... > @bob: Another comment
        ... '''
        >>> comments = parse_blockquote_comments(content)
        >>> len(comments)
        2
    """
    comments: list[Comment] = []

    if not section_content or not section_content.strip():
        return comments

    # Split into individual comment blocks (separated by blank lines before >)
    comment_blocks = re.split(r"\n\s*\n(?=>)", section_content.strip())

    for block in comment_blocks:
        if not block.strip():
            continue

        # Extract blockquote content (remove > prefixes)
        lines = []
        for line in block.strip().split("\n"):
            # Remove leading > and optional space
            cleaned = re.sub(r"^>\s?", "", line)
            lines.append(cleaned)

        if not lines:
            continue

        full_text = "\n".join(lines).strip()
        if not full_text:
            continue

        # Try to extract author and date
        author = None
        created_at = None
        body = full_text

        # Try structured format: **@username** (YYYY-MM-DD):
        header_match = COMMENT_HEADER_PATTERN.match(full_text)

        if header_match:
            author = header_match.group(1).strip()
            date_str = header_match.group(2)
            if date_str:
                with contextlib.suppress(ValueError):
                    created_at = datetime.strptime(date_str, "%Y-%m-%d")
            body = header_match.group(3).strip()
        else:
            # Check for simpler format: @username: comment
            simple_match = SIMPLE_COMMENT_PATTERN.match(full_text)
            if simple_match:
                author = simple_match.group(1).strip()
                body = simple_match.group(2).strip()

        if body:
            comments.append(
                Comment(
                    body=body,
                    author=author,
                    created_at=created_at,
                    comment_type="text",
                )
            )

    return comments


__all__ = [
    "COMMENT_HEADER_PATTERN",
    "COMMON_DATE_FORMATS",
    "SIMPLE_COMMENT_PATTERN",
    "parse_blockquote_comments",
    "parse_datetime",
]
