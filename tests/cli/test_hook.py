"""Tests for Hook Command - Pre-commit hook integration."""

import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.exit_codes import ExitCode
from spectryn.cli.hook import (
    PRE_COMMIT_SCRIPT,
    PRE_PUSH_SCRIPT,
    get_git_hooks_dir,
    install_hook,
    run_hook_install,
    run_hook_status,
    run_hook_uninstall,
    uninstall_hook,
)
from spectryn.cli.output import Console


class TestGetGitHooksDir:
    """Tests for get_git_hooks_dir function."""

    def test_finds_git_dir_in_current_directory(self, tmp_path: Path):
        """Test finding .git in current directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        with patch("spectryn.cli.hook.Path") as mock_path:
            # Make Path(".git") return our mock
            mock_git = MagicMock()
            mock_git.is_dir.return_value = True
            mock_path.return_value = mock_git
            mock_path.cwd.return_value = tmp_path

            result = get_git_hooks_dir()
            assert result is not None

    def test_returns_none_when_no_git_dir(self, tmp_path: Path):
        """Test returns None when not in a git repository."""
        with patch("spectryn.cli.hook.Path") as mock_path:
            mock_git = MagicMock()
            mock_git.is_dir.return_value = False

            mock_cwd = MagicMock()
            mock_cwd.parent = mock_cwd  # Same as self - root reached

            mock_path.return_value = mock_git
            mock_path.cwd.return_value = mock_cwd

            result = get_git_hooks_dir()
            assert result is None

    def test_finds_git_dir_in_parent(self, tmp_path: Path):
        """Test finding .git in parent directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        # Change to nested directory
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(subdir)
            result = get_git_hooks_dir()
            assert result is not None
            assert result == git_dir / "hooks"
        finally:
            os.chdir(original_cwd)


class TestInstallHook:
    """Tests for install_hook function."""

    def test_installs_new_hook(self, tmp_path: Path):
        """Test installing a new hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        result = install_hook(hooks_dir, "pre-commit", PRE_COMMIT_SCRIPT)

        assert result is True
        hook_path = hooks_dir / "pre-commit"
        assert hook_path.exists()
        assert "spectra" in hook_path.read_text(encoding="utf-8")

        # Check executable (skip on Windows - no Unix permissions)
        if sys.platform != "win32":
            mode = hook_path.stat().st_mode
            assert mode & stat.S_IXUSR

    def test_backs_up_existing_hook(self, tmp_path: Path):
        """Test backing up existing hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        existing_hook = hooks_dir / "pre-commit"
        existing_hook.write_text("#!/bin/sh\necho 'old hook'", encoding="utf-8")

        result = install_hook(hooks_dir, "pre-commit", PRE_COMMIT_SCRIPT)

        assert result is True
        backup_path = hooks_dir / "pre-commit.backup"
        assert backup_path.exists()
        assert "old hook" in backup_path.read_text(encoding="utf-8")

    def test_installs_pre_push_hook(self, tmp_path: Path):
        """Test installing pre-push hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        result = install_hook(hooks_dir, "pre-push", PRE_PUSH_SCRIPT)

        assert result is True
        hook_path = hooks_dir / "pre-push"
        assert hook_path.exists()
        assert "spectra" in hook_path.read_text(encoding="utf-8")


class TestUninstallHook:
    """Tests for uninstall_hook function."""

    def test_uninstalls_spectra_hook(self, tmp_path: Path):
        """Test uninstalling a spectra hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")

        result = uninstall_hook(hooks_dir, "pre-commit")

        assert result is True
        assert not hook_path.exists()

    def test_does_not_uninstall_non_spectra_hook(self, tmp_path: Path):
        """Test that non-spectra hooks are not uninstalled."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho 'other hook'", encoding="utf-8")

        result = uninstall_hook(hooks_dir, "pre-commit")

        assert result is False
        assert hook_path.exists()

    def test_returns_false_when_hook_not_exists(self, tmp_path: Path):
        """Test returns False when hook doesn't exist."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        result = uninstall_hook(hooks_dir, "pre-commit")

        assert result is False

    def test_restores_backup_after_uninstall(self, tmp_path: Path):
        """Test restoring backup after uninstall."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")

        backup_path = hooks_dir / "pre-commit.backup"
        backup_path.write_text("#!/bin/sh\necho 'backup hook'")

        result = uninstall_hook(hooks_dir, "pre-commit")

        assert result is True
        assert hook_path.exists()
        assert "backup hook" in hook_path.read_text(encoding="utf-8")


class TestRunHookInstall:
    """Tests for run_hook_install command."""

    def test_install_pre_commit_hook(self, tmp_path: Path):
        """Test installing pre-commit hook."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="pre-commit")

        assert result == ExitCode.SUCCESS
        assert (hooks_dir / "pre-commit").exists()

    def test_install_pre_push_hook(self, tmp_path: Path):
        """Test installing pre-push hook."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="pre-push")

        assert result == ExitCode.SUCCESS
        assert (hooks_dir / "pre-push").exists()

    def test_install_all_hooks(self, tmp_path: Path):
        """Test installing all hooks."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="all")

        assert result == ExitCode.SUCCESS
        assert (hooks_dir / "pre-commit").exists()
        assert (hooks_dir / "pre-push").exists()

    def test_error_when_not_git_repo(self):
        """Test error when not in a git repository."""
        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=None):
            result = run_hook_install(console)

        assert result == ExitCode.CONFIG_ERROR
        console.error.assert_called()

    def test_error_for_unknown_hook_type(self, tmp_path: Path):
        """Test error for unknown hook type."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="unknown")

        assert result == ExitCode.CONFIG_ERROR
        console.error.assert_called()

    def test_skips_existing_spectra_hook(self, tmp_path: Path):
        """Test skipping already installed spectra hook."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir()

        # Pre-install a spectra hook
        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="pre-commit")

        assert result == ExitCode.SUCCESS
        # Should show "already installed"
        console.info.assert_called()

    def test_warns_existing_non_spectra_hook(self, tmp_path: Path):
        """Test warning when existing non-spectra hook found."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir()

        # Pre-install a different hook
        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho 'other hook'", encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="pre-commit", force=False)

        assert result == ExitCode.SUCCESS
        console.warning.assert_called()

    def test_force_replaces_existing_hook(self, tmp_path: Path):
        """Test force flag replaces existing hook."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir()

        # Pre-install a different hook
        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho 'other hook'", encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_install(console, hook_type="pre-commit", force=True)

        assert result == ExitCode.SUCCESS
        assert "spectra" in hook_path.read_text(encoding="utf-8")


class TestRunHookUninstall:
    """Tests for run_hook_uninstall command."""

    def test_uninstall_single_hook(self, tmp_path: Path):
        """Test uninstalling a single hook."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        hook_path = hooks_dir / "pre-commit"
        hook_path.write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_uninstall(console, hook_type="pre-commit")

        assert result == ExitCode.SUCCESS
        assert not hook_path.exists()

    def test_uninstall_all_hooks(self, tmp_path: Path):
        """Test uninstalling all hooks."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        (hooks_dir / "pre-commit").write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")
        (hooks_dir / "pre-push").write_text(PRE_PUSH_SCRIPT, encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_uninstall(console, hook_type="all")

        assert result == ExitCode.SUCCESS
        assert not (hooks_dir / "pre-commit").exists()
        assert not (hooks_dir / "pre-push").exists()

    def test_error_when_not_git_repo(self):
        """Test error when not in a git repository."""
        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=None):
            result = run_hook_uninstall(console)

        assert result == ExitCode.CONFIG_ERROR
        console.error.assert_called()


class TestRunHookStatus:
    """Tests for run_hook_status command."""

    def test_shows_installed_spectra_hooks(self, tmp_path: Path):
        """Test showing installed spectra hooks."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        (hooks_dir / "pre-commit").write_text(PRE_COMMIT_SCRIPT, encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_status(console)

        assert result == ExitCode.SUCCESS
        console.success.assert_called()

    def test_shows_other_hooks(self, tmp_path: Path):
        """Test showing other (non-spectra) hooks."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        (hooks_dir / "pre-commit").write_text("#!/bin/sh\necho 'other'", encoding="utf-8")

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_status(console)

        assert result == ExitCode.SUCCESS
        console.warning.assert_called()

    def test_shows_not_installed(self, tmp_path: Path):
        """Test showing not installed hooks."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()

        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=hooks_dir):
            result = run_hook_status(console)

        assert result == ExitCode.SUCCESS
        console.info.assert_called()

    def test_error_when_not_git_repo(self):
        """Test error when not in a git repository."""
        console = MagicMock(spec=Console)

        with patch("spectryn.cli.hook.get_git_hooks_dir", return_value=None):
            result = run_hook_status(console)

        assert result == ExitCode.CONFIG_ERROR
        console.error.assert_called()


class TestHookScripts:
    """Tests for hook script content."""

    def test_pre_commit_script_contains_spectra(self):
        """Test pre-commit script contains spectra commands."""
        assert "spectra" in PRE_COMMIT_SCRIPT
        assert "pre-commit" in PRE_COMMIT_SCRIPT
        assert "--validate" in PRE_COMMIT_SCRIPT

    def test_pre_push_script_contains_spectra(self):
        """Test pre-push script contains spectra commands."""
        assert "spectra" in PRE_PUSH_SCRIPT
        assert "pre-push" in PRE_PUSH_SCRIPT
        assert "--validate" in PRE_PUSH_SCRIPT

    def test_scripts_are_valid_shell(self):
        """Test scripts have valid shell shebang."""
        assert PRE_COMMIT_SCRIPT.startswith("#!/bin/sh")
        assert PRE_PUSH_SCRIPT.startswith("#!/bin/sh")
