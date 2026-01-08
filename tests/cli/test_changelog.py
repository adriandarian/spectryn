"""Tests for changelog generation functionality."""

import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from spectryn.cli.changelog import (
    ChangeEntry,
    ChangelogFormat,
    ChangelogGenerator,
    ChangelogOptions,
    ChangeType,
    generate_changelog,
)
from spectryn.core.ports.sync_history import SyncHistoryEntry, SyncOutcome


class MockSyncHistoryStore:
    """Mock implementation of SyncHistoryPort for testing."""

    def __init__(self, entries: list[SyncHistoryEntry] | None = None):
        self.entries = entries or []

    def list_entries(
        self,
        limit: int | None = None,
        offset: int = 0,
        epic_key: str | None = None,
        tracker_type: str | None = None,
        outcome: SyncOutcome | None = None,
    ) -> list[SyncHistoryEntry]:
        return self.entries

    def add_entry(self, entry: SyncHistoryEntry) -> None:
        self.entries.append(entry)


@pytest.fixture
def sample_entries() -> list[SyncHistoryEntry]:
    """Create sample sync history entries for testing."""
    now = datetime.now()
    return [
        SyncHistoryEntry(
            entry_id="entry-001",
            session_id="session-001",
            markdown_path="stories/auth.md",
            epic_key="PROJ-100",
            tracker_type="jira",
            outcome=SyncOutcome.SUCCESS,
            started_at=now - timedelta(days=2, hours=1),
            completed_at=now - timedelta(days=2),
            duration_seconds=120.5,
            operations_total=5,
            operations_succeeded=5,
            operations_failed=0,
            user="alice",
            metadata={"sprint": "Sprint 1"},
        ),
        SyncHistoryEntry(
            entry_id="entry-002",
            session_id="session-002",
            markdown_path="stories/auth.md",
            epic_key="PROJ-100",
            tracker_type="jira",
            outcome=SyncOutcome.SUCCESS,
            started_at=now - timedelta(days=1, hours=1),
            completed_at=now - timedelta(days=1),
            duration_seconds=90.0,
            operations_total=3,
            operations_succeeded=3,
            operations_failed=0,
            user="bob",
            metadata={},
        ),
        SyncHistoryEntry(
            entry_id="entry-003",
            session_id="session-003",
            markdown_path="stories/payments.md",
            epic_key="PROJ-200",
            tracker_type="jira",
            outcome=SyncOutcome.SUCCESS,
            started_at=now - timedelta(hours=7),
            completed_at=now - timedelta(hours=6),
            duration_seconds=60.0,
            operations_total=2,
            operations_succeeded=2,
            operations_failed=0,
            user="alice",
            metadata={},
        ),
        SyncHistoryEntry(
            entry_id="entry-004",
            session_id="session-004",
            markdown_path="stories/fixes.md",
            epic_key="PROJ-300",
            tracker_type="jira",
            outcome=SyncOutcome.PARTIAL,
            started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2),
            duration_seconds=45.0,
            operations_total=4,
            operations_succeeded=3,
            operations_failed=1,
            user="charlie",
            metadata={},
        ),
        SyncHistoryEntry(
            entry_id="entry-005",
            session_id="session-005",
            markdown_path="stories/cleanup.md",
            epic_key="PROJ-400",
            tracker_type="jira",
            outcome=SyncOutcome.FAILED,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=1),
            duration_seconds=30.0,
            operations_total=1,
            operations_succeeded=0,
            operations_failed=1,
            user="bob",
            error_message="Connection timeout",
            metadata={},
        ),
    ]


class TestChangelogGenerator:
    """Tests for ChangelogGenerator class."""

    def test_generate_empty_history(self) -> None:
        """Test changelog generation with empty history."""
        store = MockSyncHistoryStore([])
        generator = ChangelogGenerator(store)
        result = generator.generate()

        assert "Changelog" in result

    def test_generate_markdown_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test markdown format output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(format=ChangelogFormat.MARKDOWN)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        assert "# Changelog" in result
        assert "## " in result  # Date headers
        assert "PROJ-" in result

    def test_generate_json_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test JSON format output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(format=ChangelogFormat.JSON)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        import json

        data = json.loads(result)
        assert "changelog" in data
        assert "generated_at" in data

    def test_generate_html_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test HTML format output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(format=ChangelogFormat.HTML)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "Changelog" in result
        assert "PROJ-" in result

    def test_generate_plain_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test plain text format output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(format=ChangelogFormat.PLAIN)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        assert "CHANGELOG" in result
        assert "=====" in result
        assert "PROJ-" in result

    def test_generate_keepachangelog_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test Keep a Changelog format output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(format=ChangelogFormat.KEEP_A_CHANGELOG)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        assert "Keep a Changelog" in result
        assert "Semantic Versioning" in result

    def test_filter_by_days(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test filtering records by number of days."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(days=1)  # Only last 24 hours
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        # Should only include recent entries
        assert "PROJ-" in result

    def test_max_entries_limit(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test limiting number of entries."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(max_entries=2)
        generator = ChangelogGenerator(store, options)
        raw_entries = generator._fetch_entries()
        entries = generator._filter_entries(generator._entries_to_changes(raw_entries))

        assert len(entries) <= 2

    def test_exclude_author(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test excluding author from output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(include_author=False)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        # Should not contain @author references
        assert "@alice" not in result
        assert "@bob" not in result

    def test_include_author(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test including author in output."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(include_author=True)
        generator = ChangelogGenerator(store, options)

        result = generator.generate()

        # Should contain @author references
        assert "@alice" in result or "@bob" in result or "@charlie" in result

    def test_output_to_file(self, sample_entries: list[SyncHistoryEntry], tmp_path: Path) -> None:
        """Test writing output to file."""
        store = MockSyncHistoryStore(sample_entries)
        output_file = tmp_path / "CHANGELOG.md"
        options = ChangelogOptions(output_file=output_file)
        generator = ChangelogGenerator(store, options)

        generator.generate()

        assert output_file.exists()
        content = output_file.read_text()
        assert "Changelog" in content


class TestChangeType:
    """Tests for change type determination."""

    def test_determine_change_type_success(self) -> None:
        """Test change type for successful sync."""
        store = MockSyncHistoryStore([])
        generator = ChangelogGenerator(store)

        entry = SyncHistoryEntry(
            entry_id="test",
            session_id="test",
            markdown_path="test.md",
            epic_key="TEST-1",
            tracker_type="jira",
            outcome=SyncOutcome.SUCCESS,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            duration_seconds=10.0,
            operations_succeeded=1,
        )

        result = generator._determine_change_type_from_outcome(entry)
        assert result == ChangeType.SYNCED

    def test_determine_change_type_failed(self) -> None:
        """Test change type for failed sync."""
        store = MockSyncHistoryStore([])
        generator = ChangelogGenerator(store)

        entry = SyncHistoryEntry(
            entry_id="test",
            session_id="test",
            markdown_path="test.md",
            epic_key="TEST-1",
            tracker_type="jira",
            outcome=SyncOutcome.FAILED,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            duration_seconds=10.0,
        )

        result = generator._determine_change_type_from_outcome(entry)
        assert result == ChangeType.CHANGED

    def test_determine_change_type_partial(self) -> None:
        """Test change type for partial sync."""
        store = MockSyncHistoryStore([])
        generator = ChangelogGenerator(store)

        entry = SyncHistoryEntry(
            entry_id="test",
            session_id="test",
            markdown_path="test.md",
            epic_key="TEST-1",
            tracker_type="jira",
            outcome=SyncOutcome.PARTIAL,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            duration_seconds=10.0,
        )

        result = generator._determine_change_type_from_outcome(entry)
        assert result == ChangeType.CHANGED


class TestGenerateChangelogFunction:
    """Tests for the generate_changelog convenience function."""

    def test_generate_with_defaults(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test generate_changelog with default options."""
        store = MockSyncHistoryStore(sample_entries)
        result = generate_changelog(store)

        assert "Changelog" in result
        assert "PROJ-" in result

    def test_generate_with_format(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test generate_changelog with specific format."""
        store = MockSyncHistoryStore(sample_entries)
        result = generate_changelog(store, format="json")

        import json

        data = json.loads(result)
        assert "changelog" in data

    def test_generate_with_days(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test generate_changelog with days filter."""
        store = MockSyncHistoryStore(sample_entries)
        result = generate_changelog(store, days=7)

        assert "Changelog" in result

    def test_generate_with_output(
        self, sample_entries: list[SyncHistoryEntry], tmp_path: Path
    ) -> None:
        """Test generate_changelog with output file."""
        store = MockSyncHistoryStore(sample_entries)
        output_file = tmp_path / "CHANGELOG.md"

        generate_changelog(store, output=output_file)

        assert output_file.exists()


class TestGrouping:
    """Tests for entry grouping functionality."""

    def test_group_by_date(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test grouping entries by date."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(group_by_date=True, group_by_type=False)
        generator = ChangelogGenerator(store, options)

        raw_entries = generator._fetch_entries()
        entries = generator._entries_to_changes(raw_entries)
        grouped = generator._group_entries(entries)

        # Should have date keys
        for key in grouped:
            assert len(key) == 10  # YYYY-MM-DD format

    def test_group_by_type(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test grouping entries by change type."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(group_by_date=False, group_by_type=True)
        generator = ChangelogGenerator(store, options)

        raw_entries = generator._fetch_entries()
        entries = generator._entries_to_changes(raw_entries)
        grouped = generator._group_entries(entries)

        # Should have "All Changes" as the only date key
        assert "All Changes" in grouped

        # Type keys should be capitalized
        type_keys = list(grouped["All Changes"].keys())
        for key in type_keys:
            assert key[0].isupper()  # Capitalized

    def test_group_by_both(self, sample_entries: list[SyncHistoryEntry]) -> None:
        """Test grouping by both date and type."""
        store = MockSyncHistoryStore(sample_entries)
        options = ChangelogOptions(group_by_date=True, group_by_type=True)
        generator = ChangelogGenerator(store, options)

        raw_entries = generator._fetch_entries()
        entries = generator._entries_to_changes(raw_entries)
        grouped = generator._group_entries(entries)

        # Should have nested structure
        for _date_key, type_groups in grouped.items():
            assert isinstance(type_groups, dict)
            for _type_key, entries_list in type_groups.items():
                assert isinstance(entries_list, list)
