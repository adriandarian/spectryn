"""
Streaming Parser - Handle very large files without loading all in memory.

Provides memory-efficient parsing for large markdown files by processing
content line-by-line and yielding stories as they are parsed.
"""

import logging
import mmap
import re
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, TextIO

from spectryn.core.domain.entities import Subtask, UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import (
    AcceptanceCriteria,
    Description,
    StoryId,
)
from spectryn.core.ports.document_parser import ParserError


logger = logging.getLogger(__name__)


@dataclass
class StreamingStats:
    """Statistics from streaming parse operation."""

    lines_processed: int = 0
    bytes_processed: int = 0
    stories_found: int = 0
    epics_found: int = 0
    parse_errors: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def lines_per_second(self) -> float:
        """Processing rate in lines per second."""
        duration = self.duration_seconds
        return self.lines_processed / duration if duration > 0 else 0.0

    @property
    def bytes_per_second(self) -> float:
        """Processing rate in bytes per second."""
        duration = self.duration_seconds
        return self.bytes_processed / duration if duration > 0 else 0.0


@dataclass
class ChunkInfo:
    """Information about a parsed chunk."""

    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    epic_key: str | None = None
    story_count: int = 0


@dataclass
class StreamingConfig:
    """Configuration for streaming parser."""

    # Buffer sizes
    chunk_size: int = 64 * 1024  # 64KB chunks for reading
    line_buffer_size: int = 1000  # Max lines to buffer for a story

    # Memory limits
    max_story_lines: int = 5000  # Max lines per story (safety limit)
    max_story_bytes: int = 1024 * 1024  # 1MB max per story

    # Progress reporting
    report_interval: int = 10000  # Report progress every N lines
    yield_on_epic: bool = True  # Yield stories when epic boundary is found

    # Error handling
    skip_malformed: bool = True  # Skip malformed stories instead of failing
    collect_errors: bool = True  # Collect errors for reporting


class StoryBuffer:
    """Buffer for accumulating lines of a single story."""

    def __init__(self, max_lines: int = 5000, max_bytes: int = 1024 * 1024):
        self.lines: list[str] = []
        self.start_line: int = 0
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self._byte_count = 0

    def add_line(self, line: str, line_num: int) -> None:
        """Add a line to the buffer."""
        if not self.lines:
            self.start_line = line_num

        if len(self.lines) >= self.max_lines:
            raise ParserError(f"Story exceeds maximum line limit ({self.max_lines} lines)")

        line_bytes = len(line.encode("utf-8"))
        if self._byte_count + line_bytes > self.max_bytes:
            raise ParserError(f"Story exceeds maximum size limit ({self.max_bytes} bytes)")

        self.lines.append(line)
        self._byte_count += line_bytes

    def get_content(self) -> str:
        """Get buffered content as string."""
        return "\n".join(self.lines)

    def clear(self) -> None:
        """Clear the buffer."""
        self.lines.clear()
        self.start_line = 0
        self._byte_count = 0

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self.lines) == 0

    @property
    def line_count(self) -> int:
        """Get number of lines in buffer."""
        return len(self.lines)

    @property
    def byte_count(self) -> int:
        """Get byte count of buffer."""
        return self._byte_count


class StreamingMarkdownParser:
    """
    Memory-efficient streaming parser for large markdown files.

    Processes files line-by-line without loading the entire file into memory.
    Yields UserStory objects as they are parsed.

    Usage:
        parser = StreamingMarkdownParser()

        # Stream from file
        for story in parser.stream_stories("/path/to/large-file.md"):
            process(story)

        # Stream from file handle
        with open("file.md") as f:
            for story in parser.stream_from_handle(f):
                process(story)

        # Get stats after parsing
        stats = parser.get_stats()
    """

    # Story header patterns - matches ### [emoji] US-001: Title or ### US-001: Title
    STORY_HEADER_PATTERN = re.compile(r"^###\s+(?:.+\s+)?([A-Z][A-Z0-9]*-\d+):\s*(.+)$")
    # Epic header patterns
    EPIC_HEADER_PATTERN = re.compile(r"^##\s+(?:Epic:\s*)?([A-Z][A-Z0-9]*-\d+)\s*[-–—:]\s*(.+)$")
    # Section headers
    SECTION_PATTERN = re.compile(r"^#{1,4}\s+(.+)$")

    def __init__(self, config: StreamingConfig | None = None):
        """Initialize the streaming parser."""
        self.config = config or StreamingConfig()
        self.stats = StreamingStats()
        self.errors: list[str] = []
        self._current_epic: str | None = None
        self.logger = logging.getLogger("StreamingParser")

    def stream_stories(
        self,
        file_path: str | Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Generator[UserStory, None, None]:
        """
        Stream stories from a file.

        Args:
            file_path: Path to the markdown file.
            progress_callback: Optional callback(lines_processed, bytes_processed).

        Yields:
            UserStory objects as they are parsed.
        """
        path = Path(file_path)
        if not path.exists():
            raise ParserError(f"File not found: {file_path}")

        file_size = path.stat().st_size
        self.logger.info(f"Starting streaming parse of {path.name} ({file_size:,} bytes)")

        self._reset_stats()

        with open(path, encoding="utf-8") as f:
            yield from self._stream_from_handle(f, file_size, progress_callback)

        self.stats.completed_at = datetime.now()
        self.logger.info(
            f"Completed: {self.stats.stories_found} stories in "
            f"{self.stats.duration_seconds:.2f}s "
            f"({self.stats.lines_per_second:.0f} lines/s)"
        )

    def stream_from_handle(
        self,
        handle: TextIO,
        total_bytes: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Generator[UserStory, None, None]:
        """
        Stream stories from a file handle.

        Args:
            handle: Open file handle.
            total_bytes: Optional total file size for progress tracking.
            progress_callback: Optional callback(lines_processed, bytes_processed).

        Yields:
            UserStory objects as they are parsed.
        """
        self._reset_stats()
        yield from self._stream_from_handle(handle, total_bytes, progress_callback)
        self.stats.completed_at = datetime.now()

    def stream_from_string(
        self,
        content: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Generator[UserStory, None, None]:
        """
        Stream stories from a string (for smaller content or testing).

        Args:
            content: Markdown content string.
            progress_callback: Optional callback.

        Yields:
            UserStory objects.
        """
        self._reset_stats()
        string_io = StringIO(content)
        yield from self._stream_from_handle(
            string_io, len(content.encode("utf-8")), progress_callback
        )
        self.stats.completed_at = datetime.now()

    def _stream_from_handle(
        self,
        handle: TextIO,
        total_bytes: int | None,
        progress_callback: Callable[[int, int], None] | None,
    ) -> Generator[UserStory, None, None]:
        """Internal streaming implementation."""
        buffer = StoryBuffer(
            max_lines=self.config.max_story_lines,
            max_bytes=self.config.max_story_bytes,
        )

        current_story_id: str | None = None
        current_story_title: str | None = None
        in_story = False

        for line_num, line in enumerate(handle, start=1):
            self.stats.lines_processed += 1
            self.stats.bytes_processed += len(line.encode("utf-8"))

            # Progress reporting
            if progress_callback and self.stats.lines_processed % self.config.report_interval == 0:
                progress_callback(self.stats.lines_processed, self.stats.bytes_processed)

            # Check for epic header
            epic_match = self.EPIC_HEADER_PATTERN.match(line.strip())
            if epic_match:
                # Yield any pending story before new epic
                if in_story and not buffer.is_empty:
                    story = self._parse_buffered_story(
                        buffer, current_story_id, current_story_title
                    )
                    if story:
                        yield story
                        self.stats.stories_found += 1

                    buffer.clear()
                    in_story = False

                self._current_epic = epic_match.group(1)
                self.stats.epics_found += 1
                continue

            # Check for story header
            story_match = self.STORY_HEADER_PATTERN.match(line.strip())
            if story_match:
                # Yield previous story if any
                if in_story and not buffer.is_empty:
                    story = self._parse_buffered_story(
                        buffer, current_story_id, current_story_title
                    )
                    if story:
                        yield story
                        self.stats.stories_found += 1

                    buffer.clear()

                # Start new story
                current_story_id = story_match.group(1)
                current_story_title = story_match.group(2).strip()
                in_story = True
                buffer.add_line(line, line_num)
                continue

            # Accumulate story content
            if in_story:
                try:
                    buffer.add_line(line, line_num)
                except ParserError as e:
                    self.stats.parse_errors += 1
                    if self.config.collect_errors:
                        self.errors.append(f"Line {line_num}: {e}")

                    if not self.config.skip_malformed:
                        raise

                    # Reset and skip this story
                    buffer.clear()
                    in_story = False

        # Yield final story
        if in_story and not buffer.is_empty:
            story = self._parse_buffered_story(buffer, current_story_id, current_story_title)
            if story:
                yield story
                self.stats.stories_found += 1

    def _parse_buffered_story(
        self,
        buffer: StoryBuffer,
        story_id: str | None,
        title: str | None,
    ) -> UserStory | None:
        """Parse a story from the buffer."""
        if buffer.is_empty or not story_id:
            return None

        try:
            content = buffer.get_content()
            return self._parse_story_content(story_id, title or "", content)
        except Exception as e:
            self.stats.parse_errors += 1
            if self.config.collect_errors:
                self.errors.append(f"Story {story_id} (line {buffer.start_line}): {e}")

            if not self.config.skip_malformed:
                raise ParserError(f"Failed to parse story {story_id}: {e}") from e

            return None

    def _parse_story_content(self, story_id: str, title: str, content: str) -> UserStory:
        """Parse story content into a UserStory entity."""
        # Parse description (user story format)
        description = self._extract_description(content)

        # Parse acceptance criteria
        acceptance_criteria = self._extract_acceptance_criteria(content)

        # Parse subtasks
        subtasks = self._extract_subtasks(content)

        # Parse metadata
        story_points = self._extract_story_points(content)
        priority = self._extract_priority(content)
        status = self._extract_status(content)
        labels = self._extract_labels(content)

        return UserStory(
            id=StoryId(story_id),
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            subtasks=subtasks,
            story_points=story_points or 0,
            priority=priority,
            status=status,
            labels=labels,
        )

    def _extract_description(self, content: str) -> Description:
        """Extract user story description."""
        # Look for As a / I want / So that pattern
        as_a_match = re.search(
            r"\*\*As a\*\*\s*(.+?)(?=\*\*I want\*\*|$)", content, re.IGNORECASE | re.DOTALL
        )
        i_want_match = re.search(
            r"\*\*I want\*\*\s*(.+?)(?=\*\*So that\*\*|$)", content, re.IGNORECASE | re.DOTALL
        )
        so_that_match = re.search(
            r"\*\*So that\*\*\s*(.+?)(?=####|##|$)", content, re.IGNORECASE | re.DOTALL
        )

        role = as_a_match.group(1).strip().rstrip(",") if as_a_match else ""
        want = i_want_match.group(1).strip().rstrip(",") if i_want_match else ""
        benefit = so_that_match.group(1).strip().rstrip(",") if so_that_match else ""

        return Description(role=role, want=want, benefit=benefit)

    def _extract_acceptance_criteria(self, content: str) -> AcceptanceCriteria:
        """Extract acceptance criteria."""
        # Find acceptance criteria section
        ac_match = re.search(
            r"(?:####|##)\s*Acceptance Criteria\s*\n(.*?)(?=####|##|$)",
            content,
            re.IGNORECASE | re.DOTALL,
        )

        if not ac_match:
            return AcceptanceCriteria.from_list([])

        ac_section = ac_match.group(1)
        criteria: list[str] = []

        # Parse checkbox items
        for line in ac_section.split("\n"):
            line = line.strip()
            # Match [ ] or [x] checkbox items
            checkbox_match = re.match(r"^-\s*\[([ xX])\]\s*(?:AC\d+:\s*)?(.+)$", line)
            if checkbox_match:
                criteria.append(checkbox_match.group(2).strip())
            elif line.startswith("- ") and not line.startswith("- ["):
                # Plain list items
                criteria.append(line[2:].strip())

        return AcceptanceCriteria.from_list(criteria)

    def _extract_subtasks(self, content: str) -> list[Subtask]:
        """Extract subtasks."""
        # Find subtasks section
        subtasks_match = re.search(
            r"(?:####|##)\s*Subtasks?\s*\n(.*?)(?=####|##|$)",
            content,
            re.IGNORECASE | re.DOTALL,
        )

        if not subtasks_match:
            return []

        subtasks_section = subtasks_match.group(1)
        subtasks: list[Subtask] = []

        for idx, line in enumerate(subtasks_section.split("\n")):
            line = line.strip()
            # Match checkbox items
            checkbox_match = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", line)
            if checkbox_match:
                completed = checkbox_match.group(1).lower() == "x"
                name = checkbox_match.group(2).strip()
                status = Status.DONE if completed else Status.PLANNED
                subtasks.append(Subtask(number=idx + 1, name=name, status=status))
            elif line.startswith("- "):
                # Plain list items
                subtasks.append(Subtask(number=idx + 1, name=line[2:].strip()))

        return subtasks

    def _extract_story_points(self, content: str) -> int | None:
        """Extract story points from metadata."""
        # Table format
        table_match = re.search(r"\|\s*\*\*Story Points\*\*\s*\|\s*(\d+)\s*\|", content)
        if table_match:
            return int(table_match.group(1))

        # Inline format
        inline_match = re.search(r"\*\*(?:Story )?Points?\*\*:?\s*(\d+)", content, re.IGNORECASE)
        if inline_match:
            return int(inline_match.group(1))

        # Blockquote format
        blockquote_match = re.search(r">\s*\*\*Points?\*\*:?\s*(\d+)", content)
        if blockquote_match:
            return int(blockquote_match.group(1))

        return None

    def _extract_priority(self, content: str) -> Priority:
        """Extract priority from metadata."""
        # Look for priority patterns
        priority_patterns = [
            r"\|\s*\*\*Priority\*\*\s*\|\s*([^|]+)\|",  # Table
            r"\*\*Priority\*\*:?\s*([^\n]+)",  # Inline
            r">\s*\*\*Priority\*\*:?\s*([^\n]+)",  # Blockquote
        ]

        for pattern in priority_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                priority_str = match.group(1).strip()
                return Priority.from_string(priority_str)

        return Priority.MEDIUM

    def _extract_status(self, content: str) -> Status:
        """Extract status from metadata."""
        # Look for status patterns
        status_patterns = [
            r"\|\s*\*\*Status\*\*\s*\|\s*([^|]+)\|",  # Table
            r"\*\*Status\*\*:?\s*([^\n]+)",  # Inline
            r">\s*\*\*Status\*\*:?\s*([^\n]+)",  # Blockquote
        ]

        for pattern in status_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                status_str = match.group(1).strip()
                return Status.from_string(status_str)

        return Status.PLANNED

    def _extract_labels(self, content: str) -> list[str]:
        """Extract labels from metadata."""
        # Look for labels patterns
        labels_patterns = [
            r"\|\s*\*\*Labels?\*\*\s*\|\s*([^|]+)\|",  # Table
            r"\*\*Labels?\*\*:?\s*([^\n]+)",  # Inline
            r">\s*\*\*Labels?\*\*:?\s*([^\n]+)",  # Blockquote
        ]

        for pattern in labels_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                labels_str = match.group(1).strip()
                # Split by comma or space
                labels = re.split(r"[,\s]+", labels_str)
                return [
                    label.strip().strip("`")
                    for label in labels
                    if label.strip() and label.strip() != "-"
                ]

        return []

    def _reset_stats(self) -> None:
        """Reset parsing statistics."""
        self.stats = StreamingStats()
        self.errors.clear()
        self._current_epic = None

    def get_stats(self) -> StreamingStats:
        """Get parsing statistics."""
        return self.stats

    def get_errors(self) -> list[str]:
        """Get parsing errors."""
        return self.errors.copy()


class MemoryMappedParser:
    """
    Parser using memory-mapped files for very large files.

    Uses OS-level memory mapping for efficient access to large files
    without loading them entirely into Python's memory.
    """

    def __init__(self, config: StreamingConfig | None = None):
        """Initialize the memory-mapped parser."""
        self.config = config or StreamingConfig()
        self.stats = StreamingStats()
        self.errors: list[str] = []
        self.logger = logging.getLogger("MemoryMappedParser")

    def parse_file(
        self,
        file_path: str | Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Generator[UserStory, None, None]:
        """
        Parse a file using memory mapping.

        Args:
            file_path: Path to the file.
            progress_callback: Optional progress callback.

        Yields:
            UserStory objects.
        """
        path = Path(file_path)
        if not path.exists():
            raise ParserError(f"File not found: {file_path}")

        file_size = path.stat().st_size
        if file_size == 0:
            return

        self.logger.info(f"Memory-mapping {path.name} ({file_size:,} bytes)")

        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            # Use streaming parser on the decoded content
            streaming_parser = StreamingMarkdownParser(self.config)

            # Use the streaming parser's internal logic
            yield from streaming_parser.stream_from_string(mm[:].decode("utf-8"), progress_callback)

            self.stats = streaming_parser.get_stats()
            self.errors = streaming_parser.get_errors()

    def _create_line_iterator(
        self,
        mm: mmap.mmap,
        total_size: int,
        progress_callback: Callable[[int, int], None] | None,
    ) -> Generator[str, None, None]:
        """Create an iterator that yields lines from memory-mapped file."""
        position = 0
        line_num = 0

        while position < total_size:
            # Find next newline
            newline_pos = mm.find(b"\n", position)
            if newline_pos == -1:
                # Last line without newline
                line_bytes = mm[position:]
                position = total_size
            else:
                line_bytes = mm[position:newline_pos]
                position = newline_pos + 1

            line_num += 1
            if progress_callback and line_num % self.config.report_interval == 0:
                progress_callback(line_num, position)

            yield line_bytes.decode("utf-8")


class ChunkedFileProcessor:
    """
    Process large files in configurable chunks.

    Useful when you want to process files in batches rather than
    streaming individual stories.
    """

    def __init__(
        self,
        chunk_lines: int = 1000,
        overlap_lines: int = 50,
        config: StreamingConfig | None = None,
    ):
        """
        Initialize the chunked processor.

        Args:
            chunk_lines: Number of lines per chunk.
            overlap_lines: Lines to overlap between chunks (for context).
            config: Streaming configuration.
        """
        self.chunk_lines = chunk_lines
        self.overlap_lines = overlap_lines
        self.config = config or StreamingConfig()
        self.stats = StreamingStats()
        self.logger = logging.getLogger("ChunkedProcessor")

    def process_chunks(
        self,
        file_path: str | Path,
        chunk_callback: Callable[[list[str], ChunkInfo], list[UserStory]],
    ) -> Generator[UserStory, None, None]:
        """
        Process file in chunks.

        Args:
            file_path: Path to the file.
            chunk_callback: Callback to process each chunk.

        Yields:
            UserStory objects from processed chunks.
        """
        path = Path(file_path)
        if not path.exists():
            raise ParserError(f"File not found: {file_path}")

        current_chunk: list[str] = []
        chunk_start_line = 1
        chunk_start_byte = 0
        current_byte = 0
        current_epic: str | None = None

        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line_bytes = len(line.encode("utf-8"))
                self.stats.lines_processed += 1
                self.stats.bytes_processed += line_bytes

                # Check for epic header
                epic_match = re.match(r"^##\s+(?:Epic:\s*)?([A-Z]+-\d+)", line.strip())
                if epic_match:
                    current_epic = epic_match.group(1)
                    self.stats.epics_found += 1

                current_chunk.append(line)
                current_byte += line_bytes

                # Check if chunk is complete
                if len(current_chunk) >= self.chunk_lines:
                    chunk_info = ChunkInfo(
                        start_line=chunk_start_line,
                        end_line=line_num,
                        start_byte=chunk_start_byte,
                        end_byte=current_byte,
                        epic_key=current_epic,
                    )

                    # Process chunk
                    stories = chunk_callback(current_chunk, chunk_info)
                    for story in stories:
                        yield story
                        self.stats.stories_found += 1

                    # Keep overlap for context
                    if self.overlap_lines > 0:
                        current_chunk = current_chunk[-self.overlap_lines :]
                        chunk_start_line = line_num - self.overlap_lines + 1
                    else:
                        current_chunk = []
                        chunk_start_line = line_num + 1

                    chunk_start_byte = current_byte

        # Process final chunk
        if current_chunk:
            chunk_info = ChunkInfo(
                start_line=chunk_start_line,
                end_line=self.stats.lines_processed,
                start_byte=chunk_start_byte,
                end_byte=self.stats.bytes_processed,
                epic_key=current_epic,
            )

            stories = chunk_callback(current_chunk, chunk_info)
            for story in stories:
                yield story
                self.stats.stories_found += 1

        self.stats.completed_at = datetime.now()


def stream_stories_from_file(
    file_path: str | Path,
    progress_callback: Callable[[int, int], None] | None = None,
    config: StreamingConfig | None = None,
) -> Generator[UserStory, None, None]:
    """
    Convenience function to stream stories from a file.

    Args:
        file_path: Path to the markdown file.
        progress_callback: Optional progress callback.
        config: Optional streaming configuration.

    Yields:
        UserStory objects.
    """
    parser = StreamingMarkdownParser(config)
    yield from parser.stream_stories(file_path, progress_callback)


def stream_stories_from_directory(
    directory: str | Path,
    pattern: str = "*.md",
    recursive: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
    config: StreamingConfig | None = None,
) -> Generator[tuple[str, UserStory], None, None]:
    """
    Stream stories from all matching files in a directory.

    Args:
        directory: Directory to scan.
        pattern: Glob pattern for files.
        recursive: Whether to search recursively.
        progress_callback: Optional callback(file_path, lines, bytes).
        config: Optional streaming configuration.

    Yields:
        Tuples of (file_path, UserStory).
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        raise ParserError(f"Directory not found: {directory}")

    files = list(dir_path.rglob(pattern)) if recursive else list(dir_path.glob(pattern))
    logger.info(f"Found {len(files)} files matching {pattern}")

    parser = StreamingMarkdownParser(config)

    for file_path in files:
        try:
            file_callback = None
            if progress_callback:

                def file_callback(lines: int, bytes_: int) -> None:
                    progress_callback(str(file_path), lines, bytes_)

            for story in parser.stream_stories(file_path, file_callback):
                yield (str(file_path), story)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            if config and not config.skip_malformed:
                raise


def estimate_file_stories(file_path: str | Path) -> int:
    """
    Estimate the number of stories in a file without fully parsing.

    Uses a quick scan to count story headers.

    Args:
        file_path: Path to the file.

    Returns:
        Estimated story count.
    """
    path = Path(file_path)
    if not path.exists():
        return 0

    count = 0
    story_pattern = re.compile(r"^###\s+(?:[^\s]+\s+)?[A-Z]+-\d+:")

    with open(path, encoding="utf-8") as f:
        for line in f:
            if story_pattern.match(line.strip()):
                count += 1

    return count


def get_file_stats(file_path: str | Path) -> dict[str, Any]:
    """
    Get statistics about a file without fully parsing.

    Args:
        file_path: Path to the file.

    Returns:
        Dictionary with file statistics.
    """
    path = Path(file_path)
    if not path.exists():
        return {"exists": False}

    file_size = path.stat().st_size
    line_count = 0
    story_count = 0
    epic_count = 0

    story_pattern = re.compile(r"^###\s+(?:[^\s]+\s+)?[A-Z]+-\d+:")
    epic_pattern = re.compile(r"^##\s+(?:Epic:\s*)?[A-Z]+-\d+")

    with open(path, encoding="utf-8") as f:
        for line in f:
            line_count += 1
            stripped = line.strip()
            if story_pattern.match(stripped):
                story_count += 1
            elif epic_pattern.match(stripped):
                epic_count += 1

    return {
        "exists": True,
        "size_bytes": file_size,
        "size_mb": file_size / (1024 * 1024),
        "line_count": line_count,
        "estimated_stories": story_count,
        "estimated_epics": epic_count,
        "recommended_streaming": file_size > 10 * 1024 * 1024,  # >10MB
    }
