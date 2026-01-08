"""
Interactive Mode - Step-by-step guided sync with previews.

Provides an interactive CLI experience for sync operations, allowing
users to preview changes, select/deselect operations, and execute
with full visibility.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .output import Colors, Console, Symbols


class Action(Enum):
    """User action choices in interactive mode."""

    CONTINUE = "continue"
    SKIP = "skip"
    SKIP_ALL = "skip_all"
    EXECUTE = "execute"
    EXECUTE_ALL = "execute_all"
    ABORT = "abort"
    BACK = "back"


@dataclass
class PendingOperation:
    """
    A single operation pending user approval.

    Attributes:
        operation_type: Type of operation (e.g., "update_description").
        issue_key: The Jira issue key affected.
        story_id: The markdown story ID.
        description: Human-readable description of the change.
        details: Optional additional details to show.
        selected: Whether this operation is selected for execution.
    """

    operation_type: str
    issue_key: str
    story_id: str
    description: str
    details: str | None = None
    selected: bool = True

    def toggle(self) -> None:
        """Toggle the selection state."""
        self.selected = not self.selected


@dataclass
class PhasePreview:
    """
    Preview of a sync phase with pending operations.

    Attributes:
        name: Phase name (e.g., "Descriptions", "Subtasks").
        description: Brief description of what this phase does.
        operations: List of pending operations in this phase.
        enabled: Whether this phase is enabled for execution.
    """

    name: str
    description: str
    operations: list[PendingOperation] = field(default_factory=list)
    enabled: bool = True

    @property
    def selected_count(self) -> int:
        """Number of selected operations."""
        return sum(1 for op in self.operations if op.selected)

    @property
    def total_count(self) -> int:
        """Total number of operations."""
        return len(self.operations)

    def select_all(self) -> None:
        """Select all operations."""
        for op in self.operations:
            op.selected = True

    def deselect_all(self) -> None:
        """Deselect all operations."""
        for op in self.operations:
            op.selected = False


class InteractiveSession:
    """
    Interactive sync session with step-by-step guidance.

    Provides a guided experience for syncing markdown to Jira,
    with previews of each change before execution.
    """

    def __init__(
        self,
        console: Console,
        orchestrator: Any,  # SyncOrchestrator - avoid circular import
        markdown_path: str,
        epic_key: str,
    ):
        """
        Initialize an interactive session.

        Args:
            console: Console for output.
            orchestrator: The sync orchestrator instance.
            markdown_path: Path to the markdown file.
            epic_key: Jira epic key to sync with.
        """
        self.console = console
        self.orchestrator = orchestrator
        self.markdown_path = markdown_path
        self.epic_key = epic_key

        self.phases: list[PhasePreview] = []
        self._aborted = False

    def run(self) -> bool:
        """
        Run the interactive sync session.

        Returns:
            True if sync completed (with any selections), False if aborted.
        """
        self._show_welcome()

        # Step 1: Analyze
        if not self._step_analyze():
            return False

        # Step 2: Build previews for each phase
        self._build_phase_previews()

        # Step 3: Show phase overview
        if not self._step_overview():
            return False

        # Step 4: Review each phase
        for phase in self.phases:
            if not phase.enabled or phase.total_count == 0:
                continue
            if not self._step_review_phase(phase):
                return False
            if self._aborted:
                return False

        # Step 5: Final confirmation and execute
        return self._step_execute()

    def _show_welcome(self) -> None:
        """Display welcome banner and instructions."""
        self.console.header(f"Interactive Sync Mode {Symbols.GEAR}")
        self.console.print()
        self.console.info("This mode guides you through each sync step with previews.")
        self.console.detail("You can review and select which changes to apply.")
        self.console.print()
        self._show_controls()

    def _show_controls(self) -> None:
        """Display keyboard controls."""
        self.console.print(self.console._c("  Controls:", Colors.BOLD))
        self.console.detail("[Enter] Continue  [s] Skip  [a] Abort  [?] Help")

    def _step_analyze(self) -> bool:
        """
        Step 1: Analyze markdown and Jira.

        Returns:
            True to continue, False to abort.
        """
        self.console.section("Step 1: Analyzing")
        self.console.info(f"Markdown: {self.markdown_path}")
        self.console.info(f"Epic: {self.epic_key}")
        self.console.print()

        try:
            # Run analysis
            result = self.orchestrator.analyze(self.markdown_path, self.epic_key)

            # Show results
            self.console.success(f"Found {len(self.orchestrator._md_stories)} stories in markdown")
            self.console.success(f"Found {len(self.orchestrator._jira_issues)} issues in Jira")
            self.console.success(f"Matched {result.stories_matched} stories")

            if result.unmatched_stories:
                self.console.print()
                self.console.warning(f"{len(result.unmatched_stories)} unmatched stories:")
                for story_id in result.unmatched_stories[:5]:
                    self.console.detail(f"• {story_id}")
                if len(result.unmatched_stories) > 5:
                    self.console.detail(f"... and {len(result.unmatched_stories) - 5} more")

            if result.stories_matched == 0:
                self.console.print()
                self.console.error("No stories matched. Check that story titles match Jira issues.")
                return self._prompt_continue("Continue anyway?", default=False)

            self.console.print()
            return self._prompt_continue()

        except Exception as e:
            self.console.error(f"Analysis failed: {e}")
            return False

    def _build_phase_previews(self) -> None:
        """Build preview data for each sync phase."""
        self.phases = []

        # Descriptions phase
        if self.orchestrator.config.sync_descriptions:
            desc_phase = PhasePreview(
                name="Descriptions",
                description="Update story descriptions in Jira from markdown content",
            )
            for story in self.orchestrator._md_stories:
                story_id = str(story.id)
                if story_id in self.orchestrator._matches and story.description:
                    issue_key = self.orchestrator._matches[story_id]
                    desc_phase.operations.append(
                        PendingOperation(
                            operation_type="update_description",
                            issue_key=issue_key,
                            story_id=story_id,
                            description=f"Update description for {story.title}",
                            details=self._truncate(story.description, 100),
                        )
                    )
            self.phases.append(desc_phase)

        # Subtasks phase
        if self.orchestrator.config.sync_subtasks:
            subtask_phase = PhasePreview(
                name="Subtasks",
                description="Create or update subtasks based on markdown",
            )
            for story in self.orchestrator._md_stories:
                story_id = str(story.id)
                if story_id in self.orchestrator._matches:
                    issue_key = self.orchestrator._matches[story_id]
                    for subtask in story.subtasks:
                        subtask_phase.operations.append(
                            PendingOperation(
                                operation_type="sync_subtask",
                                issue_key=issue_key,
                                story_id=story_id,
                                description=f"Sync subtask: {subtask.name}",
                                details=(
                                    f"{subtask.story_points} SP" if subtask.story_points else None
                                ),
                            )
                        )
            self.phases.append(subtask_phase)

        # Comments phase
        if self.orchestrator.config.sync_comments:
            comments_phase = PhasePreview(
                name="Comments",
                description="Add commit table comments to stories",
            )
            for story in self.orchestrator._md_stories:
                story_id = str(story.id)
                if story_id in self.orchestrator._matches and story.commits:
                    issue_key = self.orchestrator._matches[story_id]
                    comments_phase.operations.append(
                        PendingOperation(
                            operation_type="add_comment",
                            issue_key=issue_key,
                            story_id=story_id,
                            description=f"Add commits comment ({len(story.commits)} commits)",
                        )
                    )
            self.phases.append(comments_phase)

        # Statuses phase
        if self.orchestrator.config.sync_statuses:
            status_phase = PhasePreview(
                name="Statuses",
                description="Transition subtask statuses for completed stories",
            )
            for story in self.orchestrator._md_stories:
                story_id = str(story.id)
                if story_id in self.orchestrator._matches and story.status.is_complete():
                    issue_key = self.orchestrator._matches[story_id]
                    status_phase.operations.append(
                        PendingOperation(
                            operation_type="transition_status",
                            issue_key=issue_key,
                            story_id=story_id,
                            description="Transition subtasks to Resolved",
                        )
                    )
            self.phases.append(status_phase)

    def _step_overview(self) -> bool:
        """
        Step 2: Show overview of all phases.

        Returns:
            True to continue, False to abort.
        """
        self.console.section("Step 2: Sync Overview")
        self.console.print()

        total_ops = sum(p.total_count for p in self.phases)

        if total_ops == 0:
            self.console.warning("No operations to perform. Everything is in sync!")
            return True

        # Show phase summary table
        headers = ["Phase", "Operations", "Status"]
        rows = []
        for phase in self.phases:
            status = (
                self.console._c("enabled", Colors.GREEN)
                if phase.enabled
                else self.console._c("disabled", Colors.DIM)
            )
            rows.append([phase.name, str(phase.total_count), status])

        self.console.table(headers, rows)
        self.console.print()
        self.console.info(f"Total operations: {total_ops}")
        self.console.print()

        return self._prompt_continue("Review each phase?")

    def _step_review_phase(self, phase: PhasePreview) -> bool:
        """
        Review a single phase with its operations.

        Args:
            phase: The phase to review.

        Returns:
            True to continue, False to abort.
        """
        self.console.section(f"Review: {phase.name}")
        self.console.detail(phase.description)
        self.console.print()

        if phase.total_count == 0:
            self.console.info("No operations in this phase")
            return True

        # Show operations
        self._show_phase_operations(phase)

        # Interactive selection
        while True:
            action = self._prompt_phase_action(phase)

            if action == Action.CONTINUE:
                return True
            if action == Action.SKIP:
                phase.deselect_all()
                self.console.warning(f"Skipped all {phase.name} operations")
                return True
            if action == Action.EXECUTE_ALL:
                phase.select_all()
                return True
            if action == Action.ABORT:
                self._aborted = True
                return False
            if action == Action.BACK:
                self._show_phase_operations(phase)

    def _show_phase_operations(self, phase: PhasePreview) -> None:
        """Display operations in a phase."""
        self.console.print()
        for i, op in enumerate(phase.operations, 1):
            checkbox = (
                self.console._c("[✓]", Colors.GREEN)
                if op.selected
                else self.console._c("[ ]", Colors.DIM)
            )
            key = self.console._c(op.issue_key, Colors.CYAN)

            line = f"  {checkbox} {i}. {key} {op.description}"
            self.console.print(line)

            if op.details:
                self.console.detail(f"     {op.details}")

        self.console.print()
        self.console.info(f"Selected: {phase.selected_count}/{phase.total_count}")

    def _step_execute(self) -> bool:
        """
        Final step: Execute selected operations.

        Returns:
            True if executed, False if aborted.
        """
        self.console.section("Step 3: Execute")
        self.console.print()

        # Show final summary
        total_selected = sum(p.selected_count for p in self.phases if p.enabled)

        if total_selected == 0:
            self.console.warning("No operations selected. Nothing to execute.")
            return True

        self.console.info(f"Ready to execute {total_selected} operations:")
        for phase in self.phases:
            if phase.enabled and phase.selected_count > 0:
                self.console.detail(f"• {phase.name}: {phase.selected_count} operations")

        self.console.print()

        if self.orchestrator.config.dry_run:
            self.console.warning("DRY-RUN mode: No changes will be made")
            self.console.print()

        if not self._prompt_continue("Execute now?", default=True):
            self.console.warning("Cancelled by user")
            return False

        # Execute
        self.console.print()
        self._execute_selected_operations()

        return True

    def _execute_selected_operations(self) -> None:
        """Execute all selected operations with progress."""
        from spectryn.application.sync import SyncResult

        result = SyncResult(dry_run=self.orchestrator.config.dry_run)

        total = sum(p.selected_count for p in self.phases if p.enabled)
        current = 0

        for phase in self.phases:
            if not phase.enabled:
                continue

            for op in phase.operations:
                if not op.selected:
                    continue

                current += 1
                self.console.progress(current, total, f"{op.operation_type}: {op.issue_key}")

                # Execute based on operation type
                try:
                    if op.operation_type == "update_description":
                        self._execute_update_description(op, result)
                    elif op.operation_type == "sync_subtask":
                        self._execute_sync_subtask(op, result)
                    elif op.operation_type == "add_comment":
                        self._execute_add_comment(op, result)
                    elif op.operation_type == "transition_status":
                        self._execute_transition_status(op, result)
                except Exception as e:
                    result.add_failed_operation(
                        operation=op.operation_type,
                        issue_key=op.issue_key,
                        error=str(e),
                        story_id=op.story_id,
                    )

        # Show result summary
        self.console.print()
        self.console.sync_result(result)

    def _execute_update_description(self, op: PendingOperation, result: Any) -> None:
        """Execute a description update operation."""
        story = next((s for s in self.orchestrator._md_stories if str(s.id) == op.story_id), None)
        if story:
            adf = self.orchestrator.formatter.format_story_description(story)
            from spectryn.application.commands import UpdateDescriptionCommand

            cmd = UpdateDescriptionCommand(
                tracker=self.orchestrator.tracker,
                issue_key=op.issue_key,
                description=adf,
                event_bus=self.orchestrator.event_bus,
                dry_run=self.orchestrator.config.dry_run,
            )
            cmd_result = cmd.execute()
            if cmd_result.success:
                result.stories_updated += 1
            elif cmd_result.error:
                result.add_failed_operation(
                    operation="update_description",
                    issue_key=op.issue_key,
                    error=cmd_result.error,
                    story_id=op.story_id,
                )

    def _execute_sync_subtask(self, op: PendingOperation, result: Any) -> None:
        """Execute a subtask sync operation."""
        # Find the story and subtask
        story = next((s for s in self.orchestrator._md_stories if str(s.id) == op.story_id), None)
        if not story:
            return

        # Extract subtask name from description
        subtask_name = op.description.replace("Sync subtask: ", "")
        subtask = next((st for st in story.subtasks if st.name == subtask_name), None)
        if not subtask:
            return

        project_key = op.issue_key.split("-")[0]

        from spectryn.application.commands import CreateSubtaskCommand

        adf = self.orchestrator.formatter.format_text(subtask.description)

        cmd = CreateSubtaskCommand(
            tracker=self.orchestrator.tracker,
            parent_key=op.issue_key,
            project_key=project_key,
            summary=subtask.name,
            description=adf,
            story_points=subtask.story_points,
            event_bus=self.orchestrator.event_bus,
            dry_run=self.orchestrator.config.dry_run,
        )
        cmd_result = cmd.execute()
        if cmd_result.success:
            result.subtasks_created += 1
        elif cmd_result.error:
            result.add_failed_operation(
                operation="create_subtask",
                issue_key=op.issue_key,
                error=cmd_result.error,
                story_id=op.story_id,
            )

    def _execute_add_comment(self, op: PendingOperation, result: Any) -> None:
        """Execute an add comment operation."""
        story = next((s for s in self.orchestrator._md_stories if str(s.id) == op.story_id), None)
        if not story or not story.commits:
            return

        adf = self.orchestrator.formatter.format_commits_table(story.commits)

        from spectryn.application.commands import AddCommentCommand

        cmd = AddCommentCommand(
            tracker=self.orchestrator.tracker,
            issue_key=op.issue_key,
            body=adf,
            event_bus=self.orchestrator.event_bus,
            dry_run=self.orchestrator.config.dry_run,
        )
        cmd_result = cmd.execute()
        if cmd_result.success:
            result.comments_added += 1
        elif cmd_result.error:
            result.add_failed_operation(
                operation="add_comment",
                issue_key=op.issue_key,
                error=cmd_result.error,
                story_id=op.story_id,
            )

    def _execute_transition_status(self, op: PendingOperation, result: Any) -> None:
        """Execute a status transition operation."""
        from spectryn.application.commands import TransitionStatusCommand

        cmd = TransitionStatusCommand(
            tracker=self.orchestrator.tracker,
            issue_key=op.issue_key,
            target_status="Resolved",
            event_bus=self.orchestrator.event_bus,
            dry_run=self.orchestrator.config.dry_run,
        )
        cmd_result = cmd.execute()
        if cmd_result.success:
            result.statuses_updated += 1
        elif cmd_result.error:
            result.add_failed_operation(
                operation="transition_status",
                issue_key=op.issue_key,
                error=cmd_result.error,
                story_id=op.story_id,
            )

    # -------------------------------------------------------------------------
    # Prompts
    # -------------------------------------------------------------------------

    def _prompt_continue(self, message: str = "Continue?", default: bool = True) -> bool:
        """
        Prompt user to continue.

        Args:
            message: The prompt message.
            default: Default value if user just presses Enter.

        Returns:
            True to continue, False to abort.
        """
        hint = "(Y/n)" if default else "(y/N)"
        prompt = self.console._c(f"  {Symbols.ARROW} {message} {hint}: ", Colors.CYAN)

        try:
            response = input(prompt).strip().lower()
            if response == "":
                return default
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return False

    def _prompt_phase_action(self, phase: PhasePreview) -> Action:
        """
        Prompt user for action on a phase.

        Args:
            phase: The current phase.

        Returns:
            The selected action.
        """
        options = "[Enter] Continue  [s] Skip phase  [a] Abort  [t] Toggle items"
        self.console.print(self.console._c(f"  {options}", Colors.DIM))
        prompt = self.console._c(f"  {Symbols.ARROW} Action: ", Colors.CYAN)

        try:
            response = input(prompt).strip().lower()

            if response in {"", "c"}:
                return Action.CONTINUE
            if response == "s":
                return Action.SKIP
            if response == "a":
                return Action.ABORT
            if response == "e":
                return Action.EXECUTE_ALL
            if response == "t":
                self._toggle_operations(phase)
                return Action.BACK
            if response.isdigit():
                idx = int(response) - 1
                if 0 <= idx < len(phase.operations):
                    phase.operations[idx].toggle()
                return Action.BACK
            self.console.warning("Unknown command. Try again.")
            return Action.BACK

        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return Action.ABORT

    def _toggle_operations(self, phase: PhasePreview) -> None:
        """Interactive toggle of operations in a phase."""
        self.console.print()
        self.console.info("Enter operation numbers to toggle (comma-separated), or 'all':")
        prompt = self.console._c("  > ", Colors.DIM)

        try:
            response = input(prompt).strip().lower()

            if response == "all":
                if phase.selected_count == phase.total_count:
                    phase.deselect_all()
                else:
                    phase.select_all()
            else:
                # Parse comma-separated numbers
                for part in response.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(phase.operations):
                            phase.operations[idx].toggle()

        except (EOFError, KeyboardInterrupt):
            pass

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text with ellipsis."""
        text = text.replace("\n", " ").strip()
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."


def run_interactive(
    console: Console,
    orchestrator: Any,
    markdown_path: str,
    epic_key: str,
) -> bool:
    """
    Run an interactive sync session.

    Args:
        console: Console for output.
        orchestrator: The sync orchestrator.
        markdown_path: Path to markdown file.
        epic_key: Jira epic key.

    Returns:
        True if sync completed, False if aborted.
    """
    session = InteractiveSession(
        console=console,
        orchestrator=orchestrator,
        markdown_path=markdown_path,
        epic_key=epic_key,
    )
    return session.run()
