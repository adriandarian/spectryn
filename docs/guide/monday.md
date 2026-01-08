# Monday.com Integration Guide

spectryn supports Monday.com for syncing markdown specifications. This guide covers configuration, authentication, board setup, and column mapping.

## Overview

The Monday.com adapter supports:
- ✅ Boards, Groups (epics), Items (stories), and Subitems (subtasks)
- ✅ Status, Priority, and Story Points columns
- ✅ Timeline/Gantt view integration
- ✅ File attachments
- ✅ Updates (comments) sync
- ✅ Webhooks for real-time sync
- ✅ Custom column mapping

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Monday.com
spectryn --markdown EPIC.md --tracker monday --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Monday.com connection settings
monday:
  api_token: your-monday-api-token-v2
  board_id: "123456789"  # Board ID (numeric)
  workspace_id: "987654321"  # Optional: Workspace ID
  api_url: https://api.monday.com/v2  # Optional: defaults to production API

  # Column mapping (optional - auto-detected if not specified)
  status_column_id: "status"  # Status column ID
  priority_column_id: "priority"  # Priority column ID
  story_points_column_id: "numbers"  # Story points column ID

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[monday]
api_token = "your-monday-api-token-v2"
board_id = "123456789"
workspace_id = "987654321"
api_url = "https://api.monday.com/v2"

[monday.column_mapping]
status_column_id = "status"
priority_column_id = "priority"
story_points_column_id = "numbers"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export MONDAY_API_TOKEN=your-monday-api-token-v2
export MONDAY_BOARD_ID=123456789

# Optional
export MONDAY_WORKSPACE_ID=987654321
export MONDAY_API_URL=https://api.monday.com/v2
export MONDAY_STATUS_COLUMN_ID=status
export MONDAY_PRIORITY_COLUMN_ID=priority
export MONDAY_STORY_POINTS_COLUMN_ID=numbers
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker monday \
  --monday-api-token your-token \
  --monday-board-id 123456789 \
  --execute
```

## API Token Setup

### Getting Your Monday.com API Token (v2)

1. **Navigate to Monday.com Developer Settings**
   - Go to [Monday.com](https://monday.com)
   - Click your profile icon → **Admin** → **API**
   - Or go directly to: [https://monday.com/monday-api](https://monday.com/monday-api)

2. **Create API Token**
   - Click **"Generate new token"** or **"Create token"**
   - Give it a descriptive name (e.g., "spectryn CLI")
   - Select the appropriate scope:
     - **Read** - View boards, items, columns
     - **Write** - Create and update items, columns
     - **Full access** - Complete access (recommended for spectryn)

3. **Copy Token**
   - Copy the token immediately (shown only once)
   - Format: Long alphanumeric string (e.g., `eyJhbGciOiJIUzI1NiJ9...`)

4. **Configure spectryn**
   ```bash
   export MONDAY_API_TOKEN=your-token-here
   ```

::: warning Security
- Never commit tokens to version control
- Use environment variables or `.env` files (add to `.gitignore`)
- Rotate tokens regularly
- Use tokens with minimal required permissions
:::

### Token Permissions

| Permission | Required For |
|------------|--------------|
| **Read** | View boards, items, columns |
| **Write** | Create/update items, columns, comments |
| **Full access** | All operations (recommended) |

### Testing Your Token

Test your token with a simple API call:

```bash
curl -H "Authorization: YOUR_TOKEN" \
  https://api.monday.com/v2 \
  -H "Content-Type: application/json" \
  -d '{"query": "{ me { id name email } }"}'
```

You should receive a response with your user information.

## Board and Column Configuration

### Finding Your Board ID

1. **Open your board in Monday.com**
2. **Check the URL**
   - Format: `https://monday.com/boards/123456789`
   - The number after `/boards/` is your board ID
3. **Or use the API**
   ```bash
   curl -H "Authorization: YOUR_TOKEN" \
     https://api.monday.com/v2 \
     -H "Content-Type: application/json" \
     -d '{"query": "{ boards { id name } }"}'
   ```

### Finding Your Workspace ID (Optional)

Workspace ID is optional but useful for organization:

1. **Check the URL**
   - Format: `https://monday.com/workspaces/987654321`
   - The number after `/workspaces/` is your workspace ID
2. **Or use the API**
   ```bash
   curl -H "Authorization: YOUR_TOKEN" \
     https://api.monday.com/v2 \
     -H "Content-Type: application/json" \
     -d '{"query": "{ workspaces { id name } }"}'
   ```

### Understanding Monday.com Structure

Monday.com uses a hierarchical structure:

```
Workspace
  └── Board
      └── Group (Epic)
          └── Item (Story)
              └── Subitem (Subtask)
```

**Mapping to spectryn:**
- **Epic** → Group (column/group within a board)
- **Story** → Item (row/item on the board)
- **Subtask** → Subitem (child item linked to parent)
- **Status** → Status column
- **Priority** → Priority column
- **Story Points** → Numbers column

### Required Columns

For full spectryn functionality, your board should have these columns:

| Column Type | Column Name | Purpose |
|-------------|-------------|---------|
| **Status** | `Status` | Track story status (Planned, In Progress, Done) |
| **Priority** | `Priority` | Set story priority (Critical, High, Medium, Low) |
| **Numbers** | `Story Points` | Estimate story complexity |
| **Timeline** (optional) | `Timeline` | Gantt view for start/end dates |

### Creating Columns

If your board doesn't have the required columns:

1. **Open your board**
2. **Click the "+" button** to add a column
3. **Select column type:**
   - **Status** - For status tracking
   - **Priority** - For priority levels
   - **Numbers** - For story points
   - **Timeline** - For Gantt view (optional)

4. **Name the column:**
   - Status column: `Status`
   - Priority column: `Priority`
   - Story points column: `Story Points`
   - Timeline column: `Timeline`

## Custom Column Mapping Guide

spectryn automatically detects columns by type and name, but you can specify custom mappings if your board uses different column names.

### Auto-Detection

By default, spectryn automatically finds columns by:
1. **Type match** - Finds columns by type (status, priority, numbers, timeline)
2. **Name match** - If multiple columns of same type, matches by name hints

### Manual Column Mapping

If your board uses custom column names, specify them explicitly:

#### Using Config File

```yaml
monday:
  api_token: your-token
  board_id: "123456789"

  # Custom column IDs (get from board settings)
  status_column_id: "status_col_abc123"
  priority_column_id: "priority_col_xyz789"
  story_points_column_id: "numbers_col_def456"
```

#### Using Environment Variables

```bash
export MONDAY_STATUS_COLUMN_ID=status_col_abc123
export MONDAY_PRIORITY_COLUMN_ID=priority_col_xyz789
export MONDAY_STORY_POINTS_COLUMN_ID=numbers_col_def456
```

### Finding Column IDs

To find your column IDs:

1. **Use the API**
   ```bash
   curl -H "Authorization: YOUR_TOKEN" \
     https://api.monday.com/v2 \
     -H "Content-Type: application/json" \
     -d '{"query": "{ boards(ids: [123456789]) { columns { id title type } } }"}'
   ```

2. **Response example:**
   ```json
   {
     "data": {
       "boards": [{
         "columns": [
           {"id": "status", "title": "Status", "type": "status"},
           {"id": "priority", "title": "Priority", "type": "priority"},
           {"id": "numbers", "title": "Story Points", "type": "numbers"}
         ]
       }]
     }
   }
   ```

3. **Use the `id` field** from the response

### Column Type Reference

| Column Type | Monday.com Type | Use Case |
|-------------|----------------|----------|
| **Status** | `status` | Workflow states (Not Started, In Progress, Done) |
| **Priority** | `priority` | Priority levels (Critical, High, Medium, Low) |
| **Story Points** | `numbers` | Numeric estimates (1, 2, 3, 5, 8, 13) |
| **Timeline** | `timeline` | Start/end dates for Gantt view |
| **Date** | `date` | Individual start/end dates (alternative to timeline) |

### Status Column Configuration

Status columns need specific labels. Configure them in Monday.com:

1. **Open column settings**
2. **Add status labels:**
   - Not Started
   - Working on it
   - Done
   - (Add more as needed)

3. **spectryn will map:**
   - `Planned` → "Not Started"
   - `In Progress` → "Working on it"
   - `Done` → "Done"

### Priority Column Configuration

Priority columns use index-based values:

| Priority | Index | Label |
|----------|-------|-------|
| Critical | 0 | Critical |
| High | 1 | High |
| Medium | 2 | Medium |
| Low | 3 | Low |

spectryn automatically maps priority values to the correct index.

### Story Points Column Configuration

Story Points use a Numbers column:

- Accepts numeric values (integers or decimals)
- Common values: 1, 2, 3, 5, 8, 13 (Fibonacci)
- Can use any numeric scale

## Advanced Features

### Timeline/Gantt View Integration

Set start and end dates for items to enable Gantt view:

```python
from spectryn.adapters.monday import MondayAdapter

adapter = MondayAdapter(
    api_token="your-token",
    board_id="123456789",
)

# Set timeline dates
adapter.set_timeline_dates(
    issue_key="item-123",
    start_date="2025-01-01",
    end_date="2025-01-31"
)

# Get timeline dates
dates = adapter.get_timeline_dates("item-123")
# Returns: {"start_date": "2025-01-01", "end_date": "2025-01-31"}
```

### File Attachments

Upload files to items:

```python
# Upload file
result = adapter.upload_file(
    issue_key="item-123",
    file_path="./attachments/design.png"
)

# Get all files for an item
files = adapter.get_item_files("item-123")
```

### Webhooks for Real-Time Sync

Set up webhooks to receive real-time updates:

```python
# Create webhook
webhook = adapter.create_webhook(
    url="https://your-server.com/webhook",
    event="change_column_value"  # or "create_item", "create_update", etc.
)

# List webhooks
webhooks = adapter.list_webhooks()

# Delete webhook
adapter.delete_webhook(webhook_id="webhook-123")
```

**Supported Events:**
- `change_column_value` - When column values change (default)
- `create_item` - When new items are created
- `create_update` - When updates/comments are created
- `change_status` - When status changes
- `change_name` - When item names change
- `create_subitem` - When subitems are created

## Troubleshooting

### Common Issues

**Issue: "Board not found"**
- Verify `board_id` is correct (numeric ID from URL)
- Check token has access to the board
- Ensure board exists and is accessible

**Issue: "Status column not found"**
- Add a Status column to your board
- Or specify `status_column_id` in config
- Check column type is `status`

**Issue: "Column value update failed"**
- Verify column ID is correct
- Check column type matches the value type
- Ensure token has write permissions

**Issue: "Rate limit exceeded"**
- Monday.com limits: 500 requests per 10 seconds
- The adapter handles rate limiting automatically
- Reduce sync frequency if hitting limits

**Issue: "Authentication failed"**
- Verify token is valid and not expired
- Check token has appropriate permissions
- Ensure token format is correct (v2 API token)

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker monday --verbose
```

Or in config:

```yaml
sync:
  verbose: true
```

### Testing Connection

Test your configuration:

```bash
# Test connection (dry-run)
spectryn --markdown EPIC.md --tracker monday --validate
```

## Examples

### Basic Sync

```bash
# Dry-run (preview changes)
spectryn --markdown EPIC.md --tracker monday

# Execute sync
spectryn --markdown EPIC.md --tracker monday --execute
```

### With Custom Column Mapping

```yaml
monday:
  api_token: your-token
  board_id: "123456789"
  status_column_id: "custom_status_col"
  priority_column_id: "custom_priority_col"
  story_points_column_id: "custom_points_col"
```

### With Timeline Support

```python
from spectryn.adapters.monday import MondayAdapter

adapter = MondayAdapter(
    api_token="your-token",
    board_id="123456789",
)

# Set timeline for Gantt view
adapter.set_timeline_dates(
    issue_key="item-123",
    start_date="2025-01-01",
    end_date="2025-01-31"
)
```

## Reference

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_token` | string | Required | Monday.com API token (v2) |
| `board_id` | string | Required | Board ID (numeric) |
| `workspace_id` | string | `null` | Workspace ID (optional) |
| `api_url` | string | `https://api.monday.com/v2` | API endpoint |
| `status_column_id` | string | Auto-detected | Status column ID |
| `priority_column_id` | string | Auto-detected | Priority column ID |
| `story_points_column_id` | string | Auto-detected | Story points column ID |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `MONDAY_API_TOKEN` | API token (v2) |
| `MONDAY_BOARD_ID` | Board ID |
| `MONDAY_WORKSPACE_ID` | Workspace ID (optional) |
| `MONDAY_API_URL` | API endpoint (optional) |
| `MONDAY_STATUS_COLUMN_ID` | Status column ID (optional) |
| `MONDAY_PRIORITY_COLUMN_ID` | Priority column ID (optional) |
| `MONDAY_STORY_POINTS_COLUMN_ID` | Story points column ID (optional) |

### Column Mapping

| Spectra Field | Monday.com Column Type | Default Column Name |
|---------------|----------------------|---------------------|
| Status | `status` | Status |
| Priority | `priority` | Priority |
| Story Points | `numbers` | Story Points |
| Timeline | `timeline` | Timeline |
| Start Date | `date` | Start Date |
| End Date | `date` | End Date |

## Next Steps

- [Configuration Guide](/guide/configuration) - Full configuration reference
- [Schema Reference](/guide/schema) - Markdown format guide
- [Quick Start](/guide/quick-start) - Your first sync

