"""
Document Parser Port - Abstract interface for parsing source documents.

Implementations:
- MarkdownParser: Parse markdown epic files (.md, .markdown)
- YamlParser: Parse YAML-based specs (.yaml, .yml)
- JsonParser: Parse JSON-based specs (.json)
- TomlParser: Parse TOML-based specs (.toml)
- CsvParser: Parse CSV/TSV spreadsheets (.csv, .tsv)
- AsciiDocParser: Parse AsciiDoc documents (.adoc, .asciidoc)
- ExcelParser: Parse Excel spreadsheets (.xlsx, .xlsm, .xls)
- ToonParser: Parse TOON format (.toon) - LLM-optimized notation
- NotionParser: Parse Notion exports (markdown/CSV/folders)
"""

from abc import ABC, abstractmethod
from pathlib import Path

from spectra.core.domain.entities import Epic, UserStory

# Import ParserError from centralized module and re-export for backward compatibility
from spectra.core.exceptions import ParserError


__all__ = ["DocumentParserPort", "ParserError"]


class DocumentParserPort(ABC):
    """
    Abstract interface for document parsers.

    Parsers convert source documents (Markdown, YAML, etc.)
    into domain entities.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the parser name (e.g., 'Markdown', 'YAML')."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Get list of supported file extensions."""
        ...

    @abstractmethod
    def can_parse(self, source: str | Path) -> bool:
        """
        Check if this parser can handle the given source.

        Args:
            source: File path or content string

        Returns:
            True if parser can handle this source
        """
        ...

    @abstractmethod
    def parse_stories(self, source: str | Path) -> list[UserStory]:
        """
        Parse user stories from source.

        Args:
            source: File path or content string

        Returns:
            List of UserStory entities

        Raises:
            ParserError: If parsing fails
        """
        ...

    @abstractmethod
    def parse_epic(self, source: str | Path) -> Epic | None:
        """
        Parse an epic with its stories from source.

        Args:
            source: File path or content string

        Returns:
            Epic entity with stories, or None if no epic found
        """
        ...

    @abstractmethod
    def validate(self, source: str | Path) -> list[str]:
        """
        Validate source document without parsing.

        Args:
            source: File path or content string

        Returns:
            List of validation error messages (empty if valid)
        """
        ...
