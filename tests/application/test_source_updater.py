"""Tests for the SourceFileUpdater service."""

from datetime import datetime, timezone

import pytest

from spectryn.application.sync.source_updater import (
    EpicTrackerInfo,
    SourceFileUpdater,
    SourceUpdateResult,
    SyncStatus,
    TrackerInfo,
    compute_content_hash,
    compute_story_content_hash,
    detect_sync_conflicts,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.value_objects import IssueKey, StoryId
from spectryn.core.ports.config_provider import TrackerType


class TestSourceFileUpdater:
    """Tests for SourceFileUpdater class."""

    @pytest.fixture
    def jira_updater(self) -> SourceFileUpdater:
        """Create a Jira updater instance."""
        return SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

    @pytest.fixture
    def github_updater(self) -> SourceFileUpdater:
        """Create a GitHub updater instance."""
        return SourceFileUpdater(
            tracker_type=TrackerType.GITHUB,
            base_url="https://github.com/owner/repo",
        )

    @pytest.fixture
    def sample_story(self) -> UserStory:
        """Create a sample story with external key."""
        return UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            external_key=IssueKey("PROJ-123"),
            external_url="https://company.atlassian.net/browse/PROJ-123",
        )

    @pytest.fixture
    def story_without_key(self) -> UserStory:
        """Create a story without external key."""
        return UserStory(
            id=StoryId("US-002"),
            title="Unsynced Story",
        )


class TestTrackerBlockFormatting:
    """Tests for tracker block formatting."""

    def test_format_jira_tracker_block(self) -> None:
        """Test formatting Jira tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** Jira" in block
        assert "> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)" in block

    def test_format_github_tracker_block(self) -> None:
        """Test formatting GitHub tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.GITHUB,
            base_url="https://github.com/owner/repo",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.GITHUB,
            issue_key="#456",
            issue_url="https://github.com/owner/repo/issues/456",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** GitHub" in block
        assert "> **Issue:** [#456](https://github.com/owner/repo/issues/456)" in block

    def test_format_linear_tracker_block(self) -> None:
        """Test formatting Linear tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.LINEAR,
            base_url="https://linear.app/team",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.LINEAR,
            issue_key="TEAM-789",
            issue_url="https://linear.app/team/issue/TEAM-789",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** Linear" in block
        assert "> **Issue:** [TEAM-789](https://linear.app/team/issue/TEAM-789)" in block

    def test_format_azure_tracker_block(self) -> None:
        """Test formatting Azure DevOps tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.AZURE_DEVOPS,
            base_url="https://dev.azure.com/org/project",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.AZURE_DEVOPS,
            issue_key="123",
            issue_url="https://dev.azure.com/org/project/_workitems/edit/123",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** Azure DevOps" in block
        assert "> **Issue:** [123](https://dev.azure.com/org/project/_workitems/edit/123)" in block

    def test_format_asana_tracker_block(self) -> None:
        """Test formatting Asana tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.ASANA,
            base_url="https://app.asana.com",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.ASANA,
            issue_key="1234567890",
            issue_url="https://app.asana.com/0/0/1234567890",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** Asana" in block
        assert "> **Issue:** [1234567890](https://app.asana.com/0/0/1234567890)" in block


class TestUrlBuilding:
    """Tests for URL building."""

    def test_build_jira_url(self) -> None:
        """Test building Jira browse URL."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net/",  # trailing slash
        )
        url = updater._build_url("PROJ-123")
        assert url == "https://company.atlassian.net/browse/PROJ-123"

    def test_build_github_url(self) -> None:
        """Test building GitHub issue URL."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.GITHUB,
            base_url="https://github.com/owner/repo",
        )
        url = updater._build_url("#456")
        assert url == "https://github.com/owner/repo/issues/456"

    def test_build_github_url_without_hash(self) -> None:
        """Test building GitHub issue URL without hash prefix."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.GITHUB,
            base_url="https://github.com/owner/repo",
        )
        url = updater._build_url("789")
        assert url == "https://github.com/owner/repo/issues/789"

    def test_build_linear_url(self) -> None:
        """Test building Linear issue URL."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.LINEAR,
            base_url="https://linear.app/team",
        )
        url = updater._build_url("TEAM-123")
        assert url == "https://linear.app/team/issue/TEAM-123"

    def test_build_azure_url(self) -> None:
        """Test building Azure DevOps work item URL."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.AZURE_DEVOPS,
            base_url="https://dev.azure.com/org/project",
        )
        url = updater._build_url("456")
        assert url == "https://dev.azure.com/org/project/_workitems/edit/456"

    def test_build_asana_url(self) -> None:
        """Test building Asana task URL."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.ASANA,
            base_url="https://app.asana.com",
        )
        url = updater._build_url("1234567890")
        assert url == "https://app.asana.com/0/0/1234567890"


class TestStoryTrackerInfoUpdate:
    """Tests for updating story tracker info in content."""

    def test_insert_tracker_info_new(self) -> None:
        """Test inserting tracker info into story without existing tracker info."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# Epic

### 🔧 US-001: Test Story

| **Story Points** | 5 |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to test
**So that** it works
"""

        tracker_info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
        )

        result = updater._update_story_tracker_info(content, "US-001", tracker_info)

        assert "> **Tracker:** Jira" in result
        assert "> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)" in result
        # Tracker info should come after the header
        assert result.index("> **Tracker:**") > result.index("### 🔧 US-001:")

    def test_update_existing_tracker_info(self) -> None:
        """Test updating existing tracker info in a story."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# Epic

### 🔧 US-001: Test Story

> **Tracker:** Jira
> **Issue:** [PROJ-100](https://old.atlassian.net/browse/PROJ-100)

| **Story Points** | 5 |
"""

        tracker_info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
        )

        result = updater._update_story_tracker_info(content, "US-001", tracker_info)

        assert "> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)" in result
        # Old info should be gone
        assert "PROJ-100" not in result

    def test_update_legacy_jira_format(self) -> None:
        """Test updating legacy Jira shorthand format."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """### 🔧 US-001: Test Story

> **Jira:** [PROJ-100](https://old.atlassian.net/browse/PROJ-100)

| **Story Points** | 5 |
"""

        tracker_info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
        )

        result = updater._update_story_tracker_info(content, "US-001", tracker_info)

        assert "> **Tracker:** Jira" in result
        assert "> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)" in result

    def test_story_not_found(self) -> None:
        """Test that content is unchanged if story is not found."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """### 🔧 US-001: Test Story

| **Story Points** | 5 |
"""

        tracker_info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
        )

        result = updater._update_story_tracker_info(content, "US-999", tracker_info)

        # Content should be unchanged
        assert result == content


class TestFileUpdate:
    """Tests for file update operations."""

    def test_update_file_with_synced_stories(self, tmp_path) -> None:
        """Test updating a file with synced stories."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# Epic

### 🔧 US-001: First Story

| **Story Points** | 5 |

### 🔧 US-002: Second Story

| **Story Points** | 3 |
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(content, encoding="utf-8")

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="First Story",
                external_key=IssueKey("PROJ-100"),
                external_url="https://company.atlassian.net/browse/PROJ-100",
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Second Story",
                external_key=IssueKey("PROJ-101"),
                external_url="https://company.atlassian.net/browse/PROJ-101",
            ),
        ]

        result = updater.update_file(md_file, stories)

        assert result.success
        assert result.stories_updated == 2

        updated_content = md_file.read_text(encoding="utf-8")
        assert "PROJ-100" in updated_content
        assert "PROJ-101" in updated_content

    def test_update_file_skips_stories_without_key(self, tmp_path) -> None:
        """Test that stories without external_key are skipped."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """### 🔧 US-001: Synced Story

### 🔧 US-002: Unsynced Story
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(content, encoding="utf-8")

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Synced Story",
                external_key=IssueKey("PROJ-100"),
            ),
            UserStory(
                id=StoryId("US-002"),
                title="Unsynced Story",
                # No external_key
            ),
        ]

        result = updater.update_file(md_file, stories)

        assert result.success
        assert result.stories_updated == 1
        assert result.stories_skipped == 1

    def test_update_file_dry_run(self, tmp_path) -> None:
        """Test dry run doesn't modify file."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        original_content = """### 🔧 US-001: Test Story

| **Story Points** | 5 |
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(original_content, encoding="utf-8")

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Test Story",
                external_key=IssueKey("PROJ-100"),
            ),
        ]

        result = updater.update_file(md_file, stories, dry_run=True)

        assert result.success
        assert result.stories_updated == 1
        # File should not be modified
        assert md_file.read_text(encoding="utf-8") == original_content

    def test_update_file_not_found(self, tmp_path) -> None:
        """Test handling of non-existent file."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        md_file = tmp_path / "NONEXISTENT.md"

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Test Story",
                external_key=IssueKey("PROJ-100"),
            ),
        ]

        result = updater.update_file(md_file, stories)

        assert not result.success
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()


class TestSourceUpdateResult:
    """Tests for SourceUpdateResult dataclass."""

    def test_summary_success(self) -> None:
        """Test summary for successful update."""
        result = SourceUpdateResult(
            success=True,
            stories_updated=5,
            file_path="/path/to/EPIC.md",
        )
        assert "Updated 5 stories" in result.summary
        assert "EPIC.md" in result.summary

    def test_summary_failure(self) -> None:
        """Test summary for failed update."""
        result = SourceUpdateResult(
            success=False,
            file_path="/path/to/EPIC.md",
            errors=["Permission denied"],
        )
        assert "Failed" in result.summary
        assert "Permission denied" in result.summary

    def test_add_error(self) -> None:
        """Test adding an error marks result as failed."""
        result = SourceUpdateResult()
        assert result.success is True

        result.add_error("Something went wrong")

        assert result.success is False
        assert "Something went wrong" in result.errors


class TestEnhancedTrackerBlockFormatting:
    """Tests for enhanced tracker block formatting with timestamps and hashes."""

    def test_format_tracker_block_with_timestamp(self) -> None:
        """Test formatting tracker block with last synced timestamp."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
            last_synced=datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc),
            sync_status=SyncStatus.SYNCED,
        )
        block = updater._format_tracker_block(info)
        assert "> **Last Synced:** 2025-01-15 14:30 UTC" in block
        assert "> **Sync Status:** ✅ Synced" in block

    def test_format_tracker_block_with_content_hash(self) -> None:
        """Test formatting tracker block with content hash."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.JIRA,
            issue_key="PROJ-123",
            issue_url="https://company.atlassian.net/browse/PROJ-123",
            content_hash="a1b2c3d4",
        )
        block = updater._format_tracker_block(info)
        assert "> **Content Hash:** `a1b2c3d4`" in block

    def test_format_tracker_block_all_fields(self) -> None:
        """Test formatting tracker block with all metadata fields."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.GITHUB,
            base_url="https://github.com/owner/repo",
        )
        info = TrackerInfo(
            tracker_type=TrackerType.GITHUB,
            issue_key="#456",
            issue_url="https://github.com/owner/repo/issues/456",
            last_synced=datetime(2025, 6, 20, 10, 15, tzinfo=timezone.utc),
            sync_status=SyncStatus.MODIFIED,
            content_hash="deadbeef",
        )
        block = updater._format_tracker_block(info)
        assert "> **Tracker:** GitHub" in block
        assert "> **Issue:** [#456](https://github.com/owner/repo/issues/456)" in block
        assert "> **Last Synced:** 2025-06-20 10:15 UTC" in block
        assert "> **Sync Status:** 📝 Modified" in block
        assert "> **Content Hash:** `deadbeef`" in block


class TestEpicTrackerBlockFormatting:
    """Tests for epic-level tracker block formatting."""

    def test_format_epic_tracker_block(self) -> None:
        """Test formatting epic tracker info block."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )
        info = EpicTrackerInfo(
            tracker_type=TrackerType.JIRA,
            epic_key="PROJ-100",
            epic_url="https://company.atlassian.net/browse/PROJ-100",
            last_synced=datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc),
            total_stories=10,
            synced_stories=8,
        )
        block = updater._format_epic_tracker_block(info)
        assert "> **Epic Tracker:** Jira" in block
        assert (
            "> **Epic Issue:** [PROJ-100](https://company.atlassian.net/browse/PROJ-100)" in block
        )
        assert "> **Epic Synced:** 2025-01-15 14:30 UTC" in block
        assert "> **Stories Synced:** 8/10" in block


class TestEpicHeaderUpdate:
    """Tests for updating epic header with tracker info."""

    def test_insert_epic_header_info(self) -> None:
        """Test inserting epic tracker info into document header."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# My Project Epic

## Overview
This is the project overview.

### 🔧 US-001: First Story
"""

        stories = [
            UserStory(id=StoryId("US-001"), title="First Story", external_key=IssueKey("PROJ-101")),
        ]

        result = updater._update_epic_header(content, "PROJ-100", stories)

        assert "> **Epic Tracker:** Jira" in result
        assert (
            "> **Epic Issue:** [PROJ-100](https://company.atlassian.net/browse/PROJ-100)" in result
        )
        assert "> **Stories Synced:** 1/1" in result
        # Epic info should come after the h1 header
        assert result.index("> **Epic Tracker:**") > result.index("# My Project Epic")

    def test_update_existing_epic_header_info(self) -> None:
        """Test updating existing epic tracker info in header."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# My Project Epic

> **Epic Tracker:** Jira
> **Epic Issue:** [PROJ-OLD](https://old.atlassian.net/browse/PROJ-OLD)
> **Epic Synced:** 2024-01-01 00:00 UTC
> **Stories Synced:** 2/5

## Overview
"""

        stories = [
            UserStory(id=StoryId("US-001"), title="First Story", external_key=IssueKey("PROJ-101")),
            UserStory(
                id=StoryId("US-002"), title="Second Story", external_key=IssueKey("PROJ-102")
            ),
        ]

        result = updater._update_epic_header(content, "PROJ-100", stories)

        assert "[PROJ-100]" in result
        # Old info should be replaced
        assert "PROJ-OLD" not in result
        assert "2/2" in result


class TestContentHashing:
    """Tests for content hash computation."""

    def test_compute_content_hash(self) -> None:
        """Test basic content hash computation."""
        content = "This is some content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)

        assert len(hash1) == 8
        assert hash1 == hash2

    def test_compute_content_hash_normalizes_whitespace(self) -> None:
        """Test that whitespace is normalized for consistent hashing."""
        content1 = "This   is   content"
        content2 = "This is content"

        hash1 = compute_content_hash(content1)
        hash2 = compute_content_hash(content2)

        assert hash1 == hash2

    def test_compute_story_content_hash(self) -> None:
        """Test story content hash includes key fields."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            story_points=5,
        )

        hash1 = compute_story_content_hash(story)

        assert len(hash1) == 8

        # Changing title should change hash
        story.title = "Different Title"
        hash2 = compute_story_content_hash(story)

        assert hash1 != hash2


class TestConflictDetection:
    """Tests for conflict detection between local and synced content."""

    def test_detect_no_conflicts(self, tmp_path) -> None:
        """Test detection when no conflicts exist."""
        content = """### 🔧 US-001: Test Story

> **Content Hash:** `a1b2c3d4`

Some content.
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(content, encoding="utf-8")

        story = UserStory(id=StoryId("US-001"), title="Test Story")
        # Compute the actual hash for this story
        actual_hash = compute_story_content_hash(story)

        # Rewrite with correct hash
        content_with_hash = f"""### 🔧 US-001: Test Story

> **Content Hash:** `{actual_hash}`

Some content.
"""
        md_file.write_text(content_with_hash, encoding="utf-8")

        conflicts = detect_sync_conflicts(md_file, [story])

        assert len(conflicts) == 0

    def test_detect_conflict_when_content_changed(self, tmp_path) -> None:
        """Test detection when local content has changed since last sync."""
        # Write file with an old hash
        content = """### 🔧 US-001: Test Story

> **Content Hash:** `00000000`

Some content.
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(content, encoding="utf-8")

        # Story with different content than what was hashed
        story = UserStory(id=StoryId("US-001"), title="Modified Title")

        conflicts = detect_sync_conflicts(md_file, [story])

        assert len(conflicts) == 1
        assert conflicts[0][0] == "US-001"
        assert conflicts[0][1] == "00000000"  # stored hash
        # Current hash will be different


class TestSyncStatus:
    """Tests for SyncStatus constants and emojis."""

    def test_sync_status_values(self) -> None:
        """Test sync status constant values."""
        assert SyncStatus.SYNCED == "synced"
        assert SyncStatus.PENDING == "pending"
        assert SyncStatus.MODIFIED == "modified"
        assert SyncStatus.CONFLICT == "conflict"

    def test_sync_status_emojis(self) -> None:
        """Test sync status emoji mapping."""
        assert SyncStatus.emoji(SyncStatus.SYNCED) == "✅"
        assert SyncStatus.emoji(SyncStatus.PENDING) == "⏳"
        assert SyncStatus.emoji(SyncStatus.MODIFIED) == "📝"
        assert SyncStatus.emoji(SyncStatus.CONFLICT) == "⚠️"
        assert SyncStatus.emoji("unknown") == "❓"


class TestFileUpdateWithEpicKey:
    """Tests for file update with epic key."""

    def test_update_file_with_epic_key(self, tmp_path) -> None:
        """Test updating file includes epic header info."""
        updater = SourceFileUpdater(
            tracker_type=TrackerType.JIRA,
            base_url="https://company.atlassian.net",
        )

        content = """# Project Epic

## Overview

### 🔧 US-001: Test Story

| **Story Points** | 5 |
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(content, encoding="utf-8")

        stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Test Story",
                external_key=IssueKey("PROJ-101"),
            ),
        ]

        result = updater.update_file(md_file, stories, epic_key="PROJ-100")

        assert result.success
        assert result.epic_updated
        assert result.stories_updated == 1

        updated_content = md_file.read_text(encoding="utf-8")
        assert "PROJ-100" in updated_content
        assert "PROJ-101" in updated_content
        assert "> **Epic Tracker:**" in updated_content

    def test_summary_includes_all_counts(self) -> None:
        """Test summary includes all update counts."""
        result = SourceUpdateResult(
            success=True,
            stories_updated=5,
            subtasks_updated=12,
            epic_updated=True,
            file_path="/path/to/EPIC.md",
        )
        summary = result.summary
        assert "5 stories" in summary
        assert "12 subtasks" in summary
        assert "epic header" in summary
