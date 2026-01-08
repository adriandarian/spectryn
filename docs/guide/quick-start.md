# Quick Start

Get up and running with spectryn in 5 minutes.

## Step 1: Choose Your Tracker

spectryn supports many issue trackers. Set up credentials for your tracker:

::: code-group

```bash [Jira]
# .env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

```bash [GitHub]
# .env
GITHUB_TOKEN=ghp_your-personal-access-token
GITHUB_OWNER=your-username-or-org
GITHUB_REPO=your-repo
```

```bash [GitLab]
# .env
GITLAB_TOKEN=glpat-your-personal-access-token
GITLAB_PROJECT_ID=12345  # or group/project
GITLAB_BASE_URL=https://gitlab.com/api/v4  # or your self-hosted URL
```

```bash [Linear]
# .env
LINEAR_API_KEY=lin_api_your-api-key
LINEAR_TEAM_ID=TEAM
```

```bash [Azure DevOps]
# .env
AZURE_DEVOPS_ORG=your-organization
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_PAT=your-personal-access-token
```

```bash [Asana]
# .env
ASANA_ACCESS_TOKEN=your-personal-access-token
ASANA_WORKSPACE_ID=1234567890
ASANA_PROJECT_ID=0987654321
```

```bash [Trello]
# .env
TRELLO_API_KEY=your-api-key
TRELLO_API_TOKEN=your-api-token
TRELLO_BOARD_ID=your-board-id
```

```bash [ClickUp]
# .env
CLICKUP_API_TOKEN=pk_your-api-token
CLICKUP_LIST_ID=your-list-id
```

:::

::: warning
Add `.env` to your `.gitignore` to avoid committing secrets!
:::

## Step 2: Create Your Epic Markdown

Create `EPIC.md` with your user stories:

```markdown
# 🚀 My Project Epic

> **Epic: Building awesome features**

---

## User Stories

---

### 🔧 STORY-001: Set Up Project Infrastructure

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description

**As a** developer
**I want** project infrastructure set up
**So that** the team can start development

#### Acceptance Criteria

- [ ] Repository initialized
- [ ] CI/CD pipeline configured
- [ ] Development environment documented

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Create repo | Initialize Git repository | 1 | 📋 Planned |
| 2 | Add CI/CD | Set up GitHub Actions | 1 | 📋 Planned |
| 3 | Write docs | Document setup process | 1 | 📋 Planned |

---

### 🚀 STORY-002: User Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |

#### Description

**As a** user
**I want** to log in securely
**So that** my data is protected

#### Acceptance Criteria

- [ ] Login form with validation
- [ ] JWT token authentication
- [ ] Password reset flow

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login UI | Create login form | 2 | 📋 Planned |
| 2 | Auth backend | Implement JWT auth | 2 | 📋 Planned |
| 3 | Password reset | Add reset flow | 1 | 📋 Planned |

---
```

## Step 3: Validate Your Markdown

Before syncing, validate your markdown format:

```bash
spectryn --validate --markdown EPIC.md
```

If there are formatting issues, spectryn will suggest fixes:

```bash
# View the format guide
spectryn --validate --markdown EPIC.md --show-guide

# Get an AI prompt to fix issues (copy-paste to ChatGPT/Claude)
spectryn --validate --markdown EPIC.md --suggest-fix

# Auto-fix with AI CLI tools (if installed)
spectryn --validate --markdown EPIC.md --auto-fix
```

::: tip AI Fix
See the [AI Fix Guide](/guide/ai-fix) for detailed help with fixing formatting issues using AI tools.
:::

## Step 4: Preview Changes

Run spectryn in dry-run mode (default) to see what would change:

::: code-group

```bash [Jira]
spectryn sync --tracker jira --markdown EPIC.md --epic PROJ-123
```

```bash [GitHub]
spectryn sync --tracker github --markdown EPIC.md --repo owner/repo
```

```bash [GitLab]
spectryn sync --tracker gitlab --markdown EPIC.md --project group/project
```

```bash [Linear]
spectryn sync --tracker linear --markdown EPIC.md --team TEAM
```

```bash [Azure DevOps]
spectryn sync --tracker azure --markdown EPIC.md --project MyProject
```

```bash [Asana]
spectryn sync --tracker asana --markdown EPIC.md --project 1234567890
```

```bash [Trello]
spectryn sync --tracker trello --markdown EPIC.md --board abc123
```

:::

You'll see a detailed preview:

```
╭──────────────────────────────────────────────╮
│  spectryn - Sync Preview                      │
╰──────────────────────────────────────────────╯

Tracker: jira
Epic: PROJ-123
Stories found: 2
Mode: DRY RUN (no changes will be made)

┌─────────────────────────────────────────────┐
│ STORY-001: Set Up Project Infrastructure    │
├─────────────────────────────────────────────┤
│ ➕ Would create 3 subtasks                  │
│ 📝 Would update description                 │
│ ⏳ Would sync status: Planned               │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ STORY-002: User Authentication              │
├─────────────────────────────────────────────┤
│ ➕ Would create 3 subtasks                  │
│ 📝 Would update description                 │
│ ⏳ Would sync status: Planned               │
└─────────────────────────────────────────────┘

Summary: 2 stories, 6 subtasks to create
```

## Step 5: Execute Sync

When you're happy with the preview, add `--execute`:

::: code-group

```bash [Jira]
spectryn sync --tracker jira --markdown EPIC.md --epic PROJ-123 --execute
```

```bash [GitHub]
spectryn sync --tracker github --markdown EPIC.md --repo owner/repo --execute
```

```bash [GitLab]
spectryn sync --tracker gitlab --markdown EPIC.md --project group/project --execute
```

```bash [Linear]
spectryn sync --tracker linear --markdown EPIC.md --team TEAM --execute
```

:::

You'll be asked for confirmation:

```
This will modify 2 stories and create 6 subtasks.
Proceed? [y/N]: y
```

## Step 6: Verify in Your Tracker

Check your tracker to see the synced issues:

- ✅ Stories linked to the epic/project
- ✅ Descriptions updated with As a/I want/So that format
- ✅ Subtasks created under each story
- ✅ Story points and status set

## Common Commands

```bash
# Sync descriptions only
spectryn sync -m EPIC.md --epic PROJ-123 -x --phase descriptions

# Sync subtasks only
spectryn sync -m EPIC.md --epic PROJ-123 -x --phase subtasks

# Sync specific story
spectryn sync -m EPIC.md --epic PROJ-123 -x --story STORY-001

# Skip confirmation prompts (for CI/CD)
spectryn sync -m EPIC.md --epic PROJ-123 -x --no-confirm

# Verbose output
spectryn sync -m EPIC.md --epic PROJ-123 -v

# Export results to JSON
spectryn sync -m EPIC.md --epic PROJ-123 -x --export results.json
```

## Backup & Rollback

spectryn automatically creates backups before sync:

```bash
# List backups
spectryn backup list

# View diff from backup
spectryn backup diff --epic PROJ-123

# Rollback to previous state
spectryn backup rollback --epic PROJ-123 --execute
```

## Next Steps

- [Markdown Schema](/guide/schema) - Complete format reference
- [AI Fix](/guide/ai-fix) - Fix formatting issues with AI assistance
- [Configuration](/guide/configuration) - Config file options for all trackers
- [CLI Reference](/reference/cli) - All command options

## Tracker-Specific Guides

For detailed setup instructions for each tracker:

| Tracker | Guide |
|---------|-------|
| GitLab | [GitLab Guide](/guide/gitlab) |
| Trello | [Trello Guide](/guide/trello) |
| ClickUp | [ClickUp Guide](/guide/clickup) |
| Shortcut | [Shortcut Guide](/guide/shortcut) |
| Monday.com | [Monday Guide](/guide/monday) |
| Plane | [Plane Guide](/guide/plane) |
| YouTrack | [YouTrack Guide](/guide/youtrack) |
| Basecamp | [Basecamp Guide](/guide/basecamp) |
| Bitbucket | [Bitbucket Guide](/guide/bitbucket) |

