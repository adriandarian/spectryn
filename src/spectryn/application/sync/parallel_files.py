"""
Parallel File Processing - Process multiple files concurrently.

Provides concurrent processing of multiple markdown files,
useful for large projects with many epic files.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

from spectryn.core.domain.events import EventBus
from spectryn.core.ports.document_formatter import DocumentFormatterPort
from spectryn.core.ports.document_parser import DocumentParserPort
from spectryn.core.ports.issue_tracker import IssueTrackerPort

from .multi_epic import EpicSyncResult


if TYPE_CHECKING:
    from spectryn.core.domain.config import SyncConfig

logger = logging.getLogger(__name__)


@dataclass
class FileProgress:
    """Progress tracking for a single file."""

    file_path: str
    file_name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    epics_found: int = 0
    epics_synced: int = 0
    stories_synced: int = 0
    progress: float = 0.0  # 0.0 to 1.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0


@dataclass
class FileSyncResult:
    """Result of syncing a single file."""

    file_path: str
    file_name: str
    success: bool = True
    dry_run: bool = False

    # Epic counts
    epics_found: int = 0
    epics_synced: int = 0
    epics_failed: int = 0

    # Story counts
    stories_total: int = 0
    stories_matched: int = 0
    stories_updated: int = 0

    # Subtask counts
    subtasks_created: int = 0
    subtasks_updated: int = 0

    # Issues
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Nested results
    epic_results: list[EpicSyncResult] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def add_error(self, error: str) -> None:
        """Add an error."""
        self.errors.append(error)
        self.success = False


@dataclass
class ParallelFilesConfig:
    """Configuration for parallel file processing."""

    max_workers: int = 4  # Maximum concurrent file processors
    timeout_per_file: float = 600.0  # 10 minutes per file
    fail_fast: bool = False  # Stop all on first failure
    skip_empty_files: bool = True  # Skip files with no epics
    file_pattern: str = "*.md"  # Glob pattern for files


@dataclass
class ParallelFilesResult:
    """Result of parallel file processing."""

    success: bool = True
    dry_run: bool = False

    # File counts
    files_total: int = 0
    files_processed: int = 0
    files_succeeded: int = 0
    files_failed: int = 0
    files_skipped: int = 0

    # Aggregate counts
    total_epics: int = 0
    total_stories: int = 0
    total_stories_updated: int = 0
    total_subtasks_created: int = 0

    # File results
    file_results: list[FileSyncResult] = field(default_factory=list)
    file_progress: list[FileProgress] = field(default_factory=list)

    # Parallel stats
    workers_used: int = 0
    peak_concurrency: int = 0

    # Issues
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    def add_file_result(self, result: FileSyncResult) -> None:
        """Add result for a single file."""
        self.file_results.append(result)
        self.files_processed += 1

        if result.success:
            self.files_succeeded += 1
        else:
            self.files_failed += 1
            self.success = False

        self.total_epics += result.epics_found
        self.total_stories += result.stories_total
        self.total_stories_updated += result.stories_updated
        self.total_subtasks_created += result.subtasks_created

        self.errors.extend(result.errors)
        self.warnings.extend(result.warnings)

    def summary(self) -> str:
        """Generate a summary."""
        lines = [
            f"Parallel File Processing {'(dry run)' if self.dry_run else ''}",
            "=" * 50,
            f"Files: {self.files_succeeded}/{self.files_total} succeeded",
        ]

        if self.files_failed:
            lines.append(f"  Failed: {self.files_failed}")
        if self.files_skipped:
            lines.append(f"  Skipped: {self.files_skipped}")

        lines.extend(
            [
                "",
                f"Epics: {self.total_epics}",
                f"Stories: {self.total_stories} total, {self.total_stories_updated} updated",
                f"Subtasks: {self.total_subtasks_created} created",
                "",
                "Parallel Execution:",
                f"  Workers: {self.workers_used}",
                f"  Peak concurrency: {self.peak_concurrency}",
                f"  Duration: {self.duration_seconds:.1f}s",
            ]
        )

        # Speedup estimate
        if self.file_results:
            sequential_time = sum(r.duration_seconds for r in self.file_results)
            if sequential_time > 0 and self.duration_seconds > 0:
                speedup = sequential_time / self.duration_seconds
                lines.append(f"  Estimated speedup: {speedup:.1f}x")

        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for error in self.errors[:5]:
                lines.append(f"  - {error}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        return "\n".join(lines)


class ParallelFileProcessor:
    """
    Processes multiple markdown files in parallel.

    Uses thread pool executor to process files concurrently,
    with configurable worker count and timeout handling.
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        parser: DocumentParserPort,
        formatter: DocumentFormatterPort,
        config: "SyncConfig",
        parallel_config: ParallelFilesConfig | None = None,
        event_bus: EventBus | None = None,
    ):
        """
        Initialize the parallel file processor.

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
        self.parallel_config = parallel_config or ParallelFilesConfig()
        self.event_bus = event_bus or EventBus()
        self.logger = logging.getLogger("ParallelFileProcessor")

        # Thread-safe state
        self._lock = Lock()
        self._active_workers = 0
        self._peak_concurrency = 0
        self._cancelled = False
        self._progress_map: dict[str, FileProgress] = {}

    def process(
        self,
        file_paths: list[str | Path],
        epic_filter: list[str] | None = None,
        progress_callback: Callable[[str, str, float], None] | None = None,
    ) -> ParallelFilesResult:
        """
        Process multiple files in parallel.

        Args:
            file_paths: List of file paths to process.
            epic_filter: Optional list of epic keys to include.
            progress_callback: Callback for progress (file_path, status, progress).

        Returns:
            ParallelFilesResult with processing details.
        """
        result = ParallelFilesResult(dry_run=self.config.dry_run)

        # Reset state
        self._cancelled = False
        self._active_workers = 0
        self._peak_concurrency = 0
        self._progress_map.clear()

        # Normalize paths
        paths = [Path(p) for p in file_paths]

        # Filter to existing files
        valid_paths = []
        for path in paths:
            if path.exists():
                valid_paths.append(path)
            else:
                self.logger.warning(f"File not found: {path}")
                result.warnings.append(f"File not found: {path}")

        if not valid_paths:
            self.logger.warning("No valid files to process")
            return result

        result.files_total = len(valid_paths)

        # Initialize progress tracking
        for path in valid_paths:
            progress = FileProgress(
                file_path=str(path),
                file_name=path.name,
            )
            self._progress_map[str(path)] = progress
            result.file_progress.append(progress)

        # Process files in parallel
        self._process_parallel(valid_paths, epic_filter, result, progress_callback)

        result.completed_at = datetime.now()
        result.workers_used = min(self.parallel_config.max_workers, len(valid_paths))
        result.peak_concurrency = self._peak_concurrency

        return result

    def process_directory(
        self,
        directory: str | Path,
        pattern: str = "*.md",
        recursive: bool = False,
        epic_filter: list[str] | None = None,
        progress_callback: Callable[[str, str, float], None] | None = None,
    ) -> ParallelFilesResult:
        """
        Process all matching files in a directory.

        Args:
            directory: Directory to scan.
            pattern: Glob pattern for files.
            recursive: Whether to search recursively.
            epic_filter: Optional list of epic keys to include.
            progress_callback: Progress callback.

        Returns:
            ParallelFilesResult with processing details.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            result = ParallelFilesResult(dry_run=self.config.dry_run)
            result.errors.append(f"Directory not found: {directory}")
            result.success = False
            return result

        # Find matching files
        files = list(dir_path.rglob(pattern)) if recursive else list(dir_path.glob(pattern))

        self.logger.info(f"Found {len(files)} files matching {pattern} in {directory}")

        return self.process(
            [str(f) for f in files],
            epic_filter=epic_filter,
            progress_callback=progress_callback,
        )

    def _process_parallel(
        self,
        paths: list[Path],
        epic_filter: list[str] | None,
        result: ParallelFilesResult,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> None:
        """Execute file processing in parallel."""
        max_workers = min(self.parallel_config.max_workers, len(paths))
        self.logger.info(f"Starting parallel processing with {max_workers} workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {}
            for path in paths:
                future = executor.submit(
                    self._process_single_file,
                    path,
                    epic_filter,
                    progress_callback,
                )
                futures[future] = path

            # Collect results as they complete
            for future in as_completed(futures):
                path = futures[future]
                file_path = str(path)

                try:
                    file_result = future.result(timeout=self.parallel_config.timeout_per_file)

                    if file_result.epics_found == 0 and self.parallel_config.skip_empty_files:
                        result.files_skipped += 1
                        if progress_callback:
                            progress_callback(file_path, "skipped", 1.0)
                    else:
                        result.add_file_result(file_result)
                        if progress_callback:
                            status = "completed" if file_result.success else "failed"
                            progress_callback(file_path, status, 1.0)

                    # Check fail-fast
                    if not file_result.success and self.parallel_config.fail_fast:
                        self.logger.warning(f"Fail-fast triggered by {path.name}")
                        self._cancelled = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                except TimeoutError:
                    self.logger.error(f"Timeout processing file {path.name}")
                    file_result = FileSyncResult(
                        file_path=file_path,
                        file_name=path.name,
                        success=False,
                        errors=[
                            f"Processing timed out after {self.parallel_config.timeout_per_file}s"
                        ],
                    )
                    result.add_file_result(file_result)

                    if progress_callback:
                        progress_callback(file_path, "timeout", 1.0)

                except Exception as e:
                    self.logger.error(f"Error processing {path.name}: {e}")
                    file_result = FileSyncResult(
                        file_path=file_path,
                        file_name=path.name,
                        success=False,
                        errors=[str(e)],
                    )
                    result.add_file_result(file_result)

                    if progress_callback:
                        progress_callback(file_path, "error", 1.0)

    def _process_single_file(
        self,
        path: Path,
        epic_filter: list[str] | None,
        progress_callback: Callable[[str, str, float], None] | None,
    ) -> FileSyncResult:
        """
        Process a single file.

        Thread-safe wrapper around the sync logic.
        """
        from .multi_epic import MultiEpicSyncOrchestrator

        file_path = str(path)

        # Track worker
        with self._lock:
            if self._cancelled:
                return FileSyncResult(
                    file_path=file_path,
                    file_name=path.name,
                    success=False,
                    errors=["Processing cancelled"],
                )

            self._active_workers += 1
            self._peak_concurrency = max(self._peak_concurrency, self._active_workers)

            if file_path in self._progress_map:
                self._progress_map[file_path].status = "running"
                self._progress_map[file_path].started_at = datetime.now()

        try:
            result = FileSyncResult(
                file_path=file_path,
                file_name=path.name,
                dry_run=self.config.dry_run,
                started_at=datetime.now(),
            )

            if progress_callback:
                progress_callback(file_path, "parsing", 0.1)

            # Create multi-epic orchestrator for this file
            orchestrator = MultiEpicSyncOrchestrator(
                tracker=self.tracker,
                parser=self.parser,
                formatter=self.formatter,
                config=self.config,
                event_bus=self.event_bus,
            )

            if progress_callback:
                progress_callback(file_path, "syncing", 0.3)

            # Sync the file
            multi_result = orchestrator.sync(
                markdown_path=file_path,
                epic_filter=epic_filter,
            )

            if progress_callback:
                progress_callback(file_path, "completing", 0.9)

            # Transfer results
            result.epics_found = multi_result.epics_total
            result.epics_synced = multi_result.epics_synced
            result.epics_failed = multi_result.epics_failed
            result.stories_total = multi_result.total_stories
            result.stories_matched = multi_result.total_stories_matched
            result.stories_updated = multi_result.total_stories_updated
            result.subtasks_created = multi_result.total_subtasks_created
            result.epic_results = multi_result.epic_results
            result.errors.extend(multi_result.errors)
            result.warnings.extend(multi_result.warnings)
            result.success = multi_result.success

            # Update progress tracking
            with self._lock:
                if file_path in self._progress_map:
                    self._progress_map[file_path].epics_found = result.epics_found
                    self._progress_map[file_path].epics_synced = result.epics_synced
                    self._progress_map[file_path].stories_synced = result.stories_updated

        except Exception as e:
            result.add_error(f"Processing failed: {e!s}")
            self.logger.error(f"Error processing {path.name}: {e}")

            with self._lock:
                if file_path in self._progress_map:
                    self._progress_map[file_path].error = str(e)

        finally:
            with self._lock:
                self._active_workers -= 1

                if file_path in self._progress_map:
                    self._progress_map[file_path].status = (
                        "completed" if result.success else "failed"
                    )
                    self._progress_map[file_path].completed_at = datetime.now()
                    self._progress_map[file_path].progress = 1.0

            result.completed_at = datetime.now()

        return result

    def cancel(self) -> None:
        """Cancel ongoing parallel processing."""
        self._cancelled = True
        self.logger.info("Parallel file processing cancelled")

    def get_progress(self) -> dict[str, FileProgress]:
        """Get current progress for all files."""
        with self._lock:
            return dict(self._progress_map)

    def get_stats(self) -> dict[str, Any]:
        """Get current processing statistics."""
        with self._lock:
            return {
                "active_workers": self._active_workers,
                "peak_concurrency": self._peak_concurrency,
                "cancelled": self._cancelled,
                "files_in_progress": sum(
                    1 for p in self._progress_map.values() if p.status == "running"
                ),
                "files_completed": sum(
                    1 for p in self._progress_map.values() if p.status == "completed"
                ),
                "files_failed": sum(1 for p in self._progress_map.values() if p.status == "failed"),
            }


def create_parallel_file_processor(
    tracker: IssueTrackerPort,
    parser: DocumentParserPort,
    formatter: DocumentFormatterPort,
    config: "SyncConfig",
    max_workers: int = 4,
    fail_fast: bool = False,
) -> ParallelFileProcessor:
    """
    Factory function to create a parallel file processor.

    Args:
        tracker: Issue tracker port
        parser: Document parser port
        formatter: Document formatter port
        config: Sync configuration
        max_workers: Maximum concurrent workers
        fail_fast: Stop on first failure

    Returns:
        Configured ParallelFileProcessor
    """
    parallel_config = ParallelFilesConfig(
        max_workers=max_workers,
        fail_fast=fail_fast,
    )

    return ParallelFileProcessor(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config,
        parallel_config=parallel_config,
    )


def process_files_parallel(
    file_paths: list[str | Path],
    tracker: IssueTrackerPort,
    parser: DocumentParserPort,
    formatter: DocumentFormatterPort,
    config: "SyncConfig",
    max_workers: int = 4,
) -> ParallelFilesResult:
    """
    Convenience function to process multiple files in parallel.

    Args:
        file_paths: List of file paths to process.
        tracker: Issue tracker port
        parser: Document parser port
        formatter: Document formatter port
        config: Sync configuration
        max_workers: Maximum concurrent workers

    Returns:
        ParallelFilesResult with processing details.
    """
    processor = create_parallel_file_processor(
        tracker=tracker,
        parser=parser,
        formatter=formatter,
        config=config,
        max_workers=max_workers,
    )

    return processor.process(file_paths)
