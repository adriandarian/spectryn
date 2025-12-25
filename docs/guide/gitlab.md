# GitLab Integration Guide

spectra supports GitLab Issues for syncing markdown specifications. This guide covers configuration, authentication, and advanced features.

## Overview

The GitLab adapter supports:
- ✅ GitLab.com and self-hosted instances
- ✅ Issues, Epics (Premium/Ultimate), and Milestones
- ✅ Labels, assignees, and story points (weights)
- ✅ Merge request linking
- ✅ Issue boards integration
- ✅ Time tracking
- ✅ Optional python-gitlab SDK support

## Quick Start

```bash
# Install spectra
pip install spectra

# Optional: Install with GitLab SDK support
pip install spectra[gitlab]

# Sync markdown to GitLab
spectra --markdown EPIC.md --tracker gitlab --execute
```

## Configuration

### Config File (YAML)

Create `.spectra.yaml`:

```yaml
# GitLab connection settings
gitlab:
  token: glpat-xxxxxxxxxxxxxxxxxxxx
  project_id: "12345"  # Numeric ID or "group/project" path
  base_url: https://gitlab.com/api/v4  # Optional: defaults to GitLab.com
  group_id: "mygroup"  # Optional: for Epic support (Premium/Ultimate)

  # Label configuration (optional)
  epic_label: "epic"
  story_label: "story"
  subtask_label: "subtask"

  # Status label mapping (optional)
  status_labels:
    open: "status:open"
    "in progress": "status:in-progress"
    done: "status:done"
    closed: "status:done"

  # Use python-gitlab SDK instead of custom client (optional)
  use_sdk: false

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectra.toml`:

```toml
[gitlab]
token = "glpat-xxxxxxxxxxxxxxxxxxxx"
project_id = "12345"
base_url = "https://gitlab.com/api/v4"
group_id = "mygroup"

[gitlab.status_labels]
open = "status:open"
"in progress" = "status:in-progress"
done = "status:done"
closed = "status:done"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
export GITLAB_PROJECT_ID=12345

# Optional
export GITLAB_BASE_URL=https://gitlab.com/api/v4
export GITLAB_GROUP_ID=mygroup
export GITLAB_USE_SDK=false
```

### CLI Arguments

```bash
spectra \
  --markdown EPIC.md \
  --tracker gitlab \
  --gitlab-token glpat-xxx \
  --gitlab-project-id 12345 \
  --gitlab-base-url https://gitlab.com/api/v4 \
  --execute
```

## API Authentication Setup

### Personal Access Token

1. **Navigate to GitLab Settings**
   - Go to GitLab.com → User Settings → Access Tokens
   - Or: Self-hosted instance → User Settings → Access Tokens

2. **Create Token**
   - Token name: `spectra-sync`
   - Expiration date: Set appropriate expiration
   - Scopes: Select `api` scope (minimum required)
   - Optional scopes:
     - `read_api` - Read-only access
     - `write_repository` - For merge request linking
     - `read_user` - Read user information

3. **Copy Token**
   - Copy the token immediately (shown only once)
   - Format: `glpat-xxxxxxxxxxxxxxxxxxxx`

4. **Configure spectra**
   ```bash
   export GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
   ```

### OAuth Token (Alternative)

For OAuth applications:

1. Create OAuth application in GitLab
2. Use OAuth token instead of Personal Access Token
3. Configure same way as PAT

### Token Permissions

| Scope | Required For |
|-------|--------------|
| `api` | All operations (minimum) |
| `read_api` | Read-only operations |
| `write_repository` | Merge request linking |

::: warning Security
- Never commit tokens to version control
- Use environment variables or `.env` files (add to `.gitignore`)
- Rotate tokens regularly
- Use tokens with minimal required permissions
:::

## Self-Hosted GitLab Setup

### Configuration

For self-hosted GitLab instances, set the `base_url`:

```yaml
gitlab:
  token: glpat-xxx
  project_id: "12345"
  base_url: https://gitlab.yourcompany.com/api/v4
```

### Environment Variable

```bash
export GITLAB_BASE_URL=https://gitlab.yourcompany.com/api/v4
```

### Project ID Format

Self-hosted GitLab supports the same project ID formats:
- **Numeric ID**: `12345` (found in project settings)
- **Path format**: `group/project` (e.g., `engineering/backend`)

### SSL/TLS Certificates

If using self-signed certificates:

```bash
# Disable SSL verification (not recommended for production)
export GITLAB_SSL_VERIFY=false
```

For production, configure proper SSL certificates or use a certificate authority.

### Rate Limiting

Self-hosted instances may have different rate limits. The adapter automatically handles:
- Rate limit headers
- Exponential backoff retries
- Token bucket rate limiting (2000 requests/hour default)

## Epic vs Milestone Mapping

GitLab offers two ways to organize issues: **Milestones** (all tiers) and **Epics** (Premium/Ultimate only).

### Milestones (Default - All Tiers)

Milestones are project-level collections of issues. They're available on all GitLab tiers.

**Configuration:**
```yaml
gitlab:
  use_epics: false  # Default: use milestones
```

**Mapping:**
- Epic → Milestone
- Story → Issue (assigned to milestone)
- Subtask → Issue (linked to parent)

**Example:**
```markdown
### 🚀 EPIC-001: User Authentication Epic

| Field | Value |
|-------|-------|
| **Milestone** | Q1 2024 |

### 🔧 US-001: Login Feature
...
```

### Epics (Premium/Ultimate Only)

Epics are group-level features that span multiple projects. Available on Premium and Ultimate tiers.

**Configuration:**
```yaml
gitlab:
  use_epics: true
  group_id: "mygroup"  # Required for epics
```

**Mapping:**
- Epic → GitLab Epic (group-level)
- Story → Issue (linked to epic via `#epic_iid` reference)
- Subtask → Issue (linked to parent)

**Example:**
```markdown
### 🚀 EPIC-001: User Authentication Epic

| Field | Value |
|-------|-------|
| **Epic** | Authentication |

### 🔧 US-001: Login Feature
...
```

### Choosing Between Milestones and Epics

| Feature | Milestones | Epics |
|---------|-----------|-------|
| **Availability** | All tiers | Premium/Ultimate |
| **Scope** | Project-level | Group-level |
| **Use Case** | Single project releases | Cross-project features |
| **Timeline** | Time-based | Feature-based |
| **Issues** | Assigned to milestone | Referenced via `#epic_iid` |

**Recommendation:**
- Use **Milestones** for project releases and sprints
- Use **Epics** for large features spanning multiple projects (if on Premium/Ultimate)

### Epic Configuration Options

```yaml
gitlab:
  # Use epics instead of milestones
  use_epics: true

  # Group ID for epics (required when use_epics=true)
  group_id: "engineering"

  # Epic label (for issue-based epics fallback)
  epic_label: "epic"
```

## Advanced Features

### Merge Request Linking

Link merge requests to issues automatically:

```python
from spectra.adapters.gitlab import GitLabAdapter

adapter = GitLabAdapter(
    token="glpat-xxx",
    project_id="12345",
)

# Get MRs linked to an issue
mrs = adapter.get_merge_requests_for_issue("#123")

# Link MR to issue (closes issue when merged)
adapter.link_merge_request(
    merge_request_iid=5,
    issue_key="#123",
    action="closes"  # Options: "closes", "fixes", "resolves", "relates to"
)
```

### Issue Boards

Move issues between board columns:

```python
# List boards
boards = adapter.list_boards()

# Get board lists (columns)
lists = adapter.get_board_lists(board_id=1)

# Move issue to specific list
adapter.move_issue_to_board_list(
    issue_key="#123",
    board_id=1,
    list_id=2
)
```

### Time Tracking

Track time spent on issues:

```python
# Get time stats
stats = adapter.get_issue_time_stats("#123")
# Returns: {"time_estimate": 3600, "total_time_spent": 1800, ...}

# Add spent time
adapter.add_spent_time("#123", duration="1h 30m", summary="Implemented feature")

# Set time estimate
adapter.estimate_time("#123", duration="3h")

# Reset time
adapter.reset_spent_time("#123")
adapter.reset_time_estimate("#123")
```

### Python-GitLab SDK Support

Use the official python-gitlab SDK instead of the custom client:

**Installation:**
```bash
pip install spectra[gitlab]
```

**Configuration:**
```yaml
gitlab:
  use_sdk: true  # Use python-gitlab SDK
```

**Benefits:**
- More features and better type hints
- Official SDK maintained by GitLab community
- Better IDE support

## Label Configuration

### Default Labels

The adapter uses these default labels:

```yaml
gitlab:
  epic_label: "epic"
  story_label: "story"
  subtask_label: "subtask"
```

### Status Labels

Map statuses to labels for workflow tracking:

```yaml
gitlab:
  status_labels:
    open: "status:open"
    "in progress": "status:in-progress"
    done: "status:done"
    closed: "status:done"
```

### Custom Labels

Create labels programmatically:

```python
adapter._client.create_label(
    name="priority:high",
    color="#ff0000",
    description="High priority issues"
)
```

## Story Points Mapping

Story points are mapped to GitLab's **weight** field:

```markdown
| **Story Points** | 5 |
```

This creates an issue with `weight: 5` in GitLab.

## Status Mapping

GitLab has two states: `opened` and `closed`. For workflow states, use labels:

| Spectra Status | GitLab State | Label |
|----------------|--------------|-------|
| `open` | `opened` | `status:open` |
| `in progress` | `opened` | `status:in-progress` |
| `done` | `closed` | `status:done` |
| `closed` | `closed` | `status:done` |

## Troubleshooting

### Common Issues

**Issue: "Project not found"**
- Verify `project_id` is correct (numeric ID or `group/project` path)
- Check token has access to the project
- For self-hosted: verify `base_url` is correct

**Issue: "Epic not found" (when using epics)**
- Ensure you're on Premium/Ultimate tier
- Verify `group_id` is correct
- Check token has access to the group

**Issue: "Rate limit exceeded"**
- The adapter handles rate limiting automatically
- Reduce sync frequency if hitting limits
- Check GitLab instance rate limits

**Issue: "Authentication failed"**
- Verify token is valid and not expired
- Check token has `api` scope
- For self-hosted: verify SSL certificates

### Debug Mode

Enable verbose logging:

```bash
spectra --markdown EPIC.md --tracker gitlab --verbose
```

Or in config:

```yaml
sync:
  verbose: true
```

## Examples

### Basic Sync

```bash
# Dry-run (preview changes)
spectra --markdown EPIC.md --tracker gitlab

# Execute sync
spectra --markdown EPIC.md --tracker gitlab --execute
```

### Self-Hosted Instance

```bash
export GITLAB_BASE_URL=https://gitlab.company.com/api/v4
export GITLAB_TOKEN=glpat-xxx
export GITLAB_PROJECT_ID=engineering/backend

spectra --markdown EPIC.md --tracker gitlab --execute
```

### With Epics (Premium/Ultimate)

```yaml
gitlab:
  token: glpat-xxx
  project_id: "12345"
  use_epics: true
  group_id: "engineering"
```

## Reference

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `token` | string | Required | GitLab Personal Access Token |
| `project_id` | string | Required | Project ID (numeric or path) |
| `base_url` | string | `https://gitlab.com/api/v4` | GitLab API base URL |
| `group_id` | string | `null` | Group ID for epics (Premium/Ultimate) |
| `use_epics` | boolean | `false` | Use Epics instead of Milestones |
| `use_sdk` | boolean | `false` | Use python-gitlab SDK |
| `epic_label` | string | `"epic"` | Label for epic issues |
| `story_label` | string | `"story"` | Label for story issues |
| `subtask_label` | string | `"subtask"` | Label for subtask issues |
| `status_labels` | dict | See above | Status to label mapping |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GITLAB_TOKEN` | Personal Access Token |
| `GITLAB_PROJECT_ID` | Project ID |
| `GITLAB_BASE_URL` | API base URL |
| `GITLAB_GROUP_ID` | Group ID for epics |
| `GITLAB_USE_SDK` | Use SDK (`true`/`false`) |

## Next Steps

- [Configuration Guide](/guide/configuration) - Full configuration reference
- [Schema Reference](/guide/schema) - Markdown format guide
- [Quick Start](/guide/quick-start) - Your first sync

