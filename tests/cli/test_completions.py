"""
Tests for shell completion generation.
"""

from unittest.mock import patch

from spectryn.cli.completions import (
    BASH_COMPLETION,
    FISH_COMPLETION,
    POWERSHELL_COMPLETION,
    SUPPORTED_SHELLS,
    ZSH_COMPLETION,
    get_completion_script,
    get_installation_instructions,
    print_completion,
)


class TestGetCompletionScript:
    """Tests for get_completion_script function."""

    def test_bash_completion(self):
        """Test getting Bash completion script."""
        script = get_completion_script("bash")
        assert script is not None
        assert "#!/bin/bash" in script
        assert "_spectra_completions" in script
        assert "complete -F" in script

    def test_zsh_completion(self):
        """Test getting Zsh completion script."""
        script = get_completion_script("zsh")
        assert script is not None
        assert "#compdef spectra" in script
        assert "_spectra" in script
        assert "_arguments" in script

    def test_fish_completion(self):
        """Test getting Fish completion script."""
        script = get_completion_script("fish")
        assert script is not None
        assert "complete -c spectra" in script
        # Fish uses -l for long options
        assert "-l input" in script
        assert "-l epic" in script

    def test_powershell_completion(self):
        """Test getting PowerShell completion script."""
        script = get_completion_script("powershell")
        assert script is not None
        assert "Register-ArgumentCompleter" in script
        assert "spectra" in script
        assert "CompletionResult" in script

    def test_powershell_alias_pwsh(self):
        """Test that 'pwsh' alias works for PowerShell."""
        script = get_completion_script("pwsh")
        assert script is not None
        assert "Register-ArgumentCompleter" in script

    def test_case_insensitive(self):
        """Test that shell names are case-insensitive."""
        assert get_completion_script("BASH") is not None
        assert get_completion_script("Zsh") is not None
        assert get_completion_script("FISH") is not None
        assert get_completion_script("PowerShell") is not None
        assert get_completion_script("POWERSHELL") is not None

    def test_unknown_shell(self):
        """Test that unknown shell returns None."""
        assert get_completion_script("unknown") is None
        assert get_completion_script("") is None


class TestGetInstallationInstructions:
    """Tests for get_installation_instructions function."""

    def test_bash_instructions(self):
        """Test Bash installation instructions."""
        instructions = get_installation_instructions("bash")
        assert "bashrc" in instructions.lower()
        assert "eval" in instructions
        assert "spectra --completions bash" in instructions

    def test_zsh_instructions(self):
        """Test Zsh installation instructions."""
        instructions = get_installation_instructions("zsh")
        assert "zshrc" in instructions.lower()
        assert "compinit" in instructions

    def test_fish_instructions(self):
        """Test Fish installation instructions."""
        instructions = get_installation_instructions("fish")
        assert "config.fish" in instructions
        assert "completions" in instructions

    def test_powershell_instructions(self):
        """Test PowerShell installation instructions."""
        instructions = get_installation_instructions("powershell")
        assert "$PROFILE" in instructions
        assert "spectra --completions powershell" in instructions

    def test_pwsh_alias_instructions(self):
        """Test that pwsh alias works for PowerShell instructions."""
        instructions = get_installation_instructions("pwsh")
        assert "$PROFILE" in instructions

    def test_unknown_shell(self):
        """Test unknown shell instructions."""
        instructions = get_installation_instructions("unknown")
        assert "Unknown shell" in instructions
        assert "bash, zsh, fish, powershell" in instructions


class TestPrintCompletion:
    """Tests for print_completion function."""

    def test_print_bash(self, capsys):
        """Test printing Bash completion."""
        result = print_completion("bash")
        assert result is True

        captured = capsys.readouterr()
        assert "_spectra_completions" in captured.out

    def test_print_zsh(self, capsys):
        """Test printing Zsh completion."""
        result = print_completion("zsh")
        assert result is True

        captured = capsys.readouterr()
        assert "#compdef spectra" in captured.out

    def test_print_fish(self, capsys):
        """Test printing Fish completion."""
        result = print_completion("fish")
        assert result is True

        captured = capsys.readouterr()
        assert "complete -c spectra" in captured.out

    def test_print_powershell(self, capsys):
        """Test printing PowerShell completion."""
        result = print_completion("powershell")
        assert result is True

        captured = capsys.readouterr()
        assert "Register-ArgumentCompleter" in captured.out

    def test_print_unknown(self, capsys):
        """Test printing unknown shell returns error."""
        result = print_completion("unknown")
        assert result is False

        captured = capsys.readouterr()
        assert "Error" in captured.out
        assert "unknown" in captured.out


class TestSupportedShells:
    """Tests for SUPPORTED_SHELLS constant."""

    def test_supported_shells_list(self):
        """Test that supported shells list contains expected shells."""
        assert "bash" in SUPPORTED_SHELLS
        assert "zsh" in SUPPORTED_SHELLS
        assert "fish" in SUPPORTED_SHELLS
        assert "powershell" in SUPPORTED_SHELLS
        assert len(SUPPORTED_SHELLS) == 4


class TestCompletionScriptContent:
    """Tests for completion script content."""

    def test_bash_has_all_options(self):
        """Test Bash script includes all CLI options."""
        options = [
            "--input",
            "-f",
            "--input-dir",
            "-d",
            "--epic",
            "-e",
            "--execute",
            "-x",
            "--dry-run",
            "-n",
            "--phase",
            "--config",
            "-c",
            "--verbose",
            "-v",
            "--interactive",
            "-i",
            "--update-source",
            "--completions",
        ]
        for opt in options:
            assert opt in BASH_COMPLETION, f"Missing option: {opt}"

    def test_bash_has_phase_choices(self):
        """Test Bash script includes phase choices."""
        phases = ["all", "descriptions", "subtasks", "comments", "statuses"]
        for phase in phases:
            assert phase in BASH_COMPLETION, f"Missing phase: {phase}"

    def test_zsh_has_all_options(self):
        """Test Zsh script includes all CLI options."""
        options = [
            "--input",
            "--input-dir",
            "--epic",
            "--execute",
            "--dry-run",
            "--phase",
            "--config",
            "--verbose",
            "--interactive",
            "--update-source",
            "--completions",
        ]
        for opt in options:
            assert opt in ZSH_COMPLETION, f"Missing option: {opt}"

    def test_fish_has_all_options(self):
        """Test Fish script includes all CLI options."""
        # Fish uses -l for long options
        options = [
            "-l input",
            "-l input-dir",
            "-l epic",
            "-l execute",
            "-l dry-run",
            "-l phase",
            "-l config",
            "-l verbose",
            "-l interactive",
            "-l update-source",
            "-l completions",
        ]
        for opt in options:
            assert opt in FISH_COMPLETION, f"Missing option: {opt}"

    def test_fish_has_descriptions(self):
        """Test Fish script includes option descriptions."""
        descriptions = [
            "Path to input file",
            "Jira epic key",
            "Execute changes",
            "Which phase to run",
            "Interactive mode",
        ]
        for desc in descriptions:
            assert desc in FISH_COMPLETION, f"Missing description: {desc}"

    def test_powershell_has_all_options(self):
        """Test PowerShell script includes all CLI options."""
        options = [
            "--input",
            "--input-dir",
            "--epic",
            "--execute",
            "--dry-run",
            "--phase",
            "--config",
            "--verbose",
            "--interactive",
            "--completions",
            "--theme",
            "--no-emoji",
        ]
        for opt in options:
            assert opt in POWERSHELL_COMPLETION, f"Missing option: {opt}"

    def test_powershell_has_enum_values(self):
        """Test PowerShell script includes enum values for options."""
        # Phase values
        assert "all" in POWERSHELL_COMPLETION
        assert "descriptions" in POWERSHELL_COMPLETION
        assert "subtasks" in POWERSHELL_COMPLETION
        # Theme values
        assert "monokai" in POWERSHELL_COMPLETION
        assert "dracula" in POWERSHELL_COMPLETION
        # Output format values
        assert "json" in POWERSHELL_COMPLETION

    def test_powershell_has_descriptions(self):
        """Test PowerShell script includes option descriptions."""
        descriptions = [
            "Path to input file",
            "Jira epic key",
            "Execute changes",
            "Which phase to run",
            "Interactive mode",
            "Color theme",
        ]
        for desc in descriptions:
            assert desc in POWERSHELL_COMPLETION, f"Missing description: {desc}"


class TestCLICompletionsFlag:
    """Tests for the --completions CLI flag."""

    def test_completions_flag_bash(self, capsys):
        """Test --completions bash via CLI."""
        from spectryn.cli.app import main

        with patch("sys.argv", ["spectra", "--completions", "bash"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "_spectra_completions" in captured.out

    def test_completions_flag_zsh(self, capsys):
        """Test --completions zsh via CLI."""
        from spectryn.cli.app import main

        with patch("sys.argv", ["spectra", "--completions", "zsh"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "#compdef spectra" in captured.out

    def test_completions_flag_fish(self, capsys):
        """Test --completions fish via CLI."""
        from spectryn.cli.app import main

        with patch("sys.argv", ["spectra", "--completions", "fish"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "complete -c spectra" in captured.out

    def test_completions_flag_powershell(self, capsys):
        """Test --completions powershell via CLI."""
        from spectryn.cli.app import main

        with patch("sys.argv", ["spectra", "--completions", "powershell"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Register-ArgumentCompleter" in captured.out

    def test_completions_without_required_args(self, capsys):
        """Test that --completions works without --input and --epic."""
        from spectryn.cli.app import main

        # Should not raise error about missing required args
        with patch("sys.argv", ["spectra", "--completions", "bash"]):
            result = main()

        assert result == 0
