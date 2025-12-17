"""
Tests for multi-epic support - sync multiple epics from one file.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from spectra.adapters.parsers.markdown import MarkdownParser
from spectra.application.sync.multi_epic import (
    EpicSyncResult,
    MultiEpicSyncOrchestrator,
    MultiEpicSyncResult,
)
from spectra.core.ports.config_provider import SyncConfig


# Sample multi-epic markdown content
MULTI_EPIC_MARKDOWN = """# Project: Test Project Roadmap

## Epic: PROJ-100 - User Authentication

### 📖 US-001: User Login

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 High |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to log in
**So that** I can access the app

### 📖 US-002: Password Reset

| Field | Value |
|-------|-------|
| **Story Points** | 2 |
| **Priority** | 🟡 Medium |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to reset my password
**So that** I can regain access

## Epic: PROJ-200 - User Profile

### 📖 US-003: View Profile

| Field | Value |
|-------|-------|
| **Story Points** | 2 |
| **Priority** | 🟡 Medium |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to view my profile
**So that** I can see my info

### 📖 US-004: Edit Profile

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 Medium |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to edit my profile
**So that** I can update my info

## Epic: PROJ-300 - Notifications

### 📖 US-005: Email Notifications

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟢 Low |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to receive email notifications
**So that** I stay informed
"""

SINGLE_EPIC_MARKDOWN = """# Epic: My Single Epic

### 📖 US-001: Story One

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 High |
| **Status** | 📋 Planned |

#### Description
**As a** developer
**I want** a feature
**So that** it works
"""


class TestMarkdownParserMultiEpic:
    """Tests for multi-epic parsing in MarkdownParser."""

    def test_is_multi_epic_true(self):
        """Test detecting multi-epic file."""
        parser = MarkdownParser()

        result = parser.is_multi_epic(MULTI_EPIC_MARKDOWN)

        assert result is True

    def test_is_multi_epic_false(self):
        """Test detecting single-epic file."""
        parser = MarkdownParser()

        result = parser.is_multi_epic(SINGLE_EPIC_MARKDOWN)

        assert result is False

    def test_parse_epics_multiple(self):
        """Test parsing multiple epics."""
        parser = MarkdownParser()

        epics = parser.parse_epics(MULTI_EPIC_MARKDOWN)

        assert len(epics) == 3

        # Check first epic
        assert str(epics[0].key) == "PROJ-100"
        assert "User Authentication" in epics[0].title
        assert len(epics[0].stories) == 2

        # Check second epic
        assert str(epics[1].key) == "PROJ-200"
        assert "User Profile" in epics[1].title
        assert len(epics[1].stories) == 2

        # Check third epic
        assert str(epics[2].key) == "PROJ-300"
        assert "Notifications" in epics[2].title
        assert len(epics[2].stories) == 1

    def test_parse_epics_single_fallback(self):
        """Test that parse_epics falls back for single epic."""
        parser = MarkdownParser()

        # With ## Epic: header
        epics = parser.parse_epics(
            "## Epic: PROJ-100 - Test\n\n### 📖 US-001: Story\n\n| Field | Value |\n|-------|-------|\n| **Story Points** | 1 |\n\n#### Description\n**As a** user\n**I want** test\n**So that** works\n"
        )

        assert len(epics) == 1
        assert str(epics[0].key) == "PROJ-100"

    def test_get_epic_keys(self):
        """Test getting epic keys from file."""
        parser = MarkdownParser()

        keys = parser.get_epic_keys(MULTI_EPIC_MARKDOWN)

        assert keys == ["PROJ-100", "PROJ-200", "PROJ-300"]

    def test_parse_epic_stories_assigned_correctly(self):
        """Test that stories are assigned to correct epics."""
        parser = MarkdownParser()

        epics = parser.parse_epics(MULTI_EPIC_MARKDOWN)

        # First epic should have US-001 and US-002
        story_ids_1 = [str(s.id) for s in epics[0].stories]
        assert "US-001" in story_ids_1
        assert "US-002" in story_ids_1

        # Second epic should have US-003 and US-004
        story_ids_2 = [str(s.id) for s in epics[1].stories]
        assert "US-003" in story_ids_2
        assert "US-004" in story_ids_2

        # Third epic should have US-005
        story_ids_3 = [str(s.id) for s in epics[2].stories]
        assert "US-005" in story_ids_3

    def test_parse_epic_without_title(self):
        """Test parsing epic without title after key."""
        parser = MarkdownParser()

        content = """## Epic: PROJ-100

### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 1 |

#### Description
**As a** user
**I want** test
**So that** works
"""

        epics = parser.parse_epics(content)

        assert len(epics) == 1
        assert str(epics[0].key) == "PROJ-100"
        assert "Epic PROJ-100" in epics[0].title


class TestEpicSyncResult:
    """Tests for EpicSyncResult dataclass."""

    def test_initial_state(self):
        """Test initial state."""
        result = EpicSyncResult(
            epic_key="PROJ-100",
            epic_title="Test Epic",
        )

        assert result.success
        assert result.stories_total == 0
        assert len(result.errors) == 0

    def test_add_error(self):
        """Test adding error sets success to False."""
        result = EpicSyncResult(
            epic_key="PROJ-100",
            epic_title="Test Epic",
        )

        result.add_error("Something went wrong")

        assert not result.success
        assert "Something went wrong" in result.errors

    def test_duration_seconds(self):
        """Test duration calculation."""
        result = EpicSyncResult(
            epic_key="PROJ-100",
            epic_title="Test Epic",
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 0, 30),
        )

        assert result.duration_seconds == 30.0


class TestMultiEpicSyncResult:
    """Tests for MultiEpicSyncResult dataclass."""

    def test_initial_state(self):
        """Test initial state."""
        result = MultiEpicSyncResult()

        assert result.success
        assert result.epics_total == 0
        assert result.epics_synced == 0

    def test_add_epic_result_success(self):
        """Test adding successful epic result."""
        result = MultiEpicSyncResult()
        result.epics_total = 1

        epic_result = EpicSyncResult(
            epic_key="PROJ-100",
            epic_title="Test Epic",
            stories_total=5,
            stories_matched=5,
            subtasks_created=3,
        )

        result.add_epic_result(epic_result)

        assert result.epics_synced == 1
        assert result.epics_failed == 0
        assert result.total_stories == 5
        assert result.total_subtasks_created == 3

    def test_add_epic_result_failure(self):
        """Test adding failed epic result."""
        result = MultiEpicSyncResult()
        result.epics_total = 1

        epic_result = EpicSyncResult(
            epic_key="PROJ-100",
            epic_title="Test Epic",
            success=False,
            errors=["Error 1"],
        )

        result.add_epic_result(epic_result)

        assert result.epics_synced == 0
        assert result.epics_failed == 1
        assert not result.success
        assert "Error 1" in result.errors

    def test_summary(self):
        """Test summary generation."""
        result = MultiEpicSyncResult()
        result.epics_total = 2

        result.add_epic_result(
            EpicSyncResult(
                epic_key="PROJ-100",
                epic_title="Epic 1",
                stories_matched=5,
            )
        )
        result.add_epic_result(
            EpicSyncResult(
                epic_key="PROJ-200",
                epic_title="Epic 2",
                stories_matched=3,
            )
        )

        summary = result.summary()

        assert "Multi-Epic Sync" in summary
        assert "2/2" in summary


class TestMultiEpicSyncOrchestrator:
    """Tests for MultiEpicSyncOrchestrator class."""

    @pytest.fixture
    def mock_tracker(self):
        """Create mock tracker."""
        tracker = Mock()
        tracker.get_epic.return_value = {
            "key": "PROJ-100",
            "fields": {"summary": "Test Epic"},
        }
        tracker.get_issues_for_epic.return_value = []
        return tracker

    @pytest.fixture
    def mock_formatter(self):
        """Create mock formatter."""
        return Mock()

    @pytest.fixture
    def config(self):
        """Create sync config."""
        return SyncConfig(
            dry_run=True,
            sync_descriptions=True,
            sync_subtasks=True,
        )

    def test_initialization(self, mock_tracker, mock_formatter, config):
        """Test orchestrator initialization."""
        parser = MarkdownParser()

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=parser,
            formatter=mock_formatter,
            config=config,
        )

        assert orchestrator.tracker == mock_tracker
        assert orchestrator.parser == parser

    def test_get_epic_summary(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test getting epic summary."""
        # Write test file
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        summary = orchestrator.get_epic_summary(str(md_file))

        assert summary["total_epics"] == 3
        assert summary["total_stories"] == 5
        assert len(summary["epics"]) == 3

    def test_analyze(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test analyzing multi-epic file."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.analyze(str(md_file))

        assert result.epics_total == 3
        assert len(result.epic_results) == 3

    def test_analyze_with_filter(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test analyzing with epic filter."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.analyze(
            str(md_file),
            epic_filter=["PROJ-100", "PROJ-300"],
        )

        assert result.epics_total == 2
        epic_keys = [r.epic_key for r in result.epic_results]
        assert "PROJ-100" in epic_keys
        assert "PROJ-300" in epic_keys
        assert "PROJ-200" not in epic_keys

    def test_sync_all_epics(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test syncing all epics."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        # Mock tracker methods
        mock_tracker.get_epic.return_value = {"key": "PROJ-100", "fields": {"summary": "Epic"}}
        mock_tracker.get_issues_for_epic.return_value = []

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.sync(str(md_file))

        assert result.epics_total == 3
        # In dry run, all should succeed
        assert result.epics_synced + result.epics_failed == 3

    def test_sync_with_filter(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test syncing with filter."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        mock_tracker.get_epic.return_value = {"key": "PROJ-200", "fields": {"summary": "Epic"}}
        mock_tracker.get_issues_for_epic.return_value = []

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.sync(
            str(md_file),
            epic_filter=["PROJ-200"],
        )

        assert result.epics_total == 1
        assert result.epic_results[0].epic_key == "PROJ-200"

    def test_sync_progress_callback(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test progress callback is called."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        mock_tracker.get_epic.return_value = {"key": "PROJ-100", "fields": {"summary": "Epic"}}
        mock_tracker.get_issues_for_epic.return_value = []

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        progress_calls = []

        def on_progress(epic_key, phase, current, total):
            progress_calls.append((epic_key, phase, current, total))

        orchestrator.sync(str(md_file), progress_callback=on_progress)

        assert len(progress_calls) > 0
        # Should have calls for each epic
        epic_keys_in_calls = {call[0] for call in progress_calls}
        assert "PROJ-100" in epic_keys_in_calls

    def test_sync_stop_on_error(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test stopping on first error."""
        md_file = tmp_path / "roadmap.md"
        md_file.write_text(MULTI_EPIC_MARKDOWN, encoding="utf-8")

        # Make first epic fail
        mock_tracker.get_epic.side_effect = Exception("Epic not found")

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.sync(
            str(md_file),
            stop_on_error=True,
        )

        # Should have stopped after first error
        assert result.epics_failed >= 1
        assert len(result.epic_results) < 3  # Not all epics processed

    def test_sync_empty_file(self, mock_tracker, mock_formatter, config, tmp_path):
        """Test syncing empty file."""
        md_file = tmp_path / "empty.md"
        md_file.write_text("# Empty Project\n\nNo epics here.")

        orchestrator = MultiEpicSyncOrchestrator(
            tracker=mock_tracker,
            parser=MarkdownParser(),
            formatter=mock_formatter,
            config=config,
        )

        result = orchestrator.sync(str(md_file))

        # Should handle gracefully
        assert not result.success or result.epics_total == 0


class TestMultiEpicEdgeCases:
    """Edge case tests for multi-epic support."""

    def test_epic_with_no_stories(self):
        """Test parsing epic with no stories."""
        parser = MarkdownParser()

        content = """## Epic: PROJ-100 - Empty Epic

No stories here.

## Epic: PROJ-200 - Has Stories

### 📖 US-001: A Story

| Field | Value |
|-------|-------|
| **Story Points** | 1 |

#### Description
**As a** user
**I want** test
**So that** works
"""

        epics = parser.parse_epics(content)

        assert len(epics) == 2
        assert len(epics[0].stories) == 0
        assert len(epics[1].stories) == 1

    def test_epic_key_variations(self):
        """Test different epic key formats."""
        parser = MarkdownParser()

        content = """## Epic: ABC-1 - Short Key

### 📖 US-001: Story 1

| Field | Value |
|-------|-------|
| **Story Points** | 1 |

#### Description
**As a** user
**I want** test
**So that** works

## Epic: VERYLONGPROJECT-12345 - Long Key

### 📖 US-002: Story 2

| Field | Value |
|-------|-------|
| **Story Points** | 1 |

#### Description
**As a** user
**I want** test
**So that** works
"""

        epics = parser.parse_epics(content)

        assert len(epics) == 2
        assert str(epics[0].key) == "ABC-1"
        assert str(epics[1].key) == "VERYLONGPROJECT-12345"

    def test_epic_title_with_special_chars(self):
        """Test epic title with special characters."""
        parser = MarkdownParser()

        content = """## Epic: PROJ-100 - OAuth 2.0 & JWT Auth (Phase 1)

### 📖 US-001: Story

| Field | Value |
|-------|-------|
| **Story Points** | 1 |

#### Description
**As a** user
**I want** test
**So that** works
"""

        epics = parser.parse_epics(content)

        assert len(epics) == 1
        assert "OAuth 2.0" in epics[0].title
