"""Tests for code block preservation in tolerant_markdown.

Tests cover:
- Basic code block parsing (fenced, indented, inline)
- Language identifier detection and normalization
- Syntax highlighting preservation
- Code block statistics
- Placeholder preservation and restoration
- Multi-block extraction
- Section-based extraction
"""

import textwrap

import pytest

from spectryn.adapters.parsers.tolerant_markdown import (
    CodeBlock,
    CodeBlockCollection,
    CodeBlockType,
    code_block_to_markdown,
    extract_code_blocks_from_content,
    extract_code_from_section,
    get_code_block_stats,
    parse_code_blocks,
    preserve_code_blocks,
    restore_code_blocks,
)


class TestBasicCodeBlockParsing:
    """Test basic code block parsing functionality."""

    def test_parse_fenced_backtick_block(self) -> None:
        """Parse a fenced code block with backticks."""
        content = textwrap.dedent("""
            Some text

            ```python
            def hello():
                print("Hello!")
            ```

            More text
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 1
        block = collection.blocks[0]
        assert block.language == "python"
        assert block.block_type == CodeBlockType.FENCED_BACKTICK
        assert "def hello():" in block.content
        assert block.fence_char == "`"
        assert block.fence_count == 3

    def test_parse_fenced_tilde_block(self) -> None:
        """Parse a fenced code block with tildes."""
        content = textwrap.dedent("""
            ~~~javascript
            console.log("hello");
            ~~~
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 1
        block = collection.blocks[0]
        assert block.language == "javascript"
        assert block.block_type == CodeBlockType.FENCED_TILDE
        assert block.fence_char == "~"

    def test_parse_block_without_language(self) -> None:
        """Parse a code block without language identifier."""
        content = textwrap.dedent("""
            ```
            just some code
            ```
        """).strip()

        collection, warnings = parse_code_blocks(content)

        assert collection.count == 1
        assert collection.blocks[0].language == ""
        assert not collection.blocks[0].has_language

        # Should generate a warning
        assert len(warnings) == 1
        assert "without language" in warnings[0].message.lower()

    def test_parse_empty_content_returns_empty(self) -> None:
        """Empty content should return empty collection."""
        collection, _warnings = parse_code_blocks("")
        assert collection.count == 0

        collection2, _warnings2 = parse_code_blocks("   \n  \n  ")
        assert collection2.count == 0

    def test_parse_no_code_blocks_returns_empty(self) -> None:
        """Content without code blocks should return empty."""
        content = textwrap.dedent("""
            # Just a header

            Some regular text without any code.
        """).strip()

        collection, _warnings = parse_code_blocks(content)
        assert collection.count == 0

    def test_parse_preserves_line_numbers(self) -> None:
        """Code blocks should preserve line number information."""
        content = textwrap.dedent("""
            # Header

            Some text

            ```python
            code here
            ```
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 1
        block = collection.blocks[0]
        assert block.line_number == 5  # Line where ```python starts


class TestIndentedCodeBlocks:
    """Test indented code block parsing."""

    def test_parse_indented_code_block(self) -> None:
        """Parse 4-space indented code block."""
        content = textwrap.dedent("""
            Some text

                def indented():
                    return True

            More text
        """).strip()

        collection, _warnings = parse_code_blocks(content, include_indented=True)

        assert collection.count == 1
        block = collection.blocks[0]
        assert block.block_type == CodeBlockType.INDENTED
        assert "def indented():" in block.content

    def test_skip_indented_when_disabled(self) -> None:
        """Should skip indented blocks when disabled."""
        content = textwrap.dedent("""
                indented code

            ```python
            fenced code
            ```
        """).strip()

        collection, _warnings = parse_code_blocks(content, include_indented=False)

        assert collection.count == 1
        assert collection.blocks[0].block_type == CodeBlockType.FENCED_BACKTICK


class TestInlineCodeSpans:
    """Test inline code span parsing."""

    def test_parse_inline_code(self) -> None:
        """Parse inline code spans."""
        content = "Use `variable` in your code with `another_var`."

        collection, _warnings = parse_code_blocks(content, include_inline=True)

        assert collection.count == 2
        assert collection.blocks[0].content == "variable"
        assert collection.blocks[0].is_inline
        assert collection.blocks[1].content == "another_var"

    def test_skip_inline_when_disabled(self) -> None:
        """Should skip inline code when disabled."""
        content = "Use `variable` in your code."

        collection, _warnings = parse_code_blocks(content, include_inline=False)
        assert collection.count == 0


class TestLanguageNormalization:
    """Test language identifier normalization."""

    def test_normalize_common_aliases(self) -> None:
        """Common language aliases should be normalized."""
        test_cases = [
            ("js", "javascript"),
            ("ts", "typescript"),
            ("py", "python"),
            ("rb", "ruby"),
            ("sh", "shell"),
            ("bash", "shell"),
            ("yml", "yaml"),
            ("md", "markdown"),
        ]

        for alias, expected in test_cases:
            content = f"```{alias}\ncode\n```"
            collection, _ = parse_code_blocks(content)
            assert collection.blocks[0].normalized_language == expected

    def test_unknown_language_unchanged(self) -> None:
        """Unknown languages should remain unchanged."""
        content = "```customlang\ncode\n```"
        collection, _ = parse_code_blocks(content)
        assert collection.blocks[0].normalized_language == "customlang"


class TestCodeBlockCollection:
    """Test CodeBlockCollection methods."""

    def test_languages_property(self) -> None:
        """Get unique languages from collection."""
        content = textwrap.dedent("""
            ```python
            code1
            ```

            ```javascript
            code2
            ```

            ```python
            code3
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        assert collection.count == 3
        languages = collection.languages
        assert "python" in languages
        assert "javascript" in languages
        assert len(languages) == 2  # Unique languages

    def test_by_language(self) -> None:
        """Filter blocks by language."""
        content = textwrap.dedent("""
            ```python
            py1
            ```

            ```javascript
            js1
            ```

            ```python
            py2
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        python_blocks = collection.by_language("python")
        assert len(python_blocks) == 2

        js_blocks = collection.by_language("javascript")
        assert len(js_blocks) == 1

    def test_get_block(self) -> None:
        """Get block by index."""
        content = textwrap.dedent("""
            ```python
            first
            ```

            ```javascript
            second
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        assert collection.get_block(0) is not None
        assert collection.get_block(0).language == "python"
        assert collection.get_block(1).language == "javascript"
        assert collection.get_block(99) is None


class TestCodeBlockProperties:
    """Test CodeBlock dataclass properties."""

    def test_has_language(self) -> None:
        """Check if block has language specified."""
        content_with = "```python\ncode\n```"
        content_without = "```\ncode\n```"

        coll1, _ = parse_code_blocks(content_with)
        coll2, _ = parse_code_blocks(content_without)

        assert coll1.blocks[0].has_language is True
        assert coll2.blocks[0].has_language is False

    def test_is_fenced(self) -> None:
        """Check if block is fenced."""
        content = textwrap.dedent("""
            ```python
            fenced
            ```

                indented
        """).strip()

        collection, _ = parse_code_blocks(content, include_indented=True)

        assert collection.blocks[0].is_fenced is True
        assert collection.blocks[1].is_fenced is False

    def test_line_count(self) -> None:
        """Get number of lines in code content."""
        content = textwrap.dedent("""
            ```python
            line1
            line2
            line3
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        assert collection.blocks[0].line_count == 3


class TestExtractFunctions:
    """Test extraction utility functions."""

    def test_extract_code_blocks_from_content(self) -> None:
        """Extract all fenced code blocks."""
        content = textwrap.dedent("""
            ```python
            code1
            ```

            ```javascript
            code2
            ```
        """).strip()

        blocks, _warnings = extract_code_blocks_from_content(content)

        assert len(blocks) == 2
        assert blocks[0].language == "python"

    def test_extract_with_language_filter(self) -> None:
        """Extract blocks with specific language."""
        content = textwrap.dedent("""
            ```python
            py_code
            ```

            ```javascript
            js_code
            ```

            ```python
            more_py
            ```
        """).strip()

        blocks, _warnings = extract_code_blocks_from_content(content, language_filter="python")

        assert len(blocks) == 2
        assert all(b.language == "python" for b in blocks)

    def test_extract_from_section(self) -> None:
        """Extract code from named section."""
        content = textwrap.dedent("""
            # Introduction

            ```python
            wrong_section
            ```

            ## Examples

            ```javascript
            correct_section
            ```

            ## Other

            More content.
        """).strip()

        block, _warnings = extract_code_from_section(content, "Examples")

        assert block is not None
        assert block.language == "javascript"
        assert "correct_section" in block.content

    def test_extract_from_nonexistent_section(self) -> None:
        """Return None for missing section."""
        content = textwrap.dedent("""
            # Only Section

            ```python
            code
            ```
        """).strip()

        block, _warnings = extract_code_from_section(content, "Missing")
        assert block is None


class TestPreserveRestoreCodeBlocks:
    """Test code block preservation and restoration."""

    def test_preserve_code_blocks(self) -> None:
        """Replace code blocks with placeholders."""
        content = textwrap.dedent("""
            Some text

            ```python
            code here
            ```

            More text
        """).strip()

        processed, mapping = preserve_code_blocks(content)

        assert "___CODE_BLOCK_" in processed
        assert "```python" not in processed
        assert len(mapping) == 1

    def test_restore_code_blocks(self) -> None:
        """Restore code blocks from placeholders."""
        content = textwrap.dedent("""
            Some text

            ```python
            code here
            ```

            More text
        """).strip()

        processed, mapping = preserve_code_blocks(content)
        restored = restore_code_blocks(processed, mapping)

        assert "```python" in restored
        assert "code here" in restored
        assert "___CODE_BLOCK_" not in restored

    def test_preserve_restore_roundtrip(self) -> None:
        """Preserve and restore should be idempotent."""
        content = textwrap.dedent("""
            # Example

            ```python
            def hello():
                print("Hello!")
            ```

            Some text between.

            ```javascript
            console.log("Hi");
            ```

            End of content.
        """).strip()

        processed, mapping = preserve_code_blocks(content)
        restored = restore_code_blocks(processed, mapping)

        # The restored content should match original
        assert "```python" in restored
        assert "```javascript" in restored
        assert "def hello():" in restored
        assert "console.log" in restored


class TestCodeBlockToMarkdown:
    """Test code block to markdown conversion."""

    def test_code_block_to_markdown_with_language(self) -> None:
        """Create markdown code block with language."""
        result = code_block_to_markdown("print('hello')", "python")

        assert result == "```python\nprint('hello')\n```"

    def test_code_block_to_markdown_without_language(self) -> None:
        """Create markdown code block without language."""
        result = code_block_to_markdown("some code")

        assert result == "```\nsome code\n```"

    def test_code_block_to_markdown_custom_fence(self) -> None:
        """Create code block with custom fence character."""
        result = code_block_to_markdown("code", "python", fence_char="~")

        assert result.startswith("~~~python")
        assert result.endswith("~~~")

    def test_code_block_to_markdown_escapes_fence(self) -> None:
        """Increase fence count when code contains fence pattern."""
        code_with_fence = "```\ninner block\n```"
        result = code_block_to_markdown(code_with_fence, "markdown")

        # Should use more backticks than the inner fence
        assert result.startswith("````")

    def test_block_to_markdown_method(self) -> None:
        """CodeBlock.to_markdown() method."""
        content = "```python\ncode\n```"
        collection, _ = parse_code_blocks(content)
        block = collection.blocks[0]

        markdown = block.to_markdown()
        assert "```python" in markdown or "```" in markdown


class TestCodeBlockStats:
    """Test code block statistics."""

    def test_get_stats_basic(self) -> None:
        """Get basic statistics."""
        content = textwrap.dedent("""
            ```python
            line1
            line2
            ```

            ```javascript
            single
            ```

            ```
            no language
            ```
        """).strip()

        stats = get_code_block_stats(content)

        assert stats["total"] == 3
        assert stats["fenced"] == 3
        assert stats["with_language"] == 2
        assert stats["without_language"] == 1
        assert "python" in stats["languages"]
        assert "javascript" in stats["languages"]

    def test_get_stats_empty_content(self) -> None:
        """Stats for content without code blocks."""
        stats = get_code_block_stats("No code here.")

        assert stats["total"] == 0
        assert stats["fenced"] == 0
        assert stats["lines_of_code"] == 0
        assert stats["languages"] == []


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_nested_fence_handling(self) -> None:
        """Handle code blocks with inner backticks."""
        content = textwrap.dedent("""
            ````markdown
            ```python
            inner code
            ```
            ````
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 1
        block = collection.blocks[0]
        assert "```python" in block.content

    def test_multiple_blocks_same_language(self) -> None:
        """Multiple blocks with same language."""
        content = textwrap.dedent("""
            ```python
            first
            ```

            ```python
            second
            ```

            ```python
            third
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        assert collection.count == 3
        assert all(b.language == "python" for b in collection.blocks)

    def test_info_string_with_attributes(self) -> None:
        """Parse info string with additional attributes."""
        content = textwrap.dedent("""
            ```python title="example.py" highlight={1,3}
            code here
            ```
        """).strip()

        collection, _ = parse_code_blocks(content)

        block = collection.blocks[0]
        assert block.language == "python"
        assert "title=" in block.info_string

    def test_empty_code_block(self) -> None:
        """Handle empty code block."""
        content = textwrap.dedent("""
            ```python
            ```
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 1
        assert collection.blocks[0].content == ""

    def test_whitespace_only_code(self) -> None:
        """Handle whitespace-only code."""
        content = "```python\n   \n```"

        collection, _ = parse_code_blocks(content)

        assert collection.count == 1


class TestIntegration:
    """Integration tests for code block preservation."""

    def test_documentation_example(self) -> None:
        """Parse typical documentation with multiple code examples."""
        content = textwrap.dedent("""
            # API Reference

            ## Installation

            ```bash
            pip install mypackage
            ```

            ## Quick Start

            ```python
            from mypackage import Client

            client = Client()
            result = client.fetch()
            ```

            ## Configuration

            Create a config file:

            ```yaml
            api_key: your-key
            timeout: 30
            ```

            ## Advanced Usage

            ```python
            # Advanced configuration
            client = Client(
                timeout=60,
                retries=3
            )
            ```
        """).strip()

        collection, _warnings = parse_code_blocks(content)

        assert collection.count == 4
        assert collection.fenced_count == 4

        languages = collection.languages
        assert "shell" in languages  # bash normalized
        assert "python" in languages
        assert "yaml" in languages

        # Get all python examples
        python_blocks = collection.by_language("python")
        assert len(python_blocks) == 2

    def test_readme_code_preservation(self) -> None:
        """Preserve code blocks during markdown transformation."""
        readme = textwrap.dedent("""
            # My Project

            > Some quote

            ## Usage

            ```python
            import mylib
            mylib.run()
            ```

            ## Contributing

            Please read CONTRIBUTING.md
        """).strip()

        # Preserve code blocks
        processed, mapping = preserve_code_blocks(readme)

        # Simulate some text transformation
        processed = processed.upper()

        # Restore code blocks
        restored = restore_code_blocks(processed, mapping)

        # Code should be intact (not uppercased)
        assert "import mylib" in restored
        assert "IMPORT MYLIB" not in restored

    def test_acceptance_criteria_with_code(self) -> None:
        """Parse acceptance criteria containing code examples."""
        content = textwrap.dedent("""
            ## Acceptance Criteria

            Given the following input:

            ```json
            {
              "name": "test",
              "value": 42
            }
            ```

            When processed, the output should be:

            ```json
            {
              "result": "success",
              "processed_value": 84
            }
            ```
        """).strip()

        block, _ = extract_code_from_section(content, "Acceptance Criteria")

        assert block is not None
        assert block.language == "json"
        assert '"name": "test"' in block.content
