"""
Tests for AI Fix module.

Tests AI tool detection and format guide generation.
"""

from unittest.mock import MagicMock, patch

import pytest

from spectra.cli.ai_fix import (
    AIFixResult,
    AITool,
    DetectedTool,
    detect_ai_tools,
    format_ai_tools_list,
    generate_fix_prompt,
    generate_format_guide,
    get_tool_by_name,
)


# =============================================================================
# AITool Enum Tests
# =============================================================================


class TestAIToolEnum:
    """Tests for AITool enum."""

    def test_all_tools_have_value(self):
        """Test all tools have string value."""
        for tool in AITool:
            assert isinstance(tool.value, str)
            assert len(tool.value) > 0

    def test_tool_values(self):
        """Test specific tool values."""
        assert AITool.CLAUDE.value == "claude"
        assert AITool.OLLAMA.value == "ollama"
        assert AITool.AIDER.value == "aider"
        assert AITool.LLM.value == "llm"
        assert AITool.MODS.value == "mods"


# =============================================================================
# DetectedTool Tests
# =============================================================================


class TestDetectedTool:
    """Tests for DetectedTool dataclass."""

    def test_create_detected_tool(self):
        """Test creating a DetectedTool."""
        tool = DetectedTool(
            tool=AITool.CLAUDE,
            command="claude",
            version="1.0.0",
            available=True,
        )

        assert tool.tool == AITool.CLAUDE
        assert tool.command == "claude"
        assert tool.version == "1.0.0"
        assert tool.available is True

    def test_display_name(self):
        """Test display_name property."""
        tool = DetectedTool(tool=AITool.CLAUDE, command="claude")
        assert tool.display_name == "Claude CLI"

        tool = DetectedTool(tool=AITool.OLLAMA, command="ollama")
        assert tool.display_name == "Ollama"

        tool = DetectedTool(tool=AITool.GH_COPILOT, command="gh copilot")
        assert tool.display_name == "GitHub Copilot (gh extension)"

    def test_display_name_fallback(self):
        """Test display_name falls back to tool value."""
        # This would only happen if a new tool is added without a display name
        tool = DetectedTool(tool=AITool.SGPT, command="sgpt")
        assert tool.display_name == "Shell GPT"


# =============================================================================
# AIFixResult Tests
# =============================================================================


class TestAIFixResult:
    """Tests for AIFixResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = AIFixResult(
            success=True,
            tool_used="claude",
            output="Fixed content",
            fixed_content="# Fixed markdown",
        )

        assert result.success is True
        assert result.tool_used == "claude"
        assert result.output == "Fixed content"
        assert result.fixed_content == "# Fixed markdown"
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failed result."""
        result = AIFixResult(
            success=False,
            tool_used="claude",
            error="API error",
        )

        assert result.success is False
        assert result.error == "API error"
        assert result.fixed_content is None


# =============================================================================
# detect_ai_tools Tests
# =============================================================================


class TestDetectAITools:
    """Tests for detect_ai_tools function."""

    def test_detect_no_tools(self):
        """Test when no AI tools are available."""
        with patch("shutil.which", return_value=None):
            tools = detect_ai_tools()
            assert tools == []

    def test_detect_claude(self):
        """Test detecting Claude CLI."""

        def mock_which(cmd):
            return "/usr/bin/claude" if cmd == "claude" else None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("spectra.cli.ai_fix._get_version", return_value="claude-cli version 1.0.0"),
        ):
            tools = detect_ai_tools()

            assert len(tools) == 1
            assert tools[0].tool == AITool.CLAUDE
            assert tools[0].command == "claude"

    def test_detect_ollama(self):
        """Test detecting Ollama."""

        def mock_which(cmd):
            return "/usr/bin/ollama" if cmd == "ollama" else None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("spectra.cli.ai_fix._get_version", return_value="ollama version 0.1.0"),
        ):
            tools = detect_ai_tools()

            assert len(tools) == 1
            assert tools[0].tool == AITool.OLLAMA

    def test_detect_multiple_tools(self):
        """Test detecting multiple tools."""

        def mock_which(cmd):
            if cmd in ("claude", "ollama", "aider"):
                return f"/usr/bin/{cmd}"
            return None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("spectra.cli.ai_fix._get_version", return_value="1.0.0"),
        ):
            tools = detect_ai_tools()

            assert len(tools) == 3
            tool_types = [t.tool for t in tools]
            assert AITool.CLAUDE in tool_types
            assert AITool.OLLAMA in tool_types
            assert AITool.AIDER in tool_types


# =============================================================================
# format_ai_tools_list Tests
# =============================================================================


class TestFormatAIToolsList:
    """Tests for format_ai_tools_list function."""

    def test_format_empty_list(self):
        """Test formatting empty tools list."""
        result = format_ai_tools_list([])
        assert "No AI CLI tools detected" in result

    def test_format_single_tool(self):
        """Test formatting single tool."""
        tools = [
            DetectedTool(tool=AITool.CLAUDE, command="claude", version="1.0.0"),
        ]

        result = format_ai_tools_list(tools, color=False)

        assert "Claude CLI" in result
        assert "1.0.0" in result

    def test_format_multiple_tools(self):
        """Test formatting multiple tools."""
        tools = [
            DetectedTool(tool=AITool.CLAUDE, command="claude", version="1.0.0"),
            DetectedTool(tool=AITool.OLLAMA, command="ollama", version="0.1.0"),
        ]

        result = format_ai_tools_list(tools)

        assert "Claude CLI" in result
        assert "Ollama" in result


# =============================================================================
# generate_format_guide Tests
# =============================================================================


class TestGenerateFormatGuide:
    """Tests for format guide generation."""

    def test_generate_format_guide(self):
        """Test generate_format_guide returns content."""
        guide = generate_format_guide()

        assert isinstance(guide, str)
        assert len(guide) > 0
        # Should contain markdown format info
        assert "###" in guide or "Story" in guide or "markdown" in guide.lower()


class TestGetToolByName:
    """Tests for get_tool_by_name function."""

    def test_get_tool_by_name_found(self):
        """Test finding tool by name."""
        tools = [
            DetectedTool(tool=AITool.CLAUDE, command="claude"),
            DetectedTool(tool=AITool.OLLAMA, command="ollama"),
        ]

        result = get_tool_by_name("claude", tools)
        assert result is not None
        assert result.tool == AITool.CLAUDE

    def test_get_tool_by_name_not_found(self):
        """Test tool not found."""
        tools = [
            DetectedTool(tool=AITool.CLAUDE, command="claude"),
        ]

        result = get_tool_by_name("nonexistent", tools)
        assert result is None

    def test_get_tool_by_name_empty_list(self):
        """Test with empty tools list."""
        result = get_tool_by_name("claude", [])
        assert result is None


# =============================================================================
# generate_fix_prompt Tests
# =============================================================================


class TestGenerateFixPrompt:
    """Tests for fix prompt generation."""

    def test_generate_fix_prompt_basic(self):
        """Test basic fix prompt generation."""
        content = """# My Epic

### US-001: Test Story
Missing metadata table
"""
        errors = ["Missing metadata table for US-001"]

        prompt = generate_fix_prompt("test.md", content, errors)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should mention fixing or correcting
        assert "fix" in prompt.lower() or "correct" in prompt.lower() or "format" in prompt.lower()
        # Should include the errors
        assert "US-001" in prompt or "metadata" in prompt.lower()

    def test_generate_fix_prompt_multiple_errors(self):
        """Test fix prompt with multiple errors."""
        content = "# Invalid markdown"
        errors = [
            "Missing story header",
            "Invalid status emoji",
            "Missing required fields",
        ]

        prompt = generate_fix_prompt("test.md", content, errors)

        assert isinstance(prompt, str)
        # Should reference at least some errors
        assert len(prompt) > 0

    def test_generate_fix_prompt_empty_errors(self):
        """Test fix prompt with no errors."""
        content = "# Valid markdown"
        errors = []

        prompt = generate_fix_prompt("test.md", content, errors)

        assert isinstance(prompt, str)

    def test_generate_fix_prompt_with_warnings(self):
        """Test fix prompt with warnings."""
        content = "# Content"
        errors = ["Error 1"]
        warnings = ["Warning 1", "Warning 2"]

        prompt = generate_fix_prompt("test.md", content, errors, warnings=warnings)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
