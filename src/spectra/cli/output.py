"""
Output - Rich console output formatting.

Provides pretty-printed output with colors and formatting.
"""

import sys

from spectra.application.sync import SyncResult


class Colors:
    """
    ANSI color codes for terminal output.

    Provides constants for text colors, background colors, and text styles
    that can be used to format terminal output.

    Attributes:
        RESET: Reset all formatting to default.
        BOLD: Make text bold.
        DIM: Make text dimmed/faded.
        RED: Red text color.
        GREEN: Green text color.
        YELLOW: Yellow text color.
        BLUE: Blue text color.
        MAGENTA: Magenta text color.
        CYAN: Cyan text color.
        WHITE: White text color.
        BG_RED: Red background color.
        BG_GREEN: Green background color.
        BG_YELLOW: Yellow background color.
        BG_BLUE: Blue background color.
    """

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


class Symbols:
    """
    Unicode symbols for terminal output.

    Provides constants for commonly used symbols in CLI output,
    including status indicators, navigation arrows, and box drawing characters.

    Attributes:
        CHECK: Checkmark symbol for success.
        CROSS: Cross symbol for failure.
        ARROW: Right arrow for navigation/pointers.
        DOT: Bullet point for list items.
        WARN: Warning triangle symbol.
        INFO: Information symbol.
        ROCKET: Rocket emoji for launch/start.
        GEAR: Gear emoji for settings/processing.
        FILE: File emoji for documents.
        FOLDER: Folder emoji for directories.
        LINK: Link emoji for URLs.
        BOX_TL: Box drawing top-left corner.
        BOX_TR: Box drawing top-right corner.
        BOX_BL: Box drawing bottom-left corner.
        BOX_BR: Box drawing bottom-right corner.
        BOX_H: Box drawing horizontal line.
        BOX_V: Box drawing vertical line.
    """

    CHECK = "✓"
    CROSS = "✗"
    ARROW = "→"
    DOT = "•"
    WARN = "⚠"
    INFO = "ℹ"
    ROCKET = "🚀"
    GEAR = "⚙"
    FILE = "📄"
    FOLDER = "📁"
    LINK = "🔗"

    # Box drawing
    BOX_TL = "╭"
    BOX_TR = "╮"
    BOX_BL = "╰"
    BOX_BR = "╯"
    BOX_H = "─"
    BOX_V = "│"


class Console:
    """
    Console output helper with colors and formatting.

    Provides methods for printing formatted, colorized output to the terminal.
    Supports headers, sections, status messages, tables, progress bars, and
    interactive prompts.

    Attributes:
        color: Whether to use ANSI color codes.
        verbose: Whether to print debug messages.
        quiet: Whether to suppress most output (for CI/scripting).
        json_mode: Whether to output JSON format for programmatic use.
    """

    def __init__(
        self,
        color: bool = True,
        verbose: bool = False,
        quiet: bool = False,
        json_mode: bool = False,
    ):
        """
        Initialize the console output helper.

        Args:
            color: Enable colored output. Automatically disabled if stdout is not a TTY.
            verbose: Enable verbose debug output.
            quiet: Suppress most output, only show errors and final summary.
            json_mode: Output JSON format instead of text.
        """
        self.json_mode = json_mode
        self.color = color and sys.stdout.isatty() and not json_mode
        self.verbose = verbose
        self.quiet = quiet or json_mode  # JSON mode implies quiet for intermediate output

        # JSON mode collects messages for final output
        self._json_messages: list[dict] = []
        self._json_errors: list[str] = []

        # Quiet mode overrides verbose
        if self.quiet:
            self.verbose = False

    def _c(self, text: str, *codes: str) -> str:
        """
        Apply color codes to text.

        Args:
            text: The text to colorize.
            *codes: ANSI color codes to apply.

        Returns:
            Colorized text with reset code appended, or plain text if color is disabled.
        """
        if not self.color:
            return text
        return "".join(codes) + text + Colors.RESET

    def print(self, text: str = "", force: bool = False) -> None:
        """
        Print text to stdout.

        Args:
            text: Text to print. Defaults to empty string for blank line.
            force: Print even in quiet mode.
        """
        if self.quiet and not force:
            return
        print(text)

    def header(self, text: str) -> None:
        """
        Print a prominent header with borders.

        Args:
            text: Header text to display.
        """
        if self.quiet:
            return
        width = max(len(text) + 4, 50)
        border = Colors.CYAN + Symbols.BOX_H * width + Colors.RESET if self.color else "-" * width

        self.print()
        self.print(border)
        self.print(self._c(f"  {text}", Colors.BOLD, Colors.CYAN))
        self.print(border)
        self.print()

    def section(self, text: str) -> None:
        """
        Print a section header.

        Args:
            text: Section title to display.
        """
        if self.quiet:
            return
        self.print()
        self.print(self._c(f"{Symbols.ARROW} {text}", Colors.BOLD, Colors.BLUE))

    def success(self, text: str) -> None:
        """
        Print a success message with checkmark.

        Args:
            text: Success message to display.
        """
        if self.quiet:
            return
        self.print(self._c(f"  {Symbols.CHECK} {text}", Colors.GREEN))

    def error(self, text: str) -> None:
        """
        Print an error message with cross symbol.

        Always prints, even in quiet mode. Collected in JSON mode.

        Args:
            text: Error message to display.
        """
        if self.json_mode:
            self._json_errors.append(text)
            return
        # Errors always print, even in quiet mode
        print(self._c(f"  {Symbols.CROSS} {text}", Colors.RED))

    def error_rich(self, exc: Exception) -> None:
        """
        Print a rich, formatted error message from an exception.

        Provides actionable suggestions and context based on the error type.
        Always prints, even in quiet mode.

        Args:
            exc: Exception to format and display.
        """
        from .errors import format_error

        if self.json_mode:
            self._json_errors.append(str(exc))
            return

        formatted = format_error(exc, color=self.color, verbose=self.verbose)
        print(formatted)

    def config_errors(self, errors: list[str]) -> None:
        """
        Print formatted configuration errors with suggestions.

        Provides helpful guidance on how to fix configuration issues.
        Always prints, even in quiet mode.

        Args:
            errors: List of configuration error messages.
        """
        from .errors import format_config_errors

        if self.json_mode:
            self._json_errors.extend(errors)
            return

        formatted = format_config_errors(errors, color=self.color)
        print(formatted)

    def connection_error(self, url: str = "") -> None:
        """
        Print a formatted connection error with suggestions.

        Provides helpful guidance on how to fix connection/auth issues.
        Always prints, even in quiet mode.

        Args:
            url: The Jira URL that failed to connect (optional).
        """
        from .errors import format_connection_error

        if self.json_mode:
            self._json_errors.append(f"Connection failed: {url}" if url else "Connection failed")
            return

        formatted = format_connection_error(url, color=self.color)
        print(formatted)

    def warning(self, text: str) -> None:
        """
        Print a warning message with warning symbol.

        Args:
            text: Warning message to display.
        """
        if self.quiet:
            return
        self.print(self._c(f"  {Symbols.WARN} {text}", Colors.YELLOW))

    def info(self, text: str) -> None:
        """
        Print an info message with info symbol.

        Args:
            text: Info message to display.
        """
        if self.quiet:
            return
        self.print(self._c(f"  {Symbols.INFO} {text}", Colors.CYAN))

    def detail(self, text: str) -> None:
        """
        Print detail text in dimmed color with extra indentation.

        Args:
            text: Detail text to display.
        """
        if self.quiet:
            return
        self.print(self._c(f"    {text}", Colors.DIM))

    def debug(self, text: str) -> None:
        """
        Print debug message (only visible in verbose mode).

        Args:
            text: Debug message to display.
        """
        if self.verbose:
            self.print(self._c(f"  [DEBUG] {text}", Colors.DIM))

    def item(self, text: str, status: str | None = None) -> None:
        """
        Print a list item with optional status indicator.

        Args:
            text: Item text to display.
            status: Optional status string. Special values:
                - "ok": Shows green checkmark
                - "skip": Shows yellow SKIP label
                - "fail": Shows red cross
                - Any other string: Shows dimmed label
        """
        if self.quiet:
            return
        status_str = ""
        if status == "ok":
            status_str = self._c(f" [{Symbols.CHECK}]", Colors.GREEN)
        elif status == "skip":
            status_str = self._c(" [SKIP]", Colors.YELLOW)
        elif status == "fail":
            status_str = self._c(f" [{Symbols.CROSS}]", Colors.RED)
        elif status:
            status_str = self._c(f" [{status}]", Colors.DIM)

        self.print(f"    {Symbols.DOT} {text}{status_str}")

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """
        Print a formatted table with headers.

        Automatically calculates column widths based on content.

        Args:
            headers: List of column header strings.
            rows: List of rows, where each row is a list of cell values.
        """
        if self.quiet:
            return
        # Calculate column widths
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

        # Print header
        header_line = "  " + "  ".join(
            self._c(h.ljust(widths[i]), Colors.BOLD) for i, h in enumerate(headers)
        )
        self.print(header_line)
        self.print("  " + "  ".join("-" * w for w in widths))

        # Print rows
        for row in rows:
            row_line = "  " + "  ".join(
                str(cell).ljust(widths[i]) if i < len(widths) else str(cell)
                for i, cell in enumerate(row)
            )
            self.print(row_line)

    def progress(self, current: int, total: int, message: str = "") -> None:
        """
        Print an updating progress bar.

        Uses carriage return to update in place in interactive terminals.
        Falls back to simple line output for non-interactive terminals.

        Args:
            current: Current progress value.
            total: Total/maximum progress value.
            message: Optional message to display after the progress bar.
        """
        if self.quiet:
            return

        width = 30
        filled = int(width * current / total)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(100 * current / total)

        # Check if running in interactive terminal
        if sys.stdout.isatty():
            # Interactive: update in place with carriage return
            padded_message = f"{message:<25}"
            line = f"\r  [{bar}] {pct:>3}% {padded_message}"
            sys.stdout.write(line)
            sys.stdout.flush()
            if current >= total:
                self.print()
        else:
            # Non-interactive: print each phase once (track with instance variable)
            if not hasattr(self, "_last_progress_message"):
                self._last_progress_message = ""
            if message != self._last_progress_message:
                self._last_progress_message = message
                self.print(f"  [{bar}] {pct:>3}% {message}")

    def dry_run_banner(self) -> None:
        """
        Print a prominent dry-run mode banner.

        Displays a highlighted banner indicating that no changes will be made.
        """
        if self.quiet:
            return
        self.print()
        banner = f"  {Symbols.GEAR} DRY-RUN MODE - No changes will be made"
        if self.color:
            self.print(f"{Colors.BG_YELLOW}{Colors.BOLD}{banner}{Colors.RESET}")
        else:
            self.print(f"*** {banner} ***")
        self.print()

    def sync_result(self, result: SyncResult) -> None:
        """
        Print a formatted sync result summary.

        Displays statistics, warnings, errors, and final status.
        In JSON mode, outputs a structured JSON object.
        In quiet mode, prints a single line summary suitable for CI/scripting.

        Args:
            result: SyncResult object containing sync operation details.
        """
        import json

        # JSON mode: structured output for programmatic use
        if self.json_mode:
            output = {
                "success": result.success,
                "dry_run": result.dry_run,
                "incremental": getattr(result, "incremental", False),
                "stats": {
                    "stories_matched": result.stories_matched,
                    "stories_updated": result.stories_updated,
                    "stories_skipped": getattr(result, "stories_skipped", 0),
                    "subtasks_created": result.subtasks_created,
                    "subtasks_updated": result.subtasks_updated,
                    "comments_added": result.comments_added,
                    "statuses_updated": result.statuses_updated,
                },
                "matched_stories": result.matched_stories,
                "unmatched_stories": result.unmatched_stories,
                "errors": result.errors + self._json_errors,
                "warnings": result.warnings,
            }

            # Include failed operations if present
            if hasattr(result, "failed_operations") and result.failed_operations:
                output["failed_operations"] = [
                    {
                        "operation": op.operation,
                        "issue_key": op.issue_key,
                        "error": op.error,
                        "story_id": op.story_id,
                    }
                    for op in result.failed_operations
                ]

            print(json.dumps(output, indent=2))
            return

        # Quiet mode: compact one-line output for CI/scripting
        if self.quiet:
            status = "OK" if result.success else "FAILED"
            mode = "dry-run" if result.dry_run else "executed"
            parts = [
                f"status={status}",
                f"mode={mode}",
                f"matched={result.stories_matched}",
                f"updated={result.stories_updated}",
                f"subtasks_created={result.subtasks_created}",
                f"comments={result.comments_added}",
            ]
            if result.errors:
                parts.append(f"errors={len(result.errors)}")
            print(" ".join(parts))

            # Still print errors even in quiet mode
            for e in result.errors:
                print(f"ERROR: {e}")
            return

        # Clear the progress line with a newline
        self.print()
        self.section("Sync Complete")
        self.print()

        # Mode indicator
        if result.dry_run:
            mode_text = f"{Symbols.GEAR} Mode: DRY-RUN (no changes made)"
            if self.color:
                self.print(f"  {Colors.YELLOW}{mode_text}{Colors.RESET}")
            else:
                self.print(f"  {mode_text}")
        else:
            mode_text = f"{Symbols.CHECK} Mode: LIVE EXECUTION"
            if self.color:
                self.print(f"  {Colors.GREEN}{mode_text}{Colors.RESET}")
            else:
                self.print(f"  {mode_text}")

        self.print()

        # Human-readable summary line
        epic_updated = getattr(result, "epic_updated", False)
        actions = []
        if epic_updated:
            actions.append("epic")
        if result.stories_updated > 0:
            actions.append(f"{result.stories_updated} stories")
        if result.subtasks_created > 0:
            actions.append(f"{result.subtasks_created} new subtasks")
        if result.subtasks_updated > 0:
            actions.append(f"{result.subtasks_updated} subtasks")
        if result.comments_added > 0:
            actions.append(f"{result.comments_added} comments")
        if result.statuses_updated > 0:
            actions.append(f"{result.statuses_updated} status changes")

        if actions:
            summary = "  Updated: " + ", ".join(actions)
            if self.color:
                self.print(f"{Colors.CYAN}{summary}{Colors.RESET}")
            else:
                self.print(summary)
        else:
            self.print("  No changes needed")

        self.print()

        # Compact stats table
        stats = [
            ["Stories", f"{result.stories_matched} matched, {result.stories_updated} updated"],
            [
                "Subtasks",
                f"{result.subtasks_created} created, {result.subtasks_updated} updated",
            ],
        ]

        # Only show if there were comments or status changes
        if result.comments_added > 0 or result.statuses_updated > 0:
            stats.append(
                [
                    "Other",
                    f"{result.comments_added} comments, {result.statuses_updated} transitions",
                ]
            )

        # Add incremental stats if applicable
        if getattr(result, "incremental", False) and result.stories_skipped > 0:
            stats.insert(
                0, ["Incremental", f"{result.stories_skipped} stories skipped (unchanged)"]
            )

        self.table(["Metric", "Count"], stats)

        # Warnings
        if result.warnings:
            self.print()
            self.warning(f"{len(result.warnings)} warning(s):")
            for w in result.warnings[:5]:
                self.detail(w)
            if len(result.warnings) > 5:
                self.detail(f"... and {len(result.warnings) - 5} more")

        # Errors
        if result.errors:
            self.print()
            self.error(f"{len(result.errors)} error(s):")
            for e in result.errors[:5]:
                self.detail(e)
            if len(result.errors) > 5:
                self.detail(f"... and {len(result.errors) - 5} more")

        # Final status
        self.print()
        if result.success:
            self.success("Sync completed successfully!")
        else:
            self.error("Sync completed with errors")

    def confirm(self, message: str) -> bool:
        """
        Ask the user for confirmation.

        Displays a yes/no prompt and waits for user input.

        Args:
            message: Confirmation message to display.

        Returns:
            True if user confirmed (y/yes), False otherwise or on interrupt.
        """
        prompt = self._c(f"\n{Symbols.WARN} {message} (y/N): ", Colors.YELLOW)
        try:
            response = input(prompt).strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            self.print()
            return False
