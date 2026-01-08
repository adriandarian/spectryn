"""
Changelog Generator - Generate changelog from sync history.

Creates formatted changelogs from the sync history database,
supporting multiple output formats and customization options.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from spectryn.core.ports.sync_history import SyncHistoryEntry, SyncHistoryPort


logger = logging.getLogger(__name__)


class ChangelogFormat(Enum):
    """Output format for changelog."""

    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    PLAIN = "plain"
    KEEP_A_CHANGELOG = "keepachangelog"


class ChangeType(Enum):
    """Type of change for categorization."""

    ADDED = "added"
    CHANGED = "changed"
    FIXED = "fixed"
    REMOVED = "removed"
    SYNCED = "synced"


@dataclass
class ChangeEntry:
    """A single changelog entry."""

    timestamp: datetime
    change_type: ChangeType
    story_id: str
    title: str
    description: str
    author: str | None = None
    tracker_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangelogVersion:
    """A version/release in the changelog."""

    version: str
    date: datetime
    entries: list[ChangeEntry] = field(default_factory=list)
    summary: str | None = None


@dataclass
class ChangelogOptions:
    """Options for changelog generation."""

    # Output settings
    format: ChangelogFormat = ChangelogFormat.MARKDOWN
    output_file: Path | None = None

    # Filtering
    since: datetime | None = None
    until: datetime | None = None
    days: int | None = None
    include_syncs: bool = True
    include_creates: bool = True
    include_updates: bool = True
    include_deletes: bool = True

    # Grouping
    group_by_date: bool = True
    group_by_type: bool = True
    group_by_epic: bool = False

    # Content
    include_metadata: bool = False
    include_author: bool = True
    include_tracker_links: bool = True
    max_entries: int | None = None

    # Format-specific
    version_prefix: str = "v"
    date_format: str = "%Y-%m-%d"
    header: str = "# Changelog"


class ChangelogGenerator:
    """Generate changelogs from sync history."""

    def __init__(
        self,
        history_store: SyncHistoryPort,
        options: ChangelogOptions | None = None,
    ):
        """
        Initialize changelog generator.

        Args:
            history_store: Sync history storage backend.
            options: Generation options.
        """
        self.history = history_store
        self.options = options or ChangelogOptions()
        self.logger = logging.getLogger(__name__)

    def generate(self) -> str:
        """
        Generate changelog content.

        Returns:
            Formatted changelog string.
        """
        # Fetch sync history entries
        entries_raw = self._fetch_entries()

        # Convert to change entries
        entries = self._entries_to_changes(entries_raw)

        # Apply filters
        entries = self._filter_entries(entries)

        # Group entries
        grouped = self._group_entries(entries)

        # Format output
        output = self._format_changelog(grouped)

        # Write to file if specified
        if self.options.output_file:
            self.options.output_file.write_text(output, encoding="utf-8")
            self.logger.info(f"Wrote changelog to {self.options.output_file}")

        return output

    def _fetch_entries(self) -> list[SyncHistoryEntry]:
        """Fetch sync history entries from history store."""
        # Calculate date range
        since = self.options.since
        until = self.options.until

        if self.options.days and not since:
            since = datetime.now() - timedelta(days=self.options.days)

        # Get all entries and filter by date
        try:
            all_entries = self.history.list_entries()
        except Exception as e:
            self.logger.warning(f"Could not fetch history: {e}")
            return []

        entries = []
        for entry in all_entries:
            if since and entry.completed_at < since:
                continue
            if until and entry.completed_at > until:
                continue
            entries.append(entry)

        return sorted(entries, key=lambda e: e.completed_at, reverse=True)

    def _entries_to_changes(self, entries: list[SyncHistoryEntry]) -> list[ChangeEntry]:
        """Convert sync history entries to changelog entries."""
        changes = []

        for entry in entries:
            change_type = self._determine_change_type_from_outcome(entry)

            change = ChangeEntry(
                timestamp=entry.completed_at,
                change_type=change_type,
                story_id=entry.epic_key or "unknown",
                title=f"Sync: {entry.markdown_path}",
                description=f"{entry.operations_succeeded}/{entry.operations_total} operations",
                author=entry.user,
                tracker_key=entry.epic_key,
                metadata=entry.metadata or {},
            )
            changes.append(change)

        return changes

    def _determine_change_type_from_outcome(self, entry: SyncHistoryEntry) -> ChangeType:
        """Determine the type of change from a sync history entry."""
        from spectryn.core.ports.sync_history import SyncOutcome

        if entry.outcome == SyncOutcome.SUCCESS:
            # Determine based on operations
            if entry.operations_succeeded > 0:
                return ChangeType.SYNCED
        elif entry.outcome == SyncOutcome.FAILED:
            return ChangeType.CHANGED  # Attempted change
        elif entry.outcome == SyncOutcome.PARTIAL:
            return ChangeType.CHANGED

        return ChangeType.SYNCED

    def _filter_entries(self, entries: list[ChangeEntry]) -> list[ChangeEntry]:
        """Apply filters to entries."""
        filtered = []

        for entry in entries:
            # Filter by change type
            if entry.change_type == ChangeType.ADDED and not self.options.include_creates:
                continue
            if entry.change_type == ChangeType.CHANGED and not self.options.include_updates:
                continue
            if entry.change_type == ChangeType.REMOVED and not self.options.include_deletes:
                continue
            if entry.change_type == ChangeType.SYNCED and not self.options.include_syncs:
                continue

            filtered.append(entry)

        # Apply max entries limit
        if self.options.max_entries:
            filtered = filtered[: self.options.max_entries]

        return filtered

    def _group_entries(self, entries: list[ChangeEntry]) -> dict[str, dict[str, list[ChangeEntry]]]:
        """Group entries by date and/or type."""
        grouped: dict[str, dict[str, list[ChangeEntry]]] = {}

        for entry in entries:
            # Determine group key
            if self.options.group_by_date:
                date_key = entry.timestamp.strftime(self.options.date_format)
            else:
                date_key = "All Changes"

            if date_key not in grouped:
                grouped[date_key] = {}

            # Determine type key
            if self.options.group_by_type:
                type_key = entry.change_type.value.capitalize()
            else:
                type_key = "Changes"

            if type_key not in grouped[date_key]:
                grouped[date_key][type_key] = []

            grouped[date_key][type_key].append(entry)

        return grouped

    def _format_changelog(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format the grouped entries into output."""
        format_method = {
            ChangelogFormat.MARKDOWN: self._format_markdown,
            ChangelogFormat.JSON: self._format_json,
            ChangelogFormat.HTML: self._format_html,
            ChangelogFormat.PLAIN: self._format_plain,
            ChangelogFormat.KEEP_A_CHANGELOG: self._format_keepachangelog,
        }.get(self.options.format, self._format_markdown)

        return format_method(grouped)

    def _format_markdown(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format as Markdown."""
        lines = [
            self.options.header,
            "",
            "All notable changes to this project are documented below.",
            "",
            "---",
            "",
        ]

        for date_key in sorted(grouped.keys(), reverse=True):
            lines.append(f"## {date_key}")
            lines.append("")

            type_groups = grouped[date_key]
            for type_key in ["Added", "Changed", "Fixed", "Removed", "Synced"]:
                if type_key not in type_groups:
                    continue

                entries = type_groups[type_key]
                lines.append(f"### {type_key}")
                lines.append("")

                for entry in entries:
                    line = f"- **{entry.story_id}**: {entry.title}"
                    if entry.tracker_key and self.options.include_tracker_links:
                        line += f" (`{entry.tracker_key}`)"
                    if entry.author and self.options.include_author:
                        line += f" - @{entry.author}"
                    lines.append(line)

                lines.append("")

        return "\n".join(lines)

    def _format_json(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format as JSON."""
        import json

        data: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "changelog": [],
        }

        for date_key in sorted(grouped.keys(), reverse=True):
            date_entry: dict[str, Any] = {
                "date": date_key,
                "changes": {},
            }

            for type_key, entries in grouped[date_key].items():
                date_entry["changes"][type_key.lower()] = [
                    {
                        "story_id": e.story_id,
                        "title": e.title,
                        "tracker_key": e.tracker_key,
                        "author": e.author,
                        "timestamp": e.timestamp.isoformat(),
                        **({"metadata": e.metadata} if self.options.include_metadata else {}),
                    }
                    for e in entries
                ]

            data["changelog"].append(date_entry)

        return json.dumps(data, indent=2)

    def _format_html(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format as HTML."""
        lines = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "  <meta charset='UTF-8'>",
            "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "  <title>Changelog</title>",
            "  <style>",
            "    body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; padding: 1rem; }",
            "    h1 { color: #333; border-bottom: 2px solid #333; padding-bottom: 0.5rem; }",
            "    h2 { color: #555; margin-top: 2rem; }",
            "    h3 { color: #666; font-size: 1rem; }",
            "    ul { list-style-type: disc; padding-left: 1.5rem; }",
            "    li { margin: 0.5rem 0; }",
            "    .story-id { font-weight: bold; color: #0066cc; }",
            "    .tracker-key { color: #888; font-size: 0.9rem; }",
            "    .author { color: #666; font-style: italic; }",
            "    .added { border-left: 4px solid #28a745; padding-left: 1rem; }",
            "    .changed { border-left: 4px solid #ffc107; padding-left: 1rem; }",
            "    .fixed { border-left: 4px solid #17a2b8; padding-left: 1rem; }",
            "    .removed { border-left: 4px solid #dc3545; padding-left: 1rem; }",
            "  </style>",
            "</head>",
            "<body>",
            f"  <h1>{self.options.header.replace('# ', '')}</h1>",
            "  <p>All notable changes to this project are documented below.</p>",
        ]

        for date_key in sorted(grouped.keys(), reverse=True):
            lines.append(f"  <h2>{date_key}</h2>")

            for type_key, entries in grouped[date_key].items():
                css_class = type_key.lower()
                lines.append(f"  <div class='{css_class}'>")
                lines.append(f"    <h3>{type_key}</h3>")
                lines.append("    <ul>")

                for entry in entries:
                    html_line = (
                        f"      <li><span class='story-id'>{entry.story_id}</span>: {entry.title}"
                    )
                    if entry.tracker_key and self.options.include_tracker_links:
                        html_line += f" <span class='tracker-key'>({entry.tracker_key})</span>"
                    if entry.author and self.options.include_author:
                        html_line += f" <span class='author'>@{entry.author}</span>"
                    html_line += "</li>"
                    lines.append(html_line)

                lines.append("    </ul>")
                lines.append("  </div>")

        lines.extend(
            [
                "</body>",
                "</html>",
            ]
        )

        return "\n".join(lines)

    def _format_plain(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format as plain text."""
        lines = [
            self.options.header.replace("# ", "").upper(),
            "=" * 60,
            "",
        ]

        for date_key in sorted(grouped.keys(), reverse=True):
            lines.append(date_key)
            lines.append("-" * len(date_key))
            lines.append("")

            for type_key, entries in grouped[date_key].items():
                lines.append(f"  {type_key.upper()}:")
                for entry in entries:
                    lines.append(f"    * {entry.story_id}: {entry.title}")
                lines.append("")

        return "\n".join(lines)

    def _format_keepachangelog(self, grouped: dict[str, dict[str, list[ChangeEntry]]]) -> str:
        """Format following Keep a Changelog standard."""
        lines = [
            "# Changelog",
            "",
            "All notable changes to this project will be documented in this file.",
            "",
            "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),",
            "and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).",
            "",
        ]

        for date_key in sorted(grouped.keys(), reverse=True):
            lines.append(f"## [{self.options.version_prefix}{date_key}] - {date_key}")
            lines.append("")

            type_groups = grouped[date_key]
            for type_key in ["Added", "Changed", "Fixed", "Removed"]:
                if type_key not in type_groups:
                    continue

                lines.append(f"### {type_key}")
                lines.append("")

                for entry in type_groups[type_key]:
                    lines.append(f"- {entry.title} ({entry.story_id})")

                lines.append("")

        return "\n".join(lines)


def generate_changelog(
    history_store: SyncHistoryPort,
    format: str = "markdown",
    days: int | None = None,
    output: str | Path | None = None,
    **kwargs: Any,
) -> str:
    """
    Generate a changelog from sync history.

    Args:
        history_store: Sync history storage.
        format: Output format (markdown, json, html, plain, keepachangelog).
        days: Number of days to include (None for all).
        output: Output file path.
        **kwargs: Additional options for ChangelogOptions.

    Returns:
        Formatted changelog string.
    """
    try:
        fmt = ChangelogFormat(format.lower())
    except ValueError:
        fmt = ChangelogFormat.MARKDOWN

    options = ChangelogOptions(
        format=fmt,
        days=days,
        output_file=Path(output) if output else None,
        **kwargs,
    )

    generator = ChangelogGenerator(history_store, options)
    return generator.generate()
