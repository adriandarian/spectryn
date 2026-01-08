"""Tests for JSON Parser."""

import json
from pathlib import Path

import pytest

from spectryn.adapters.parsers import JsonParser
from spectryn.core.domain.enums import Priority, Status


class TestJsonParser:
    """Tests for JsonParser class."""

    @pytest.fixture
    def parser(self) -> JsonParser:
        """Create a JSON parser instance."""
        return JsonParser()

    def test_name(self, parser: JsonParser) -> None:
        """Test parser name property."""
        assert parser.name == "JSON"

    def test_supported_extensions(self, parser: JsonParser) -> None:
        """Test supported file extensions."""
        assert parser.supported_extensions == [".json"]

    def test_can_parse_json_file(self, parser: JsonParser, tmp_path: Path) -> None:
        """Test can_parse with JSON file."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"stories": []}')
        assert parser.can_parse(json_file) is True

    def test_can_parse_non_json_file(self, parser: JsonParser, tmp_path: Path) -> None:
        """Test can_parse rejects non-JSON files."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")
        assert parser.can_parse(md_file) is False

    def test_can_parse_json_content(self, parser: JsonParser) -> None:
        """Test can_parse with JSON content string."""
        content = '{"stories": []}'
        assert parser.can_parse(content) is True

    def test_can_parse_invalid_json(self, parser: JsonParser) -> None:
        """Test can_parse with invalid JSON."""
        content = "not valid json"
        assert parser.can_parse(content) is False

    def test_parse_stories_minimal(self, parser: JsonParser) -> None:
        """Test parsing minimal story structure."""
        content = json.dumps({"stories": [{"id": "US-001", "title": "Test Story"}]})

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert str(stories[0].id) == "US-001"
        assert stories[0].title == "Test Story"

    def test_parse_stories_full(self, parser: JsonParser) -> None:
        """Test parsing story with all fields."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Full Story",
                        "description": {
                            "as_a": "developer",
                            "i_want": "to parse JSON",
                            "so_that": "I can use structured data",
                        },
                        "story_points": 5,
                        "priority": "high",
                        "status": "in_progress",
                        "acceptance_criteria": [
                            {"criterion": "Parse valid JSON", "done": True},
                            {"criterion": "Handle errors", "done": False},
                        ],
                        "subtasks": [
                            {
                                "name": "Implement parser",
                                "description": "Write the code",
                                "story_points": 3,
                                "status": "done",
                            }
                        ],
                        "technical_notes": "Use standard library",
                        "links": [{"type": "blocks", "target": "PROJ-123"}],
                        "comments": [
                            {"body": "Good progress", "author": "user1", "created_at": "2025-01-15"}
                        ],
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Full Story"
        assert story.description is not None
        assert story.description.role == "developer"
        assert story.description.want == "to parse JSON"
        assert story.description.benefit == "I can use structured data"
        assert story.story_points == 5
        assert story.priority == Priority.HIGH
        assert story.status == Status.IN_PROGRESS
        assert len(story.acceptance_criteria.items) == 2
        assert len(story.subtasks) == 1
        assert story.subtasks[0].name == "Implement parser"
        assert story.technical_notes == "Use standard library"
        assert len(story.links) == 1
        assert story.links[0] == ("blocks", "PROJ-123")
        assert len(story.comments) == 1
        assert story.comments[0].body == "Good progress"
        assert story.comments[0].author == "user1"

    def test_parse_epic(self, parser: JsonParser) -> None:
        """Test parsing epic structure."""
        content = json.dumps(
            {
                "epic": {
                    "key": "PROJ-100",
                    "title": "Test Epic",
                    "description": "Epic description",
                },
                "stories": [
                    {"id": "US-001", "title": "Story 1"},
                    {"id": "US-002", "title": "Story 2"},
                ],
            }
        )

        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert epic.title == "Test Epic"
        assert epic.description == "Epic description"
        assert len(epic.stories) == 2

    def test_parse_epic_no_stories(self, parser: JsonParser) -> None:
        """Test parsing epic without stories."""
        content = json.dumps({"epic": {"key": "PROJ-100", "title": "Empty Epic"}})

        epic = parser.parse_epic(content)

        assert epic is not None
        assert str(epic.key) == "PROJ-100"
        assert len(epic.stories) == 0

    def test_parse_description_string(self, parser: JsonParser) -> None:
        """Test parsing description as simple string."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Test",
                        "description": "As a user, I want to login, so that I can access my account",
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)
        assert stories[0].description is not None
        assert stories[0].description.role == "user"
        assert stories[0].description.want == "to login"
        assert stories[0].description.benefit == "I can access my account"

    def test_parse_links_shorthand(self, parser: JsonParser) -> None:
        """Test parsing links with shorthand format."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Test",
                        "links": [{"blocks": "PROJ-123"}, {"depends_on": ["A-1", "B-2"]}],
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)
        links = stories[0].links
        assert len(links) == 3
        assert ("blocks", "PROJ-123") in links
        assert ("depends on", "A-1") in links
        assert ("depends on", "B-2") in links

    def test_parse_comments_simple(self, parser: JsonParser) -> None:
        """Test parsing simple string comments."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Test",
                        "comments": ["Simple comment", "Another comment"],
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)
        comments = stories[0].comments
        assert len(comments) == 2
        assert comments[0].body == "Simple comment"
        assert comments[0].author is None
        assert comments[1].body == "Another comment"

    def test_validate_valid(self, parser: JsonParser) -> None:
        """Test validation passes for valid JSON."""
        content = json.dumps({"stories": [{"id": "US-001", "title": "Valid Story"}]})

        errors = parser.validate(content)
        assert errors == []

    def test_validate_missing_id(self, parser: JsonParser) -> None:
        """Test validation catches missing id."""
        content = json.dumps({"stories": [{"title": "No ID"}]})

        errors = parser.validate(content)
        assert any("id" in e for e in errors)

    def test_validate_missing_title(self, parser: JsonParser) -> None:
        """Test validation catches missing title."""
        content = json.dumps({"stories": [{"id": "US-001"}]})

        errors = parser.validate(content)
        assert any("title" in e for e in errors)

    def test_validate_invalid_priority(self, parser: JsonParser) -> None:
        """Test validation catches invalid priority."""
        content = json.dumps(
            {"stories": [{"id": "US-001", "title": "Test", "priority": "invalid"}]}
        )

        errors = parser.validate(content)
        assert any("priority" in e for e in errors)

    def test_validate_invalid_status(self, parser: JsonParser) -> None:
        """Test validation catches invalid status."""
        content = json.dumps({"stories": [{"id": "US-001", "title": "Test", "status": "invalid"}]})

        errors = parser.validate(content)
        assert any("status" in e for e in errors)

    def test_validate_invalid_json(self, parser: JsonParser) -> None:
        """Test validation handles invalid JSON."""
        content = "not valid json"

        errors = parser.validate(content)
        assert len(errors) > 0
        assert any("Invalid JSON" in e for e in errors)

    def test_parse_from_file(self, parser: JsonParser, tmp_path: Path) -> None:
        """Test parsing from actual file."""
        json_file = tmp_path / "stories.json"
        json_file.write_text(json.dumps({"stories": [{"id": "US-001", "title": "From File"}]}))

        stories = parser.parse_stories(json_file)
        assert len(stories) == 1
        assert stories[0].title == "From File"

    def test_parse_subtasks_string_format(self, parser: JsonParser) -> None:
        """Test parsing subtasks as simple strings."""
        content = json.dumps(
            {"stories": [{"id": "US-001", "title": "Test", "subtasks": ["Task 1", "Task 2"]}]}
        )

        stories = parser.parse_stories(content)
        subtasks = stories[0].subtasks
        assert len(subtasks) == 2
        assert subtasks[0].name == "Task 1"
        assert subtasks[0].number == 1
        assert subtasks[1].name == "Task 2"
        assert subtasks[1].number == 2

    def test_parse_commits(self, parser: JsonParser) -> None:
        """Test parsing commit references."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Test",
                        "commits": [{"hash": "abc123def456", "message": "Fix bug"}, "deadbeef"],
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)
        commits = stories[0].commits
        assert len(commits) == 2
        assert commits[0].hash == "abc123de"  # Truncated to 8 chars
        assert commits[0].message == "Fix bug"
        assert commits[1].hash == "deadbeef"
        assert commits[1].message == ""

    def test_parse_acceptance_criteria_string_format(self, parser: JsonParser) -> None:
        """Test parsing acceptance criteria as simple strings."""
        content = json.dumps(
            {
                "stories": [
                    {
                        "id": "US-001",
                        "title": "Test",
                        "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                    }
                ]
            }
        )

        stories = parser.parse_stories(content)
        ac = stories[0].acceptance_criteria
        assert len(ac.items) == 2
        assert "Criterion 1" in ac.items
        assert "Criterion 2" in ac.items
