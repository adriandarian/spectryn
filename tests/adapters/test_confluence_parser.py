"""Tests for Confluence Cloud API parser."""

import pytest

from spectra.adapters.parsers.confluence_parser import ConfluenceParser


class TestConfluenceParser:
    """Tests for ConfluenceParser."""

    @pytest.fixture
    def parser(self) -> ConfluenceParser:
        """Create parser instance."""
        return ConfluenceParser()

    def test_name(self, parser: ConfluenceParser) -> None:
        """Test parser name."""
        assert parser.name == "Confluence"

    def test_supported_extensions(self, parser: ConfluenceParser) -> None:
        """Test supported file extensions (empty for API-based parser)."""
        assert parser.supported_extensions == []

    def test_can_parse_confluence_url(self, parser: ConfluenceParser) -> None:
        """Test can_parse with Confluence URL."""
        url = "https://company.atlassian.net/wiki/spaces/PROJ/pages/12345"
        assert parser.can_parse(url) is True

    def test_can_parse_page_id(self, parser: ConfluenceParser) -> None:
        """Test can_parse with page ID."""
        assert parser.can_parse("12345") is True

    def test_cannot_parse_file_path(self, parser: ConfluenceParser, tmp_path) -> None:
        """Test can_parse rejects file paths."""
        test_file = tmp_path / "test.md"
        test_file.write_text("content")
        assert parser.can_parse(test_file) is False

    def test_cannot_parse_plain_text(self, parser: ConfluenceParser) -> None:
        """Test can_parse rejects plain text."""
        assert parser.can_parse("Just some text") is False

    def test_validate_missing_credentials(self, parser: ConfluenceParser) -> None:
        """Test validation fails without credentials."""
        errors = parser.validate("12345")
        assert any("not configured" in e.lower() for e in errors)

    def test_validate_rejects_file_path(self, parser: ConfluenceParser, tmp_path) -> None:
        """Test validation rejects file paths."""
        parser_with_creds = ConfluenceParser(
            base_url="https://test.atlassian.net/wiki",
            username="test@example.com",
            api_token="test-token",
        )
        test_file = tmp_path / "test.md"
        test_file.write_text("content")

        errors = parser_with_creds.validate(test_file)
        assert any("file path" in e.lower() for e in errors)

    def test_extract_page_id_from_url(self, parser: ConfluenceParser) -> None:
        """Test extracting page ID from various URL formats."""
        # Standard format
        url1 = "https://company.atlassian.net/wiki/spaces/PROJ/pages/12345/Title"
        assert parser._extract_page_id(url1) == "12345"

        # With pageId parameter
        url2 = "https://company.atlassian.net/wiki?pageId=67890"
        assert parser._extract_page_id(url2) == "67890"

        # Direct ID
        assert parser._extract_page_id("12345") == "12345"

    def test_extract_epic_key_from_title(self, parser: ConfluenceParser) -> None:
        """Test extracting epic key from title."""
        content = "Epic Key: PROJ-123"
        key = parser._extract_epic_key("Test Title", content)
        assert key == "PROJ-123"

    def test_extract_epic_key_from_title_pattern(self, parser: ConfluenceParser) -> None:
        """Test extracting epic key from title pattern."""
        key = parser._extract_epic_key("PROJ-123: Epic Title", "")
        assert key == "PROJ-123"

    def test_html_to_text(self, parser: ConfluenceParser) -> None:
        """Test HTML to text conversion."""
        html = "<p>Hello <strong>world</strong></p><p>Next line</p>"
        text = parser._html_to_text(html)
        assert "Hello" in text
        assert "world" in text

    def test_extract_field_from_table(self, parser: ConfluenceParser) -> None:
        """Test extracting field from table format."""
        content = "| Story Points | 5 |\n| Priority | High |"
        assert parser._extract_field(content, "Story Points", "0") == "5"
        assert parser._extract_field(content, "Priority", "Medium") == "High"

    def test_extract_field_inline(self, parser: ConfluenceParser) -> None:
        """Test extracting field from inline format."""
        content = "Story Points: 8\nPriority: Critical"
        assert parser._extract_field(content, "Story Points", "0") == "8"
        assert parser._extract_field(content, "Priority", "Medium") == "Critical"

    def test_extract_description(self, parser: ConfluenceParser) -> None:
        """Test extracting user story description."""
        content = "As a user I want to test so that it works"
        description = parser._extract_description(content)
        assert description is not None
        assert description.role == "user"
        assert "test" in description.want

    def test_extract_acceptance_criteria(self, parser: ConfluenceParser) -> None:
        """Test extracting acceptance criteria."""
        content = """
        Acceptance Criteria
        [x] First item done
        [ ] Second item pending
        """
        ac = parser._extract_acceptance_criteria(content)
        assert len(ac.items) == 2
