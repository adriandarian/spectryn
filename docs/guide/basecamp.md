# Basecamp Integration Guide

spectryn supports Basecamp 3 for syncing markdown specifications. This guide covers OAuth setup, account and project configuration, and the Todo vs Message mapping strategy.

## Overview

The Basecamp adapter supports:
- ✅ Projects (epics), Todos and Messages (stories), and Todo items (subtasks)
- ✅ Status mapping via todo completion state
- ✅ Priority and story points (stored in notes)
- ✅ Comments sync
- ✅ Campfire (chat) integration
- ✅ Webhooks for real-time sync
- ✅ Message boards as alternative to todos

## Quick Start

```bash
# Install spectryn
pip install spectryn

# Sync markdown to Basecamp
spectryn --markdown EPIC.md --tracker basecamp --execute
```

## Configuration

### Config File (YAML)

Create `.spectryn.yaml`:

```yaml
# Basecamp connection settings
basecamp:
  access_token: your-basecamp-access-token
  account_id: "123456"  # Basecamp account ID
  project_id: "789012"  # Basecamp project ID
  api_url: https://3.basecampapi.com  # Optional: defaults to Basecamp 3 API
  use_messages_for_stories: false  # Optional: use Messages instead of Todos

# Sync settings
sync:
  execute: false  # Set to true for live mode
  verbose: true
```

### Config File (TOML)

Create `.spectryn.toml`:

```toml
[basecamp]
access_token = "your-basecamp-access-token"
account_id = "123456"
project_id = "789012"
api_url = "https://3.basecampapi.com"
use_messages_for_stories = false

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export BASECAMP_ACCESS_TOKEN=your-basecamp-access-token
export BASECAMP_ACCOUNT_ID=123456
export BASECAMP_PROJECT_ID=789012

# Optional
export BASECAMP_API_URL=https://3.basecampapi.com
export BASECAMP_USE_MESSAGES_FOR_STORIES=false
```

### CLI Arguments

```bash
spectryn \
  --markdown EPIC.md \
  --tracker basecamp \
  --basecamp-access-token your-token \
  --basecamp-account-id 123456 \
  --basecamp-project-id 789012 \
  --execute
```

## OAuth Setup

Basecamp 3 uses OAuth 2.0 for authentication. You'll need to create an OAuth application and obtain an access token.

### Step 1: Create OAuth Application

1. **Log in to Basecamp**
   - Go to [basecamp.com](https://basecamp.com)
   - Sign in to your account

2. **Navigate to Integrations**
   - Click on your account name (top right)
   - Go to **Settings** → **Integrations** → **OAuth Applications**
   - Or visit: `https://launchpad.37signals.com/integrations`

3. **Create New Application**
   - Click **"New application"** or **"Create a new application"**
   - Fill in the application details:
     - **Name**: `spectryn-sync` (or your preferred name)
     - **Description**: `CLI tool for syncing markdown specifications to Basecamp`
     - **Redirect URI**: `urn:ietf:wg:oauth:2.0:oob` (for CLI applications)
     - **Scopes**: Select the permissions you need:
       - ✅ **Read** - Read todos, messages, comments
       - ✅ **Write** - Create and update todos, messages, comments
       - ✅ **Admin** - Full access (if you need to manage projects)

4. **Save Application**
   - Click **"Save"** or **"Create application"**
   - You'll receive a **Client ID** and **Client Secret**

### Step 2: Obtain Access Token

There are two ways to get an access token:

#### Option A: Personal Access Token (Recommended for CLI)

1. **Go to Account Settings**
   - Navigate to your account settings
   - Go to **"My info"** → **"API tokens"** or visit:
     `https://3.basecampapi.com/YOUR_ACCOUNT_ID/people/me.json`

2. **Generate Token**
   - Click **"Create a new token"**
   - Give it a name: `spectryn-sync`
   - Select scopes (same as OAuth scopes)
   - Copy the token immediately (shown only once)

#### Option B: OAuth 2.0 Flow (For Applications)

If you're building an application that needs OAuth:

1. **Authorize Application**
   ```
   https://launchpad.37signals.com/authorization/new?
     type=web_server&
     client_id=YOUR_CLIENT_ID&
     redirect_uri=urn:ietf:wg:oauth:2.0:oob&
     response_type=code
   ```

2. **Get Authorization Code**
   - User authorizes the application
   - Copy the authorization code from the redirect

3. **Exchange for Access Token**
   ```bash
   curl -X POST https://launchpad.37signals.com/authorization/token \
     -H "Content-Type: application/json" \
     -d '{
       "type": "web_server",
       "client_id": "YOUR_CLIENT_ID",
       "client_secret": "YOUR_CLIENT_SECRET",
       "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
       "code": "AUTHORIZATION_CODE"
     }'
   ```

4. **Use Access Token**
   - The response contains an `access_token`
   - Use this token for API requests

### Step 3: Configure spectryn

Set the access token as an environment variable:

```bash
export BASECAMP_ACCESS_TOKEN=your-access-token-here
```

Or in your config file:

```yaml
basecamp:
  access_token: your-access-token-here
```

### Token Permissions

| Scope | Required For |
|-------|--------------|
| **Read** | Viewing todos, messages, comments |
| **Write** | Creating/updating todos, messages, comments |
| **Admin** | Managing projects, webhooks, Campfire |

::: warning Security
- Never commit tokens to version control
- Use environment variables or `.env` files (add to `.gitignore`)
- Rotate tokens regularly
- Use tokens with minimal required permissions
- Personal access tokens don't expire, but OAuth tokens may
:::

## Account and Project Configuration

### Finding Your Account ID

The account ID is the numeric identifier for your Basecamp account.

1. **Method 1: From API Response**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://3.basecampapi.com/people/me.json
   ```
   Look for `accounts` array - each account has an `id` field.

2. **Method 2: From Basecamp URL**
   - When viewing a project, check the URL
   - Format: `https://3.basecampapi.com/{ACCOUNT_ID}/projects/{PROJECT_ID}`
   - The first number is your account ID

3. **Method 3: From Basecamp Web Interface**
   - Go to your account settings
   - The account ID may be visible in the URL or API settings

### Finding Your Project ID

The project ID is the numeric identifier for a specific Basecamp project.

1. **Method 1: From Project URL**
   - Open your Basecamp project in a web browser
   - Check the URL: `https://3.basecampapi.com/{ACCOUNT_ID}/projects/{PROJECT_ID}`
   - The project ID is the number after `/projects/`

2. **Method 2: List Projects via API**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://3.basecampapi.com/{ACCOUNT_ID}/projects.json
   ```
   Each project in the response has an `id` field.

3. **Method 3: From Basecamp Web Interface**
   - Go to your project
   - Check the browser's developer tools → Network tab
   - Look for API requests - the project ID appears in URLs

### Configuration Example

```yaml
basecamp:
  access_token: ${BASECAMP_ACCESS_TOKEN}
  account_id: "123456"      # Your Basecamp account ID
  project_id: "789012"      # Your Basecamp project ID
  api_url: https://3.basecampapi.com
```

```bash
# Set environment variables
export BASECAMP_ACCESS_TOKEN=your-token
export BASECAMP_ACCOUNT_ID=123456
export BASECAMP_PROJECT_ID=789012
```

## Todo vs Message Mapping

Basecamp 3 offers two ways to represent stories: **Todos** and **Messages**. The adapter supports both, and you can choose which one fits your workflow.

### Todos (Default)

**Use Todos when:**
- ✅ You need task tracking with completion status
- ✅ You want assignees and due dates
- ✅ You need subtasks (todo items)
- ✅ You're managing a backlog or sprint

**Characteristics:**
- Can be marked as completed/not completed
- Support assignees and due dates
- Organized in Todo Sets (lists)
- Can have subtasks (todo items within a todo)

**Example:**
```markdown
### STORY-001: Implement Login Feature
**Status:** In Progress
**Story Points:** 5
**Assignee:** john@example.com
**Due Date:** 2024-12-31
```

Creates a todo in Basecamp that can be:
- Assigned to team members
- Marked as completed
- Given a due date
- Broken down into subtasks

### Messages

**Use Messages when:**
- ✅ You want discussion-focused content
- ✅ You need announcements or updates
- ✅ You're documenting decisions or proposals
- ✅ Completion status isn't important

**Characteristics:**
- Posted to Message Boards
- Organized by categories
- Better for discussions and documentation
- No completion status (always "Planned")

**Example:**
```markdown
### STORY-001: Design System Proposal
**Status:** Planned
**Story Points:** 3
```

Creates a message in Basecamp that:
- Appears in the project's message board
- Can be categorized
- Supports rich text content
- Encourages discussion via comments

### Configuration

Choose your mapping strategy:

```yaml
# Use Todos (default)
basecamp:
  use_messages_for_stories: false

# Use Messages
basecamp:
  use_messages_for_stories: true
```

### Mapping Summary

| spectryn Concept | Basecamp (Todos) | Basecamp (Messages) |
|----------------|------------------|---------------------|
| Epic | Project or Todo Set | Project or Message Board Category |
| Story | Todo | Message |
| Subtask | Todo Item (within todo) | Not supported |
| Status | Completed/Not Completed | Always "Planned" |
| Priority | Stored in notes | Stored in content |
| Story Points | Stored in notes | Stored in content |
| Assignee | Supported | Not supported |
| Due Date | Supported | Not supported |

### When to Use Each

**Choose Todos if:**
- You're managing a development backlog
- You need to track completion status
- Assignees and due dates are important
- You have subtasks to track

**Choose Messages if:**
- You're documenting decisions or proposals
- Discussion is more important than completion
- You want announcement-style updates
- You don't need task tracking

### Switching Between Modes

You can switch between modes, but note:
- Existing todos won't become messages (and vice versa)
- You may need to manually migrate content
- Consider your team's workflow before switching

## Status Mapping

Basecamp todos use a simple completion model. The adapter maps standard statuses:

| spectryn Status | Basecamp Todo Status |
|----------------|---------------------|
| Done, Completed, Closed, Resolved | ✅ Completed |
| Planned, To Do, Backlog | ⬜ Not Completed |
| In Progress, In Review | ⬜ Not Completed (status in notes) |
| Blocked, On Hold | ⬜ Not Completed (status in notes) |

**Note:** Messages don't have completion status - they're always "Planned".

## Priority and Story Points

Basecamp doesn't natively support priority or story points. The adapter stores these values in the **notes** field (for todos) or **content** field (for messages).

### Format

The adapter stores metadata in this format:

```markdown
**Priority:** High
**Story Points:** 5

Your description here...
```

### Extraction

When reading from Basecamp, the adapter extracts:
- Story points from patterns like: `Story Points: 5`, `SP: 5`, `Points: 5`
- Priority from patterns like: `Priority: High`

### Updating

When updating story points or priority:
- The adapter preserves existing notes/content
- Removes old priority/story points entries
- Adds new entries in the standard format

## Advanced Features

### Campfire (Chat) Integration

Basecamp includes Campfire for real-time chat. The adapter supports:

```python
# Get all Campfires
campfires = adapter.get_campfires()

# Send a message
adapter.send_campfire_message(
    chat_id="chat123",
    content="Story STORY-001 has been completed!"
)

# Get chat history
messages = adapter.get_campfire_messages(
    chat_id="chat123",
    since="2024-01-01T00:00:00Z",
    limit=50
)
```

**Use cases:**
- Automated notifications when stories are synced
- Status updates for team members
- Integration with CI/CD pipelines

### Webhooks

Set up webhooks to receive real-time updates:

```python
# Create webhook
webhook = adapter.create_webhook(
    url="https://your-server.com/webhook",
    events=["todo.created", "todo.updated", "message.created"],
    description="Spectra sync webhook"
)

# List webhooks
webhooks = adapter.list_webhooks()

# Delete webhook
adapter.delete_webhook(webhook_id="webhook123")
```

**Supported Events:**
- `todo.created`, `todo.updated`, `todo.completed`, `todo.uncompleted`
- `message.created`, `message.updated`
- `comment.created`, `comment.updated`
- `todo_list.created`, `todo_list.updated`

### Comments

Comments are synced bidirectionally:
- Comments added in Basecamp appear in markdown
- Comments in markdown are added to Basecamp todos/messages

### Rate Limiting

Basecamp API has a rate limit of **40 requests per 10 seconds**. The adapter:
- Automatically throttles requests
- Implements exponential backoff on rate limit errors
- Respects `Retry-After` headers

## Examples

### Basic Sync

```bash
# Dry run (preview changes)
spectryn --markdown EPIC.md --tracker basecamp

# Execute sync
spectryn --markdown EPIC.md --tracker basecamp --execute
```

### With Custom Configuration

```yaml
# .spectryn.yaml
basecamp:
  access_token: ${BASECAMP_ACCESS_TOKEN}
  account_id: "123456"
  project_id: "789012"
  use_messages_for_stories: false  # Use todos

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

#### Subtasks
- [ ] Design login form (STORY-001-T1)
- [ ] Implement authentication API (STORY-001-T2)
- [ ] Add error handling (STORY-001-T3)
```

## Troubleshooting

### Common Issues

#### "Authentication failed"
- Verify your access token is correct
- Check that the token hasn't expired (OAuth tokens)
- Ensure the token has the necessary scopes (Read, Write, Admin)
- Verify the token format (should start with a long string, no special prefix)

#### "Account not found"
- Verify the account ID is correct (numeric string)
- Check that you have access to the account
- Ensure the account ID matches the token's account

#### "Project not found"
- Verify the project ID is correct (numeric string)
- Check that the project exists in the specified account
- Ensure you have access to the project
- Verify the project ID is from Basecamp 3 (not Basecamp 2)

#### "Todo list not found"
- Ensure the project has at least one Todo Set
- Create a Todo Set in Basecamp if none exist
- Check that you're using the correct project ID

#### "Cannot create subtask for message"
- Subtasks are only supported for todos, not messages
- Switch to todo mode: `use_messages_for_stories: false`
- Or create the parent as a todo instead of a message

### Debug Mode

Enable verbose logging:

```bash
spectryn --markdown EPIC.md --tracker basecamp --verbose
```

Or set in config:

```yaml
sync:
  verbose: true
```

### Testing Connection

Test your configuration:

```python
from spectryn.adapters.basecamp import BasecampAdapter

adapter = BasecampAdapter(
    access_token="your-token",
    account_id="123456",
    project_id="789012",
    dry_run=True
)

# Test connection
if adapter.test_connection():
    print("✓ Connection successful")
    user = adapter.get_current_user()
    print(f"✓ Logged in as: {user.get('name')}")
else:
    print("✗ Connection failed")
```

## API Reference

### Endpoints Used

- `GET /people/me.json` - Get current user
- `GET /projects/{id}.json` - Get project
- `GET /projects/{id}/todosets.json` - Get todo lists
- `GET /projects/{id}/todosets/{id}/todos.json` - Get todos
- `GET /projects/{id}/todos/{id}.json` - Get todo
- `POST /projects/{id}/todosets/{id}/todos.json` - Create todo
- `PUT /projects/{id}/todos/{id}.json` - Update todo
- `GET /projects/{id}/messages.json` - Get messages
- `GET /projects/{id}/messages/{id}.json` - Get message
- `POST /projects/{id}/messages.json` - Create message
- `GET /projects/{id}/recordings/{id}/comments.json` - Get comments
- `POST /projects/{id}/recordings/{id}/comments.json` - Create comment
- `GET /projects/{id}/chats.json` - Get Campfires
- `POST /projects/{id}/chats/{id}/lines.json` - Send Campfire message
- `POST /projects/{id}/webhooks.json` - Create webhook

### Rate Limits

- **40 requests per 10 seconds** per account
- Adapter automatically throttles to stay under limit
- Retries with exponential backoff on 429 errors

## Best Practices

1. **Use Dry Run First**: Always test with `--execute` flag off first
2. **Choose the Right Mode**: Decide between Todos and Messages based on your workflow
3. **Backup Your Data**: Export your Basecamp project before bulk operations
4. **Incremental Syncs**: Sync frequently to avoid large changes
5. **Consistent Naming**: Use consistent story point and priority formats in notes
6. **Webhooks**: Set up webhooks for real-time sync if needed
7. **Campfire Notifications**: Use Campfire for team notifications about syncs

## See Also

- [Configuration Guide](./configuration.md) - General configuration options
- [Getting Started](./getting-started.md) - Quick start guide
- [Schema Reference](./schema.md) - Markdown schema details
- [Basecamp 3 API Documentation](https://github.com/basecamp/bc3-api) - Official API docs

