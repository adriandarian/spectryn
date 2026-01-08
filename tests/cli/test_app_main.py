"""
Additional tests for CLI app.py to improve coverage.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectryn.cli.app import create_parser, main
from spectryn.cli.exit_codes import ExitCode


class TestCreateParser:
    """Tests for create_parser function."""

    def test_parser_creation(self):
        """Test parser is created successfully."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "spectra"

    def test_parser_has_epilog(self):
        """Test parser has help examples in epilog."""
        parser = create_parser()
        assert "Examples" in parser.epilog

    def test_parser_completions_flag(self):
        """Test --completions argument."""
        parser = create_parser()
        args = parser.parse_args(["--completions", "bash"])
        assert args.completions == "bash"

    def test_parser_init_flag(self):
        """Test --init argument."""
        parser = create_parser()
        args = parser.parse_args(["--init"])
        assert args.init is True

    def test_parser_generate_flag(self):
        """Test --generate argument."""
        parser = create_parser()
        args = parser.parse_args(["--generate", "--epic", "PROJ-123"])
        assert args.generate is True
        assert args.epic == "PROJ-123"

    def test_parser_pull_flag(self):
        """Test --pull argument."""
        parser = create_parser()
        args = parser.parse_args(["--pull", "--epic", "PROJ-123"])
        assert args.pull is True

    def test_parser_watch_flag(self):
        """Test --watch argument."""
        parser = create_parser()
        args = parser.parse_args(["--watch", "-f", "test.md", "-e", "PROJ-123"])
        assert args.watch is True

    def test_parser_schedule_flag(self):
        """Test --schedule argument."""
        parser = create_parser()
        args = parser.parse_args(["--schedule", "5m", "-f", "test.md", "-e", "PROJ-123"])
        assert args.schedule == "5m"

    def test_parser_webhook_flag(self):
        """Test --webhook argument."""
        parser = create_parser()
        args = parser.parse_args(["--webhook", "-e", "PROJ-123"])
        assert args.webhook is True

    def test_parser_multi_epic_flag(self):
        """Test --multi-epic argument."""
        parser = create_parser()
        args = parser.parse_args(["--multi-epic", "-f", "roadmap.md"])
        assert args.multi_epic is True

    def test_parser_list_epics_flag(self):
        """Test --list-epics argument."""
        parser = create_parser()
        args = parser.parse_args(["--list-epics", "-f", "roadmap.md"])
        assert args.list_epics is True

    def test_parser_sync_links_flag(self):
        """Test --sync-links argument."""
        parser = create_parser()
        args = parser.parse_args(["--sync-links", "-f", "test.md", "-e", "PROJ-123"])
        assert args.sync_links is True

    def test_parser_analyze_links_flag(self):
        """Test --analyze-links argument."""
        parser = create_parser()
        args = parser.parse_args(["--analyze-links", "-f", "test.md", "-e", "PROJ-123"])
        assert args.analyze_links is True

    def test_parser_dashboard_flag(self):
        """Test --dashboard argument."""
        parser = create_parser()
        args = parser.parse_args(["--dashboard", "-f", "test.md", "-e", "PROJ-123"])
        assert args.dashboard is True

    def test_parser_interactive_flag(self):
        """Test --interactive argument."""
        parser = create_parser()
        args = parser.parse_args(["--interactive", "-f", "test.md", "-e", "PROJ-123"])
        assert args.interactive is True

    def test_parser_input_dir_flag(self):
        """Test -d/--input-dir argument."""
        parser = create_parser()
        args = parser.parse_args(["-d", "./docs/plan", "-e", "PROJ-123"])
        assert args.input_dir == "./docs/plan"

    def test_parser_list_files_flag(self):
        """Test --list-files argument."""
        parser = create_parser()
        args = parser.parse_args(["-d", "./docs/plan", "--list-files"])
        assert args.list_files is True

    def test_parser_run_now_flag(self):
        """Test --run-now argument."""
        parser = create_parser()
        args = parser.parse_args(
            ["--schedule", "1h", "-f", "test.md", "-e", "PROJ-123", "--run-now"]
        )
        assert args.run_now is True

    def test_parser_debounce_flag(self):
        """Test --debounce argument."""
        parser = create_parser()
        args = parser.parse_args(["--watch", "-f", "test.md", "-e", "PROJ-123", "--debounce", "5"])
        assert args.debounce == 5

    def test_parser_webhook_port_flag(self):
        """Test --webhook-port argument."""
        parser = create_parser()
        args = parser.parse_args(["--webhook", "-e", "PROJ-123", "--webhook-port", "9000"])
        assert args.webhook_port == 9000

    def test_parser_webhook_secret_flag(self):
        """Test --webhook-secret argument."""
        parser = create_parser()
        args = parser.parse_args(["--webhook", "-e", "PROJ-123", "--webhook-secret", "mysecret"])
        assert args.webhook_secret == "mysecret"

    def test_parser_otel_flags(self):
        """Test OpenTelemetry flags."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "-f",
                "test.md",
                "-e",
                "PROJ-123",
                "--otel-enable",
                "--otel-endpoint",
                "http://localhost:4317",
            ]
        )
        assert args.otel_enable is True
        assert args.otel_endpoint == "http://localhost:4317"

    def test_parser_prometheus_flags(self):
        """Test Prometheus flags."""
        parser = create_parser()
        args = parser.parse_args(
            ["-f", "test.md", "-e", "PROJ-123", "--prometheus", "--prometheus-port", "9090"]
        )
        assert args.prometheus is True
        assert args.prometheus_port == 9090

    def test_parser_health_flags(self):
        """Test health check flags."""
        parser = create_parser()
        args = parser.parse_args(
            ["-f", "test.md", "-e", "PROJ-123", "--health", "--health-port", "8080"]
        )
        assert args.health is True
        assert args.health_port == 8080

    def test_parser_analytics_flags(self):
        """Test analytics flags."""
        parser = create_parser()
        args = parser.parse_args(["--analytics-show"])
        assert args.analytics_show is True

        args = parser.parse_args(["--analytics-clear"])
        assert args.analytics_clear is True

    def test_parser_quiet_flag(self):
        """Test --quiet flag."""
        parser = create_parser()
        args = parser.parse_args(["-f", "test.md", "-e", "PROJ-123", "--quiet"])
        assert args.quiet is True

    def test_parser_config_flag(self):
        """Test --config flag."""
        parser = create_parser()
        args = parser.parse_args(["-f", "test.md", "-e", "PROJ-123", "--config", "config.yaml"])
        assert args.config == "config.yaml"

    def test_parser_list_ai_tools_flag(self):
        """Test --list-ai-tools flag."""
        parser = create_parser()
        args = parser.parse_args(["--list-ai-tools"])
        assert args.list_ai_tools is True


class TestMainCompletions:
    """Tests for main with completions mode."""

    def test_main_completions_bash(self):
        """Test completions mode with bash."""
        with (
            patch("sys.argv", ["spectra", "--completions", "bash"]),
            patch("spectryn.cli.completions.print_completion") as mock_print,
        ):
            mock_print.return_value = True
            result = main()
            assert result == ExitCode.SUCCESS

    def test_main_completions_failure(self):
        """Test completions mode failure with valid shell but failed generation."""
        with (
            patch("sys.argv", ["spectra", "--completions", "bash"]),
            patch("spectryn.cli.completions.print_completion") as mock_print,
        ):
            mock_print.return_value = False
            result = main()
            assert result == ExitCode.ERROR


class TestMainInit:
    """Tests for main with init mode."""

    def test_main_init(self):
        """Test init mode."""
        with (
            patch("sys.argv", ["spectra", "--init"]),
            patch("spectryn.cli.init.run_init") as mock_run_init,
        ):
            mock_run_init.return_value = ExitCode.SUCCESS
            result = main()
            assert result == ExitCode.SUCCESS
            mock_run_init.assert_called_once()


class TestMainGenerate:
    """Tests for main with generate mode."""

    def test_main_generate(self):
        """Test generate mode."""
        with (
            patch("sys.argv", ["spectra", "--generate", "--epic", "PROJ-123"]),
            patch("spectryn.cli.generate.run_generate") as mock_run_gen,
        ):
            mock_run_gen.return_value = ExitCode.SUCCESS
            result = main()
            assert result == ExitCode.SUCCESS
            mock_run_gen.assert_called_once()

    def test_main_generate_no_epic(self):
        """Test generate mode without epic exits with error."""
        with patch("sys.argv", ["spectra", "--generate"]):
            # parser.error() causes SystemExit(2)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2


class TestMainListAiTools:
    """Tests for main with list-ai-tools mode."""

    def test_main_list_ai_tools(self):
        """Test list-ai-tools mode."""
        with (
            patch("sys.argv", ["spectra", "--list-ai-tools"]),
            patch("spectryn.cli.ai_fix.detect_ai_tools") as mock_detect,
            patch("spectryn.cli.ai_fix.format_ai_tools_list") as mock_format,
        ):
            mock_detect.return_value = []
            mock_format.return_value = ""
            result = main()
            assert result == ExitCode.SUCCESS


class TestMainAnalytics:
    """Tests for main with analytics modes."""

    def test_main_analytics_show(self):
        """Test analytics show mode."""
        with (
            patch("sys.argv", ["spectra", "--analytics-show"]),
            patch("spectryn.cli.analytics.configure_analytics") as mock_configure,
            patch("spectryn.cli.analytics.show_analytics_info") as mock_info,
            patch("spectryn.cli.analytics.format_analytics_display") as mock_format,
        ):
            mock_manager = MagicMock()
            mock_manager.get_display_data.return_value = {}
            mock_configure.return_value = mock_manager
            mock_info.return_value = "info"
            mock_format.return_value = "formatted"
            result = main()
            assert result == ExitCode.SUCCESS

    def test_main_analytics_clear(self):
        """Test analytics clear mode."""
        with (
            patch("sys.argv", ["spectra", "--analytics-clear"]),
            patch("spectryn.cli.analytics.configure_analytics") as mock_configure,
        ):
            mock_manager = MagicMock()
            mock_manager.clear_data.return_value = True
            mock_configure.return_value = mock_manager
            result = main()
            assert result == ExitCode.SUCCESS


class TestMainValidation:
    """Tests for main validation behavior."""

    def test_main_validation_missing_file_and_epic(self):
        """Test validation error when both file and epic are missing."""
        with patch("sys.argv", ["spectra"]):
            # parser.error() causes SystemExit(2)
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    def test_main_validation_validate_only_needs_file(self):
        """Test validate mode only needs file."""
        with (
            patch("sys.argv", ["spectra", "--validate", "-f", "test.md"]),
            patch("spectryn.cli.app.validate_markdown") as mock_validate,
        ):
            mock_validate.return_value = ExitCode.SUCCESS
            result = main()
            assert result == ExitCode.SUCCESS
