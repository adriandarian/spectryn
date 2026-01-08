# Trello Integration Guide

spectryn supports Trello for syncing markdown specifications. This guide covers configuration, authentication, board setup, and advanced features.

## Overview

The Trello adapter supports:
- ✅ Boards, Lists (status), Cards (stories), and Checklists (subtasks)
- ✅ Status mapping via board lists
- ✅ Priority mapping via color-coded labels
- ✅ Story points via custom fields or card description
- ✅ Comments sync
- ✅ Webhooks for real-time sync
- ✅ Power-Ups integration (custom fields)
- ✅ Subtasks as checklist items or linked cards

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Trello
spectryn --markdown EPIC.md --tracker trello --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Trello connection settings
trello:
  api_key: your-trello-api-key
  api_token: your-trello-api-token
  board_id: "your-board-id"  # Board ID (alphanumeric)
  api_url: https://api.trello.com/1  # Optional: defaults to Trello API

  # Status list mapping (optional)
  # Maps status names to list names or IDs
  status_lists:
    "Planned": "To Do"
    "In Progress": "Doing"
    "Done": "Done"

  # Priority label mapping (optional)
  priority_labels:
    Critical: "red"
    High: "orange"
    Medium: "yellow"
    Low: "green"

  # Subtask mode: "checklist" (default) or "linked_card"
  subtask_mode: "checklist"

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[trello]
api_key = "your-trello-api-key"
api_token = "your-trello-api-token"
board_id = "your-board-id"
api_url = "https://api.trello.com/1"

[trello.status_lists]
Planned = "To Do"
"In Progress" = "Doing"
Done = "Done"

[trello.priority_labels]
Critical = "red"
High = "orange"
Medium = "yellow"
Low = "green"

[trello]
subtask_mode = "checklist"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export TRELLO_API_KEY=your-trello-api-key
export TRELLO_API_TOKEN=your-trello-api-token
export TRELLO_BOARD_ID=your-board-id

# Optional
export TRELLO_API_URL=https://api.trello.com/1
export TRELLO_SUBTASK_MODE=checklist  # or "linked_card"
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker trello \
  --trello-api-key your-key \
  --trello-api-token your-token \
  --trello-board-id your-board-id \
  --execute
```

## API Key/Token Setup

### Getting Your Trello API Key and Token

1. **Get API Key:**
   - Go to https://trello.com/app-key
   - Copy your API Key (you'll see it immediately)

2. **Generate API Token:**
   - Scroll down on the same page
   - Click "Token" link under "API Token"
   - Authorize the application
   - Copy the generated token

3. **Set Permissions:**
   - The token inherits permissions from your Trello account
   - Ensure you have read/write access to the boards you want to sync

### Security Best Practices

- **Never commit tokens to version control**
- Store tokens in environment variables or `.env` files (add `.env` to `.gitignore`)
- Use separate tokens for different environments (dev/staging/prod)
- Rotate tokens periodically

## Board and List Configuration

### Finding Your Board ID

1. Open your Trello board in a web browser
2. Look at the URL: `https://trello.com/b/BOARD_ID/board-name`
3. The `BOARD_ID` is the alphanumeric string after `/b/`

Example:
- URL: `https://trello.com/b/abc123xyz/my-project`
- Board ID: `abc123xyz`

### List Configuration

Trello uses **Lists** to represent workflow states (statuses). The adapter maps story statuses to list names.

#### Automatic List Detection

The adapter automatically detects lists on your board and maps statuses:

- **Exact match**: Status "To Do" → List "To Do"
- **Partial match**: Status "In Progress" → List "Doing" (if "progress" or "doing" appears in list name)
- **Smart mapping**: Common status aliases are mapped automatically:
  - "Planned", "Todo", "Backlog" → Lists with similar names
  - "In Progress", "Doing", "WIP" → Lists with similar names
  - "Done", "Complete", "Finished" → Lists with similar names

#### Manual List Mapping

For precise control, use `status_lists` configuration:

```yaml
trello:
  status_lists:
    "Planned": "Backlog"  # Map "Planned" status to "Backlog" list
    "In Progress": "Doing"
    "Done": "Done"
    "Blocked": "On Hold"
```

You can also use list IDs instead of names:

```yaml
trello:
  status_lists:
    "Planned": "5f8a1b2c3d4e5f6a7b8c9d0"  # List ID
```

### Creating Lists

If a status doesn't match any list, you can:

1. **Create the list manually** in Trello
2. **Use status_lists mapping** to map to an existing list
3. **Let the adapter create it** (if you have write permissions)

## Checklist vs Linked Cards for Subtasks

The Trello adapter supports two modes for subtasks:

### Checklist Mode (Default)

Subtasks are created as **checklist items** on the parent card.

**Pros:**
- Simple and lightweight
- Easy to check off
- No extra cards cluttering the board

**Cons:**
- Limited metadata (just name and checked status)
- Description stored as comment

**Configuration:**
```yaml
trello:
  subtask_mode: "checklist"
```

**Example:**
```markdown
### STORY-001: User Authentication

**Subtasks:**
- [ ] Set up OAuth provider
- [ ] Implement login flow
- [ ] Add password reset
```

Creates a checklist on the card with these items.

### Linked Card Mode

Subtasks are created as **separate cards** linked to the parent.

**Pros:**
- Full card features (description, labels, due dates, etc.)
- Can be moved between lists independently
- Better for complex subtasks

**Cons:**
- More cards on the board
- Slightly more complex structure

**Configuration:**
```yaml
trello:
  subtask_mode: "linked_card"
```

**Example:**
```markdown
### STORY-001: User Authentication

**Subtasks:**
- STORY-001-1: Set up OAuth provider
- STORY-001-2: Implement login flow
```

Creates separate cards linked to the parent card.

### Choosing the Right Mode

- **Use Checklist Mode** for:
  - Simple task lists
  - Quick check-offs
  - Minimal metadata needs

- **Use Linked Card Mode** for:
  - Complex subtasks with descriptions
  - Independent workflow tracking
  - Subtasks that need their own labels/assignees

## Advanced Features

### Priority Mapping

Priorities are mapped to **color-coded labels**:

```yaml
trello:
  priority_labels:
    Critical: "red"
    High: "orange"
    Medium: "yellow"
    Low: "green"
```

The adapter:
1. Looks for existing labels with matching colors
2. Creates labels if they don't exist
3. Applies labels to cards based on priority

### Story Points

Story points can be stored in two ways:

#### Option 1: Card Description (Default)

Story points are added to the card description:

```markdown
**Story Points:** 5

Card description here...
```

#### Option 2: Custom Fields (Power-Up)

If you have the "Custom Fields" Power-Up installed:

```python
# Get custom field definitions
custom_fields = adapter.get_board_custom_field_definitions()

# Find story points field
story_points_field = next(
    (f for f in custom_fields if f["name"].lower() == "story points"),
    None
)

# Set story points
if story_points_field:
    adapter.set_custom_field(
        card_id="card123",
        custom_field_id=story_points_field["id"],
        value=5
    )
```

### Webhooks for Real-Time Sync

Set up webhooks to receive real-time updates:

```python
# Create webhook for board
webhook = adapter.create_webhook(
    callback_url="https://your-server.com/webhook",
    description="Spectra sync webhook"
)

# List webhooks
webhooks = adapter.list_webhooks()

# Get webhook details
webhook_details = adapter.get_webhook(webhook_id="webhook123")

# Update webhook
adapter.update_webhook(
    webhook_id="webhook123",
    active=False  # Disable webhook
)

# Delete webhook
adapter.delete_webhook(webhook_id="webhook123")
```

**Webhook Events:**
Trello sends webhooks when:
- Cards are created, updated, or deleted
- Cards move between lists
- Comments are added
- Checklists are modified
- Labels are added/removed

### Power-Ups Integration

#### List Installed Power-Ups

```python
power_ups = adapter.get_installed_power_ups()
for power_up in power_ups:
    print(f"{power_up['name']}: {power_up['id']}")
```

#### Working with Custom Fields

```python
# Get all custom field definitions
custom_fields = adapter.get_board_custom_field_definitions()

# Get custom field values for a card
values = adapter.get_custom_fields(card_id="card123")

# Set a custom field value
adapter.set_custom_field(
    card_id="card123",
    custom_field_id="field_id_here",
    value=5  # Number, string, bool, or list
)

# Get a custom field value by name
story_points = adapter.get_custom_field_value(
    card_id="card123",
    custom_field_name="Story Points"
)
```

**Supported Custom Field Types:**
- **Number**: `value=5` or `value=5.5`
- **Text**: `value="High priority"`
- **Checkbox**: `value=True` or `value=False`
- **Date**: `value="2024-12-31"`
- **List**: `value=["option1", "option2"]`

### Comments Sync

Comments are automatically synced:

```python
# Add a comment
adapter.add_comment(
    issue_key="card123",
    body="This is a comment"
)

# Get comments
comments = adapter.get_issue_comments("card123")
```

## Troubleshooting

### Common Issues

**Issue: "Board not found"**
- Verify `board_id` is correct (alphanumeric ID from URL)
- Check API token has access to the board
- Ensure board exists and is accessible

**Issue: "List not found for status: X"**
- Check list names match your status names
- Use `status_lists` mapping to map statuses to lists
- Create the list manually in Trello if needed

**Issue: "Rate limit exceeded"**
- Trello limits: 300 requests per 10 seconds
- The adapter handles rate limiting automatically (25 req/s)
- Reduce sync frequency if hitting limits

**Issue: "Authentication failed"**
- Verify API key and token are correct
- Check token hasn't expired
- Ensure token has appropriate permissions

**Issue: "Custom field not found"**
- Verify Power-Up is installed on the board
- Check custom field name matches exactly (case-insensitive)
- Use `get_board_custom_field_definitions()` to list available fields

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker trello --verbose
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
spectryn --markdown EPIC.md --tracker trello --validate
```

## Examples

### Basic Sync

```bash
# Dry-run (preview changes)
spectryn --markdown EPIC.md --tracker trello

# Execute sync
spectryn --markdown EPIC.md --tracker trello --execute
```

### With Custom Configuration

```yaml
# .spectryn.yaml
trello:
  api_key: ${TRELLO_API_KEY}
  api_token: ${TRELLO_API_TOKEN}
  board_id: "my-project-board"

  status_lists:
    "Planned": "Backlog"
    "In Progress": "In Development"
    "Done": "Completed"

  priority_labels:
    Critical: "red"
    High: "orange"
    Medium: "yellow"
    Low: "green"

  subtask_mode: "linked_card"

sync:
  execute: true
  verbose: true
```

### Using Custom Fields for Story Points

```python
from spectryn.adapters.trello import TrelloAdapter
from spectryn.core.ports.config_provider import TrelloConfig

config = TrelloConfig(
    api_key="your-key",
    api_token="your-token",
    board_id="your-board-id"
)

adapter = TrelloAdapter(config=config, dry_run=False)

# Get custom field definitions
custom_fields = adapter.get_board_custom_field_definitions()
story_points_field = next(
    (f for f in custom_fields if "story points" in f["name"].lower()),
    None
)

if story_points_field:
    # Set story points on a card
    adapter.set_custom_field(
        card_id="card123",
        custom_field_id=story_points_field["id"],
        value=8
    )
```

### Webhook Setup

```python
# Create webhook
webhook = adapter.create_webhook(
    callback_url="https://your-server.com/trello-webhook",
    description="Automated sync webhook"
)

print(f"Webhook created: {webhook['id']}")

# Later, check webhook status
webhooks = adapter.list_webhooks()
for wh in webhooks:
    print(f"{wh['id']}: {wh['callbackURL']} - Active: {wh.get('active', True)}")
```

## Best Practices

1. **Use Status Lists Mapping**: Explicitly map statuses to lists for predictable behavior
2. **Choose Subtask Mode Wisely**: Use checklists for simple tasks, linked cards for complex ones
3. **Leverage Labels**: Use color-coded labels for priorities and categories
4. **Custom Fields**: Install Power-Ups for advanced metadata (story points, estimates, etc.)
5. **Webhooks**: Set up webhooks for real-time bidirectional sync
6. **Rate Limiting**: The adapter handles rate limiting automatically, but be mindful of sync frequency

## Limitations

- **Card Attachments**: Not yet supported (future enhancement)
- **Due Dates**: Supported via API but not yet mapped in adapter (future enhancement)
- **Card Members**: Assignee support is limited (Trello API doesn't expose in basic card data)
- **Power-Ups**: Only custom fields Power-Up is fully supported; other Power-Ups may require custom integration

## See Also

- [Configuration Guide](../guide/configuration.md) - General configuration options
- [Getting Started](../guide/getting-started.md) - Basic usage guide
- [Trello API Documentation](https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/) - Official Trello API docs

