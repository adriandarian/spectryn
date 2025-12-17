"""Tests for Markdown parser adapter."""


class TestMarkdownParser:
    """Tests for MarkdownParser."""

    def test_can_parse_markdown_file(self, markdown_parser, tmp_path):
        """Test parser recognizes markdown files."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Test")

        assert markdown_parser.can_parse(md_file)

    def test_can_parse_markdown_content(self, markdown_parser, sample_markdown):
        """Test parser recognizes markdown content."""
        assert markdown_parser.can_parse(sample_markdown)

    def test_supported_extensions(self, markdown_parser):
        """Test supported file extensions."""
        assert ".md" in markdown_parser.supported_extensions
        assert ".markdown" in markdown_parser.supported_extensions

    def test_parse_stories_count(self, markdown_parser, sample_markdown):
        """Test correct number of stories parsed."""
        stories = markdown_parser.parse_stories(sample_markdown)
        assert len(stories) == 2

    def test_parse_story_id(self, markdown_parser, sample_markdown):
        """Test story ID extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        assert str(stories[0].id) == "US-001"
        assert str(stories[1].id) == "US-002"

    def test_parse_story_title(self, markdown_parser, sample_markdown):
        """Test story title extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        assert stories[0].title == "First Story"

    def test_parse_story_points(self, markdown_parser, sample_markdown):
        """Test story points extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        assert stories[0].story_points == 5
        assert stories[1].story_points == 3

    def test_parse_priority(self, markdown_parser, sample_markdown):
        """Test priority extraction."""
        from spectra.core.domain import Priority

        stories = markdown_parser.parse_stories(sample_markdown)
        assert stories[0].priority == Priority.HIGH
        assert stories[1].priority == Priority.MEDIUM

    def test_parse_status(self, markdown_parser, sample_markdown):
        """Test status extraction."""
        from spectra.core.domain import Status

        stories = markdown_parser.parse_stories(sample_markdown)
        assert stories[0].status == Status.DONE
        assert stories[1].status == Status.IN_PROGRESS

    def test_parse_description(self, markdown_parser, sample_markdown):
        """Test description extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        desc = stories[0].description

        assert desc is not None
        assert desc.role == "developer"
        assert "test parsing" in desc.want

    def test_parse_acceptance_criteria(self, markdown_parser, sample_markdown):
        """Test acceptance criteria extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        ac = stories[0].acceptance_criteria

        assert len(ac) == 2
        # First item is checked
        items = list(ac)
        assert items[0][1] is True  # checked
        assert items[1][1] is False  # not checked

    def test_parse_subtasks(self, markdown_parser, sample_markdown):
        """Test subtask extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        subtasks = stories[0].subtasks

        assert len(subtasks) == 2
        assert subtasks[0].name == "Create parser"
        assert subtasks[0].story_points == 3

    def test_parse_commits(self, markdown_parser, sample_markdown):
        """Test commit extraction."""
        stories = markdown_parser.parse_stories(sample_markdown)
        commits = stories[0].commits

        assert len(commits) == 2
        assert commits[0].hash == "abc1234"
        assert "Initial parser" in commits[0].message

    def test_validate_valid_markdown(self, markdown_parser, sample_markdown):
        """Test validation of valid markdown."""
        errors = markdown_parser.validate(sample_markdown)
        assert len(errors) == 0

    def test_validate_missing_stories(self, markdown_parser):
        """Test validation catches missing stories."""
        content = "# Epic without stories"
        errors = markdown_parser.validate(content)
        assert len(errors) > 0

    def test_parse_from_file(self, markdown_parser, sample_markdown, tmp_path):
        """Test parsing from file path."""
        md_file = tmp_path / "epic.md"
        md_file.write_text(sample_markdown, encoding="utf-8")

        stories = markdown_parser.parse_stories(str(md_file))
        assert len(stories) == 2
