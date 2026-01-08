# Shortcut Integration Guide

spectryn supports Shortcut (formerly Clubhouse) for syncing markdown specifications. This guide covers configuration, authentication, workspace setup, and advanced features.

## Overview

The Shortcut adapter supports:
- ✅ Epics, Stories, and Tasks (subtasks)
- ✅ Workflow state mapping
- ✅ Story priority mapping
- ✅ Story points (estimates)
- ✅ Story dependencies
- ✅ Comments sync
- ✅ Story types (feature, bug, chore)

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Shortcut
spectryn --markdown EPIC.md --tracker shortcut --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Shortcut connection settings
shortcut:
  api_token: your-shortcut-api-token
  workspace_id: "your-workspace-id"  # Workspace ID (UUID or slug)
  api_url: https://api.app.shortcut.com/api/v3  # Optional: defaults to Shortcut API

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[shortcut]
api_token = "your-shortcut-api-token"
workspace_id = "your-workspace-id"
api_url = "https://api.app.shortcut.com/api/v3"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export SHORTCUT_API_TOKEN=your-shortcut-api-token
export SHORTCUT_WORKSPACE_ID=your-workspace-id

# Optional
export SHORTCUT_API_URL=https://api.app.shortcut.com/api/v3
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker shortcut \
  --shortcut-api-token your-token \
  --shortcut-workspace-id your-workspace-id \
  --execute
```

## Authentication

### API Token Setup

1. **Log in to Shortcut**
   - Go to [app.shortcut.com](https://app.shortcut.com)
   - Sign in to your workspace

2. **Generate API Token**
   - Click on your profile icon (top right)
   - Go to **Settings** → **API Tokens**
   - Click **Create Token**
   - Give it a name (e.g., "spectryn-sync")
   - Copy the token immediately (you won't be able to see it again)

3. **Find Your Workspace ID**
   - The workspace ID is typically found in your workspace URL
   - Example: `https://app.shortcut.com/workspace-name` → workspace ID is `workspace-name`
   - Or check your workspace settings for the UUID

4. **Set Environment Variables**
   ```bash
   export SHORTCUT_API_TOKEN=your-token-here
   export SHORTCUT_WORKSPACE_ID=your-workspace-id
   ```

### Token Permissions

The API token has the same permissions as your user account. Ensure your account has:
- **Read** access to stories, epics, and tasks
- **Write** access to create/update stories (for sync operations)
- **Admin** access if you need to manage epics

## Workspace Configuration

### Workspace ID

The workspace ID can be:
- **Slug**: The workspace name in the URL (e.g., `my-workspace`)
- **UUID**: The unique identifier (found in workspace settings)

To find your workspace ID:
1. Go to your Shortcut workspace
2. Check the URL: `https://app.shortcut.com/{workspace-id}`
3. Or go to Settings → Workspace → General to see the UUID

### Workspace Structure

Shortcut organizes work as:
- **Epics**: Collections of related stories
- **Stories**: Individual work items (features, bugs, chores)
- **Tasks**: Subtasks within stories
- **Workflow States**: Status values (To Do, In Progress, Done, etc.)

## Workflow State Mapping

Shortcut uses workflow states to track story status. The adapter maps standard statuses to Shortcut workflow states:

### Default Status Mapping

| spectryn Status | Shortcut Workflow State |
|----------------|------------------------|
| Planned        | To Do                  |
| Open           | To Do                  |
| In Progress    | In Progress            |
| In Review      | In Progress            |
| Done           | Done                   |
| Cancelled      | Done                   |

### Custom Workflow States

If your workspace uses custom workflow states, the adapter will:
1. Try to match by exact name (case-insensitive)
2. Try partial matching
3. Fall back to type-based matching (unstarted → To Do, started → In Progress, completed → Done)

### Finding Your Workflow States

To see available workflow states in your workspace:
1. Go to Settings → Workflows
2. View the states defined for your workflow
3. Use these exact names in your markdown status fields

## Story Mapping

### Epic → Epic
- Epics in markdown are created as Shortcut epics
- Epic children (stories) are linked to the epic

### Story → Story
- Stories are created as Shortcut stories
- Story type defaults to "feature" but can be "bug" or "chore" based on labels

### Subtask → Task
- Subtasks are created as tasks within the parent story
- Tasks appear in the story's task list

### Story Points → Estimate
- Story points are mapped to Shortcut's estimate field
- Estimates are integers (Shortcut uses Fibonacci or linear scales)

### Priority Mapping

Shortcut supports story priorities:
- **Critical** → High priority
- **High** → Medium-high priority
- **Medium** → Medium priority
- **Low** → Low priority

## Story Dependencies

Shortcut supports story dependencies. The adapter maps link types:

| Link Type          | Shortcut Dependency |
|--------------------|---------------------|
| `depends on`       | Story depends on target |
| `is dependency of` | Target depends on story (reverse) |
| `blocks`           | Target depends on story |
| `is blocked by`    | Story depends on target |

### Using Dependencies in Markdown

```markdown
### STORY-001: Example Story

**As a** developer
**I want** feature X
**So that** benefit Y

#### Links
| Link Type | Target |
|-----------|--------|
| depends on | STORY-002 |
| blocks | STORY-003 |
```

## Advanced Features

### Story Types

Shortcut supports different story types:
- **feature**: Default for user stories
- **bug**: For bug reports
- **chore**: For maintenance tasks

The adapter detects story type from:
1. Labels in markdown (e.g., `bug`, `chore`)
2. Story title patterns
3. Defaults to "feature"

### Comments

Comments are synced bidirectionally:
- Comments added in Shortcut appear in markdown
- Comments in markdown are added to Shortcut stories

### Rate Limiting

Shortcut API has a rate limit of **200 requests per minute**. The adapter:
- Automatically throttles requests
- Implements exponential backoff on rate limit errors
- Respects `Retry-After` headers

## Examples

### Basic Sync

```bash
# Dry run (preview changes)
spectryn --markdown EPIC.md --tracker shortcut

# Execute sync
spectryn --markdown EPIC.md --tracker shortcut --execute
```

### With Custom Configuration

```yaml
# .spectryn.yaml
shortcut:
  api_token: ${SHORTCUT_API_TOKEN}
  workspace_id: my-workspace
  api_url: https://api.app.shortcut.com/api/v3

sync:
  execute: true
  update_source_file: true  # Write tracker info back to markdown
```

### Markdown Example

```markdown
# Epic: User Authentication

## Stories

### STORY-001: Login Page
**Story Points:** 5
**Priority:** High
**Status:** In Progress

**As a** user
**I want** to log in with email and password
**So that** I can access my account

#### Acceptance Criteria
- [ ] Email and password fields are present
- [ ] Form validation works
- [ ] Error messages display correctly

#### Links
| Link Type | Target |
|-----------|--------|
| depends on | STORY-002 |

#### Subtasks
- [ ] Design login form (STORY-001-T1)
- [ ] Implement authentication API (STORY-001-T2)
- [ ] Add error handling (STORY-001-T3)
```

## Troubleshooting

### Common Issues

#### "Authentication failed"
- Verify your API token is correct
- Check that the token hasn't expired
- Ensure the token has the necessary permissions

#### "Workspace not found"
- Verify the workspace ID is correct
- Check that you have access to the workspace
- Try using the workspace slug instead of UUID (or vice versa)

#### "Workflow state not found"
- Check available workflow states in Settings → Workflows
- Use exact state names (case-sensitive)
- Verify the state exists in your workspace's workflow

#### "Story not found"
- Ensure the story ID exists in Shortcut
- Check that you have read access to the story
- Verify the story hasn't been deleted

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker shortcut --verbose
```

Or set in config:

```yaml
sync:
  verbose: true
```

## API Reference

### Endpoints Used

- `GET /member` - Get current user
- `GET /epics/{id}` - Get epic
- `GET /epics/{id}/stories` - Get epic children
- `GET /stories/{id}` - Get story
- `POST /stories` - Create story
- `PUT /stories/{id}` - Update story
- `GET /stories/{id}/tasks` - Get story tasks
- `POST /stories/{id}/tasks` - Create task
- `GET /workflows` - Get workflow states
- `GET /stories/{id}/comments` - Get comments
- `POST /stories/{id}/comments` - Create comment

### Rate Limits

- **200 requests per minute** per workspace
- Adapter automatically throttles to stay under limit
- Retries with exponential backoff on 429 errors

## Best Practices

1. **Use Dry Run First**: Always test with `--execute` flag off first
2. **Backup Your Data**: Export your Shortcut workspace before bulk operations
3. **Incremental Syncs**: Sync frequently to avoid large changes
4. **Workflow State Names**: Use consistent workflow state names across your workspace
5. **Story Dependencies**: Define dependencies clearly in markdown for better tracking
6. **Story Points**: Use consistent estimation scales (Fibonacci recommended)

## See Also

- [Configuration Guide](../guide/configuration.md) - General configuration options
- [Getting Started](../guide/getting-started.md) - Quick start guide
- [Schema Reference](../guide/schema.md) - Markdown schema details

