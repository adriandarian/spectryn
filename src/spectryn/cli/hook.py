"""
Hook Command - Pre-commit hook integration.

Features:
- Install pre-commit hooks
- Uninstall hooks
- Run hook manually
- Validate before commit
"""

import stat
from pathlib import Path

from .exit_codes import ExitCode
from .output import Console, Symbols


# Pre-commit hook script template
PRE_COMMIT_SCRIPT = """#!/bin/sh
# spectra pre-commit hook
# Validates markdown files before commit

# Check if spectra is installed
if ! command -v spectra &> /dev/null; then
    echo "spectra not found, skipping validation"
    exit 0
fi

# Find changed markdown files
CHANGED_MD=$(git diff --cached --name-only --diff-filter=ACM | grep -E "\\.(md|markdown)$" || true)

if [ -z "$CHANGED_MD" ]; then
    exit 0
fi

echo "🔍 Validating markdown files..."

ERRORS=0
for file in $CHANGED_MD; do
    if [ -f "$file" ]; then
        # Check if it looks like a spectra file (has story headers)
        if grep -qE "^#{2,3}\\s+.*[A-Z]+-\\d+:" "$file"; then
            echo "  Checking $file..."
            if ! spectra --validate --input "$file" --quiet; then
                echo "  ❌ Validation failed: $file"
                ERRORS=$((ERRORS + 1))
            else
                echo "  ✅ $file"
            fi
        fi
    fi
done

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "❌ Pre-commit validation failed!"
    echo "   Fix the errors above or use --no-verify to skip"
    exit 1
fi

echo "✅ All files validated"
exit 0
"""

# Pre-push hook script template
PRE_PUSH_SCRIPT = """#!/bin/sh
# spectra pre-push hook
# Validates all epic files before push

echo "🔍 Validating epic files before push..."

# Find all epic markdown files
EPIC_FILES=$(find . -name "*.md" -type f | xargs grep -l "^#{2,3}\\s+.*[A-Z]+-\\d+:" 2>/dev/null || true)

if [ -z "$EPIC_FILES" ]; then
    echo "No epic files found"
    exit 0
fi

ERRORS=0
for file in $EPIC_FILES; do
    echo "  Checking $file..."
    if ! spectra --validate --input "$file" --quiet; then
        ERRORS=$((ERRORS + 1))
    fi
done

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "❌ Validation failed for $ERRORS file(s)"
    exit 1
fi

echo "✅ All epic files validated"
exit 0
"""


def get_git_hooks_dir() -> Path | None:
    """Get the git hooks directory."""
    # Check if we're in a git repository
    git_dir = Path(".git")
    if not git_dir.is_dir():
        # Try to find .git in parent directories
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").is_dir():
                git_dir = current / ".git"
                break
            current = current.parent
        else:
            return None

    return git_dir / "hooks"


def install_hook(hooks_dir: Path, hook_name: str, script: str) -> bool:
    """
    Install a git hook.

    Args:
        hooks_dir: Path to hooks directory.
        hook_name: Name of the hook (pre-commit, pre-push).
        script: Hook script content.

    Returns:
        True if installed successfully.
    """
    hook_path = hooks_dir / hook_name

    # Backup existing hook if present
    if hook_path.exists():
        backup_path = hooks_dir / f"{hook_name}.backup"
        hook_path.rename(backup_path)

    # Write new hook
    hook_path.write_text(script, encoding="utf-8")

    # Make executable
    current_mode = hook_path.stat().st_mode
    hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return True


def uninstall_hook(hooks_dir: Path, hook_name: str) -> bool:
    """
    Uninstall a git hook.

    Args:
        hooks_dir: Path to hooks directory.
        hook_name: Name of the hook.

    Returns:
        True if uninstalled successfully.
    """
    hook_path = hooks_dir / hook_name

    if not hook_path.exists():
        return False

    # Check if it's a spectra hook
    content = hook_path.read_text(encoding="utf-8")
    if "spectra" not in content:
        return False

    # Remove hook
    hook_path.unlink()

    # Restore backup if exists
    backup_path = hooks_dir / f"{hook_name}.backup"
    if backup_path.exists():
        backup_path.rename(hook_path)

    return True


def run_hook_install(
    console: Console,
    hook_type: str = "pre-commit",
    force: bool = False,
) -> int:
    """
    Run the hook install command.

    Args:
        console: Console for output.
        hook_type: Type of hook to install (pre-commit, pre-push, all).
        force: Overwrite existing hooks.

    Returns:
        Exit code.
    """
    console.header(f"spectra Hook Install {Symbols.GEAR}")
    console.print()

    # Find git hooks directory
    hooks_dir = get_git_hooks_dir()

    if hooks_dir is None:
        console.error("Not a git repository")
        console.info("Initialize git first: git init")
        return ExitCode.CONFIG_ERROR

    console.info(f"Hooks directory: {hooks_dir}")
    console.print()

    # Ensure hooks directory exists
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hooks_to_install = []
    if hook_type == "all":
        hooks_to_install = [
            ("pre-commit", PRE_COMMIT_SCRIPT),
            ("pre-push", PRE_PUSH_SCRIPT),
        ]
    elif hook_type == "pre-commit":
        hooks_to_install = [("pre-commit", PRE_COMMIT_SCRIPT)]
    elif hook_type == "pre-push":
        hooks_to_install = [("pre-push", PRE_PUSH_SCRIPT)]
    else:
        console.error(f"Unknown hook type: {hook_type}")
        console.info("Supported: pre-commit, pre-push, all")
        return ExitCode.CONFIG_ERROR

    installed = 0
    for name, script in hooks_to_install:
        hook_path = hooks_dir / name

        # Check for existing hook
        if hook_path.exists() and not force:
            content = hook_path.read_text(encoding="utf-8")
            if "spectra" in content:
                console.info(f"  {name}: already installed")
                continue
            console.warning(f"  {name}: existing hook found (use --force to replace)")
            continue

        if install_hook(hooks_dir, name, script):
            console.success(f"  {name}: installed")
            installed += 1
        else:
            console.error(f"  {name}: installation failed")

    console.print()
    if installed > 0:
        console.success(f"Installed {installed} hook(s)")
        console.print()
        console.info("The hooks will:")
        console.item("Validate markdown files before commit")
        console.item("Check story format and structure")
        console.item("Block commits with validation errors")
        console.print()
        console.info("Skip validation with: git commit --no-verify")
    else:
        console.info("No hooks installed")

    return ExitCode.SUCCESS


def run_hook_uninstall(console: Console, hook_type: str = "all") -> int:
    """
    Uninstall git hooks.

    Args:
        console: Console for output.
        hook_type: Type of hook to uninstall.

    Returns:
        Exit code.
    """
    console.header(f"spectra Hook Uninstall {Symbols.GEAR}")
    console.print()

    hooks_dir = get_git_hooks_dir()

    if hooks_dir is None:
        console.error("Not a git repository")
        return ExitCode.CONFIG_ERROR

    hooks = ["pre-commit", "pre-push"] if hook_type == "all" else [hook_type]

    removed = 0
    for name in hooks:
        if uninstall_hook(hooks_dir, name):
            console.success(f"  {name}: removed")
            removed += 1
        else:
            console.info(f"  {name}: not a spectra hook or not found")

    console.print()
    if removed > 0:
        console.success(f"Removed {removed} hook(s)")
    else:
        console.info("No spectra hooks found to remove")

    return ExitCode.SUCCESS


def run_hook_status(console: Console) -> int:
    """
    Show status of installed hooks.

    Args:
        console: Console for output.

    Returns:
        Exit code.
    """
    console.header(f"spectra Hook Status {Symbols.GEAR}")
    console.print()

    hooks_dir = get_git_hooks_dir()

    if hooks_dir is None:
        console.error("Not a git repository")
        return ExitCode.CONFIG_ERROR

    console.info(f"Hooks directory: {hooks_dir}")
    console.print()

    hooks = ["pre-commit", "pre-push"]

    for name in hooks:
        hook_path = hooks_dir / name

        if not hook_path.exists():
            console.info(f"  {name}: not installed")
        else:
            content = hook_path.read_text(encoding="utf-8")
            if "spectra" in content:
                console.success(f"  {name}: installed (spectra)")
            else:
                console.warning(f"  {name}: installed (other)")

    return ExitCode.SUCCESS
