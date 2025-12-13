"""
Tests for conflict detection and resolution.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from md2jira.application.sync.conflict import (
    ConflictType,
    ResolutionStrategy,
    Conflict,
    ConflictReport,
    ConflictResolution,
    ConflictDetector,
    ConflictResolver,
    SyncSnapshot,
    StorySnapshot,
    FieldSnapshot,
    SnapshotStore,
    create_snapshot_from_sync,
)
from md2jira.core.domain.entities import UserStory, Subtask
from md2jira.core.domain.value_objects import StoryId, IssueKey, Description
from md2jira.core.domain.enums import Status, Priority
from md2jira.core.ports.issue_tracker import IssueData


class TestFieldSnapshot:
    """Tests for FieldSnapshot class."""
    
    def test_hash_computation(self):
        """Test that hash is computed correctly."""
        snap1 = FieldSnapshot("hello")
        snap2 = FieldSnapshot("hello")
        snap3 = FieldSnapshot("world")
        
        assert snap1.hash == snap2.hash
        assert snap1.hash != snap3.hash
    
    def test_matches(self):
        """Test matching snapshots."""
        snap1 = FieldSnapshot("value")
        snap2 = FieldSnapshot("value")
        snap3 = FieldSnapshot("other")
        
        assert snap1.matches(snap2)
        assert not snap1.matches(snap3)
    
    def test_none_value(self):
        """Test with None value."""
        snap = FieldSnapshot(None)
        assert snap.hash == "null"
    
    def test_to_dict(self):
        """Test serialization."""
        snap = FieldSnapshot("test")
        data = snap.to_dict()
        
        assert data["value"] == "test"
        assert "hash" in data
    
    def test_from_dict(self):
        """Test deserialization."""
        data = {"value": "test", "hash": "abc123"}
        snap = FieldSnapshot.from_dict(data)
        
        assert snap.value == "test"
        assert snap.hash == "abc123"


class TestStorySnapshot:
    """Tests for StorySnapshot class."""
    
    def test_from_story(self):
        """Test creating snapshot from UserStory."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            description=Description(
                role="user",
                want="to test",
                benefit="verification",
            ),
            story_points=5,
            status=Status.IN_PROGRESS,
            subtasks=[
                Subtask(name="Subtask 1", story_points=2, status=Status.DONE),
            ],
        )
        
        snapshot = StorySnapshot.from_story(story, "PROJ-123")
        
        assert snapshot.story_id == "US-001"
        assert snapshot.jira_key == "PROJ-123"
        assert snapshot.title.value == "Test Story"
        assert snapshot.story_points.value == 5
        assert snapshot.subtask_count == 1
    
    def test_to_dict_from_dict(self):
        """Test round-trip serialization."""
        snapshot = StorySnapshot(
            story_id="US-001",
            jira_key="PROJ-123",
            title=FieldSnapshot("Title"),
            description=FieldSnapshot("Desc"),
            status=FieldSnapshot(1),
            story_points=FieldSnapshot(5),
        )
        
        data = snapshot.to_dict()
        restored = StorySnapshot.from_dict(data)
        
        assert restored.story_id == "US-001"
        assert restored.jira_key == "PROJ-123"
        assert restored.title.value == "Title"


class TestSyncSnapshot:
    """Tests for SyncSnapshot class."""
    
    def test_get_story(self):
        """Test getting story by ID."""
        snapshot = SyncSnapshot(
            snapshot_id="snap-1",
            epic_key="PROJ-100",
            markdown_path="/test.md",
            markdown_hash="abc",
            stories=[
                StorySnapshot(story_id="US-001", jira_key="PROJ-101"),
                StorySnapshot(story_id="US-002", jira_key="PROJ-102"),
            ],
        )
        
        story = snapshot.get_story("US-001")
        assert story is not None
        assert story.jira_key == "PROJ-101"
        
        assert snapshot.get_story("US-999") is None
    
    def test_get_story_by_jira_key(self):
        """Test getting story by Jira key."""
        snapshot = SyncSnapshot(
            snapshot_id="snap-1",
            epic_key="PROJ-100",
            markdown_path="/test.md",
            markdown_hash="abc",
            stories=[
                StorySnapshot(story_id="US-001", jira_key="PROJ-101"),
            ],
        )
        
        story = snapshot.get_story_by_jira_key("PROJ-101")
        assert story is not None
        assert story.story_id == "US-001"
    
    def test_generate_id(self):
        """Test ID generation."""
        id1 = SyncSnapshot.generate_id("PROJ-100", "/path/file.md")
        id2 = SyncSnapshot.generate_id("PROJ-100", "/path/file.md")
        
        # IDs should be different (include timestamp)
        assert len(id1) == 16
        assert len(id2) == 16


class TestConflict:
    """Tests for Conflict class."""
    
    def test_str(self):
        """Test string representation."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        )
        
        result = str(conflict)
        assert "US-001" in result
        assert "status" in result
    
    def test_summary(self):
        """Test summary property."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        )
        
        assert "Both modified" in conflict.summary


class TestConflictReport:
    """Tests for ConflictReport class."""
    
    def test_has_conflicts(self):
        """Test has_conflicts property."""
        report = ConflictReport(epic_key="PROJ-100")
        assert not report.has_conflicts
        
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="a",
            remote_value="b",
            base_value="c",
        ))
        assert report.has_conflicts
    
    def test_stories_with_conflicts(self):
        """Test getting unique story IDs with conflicts."""
        report = ConflictReport(epic_key="PROJ-100")
        
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="a", remote_value="b", base_value="c",
        ))
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="story_points",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="5", remote_value="8", base_value="3",
        ))
        report.add_conflict(Conflict(
            story_id="US-002",
            jira_key="PROJ-124",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="a", remote_value="b", base_value="c",
        ))
        
        assert len(report.stories_with_conflicts) == 2
        assert "US-001" in report.stories_with_conflicts
        assert "US-002" in report.stories_with_conflicts
    
    def test_summary(self):
        """Test summary generation."""
        report = ConflictReport(epic_key="PROJ-100")
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="a", remote_value="b", base_value="c",
        ))
        
        summary = report.summary()
        assert "PROJ-100" in summary
        assert "Total conflicts: 1" in summary


class TestConflictDetector:
    """Tests for ConflictDetector class."""
    
    def test_no_base_snapshot_no_conflicts(self):
        """Test that without base snapshot, no conflicts are detected."""
        detector = ConflictDetector(base_snapshot=None)
        
        local_stories = [
            UserStory(id=StoryId("US-001"), title="Story", status=Status.DONE),
        ]
        remote_issues = [
            IssueData(key="PROJ-123", summary="Story", status="Open"),
        ]
        
        report = detector.detect_conflicts(
            local_stories=local_stories,
            remote_issues=remote_issues,
            matches={"US-001": "PROJ-123"},
        )
        
        assert not report.has_conflicts
    
    def test_detect_status_conflict(self):
        """Test detecting status conflict."""
        # Create base snapshot
        base = SyncSnapshot(
            snapshot_id="snap-1",
            epic_key="PROJ-100",
            markdown_path="/test.md",
            markdown_hash="abc",
            stories=[
                StorySnapshot(
                    story_id="US-001",
                    jira_key="PROJ-123",
                    status=FieldSnapshot(Status.OPEN.value),
                    story_points=FieldSnapshot(5),
                ),
            ],
        )
        
        detector = ConflictDetector(base_snapshot=base)
        
        # Local changed to DONE, remote changed to IN_PROGRESS
        local_stories = [
            UserStory(id=StoryId("US-001"), title="Story", status=Status.DONE),
        ]
        remote_issues = [
            IssueData(key="PROJ-123", summary="Story", status="In Progress"),
        ]
        
        report = detector.detect_conflicts(
            local_stories=local_stories,
            remote_issues=remote_issues,
            matches={"US-001": "PROJ-123"},
        )
        
        assert report.has_conflicts
        assert report.conflict_count == 1
        assert report.conflicts[0].field == "status"
        assert report.conflicts[0].conflict_type == ConflictType.BOTH_MODIFIED
    
    def test_detect_story_points_conflict(self):
        """Test detecting story points conflict."""
        base = SyncSnapshot(
            snapshot_id="snap-1",
            epic_key="PROJ-100",
            markdown_path="/test.md",
            markdown_hash="abc",
            stories=[
                StorySnapshot(
                    story_id="US-001",
                    jira_key="PROJ-123",
                    status=FieldSnapshot(Status.OPEN.value),
                    story_points=FieldSnapshot(5),
                ),
            ],
        )
        
        detector = ConflictDetector(base_snapshot=base)
        
        # Local: 8, Remote: 13 (both changed from base 5)
        local_stories = [
            UserStory(
                id=StoryId("US-001"),
                title="Story",
                status=Status.OPEN,
                story_points=8,
            ),
        ]
        remote_issues = [
            IssueData(
                key="PROJ-123",
                summary="Story",
                status="Open",
                story_points=13.0,
            ),
        ]
        
        report = detector.detect_conflicts(
            local_stories=local_stories,
            remote_issues=remote_issues,
            matches={"US-001": "PROJ-123"},
        )
        
        assert report.has_conflicts
        sp_conflict = next((c for c in report.conflicts if c.field == "story_points"), None)
        assert sp_conflict is not None
        assert sp_conflict.local_value == 8
        assert sp_conflict.remote_value == 13


class TestConflictResolver:
    """Tests for ConflictResolver class."""
    
    def test_force_local_strategy(self):
        """Test force-local resolution strategy."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.FORCE_LOCAL)
        
        report = ConflictReport(epic_key="PROJ-100")
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        ))
        
        resolved = resolver.resolve(report)
        
        assert resolved.resolved_count == 1
        assert resolved.resolutions[0].resolution == "local"
        assert resolved.resolutions[0].final_value == "Done"
    
    def test_force_remote_strategy(self):
        """Test force-remote resolution strategy."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.FORCE_REMOTE)
        
        report = ConflictReport(epic_key="PROJ-100")
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        ))
        
        resolved = resolver.resolve(report)
        
        assert resolved.resolved_count == 1
        assert resolved.resolutions[0].resolution == "remote"
        assert resolved.resolutions[0].final_value == "In Progress"
    
    def test_skip_strategy(self):
        """Test skip resolution strategy."""
        resolver = ConflictResolver(strategy=ResolutionStrategy.SKIP)
        
        report = ConflictReport(epic_key="PROJ-100")
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        ))
        
        resolved = resolver.resolve(report)
        
        assert resolved.resolved_count == 1
        assert resolved.resolutions[0].resolution == "skip"
    
    def test_ask_strategy_with_prompt(self):
        """Test ask strategy with prompt function."""
        def prompt(conflict):
            return "remote"
        
        resolver = ConflictResolver(
            strategy=ResolutionStrategy.ASK,
            prompt_func=prompt,
        )
        
        report = ConflictReport(epic_key="PROJ-100")
        report.add_conflict(Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="Done",
            remote_value="In Progress",
            base_value="Open",
        ))
        
        resolved = resolver.resolve(report)
        
        assert resolved.resolutions[0].resolution == "remote"


class TestSnapshotStore:
    """Tests for SnapshotStore class."""
    
    def test_save_and_load(self):
        """Test saving and loading snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SnapshotStore(snapshot_dir=Path(tmpdir))
            
            snapshot = SyncSnapshot(
                snapshot_id="snap-1",
                epic_key="PROJ-100",
                markdown_path="/test.md",
                markdown_hash="abc123",
                stories=[
                    StorySnapshot(story_id="US-001", jira_key="PROJ-101"),
                ],
            )
            
            store.save(snapshot)
            loaded = store.load("PROJ-100")
            
            assert loaded is not None
            assert loaded.snapshot_id == "snap-1"
            assert loaded.epic_key == "PROJ-100"
            assert len(loaded.stories) == 1
    
    def test_delete(self):
        """Test deleting snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SnapshotStore(snapshot_dir=Path(tmpdir))
            
            snapshot = SyncSnapshot(
                snapshot_id="snap-1",
                epic_key="PROJ-100",
                markdown_path="/test.md",
                markdown_hash="abc",
            )
            
            store.save(snapshot)
            assert store.load("PROJ-100") is not None
            
            store.delete("PROJ-100")
            assert store.load("PROJ-100") is None
    
    def test_list_snapshots(self):
        """Test listing all snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SnapshotStore(snapshot_dir=Path(tmpdir))
            
            store.save(SyncSnapshot(
                snapshot_id="snap-1",
                epic_key="PROJ-100",
                markdown_path="/a.md",
                markdown_hash="abc",
                stories=[StorySnapshot(story_id="US-001", jira_key="PROJ-101")],
            ))
            store.save(SyncSnapshot(
                snapshot_id="snap-2",
                epic_key="PROJ-200",
                markdown_path="/b.md",
                markdown_hash="def",
            ))
            
            snapshots = store.list_snapshots()
            
            assert len(snapshots) == 2
            epic_keys = [s["epic_key"] for s in snapshots]
            assert "PROJ-100" in epic_keys
            assert "PROJ-200" in epic_keys


class TestCreateSnapshotFromSync:
    """Tests for create_snapshot_from_sync function."""
    
    def test_create_snapshot(self):
        """Test creating snapshot from sync data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "epic.md"
            md_path.write_text("# Epic\n\nContent here")
            
            stories = [
                UserStory(
                    id=StoryId("US-001"),
                    title="Story 1",
                    status=Status.DONE,
                    story_points=5,
                ),
                UserStory(
                    id=StoryId("US-002"),
                    title="Story 2",
                    status=Status.OPEN,
                    story_points=3,
                ),
            ]
            
            matches = {"US-001": "PROJ-101", "US-002": "PROJ-102"}
            
            snapshot = create_snapshot_from_sync(
                epic_key="PROJ-100",
                markdown_path=str(md_path),
                stories=stories,
                matches=matches,
            )
            
            assert snapshot.epic_key == "PROJ-100"
            assert len(snapshot.stories) == 2
            assert snapshot.markdown_hash != ""
            
            story1 = snapshot.get_story("US-001")
            assert story1 is not None
            assert story1.jira_key == "PROJ-101"


class TestConflictResolution:
    """Tests for ConflictResolution class."""
    
    def test_final_value_local(self):
        """Test final_value with local resolution."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local_val",
            remote_value="remote_val",
            base_value="base_val",
        )
        
        resolution = ConflictResolution(conflict=conflict, resolution="local")
        assert resolution.final_value == "local_val"
    
    def test_final_value_remote(self):
        """Test final_value with remote resolution."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="status",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local_val",
            remote_value="remote_val",
            base_value="base_val",
        )
        
        resolution = ConflictResolution(conflict=conflict, resolution="remote")
        assert resolution.final_value == "remote_val"
    
    def test_final_value_merge(self):
        """Test final_value with merge resolution."""
        conflict = Conflict(
            story_id="US-001",
            jira_key="PROJ-123",
            field="description",
            conflict_type=ConflictType.BOTH_MODIFIED,
            local_value="local desc",
            remote_value="remote desc",
            base_value="base desc",
        )
        
        resolution = ConflictResolution(
            conflict=conflict,
            resolution="merge",
            merged_value="merged description",
        )
        assert resolution.final_value == "merged description"

