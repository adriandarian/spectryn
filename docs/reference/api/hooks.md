# Hooks System

API reference for spectryn's plugin hooks system.

## Overview

The hooks system allows you to execute custom code at specific points during spectryn operations. This enables:

- Notifications (Slack, email, PagerDuty)
- Logging and auditing
- Custom validation rules
- Integration with other systems

## Hook Points

### Available Hooks

```python
from spectryn.plugins import HookPoint

class HookPoint(Enum):
    """Available hook points in the sync lifecycle."""
    
    # Sync lifecycle
    BEFORE_SYNC = "before_sync"      # Before sync starts
    AFTER_SYNC = "after_sync"        # After sync completes
    
    # Command lifecycle
    BEFORE_COMMAND = "before_command"  # Before each command
    AFTER_COMMAND = "after_command"    # After each command
    
    # Error handling
    ON_ERROR = "on_error"            # When an error occurs
    
    # Validation
    ON_VALIDATION = "on_validation"  # During markdown validation
    
    # Backup/Restore
    BEFORE_BACKUP = "before_backup"  # Before creating backup
    AFTER_BACKUP = "after_backup"    # After backup created
    BEFORE_RESTORE = "before_restore"  # Before restoring
    AFTER_RESTORE = "after_restore"    # After restore
```

### Hook Context

Each hook receives a context object with relevant data:

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class HookContext:
    """Context passed to hook handlers."""
    
    hook_point: HookPoint
    data: dict[str, Any]
    
    # Error context (only for ON_ERROR)
    error: Exception | None = None
    
    # Command context (only for command hooks)
    command_type: str | None = None
    issue_key: str | None = None
    result: CommandResult | None = None
    
    def add_error(self, message: str) -> None:
        """Add a validation error (for ON_VALIDATION)."""
        ...
```

## Registering Hooks

### Using Decorators

```python
from spectryn.plugins import HookPoint, get_registry

hook_manager = get_registry().hook_manager

@hook_manager.hook(HookPoint.BEFORE_SYNC)
def on_sync_start(ctx: HookContext):
    """Called before sync starts."""
    print(f"Starting sync for epic: {ctx.data['epic_key']}")
    print(f"Markdown file: {ctx.data['markdown_path']}")

@hook_manager.hook(HookPoint.AFTER_SYNC)
def on_sync_complete(ctx: HookContext):
    """Called after sync completes."""
    results = ctx.data['results']
    print(f"Synced {results.stories_count} stories")
```

### Programmatic Registration

```python
from spectryn.plugins import HookPoint, get_registry

def my_handler(ctx: HookContext):
    print(f"Hook triggered: {ctx.hook_point}")

hook_manager = get_registry().hook_manager
hook_manager.register(HookPoint.BEFORE_SYNC, my_handler)
```

### Priority

Hooks can have priority (lower numbers run first):

```python
@hook_manager.hook(HookPoint.BEFORE_SYNC, priority=10)
def high_priority_hook(ctx):
    """Runs before default priority hooks."""
    pass

@hook_manager.hook(HookPoint.BEFORE_SYNC, priority=100)
def low_priority_hook(ctx):
    """Runs after default priority hooks."""
    pass
```

## Hook Context Data

### BEFORE_SYNC / AFTER_SYNC

```python
@hook_manager.hook(HookPoint.BEFORE_SYNC)
def on_sync_start(ctx):
    epic_key = ctx.data['epic_key']        # "PROJ-123"
    markdown_path = ctx.data['markdown_path']  # "/path/to/EPIC.md"
    dry_run = ctx.data['dry_run']          # True/False
    phases = ctx.data['phases']            # ["descriptions", "subtasks", ...]

@hook_manager.hook(HookPoint.AFTER_SYNC)
def on_sync_complete(ctx):
    results = ctx.data['results']
    # results.stories_count: int
    # results.subtasks_created: int
    # results.subtasks_updated: int
    # results.descriptions_updated: int
    # results.errors: list[Error]
    # results.duration: timedelta
```

### BEFORE_COMMAND / AFTER_COMMAND

```python
@hook_manager.hook(HookPoint.BEFORE_COMMAND)
def before_cmd(ctx):
    cmd_type = ctx.command_type    # "CreateSubtask", "UpdateDescription", etc.
    issue_key = ctx.issue_key      # "PROJ-456"
    command = ctx.data['command']  # Command object

@hook_manager.hook(HookPoint.AFTER_COMMAND)
def after_cmd(ctx):
    result = ctx.result            # CommandResult
    # result.success: bool
    # result.message: str
    # result.issue_key: str | None
```

### ON_ERROR

```python
@hook_manager.hook(HookPoint.ON_ERROR)
def on_error(ctx):
    error = ctx.error              # Exception
    issue_key = ctx.issue_key      # Issue being processed (if any)
    command = ctx.data.get('command')  # Command that failed (if any)
```

### ON_VALIDATION

```python
@hook_manager.hook(HookPoint.ON_VALIDATION)
def validate(ctx):
    stories = ctx.data['stories']  # List of parsed stories
    
    for story in stories:
        if story.story_points > 13:
            ctx.add_error(
                f"Story {story.id} has {story.story_points} points. "
                "Max allowed is 13."
            )
```

## Real-World Examples

### Slack Notifications

```python
from slack_sdk import WebClient
from spectryn.plugins import HookPoint, get_registry

slack = WebClient(token=os.environ["SLACK_TOKEN"])
CHANNEL = "#jira-sync"

@get_registry().hook_manager.hook(HookPoint.AFTER_SYNC)
def notify_slack(ctx):
    results = ctx.data['results']
    epic_key = ctx.data['epic_key']
    
    if results.errors:
        emoji = "⚠️"
        color = "warning"
    else:
        emoji = "✅"
        color = "good"
    
    slack.chat_postMessage(
        channel=CHANNEL,
        attachments=[{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *Jira Sync Complete*\n"
                                f"Epic: `{epic_key}`\n"
                                f"Stories: {results.stories_count}\n"
                                f"Subtasks created: {results.subtasks_created}\n"
                                f"Errors: {len(results.errors)}"
                    }
                }
            ]
        }]
    )

@get_registry().hook_manager.hook(HookPoint.ON_ERROR)
def notify_error(ctx):
    slack.chat_postMessage(
        channel=CHANNEL,
        text=f"❌ Error in Jira sync: {ctx.error}"
    )
```

### Database Audit Log

```python
from sqlalchemy import create_engine, text
from spectryn.plugins import HookPoint, get_registry
from datetime import datetime

engine = create_engine(os.environ["DATABASE_URL"])

@get_registry().hook_manager.hook(HookPoint.AFTER_COMMAND)
def audit_log(ctx):
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO audit_log 
                (timestamp, epic_key, command_type, issue_key, success, message)
                VALUES (:ts, :epic, :cmd, :issue, :success, :msg)
            """),
            {
                "ts": datetime.now(),
                "epic": ctx.data.get('epic_key'),
                "cmd": ctx.command_type,
                "issue": ctx.issue_key,
                "success": ctx.result.success,
                "msg": ctx.result.message,
            }
        )
        conn.commit()
```

### PagerDuty Alerts

```python
import pdpyras
from spectryn.plugins import HookPoint, get_registry

pagerduty = pdpyras.EventsAPIV2Session(
    os.environ["PAGERDUTY_ROUTING_KEY"]
)

@get_registry().hook_manager.hook(HookPoint.ON_ERROR)
def alert_pagerduty(ctx):
    # Only alert on critical errors
    if isinstance(ctx.error, (AuthenticationError, ConnectionError)):
        pagerduty.trigger(
            summary=f"spectryn sync failed: {ctx.error}",
            severity="error",
            source="spectryn",
            custom_details={
                "epic_key": ctx.data.get('epic_key'),
                "command": ctx.command_type,
                "issue_key": ctx.issue_key,
            }
        )
```

### Custom Validation

```python
from spectryn.plugins import HookPoint, get_registry

@get_registry().hook_manager.hook(HookPoint.ON_VALIDATION)
def validate_story_points(ctx):
    """Enforce Fibonacci story points."""
    FIBONACCI = {1, 2, 3, 5, 8, 13}
    
    for story in ctx.data['stories']:
        if story.story_points not in FIBONACCI:
            ctx.add_error(
                f"Story {story.id}: {story.story_points} is not a valid "
                f"Fibonacci number. Use: {sorted(FIBONACCI)}"
            )

@get_registry().hook_manager.hook(HookPoint.ON_VALIDATION)
def validate_description_length(ctx):
    """Ensure descriptions aren't too short."""
    MIN_LENGTH = 50
    
    for story in ctx.data['stories']:
        desc_len = len(str(story.description))
        if desc_len < MIN_LENGTH:
            ctx.add_error(
                f"Story {story.id}: Description too short "
                f"({desc_len} chars, min {MIN_LENGTH})"
            )
```

## Unregistering Hooks

```python
# Unregister specific handler
hook_manager.unregister(HookPoint.BEFORE_SYNC, my_handler)

# Unregister all handlers for a hook point
hook_manager.clear(HookPoint.BEFORE_SYNC)

# Unregister all handlers
hook_manager.clear_all()
```

