# Feature Plan: Tracker Writeback

> **Status**: 📋 Planned
> **Priority**: High
> **Estimated Effort**: 4-6 hours

## Problem Statement

When users import/sync markdown stories to an issue tracker (Jira, GitHub, Linear, Azure DevOps), the created ticket information is lost. For subsequent operations, users must:

1. Manually look up which ticket corresponds to which story
2. Re-run matching logic that might fail or create duplicates
3. Lose the ability to directly reference the ticket from the source file

**Goal**: After a successful sync/import, automatically update the source markdown file with:
- The tracker type (jira, github, linear, azure_devops)
- The issue key/number created (e.g., `PROJ-123`)
- The URL to view the issue

---

## Current State

### Already Exists

1. **Domain entities** (`UserStory`) have fields for this:
   ```python
   external_key: IssueKey | None = None
   external_url: str | None = None
   ```

2. **MarkdownWriter** already outputs tracker info (but hardcoded to "Jira"):
   ```python
   if story.external_key:
       lines.append(f"> **Jira:** [{story.external_key}]({story.external_url or '#'})")
   ```

3. **TrackerType enum** exists:
   ```python
   class TrackerType(Enum):
       JIRA = "jira"
       GITHUB = "github"
       LINEAR = "linear"
       AZURE_DEVOPS = "azure_devops"
   ```

### Missing

1. **Parser doesn't read** existing tracker info from markdown
2. **No writeback service** to update source files after sync
3. **URL construction** isn't standardized across adapters
4. **No CLI option** to enable/disable writeback

---

## Proposed Markdown Format

### For Stories (Blockquote Style)

```markdown
### 🔧 US-001: Implement user authentication

> **Tracker:** jira
> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)

| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
```

### Alternative: Table Style (Consistent with Metadata)

```markdown
### 🔧 US-001: Implement user authentication

| Field | Value |
|-------|-------|
| **Tracker** | Jira |
| **Issue** | [PROJ-123](https://company.atlassian.net/browse/PROJ-123) |
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
```

### Recommendation

Use the **blockquote style** because:
1. It's visually distinct from story metadata
2. Matches existing `MarkdownWriter` output
3. Clearly separates "synced tracker info" from "user-authored content"
4. Less intrusive when tracker info is added/updated

---

## Implementation Plan

### Phase 1: Parser Enhancement

**File**: `src/spectra/adapters/parsers/markdown.py`

Add method to extract tracker info:

```python
def _extract_tracker_info(self, content: str) -> tuple[str | None, str | None, str | None]:
    """
    Extract tracker information from story content.

    Formats supported:
    - > **Tracker:** jira
    - > **Issue:** [PROJ-123](https://url)
    - > **Jira:** [PROJ-123](https://url)  # Legacy format
    - > **GitHub:** [#123](https://url)

    Returns:
        Tuple of (tracker_type, issue_key, issue_url) or (None, None, None)
    """
    tracker_type = None
    issue_key = None
    issue_url = None

    # Pattern for tracker type: > **Tracker:** jira
    tracker_match = re.search(
        r">\s*\*\*Tracker\*\*:\s*(\w+)",
        content, re.IGNORECASE
    )
    if tracker_match:
        tracker_type = tracker_match.group(1).lower()

    # Pattern for issue: > **Issue:** [KEY](URL) or > **Jira:** [KEY](URL)
    issue_match = re.search(
        r">\s*\*\*(?:Issue|Jira|GitHub|Linear|Azure)\*\*:\s*\[([^\]]+)\]\(([^)]+)\)",
        content, re.IGNORECASE
    )
    if issue_match:
        issue_key = issue_match.group(1)
        issue_url = issue_match.group(2)

        # Infer tracker type from label if not explicit
        if not tracker_type:
            label = issue_match.re.match.group(0)  # Get full match
            if 'jira' in label.lower():
                tracker_type = 'jira'
            elif 'github' in label.lower():
                tracker_type = 'github'
            # etc.

    return tracker_type, issue_key, issue_url
```

Update `_parse_story()` to populate `external_key` and `external_url`:

```python
def _parse_story(self, story_id: str, title: str, content: str) -> UserStory | None:
    # ... existing parsing ...

    # Extract tracker info
    tracker_type, issue_key, issue_url = self._extract_tracker_info(content)

    return UserStory(
        # ... existing fields ...
        external_key=IssueKey(issue_key) if issue_key else None,
        external_url=issue_url,
    )
```

### Phase 2: Source File Updater Service

**File**: `src/spectra/application/sync/source_updater.py`

```python
"""
Source File Updater - Update markdown files with tracker information.

Updates the source markdown file after successful sync operations
to record the tracker type, issue key, and URL for each story.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from spectra.core.domain.entities import UserStory
from spectra.core.ports.config_provider import TrackerType


@dataclass
class TrackerInfo:
    """Information about a synced issue in the tracker."""
    tracker_type: TrackerType
    issue_key: str
    issue_url: str


@dataclass
class UpdateResult:
    """Result of a source file update operation."""
    success: bool = True
    stories_updated: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class SourceFileUpdater:
    """
    Updates markdown source files with tracker information.

    After a successful sync, this service writes back:
    - Tracker type (jira, github, linear, azure_devops)
    - Issue key (PROJ-123, #456, etc.)
    - Issue URL (clickable link to view)

    This enables:
    - Direct navigation from markdown to tracker
    - Reliable re-sync without re-matching
    - Audit trail of what's synced where
    """

    def __init__(self, tracker_type: TrackerType, base_url: str):
        """
        Initialize the updater.

        Args:
            tracker_type: The type of tracker being used.
            base_url: Base URL for constructing issue links.
        """
        self.tracker_type = tracker_type
        self.base_url = base_url.rstrip('/')
        self.logger = logging.getLogger("SourceFileUpdater")

    def update_file(
        self,
        file_path: Path,
        stories: list[UserStory],
    ) -> UpdateResult:
        """
        Update a markdown file with tracker info for synced stories.

        Args:
            file_path: Path to the markdown file.
            stories: Stories that have been synced (with external_key set).

        Returns:
            UpdateResult with details of changes made.
        """
        result = UpdateResult()

        try:
            content = file_path.read_text(encoding='utf-8')
            original = content

            for story in stories:
                if story.external_key:
                    content = self._update_story_tracker_info(
                        content=content,
                        story_id=str(story.id),
                        tracker_info=TrackerInfo(
                            tracker_type=self.tracker_type,
                            issue_key=str(story.external_key),
                            issue_url=story.external_url or self._build_url(str(story.external_key)),
                        ),
                    )
                    result.stories_updated += 1

            if content != original:
                file_path.write_text(content, encoding='utf-8')
                self.logger.info(f"Updated {file_path} with tracker info for {result.stories_updated} stories")

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.logger.error(f"Failed to update {file_path}: {e}")

        return result

    def _update_story_tracker_info(
        self,
        content: str,
        story_id: str,
        tracker_info: TrackerInfo,
    ) -> str:
        """
        Update or insert tracker info for a single story.

        Args:
            content: Full markdown content.
            story_id: Story ID to update (e.g., "US-001").
            tracker_info: Tracker information to write.

        Returns:
            Updated content.
        """
        # Find the story header
        story_pattern = rf"(### [^\n]* {re.escape(story_id)}: [^\n]+\n)"
        match = re.search(story_pattern, content)

        if not match:
            self.logger.warning(f"Story {story_id} not found in content")
            return content

        header_end = match.end()

        # Check if tracker info already exists after the header
        existing_tracker = re.search(
            r">\s*\*\*(?:Tracker|Issue|Jira|GitHub|Linear|Azure)\*\*:",
            content[header_end:header_end + 500]  # Look in next 500 chars
        )

        tracker_block = self._format_tracker_block(tracker_info)

        if existing_tracker:
            # Replace existing tracker info block
            # Find the end of the blockquote section
            block_start = header_end + existing_tracker.start()
            block_end = block_start

            # Find where the blockquote block ends
            remaining = content[block_start:]
            lines = remaining.split('\n')
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('>'):
                    block_end = block_start + sum(len(l) + 1 for l in lines[:i])
                    break
            else:
                block_end = block_start + len(remaining)

            content = content[:block_start] + tracker_block + '\n' + content[block_end:].lstrip()
        else:
            # Insert new tracker info after header
            content = content[:header_end] + '\n' + tracker_block + '\n' + content[header_end:]

        return content

    def _format_tracker_block(self, info: TrackerInfo) -> str:
        """Format tracker info as markdown blockquote."""
        tracker_name = info.tracker_type.value.replace('_', ' ').title()
        return (
            f"> **Tracker:** {tracker_name}\n"
            f"> **Issue:** [{info.issue_key}]({info.issue_url})"
        )

    def _build_url(self, issue_key: str) -> str:
        """Build issue URL from key based on tracker type."""
        if self.tracker_type == TrackerType.JIRA:
            return f"{self.base_url}/browse/{issue_key}"
        elif self.tracker_type == TrackerType.GITHUB:
            # GitHub URLs: https://github.com/owner/repo/issues/123
            return f"{self.base_url}/issues/{issue_key.lstrip('#')}"
        elif self.tracker_type == TrackerType.LINEAR:
            # Linear URLs: https://linear.app/team/issue/TEAM-123
            return f"{self.base_url}/issue/{issue_key}"
        elif self.tracker_type == TrackerType.AZURE_DEVOPS:
            # Azure DevOps URLs: https://dev.azure.com/org/project/_workitems/edit/123
            return f"{self.base_url}/_workitems/edit/{issue_key}"
        else:
            return f"{self.base_url}/{issue_key}"
```

### Phase 3: Orchestrator Integration

**File**: `src/spectra/application/sync/orchestrator.py`

Add to `SyncOrchestrator.__init__`:
```python
self.source_updater: SourceFileUpdater | None = None
self.update_source_file: bool = False
```

Add to `sync()` method after successful sync:
```python
# Phase N: Update source file with tracker info
if self.update_source_file and not self.config.dry_run:
    self._update_source_with_tracker_info(markdown_path, result)
```

### Phase 4: CLI Integration

**File**: `src/spectra/cli/app.py`

Add new option:
```python
@click.option(
    '--update-source/--no-update-source',
    default=False,
    help='Update source markdown file with tracker info after sync'
)
```

### Phase 5: Configuration

Add to `SyncConfig`:
```python
@dataclass
class SyncConfig:
    # ... existing fields ...
    update_source_file: bool = False
```

---

## Testing Plan

### Unit Tests

1. **Parser tests**: Verify `_extract_tracker_info()` parses all formats
2. **Updater tests**: Test `_update_story_tracker_info()` with:
   - New tracker info insertion
   - Existing tracker info update
   - Multiple stories in file
   - Different header formats

### Integration Tests

1. Full sync with writeback enabled
2. Re-sync with existing tracker info
3. Directory-based parsing with writeback

### Edge Cases

1. Story without external_key (shouldn't update)
2. Malformed existing tracker block
3. File permission errors
4. Unicode in URLs/keys

---

## Migration & Backwards Compatibility

- **Parser**: Will read new format, continue to work with files without tracker info
- **Writeback**: Off by default, opt-in via `--update-source`
- **Existing files**: Won't be modified unless explicitly enabled

---

## Future Enhancements

1. **Subtask tracking**: Write subtask keys back too
2. **Last sync timestamp**: Add sync metadata
3. **Conflict detection**: Warn if tracker info changed externally
4. **Dry-run preview**: Show what would be written back

---

## Example: Before & After

### Before Sync
```markdown
### 🔧 US-001: Implement user authentication

| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to log in securely
**So that** my data is protected
```

### After Sync (with `--update-source`)
```markdown
### 🔧 US-001: Implement user authentication

> **Tracker:** Jira
> **Issue:** [PROJ-123](https://company.atlassian.net/browse/PROJ-123)

| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description
**As a** user
**I want** to log in securely
**So that** my data is protected
```

---

## Implementation Order

1. ✅ Create this plan document
2. ⏳ Add tracker info parsing to `MarkdownParser`
3. ⏳ Create `SourceFileUpdater` service
4. ⏳ Integrate with `SyncOrchestrator`
5. ⏳ Add CLI `--update-source` option
6. ⏳ Write tests
7. ⏳ Update documentation

---

## Open Questions

1. **Format preference**: Blockquote vs table for tracker info?
   - **Decision**: Blockquote (visually distinct, less intrusive)

2. **Tracker type label**: "Jira" vs "jira" vs "JIRA"?
   - **Decision**: Title case ("Jira", "GitHub", "Linear")

3. **Default behavior**: Should writeback be opt-in or opt-out?
   - **Decision**: Opt-in via `--update-source` (conservative)

4. **URL format for GitHub**: `#123` or `123` in display?
   - **Decision**: Use `#123` to match GitHub convention


