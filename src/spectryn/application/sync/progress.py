"""
Progress reporting for sync operations.

Provides granular progress tracking at both phase and item level.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SyncPhase(Enum):
    """Phases of the sync operation."""

    BACKUP = "backup"
    ANALYZING = "analyzing"
    DESCRIPTIONS = "descriptions"
    SUBTASKS = "subtasks"
    COMMENTS = "comments"
    STATUSES = "statuses"
    SOURCE_UPDATE = "source_update"
    COMPLETE = "complete"

    @property
    def display_name(self) -> str:
        """Get display name for the phase."""
        names = {
            SyncPhase.BACKUP: "Creating backup",
            SyncPhase.ANALYZING: "Analyzing",
            SyncPhase.DESCRIPTIONS: "Updating descriptions",
            SyncPhase.SUBTASKS: "Syncing subtasks",
            SyncPhase.COMMENTS: "Adding comments",
            SyncPhase.STATUSES: "Syncing statuses",
            SyncPhase.SOURCE_UPDATE: "Updating source",
            SyncPhase.COMPLETE: "Complete",
        }
        return names.get(self, self.value)


@dataclass
class ProgressState:
    """Current state of sync progress."""

    # Phase-level progress
    phase: SyncPhase = SyncPhase.ANALYZING
    phase_index: int = 0
    total_phases: int = 5

    # Item-level progress within current phase
    current_item: int = 0
    total_items: int = 0
    item_name: str = ""

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    phase_start_time: datetime = field(default_factory=datetime.now)

    @property
    def phase_progress(self) -> float:
        """Get overall phase progress (0-100)."""
        if self.total_phases == 0:
            return 0.0
        return (self.phase_index / self.total_phases) * 100

    @property
    def item_progress(self) -> float:
        """Get progress within current phase (0-100)."""
        if self.total_items == 0:
            return 0.0
        return (self.current_item / self.total_items) * 100

    @property
    def overall_progress(self) -> float:
        """
        Get combined overall progress (0-100).

        Each phase contributes equally, with item progress within the phase.
        """
        if self.total_phases == 0:
            return 0.0

        phase_weight = 100.0 / self.total_phases
        completed_phases = self.phase_index * phase_weight

        # Add partial progress from current phase
        if self.total_items > 0:
            current_phase_progress = (self.current_item / self.total_items) * phase_weight
        else:
            current_phase_progress = 0

        return min(completed_phases + current_phase_progress, 100.0)

    @property
    def elapsed_seconds(self) -> float:
        """Get total elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def phase_elapsed_seconds(self) -> float:
        """Get elapsed time for current phase in seconds."""
        return (datetime.now() - self.phase_start_time).total_seconds()


# Callback type for progress updates
# Args: phase_name, current_item_name, overall_progress (0-100), items_in_phase (current/total)
ProgressCallback = Callable[[str, str, float, int, int], None]

# Legacy callback for backwards compatibility
LegacyProgressCallback = Callable[[str, int, int], None]


class ProgressReporter:
    """
    Reports progress during sync operations.

    Provides both phase-level and item-level progress tracking.
    Supports both new-style and legacy callbacks for backwards compatibility.
    """

    def __init__(
        self,
        callback: ProgressCallback | None = None,
        legacy_callback: LegacyProgressCallback | None = None,
        total_phases: int = 5,
    ) -> None:
        """
        Initialize the progress reporter.

        Args:
            callback: New-style callback with item-level progress.
            legacy_callback: Legacy callback (phase, current, total).
            total_phases: Total number of sync phases.
        """
        self._callback = callback
        self._legacy_callback = legacy_callback
        self._state = ProgressState(total_phases=total_phases)

    @property
    def state(self) -> ProgressState:
        """Get current progress state."""
        return self._state

    def start_phase(self, phase: SyncPhase, total_items: int = 0) -> None:
        """
        Start a new phase.

        Args:
            phase: The phase starting.
            total_items: Total items to process in this phase (0 if unknown).
        """
        self._state.phase = phase
        self._state.phase_index = self._get_phase_index(phase)
        self._state.total_items = total_items
        self._state.current_item = 0
        self._state.item_name = ""
        self._state.phase_start_time = datetime.now()

        self._report()

    def update_item(self, item_name: str = "", increment: bool = True) -> None:
        """
        Update progress for current item.

        Args:
            item_name: Name of the current item being processed.
            increment: Whether to increment the item counter.
        """
        if increment:
            self._state.current_item += 1
        self._state.item_name = item_name

        self._report()

    def set_total_items(self, total: int) -> None:
        """Set total items for current phase."""
        self._state.total_items = total

    def complete(self) -> None:
        """Mark sync as complete."""
        self._state.phase = SyncPhase.COMPLETE
        self._state.phase_index = self._state.total_phases
        self._state.current_item = self._state.total_items
        self._state.item_name = ""

        self._report()

    def _get_phase_index(self, phase: SyncPhase) -> int:
        """Get numeric index for a phase."""
        phase_order = [
            SyncPhase.BACKUP,
            SyncPhase.ANALYZING,
            SyncPhase.DESCRIPTIONS,
            SyncPhase.SUBTASKS,
            SyncPhase.COMMENTS,
            SyncPhase.STATUSES,
            SyncPhase.SOURCE_UPDATE,
            SyncPhase.COMPLETE,
        ]
        try:
            return phase_order.index(phase)
        except ValueError:
            return 0

    def _report(self) -> None:
        """Report progress via callbacks."""
        # Call new-style callback
        if self._callback:
            self._callback(
                self._state.phase.display_name,
                self._state.item_name,
                self._state.overall_progress,
                self._state.current_item,
                self._state.total_items,
            )

        # Call legacy callback for backwards compatibility
        if self._legacy_callback:
            self._legacy_callback(
                self._state.phase.display_name,
                self._state.phase_index,
                self._state.total_phases,
            )


def create_progress_reporter(
    callback: ProgressCallback | LegacyProgressCallback | None = None,
    total_phases: int = 5,
) -> ProgressReporter | None:
    """
    Create a progress reporter from a callback.

    Automatically detects legacy vs new-style callbacks based on signature.

    Args:
        callback: Progress callback (either style).
        total_phases: Total phases in sync.

    Returns:
        ProgressReporter instance or None if no callback.
    """
    if callback is None:
        return None

    # Check callback signature to determine type
    import inspect

    sig = inspect.signature(callback)
    param_count = len(sig.parameters)

    if param_count == 3:
        # Legacy callback: (phase, current, total)
        return ProgressReporter(legacy_callback=callback, total_phases=total_phases)
    if param_count >= 5:
        # New-style callback: (phase, item, progress, current, total)
        return ProgressReporter(callback=callback, total_phases=total_phases)
    # Assume legacy for unknown
    return ProgressReporter(legacy_callback=callback, total_phases=total_phases)
