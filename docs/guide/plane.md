# Plane.so Integration Guide

spectryn supports Plane.so for syncing markdown specifications. This guide covers configuration, authentication, workspace and project setup, self-hosted instances, and advanced features.

## Overview

The Plane.so adapter supports:
- ✅ Cycles (sprints) and Modules (epics)
- ✅ Issues (stories) and Sub-issues (subtasks)
- ✅ Workflow state mapping
- ✅ Priority mapping
- ✅ Story points (estimate points)
- ✅ Comments sync
- ✅ Assignees
- ✅ Labels
- ✅ File attachments
- ✅ Webhooks for real-time sync
- ✅ Views and filters
- ✅ Self-hosted instances

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Plane.so
spectryn --markdown EPIC.md --tracker plane --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Plane.so connection settings
plane:
  api_token: your-plane-api-token
  workspace_slug: your-workspace-slug  # Workspace slug (from URL)
  project_id: your-project-id  # Project ID (UUID)
  api_url: https://app.plane.so/api/v1  # Optional: defaults to Plane.so cloud API

  # Epic mapping (optional)
  epic_as_cycle: true  # If true, map Epic to Cycle; otherwise, to Module

  # Status mapping (optional - defaults provided)
  status_map:
    backlog: Backlog
    todo: Todo
    "in progress": In Progress
    done: Done
    cancelled: Cancelled

  # Priority mapping (optional - defaults provided)
  priority_map:
    urgent: Urgent
    high: High
    medium: Medium
    low: Low

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[plane]
api_token = "your-plane-api-token"
workspace_slug = "your-workspace-slug"
project_id = "your-project-id"
api_url = "https://app.plane.so/api/v1"

[plane.status_map]
backlog = "Backlog"
todo = "Todo"
"in progress" = "In Progress"
done = "Done"
cancelled = "Cancelled"

[plane.priority_map]
urgent = "Urgent"
high = "High"
medium = "Medium"
low = "Low"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export PLANE_API_TOKEN=your-plane-api-token
export PLANE_WORKSPACE_SLUG=your-workspace-slug
export PLANE_PROJECT_ID=your-project-id

# Optional
export PLANE_API_URL=https://app.plane.so/api/v1
export PLANE_EPIC_AS_CYCLE=true
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker plane \
  --plane-api-token your-token \
  --plane-workspace-slug your-workspace-slug \
  --plane-project-id your-project-id \
  --execute
```

## Authentication

### API Token Setup

1. **Log in to Plane.so**
   - Go to [app.plane.so](https://app.plane.so) (or your self-hosted instance)
   - Sign in to your workspace

2. **Generate API Token**
   - Click on your profile icon (top right)
   - Go to **Settings** → **API Tokens** (or **Account Settings** → **API**)
   - Click **Generate Token** or **Create Token**
   - Give it a descriptive name (e.g., "spectryn-sync")
   - Select appropriate permissions:
     - **Read**: View issues, cycles, modules
     - **Write**: Create and update issues, cycles, modules
     - **Full access**: Complete access (recommended for spectryn)
   - Copy the token immediately (you won't be able to see it again)

3. **Set Environment Variables**
   ```bash
   export PLANE_API_TOKEN=your-token-here
   export PLANE_WORKSPACE_SLUG=your-workspace-slug
   export PLANE_PROJECT_ID=your-project-id
   ```

::: warning Security
- Never commit tokens to version control
- Use environment variables or `.env` files (add to `.gitignore`)
- Rotate tokens regularly
- Use tokens with minimal required permissions
:::

### Token Permissions

| Permission | Required For |
|-----------|--------------|
| **Read** | View issues, cycles, modules, states, priorities |
| **Write** | Create/update issues, cycles, modules, comments |
| **Full access** | All operations including webhooks, attachments (recommended) |

### Testing Your Token

Test your token with a simple API call:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://app.plane.so/api/v1/workspaces/YOUR_WORKSPACE_SLUG/projects/YOUR_PROJECT_ID/ \
  -H "Content-Type: application/json"
```

You should receive a response with project information.

## Workspace and Project Configuration

### Finding Your Workspace Slug

The workspace slug is the identifier in your Plane.so workspace URL:

1. **Open your workspace in Plane.so**
2. **Check the URL**: `https://app.plane.so/{workspace-slug}/...`
   - Example: `https://app.plane.so/my-company/...` → workspace slug is `my-company`
3. **Or check workspace settings**:
   - Go to Settings → Workspace → General
   - The slug is shown in the workspace details

### Finding Your Project ID

The project ID is a UUID that identifies your project:

1. **Open your project in Plane.so**
2. **Check the URL**: `https://app.plane.so/{workspace-slug}/projects/{project-id}/...`
   - The project ID is the UUID in the URL
3. **Or check project settings**:
   - Go to Project Settings → General
   - The project ID is shown in the project details

### Workspace Structure

Plane.so organizes work as:
- **Workspaces**: Top-level organization (contains projects)
- **Projects**: Collections of issues, cycles, and modules
- **Cycles**: Time-boxed iterations (sprints)
- **Modules**: Feature groups (epics)
- **Issues**: Individual work items (stories)
- **Sub-issues**: Subtasks within issues
- **States**: Workflow status values (Backlog, Todo, In Progress, Done, etc.)
- **Priorities**: Issue priority levels (Urgent, High, Medium, Low)

## Self-Hosted Setup

Plane.so supports self-hosted instances. To use a self-hosted instance:

### Configuration

Set the `api_url` to your self-hosted instance URL:

```yaml
# .spectryn.yaml
plane:
  api_token: your-api-token
  workspace_slug: your-workspace-slug
  project_id: your-project-id
  api_url: https://plane.your-company.com/api/v1  # Self-hosted instance
```

Or via environment variable:

```bash
export PLANE_API_URL=https://plane.your-company.com/api/v1
```

### API Endpoint Structure

The adapter expects the API to follow Plane.so's standard structure:
- Base URL: `{api_url}/api/v1`
- Workspace endpoints: `/workspaces/{slug}/...`
- Project endpoints: `/workspaces/{slug}/projects/{id}/...`

### Authentication

Self-hosted instances use the same API token authentication:
1. Generate an API token from your self-hosted instance
2. Use the same token format and authentication headers
3. Ensure your instance has API access enabled

### Rate Limiting

Self-hosted instances may have different rate limits:
- Check your instance's rate limit configuration
- The adapter respects rate limits automatically
- Adjust rate limiter settings if needed for your instance

## Workflow State Mapping

Plane.so uses states to track issue status. The adapter maps standard statuses to Plane.so states:

### Default Status Mapping

| spectryn Status | Plane.so State |
|---------------|----------------|
| Backlog       | Backlog        |
| Todo          | Todo           |
| In Progress   | In Progress    |
| Done          | Done           |
| Cancelled     | Cancelled      |

### Custom State Mapping

You can customize state mapping in your config:

```yaml
plane:
  status_map:
    backlog: Backlog
    todo: Todo
    "in progress": In Progress
    "in review": In Review  # Custom state
    done: Done
    cancelled: Cancelled
```

### Finding Your States

To see available states in your project:
1. Go to Project Settings → States
2. View the states defined for your project
3. Use these exact names in your markdown status fields

## Priority Mapping

Plane.so supports issue priorities. The adapter maps standard priorities:

### Default Priority Mapping

| spectryn Priority | Plane.so Priority |
|------------------|-------------------|
| Critical         | Urgent            |
| High             | High              |
| Medium           | Medium            |
| Low              | Low               |

### Custom Priority Mapping

You can customize priority mapping in your config:

```yaml
plane:
  priority_map:
    critical: Urgent
    high: High
    medium: Medium
    low: Low
    minor: Low  # Custom mapping
```

## Story Mapping

### Epic → Cycle or Module

Plane.so supports both Cycles (sprints) and Modules (epics) for organizing work:

- **Epic as Cycle** (`epic_as_cycle: true`): Maps epics to time-boxed cycles
  - Useful for sprint-based workflows
  - Cycles have start/end dates
- **Epic as Module** (`epic_as_cycle: false`): Maps epics to feature modules
  - Useful for feature-based organization
  - Modules group related issues

Configure in your `.spectryn.yaml`:

```yaml
plane:
  epic_as_cycle: true  # or false for modules
```

### Story → Issue

- Stories are created as Plane.so issues
- Issue properties are mapped:
  - Title → Issue name
  - Description → Issue description
  - Status → State
  - Priority → Priority
  - Story Points → Estimate points

### Subtask → Sub-issue

- Subtasks are created as sub-issues
- Sub-issues appear nested under the parent issue
- Sub-issues inherit project and workspace from parent

### Story Points → Estimate Points

- Story points are mapped to Plane.so's estimate points
- Estimates are integers (Plane.so uses numeric scales)
- Default mapping: 1:1 (5 story points → 5 estimate points)

## Advanced Features

### Cycles (Sprints)

Cycles are time-boxed iterations for sprint planning:

```yaml
# Create a cycle
plane:
  # Cycle configuration is handled automatically
  # Epics can be mapped to cycles if epic_as_cycle: true
```

### Modules (Epics)

Modules group related issues for feature tracking:

```yaml
# Create a module
plane:
  epic_as_cycle: false  # Use modules instead of cycles
```

### Views and Filters

Plane.so supports saved views and filters:

- **Get views**: List all saved views for a project
- **Get view issues**: Get issues matching a view's filters
- **Create view**: Save a filter as a view
- **Update view**: Modify view filters
- **Delete view**: Remove a saved view

### Webhooks

Plane.so supports webhooks for real-time sync:

- **Create webhook**: Subscribe to project events
- **List webhooks**: View all webhook subscriptions
- **Update webhook**: Modify webhook configuration
- **Delete webhook**: Remove a webhook subscription

Supported events:
- `issue.created`, `issue.updated`, `issue.deleted`
- `cycle.created`, `cycle.updated`, `cycle.deleted`
- `module.created`, `module.updated`, `module.deleted`
- `comment.created`, `comment.updated`

### Attachments

Plane.so supports file attachments on issues:

- **Get attachments**: List all attachments for an issue
- **Upload attachment**: Add a file to an issue
- **Delete attachment**: Remove an attachment
- **Download attachment**: Download an attachment to local file

### Labels

Plane.so supports labels for categorizing issues:

- Labels can be added to issues during creation
- Labels are synced from markdown labels
- Filter issues by labels using views/filters

### Assignees

Plane.so supports assigning issues to team members:

- Assignees are synced from markdown assignee fields
- Assignee IDs are resolved from user emails or IDs
- Filter issues by assignee using views/filters

## Examples

### Basic Sync

```bash
# Dry run (preview changes)
spectryn --markdown EPIC.md --tracker plane

# Execute sync
spectryn --markdown EPIC.md --tracker plane --execute
```

### With Custom Configuration

```yaml
# .spectryn.yaml
plane:
  api_token: ${PLANE_API_TOKEN}
  workspace_slug: my-company
  project_id: 123e4567-e89b-12d3-a456-426614174000
  api_url: https://app.plane.so/api/v1
  epic_as_cycle: true

sync:
  execute: true
  update_source_file: true  # Write tracker info back to markdown
```

### Self-Hosted Instance

```yaml
# .spectryn.yaml
plane:
  api_token: ${PLANE_API_TOKEN}
  workspace_slug: my-company
  project_id: 123e4567-e89b-12d3-a456-426614174000
  api_url: https://plane.your-company.com/api/v1  # Self-hosted

sync:
  execute: true
```

### Markdown Example

```markdown
# Epic: User Authentication

## Stories

### STORY-001: Login Page
**Story Points:** 5
**Priority:** High
**Status:** In Progress
**Assignee:** developer@company.com

**As a** user
**I want** to log in with email and password
**So that** I can access my account

#### Acceptance Criteria
- [ ] Email and password fields are present
- [ ] Form validation works
- [ ] Error messages display correctly

#### Subtasks
- [ ] Design login form (STORY-001-T1)
- [ ] Implement authentication API (STORY-001-T2)
- [ ] Add error handling (STORY-001-T3)

#### Labels
- frontend
- authentication
- high-priority
```

## Troubleshooting

### Common Issues

#### "Authentication failed"
- Verify your API token is correct
- Check that the token hasn't expired
- Ensure the token has the necessary permissions
- For self-hosted instances, verify the API URL is correct

#### "Workspace not found"
- Verify the workspace slug is correct (check URL)
- Ensure you have access to the workspace
- Check that the workspace slug matches exactly (case-sensitive)

#### "Project not found"
- Verify the project ID is correct (UUID format)
- Check that you have access to the project
- Ensure the project exists in the specified workspace

#### "State not found"
- Check available states in Project Settings → States
- Use exact state names (case-sensitive)
- Verify the state exists in your project
- Update `status_map` in config if using custom states

#### "Priority not found"
- Check available priorities in Project Settings → Priorities
- Use exact priority names (case-sensitive)
- Update `priority_map` in config if using custom priorities

#### "Self-hosted instance connection failed"
- Verify the API URL is correct (should end with `/api/v1`)
- Check that your self-hosted instance has API access enabled
- Ensure network connectivity to the instance
- Verify SSL certificates if using HTTPS

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker plane --verbose
```

Or set in config:

```yaml
sync:
  verbose: true
```

## API Reference

### Endpoints Used

- `GET /workspaces/{slug}/projects/{id}/` - Get project
- `GET /workspaces/{slug}/projects/{id}/issues/` - List issues
- `GET /workspaces/{slug}/projects/{id}/issues/{issue_id}/` - Get issue
- `POST /workspaces/{slug}/projects/{id}/issues/` - Create issue
- `PATCH /workspaces/{slug}/projects/{id}/issues/{issue_id}/` - Update issue
- `GET /workspaces/{slug}/projects/{id}/cycles/` - List cycles
- `POST /workspaces/{slug}/projects/{id}/cycles/` - Create cycle
- `GET /workspaces/{slug}/projects/{id}/modules/` - List modules
- `POST /workspaces/{slug}/projects/{id}/modules/` - Create module
- `GET /workspaces/{slug}/projects/{id}/states/` - List states
- `GET /workspaces/{slug}/projects/{id}/priorities/` - List priorities
- `GET /workspaces/{slug}/projects/{id}/issues/{issue_id}/attachments/` - List attachments
- `POST /workspaces/{slug}/projects/{id}/issues/{issue_id}/attachments/` - Upload attachment
- `DELETE /workspaces/{slug}/projects/{id}/issues/{issue_id}/attachments/{attachment_id}/` - Delete attachment
- `GET /workspaces/{slug}/projects/{id}/views/` - List views
- `GET /workspaces/{slug}/projects/{id}/views/{view_id}/issues/` - Get view issues
- `POST /workspaces/{slug}/projects/{id}/webhooks/` - Create webhook
- `GET /workspaces/{slug}/projects/{id}/webhooks/` - List webhooks

### Rate Limits

- **Cloud instance**: Varies by plan (typically 100-1000 requests/minute)
- **Self-hosted**: Depends on instance configuration
- Adapter automatically throttles to stay under limit
- Retries with exponential backoff on 429 errors

## Best Practices

1. **Use Dry Run First**: Always test with `--execute` flag off first
2. **Backup Your Data**: Export your Plane.so project before bulk operations
3. **Incremental Syncs**: Sync frequently to avoid large changes
4. **State Names**: Use consistent state names across your project
5. **Epic Mapping**: Choose cycles vs modules based on your workflow
6. **Story Points**: Use consistent estimation scales
7. **Self-Hosted**: Test connectivity and API access before syncing
8. **Webhooks**: Use webhooks for real-time sync instead of polling
9. **Views**: Create saved views for common filter patterns
10. **Attachments**: Keep attachment sizes reasonable (< 10MB recommended)

## See Also

- [Configuration Guide](./configuration.md) - General configuration options
- [Getting Started](./getting-started.md) - Quick start guide
- [Schema Reference](./schema.md) - Markdown schema details
- [Plane.so API Documentation](https://docs.plane.so/api-reference) - Official API docs

