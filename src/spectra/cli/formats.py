"""
Output Formats - Multi-format output support for CI pipelines.

Provides JSON, YAML, and Markdown output for:
- Sync results
- Validation results
- Diff results
- Stats and reports
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OutputFormat(str, Enum):
    """Supported output formats."""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"
    MARKDOWN = "markdown"

    @classmethod
    def from_string(cls, value: str) -> "OutputFormat":
        """Parse output format from string."""
        value_lower = value.lower()
        for fmt in cls:
            if fmt.value == value_lower:
                return fmt
        return cls.TEXT


@dataclass
class OutputData:
    """Generic output data container."""

    title: str
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "success": self.success,
            **self.data,
        }
        if self.errors:
            result["errors"] = self.errors
        if self.warnings:
            result["warnings"] = self.warnings
        if self.metadata:
            result["metadata"] = self.metadata
        return result


class OutputFormatter:
    """
    Multi-format output formatter.

    Converts data to JSON, YAML, or Markdown for CI/CD integration.
    """

    def __init__(self, format: OutputFormat = OutputFormat.TEXT, color: bool = True):
        """
        Initialize the formatter.

        Args:
            format: Output format to use.
            color: Whether to use colors (for text/markdown).
        """
        self.format = format
        self.color = color

    def format_output(self, data: OutputData) -> str:
        """
        Format output data.

        Args:
            data: OutputData to format.

        Returns:
            Formatted string.
        """
        if self.format == OutputFormat.JSON:
            return self.to_json(data)
        if self.format == OutputFormat.YAML:
            return self.to_yaml(data)
        if self.format == OutputFormat.MARKDOWN:
            return self.to_markdown(data)
        return self.to_text(data)

    def to_json(self, data: OutputData) -> str:
        """Format as JSON."""
        return json.dumps(data.to_dict(), indent=2, default=self._json_serializer)

    def to_yaml(self, data: OutputData) -> str:
        """Format as YAML."""
        try:
            import yaml

            return yaml.dump(
                data.to_dict(),
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        except ImportError:
            # Fallback to simple YAML-like format
            return self._simple_yaml(data.to_dict())

    def to_markdown(self, data: OutputData) -> str:
        """Format as Markdown."""
        lines = []

        # Title
        lines.append(f"# {data.title}")
        lines.append("")

        # Status badge
        status = "✅ Success" if data.success else "❌ Failed"
        lines.append(f"**Status**: {status}")
        lines.append("")

        # Main data
        if data.data:
            lines.append("## Summary")
            lines.append("")
            lines.extend(self._data_to_markdown(data.data))
            lines.append("")

        # Errors
        if data.errors:
            lines.append("## Errors")
            lines.append("")
            for error in data.errors:
                lines.append(f"- ❌ {error}")
            lines.append("")

        # Warnings
        if data.warnings:
            lines.append("## Warnings")
            lines.append("")
            for warning in data.warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        # Metadata
        if data.metadata:
            lines.append("---")
            lines.append("")
            lines.append("## Metadata")
            lines.append("")
            for key, value in data.metadata.items():
                lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)

    def to_text(self, data: OutputData) -> str:
        """Format as plain text (fallback)."""
        return json.dumps(data.to_dict(), indent=2, default=self._json_serializer)

    def _data_to_markdown(self, data: dict, level: int = 0) -> list[str]:
        """Convert data dict to markdown lines."""
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{'  ' * level}- **{key}**:")
                lines.extend(self._data_to_markdown(value, level + 1))
            elif isinstance(value, list):
                lines.append(f"{'  ' * level}- **{key}**:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{'  ' * (level + 1)}- {self._format_dict_inline(item)}")
                    else:
                        lines.append(f"{'  ' * (level + 1)}- {item}")
            else:
                lines.append(f"{'  ' * level}- **{key}**: {value}")
        return lines

    def _format_dict_inline(self, d: dict) -> str:
        """Format a dict as inline key=value pairs."""
        parts = [f"{k}={v}" for k, v in d.items() if v is not None]
        return ", ".join(parts)

    def _simple_yaml(self, data: dict, indent: int = 0) -> str:
        """Simple YAML-like format without pyyaml."""
        lines = []
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._simple_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.append(self._simple_yaml(item, indent + 2))
                    else:
                        lines.append(f"{prefix}  - {self._yaml_value(item)}")
            else:
                lines.append(f"{prefix}{key}: {self._yaml_value(value)}")
        return "\n".join(lines)

    def _yaml_value(self, value: Any) -> str:
        """Format a value for YAML."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            # Quote strings that need it
            if any(c in value for c in ":#[]{}"):
                return f'"{value}"'
            return value
        return str(value)

    def _json_serializer(self, obj: Any) -> Any:
        """JSON serializer for non-standard types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)


def format_sync_result_output(
    result: Any,
    format: OutputFormat = OutputFormat.JSON,
    epic_key: str = "",
    markdown_path: str = "",
) -> str:
    """
    Format sync result for output.

    Args:
        result: SyncResult object.
        format: Output format.
        epic_key: Epic key being synced.
        markdown_path: Path to markdown file.

    Returns:
        Formatted output string.
    """
    data = OutputData(
        title=f"Sync Result: {epic_key}",
        success=result.success,
        data={
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
        },
        errors=result.errors,
        warnings=result.warnings,
        metadata={
            "epic_key": epic_key,
            "markdown_path": markdown_path,
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Include failed operations if present
    if hasattr(result, "failed_operations") and result.failed_operations:
        data.data["failed_operations"] = [
            {
                "operation": op.operation,
                "issue_key": op.issue_key,
                "error": op.error,
                "story_id": op.story_id,
            }
            for op in result.failed_operations
        ]

    formatter = OutputFormatter(format=format)
    return formatter.format_output(data)


def format_validation_result_output(
    result: Any,
    format: OutputFormat = OutputFormat.JSON,
    file_path: str = "",
) -> str:
    """
    Format validation result for output.

    Args:
        result: ValidationResult object.
        format: Output format.
        file_path: Path to validated file.

    Returns:
        Formatted output string.
    """
    data = OutputData(
        title=f"Validation Result: {file_path}",
        success=result.valid,
        data={
            "valid": result.valid,
            "stories_count": len(result.stories) if hasattr(result, "stories") else 0,
            "errors_count": len(result.errors),
            "warnings_count": len(result.warnings),
            "error_details": [
                {"code": e.code, "message": e.message, "line": getattr(e, "line", None)}
                for e in result.errors
            ],
            "warning_details": [
                {"code": w.code, "message": w.message, "line": getattr(w, "line", None)}
                for w in result.warnings
            ],
        },
        errors=[e.message for e in result.errors],
        warnings=[w.message for w in result.warnings],
        metadata={
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
        },
    )

    formatter = OutputFormatter(format=format)
    return formatter.format_output(data)


def format_diff_result_output(
    diff_result: Any,
    format: OutputFormat = OutputFormat.JSON,
) -> str:
    """
    Format diff result for output.

    Args:
        diff_result: DiffResult object.
        format: Output format.

    Returns:
        Formatted output string.
    """
    data = OutputData(
        title="Diff Result",
        success=True,
        data={
            "has_changes": diff_result.has_changes,
            "total_changes": diff_result.total_changes,
            "local_path": getattr(diff_result, "local_path", ""),
            "remote_source": getattr(diff_result, "remote_source", ""),
            "local_only": getattr(diff_result, "local_only", []),
            "remote_only": getattr(diff_result, "remote_only", []),
            "modified": [
                {
                    "story_id": s.story_id,
                    "title": s.title,
                    "external_key": s.external_key,
                    "field_changes": [
                        {
                            "field": f.field_name,
                            "local": f.local_value,
                            "remote": f.remote_value,
                        }
                        for f in s.field_diffs
                    ],
                }
                for s in getattr(diff_result, "story_diffs", [])
                if s.has_changes
            ],
        },
        metadata={"timestamp": datetime.now().isoformat()},
    )

    formatter = OutputFormatter(format=format)
    return formatter.format_output(data)


def format_stats_output(
    stats: dict[str, Any],
    format: OutputFormat = OutputFormat.JSON,
) -> str:
    """
    Format stats for output.

    Args:
        stats: Stats dictionary.
        format: Output format.

    Returns:
        Formatted output string.
    """
    data = OutputData(
        title="Project Statistics",
        success=True,
        data=stats,
        metadata={"timestamp": datetime.now().isoformat()},
    )

    formatter = OutputFormatter(format=format)
    return formatter.format_output(data)
