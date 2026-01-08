# YouTrack Integration

Spectra supports syncing user stories to JetBrains YouTrack issue tracker.

## Overview

The YouTrack adapter maps Spectra's domain model to YouTrack's issue tracking system:

- **Epic** → Epic issue type
- **Story** → Task or User Story issue type
- **Subtask** → Subtask issue type
- **Status** → State field
- **Priority** → Priority field
- **Story Points** → Custom field (configurable)

## Configuration

### Environment Variables

Set the following environment variables:

```bash
export YOUTRACK_URL="https://youtrack.example.com"
export YOUTRACK_TOKEN="your-permanent-token"
export YOUTRACK_PROJECT_ID="PROJ"
```

### Configuration Options

The `YouTrackConfig` dataclass supports the following options:

- `url` (required): YouTrack instance URL (e.g., `https://youtrack.example.com`)
- `token` (required): Permanent Token for authentication
- `project_id` (required): Project ID in YouTrack
- `api_url` (optional): API URL override (defaults to `{url}/api`)
- `epic_type` (optional): Epic issue type name (default: `"Epic"`)
- `story_type` (optional): Story issue type name (default: `"Task"`)
- `subtask_type` (optional): Subtask issue type name (default: `"Subtask"`)
- `story_points_field` (optional): Custom field ID for story points
- `status_field` (optional): Field name for status/state (default: `"State"`)
- `priority_field` (optional): Field name for priority (default: `"Priority"`)

## Authentication

YouTrack uses Permanent Tokens for authentication. To create a token:

1. Log in to your YouTrack instance
2. Go to **Settings** → **User** → **Tokens**
3. Click **Generate new token**
4. Copy the token and use it in the `YOUTRACK_TOKEN` environment variable

**Note**: Tokens have the same permissions as your user account. Ensure your account has the necessary permissions to create and update issues in the target project.

## Usage

### Basic Sync

```bash
spectryn sync --tracker youtrack --markdown EPIC.md
```

### With Custom Configuration

```python
from spectryn.core.ports.config_provider import YouTrackConfig
from spectryn.adapters.youtrack import YouTrackAdapter

config = YouTrackConfig(
    url="https://youtrack.example.com",
    token="your-token",
    project_id="PROJ",
    story_points_field="Story Points",
)

adapter = YouTrackAdapter(config=config, dry_run=False)
```

## Issue Type Mapping

YouTrack supports various issue types. The adapter maps:

- **Epic** → `Epic` (configurable via `epic_type`)
- **Story** → `Task` or `User Story` (configurable via `story_type`)
- **Subtask** → `Subtask` (configurable via `subtask_type`)

## Status Mapping

YouTrack uses a `State` field (or custom field name) for workflow states. The adapter maps common status values:

- `Planned` / `Backlog` → `Open` or `Planned`
- `In Progress` → `In Progress`
- `In Review` → `In Review` or `Testing`
- `Done` → `Done` or `Resolved`
- `Cancelled` → `Cancelled` or `Won't Fix`

The adapter automatically discovers available states from your YouTrack project and maps statuses accordingly.

## Priority Mapping

YouTrack priorities are mapped as follows:

- `Critical` → `Critical` or `Blocker`
- `High` → `High` or `Major`
- `Medium` → `Medium` or `Normal`
- `Low` → `Low` or `Minor`

The adapter discovers available priorities from your YouTrack instance and maps accordingly.

## Story Points

Story points can be stored in a custom field. Configure the field ID:

```python
config = YouTrackConfig(
    url="https://youtrack.example.com",
    token="your-token",
    project_id="PROJ",
    story_points_field="Story Points",  # Custom field name or ID
)
```

If `story_points_field` is not configured, story points will not be synced.

## Custom Fields

YouTrack supports custom fields. To use custom fields:

1. Identify the custom field ID or name in your YouTrack project
2. Configure it in `YouTrackConfig` (e.g., `story_points_field`)
3. The adapter will use it when creating/updating issues

## API Rate Limiting

YouTrack instances may have rate limiting. The adapter includes:

- Automatic retry with exponential backoff
- Connection pooling for performance
- Configurable timeout settings

Rate limits vary by instance (cloud vs. self-hosted). The adapter uses conservative defaults (10 requests/second) but can be adjusted if needed.

## Cloud vs. Self-Hosted

The adapter supports both YouTrack Cloud and self-hosted instances:

- **Cloud**: Use `https://your-company.myjetbrains.com/youtrack`
- **Self-hosted**: Use your instance URL (e.g., `https://youtrack.example.com`)

The API URL is automatically constructed as `{url}/api` unless overridden.

## Limitations

- **Delete Links**: The YouTrack API doesn't provide a direct endpoint to delete links. This feature is not yet implemented.
- **Custom Fields**: Complex custom field types may require additional configuration.
- **Workflows**: Custom workflows with non-standard state names may need manual mapping.

## Troubleshooting

### Authentication Errors

If you see authentication errors:

1. Verify your token is valid and not expired
2. Check that the token has permissions for the target project
3. Ensure the URL is correct (include protocol: `https://`)

### State Mapping Issues

If status transitions fail:

1. Check available states in your project: `GET /api/admin/projects/{project_id}/customFields/State`
2. Verify state names match your workflow
3. Consider configuring custom state mappings

### Custom Field Issues

If custom fields aren't updating:

1. Verify the field ID/name is correct
2. Check field permissions
3. Ensure the field type is supported (text, number, etc.)

## Examples

### Sync Epic with Stories

```bash
# Set environment variables
export YOUTRACK_URL="https://youtrack.example.com"
export YOUTRACK_TOKEN="your-token"
export YOUTRACK_PROJECT_ID="PROJ"

# Sync epic
spectryn sync --tracker youtrack --markdown EPIC.md
```

### Create Subtask

```python
from spectryn.core.ports.config_provider import YouTrackConfig
from spectryn.adapters.youtrack import YouTrackAdapter

config = YouTrackConfig(
    url="https://youtrack.example.com",
    token="your-token",
    project_id="PROJ",
)

adapter = YouTrackAdapter(config=config, dry_run=False)

# Create subtask
subtask_id = adapter.create_subtask(
    parent_key="PROJ-123",
    summary="Implement feature X",
    description="Detailed description...",
    project_key="PROJ",
    story_points=5,
    priority="High",
)
```

## References

- [YouTrack REST API Documentation](https://www.jetbrains.com/help/youtrack/server/rest-api.html)
- [YouTrack Query Language (YQL)](https://www.jetbrains.com/help/youtrack/server/yql.html)
- [YouTrack Custom Fields](https://www.jetbrains.com/help/youtrack/server/custom-fields.html)

