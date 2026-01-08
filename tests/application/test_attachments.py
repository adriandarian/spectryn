"""Tests for attachment sync functionality."""

import tempfile
from pathlib import Path

import pytest

from spectryn.application.sync.attachments import (
    Attachment,
    AttachmentExtractor,
    AttachmentStatus,
    AttachmentStore,
    AttachmentSyncConfig,
    AttachmentSyncDirection,
    AttachmentSyncer,
    AttachmentSyncResult,
    extract_attachments_from_markdown,
)


class TestAttachment:
    """Tests for Attachment dataclass."""

    def test_create_basic_attachment(self):
        """Test creating a basic attachment."""
        att = Attachment(
            name="test.png",
            filename="test.png",
            local_path="./images/test.png",
        )
        assert att.name == "test.png"
        assert att.filename == "test.png"
        assert att.local_path == "./images/test.png"
        assert att.is_local
        assert not att.is_remote
        assert not att.is_synced

    def test_attachment_from_markdown_link(self):
        """Test creating attachment from markdown link."""
        att = Attachment.from_markdown_link("Screenshot", "./images/screenshot.png")
        assert att.name == "Screenshot"
        assert att.filename == "screenshot.png"
        assert att.local_path == "./images/screenshot.png"
        assert att.mime_type == "image/png"

    def test_attachment_from_remote(self):
        """Test creating attachment from remote data."""
        remote_data = {
            "id": "12345",
            "name": "document.pdf",
            "url": "https://jira.example.com/attachments/12345",
            "size": 1024,
            "mimeType": "application/pdf",
        }
        att = Attachment.from_remote(remote_data)
        assert att.remote_id == "12345"
        assert att.name == "document.pdf"
        assert att.remote_url == "https://jira.example.com/attachments/12345"
        assert att.size == 1024
        assert att.is_remote
        assert not att.is_local

    def test_attachment_to_markdown_link(self):
        """Test converting attachment to markdown link."""
        att = Attachment(
            name="Test Image",
            filename="test.png",
            local_path="./attachments/test.png",
        )
        link = att.to_markdown_link()
        assert link == "[Test Image](./attachments/test.png)"

    def test_attachment_to_dict_and_back(self):
        """Test serialization roundtrip."""
        att = Attachment(
            name="test.pdf",
            filename="test.pdf",
            local_path="./docs/test.pdf",
            remote_id="abc123",
            size=2048,
            status=AttachmentStatus.SYNCED,
        )
        data = att.to_dict()
        restored = Attachment.from_dict(data)
        assert restored.name == att.name
        assert restored.local_path == att.local_path
        assert restored.remote_id == att.remote_id
        assert restored.status == AttachmentStatus.SYNCED

    def test_attachment_id_generation(self):
        """Test that attachment ID is generated."""
        att = Attachment(name="test.txt", local_path="./test.txt")
        assert att.id  # Should have a generated ID
        assert len(att.id) == 12


class TestAttachmentExtractor:
    """Tests for AttachmentExtractor."""

    def test_extract_from_attachments_section(self):
        """Test extracting attachments from dedicated section."""
        content = """
# Story Title

Some content here.

#### Attachments
- [Screenshot](./images/screenshot.png)
- [Document](./docs/spec.pdf)

#### Next Section
More content.
"""
        extractor = AttachmentExtractor()
        attachments = extractor.extract_from_content(content)
        assert len(attachments) == 2
        assert attachments[0].name == "Screenshot"
        assert attachments[0].local_path == "./images/screenshot.png"
        assert attachments[1].name == "Document"
        assert attachments[1].local_path == "./docs/spec.pdf"

    def test_extract_embedded_images(self):
        """Test extracting embedded markdown images."""
        content = """
# Story

Here's a diagram:

![Architecture Diagram](./diagrams/arch.png)

And another image:

![](./images/logo.svg)
"""
        extractor = AttachmentExtractor()
        attachments = extractor.extract_from_content(content, include_images=True)
        assert len(attachments) == 2
        assert attachments[0].name == "Architecture Diagram"
        assert attachments[1].name == "image"  # Default name for alt-less images

    def test_skip_remote_urls(self):
        """Test that remote URLs are not extracted as local files."""
        content = """
# Story

![External](https://example.com/image.png)

#### Attachments
- [Link](https://example.com/doc.pdf)
- [Local](./local.pdf)
"""
        extractor = AttachmentExtractor()
        attachments = extractor.extract_from_content(content)
        # Should only extract local files
        assert len(attachments) == 1
        assert attachments[0].local_path == "./local.pdf"

    def test_extract_obsidian_wikilinks(self):
        """Test extracting Obsidian-style image wikilinks."""
        content = """
# Story

![[images/screenshot.png]]
![[diagram.svg|Architecture]]
"""
        extractor = AttachmentExtractor()
        attachments = extractor.extract_from_content(content)
        assert len(attachments) == 2
        assert "screenshot.png" in attachments[0].local_path
        assert attachments[1].name == "Architecture"

    def test_deduplicate_attachments(self):
        """Test that duplicate paths are not extracted twice."""
        content = """
# Story

![Screenshot](./images/test.png)

More content with same image:

![Screenshot](./images/test.png)

#### Attachments
- [Screenshot](./images/test.png)
"""
        extractor = AttachmentExtractor()
        attachments = extractor.extract_from_content(content)
        assert len(attachments) == 1


class TestAttachmentSyncConfig:
    """Tests for AttachmentSyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AttachmentSyncConfig()
        assert config.direction == AttachmentSyncDirection.UPLOAD
        assert config.dry_run is True
        assert config.attachments_dir == "attachments"
        assert config.max_file_size == 50 * 1024 * 1024
        assert config.skip_existing is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = AttachmentSyncConfig(
            direction=AttachmentSyncDirection.BIDIRECTIONAL,
            dry_run=False,
            attachments_dir="files",
            max_file_size=10 * 1024 * 1024,
            allowed_extensions=[".pdf", ".docx"],
        )
        assert config.direction == AttachmentSyncDirection.BIDIRECTIONAL
        assert config.dry_run is False
        assert config.attachments_dir == "files"
        assert config.allowed_extensions == [".pdf", ".docx"]


class TestAttachmentSyncResult:
    """Tests for AttachmentSyncResult."""

    def test_empty_result(self):
        """Test empty sync result."""
        result = AttachmentSyncResult(story_id="US-001")
        assert result.success
        assert result.total_uploaded == 0
        assert result.total_downloaded == 0
        assert result.total_synced == 0

    def test_result_with_uploads(self):
        """Test result with uploaded files."""
        result = AttachmentSyncResult(
            story_id="US-001",
            issue_key="PROJ-123",
            uploaded=[
                Attachment(name="a.png", filename="a.png"),
                Attachment(name="b.png", filename="b.png"),
            ],
        )
        assert result.success
        assert result.total_uploaded == 2
        assert result.total_synced == 2

    def test_result_with_errors(self):
        """Test result with errors."""
        att = Attachment(name="bad.png", filename="bad.png")
        result = AttachmentSyncResult(
            story_id="US-001",
            errors=[(att, "File not found")],
        )
        assert not result.success


class TestAttachmentStore:
    """Tests for AttachmentStore persistence."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving attachments."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "attachments.json"
            store = AttachmentStore(store_path)

            attachments = [
                Attachment(name="a.png", filename="a.png", local_path="./a.png"),
                Attachment(name="b.pdf", filename="b.pdf", remote_id="123"),
            ]
            store.save_attachments("US-001", attachments)

            # Retrieve
            restored = store.get_attachments("US-001")
            assert len(restored) == 2
            assert restored[0].name == "a.png"
            assert restored[1].remote_id == "123"

    def test_clear_story(self):
        """Test clearing attachments for a story."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "attachments.json"
            store = AttachmentStore(store_path)

            store.save_attachments("US-001", [Attachment(name="test.png", filename="test.png")])
            store.clear_story("US-001")

            assert store.get_attachments("US-001") == []


class TestExtractAttachmentsFromMarkdown:
    """Tests for the convenience function."""

    def test_extract_from_file(self):
        """Test extracting attachments from a markdown file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "EPIC.md"
            md_path.write_text("""
# Epic

#### Attachments
- [Test](./test.png)
""")
            attachments = extract_attachments_from_markdown(md_path)
            assert len(attachments) == 1
            assert attachments[0].name == "Test"


class TestAttachmentSyncer:
    """Tests for AttachmentSyncer."""

    def test_syncer_dry_run(self):
        """Test syncer in dry-run mode."""

        class MockTracker:
            name = "MockTracker"

            def get_issue_attachments(self, issue_key: str):
                return []

            def upload_attachment(self, issue_key: str, file_path: str, name: str | None):
                return {"id": "mock-123", "filename": name or "file"}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test.png"
            test_file.write_bytes(b"fake image content")

            md_path = Path(tmpdir) / "EPIC.md"
            md_path.write_text(f"""
# Epic

#### Attachments
- [Test]({test_file.name})
""")

            config = AttachmentSyncConfig(
                direction=AttachmentSyncDirection.UPLOAD,
                dry_run=True,
            )
            syncer = AttachmentSyncer(MockTracker(), config)

            local_attachments = extract_attachments_from_markdown(md_path)
            result = syncer.sync_story_attachments(
                story_id="US-001",
                issue_key="PROJ-123",
                local_attachments=local_attachments,
                markdown_path=md_path,
            )

            # Dry run should skip the upload
            assert len(result.skipped) == 1
            assert result.total_uploaded == 0

    def test_syncer_skip_large_files(self):
        """Test that large files are skipped."""

        class MockTracker:
            name = "MockTracker"

            def get_issue_attachments(self, issue_key: str):
                return []

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "large.bin"
            test_file.write_bytes(b"x" * 1000)

            md_path = Path(tmpdir) / "EPIC.md"
            md_path.write_text(f"""
# Epic

#### Attachments
- [Large]({test_file.name})
""")

            config = AttachmentSyncConfig(
                direction=AttachmentSyncDirection.UPLOAD,
                dry_run=False,
                max_file_size=500,  # Smaller than file
            )
            syncer = AttachmentSyncer(MockTracker(), config)

            local_attachments = extract_attachments_from_markdown(md_path)
            result = syncer.sync_story_attachments(
                story_id="US-001",
                issue_key="PROJ-123",
                local_attachments=local_attachments,
                markdown_path=md_path,
            )

            # Should have error for file too large
            assert len(result.errors) == 1
            assert "too large" in result.errors[0][1]

    def test_syncer_filter_extensions(self):
        """Test filtering by extension."""

        class MockTracker:
            name = "MockTracker"

            def get_issue_attachments(self, issue_key: str):
                return []

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            pdf_file = Path(tmpdir) / "doc.pdf"
            pdf_file.write_bytes(b"pdf content")

            txt_file = Path(tmpdir) / "notes.txt"
            txt_file.write_bytes(b"text content")

            md_path = Path(tmpdir) / "EPIC.md"
            md_path.write_text(f"""
# Epic

#### Attachments
- [Doc]({pdf_file.name})
- [Notes]({txt_file.name})
""")

            config = AttachmentSyncConfig(
                direction=AttachmentSyncDirection.UPLOAD,
                dry_run=True,
                allowed_extensions=[".pdf"],  # Only PDFs
            )
            syncer = AttachmentSyncer(MockTracker(), config)

            local_attachments = extract_attachments_from_markdown(md_path)
            result = syncer.sync_story_attachments(
                story_id="US-001",
                issue_key="PROJ-123",
                local_attachments=local_attachments,
                markdown_path=md_path,
            )

            # PDF should be in skipped (dry run), txt should be skipped due to filter
            # Both end up in skipped but for different reasons
            assert len(result.skipped) == 2


class TestAttachmentStatus:
    """Tests for AttachmentStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert AttachmentStatus.PENDING.value == "pending"
        assert AttachmentStatus.SYNCED.value == "synced"
        assert AttachmentStatus.MODIFIED.value == "modified"
        assert AttachmentStatus.CONFLICT.value == "conflict"
        assert AttachmentStatus.ERROR.value == "error"
        assert AttachmentStatus.SKIPPED.value == "skipped"


class TestAttachmentSyncDirection:
    """Tests for AttachmentSyncDirection enum."""

    def test_direction_values(self):
        """Test all direction values exist."""
        assert AttachmentSyncDirection.UPLOAD.value == "upload"
        assert AttachmentSyncDirection.DOWNLOAD.value == "download"
        assert AttachmentSyncDirection.BIDIRECTIONAL.value == "bidirectional"
