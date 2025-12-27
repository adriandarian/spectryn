"""Tests for Protobuf parser."""

import textwrap

import pytest

from spectra.adapters.parsers.protobuf_parser import ProtobufParser
from spectra.core.domain.enums import Priority, Status


class TestProtobufParser:
    """Tests for ProtobufParser."""

    @pytest.fixture
    def parser(self) -> ProtobufParser:
        """Create parser instance."""
        return ProtobufParser()

    @pytest.fixture
    def sample_proto(self) -> str:
        """Sample protobuf content with stories."""
        return textwrap.dedent("""
            // Epic: PROJ-123 - User Management API
            // Epic Key: PROJ-123
            syntax = "proto3";

            package user.v1;

            // PROJ-001: Create User Endpoint
            // Story Points: 5
            // Priority: High
            // Status: Planned
            //
            // Description:
            // As a client application
            // I want to create new users via API
            // So that users can be onboarded
            //
            // Acceptance Criteria:
            // - [ ] Validates required fields
            // - [x] Returns created user ID
            message CreateUserRequest {
                string email = 1;
                string name = 2;
                optional string phone = 3;
            }

            // PROJ-002: Get User Endpoint
            // Story Points: 3
            // Priority: Medium
            // Status: Done
            message GetUserRequest {
                string user_id = 1;
            }
        """)

    def test_name(self, parser: ProtobufParser) -> None:
        """Test parser name."""
        assert parser.name == "Protobuf"

    def test_supported_extensions(self, parser: ProtobufParser) -> None:
        """Test supported file extensions."""
        assert ".proto" in parser.supported_extensions

    def test_can_parse_proto_content(self, parser: ProtobufParser, sample_proto: str) -> None:
        """Test can_parse with proto content."""
        assert parser.can_parse(sample_proto) is True

    def test_cannot_parse_plain_text(self, parser: ProtobufParser) -> None:
        """Test can_parse with plain text."""
        assert parser.can_parse("Just plain text") is False

    def test_parse_stories(self, parser: ProtobufParser, sample_proto: str) -> None:
        """Test parsing stories from proto content."""
        stories = parser.parse_stories(sample_proto)

        assert len(stories) == 2

        # First story
        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "Create User Endpoint"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.PLANNED

        # Description
        assert story1.description is not None
        assert "client application" in story1.description.role

        # Acceptance criteria
        assert len(story1.acceptance_criteria.items) == 2

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: ProtobufParser, sample_proto: str) -> None:
        """Test parsing epic from proto content."""
        epic = parser.parse_epic(sample_proto)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert "User Management API" in epic.title
        assert len(epic.stories) == 2

    def test_validate_valid_content(self, parser: ProtobufParser, sample_proto: str) -> None:
        """Test validation of valid proto content."""
        errors = parser.validate(sample_proto)
        assert len(errors) == 0

    def test_validate_missing_syntax(self, parser: ProtobufParser) -> None:
        """Test validation of proto without syntax declaration."""
        content = textwrap.dedent("""
            message Test {
                string field = 1;
            }
        """)
        errors = parser.validate(content)
        assert any("syntax" in e.lower() for e in errors)

    def test_parse_file(self, parser: ProtobufParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            syntax = "proto3";

            // PROJ-001: Test Endpoint
            // Story Points: 3
            message TestRequest {
                string id = 1;
            }
        """)

        proto_file = tmp_path / "service.proto"
        proto_file.write_text(content)

        stories = parser.parse_stories(proto_file)
        assert len(stories) == 1
        assert str(stories[0].id) == "PROJ-001"
