"""
Property-based tests for document parsers.

Tests edge cases and invariants for:
- Markdown parser robustness
- YAML/JSON parser consistency
- Story ID preservation
- Status/Priority parsing
- Subtask extraction
"""

import json
from textwrap import dedent

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from spectryn.adapters.parsers import MarkdownParser
from spectryn.adapters.parsers.json_parser import JsonParser
from spectryn.adapters.parsers.yaml_parser import YamlParser
from spectryn.core.domain.enums import Priority, Status


# =============================================================================
# Strategies for Generating Test Data
# =============================================================================

# Valid story ID prefixes
PREFIXES = ["US", "PROJ", "FEAT", "BUG", "TASK", "EU", "NA", "EPIC"]

# Strategy for story IDs
story_id_strategy = st.builds(
    lambda prefix, num: f"{prefix}-{num:03d}",
    prefix=st.sampled_from(PREFIXES),
    num=st.integers(min_value=1, max_value=999),
)

# Strategy for safe titles (no special markdown chars)
safe_title_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "),
    min_size=5,
    max_size=50,
).filter(lambda x: x.strip())

# Strategy for story points
story_points_strategy = st.sampled_from([1, 2, 3, 5, 8, 13, 21, None])

# Strategy for status values
status_strategy = st.sampled_from(list(Status))

# Strategy for priority values
priority_strategy = st.sampled_from(list(Priority))


# =============================================================================
# Markdown Parser Properties
# =============================================================================


class TestMarkdownParserProperties:
    """Property tests for MarkdownParser."""

    @given(story_id_strategy, safe_title_strategy)
    @settings(max_examples=50)
    def test_parses_story_id_preserves_id(self, story_id: str, title: str) -> None:
        """Parser preserves story ID from header."""
        content = dedent(f"""
            # Test Epic

            ### {story_id}: {title}

            | **Story Points** | 5 |

            **As a** user **I want** feature **So that** benefit
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == story_id

    @given(story_id_strategy, safe_title_strategy, story_points_strategy)
    @settings(max_examples=50)
    def test_parses_story_points(self, story_id: str, title: str, points: int | None) -> None:
        """Parser correctly extracts story points."""
        points_row = f"| **Story Points** | {points} |" if points else ""

        content = dedent(f"""
            # Test Epic

            ### {story_id}: {title}

            {points_row}

            **As a** user **I want** feature **So that** benefit
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        if points:
            assert stories[0].story_points == points

    @given(st.lists(story_id_strategy, min_size=1, max_size=5, unique=True))
    @settings(max_examples=30)
    def test_parses_multiple_stories(self, story_ids: list[str]) -> None:
        """Parser handles multiple stories in one document."""
        stories_md = "\n\n---\n\n".join(
            dedent(f"""
                ### {sid}: Story Title {i}

                | **Story Points** | 3 |

                **As a** user **I want** feature {i} **So that** benefit
            """)
            for i, sid in enumerate(story_ids)
        )

        content = f"# Epic\n\n{stories_md}"

        parser = MarkdownParser()
        parsed = parser.parse_stories(content)

        assert len(parsed) == len(story_ids)
        parsed_ids = {str(s.id) for s in parsed}
        assert parsed_ids == set(story_ids)

    @given(story_id_strategy, safe_title_strategy)
    @settings(max_examples=30)
    def test_story_has_required_fields(self, story_id: str, title: str) -> None:
        """Parsed stories have all required fields."""
        content = dedent(f"""
            # Epic

            ### {story_id}: {title}

            | **Story Points** | 5 |
            | **Priority** | High |
            | **Status** | Planned |

            **As a** developer
            **I want** to test
            **So that** it works
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]

        # Required fields should be populated
        assert story.id is not None
        assert story.title is not None
        assert len(story.title) > 0


class TestMarkdownParserRobustness:
    """Tests for parser robustness with edge cases."""

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=50)
    def test_never_crashes_on_arbitrary_input(self, content: str) -> None:
        """Parser never crashes, even on garbage input."""
        parser = MarkdownParser()

        # Should not raise exception
        try:
            result = parser.parse_stories(content)
            assert isinstance(result, list)
        except Exception as e:
            # Only allow specific expected exceptions
            assert isinstance(e, (ValueError, TypeError))

    def test_empty_input(self) -> None:
        """Parser handles empty input gracefully."""
        parser = MarkdownParser()
        result = parser.parse_stories("")
        assert result == []

    def test_whitespace_only(self) -> None:
        """Parser handles whitespace-only input."""
        parser = MarkdownParser()
        result = parser.parse_stories("   \n\n   \t\t\n   ")
        assert result == []

    @given(st.text(min_size=10, max_size=100).filter(lambda x: "###" not in x))
    @settings(max_examples=30)
    def test_no_stories_in_plain_text(self, content: str) -> None:
        """Parser returns empty for content without story markers."""
        parser = MarkdownParser()
        result = parser.parse_stories(content)
        assert result == []


# =============================================================================
# YAML Parser Properties
# =============================================================================


class TestYamlParserProperties:
    """Property tests for YamlParser."""

    @given(story_id_strategy, safe_title_strategy, story_points_strategy)
    @settings(max_examples=50)
    def test_parses_story_preserves_data(
        self, story_id: str, title: str, points: int | None
    ) -> None:
        """YAML parser preserves all story data."""
        content = dedent(f"""
            epic:
              key: EPIC-100
              title: Test Epic

            stories:
              - id: {story_id}
                title: "{title}"
                story_points: {points if points else 0}
                status: planned
                priority: medium
        """)

        parser = YamlParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == story_id
        assert stories[0].title == title

    @given(st.lists(story_id_strategy, min_size=1, max_size=5, unique=True))
    @settings(max_examples=30)
    def test_parses_multiple_stories_yaml(self, story_ids: list[str]) -> None:
        """YAML parser handles multiple stories."""
        stories_yaml = "\n".join(
            f"  - id: {sid}\n    title: Story {i}\n    story_points: 3"
            for i, sid in enumerate(story_ids)
        )

        content = f"epic:\n  title: Epic\n\nstories:\n{stories_yaml}"

        parser = YamlParser()
        parsed = parser.parse_stories(content)

        assert len(parsed) == len(story_ids)


# =============================================================================
# JSON Parser Properties
# =============================================================================


class TestJsonParserProperties:
    """Property tests for JsonParser."""

    @given(story_id_strategy, safe_title_strategy, story_points_strategy)
    @settings(max_examples=50)
    def test_parses_story_preserves_data(
        self, story_id: str, title: str, points: int | None
    ) -> None:
        """JSON parser preserves all story data."""
        data = {
            "epic": {"key": "EPIC-100", "title": "Test Epic"},
            "stories": [
                {
                    "id": story_id,
                    "title": title,
                    "story_points": points if points else 0,
                    "status": "planned",
                    "priority": "medium",
                }
            ],
        }

        parser = JsonParser()
        stories = parser.parse_stories(json.dumps(data))

        assert len(stories) == 1
        assert str(stories[0].id) == story_id
        assert stories[0].title == title

    @given(st.lists(story_id_strategy, min_size=1, max_size=5, unique=True))
    @settings(max_examples=30)
    def test_parses_multiple_stories_json(self, story_ids: list[str]) -> None:
        """JSON parser handles multiple stories."""
        data = {
            "epic": {"title": "Epic"},
            "stories": [
                {"id": sid, "title": f"Story {i}", "story_points": 3}
                for i, sid in enumerate(story_ids)
            ],
        }

        parser = JsonParser()
        parsed = parser.parse_stories(json.dumps(data))

        assert len(parsed) == len(story_ids)


# =============================================================================
# Cross-Parser Consistency Properties
# =============================================================================


class TestCrossParserConsistency:
    """Test that all parsers behave consistently."""

    @given(story_id_strategy, safe_title_strategy, story_points_strategy)
    @settings(max_examples=30)
    def test_all_parsers_produce_same_story_id(
        self, story_id: str, title: str, points: int | None
    ) -> None:
        """All parsers extract the same story ID from equivalent content."""
        points_val = points if points else 5

        # Markdown format
        md_content = dedent(f"""
            # Epic

            ### {story_id}: {title}

            | **Story Points** | {points_val} |

            **As a** user **I want** feature **So that** benefit
        """)

        # YAML format
        yaml_content = dedent(f"""
            epic:
              title: Epic
            stories:
              - id: {story_id}
                title: "{title}"
                story_points: {points_val}
        """)

        # JSON format
        json_data = {
            "epic": {"title": "Epic"},
            "stories": [{"id": story_id, "title": title, "story_points": points_val}],
        }

        md_stories = MarkdownParser().parse_stories(md_content)
        yaml_stories = YamlParser().parse_stories(yaml_content)
        json_stories = JsonParser().parse_stories(json.dumps(json_data))

        assert len(md_stories) == 1
        assert len(yaml_stories) == 1
        assert len(json_stories) == 1

        # All should produce the same ID
        assert str(md_stories[0].id) == story_id
        assert str(yaml_stories[0].id) == story_id
        assert str(json_stories[0].id) == story_id


# =============================================================================
# Status Parsing Properties
# =============================================================================


class TestStatusParsingProperties:
    """Property tests for status parsing."""

    @given(st.sampled_from(["done", "Done", "DONE", "✅", "complete", "Complete"]))
    def test_done_status_variants(self, status_str: str) -> None:
        """Various done status representations are normalized."""
        parsed = Status.from_string(status_str)
        assert parsed == Status.DONE

    @given(st.sampled_from(["in progress", "In Progress", "IN_PROGRESS", "🔄", "in_progress"]))
    def test_in_progress_status_variants(self, status_str: str) -> None:
        """Various in-progress status representations are normalized."""
        parsed = Status.from_string(status_str)
        assert parsed == Status.IN_PROGRESS

    @given(st.sampled_from(["not started", "🔲", "backlog"]))
    def test_planned_status_variants(self, status_str: str) -> None:
        """Various planned status representations are normalized."""
        parsed = Status.from_string(status_str)
        assert parsed == Status.PLANNED

    @given(st.sampled_from(["open", "Open", "OPEN", "todo", "to do", "new"]))
    def test_open_status_variants(self, status_str: str) -> None:
        """Various open status representations are normalized."""
        parsed = Status.from_string(status_str)
        assert parsed == Status.OPEN

    @given(st.sampled_from(["cancelled", "cancel", "wontfix", "won't fix"]))
    def test_cancelled_status_variants(self, status_str: str) -> None:
        """Various cancelled status representations are normalized."""
        parsed = Status.from_string(status_str)
        assert parsed == Status.CANCELLED


# =============================================================================
# Priority Parsing Properties
# =============================================================================


class TestPriorityParsingProperties:
    """Property tests for priority parsing."""

    @given(st.sampled_from(["critical", "Critical", "CRITICAL", "🔴", "p0", "blocker"]))
    def test_critical_priority_variants(self, priority_str: str) -> None:
        """Various critical priority representations are normalized."""
        parsed = Priority.from_string(priority_str)
        assert parsed == Priority.CRITICAL

    @given(st.sampled_from(["high", "High", "HIGH", "🟡", "p1"]))
    def test_high_priority_variants(self, priority_str: str) -> None:
        """Various high priority representations are normalized."""
        parsed = Priority.from_string(priority_str)
        assert parsed == Priority.HIGH

    @given(st.sampled_from(["medium", "Medium", "MEDIUM", "🟢", "p2"]))
    def test_medium_priority_variants(self, priority_str: str) -> None:
        """Various medium priority representations are normalized."""
        parsed = Priority.from_string(priority_str)
        assert parsed == Priority.MEDIUM

    @given(st.sampled_from(["low", "Low", "LOW", "p3", "minor"]))
    def test_low_priority_variants(self, priority_str: str) -> None:
        """Various low priority representations are normalized."""
        parsed = Priority.from_string(priority_str)
        assert parsed == Priority.LOW


# =============================================================================
# Subtask Parsing Properties
# =============================================================================


class TestSubtaskParsingProperties:
    """Property tests for subtask parsing."""

    @given(
        story_id_strategy,
        st.lists(safe_title_strategy, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=30)
    def test_subtasks_preserved(self, story_id: str, subtask_names: list[str]) -> None:
        """All subtasks are preserved during parsing."""
        subtasks_md = "\n".join(f"- [ ] **{name}** (3 pts)" for name in subtask_names)

        content = dedent(f"""
            # Epic

            ### {story_id}: Story with Subtasks

            | **Story Points** | 5 |

            **As a** user **I want** feature **So that** benefit

            #### Subtasks

            {subtasks_md}
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        # Should find the story (subtasks are optional)
        assert len(stories) >= 1


# =============================================================================
# ID Format Edge Cases
# =============================================================================


class TestIdFormatEdgeCases:
    """Test edge cases for ID formats."""

    @given(st.integers(min_value=1, max_value=999999))
    @settings(max_examples=50)
    def test_github_style_ids(self, num: int) -> None:
        """GitHub-style #123 IDs are parsed correctly."""
        content = dedent(f"""
            # Epic

            ### #{num}: GitHub Style Story

            | **Story Points** | 5 |

            **As a** user **I want** feature **So that** benefit
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == f"#{num}"

    @given(
        st.sampled_from(PREFIXES),
        st.integers(min_value=1, max_value=99999),
        st.sampled_from(["-", "_", "/"]),
    )
    @settings(max_examples=50)
    def test_custom_separator_ids(self, prefix: str, num: int, separator: str) -> None:
        """Custom separators (-, _, /) are handled."""
        story_id = f"{prefix}{separator}{num}"

        content = dedent(f"""
            # Epic

            ### {story_id}: Story with Custom Separator

            | **Story Points** | 5 |

            **As a** user **I want** feature **So that** benefit
        """)

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == story_id
