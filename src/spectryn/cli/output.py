"""
Output - Rich console output formatting.

Provides pretty-printed output with colors and formatting.
"""

import sys
from dataclasses import dataclass
from enum import Enum

from spectryn.application.sync import SyncResult


# =============================================================================
# Color Theme System
# =============================================================================


class ThemeName(Enum):
    """Available color themes."""

    DEFAULT = "default"
    DARK = "dark"
    LIGHT = "light"
    MONOKAI = "monokai"
    SOLARIZED = "solarized"
    NORD = "nord"
    DRACULA = "dracula"
    GRUVBOX = "gruvbox"
    OCEAN = "ocean"
    MINIMAL = "minimal"

    @classmethod
    def from_string(cls, value: str) -> "ThemeName":
        """Parse theme name from string."""
        normalized = value.lower().strip()
        for theme in cls:
            if theme.value == normalized:
                return theme
        return cls.DEFAULT


@dataclass(frozen=True)
class ColorTheme:
    """
    A color theme definition.

    Defines semantic colors for different output types (success, error, etc.)
    rather than raw color names, allowing themes to customize the palette.
    """

    name: str
    description: str

    # Text styles (always the same across themes)
    reset: str = "\033[0m"
    bold: str = "\033[1m"
    dim: str = "\033[2m"
    underline: str = "\033[4m"

    # Semantic colors - what they mean, not what color they are
    success: str = "\033[32m"  # Default: green
    error: str = "\033[31m"  # Default: red
    warning: str = "\033[33m"  # Default: yellow
    info: str = "\033[36m"  # Default: cyan
    accent: str = "\033[34m"  # Default: blue
    muted: str = "\033[90m"  # Default: gray
    highlight: str = "\033[35m"  # Default: magenta
    text: str = "\033[37m"  # Default: white

    # Background colors
    bg_success: str = "\033[42m"
    bg_error: str = "\033[41m"
    bg_warning: str = "\033[43m"
    bg_info: str = "\033[44m"


# Theme definitions
THEMES: dict[ThemeName, ColorTheme] = {
    ThemeName.DEFAULT: ColorTheme(
        name="default",
        description="Classic terminal colors",
        success="\033[32m",  # Green
        error="\033[31m",  # Red
        warning="\033[33m",  # Yellow
        info="\033[36m",  # Cyan
        accent="\033[34m",  # Blue
        muted="\033[90m",  # Gray
        highlight="\033[35m",  # Magenta
        text="\033[37m",  # White
    ),
    ThemeName.DARK: ColorTheme(
        name="dark",
        description="High contrast for dark terminals",
        success="\033[92m",  # Bright green
        error="\033[91m",  # Bright red
        warning="\033[93m",  # Bright yellow
        info="\033[96m",  # Bright cyan
        accent="\033[94m",  # Bright blue
        muted="\033[90m",  # Gray
        highlight="\033[95m",  # Bright magenta
        text="\033[97m",  # Bright white
    ),
    ThemeName.LIGHT: ColorTheme(
        name="light",
        description="Optimized for light terminals",
        success="\033[32m",  # Green
        error="\033[31m",  # Red
        warning="\033[33m",  # Yellow (darker for light bg)
        info="\033[34m",  # Blue (instead of cyan)
        accent="\033[35m",  # Magenta
        muted="\033[90m",  # Gray
        highlight="\033[36m",  # Cyan
        text="\033[30m",  # Black (for light background)
    ),
    ThemeName.MONOKAI: ColorTheme(
        name="monokai",
        description="Inspired by Monokai editor theme",
        success="\033[38;5;148m",  # Monokai green
        error="\033[38;5;197m",  # Monokai pink/red
        warning="\033[38;5;208m",  # Monokai orange
        info="\033[38;5;81m",  # Monokai blue
        accent="\033[38;5;141m",  # Monokai purple
        muted="\033[38;5;242m",  # Gray
        highlight="\033[38;5;186m",  # Monokai yellow
        text="\033[38;5;231m",  # White
    ),
    ThemeName.SOLARIZED: ColorTheme(
        name="solarized",
        description="Solarized color palette",
        success="\033[38;5;64m",  # Solarized green
        error="\033[38;5;160m",  # Solarized red
        warning="\033[38;5;136m",  # Solarized yellow
        info="\033[38;5;37m",  # Solarized cyan
        accent="\033[38;5;33m",  # Solarized blue
        muted="\033[38;5;240m",  # Solarized base01
        highlight="\033[38;5;125m",  # Solarized magenta
        text="\033[38;5;245m",  # Solarized base0
    ),
    ThemeName.NORD: ColorTheme(
        name="nord",
        description="Arctic, north-bluish color palette",
        success="\033[38;5;108m",  # Nord green
        error="\033[38;5;131m",  # Nord red
        warning="\033[38;5;179m",  # Nord yellow
        info="\033[38;5;110m",  # Nord frost blue
        accent="\033[38;5;67m",  # Nord blue
        muted="\033[38;5;59m",  # Nord polar night
        highlight="\033[38;5;139m",  # Nord purple
        text="\033[38;5;188m",  # Nord snow storm
    ),
    ThemeName.DRACULA: ColorTheme(
        name="dracula",
        description="Dark theme with vibrant colors",
        success="\033[38;5;84m",  # Dracula green
        error="\033[38;5;203m",  # Dracula red
        warning="\033[38;5;228m",  # Dracula yellow
        info="\033[38;5;117m",  # Dracula cyan
        accent="\033[38;5;141m",  # Dracula purple
        muted="\033[38;5;61m",  # Dracula comment
        highlight="\033[38;5;212m",  # Dracula pink
        text="\033[38;5;231m",  # Dracula foreground
    ),
    ThemeName.GRUVBOX: ColorTheme(
        name="gruvbox",
        description="Retro groove color scheme",
        success="\033[38;5;142m",  # Gruvbox green
        error="\033[38;5;167m",  # Gruvbox red
        warning="\033[38;5;214m",  # Gruvbox yellow
        info="\033[38;5;109m",  # Gruvbox aqua
        accent="\033[38;5;109m",  # Gruvbox blue
        muted="\033[38;5;245m",  # Gruvbox gray
        highlight="\033[38;5;175m",  # Gruvbox purple
        text="\033[38;5;223m",  # Gruvbox fg
    ),
    ThemeName.OCEAN: ColorTheme(
        name="ocean",
        description="Deep ocean blues and teals",
        success="\033[38;5;43m",  # Teal
        error="\033[38;5;167m",  # Coral
        warning="\033[38;5;215m",  # Sandy
        info="\033[38;5;75m",  # Ocean blue
        accent="\033[38;5;32m",  # Deep blue
        muted="\033[38;5;60m",  # Deep slate
        highlight="\033[38;5;44m",  # Turquoise
        text="\033[38;5;195m",  # Pale blue
    ),
    ThemeName.MINIMAL: ColorTheme(
        name="minimal",
        description="Subtle, low-contrast colors",
        success="\033[38;5;71m",  # Muted green
        error="\033[38;5;131m",  # Muted red
        warning="\033[38;5;172m",  # Muted orange
        info="\033[38;5;67m",  # Muted blue
        accent="\033[38;5;103m",  # Muted purple
        muted="\033[38;5;244m",  # Gray
        highlight="\033[38;5;139m",  # Muted pink
        text="\033[38;5;250m",  # Light gray
    ),
}

# Current theme (module-level for global access)
_current_theme: ColorTheme = THEMES[ThemeName.DEFAULT]


def set_theme(theme: ThemeName | str) -> None:
    """
    Set the current color theme.

    Args:
        theme: Theme name or ThemeName enum value.
    """
    global _current_theme
    if isinstance(theme, str):
        theme = ThemeName.from_string(theme)
    _current_theme = THEMES.get(theme, THEMES[ThemeName.DEFAULT])


def get_theme() -> ColorTheme:
    """Get the current color theme."""
    return _current_theme


def get_theme_name() -> str:
    """Get the current theme name."""
    return _current_theme.name


def list_themes() -> list[tuple[str, str]]:
    """
    List all available themes.

    Returns:
        List of (name, description) tuples.
    """
    return [(t.name, t.description) for t in THEMES.values()]


class _ColorsMeta(type):
    """Metaclass for dynamic color access based on current theme."""

    def __getattr__(cls, name: str) -> str:
        # Static values (not theme-dependent)
        static = {
            "RESET": "\033[0m",
            "BOLD": "\033[1m",
            "DIM": "\033[2m",
            "UNDERLINE": "\033[4m",
        }
        if name in static:
            return static[name]

        # Map old color names to semantic theme colors
        theme = get_theme()
        color_map = {
            # Text colors -> semantic mapping
            "RED": theme.error,
            "GREEN": theme.success,
            "YELLOW": theme.warning,
            "BLUE": theme.accent,
            "MAGENTA": theme.highlight,
            "CYAN": theme.info,
            "WHITE": theme.text,
            "GRAY": theme.muted,
            "GREY": theme.muted,
            # Background colors
            "BG_RED": theme.bg_error,
            "BG_GREEN": theme.bg_success,
            "BG_YELLOW": theme.bg_warning,
            "BG_BLUE": theme.bg_info,
            # Semantic names (preferred)
            "SUCCESS": theme.success,
            "ERROR": theme.error,
            "WARNING": theme.warning,
            "INFO": theme.info,
            "ACCENT": theme.accent,
            "MUTED": theme.muted,
            "HIGHLIGHT": theme.highlight,
            "TEXT": theme.text,
        }
        if name in color_map:
            return color_map[name]

        raise AttributeError(f"'{cls.__name__}' has no attribute '{name}'")


class Colors(metaclass=_ColorsMeta):
    """
    ANSI color codes for terminal output.

    Provides constants for text colors, background colors, and text styles
    that can be used to format terminal output.

    Colors are now theme-aware - the actual ANSI codes returned depend
    on the currently active theme. Use `set_theme()` to change themes.

    Attributes:
        RESET: Reset all formatting to default.
        BOLD: Make text bold.
        DIM: Make text dimmed/faded.
        UNDERLINE: Underline text.
        RED/ERROR: Error/failure color.
        GREEN/SUCCESS: Success color.
        YELLOW/WARNING: Warning color.
        BLUE/ACCENT: Accent/primary color.
        MAGENTA/HIGHLIGHT: Highlight color.
        CYAN/INFO: Informational color.
        WHITE/TEXT: Default text color.
        GRAY/MUTED: Muted/secondary text color.
        BG_RED, BG_GREEN, BG_YELLOW, BG_BLUE: Background colors.
    """

    # Type hints for IDE support (actual values from metaclass)
    RESET: str
    BOLD: str
    DIM: str
    UNDERLINE: str

    # Traditional color names (mapped to semantic colors via theme)
    RED: str
    GREEN: str
    YELLOW: str
    BLUE: str
    MAGENTA: str
    CYAN: str
    WHITE: str
    GRAY: str
    GREY: str

    # Semantic color names (preferred)
    SUCCESS: str
    ERROR: str
    WARNING: str
    INFO: str
    ACCENT: str
    MUTED: str
    HIGHLIGHT: str
    TEXT: str

    # Background colors
    BG_RED: str
    BG_GREEN: str
    BG_YELLOW: str
    BG_BLUE: str


# Global emoji toggle (module-level for persistence)
_emoji_enabled: bool = True

# Global accessibility mode (module-level for persistence)
_accessibility_mode: bool = False

# Emoji versions of symbols
_EMOJI_SYMBOLS = {
    "CHECK": "✓",
    "CROSS": "✗",
    "ARROW": "→",
    "DOT": "•",
    "WARN": "⚠",
    "INFO": "ℹ",
    "ROCKET": "🚀",
    "GEAR": "⚙",
    "FILE": "📄",
    "FOLDER": "📁",
    "LINK": "🔗",
    "SUCCESS": "✅",
    "FAILURE": "❌",
    "WARNING": "⚠️",
    "PROGRESS": "🔄",
    "COMPLETE": "✅",
    "PENDING": "📋",
    "BLOCKED": "⏸️",
    "CHART": "📊",
    "DOWNLOAD": "📥",
    "SYNC": "🔄",
    "DIFF": "📝",
}

# ASCII fallbacks (no emojis)
_ASCII_SYMBOLS = {
    "CHECK": "[OK]",
    "CROSS": "[X]",
    "ARROW": "->",
    "DOT": "*",
    "WARN": "[!]",
    "INFO": "[i]",
    "ROCKET": "[>]",
    "GEAR": "[*]",
    "FILE": "[F]",
    "FOLDER": "[D]",
    "LINK": "[L]",
    "SUCCESS": "[OK]",
    "FAILURE": "[FAIL]",
    "WARNING": "[WARN]",
    "PROGRESS": "[...]",
    "COMPLETE": "[DONE]",
    "PENDING": "[TODO]",
    "BLOCKED": "[HOLD]",
    "CHART": "[#]",
    "DOWNLOAD": "[v]",
    "SYNC": "[~]",
    "DIFF": "[D]",
}


# =============================================================================
# Accessibility Mode - Color-blind Friendly Output
# =============================================================================


# Status indicators with different shapes (not just colors)
# These use distinct Unicode shapes recognizable without color
_STATUS_SHAPES = {
    "success": "●",  # Filled circle
    "error": "■",  # Filled square
    "warning": "▲",  # Triangle
    "info": "◆",  # Diamond
    "pending": "○",  # Empty circle
    "blocked": "▣",  # Square with fill
    "progress": "◐",  # Half-filled circle
}

# Text labels for accessibility mode
_STATUS_LABELS = {
    "success": "OK",
    "error": "ERROR",
    "warning": "WARN",
    "info": "INFO",
    "pending": "TODO",
    "blocked": "BLOCKED",
    "progress": "RUNNING",
    "done": "DONE",
    "in_progress": "IN PROGRESS",
    "planned": "PLANNED",
    "open": "OPEN",
    "in_review": "IN REVIEW",
    "cancelled": "CANCELLED",
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}


def set_accessibility_mode(enabled: bool) -> None:
    """
    Enable or disable accessibility mode for color-blind friendly output.

    When enabled, output includes text labels alongside or instead of
    color-only indicators, and uses distinct shapes to differentiate
    status types.

    Args:
        enabled: True to enable accessibility mode, False to disable.
    """
    global _accessibility_mode
    _accessibility_mode = enabled


def get_accessibility_mode() -> bool:
    """
    Get the current accessibility mode state.

    Returns:
        True if accessibility mode is enabled, False otherwise.
    """
    return _accessibility_mode


def get_status_indicator(
    status: str,
    include_label: bool | None = None,
    use_color: bool = True,
) -> str:
    """
    Get a status indicator that works without color.

    Returns a shape-based indicator with optional text label for
    accessibility. When accessibility mode is enabled, always includes
    the text label.

    Args:
        status: Status type ('success', 'error', 'warning', 'info', 'pending', etc.)
        include_label: Whether to include text label. If None, uses accessibility mode.
        use_color: Whether to apply color codes.

    Returns:
        Formatted status indicator string.

    Examples:
        >>> get_status_indicator("success")
        "●"  # or "● OK" in accessibility mode
        >>> get_status_indicator("error", include_label=True)
        "■ ERROR"
    """
    # Determine if we should include the label
    show_label = include_label if include_label is not None else _accessibility_mode

    # Get shape (defaults to dot if unknown status)
    shape = _STATUS_SHAPES.get(status.lower(), "•")

    # Get label if needed
    label = _STATUS_LABELS.get(status.lower(), status.upper()) if show_label else ""

    # Apply color if enabled
    if use_color:
        color_map = {
            "success": Colors.SUCCESS,
            "error": Colors.ERROR,
            "warning": Colors.WARNING,
            "info": Colors.INFO,
            "pending": Colors.MUTED,
            "blocked": Colors.WARNING,
            "progress": Colors.INFO,
            "done": Colors.SUCCESS,
            "in_progress": Colors.WARNING,
            "planned": Colors.INFO,
            "open": Colors.INFO,
            "in_review": Colors.WARNING,
            "cancelled": Colors.MUTED,
            "critical": Colors.ERROR,
            "high": Colors.WARNING,
            "medium": Colors.SUCCESS,
            "low": Colors.INFO,
        }
        color = color_map.get(status.lower(), "")
        if color:
            if show_label:
                return f"{color}{shape} {label}{Colors.RESET}"
            return f"{color}{shape}{Colors.RESET}"

    # No color
    if show_label:
        return f"{shape} {label}"
    return shape


def format_status_text(
    status: str,
    use_color: bool = True,
    include_indicator: bool = True,
) -> str:
    """
    Format a status string with optional color and indicator.

    Always includes the text status name, making it accessible
    without relying on color alone.

    Args:
        status: Status name (e.g., 'Done', 'In Progress', 'Error')
        use_color: Whether to apply color codes.
        include_indicator: Whether to include shape indicator prefix.

    Returns:
        Formatted status string.

    Examples:
        >>> format_status_text("Done")
        "● Done"
        >>> format_status_text("Error", include_indicator=False)
        "Error"  # with color if enabled
    """
    normalized = status.lower().replace(" ", "_").replace("-", "_")

    # Map common status variations
    status_map = {
        "done": "success",
        "completed": "success",
        "passed": "success",
        "ok": "success",
        "error": "error",
        "failed": "error",
        "failure": "error",
        "warn": "warning",
        "warning": "warning",
        "caution": "warning",
        "in_progress": "progress",
        "running": "progress",
        "syncing": "progress",
        "pending": "pending",
        "todo": "pending",
        "planned": "pending",
        "open": "info",
        "info": "info",
        "blocked": "blocked",
        "cancelled": "blocked",
        "in_review": "warning",
    }

    status_type = status_map.get(normalized, "info")

    if include_indicator:
        indicator = get_status_indicator(status_type, use_color=use_color)
        if use_color:
            color_map = {
                "success": Colors.SUCCESS,
                "error": Colors.ERROR,
                "warning": Colors.WARNING,
                "info": Colors.INFO,
                "pending": Colors.MUTED,
                "blocked": Colors.WARNING,
                "progress": Colors.INFO,
            }
            color = color_map.get(status_type, "")
            return f"{indicator} {color}{status}{Colors.RESET}"
        return f"{indicator} {status}"

    # No indicator, just colored text
    if use_color:
        color_map = {
            "success": Colors.SUCCESS,
            "error": Colors.ERROR,
            "warning": Colors.WARNING,
            "info": Colors.INFO,
            "pending": Colors.MUTED,
            "blocked": Colors.WARNING,
            "progress": Colors.INFO,
        }
        color = color_map.get(status_type, "")
        return f"{color}{status}{Colors.RESET}"

    return status


def format_priority_text(
    priority: str,
    use_color: bool = True,
    include_indicator: bool = True,
) -> str:
    """
    Format a priority string with optional color and indicator.

    Uses distinct shapes for each priority level and always includes
    the text label, making it accessible without color.

    Args:
        priority: Priority name (e.g., 'Critical', 'High', 'Medium', 'Low')
        use_color: Whether to apply color codes.
        include_indicator: Whether to include shape indicator prefix.

    Returns:
        Formatted priority string.

    Examples:
        >>> format_priority_text("Critical")
        "▲▲ Critical"  # Double triangle for critical
        >>> format_priority_text("Low")
        "▽ Low"  # Down triangle for low
    """
    normalized = priority.lower().strip()

    # Priority indicators (shape-based, distinguishable without color)
    indicators = {
        "critical": "▲▲",  # Double up triangle
        "high": "▲",  # Up triangle
        "medium": "►",  # Right triangle (neutral)
        "low": "▽",  # Down triangle
        "none": "○",  # Empty circle
    }

    indicator = indicators.get(normalized, "►")

    if use_color:
        color_map = {
            "critical": Colors.ERROR,
            "high": Colors.WARNING,
            "medium": Colors.SUCCESS,
            "low": Colors.INFO,
            "none": Colors.MUTED,
        }
        color = color_map.get(normalized, "")
        if include_indicator:
            return f"{color}{indicator} {priority}{Colors.RESET}"
        return f"{color}{priority}{Colors.RESET}"

    if include_indicator:
        return f"{indicator} {priority}"
    return priority


def format_score_text(
    score: int | float,
    max_score: int = 100,
    use_color: bool = True,
    show_bar: bool = True,
    bar_width: int = 10,
) -> str:
    """
    Format a numeric score with optional color and visual bar.

    Uses both color and text/shape indicators for accessibility.
    The bar uses different fill characters for different score ranges.

    Args:
        score: Numeric score value.
        max_score: Maximum possible score (default 100).
        use_color: Whether to apply color codes.
        show_bar: Whether to show a visual progress bar.
        bar_width: Width of the progress bar in characters.

    Returns:
        Formatted score string with optional bar.

    Examples:
        >>> format_score_text(85)
        "████████░░ 85/100 (Good)"
        >>> format_score_text(45, show_bar=False)
        "45/100 (Poor)"
    """
    # Calculate percentage
    pct = (score / max_score) * 100 if max_score > 0 else 0

    # Determine level (text label for accessibility)
    if pct >= 80:
        level = "Excellent"
        level_type = "success"
        fill_char = "█"
    elif pct >= 60:
        level = "Good"
        level_type = "success"
        fill_char = "█"
    elif pct >= 40:
        level = "Fair"
        level_type = "warning"
        fill_char = "▓"
    else:
        level = "Poor"
        level_type = "error"
        fill_char = "▒"

    # Build the output
    parts = []

    if show_bar:
        filled = int((pct / 100) * bar_width)
        empty = bar_width - filled
        bar = fill_char * filled + "░" * empty

        if use_color:
            color_map = {
                "success": Colors.SUCCESS,
                "warning": Colors.WARNING,
                "error": Colors.ERROR,
            }
            color = color_map.get(level_type, "")
            parts.append(f"{color}{bar}{Colors.RESET}")
        else:
            parts.append(bar)

    # Add numeric score
    score_text = f"{score:.0f}/{max_score}"
    if use_color:
        color_map = {
            "success": Colors.SUCCESS,
            "warning": Colors.WARNING,
            "error": Colors.ERROR,
        }
        color = color_map.get(level_type, "")
        parts.append(f"{color}{score_text}{Colors.RESET}")
    else:
        parts.append(score_text)

    # Add text level for accessibility
    parts.append(f"({level})")

    return " ".join(parts)


def format_diff_indicator(
    change_type: str,
    use_color: bool = True,
) -> str:
    """
    Format a diff change indicator that's accessible without color.

    Uses both symbols and text labels to indicate add/remove/modify.

    Args:
        change_type: Type of change ('add', 'remove', 'modify', 'unchanged')
        use_color: Whether to apply color codes.

    Returns:
        Formatted diff indicator.

    Examples:
        >>> format_diff_indicator("add")
        "+ ADD"
        >>> format_diff_indicator("remove")
        "- DEL"
    """
    indicators = {
        "add": ("+", "ADD", Colors.SUCCESS),
        "added": ("+", "ADD", Colors.SUCCESS),
        "new": ("+", "NEW", Colors.SUCCESS),
        "create": ("+", "NEW", Colors.SUCCESS),
        "remove": ("-", "DEL", Colors.ERROR),
        "removed": ("-", "DEL", Colors.ERROR),
        "delete": ("-", "DEL", Colors.ERROR),
        "deleted": ("-", "DEL", Colors.ERROR),
        "modify": ("~", "MOD", Colors.WARNING),
        "modified": ("~", "MOD", Colors.WARNING),
        "change": ("~", "CHG", Colors.WARNING),
        "changed": ("~", "CHG", Colors.WARNING),
        "update": ("~", "UPD", Colors.WARNING),
        "unchanged": ("=", "===", Colors.MUTED),
        "same": ("=", "===", Colors.MUTED),
    }

    normalized = change_type.lower().strip()
    symbol, label, color = indicators.get(normalized, ("?", "???", Colors.MUTED))

    # In accessibility mode, always show the label
    if _accessibility_mode:
        if use_color:
            return f"{color}{symbol} {label}{Colors.RESET}"
        return f"{symbol} {label}"

    # Normal mode - just the symbol (with color)
    if use_color:
        return f"{color}{symbol}{Colors.RESET}"
    return symbol


def set_emoji_mode(use_emoji: bool) -> None:
    """
    Set whether to use emojis or ASCII fallbacks globally.

    Args:
        use_emoji: True to use emojis, False for ASCII-only.
    """
    global _emoji_enabled
    _emoji_enabled = use_emoji


def get_emoji_mode() -> bool:
    """Get current emoji mode."""
    return _emoji_enabled


def get_symbol(name: str) -> str:
    """
    Get a symbol by name, respecting the global emoji mode.

    Args:
        name: Symbol name (CHECK, CROSS, ARROW, etc.)

    Returns:
        The symbol string (emoji or ASCII based on mode).
    """
    if _emoji_enabled:
        return _EMOJI_SYMBOLS.get(name, name)
    return _ASCII_SYMBOLS.get(name, name)


class _SymbolsMeta(type):
    """Metaclass to enable dynamic class attribute access for Symbols."""

    def __getattr__(cls, name: str) -> str:
        # Handle box drawing characters (not affected by emoji toggle)
        if name.startswith("BOX_"):
            box_chars = {
                "BOX_TL": "╭",
                "BOX_TR": "╮",
                "BOX_BL": "╰",
                "BOX_BR": "╯",
                "BOX_H": "─",
                "BOX_V": "│",
            }
            if name in box_chars:
                return box_chars[name]
        # Handle symbol lookup with emoji toggle
        if name in _EMOJI_SYMBOLS:
            return get_symbol(name)
        raise AttributeError(f"'{cls.__name__}' has no attribute '{name}'")


class Symbols(metaclass=_SymbolsMeta):
    """
    Unicode symbols for terminal output.

    Provides constants for commonly used symbols in CLI output,
    including status indicators, navigation arrows, and box drawing characters.

    Supports both emoji and ASCII-only modes for accessibility and
    compatibility with terminals that don't support emojis.

    Use `set_emoji_mode(False)` to disable emojis globally.

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

    # These are provided for IDE auto-complete, but actual values
    # come from the metaclass __getattr__
    CHECK: str
    CROSS: str
    ARROW: str
    DOT: str
    WARN: str
    INFO: str
    ROCKET: str
    GEAR: str
    FILE: str
    FOLDER: str
    LINK: str
    SUCCESS: str
    FAILURE: str
    WARNING: str
    PROGRESS: str
    COMPLETE: str
    PENDING: str
    BLOCKED: str
    CHART: str
    DOWNLOAD: str
    SYNC: str
    DIFF: str

    # Box drawing (static, not affected by emoji toggle)
    BOX_TL: str
    BOX_TR: str
    BOX_BL: str
    BOX_BR: str
    BOX_H: str
    BOX_V: str

    @staticmethod
    def set_emoji_mode(use_emoji: bool) -> None:
        """Set whether to use emojis or ASCII fallbacks."""
        set_emoji_mode(use_emoji)

    @staticmethod
    def get_emoji_mode() -> bool:
        """Get current emoji mode."""
        return get_emoji_mode()


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
        accessible: Whether to enable accessibility mode (text labels with status).
    """

    def __init__(
        self,
        color: bool = True,
        verbose: bool = False,
        quiet: bool = False,
        json_mode: bool = False,
        accessible: bool = False,
    ):
        """
        Initialize the console output helper.

        Args:
            color: Enable colored output. Automatically disabled if stdout is not a TTY.
            verbose: Enable verbose debug output.
            quiet: Suppress most output, only show errors and final summary.
            json_mode: Output JSON format instead of text.
            accessible: Enable accessibility mode with text labels alongside colors.
                       When enabled, status indicators include text labels and use
                       distinct shapes to convey meaning without relying on color.
        """
        self.json_mode = json_mode
        self.color = color and sys.stdout.isatty() and not json_mode
        self.verbose = verbose
        self.quiet = quiet or json_mode  # JSON mode implies quiet for intermediate output
        self.accessible = accessible

        # Set global accessibility mode
        if accessible:
            set_accessibility_mode(True)

        # JSON mode collects messages for final output
        self._json_messages: list[dict] = []
        self._json_errors: list[str] = []

        # Progress tracking state
        self._last_progress_message: str = ""
        self._last_progress_phase: str = ""
        self._last_had_item: bool = False

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

        In accessibility mode, includes "[OK]" text label for color-blind users.

        Args:
            text: Success message to display.
        """
        if self.quiet:
            return
        if self.accessible:
            indicator = get_status_indicator("success", include_label=True, use_color=self.color)
            self.print(f"  {indicator} {text}")
        else:
            self.print(self._c(f"  {Symbols.CHECK} {text}", Colors.GREEN))

    def error(self, text: str) -> None:
        """
        Print an error message with cross symbol.

        Always prints, even in quiet mode. Collected in JSON mode.
        In accessibility mode, includes "[ERROR]" text label.

        Args:
            text: Error message to display.
        """
        if self.json_mode:
            self._json_errors.append(text)
            return
        # Errors always print, even in quiet mode
        if self.accessible:
            indicator = get_status_indicator("error", include_label=True, use_color=self.color)
            print(f"  {indicator} {text}")
        else:
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

        In accessibility mode, includes "[WARN]" text label.

        Args:
            text: Warning message to display.
        """
        if self.quiet:
            return
        if self.accessible:
            indicator = get_status_indicator("warning", include_label=True, use_color=self.color)
            self.print(f"  {indicator} {text}")
        else:
            self.print(self._c(f"  {Symbols.WARN} {text}", Colors.YELLOW))

    def info(self, text: str) -> None:
        """
        Print an info message with info symbol.

        In accessibility mode, includes "[INFO]" text label.

        Args:
            text: Info message to display.
        """
        if self.quiet:
            return
        if self.accessible:
            indicator = get_status_indicator("info", include_label=True, use_color=self.color)
            self.print(f"  {indicator} {text}")
        else:
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
        filled = int(width * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (width - filled)
        pct = int(100 * current / total) if total > 0 else 0

        # Check if running in interactive terminal
        if sys.stdout.isatty():
            # Interactive: update in place with carriage return
            padded_message = f"{message:<25}"
            line = f"\r  [{bar}] {pct:>3}% {padded_message}"
            sys.stdout.write(line)
            sys.stdout.flush()
            if current >= total > 0:
                self.print()
        else:
            # Non-interactive: print each phase once (track with instance variable)
            if not hasattr(self, "_last_progress_message"):
                self._last_progress_message = ""
            if message != self._last_progress_message:
                self._last_progress_message = message
                self.print(f"  [{bar}] {pct:>3}% {message}")

    def progress_detailed(
        self,
        phase: str,
        item: str,
        overall_progress: float,
        current_item: int,
        total_items: int,
    ) -> None:
        """
        Print a detailed progress bar with phase and item information.

        Shows overall progress and current item being processed.

        Args:
            phase: Current sync phase name.
            item: Current item being processed.
            overall_progress: Overall progress (0-100).
            current_item: Current item number in phase.
            total_items: Total items in current phase.
        """
        if self.quiet:
            return

        width = 25
        filled = int(width * overall_progress / 100)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(overall_progress)

        # Build message with phase and item info
        item_info = f"({current_item}/{total_items})" if total_items > 0 else ""

        # Truncate item name for display
        item_display = (item[:20] + "...") if len(item) > 23 else item

        # Check if running in interactive terminal
        if sys.stdout.isatty():
            # Interactive: show two-line progress (phase + item)
            # Use ANSI escape sequences to position cursor
            phase_line = f"\r  [{bar}] {pct:>3}% {phase} {item_info}"
            item_line = f"\n  {Colors.DIM}→ {item_display}{Colors.RESET}" if item else ""

            # Move up if we have a previous line, then clear
            if hasattr(self, "_last_had_item") and self._last_had_item:
                sys.stdout.write("\033[A\033[K")  # Move up and clear line

            sys.stdout.write(phase_line)
            if item:
                sys.stdout.write(item_line)
                self._last_had_item = True
            else:
                self._last_had_item = False

            sys.stdout.flush()

            if overall_progress >= 100:
                if hasattr(self, "_last_had_item") and self._last_had_item:
                    sys.stdout.write("\n")
                self.print()
                self._last_had_item = False
        else:
            # Non-interactive: print phase changes only
            if not hasattr(self, "_last_progress_phase"):
                self._last_progress_phase = ""
            if phase != self._last_progress_phase:
                self._last_progress_phase = phase
                self.print(f"  [{bar}] {pct:>3}% {phase}")

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
