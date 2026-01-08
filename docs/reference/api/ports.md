# Ports & Adapters

API reference for spectryn's port interfaces and adapter implementations.

## Ports (Interfaces)

Ports define abstract interfaces that adapters must implement. This enables swapping implementations without changing core logic.

### IssueTrackerPort

Interface for issue tracker integrations.

```python
from abc import ABC, abstractmethod
from spectryn.core.domain import IssueData, SubtaskData, Status

class IssueTrackerPort(ABC):
    """Abstract interface for issue trackers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tracker name (e.g., 'Jira', 'GitHub')."""
        pass
    
    @abstractmethod
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        """
        Get all issues under an epic.
        
        Args:
            epic_key: The epic identifier
            
        Returns:
            List of issues linked to the epic
        """
        pass
    
    @abstractmethod
    def get_issue(self, issue_key: str) -> IssueData:
        """
        Get a single issue by key.
        
        Args:
            issue_key: The issue identifier
            
        Returns:
            Issue data
            
        Raises:
            IssueNotFoundError: If issue doesn't exist
        """
        pass
    
    @abstractmethod
    def update_description(
        self, 
        issue_key: str, 
        description: str
    ) -> None:
        """
        Update an issue's description.
        
        Args:
            issue_key: The issue identifier
            description: New description content
        """
        pass
    
    @abstractmethod
    def create_subtask(
        self, 
        parent_key: str, 
        subtask: SubtaskData
    ) -> str:
        """
        Create a subtask under a parent issue.
        
        Args:
            parent_key: Parent issue identifier
            subtask: Subtask data
            
        Returns:
            Created subtask key
        """
        pass
    
    @abstractmethod
    def transition_issue(
        self, 
        issue_key: str, 
        status: Status
    ) -> None:
        """
        Transition an issue to a new status.
        
        Args:
            issue_key: The issue identifier
            status: Target status
        """
        pass
    
    @abstractmethod
    def add_comment(
        self, 
        issue_key: str, 
        body: str
    ) -> str:
        """
        Add a comment to an issue.
        
        Args:
            issue_key: The issue identifier
            body: Comment body
            
        Returns:
            Created comment ID
        """
        pass
```

### DocumentParserPort

Interface for document parsers.

```python
from abc import ABC, abstractmethod
from spectryn.core.domain import Epic

class DocumentParserPort(ABC):
    """Abstract interface for document parsers."""
    
    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return supported file extensions (e.g., ['.md', '.markdown'])."""
        pass
    
    @abstractmethod
    def parse(self, content: str) -> Epic:
        """
        Parse document content into an Epic.
        
        Args:
            content: Raw document content
            
        Returns:
            Parsed Epic with stories
            
        Raises:
            ParseError: If content is invalid
        """
        pass
    
    @abstractmethod
    def validate(self, content: str) -> list[ValidationError]:
        """
        Validate document without parsing.
        
        Args:
            content: Raw document content
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
```

### DocumentFormatterPort

Interface for output formatters.

```python
from abc import ABC, abstractmethod

class DocumentFormatterPort(ABC):
    """Abstract interface for output formatters."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return formatter name (e.g., 'ADF', 'HTML')."""
        pass
    
    @abstractmethod
    def format_description(self, description: Description) -> Any:
        """
        Format a description for the target system.
        
        Args:
            description: Structured description
            
        Returns:
            Formatted output (type depends on target)
        """
        pass
```

### ConfigProviderPort

Interface for configuration providers.

```python
from abc import ABC, abstractmethod
from typing import Any

class ConfigProviderPort(ABC):
    """Abstract interface for configuration providers."""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key (dot-notation supported)
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        pass
    
    @abstractmethod
    def get_required(self, key: str) -> Any:
        """
        Get a required configuration value.
        
        Args:
            key: Configuration key
            
        Returns:
            Configuration value
            
        Raises:
            ConfigurationError: If key not found
        """
        pass
```

## Adapters (Implementations)

### JiraAdapter

Jira implementation of `IssueTrackerPort`.

```python
from spectryn.adapters.trackers.jira import JiraAdapter

# Create adapter with credentials
adapter = JiraAdapter(
    url="https://company.atlassian.net",
    email="user@company.com",
    api_token="token",
)

# Use the adapter
issues = adapter.get_epic_children("PROJ-123")
adapter.update_description("PROJ-456", "New description")
adapter.transition_issue("PROJ-456", Status.DONE)
```

### MarkdownParser

Markdown implementation of `DocumentParserPort`.

```python
from spectryn.adapters.input.parsers import MarkdownParser

parser = MarkdownParser()

# Check supported extensions
print(parser.supported_extensions)  # ['.md', '.markdown']

# Parse content
with open("EPIC.md") as f:
    epic = parser.parse(f.read())

# Validate without parsing
errors = parser.validate(content)
for error in errors:
    print(f"{error.line}: {error.message}")
```

### ADFFormatter

Atlassian Document Format implementation.

```python
from spectryn.adapters.output.formatters import ADFFormatter

formatter = ADFFormatter()

# Format description for Jira
adf_content = formatter.format_description(story.description)
# Returns ADF JSON structure
```

### EnvironmentConfigProvider

Environment-based configuration.

```python
from spectryn.adapters.infrastructure.config import EnvironmentConfigProvider

config = EnvironmentConfigProvider()

# Get values (checks env vars and .env file)
jira_url = config.get("jira.url")
verbose = config.get("sync.verbose", False)

# Get required value (raises if missing)
api_token = config.get_required("jira.api_token")
```

## Creating Custom Adapters

### Example: Linear Adapter

```python
from linear_api import LinearClient
from spectryn.core.ports import IssueTrackerPort
from spectryn.core.domain import IssueData, Status

class LinearAdapter(IssueTrackerPort):
    """Linear.app adapter for spectryn."""
    
    def __init__(self, api_key: str):
        self.client = LinearClient(api_key=api_key)
    
    @property
    def name(self) -> str:
        return "Linear"
    
    def get_epic_children(self, epic_key: str) -> list[IssueData]:
        # epic_key is a Linear project ID
        project = self.client.get_project(epic_key)
        issues = project.issues()
        
        return [
            IssueData(
                key=issue.identifier,
                title=issue.title,
                description=issue.description,
                status=self._map_status(issue.state.name),
            )
            for issue in issues
        ]
    
    def _map_status(self, linear_state: str) -> Status:
        mapping = {
            "Backlog": Status.PLANNED,
            "Todo": Status.PLANNED,
            "In Progress": Status.IN_PROGRESS,
            "Done": Status.DONE,
            "Canceled": Status.DONE,
        }
        return mapping.get(linear_state, Status.PLANNED)
    
    def update_description(self, issue_key: str, description: str) -> None:
        self.client.update_issue(issue_key, description=description)
    
    def create_subtask(self, parent_key: str, subtask: SubtaskData) -> str:
        issue = self.client.create_issue(
            title=subtask.title,
            description=subtask.description,
            parent_id=parent_key,
        )
        return issue.identifier
    
    def transition_issue(self, issue_key: str, status: Status) -> None:
        state_name = {
            Status.PLANNED: "Backlog",
            Status.IN_PROGRESS: "In Progress",
            Status.DONE: "Done",
        }[status]
        
        state = self.client.get_state_by_name(state_name)
        self.client.update_issue(issue_key, state_id=state.id)
    
    def add_comment(self, issue_key: str, body: str) -> str:
        comment = self.client.create_comment(issue_key, body=body)
        return comment.id
```

### Register the Adapter

```python
from spectryn.plugins import get_registry

registry = get_registry()
registry.register_adapter("linear", LinearAdapter)
```

### Use via CLI

```bash
spectryn --tracker linear --markdown EPIC.md --epic proj_123
```

