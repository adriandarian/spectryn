"""
Hook System - Pre/post processing hooks for extensibility.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class HookPoint(Enum):
    """
    Points where hooks can be attached in the sync lifecycle.

    Hook points are organized by phase:
    - Parsing: Before/after parsing markdown documents
    - Matching: Before/after matching stories to issues
    - Sync operations: Before/after the overall sync
    - Individual operations: Before/after specific API calls
    - Error handling: When errors occur

    Attributes:
        BEFORE_PARSE: Before parsing a markdown document.
        AFTER_PARSE: After parsing completes successfully.
        BEFORE_MATCH: Before matching markdown stories to tracker issues.
        AFTER_MATCH: After matching completes.
        ON_MATCH_FAILURE: When a story cannot be matched.
        BEFORE_SYNC: Before the sync operation starts.
        AFTER_SYNC: After the sync operation completes.
        BEFORE_UPDATE_DESCRIPTION: Before updating an issue description.
        AFTER_UPDATE_DESCRIPTION: After updating an issue description.
        BEFORE_CREATE_SUBTASK: Before creating a subtask.
        AFTER_CREATE_SUBTASK: After creating a subtask.
        BEFORE_ADD_COMMENT: Before adding a comment.
        AFTER_ADD_COMMENT: After adding a comment.
        BEFORE_TRANSITION: Before transitioning issue status.
        AFTER_TRANSITION: After transitioning issue status.
        ON_ERROR: When an error occurs during processing.
    """

    # Parsing
    BEFORE_PARSE = auto()
    AFTER_PARSE = auto()

    # Matching
    BEFORE_MATCH = auto()
    AFTER_MATCH = auto()
    ON_MATCH_FAILURE = auto()

    # Sync operations
    BEFORE_SYNC = auto()
    AFTER_SYNC = auto()

    # Individual operations
    BEFORE_UPDATE_DESCRIPTION = auto()
    AFTER_UPDATE_DESCRIPTION = auto()

    BEFORE_CREATE_SUBTASK = auto()
    AFTER_CREATE_SUBTASK = auto()

    BEFORE_ADD_COMMENT = auto()
    AFTER_ADD_COMMENT = auto()

    BEFORE_TRANSITION = auto()
    AFTER_TRANSITION = auto()

    # Error handling
    ON_ERROR = auto()


@dataclass
class HookContext:
    """
    Context passed to hook handlers.

    Provides access to hook data and allows hooks to modify behavior
    by cancelling operations or overriding results.

    Attributes:
        hook_point: The hook point that triggered this context.
        data: Dictionary of data relevant to the hook point.
        result: Result from the operation (set by post-hooks).
        error: Exception if an error occurred.
        cancelled: Whether the operation was cancelled by a hook.
    """

    hook_point: HookPoint
    data: dict = field(default_factory=dict)
    result: Any = None
    error: Exception | None = None
    cancelled: bool = False

    def cancel(self) -> None:
        """
        Cancel the current operation.

        When called, the operation associated with this hook point will be skipped.
        """
        self.cancelled = True

    def set_result(self, result: Any) -> None:
        """
        Override the operation result.

        Args:
            result: The new result to use instead of the default.
        """
        self.result = result


class Hook:
    """
    A hook that can be attached to a hook point.

    Hooks are called in priority order (lower = earlier).

    Attributes:
        name: Unique name identifying this hook.
        hook_point: The hook point this hook is attached to.
        handler: Callable that receives HookContext.
        priority: Execution order (lower = earlier, default 100).
    """

    def __init__(
        self,
        name: str,
        hook_point: HookPoint,
        handler: Callable[[HookContext], None],
        priority: int = 100,
    ):
        """
        Initialize a hook.

        Args:
            name: Unique name for this hook.
            hook_point: Hook point to attach to.
            handler: Function to call when hook is triggered.
            priority: Execution order (lower = earlier).
        """
        self.name = name
        self.hook_point = hook_point
        self.handler = handler
        self.priority = priority

    def __call__(self, context: HookContext) -> None:
        """
        Execute the hook handler.

        Args:
            context: Hook context with data and control methods.
        """
        self.handler(context)

    def __lt__(self, other: "Hook") -> bool:
        """
        Compare by priority for sorting.

        Args:
            other: Another Hook to compare with.

        Returns:
            True if this hook has lower priority (should run first).
        """
        return self.priority < other.priority


class HookManager:
    """
    Manages hooks and their execution.

    Usage:
        manager = HookManager()

        @manager.hook(HookPoint.BEFORE_SYNC)
        def my_hook(ctx):
            print("Before sync!")

        # Or register manually
        manager.register(Hook("my_hook", HookPoint.BEFORE_SYNC, my_handler))

        # Trigger hooks
        manager.trigger(HookPoint.BEFORE_SYNC, {"epic_key": "PROJ-123"})
    """

    def __init__(self) -> None:
        """Initialize the hook manager with empty hook lists for all hook points."""
        self._hooks: dict[HookPoint, list[Hook]] = {hp: [] for hp in HookPoint}
        self.logger = logging.getLogger("HookManager")

    def register(self, hook: Hook) -> None:
        """
        Register a hook at its designated hook point.

        Hooks are automatically sorted by priority after registration.

        Args:
            hook: The Hook instance to register.
        """
        self._hooks[hook.hook_point].append(hook)
        self._hooks[hook.hook_point].sort()  # Sort by priority
        self.logger.debug(f"Registered hook: {hook.name} at {hook.hook_point.name}")

    def unregister(self, hook_name: str) -> bool:
        """
        Unregister a hook by its name.

        Searches all hook points for a hook with the given name.

        Args:
            hook_name: Name of the hook to remove.

        Returns:
            True if the hook was found and removed, False otherwise.
        """
        for hook_point in HookPoint:
            for hook in self._hooks[hook_point]:
                if hook.name == hook_name:
                    self._hooks[hook_point].remove(hook)
                    return True
        return False

    def trigger(
        self,
        hook_point: HookPoint,
        data: dict | None = None,
    ) -> HookContext:
        """
        Trigger all hooks at a hook point.

        Args:
            hook_point: The hook point to trigger
            data: Data to pass to hooks

        Returns:
            HookContext with results
        """
        context = HookContext(
            hook_point=hook_point,
            data=data or {},
        )

        for hook in self._hooks[hook_point]:
            try:
                hook(context)

                if context.cancelled:
                    self.logger.info(f"Operation cancelled by hook: {hook.name}")
                    break

            except Exception as e:
                self.logger.error(f"Hook {hook.name} failed: {e}")
                context.error = e

        return context

    def hook(
        self,
        hook_point: HookPoint,
        priority: int = 100,
        name: str | None = None,
    ) -> Callable[[Callable[[HookContext], None]], Callable[[HookContext], None]]:
        """
        Decorator to register a hook.

        Usage:
            @manager.hook(HookPoint.BEFORE_SYNC)
            def my_hook(ctx):
                print("Before sync!")
        """

        def decorator(func: Callable[[HookContext], None]) -> Callable[[HookContext], None]:
            hook_name = name or func.__name__
            self.register(Hook(hook_name, hook_point, func, priority))
            return func

        return decorator

    def get_hooks(self, hook_point: HookPoint) -> list[Hook]:
        """
        Get all hooks registered at a hook point.

        Args:
            hook_point: The hook point to query.

        Returns:
            Copy of the list of hooks at this point (sorted by priority).
        """
        return self._hooks[hook_point].copy()

    def clear(self, hook_point: HookPoint | None = None) -> None:
        """
        Clear registered hooks.

        Args:
            hook_point: If provided, clear only hooks at this point.
                       If None, clear all hooks at all points.
        """
        if hook_point:
            self._hooks[hook_point] = []
        else:
            for hp in HookPoint:
                self._hooks[hp] = []
