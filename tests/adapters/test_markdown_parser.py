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


# =============================================================================
# Inline Format Tests (Format B - SpaceMouse style)
# =============================================================================


class TestMarkdownParserInlineFormat:
    """Tests for inline metadata format parsing (Format B)."""

    INLINE_FORMAT_MARKDOWN = '''
# SpaceMouse Integration User Stories

**Epic**: UPP-57735 - Pathologist Using a Space Mouse

---

### US-001: Technical Design Document

**Priority**: P0
**Story Points**: 5
**Status**: ✅ Complete

#### User Story

> **As a** development team member,
> **I want** a comprehensive technical design document,
> **So that** I can understand the architecture before development.

#### Description

Create detailed technical documentation.

#### Acceptance Criteria

- [ ] Architecture diagram created
- [x] Complete list of supported devices
- [ ] TypeScript interfaces defined

#### Dependencies

- None (this is the first story)

---

### US-002: WebHID Connection Service

**Priority**: P1
**Story Points**: 8
**Status**: 🔲 Not Started

#### User Story

> **As a** pathologist,
> **I want** to connect my SpaceMouse through my browser,
> **So that** I can navigate slides without extra software.

#### Acceptance Criteria

- [ ] Can request device connection
- [ ] Handles disconnection gracefully
'''

    def test_detect_inline_format(self, markdown_parser):
        """Test format detection identifies inline format."""
        content = self.INLINE_FORMAT_MARKDOWN
        detected = markdown_parser._detect_format(content)
        assert detected == markdown_parser.FORMAT_INLINE

    def test_parse_inline_story_count(self, markdown_parser):
        """Test parsing inline format returns correct story count."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert len(stories) == 2

    def test_parse_inline_story_id(self, markdown_parser):
        """Test story ID extraction from inline format."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert str(stories[0].id) == "US-001"
        assert str(stories[1].id) == "US-002"

    def test_parse_inline_story_title(self, markdown_parser):
        """Test story title extraction from inline format."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert stories[0].title == "Technical Design Document"
        assert stories[1].title == "WebHID Connection Service"

    def test_parse_inline_story_points(self, markdown_parser):
        """Test story points extraction from inline format."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert stories[0].story_points == 5
        assert stories[1].story_points == 8

    def test_parse_inline_priority(self, markdown_parser):
        """Test priority extraction from inline format with P0/P1 notation."""
        from spectra.core.domain import Priority

        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert stories[0].priority == Priority.CRITICAL  # P0
        assert stories[1].priority == Priority.HIGH  # P1

    def test_parse_inline_status_complete(self, markdown_parser):
        """Test status extraction for Complete status."""
        from spectra.core.domain import Status

        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert stories[0].status == Status.DONE  # ✅ Complete

    def test_parse_inline_status_not_started(self, markdown_parser):
        """Test status extraction for Not Started status."""
        from spectra.core.domain import Status

        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        assert stories[1].status == Status.PLANNED  # 🔲 Not Started

    def test_parse_blockquote_description(self, markdown_parser):
        """Test description extraction from blockquote User Story section."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        desc = stories[0].description

        assert desc is not None
        assert desc.role == "development team member"
        assert "technical design document" in desc.want
        assert "architecture" in desc.benefit

    def test_parse_inline_acceptance_criteria(self, markdown_parser):
        """Test acceptance criteria extraction from inline format."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_MARKDOWN)
        ac = stories[0].acceptance_criteria

        assert len(ac) == 3
        items = list(ac)
        # Second item is checked
        assert items[0][1] is False
        assert items[1][1] is True  # Complete list of supported devices
        assert items[2][1] is False

    def test_validate_inline_format(self, markdown_parser):
        """Test validation passes for inline format."""
        errors = markdown_parser.validate(self.INLINE_FORMAT_MARKDOWN)
        assert len(errors) == 0

    def test_can_parse_inline_format(self, markdown_parser):
        """Test can_parse recognizes inline format markdown."""
        assert markdown_parser.can_parse(self.INLINE_FORMAT_MARKDOWN)


# =============================================================================
# Mixed Format Tests
# =============================================================================


class TestMarkdownParserFormatDetection:
    """Tests for format detection and mixed scenarios."""

    TABLE_FORMAT_SAMPLE = '''
### ✅ US-001: Table Format Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | ✅ Done |

#### Description

**As a** developer
**I want** table format
**So that** it works
'''

    INLINE_FORMAT_SAMPLE = '''
### US-001: Inline Format Story

**Priority**: P0
**Story Points**: 3
**Status**: ✅ Complete

#### User Story

> **As a** user,
> **I want** inline format,
> **So that** it also works.
'''

    def test_detect_table_format(self, markdown_parser):
        """Test detecting table-based metadata format."""
        detected = markdown_parser._detect_format(self.TABLE_FORMAT_SAMPLE)
        assert detected == markdown_parser.FORMAT_TABLE

    def test_detect_inline_format(self, markdown_parser):
        """Test detecting inline metadata format."""
        detected = markdown_parser._detect_format(self.INLINE_FORMAT_SAMPLE)
        assert detected == markdown_parser.FORMAT_INLINE

    def test_parse_table_format(self, markdown_parser):
        """Test parsing table format still works."""
        stories = markdown_parser.parse_stories(self.TABLE_FORMAT_SAMPLE)
        assert len(stories) == 1
        assert stories[0].story_points == 5

    def test_parse_inline_format(self, markdown_parser):
        """Test parsing inline format works."""
        stories = markdown_parser.parse_stories(self.INLINE_FORMAT_SAMPLE)
        assert len(stories) == 1
        assert stories[0].story_points == 3


class TestCommentsExtraction:
    """Tests for comments section parsing."""

    COMMENTS_SAMPLE = '''
### US-001: Story With Comments

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |

#### Description

**As a** user
**I want** to track discussions
**So that** context is preserved

#### Comments

> **@reviewer** (2025-01-15):
> This looks good overall.
> Consider adding error handling.

> **@developer** (2025-01-16):
> Thanks! Will add in next iteration.

> Simple comment without author
'''

    def test_extract_comments_with_author_and_date(self, markdown_parser):
        """Test extracting comments with full metadata."""
        stories = markdown_parser.parse_stories(self.COMMENTS_SAMPLE)
        assert len(stories) == 1

        comments = stories[0].comments
        assert len(comments) >= 2

        # First comment with author and date
        first_comment = comments[0]
        assert first_comment.author == "reviewer"
        assert first_comment.created_at is not None
        assert first_comment.created_at.year == 2025
        assert "looks good" in first_comment.body

    def test_extract_comment_body_multiline(self, markdown_parser):
        """Test multiline comment body extraction."""
        stories = markdown_parser.parse_stories(self.COMMENTS_SAMPLE)
        comments = stories[0].comments

        # First comment spans multiple lines
        first_comment = comments[0]
        assert "error handling" in first_comment.body

    def test_extract_comment_without_author(self, markdown_parser):
        """Test extracting comments without author metadata."""
        stories = markdown_parser.parse_stories(self.COMMENTS_SAMPLE)
        comments = stories[0].comments

        # Last comment has no author
        last_comment = comments[-1]
        assert "Simple comment" in last_comment.body

    def test_no_comments_section(self, markdown_parser, sample_markdown):
        """Test parsing markdown without comments section."""
        stories = markdown_parser.parse_stories(sample_markdown)
        # Should return empty list, not error
        assert stories[0].comments == []

