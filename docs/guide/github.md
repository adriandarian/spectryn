# GitHub Integration Guide

spectra supports GitHub Issues and Projects for syncing markdown specifications. This guide covers configuration, authentication, and advanced features.

## Overview

The GitHub adapter supports:
- ✅ GitHub.com and GitHub Enterprise
- ✅ Issues with labels, milestones, and assignees
- ✅ GitHub Projects (v2) integration
- ✅ Pull request linking
- ✅ Markdown rendering
- ✅ Issue templates
- ✅ Organization and user repositories

## Quick Start

```bash
# Install spectra
pip install spectra

# Sync markdown to GitHub
spectra sync --markdown EPIC.md --tracker github --repo owner/repo --execute
```

## Configuration

### Config File (YAML)

Create `.spectra.yaml`:

```yaml
# GitHub connection settings
github:
  token: ghp_xxxxxxxxxxxxxxxxxxxx
  owner: your-org-or-username
  repo: your-repo
  
  # Optional: GitHub Enterprise
  base_url: https://api.github.com  # or https://github.mycompany.com/api/v3
  
  # Optional: GitHub Projects v2
  project_number: 1  # Project board number
  
  # Label configuration (optional)
  epic_label: "epic"
  story_label: "user-story"
  subtask_label: "subtask"
  
  # Priority labels (optional)
  priority_labels:
    critical: "priority: critical"
    high: "priority: high"
    medium: "priority: medium"
    low: "priority: low"
  
  # Status labels (optional)
  status_labels:
    planned: "status: todo"
    in_progress: "status: in-progress"
    done: "status: done"

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectra.toml`:

```toml
[github]
token = "ghp_xxxxxxxxxxxxxxxxxxxx"
owner = "your-org-or-username"
repo = "your-repo"
base_url = "https://api.github.com"
project_number = 1

[github.priority_labels]
critical = "priority: critical"
high = "priority: high"
medium = "priority: medium"
low = "priority: low"

[github.status_labels]
planned = "status: todo"
in_progress = "status: in-progress"
done = "status: done"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
export GITHUB_OWNER=your-org-or-username
export GITHUB_REPO=your-repo

# Optional
export GITHUB_BASE_URL=https://api.github.com
export GITHUB_PROJECT_NUMBER=1
```

### CLI Arguments

```bash
spectra sync \
  --tracker github \
  --markdown EPIC.md \
  --repo owner/repo \
  --execute
```

## Authentication

### Personal Access Token (Classic)

1. Go to **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Select scopes:
   - `repo` - Full repository access
   - `project` - Project board access (if using Projects)
4. Copy the token (starts with `ghp_`)

### Fine-Grained Personal Access Token

1. Go to **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click **Generate new token**
3. Select repository access
4. Set permissions:
   - **Issues**: Read and write
   - **Projects**: Read and write (if using Projects)
   - **Pull requests**: Read (for linking)

### GitHub App (Recommended for Organizations)

For production use, consider creating a GitHub App:

```yaml
github:
  app_id: 12345
  installation_id: 67890
  private_key_path: /path/to/private-key.pem
```

## Features

### Issue Creation

Stories become GitHub Issues:

```markdown
### 🚀 STORY-001: User Authentication

| Field | Value |
|-------|-------|
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Labels** | feature, authentication |
| **Milestone** | v1.0.0 |
| **Assignee** | @username |

#### Description

**As a** user
**I want** to log in securely
**So that** my data is protected
```

Creates:
- Issue titled "User Authentication"
- Labels: `feature`, `authentication`, `user-story`, `priority: critical`
- Milestone: v1.0.0
- Assignee: @username

### Subtasks as Checklists

Subtasks become task lists within the issue:

```markdown
#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login form | Create login UI | 2 | 📋 Planned |
| 2 | Auth backend | Implement JWT | 3 | 🔄 In Progress |
```

Renders as:
```markdown
## Subtasks
- [ ] Login form - Create login UI (2 SP)
- [x] Auth backend - Implement JWT (3 SP)
```

### GitHub Projects Integration

Link issues to GitHub Projects v2:

```yaml
github:
  project_number: 1
  
  # Map status to project columns
  project_status_mapping:
    planned: "Todo"
    in_progress: "In Progress"
    done: "Done"
```

### Milestones

Map epics or releases to milestones:

```yaml
github:
  auto_create_milestones: true
  milestone_mapping:
    "Sprint 1": "v1.0.0"
    "Sprint 2": "v1.1.0"
```

### Issue Templates

Use existing issue templates:

```yaml
github:
  issue_template: "user-story.md"
```

## Advanced Configuration

### Label Synchronization

```yaml
github:
  sync_labels: true  # Create missing labels
  label_colors:
    epic: "0052CC"
    story: "5319E7"
    bug: "D73A4A"
    priority-critical: "B60205"
```

### Cross-Repository References

```yaml
github:
  cross_repo_refs: true
  related_repos:
    - owner/frontend
    - owner/backend
```

### Pull Request Integration

Link PRs to issues:

```yaml
github:
  link_prs: true
  pr_keywords:
    - "fixes"
    - "closes"
    - "resolves"
```

## Example Workflow

### 1. Create Epic Markdown

```markdown
# 🚀 User Management Epic

> **Epic: Complete user management system**

---

## User Stories

---

### 📝 US-001: User Registration

| Field | Value |
|-------|-------|
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Labels** | feature, auth |
| **Milestone** | v1.0.0 |

#### Description

**As a** visitor
**I want** to create an account
**So that** I can access the platform

#### Acceptance Criteria

- [ ] Email validation
- [ ] Password strength requirements
- [ ] Email verification flow

---

### 📝 US-002: User Profile

| Field | Value |
|-------|-------|
| **Priority** | 🟡 Medium |
| **Status** | 📋 Planned |
| **Labels** | feature, profile |
| **Milestone** | v1.0.0 |

#### Description

**As a** user
**I want** to manage my profile
**So that** I can update my information
```

### 2. Preview Sync

```bash
spectra sync --tracker github --markdown epic.md --repo owner/repo
```

### 3. Execute Sync

```bash
spectra sync --tracker github --markdown epic.md --repo owner/repo --execute
```

### 4. View Results

Check your GitHub repository's Issues tab and Project board.

## Troubleshooting

### Authentication Errors

```
Error: Bad credentials
```

- Verify token is valid and not expired
- Check token has required scopes
- For GitHub Enterprise, ensure correct base URL

### Rate Limiting

```
Error: API rate limit exceeded
```

- Use authenticated requests (increases limit from 60 to 5000/hour)
- Enable caching: `spectra sync --cache`
- Use `--delay` flag: `spectra sync --delay 1000`

### Project Access

```
Error: Could not resolve to a ProjectV2
```

- Verify project number is correct
- Ensure token has `project` scope
- Check you have write access to the project

## Best Practices

1. **Use Fine-Grained Tokens** - Minimize permissions to only what's needed
2. **Enable Projects** - Better visualization of story progress
3. **Use Milestones** - Track release progress
4. **Label Consistently** - Use label prefixes like `priority:`, `status:`
5. **Link PRs** - Automatic issue closing with PR keywords

## See Also

- [Configuration Reference](/guide/configuration)
- [Quick Start](/guide/quick-start)
- [GitHub Actions CI/CD](/examples/cicd)
