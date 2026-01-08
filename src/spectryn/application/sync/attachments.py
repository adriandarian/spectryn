"""
Attachment Sync - Upload/download attachments between markdown and issue trackers.

This module provides comprehensive attachment synchronization:
- Extract attachment references from markdown files
- Upload local files to issue trackers
- Download remote attachments to local filesystem
- Track attachment sync state for bidirectional sync
- Handle attachment conflicts and deduplication
"""

import hashlib
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from spectryn.core.ports.issue_tracker import IssueTrackerPort

logger = logging.getLogger(__name__)


class AttachmentSyncDirection(Enum):
    """Direction of attachment sync."""

    UPLOAD = "upload"  # Local → Tracker
    DOWNLOAD = "download"  # Tracker → Local
    BIDIRECTIONAL = "bidirectional"  # Both directions


class AttachmentStatus(Enum):
    """Status of an attachment in sync."""

    PENDING = "pending"  # Not yet synced
    SYNCED = "synced"  # Successfully synced
    MODIFIED = "modified"  # Changed since last sync
    CONFLICT = "conflict"  # Both local and remote changed
    ERROR = "error"  # Sync failed
    SKIPPED = "skipped"  # Intentionally skipped


@dataclass
class Attachment:
    """
    Represents a file attachment for a story or issue.

    Can be either a local file or a remote attachment from an issue tracker.
    """

    id: str = ""
    name: str = ""  # Display name
    filename: str = ""  # Actual file name
    local_path: str | None = None  # Path relative to markdown file
    remote_url: str | None = None  # URL in issue tracker
    remote_id: str | None = None  # ID in issue tracker

    # File metadata
    size: int = 0
    mime_type: str = ""
    content_hash: str | None = None  # MD5/SHA256 for change detection

    # Sync metadata
    status: AttachmentStatus = AttachmentStatus.PENDING
    last_synced: datetime | None = None
    error_message: str | None = None

    # Additional metadata
    description: str = ""
    created_at: datetime | None = None
    created_by: str | None = None

    def __post_init__(self) -> None:
        """Generate ID if not provided."""
        if not self.id:
            self.id = hashlib.md5(
                f"{self.name}:{self.local_path}:{self.remote_id}".encode()
            ).hexdigest()[:12]

    @property
    def is_local(self) -> bool:
        """Check if attachment exists locally."""
        return self.local_path is not None

    @property
    def is_remote(self) -> bool:
        """Check if attachment exists in tracker."""
        return self.remote_id is not None

    @property
    def is_synced(self) -> bool:
        """Check if attachment is synced (exists both locally and remotely)."""
        return self.is_local and self.is_remote

    def compute_local_hash(self, base_path: Path | None = None) -> str | None:
        """Compute hash of local file content."""
        if not self.local_path:
            return None

        file_path = Path(self.local_path)
        if base_path:
            file_path = base_path / file_path

        if not file_path.exists():
            return None

        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "filename": self.filename,
            "local_path": self.local_path,
            "remote_url": self.remote_url,
            "remote_id": self.remote_id,
            "size": self.size,
            "mime_type": self.mime_type,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attachment":
        """Create from dictionary."""
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = AttachmentStatus(status)

        last_synced = data.get("last_synced")
        if isinstance(last_synced, str):
            last_synced = datetime.fromisoformat(last_synced)

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            filename=data.get("filename", ""),
            local_path=data.get("local_path"),
            remote_url=data.get("remote_url"),
            remote_id=data.get("remote_id"),
            size=data.get("size", 0),
            mime_type=data.get("mime_type", ""),
            content_hash=data.get("content_hash"),
            status=status,
            last_synced=last_synced,
            description=data.get("description", ""),
        )

    @classmethod
    def from_markdown_link(cls, link_text: str, link_path: str) -> "Attachment":
        """Create attachment from markdown link [text](path)."""
        filename = Path(link_path).name
        mime_type, _ = mimetypes.guess_type(filename)

        return cls(
            name=link_text or filename,
            filename=filename,
            local_path=link_path,
            mime_type=mime_type or "application/octet-stream",
        )

    @classmethod
    def from_remote(cls, data: dict[str, Any]) -> "Attachment":
        """Create attachment from remote tracker data."""
        return cls(
            name=data.get("name", data.get("filename", "")),
            filename=data.get("filename", data.get("name", "")),
            remote_url=data.get("url", data.get("content", "")),
            remote_id=str(data.get("id", "")),
            size=data.get("size", 0),
            mime_type=data.get("mime_type", data.get("mimeType", "")),
            created_by=data.get("author", data.get("created_by")),
        )

    def to_markdown_link(self) -> str:
        """Convert to markdown link format."""
        path = self.local_path or self.remote_url or self.filename
        return f"[{self.name}]({path})"


@dataclass
class AttachmentSyncResult:
    """Result of attachment sync operation."""

    story_id: str
    issue_key: str | None = None
    uploaded: list[Attachment] = field(default_factory=list)
    downloaded: list[Attachment] = field(default_factory=list)
    skipped: list[Attachment] = field(default_factory=list)
    errors: list[tuple[Attachment, str]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Check if sync was successful (no errors)."""
        return len(self.errors) == 0

    @property
    def total_uploaded(self) -> int:
        return len(self.uploaded)

    @property
    def total_downloaded(self) -> int:
        return len(self.downloaded)

    @property
    def total_synced(self) -> int:
        return self.total_uploaded + self.total_downloaded


@dataclass
class AttachmentSyncConfig:
    """Configuration for attachment sync."""

    direction: AttachmentSyncDirection = AttachmentSyncDirection.UPLOAD
    dry_run: bool = True

    # Local storage
    attachments_dir: str = "attachments"  # Relative to markdown file
    create_dirs: bool = True
    preserve_structure: bool = True  # Keep remote folder structure

    # Filters
    allowed_extensions: list[str] = field(default_factory=list)  # Empty = all allowed
    max_file_size: int = 50 * 1024 * 1024  # 50MB default
    skip_existing: bool = True  # Skip if already exists at target

    # Deduplication
    deduplicate_by_hash: bool = True
    deduplicate_by_name: bool = False

    # Cleanup
    delete_orphaned_remote: bool = False  # Delete remote attachments not in markdown
    delete_orphaned_local: bool = False  # Delete local files not in tracker


class AttachmentExtractor:
    """Extract attachment references from markdown content."""

    # Patterns for various attachment formats
    MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    WIKILINK = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

    # Attachment section pattern
    ATTACHMENT_SECTION = re.compile(
        r"#{2,4}\s*Attachments?\s*\n([\s\S]*?)(?=#{2,4}|\Z)", re.IGNORECASE
    )

    # Image extensions (for detecting embedded images)
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}

    def __init__(self, base_path: Path | None = None):
        """
        Initialize the extractor.

        Args:
            base_path: Base path for resolving relative paths
        """
        self.base_path = base_path

    def extract_from_content(
        self,
        content: str,
        include_images: bool = True,
        include_documents: bool = True,
    ) -> list[Attachment]:
        """
        Extract all attachment references from markdown content.

        Args:
            content: Markdown content
            include_images: Include image links
            include_documents: Include document links

        Returns:
            List of Attachment objects
        """
        attachments: list[Attachment] = []
        seen_paths: set[str] = set()

        # 1. Extract from Attachments section
        section_match = self.ATTACHMENT_SECTION.search(content)
        if section_match:
            section_content = section_match.group(1)
            for match in self.MARKDOWN_LINK.finditer(section_content):
                text, path = match.groups()
                if path not in seen_paths and self._is_local_file(path):
                    attachments.append(Attachment.from_markdown_link(text, path))
                    seen_paths.add(path)

        # 2. Extract embedded images
        if include_images:
            for match in self.MARKDOWN_IMAGE.finditer(content):
                alt_text, path = match.groups()
                if path not in seen_paths and self._is_local_file(path):
                    attachments.append(Attachment.from_markdown_link(alt_text or "image", path))
                    seen_paths.add(path)

        # 3. Extract Obsidian wikilinks (images)
        for match in self.WIKILINK.finditer(content):
            file_path, alias = match.groups()
            if file_path not in seen_paths:
                attachments.append(
                    Attachment.from_markdown_link(alias or Path(file_path).stem, file_path)
                )
                seen_paths.add(file_path)

        # 4. Extract document links if requested
        if include_documents:
            for match in self.MARKDOWN_LINK.finditer(content):
                text, path = match.groups()
                if path not in seen_paths and self._is_document(path):
                    attachments.append(Attachment.from_markdown_link(text, path))
                    seen_paths.add(path)

        # Compute local file info
        for attachment in attachments:
            self._enrich_attachment(attachment)

        return attachments

    def _is_local_file(self, path: str) -> bool:
        """Check if path appears to be a local file (not URL)."""
        return not path.startswith(("http://", "https://", "ftp://", "data:"))

    def _is_document(self, path: str) -> bool:
        """Check if path appears to be a document file."""
        if not self._is_local_file(path):
            return False

        ext = Path(path).suffix.lower()
        document_extensions = {
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".txt",
            ".csv",
            ".zip",
            ".tar",
            ".gz",
            ".json",
            ".xml",
            ".yaml",
            ".yml",
        }
        return ext in document_extensions

    def _enrich_attachment(self, attachment: Attachment) -> None:
        """Add file info to attachment if local file exists."""
        if not attachment.local_path or not self.base_path:
            return

        file_path = self.base_path / attachment.local_path
        if file_path.exists():
            attachment.size = file_path.stat().st_size
            attachment.content_hash = attachment.compute_local_hash(self.base_path)
            if not attachment.mime_type:
                mime_type, _ = mimetypes.guess_type(str(file_path))
                attachment.mime_type = mime_type or "application/octet-stream"


class AttachmentSyncer:
    """
    Synchronize attachments between markdown files and issue trackers.

    Supports:
    - Uploading local attachments to issues
    - Downloading remote attachments to local filesystem
    - Bidirectional sync with conflict detection
    - Deduplication based on content hash or name
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort",
        config: AttachmentSyncConfig | None = None,
    ):
        """
        Initialize the syncer.

        Args:
            tracker: Issue tracker adapter
            config: Sync configuration
        """
        self.tracker = tracker
        self.config = config or AttachmentSyncConfig()
        self.logger = logging.getLogger("AttachmentSyncer")

    def sync_story_attachments(
        self,
        story_id: str,
        issue_key: str,
        local_attachments: list[Attachment],
        markdown_path: Path,
    ) -> AttachmentSyncResult:
        """
        Sync attachments for a single story/issue.

        Args:
            story_id: Local story ID
            issue_key: Remote issue key
            local_attachments: Attachments extracted from markdown
            markdown_path: Path to the markdown file

        Returns:
            AttachmentSyncResult with sync details
        """
        result = AttachmentSyncResult(story_id=story_id, issue_key=issue_key)

        # Get remote attachments
        try:
            remote_attachments = self._get_remote_attachments(issue_key)
        except Exception as e:
            self.logger.error(f"Failed to get remote attachments for {issue_key}: {e}")
            remote_attachments = []

        # Build lookup maps
        remote_by_name = {a.filename.lower(): a for a in remote_attachments}
        remote_by_hash = {a.content_hash: a for a in remote_attachments if a.content_hash}

        base_path = markdown_path.parent

        # Process based on sync direction
        if self.config.direction in (
            AttachmentSyncDirection.UPLOAD,
            AttachmentSyncDirection.BIDIRECTIONAL,
        ):
            for attachment in local_attachments:
                self._upload_attachment(
                    attachment, issue_key, base_path, remote_by_name, remote_by_hash, result
                )

        if self.config.direction in (
            AttachmentSyncDirection.DOWNLOAD,
            AttachmentSyncDirection.BIDIRECTIONAL,
        ):
            local_by_name = {a.filename.lower(): a for a in local_attachments}
            for attachment in remote_attachments:
                self._download_attachment(attachment, base_path, local_by_name, result)

        return result

    def _get_remote_attachments(self, issue_key: str) -> list[Attachment]:
        """Fetch remote attachments from tracker."""
        # Use the tracker's get_issue_attachments if available
        if hasattr(self.tracker, "get_issue_attachments"):
            raw_attachments = self.tracker.get_issue_attachments(issue_key)
            return [Attachment.from_remote(a) for a in raw_attachments]
        return []

    def _upload_attachment(
        self,
        attachment: Attachment,
        issue_key: str,
        base_path: Path,
        remote_by_name: dict[str, Attachment],
        remote_by_hash: dict[str, Attachment],
        result: AttachmentSyncResult,
    ) -> None:
        """Upload a local attachment to the tracker."""
        if not attachment.local_path:
            return

        file_path = base_path / attachment.local_path
        if not file_path.exists():
            result.errors.append((attachment, f"File not found: {file_path}"))
            return

        # Check file size
        if file_path.stat().st_size > self.config.max_file_size:
            result.errors.append((attachment, f"File too large: {file_path.stat().st_size} bytes"))
            return

        # Check extension filter
        if self.config.allowed_extensions:
            ext = file_path.suffix.lower()
            if ext not in self.config.allowed_extensions:
                attachment.status = AttachmentStatus.SKIPPED
                result.skipped.append(attachment)
                return

        # Check for duplicates
        if self.config.skip_existing:
            if self.config.deduplicate_by_hash and attachment.content_hash:
                if attachment.content_hash in remote_by_hash:
                    attachment.status = AttachmentStatus.SYNCED
                    attachment.remote_id = remote_by_hash[attachment.content_hash].remote_id
                    result.skipped.append(attachment)
                    self.logger.debug(f"Skipping duplicate by hash: {attachment.filename}")
                    return

            if self.config.deduplicate_by_name:
                if attachment.filename.lower() in remote_by_name:
                    attachment.status = AttachmentStatus.SYNCED
                    attachment.remote_id = remote_by_name[attachment.filename.lower()].remote_id
                    result.skipped.append(attachment)
                    self.logger.debug(f"Skipping duplicate by name: {attachment.filename}")
                    return

        # Upload the file
        if self.config.dry_run:
            self.logger.info(f"[DRY-RUN] Would upload {attachment.filename} to {issue_key}")
            attachment.status = AttachmentStatus.PENDING
            result.skipped.append(attachment)
            return

        try:
            if hasattr(self.tracker, "upload_attachment"):
                remote_result = self.tracker.upload_attachment(
                    issue_key, str(file_path), attachment.filename
                )
                attachment.remote_id = str(remote_result.get("id", ""))
                attachment.remote_url = remote_result.get("url", remote_result.get("self", ""))
                attachment.status = AttachmentStatus.SYNCED
                attachment.last_synced = datetime.now()
                result.uploaded.append(attachment)
                self.logger.info(f"Uploaded {attachment.filename} to {issue_key}")
            else:
                result.errors.append(
                    (attachment, f"Tracker {self.tracker.name} does not support attachments")
                )
        except Exception as e:
            attachment.status = AttachmentStatus.ERROR
            attachment.error_message = str(e)
            result.errors.append((attachment, str(e)))
            self.logger.error(f"Failed to upload {attachment.filename}: {e}")

    def _download_attachment(
        self,
        attachment: Attachment,
        base_path: Path,
        local_by_name: dict[str, Attachment],
        result: AttachmentSyncResult,
    ) -> None:
        """Download a remote attachment to local filesystem."""
        if not attachment.remote_url:
            return

        # Determine download path
        download_dir = base_path / self.config.attachments_dir
        if self.config.create_dirs:
            download_dir.mkdir(parents=True, exist_ok=True)

        target_path = download_dir / attachment.filename

        # Check if already exists locally
        if self.config.skip_existing and attachment.filename.lower() in local_by_name:
            local = local_by_name[attachment.filename.lower()]
            if local.local_path:
                local_file = base_path / local.local_path
                if local_file.exists():
                    # Check if content matches (if we have hashes)
                    if (
                        self.config.deduplicate_by_hash
                        and attachment.content_hash
                        and local.content_hash == attachment.content_hash
                    ):
                        attachment.status = AttachmentStatus.SYNCED
                        result.skipped.append(attachment)
                        return

        if self.config.dry_run:
            self.logger.info(f"[DRY-RUN] Would download {attachment.filename} to {target_path}")
            attachment.status = AttachmentStatus.PENDING
            result.skipped.append(attachment)
            return

        try:
            if hasattr(self.tracker, "download_attachment"):
                success = self.tracker.download_attachment(
                    attachment.remote_id or "",
                    attachment.remote_id or "",
                    str(target_path),
                )
                if success:
                    attachment.local_path = str(target_path.relative_to(base_path))
                    attachment.status = AttachmentStatus.SYNCED
                    attachment.last_synced = datetime.now()
                    result.downloaded.append(attachment)
                    self.logger.info(f"Downloaded {attachment.filename} to {target_path}")
                else:
                    result.errors.append((attachment, "Download returned False"))
            else:
                # Fallback: try to download via URL
                self._download_via_url(attachment, target_path, base_path, result)
        except Exception as e:
            attachment.status = AttachmentStatus.ERROR
            attachment.error_message = str(e)
            result.errors.append((attachment, str(e)))
            self.logger.error(f"Failed to download {attachment.filename}: {e}")

    def _download_via_url(
        self,
        attachment: Attachment,
        target_path: Path,
        base_path: Path,
        result: AttachmentSyncResult,
    ) -> None:
        """Download attachment via HTTP URL."""
        if not attachment.remote_url:
            result.errors.append((attachment, "No remote URL available"))
            return

        try:
            import requests

            # Some trackers require authentication for attachments
            response = requests.get(attachment.remote_url, stream=True, timeout=60)
            response.raise_for_status()

            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            attachment.local_path = str(target_path.relative_to(base_path))
            attachment.status = AttachmentStatus.SYNCED
            attachment.last_synced = datetime.now()
            result.downloaded.append(attachment)
            self.logger.info(f"Downloaded {attachment.filename} to {target_path}")
        except Exception as e:
            result.errors.append((attachment, f"HTTP download failed: {e}"))


class AttachmentStore:
    """
    Persistent store for attachment sync state.

    Stores attachment metadata in a JSON file for tracking sync state
    across runs.
    """

    def __init__(self, store_path: Path | None = None):
        """
        Initialize the store.

        Args:
            store_path: Path to the JSON store file
        """
        self.store_path = store_path or Path.home() / ".spectra" / "attachments.json"
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        """Load store from disk."""
        if self.store_path.exists():
            import json

            try:
                with open(self.store_path) as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self) -> None:
        """Save store to disk."""
        import json

        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_attachments(self, story_id: str) -> list[Attachment]:
        """Get stored attachments for a story."""
        raw = self._data.get(story_id, [])
        return [Attachment.from_dict(a) for a in raw]

    def save_attachments(self, story_id: str, attachments: list[Attachment]) -> None:
        """Save attachments for a story."""
        self._data[story_id] = [a.to_dict() for a in attachments]
        self._save()

    def clear_story(self, story_id: str) -> None:
        """Clear attachments for a story."""
        if story_id in self._data:
            del self._data[story_id]
            self._save()


def extract_attachments_from_markdown(
    markdown_path: Path,
    include_images: bool = True,
    include_documents: bool = True,
) -> list[Attachment]:
    """
    Extract attachment references from a markdown file.

    Args:
        markdown_path: Path to the markdown file
        include_images: Include embedded images
        include_documents: Include document links

    Returns:
        List of Attachment objects
    """
    content = markdown_path.read_text(encoding="utf-8")
    extractor = AttachmentExtractor(base_path=markdown_path.parent)
    return extractor.extract_from_content(
        content, include_images=include_images, include_documents=include_documents
    )


def sync_attachments(
    tracker: "IssueTrackerPort",
    story_id: str,
    issue_key: str,
    markdown_path: Path,
    direction: AttachmentSyncDirection = AttachmentSyncDirection.UPLOAD,
    dry_run: bool = True,
    attachments_dir: str = "attachments",
) -> AttachmentSyncResult:
    """
    Convenience function to sync attachments for a story.

    Args:
        tracker: Issue tracker adapter
        story_id: Local story ID
        issue_key: Remote issue key
        markdown_path: Path to the markdown file
        direction: Sync direction
        dry_run: If True, don't make changes
        attachments_dir: Directory for downloaded attachments

    Returns:
        AttachmentSyncResult
    """
    config = AttachmentSyncConfig(
        direction=direction,
        dry_run=dry_run,
        attachments_dir=attachments_dir,
    )

    syncer = AttachmentSyncer(tracker, config)
    local_attachments = extract_attachments_from_markdown(markdown_path)

    return syncer.sync_story_attachments(
        story_id=story_id,
        issue_key=issue_key,
        local_attachments=local_attachments,
        markdown_path=markdown_path,
    )
