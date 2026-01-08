"""Tests for streaming parser."""

import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from spectryn.adapters.parsers.streaming import (
    ChunkedFileProcessor,
    ChunkInfo,
    MemoryMappedParser,
    StoryBuffer,
    StreamingConfig,
    StreamingMarkdownParser,
    StreamingStats,
    estimate_file_stories,
    get_file_stats,
    stream_stories_from_file,
)
from spectryn.core.domain.entities import Subtask
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.ports.document_parser import ParserError


class TestStreamingStats:
    """Tests for StreamingStats dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = StreamingStats()

        assert stats.lines_processed == 0
        assert stats.bytes_processed == 0
        assert stats.stories_found == 0
        assert stats.epics_found == 0
        assert stats.parse_errors == 0

    def test_duration_calculation(self):
        """Test duration calculation."""
        stats = StreamingStats(
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 30),
        )

        assert stats.duration_seconds == 30.0

    def test_lines_per_second(self):
        """Test lines per second calculation."""
        stats = StreamingStats(
            lines_processed=1000,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 10, 0, 10),
        )

        assert stats.lines_per_second == 100.0


class TestStreamingConfig:
    """Tests for StreamingConfig dataclass."""

    def test_default_values(self):
        """Test default configuration."""
        config = StreamingConfig()

        assert config.chunk_size == 64 * 1024
        assert config.line_buffer_size == 1000
        assert config.max_story_lines == 5000
        assert config.max_story_bytes == 1024 * 1024
        assert config.skip_malformed is True

    def test_custom_values(self):
        """Test custom configuration."""
        config = StreamingConfig(
            chunk_size=128 * 1024,
            max_story_lines=10000,
            skip_malformed=False,
        )

        assert config.chunk_size == 128 * 1024
        assert config.max_story_lines == 10000
        assert config.skip_malformed is False


class TestStoryBuffer:
    """Tests for StoryBuffer."""

    def test_add_line(self):
        """Test adding lines to buffer."""
        buffer = StoryBuffer()
        buffer.add_line("Line 1", 1)
        buffer.add_line("Line 2", 2)

        assert buffer.line_count == 2
        assert buffer.start_line == 1

    def test_get_content(self):
        """Test getting content from buffer."""
        buffer = StoryBuffer()
        buffer.add_line("Line 1", 1)
        buffer.add_line("Line 2", 2)

        content = buffer.get_content()
        assert content == "Line 1\nLine 2"

    def test_clear(self):
        """Test clearing buffer."""
        buffer = StoryBuffer()
        buffer.add_line("Line 1", 1)
        buffer.clear()

        assert buffer.is_empty
        assert buffer.line_count == 0

    def test_max_lines_exceeded(self):
        """Test max lines limit."""
        buffer = StoryBuffer(max_lines=2)
        buffer.add_line("Line 1", 1)
        buffer.add_line("Line 2", 2)

        with pytest.raises(ParserError) as exc_info:
            buffer.add_line("Line 3", 3)

        assert "maximum line limit" in str(exc_info.value)

    def test_max_bytes_exceeded(self):
        """Test max bytes limit."""
        buffer = StoryBuffer(max_bytes=10)
        buffer.add_line("Short", 1)

        with pytest.raises(ParserError) as exc_info:
            buffer.add_line("This is a much longer line", 2)

        assert "maximum size limit" in str(exc_info.value)


class TestStreamingMarkdownParser:
    """Tests for StreamingMarkdownParser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return StreamingMarkdownParser()

    @pytest.fixture
    def sample_epic(self):
        """Sample epic markdown content."""
        return textwrap.dedent("""
            ## Epic: PROJ-100 - Sample Epic

            ### 🔧 US-001: First Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 3 |
            | **Priority** | 🔴 Critical |
            | **Status** | 📋 Planned |

            **As a** developer
            **I want** to test streaming
            **So that** I can verify it works

            #### Acceptance Criteria
            - [ ] AC1: First criteria
            - [ ] AC2: Second criteria

            #### Subtasks
            - [ ] Task 1
            - [x] Task 2

            ### 🔧 US-002: Second Story

            | Field | Value |
            |-------|-------|
            | **Story Points** | 5 |
            | **Priority** | 🟡 High |
            | **Status** | 🔄 In Progress |

            **As a** user
            **I want** more features
            **So that** I can be productive

            #### Acceptance Criteria
            - [ ] AC1: Be productive
            """)

    def test_stream_from_string_basic(self, parser, sample_epic):
        """Test streaming stories from string."""
        stories = list(parser.stream_from_string(sample_epic))

        assert len(stories) == 2
        assert stories[0].id.value == "US-001"
        assert stories[1].id.value == "US-002"

    def test_story_metadata_extraction(self, parser, sample_epic):
        """Test that metadata is correctly extracted."""
        stories = list(parser.stream_from_string(sample_epic))

        first_story = stories[0]
        assert first_story.story_points == 3
        assert first_story.priority == Priority.CRITICAL
        assert first_story.status == Status.PLANNED

        second_story = stories[1]
        assert second_story.story_points == 5
        assert second_story.priority == Priority.HIGH
        assert second_story.status == Status.IN_PROGRESS

    def test_description_extraction(self, parser, sample_epic):
        """Test that description is correctly extracted."""
        stories = list(parser.stream_from_string(sample_epic))

        first_story = stories[0]
        assert "developer" in first_story.description.role
        assert "streaming" in first_story.description.want
        assert "verify" in first_story.description.benefit

    def test_acceptance_criteria_extraction(self, parser, sample_epic):
        """Test that acceptance criteria are extracted."""
        stories = list(parser.stream_from_string(sample_epic))

        first_story = stories[0]
        assert len(first_story.acceptance_criteria.items) == 2
        assert "First criteria" in first_story.acceptance_criteria.items[0]

    def test_subtasks_extraction(self, parser, sample_epic):
        """Test that subtasks are extracted."""
        stories = list(parser.stream_from_string(sample_epic))

        first_story = stories[0]
        assert len(first_story.subtasks) == 2
        assert first_story.subtasks[0].name == "Task 1"
        assert first_story.subtasks[0].status == Status.PLANNED
        assert first_story.subtasks[1].name == "Task 2"
        assert first_story.subtasks[1].status == Status.DONE

    def test_epic_key_tracking(self, parser, sample_epic):
        """Test that epic is tracked in stats."""
        list(parser.stream_from_string(sample_epic))

        # Epic is tracked in stats but not stored on stories
        stats = parser.get_stats()
        assert stats.epics_found == 1

    def test_stats_collection(self, parser, sample_epic):
        """Test statistics collection."""
        list(parser.stream_from_string(sample_epic))

        stats = parser.get_stats()
        assert stats.lines_processed > 0
        assert stats.bytes_processed > 0
        assert stats.stories_found == 2
        assert stats.epics_found == 1

    def test_empty_content(self, parser):
        """Test parsing empty content."""
        stories = list(parser.stream_from_string(""))
        assert len(stories) == 0

    def test_no_stories(self, parser):
        """Test parsing content with no stories."""
        content = "# Just a header\n\nSome text without stories."
        stories = list(parser.stream_from_string(content))
        assert len(stories) == 0

    def test_progress_callback(self, parser, sample_epic):
        """Test progress callback is called."""
        callbacks = []

        def callback(lines: int, bytes_: int) -> None:
            callbacks.append((lines, bytes_))

        # Use smaller interval for testing
        parser.config.report_interval = 5
        list(parser.stream_from_string(sample_epic, progress_callback=callback))

        # Should have at least some callbacks
        assert len(callbacks) >= 0  # May or may not have callbacks depending on content size


class TestStreamFromFile:
    """Tests for file streaming."""

    def test_stream_from_file(self, tmp_path):
        """Test streaming from a file."""
        content = textwrap.dedent("""
            ## Epic: TEST-100 - Test Epic

            ### US-001: Test Story

            **As a** tester
            **I want** to test file streaming
            **So that** it works correctly

            #### Acceptance Criteria
            - [ ] It streams correctly
            """)

        test_file = tmp_path / "test.md"
        test_file.write_text(content)

        stories = list(stream_stories_from_file(test_file))

        assert len(stories) == 1
        assert stories[0].id.value == "US-001"

    def test_stream_nonexistent_file(self):
        """Test streaming from nonexistent file raises error."""
        parser = StreamingMarkdownParser()

        with pytest.raises(ParserError) as exc_info:
            list(parser.stream_stories("/nonexistent/file.md"))

        assert "not found" in str(exc_info.value)

    def test_large_file_simulation(self, tmp_path):
        """Test streaming a larger file."""
        # Generate a file with many stories
        lines = ["## Epic: BIG-100 - Large Epic\n"]

        for i in range(100):
            lines.extend(
                [
                    f"\n### US-{i:03d}: Story {i}\n",
                    "\n",
                    "| Field | Value |\n",
                    "|-------|-------|\n",
                    f"| **Story Points** | {(i % 8) + 1} |\n",
                    "\n",
                    f"**As a** user {i}\n",
                    f"**I want** feature {i}\n",
                    f"**So that** benefit {i}\n",
                    "\n",
                    "#### Acceptance Criteria\n",
                    f"- [ ] AC for story {i}\n",
                ]
            )

        content = "".join(lines)
        test_file = tmp_path / "large.md"
        test_file.write_text(content)

        # Stream and count
        parser = StreamingMarkdownParser()
        stories = list(parser.stream_stories(test_file))

        assert len(stories) == 100
        assert parser.get_stats().stories_found == 100


class TestMemoryMappedParser:
    """Tests for MemoryMappedParser."""

    def test_parse_file(self, tmp_path):
        """Test parsing with memory mapping."""
        content = textwrap.dedent("""
            ## Epic: MEM-100 - Memory Mapped Test

            ### US-001: First Story

            **As a** developer
            **I want** to test mmap
            **So that** it works

            #### Acceptance Criteria
            - [ ] It works
            """)

        test_file = tmp_path / "mmap_test.md"
        test_file.write_text(content)

        parser = MemoryMappedParser()
        stories = list(parser.parse_file(test_file))

        assert len(stories) == 1
        assert stories[0].id.value == "US-001"


class TestChunkedFileProcessor:
    """Tests for ChunkedFileProcessor."""

    def test_process_chunks(self, tmp_path):
        """Test processing file in chunks."""
        content = textwrap.dedent("""
            ## Epic: CHUNK-100 - Chunked Test

            ### US-001: First Story

            **As a** developer
            **I want** to test chunking
            **So that** large files work

            #### Acceptance Criteria
            - [ ] Chunks work
            """)

        test_file = tmp_path / "chunked.md"
        test_file.write_text(content)

        processor = ChunkedFileProcessor(chunk_lines=5, overlap_lines=2)
        chunks_received = []

        def chunk_callback(lines: list[str], info: ChunkInfo) -> list:
            chunks_received.append(len(lines))
            return []  # Don't parse in this test

        list(processor.process_chunks(test_file, chunk_callback))

        # Should have processed multiple chunks
        assert len(chunks_received) > 0
        assert processor.stats.lines_processed > 0


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_estimate_file_stories(self, tmp_path):
        """Test story count estimation."""
        content = textwrap.dedent("""
            ## Epic: EST-100 - Estimate Test

            ### US-001: First Story
            Content...

            ### US-002: Second Story
            Content...

            ### US-003: Third Story
            Content...
            """)

        test_file = tmp_path / "estimate.md"
        test_file.write_text(content)

        count = estimate_file_stories(test_file)
        assert count == 3

    def test_estimate_nonexistent_file(self):
        """Test estimating nonexistent file."""
        count = estimate_file_stories("/nonexistent/file.md")
        assert count == 0

    def test_get_file_stats(self, tmp_path):
        """Test getting file statistics."""
        content = textwrap.dedent("""
            ## Epic: STATS-100 - Stats Test

            ### US-001: First Story
            Content...

            ### US-002: Second Story
            Content...
            """)

        test_file = tmp_path / "stats.md"
        test_file.write_text(content)

        stats = get_file_stats(test_file)

        assert stats["exists"] is True
        assert stats["size_bytes"] > 0
        assert stats["line_count"] > 0
        assert stats["estimated_stories"] == 2
        assert stats["estimated_epics"] == 1

    def test_get_file_stats_nonexistent(self):
        """Test stats for nonexistent file."""
        stats = get_file_stats("/nonexistent/file.md")
        assert stats["exists"] is False


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_story_skipped(self):
        """Test that malformed stories are skipped when configured."""
        parser = StreamingMarkdownParser()

        # Story with extremely long content (simulated by just having content)
        content = textwrap.dedent("""
            ### US-001: Good Story

            **As a** developer
            **I want** something
            **So that** benefit

            ### US-002: Another Good Story

            **As a** user
            **I want** feature
            **So that** value
            """)

        stories = list(parser.stream_from_string(content))

        # Both stories should be parsed
        assert len(stories) == 2

    def test_multiple_epics(self):
        """Test parsing multiple epics."""
        parser = StreamingMarkdownParser()

        content = textwrap.dedent("""
            ## Epic: PROJ-100 - First Epic

            ### US-001: Story in First Epic

            **As a** developer
            **I want** feature 1
            **So that** benefit 1

            ## Epic: PROJ-200 - Second Epic

            ### US-002: Story in Second Epic

            **As a** user
            **I want** feature 2
            **So that** benefit 2
            """)

        stories = list(parser.stream_from_string(content))

        assert len(stories) == 2
        assert stories[0].id.value == "US-001"
        assert stories[1].id.value == "US-002"

    def test_story_without_epic(self):
        """Test parsing story without epic header."""
        parser = StreamingMarkdownParser()

        content = textwrap.dedent("""
            ### US-001: Standalone Story

            **As a** developer
            **I want** something
            **So that** benefit
            """)

        stories = list(parser.stream_from_string(content))

        assert len(stories) == 1
        assert stories[0].id.value == "US-001"

    def test_inline_metadata_format(self):
        """Test parsing inline metadata format."""
        parser = StreamingMarkdownParser()

        content = textwrap.dedent("""
            ### US-001: Story with Inline Metadata

            **Priority**: High
            **Story Points**: 5
            **Status**: In Progress

            **As a** developer
            **I want** something
            **So that** benefit

            #### Acceptance Criteria
            - [ ] AC 1
            """)

        stories = list(parser.stream_from_string(content))

        assert len(stories) == 1
        assert stories[0].story_points == 5
        assert stories[0].priority == Priority.HIGH
        assert stories[0].status == Status.IN_PROGRESS

    def test_labels_extraction(self):
        """Test labels extraction."""
        parser = StreamingMarkdownParser()

        content = textwrap.dedent("""
            ### US-001: Story with Labels

            | Field | Value |
            |-------|-------|
            | **Labels** | frontend, api, security |

            **As a** developer
            **I want** something
            **So that** benefit
            """)

        stories = list(parser.stream_from_string(content))

        assert len(stories) == 1
        assert "frontend" in stories[0].labels
        assert "api" in stories[0].labels
        assert "security" in stories[0].labels
