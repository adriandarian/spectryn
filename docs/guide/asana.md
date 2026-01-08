# Asana Integration Guide

spectryn supports Asana for syncing markdown specifications to tasks. This guide covers configuration, authentication, and advanced features.

## Overview

The Asana adapter supports:
- ✅ Tasks with subtasks, sections, and custom fields
- ✅ Projects and portfolios
- ✅ Workspaces and teams
- ✅ Goals and milestones
- ✅ Custom fields (text, number, enum, date)
- ✅ Tags and followers
- ✅ Task dependencies
- ✅ Attachments

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Asana
spectryn sync --markdown EPIC.md --tracker asana --project 1234567890 --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Asana connection settings
asana:
  access_token: your-personal-access-token
  workspace_id: "1234567890"
  project_id: "0987654321"

  # Optional settings
  team_id: "team-id"  # For team-specific operations

  # Section mapping (optional)
  sections:
    backlog: "Backlog"
    in_progress: "In Progress"
    review: "Review"
    done: "Done"

  # Custom field mapping (optional)
  custom_fields:
    story_points: "1234567890123"  # Custom field GID
    priority: "9876543210987"

  # Priority enum mapping (optional)
  priority_mapping:
    critical: "P0"
    high: "P1"
    medium: "P2"
    low: "P3"

# Sync settings
sync:
  execute: false
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[asana]
access_token = "your-personal-access-token"
workspace_id = "1234567890"
project_id = "0987654321"

[asana.sections]
backlog = "Backlog"
in_progress = "In Progress"
done = "Done"

[asana.custom_fields]
story_points = "1234567890123"
priority = "9876543210987"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export ASANA_ACCESS_TOKEN=your-personal-access-token
export ASANA_WORKSPACE_ID=1234567890
export ASANA_PROJECT_ID=0987654321

# Optional
export ASANA_TEAM_ID=team-id
```

### CLI Arguments

```bash
spectryn sync \
  --tracker asana \
  --markdown EPIC.md \
  --project 0987654321 \
  --execute
```

## Authentication

### Personal Access Token

1. Go to **My Settings** → **Apps** → **Developer Console**
2. Click **Create new token**
3. Name your token (e.g., "spectryn-sync")
4. Copy the token immediately

::: warning
Personal access tokens have full access to your account. Keep them secure!
:::

### OAuth Application

For team use, create an OAuth app:

1. Go to **Developer Console** → **Create app**
2. Configure OAuth settings
3. Implement OAuth flow:

```yaml
asana:
  client_id: your-client-id
  client_secret: your-client-secret
  redirect_uri: https://your-app.com/callback
```

### Service Account

For automation, use a Service Account:

1. Create a dedicated Asana account for integrations
2. Generate a personal access token
3. Add to relevant projects with appropriate permissions

## Features

### Task Creation

Stories become Asana tasks:

```markdown
### 🚀 STORY-001: User Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Backlog |
| **Tags** | feature, auth |
| **Assignee** | user@company.com |
| **Due Date** | 2024-03-15 |

#### Description

**As a** user
**I want** to log in securely
**So that** my data is protected
```

Creates:
- Task in project
- Section: Backlog
- Custom field: Story Points = 5
- Tags: feature, auth
- Assignee and due date set

### Subtasks

Subtasks become Asana subtasks:

```markdown
#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login form | Create login UI | 2 | 📋 Backlog |
| 2 | Auth backend | Implement JWT | 3 | 🔄 In Progress |
```

### Sections

Map statuses to project sections:

```yaml
asana:
  sections:
    "📋 Backlog": "Backlog"
    "📥 Ready": "Ready for Dev"
    "🔄 In Progress": "In Progress"
    "🔍 Review": "Code Review"
    "🧪 Testing": "QA"
    "✅ Done": "Complete"
```

### Custom Fields

#### Number Fields (Story Points)

```yaml
asana:
  custom_fields:
    story_points: "1234567890123"  # Number field GID
```

#### Enum Fields (Priority)

```yaml
asana:
  custom_fields:
    priority: "9876543210987"

  # Map markdown values to enum options
  priority_mapping:
    "🔴 Critical": "P0 - Critical"
    "🟠 High": "P1 - High"
    "🟡 Medium": "P2 - Medium"
    "🟢 Low": "P3 - Low"
```

#### Date Fields

```markdown
| Field | Value |
|-------|-------|
| **Due Date** | 2024-03-15 |
| **Start Date** | 2024-03-01 |
```

### Tags

Add tags to tasks:

```yaml
asana:
  sync_tags: true
  auto_create_tags: true
  tag_mapping:
    feature: "1234567890"  # Existing tag GID
    bug: "0987654321"
```

### Dependencies

Create task dependencies:

```markdown
| Field | Value |
|-------|-------|
| **Blocked By** | STORY-001, STORY-002 |
| **Blocks** | STORY-005 |
```

```yaml
asana:
  sync_dependencies: true
```

## Advanced Configuration

### Multiple Projects

Sync to multiple projects:

```yaml
asana:
  projects:
    - id: "1234567890"
      patterns:
        - "frontend/*"
    - id: "0987654321"
      patterns:
        - "backend/*"
```

### Goals Integration

Link tasks to goals:

```yaml
asana:
  goal_id: "goal-gid"
  sync_goals: true
```

### Portfolios

Add projects to portfolios:

```yaml
asana:
  portfolio_id: "portfolio-gid"
```

### Milestones

Create milestones from epics:

```yaml
asana:
  create_milestones: true
  milestone_section: "Milestones"
```

### Attachments

Sync attachments:

```yaml
asana:
  sync_attachments: true
  attachment_path: ./docs/images
```

## Example Workflow

### 1. Create Epic Markdown

```markdown
# 🚀 Mobile App Epic

> **Epic: Launch mobile application**

---

## User Stories

---

### 📱 US-001: App Setup

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Backlog |
| **Tags** | mobile, setup |
| **Due Date** | 2024-02-01 |

#### Description

**As a** developer
**I want** the app scaffolding set up
**So that** development can begin

#### Acceptance Criteria

- [ ] React Native project initialized
- [ ] Navigation configured
- [ ] State management set up

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Initialize project | Create RN project | 1 | 📋 Backlog |
| 2 | Add navigation | Set up React Navigation | 1 | 📋 Backlog |
| 3 | State management | Configure Redux | 1 | 📋 Backlog |

---

### 🔐 US-002: Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Backlog |
| **Tags** | mobile, auth |
| **Due Date** | 2024-02-15 |
| **Blocked By** | US-001 |

#### Description

**As a** user
**I want** to log in to the app
**So that** I can access my data
```

### 2. Preview Sync

```bash
spectryn sync --tracker asana --markdown epic.md --project 1234567890
```

### 3. Execute Sync

```bash
spectryn sync --tracker asana --markdown epic.md --project 1234567890 --execute
```

### 4. View Results

Check your Asana project for the synced tasks.

## CI/CD Integration

### GitHub Actions

```yaml
name: Sync to Asana

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

      - name: Sync to Asana
        run: |
          spectryn sync \
            --tracker asana \
            --markdown docs/EPIC.md \
            --project ${{ vars.ASANA_PROJECT_ID }} \
            --execute \
            --no-confirm
        env:
          ASANA_ACCESS_TOKEN: ${{ secrets.ASANA_ACCESS_TOKEN }}
          ASANA_WORKSPACE_ID: ${{ vars.ASANA_WORKSPACE_ID }}
```

## Troubleshooting

### Authentication Errors

```
Error: Invalid token
```

- Verify token is valid and not revoked
- Check token has not expired
- Ensure correct workspace access

### Project Not Found

```
Error: Project not found
```

- Verify project GID is correct (find in URL)
- Check you have access to the project
- Ensure project is not archived

### Custom Field Errors

```
Error: Custom field not found
```

- Verify custom field GID
- Check field is added to the project
- Ensure field type matches expected type

### Section Not Found

```
Error: Section not found
```

- Check exact section names (case-sensitive)
- Verify sections exist in the project
- Create missing sections first

## Best Practices

1. **Use Project Templates** - Set up sections and custom fields consistently
2. **Leverage Custom Fields** - Track story points, priority, etc.
3. **Use Tags for Labels** - Cross-project categorization
4. **Set Up Dependencies** - Visualize blockers
5. **Enable Goals** - Link work to outcomes

## Finding GIDs

To find GIDs (Global IDs) for Asana resources:

1. **Project GID**: In the URL `app.asana.com/0/PROJECT_GID/...`
2. **Custom Field GID**: Project Settings → Custom Fields → Click field → GID in URL
3. **Section GID**: API Explorer or browser dev tools

Or use the spectryn helper:

```bash
spectryn asana list-projects --workspace 1234567890
spectryn asana list-custom-fields --project 0987654321
spectryn asana list-sections --project 0987654321
```

## See Also

- [Configuration Reference](/guide/configuration)
- [Quick Start](/guide/quick-start)
- [CI/CD Integration](/examples/cicd)
