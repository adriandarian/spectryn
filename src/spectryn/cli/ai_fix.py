"""
AI Fix - AI-assisted markdown format correction for spectra.

Provides functionality to:
- Detect available AI CLI tools (ollama, claude, gh copilot, aider, etc.)
- Generate format guides and fix prompts
- Optionally execute fixes through detected AI tools
"""

import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .output import Colors, Console, Symbols


class AITool(Enum):
    """Supported AI CLI tools."""

    # Major AI provider CLIs
    CLAUDE = "claude"  # Anthropic Claude CLI (claude.ai/code)
    GEMINI = "gemini"  # Google Gemini CLI (@google/gemini-cli)
    CODEX = "codex"  # OpenAI Codex CLI

    # Local model tools
    OLLAMA = "ollama"  # Ollama local models

    # GitHub ecosystem
    GH_COPILOT = "gh copilot"  # GitHub Copilot CLI (gh extension)
    COPILOT = "copilot"  # GitHub Copilot CLI (standalone npm package)

    # Coding assistants
    AIDER = "aider"  # Aider coding assistant
    GOOSE = "goose"  # Block's Goose AI agent
    CODY = "cody"  # Sourcegraph Cody CLI

    # General LLM CLI tools
    SGPT = "sgpt"  # Shell GPT
    LLM = "llm"  # Simon Willison's LLM CLI
    MODS = "mods"  # Charmbracelet mods
    FABRIC = "fabric"  # Daniel Miessler's Fabric


@dataclass
class DetectedTool:
    """A detected AI CLI tool."""

    tool: AITool
    command: str
    version: str | None = None
    available: bool = True

    @property
    def display_name(self) -> str:
        """Get human-readable name."""
        names = {
            AITool.CLAUDE: "Claude Code",
            AITool.GEMINI: "Gemini CLI",
            AITool.CODEX: "OpenAI Codex CLI",
            AITool.OLLAMA: "Ollama",
            AITool.GH_COPILOT: "GitHub Copilot (gh extension)",
            AITool.COPILOT: "GitHub Copilot CLI",
            AITool.AIDER: "Aider",
            AITool.GOOSE: "Goose (Block)",
            AITool.CODY: "Sourcegraph Cody",
            AITool.SGPT: "Shell GPT",
            AITool.LLM: "LLM CLI",
            AITool.MODS: "Mods",
            AITool.FABRIC: "Fabric",
        }
        return names.get(self.tool, self.tool.value)


@dataclass
class AIFixResult:
    """Result of an AI fix operation."""

    success: bool
    tool_used: str
    output: str | None = None
    fixed_content: str | None = None
    error: str | None = None
    command_run: str | None = None


def detect_ai_tools() -> list[DetectedTool]:
    """
    Detect available AI CLI tools on the system.

    Returns:
        List of detected tools with their availability status.
    """
    detected: list[DetectedTool] = []

    # Check for Claude CLI
    if shutil.which("claude"):
        version = _get_version("claude", ["--version"])
        detected.append(DetectedTool(AITool.CLAUDE, "claude", version))

    # Check for Ollama
    if shutil.which("ollama"):
        version = _get_version("ollama", ["--version"])
        detected.append(DetectedTool(AITool.OLLAMA, "ollama", version))

    # Check for GitHub Copilot CLI (standalone npm package: @githubnext/github-copilot-cli)
    if shutil.which("copilot"):
        version = _get_version("copilot", ["--version"])
        detected.append(DetectedTool(AITool.COPILOT, "copilot", version))

    # Check for GitHub Copilot CLI (via gh extension)
    if shutil.which("gh"):
        # Check if copilot extension is installed
        try:
            result = subprocess.run(
                ["gh", "extension", "list"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "copilot" in result.stdout.lower():
                detected.append(DetectedTool(AITool.GH_COPILOT, "gh copilot", None))
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

    # Check for Aider
    if shutil.which("aider"):
        version = _get_version("aider", ["--version"])
        detected.append(DetectedTool(AITool.AIDER, "aider", version))

    # Check for Shell GPT
    if shutil.which("sgpt"):
        version = _get_version("sgpt", ["--version"])
        detected.append(DetectedTool(AITool.SGPT, "sgpt", version))

    # Check for LLM CLI
    if shutil.which("llm"):
        version = _get_version("llm", ["--version"])
        detected.append(DetectedTool(AITool.LLM, "llm", version))

    # Check for Mods
    if shutil.which("mods"):
        version = _get_version("mods", ["--version"])
        detected.append(DetectedTool(AITool.MODS, "mods", version))

    # Check for Gemini CLI (Google)
    if shutil.which("gemini"):
        version = _get_version("gemini", ["--version"])
        detected.append(DetectedTool(AITool.GEMINI, "gemini", version))

    # Check for OpenAI Codex CLI
    if shutil.which("codex"):
        version = _get_version("codex", ["--version"])
        detected.append(DetectedTool(AITool.CODEX, "codex", version))

    # Check for Goose (Block's AI agent)
    if shutil.which("goose"):
        version = _get_version("goose", ["--version"])
        detected.append(DetectedTool(AITool.GOOSE, "goose", version))

    # Check for Sourcegraph Cody
    if shutil.which("cody"):
        version = _get_version("cody", ["--version"])
        detected.append(DetectedTool(AITool.CODY, "cody", version))

    # Check for Fabric (Daniel Miessler's tool)
    if shutil.which("fabric"):
        version = _get_version("fabric", ["--version"])
        detected.append(DetectedTool(AITool.FABRIC, "fabric", version))

    return detected


def _get_version(command: str, args: list[str]) -> str | None:
    """Get version string from a command."""
    try:
        result = subprocess.run(
            [command, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0][:50]  # First line, truncated
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def generate_format_guide() -> str:
    """
    Generate a concise format guide for spectra markdown files.

    Returns:
        A formatted guide string.
    """
    return """
╔══════════════════════════════════════════════════════════════════════════════╗
║                      SPECTRA MARKDOWN FORMAT GUIDE                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

REQUIRED STRUCTURE
──────────────────

1. STORY HEADER (Required)
   Format: ### [emoji] PREFIX-XXX: Story Title
   Any PREFIX-NUMBER format works (PROJ-001, FEAT-042, US-123, EU-001, etc.)

   Examples:
     ### 🔧 STORY-001: Implement User Authentication
     ### 🚀 STORY-042: Add Dashboard Feature
     ### PROJ-123: Fix Login Bug

2. METADATA (Required after each story header)
   Use inline format with bold labels:

   **Priority**: P0|P1|P2|High|Medium|Low
   **Story Points**: [number]
   **Status**: ✅ Done|🔄 In Progress|📋 Planned|To Do

   Example:
     **Priority**: P0
     **Story Points**: 5
     **Status**: 🔄 In Progress

3. USER STORY DESCRIPTION (Required)
   Format with bold markers:

   > **As a** [role],
   > **I want** [feature],
   > **So that** [benefit]

4. ACCEPTANCE CRITERIA (Optional but recommended)
   Use checkbox format:

   #### Acceptance Criteria
   - [ ] First criterion
   - [ ] Second criterion
   - [x] Completed criterion

5. SUBTASKS TABLE (Optional)
   Format with 5 columns:

   #### Subtasks
   | # | Subtask | Description | SP | Status |
   |---|---------|-------------|:--:|--------|
   | 1 | Task name | Description | 2 | ✅ Done |

6. STORY SEPARATOR
   Use --- between stories

VALID STATUS VALUES
───────────────────
  ✅ Done, Complete, Completed, Closed, Resolved
  🔄 In Progress, In Development, In Review, Active
  📋 Planned, To Do, Todo, Backlog, Open
  ⏸️ Blocked, On Hold, Waiting

VALID PRIORITY VALUES
─────────────────────
  🔴 Critical, Highest, P0, Blocker
  🟡 High, Major, P1
  🟢 Medium, P2
  🔵 Low, Minor, P3, P4, Trivial, Lowest

COMPLETE EXAMPLE
────────────────

# 🚀 Epic Title

## User Stories

---

### 🔧 STORY-001: Implement Feature X

**Priority**: P0
**Story Points**: 5
**Status**: 🔄 In Progress

#### Description

> **As a** developer,
> **I want** feature X implemented,
> **So that** I can improve productivity.

#### Acceptance Criteria

- [ ] Criterion 1 is met
- [ ] Criterion 2 is verified
- [x] Basic setup complete

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Setup | Initial configuration | 1 | ✅ Done |
| 2 | Implementation | Core feature | 3 | 🔄 In Progress |
| 3 | Testing | Unit tests | 1 | 📋 Planned |

---

### 🚀 STORY-002: Add Feature Y

... (continue with same format)

"""


def generate_fix_prompt(
    file_path: str,
    content: str,
    errors: list[str],
    warnings: list[str] | None = None,
) -> str:
    """
    Generate an AI prompt to fix markdown format issues.

    Args:
        file_path: Path to the markdown file.
        content: Current file content.
        errors: List of validation errors.
        warnings: Optional list of warnings.

    Returns:
        A prompt string for an AI to fix the issues.
    """
    error_list = "\n".join(f"  - {e}" for e in errors)
    warning_list = ""
    if warnings:
        warning_list = "\n\nWarnings to address:\n" + "\n".join(f"  - {w}" for w in warnings)

    return f"""You are helping fix a markdown file to match the spectra tool's expected format.

FILE: {file_path}

VALIDATION ERRORS:
{error_list}{warning_list}

REQUIRED FORMAT SPECIFICATIONS:
1. Story headers MUST use format: ### [emoji] PREFIX-XXX: Title (e.g., STORY-001, PROJ-123, FEAT-042, TASK-100)
2. Each story MUST have metadata with **Priority**, **Story Points**, and **Status** using bold labels
3. User story descriptions MUST use: **As a** role, **I want** feature, **So that** benefit
4. Acceptance criteria should use checkbox format: - [ ] criterion
5. Subtasks tables need 5 columns: #, Subtask, Description, SP, Status
6. Stories should be separated by ---

VALID STATUS VALUES: Done, In Progress, Planned, To Do, Blocked, Complete, Closed
VALID PRIORITY VALUES: P0, P1, P2, P3, Critical, High, Medium, Low

CURRENT CONTENT:
```markdown
{content}
```

INSTRUCTIONS:
1. Fix ALL validation errors listed above
2. Preserve ALL existing content and meaning
3. Only change formatting to match the required structure
4. Keep story IDs, titles, and descriptions intact
5. Output ONLY the corrected markdown, no explanations

Corrected markdown:
"""


def generate_copy_paste_prompt(
    file_path: str,
    errors: list[str],
    warnings: list[str] | None = None,
) -> str:
    """
    Generate a simplified prompt for manual copy-paste into AI tools.

    Args:
        file_path: Path to the markdown file.
        errors: List of validation errors.
        warnings: Optional list of warnings.

    Returns:
        A simplified prompt string.
    """
    error_list = "\n".join(f"- {e}" for e in errors[:10])  # Limit to 10 errors
    warning_list = ""
    if warnings:
        warning_list = "\n\nAlso fix these warnings:\n" + "\n".join(f"- {w}" for w in warnings[:5])

    return f"""Fix this markdown file ({file_path}) to match the spectra format.

Issues to fix:
{error_list}{warning_list}

Required format:
- Story headers: ### [emoji] PREFIX-XXX: Title (e.g., STORY-001, PROJ-123, FEAT-042)
- Metadata: **Priority**: X, **Story Points**: N, **Status**: X
- Description: **As a** role, **I want** feature, **So that** benefit
- Acceptance criteria: - [ ] criterion (checkbox format)
- Separate stories with ---

Paste your file content after this prompt, then I'll return the corrected version.
"""


def build_ai_command(
    tool: DetectedTool,
    prompt: str,
    file_path: str,
    output_path: str | None = None,
) -> tuple[list[str], str]:
    """
    Build the command to run an AI tool with the fix prompt.

    Args:
        tool: The AI tool to use.
        prompt: The fix prompt.
        file_path: Path to the input file.
        output_path: Optional output path (defaults to modifying in place).

    Returns:
        Tuple of (command args list, description of what the command does).
    """
    if tool.tool == AITool.CLAUDE:
        # Claude CLI: claude "prompt" -f file.md
        return (
            ["claude", prompt, "-f", file_path],
            "Claude will analyze and fix the file, outputting to stdout",
        )

    if tool.tool == AITool.OLLAMA:
        # Ollama: cat file | ollama run llama3 "prompt"
        # Need to use shell for piping
        return (
            ["sh", "-c", f'cat "{file_path}" | ollama run llama3.2 "{prompt}"'],
            "Ollama (llama3.2) will process the file content",
        )

    if tool.tool == AITool.AIDER:
        # Aider: aider --message "prompt" file.md
        return (
            ["aider", "--message", prompt, "--yes", file_path],
            f"Aider will edit {file_path} in place",
        )

    if tool.tool == AITool.SGPT:
        # Shell GPT: cat file | sgpt "prompt"
        return (
            ["sh", "-c", f'cat "{file_path}" | sgpt "{prompt}"'],
            "Shell GPT will process and output the fixed content",
        )

    if tool.tool == AITool.LLM:
        # LLM CLI: cat file | llm "prompt"
        return (
            ["sh", "-c", f'cat "{file_path}" | llm "{prompt}"'],
            "LLM CLI will process and output the fixed content",
        )

    if tool.tool == AITool.MODS:
        # Mods: cat file | mods "prompt"
        return (
            ["sh", "-c", f'cat "{file_path}" | mods "{prompt}"'],
            "Mods will process and output the fixed content",
        )

    if tool.tool == AITool.GH_COPILOT:
        # GitHub Copilot: gh copilot suggest "prompt"
        return (
            ["gh", "copilot", "suggest", prompt],
            "GitHub Copilot will suggest fixes (interactive)",
        )

    if tool.tool == AITool.COPILOT:
        # Standalone Copilot CLI: copilot explain "prompt"
        # The copilot CLI has subcommands: explain, suggest, etc.
        return (
            ["sh", "-c", f'cat "{file_path}" | copilot explain "{prompt}"'],
            "GitHub Copilot CLI will analyze and suggest fixes",
        )

    if tool.tool == AITool.GEMINI:
        # Gemini CLI: gemini "prompt" or pipe content
        return (
            ["sh", "-c", f'cat "{file_path}" | gemini "{prompt}"'],
            "Gemini CLI will process and output the fixed content",
        )

    if tool.tool == AITool.CODEX:
        # OpenAI Codex CLI
        return (
            ["sh", "-c", f'cat "{file_path}" | codex "{prompt}"'],
            "OpenAI Codex CLI will process and output the fixed content",
        )

    if tool.tool == AITool.GOOSE:
        # Goose (Block's AI agent): goose run "prompt"
        return (
            ["goose", "run", prompt, "--file", file_path],
            "Goose will analyze and fix the file",
        )

    if tool.tool == AITool.CODY:
        # Sourcegraph Cody CLI
        return (
            ["sh", "-c", f'cat "{file_path}" | cody chat "{prompt}"'],
            "Cody will process and output the fixed content",
        )

    if tool.tool == AITool.FABRIC:
        # Fabric: cat file | fabric --pattern "prompt"
        return (
            ["sh", "-c", f'cat "{file_path}" | fabric -p "{prompt}"'],
            "Fabric will process using its patterns",
        )

    # Fallback
    return (["echo", "Unsupported tool"], "Unsupported tool")


def run_ai_fix(
    tool: DetectedTool,
    file_path: str,
    errors: list[str],
    warnings: list[str] | None = None,
    dry_run: bool = True,
    output_path: str | None = None,
) -> AIFixResult:
    """
    Run an AI tool to fix the markdown file.

    Args:
        tool: The AI tool to use.
        file_path: Path to the markdown file.
        errors: List of validation errors.
        warnings: Optional list of warnings.
        dry_run: If True, only show what would be done.
        output_path: Optional output path (defaults to modifying in place).

    Returns:
        AIFixResult with the operation outcome.
    """
    # Read file content
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return AIFixResult(
            success=False,
            tool_used=tool.display_name,
            error=f"Failed to read file: {e}",
        )

    # Generate prompt
    prompt = generate_fix_prompt(file_path, content, errors, warnings)

    # Build command
    cmd, description = build_ai_command(tool, prompt, file_path, output_path)

    if dry_run:
        return AIFixResult(
            success=True,
            tool_used=tool.display_name,
            output=f"Would run: {' '.join(cmd[:3])}...\n{description}",
            command_run=" ".join(cmd[:50]),  # Truncated for display
        )

    # Execute the command
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode == 0:
            return AIFixResult(
                success=True,
                tool_used=tool.display_name,
                output=result.stdout,
                fixed_content=result.stdout if result.stdout.strip() else None,
                command_run=" ".join(cmd[:50]),
            )
        return AIFixResult(
            success=False,
            tool_used=tool.display_name,
            error=result.stderr or f"Command failed with exit code {result.returncode}",
            command_run=" ".join(cmd[:50]),
        )

    except subprocess.TimeoutExpired:
        return AIFixResult(
            success=False,
            tool_used=tool.display_name,
            error="Command timed out after 120 seconds",
        )
    except Exception as e:
        return AIFixResult(
            success=False,
            tool_used=tool.display_name,
            error=str(e),
        )


def format_ai_tools_list(tools: list[DetectedTool], color: bool = True) -> str:
    """
    Format detected AI tools for display.

    Args:
        tools: List of detected tools.
        color: Whether to use ANSI colors.

    Returns:
        Formatted string.
    """
    if not tools:
        msg = "No AI CLI tools detected on your system."
        if color:
            return f"{Colors.YELLOW}{msg}{Colors.RESET}"
        return msg

    lines = []
    header = "Available AI tools for auto-fix:"
    if color:
        lines.append(f"{Colors.CYAN}{Colors.BOLD}{header}{Colors.RESET}")
    else:
        lines.append(header)

    for i, tool in enumerate(tools, 1):
        version_str = f" ({tool.version})" if tool.version else ""
        if color:
            lines.append(
                f"  {Colors.GREEN}{i}.{Colors.RESET} {tool.display_name}{Colors.DIM}{version_str}{Colors.RESET}"
            )
        else:
            lines.append(f"  {i}. {tool.display_name}{version_str}")

    return "\n".join(lines)


def format_fix_suggestion(
    file_path: str,
    errors: list[str],
    warnings: list[str] | None = None,
    tools: list[DetectedTool] | None = None,
    color: bool = True,
) -> str:
    """
    Format the complete fix suggestion with guide, prompt, and tool options.

    Args:
        file_path: Path to the markdown file.
        errors: List of validation errors.
        warnings: Optional list of warnings.
        tools: Optional list of detected AI tools.
        color: Whether to use ANSI colors.

    Returns:
        Formatted suggestion string.
    """
    lines = []

    # Section header
    header = "AI-Assisted Fix Available"
    if color:
        lines.append(f"\n{Colors.CYAN}{Colors.BOLD}{'─' * 60}{Colors.RESET}")
        lines.append(f"{Colors.CYAN}{Colors.BOLD}{Symbols.INFO} {header}{Colors.RESET}")
        lines.append(f"{Colors.CYAN}{Colors.BOLD}{'─' * 60}{Colors.RESET}\n")
    else:
        lines.append(f"\n{'─' * 60}")
        lines.append(f"ℹ {header}")
        lines.append(f"{'─' * 60}\n")

    # Option 1: View format guide
    if color:
        lines.append(f"{Colors.BOLD}Option 1: View format guide{Colors.RESET}")
        lines.append(
            f"  {Colors.DIM}Run: spectra --validate --input {file_path} --show-guide{Colors.RESET}\n"
        )
    else:
        lines.append("Option 1: View format guide")
        lines.append(f"  Run: spectra --validate --input {file_path} --show-guide\n")

    # Option 2: Get AI prompt
    if color:
        lines.append(
            f"{Colors.BOLD}Option 2: Get AI fix prompt (copy to your AI tool){Colors.RESET}"
        )
        lines.append(
            f"  {Colors.DIM}Run: spectra --validate --input {file_path} --suggest-fix{Colors.RESET}\n"
        )
    else:
        lines.append("Option 2: Get AI fix prompt (copy to your AI tool)")
        lines.append(f"  Run: spectra --validate --input {file_path} --suggest-fix\n")

    # Option 3: Auto-fix with detected tools
    if tools:
        if color:
            lines.append(f"{Colors.BOLD}Option 3: Auto-fix with AI tool{Colors.RESET}")
        else:
            lines.append("Option 3: Auto-fix with AI tool")

        lines.append(format_ai_tools_list(tools, color))
        lines.append("")

        # Show example commands
        first_tool = tools[0]
        if color:
            lines.append(
                f"  {Colors.DIM}Run: spectra --validate --input {file_path} --auto-fix --ai-tool {first_tool.tool.value}{Colors.RESET}"
            )
            lines.append(
                f"  {Colors.DIM}Or interactively: spectra --validate --input {file_path} --auto-fix{Colors.RESET}"
            )
        else:
            lines.append(
                f"  Run: spectra --validate --input {file_path} --auto-fix --ai-tool {first_tool.tool.value}"
            )
            lines.append(f"  Or interactively: spectra --validate --input {file_path} --auto-fix")
    # No tools detected, suggest installing one
    elif color:
        lines.append(f"{Colors.BOLD}Option 3: Install an AI CLI tool for auto-fix{Colors.RESET}")
        lines.append(f"  {Colors.DIM}Major AI CLIs:{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • claude: npm i -g @anthropic-ai/claude-code{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • gemini: npm i -g @google/gemini-cli{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • codex: npm i -g @openai/codex{Colors.RESET}")
        lines.append(f"  {Colors.DIM}Local models:{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • ollama: https://ollama.ai{Colors.RESET}")
        lines.append(f"  {Colors.DIM}Coding assistants:{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • aider: pip install aider-chat{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • goose: pip install goose-ai{Colors.RESET}")
        lines.append(
            f"  {Colors.DIM}  • gh copilot: gh extension install github/gh-copilot{Colors.RESET}"
        )
        lines.append(f"  {Colors.DIM}LLM tools:{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • llm: pip install llm{Colors.RESET}")
        lines.append(f"  {Colors.DIM}  • fabric: pip install fabric-ai{Colors.RESET}")
    else:
        lines.append("Option 3: Install an AI CLI tool for auto-fix")
        lines.append("  Major AI CLIs:")
        lines.append("    • claude: npm i -g @anthropic-ai/claude-code")
        lines.append("    • gemini: npm i -g @google/gemini-cli")
        lines.append("    • codex: npm i -g @openai/codex")
        lines.append("  Local models:")
        lines.append("    • ollama: https://ollama.ai")
        lines.append("  Coding assistants:")
        lines.append("    • aider: pip install aider-chat")
        lines.append("    • goose: pip install goose-ai")
        lines.append("    • gh copilot: gh extension install github/gh-copilot")
        lines.append("  LLM tools:")
        lines.append("    • llm: pip install llm")
        lines.append("    • fabric: pip install fabric-ai")

    return "\n".join(lines)


def select_ai_tool(tools: list[DetectedTool], console: Console) -> DetectedTool | None:
    """
    Interactively select an AI tool.

    Args:
        tools: List of available tools.
        console: Console for output.

    Returns:
        Selected tool or None if cancelled.
    """
    if not tools:
        console.error("No AI tools available")
        return None

    if len(tools) == 1:
        console.info(f"Using {tools[0].display_name}")
        return tools[0]

    # Show options
    console.print("\nSelect an AI tool for auto-fix:")
    for i, tool in enumerate(tools, 1):
        version_str = f" ({tool.version})" if tool.version else ""
        console.print(f"  {i}. {tool.display_name}{version_str}")

    console.print("  0. Cancel")
    console.print()

    try:
        choice = input("Enter choice [1]: ").strip()
        if choice == "0":
            return None
        if choice == "":
            choice = "1"

        idx = int(choice) - 1
        if 0 <= idx < len(tools):
            return tools[idx]
        console.error("Invalid choice")
        return None
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def get_tool_by_name(name: str, tools: list[DetectedTool]) -> DetectedTool | None:
    """
    Find a tool by name or enum value.

    Args:
        name: Tool name or enum value.
        tools: List of available tools.

    Returns:
        Matching tool or None.
    """
    name_lower = name.lower().strip()
    for tool in tools:
        if tool.tool.value == name_lower or tool.display_name.lower() == name_lower:
            return tool
        # Also match partial names
        if name_lower in tool.tool.value or name_lower in tool.display_name.lower():
            return tool
    return None
