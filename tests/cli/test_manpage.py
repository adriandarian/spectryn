"""
Tests for man page generation.
"""

from unittest.mock import patch

import pytest

from spectryn.cli.manpage import (
    generate_man_page,
    get_installation_instructions,
    get_man_path,
    print_man_page,
)


class TestGenerateManPage:
    """Tests for generate_man_page function."""

    def test_generates_valid_troff(self):
        """Test that generated content is valid troff format."""
        content = generate_man_page()
        assert content.startswith(".TH SPECTRA 1")
        assert ".SH NAME" in content
        assert ".SH SYNOPSIS" in content
        assert ".SH DESCRIPTION" in content
        assert ".SH OPTIONS" in content

    def test_contains_all_sections(self):
        """Test that all standard man page sections are present."""
        content = generate_man_page()
        sections = [
            ".SH NAME",
            ".SH SYNOPSIS",
            ".SH DESCRIPTION",
            ".SH OPTIONS",
            ".SH ENVIRONMENT",
            ".SH FILES",
            ".SH EXAMPLES",
            ".SH EXIT STATUS",
            ".SH SEE ALSO",
            ".SH BUGS",
            ".SH AUTHOR",
            ".SH COPYRIGHT",
        ]
        for section in sections:
            assert section in content, f"Missing section: {section}"

    def test_contains_input_options(self):
        """Test that input options are documented (troff escapes dashes)."""
        content = generate_man_page()
        # In troff format, -- becomes \\-\\-
        assert "input" in content
        assert "input-dir" in content or "input\\-dir" in content
        assert "epic" in content
        assert "-f" in content
        assert "-d" in content
        assert "-e" in content

    def test_contains_execution_options(self):
        """Test that execution options are documented."""
        content = generate_man_page()
        assert "execute" in content
        assert "dry-run" in content or "dry\\-run" in content
        assert "no-confirm" in content or "no\\-confirm" in content
        assert "-x" in content
        assert "-n" in content

    def test_contains_output_options(self):
        """Test that output options are documented."""
        content = generate_man_page()
        assert "verbose" in content
        assert "quiet" in content
        assert "no-color" in content or "no\\-color" in content
        assert "no-emoji" in content or "no\\-emoji" in content
        assert "theme" in content
        assert "-v" in content
        assert "-q" in content

    def test_contains_special_modes(self):
        """Test that special mode options are documented."""
        content = generate_man_page()
        assert "validate" in content
        assert "interactive" in content
        assert "tui" in content
        assert "generate" in content

    def test_contains_environment_variables(self):
        """Test that environment variables are documented."""
        content = generate_man_page()
        assert "JIRA_URL" in content
        assert "JIRA_EMAIL" in content
        assert "JIRA_API_TOKEN" in content

    def test_contains_examples(self):
        """Test that examples are included."""
        content = generate_man_page()
        assert "spectra --init" in content
        assert "spectra --validate" in content
        assert "spectra -f EPIC.md -e PROJ-123" in content

    def test_contains_exit_codes(self):
        """Test that exit codes are documented."""
        content = generate_man_page()
        assert "Exit" in content or "exit" in content
        assert "Success" in content or "0" in content

    def test_contains_shell_completion_option(self):
        """Test that completions option is documented."""
        content = generate_man_page()
        assert "completions" in content
        assert "bash" in content
        assert "zsh" in content
        assert "fish" in content
        assert "powershell" in content

    def test_contains_man_page_options(self):
        """Test that man page options are documented."""
        content = generate_man_page()
        # In troff, these get escaped
        assert "man" in content.lower()
        assert "install" in content.lower()


class TestPrintManPage:
    """Tests for print_man_page function."""

    def test_prints_to_stdout(self, capsys):
        """Test that man page is printed to stdout."""
        print_man_page()
        captured = capsys.readouterr()
        assert ".TH SPECTRA 1" in captured.out
        assert ".SH NAME" in captured.out


class TestGetInstallationInstructions:
    """Tests for get_installation_instructions function."""

    def test_contains_install_command(self):
        """Test instructions contain install command."""
        instructions = get_installation_instructions()
        assert "spectra --install-man" in instructions

    def test_contains_linux_instructions(self):
        """Test instructions contain Linux paths."""
        instructions = get_installation_instructions()
        assert "/usr/local/share/man" in instructions or "man1" in instructions

    def test_contains_macos_instructions(self):
        """Test instructions contain macOS instructions."""
        instructions = get_installation_instructions()
        assert "macOS" in instructions

    def test_contains_user_local_option(self):
        """Test instructions contain user-local installation option."""
        instructions = get_installation_instructions()
        assert ".local/share/man" in instructions

    def test_contains_usage_example(self):
        """Test instructions contain usage example."""
        instructions = get_installation_instructions()
        assert "man spectra" in instructions


class TestGetManPath:
    """Tests for get_man_path function."""

    def test_returns_path_or_none(self):
        """Test that function returns Path or None."""
        from pathlib import Path

        result = get_man_path()
        assert result is None or isinstance(result, Path)

    def test_path_ends_with_man1(self):
        """Test that returned path ends with man1."""
        result = get_man_path()
        if result is not None:
            assert result.name == "man1"


class TestCLIManFlag:
    """Tests for CLI --man flag."""

    def test_man_flag_shows_content(self, capsys):
        """Test --man flag displays man page content."""
        from spectryn.cli.app import main

        # Mock subprocess to avoid actually calling man
        with (
            patch("sys.argv", ["spectra", "--man"]),
            patch("spectryn.cli.manpage.subprocess.run") as mock_run,
        ):
            # Simulate man not being available
            mock_run.side_effect = FileNotFoundError
            result = main()

        # Should succeed (falls back to printing raw content)
        assert result == 0
        captured = capsys.readouterr()
        assert ".TH SPECTRA 1" in captured.out

    def test_install_man_flag(self, tmp_path, capsys):
        """Test --install-man flag attempts installation."""
        from spectryn.cli.app import main

        # Mock get_man_path to use temp directory
        with (
            patch("sys.argv", ["spectra", "--install-man"]),
            patch("spectryn.cli.manpage.get_man_path", return_value=tmp_path),
        ):
            result = main()

        captured = capsys.readouterr()
        # Should either succeed or give informative message
        assert result == 0 or "Permission" in captured.out or "Error" in captured.out

        # If successful, man page should exist (named spectra.1 for command name)
        man_file = tmp_path / "spectra.1"
        if result == 0:
            assert man_file.exists()
            content = man_file.read_text()
            assert ".TH SPECTRA 1" in content
