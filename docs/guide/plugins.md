# Plugin System

spectryn features an extensible plugin system that allows you to customize behavior, add new adapters, and integrate with external services.

## Overview

The plugin system supports:

- **Hooks** - Execute code at specific points in the sync lifecycle
- **Adapters** - Add support for new issue trackers (GitHub, Linear, etc.)
- **Parsers** - Add support for new document formats
- **Formatters** - Customize output formatting

## Hook System

Hooks allow you to execute custom code at specific points during sync operations.

### Available Hook Points

| Hook Point | Description | Context Data |
|------------|-------------|--------------|
| `BEFORE_SYNC` | Before sync starts | `epic_key`, `markdown_path` |
| `AFTER_SYNC` | After sync completes | `results`, `statistics` |
| `BEFORE_COMMAND` | Before each command | `command`, `issue_key` |
| `AFTER_COMMAND` | After each command | `command`, `result` |
| `ON_ERROR` | When an error occurs | `error`, `context` |
| `ON_VALIDATION` | During validation | `stories`, `errors` |

### Registering Hooks

```python
from spectryn.plugins import HookPoint, get_registry

hook_manager = get_registry().hook_manager

# Using decorator
@hook_manager.hook(HookPoint.BEFORE_SYNC)
def log_sync_start(ctx):
    print(f"Starting sync for epic: {ctx.data['epic_key']}")
    print(f"Markdown file: {ctx.data['markdown_path']}")

@hook_manager.hook(HookPoint.AFTER_COMMAND)
def notify_on_create(ctx):
    if ctx.command_type == "CreateSubtask":
        # Send Slack notification
        send_slack_message(f"Created: {ctx.result.issue_key}")

@hook_manager.hook(HookPoint.ON_ERROR)
def handle_errors(ctx):
    # Send to error tracking service
    sentry_sdk.capture_exception(ctx.error)
```

### Hook Context

Each hook receives a context object with relevant data:

```python
@hook_manager.hook(HookPoint.AFTER_SYNC)
def on_sync_complete(ctx):
    # Access sync results
    results = ctx.data['results']
    
    print(f"Stories processed: {results.stories_count}")
    print(f"Subtasks created: {results.subtasks_created}")
    print(f"Errors: {len(results.errors)}")
```

## Creating Custom Adapters

Add support for new issue trackers by implementing the `IssueTrackerPort` interface.

### Interface Definition

```python
from abc import ABC, abstractmethod
from spectryn.core.ports import IssueTrackerPort
from spectryn.core.domain import IssueData, SubtaskData, Status

class IssueTrackerPort(ABC):
    """Abstract interface for issue trackers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tracker name."""
        pass
    
    @abstractmethod
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """Get all issues under an epic."""
        pass
    
    @abstractmethod
    def get_issue(self, issue_key: str) -> IssueData:
        """Get a single issue by key."""
        pass
    
    @abstractmethod
    def update_description(self, issue_key: str, description: str) -> None:
        """Update an issue's description."""
        pass
    
    @abstractmethod
    def create_subtask(self, parent_key: str, subtask: SubtaskData) -> str:
        """Create a subtask under a parent issue."""
        pass
    
    @abstractmethod
    def transition_issue(self, issue_key: str, status: Status) -> None:
        """Transition an issue to a new status."""
        pass
```

### Example: GitHub Issues Adapter

```python
from github import Github
from spectryn.core.ports import IssueTrackerPort
from spectryn.core.domain import IssueData, Status

class GitHubIssuesAdapter(IssueTrackerPort):
    """GitHub Issues adapter for spectryn."""
    
    def __init__(self, token: str):
        self.client = Github(token)
    
    @property
    def name(self) -> str:
        return "GitHub Issues"
    
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        # epic_key format: "owner/repo#milestone_number"
        owner, repo_milestone = epic_key.split("/")
        repo_name, milestone_num = repo_milestone.split("#")
        
        repo = self.client.get_repo(f"{owner}/{repo_name}")
        milestone = repo.get_milestone(int(milestone_num))
        
        issues = repo.get_issues(milestone=milestone, state="all")
        
        return [
            IssueData(
                key=f"{owner}/{repo_name}#{issue.number}",
                title=issue.title,
                description=issue.body,
                status=self._map_state(issue.state),
            )
            for issue in issues
        ]
    
    def _map_state(self, state: str) -> Status:
        return Status.DONE if state == "closed" else Status.OPEN
    
    # ... implement other methods
```

### Registering Adapters

```python
from spectryn.plugins import get_registry

registry = get_registry()
registry.register_adapter("github", GitHubIssuesAdapter)

# Now usable via CLI or config
# spectryn --tracker github --markdown EPIC.md --epic owner/repo#1
```

## Custom Parsers

Add support for different input formats (YAML, Notion exports, etc.).

```python
from spectryn.core.ports import DocumentParserPort
from spectryn.core.domain import Epic, UserStory

class YAMLParser(DocumentParserPort):
    """Parse YAML-formatted epic documents."""
    
    def parse(self, content: str) -> Epic:
        data = yaml.safe_load(content)
        
        stories = [
            UserStory(
                id=story['id'],
                title=story['title'],
                description=story['description'],
                story_points=story.get('points', 0),
                status=Status(story.get('status', 'planned')),
            )
            for story in data.get('stories', [])
        ]
        
        return Epic(
            title=data['title'],
            stories=stories,
        )

# Register
registry.register_parser("yaml", YAMLParser)
```

## Plugin Discovery

spectryn can auto-discover plugins from:

1. **Entry points** - Installed packages with `spectryn.plugins` entry point
2. **Plugin directory** - `~/.spectryn/plugins/`
3. **Project plugins** - `.spectryn/plugins/` in project root

### Entry Point Registration

In your plugin's `pyproject.toml`:

```toml
[project.entry-points."spectryn.plugins"]
my_plugin = "my_package.plugin:register"
```

```python
# my_package/plugin.py
def register(registry):
    """Called by spectryn on startup."""
    registry.register_adapter("my-tracker", MyTrackerAdapter)
    registry.register_hook(HookPoint.BEFORE_SYNC, my_hook)
```

## Real-World Examples

### Slack Notifications

```python
from slack_sdk import WebClient
from spectryn.plugins import HookPoint, get_registry

slack = WebClient(token=os.environ["SLACK_TOKEN"])
channel = "#jira-sync"

@get_registry().hook_manager.hook(HookPoint.AFTER_SYNC)
def notify_slack(ctx):
    results = ctx.data['results']
    
    slack.chat_postMessage(
        channel=channel,
        text=f"✅ Synced {results.stories_count} stories to Jira",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Epic:* {ctx.data['epic_key']}\n"
                            f"*Stories:* {results.stories_count}\n"
                            f"*Subtasks created:* {results.subtasks_created}"
                }
            }
        ]
    )
```

### Audit Logging to Database

```python
from sqlalchemy import create_engine
from spectryn.plugins import HookPoint, get_registry

engine = create_engine(os.environ["DATABASE_URL"])

@get_registry().hook_manager.hook(HookPoint.AFTER_COMMAND)
def log_to_db(ctx):
    with engine.connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp, command, issue_key, result) VALUES (?, ?, ?, ?)",
            [datetime.now(), ctx.command_type, ctx.issue_key, ctx.result.success]
        )
```

### Custom Validation Rules

```python
@get_registry().hook_manager.hook(HookPoint.ON_VALIDATION)
def enforce_story_points(ctx):
    for story in ctx.data['stories']:
        if story.story_points > 13:
            ctx.add_error(
                f"Story {story.id} has {story.story_points} points. "
                "Maximum allowed is 13 (Fibonacci)."
            )
```

