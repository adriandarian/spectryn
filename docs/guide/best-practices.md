# Best Practices Guide

Recommended workflows and patterns for using spectryn effectively.

## Core Principles

### 1. Markdown as Source of Truth

Your markdown file should be the **authoritative source** for story definitions:

```
┌─────────────────┐      spectryn       ┌─────────────────┐
│    EPIC.md      │  ──────────────▶   │  Issue Tracker  │
│ (Source of Truth)│                    │   (Execution)   │
└─────────────────┘                    └─────────────────┘
```

::: tip Why Markdown First?
- Version controlled (Git history)
- Easy to review in PRs
- Works offline
- Editor-agnostic
- AI-friendly for generation
:::

### 2. Commit Before Sync

Always commit your markdown changes before syncing:

```bash
git add EPIC.md
git commit -m "feat: Add user authentication stories"
spectryn sync --markdown EPIC.md
```

This ensures you can:
- Review changes in PRs
- Rollback if needed
- Track who changed what

### 3. Use Dry Run First

Always preview changes before executing:

```bash
# See what would change
spectryn --markdown EPIC.md --epic PROJ-123

# Then execute
spectryn --execute --markdown EPIC.md --epic PROJ-123
```

---

## Project Setup

### Recommended File Structure

```
project/
├── docs/
│   ├── epics/
│   │   ├── user-auth.md
│   │   ├── payment-system.md
│   │   └── notifications.md
│   └── templates/
│       └── epic-template.md
├── spectryn.yaml
└── .spectryn/
    └── state.json
```

### Configuration File

Create a `spectryn.yaml` at your project root:

```yaml
# spectryn.yaml
tracker: jira
version: 1

jira:
  url: ${JIRA_URL}
  project: PROJ

defaults:
  story_type: Story
  subtask_type: Sub-task
  default_status: To Do
  default_priority: Medium

validation:
  require_acceptance_criteria: true
  require_story_points: true
  min_description_length: 20

mappings:
  status:
    "✅ Done": Done
    "🔄 In Progress": In Progress
    "📋 To Do": To Do
  priority:
    "🔴 Critical": Highest
    "🟠 High": High
    "🟡 Medium": Medium
    "🟢 Low": Low
```

### Environment Variables

Use `.env` for secrets (never commit):

```bash
# .env (add to .gitignore!)
JIRA_URL=https://company.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your-secret-token
```

---

## Writing Effective Stories

### Story Structure

Follow the template consistently:

```markdown
### 🔐 US-001: User Login

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟠 High |
| **Status** | 📋 To Do |
| **Assignee** | @john.doe |
| **Labels** | authentication, security |
| **Sprint** | Sprint 23 |

#### Description

**As a** registered user
**I want** to log in with my email and password
**So that** I can access my personalized dashboard

Additional context: Support SSO for enterprise customers.

#### Acceptance Criteria

- [ ] User can enter email and password
- [ ] Invalid credentials show error message
- [ ] Successful login redirects to dashboard
- [ ] "Remember me" option works for 30 days
- [ ] Account locks after 5 failed attempts

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Design login form | Create UI mockups | 1 | ✅ Done |
| 2 | Implement backend | Auth API endpoints | 2 | 🔄 In Progress |
| 3 | Add validation | Form validation logic | 1 | 📋 To Do |
| 4 | Write tests | Unit and E2E tests | 1 | 📋 To Do |
```

### Acceptance Criteria Best Practices

**Do:**
- [ ] Use checkboxes for trackable criteria
- [ ] Make each criterion testable
- [ ] Include edge cases
- [ ] Be specific about expected behavior

**Don't:**
- ❌ Vague criteria like "Works well"
- ❌ Implementation details
- ❌ Too many criteria (aim for 3-7)

### Story Sizing

| Points | Meaning | Example |
|--------|---------|---------|
| 1 | Trivial | Config change, copy update |
| 2 | Small | Simple CRUD endpoint |
| 3 | Medium | Feature with some complexity |
| 5 | Large | Full feature with edge cases |
| 8 | Very Large | Complex feature, consider splitting |
| 13 | Epic-sized | **Split this story!** |

::: warning
If a story is 13+ points, use `spectryn split` to break it down:
```bash
spectryn split --story US-001 --markdown EPIC.md
```
:::

---

## Workflow Patterns

### 1. Sprint Planning Workflow

```bash
# 1. Create/update stories in markdown
vim docs/epics/sprint-23.md

# 2. Validate structure
spectryn --validate --markdown docs/epics/sprint-23.md

# 3. Preview sync
spectryn diff --markdown docs/epics/sprint-23.md

# 4. Commit to git
git add docs/epics/sprint-23.md
git commit -m "plan: Sprint 23 stories"

# 5. Sync to tracker
spectryn sync --execute --markdown docs/epics/sprint-23.md

# 6. Push changes
git push
```

### 2. Story Refinement Workflow

```bash
# 1. Import current state from tracker
spectryn import --epic PROJ-123 --output docs/epics/current.md

# 2. Review and refine in markdown
# - Add acceptance criteria
# - Split large stories
# - Update estimates

# 3. Diff changes
spectryn diff --markdown docs/epics/current.md --epic PROJ-123

# 4. Sync refinements back
spectryn sync --execute --markdown docs/epics/current.md
```

### 3. AI-Assisted Planning

```bash
# 1. Generate stories from high-level description
spectryn ai generate \
  --prompt "User authentication with OAuth support" \
  --output docs/epics/auth.md

# 2. Review and refine AI output
vim docs/epics/auth.md

# 3. Validate and improve
spectryn ai refine --markdown docs/epics/auth.md

# 4. Sync when ready
spectryn sync --execute --markdown docs/epics/auth.md
```

### 4. CI/CD Integration

```yaml
# .github/workflows/sync-stories.yml
name: Sync Stories

on:
  push:
    paths:
      - 'docs/epics/**/*.md'
    branches:
      - main

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup spectryn
        uses: adriandarian/spectryn-action@v1

      - name: Validate stories
        run: spectryn --validate --markdown docs/epics/

      - name: Sync to Jira
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: spectryn sync --execute --markdown docs/epics/
```

---

## Team Collaboration

### Code Review for Stories

Include story changes in PRs:

```markdown
## PR Description

### Stories Added/Updated
- US-001: User Login (New)
- US-002: Password Reset (Updated AC)

### Sync Preview
```spectryn
spectryn diff --markdown docs/epics/auth.md
```

### Checklist
- [ ] Stories follow template
- [ ] Acceptance criteria are testable
- [ ] Story points estimated
- [ ] No duplicates
```

### Ownership Conventions

Use labels or prefixes for team ownership:

```markdown
### 🔐 US-001: User Login
| **Labels** | team:backend, authentication |

### 🎨 US-002: Login Page Design
| **Labels** | team:frontend, authentication |
```

### Communication

When syncing significant changes, notify the team:

```bash
# Generate summary for Slack/Teams
spectryn sync --execute --markdown EPIC.md --notify slack
```

---

## Error Prevention

### Validation Rules

Enable strict validation:

```yaml
# spectryn.yaml
validation:
  require_acceptance_criteria: true
  require_story_points: true
  require_description: true
  min_description_length: 20
  max_story_points: 13
  allowed_statuses:
    - To Do
    - In Progress
    - Done
    - Blocked
```

### Pre-commit Hook

Prevent invalid stories from being committed:

```bash
# Install hook
spectryn hook install

# Or manually in .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: spectryn-validate
        name: Validate spectryn stories
        entry: spectryn --validate --markdown
        language: system
        files: '\.md$'
```

### Backup Before Sync

Always have a backup:

```bash
# Automatic backup
spectryn sync --backup --execute --markdown EPIC.md

# Manual backup
spectryn backup create --epic PROJ-123

# List backups
spectryn backup list

# Restore if needed
spectryn backup restore --timestamp 2025-01-06T10:30:00
```

---

## Performance Tips

### For Large Projects

```yaml
# spectryn.yaml
performance:
  parallel_sync: true
  max_workers: 4
  cache:
    enabled: true
    ttl: 3600
```

### Incremental Sync

After initial sync, use incremental mode:

```bash
spectryn sync --incremental --markdown EPIC.md
```

### Split Large Files

If an epic file grows beyond 100 stories, split by theme:

```
docs/epics/
├── user-management/
│   ├── authentication.md
│   ├── authorization.md
│   └── profile.md
└── payments/
    ├── checkout.md
    └── subscriptions.md
```

---

## Common Mistakes to Avoid

### ❌ Don't: Edit in Both Places

```
WRONG:
1. Update story in Jira
2. Update same story in markdown
3. Sync → Conflict!
```

### ✅ Do: Single Source of Truth

```
RIGHT:
1. All changes in markdown
2. Review in PR
3. Sync to tracker
4. Tracker reflects markdown
```

### ❌ Don't: Sync Without Review

```bash
# WRONG - No preview!
spectryn sync --execute --markdown EPIC.md
```

### ✅ Do: Always Preview

```bash
# RIGHT - Preview first
spectryn diff --markdown EPIC.md
spectryn sync --execute --markdown EPIC.md
```

### ❌ Don't: Store Secrets in Config

```yaml
# WRONG - Never do this!
jira:
  api_token: my-secret-token
```

### ✅ Do: Use Environment Variables

```yaml
# RIGHT - Reference env vars
jira:
  api_token: ${JIRA_API_TOKEN}
```

---

## Checklist

Use this checklist for each sync:

- [ ] Stories follow the standard template
- [ ] All stories have acceptance criteria
- [ ] Story points are estimated (1-8 range)
- [ ] No duplicate story IDs
- [ ] Changes committed to git
- [ ] Dry run reviewed
- [ ] Team notified of significant changes
- [ ] Backup created for production sync
