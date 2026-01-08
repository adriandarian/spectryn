"""Tests for Parallel Epic Sync module."""

import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from spectryn.application.sync.parallel import (
    EpicProgress,
    ParallelStrategy,
    ParallelSyncConfig,
    ParallelSyncOrchestrator,
    ParallelSyncResult,
    create_parallel_orchestrator,
)
from spectryn.core.domain.entities import Epic, UserStory
from spectryn.core.domain.value_objects import Description, IssueKey, StoryId


@pytest.fixture
def mock_tracker():
    """Create a mock tracker."""
    tracker = MagicMock()
    tracker.get_issues_for_epic.return_value = []
    return tracker


@pytest.fixture
def mock_parser():
    """Create a mock parser."""
    return MagicMock()


@pytest.fixture
def mock_formatter():
    """Create a mock formatter."""
    return MagicMock()


@pytest.fixture
def mock_config():
    """Create a mock sync config."""
    config = MagicMock()
    config.dry_run = False
    config.sync_descriptions = True
    config.sync_subtasks = True
    return config


@pytest.fixture
def sample_stories() -> list[UserStory]:
    """Create sample stories."""
    return [
        UserStory(
            id=StoryId.from_string("US-001"),
            title="Story 1",
            description=Description(role="user", want="feature", benefit="value"),
        ),
        UserStory(
            id=StoryId.from_string("US-002"),
            title="Story 2",
            description=Description(role="user", want="feature 2", benefit="value 2"),
        ),
    ]


@pytest.fixture
def sample_epics(sample_stories: list[UserStory]) -> list[Epic]:
    """Create sample epics."""
    return [
        Epic(
            key=IssueKey("PROJ-1"),
            title="Epic 1",
            stories=sample_stories[:1],
        ),
        Epic(
            key=IssueKey("PROJ-2"),
            title="Epic 2",
            stories=sample_stories[1:],
        ),
        Epic(
            key=IssueKey("PROJ-3"),
            title="Epic 3",
            stories=[],
        ),
    ]


class TestParallelStrategy:
    """Tests for ParallelStrategy enum."""

    def test_strategy_values(self) -> None:
        """Test strategy enum values."""
        assert ParallelStrategy.THREAD_POOL.value == "thread_pool"
        assert ParallelStrategy.SEQUENTIAL.value == "sequential"


class TestParallelSyncConfig:
    """Tests for ParallelSyncConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = ParallelSyncConfig()

        assert config.max_workers == 4
        assert config.strategy == ParallelStrategy.THREAD_POOL
        assert config.timeout_per_epic == 300.0
        assert config.fail_fast is False

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = ParallelSyncConfig(
            max_workers=8,
            strategy=ParallelStrategy.SEQUENTIAL,
            fail_fast=True,
        )

        assert config.max_workers == 8
        assert config.strategy == ParallelStrategy.SEQUENTIAL
        assert config.fail_fast is True


class TestEpicProgress:
    """Tests for EpicProgress."""

    def test_progress_creation(self) -> None:
        """Test creating epic progress."""
        progress = EpicProgress(
            epic_key="PROJ-1",
            epic_title="Epic 1",
            status="running",
            phase="fetching",
            progress=0.5,
        )

        assert progress.epic_key == "PROJ-1"
        assert progress.status == "running"
        assert progress.progress == 0.5


class TestParallelSyncResult:
    """Tests for ParallelSyncResult."""

    def test_result_extends_multi_epic(self) -> None:
        """Test result extends MultiEpicSyncResult."""
        result = ParallelSyncResult()

        assert result.workers_used == 0
        assert result.peak_concurrency == 0
        assert result.epic_progress == []
        # Inherited fields
        assert result.epics_total == 0
        assert result.success is True

    def test_summary_includes_parallel_info(self) -> None:
        """Test summary includes parallel execution info."""
        result = ParallelSyncResult(
            workers_used=4,
            peak_concurrency=4,
        )
        result.started_at = datetime.now()
        result.completed_at = datetime.now()

        summary = result.summary()

        assert "Parallel Execution" in summary
        assert "Workers: 4" in summary


class TestParallelSyncOrchestrator:
    """Tests for ParallelSyncOrchestrator."""

    def test_sync_empty_epics(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
    ) -> None:
        """Test syncing with no epics."""
        mock_parser.parse_epics.return_value = []

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

        result = orchestrator.sync("test.md")

        assert result.epics_total == 0
        assert result.success is True

    def test_sync_sequential_strategy(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
        sample_epics,
    ) -> None:
        """Test sequential sync strategy."""
        mock_parser.parse_epics.return_value = sample_epics

        parallel_config = ParallelSyncConfig(strategy=ParallelStrategy.SEQUENTIAL)

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            parallel_config=parallel_config,
        )

        # Mock the internal orchestrator
        with patch("spectryn.application.sync.orchestrator.SyncOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch._matches = {}
            mock_orch_cls.return_value = mock_orch

            result = orchestrator.sync("test.md")

            assert result.epics_total == 3
            assert result.peak_concurrency == 1  # Sequential

    def test_sync_parallel_strategy(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
        sample_epics,
    ) -> None:
        """Test parallel sync strategy."""
        mock_parser.parse_epics.return_value = sample_epics

        parallel_config = ParallelSyncConfig(
            max_workers=2,
            strategy=ParallelStrategy.THREAD_POOL,
        )

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            parallel_config=parallel_config,
        )

        with patch("spectryn.application.sync.orchestrator.SyncOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch._matches = {}
            mock_orch_cls.return_value = mock_orch

            result = orchestrator.sync("test.md")

            assert result.epics_total == 3
            assert result.workers_used == 2  # Min of workers and epics
            assert result.peak_concurrency >= 1

    def test_sync_with_epic_filter(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
        sample_epics,
    ) -> None:
        """Test syncing with epic filter."""
        mock_parser.parse_epics.return_value = sample_epics

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

        with patch("spectryn.application.sync.orchestrator.SyncOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch._matches = {}
            mock_orch_cls.return_value = mock_orch

            result = orchestrator.sync("test.md", epic_filter=["PROJ-1"])

            assert result.epics_total == 1

    def test_sync_with_progress_callback(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
        sample_epics,
    ) -> None:
        """Test progress callback is called."""
        mock_parser.parse_epics.return_value = sample_epics[:1]

        parallel_config = ParallelSyncConfig(strategy=ParallelStrategy.SEQUENTIAL)

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            parallel_config=parallel_config,
        )

        progress_calls = []

        def progress_callback(epic_key: str, status: str, progress: float) -> None:
            progress_calls.append((epic_key, status, progress))

        with patch("spectryn.application.sync.orchestrator.SyncOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch._matches = {}
            mock_orch_cls.return_value = mock_orch

            orchestrator.sync("test.md", progress_callback=progress_callback)

            # Should have received progress calls
            assert len(progress_calls) > 0

    def test_cancel(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
    ) -> None:
        """Test cancellation."""
        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

        orchestrator.cancel()

        assert orchestrator._cancelled is True

    def test_get_progress(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
    ) -> None:
        """Test getting progress."""
        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

        progress = orchestrator.get_progress()
        assert isinstance(progress, dict)

    def test_get_stats(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
    ) -> None:
        """Test getting stats."""
        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
        )

        stats = orchestrator.get_stats()

        assert "active_workers" in stats
        assert "peak_concurrency" in stats
        assert "cancelled" in stats

    def test_fail_fast_stops_sync(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
        sample_epics,
    ) -> None:
        """Test fail-fast stops on first failure."""
        mock_parser.parse_epics.return_value = sample_epics

        parallel_config = ParallelSyncConfig(
            strategy=ParallelStrategy.SEQUENTIAL,
            fail_fast=True,
        )

        orchestrator = ParallelSyncOrchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            parallel_config=parallel_config,
        )

        with patch("spectryn.application.sync.orchestrator.SyncOrchestrator") as mock_orch_cls:
            # First epic fails
            mock_orch = MagicMock()
            mock_orch._fetch_jira_state.side_effect = Exception("API Error")
            mock_orch_cls.return_value = mock_orch

            result = orchestrator.sync("test.md")

            # Should have stopped after first failure
            assert result.epics_failed >= 1
            # Not all epics processed due to fail-fast
            assert len(result.epic_results) < len(sample_epics)


class TestCreateParallelOrchestrator:
    """Tests for create_parallel_orchestrator factory."""

    def test_factory_creates_orchestrator(
        self,
        mock_tracker,
        mock_parser,
        mock_formatter,
        mock_config,
    ) -> None:
        """Test factory creates configured orchestrator."""
        orchestrator = create_parallel_orchestrator(
            tracker=mock_tracker,
            parser=mock_parser,
            formatter=mock_formatter,
            config=mock_config,
            max_workers=8,
            fail_fast=True,
        )

        assert isinstance(orchestrator, ParallelSyncOrchestrator)
        assert orchestrator.parallel_config.max_workers == 8
        assert orchestrator.parallel_config.fail_fast is True
