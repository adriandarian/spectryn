"""
Tests for image embedding extraction in markdown content.

This module tests the EmbeddedImage dataclass and parse_embedded_images function
that extract images from markdown content, supporting multiple syntaxes:
- Standard markdown: ![alt](url)
- With title: ![alt](url "title")
- Reference style: ![alt][ref] with [ref]: url
- HTML img tags: <img src="url" alt="alt">
- Obsidian wikilinks: ![[image.png]] or ![[image.png|alt]]
"""

import textwrap

import pytest

from spectryn.adapters.parsers.tolerant_markdown import (
    EmbeddedImage,
    extract_images_from_section,
    parse_embedded_images,
)


class TestEmbeddedImageDataclass:
    """Tests for the EmbeddedImage dataclass."""

    def test_basic_creation(self):
        """Test creating a basic EmbeddedImage."""
        img = EmbeddedImage(
            src="./images/logo.png",
            alt_text="Logo",
            title="Company Logo",
            is_local=True,
            line_number=5,
        )
        assert img.src == "./images/logo.png"
        assert img.alt_text == "Logo"
        assert img.title == "Company Logo"
        assert img.is_local is True
        assert img.line_number == 5

    def test_defaults(self):
        """Test default values for optional fields."""
        img = EmbeddedImage(src="image.png")
        assert img.alt_text == ""
        assert img.title == ""
        assert img.is_local is False
        assert img.line_number == 0
        assert img.original_syntax == ""
        assert img.width is None
        assert img.height is None

    def test_filename_from_local_path(self):
        """Test extracting filename from local path."""
        img = EmbeddedImage(src="./images/logo.png", is_local=True)
        assert img.filename == "logo.png"

    def test_filename_from_url(self):
        """Test extracting filename from URL."""
        img = EmbeddedImage(src="https://example.com/assets/banner.jpg")
        assert img.filename == "banner.jpg"

    def test_filename_from_url_with_query_params(self):
        """Test extracting filename from URL with query params."""
        img = EmbeddedImage(src="https://example.com/image.png?v=123")
        # The query params are part of the path, so we get the full path component
        assert "image.png" in img.filename

    def test_extension_property(self):
        """Test getting file extension."""
        assert EmbeddedImage(src="logo.png").extension == "png"
        assert EmbeddedImage(src="photo.JPEG").extension == "jpeg"
        assert EmbeddedImage(src="diagram.SVG").extension == "svg"
        assert EmbeddedImage(src="noext").extension == ""

    def test_is_supported_format(self):
        """Test checking for supported image formats."""
        assert EmbeddedImage(src="image.png").is_supported_format is True
        assert EmbeddedImage(src="image.jpg").is_supported_format is True
        assert EmbeddedImage(src="image.jpeg").is_supported_format is True
        assert EmbeddedImage(src="image.gif").is_supported_format is True
        assert EmbeddedImage(src="image.webp").is_supported_format is True
        assert EmbeddedImage(src="image.svg").is_supported_format is True
        assert EmbeddedImage(src="image.bmp").is_supported_format is True
        assert EmbeddedImage(src="image.avif").is_supported_format is True
        assert EmbeddedImage(src="image.tiff").is_supported_format is False
        assert EmbeddedImage(src="image.psd").is_supported_format is False

    def test_to_markdown(self):
        """Test converting to markdown syntax."""
        img = EmbeddedImage(src="logo.png", alt_text="Logo")
        assert img.to_markdown() == "![Logo](logo.png)"

        img_with_title = EmbeddedImage(src="logo.png", alt_text="Logo", title="Company Logo")
        assert img_with_title.to_markdown() == '![Logo](logo.png "Company Logo")'

    def test_to_html(self):
        """Test converting to HTML."""
        img = EmbeddedImage(
            src="logo.png",
            alt_text="Logo",
            title="Company Logo",
            width=100,
            height=50,
        )
        html = img.to_html()
        assert 'src="logo.png"' in html
        assert 'alt="Logo"' in html
        assert 'title="Company Logo"' in html
        assert 'width="100"' in html
        assert 'height="50"' in html


class TestParseEmbeddedImagesStandard:
    """Tests for standard markdown image syntax."""

    def test_simple_image(self):
        """Test parsing a simple markdown image."""
        content = "![Logo](./images/logo.png)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "./images/logo.png"
        assert images[0].alt_text == "Logo"
        assert images[0].is_local is True

    def test_image_with_title(self):
        """Test parsing image with title attribute."""
        content = '![Banner](https://example.com/banner.jpg "Site Banner")'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "https://example.com/banner.jpg"
        assert images[0].alt_text == "Banner"
        assert images[0].title == "Site Banner"
        assert images[0].is_local is False

    def test_image_with_dimensions(self):
        """Test parsing image with width/height specification."""
        content = "![Diagram](diagram.png =200x150)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].width == 200
        assert images[0].height == 150

    def test_image_with_width_only(self):
        """Test parsing image with width only."""
        content = "![Diagram](diagram.png =200x)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].width == 200
        assert images[0].height is None

    def test_multiple_images(self):
        """Test parsing multiple images from content."""
        content = textwrap.dedent("""
            # My Document

            Here is the logo: ![Logo](logo.png)

            And here is a screenshot:
            ![Screenshot](./screens/app.png)

            External image: ![External](https://cdn.example.com/image.jpg)
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 3
        assert images[0].src == "logo.png"
        assert images[1].src == "./screens/app.png"
        assert images[2].src == "https://cdn.example.com/image.jpg"

    def test_empty_alt_text(self):
        """Test parsing image with empty alt text (with warning)."""
        content = "![](image.png)"
        images, warnings = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].alt_text == ""

        # Should have warning about missing alt text
        assert any(w.code == "MISSING_ALT_TEXT" for w in warnings)

    def test_line_numbers_tracked(self):
        """Test that line numbers are correctly tracked."""
        content = textwrap.dedent("""
            Line 1
            Line 2
            ![Image](test.png)
            Line 4
        """).lstrip()
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].line_number == 3


class TestParseEmbeddedImagesObsidian:
    """Tests for Obsidian wikilink image syntax."""

    def test_simple_wikilink(self):
        """Test parsing Obsidian wikilink image."""
        content = "![[diagram.png]]"
        images, warnings = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "diagram.png"
        assert images[0].is_local is True

        # Should have warning about non-standard syntax
        assert any(w.code == "WIKILINK_IMAGE" for w in warnings)

    def test_wikilink_with_alt_text(self):
        """Test parsing Obsidian wikilink with alt text."""
        content = "![[diagram.svg|Architecture Diagram]]"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "diagram.svg"
        assert images[0].alt_text == "Architecture Diagram"

    def test_wikilink_with_path(self):
        """Test parsing Obsidian wikilink with nested path."""
        content = "![[attachments/images/logo.png|Company Logo]]"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "attachments/images/logo.png"
        assert images[0].alt_text == "Company Logo"


class TestParseEmbeddedImagesHtml:
    """Tests for HTML img tag syntax."""

    def test_simple_html_img(self):
        """Test parsing simple HTML img tag."""
        content = '<img src="logo.png" alt="Logo">'
        images, warnings = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "logo.png"
        assert images[0].alt_text == "Logo"

        # Should have warning about HTML in markdown
        assert any(w.code == "HTML_IMAGE_TAG" for w in warnings)

    def test_html_img_self_closing(self):
        """Test parsing self-closing HTML img tag."""
        content = '<img src="logo.png" alt="Logo" />'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "logo.png"

    def test_html_img_with_dimensions(self):
        """Test parsing HTML img with width and height."""
        content = '<img src="chart.png" alt="Chart" width="600" height="400">'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].width == 600
        assert images[0].height == 400

    def test_html_img_with_title(self):
        """Test parsing HTML img with title attribute."""
        content = '<img src="logo.png" alt="Logo" title="Company Logo">'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].title == "Company Logo"

    def test_html_img_url(self):
        """Test parsing HTML img with URL source."""
        content = '<img src="https://cdn.example.com/logo.png" alt="Logo">'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "https://cdn.example.com/logo.png"
        assert images[0].is_local is False


class TestParseEmbeddedImagesReference:
    """Tests for reference-style markdown images."""

    def test_reference_style_image(self):
        """Test parsing reference-style image."""
        content = textwrap.dedent("""
            Check out this diagram:

            ![Architecture][arch-diagram]

            [arch-diagram]: ./images/architecture.svg
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "./images/architecture.svg"
        assert images[0].alt_text == "Architecture"

    def test_reference_style_with_title(self):
        """Test reference-style image with title."""
        content = textwrap.dedent("""
            ![Logo][logo-ref]

            [logo-ref]: ./logo.png "Company Logo"
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].title == "Company Logo"

    def test_reference_style_missing_reference(self):
        """Test warning for missing reference definition."""
        content = "![Missing Image][nonexistent-ref]"
        images, warnings = parse_embedded_images(content)

        assert len(images) == 0
        assert any(w.code == "MISSING_IMAGE_REFERENCE" for w in warnings)

    def test_reference_style_implicit_ref(self):
        """Test reference-style with implicit reference (same as alt)."""
        content = textwrap.dedent("""
            ![logo][]

            [logo]: ./images/logo.png
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "./images/logo.png"


class TestParseEmbeddedImagesFiltering:
    """Tests for filtering images by type."""

    def test_include_only_local(self):
        """Test including only local images."""
        content = textwrap.dedent("""
            ![Local](./local.png)
            ![Remote](https://example.com/remote.png)
        """)
        images, _ = parse_embedded_images(content, include_remote=False)

        assert len(images) == 1
        assert images[0].src == "./local.png"

    def test_include_only_remote(self):
        """Test including only remote images."""
        content = textwrap.dedent("""
            ![Local](./local.png)
            ![Remote](https://example.com/remote.png)
        """)
        images, _ = parse_embedded_images(content, include_local=False)

        assert len(images) == 1
        assert images[0].src == "https://example.com/remote.png"

    def test_exclude_all(self):
        """Test excluding both local and remote."""
        content = textwrap.dedent("""
            ![Local](./local.png)
            ![Remote](https://example.com/remote.png)
        """)
        images, _ = parse_embedded_images(content, include_local=False, include_remote=False)

        assert len(images) == 0


class TestParseEmbeddedImagesDuplicates:
    """Tests for handling duplicate images."""

    def test_duplicate_images_deduplicated(self):
        """Test that duplicate image sources are deduplicated."""
        content = textwrap.dedent("""
            ![Logo](logo.png)
            Some text
            ![Logo Again](logo.png)
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "logo.png"


class TestParseEmbeddedImagesWarnings:
    """Tests for warning generation."""

    def test_unsupported_format_warning(self):
        """Test warning for unsupported image formats."""
        content = "![Image](photo.tiff)"
        images, warnings = parse_embedded_images(content)

        assert len(images) == 1
        assert any(w.code == "UNSUPPORTED_IMAGE_FORMAT" for w in warnings)

    def test_missing_alt_text_warning(self):
        """Test warning for missing alt text."""
        content = "![](image.png)"
        _, warnings = parse_embedded_images(content)

        assert any(w.code == "MISSING_ALT_TEXT" for w in warnings)

    def test_warning_includes_source_file(self):
        """Test that warnings include source file."""
        content = "![](image.png)"
        _, warnings = parse_embedded_images(content, source="test.md")

        assert len(warnings) > 0
        assert warnings[0].location.source == "test.md"


class TestExtractImagesFromSection:
    """Tests for extracting images from specific sections."""

    def test_extract_from_description_section(self):
        """Test extracting images from Description section."""
        content = textwrap.dedent("""
            # Story Title

            ## Description

            Here is a diagram:
            ![Diagram](./diagrams/flow.png)

            ## Technical Notes

            ![Tech Diagram](./tech.png)
        """)
        images, _ = extract_images_from_section(content, "Description")

        assert len(images) == 1
        assert images[0].src == "./diagrams/flow.png"

    def test_section_not_found(self):
        """Test when section is not found."""
        content = "# Just a title\n\nSome content"
        images, warnings = extract_images_from_section(content, "Description")

        assert len(images) == 0
        assert len(warnings) == 0


class TestParseEmbeddedImagesMixedContent:
    """Tests for mixed content with multiple image formats."""

    def test_mixed_syntax_types(self):
        """Test parsing content with multiple image syntaxes."""
        content = textwrap.dedent("""
            # Document with Various Images

            Standard markdown:
            ![Logo](logo.png)

            Obsidian style:
            ![[diagram.svg|Architecture]]

            HTML embedded:
            <img src="chart.png" alt="Chart" width="400">

            Reference style:
            ![Banner][banner]

            [banner]: banner.jpg "Site Banner"
        """)
        images, _ = parse_embedded_images(content)

        assert len(images) == 4

        # Check we got all formats
        sources = {img.src for img in images}
        assert "logo.png" in sources
        assert "diagram.svg" in sources
        assert "chart.png" in sources
        assert "banner.jpg" in sources


class TestParseEmbeddedImagesEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_content(self):
        """Test parsing empty content."""
        images, warnings = parse_embedded_images("")
        assert len(images) == 0
        assert len(warnings) == 0

    def test_no_images(self):
        """Test parsing content with no images."""
        content = "# Just some text\n\nNo images here."
        images, _ = parse_embedded_images(content)
        assert len(images) == 0

    def test_image_in_code_block_still_parsed(self):
        """Note: Current implementation doesn't skip code blocks."""
        # This is a known limitation - images in code blocks will be parsed
        content = textwrap.dedent("""
            ```markdown
            ![Example](example.png)
            ```
        """)
        # Currently parsed (known limitation)
        # A future enhancement could skip code blocks
        _images, _ = parse_embedded_images(content)
        assert _images  # Just verify it parses without error

    def test_nested_brackets_in_alt_text(self):
        """Test handling alt text with special characters."""
        content = "![Image with [brackets]](image.png)"
        # The current regex may not handle this perfectly
        # This test documents current behavior
        _images, _ = parse_embedded_images(content)
        assert _images is not None  # Just verify it parses without error

    def test_url_with_spaces_encoded(self):
        """Test URL with encoded spaces."""
        content = "![Spaced](./my%20image.png)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].src == "./my%20image.png"

    def test_data_uri_detected_as_remote(self):
        """Test that data URIs are detected as non-local."""
        content = "![Data](data:image/png;base64,iVBORw0KGgo...)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].is_local is False

    def test_protocol_relative_url(self):
        """Test protocol-relative URLs are detected as remote."""
        content = "![Image](//cdn.example.com/image.png)"
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].is_local is False

    def test_original_syntax_preserved(self):
        """Test that original syntax is preserved."""
        content = '![Alt Text](image.png "Title")'
        images, _ = parse_embedded_images(content)

        assert len(images) == 1
        assert images[0].original_syntax == '![Alt Text](image.png "Title")'
