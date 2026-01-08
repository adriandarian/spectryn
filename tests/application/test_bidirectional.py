"""Tests for bidirectional sync orchestrator."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.sync.bidirectional import (
    BidirectionalSyncOrchestrator,
    BidirectionalSyncResult,
)
from spectryn.application.sync.conflict import (
    Conflict,
    ConflictReport,
    ConflictType,
    FieldSnapshot,
    ResolutionStrategy,
    SnapshotStore,
    StorySnapshot,
    SyncSnapshot,
)
from spectryn.core.domain.entities import UserStory
from spectryn.core.domain.enums import Priority, Status
from spectryn.core.domain.value_objects import IssueKey, StoryId
from spectryn.core.ports.config_provider import SyncConfig
from spectryn.core.ports.issue_tracker import IssueData


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tracker():
    """Create a mock issue tracker."""
    tracker = MagicMock()
    tracker.name = "Jira"
    tracker.test_connection.return_value = True
    tracker.get_epic_children.return_value = []
    return tracker


@pytest.fixture
def sync_config():
    """Create a default sync config."""
    return SyncConfig(dry_run=True)


@pytest.fixture
def mock_snapshot_store(tmp_path):
    """Create a mock snapshot store."""
    return SnapshotStore(snapshot_dir=tmp_path / ".spectra" / "snapshots")


@pytest.fixture
def orchestrator(mock_tracker, sync_config, mock_snapshot_store):
    """Create a bidirectional sync orchestrator."""
    return BidirectionalSyncOrchestrator(
        tracker=mock_tracker,
        config=sync_config,
        snapshot_store=mock_snapshot_store,
    )


@pytest.fixture
def sample_markdown(tmp_path):
    """Create a sample markdown file."""
    content = """\
# 🚀 PROJ-123: Test Epic

---

### 🔧 US-001: First Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 🔄 In Progress |

#### Description

**As a** developer
**I want** to test bidirectional sync
**So that** I can verify it works

---

### 📋 US-002: Second Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟢 Medium |
| **Status** | 📋 Planned |

#### Description

**As a** user
**I want** another story
**So that** I have more test data

---
"""
    md_file = tmp_path / "EPIC.md"
    md_file.write_text(content, encoding="utf-8")
    return str(md_file)


@pytest.fixture
def sample_stories():
    """Create sample UserStory entities."""
    return [
        UserStory(
            id=StoryId("US-001"),
            title="First Story",
            status=Status.IN_PROGRESS,
            story_points=5,
            priority=Priority.HIGH,
            external_key=IssueKey("PROJ-101"),
        ),
        UserStory(
            id=StoryId("US-002"),
            title="Second Story",
            status=Status.PLANNED,
            story_points=3,
            priority=Priority.MEDIUM,
            external_key=IssueKey("PROJ-102"),
        ),
    ]


@pytest.fixture
def sample_issues():
    """Create sample IssueData from tracker."""
    return [
        IssueData(
            key="PROJ-101",
            summary="First Story",
            status="In Progress",
            story_points=5,
        ),
        IssueData(
            key="PROJ-102",
            summary="Second Story",
            status="Done",  # Changed from Planned!
            story_points=3,
        ),
    ]


# =============================================================================
# BidirectionalSyncResult Tests
# =============================================================================


class TestBidirectionalSyncResult:
    """Tests for BidirectionalSyncResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = BidirectionalSyncResult()

        assert result.success is True
        assert result.dry_run is True
        assert result.stories_pushed == 0
        assert result.stories_created == 0
        assert result.stories_updated == 0
        assert result.stories_pulled == 0
        assert result.conflicts_detected == 0
        assert result.conflicts_resolved == 0
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_sets_success_false(self):
        """Test that adding an error sets success to False."""
        result = BidirectionalSyncResult()
        assert result.success is True

        result.add_error("Something went wrong")

        assert result.success is False
        assert "Something went wrong" in result.errors

    def test_add_warning_keeps_success(self):
        """Test that adding a warning doesn't affect success."""
        result = BidirectionalSyncResult()
        result.add_warning("Minor issue")

        assert result.success is True
        assert "Minor issue" in result.warnings

    def test_has_conflicts_property(self):
        """Test has_conflicts property."""
        result = BidirectionalSyncResult()
        assert result.has_conflicts is False

        result.conflicts_detected = 3
        assert result.has_conflicts is True

    def test_summary_generation(self):
        """Test that summary is generated correctly."""
        result = BidirectionalSyncResult(
            stories_pushed=5,
            stories_created=2,
            stories_updated=3,
            stories_pulled=4,
            fields_updated_locally=8,
            conflicts_detected=1,
            conflicts_resolved=1,
        )

        summary = result.summary

        assert "Bidirectional Sync" in summary
        assert "Push" in summary
        assert "Pull" in summary
        assert "5" in summary  # stories_pushed
        assert "Conflicts" in summary


# =============================================================================
# BidirectionalSyncOrchestrator Tests
# =============================================================================


class TestBidirectionalSyncOrchestrator:
    """Tests for BidirectionalSyncOrchestrator."""

    def test_init(self, mock_tracker, sync_config, mock_snapshot_store):
        """Test orchestrator initialization."""
        orchestrator = BidirectionalSyncOrchestrator(
            tracker=mock_tracker,
            config=sync_config,
            snapshot_store=mock_snapshot_store,
        )

        assert orchestrator.tracker == mock_tracker
        assert orchestrator.config == sync_config
        assert orchestrator.snapshot_store == mock_snapshot_store

    def test_lazy_parser_creation(self, orchestrator):
        """Test that parser is created lazily."""
        assert orchestrator._parser is None

        parser = orchestrator.parser

        assert parser is not None
        # Should return same instance on second call
        assert orchestrator.parser is parser

    def test_lazy_writer_creation(self, orchestrator):
        """Test that writer is created lazily."""
        assert orchestrator._writer is None

        writer = orchestrator.writer

        assert writer is not None
        assert orchestrator.writer is writer

    def test_sync_with_no_markdown_file(self, orchestrator):
        """Test sync when markdown file doesn't exist."""
        result = orchestrator.sync(
            markdown_path="/nonexistent/file.md",
            epic_key="PROJ-123",
            resolution_strategy=ResolutionStrategy.SKIP,
        )

        assert result.success is False
        assert any("not found" in err.lower() for err in result.errors)

    def test_sync_with_empty_tracker(self, orchestrator, sample_markdown):
        """Test sync when tracker has no issues."""
        orchestrator.tracker.get_epic_children.return_value = []

        result = orchestrator.sync(
            markdown_path=sample_markdown,
            epic_key="PROJ-123",
            resolution_strategy=ResolutionStrategy.SKIP,
        )

        assert result.success is True
        # In dry_run mode (default), stories are not actually pushed
        # but they are parsed from markdown
        assert result.dry_run is True

    def test_preview_mode(self, orchestrator, sample_markdown):
        """Test preview mode doesn't modify anything."""
        orchestrator.tracker.get_epic_children.return_value = []

        result = orchestrator.preview(
            markdown_path=sample_markdown,
            epic_key="PROJ-123",
        )

        assert result.dry_run is True
        # Preview should not save snapshot
        assert orchestrator.snapshot_store.load("PROJ-123") is None

    def test_match_stories_by_external_key(self, orchestrator, sample_stories):
        """Test matching stories by external key."""
        orchestrator._local_stories = sample_stories
        orchestrator._remote_issues = [
            IssueData(key="PROJ-101", summary="First Story", status="Done"),
            IssueData(key="PROJ-102", summary="Second Story", status="Done"),
        ]

        orchestrator._match_stories()

        assert len(orchestrator._matches) == 2
        assert orchestrator._matches["US-001"] == "PROJ-101"
        assert orchestrator._matches["US-002"] == "PROJ-102"

    def test_match_stories_by_title(self, orchestrator):
        """Test matching stories by title when no external key."""
        orchestrator._local_stories = [
            UserStory(
                id=StoryId("US-001"),
                title="First Story",
                status=Status.PLANNED,
            ),
        ]
        orchestrator._remote_issues = [
            IssueData(key="PROJ-101", summary="First Story", status="Done"),
        ]

        orchestrator._match_stories()

        assert orchestrator._matches.get("US-001") == "PROJ-101"

    def test_titles_match_exact(self, orchestrator):
        """Test exact title matching."""
        assert orchestrator._titles_match("Some Title", "Some Title")
        assert orchestrator._titles_match("Some Title", "some title")

    def test_titles_match_partial(self, orchestrator):
        """Test partial title matching."""
        assert orchestrator._titles_match("Story", "PROJ-123: Story")
        assert orchestrator._titles_match("PROJ-123: Story", "Story")

    def test_detect_conflicts_no_baseline(self, orchestrator, sample_stories, sample_issues):
        """Test conflict detection with no baseline snapshot."""
        orchestrator._local_stories = sample_stories
        orchestrator._remote_issues = sample_issues
        orchestrator._base_snapshot = None
        orchestrator._matches = {"US-001": "PROJ-101", "US-002": "PROJ-102"}

        report = orchestrator._detect_conflicts("PROJ-123")

        # No conflicts without baseline
        assert report.conflict_count == 0

    def test_detect_conflicts_with_baseline(
        self, orchestrator, sample_stories, sample_issues, mock_snapshot_store
    ):
        """Test conflict detection with baseline snapshot."""
        # Create a baseline snapshot
        baseline = SyncSnapshot(
            snapshot_id="test-123",
            epic_key="PROJ-123",
            markdown_path="/test/EPIC.md",
            markdown_hash="abc123",
        )
        baseline.stories = [
            StorySnapshot(
                story_id="US-001",
                jira_key="PROJ-101",
                status=FieldSnapshot("in_progress"),
                story_points=FieldSnapshot(5),
            ),
            StorySnapshot(
                story_id="US-002",
                jira_key="PROJ-102",
                status=FieldSnapshot("planned"),  # Was planned in baseline
                story_points=FieldSnapshot(3),
            ),
        ]
        mock_snapshot_store.save(baseline)

        # Update local story
        sample_stories[1].status = Status.IN_PROGRESS  # Local changed to in_progress

        orchestrator._local_stories = sample_stories
        orchestrator._remote_issues = sample_issues  # Remote has Done
        orchestrator._base_snapshot = baseline
        orchestrator._matches = {"US-001": "PROJ-101", "US-002": "PROJ-102"}

        report = orchestrator._detect_conflicts("PROJ-123")

        # Should detect status conflict on US-002
        # Both changed from planned: local -> in_progress, remote -> done
        assert report.conflict_count >= 1

    def test_resolve_conflicts_force_local(self, orchestrator):
        """Test resolving conflicts with force-local strategy."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-101",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="in_progress",
            remote_value="done",
            base_value="planned",
        )
        report = ConflictReport(epic_key="PROJ-123")
        report.add_conflict(conflict)

        result = BidirectionalSyncResult()
        orchestrator._resolve_conflicts(
            report,
            ResolutionStrategy.FORCE_LOCAL,
            None,
            result,
        )

        assert result.conflicts_resolved == 1
        assert report.resolutions[0].resolution == "local"

    def test_resolve_conflicts_force_remote(self, orchestrator):
        """Test resolving conflicts with force-remote strategy."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-101",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="in_progress",
            remote_value="done",
            base_value="planned",
        )
        report = ConflictReport(epic_key="PROJ-123")
        report.add_conflict(conflict)

        result = BidirectionalSyncResult()
        orchestrator._resolve_conflicts(
            report,
            ResolutionStrategy.FORCE_REMOTE,
            None,
            result,
        )

        assert result.conflicts_resolved == 1
        assert report.resolutions[0].resolution == "remote"

    def test_resolve_conflicts_skip(self, orchestrator):
        """Test resolving conflicts with skip strategy."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-101",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="in_progress",
            remote_value="done",
            base_value="planned",
        )
        report = ConflictReport(epic_key="PROJ-123")
        report.add_conflict(conflict)

        result = BidirectionalSyncResult()
        orchestrator._resolve_conflicts(
            report,
            ResolutionStrategy.SKIP,
            None,
            result,
        )

        assert result.conflicts_resolved == 1
        assert report.resolutions[0].resolution == "skip"

    def test_progress_callback_called(self, orchestrator, sample_markdown):
        """Test that progress callback is invoked."""
        progress_calls = []

        def progress_callback(phase: str, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        orchestrator.sync(
            markdown_path=sample_markdown,
            epic_key="PROJ-123",
            resolution_strategy=ResolutionStrategy.SKIP,
            progress_callback=progress_callback,
        )

        assert len(progress_calls) > 0
        phases = [p[0] for p in progress_calls]
        assert "Loading baseline" in phases
        assert "Parsing markdown" in phases
        assert "Fetching from tracker" in phases


# =============================================================================
# Integration Tests
# =============================================================================


class TestBidirectionalSyncIntegration:
    """Integration tests for bidirectional sync."""

    def test_full_sync_cycle(self, mock_tracker, sync_config, tmp_path):
        """Test a complete sync cycle: push and pull."""
        # Create markdown file
        md_content = """\
# 🚀 PROJ-123: Test Epic

---

### 🔧 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |

#### Description

**As a** developer
**I want** a feature
**So that** it works

---
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(md_content, encoding="utf-8")

        # Mock tracker returning the story with updated status
        mock_tracker.get_epic_children.return_value = [
            IssueData(
                key="PROJ-101",
                summary="Test Story",
                status="Done",  # Changed remotely
                story_points=5,
            ),
        ]

        # Create orchestrator
        snapshot_store = SnapshotStore(snapshot_dir=tmp_path / ".spectra" / "snapshots")
        orchestrator = BidirectionalSyncOrchestrator(
            tracker=mock_tracker,
            config=sync_config,
            snapshot_store=snapshot_store,
        )

        # First sync (no baseline) - in dry run mode
        result = orchestrator.sync(
            markdown_path=str(md_file),
            epic_key="PROJ-123",
            resolution_strategy=ResolutionStrategy.SKIP,
        )

        assert result.success is True
        # In dry_run mode, stories are counted but not actually pushed
        assert result.dry_run is True

    def test_sync_saves_snapshot_when_not_dry_run(self, mock_tracker, tmp_path):
        """Test that snapshot is saved after successful sync (not dry run)."""
        md_content = """\
# 🚀 PROJ-123: Test Epic

---

### 🔧 US-001: Test Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Status** | 📋 Planned |

---
"""
        md_file = tmp_path / "EPIC.md"
        md_file.write_text(md_content, encoding="utf-8")

        mock_tracker.get_epic_children.return_value = []

        # Not dry run
        config = SyncConfig(dry_run=False)
        snapshot_store = SnapshotStore(snapshot_dir=tmp_path / ".spectra" / "snapshots")

        orchestrator = BidirectionalSyncOrchestrator(
            tracker=mock_tracker,
            config=config,
            snapshot_store=snapshot_store,
        )

        result = orchestrator.sync(
            markdown_path=str(md_file),
            epic_key="PROJ-123",
            resolution_strategy=ResolutionStrategy.SKIP,
        )

        assert result.success is True

        # Snapshot should be saved
        snapshot = snapshot_store.load("PROJ-123")
        assert snapshot is not None
        assert snapshot.epic_key == "PROJ-123"
