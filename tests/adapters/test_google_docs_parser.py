"""Tests for Google Docs parser."""

import pytest

from spectryn.adapters.parsers.google_docs_parser import GoogleDocsParser


class TestGoogleDocsParser:
    """Tests for GoogleDocsParser."""

    @pytest.fixture
    def parser(self) -> GoogleDocsParser:
        """Create parser instance."""
        return GoogleDocsParser()

    def test_name(self, parser: GoogleDocsParser) -> None:
        """Test parser name."""
        assert parser.name == "GoogleDocs"

    def test_supported_extensions(self, parser: GoogleDocsParser) -> None:
        """Test supported file extensions (empty for API-based parser)."""
        assert parser.supported_extensions == []

    def test_can_parse_google_docs_url(self, parser: GoogleDocsParser) -> None:
        """Test can_parse with Google Docs URL."""
        url = "https://docs.google.com/document/d/1abcdefghijklmnopqrstuvwxyz12345/edit"
        assert parser.can_parse(url) is True

    def test_can_parse_document_id(self, parser: GoogleDocsParser) -> None:
        """Test can_parse with document ID."""
        doc_id = "1abcdefghijklmnopqrstuvwxyz12345"
        assert parser.can_parse(doc_id) is True

    def test_cannot_parse_file_path(self, parser: GoogleDocsParser, tmp_path) -> None:
        """Test can_parse rejects file paths."""
        test_file = tmp_path / "test.md"
        test_file.write_text("content")
        assert parser.can_parse(test_file) is False

    def test_cannot_parse_short_string(self, parser: GoogleDocsParser) -> None:
        """Test can_parse rejects short strings."""
        assert parser.can_parse("short") is False

    def test_validate_missing_credentials(self, parser: GoogleDocsParser) -> None:
        """Test validation fails without credentials."""
        errors = parser.validate("1abcdefghijklmnopqrstuvwxyz12345")
        assert any("credentials" in e.lower() for e in errors)

    def test_validate_rejects_file_path(self, parser: GoogleDocsParser, tmp_path) -> None:
        """Test validation rejects file paths."""
        parser_with_creds = GoogleDocsParser(
            credentials={"type": "service_account", "project_id": "test"}
        )
        test_file = tmp_path / "test.md"
        test_file.write_text("content")

        errors = parser_with_creds.validate(test_file)
        assert any("url" in e.lower() or "document id" in e.lower() for e in errors)

    def test_extract_document_id_from_url(self, parser: GoogleDocsParser) -> None:
        """Test extracting document ID from URL."""
        url = "https://docs.google.com/document/d/1abcdefghijklmnopqrstuvwxyz12345/edit"
        doc_id = parser._extract_document_id(url)
        assert doc_id == "1abcdefghijklmnopqrstuvwxyz12345"

    def test_extract_document_id_direct(self, parser: GoogleDocsParser) -> None:
        """Test extracting direct document ID."""
        doc_id = "1abcdefghijklmnopqrstuvwxyz12345"
        result = parser._extract_document_id(doc_id)
        assert result == doc_id

    def test_extract_epic_key(self, parser: GoogleDocsParser) -> None:
        """Test extracting epic key from content."""
        content = "Epic Key: PROJ-123\nSome other content"
        key = parser._extract_epic_key(content)
        assert key == "PROJ-123"

    def test_extract_field_table(self, parser: GoogleDocsParser) -> None:
        """Test extracting field from table format."""
        content = "| Story Points | 5 |\n| Priority | High |"
        assert parser._extract_field(content, "Story Points", "0") == "5"

    def test_extract_field_inline(self, parser: GoogleDocsParser) -> None:
        """Test extracting field from inline format."""
        content = "Story Points: 8\nPriority: Critical"
        assert parser._extract_field(content, "Story Points", "0") == "8"

    def test_extract_description(self, parser: GoogleDocsParser) -> None:
        """Test extracting user story description."""
        content = "As a user I want to test so that it works"
        description = parser._extract_description(content)
        assert description is not None
        assert description.role == "user"

    def test_extract_acceptance_criteria_checkboxes(self, parser: GoogleDocsParser) -> None:
        """Test extracting acceptance criteria with checkbox characters."""
        content = """
        Acceptance Criteria
        ☑ First item done
        ☐ Second item pending
        """
        ac = parser._extract_acceptance_criteria(content)
        assert len(ac.items) == 2

    def test_extract_acceptance_criteria_standard(self, parser: GoogleDocsParser) -> None:
        """Test extracting acceptance criteria with standard checkboxes."""
        content = """
        Acceptance Criteria
        [x] First item done
        [ ] Second item pending
        """
        ac = parser._extract_acceptance_criteria(content)
        assert len(ac.items) == 2

    def test_parse_stories_from_text(self, parser: GoogleDocsParser) -> None:
        """Test parsing stories from text content."""
        content = """
        PROJ-001: First Story

        Story Points: 5
        Priority: High
        Status: Planned

        As a user I want feature so that benefit

        PROJ-002: Second Story

        Story Points: 3
        Priority: Medium
        Status: Done
        """
        stories = parser._parse_stories_from_text(content)
        assert len(stories) == 2
        assert str(stories[0].id) == "PROJ-001"
        assert str(stories[1].id) == "PROJ-002"
