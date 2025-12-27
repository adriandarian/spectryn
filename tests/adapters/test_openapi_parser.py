"""Tests for OpenAPI/Swagger parser."""

import textwrap

import pytest

from spectra.adapters.parsers.openapi_parser import OpenAPIParser
from spectra.core.domain.enums import Priority, Status


class TestOpenAPIParser:
    """Tests for OpenAPIParser."""

    @pytest.fixture
    def parser(self) -> OpenAPIParser:
        """Create parser instance."""
        return OpenAPIParser()

    @pytest.fixture
    def sample_openapi(self) -> str:
        """Sample OpenAPI content with stories."""
        return textwrap.dedent("""
            openapi: "3.0.0"
            info:
              title: User API
              version: "1.0.0"
              x-spectra-epic-key: PROJ-123

            paths:
              /users:
                post:
                  operationId: createUser
                  summary: Create a new user
                  x-spectra-story-id: PROJ-001
                  x-spectra-story-points: 5
                  x-spectra-priority: High
                  x-spectra-status: Planned
                  x-spectra-acceptance-criteria:
                    - Validates email format
                    - Returns user ID
                  description: |
                    As a client application
                    I want to create new users
                    So that users can register

                    ## Technical Notes
                    Use bcrypt for passwords.
                  responses:
                    201:
                      description: User created

                get:
                  operationId: listUsers
                  summary: List all users
                  x-spectra-story-id: PROJ-002
                  x-spectra-story-points: 3
                  x-spectra-priority: Medium
                  x-spectra-status: Done
                  responses:
                    200:
                      description: User list

              /users/{id}:
                get:
                  operationId: getUser
                  summary: Get user by ID
                  x-spectra-story-id: PROJ-003
                  x-spectra-story-points: 2
                  responses:
                    200:
                      description: User found
        """)

    def test_name(self, parser: OpenAPIParser) -> None:
        """Test parser name."""
        assert parser.name == "OpenAPI"

    def test_supported_extensions(self, parser: OpenAPIParser) -> None:
        """Test supported file extensions."""
        assert ".yaml" in parser.supported_extensions
        assert ".yml" in parser.supported_extensions
        assert ".json" in parser.supported_extensions

    def test_can_parse_openapi_content(self, parser: OpenAPIParser, sample_openapi: str) -> None:
        """Test can_parse with OpenAPI content."""
        assert parser.can_parse(sample_openapi) is True

    def test_cannot_parse_plain_yaml(self, parser: OpenAPIParser) -> None:
        """Test can_parse with plain YAML."""
        plain_yaml = "key: value\nother: data"
        assert parser.can_parse(plain_yaml) is False

    def test_parse_stories(self, parser: OpenAPIParser, sample_openapi: str) -> None:
        """Test parsing stories from OpenAPI content."""
        stories = parser.parse_stories(sample_openapi)

        assert len(stories) == 3

        # First story
        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "Create a new user"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH
        assert story1.status == Status.PLANNED

        # Description
        assert story1.description is not None
        assert "client application" in story1.description.role

        # Acceptance criteria from extension
        assert len(story1.acceptance_criteria.items) == 2

        # Technical notes
        assert "bcrypt" in story1.technical_notes

        # Second story
        story2 = stories[1]
        assert str(story2.id) == "PROJ-002"
        assert story2.status == Status.DONE

    def test_parse_epic(self, parser: OpenAPIParser, sample_openapi: str) -> None:
        """Test parsing epic from OpenAPI content."""
        epic = parser.parse_epic(sample_openapi)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert epic.title == "User API"
        assert len(epic.stories) == 3

    def test_validate_valid_content(self, parser: OpenAPIParser, sample_openapi: str) -> None:
        """Test validation of valid OpenAPI content."""
        errors = parser.validate(sample_openapi)
        assert len(errors) == 0

    def test_validate_invalid_yaml(self, parser: OpenAPIParser) -> None:
        """Test validation of invalid content."""
        errors = parser.validate("Not valid YAML: {broken")
        assert len(errors) > 0

    def test_validate_no_stories(self, parser: OpenAPIParser) -> None:
        """Test validation of OpenAPI without story extensions."""
        content = textwrap.dedent("""
            openapi: "3.0.0"
            info:
              title: Test API
              version: "1.0.0"
            paths:
              /test:
                get:
                  summary: Test endpoint
                  responses:
                    200:
                      description: OK
        """)
        errors = parser.validate(content)
        assert any("story" in e.lower() for e in errors)

    def test_parse_swagger_2(self, parser: OpenAPIParser) -> None:
        """Test parsing Swagger 2.0 format."""
        content = textwrap.dedent("""
            swagger: "2.0"
            info:
              title: Legacy API
              version: "1.0.0"
              x-spectra-epic-key: LEGACY-001
            paths:
              /items:
                get:
                  operationId: listItems
                  summary: List items
                  x-spectra-story-id: LEGACY-001
                  x-spectra-story-points: 2
                  responses:
                    200:
                      description: OK
        """)

        assert parser.can_parse(content) is True
        stories = parser.parse_stories(content)
        assert len(stories) == 1

    def test_parse_with_subtasks(self, parser: OpenAPIParser) -> None:
        """Test parsing with x-spectra-subtasks extension."""
        content = textwrap.dedent("""
            openapi: "3.0.0"
            info:
              title: Test API
              version: "1.0.0"
            paths:
              /test:
                post:
                  operationId: createTest
                  summary: Create test
                  x-spectra-story-id: TEST-001
                  x-spectra-subtasks:
                    - name: Implement endpoint
                      story_points: 2
                      status: Planned
                    - name: Write tests
                      story_points: 1
                      status: Done
                  responses:
                    201:
                      description: Created
        """)

        stories = parser.parse_stories(content)
        assert len(stories) == 1
        assert len(stories[0].subtasks) == 2

    def test_parse_file(self, parser: OpenAPIParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            openapi: "3.0.0"
            info:
              title: Test API
              version: "1.0.0"
            paths:
              /test:
                get:
                  summary: Test
                  x-spectra-story-id: TEST-001
                  x-spectra-story-points: 3
                  responses:
                    200:
                      description: OK
        """)

        yaml_file = tmp_path / "api.yaml"
        yaml_file.write_text(content)

        stories = parser.parse_stories(yaml_file)
        assert len(stories) == 1
        assert str(stories[0].id) == "TEST-001"
