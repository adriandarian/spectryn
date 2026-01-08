"""
Parallel Epic Sync - Process multiple epics simultaneously.

Uses concurrent execution to sync multiple epics in parallel,
significantly reducing total sync time for multi-epic files.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.entities import Epic
from spectryn.core.domain.events import EventBus
from spectryn.core.ports.document_formatter import DocumentFormatterPort
from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.core.ports.issue_tracker import IssueTrackerPort

from .multi_epic import EpicSyncResult, MultiEpicSyncResult


if TYPE_CHECKING:
    from spectryn.core.domain.config import SyncConfig

logger = logging.getLogger(__name__)


class ParallelStrategy(Enum):
    """Strategy for parallel execution."""

    THREAD_POOL = "thread_pool"  # Use thread pool executor
    SEQUENTIAL = "sequential"  # Fall back to sequential (for testing)


@dataclass
class ParallelSyncConfig:
    """Configuration for parallel sync."""

    max_workers: int = 4  # Maximum concurrent syncs
    strategy: ParallelStrategy = ParallelStrategy.THREAD_POOL
    timeout_per_epic: float = 300.0  # 5 minutes per epic
    fail_fast: bool = False  # Stop all on first failure
    rate_limit_delay: float = 0.1  # Delay between starting workers


@dataclass
class EpicProgress:
    """Progress tracking for a single epic."""

    epic_key: str
    epic_title: str
    status: str = "pending"  # pending, running, completed, failed
    phase: str = ""
    progress: float = 0.0  # 0.0 to 1.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


@dataclass
class ParallelSyncResult(MultiEpicSyncResult):
    """Extended result for parallel sync."""

    parallel_config: ParallelSyncConfig = field(default_factory=ParallelSyncConfig)
    workers_used: int = 0
    peak_concurrency: int = 0
    epic_progress: list[EpicProgress] = field(default_factory=list)

    def summary(self) -> str:
        """Generate a summary including parallel info."""
        base = super().summary()
        parallel_info = [
            "",
            "Parallel Execution:",
            f"  Workers: {self.workers_used}",
            f"  Peak concurrency: {self.peak_concurrency}",
            f"  Duration: {self.duration_seconds:.1f}s",
        ]

        # Calculate speedup estimate
        if self.epic_results:
            sequential_time = sum(r.duration_seconds for r in self.epic_results)
            if sequential_time > 0 and self.duration_seconds > 0:
                speedup = sequential_time / self.duration_seconds
                parallel_info.append(f"  Estimated speedup: {speedup:.1f}x")

        return base + "\n" + "\n".join(parallel_info)


class ParallelSyncOrchestrator:
    """
    Orchestrates parallel synchronization of multiple epics.

    Uses thread pool executor to process multiple epics concurrently,
    with configurable worker count and timeout handling.
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        parser: DocumentParserPort,
        formatter: DocumentFormatterPort,
        config: "SyncConfig",
        parallel_config: ParallelSyncConfig | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize the parallel sync orchestrator.

        Args:
            tracker: Issue tracker port
            parser: Document parser port
            formatter: Document formatter port
            config: Sync configuration
            parallel_config: Parallel execution configuration
            event_bus: Optional event bus
        """
        self.tracker = tracker
        self.parser = parser
        self.formatter = formatter
        self.config = config
        self.parallel_config = parallel_config or ParallelSyncConfig()
        self.event_bus = event_bus or EventBus()
        self.logger = logging.getLogger("ParallelSyncOrchestrator")

        # Thread-safe state
        self._lock = threading.Lock()
        self._active_workers = 0
        self._peak_concurrency = 0
        self._cancelled = False
        self._progress_map: dict[str, EpicProgress] = {}

    def sync(
        self,
        markdown_path: str,
        epic_filter: list[str] | None = None,
        progress_callback: Callable[[str, str, float], None] | None = None,
    ) -> ParallelSyncResult:
        """
        Sync multiple epics in parallel.

        Args:
            markdown_path: Path to markdown file
            epic_filter: Optional list of epic keys to include
            progress_callback: Callback for progress (epic_key, status, progress)

        Returns:
            ParallelSyncResult with sync details
        """
        result = ParallelSyncResult(
            dry_run=self.config.dry_run,
            parallel_config=self.parallel_config,
        )

        # Reset state
        self._cancelled = False
        self._active_workers = 0
        self._peak_concurrency = 0
        self._progress_map.clear()

        # Parse epics from file
        self.logger.info(f"Parsing epics from {markdown_path}")
        epics = self.parser.parse_epics(markdown_path)

        if not epics:
            self.logger.warning("No epics found in file")
            return result

        # Filter if specified
        if epic_filter:
            epics = [e for e in epics if str(e.key) in epic_filter]
            self.logger.info(f"Filtered to {len(epics)} epics")

        result.epics_total = len(epics)

        # Initialize progress tracking
        for epic in epics:
            progress = EpicProgress(
                epic_key=str(epic.key),
                epic_title=epic.title,
            )
            self._progress_map[str(epic.key)] = progress
            result.epic_progress.append(progress)

        # Choose strategy
        if self.parallel_config.strategy == ParallelStrategy.SEQUENTIAL:
            self._sync_sequential(epics, markdown_path, result, progress_callback)
        else:
            self._sync_parallel(epics, markdown_path, result, progress_callback)

        result.completed_at = datetime.now()
        result.workers_used = min(self.parallel_config.max_workers, len(epics))
        result.peak_concurrency = self._peak_concurrency

        return result

    def _sync_parallel(
        self,
        epics: list[Epic],
        markdown_path: str,
        result: ParallelSyncResult,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> None:
        """Execute sync in parallel using thread pool."""
        max_workers = min(self.parallel_config.max_workers, len(epics))
        self.logger.info(f"Starting parallel sync with {max_workers} workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {}
            for epic in epics:
                future = executor.submit(
                    self._sync_single_epic_safe,
                    epic,
                    markdown_path,
                    progress_callback,
                )
                futures[future] = epic

            # Collect results as they complete
            for future in as_completed(futures):
                epic = futures[future]
                epic_key = str(epic.key)

                try:
                    epic_result = future.result(timeout=self.parallel_config.timeout_per_epic)
                    result.add_epic_result(epic_result)

                    if progress_callback:
                        status = "completed" if epic_result.success else "failed"
                        progress_callback(epic_key, status, 1.0)

                    # Check fail-fast
                    if not epic_result.success and self.parallel_config.fail_fast:
                        self.logger.warning(f"Fail-fast triggered by {epic_key}")
                        self._cancelled = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                except TimeoutError:
                    self.logger.error(f"Timeout syncing epic {epic_key}")
                    epic_result = EpicSyncResult(
                        epic_key=epic_key,
                        epic_title=epic.title,
                        success=False,
                        errors=[f"Sync timed out after {self.parallel_config.timeout_per_epic}s"],
                    )
                    result.add_epic_result(epic_result)

                    if progress_callback:
                        progress_callback(epic_key, "timeout", 1.0)

                except Exception as e:
                    self.logger.error(f"Error syncing {epic_key}: {e}")
                    epic_result = EpicSyncResult(
                        epic_key=epic_key,
                        epic_title=epic.title,
                        success=False,
                        errors=[str(e)],
                    )
                    result.add_epic_result(epic_result)

                    if progress_callback:
                        progress_callback(epic_key, "error", 1.0)

    def _sync_sequential(
        self,
        epics: list[Epic],
        markdown_path: str,
        result: ParallelSyncResult,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> None:
        """Execute sync sequentially (fallback/testing)."""
        self.logger.info("Running sequential sync")
        self._peak_concurrency = 1

        for i, epic in enumerate(epics):
            if self._cancelled:
                break

            epic_key = str(epic.key)
            self.logger.info(f"[{i + 1}/{len(epics)}] Syncing {epic_key}")

            if progress_callback:
                progress_callback(epic_key, "running", 0.0)

            epic_result = self._sync_single_epic_safe(epic, markdown_path, progress_callback)
            result.add_epic_result(epic_result)

            if progress_callback:
                status = "completed" if epic_result.success else "failed"
                progress_callback(epic_key, status, 1.0)

            if not epic_result.success and self.parallel_config.fail_fast:
                self._cancelled = True
                break

    def _sync_single_epic_safe(
        self,
        epic: Epic,
        markdown_path: str,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> EpicSyncResult:
        """
        Safely sync a single epic with error handling.

        Thread-safe wrapper around the sync logic.
        """
        from .orchestrator import SyncOrchestrator, SyncResult

        epic_key = str(epic.key)

        # Track worker
        with self._lock:
            if self._cancelled:
                return EpicSyncResult(
                    epic_key=epic_key,
                    epic_title=epic.title,
                    success=False,
                    errors=["Sync cancelled"],
                )

            self._active_workers += 1
            self._peak_concurrency = max(self._peak_concurrency, self._active_workers)

            if epic_key in self._progress_map:
                self._progress_map[epic_key].status = "running"
                self._progress_map[epic_key].started_at = datetime.now()

        try:
            result = EpicSyncResult(
                epic_key=epic_key,
                epic_title=epic.title,
                dry_run=self.config.dry_run,
                started_at=datetime.now(),
            )

            result.stories_total = len(epic.stories)

            if not epic.stories:
                result.add_warning(f"No stories found for epic {epic_key}")
                result.completed_at = datetime.now()
                return result

            if progress_callback:
                progress_callback(epic_key, "fetching", 0.2)

            # Create orchestrator for this epic
            orchestrator = SyncOrchestrator(
                tracker=self.tracker,
                parser=self.parser,
                formatter=self.formatter,
                config=self.config,
                event_bus=self.event_bus,
            )

            # Inject pre-parsed stories
            orchestrator._md_stories = epic.stories

            # Fetch and match
            orchestrator._fetch_jira_state(epic_key)
            orchestrator._match_stories()

            result.stories_matched = len(orchestrator._matches)

            if progress_callback:
                progress_callback(epic_key, "syncing", 0.5)

            # Create sync result
            sync_result = SyncResult(dry_run=self.config.dry_run)
            sync_result.stories_matched = result.stories_matched

            # Sync descriptions
            if self.config.sync_descriptions:
                orchestrator._sync_descriptions(sync_result)

            if progress_callback:
                progress_callback(epic_key, "subtasks", 0.7)

            # Sync subtasks
            if self.config.sync_subtasks:
                orchestrator._sync_subtasks(sync_result)

            # Transfer results
            result.stories_updated = sync_result.stories_updated
            result.subtasks_created = sync_result.subtasks_created
            result.subtasks_updated = sync_result.subtasks_updated
            result.errors.extend(sync_result.errors)
            result.warnings.extend(sync_result.warnings)
            result.success = sync_result.success

            if progress_callback:
                progress_callback(epic_key, "completing", 0.9)

        except Exception as e:
            result.add_error(f"Sync failed: {e!s}")
            self.logger.error(f"Error syncing {epic_key}: {e}")

            with self._lock:
                if epic_key in self._progress_map:
                    self._progress_map[epic_key].error = str(e)

        finally:
            with self._lock:
                self._active_workers -= 1

                if epic_key in self._progress_map:
                    self._progress_map[epic_key].status = (
                        "completed" if result.success else "failed"
                    )
                    self._progress_map[epic_key].completed_at = datetime.now()
                    self._progress_map[epic_key].progress = 1.0

            result.completed_at = datetime.now()

        return result

    def cancel(self) -> None:
        """Cancel ongoing parallel sync."""
        self._cancelled = True
        self.logger.info("Parallel sync cancelled")

    def get_progress(self) -> dict[str, EpicProgress]:
        """Get current progress for all epics."""
        with self._lock:
            return dict(self._progress_map)

    def get_stats(self) -> dict[str, Any]:
        """Get current sync statistics."""
        with self._lock:
            return {
                "active_workers": self._active_workers,
                "peak_concurrency": self._peak_concurrency,
                "cancelled": self._cancelled,
                "epics_in_progress": sum(
                    1 for p in self._progress_map.values() if p.status == "running"
                ),
                "epics_completed": sum(
                    1 for p in self._progress_map.values() if p.status == "completed"
                ),
                "epics_failed": sum(1 for p in self._progress_map.values() if p.status == "failed"),
            }


def create_parallel_orchestrator(
    tracker: IssueTrackerPort,
    parser: DocumentParserPort,
    formatter: DocumentFormatterPort,
    config: "SyncConfig",
    max_workers: int = 4,
    fail_fast: bool = False,
) -> ParallelSyncOrchestrator:
    """
    Factory function to create a parallel sync orchestrator.

    Args:
        tracker: Issue tracker port
        parser: Document parser port
        formatter: Document formatter port
        config: Sync configuration
        max_workers: Maximum concurrent workers
        fail_fast: Stop on first failure

    Returns:
        Configured ParallelSyncOrchestrator
    """
    parallel_config = ParallelSyncConfig(
        max_workers=max_workers,
        fail_fast=fail_fast,
    )

    return ParallelSyncOrchestrator(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config,
        parallel_config=parallel_config,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def is_parallel_available() -> bool:
    """
    Check if parallel processing is available.

    Returns:
        True if parallel processing can be used.
    """
    try:
        import asyncio

        # Check if we can create an event loop
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            # No running loop, but asyncio is available
            return True
    except ImportError:
        return False


def run_async(coro: Any) -> Any:
    """
    Run an async coroutine synchronously.

    Args:
        coro: Coroutine to run.

    Returns:
        Result of the coroutine.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
        # Already in async context, run in thread pool
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, create one
        return asyncio.run(coro)
