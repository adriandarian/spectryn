# Pivotal Tracker Integration Guide

spectra supports Pivotal Tracker for syncing markdown specifications to stories. This guide covers configuration, authentication, and advanced features.

## Overview

The Pivotal Tracker adapter supports:
- ✅ Stories (features, bugs, chores)
- ✅ Epics
- ✅ Story points (estimates)
- ✅ Labels
- ✅ Iterations (sprints)
- ✅ Blockers
- ✅ Tasks (subtasks)
- ✅ Comments and attachments

## Quick Start

```bash
# Install spectra
pip install spectra

# Sync markdown to Pivotal Tracker
spectra sync --markdown EPIC.md --tracker pivotal --project 1234567 --execute
```

## Configuration

### Config File (YAML)

Create `.spectra.yaml`:

```yaml
# Pivotal Tracker connection settings
pivotal:
  api_token: your-api-token
  project_id: 1234567
  
  # Story type mapping (optional)
  story_types:
    story: feature
    bug: bug
    task: chore
  
  # State mapping (optional)
  state_mapping:
    planned: unscheduled
    ready: unstarted
    in_progress: started
    delivered: delivered
    accepted: accepted
    rejected: rejected
  
  # Label configuration (optional)
  labels:
    epic: "epic"
    mvp: "mvp"

# Sync settings
sync:
  execute: false
  verbose: true
```

### Config File (TOML)

Create `.spectra.toml`:

```toml
[pivotal]
api_token = "your-api-token"
project_id = 1234567

[pivotal.story_types]
story = "feature"
bug = "bug"
task = "chore"

[pivotal.state_mapping]
planned = "unscheduled"
in_progress = "started"
done = "accepted"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export PIVOTAL_API_TOKEN=your-api-token
export PIVOTAL_PROJECT_ID=1234567
```

### CLI Arguments

```bash
spectra sync \
  --tracker pivotal \
  --markdown EPIC.md \
  --project 1234567 \
  --execute
```

## Authentication

### API Token

1. Go to **Profile** → **API Token**
2. Copy your API token
3. Use in configuration or environment variable

::: tip
The API token provides full access to projects you're a member of.
:::

## Features

### Story Types

Pivotal has three story types:

| Markdown | Pivotal Type | Description |
|----------|--------------|-------------|
| Story | Feature | User-facing functionality |
| Bug | Bug | Defect or issue |
| Task/Chore | Chore | Technical work |

```markdown
### 🚀 STORY-001: User Login

| Field | Value |
|-------|-------|
| **Type** | Feature |
| **Points** | 3 |
| **Status** | 📋 Unscheduled |
```

### Story Points

Pivotal uses the Fibonacci scale by default:

```markdown
| Field | Value |
|-------|-------|
| **Points** | 3 |
```

Available values: 0, 1, 2, 3, 5, 8

### Story States

Map to Pivotal's workflow states:

```yaml
pivotal:
  state_mapping:
    "📋 Planned": "unscheduled"
    "📥 Ready": "unstarted"
    "🔄 In Progress": "started"
    "🚚 Delivered": "delivered"
    "✅ Accepted": "accepted"
    "❌ Rejected": "rejected"
```

### Epics

Create Pivotal epics from markdown:

```markdown
# 🚀 Authentication Epic

> **Epic: User authentication system**

---

## Stories

---

### 📝 STORY-001: Login Page
...
```

```yaml
pivotal:
  create_epics: true
  epic_label: "epic"
```

### Tasks (Subtasks)

Subtasks become Pivotal tasks:

```markdown
#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login form | Create login UI | - | 📋 Planned |
| 2 | Validation | Add form validation | - | 📋 Planned |
```

::: info
Pivotal tasks don't have individual estimates. They're checkboxes on the story.
:::

### Labels

Add labels to stories:

```markdown
| Field | Value |
|-------|-------|
| **Labels** | frontend, auth, mvp |
```

### Blockers

Mark stories as blocked:

```markdown
| Field | Value |
|-------|-------|
| **Blocked By** | STORY-001 |
| **Blocker Reason** | Waiting for API design |
```

### Requesters and Owners

Assign people:

```markdown
| Field | Value |
|-------|-------|
| **Requester** | user@company.com |
| **Owner** | developer@company.com |
```

## Advanced Configuration

### Iterations

Assign to iterations (sprints):

```yaml
pivotal:
  auto_assign_iteration: current  # or "next", "backlog"
  
  # Or specific iteration
  iteration_number: 5
```

### Scheduled vs Unscheduled

Control story scheduling:

```yaml
pivotal:
  default_state: unscheduled  # or "unstarted"
  auto_schedule: false
```

### Story Templates

Use description templates:

```yaml
pivotal:
  description_template: |
    ## User Story
    {description}
    
    ## Acceptance Criteria
    {acceptance_criteria}
    
    ## Technical Notes
    {notes}
```

### Workspace Integration

For organizations with multiple workspaces:

```yaml
pivotal:
  workspace_id: 12345  # Optional
```

## Example Workflow

### 1. Create Epic Markdown

```markdown
# 🚀 Payment Processing Epic

> **Epic: Complete payment system**

---

## Stories

---

### 💳 STORY-001: Credit Card Payment

| Field | Value |
|-------|-------|
| **Type** | Feature |
| **Points** | 5 |
| **Status** | 📋 Unscheduled |
| **Labels** | payments, stripe |
| **Requester** | product@company.com |

#### Description

**As a** customer
**I want** to pay with credit card
**So that** I can complete purchases

#### Acceptance Criteria

- [ ] Support Visa, Mastercard, Amex
- [ ] Display card validation errors
- [ ] Show processing indicator

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Stripe integration | Set up Stripe SDK | - | 📋 Planned |
| 2 | Payment form | Create card input form | - | 📋 Planned |
| 3 | Error handling | Handle payment failures | - | 📋 Planned |

---

### 🧾 STORY-002: Receipt Generation

| Field | Value |
|-------|-------|
| **Type** | Feature |
| **Points** | 3 |
| **Status** | 📋 Unscheduled |
| **Labels** | payments, pdf |
| **Blocked By** | STORY-001 |

#### Description

**As a** customer
**I want** to receive a receipt
**So that** I have proof of purchase

---

### 🐛 BUG-001: Fix Currency Formatting

| Field | Value |
|-------|-------|
| **Type** | Bug |
| **Points** | 1 |
| **Status** | 📋 Unscheduled |
| **Labels** | bug, payments |

#### Description

Currency is displaying without proper formatting in some locales.
```

### 2. Preview Sync

```bash
spectra sync --tracker pivotal --markdown epic.md --project 1234567
```

### 3. Execute Sync

```bash
spectra sync --tracker pivotal --markdown epic.md --project 1234567 --execute
```

### 4. View Results

Check your Pivotal Tracker project for the synced stories.

## CI/CD Integration

### GitHub Actions

```yaml
name: Sync to Pivotal

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
      
      - name: Install spectra
        run: pip install spectra
      
      - name: Sync to Pivotal
        run: |
          spectra sync \
            --tracker pivotal \
            --markdown docs/EPIC.md \
            --project ${{ vars.PIVOTAL_PROJECT_ID }} \
            --execute \
            --no-confirm
        env:
          PIVOTAL_API_TOKEN: ${{ secrets.PIVOTAL_API_TOKEN }}
```

## Troubleshooting

### Authentication Errors

```
Error: Unauthorized
```

- Verify API token is valid
- Check token has not been revoked
- Ensure project membership

### Invalid Story State

```
Error: Invalid state transition
```

Pivotal enforces state transitions:
- unscheduled → unstarted → started → finished → delivered → accepted/rejected

### Points on Bugs/Chores

```
Error: Bugs and chores cannot have points
```

Only features can have story points. Remove points from bugs and chores:

```yaml
pivotal:
  points_on_features_only: true
```

### Label Limits

```
Error: Too many labels
```

Pivotal has a limit of 10 labels per story. Use:

```yaml
pivotal:
  max_labels: 10
  label_priority:
    - epic
    - mvp
    - team
```

## Best Practices

1. **Use Story Types Correctly** - Features for user value, bugs for defects, chores for tech work
2. **Estimate Features Only** - Don't estimate bugs and chores
3. **Use Labels Sparingly** - Focus on important categorizations
4. **Link Blockers** - Make dependencies visible
5. **Keep Stories Small** - Aim for 1-3 point stories

## Story Type Reference

| Type | When to Use | Has Points | Example |
|------|-------------|------------|---------|
| Feature | User-facing value | Yes | "User can reset password" |
| Bug | Defect/issue | No | "Login fails on Safari" |
| Chore | Technical work | No | "Upgrade React to v18" |

## See Also

- [Configuration Reference](/guide/configuration)
- [Quick Start](/guide/quick-start)
- [CI/CD Integration](/examples/cicd)
