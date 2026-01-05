"""
Tests for CLI output module.
"""

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from spectra.cli.output import (
    Colors,
    ColorTheme,
    Console,
    Symbols,
    ThemeName,
    format_diff_indicator,
    format_priority_text,
    format_score_text,
    format_status_text,
    get_accessibility_mode,
    get_emoji_mode,
    get_status_indicator,
    get_symbol,
    get_theme,
    get_theme_name,
    list_themes,
    set_accessibility_mode,
    set_emoji_mode,
    set_theme,
)


class TestColors:
    """Tests for Colors class."""

    def test_color_codes_defined(self):
        """Test that all color codes are defined."""
        assert Colors.RESET == "\033[0m"
        assert Colors.BOLD == "\033[1m"
        assert Colors.DIM == "\033[2m"
        assert Colors.RED == "\033[31m"
        assert Colors.GREEN == "\033[32m"
        assert Colors.YELLOW == "\033[33m"
        assert Colors.BLUE == "\033[34m"
        assert Colors.MAGENTA == "\033[35m"
        assert Colors.CYAN == "\033[36m"
        assert Colors.WHITE == "\033[37m"

    def test_background_colors_defined(self):
        """Test that background colors are defined."""
        assert Colors.BG_RED == "\033[41m"
        assert Colors.BG_GREEN == "\033[42m"
        assert Colors.BG_YELLOW == "\033[43m"
        assert Colors.BG_BLUE == "\033[44m"


class TestSymbols:
    """Tests for Symbols class."""

    @pytest.fixture(autouse=True)
    def reset_emoji_mode(self):
        """Reset emoji mode to default before and after each test."""
        set_emoji_mode(True)
        yield
        set_emoji_mode(True)

    def test_status_symbols_defined(self):
        """Test that status symbols are defined."""
        assert Symbols.CHECK == "✓"
        assert Symbols.CROSS == "✗"
        assert Symbols.ARROW == "→"
        assert Symbols.DOT == "•"
        assert Symbols.WARN == "⚠"
        assert Symbols.INFO == "ℹ"

    def test_emoji_symbols_defined(self):
        """Test that emoji symbols are defined."""
        assert Symbols.ROCKET == "🚀"
        assert Symbols.GEAR == "⚙"
        assert Symbols.FILE == "📄"
        assert Symbols.FOLDER == "📁"
        assert Symbols.LINK == "🔗"

    def test_box_drawing_symbols_defined(self):
        """Test that box drawing symbols are defined."""
        assert Symbols.BOX_TL == "╭"
        assert Symbols.BOX_TR == "╮"
        assert Symbols.BOX_BL == "╰"
        assert Symbols.BOX_BR == "╯"
        assert Symbols.BOX_H == "─"
        assert Symbols.BOX_V == "│"

    def test_additional_emoji_symbols_defined(self):
        """Test that additional emoji symbols are defined."""
        assert Symbols.CHART == "📊"
        assert Symbols.DOWNLOAD == "📥"
        assert Symbols.SYNC == "🔄"
        assert Symbols.DIFF == "📝"


class TestEmojiToggle:
    """Tests for emoji toggle functionality."""

    @pytest.fixture(autouse=True)
    def reset_emoji_mode(self):
        """Reset emoji mode to default before and after each test."""
        set_emoji_mode(True)
        yield
        set_emoji_mode(True)

    def test_emoji_mode_enabled_by_default(self):
        """Test that emoji mode is enabled by default."""
        assert get_emoji_mode() is True

    def test_set_emoji_mode_off(self):
        """Test disabling emoji mode."""
        set_emoji_mode(False)
        assert get_emoji_mode() is False

    def test_set_emoji_mode_on(self):
        """Test enabling emoji mode."""
        set_emoji_mode(False)
        set_emoji_mode(True)
        assert get_emoji_mode() is True

    def test_symbols_with_emoji_mode(self):
        """Test Symbols class returns emojis when enabled."""
        set_emoji_mode(True)
        assert Symbols.CHECK == "✓"
        assert Symbols.ROCKET == "🚀"
        assert Symbols.GEAR == "⚙"

    def test_symbols_without_emoji_mode(self):
        """Test Symbols class returns ASCII when disabled."""
        set_emoji_mode(False)
        assert Symbols.CHECK == "[OK]"
        assert Symbols.CROSS == "[X]"
        assert Symbols.ARROW == "->"
        assert Symbols.DOT == "*"
        assert Symbols.WARN == "[!]"
        assert Symbols.INFO == "[i]"
        assert Symbols.ROCKET == "[>]"
        assert Symbols.GEAR == "[*]"
        assert Symbols.FILE == "[F]"
        assert Symbols.FOLDER == "[D]"
        assert Symbols.LINK == "[L]"

    def test_get_symbol_with_emoji_mode(self):
        """Test get_symbol function returns emojis when enabled."""
        set_emoji_mode(True)
        assert get_symbol("CHECK") == "✓"
        assert get_symbol("ROCKET") == "🚀"

    def test_get_symbol_without_emoji_mode(self):
        """Test get_symbol function returns ASCII when disabled."""
        set_emoji_mode(False)
        assert get_symbol("CHECK") == "[OK]"
        assert get_symbol("ROCKET") == "[>]"

    def test_box_drawing_unaffected_by_emoji_mode(self):
        """Test box drawing characters are not affected by emoji toggle."""
        set_emoji_mode(True)
        assert Symbols.BOX_TL == "╭"
        assert Symbols.BOX_H == "─"

        set_emoji_mode(False)
        assert Symbols.BOX_TL == "╭"
        assert Symbols.BOX_H == "─"

    def test_symbols_class_set_emoji_mode(self):
        """Test Symbols class method for setting emoji mode."""
        Symbols.set_emoji_mode(False)
        assert Symbols.get_emoji_mode() is False

        Symbols.set_emoji_mode(True)
        assert Symbols.get_emoji_mode() is True

    def test_unknown_symbol_returns_name(self):
        """Test that unknown symbol names return the name itself."""
        assert get_symbol("UNKNOWN_SYMBOL") == "UNKNOWN_SYMBOL"

    def test_additional_ascii_symbols(self):
        """Test additional ASCII symbols when emoji mode is off."""
        set_emoji_mode(False)
        assert Symbols.CHART == "[#]"
        assert Symbols.DOWNLOAD == "[v]"
        assert Symbols.SYNC == "[~]"
        assert Symbols.DIFF == "[D]"


class TestColorThemes:
    """Tests for color theme functionality."""

    @pytest.fixture(autouse=True)
    def reset_theme(self):
        """Reset theme to default before and after each test."""
        set_theme(ThemeName.DEFAULT)
        yield
        set_theme(ThemeName.DEFAULT)

    def test_default_theme(self):
        """Test that default theme is set initially."""
        assert get_theme_name() == "default"

    def test_set_theme_by_enum(self):
        """Test setting theme by enum value."""
        set_theme(ThemeName.MONOKAI)
        assert get_theme_name() == "monokai"

    def test_set_theme_by_string(self):
        """Test setting theme by string name."""
        set_theme("dracula")
        assert get_theme_name() == "dracula"

    def test_set_theme_case_insensitive(self):
        """Test theme names are case insensitive."""
        set_theme("NORD")
        assert get_theme_name() == "nord"

    def test_invalid_theme_falls_back_to_default(self):
        """Test that invalid theme name falls back to default."""
        set_theme("nonexistent")
        assert get_theme_name() == "default"

    def test_get_theme_returns_theme_object(self):
        """Test get_theme returns ColorTheme object."""
        theme = get_theme()
        assert isinstance(theme, ColorTheme)
        assert theme.name == "default"

    def test_list_themes(self):
        """Test listing all available themes."""
        themes = list_themes()
        assert len(themes) == 10  # 10 themes defined
        names = [name for name, _ in themes]
        assert "default" in names
        assert "monokai" in names
        assert "dracula" in names

    def test_theme_name_from_string(self):
        """Test ThemeName.from_string parsing."""
        assert ThemeName.from_string("default") == ThemeName.DEFAULT
        assert ThemeName.from_string("MONOKAI") == ThemeName.MONOKAI
        assert ThemeName.from_string("  nord  ") == ThemeName.NORD
        assert ThemeName.from_string("invalid") == ThemeName.DEFAULT

    def test_colors_change_with_theme(self):
        """Test Colors class values change based on theme."""
        set_theme(ThemeName.DEFAULT)
        default_green = Colors.GREEN

        set_theme(ThemeName.DARK)
        dark_green = Colors.GREEN

        # Dark theme uses bright colors
        assert default_green != dark_green

    def test_colors_static_values_unchanged(self):
        """Test that RESET, BOLD, DIM are theme-independent."""
        set_theme(ThemeName.DEFAULT)
        default_reset = Colors.RESET
        default_bold = Colors.BOLD

        set_theme(ThemeName.MONOKAI)
        monokai_reset = Colors.RESET
        monokai_bold = Colors.BOLD

        assert default_reset == monokai_reset == "\033[0m"
        assert default_bold == monokai_bold == "\033[1m"

    def test_colors_semantic_names(self):
        """Test semantic color names work."""
        assert Colors.SUCCESS == Colors.GREEN
        assert Colors.ERROR == Colors.RED
        assert Colors.WARNING == Colors.YELLOW
        assert Colors.INFO == Colors.CYAN

    def test_all_themes_have_required_colors(self):
        """Test all themes define required color properties."""
        for theme_name in ThemeName:
            set_theme(theme_name)
            theme = get_theme()
            assert theme.success
            assert theme.error
            assert theme.warning
            assert theme.info
            assert theme.accent
            assert theme.muted
            assert theme.highlight
            assert theme.text

    def test_theme_description_not_empty(self):
        """Test all themes have descriptions."""
        for name, description in list_themes():
            assert description, f"Theme {name} has no description"


class TestConsoleInit:
    """Tests for Console initialization."""

    def test_init_defaults(self):
        """Test default initialization."""
        console = Console()

        # Note: color depends on isatty(), quiet/verbose default false
        assert console.verbose is False
        assert console.json_mode is False

    def test_init_with_verbose(self):
        """Test initialization with verbose mode."""
        console = Console(verbose=True)

        assert console.verbose is True

    def test_init_with_quiet(self):
        """Test initialization with quiet mode."""
        console = Console(quiet=True)

        assert console.quiet is True
        assert console.verbose is False  # quiet overrides verbose

    def test_init_with_json_mode(self):
        """Test initialization with JSON mode."""
        console = Console(json_mode=True)

        assert console.json_mode is True
        assert console.quiet is True  # JSON mode implies quiet
        assert console.color is False  # JSON mode disables color

    def test_quiet_overrides_verbose(self):
        """Test that quiet mode overrides verbose."""
        console = Console(verbose=True, quiet=True)

        assert console.quiet is True
        assert console.verbose is False


class TestConsoleColorize:
    """Tests for Console colorization."""

    def test_colorize_when_enabled(self):
        """Test colorization when color is enabled."""
        with patch("sys.stdout.isatty", return_value=True):
            console = Console(color=True)
            console.color = True  # Force enable

            result = console._c("test", Colors.RED)

            assert Colors.RED in result
            assert Colors.RESET in result
            assert "test" in result

    def test_colorize_when_disabled(self):
        """Test colorization when color is disabled."""
        console = Console(color=False)

        result = console._c("test", Colors.RED)

        assert result == "test"
        assert Colors.RED not in result


class TestConsolePrint:
    """Tests for Console print methods."""

    def test_print_normal(self, capsys):
        """Test normal print."""
        console = Console(quiet=False)

        console.print("Hello, World!")

        captured = capsys.readouterr()
        assert "Hello, World!" in captured.out

    def test_print_empty_line(self, capsys):
        """Test printing empty line."""
        console = Console(quiet=False)

        console.print()

        captured = capsys.readouterr()
        assert captured.out == "\n"

    def test_print_suppressed_in_quiet(self, capsys):
        """Test print is suppressed in quiet mode."""
        console = Console(quiet=True)

        console.print("Hello, World!")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_force_in_quiet(self, capsys):
        """Test force print works in quiet mode."""
        console = Console(quiet=True)

        console.print("Forced!", force=True)

        captured = capsys.readouterr()
        assert "Forced!" in captured.out


class TestConsoleMessages:
    """Tests for Console message methods."""

    def test_success_message(self, capsys):
        """Test success message."""
        console = Console(quiet=False, color=False)

        console.success("It worked!")

        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "It worked!" in captured.out

    def test_success_suppressed_in_quiet(self, capsys):
        """Test success is suppressed in quiet mode."""
        console = Console(quiet=True)

        console.success("It worked!")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_error_message(self, capsys):
        """Test error message."""
        console = Console(quiet=False, color=False)

        console.error("Something broke!")

        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Something broke!" in captured.out

    def test_error_always_prints_in_quiet(self, capsys):
        """Test error prints even in quiet mode."""
        console = Console(quiet=True, color=False, json_mode=False)

        console.error("Something broke!")

        captured = capsys.readouterr()
        assert "Something broke!" in captured.out

    def test_error_collected_in_json_mode(self, capsys):
        """Test error is collected in JSON mode."""
        console = Console(json_mode=True)

        console.error("Something broke!")

        assert "Something broke!" in console._json_errors

    def test_warning_message(self, capsys):
        """Test warning message."""
        console = Console(quiet=False, color=False)

        console.warning("Be careful!")

        captured = capsys.readouterr()
        assert "⚠" in captured.out or "Be careful!" in captured.out

    def test_info_message(self, capsys):
        """Test info message."""
        console = Console(quiet=False, color=False)

        console.info("Just FYI")

        captured = capsys.readouterr()
        assert "ℹ" in captured.out or "Just FYI" in captured.out

    def test_debug_message_with_verbose(self, capsys):
        """Test debug message in verbose mode."""
        console = Console(verbose=True, color=False)

        console.debug("Debug info")

        captured = capsys.readouterr()
        assert "Debug info" in captured.out

    def test_debug_message_without_verbose(self, capsys):
        """Test debug message is suppressed without verbose."""
        console = Console(verbose=False)

        console.debug("Debug info")

        captured = capsys.readouterr()
        assert captured.out == ""


class TestConsoleHeaders:
    """Tests for Console header methods."""

    def test_header(self, capsys):
        """Test header printing."""
        console = Console(quiet=False, color=False)

        console.header("Main Title")

        captured = capsys.readouterr()
        assert "Main Title" in captured.out
        assert "-" in captured.out or "─" in captured.out

    def test_header_suppressed_in_quiet(self, capsys):
        """Test header is suppressed in quiet mode."""
        console = Console(quiet=True)

        console.header("Main Title")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_section(self, capsys):
        """Test section printing."""
        console = Console(quiet=False, color=False)

        console.section("Section Title")

        captured = capsys.readouterr()
        assert "Section Title" in captured.out

    def test_section_suppressed_in_quiet(self, capsys):
        """Test section is suppressed in quiet mode."""
        console = Console(quiet=True)

        console.section("Section Title")

        captured = capsys.readouterr()
        assert captured.out == ""


class TestConsoleTable:
    """Tests for Console table methods."""

    def test_table(self, capsys):
        """Test table printing."""
        console = Console(quiet=False, color=False)

        headers = ["Name", "Value"]
        rows = [
            ["Key1", "Val1"],
            ["Key2", "Val2"],
        ]
        console.table(headers, rows)

        captured = capsys.readouterr()
        assert "Name" in captured.out
        assert "Value" in captured.out
        assert "Key1" in captured.out

    def test_table_suppressed_in_quiet(self, capsys):
        """Test table is suppressed in quiet mode."""
        console = Console(quiet=True)

        headers = ["Key"]
        rows = [["Value"]]
        console.table(headers, rows)

        captured = capsys.readouterr()
        assert captured.out == ""


class TestConsoleProgress:
    """Tests for Console progress methods."""

    def test_progress_bar(self, capsys):
        """Test progress bar."""
        console = Console(quiet=False, color=False)

        console.progress(50, 100, "Halfway")

        captured = capsys.readouterr()
        # Progress bar outputs to same line with \r
        assert "50" in captured.out or "Halfway" in captured.out

    def test_progress_suppressed_in_quiet(self, capsys):
        """Test progress is suppressed in quiet mode."""
        console = Console(quiet=True)

        console.progress(50, 100)

        captured = capsys.readouterr()
        assert captured.out == ""


class TestConsolePrompt:
    """Tests for Console prompt methods."""

    def test_confirm_yes(self):
        """Test confirm with yes response."""
        console = Console(quiet=False)

        with patch("builtins.input", return_value="y"):
            result = console.confirm("Continue?")

        assert result is True

    def test_confirm_no(self):
        """Test confirm with no response."""
        console = Console(quiet=False)

        with patch("builtins.input", return_value="n"):
            result = console.confirm("Continue?")

        assert result is False

    def test_confirm_empty_response_defaults_no(self):
        """Test confirm with empty response defaults to no."""
        console = Console(quiet=False)

        with patch("builtins.input", return_value=""):
            result = console.confirm("Continue?")

        # Default is N
        assert result is False

    def test_confirm_keyboard_interrupt(self):
        """Test confirm handles keyboard interrupt."""
        console = Console(quiet=False)

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = console.confirm("Continue?")

        assert result is False

    def test_confirm_eof_error(self):
        """Test confirm handles EOF error."""
        console = Console(quiet=False)

        with patch("builtins.input", side_effect=EOFError):
            result = console.confirm("Continue?")

        assert result is False

class TestAccessibilityMode:
    """Tests for accessibility mode (color-blind friendly output)."""

    @pytest.fixture(autouse=True)
    def reset_accessibility_mode(self):
        """Reset accessibility mode to default before and after each test."""

        set_accessibility_mode(False)
        yield
        set_accessibility_mode(False)

    def test_accessibility_mode_disabled_by_default(self):
        """Test that accessibility mode is disabled by default."""

        assert get_accessibility_mode() is False

    def test_set_accessibility_mode_on(self):
        """Test enabling accessibility mode."""

        set_accessibility_mode(True)
        assert get_accessibility_mode() is True

    def test_set_accessibility_mode_off(self):
        """Test disabling accessibility mode."""

        set_accessibility_mode(True)
        set_accessibility_mode(False)
        assert get_accessibility_mode() is False

    def test_console_accessible_parameter(self):
        """Test Console with accessible parameter."""
        console = Console(accessible=True)
        assert console.accessible is True

    def test_console_sets_global_accessibility_mode(self):
        """Test that Console sets global accessibility mode."""

        Console(accessible=True)
        assert get_accessibility_mode() is True


class TestStatusIndicator:
    """Tests for status indicator functions."""

    @pytest.fixture(autouse=True)
    def reset_accessibility_mode(self):
        """Reset accessibility mode before and after each test."""

        set_accessibility_mode(False)
        yield
        set_accessibility_mode(False)

    def test_get_status_indicator_success(self):
        """Test success status indicator returns filled circle."""

        indicator = get_status_indicator("success", use_color=False)
        assert "●" in indicator

    def test_get_status_indicator_error(self):
        """Test error status indicator returns filled square."""

        indicator = get_status_indicator("error", use_color=False)
        assert "■" in indicator

    def test_get_status_indicator_warning(self):
        """Test warning status indicator returns triangle."""

        indicator = get_status_indicator("warning", use_color=False)
        assert "▲" in indicator

    def test_get_status_indicator_info(self):
        """Test info status indicator returns diamond."""

        indicator = get_status_indicator("info", use_color=False)
        assert "◆" in indicator

    def test_get_status_indicator_with_label(self):
        """Test status indicator includes label when requested."""

        indicator = get_status_indicator("success", include_label=True, use_color=False)
        assert "● OK" in indicator

    def test_get_status_indicator_accessibility_mode(self):
        """Test status indicator includes label in accessibility mode."""

        set_accessibility_mode(True)
        indicator = get_status_indicator("error", use_color=False)
        assert "■ ERROR" in indicator


class TestFormatStatusText:
    """Tests for format_status_text function."""

    def test_format_done_status(self):
        """Test formatting Done status."""

        result = format_status_text("Done", use_color=False)
        assert "Done" in result
        assert "●" in result  # Success shape

    def test_format_in_progress_status(self):
        """Test formatting In Progress status."""

        result = format_status_text("In Progress", use_color=False)
        assert "In Progress" in result
        assert "◐" in result  # Progress shape

    def test_format_error_status(self):
        """Test formatting error status."""

        result = format_status_text("Failed", use_color=False)
        assert "Failed" in result
        assert "■" in result  # Error shape

    def test_format_status_without_indicator(self):
        """Test formatting status without indicator."""

        result = format_status_text("Done", use_color=False, include_indicator=False)
        assert "Done" in result
        assert "●" not in result


class TestFormatPriorityText:
    """Tests for format_priority_text function."""

    def test_format_critical_priority(self):
        """Test formatting critical priority with double triangle."""

        result = format_priority_text("Critical", use_color=False)
        assert "Critical" in result
        assert "▲▲" in result

    def test_format_high_priority(self):
        """Test formatting high priority with single up triangle."""

        result = format_priority_text("High", use_color=False)
        assert "High" in result
        assert "▲ " in result  # Single triangle (not double)

    def test_format_medium_priority(self):
        """Test formatting medium priority with right triangle."""

        result = format_priority_text("Medium", use_color=False)
        assert "Medium" in result
        assert "►" in result

    def test_format_low_priority(self):
        """Test formatting low priority with down triangle."""

        result = format_priority_text("Low", use_color=False)
        assert "Low" in result
        assert "▽" in result

    def test_format_priority_without_indicator(self):
        """Test formatting priority without indicator."""

        result = format_priority_text("High", use_color=False, include_indicator=False)
        assert "High" in result
        assert "▲" not in result


class TestFormatScoreText:
    """Tests for format_score_text function."""

    def test_format_excellent_score(self):
        """Test formatting excellent score (>= 80%)."""

        result = format_score_text(90, max_score=100, use_color=False)
        assert "90/100" in result
        assert "(Excellent)" in result

    def test_format_good_score(self):
        """Test formatting good score (>= 60%)."""

        result = format_score_text(70, max_score=100, use_color=False)
        assert "70/100" in result
        assert "(Good)" in result

    def test_format_fair_score(self):
        """Test formatting fair score (>= 40%)."""

        result = format_score_text(50, max_score=100, use_color=False)
        assert "50/100" in result
        assert "(Fair)" in result

    def test_format_poor_score(self):
        """Test formatting poor score (< 40%)."""

        result = format_score_text(20, max_score=100, use_color=False)
        assert "20/100" in result
        assert "(Poor)" in result

    def test_format_score_without_bar(self):
        """Test formatting score without progress bar."""

        result = format_score_text(80, max_score=100, show_bar=False, use_color=False)
        assert "80/100" in result
        assert "█" not in result

    def test_format_score_with_bar(self):
        """Test formatting score with progress bar."""

        result = format_score_text(80, max_score=100, show_bar=True, use_color=False)
        assert "█" in result  # Filled portion of bar


class TestFormatDiffIndicator:
    """Tests for format_diff_indicator function."""

    @pytest.fixture(autouse=True)
    def reset_accessibility_mode(self):
        """Reset accessibility mode before and after each test."""

        set_accessibility_mode(False)
        yield
        set_accessibility_mode(False)

    def test_add_indicator(self):
        """Test add indicator shows + symbol."""

        result = format_diff_indicator("add", use_color=False)
        assert "+" in result

    def test_remove_indicator(self):
        """Test remove indicator shows - symbol."""

        result = format_diff_indicator("remove", use_color=False)
        assert "-" in result

    def test_modify_indicator(self):
        """Test modify indicator shows ~ symbol."""

        result = format_diff_indicator("modify", use_color=False)
        assert "~" in result

    def test_accessibility_mode_shows_label(self):
        """Test accessibility mode shows full label."""

        set_accessibility_mode(True)
        result = format_diff_indicator("add", use_color=False)
        assert "+ ADD" in result

    def test_accessibility_mode_remove_label(self):
        """Test accessibility mode shows DEL label for remove."""

        set_accessibility_mode(True)
        result = format_diff_indicator("remove", use_color=False)
        assert "- DEL" in result


class TestConsoleAccessibleOutput:
    """Tests for Console class with accessibility mode."""

    @pytest.fixture(autouse=True)
    def reset_accessibility_mode(self):
        """Reset accessibility mode before and after each test."""

        set_accessibility_mode(False)
        yield
        set_accessibility_mode(False)

    def test_success_message_accessible(self, capsys):
        """Test success message includes text label in accessible mode."""
        console = Console(color=False, accessible=True)
        console.success("Test passed")

        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "Test passed" in captured.out

    def test_error_message_accessible(self, capsys):
        """Test error message includes text label in accessible mode."""
        console = Console(color=False, accessible=True)
        console.error("Test failed")

        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "Test failed" in captured.out

    def test_warning_message_accessible(self, capsys):
        """Test warning message includes text label in accessible mode."""
        console = Console(color=False, accessible=True)
        console.warning("Test warning")

        captured = capsys.readouterr()
        assert "WARN" in captured.out
        assert "Test warning" in captured.out

    def test_info_message_accessible(self, capsys):
        """Test info message includes text label in accessible mode."""
        console = Console(color=False, accessible=True)
        console.info("Test info")

        captured = capsys.readouterr()
        assert "INFO" in captured.out
        assert "Test info" in captured.out

    def test_non_accessible_mode_no_labels(self, capsys):
        """Test non-accessible mode doesn't include text labels."""
        console = Console(color=False, accessible=False)
        console.success("Test passed")

        captured = capsys.readouterr()
        assert "OK" not in captured.out
        assert "Test passed" in captured.out
