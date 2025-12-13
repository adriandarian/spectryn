"""
Document Parser Port - Abstract interface for parsing source documents.

Implementations:
- MarkdownParser: Parse markdown epic files
- YamlParser: Parse YAML-based specs
- (Future) JsonParser: Parse JSON specs
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union

from ..domain.entities import Epic, UserStory


class ParserError(Exception):
    """Error during document parsing."""
    
    def __init__(self, message: str, line_number: Optional[int] = None, source: Optional[str] = None):
        super().__init__(message)
        self.line_number = line_number
        self.source = source


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
    def can_parse(self, source: Union[str, Path]) -> bool:
        """
        Check if this parser can handle the given source.
        
        Args:
            source: File path or content string
            
        Returns:
            True if parser can handle this source
        """
        ...
    
    @abstractmethod
    def parse_stories(self, source: Union[str, Path]) -> list[UserStory]:
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
    def parse_epic(self, source: Union[str, Path]) -> Optional[Epic]:
        """
        Parse an epic with its stories from source.
        
        Args:
            source: File path or content string
            
        Returns:
            Epic entity with stories, or None if no epic found
        """
        ...
    
    @abstractmethod
    def validate(self, source: Union[str, Path]) -> list[str]:
        """
        Validate source document without parsing.
        
        Args:
            source: File path or content string
            
        Returns:
            List of validation error messages (empty if valid)
        """
        ...

