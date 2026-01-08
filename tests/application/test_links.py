"""
Tests for cross-project linking - link stories across Jira projects.
"""

from unittest.mock import Mock

import pytest

from spectryn.adapters.parsers.markdown import MarkdownParser
from spectryn.application.sync.links import (
    LinkChange,
    LinkSyncOrchestrator,
    LinkSyncResult,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.value_objects import IssueKey, StoryId
from spectryn.core.ports.issue_tracker import IssueLink, LinkType


class TestLinkType:
    """Tests for LinkType enum."""

    def test_from_string_blocks(self):
        """Test parsing 'blocks' link type."""
        result = LinkType.from_string("blocks")
        assert result == LinkType.BLOCKS

    def test_from_string_is_blocked_by(self):
        """Test parsing 'is blocked by' link type."""
        result = LinkType.from_string("is blocked by")
        assert result == LinkType.IS_BLOCKED_BY

    def test_from_string_blocked_by_alias(self):
        """Test parsing 'blocked by' alias."""
        result = LinkType.from_string("blocked by")
        assert result == LinkType.IS_BLOCKED_BY

    def test_from_string_relates_to(self):
        """Test parsing 'relates to' link type."""
        result = LinkType.from_string("relates to")
        assert result == LinkType.RELATES_TO

    def test_from_string_depends_on(self):
        """Test parsing 'depends on' link type."""
        result = LinkType.from_string("depends on")
        assert result == LinkType.DEPENDS_ON

    def test_from_string_unknown_defaults_to_relates(self):
        """Test unknown link type defaults to relates to."""
        result = LinkType.from_string("unknown type")
        assert result == LinkType.RELATES_TO

    def test_jira_name_blocks(self):
        """Test Jira name for blocks."""
        assert LinkType.BLOCKS.jira_name == "Blocks"

    def test_jira_name_relates(self):
        """Test Jira name for relates."""
        assert LinkType.RELATES_TO.jira_name == "Relates"

    def test_is_outward_blocks(self):
        """Test blocks is outward."""
        assert LinkType.BLOCKS.is_outward is True

    def test_is_outward_is_blocked_by(self):
        """Test is blocked by is not outward."""
        assert LinkType.IS_BLOCKED_BY.is_outward is False


class TestIssueLink:
    """Tests for IssueLink dataclass."""

    def test_str(self):
        """Test string representation."""
        link = IssueLink(
            link_type=LinkType.BLOCKS,
            target_key="OTHER-123",
        )

        result = str(link)
        assert "blocks" in result
        assert "OTHER-123" in result

    def test_target_project(self):
        """Test target project extraction."""
        link = IssueLink(
            link_type=LinkType.BLOCKS,
            target_key="OTHER-123",
        )

        assert link.target_project == "OTHER"


class TestLinkChange:
    """Tests for LinkChange dataclass."""

    def test_create_change(self):
        """Test creating a link change."""
        change = LinkChange(
            source_key="PROJ-100",
            target_key="OTHER-200",
            link_type="blocks",
            action="create",
        )

        assert change.source_key == "PROJ-100"
        assert change.target_key == "OTHER-200"
        assert change.success is True


class TestLinkSyncResult:
    """Tests for LinkSyncResult dataclass."""

    def test_initial_state(self):
        """Test initial state."""
        result = LinkSyncResult()

        assert result.success is True
        assert result.links_created == 0
        assert result.links_failed == 0

    def test_add_successful_create(self):
        """Test adding successful create."""
        result = LinkSyncResult()

        change = LinkChange(
            source_key="PROJ-100",
            target_key="OTHER-200",
            link_type="blocks",
            action="create",
            success=True,
        )

        result.add_change(change)

        assert result.links_created == 1
        assert result.success is True

    def test_add_failed_create(self):
        """Test adding failed create."""
        result = LinkSyncResult()

        change = LinkChange(
            source_key="PROJ-100",
            target_key="OTHER-200",
            link_type="blocks",
            action="create",
            success=False,
            error="Permission denied",
        )

        result.add_change(change)

        assert result.links_failed == 1
        assert result.success is False

    def test_summary(self):
        """Test summary generation."""
        result = LinkSyncResult()
        result.stories_processed = 5
        result.links_created = 3
        result.links_unchanged = 2

        summary = result.summary()

        assert "Link Sync" in summary
        assert "5" in summary
        assert "3" in summary


class TestMarkdownParserLinks:
    """Tests for link parsing in MarkdownParser."""

    def test_extract_links_table(self):
        """Test extracting links from table."""
        content = """### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

#### Description
**As a** user
**I want** test
**So that** works

#### Links
| Link Type | Target |
|-----------|--------|
| blocks | OTHER-100 |
| relates to | PROJ-200 |
"""

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert len(stories[0].links) == 2

        link_types = [l[0] for l in stories[0].links]
        targets = [l[1] for l in stories[0].links]

        assert "blocks" in link_types
        assert "OTHER-100" in targets
        assert "PROJ-200" in targets

    def test_extract_links_inline(self):
        """Test extracting inline links."""
        content = """### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

**Blocks:** OTHER-100, OTHER-101

#### Description
**As a** user
**I want** test
**So that** works
"""

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert len(stories[0].links) == 2

        targets = [l[1] for l in stories[0].links]
        assert "OTHER-100" in targets
        assert "OTHER-101" in targets

    def test_extract_links_depends_on(self):
        """Test extracting depends on links."""
        content = """### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

**Depends on:** BACKEND-50

#### Description
**As a** user
**I want** test
**So that** works
"""

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert len(stories[0].links) == 1
        assert stories[0].links[0] == ("depends on", "BACKEND-50")

    def test_no_links(self):
        """Test story with no links."""
        content = """### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

#### Description
**As a** user
**I want** test
**So that** works
"""

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        assert len(stories[0].links) == 0


class TestLinkSyncOrchestrator:
    """Tests for LinkSyncOrchestrator class."""

    @pytest.fixture
    def mock_tracker(self):
        """Create mock tracker."""
        tracker = Mock()
        tracker.get_issue_links.return_value = []
        tracker.create_link.return_value = True
        tracker.delete_link.return_value = True
        return tracker

    def test_initialization(self, mock_tracker):
        """Test orchestrator initialization."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        assert orchestrator.tracker == mock_tracker
        assert orchestrator.dry_run is True

    def test_sync_story_links_no_external_key(self, mock_tracker):
        """Test syncing story without external key."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            links=[("blocks", "OTHER-100")],
        )

        result = orchestrator.sync_story_links(story)

        assert not result.success
        assert len(result.errors) > 0

    def test_sync_story_links_creates_links(self, mock_tracker):
        """Test syncing creates new links."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=False,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            external_key=IssueKey("PROJ-100"),
            links=[("blocks", "OTHER-100")],
        )

        result = orchestrator.sync_story_links(story)

        assert result.success
        assert result.links_created == 1
        mock_tracker.create_link.assert_called_once()

    def test_sync_story_links_dry_run(self, mock_tracker):
        """Test dry run doesn't create links."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            external_key=IssueKey("PROJ-100"),
            links=[("blocks", "OTHER-100")],
        )

        result = orchestrator.sync_story_links(story)

        # Dry run should succeed without calling create_link
        assert result.success
        assert result.links_created == 1  # Counted as would-be created

    def test_sync_story_links_existing_unchanged(self, mock_tracker):
        """Test existing links are counted as unchanged."""
        # Return an existing link
        mock_tracker.get_issue_links.return_value = [
            IssueLink(
                link_type=LinkType.BLOCKS,
                target_key="OTHER-100",
                source_key="PROJ-100",
            )
        ]

        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            external_key=IssueKey("PROJ-100"),
            links=[("blocks", "OTHER-100")],
        )

        result = orchestrator.sync_story_links(story)

        assert result.success
        assert result.links_unchanged == 1
        assert result.links_created == 0

    def test_sync_all_links(self, mock_tracker):
        """Test syncing multiple stories."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Story 1",
                external_key=IssueKey("PROJ-100"),
                links=[("blocks", "OTHER-100")],
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Story 2",
                external_key=IssueKey("PROJ-101"),
                links=[("depends on", "BACKEND-50")],
            ),
        ]

        result = orchestrator.sync_all_links(stories)

        assert result.success
        assert result.stories_processed == 2
        assert result.links_created == 2

    def test_analyze_links(self, mock_tracker):
        """Test link analysis."""
        orchestrator = LinkSyncOrchestrator(
            tracker=mock_tracker,
            dry_run=True,
        )

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Story 1",
                external_key=IssueKey("PROJ-100"),
                links=[
                    ("blocks", "OTHER-100"),  # Cross-project
                    ("relates to", "PROJ-200"),  # Same project
                ],
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Story 2",
                external_key=IssueKey("PROJ-101"),
                links=[("depends on", "BACKEND-50")],  # Cross-project
            ),
        ]

        analysis = orchestrator.analyze_links(stories)

        assert analysis["total_links"] == 3
        assert analysis["cross_project_links"] == 2
        assert analysis["same_project_links"] == 1
        assert "blocks" in analysis["link_types"]
        assert "OTHER" in analysis["target_projects"]


class TestCrossProjectLinkScenarios:
    """Integration-style tests for cross-project linking scenarios."""

    def test_link_to_multiple_projects(self):
        """Test linking to issues in multiple projects."""
        content = """### 📖 US-001: Frontend Feature

| Field | Value |
|-------|-------|
| **Story Points** | 5 |

**Depends on:** BACKEND-100, API-50
**Blocks:** MOBILE-200

#### Description
**As a** developer
**I want** API ready
**So that** I can build frontend
"""

        parser = MarkdownParser()
        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]

        # Should have 3 links total
        assert len(story.links) == 3

        # Extract targets
        targets = [l[1] for l in story.links]
        assert "BACKEND-100" in targets
        assert "API-50" in targets
        assert "MOBILE-200" in targets

    def test_bidirectional_links(self):
        """Test both directions of link."""
        content1 = """### 📖 US-001: Story A

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

**Blocks:** PROJ-200

#### Description
**As a** user
**I want** A
**So that** works
"""

        content2 = """### 📖 US-002: Story B

| Field | Value |
|-------|-------|
| **Story Points** | 3 |

**Blocked by:** PROJ-100

#### Description
**As a** user
**I want** B
**So that** works
"""

        parser = MarkdownParser()

        stories1 = parser.parse_stories(content1)
        stories2 = parser.parse_stories(content2)

        assert stories1[0].links[0] == ("blocks", "PROJ-200")
        assert stories2[0].links[0] == ("blocked by", "PROJ-100")
