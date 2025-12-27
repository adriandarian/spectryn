"""Tests for PlantUML/Mermaid diagram parser."""

import textwrap

import pytest

from spectra.adapters.parsers.diagram_parser import DiagramParser
from spectra.core.domain.enums import Priority, Status


class TestDiagramParser:
    """Tests for DiagramParser."""

    @pytest.fixture
    def parser(self) -> DiagramParser:
        """Create parser instance."""
        return DiagramParser()

    @pytest.fixture
    def sample_plantuml(self) -> str:
        """Sample PlantUML content with stories."""
        return textwrap.dedent("""
            @startuml
            ' Epic: PROJ-123 - User Flow
            ' Epic Key: PROJ-123

            title User Registration Flow

            actor User
            participant "Web App" as App
            participant "API" as API
            database "DB" as DB

            note over App
            PROJ-001: User Registration
            Story Points: 5
            Priority: High
            Status: Planned

            As a user
            I want to register an account
            So that I can access the system

            Acceptance Criteria:
            - [ ] Email validation
            - [x] Password strength check
            end note

            User -> App: Submit form
            App -> API: POST /register
            API -> DB: Create user

            note over API
            PROJ-002: API Validation
            Story Points: 3
            Priority: Medium
            Status: Done
            end note

            @enduml
        """)

    @pytest.fixture
    def sample_mermaid(self) -> str:
        """Sample Mermaid content with stories."""
        return textwrap.dedent("""
            %%{ Epic: PROJ-123 - User Flow }%%
            %%{ Epic Key: PROJ-123 }%%

            sequenceDiagram
                %% PROJ-001: User Registration
                %% Story Points: 5
                %% Priority: High
                %% Status: Planned
                %%
                %% As a user
                %% I want to register
                %% So that I can access

                User->>App: Submit form
                App->>API: POST /register
                API->>DB: Create user
        """)

    def test_name(self, parser: DiagramParser) -> None:
        """Test parser name."""
        assert parser.name == "Diagram"

    def test_supported_extensions(self, parser: DiagramParser) -> None:
        """Test supported file extensions."""
        assert ".puml" in parser.supported_extensions
        assert ".plantuml" in parser.supported_extensions
        assert ".mmd" in parser.supported_extensions
        assert ".mermaid" in parser.supported_extensions

    def test_can_parse_plantuml_content(self, parser: DiagramParser, sample_plantuml: str) -> None:
        """Test can_parse with PlantUML content."""
        assert parser.can_parse(sample_plantuml) is True

    def test_can_parse_mermaid_content(self, parser: DiagramParser, sample_mermaid: str) -> None:
        """Test can_parse with Mermaid content."""
        assert parser.can_parse(sample_mermaid) is True

    def test_cannot_parse_plain_text(self, parser: DiagramParser) -> None:
        """Test can_parse with plain text."""
        assert parser.can_parse("Just plain text") is False

    def test_parse_plantuml_stories(self, parser: DiagramParser, sample_plantuml: str) -> None:
        """Test parsing stories from PlantUML content."""
        stories = parser.parse_stories(sample_plantuml)

        assert len(stories) >= 1

        # First story
        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.title == "User Registration"
        assert story1.story_points == 5
        assert story1.priority == Priority.HIGH

        # Description
        assert story1.description is not None

        # Acceptance criteria
        assert len(story1.acceptance_criteria.items) == 2

    def test_parse_mermaid_stories(self, parser: DiagramParser, sample_mermaid: str) -> None:
        """Test parsing stories from Mermaid content."""
        stories = parser.parse_stories(sample_mermaid)

        assert len(stories) >= 1

        story1 = stories[0]
        assert str(story1.id) == "PROJ-001"
        assert story1.story_points == 5

    def test_parse_epic_plantuml(self, parser: DiagramParser, sample_plantuml: str) -> None:
        """Test parsing epic from PlantUML content."""
        epic = parser.parse_epic(sample_plantuml)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"
        assert "User Flow" in epic.title

    def test_parse_epic_mermaid(self, parser: DiagramParser, sample_mermaid: str) -> None:
        """Test parsing epic from Mermaid content."""
        epic = parser.parse_epic(sample_mermaid)

        assert epic is not None
        assert str(epic.key) == "PROJ-123"

    def test_validate_valid_content(self, parser: DiagramParser, sample_plantuml: str) -> None:
        """Test validation of valid diagram content."""
        errors = parser.validate(sample_plantuml)
        assert len(errors) == 0

    def test_validate_invalid_content(self, parser: DiagramParser) -> None:
        """Test validation of invalid diagram content."""
        errors = parser.validate("Not a diagram")
        assert any("valid" in e.lower() for e in errors)

    def test_parse_file(self, parser: DiagramParser, tmp_path) -> None:
        """Test parsing from file."""
        content = textwrap.dedent("""
            @startuml

            note over Actor
            PROJ-001: Test Story
            Story Points: 3
            end note

            @enduml
        """)

        puml_file = tmp_path / "flow.puml"
        puml_file.write_text(content)

        stories = parser.parse_stories(puml_file)
        assert len(stories) == 1
        assert str(stories[0].id) == "PROJ-001"
