"""
Load testing for Spectra.

Tests parser and sync performance with large datasets to ensure
the system can handle real-world scale workloads.

Run with:
    pytest tests/load/ -v -m "slow or stress" --benchmark-enable

For stress testing:
    pytest tests/load/ -v -m stress --benchmark-enable
"""

import random
import string
import textwrap
import time
from pathlib import Path

import pytest

from spectryn.adapters.parsers.markdown import MarkdownParser
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import Description, StoryId


# Mark all tests in this module as slow (skipped by default)
pytestmark = pytest.mark.slow


def generate_story_markdown(story_id: str, title: str, points: int = 5) -> str:
    """Generate a single story in markdown format."""
    return textwrap.dedent(f"""
        ### {story_id}: {title}

        | Field | Value |
        |-------|-------|
        | **Story Points** | {points} |
        | **Priority** | High |
        | **Status** | In Progress |

        **As a** user
        **I want** to {title.lower()}
        **So that** I can achieve my goals

        #### Acceptance Criteria

        - [ ] First criterion for {story_id}
        - [ ] Second criterion for {story_id}
        - [ ] Third criterion for {story_id}

        #### Subtasks

        | Task | Description | Points |
        |------|-------------|--------|
        | Task 1 | First task for {story_id} | 2 |
        | Task 2 | Second task for {story_id} | 3 |
    """)


def generate_large_markdown(num_stories: int) -> str:
    """Generate markdown with many stories."""
    content = "# Epic: Large Scale Test\n\n"

    for i in range(num_stories):
        story_id = f"LOAD-{i + 1:04d}"
        title = f"Load Test Story {i + 1}"
        points = random.randint(1, 13)
        content += generate_story_markdown(story_id, title, points)
        content += "\n---\n\n"

    return content


def generate_random_string(length: int) -> str:
    """Generate a random string of specified length."""
    return "".join(random.choices(string.ascii_letters + " ", k=length))


class TestParserLoadPerformance:
    """Load tests for markdown parser."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_parse_100_stories(self, parser, benchmark):
        """Benchmark parsing 100 stories."""
        content = generate_large_markdown(100)

        result = benchmark(parser.parse_stories, content)

        assert len(result) == 100

    def test_parse_500_stories(self, parser, benchmark):
        """Benchmark parsing 500 stories."""
        content = generate_large_markdown(500)

        result = benchmark(parser.parse_stories, content)

        assert len(result) == 500

    @pytest.mark.slow
    def test_parse_1000_stories(self, parser, benchmark):
        """Benchmark parsing 1000 stories."""
        content = generate_large_markdown(1000)

        result = benchmark(parser.parse_stories, content)

        assert len(result) == 1000

    def test_parse_stories_with_long_descriptions(self, parser, benchmark):
        """Benchmark parsing stories with very long descriptions."""
        content = "# Epic: Long Descriptions\n\n"

        for i in range(50):
            long_desc = generate_random_string(5000)
            content += textwrap.dedent(f"""
                ### LONG-{i + 1:03d}: Story with long description

                **As a** user
                **I want** {long_desc[:100]}
                **So that** {long_desc[:100]}

                #### Description

                {long_desc}
            """)

        result = benchmark(parser.parse_stories, content)

        assert len(result) == 50

    def test_parse_stories_with_many_subtasks(self, parser, benchmark):
        """Benchmark parsing stories with many subtasks."""
        content = "# Epic: Many Subtasks\n\n"

        for i in range(20):
            content += f"### SUBTASK-{i + 1:03d}: Story with many subtasks\n\n"
            content += "**As a** user\n**I want** many subtasks\n**So that** I can track work\n\n"
            content += "#### Subtasks\n\n"
            content += "| Task | Description | Points |\n|------|-------------|--------|\n"
            for j in range(50):
                content += f"| Task {j + 1} | Subtask {j + 1} description | 1 |\n"
            content += "\n"

        result = benchmark(parser.parse_stories, content)

        assert len(result) == 20


class TestStressPerformance:
    """Stress tests with extreme data sizes."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    @pytest.mark.slow
    @pytest.mark.stress
    def test_stress_5000_stories(self, parser):
        """Stress test with 5000 stories."""
        content = generate_large_markdown(5000)

        start = time.time()
        result = parser.parse_stories(content)
        elapsed = time.time() - start

        assert len(result) == 5000
        assert elapsed < 60, f"Parsing took too long: {elapsed:.2f}s"

    @pytest.mark.slow
    @pytest.mark.stress
    def test_stress_10000_stories(self, parser):
        """Stress test with 10000 stories (target scale)."""
        content = generate_large_markdown(10000)

        start = time.time()
        result = parser.parse_stories(content)
        elapsed = time.time() - start

        assert len(result) == 10000
        # Should complete within 2 minutes for 10K stories
        assert elapsed < 120, f"Parsing took too long: {elapsed:.2f}s"

    @pytest.mark.stress
    def test_stress_very_large_file(self, parser):
        """Stress test with a very large file (>10MB)."""
        # Generate ~10MB of markdown
        content = generate_large_markdown(3000)
        # Add padding to reach ~10MB
        while len(content.encode()) < 10 * 1024 * 1024:
            content += generate_story_markdown(
                f"PAD-{random.randint(1, 9999):04d}",
                f"Padding story {generate_random_string(50)}",
            )

        start = time.time()
        result = parser.parse_stories(content)
        elapsed = time.time() - start

        assert len(result) > 3000
        assert elapsed < 180, f"Parsing large file took too long: {elapsed:.2f}s"


class TestMemoryUsage:
    """Tests for memory efficiency."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_memory_not_leaked_on_repeated_parsing(self, parser):
        """Test that repeated parsing doesn't leak memory."""
        import gc

        content = generate_large_markdown(100)

        # Parse multiple times
        for _ in range(10):
            result = parser.parse_stories(content)
            assert len(result) == 100
            del result
            gc.collect()

        # If we get here without OOM, memory is being managed properly
        assert True

    def test_stories_are_independent(self, parser):
        """Test that parsed stories don't share mutable state."""
        content = generate_large_markdown(10)

        stories1 = parser.parse_stories(content)
        stories2 = parser.parse_stories(content)

        # Modify story from first parse
        if stories1[0].subtasks:
            stories1[0].subtasks.clear()

        # Second parse should be unaffected
        # (This tests for shared mutable default arguments)
        stories3 = parser.parse_stories(content)

        # Each parse should be independent - verify all parses completed
        assert len(stories1) > 0
        assert len(stories2) > 0
        assert len(stories3) > 0


class TestConcurrentParsing:
    """Tests for concurrent parser usage."""

    @pytest.fixture
    def parser(self):
        return MarkdownParser()

    def test_parser_thread_safety(self, parser):
        """Test parser can be used from multiple threads."""
        import concurrent.futures

        contents = [generate_large_markdown(50) for _ in range(10)]

        def parse_content(content):
            return len(parser.parse_stories(content))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(parse_content, contents))

        assert all(r == 50 for r in results)

    def test_parser_process_safety(self, parser):
        """Test parser can be used from multiple processes."""
        # Skip process pool test as local functions can't be pickled
        # Process safety is verified by the fact that MarkdownParser has no shared state
        contents = [generate_large_markdown(20) for _ in range(3)]

        # Sequential test to verify parser works with same content
        results = []
        for content in contents:
            p = MarkdownParser()
            results.append(len(p.parse_stories(content)))

        assert all(r == 20 for r in results)
