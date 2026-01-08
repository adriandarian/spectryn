# Linear Integration Guide

spectryn supports Linear for syncing markdown specifications to issues. This guide covers configuration, authentication, and advanced features.

## Overview

The Linear adapter supports:
- ✅ Issues with labels, projects, and cycles
- ✅ Team workspaces
- ✅ Projects and roadmaps
- ✅ Cycles (sprints)
- ✅ Custom states and workflows
- ✅ Estimates (story points)
- ✅ Parent/sub-issue relationships
- ✅ GraphQL API with real-time sync

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Linear
spectryn sync --markdown EPIC.md --tracker linear --team TEAM --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Linear connection settings
linear:
  api_key: lin_api_xxxxxxxxxxxxxxxxxxxx
  team_id: TEAM  # Team key or UUID

  # Optional settings
  project_id: project-uuid  # Link issues to a project
  cycle_id: cycle-uuid  # Assign to a cycle (sprint)

  # Label configuration (optional)
  labels:
    epic: "Epic"
    story: "Story"
    bug: "Bug"
    subtask: "Sub-issue"

  # State mapping (optional)
  state_mapping:
    planned: "Backlog"
    in_progress: "In Progress"
    in_review: "In Review"
    done: "Done"
    cancelled: "Canceled"

  # Priority mapping (optional)
  priority_mapping:
    critical: 1  # Urgent
    high: 2      # High
    medium: 3    # Medium
    low: 4       # Low
    none: 0      # No priority

# Sync settings
sync:
  execute: false
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[linear]
api_key = "lin_api_xxxxxxxxxxxxxxxxxxxx"
team_id = "TEAM"
project_id = "project-uuid"

[linear.labels]
epic = "Epic"
story = "Story"
bug = "Bug"

[linear.state_mapping]
planned = "Backlog"
in_progress = "In Progress"
done = "Done"

[linear.priority_mapping]
critical = 1
high = 2
medium = 3
low = 4

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export LINEAR_API_KEY=lin_api_xxxxxxxxxxxxxxxxxxxx
export LINEAR_TEAM_ID=TEAM

# Optional
export LINEAR_PROJECT_ID=project-uuid
export LINEAR_CYCLE_ID=cycle-uuid
```

### CLI Arguments

```bash
spectryn sync \
  --tracker linear \
  --markdown EPIC.md \
  --team TEAM \
  --execute
```

## Authentication

### Personal API Key

1. Go to **Settings** → **API** → **Personal API keys**
2. Click **Create key**
3. Copy the key (starts with `lin_api_`)

::: warning
API keys have full access to your workspace. For production, consider OAuth apps.
:::

### OAuth Application

For team use, create an OAuth app:

1. Go to **Settings** → **API** → **OAuth applications**
2. Create new application
3. Configure redirect URI
4. Use OAuth flow in spectryn:

```yaml
linear:
  client_id: your-client-id
  client_secret: your-client-secret
  access_token: user-access-token
```

## Features

### Issue Creation

Stories become Linear Issues:

```markdown
### 🚀 STORY-001: User Authentication

| Field | Value |
|-------|-------|
| **Estimate** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Backlog |
| **Labels** | feature, auth |
| **Project** | Q1 Roadmap |
| **Cycle** | Sprint 1 |

#### Description

**As a** user
**I want** to log in securely
**So that** my data is protected
```

Creates:
- Issue in team TEAM
- Estimate: 5 points
- Priority: Urgent (1)
- State: Backlog
- Labels: feature, auth
- Project: Q1 Roadmap
- Cycle: Sprint 1

### Sub-Issues

Subtasks become sub-issues:

```markdown
#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login form | Create login UI | 2 | 📋 Backlog |
| 2 | Auth backend | Implement JWT | 3 | 🔄 In Progress |
```

Each subtask creates a sub-issue linked to the parent.

### Estimates (Story Points)

Linear uses estimates for planning:

```yaml
linear:
  estimate_scale: linear  # or "exponential", "t-shirt"

  # Custom estimate mapping
  estimate_mapping:
    1: 1
    2: 2
    3: 3
    5: 5
    8: 8
    13: 13
```

### Projects and Roadmaps

Link issues to projects:

```yaml
linear:
  project_id: project-uuid

  # Or map from markdown
  project_mapping:
    "Q1 Features": "project-uuid-1"
    "Tech Debt": "project-uuid-2"
```

### Cycles (Sprints)

Assign to cycles:

```yaml
linear:
  auto_assign_cycle: current  # or "next", "none"

  # Or specific cycle
  cycle_id: cycle-uuid
```

### Custom Workflows

Map to your team's workflow:

```yaml
linear:
  state_mapping:
    "📋 Planned": "Backlog"
    "📥 Ready": "Todo"
    "🔄 In Progress": "In Progress"
    "🔍 Review": "In Review"
    "🧪 Testing": "QA"
    "✅ Done": "Done"
    "🚫 Cancelled": "Canceled"
```

## Advanced Configuration

### Label Synchronization

```yaml
linear:
  sync_labels: true
  auto_create_labels: true
  label_colors:
    feature: "#0066FF"
    bug: "#FF3333"
    tech-debt: "#FF9900"
```

### Templates

Use issue templates:

```yaml
linear:
  template_id: template-uuid
```

### Attachments

```yaml
linear:
  sync_attachments: true
  attachment_upload: true  # Upload local files
```

### Multiple Teams

Sync to multiple teams:

```yaml
linear:
  teams:
    - id: TEAM-A
      patterns:
        - "frontend/*"
    - id: TEAM-B
      patterns:
        - "backend/*"
```

## Example Workflow

### 1. Create Epic Markdown

```markdown
# 🚀 Search Feature Epic

> **Epic: Implement full-text search**

---

## User Stories

---

### 🔍 US-001: Basic Search

| Field | Value |
|-------|-------|
| **Estimate** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Backlog |
| **Labels** | feature, search |
| **Project** | Q1 Roadmap |

#### Description

**As a** user
**I want** to search content
**So that** I can find information quickly

#### Acceptance Criteria

- [ ] Search box in header
- [ ] Real-time suggestions
- [ ] Results highlighting

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Search UI | Build search component | 2 | 📋 Backlog |
| 2 | API endpoint | Create search API | 2 | 📋 Backlog |
| 3 | Indexing | Set up Elasticsearch | 1 | 📋 Backlog |

---

### 🔍 US-002: Advanced Filters

| Field | Value |
|-------|-------|
| **Estimate** | 3 |
| **Priority** | 🟡 Medium |
| **Status** | 📋 Backlog |
| **Labels** | feature, search |
| **Project** | Q1 Roadmap |

#### Description

**As a** user
**I want** to filter search results
**So that** I can narrow down my search
```

### 2. Preview Sync

```bash
spectryn sync --tracker linear --markdown epic.md --team ENG
```

### 3. Execute Sync

```bash
spectryn sync --tracker linear --markdown epic.md --team ENG --execute
```

### 4. View Results

Check your Linear workspace for the synced issues.

## CI/CD Integration

### GitHub Actions

```yaml
name: Sync to Linear

on:
  push:
    branches: [main]
    paths:
      - 'docs/**/*.md'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install spectryn
        run: pip install spectryn

      - name: Sync to Linear
        run: |
          spectryn sync \
            --tracker linear \
            --markdown docs/EPIC.md \
            --team ${{ vars.LINEAR_TEAM }} \
            --execute \
            --no-confirm
        env:
          LINEAR_API_KEY: ${{ secrets.LINEAR_API_KEY }}
```

## Troubleshooting

### Authentication Errors

```
Error: Authentication failed
```

- Verify API key is valid
- Check key has not been revoked
- Ensure correct workspace access

### Team Not Found

```
Error: Team not found
```

- Use team key (e.g., "ENG") not full name
- Verify you have access to the team
- Check for typos in team ID

### State Mapping Errors

```
Error: State not found
```

- Check exact state names in your workflow
- States are case-sensitive
- Use Linear's default states or your custom ones

## Best Practices

1. **Use Team Keys** - Shorter and less error-prone
2. **Map All States** - Ensure all markdown statuses map to Linear states
3. **Use Estimates** - Enable velocity tracking
4. **Link to Projects** - Better roadmap visibility
5. **Assign to Cycles** - Sprint planning alignment

## See Also

- [Configuration Reference](/guide/configuration)
- [Quick Start](/guide/quick-start)
- [CI/CD Integration](/examples/cicd)
