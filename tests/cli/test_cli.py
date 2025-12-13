"""
Tests for CLI argument parsing and output formatting.
"""

import io
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

from md2jira.cli.app import create_parser, main, validate_markdown, run_sync
from md2jira.cli.output import Console, Colors, Symbols
from md2jira.cli.exit_codes import ExitCode
from md2jira.application.sync import SyncResult


# =============================================================================
# Argument Parser Tests
# =============================================================================

class TestArgumentParser:
    """Tests for CLI argument parsing."""

    def test_required_arguments(self, cli_parser):
        """Test that --markdown and --epic are conditionally required.
        
        Note: Arguments are no longer required at the parser level to support
        --completions mode. Validation happens in main() for other modes.
        """
        # Parser accepts empty args (validation happens in main())
        args = cli_parser.parse_args([])
        assert args.markdown is None
        assert args.epic is None
        
        # Parser accepts partial args
        args = cli_parser.parse_args(["--markdown", "file.md"])
        assert args.markdown == "file.md"
        assert args.epic is None
        
        args = cli_parser.parse_args(["--epic", "PROJ-123"])
        assert args.epic == "PROJ-123"
        assert args.markdown is None

    def test_minimal_valid_args(self, cli_parser):
        """Test parsing with only required arguments."""
        args = cli_parser.parse_args(["--markdown", "epic.md", "--epic", "PROJ-123"])

        assert args.markdown == "epic.md"
        assert args.epic == "PROJ-123"
        assert args.execute is False  # default
        assert args.phase == "all"  # default

    def test_short_form_arguments(self, cli_parser):
        """Test short form argument aliases."""
        args = cli_parser.parse_args(["-m", "epic.md", "-e", "PROJ-123"])

        assert args.markdown == "epic.md"
        assert args.epic == "PROJ-123"

    def test_execute_flag(self, cli_parser):
        """Test --execute flag for live mode."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--execute"
        ])

        assert args.execute is True

    def test_execute_short_form(self, cli_parser):
        """Test -x short form for execute."""
        args = cli_parser.parse_args([
            "-m", "epic.md",
            "-e", "PROJ-123",
            "-x"
        ])

        assert args.execute is True

    def test_no_confirm_flag(self, cli_parser):
        """Test --no-confirm flag."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--no-confirm"
        ])

        assert args.no_confirm is True

    def test_phase_choices(self, cli_parser):
        """Test --phase argument with valid choices."""
        valid_phases = ["all", "descriptions", "subtasks", "comments", "statuses"]

        for phase in valid_phases:
            args = cli_parser.parse_args([
                "--markdown", "epic.md",
                "--epic", "PROJ-123",
                "--phase", phase
            ])
            assert args.phase == phase

    def test_phase_invalid_choice(self, cli_parser):
        """Test --phase with invalid choice raises error."""
        with pytest.raises(SystemExit):
            cli_parser.parse_args([
                "--markdown", "epic.md",
                "--epic", "PROJ-123",
                "--phase", "invalid"
            ])

    def test_story_filter(self, cli_parser):
        """Test --story filter argument."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--story", "US-001"
        ])

        assert args.story == "US-001"

    def test_jira_url_override(self, cli_parser):
        """Test --jira-url override."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--jira-url", "https://custom.atlassian.net"
        ])

        assert args.jira_url == "https://custom.atlassian.net"

    def test_project_override(self, cli_parser):
        """Test --project override."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--project", "NEWPROJ"
        ])

        assert args.project == "NEWPROJ"

    def test_verbose_flag(self, cli_parser):
        """Test --verbose flag."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--verbose"
        ])

        assert args.verbose is True

    def test_verbose_short_form(self, cli_parser):
        """Test -v short form for verbose."""
        args = cli_parser.parse_args([
            "-m", "epic.md",
            "-e", "PROJ-123",
            "-v"
        ])

        assert args.verbose is True

    def test_no_color_flag(self, cli_parser):
        """Test --no-color flag."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--no-color"
        ])

        assert args.no_color is True

    def test_log_format_choices(self, cli_parser):
        """Test --log-format argument with valid choices."""
        # Default is text
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
        ])
        assert args.log_format == "text"
        
        # JSON format
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--log-format", "json"
        ])
        assert args.log_format == "json"
        
        # Text format (explicit)
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--log-format", "text"
        ])
        assert args.log_format == "text"

    def test_log_file_argument(self, cli_parser):
        """Test --log-file argument."""
        # Default is None
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
        ])
        assert args.log_file is None
        
        # With log file path
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--log-file", "/var/log/md2jira.log"
        ])
        assert args.log_file == "/var/log/md2jira.log"

    def test_export_path(self, cli_parser):
        """Test --export argument."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--export", "results.json"
        ])

        assert args.export == "results.json"

    def test_validate_flag(self, cli_parser):
        """Test --validate mode flag."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--validate"
        ])

        assert args.validate is True

    def test_combined_arguments(self, cli_parser):
        """Test multiple arguments combined."""
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--execute",
            "--no-confirm",
            "--phase", "subtasks",
            "--story", "US-002",
            "--verbose",
            "--export", "out.json"
        ])

        assert args.markdown == "epic.md"
        assert args.epic == "PROJ-123"
        assert args.execute is True
        assert args.no_confirm is True
        assert args.phase == "subtasks"
        assert args.story == "US-002"
        assert args.verbose is True
        assert args.export == "out.json"

    def test_backup_options(self, cli_parser):
        """Test backup-related arguments."""
        # --no-backup flag
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--no-backup"
        ])
        assert args.no_backup is True
        
        # --backup-dir
        args = cli_parser.parse_args([
            "--markdown", "epic.md",
            "--epic", "PROJ-123",
            "--backup-dir", "/custom/backups"
        ])
        assert args.backup_dir == "/custom/backups"
        
        # --list-backups
        args = cli_parser.parse_args(["--list-backups", "--epic", "PROJ-123"])
        assert args.list_backups is True

    def test_restore_backup_option(self, cli_parser):
        """Test --restore-backup argument."""
        args = cli_parser.parse_args([
            "--restore-backup", "PROJ-123_20251212_123456_abc12345",
            "--execute"
        ])
        assert args.restore_backup == "PROJ-123_20251212_123456_abc12345"
        assert args.execute is True

    def test_diff_backup_option(self, cli_parser):
        """Test --diff-backup argument."""
        args = cli_parser.parse_args([
            "--diff-backup", "PROJ-123_20251212_123456_abc12345"
        ])
        assert args.diff_backup == "PROJ-123_20251212_123456_abc12345"

    def test_diff_latest_option(self, cli_parser):
        """Test --diff-latest argument."""
        args = cli_parser.parse_args([
            "--diff-latest",
            "--epic", "PROJ-123"
        ])
        assert args.diff_latest is True

    def test_rollback_option(self, cli_parser):
        """Test --rollback argument."""
        args = cli_parser.parse_args([
            "--rollback",
            "--epic", "PROJ-123",
            "--execute"
        ])
        assert args.rollback is True
        assert args.epic == "PROJ-123"
        assert args.execute is True


# =============================================================================
# Console Output Tests
# =============================================================================

class TestConsoleOutput:
    """Tests for Console output formatting."""

    @pytest.fixture
    def color_console(self):
        """Create a console with colors enabled (forced)."""
        console = Console(color=True, verbose=False)
        console.color = True  # Force color even if not a TTY
        return console

    def test_console_init_defaults(self):
        """Test Console initialization defaults."""
        console = Console()
        assert console.verbose is False

    def test_console_verbose_mode(self):
        """Test Console verbose flag."""
        console = Console(verbose=True)
        assert console.verbose is True

    def test_print_output(self, console, capsys):
        """Test basic print output."""
        console.print("Hello World")
        captured = capsys.readouterr()
        assert "Hello World" in captured.out

    def test_print_empty_line(self, console, capsys):
        """Test printing empty line."""
        console.print()
        captured = capsys.readouterr()
        assert captured.out == "\n"

    def test_header_output(self, console, capsys):
        """Test header formatting."""
        console.header("Test Header")
        captured = capsys.readouterr()
        assert "Test Header" in captured.out

    def test_section_output(self, console, capsys):
        """Test section formatting."""
        console.section("Test Section")
        captured = capsys.readouterr()
        assert "Test Section" in captured.out
        assert Symbols.ARROW in captured.out

    def test_success_output(self, console, capsys):
        """Test success message formatting."""
        console.success("Operation succeeded")
        captured = capsys.readouterr()
        assert "Operation succeeded" in captured.out
        assert Symbols.CHECK in captured.out

    def test_error_output(self, console, capsys):
        """Test error message formatting."""
        console.error("Something went wrong")
        captured = capsys.readouterr()
        assert "Something went wrong" in captured.out
        assert Symbols.CROSS in captured.out

    def test_warning_output(self, console, capsys):
        """Test warning message formatting."""
        console.warning("Be careful")
        captured = capsys.readouterr()
        assert "Be careful" in captured.out
        assert Symbols.WARN in captured.out

    def test_info_output(self, console, capsys):
        """Test info message formatting."""
        console.info("Information")
        captured = capsys.readouterr()
        assert "Information" in captured.out
        assert Symbols.INFO in captured.out

    def test_detail_output(self, console, capsys):
        """Test detail message formatting."""
        console.detail("Some detail")
        captured = capsys.readouterr()
        assert "Some detail" in captured.out

    def test_debug_output_hidden_by_default(self, console, capsys):
        """Test debug messages hidden when not verbose."""
        console.debug("Debug info")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_debug_output_visible_in_verbose(self, verbose_console, capsys):
        """Test debug messages visible in verbose mode."""
        verbose_console.debug("Debug info")
        captured = capsys.readouterr()
        assert "Debug info" in captured.out
        assert "[DEBUG]" in captured.out

    def test_item_output_no_status(self, console, capsys):
        """Test item output without status."""
        console.item("List item")
        captured = capsys.readouterr()
        assert "List item" in captured.out
        assert Symbols.DOT in captured.out

    def test_item_output_ok_status(self, console, capsys):
        """Test item output with ok status."""
        console.item("Passed item", status="ok")
        captured = capsys.readouterr()
        assert "Passed item" in captured.out
        assert Symbols.CHECK in captured.out

    def test_item_output_skip_status(self, console, capsys):
        """Test item output with skip status."""
        console.item("Skipped item", status="skip")
        captured = capsys.readouterr()
        assert "Skipped item" in captured.out
        assert "SKIP" in captured.out

    def test_item_output_fail_status(self, console, capsys):
        """Test item output with fail status."""
        console.item("Failed item", status="fail")
        captured = capsys.readouterr()
        assert "Failed item" in captured.out
        assert Symbols.CROSS in captured.out

    def test_item_output_custom_status(self, console, capsys):
        """Test item output with custom status."""
        console.item("Custom item", status="CUSTOM")
        captured = capsys.readouterr()
        assert "Custom item" in captured.out
        assert "CUSTOM" in captured.out

    def test_table_output(self, console, capsys):
        """Test table formatting."""
        headers = ["Name", "Value"]
        rows = [
            ["Item 1", "100"],
            ["Item 2", "200"],
        ]
        console.table(headers, rows)
        captured = capsys.readouterr()

        assert "Name" in captured.out
        assert "Value" in captured.out
        assert "Item 1" in captured.out
        assert "100" in captured.out
        assert "Item 2" in captured.out
        assert "200" in captured.out

    def test_dry_run_banner(self, console, capsys):
        """Test dry-run banner output."""
        console.dry_run_banner()
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        assert "No changes" in captured.out

    def test_sync_result_success(self, console, capsys):
        """Test sync result display for successful sync."""
        result = SyncResult(
            success=True,
            dry_run=True,
            stories_matched=5,
            stories_updated=3,
            subtasks_created=10,
        )
        console.sync_result(result)
        captured = capsys.readouterr()

        assert "5" in captured.out
        assert "3" in captured.out
        assert "10" in captured.out
        assert "successfully" in captured.out

    def test_sync_result_with_errors(self, console, capsys):
        """Test sync result display with errors."""
        result = SyncResult(success=False)
        result.add_error("First error")
        result.add_error("Second error")

        console.sync_result(result)
        captured = capsys.readouterr()

        assert "error" in captured.out.lower()
        assert "First error" in captured.out

    def test_sync_result_with_warnings(self, console, capsys):
        """Test sync result display with warnings."""
        result = SyncResult()
        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        console.sync_result(result)
        captured = capsys.readouterr()

        assert "warning" in captured.out.lower()

    def test_color_disabled_no_ansi_codes(self, console):
        """Test that color codes are not included when disabled."""
        text = console._c("test", Colors.RED)
        assert "\033[" not in text
        assert text == "test"

    def test_color_enabled_includes_ansi_codes(self, color_console):
        """Test that color codes are included when enabled."""
        text = color_console._c("test", Colors.RED)
        assert "\033[" in text
        assert Colors.RESET in text

    def test_confirm_yes(self, console):
        """Test confirm returns True for 'y' input."""
        with patch("builtins.input", return_value="y"):
            result = console.confirm("Proceed?")
            assert result is True

    def test_confirm_yes_full(self, console):
        """Test confirm returns True for 'yes' input."""
        with patch("builtins.input", return_value="yes"):
            result = console.confirm("Proceed?")
            assert result is True

    def test_confirm_no(self, console):
        """Test confirm returns False for 'n' input."""
        with patch("builtins.input", return_value="n"):
            result = console.confirm("Proceed?")
            assert result is False

    def test_confirm_empty(self, console):
        """Test confirm returns False for empty input."""
        with patch("builtins.input", return_value=""):
            result = console.confirm("Proceed?")
            assert result is False

    def test_confirm_keyboard_interrupt(self, console):
        """Test confirm returns False on KeyboardInterrupt."""
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = console.confirm("Proceed?")
            assert result is False

    def test_confirm_eof_error(self, console):
        """Test confirm returns False on EOFError."""
        with patch("builtins.input", side_effect=EOFError):
            result = console.confirm("Proceed?")
            assert result is False


# =============================================================================
# Symbols and Colors Tests
# =============================================================================

class TestSymbolsAndColors:
    """Tests for Symbols and Colors constants."""

    def test_symbols_are_defined(self):
        """Test that all expected symbols are defined."""
        assert Symbols.CHECK == "✓"
        assert Symbols.CROSS == "✗"
        assert Symbols.ARROW == "→"
        assert Symbols.DOT == "•"
        assert Symbols.WARN == "⚠"
        assert Symbols.INFO == "ℹ"
        assert Symbols.ROCKET == "🚀"
        assert Symbols.GEAR == "⚙"

    def test_colors_are_ansi_codes(self):
        """Test that colors are valid ANSI escape codes."""
        assert Colors.RESET.startswith("\033[")
        assert Colors.RED.startswith("\033[")
        assert Colors.GREEN.startswith("\033[")
        assert Colors.YELLOW.startswith("\033[")
        assert Colors.BLUE.startswith("\033[")


# =============================================================================
# Main Function Tests
# =============================================================================

class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_main_missing_args_returns_error(self):
        """Test main returns error code when args missing."""
        with patch("sys.argv", ["md2jira"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_main_validate_mode(self):
        """Test main in validate mode."""
        with patch("sys.argv", [
            "md2jira",
            "--markdown", "test.md",
            "--epic", "PROJ-123",
            "--validate"
        ]):
            with patch("md2jira.cli.app.validate_markdown") as mock_validate:
                mock_validate.return_value = True
                result = main()
                assert result == ExitCode.SUCCESS
                mock_validate.assert_called_once()

    def test_main_keyboard_interrupt(self):
        """Test main handles KeyboardInterrupt gracefully."""
        with patch("sys.argv", [
            "md2jira",
            "--markdown", "test.md",
            "--epic", "PROJ-123",
            "--validate"
        ]):
            with patch("md2jira.cli.app.validate_markdown") as mock_validate:
                mock_validate.side_effect = KeyboardInterrupt()
                result = main()
                assert result == ExitCode.SIGINT

    def test_main_unexpected_error(self):
        """Test main handles unexpected errors gracefully."""
        with patch("sys.argv", [
            "md2jira",
            "--markdown", "test.md",
            "--epic", "PROJ-123",
            "--validate"
        ]):
            with patch("md2jira.cli.app.validate_markdown") as mock_validate:
                mock_validate.side_effect = RuntimeError("Unexpected")
                result = main()
                assert result == ExitCode.ERROR


# =============================================================================
# Validate Markdown Tests
# =============================================================================

class TestValidateMarkdown:
    """Tests for markdown validation function."""

    def test_validate_markdown_success(self, console, capsys):
        """Test validation with valid markdown."""
        with patch("md2jira.cli.app.MarkdownParser") as MockParser:
            mock_parser = MockParser.return_value
            mock_parser.validate.return_value = []
            mock_parser.parse_stories.return_value = []

            result = validate_markdown(console, "valid.md")

            assert result is True
            captured = capsys.readouterr()
            assert "valid" in captured.out.lower()

    def test_validate_markdown_with_errors(self, console, capsys):
        """Test validation with invalid markdown."""
        with patch("md2jira.cli.app.MarkdownParser") as MockParser:
            mock_parser = MockParser.return_value
            mock_parser.validate.return_value = ["Error 1", "Error 2"]

            result = validate_markdown(console, "invalid.md")

            assert result is False
            captured = capsys.readouterr()
            assert "Error 1" in captured.out
            assert "Error 2" in captured.out

    def test_validate_markdown_shows_story_count(self, console, capsys):
        """Test validation shows story count on success."""
        with patch("md2jira.cli.app.MarkdownParser") as MockParser:
            mock_parser = MockParser.return_value
            mock_parser.validate.return_value = []

            # Create mock stories
            mock_story = Mock()
            mock_story.subtasks = [Mock(), Mock()]
            mock_story.commits = [Mock()]
            mock_parser.parse_stories.return_value = [mock_story]

            result = validate_markdown(console, "valid.md")

            assert result is True
            captured = capsys.readouterr()
            assert "1" in captured.out  # 1 story
            assert "2" in captured.out  # 2 subtasks


# =============================================================================
# Run Sync Tests
# =============================================================================

class TestRunSync:
    """Tests for the run_sync function."""

    def test_run_sync_config_errors(self, console, base_cli_args, capsys):
        """Test run_sync returns error on config validation failure."""
        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider:
            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = ["Missing JIRA_URL"]

            result = run_sync(console, base_cli_args)

            assert result == ExitCode.CONFIG_ERROR
            captured = capsys.readouterr()
            assert "Missing JIRA_URL" in captured.out

    def test_run_sync_markdown_not_found(self, console, base_cli_args, capsys):
        """Test run_sync returns error when markdown file not found."""
        base_cli_args.markdown = "/nonexistent/path/epic.md"

        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider:
            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = []
            mock_provider.config_file_path = None
            mock_provider.load.return_value = Mock(
                sync=Mock(dry_run=True),
                tracker=Mock()
            )

            result = run_sync(console, base_cli_args)

            assert result == ExitCode.FILE_NOT_FOUND
            captured = capsys.readouterr()
            assert "not found" in captured.out.lower()

    def test_run_sync_connection_failure(self, console, base_cli_args, capsys, tmp_path):
        """Test run_sync returns error on Jira connection failure."""
        # Create temp markdown file
        md_file = tmp_path / "epic.md"
        md_file.write_text("# Test Epic")
        base_cli_args.markdown = str(md_file)

        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider, \
             patch("md2jira.cli.app.JiraAdapter") as MockAdapter:

            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = []
            mock_provider.config_file_path = None
            mock_provider.load.return_value = Mock(
                sync=Mock(dry_run=True),
                tracker=Mock()
            )

            mock_adapter = MockAdapter.return_value
            mock_adapter.test_connection.return_value = False

            result = run_sync(console, base_cli_args)

            assert result == ExitCode.CONNECTION_ERROR
            captured = capsys.readouterr()
            assert "Failed to connect" in captured.out

    def test_run_sync_user_cancellation(self, console, base_cli_args, capsys, tmp_path):
        """Test run_sync handles user cancellation."""
        md_file = tmp_path / "epic.md"
        md_file.write_text("# Test Epic")
        base_cli_args.markdown = str(md_file)
        base_cli_args.execute = True
        base_cli_args.no_confirm = False

        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider, \
             patch("md2jira.cli.app.JiraAdapter") as MockAdapter, \
             patch("md2jira.application.sync.StateStore") as MockStateStore:

            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = []
            mock_provider.config_file_path = None
            mock_provider.load.return_value = Mock(
                sync=Mock(dry_run=False),
                tracker=Mock()
            )

            mock_adapter = MockAdapter.return_value
            mock_adapter.test_connection.return_value = True
            mock_adapter.get_current_user.return_value = {"displayName": "Test User"}
            
            MockStateStore.return_value.find_latest_resumable.return_value = None

            # Mock console.confirm to return False
            with patch.object(console, "confirm", return_value=False):
                result = run_sync(console, base_cli_args)

            assert result == ExitCode.CANCELLED
            captured = capsys.readouterr()
            assert "Cancelled" in captured.out

    def test_run_sync_success(self, console, base_cli_args, capsys, tmp_path):
        """Test successful sync execution."""
        md_file = tmp_path / "epic.md"
        md_file.write_text("# Test Epic")
        base_cli_args.markdown = str(md_file)

        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider, \
             patch("md2jira.cli.app.JiraAdapter") as MockAdapter, \
             patch("md2jira.cli.app.SyncOrchestrator") as MockOrchestrator, \
             patch("md2jira.application.sync.StateStore") as MockStateStore:

            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = []
            mock_provider.config_file_path = None
            mock_provider.load.return_value = Mock(
                sync=Mock(dry_run=True),
                tracker=Mock()
            )

            mock_adapter = MockAdapter.return_value
            mock_adapter.test_connection.return_value = True
            mock_adapter.get_current_user.return_value = {"displayName": "Test User"}

            mock_orchestrator = MockOrchestrator.return_value
            mock_orchestrator.sync_resumable.return_value = SyncResult(
                success=True,
                dry_run=True,
                stories_matched=3,
            )
            
            MockStateStore.return_value.find_latest_resumable.return_value = None

            result = run_sync(console, base_cli_args)

            assert result == ExitCode.SUCCESS

    def test_run_sync_with_export(self, console, base_cli_args, capsys, tmp_path):
        """Test sync with JSON export."""
        md_file = tmp_path / "epic.md"
        md_file.write_text("# Test Epic")
        base_cli_args.markdown = str(md_file)

        export_file = tmp_path / "results.json"
        base_cli_args.export = str(export_file)

        with patch("md2jira.cli.app.EnvironmentConfigProvider") as MockProvider, \
             patch("md2jira.cli.app.JiraAdapter") as MockAdapter, \
             patch("md2jira.cli.app.SyncOrchestrator") as MockOrchestrator, \
             patch("md2jira.application.sync.StateStore") as MockStateStore:

            mock_provider = MockProvider.return_value
            mock_provider.validate.return_value = []
            mock_provider.config_file_path = None
            mock_provider.load.return_value = Mock(
                sync=Mock(dry_run=True),
                tracker=Mock()
            )

            mock_adapter = MockAdapter.return_value
            mock_adapter.test_connection.return_value = True
            mock_adapter.get_current_user.return_value = {"displayName": "Test User"}

            mock_orchestrator = MockOrchestrator.return_value
            mock_orchestrator.sync_resumable.return_value = SyncResult(
                success=True,
                dry_run=True,
                stories_matched=3,
            )
            
            MockStateStore.return_value.find_latest_resumable.return_value = None

            result = run_sync(console, base_cli_args)

            assert result == ExitCode.SUCCESS
            assert export_file.exists()

            import json
            with open(export_file) as f:
                data = json.load(f)
            assert data["success"] is True
            assert data["stats"]["stories_matched"] == 3

