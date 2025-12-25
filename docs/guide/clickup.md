# ClickUp Integration Guide

spectra supports ClickUp for syncing markdown specifications. This guide covers configuration, authentication, space/folder/list hierarchy, and advanced features.

## Overview

The ClickUp adapter supports:
- ✅ Spaces, Folders, Lists, and Tasks (hierarchical structure)
- ✅ Goals (epics) and Tasks (stories)
- ✅ Subtasks and Checklist items
- ✅ Custom statuses per list
- ✅ Priority mapping (Urgent, High, Normal, Low)
- ✅ Story points via custom fields
- ✅ Time tracking (time entries, stats)
- ✅ Task dependencies and relationships
- ✅ Views (Board, List, Calendar, Table, Timeline, Gantt)
- ✅ Comments sync
- ✅ Webhooks for real-time sync
- ✅ Custom fields support

## Quick Start

```bash
# Install spectra
pip install spectra

# Sync markdown to ClickUp
spectra --markdown EPIC.md --tracker clickup --execute
```

## Configuration

### Config File (YAML)

Create `.spectra.yaml`:

```yaml
# ClickUp connection settings
clickup:
  api_token: your-clickup-api-token
  space_id: "your-space-id"  # Optional: Space ID (for scoping operations)
  folder_id: "your-folder-id"  # Optional: Folder ID (for scoping operations)
  list_id: "your-list-id"  # Optional: List ID (for scoping operations)
  api_url: https://api.clickup.com/api/v2  # Optional: defaults to ClickUp API v2

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectra.toml`:

```toml
[clickup]
api_token = "your-clickup-api-token"
space_id = "your-space-id"
folder_id = "your-folder-id"
list_id = "your-list-id"
api_url = "https://api.clickup.com/api/v2"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export CLICKUP_API_TOKEN=your-clickup-api-token

# Optional (for scoping operations)
export CLICKUP_SPACE_ID=your-space-id
export CLICKUP_FOLDER_ID=your-folder-id
export CLICKUP_LIST_ID=your-list-id

# Optional
export CLICKUP_API_URL=https://api.clickup.com/api/v2
```

### CLI Arguments

```bash
spectra \
  --markdown EPIC.md \
  --tracker clickup \
  --clickup-api-token your-token \
  --clickup-list-id your-list-id \
  --execute
```

## Authentication

### API Token Setup

1. **Log in to ClickUp**
   - Go to [app.clickup.com](https://app.clickup.com)
   - Sign in to your workspace

2. **Generate API Token**
   - Click on your profile icon (bottom left)
   - Go to **Settings** → **Apps** → **API**
   - Click **Generate** to create a new API token
   - Give it a name (e.g., "spectra-sync")
   - Copy the token immediately (you won't be able to see it again)
   - **Important**: Store the token securely - it provides full access to your ClickUp workspace

3. **Token Permissions**
   - ClickUp API tokens have full access to your workspace
   - Ensure you're using a token from an account with appropriate permissions
   - Consider creating a dedicated service account for automation

## Space/Folder/List Hierarchy

ClickUp uses a hierarchical structure:

```
Team
└── Space
    └── Folder (optional)
        └── List
            └── Task
                ├── Subtask
                └── Checklist Item
```

### Understanding the Hierarchy

- **Team**: Top-level organization (usually your company/workspace)
- **Space**: Project or department container
- **Folder**: Optional grouping within a space (can represent an epic)
- **List**: Board column or project list (like a Kanban board column)
- **Task**: Individual work item (maps to Story)
- **Subtask**: Child task (maps to Subtask)
- **Checklist**: Items within a task (alternative to subtasks)

### Finding IDs

#### Space ID

1. Open ClickUp and navigate to your Space
2. The Space ID is in the URL: `https://app.clickup.com/{team_id}/v/li/{space_id}`
3. Or use the API: `GET /team/{team_id}/space` to list all spaces

#### Folder ID

1. Open a Folder within a Space
2. The Folder ID is in the URL: `https://app.clickup.com/{team_id}/v/f/{folder_id}`
3. Or use the API: `GET /space/{space_id}/folder` to list folders

#### List ID

1. Open a List
2. The List ID is in the URL: `https://app.clickup.com/{team_id}/v/li/{list_id}`
3. Or use the API: `GET /folder/{folder_id}/list` to list lists

#### Team ID

1. The Team ID is typically in your workspace URL
2. Or use the API: `GET /team` to list all teams

### Configuration Examples

**Minimal Configuration** (list-level):
```yaml
clickup:
  api_token: your-token
  list_id: "12345678"  # All operations scoped to this list
```

**Space-level Configuration**:
```yaml
clickup:
  api_token: your-token
  space_id: "87654321"  # Operations can span all folders/lists in space
```

**Folder-level Configuration**:
```yaml
clickup:
  api_token: your-token
  folder_id: "11223344"  # Operations scoped to this folder
```

## Custom Fields Configuration

ClickUp supports custom fields for additional metadata. Story points are typically stored in a custom field.

### Finding Custom Field IDs

1. **Via ClickUp UI**:
   - Open a task in ClickUp
   - Click on a custom field
   - The field ID may be visible in the browser developer tools (Network tab)
   - Or check the field settings

2. **Via API**:
   ```bash
   # Get a task to see its custom fields
   curl -H "Authorization: YOUR_API_TOKEN" \
     https://api.clickup.com/api/v2/task/TASK_ID
   ```
   - Look for the `custom_fields` array in the response
   - Each field has an `id` property

### Story Points Custom Field

ClickUp doesn't have a built-in "story points" field. You need to:

1. **Create a Custom Field**:
   - Go to List settings → Custom Fields
   - Create a "Number" type field named "Story Points" or "Points"
   - Note the field ID

2. **Configure in spectra**:
   - The adapter automatically detects custom fields with "story point" or "point" in the name
   - No manual configuration needed if you use standard naming

3. **Manual Field ID** (if needed):
   ```yaml
   # Note: ClickUp adapter auto-detects story points fields
   # Manual configuration not currently required
   ```

### Custom Field Types

ClickUp supports various custom field types:
- **Number**: For story points, estimates, etc.
- **Text**: For additional notes
- **Dropdown**: For categorization
- **Date**: For due dates, milestones
- **Checkbox**: For flags
- **Email/Phone/URL**: For contact information
- **Formula**: Calculated fields
- **Rating**: Star ratings

## Entity Mapping

### Epic → Goal or Folder

ClickUp doesn't have a native "Epic" concept. Epics can be represented as:

- **Goal**: High-level objective (recommended for epics)
  - Created via Goals API
  - Can span multiple teams/spaces
  - Good for long-term objectives

- **Folder**: Collection of lists (alternative for epics)
  - Created within a Space
  - Can contain multiple Lists
  - Good for project-level grouping

### Story → Task

- Stories map directly to ClickUp Tasks
- Tasks belong to a List
- Support custom statuses, priorities, assignees, due dates

### Subtask → Subtask or Checklist Item

- **Subtask**: Child task (recommended)
  - Full-featured task with its own status, assignee, etc.
  - Appears in task hierarchy
  - Can have its own subtasks

- **Checklist Item**: Simple checkbox item
  - Lightweight alternative
  - Good for simple to-do items
  - Limited metadata support

### Status Mapping

ClickUp uses **custom statuses** per list. Each list can have different statuses:

- Common statuses: "Open", "In Progress", "Complete", "On Hold"
- Statuses are list-specific
- The adapter automatically maps common status names

**Status Mapping Examples**:
- `Planned` → "Open" or "Backlog"
- `In Progress` → "In Progress" or "Working"
- `Done` → "Complete" or "Closed"
- `Blocked` → "On Hold" or "Blocked"

### Priority Mapping

ClickUp priorities map as follows:

| spectra Priority | ClickUp Priority | Value |
|------------------|------------------|-------|
| Critical | Urgent | 1 |
| High | High | 2 |
| Medium | Normal | 3 |
| Low | Low | 4 |

## Advanced Features

### Time Tracking

ClickUp has built-in time tracking. The adapter supports:

```python
# Get time stats for a task
stats = adapter.get_task_time_stats("task123")
# Returns: {"time_spent": 3600000, "time_estimate": 7200000, "time_entries_count": 3}

# Add spent time
adapter.add_spent_time(
    task_id="task123",
    duration=1800000,  # 30 minutes in milliseconds
    start=1609459200000,  # Unix timestamp in milliseconds
    billable=True,
    description="Worked on feature"
)

# Get time entries
entries = adapter.get_time_entries(
    team_id="team123",
    task_id="task123",  # Optional: filter by task
    start_date=1609459200000,  # Optional: start date
    end_date=1612137600000  # Optional: end date
)
```

### Dependencies and Relationships

ClickUp supports task dependencies:

```python
# Get dependencies for a task
links = adapter.get_issue_links("task123")
# Returns list of IssueLink objects

# Create a dependency
adapter.create_link(
    source_key="task123",
    target_key="task456",
    link_type=LinkType.DEPENDS_ON
)

# Delete a dependency
adapter.delete_link("task123", "task456")

# Get available link types
link_types = adapter.get_link_types()
# Returns: [{"name": "Waiting On", "type": "waiting_on"}, ...]
```

**Dependency Types**:
- `waiting_on`: Task depends on another (maps to `DEPENDS_ON`)
- `blocked_by`: Task is blocked by another (maps to `IS_BLOCKED_BY`)

### Views

ClickUp supports multiple view types:

```python
# Get all views for a team
views = adapter.get_views(team_id="team123")
# Returns: [{"id": "view1", "name": "Board View", "type": "board"}, ...]

# Filter by view type
board_views = adapter.get_views(team_id="team123", view_type="board")
calendar_views = adapter.get_views(team_id="team123", view_type="calendar")

# Get a specific view
view = adapter.get_view("view123")

# Get tasks from a view
tasks = adapter.get_view_tasks("view123", page=0, include_closed=False)
# Returns list of IssueData objects
```

**Supported View Types**:
- `board`: Kanban board view
- `list`: List view
- `calendar`: Calendar view
- `table`: Table/spreadsheet view
- `timeline`: Timeline/Gantt view
- `gantt`: Gantt chart view

### Webhooks

ClickUp supports webhooks for real-time sync:

```python
# Create a webhook
webhook = adapter.create_webhook(
    endpoint="https://your-server.com/webhook",
    team_id="team123",
    events=["taskCreated", "taskUpdated", "taskStatusUpdated"]
)

# List webhooks
webhooks = adapter.list_webhooks(team_id="team123")

# Get a webhook
webhook = adapter.get_webhook("webhook123")

# Update a webhook
adapter.update_webhook(
    webhook_id="webhook123",
    endpoint="https://new-url.com/webhook",
    status="active"
)

# Delete a webhook
adapter.delete_webhook("webhook123")
```

**Supported Events**:
- `taskCreated`, `taskUpdated`, `taskDeleted`
- `taskStatusUpdated`, `taskPriorityUpdated`, `taskAssigneeUpdated`
- `taskCommentPosted`, `taskCommentUpdated`, `taskCommentDeleted`
- `taskTimeTracked`, `taskTimeDeleted`
- `listCreated`, `listUpdated`, `listDeleted`
- `folderCreated`, `folderUpdated`, `folderDeleted`
- `spaceCreated`, `spaceUpdated`, `spaceDeleted`

## Rate Limiting

ClickUp API rate limits:
- **100 requests per minute** per API token
- The adapter automatically handles rate limiting
- Requests are throttled to stay under the limit

## Error Handling

Common errors and solutions:

### Authentication Error
```
AuthenticationError: ClickUp authentication failed. Check your API token.
```
**Solution**: Verify your API token is correct and hasn't expired.

### Not Found Error
```
NotFoundError: Resource not found
```
**Solution**: Check that the Space/Folder/List/Task ID exists and is accessible.

### Rate Limit Error
```
RateLimitError: ClickUp rate limit exceeded
```
**Solution**: The adapter automatically retries with backoff. If persistent, reduce request frequency.

### Missing Team ID
```
IssueTrackerError: team_id is required
```
**Solution**: Provide `team_id` parameter or configure `space_id` to auto-detect.

## Best Practices

1. **Scope Configuration**: Use `list_id` for focused operations, `space_id` for broader scope
2. **Custom Fields**: Use consistent naming for story points fields ("Story Points", "Points")
3. **Status Names**: Keep status names consistent across lists for easier mapping
4. **Dependencies**: Use `waiting_on` for sequential work, `blocked_by` for blockers
5. **Time Tracking**: Track time at the task level for better reporting
6. **Views**: Use Board views for Kanban workflows, List views for traditional backlogs

## Examples

### Sync Epic to ClickUp Goal

```bash
# Create a goal (epic) first
# Then sync stories as tasks linked to the goal

spectra \
  --markdown EPIC.md \
  --tracker clickup \
  --clickup-api-token $CLICKUP_API_TOKEN \
  --clickup-space-id $CLICKUP_SPACE_ID \
  --execute
```

### Sync to Specific List

```bash
spectra \
  --markdown STORIES.md \
  --tracker clickup \
  --clickup-api-token $CLICKUP_API_TOKEN \
  --clickup-list-id $CLICKUP_LIST_ID \
  --execute
```

### Dry Run (Preview Changes)

```bash
spectra \
  --markdown EPIC.md \
  --tracker clickup \
  --clickup-api-token $CLICKUP_API_TOKEN \
  --clickup-list-id $CLICKUP_LIST_ID
  # --execute flag omitted = dry-run mode
```

## Troubleshooting

### Tasks Not Appearing

- Verify the `list_id` is correct
- Check that the list exists and is accessible
- Ensure the API token has permissions

### Status Not Updating

- Verify the status name matches exactly (case-sensitive)
- Check available statuses: `adapter.get_available_transitions("task123")`
- Ensure the status exists in the task's list

### Custom Fields Not Working

- Verify the custom field exists in the list
- Check field name contains "story point" or "point" (case-insensitive)
- Ensure the field type is "Number"

### Dependencies Not Creating

- Verify both tasks exist
- Check that tasks are in accessible lists
- Ensure dependency type is supported (`waiting_on` or `blocked_by`)

## API Reference

For detailed API documentation, see:
- [ClickUp API Documentation](https://clickup.com/api)
- [ClickUp API v2 Reference](https://clickup.com/api/clickupreference/operation/GetAuthorizedUser)

## Support

For issues or questions:
- Check the [spectra documentation](/guide)
- Review [ClickUp API docs](https://clickup.com/api)
- Open an issue on GitHub

