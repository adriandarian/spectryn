# Bitbucket Integration Guide

spectryn supports Bitbucket Cloud and Server for syncing markdown specifications. This guide covers configuration, authentication, workspace setup, and advanced features.

## Overview

The Bitbucket adapter supports:
- ✅ Bitbucket Cloud and Server (self-hosted)
- ✅ Issues, Milestones, and Epics
- ✅ Pull request linking
- ✅ Comments sync
- ✅ Attachments support
- ✅ Component and version fields
- ✅ Optional atlassian-python-api for enhanced Server support

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Optional: Install with atlassian-python-api for enhanced Server support
pip install spectryn[bitbucket]

# Sync markdown to Bitbucket
spectryn --markdown EPIC.md --tracker bitbucket --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Bitbucket connection settings
bitbucket:
  username: your-username
  app_password: your-app-password  # Cloud: App Password, Server: Personal Access Token
  workspace: your-workspace  # Workspace slug (Cloud) or project key (Server)
  repo: your-repo  # Repository slug
  base_url: https://api.bitbucket.org/2.0  # Optional: defaults to Cloud API

  # Label configuration (optional)
  epic_label: "epic"
  story_label: "story"
  subtask_label: "subtask"

  # Status mapping (optional)
  status_mapping:
    open: "open"
    "in progress": "open"
    done: "resolved"
    closed: "closed"

  # Priority mapping (optional)
  priority_mapping:
    critical: "blocker"
    high: "major"
    medium: "minor"
    low: "trivial"

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[bitbucket]
username = "your-username"
app_password = "your-app-password"
workspace = "your-workspace"
repo = "your-repo"
base_url = "https://api.bitbucket.org/2.0"

[bitbucket.status_mapping]
open = "open"
"in progress" = "open"
done = "resolved"
closed = "closed"

[bitbucket.priority_mapping]
critical = "blocker"
high = "major"
medium = "minor"
low = "trivial"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export BITBUCKET_USERNAME=your-username
export BITBUCKET_APP_PASSWORD=your-app-password
export BITBUCKET_WORKSPACE=your-workspace
export BITBUCKET_REPO=your-repo

# Optional
export BITBUCKET_BASE_URL=https://api.bitbucket.org/2.0
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker bitbucket \
  --bitbucket-username your-username \
  --bitbucket-app-password your-password \
  --bitbucket-workspace your-workspace \
  --bitbucket-repo your-repo \
  --execute
```

## Authentication

### Bitbucket Cloud: App Password Setup

App Passwords are required for Bitbucket Cloud authentication. They provide secure access without using your account password.

#### Step 1: Navigate to App Passwords

1. **Log in to Bitbucket**
   - Go to [bitbucket.org](https://bitbucket.org)
   - Sign in to your account

2. **Access Personal Settings**
   - Click your profile picture (bottom left)
   - Select **Personal settings**
   - Or go directly to: [https://bitbucket.org/account/settings/app-passwords/](https://bitbucket.org/account/settings/app-passwords/)

#### Step 2: Create App Password

1. **Click "Create app password"**
   - You'll see a list of existing app passwords (if any)

2. **Configure App Password**
   - **Label**: Give it a descriptive name (e.g., `spectryn-sync`)
   - **Permissions**: Select the required scopes:
     - ✅ **Issues: Write** - Create and update issues
     - ✅ **Issues: Read** - Read issues
     - ✅ **Repositories: Read** - Access repository information
     - ✅ **Pull requests: Read** - Link pull requests to issues
     - ✅ **Pull requests: Write** - Update pull requests (if needed)

3. **Create and Copy**
   - Click **Create**
   - **Important**: Copy the password immediately - it's shown only once!
   - Format: `xxxxxxxxxxxxxxxxxxxx` (20+ characters)

#### Step 3: Configure spectryn

```bash
export BITBUCKET_USERNAME=your-username
export BITBUCKET_APP_PASSWORD=xxxxxxxxxxxxxxxxxxxx
```

Or in config file:

```yaml
bitbucket:
  username: your-username
  app_password: xxxxxxxxxxxxxxxxxxxx
```

::: warning Security
- App Passwords are shown only once - save them securely
- Never commit app passwords to version control
- Use environment variables or `.env` files (add to `.gitignore`)
- Rotate app passwords regularly
- Use minimal required permissions
:::

### Bitbucket Server: Personal Access Token Setup

For self-hosted Bitbucket Server, use Personal Access Tokens (PATs) instead of App Passwords.

#### Step 1: Navigate to Access Tokens

1. **Log in to Bitbucket Server**
   - Go to your Server instance URL
   - Sign in with your account

2. **Access Personal Settings**
   - Click your profile picture → **Personal settings**
   - Navigate to **Access tokens** section
   - Or go directly to: `https://your-server.com/plugins/servlet/access-tokens`

#### Step 2: Create Personal Access Token

1. **Click "Create token"**

2. **Configure Token**
   - **Label**: Give it a descriptive name (e.g., `spectryn-sync`)
   - **Expiration**: Set appropriate expiration date
   - **Permissions**: Select required scopes:
     - ✅ **Read** - Read issues and repositories
     - ✅ **Write** - Create and update issues
     - ✅ **Admin** - Full access (if needed for advanced features)

3. **Create and Copy**
   - Click **Create**
   - **Important**: Copy the token immediately - it's shown only once!
   - Format: Varies by Server version

#### Step 3: Configure spectryn

```bash
export BITBUCKET_USERNAME=your-username
export BITBUCKET_APP_PASSWORD=your-pat-token
export BITBUCKET_BASE_URL=https://your-server.com/rest/api/2.0
```

Or in config file:

```yaml
bitbucket:
  username: your-username
  app_password: your-pat-token  # PAT for Server
  base_url: https://your-server.com/rest/api/2.0
```

### Token Permissions

| Permission | Required For |
|------------|--------------|
| **Issues: Read** | Reading issues, comments, attachments |
| **Issues: Write** | Creating and updating issues |
| **Repositories: Read** | Accessing repository information |
| **Pull requests: Read** | Linking pull requests to issues |

## Workspace and Repository Configuration

### Finding Your Workspace

**Bitbucket Cloud:**
- Workspace is the slug in your repository URL
- Example: `https://bitbucket.org/my-workspace/my-repo`
  - Workspace: `my-workspace`
  - Repository: `my-repo`

**Bitbucket Server:**
- Workspace is typically the project key
- Example: `https://server.com/projects/PROJ/repos/my-repo`
  - Workspace: `PROJ` (project key)
  - Repository: `my-repo`

### Configuration Examples

**Cloud:**
```yaml
bitbucket:
  username: john.doe
  app_password: xxxxxxxxxxxxxxxxxxxx
  workspace: acme-corp  # From URL: bitbucket.org/acme-corp/my-repo
  repo: backend-api
```

**Server:**
```yaml
bitbucket:
  username: john.doe
  app_password: your-pat-token
  workspace: PROJ  # Project key
  repo: backend-api
  base_url: https://bitbucket.company.com/rest/api/2.0
```

### Verifying Configuration

Test your configuration:

```bash
# Dry-run to verify connection
spectryn --markdown EPIC.md --tracker bitbucket --verbose
```

The adapter will:
1. Authenticate with Bitbucket
2. Verify workspace and repository access
3. List existing issues (if any)
4. Show what would be synced

## Bitbucket Server Setup

### Configuration

For self-hosted Bitbucket Server, set the `base_url`:

```yaml
bitbucket:
  username: your-username
  app_password: your-pat-token
  workspace: PROJ
  repo: your-repo
  base_url: https://bitbucket.yourcompany.com/rest/api/2.0
```

### Enhanced Server Support (Optional)

Install `atlassian-python-api` for enhanced Server support:

```bash
pip install spectryn[bitbucket]
```

**Benefits:**
- Better Server-specific feature support
- Improved error handling
- Enhanced compatibility with Server API quirks

The adapter automatically detects Server URLs and uses the library when available.

### SSL/TLS Certificates

If using self-signed certificates:

```bash
# Disable SSL verification (not recommended for production)
export BITBUCKET_SSL_VERIFY=false
```

For production, configure proper SSL certificates or use a certificate authority.

### Rate Limiting

Bitbucket Cloud: 1000 requests per hour
Bitbucket Server: Varies by instance configuration

The adapter automatically handles:
- Rate limit headers
- Exponential backoff retries
- Token bucket rate limiting

## Epic vs Milestone Mapping

Bitbucket supports both Milestones and Epic issues for organizing work.

### Milestones (Default)

Milestones are repository-level collections of issues.

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

### Epic Issues

Epic issues are special issue types that can contain other issues.

**Mapping:**
- Epic → Epic issue (with `epic` label)
- Story → Issue (referenced in epic issue)
- Subtask → Issue (linked to parent)

**Configuration:**
```yaml
bitbucket:
  epic_label: "epic"  # Label for epic issues
```

## Advanced Features

### Pull Request Linking

Link pull requests to issues automatically:

```python
from spectryn.adapters.bitbucket import BitbucketAdapter

adapter = BitbucketAdapter(
    username="user",
    app_password="pass",
    workspace="workspace",
    repo="repo",
)

# Get PRs linked to an issue
prs = adapter.get_pull_requests_for_issue("#123")

# Link PR to issue
adapter.link_pull_request(
    issue_key="#123",
    pull_request_id=456
)
```

Pull requests are automatically linked when referenced in issue content:
- `PR #456`
- `Pull Request 456`
- `https://bitbucket.org/workspace/repo/pull-requests/456`

### Attachments

Manage issue attachments:

```python
# Get attachments
attachments = adapter.get_issue_attachments("#123")

# Upload attachment
adapter.upload_attachment(
    issue_key="#123",
    file_path="document.pdf",
    description="Project documentation"
)

# Delete attachment
adapter.delete_attachment("#123", attachment_id="att1")
```

### Components and Versions

Set component and version fields:

```python
# List available components
components = adapter.list_components()
# Returns: [{"name": "Frontend", "id": "comp1"}, ...]

# List available versions
versions = adapter.list_versions()
# Returns: [{"name": "v1.0", "id": "ver1"}, ...]

# Update issue with component and version
adapter.update_issue_with_metadata(
    issue_key="#123",
    component="Frontend",
    version="v1.0"
)
```

### Comments Sync

Comments are automatically synced:

```python
# Get comments
comments = adapter.get_comments("#123")

# Add comment
adapter.add_comment("#123", "This is a comment")
```

## Status Mapping

Bitbucket has these issue states:
- `new` - Newly created
- `open` - Open/in progress
- `resolved` - Resolved
- `closed` - Closed
- `on hold` - On hold
- `invalid` - Invalid
- `duplicate` - Duplicate
- `wontfix` - Won't fix

**Default Mapping:**

| Spectra Status | Bitbucket State |
|----------------|-----------------|
| `open` | `open` |
| `in progress` | `open` |
| `done` | `resolved` |
| `closed` | `closed` |
| `blocked` | `on hold` |

**Custom Mapping:**

```yaml
bitbucket:
  status_mapping:
    open: "open"
    "in progress": "open"
    done: "resolved"
    closed: "closed"
    blocked: "on hold"
```

## Priority Mapping

Bitbucket priorities:
- `trivial` - Lowest
- `minor` - Low
- `major` - Medium
- `critical` - High
- `blocker` - Highest

**Default Mapping:**

| Spectra Priority | Bitbucket Priority |
|-------------------|---------------------|
| `low` | `minor` |
| `medium` | `major` |
| `high` | `critical` |
| `critical` | `blocker` |

**Custom Mapping:**

```yaml
bitbucket:
  priority_mapping:
    low: "minor"
    medium: "major"
    high: "critical"
    critical: "blocker"
```

## Story Points

Story points are stored in issue content:

```markdown
| **Story Points** | 5 |
```

The adapter extracts story points from the markdown table and includes them in issue content.

## Troubleshooting

### Common Issues

**Issue: "Authentication failed"**
- Verify username and app password/PAT are correct
- Check app password has required permissions
- For Server: verify base_url is correct
- Ensure token hasn't expired

**Issue: "Workspace not found"**
- Verify workspace slug/project key is correct
- Check token has access to the workspace/project
- For Cloud: workspace is the slug in the URL
- For Server: workspace is typically the project key

**Issue: "Repository not found"**
- Verify repository slug is correct
- Check token has access to the repository
- Ensure repository exists in the workspace/project

**Issue: "Rate limit exceeded"**
- The adapter handles rate limiting automatically
- Reduce sync frequency if hitting limits
- Cloud: 1000 requests/hour limit
- Server: Check instance rate limits

**Issue: "Server features not working"**
- Install `atlassian-python-api`: `pip install spectryn[bitbucket]`
- Verify Server URL is correctly formatted
- Check Server version compatibility

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker bitbucket --verbose
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
spectryn --markdown EPIC.md --tracker bitbucket

# Execute sync
spectryn --markdown EPIC.md --tracker bitbucket --execute
```

### Bitbucket Cloud

```bash
export BITBUCKET_USERNAME=john.doe
export BITBUCKET_APP_PASSWORD=xxxxxxxxxxxxxxxxxxxx
export BITBUCKET_WORKSPACE=acme-corp
export BITBUCKET_REPO=backend-api

spectryn --markdown EPIC.md --tracker bitbucket --execute
```

### Bitbucket Server

```bash
export BITBUCKET_USERNAME=john.doe
export BITBUCKET_APP_PASSWORD=your-pat-token
export BITBUCKET_WORKSPACE=PROJ
export BITBUCKET_REPO=backend-api
export BITBUCKET_BASE_URL=https://bitbucket.company.com/rest/api/2.0

spectryn --markdown EPIC.md --tracker bitbucket --execute
```

### With Enhanced Server Support

```bash
# Install with atlassian-python-api
pip install spectryn[bitbucket]

# Use as normal - adapter detects Server and uses library automatically
spectryn --markdown EPIC.md --tracker bitbucket --execute
```

## Reference

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `username` | string | Required | Bitbucket username |
| `app_password` | string | Required | App Password (Cloud) or PAT (Server) |
| `workspace` | string | Required | Workspace slug (Cloud) or project key (Server) |
| `repo` | string | Required | Repository slug |
| `base_url` | string | `https://api.bitbucket.org/2.0` | API base URL |
| `epic_label` | string | `"epic"` | Label for epic issues |
| `story_label` | string | `"story"` | Label for story issues |
| `subtask_label` | string | `"subtask"` | Label for subtask issues |
| `status_mapping` | dict | See above | Status to state mapping |
| `priority_mapping` | dict | See above | Priority mapping |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `BITBUCKET_USERNAME` | Bitbucket username |
| `BITBUCKET_APP_PASSWORD` | App Password (Cloud) or PAT (Server) |
| `BITBUCKET_WORKSPACE` | Workspace slug or project key |
| `BITBUCKET_REPO` | Repository slug |
| `BITBUCKET_BASE_URL` | API base URL |

### Issue States

| State | Description |
|-------|-------------|
| `new` | Newly created issue |
| `open` | Open/in progress |
| `resolved` | Resolved |
| `closed` | Closed |
| `on hold` | On hold |
| `invalid` | Invalid |
| `duplicate` | Duplicate |
| `wontfix` | Won't fix |

### Issue Priorities

| Priority | Description |
|----------|-------------|
| `trivial` | Lowest priority |
| `minor` | Low priority |
| `major` | Medium priority |
| `critical` | High priority |
| `blocker` | Highest priority |

## Next Steps

- [Configuration Guide](/guide/configuration) - Full configuration reference
- [Schema Reference](/guide/schema) - Markdown format guide
- [Quick Start](/guide/quick-start) - Your first sync

