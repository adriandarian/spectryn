# Basic Usage Examples

Common usage patterns for spectryn.

## Your First Sync

### 1. Set Up Credentials

Create a `.env` file:

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

### 2. Create Your Markdown

Create `EPIC.md`:

```markdown
# 🚀 My First Epic

> **Epic: Getting started with spectryn**

---

## User Stories

---

### 🔧 STORY-001: Setup Development Environment

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description

**As a** developer
**I want** the development environment configured
**So that** I can start building features

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Install dependencies | Run npm install | 1 | 📋 Planned |
| 2 | Configure linting | Set up ESLint | 1 | 📋 Planned |
| 3 | Set up testing | Configure Jest | 1 | 📋 Planned |

---
```

## Flexible Story ID Prefixes

Spectra supports various story ID prefixes to match your team's conventions:

### Standard Prefixes

```markdown
### US-001: User Story with US prefix
### STORY-001: Using STORY prefix
### FEAT-001: Feature with FEAT prefix
### TASK-001: Task with TASK prefix
```

### Project-Based Prefixes

Match your Jira project key:

```markdown
### PROJ-001: Project-prefixed story
### ENG-123: Engineering project story
### MOBILE-456: Mobile team story
### API-789: API team story
```

### Custom Prefixes

Any uppercase letters followed by a dash and numbers work:

```markdown
### BUG-001: Bug tracking
### SPIKE-001: Technical spike
### CHORE-001: Maintenance task
### DOC-001: Documentation task
### TEST-001: Test automation task
```

### Mixed Prefixes in One File

You can use multiple prefix styles in a single file:

```markdown
# Q4 Planning

## User Stories

### US-001: Core Feature Implementation
**As a** user...

### BUG-042: Fix Login Timeout Issue
**As a** user...

### SPIKE-003: Evaluate New Framework
**As a** developer...

### PROJ-789: Integration with External API
**As a** developer...
```

### 3. Preview Changes

```bash
spectryn --markdown EPIC.md --epic PROJ-123
```

### 4. Execute Sync

```bash
spectryn --markdown EPIC.md --epic PROJ-123 --execute
```

## Common Scenarios

### Sync Only Descriptions

When you only want to update story descriptions:

```bash
spectryn -m EPIC.md -e PROJ-123 -x --phase descriptions
```

### Sync Only Subtasks

When you only want to create/update subtasks:

```bash
spectryn -m EPIC.md -e PROJ-123 -x --phase subtasks
```

### Sync Specific Story

Focus on a single story:

```bash
spectryn -m EPIC.md -e PROJ-123 -x --story STORY-001
```

### Verbose Output

See detailed information about each operation:

```bash
spectryn -m EPIC.md -e PROJ-123 -v
```

### Export Results

Save sync results to JSON:

```bash
spectryn -m EPIC.md -e PROJ-123 -x --export results.json
```

Output:

```json
{
  "epic_key": "PROJ-123",
  "timestamp": "2025-01-13T10:30:00Z",
  "dry_run": false,
  "results": {
    "stories_processed": 5,
    "descriptions_updated": 5,
    "subtasks_created": 12,
    "subtasks_updated": 3,
    "statuses_synced": 5,
    "errors": []
  }
}
```

## Validation

### Validate Before Sync

Check your markdown format without syncing:

```bash
spectryn -m EPIC.md -e PROJ-123 --validate
```

Output for valid file:

```
✓ Markdown validation passed
  - 5 stories found
  - 12 subtasks defined
  - All required fields present
```

Output for invalid file:

```
✗ Markdown validation failed

Errors:
  Line 15: Story "STORY-002" missing metadata table
  Line 42: Invalid status emoji "⏳" - use ✅, 🔄, or 📋
  Line 67: Subtasks table missing "SP" column
```

## Backup & Recovery

### List Backups

```bash
spectryn --list-backups
```

Output:

```
Available backups:
  1. backup_20250113_103000 (PROJ-123) - 2 hours ago
  2. backup_20250113_090000 (PROJ-123) - 5 hours ago
  3. backup_20250112_150000 (PROJ-456) - yesterday
```

### View Changes Since Last Backup

```bash
spectryn --diff-latest --epic PROJ-123
```

Output:

```diff
Story: PROJ-124 (STORY-001: Setup Development Environment)
  Description:
-   **As a** developer
-   **I want** the environment ready
+   **As a** developer
+   **I want** the development environment configured
+   **So that** I can start building features

  Subtasks:
+   [NEW] PROJ-125: Install dependencies
+   [NEW] PROJ-126: Configure linting
```

### Rollback Last Sync

Preview rollback:

```bash
spectryn --rollback --epic PROJ-123
```

Execute rollback:

```bash
spectryn --rollback --epic PROJ-123 --execute
```

## Interactive Mode

For step-by-step guided sync:

```bash
spectryn -m EPIC.md -e PROJ-123 --interactive
```

Interactive session:

```
╭──────────────────────────────────────────────╮
│  spectryn Interactive Mode                    │
╰──────────────────────────────────────────────╯

Found 5 stories to sync with PROJ-123

Story 1/5: STORY-001 - Setup Development Environment

Preview changes:
  📝 Update description
  ➕ Create 3 subtasks
  ⏳ Sync status (Planned → Open)

Apply changes to STORY-001? [y/n/s(kip)/q(uit)]: y

✓ Updated description
✓ Created subtask PROJ-125
✓ Created subtask PROJ-126
✓ Created subtask PROJ-127
✓ Status synced

Story 2/5: STORY-002 - User Authentication
...
```

## Configuration File Usage

### With YAML Config

```yaml
# .spectryn.yaml
jira:
  url: https://company.atlassian.net
  project: PROJ

sync:
  descriptions: true
  subtasks: true
  comments: false
  statuses: true

markdown: ./docs/EPIC.md
epic: PROJ-123
```

Run with defaults from config:

```bash
spectryn
```

Or override specific values:

```bash
spectryn --epic PROJ-456
```

### With pyproject.toml

```toml
# pyproject.toml
[tool.spectryn]
epic = "PROJ-123"

[tool.spectryn.jira]
url = "https://company.atlassian.net"
project = "PROJ"

[tool.spectryn.sync]
verbose = true
```

