"""Interactive tutorial command for spectra.

Provides step-by-step learning experience for new users.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .exit_codes import ExitCode
from .output import Colors, Console, Symbols


@dataclass
class TutorialStep:
    """A single step in the tutorial."""

    title: str
    description: str
    action: str  # What the user should do
    validation: Callable[[], bool] | None = None  # Check if step is complete
    hint: str = ""
    example: str = ""


@dataclass
class TutorialProgress:
    """Track tutorial progress."""

    current_step: int = 0
    completed_steps: list[int] = field(default_factory=list)
    total_steps: int = 0


TUTORIAL_STEPS: list[TutorialStep] = [
    TutorialStep(
        title="Welcome to Spectra!",
        description="""
Spectra syncs your markdown user stories with issue trackers like Jira,
GitHub Issues, Linear, and more. This tutorial will guide you through
the basics.""",
        action="Press Enter to continue...",
        example="",
    ),
    TutorialStep(
        title="Understanding the Markdown Format",
        description="""
Spectra parses markdown files with a specific structure. Stories are
defined with headers, metadata tables, and user story format.""",
        action="Review the example below, then press Enter",
        example="""
### US-001: User Authentication

| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

**As a** user
**I want** to log in securely
**So that** my data is protected

#### Acceptance Criteria
- [ ] Login form validates input
- [ ] Password is encrypted
- [ ] Session timeout after 30 minutes
""",
    ),
    TutorialStep(
        title="Creating Your First Epic File",
        description="""
An Epic file contains multiple user stories grouped under a common theme.
The file starts with epic metadata followed by stories.""",
        action="Create a file called EPIC-DEMO.md in your project",
        hint="You can use: touch EPIC-DEMO.md",
        example="""
# 🎯 EPIC-DEMO: My First Epic

## Epic Overview
| **Epic Key** | DEMO-1 |
| **Status** | 🔄 In Progress |

## User Stories

### US-001: First Story
...
""",
    ),
    TutorialStep(
        title="Configuration",
        description="""
Before syncing, you need to configure your tracker credentials.
Spectra supports multiple configuration methods:
- Environment variables
- .env file
- spectra.yaml config file""",
        action="Run: spectra --init",
        hint="The init wizard will guide you through setup",
    ),
    TutorialStep(
        title="Validating Your Markdown",
        description="""
Before syncing, validate your markdown to catch formatting issues.
Spectra checks for common problems like missing fields, invalid
priorities, and malformed acceptance criteria.""",
        action="Run: spectra --validate --markdown EPIC-DEMO.md",
        hint="Fix any reported issues before syncing",
    ),
    TutorialStep(
        title="Planning a Sync",
        description="""
Before actually syncing, you can preview what changes will be made.
This is like a 'dry run' that shows creates, updates, and no-changes.""",
        action="Run: spectra --plan --markdown EPIC-DEMO.md",
        hint="Review the plan carefully before proceeding",
    ),
    TutorialStep(
        title="Syncing to Jira",
        description="""
When you're ready, sync your stories to the tracker. Spectra will:
- Create new stories for unmatched local stories
- Update existing stories with local changes
- Optionally sync status changes bidirectionally""",
        action="Run: spectra --sync --markdown EPIC-DEMO.md",
        hint="Use --dry-run first if you're nervous!",
    ),
    TutorialStep(
        title="Viewing Statistics",
        description="""
Track your progress with the stats command. See story counts,
points distribution, status breakdown, and more.""",
        action="Run: spectra --stats --markdown EPIC-DEMO.md",
    ),
    TutorialStep(
        title="Generating Reports",
        description="""
Generate progress reports for stakeholders. Reports include
completed work, in-progress items, and blockers.""",
        action="Run: spectra --report weekly --markdown EPIC-DEMO.md",
        hint="Supports weekly, monthly, and sprint reports",
    ),
    TutorialStep(
        title="Tutorial Complete! 🎉",
        description="""
Congratulations! You've learned the basics of Spectra.

Key commands to remember:
  spectra --init           Set up configuration
  spectra --validate       Check markdown format
  spectra --plan           Preview sync changes
  spectra --sync           Sync to tracker
  spectra --stats          View statistics
  spectra --doctor         Diagnose issues

For more help:
  spectra --help           Show all options
  spectra --version        Show version info
""",
        action="Press Enter to exit the tutorial",
    ),
]


def format_step(
    step: TutorialStep,
    step_num: int,
    total_steps: int,
    color: bool = True,
) -> list[str]:
    """Format a tutorial step for display."""
    lines: list[str] = []

    # Header
    if color:
        lines.append("")
        lines.append(f"{Colors.CYAN}{'═' * 60}{Colors.RESET}")
        lines.append(
            f"{Colors.BOLD}{Colors.CYAN}Step {step_num}/{total_steps}: {step.title}{Colors.RESET}"
        )
        lines.append(f"{Colors.CYAN}{'═' * 60}{Colors.RESET}")
    else:
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"Step {step_num}/{total_steps}: {step.title}")
        lines.append("=" * 60)

    lines.append("")

    # Description
    for line in step.description.strip().split("\n"):
        lines.append(f"  {line.strip()}")
    lines.append("")

    # Example (if any)
    if step.example:
        if color:
            lines.append(f"{Colors.DIM}Example:{Colors.RESET}")
            lines.append(f"{Colors.GREEN}```markdown")
            for line in step.example.strip().split("\n"):
                lines.append(line)
            lines.append(f"```{Colors.RESET}")
        else:
            lines.append("Example:")
            lines.append("```markdown")
            for line in step.example.strip().split("\n"):
                lines.append(line)
            lines.append("```")
        lines.append("")

    # Hint (if any)
    if step.hint:
        if color:
            lines.append(f"  {Colors.YELLOW}💡 Hint: {step.hint}{Colors.RESET}")
        else:
            lines.append(f"  Hint: {step.hint}")
        lines.append("")

    # Action
    if color:
        lines.append(f"  {Colors.BOLD}➤ {step.action}{Colors.RESET}")
    else:
        lines.append(f"  → {step.action}")
    lines.append("")

    return lines


def run_tutorial(
    console: Console | None = None,
    color: bool = True,
    step: int | None = None,
) -> ExitCode:
    """Run the interactive tutorial.

    Args:
        console: Console for output
        color: Whether to use colors
        step: Specific step to show (1-based), or None for all

    Returns:
        Exit code
    """
    console = console or Console(color=color)
    total_steps = len(TUTORIAL_STEPS)

    # Show welcome banner
    if color:
        console.print("")
        console.print(f"{Colors.BOLD}{Colors.MAGENTA}")
        console.print("  ╔═══════════════════════════════════════════╗")
        console.print("  ║     🎓 SPECTRA INTERACTIVE TUTORIAL 🎓    ║")
        console.print("  ╚═══════════════════════════════════════════╝")
        console.print(f"{Colors.RESET}")
    else:
        console.print("")
        console.print("  ╔═══════════════════════════════════════════╗")
        console.print("  ║       SPECTRA INTERACTIVE TUTORIAL        ║")
        console.print("  ╚═══════════════════════════════════════════╝")
        console.print("")

    # If specific step requested
    if step is not None:
        if step < 1 or step > total_steps:
            console.error(f"Invalid step: {step}. Valid range: 1-{total_steps}")
            return ExitCode.ERROR

        tutorial_step = TUTORIAL_STEPS[step - 1]
        lines = format_step(tutorial_step, step, total_steps, color)
        for line in lines:
            console.print(line)

        return ExitCode.SUCCESS

    # Interactive mode - show all steps
    console.print("")
    console.print(f"  This tutorial has {total_steps} steps.")
    console.print("  Navigate with Enter (next) or 'q' to quit.")
    console.print("")

    for i, tutorial_step in enumerate(TUTORIAL_STEPS, 1):
        lines = format_step(tutorial_step, i, total_steps, color)
        for line in lines:
            console.print(line)

        # Wait for user input (in non-interactive mode, just continue)
        try:
            user_input = input("  ")
            if user_input.lower() in ("q", "quit", "exit"):
                console.print("")
                console.info("Tutorial exited. Run 'spectra --tutorial' to resume.")
                return ExitCode.SUCCESS
        except (EOFError, KeyboardInterrupt):
            console.print("")
            console.info("Tutorial interrupted.")
            return ExitCode.SUCCESS

    # Final message
    if color:
        console.print(f"\n{Colors.GREEN}{Symbols.CHECK} Tutorial complete!{Colors.RESET}")
    else:
        console.print("\n✓ Tutorial complete!")

    return ExitCode.SUCCESS


def list_tutorial_steps(console: Console | None = None, color: bool = True) -> ExitCode:
    """List all tutorial steps.

    Args:
        console: Console for output
        color: Whether to use colors

    Returns:
        Exit code
    """
    console = console or Console(color=color)

    console.header("Tutorial Steps")

    for i, step in enumerate(TUTORIAL_STEPS, 1):
        if color:
            console.print(f"  {Colors.CYAN}{i:2}.{Colors.RESET} {step.title}")
        else:
            console.print(f"  {i:2}. {step.title}")

    console.print("")
    console.print("  Run 'spectra --tutorial' to start")
    console.print("  Run 'spectra --tutorial-step N' to jump to step N")

    return ExitCode.SUCCESS
