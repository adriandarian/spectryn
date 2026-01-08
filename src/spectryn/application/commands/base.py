"""
Base Command - Abstract base class for all commands.

Commands follow the Command pattern for:
- Encapsulating operations
- Supporting undo/redo
- Enabling logging and audit trails
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

from spectryn.core.domain.events import DomainEvent, EventBus
from spectryn.core.ports.issue_tracker import IssueTrackerPort


T = TypeVar("T")


@dataclass
class CommandResult(Generic[T]):
    """Result of command execution."""

    success: bool
    data: T | None = None
    error: str | None = None
    skipped: bool = False
    dry_run: bool = False

    # For undo support
    undo_data: Any | None = None

    @classmethod
    def ok(cls, data: T | None = None, dry_run: bool = False) -> "CommandResult[T]":
        """Create successful result."""
        return cls(success=True, data=data, dry_run=dry_run)

    @classmethod
    def fail(cls, error: str) -> "CommandResult[T]":
        """Create failed result."""
        return cls(success=False, error=error)

    @classmethod
    def skip(cls, reason: str = "") -> "CommandResult[T]":
        """Create skipped result."""
        return cls(success=True, skipped=True, error=reason)


class Command(ABC):
    """
    Abstract base class for all commands.

    Commands encapsulate a single operation that can be:
    - Validated before execution
    - Executed
    - Undone (if supported)
    - Logged for audit
    """

    def __init__(
        self,
        tracker: IssueTrackerPort,
        event_bus: EventBus | None = None,
        dry_run: bool = True,
    ) -> None:
        """
        Initialize command.

        Args:
            tracker: Issue tracker port
            event_bus: Optional event bus for publishing events
            dry_run: If True, don't make actual changes
        """
        self.tracker = tracker
        self.event_bus = event_bus
        self.dry_run = dry_run
        self.executed_at: datetime | None = None
        self._undo_data: Any | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable command name."""
        ...

    @property
    def supports_undo(self) -> bool:
        """Check if this command supports undo."""
        return False

    def validate(self) -> str | None:
        """
        Validate command before execution.

        Returns:
            Error message if invalid, None if valid
        """
        return None

    @abstractmethod
    def execute(self) -> CommandResult:
        """
        Execute the command.

        Returns:
            CommandResult with success status and data
        """
        ...

    def undo(self) -> CommandResult | None:
        """
        Undo the command (if supported).

        Returns:
            CommandResult, or None if undo not supported
        """
        return None

    def _publish_event(self, event: DomainEvent) -> None:
        """Publish an event if event bus is available."""
        if self.event_bus:
            self.event_bus.publish(event)


@dataclass
class CommandBatch:
    """A batch of commands to execute together."""

    commands: list[Command] = field(default_factory=list)
    stop_on_error: bool = True
    results: list[CommandResult] = field(default_factory=list)

    def add(self, command: Command) -> "CommandBatch":
        """Add a command to the batch."""
        self.commands.append(command)
        return self

    def execute_all(self) -> list[CommandResult]:
        """Execute all commands in order."""
        self.results = []

        for command in self.commands:
            result = command.execute()
            self.results.append(result)

            if not result.success and self.stop_on_error:
                break

        return self.results

    @property
    def all_succeeded(self) -> bool:
        """Check if all commands succeeded."""
        return all(r.success for r in self.results)

    @property
    def executed_count(self) -> int:
        """Count of successfully executed commands."""
        return sum(1 for r in self.results if r.success and not r.skipped)

    @property
    def skipped_count(self) -> int:
        """Count of skipped commands."""
        return sum(1 for r in self.results if r.skipped)

    @property
    def failed_count(self) -> int:
        """Count of failed commands."""
        return sum(1 for r in self.results if not r.success)
