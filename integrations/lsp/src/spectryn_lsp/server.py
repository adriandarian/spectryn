"""Spectra Language Server implementation using pygls."""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from lsprotocol import types as lsp
from pygls.server import LanguageServer

__all__ = ["SpectraLanguageServer", "main"]

logger = logging.getLogger(__name__)


@dataclass
class SpectraConfig:
    """Server configuration."""

    tracker_type: str = "jira"
    tracker_url: str = ""
    project_key: str = ""
    validate_on_save: bool = True
    validate_on_type: bool = True
    show_warnings: bool = True
    show_hints: bool = True
    hover_cache_timeout: int = 60


@dataclass
class CachedIssue:
    """Cached tracker issue details."""

    data: dict[str, Any]
    timestamp: float


class SpectraLanguageServer(LanguageServer):
    """Language Server for Spectra markdown files."""

    # Pattern to match issue IDs like PROJ-123, #123, etc.
    ISSUE_PATTERN = re.compile(
        r"(?P<prefix>(?:[A-Z][A-Z0-9]+-)|#|GH-|GL-|LIN-|AZ-)"
        r"(?P<number>\d+)"
    )

    # Pattern to match Spectra headers
    HEADER_PATTERN = re.compile(
        r"^##?\s+(?P<type>Epic|Story|Subtask):\s*(?P<title>.+?)(?:\s*\[(?P<id>[^\]]+)\])?\s*$",
        re.MULTILINE,
    )

    # Pattern to match metadata fields
    METADATA_PATTERN = re.compile(
        r"^\*\*(?P<field>Status|Priority|Points|Assignee|Labels|Sprint)\*\*:\s*(?P<value>.+)$",
        re.MULTILINE,
    )

    def __init__(self) -> None:
        super().__init__(name="spectra-lsp", version="0.1.0")
        self.config = SpectraConfig()
        self.issue_cache: dict[str, CachedIssue] = {}

        # Register all handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all LSP handlers."""

        @self.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
        def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
            """Handle document open."""
            self._validate_document(params.text_document.uri)

        @self.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
            """Handle document change."""
            if self.config.validate_on_type:
                self._validate_document(params.text_document.uri)

        @self.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
        def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
            """Handle document save."""
            if self.config.validate_on_save:
                self._validate_document(params.text_document.uri)

        @self.feature(lsp.TEXT_DOCUMENT_HOVER)
        def hover(params: lsp.HoverParams) -> lsp.Hover | None:
            """Provide hover information."""
            return self._get_hover(params)

        @self.feature(lsp.TEXT_DOCUMENT_COMPLETION)
        def completion(params: lsp.CompletionParams) -> lsp.CompletionList:
            """Provide completions."""
            return self._get_completions(params)

        @self.feature(lsp.TEXT_DOCUMENT_DEFINITION)
        def definition(params: lsp.DefinitionParams) -> list[lsp.Location]:
            """Provide go-to-definition."""
            return self._get_definition(params)

        @self.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
        def document_symbol(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
            """Provide document symbols (outline)."""
            return self._get_document_symbols(params)

        @self.feature(lsp.TEXT_DOCUMENT_CODE_ACTION)
        def code_action(params: lsp.CodeActionParams) -> list[lsp.CodeAction]:
            """Provide code actions."""
            return self._get_code_actions(params)

        @self.feature(lsp.TEXT_DOCUMENT_DOCUMENT_LINK)
        def document_link(params: lsp.DocumentLinkParams) -> list[lsp.DocumentLink]:
            """Provide document links."""
            return self._get_document_links(params)

        @self.feature(lsp.TEXT_DOCUMENT_FORMATTING)
        def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit]:
            """Provide document formatting."""
            return self._format_document(params)

        @self.feature(lsp.WORKSPACE_DID_CHANGE_CONFIGURATION)
        def did_change_configuration(params: lsp.DidChangeConfigurationParams) -> None:
            """Handle configuration changes."""
            self._update_config(params.settings)

    def _validate_document(self, uri: str) -> None:
        """Run validation and publish diagnostics."""
        document = self.workspace.get_text_document(uri)
        diagnostics: list[lsp.Diagnostic] = []

        try:
            # Run spectra CLI validation
            result = subprocess.run(
                ["spectra", "--validate", "--markdown", "-", "--format", "json"],
                input=document.source,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Parse validation errors from stderr or stdout
                errors = self._parse_validation_output(result.stdout, result.stderr)
                for error in errors:
                    diagnostics.append(
                        lsp.Diagnostic(
                            range=lsp.Range(
                                start=lsp.Position(line=error.get("line", 0), character=0),
                                end=lsp.Position(line=error.get("line", 0), character=100),
                            ),
                            message=error.get("message", "Validation error"),
                            severity=self._get_severity(error.get("severity", "error")),
                            source="spectra",
                            code=error.get("code"),
                        )
                    )
        except subprocess.TimeoutExpired:
            diagnostics.append(
                lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=0, character=0),
                    ),
                    message="Validation timed out",
                    severity=lsp.DiagnosticSeverity.Warning,
                    source="spectra",
                )
            )
        except FileNotFoundError:
            # spectra CLI not installed, do basic validation
            diagnostics.extend(self._basic_validation(document.source))

        self.publish_diagnostics(uri, diagnostics)

    def _parse_validation_output(self, stdout: str, stderr: str) -> list[dict[str, Any]]:
        """Parse validation output from spectra CLI."""
        import json

        errors: list[dict[str, Any]] = []
        try:
            if stdout.strip():
                data = json.loads(stdout)
                if isinstance(data, list):
                    errors.extend(data)
                elif isinstance(data, dict) and "errors" in data:
                    errors.extend(data["errors"])
        except json.JSONDecodeError:
            # Parse line-based error output
            for line in (stdout + stderr).splitlines():
                if "error" in line.lower() or "warning" in line.lower():
                    # Try to extract line number
                    match = re.search(r"line\s*(\d+)", line, re.IGNORECASE)
                    line_num = int(match.group(1)) - 1 if match else 0
                    errors.append({"line": line_num, "message": line.strip()})
        return errors

    def _basic_validation(self, source: str) -> list[lsp.Diagnostic]:
        """Perform basic validation without CLI."""
        diagnostics: list[lsp.Diagnostic] = []
        lines = source.splitlines()

        for i, line in enumerate(lines):
            # Check for malformed headers
            if line.startswith("##") and ":" in line:
                header_match = self.HEADER_PATTERN.match(line)
                if not header_match:
                    # Check for common issues
                    if re.match(r"^##?\s*(Epic|Story|Subtask)\s*[^:]", line):
                        diagnostics.append(
                            lsp.Diagnostic(
                                range=lsp.Range(
                                    start=lsp.Position(line=i, character=0),
                                    end=lsp.Position(line=i, character=len(line)),
                                ),
                                message="Missing colon after type. Use '## Epic: Title' format.",
                                severity=lsp.DiagnosticSeverity.Error,
                                source="spectra",
                                code="E001",
                            )
                        )

            # Check for missing status
            if re.match(r"^##\s+Story:", line):
                # Look for Status in next few lines
                has_status = False
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].startswith("**Status**:"):
                        has_status = True
                        break
                    if lines[j].startswith("##"):
                        break
                if not has_status and self.config.show_warnings:
                    diagnostics.append(
                        lsp.Diagnostic(
                            range=lsp.Range(
                                start=lsp.Position(line=i, character=0),
                                end=lsp.Position(line=i, character=len(line)),
                            ),
                            message="Story is missing **Status** field",
                            severity=lsp.DiagnosticSeverity.Warning,
                            source="spectra",
                            code="W001",
                        )
                    )

        return diagnostics

    def _get_severity(self, severity: str) -> lsp.DiagnosticSeverity:
        """Convert severity string to LSP severity."""
        severity_map = {
            "error": lsp.DiagnosticSeverity.Error,
            "warning": lsp.DiagnosticSeverity.Warning,
            "info": lsp.DiagnosticSeverity.Information,
            "hint": lsp.DiagnosticSeverity.Hint,
        }
        return severity_map.get(severity.lower(), lsp.DiagnosticSeverity.Error)

    def _get_hover(self, params: lsp.HoverParams) -> lsp.Hover | None:
        """Get hover information for a position."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()

        if params.position.line >= len(lines):
            return None

        line = lines[params.position.line]
        char = params.position.character

        # Check if hovering over an issue ID
        for match in self.ISSUE_PATTERN.finditer(line):
            if match.start() <= char <= match.end():
                issue_id = match.group(0)
                details = self._get_issue_details(issue_id)
                if details:
                    return lsp.Hover(
                        contents=lsp.MarkupContent(
                            kind=lsp.MarkupKind.Markdown,
                            value=details,
                        ),
                        range=lsp.Range(
                            start=lsp.Position(line=params.position.line, character=match.start()),
                            end=lsp.Position(line=params.position.line, character=match.end()),
                        ),
                    )

        # Check if hovering over a header
        header_match = self.HEADER_PATTERN.match(line)
        if header_match:
            item_type = header_match.group("type")
            title = header_match.group("title")
            item_id = header_match.group("id")

            content = f"### {item_type}: {title}\n\n"
            if item_id:
                content += f"**ID**: `{item_id}`\n\n"

            # Find metadata
            for i in range(params.position.line + 1, min(params.position.line + 15, len(lines))):
                if lines[i].startswith("##"):
                    break
                meta_match = self.METADATA_PATTERN.match(lines[i])
                if meta_match:
                    content += f"**{meta_match.group('field')}**: {meta_match.group('value')}\n"

            return lsp.Hover(
                contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=content,
                ),
            )

        return None

    def _get_issue_details(self, issue_id: str) -> str | None:
        """Fetch issue details from tracker via CLI."""
        import time

        # Check cache
        if issue_id in self.issue_cache:
            cached = self.issue_cache[issue_id]
            if time.time() - cached.timestamp < self.config.hover_cache_timeout:
                return self._format_issue_details(cached.data)

        try:
            result = subprocess.run(
                ["spectra", "issue", "get", issue_id, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                import json

                data = json.loads(result.stdout)
                self.issue_cache[issue_id] = CachedIssue(data=data, timestamp=time.time())
                return self._format_issue_details(data)
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return None

    def _format_issue_details(self, data: dict[str, Any]) -> str:
        """Format issue data as markdown."""
        lines = [f"### {data.get('title', 'Unknown')}\n"]

        if data.get("status"):
            lines.append(f"**Status**: {data['status']}")
        if data.get("priority"):
            lines.append(f"**Priority**: {data['priority']}")
        if data.get("assignee"):
            lines.append(f"**Assignee**: {data['assignee']}")
        if data.get("points"):
            lines.append(f"**Points**: {data['points']}")
        if data.get("description"):
            desc = data["description"][:200]
            if len(data["description"]) > 200:
                desc += "..."
            lines.append(f"\n{desc}")

        return "\n".join(lines)

    def _get_completions(self, params: lsp.CompletionParams) -> lsp.CompletionList:
        """Provide completions."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        items: list[lsp.CompletionItem] = []

        if params.position.line >= len(lines):
            return lsp.CompletionList(is_incomplete=False, items=items)

        line = lines[params.position.line]
        char = params.position.character
        prefix = line[:char]

        # Status completions
        if prefix.endswith("**Status**:") or prefix.endswith("**Status**: "):
            for status in ["Todo", "In Progress", "In Review", "Done", "Blocked", "Cancelled"]:
                items.append(
                    lsp.CompletionItem(
                        label=status,
                        kind=lsp.CompletionItemKind.EnumMember,
                        detail="Story status",
                        insert_text=f" {status}" if prefix.endswith(":") else status,
                    )
                )

        # Priority completions
        elif prefix.endswith("**Priority**:") or prefix.endswith("**Priority**: "):
            for priority in ["Critical", "High", "Medium", "Low"]:
                items.append(
                    lsp.CompletionItem(
                        label=priority,
                        kind=lsp.CompletionItemKind.EnumMember,
                        detail="Story priority",
                        insert_text=f" {priority}" if prefix.endswith(":") else priority,
                    )
                )

        # Points completions
        elif prefix.endswith("**Points**:") or prefix.endswith("**Points**: "):
            for points in ["1", "2", "3", "5", "8", "13", "21"]:
                items.append(
                    lsp.CompletionItem(
                        label=points,
                        kind=lsp.CompletionItemKind.Value,
                        detail="Story points (Fibonacci)",
                        insert_text=f" {points}" if prefix.endswith(":") else points,
                    )
                )

        # Header type completions
        elif re.match(r"^##?\s*$", prefix):
            for item_type in ["Epic:", "Story:", "Subtask:"]:
                items.append(
                    lsp.CompletionItem(
                        label=item_type,
                        kind=lsp.CompletionItemKind.Struct,
                        detail=f"Spectra {item_type[:-1]}",
                        insert_text=f" {item_type} ",
                    )
                )

        # Metadata field completions at line start
        elif prefix.strip() == "" or prefix.strip() == "*":
            for field_name in ["Status", "Priority", "Points", "Assignee", "Labels", "Sprint"]:
                items.append(
                    lsp.CompletionItem(
                        label=f"**{field_name}**:",
                        kind=lsp.CompletionItemKind.Field,
                        detail=f"Spectra {field_name.lower()} field",
                        insert_text=f"**{field_name}**: ",
                    )
                )

        return lsp.CompletionList(is_incomplete=False, items=items)

    def _get_definition(self, params: lsp.DefinitionParams) -> list[lsp.Location]:
        """Get definition location for symbols."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        locations: list[lsp.Location] = []

        if params.position.line >= len(lines):
            return locations

        line = lines[params.position.line]
        char = params.position.character

        # Check if on an issue ID reference
        for match in self.ISSUE_PATTERN.finditer(line):
            if match.start() <= char <= match.end():
                issue_id = match.group(0)

                # Find the definition (header with this ID)
                for i, search_line in enumerate(lines):
                    if f"[{issue_id}]" in search_line:
                        header_match = self.HEADER_PATTERN.match(search_line)
                        if header_match:
                            locations.append(
                                lsp.Location(
                                    uri=params.text_document.uri,
                                    range=lsp.Range(
                                        start=lsp.Position(line=i, character=0),
                                        end=lsp.Position(line=i, character=len(search_line)),
                                    ),
                                )
                            )
                            break

        return locations

    def _get_document_symbols(self, params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
        """Get document symbols for outline view."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        symbols: list[lsp.DocumentSymbol] = []
        current_epic: lsp.DocumentSymbol | None = None
        current_story: lsp.DocumentSymbol | None = None

        for i, line in enumerate(lines):
            match = self.HEADER_PATTERN.match(line)
            if not match:
                continue

            item_type = match.group("type")
            title = match.group("title")
            item_id = match.group("id") or ""

            # Find the end of this section
            end_line = len(lines) - 1
            for j in range(i + 1, len(lines)):
                if self.HEADER_PATTERN.match(lines[j]):
                    # Check if same or higher level
                    next_match = self.HEADER_PATTERN.match(lines[j])
                    if next_match:
                        next_type = next_match.group("type")
                        if item_type == "Epic" or (item_type == "Story" and next_type != "Subtask"):
                            end_line = j - 1
                            break

            symbol = lsp.DocumentSymbol(
                name=f"{title}" + (f" [{item_id}]" if item_id else ""),
                kind=self._get_symbol_kind(item_type),
                range=lsp.Range(
                    start=lsp.Position(line=i, character=0),
                    end=lsp.Position(line=end_line, character=len(lines[end_line]) if end_line < len(lines) else 0),
                ),
                selection_range=lsp.Range(
                    start=lsp.Position(line=i, character=0),
                    end=lsp.Position(line=i, character=len(line)),
                ),
                detail=item_type,
                children=[],
            )

            if item_type == "Epic":
                symbols.append(symbol)
                current_epic = symbol
                current_story = None
            elif item_type == "Story":
                if current_epic and current_epic.children is not None:
                    current_epic.children.append(symbol)
                else:
                    symbols.append(symbol)
                current_story = symbol
            elif item_type == "Subtask":
                if current_story and current_story.children is not None:
                    current_story.children.append(symbol)
                elif current_epic and current_epic.children is not None:
                    current_epic.children.append(symbol)
                else:
                    symbols.append(symbol)

        return symbols

    def _get_symbol_kind(self, item_type: str) -> lsp.SymbolKind:
        """Map Spectra type to LSP symbol kind."""
        kind_map = {
            "Epic": lsp.SymbolKind.Module,
            "Story": lsp.SymbolKind.Class,
            "Subtask": lsp.SymbolKind.Method,
        }
        return kind_map.get(item_type, lsp.SymbolKind.Variable)

    def _get_code_actions(self, params: lsp.CodeActionParams) -> list[lsp.CodeAction]:
        """Get code actions for the selected range."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        actions: list[lsp.CodeAction] = []

        start_line = params.range.start.line
        if start_line >= len(lines):
            return actions

        line = lines[start_line]

        # Quick fix for diagnostics
        for diagnostic in params.context.diagnostics:
            if diagnostic.code == "E001":
                # Missing colon fix
                actions.append(
                    lsp.CodeAction(
                        title="Add missing colon",
                        kind=lsp.CodeActionKind.QuickFix,
                        diagnostics=[diagnostic],
                        edit=lsp.WorkspaceEdit(
                            changes={
                                params.text_document.uri: [
                                    lsp.TextEdit(
                                        range=diagnostic.range,
                                        new_text=re.sub(
                                            r"^(##?\s*)(Epic|Story|Subtask)\s+",
                                            r"\1\2: ",
                                            line,
                                        ),
                                    )
                                ]
                            }
                        ),
                    )
                )
            elif diagnostic.code == "W001":
                # Add missing status
                actions.append(
                    lsp.CodeAction(
                        title="Add Status field",
                        kind=lsp.CodeActionKind.QuickFix,
                        diagnostics=[diagnostic],
                        edit=lsp.WorkspaceEdit(
                            changes={
                                params.text_document.uri: [
                                    lsp.TextEdit(
                                        range=lsp.Range(
                                            start=lsp.Position(line=start_line + 1, character=0),
                                            end=lsp.Position(line=start_line + 1, character=0),
                                        ),
                                        new_text="**Status**: Todo\n",
                                    )
                                ]
                            }
                        ),
                    )
                )

        # Source actions on headers
        header_match = self.HEADER_PATTERN.match(line)
        if header_match:
            item_type = header_match.group("type")
            item_id = header_match.group("id")

            # Create in tracker
            if not item_id:
                actions.append(
                    lsp.CodeAction(
                        title=f"Create {item_type} in tracker",
                        kind=lsp.CodeActionKind.Source,
                        command=lsp.Command(
                            title=f"Create {item_type}",
                            command="spectra.createInTracker",
                            arguments=[params.text_document.uri, start_line],
                        ),
                    )
                )

            # Sync with tracker
            if item_id:
                actions.append(
                    lsp.CodeAction(
                        title=f"Sync {item_type} with tracker",
                        kind=lsp.CodeActionKind.Source,
                        command=lsp.Command(
                            title=f"Sync {item_type}",
                            command="spectra.syncWithTracker",
                            arguments=[item_id],
                        ),
                    )
                )

        # Refactor actions
        if line.strip().startswith("##") and "Story:" in line:
            actions.append(
                lsp.CodeAction(
                    title="Generate acceptance criteria",
                    kind=lsp.CodeActionKind.RefactorRewrite,
                    command=lsp.Command(
                        title="Generate AC",
                        command="spectra.generateAC",
                        arguments=[params.text_document.uri, start_line],
                    ),
                )
            )

            actions.append(
                lsp.CodeAction(
                    title="Estimate story points",
                    kind=lsp.CodeActionKind.RefactorRewrite,
                    command=lsp.Command(
                        title="Estimate Points",
                        command="spectra.estimatePoints",
                        arguments=[params.text_document.uri, start_line],
                    ),
                )
            )

        return actions

    def _get_document_links(self, params: lsp.DocumentLinkParams) -> list[lsp.DocumentLink]:
        """Get clickable links in the document."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        links: list[lsp.DocumentLink] = []

        for i, line in enumerate(lines):
            # Find issue IDs and create links to tracker
            for match in self.ISSUE_PATTERN.finditer(line):
                issue_id = match.group(0)
                tracker_url = self._build_tracker_url(issue_id)
                if tracker_url:
                    links.append(
                        lsp.DocumentLink(
                            range=lsp.Range(
                                start=lsp.Position(line=i, character=match.start()),
                                end=lsp.Position(line=i, character=match.end()),
                            ),
                            target=tracker_url,
                            tooltip=f"Open {issue_id} in tracker",
                        )
                    )

        return links

    def _build_tracker_url(self, issue_id: str) -> str | None:
        """Build tracker URL for an issue ID."""
        if not self.config.tracker_url:
            return None

        base_url = self.config.tracker_url.rstrip("/")
        tracker_type = self.config.tracker_type.lower()

        # Extract numeric ID
        match = self.ISSUE_PATTERN.match(issue_id)
        if not match:
            return None

        number = match.group("number")

        url_patterns = {
            "jira": f"{base_url}/browse/{issue_id}",
            "github": f"{base_url}/issues/{number}",
            "gitlab": f"{base_url}/-/issues/{number}",
            "linear": f"{base_url}/issue/{issue_id}",
            "azure": f"{base_url}/_workitems/edit/{number}",
            "trello": f"{base_url}/c/{issue_id}",
            "asana": f"{base_url}/0/{number}/f",
            "clickup": f"{base_url}/t/{issue_id}",
            "monday": f"{base_url}/boards/{self.config.project_key}/pulses/{number}",
            "shortcut": f"{base_url}/story/{number}",
            "youtrack": f"{base_url}/issue/{issue_id}",
            "plane": f"{base_url}/issues/{issue_id}",
            "pivotal": f"{base_url}/stories/{number}",
            "basecamp": f"{base_url}/todos/{number}",
            "notion": f"{base_url}/{issue_id}",
        }

        return url_patterns.get(tracker_type)

    def _format_document(self, params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit]:
        """Format the document."""
        document = self.workspace.get_text_document(params.text_document.uri)
        lines = document.source.splitlines()
        edits: list[lsp.TextEdit] = []

        for i, line in enumerate(lines):
            new_line = line

            # Normalize header spacing
            header_match = re.match(r"^(##?)\s*(\w+):\s*(.+)$", line)
            if header_match:
                hashes, item_type, rest = header_match.groups()
                new_line = f"{hashes} {item_type}: {rest.strip()}"

            # Normalize metadata spacing
            meta_match = re.match(r"^\*\*(\w+)\*\*:\s*(.+)$", line)
            if meta_match:
                field, value = meta_match.groups()
                new_line = f"**{field}**: {value.strip()}"

            if new_line != line:
                edits.append(
                    lsp.TextEdit(
                        range=lsp.Range(
                            start=lsp.Position(line=i, character=0),
                            end=lsp.Position(line=i, character=len(line)),
                        ),
                        new_text=new_line,
                    )
                )

        return edits

    def _update_config(self, settings: Any) -> None:
        """Update configuration from settings."""
        if not isinstance(settings, dict):
            return

        spectra_settings = settings.get("spectra", {})

        # Validation settings
        validation = spectra_settings.get("validation", {})
        self.config.validate_on_save = validation.get("validateOnSave", True)
        self.config.validate_on_type = validation.get("validateOnType", True)

        # Tracker settings
        tracker = spectra_settings.get("tracker", {})
        self.config.tracker_type = tracker.get("type", "jira")
        self.config.tracker_url = tracker.get("url", "")
        self.config.project_key = tracker.get("projectKey", "")

        # Diagnostics settings
        diagnostics = spectra_settings.get("diagnostics", {})
        self.config.show_warnings = diagnostics.get("showWarnings", True)
        self.config.show_hints = diagnostics.get("showHints", True)

        # Hover settings
        hover = spectra_settings.get("hover", {})
        self.config.hover_cache_timeout = hover.get("cacheTimeout", 60)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Spectra Language Server")
    parser.add_argument("--tcp", action="store_true", help="Start in TCP mode")
    parser.add_argument("--stdio", action="store_true", help="Start in stdio mode")
    parser.add_argument("--port", type=int, default=2087, help="TCP port (default: 2087)")
    parser.add_argument("--host", default="127.0.0.1", help="TCP host (default: 127.0.0.1)")
    parser.add_argument("--log-file", help="Log file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: list[logging.Handler] = []

    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    server = SpectraLanguageServer()

    if args.tcp:
        server.start_tcp(args.host, args.port)
    else:
        # Default to stdio mode
        server.start_io()


if __name__ == "__main__":
    main()
