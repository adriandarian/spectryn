"""
Snapshot command handlers.

This module contains handlers for snapshot-related commands:
- run_list_snapshots: List all stored sync snapshots
- run_clear_snapshot: Clear the sync snapshot for an epic
"""

from spectryn.cli.exit_codes import ExitCode


__all__ = [
    "run_clear_snapshot",
    "run_list_snapshots",
]


def run_list_snapshots() -> int:
    """
    List all stored sync snapshots.

    Returns:
        Exit code.
    """
    from spectryn.application.sync import SnapshotStore

    store = SnapshotStore()
    snapshots = store.list_snapshots()

    if not snapshots:
        print("No sync snapshots found.")
        print(f"Snapshot directory: {store.snapshot_dir}")
        return ExitCode.SUCCESS

    print(f"\n{'Epic':<15} {'Stories':<10} {'Created':<25}")
    print("-" * 52)

    for s in snapshots:
        epic = s.get("epic_key", "")[:13]
        stories = str(s.get("story_count", 0))
        created = s.get("created_at", "")[:24]
        print(f"{epic:<15} {stories:<10} {created:<25}")

    print()
    print(f"Total snapshots: {len(snapshots)}")
    print(f"Snapshot directory: {store.snapshot_dir}")
    print()
    print("Use --clear-snapshot --epic EPIC-KEY to reset conflict baseline")

    return ExitCode.SUCCESS


def run_clear_snapshot(epic_key: str) -> int:
    """
    Clear the sync snapshot for an epic.

    Args:
        epic_key: The epic key.

    Returns:
        Exit code.
    """
    from spectryn.application.sync import SnapshotStore

    store = SnapshotStore()

    if store.delete(epic_key):
        print(f"✓ Cleared snapshot for {epic_key}")
        print("  Next sync will not detect conflicts (fresh baseline)")
        return ExitCode.SUCCESS
    print(f"No snapshot found for {epic_key}")
    return ExitCode.FILE_NOT_FOUND
