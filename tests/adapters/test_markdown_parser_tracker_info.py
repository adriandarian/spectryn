"""Tests for MarkdownParser tracker info extraction."""

import textwrap
from datetime import datetime

import pytest

from spectryn.adapters.parsers.markdown import MarkdownParser


class TestExtractTrackerInfo:
    """Tests for _extract_tracker_info method."""

    @pytest.fixture
    def parser(self) -> MarkdownParser:
        """Create a parser instance."""
        return MarkdownParser()

    def test_extract_explicit_tracker_and_issue(self, parser: MarkdownParser) -> None:
        """Test extracting explicit Tracker and Issue fields."""
        content = textwrap.dedent("""
            > **Tracker:** Jira
            > **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)

            | **Story Points** | 5 |
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "PROJ-123"
        assert issue_url == "https://company.atlassian.net/browse/PROJ-123"

    def test_extract_jira_shorthand(self, parser: MarkdownParser) -> None:
        """Test extracting Jira shorthand format."""
        content = textwrap.dedent("""
            > **Jira:** [PROJ-456](https://company.atlassian.net/browse/PROJ-456)

            | **Story Points** | 5 |
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "PROJ-456"
        assert issue_url == "https://company.atlassian.net/browse/PROJ-456"

    def test_extract_github_shorthand(self, parser: MarkdownParser) -> None:
        """Test extracting GitHub shorthand format."""
        content = textwrap.dedent("""
            > **GitHub:** [#789](https://github.com/owner/repo/issues/789)

            | **Story Points** | 3 |
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "#789"
        assert issue_url == "https://github.com/owner/repo/issues/789"

    def test_extract_linear_shorthand(self, parser: MarkdownParser) -> None:
        """Test extracting Linear shorthand format."""
        content = textwrap.dedent("""
            > **Linear:** [TEAM-123](https://linear.app/team/issue/TEAM-123)
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "TEAM-123"
        assert issue_url == "https://linear.app/team/issue/TEAM-123"

    def test_extract_azure_shorthand(self, parser: MarkdownParser) -> None:
        """Test extracting Azure DevOps shorthand format."""
        content = textwrap.dedent("""
            > **Azure DevOps:** [456](https://dev.azure.com/org/project/_workitems/edit/456)
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "456"
        assert issue_url == "https://dev.azure.com/org/project/_workitems/edit/456"

    def test_extract_issue_key_only(self, parser: MarkdownParser) -> None:
        """Test extracting issue key without URL."""
        content = textwrap.dedent("""
            > **Issue:** PROJ-999
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "PROJ-999"
        assert issue_url is None

    def test_extract_issue_key_github_number(self, parser: MarkdownParser) -> None:
        """Test extracting GitHub issue number without URL."""
        content = textwrap.dedent("""
            > **Issue:** #123
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "#123"
        assert issue_url is None

    def test_no_tracker_info(self, parser: MarkdownParser) -> None:
        """Test content without tracker info."""
        content = textwrap.dedent("""
            | **Story Points** | 5 |
            | **Priority** | 🔴 Critical |

            #### Description
            **As a** user
            **I want** to test
            **So that** it works
        """)

        issue_key, issue_url, last_synced, sync_status, content_hash = parser._extract_tracker_info(
            content
        )

        assert issue_key is None
        assert issue_url is None
        assert last_synced is None
        assert sync_status is None
        assert content_hash is None

    def test_case_insensitive_fields(self, parser: MarkdownParser) -> None:
        """Test that field matching is case-insensitive."""
        content = textwrap.dedent("""
            > **ISSUE:** [PROJ-123](https://example.com)
        """)

        issue_key, issue_url, _, _, _ = parser._extract_tracker_info(content)

        assert issue_key == "PROJ-123"
        assert issue_url == "https://example.com"


class TestExtractSyncMetadata:
    """Tests for extracting sync metadata (timestamp, status, hash)."""

    @pytest.fixture
    def parser(self) -> MarkdownParser:
        """Create a parser instance."""
        return MarkdownParser()

    def test_extract_last_synced_timestamp(self, parser: MarkdownParser) -> None:
        """Test extracting last synced timestamp."""
        content = textwrap.dedent("""
            > **Tracker:** Jira
            > **Issue:** [PROJ-123](https://example.com)
            > **Last Synced:** 2025-01-15 14:30 UTC
        """)

        _, _, last_synced, _, _ = parser._extract_tracker_info(content)

        assert last_synced is not None
        assert isinstance(last_synced, datetime)
        assert last_synced.year == 2025
        assert last_synced.month == 1
        assert last_synced.day == 15
        assert last_synced.hour == 14
        assert last_synced.minute == 30

    def test_extract_last_synced_without_utc(self, parser: MarkdownParser) -> None:
        """Test extracting timestamp without UTC suffix."""
        content = textwrap.dedent("""
            > **Last Synced:** 2025-06-20 10:15
        """)

        _, _, last_synced, _, _ = parser._extract_tracker_info(content)

        assert last_synced is not None
        assert last_synced.hour == 10
        assert last_synced.minute == 15

    def test_extract_sync_status_synced(self, parser: MarkdownParser) -> None:
        """Test extracting synced status."""
        content = textwrap.dedent("""
            > **Sync Status:** ✅ Synced
        """)

        _, _, _, sync_status, _ = parser._extract_tracker_info(content)

        assert sync_status == "synced"

    def test_extract_sync_status_pending(self, parser: MarkdownParser) -> None:
        """Test extracting pending status."""
        content = textwrap.dedent("""
            > **Sync Status:** ⏳ Pending
        """)

        _, _, _, sync_status, _ = parser._extract_tracker_info(content)

        assert sync_status == "pending"

    def test_extract_sync_status_modified(self, parser: MarkdownParser) -> None:
        """Test extracting modified status."""
        content = textwrap.dedent("""
            > **Sync Status:** 📝 Modified
        """)

        _, _, _, sync_status, _ = parser._extract_tracker_info(content)

        assert sync_status == "modified"

    def test_extract_sync_status_conflict(self, parser: MarkdownParser) -> None:
        """Test extracting conflict status."""
        content = textwrap.dedent("""
            > **Sync Status:** ⚠️ Conflict
        """)

        _, _, _, sync_status, _ = parser._extract_tracker_info(content)

        assert sync_status == "conflict"

    def test_extract_sync_status_without_emoji(self, parser: MarkdownParser) -> None:
        """Test extracting status without emoji prefix."""
        content = textwrap.dedent("""
            > **Sync Status:** synced
        """)

        _, _, _, sync_status, _ = parser._extract_tracker_info(content)

        assert sync_status == "synced"

    def test_extract_content_hash(self, parser: MarkdownParser) -> None:
        """Test extracting content hash."""
        content = textwrap.dedent("""
            > **Content Hash:** `a1b2c3d4`
        """)

        _, _, _, _, content_hash = parser._extract_tracker_info(content)

        assert content_hash == "a1b2c3d4"

    def test_extract_full_tracker_block(self, parser: MarkdownParser) -> None:
        """Test extracting all fields from a complete tracker block."""
        content = textwrap.dedent("""
            > **Tracker:** Jira
            > **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)
            > **Last Synced:** 2025-12-19 10:00 UTC
            > **Sync Status:** ✅ Synced
            > **Content Hash:** `deadbeef`

            | **Story Points** | 5 |
        """)

        issue_key, issue_url, last_synced, sync_status, content_hash = parser._extract_tracker_info(
            content
        )

        assert issue_key == "PROJ-123"
        assert issue_url == "https://company.atlassian.net/browse/PROJ-123"
        assert last_synced is not None
        assert last_synced.year == 2025
        assert sync_status == "synced"
        assert content_hash == "deadbeef"


class TestParseStoryWithTrackerInfo:
    """Tests for parsing full stories with tracker info."""

    @pytest.fixture
    def parser(self) -> MarkdownParser:
        """Create a parser instance."""
        return MarkdownParser()

    def test_parse_story_with_tracker_info(self, parser: MarkdownParser) -> None:
        """Test parsing a complete story with tracker info."""
        content = textwrap.dedent("""
            # Epic Title

            ### 🔧 US-001: Test Story

            > **Tracker:** Jira
            > **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)

            | **Story Points** | 5 |
            | **Priority** | 🔴 Critical |
            | **Status** | 📋 Planned |

            #### Description
            **As a** developer
            **I want** to test parsing
            **So that** tracker info is preserved
        """)

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-001"
        assert story.title == "Test Story"
        assert story.external_key is not None
        assert str(story.external_key) == "PROJ-123"
        assert story.external_url == "https://company.atlassian.net/browse/PROJ-123"

    def test_parse_story_with_full_sync_metadata(self, parser: MarkdownParser) -> None:
        """Test parsing a story with all sync metadata fields."""
        content = textwrap.dedent("""
            ### 🔧 US-001: Synced Story

            > **Tracker:** Jira
            > **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)
            > **Last Synced:** 2025-01-15 14:30 UTC
            > **Sync Status:** ✅ Synced
            > **Content Hash:** `abc12345`

            | **Story Points** | 5 |
        """)

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert story.external_key is not None
        assert story.external_url is not None
        assert story.last_synced is not None
        assert story.last_synced.year == 2025
        assert story.sync_status == "synced"
        assert story.content_hash == "abc12345"

    def test_parse_story_without_tracker_info(self, parser: MarkdownParser) -> None:
        """Test parsing a story without tracker info."""
        content = textwrap.dedent("""
            ### 🔧 US-002: New Story

            | **Story Points** | 3 |
            | **Status** | 📋 Planned |

            #### Description
            **As a** user
            **I want** a feature
            **So that** I benefit
        """)

        stories = parser.parse_stories(content)

        assert len(stories) == 1
        story = stories[0]
        assert str(story.id) == "US-002"
        assert story.external_key is None
        assert story.external_url is None
        assert story.last_synced is None
        assert story.sync_status is None
        assert story.content_hash is None

    def test_parse_multiple_stories_mixed_tracker_info(self, parser: MarkdownParser) -> None:
        """Test parsing multiple stories, some with tracker info."""
        content = textwrap.dedent("""
            # Epic

            ### 🔧 US-001: Synced Story

            > **Jira:** [PROJ-100](https://company.atlassian.net/browse/PROJ-100)

            | **Story Points** | 5 |

            ### 🔧 US-002: Unsynced Story

            | **Story Points** | 3 |

            ### 🔧 US-003: Also Synced

            > **Linear:** [TEAM-456](https://linear.app/team/issue/TEAM-456)

            | **Story Points** | 8 |
        """)

        stories = parser.parse_stories(content)

        assert len(stories) == 3

        # US-001 has Jira info
        assert str(stories[0].external_key) == "PROJ-100"
        assert "atlassian.net" in stories[0].external_url

        # US-002 has no tracker info
        assert stories[1].external_key is None
        assert stories[1].external_url is None

        # US-003 has Linear info
        assert str(stories[2].external_key) == "TEAM-456"
        assert "linear.app" in stories[2].external_url
