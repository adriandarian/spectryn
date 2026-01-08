# Architecture

spectryn follows a **Clean Architecture** / **Hexagonal Architecture** pattern for maximum flexibility and testability.

## Project Structure

```
src/spectryn/
├── core/                     # Pure domain logic (no external deps)
│   ├── domain/               # Entities, value objects, enums
│   │   ├── entities.py       # Epic, UserStory, Subtask, Comment
│   │   ├── value_objects.py  # StoryId, IssueKey, Description
│   │   ├── enums.py          # Status, Priority, IssueType
│   │   └── events.py         # Domain events for audit trail
│   └── ports/                # Abstract interfaces
│       ├── issue_tracker.py  # IssueTrackerPort interface
│       ├── document_parser.py
│       └── document_formatter.py
├── adapters/                 # Infrastructure implementations
│   ├── jira/                 # Jira API adapter
│   │   ├── adapter.py        # IssueTrackerPort implementation
│   │   └── client.py         # Low-level HTTP client
│   ├── parsers/              # Document parsers
│   │   └── markdown.py       # Markdown parser
│   ├── formatters/           # Output formatters
│   │   └── adf.py            # Atlassian Document Format
│   └── config/               # Configuration providers
│       └── environment.py    # Env vars / .env loader
├── application/              # Use cases / orchestration
│   ├── commands/             # Command pattern handlers
│   │   ├── base.py           # Command, CommandResult, CommandBatch
│   │   └── issue_commands.py # UpdateDescription, CreateSubtask, etc.
│   └── sync/                 # Sync orchestrator
│       └── orchestrator.py   # Main sync logic
├── cli/                      # Command line interface
│   ├── app.py                # Entry point, argument parsing
│   └── output.py             # Rich console output
└── plugins/                  # Extension system
    ├── base.py               # Plugin base classes
    ├── hooks.py              # Hook system for extensibility
    └── registry.py           # Plugin discovery and loading
```

## Key Patterns

### Ports & Adapters (Hexagonal Architecture)

The core domain logic depends only on abstract interfaces (ports), making it easy to swap implementations:

```
┌──────────────────────────────────────────────────────────────┐
│                        Application                            │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                     Core Domain                          │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │ │
│  │  │  Entities   │  │   Events    │  │   Enums     │      │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │ │
│  │                                                          │ │
│  │  ┌─────────────────────────────────────────────────┐    │ │
│  │  │                    Ports                         │    │ │
│  │  │  IssueTrackerPort  DocumentParserPort  ...      │    │ │
│  │  └─────────────────────────────────────────────────┘    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              ▲                                │
│                              │                                │
│  ┌───────────────────────────┼──────────────────────────────┐ │
│  │                    Adapters                              │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │ │
│  │  │  Jira   │  │Markdown │  │   ADF   │  │ Config  │     │ │
│  │  │ Adapter │  │ Parser  │  │Formatter│  │ Loader  │     │ │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Command Pattern

All write operations are encapsulated as commands, enabling undo/redo and audit trails:

```python
from spectryn.application.commands import Command, CommandResult

class UpdateDescriptionCommand(Command):
    """Command to update an issue's description."""
    
    def execute(self) -> CommandResult:
        # Store original for rollback
        self.original = self.tracker.get_issue(self.issue_key)
        
        # Execute the update
        self.tracker.update_description(self.issue_key, self.new_description)
        
        return CommandResult(success=True, message="Description updated")
    
    def undo(self) -> CommandResult:
        # Restore original description
        self.tracker.update_description(self.issue_key, self.original.description)
        return CommandResult(success=True, message="Description restored")
```

### Event-Driven Architecture

Domain events provide loose coupling and enable audit logging:

```python
from spectryn.core.domain.events import DomainEvent, EventBus

class IssueUpdatedEvent(DomainEvent):
    issue_key: str
    field: str
    old_value: str
    new_value: str

# Subscribe to events
@event_bus.subscribe(IssueUpdatedEvent)
def log_update(event: IssueUpdatedEvent):
    logger.info(f"Updated {event.issue_key}: {event.field}")
```

## Adding a New Tracker

To add support for a new issue tracker (e.g., GitHub Issues), implement the `IssueTrackerPort` interface:

```python
from spectryn.core.ports import IssueTrackerPort, IssueData

class GitHubAdapter(IssueTrackerPort):
    """GitHub Issues adapter."""
    
    @property
    def name(self) -> str:
        return "GitHub"
    
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        # Implement GitHub API calls to get issues
        repo_owner, repo_name = epic_key.split("/")
        # ... fetch issues from GitHub API
        return issues
    
    def update_description(self, issue_key: str, description: str) -> None:
        # Update issue body via GitHub API
        pass
    
    def create_subtask(self, parent_key: str, subtask: SubtaskData) -> str:
        # Create a new issue linked to parent
        pass
    
    def transition_issue(self, issue_key: str, status: Status) -> None:
        # Update issue state (open/closed)
        pass
```

Register the adapter:

```python
from spectryn.plugins import get_registry

registry = get_registry()
registry.register_adapter("github", GitHubAdapter)
```

## Using Hooks

Extend spectryn behavior without modifying core code:

```python
from spectryn.plugins import HookPoint, get_registry

hook_manager = get_registry().hook_manager

@hook_manager.hook(HookPoint.BEFORE_SYNC)
def log_sync_start(ctx):
    print(f"Starting sync for epic: {ctx.data['epic_key']}")

@hook_manager.hook(HookPoint.AFTER_COMMAND)
def notify_on_create(ctx):
    if ctx.command_type == "CreateSubtask":
        send_slack_notification(f"Created subtask: {ctx.result.issue_key}")

@hook_manager.hook(HookPoint.ON_ERROR)
def handle_errors(ctx):
    send_pagerduty_alert(ctx.error)
```

## Configuration Flow

```
┌─────────────────┐
│  CLI Arguments  │ ──┐
└─────────────────┘   │
                      │    ┌──────────────────┐
┌─────────────────┐   ├──▶ │ Config Provider  │ ──▶ Final Config
│ Env Variables   │ ──┤    │ (merges sources) │
└─────────────────┘   │    └──────────────────┘
                      │
┌─────────────────┐   │
│  Config Files   │ ──┘
└─────────────────┘
```

## Data Flow

```
┌────────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
│  Markdown  │ ──▶ │   Parser   │ ──▶ │   Domain   │ ──▶ │  Commands  │
│    File    │     │            │     │  Entities  │     │            │
└────────────┘     └────────────┘     └────────────┘     └────────────┘
                                                               │
                                                               ▼
┌────────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
│   Output   │ ◀── │   Events   │ ◀── │  Adapter   │ ◀── │ Orchestr-  │
│  Reporter  │     │            │     │  (Jira)    │     │   ator     │
└────────────┘     └────────────┘     └────────────┘     └────────────┘
```

## Testing Strategy

The architecture enables thorough testing at each layer:

| Layer | Test Type | Approach |
|-------|-----------|----------|
| Domain | Unit tests | Pure functions, no mocking needed |
| Ports | Interface tests | Verify contract compliance |
| Adapters | Integration tests | Mock external APIs |
| Commands | Unit tests | Mock port implementations |
| CLI | End-to-end tests | Test full command execution |

