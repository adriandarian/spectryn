"""
Smart 3-Way Merge - Intelligent merging for sync conflicts.

When both local (markdown) and remote (tracker) have changed since the last sync,
3-way merge can often automatically resolve the conflict by:
1. Comparing both versions against the common ancestor (base)
2. Identifying non-overlapping changes
3. Combining changes when possible
4. Flagging true conflicts when changes overlap

Supports merging:
- Text fields (description, comments) with line-level or word-level diff
- Status fields (with priority rules)
- Numeric fields (story points, with various strategies)
- List fields (subtasks, labels)
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from spectryn.application.sync.conflict import Conflict, ConflictResolution


logger = logging.getLogger(__name__)


class MergeResult(Enum):
    """Possible outcomes of a merge attempt."""

    SUCCESS = "success"  # Merge succeeded automatically
    PARTIAL = "partial"  # Some parts merged, conflicts remain
    CONFLICT = "conflict"  # Cannot merge, true conflict
    UNCHANGED = "unchanged"  # No changes needed


class MergeStrategy(Enum):
    """Strategies for different merge scenarios."""

    # Text merging
    LINE_LEVEL = "line_level"  # Merge at line level (default for descriptions)
    WORD_LEVEL = "word_level"  # Merge at word level (more aggressive)
    CHARACTER_LEVEL = "character_level"  # Merge at character level (most aggressive)

    # Numeric merging
    TAKE_HIGHER = "take_higher"  # Take higher value (e.g., story points)
    TAKE_LOWER = "take_lower"  # Take lower value
    TAKE_LOCAL = "take_local"  # Prefer local changes
    TAKE_REMOTE = "take_remote"  # Prefer remote changes
    SUM_CHANGES = "sum_changes"  # Sum the deltas from base

    # List merging
    UNION = "union"  # Combine all items from both
    INTERSECTION = "intersection"  # Only items in both
    LOCAL_PRIORITY = "local_priority"  # Local order, add remote additions


@dataclass
class MergeConfig:
    """Configuration for merge behavior."""

    # Text merge settings
    text_strategy: MergeStrategy = MergeStrategy.LINE_LEVEL
    preserve_formatting: bool = True
    conflict_markers: bool = True  # Add <<<< ==== >>>> markers

    # Numeric merge settings
    numeric_strategy: MergeStrategy = MergeStrategy.TAKE_HIGHER

    # List merge settings
    list_strategy: MergeStrategy = MergeStrategy.UNION

    # Status merge settings
    status_priority: list[str] = field(
        default_factory=lambda: ["done", "in_progress", "blocked", "planned", "open"]
    )

    # General settings
    auto_merge_threshold: float = 0.8  # Similarity threshold for auto-merge


@dataclass
class MergeAttempt:
    """Result of a merge attempt."""

    result: MergeResult
    merged_value: Any | None = None
    conflict_regions: list[tuple[int, int, str, str]] = field(default_factory=list)
    changes_from_local: int = 0
    changes_from_remote: int = 0
    message: str = ""

    @property
    def success(self) -> bool:
        return self.result in (MergeResult.SUCCESS, MergeResult.UNCHANGED)


class ThreeWayMerger:
    """
    Implements 3-way merge algorithm for conflict resolution.

    Uses the common ancestor (base) to determine what changed on each side,
    then intelligently combines changes when possible.
    """

    def __init__(self, config: MergeConfig | None = None):
        """
        Initialize the merger.

        Args:
            config: Merge configuration. Uses defaults if not provided.
        """
        self.config = config or MergeConfig()
        self.logger = logging.getLogger("ThreeWayMerger")

    def merge(
        self,
        base: Any,
        local: Any,
        remote: Any,
        field_type: str = "text",
    ) -> MergeAttempt:
        """
        Attempt a 3-way merge.

        Args:
            base: The common ancestor value (last sync state).
            local: The current local (markdown) value.
            remote: The current remote (tracker) value.
            field_type: Type of field being merged (text, status, numeric, list).

        Returns:
            MergeAttempt with result and merged value if successful.
        """
        # Check for simple cases first
        if base == local == remote:
            return MergeAttempt(
                result=MergeResult.UNCHANGED, merged_value=base, message="All values identical"
            )

        if local == remote:
            return MergeAttempt(
                result=MergeResult.UNCHANGED,
                merged_value=local,
                message="Local and remote are identical",
            )

        if base == local:
            # Only remote changed
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=remote,
                changes_from_remote=1,
                message="Only remote changed",
            )

        if base == remote:
            # Only local changed
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=local,
                changes_from_local=1,
                message="Only local changed",
            )

        # Both changed - need to merge based on field type
        if field_type == "text":
            return self._merge_text(base, local, remote)
        if field_type == "status":
            return self._merge_status(base, local, remote)
        if field_type == "numeric":
            return self._merge_numeric(base, local, remote)
        if field_type == "list":
            return self._merge_list(base, local, remote)

        # Default: cannot merge
        return MergeAttempt(
            result=MergeResult.CONFLICT,
            message=f"Unknown field type: {field_type}",
        )

    def _merge_text(self, base: str | None, local: str | None, remote: str | None) -> MergeAttempt:
        """
        Merge text fields using diff3 algorithm.

        Uses line-level or word-level merging depending on config.
        """
        base_str = str(base) if base else ""
        local_str = str(local) if local else ""
        remote_str = str(remote) if remote else ""

        if self.config.text_strategy == MergeStrategy.LINE_LEVEL:
            return self._merge_text_by_lines(base_str, local_str, remote_str)
        if self.config.text_strategy == MergeStrategy.WORD_LEVEL:
            return self._merge_text_by_words(base_str, local_str, remote_str)

        return self._merge_text_by_lines(base_str, local_str, remote_str)

    def _merge_text_by_lines(self, base: str, local: str, remote: str) -> MergeAttempt:
        """Line-level text merge using diff3-like algorithm."""
        base_lines = base.splitlines(keepends=True)
        local_lines = local.splitlines(keepends=True)
        remote_lines = remote.splitlines(keepends=True)

        # Use SequenceMatcher to find overlapping changes
        matcher_local = difflib.SequenceMatcher(None, base_lines, local_lines)
        matcher_remote = difflib.SequenceMatcher(None, base_lines, remote_lines)

        local_changes = self._get_change_ranges(matcher_local)
        remote_changes = self._get_change_ranges(matcher_remote)

        # Check for overlapping changes
        overlaps = self._find_overlapping_ranges(local_changes, remote_changes)

        if not overlaps:
            # No overlapping changes - can merge automatically
            merged = self._apply_non_overlapping_changes(
                base_lines, local_lines, remote_lines, local_changes, remote_changes
            )
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value="".join(merged),
                changes_from_local=len(local_changes),
                changes_from_remote=len(remote_changes),
                message=f"Merged {len(local_changes)} local + {len(remote_changes)} remote changes",
            )

        # Has overlapping changes - check if they're identical
        identical_overlaps = self._check_identical_overlaps(
            base_lines, local_lines, remote_lines, overlaps
        )

        if identical_overlaps:
            # Same change on both sides - can merge
            merged = self._apply_non_overlapping_changes(
                base_lines, local_lines, remote_lines, local_changes, remote_changes
            )
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value="".join(merged),
                changes_from_local=len(local_changes),
                changes_from_remote=len(remote_changes),
                message="Both sides made identical changes",
            )

        # True conflict - add conflict markers if configured
        if self.config.conflict_markers:
            merged = self._merge_with_conflict_markers(
                base_lines, local_lines, remote_lines, overlaps
            )
            return MergeAttempt(
                result=MergeResult.PARTIAL,
                merged_value="".join(merged),
                conflict_regions=[(o[0], o[1], "local", "remote") for o in overlaps],
                changes_from_local=len(local_changes),
                changes_from_remote=len(remote_changes),
                message=f"Merged with {len(overlaps)} conflict marker(s)",
            )

        return MergeAttempt(
            result=MergeResult.CONFLICT,
            conflict_regions=[(o[0], o[1], "local", "remote") for o in overlaps],
            message=f"{len(overlaps)} overlapping change(s) cannot be merged",
        )

    def _merge_text_by_words(self, base: str, local: str, remote: str) -> MergeAttempt:
        """Word-level text merge."""
        base_words = base.split()
        local_words = local.split()
        remote_words = remote.split()

        # Use SequenceMatcher for word-level diff
        matcher_local = difflib.SequenceMatcher(None, base_words, local_words)
        matcher_remote = difflib.SequenceMatcher(None, base_words, remote_words)

        local_changes = self._get_change_ranges(matcher_local)
        remote_changes = self._get_change_ranges(matcher_remote)

        overlaps = self._find_overlapping_ranges(local_changes, remote_changes)

        if not overlaps:
            # No overlapping changes
            merged_words = self._apply_non_overlapping_changes(
                base_words, local_words, remote_words, local_changes, remote_changes
            )
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=" ".join(merged_words),
                changes_from_local=len(local_changes),
                changes_from_remote=len(remote_changes),
                message=f"Word-level merge: {len(local_changes)} local + {len(remote_changes)} remote",
            )

        return MergeAttempt(
            result=MergeResult.CONFLICT,
            conflict_regions=overlaps,
            message=f"{len(overlaps)} word-level conflict(s)",
        )

    def _merge_status(self, base: Any, local: Any, remote: Any) -> MergeAttempt:
        """
        Merge status fields using priority rules.

        Generally, the "more advanced" status wins (e.g., done > in_progress > planned).
        """
        local_str = str(local).lower() if local else ""
        remote_str = str(remote).lower() if remote else ""

        # Get priority indices
        priority = self.config.status_priority
        local_idx = priority.index(local_str) if local_str in priority else len(priority)
        remote_idx = priority.index(remote_str) if remote_str in priority else len(priority)

        # Lower index = higher priority (more advanced status)
        if local_idx < remote_idx:
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=local,
                changes_from_local=1,
                message=f"Status: local '{local}' wins (higher priority)",
            )
        if remote_idx < local_idx:
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=remote,
                changes_from_remote=1,
                message=f"Status: remote '{remote}' wins (higher priority)",
            )

        # Same priority - conflict
        return MergeAttempt(
            result=MergeResult.CONFLICT,
            message=f"Status conflict: '{local}' vs '{remote}' (same priority)",
        )

    def _merge_numeric(self, base: Any, local: Any, remote: Any) -> MergeAttempt:
        """
        Merge numeric fields (e.g., story points).

        Uses the configured strategy (take_higher, sum_changes, etc.)
        """
        try:
            base_num = float(base) if base is not None else 0
            local_num = float(local) if local is not None else 0
            remote_num = float(remote) if remote is not None else 0
        except (ValueError, TypeError):
            return MergeAttempt(
                result=MergeResult.CONFLICT,
                message="Cannot convert values to numbers",
            )

        if self.config.numeric_strategy == MergeStrategy.TAKE_HIGHER:
            merged = max(local_num, remote_num)
            winner = "local" if local_num >= remote_num else "remote"
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=int(merged) if merged == int(merged) else merged,
                changes_from_local=1 if winner == "local" else 0,
                changes_from_remote=1 if winner == "remote" else 0,
                message=f"Took higher value: {merged} ({winner})",
            )

        if self.config.numeric_strategy == MergeStrategy.TAKE_LOWER:
            merged = min(local_num, remote_num)
            winner = "local" if local_num <= remote_num else "remote"
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=int(merged) if merged == int(merged) else merged,
                changes_from_local=1 if winner == "local" else 0,
                changes_from_remote=1 if winner == "remote" else 0,
                message=f"Took lower value: {merged} ({winner})",
            )

        if self.config.numeric_strategy == MergeStrategy.SUM_CHANGES:
            # Apply both deltas: merged = base + (local - base) + (remote - base)
            # Simplified: merged = local + remote - base
            merged = local_num + remote_num - base_num
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=int(merged) if merged == int(merged) else merged,
                changes_from_local=1,
                changes_from_remote=1,
                message=f"Sum of changes: {merged}",
            )

        # Default: take local
        return MergeAttempt(
            result=MergeResult.SUCCESS,
            merged_value=local,
            changes_from_local=1,
            message="Took local value (default)",
        )

    def _merge_list(self, base: Any, local: Any, remote: Any) -> MergeAttempt:
        """
        Merge list fields (e.g., subtasks, labels).

        Uses union, intersection, or priority-based merging.
        """
        base_list = list(base) if base else []
        local_list = list(local) if local else []
        remote_list = list(remote) if remote else []

        if self.config.list_strategy == MergeStrategy.UNION:
            # Combine all items, preserving local order
            merged = list(local_list)
            for item in remote_list:
                if item not in merged:
                    merged.append(item)
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=merged,
                changes_from_local=len(set(local_list) - set(base_list)),
                changes_from_remote=len(set(remote_list) - set(base_list)),
                message=f"Union merge: {len(merged)} items",
            )

        if self.config.list_strategy == MergeStrategy.INTERSECTION:
            merged = [item for item in local_list if item in remote_list]
            return MergeAttempt(
                result=MergeResult.SUCCESS,
                merged_value=merged,
                message=f"Intersection merge: {len(merged)} items",
            )

        # LOCAL_PRIORITY: Keep local list, add remote additions
        added_in_remote = [item for item in remote_list if item not in base_list]
        merged = list(local_list)
        for item in added_in_remote:
            if item not in merged:
                merged.append(item)
        return MergeAttempt(
            result=MergeResult.SUCCESS,
            merged_value=merged,
            changes_from_local=len(set(local_list) - set(base_list)),
            changes_from_remote=len(added_in_remote),
            message=f"Local priority merge: {len(merged)} items",
        )

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _get_change_ranges(self, matcher: difflib.SequenceMatcher) -> list[tuple[int, int]]:
        """Get ranges of changes from a SequenceMatcher."""
        ranges = []
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
            if tag in ("replace", "insert", "delete"):
                ranges.append((i1, i2))
        return ranges

    def _find_overlapping_ranges(
        self, ranges1: list[tuple[int, int]], ranges2: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Find overlapping ranges between two lists of ranges."""
        overlaps = []
        for r1 in ranges1:
            for r2 in ranges2:
                if r1[0] < r2[1] and r2[0] < r1[1]:
                    # Ranges overlap
                    overlaps.append((max(r1[0], r2[0]), min(r1[1], r2[1])))
        return overlaps

    def _apply_non_overlapping_changes(
        self,
        base: list,
        local: list,
        remote: list,
        local_changes: list[tuple[int, int]],
        remote_changes: list[tuple[int, int]],
    ) -> list:
        """Apply non-overlapping changes from both sides."""
        # Start with base
        result = list(base)

        # Apply changes in reverse order (to preserve indices)
        all_changes = []

        # Get what changed in local
        matcher = difflib.SequenceMatcher(None, base, local)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                all_changes.append((i1, i2, local[j1:j2], "local"))
            elif tag == "delete":
                all_changes.append((i1, i2, [], "local"))

        # Get what changed in remote
        matcher = difflib.SequenceMatcher(None, base, remote)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                all_changes.append((i1, i2, remote[j1:j2], "remote"))
            elif tag == "delete":
                all_changes.append((i1, i2, [], "remote"))

        # Sort by position (reverse) and apply
        all_changes.sort(key=lambda x: x[0], reverse=True)

        # Track which ranges we've modified
        modified_ranges: list[tuple[int, int]] = []
        for i1, i2, new_content, _source in all_changes:
            # Check if this range overlaps with already modified range
            overlaps = False
            for mr in modified_ranges:
                if i1 < mr[1] and mr[0] < i2:
                    overlaps = True
                    break

            if not overlaps:
                result[i1:i2] = new_content
                modified_ranges.append((i1, i2))

        return result

    def _check_identical_overlaps(
        self,
        base: list,
        local: list,
        remote: list,
        overlaps: list[tuple[int, int]],
    ) -> bool:
        """Check if overlapping changes are identical."""
        for start, end in overlaps:
            # Get the content at this range in each version
            # This is a simplified check - could be more sophisticated
            local_content = local[start:end] if start < len(local) else []
            remote_content = remote[start:end] if start < len(remote) else []
            if local_content != remote_content:
                return False
        return True

    def _merge_with_conflict_markers(
        self,
        base: list,
        local: list,
        remote: list,
        overlaps: list[tuple[int, int]],
    ) -> list:
        """Add Git-style conflict markers for overlapping changes."""
        result = []
        current_pos = 0

        for start, end in sorted(overlaps):
            # Add content before this overlap
            result.extend(base[current_pos:start])

            # Add conflict markers
            result.append("<<<<<<< LOCAL\n")
            if start < len(local):
                result.extend(local[start : min(end, len(local))])
            result.append("=======\n")
            if start < len(remote):
                result.extend(remote[start : min(end, len(remote))])
            result.append(">>>>>>> REMOTE\n")

            current_pos = end

        # Add remaining content
        result.extend(base[current_pos:])

        return result


def resolve_conflict_with_merge(
    conflict: Conflict,
    config: MergeConfig | None = None,
) -> ConflictResolution:
    """
    Attempt to resolve a conflict using 3-way merge.

    Args:
        conflict: The conflict to resolve.
        config: Optional merge configuration.

    Returns:
        ConflictResolution with merged result if successful.
    """
    merger = ThreeWayMerger(config)

    # Determine field type
    field_type = "text"
    if conflict.field in ("status",):
        field_type = "status"
    elif conflict.field in ("story_points", "priority"):
        field_type = "numeric"
    elif conflict.field in ("subtasks", "labels", "tags"):
        field_type = "list"

    attempt = merger.merge(
        base=conflict.base_value,
        local=conflict.local_value,
        remote=conflict.remote_value,
        field_type=field_type,
    )

    if attempt.success:
        return ConflictResolution(
            conflict=conflict,
            resolution="merge",
            merged_value=attempt.merged_value,
        )

    # Merge failed - return as unresolved
    return ConflictResolution(
        conflict=conflict,
        resolution="conflict",
        merged_value=None,
    )


class SmartMergeResolver:
    """
    A conflict resolver that uses 3-way merge as first strategy.

    Falls back to other strategies when merge fails.
    """

    def __init__(
        self,
        merge_config: MergeConfig | None = None,
        fallback_strategy: str = "ask",
        prompt_func: Any | None = None,
    ):
        """
        Initialize the smart merge resolver.

        Args:
            merge_config: Configuration for the merger.
            fallback_strategy: What to do when merge fails ("ask", "local", "remote", "skip").
            prompt_func: Function to prompt user for resolution.
        """
        self.merger = ThreeWayMerger(merge_config)
        self.fallback_strategy = fallback_strategy
        self.prompt_func = prompt_func
        self.logger = logging.getLogger("SmartMergeResolver")

    def resolve(self, conflict: Conflict) -> ConflictResolution:
        """
        Resolve a conflict, trying merge first.

        Args:
            conflict: The conflict to resolve.

        Returns:
            ConflictResolution with result.
        """
        # Determine field type
        field_type = self._get_field_type(conflict.field)

        # Attempt merge
        attempt = self.merger.merge(
            base=conflict.base_value,
            local=conflict.local_value,
            remote=conflict.remote_value,
            field_type=field_type,
        )

        if attempt.success:
            self.logger.info(f"Auto-merged {conflict.field}: {attempt.message}")
            return ConflictResolution(
                conflict=conflict,
                resolution="merge",
                merged_value=attempt.merged_value,
            )

        if attempt.result == MergeResult.PARTIAL:
            self.logger.warning(f"Partial merge for {conflict.field}: {attempt.message}")
            return ConflictResolution(
                conflict=conflict,
                resolution="merge",
                merged_value=attempt.merged_value,
            )

        # Merge failed - use fallback
        self.logger.info(f"Merge failed for {conflict.field}: {attempt.message}")
        return self._apply_fallback(conflict)

    def _get_field_type(self, field: str) -> str:
        """Get the field type for merge strategy."""
        if field in ("description", "title", "comment", "notes"):
            return "text"
        if field in ("status", "state", "workflow"):
            return "status"
        if field in ("story_points", "estimate", "priority", "points"):
            return "numeric"
        if field in ("subtasks", "labels", "tags", "components", "watchers"):
            return "list"
        return "text"

    def _apply_fallback(self, conflict: Conflict) -> ConflictResolution:
        """Apply fallback strategy when merge fails."""
        if self.fallback_strategy == "local":
            return ConflictResolution(conflict=conflict, resolution="local")
        if self.fallback_strategy == "remote":
            return ConflictResolution(conflict=conflict, resolution="remote")
        if self.fallback_strategy == "skip":
            return ConflictResolution(conflict=conflict, resolution="skip")
        if self.fallback_strategy == "ask" and self.prompt_func:
            choice = self.prompt_func(conflict)
            return ConflictResolution(conflict=conflict, resolution=choice)

        # Default to skip
        return ConflictResolution(conflict=conflict, resolution="skip")
