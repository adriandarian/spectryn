# Core Domain

API reference for spectryn's core domain entities and value objects.

## Entities

### Epic

Represents a Jira epic with associated user stories.

```python
from spectryn.core.domain import Epic

class Epic:
    """An epic containing user stories."""
    
    title: str
    key: str | None
    description: str | None
    stories: list[UserStory]
    status: Status
    priority: Priority
```

### UserStory

Represents a user story with subtasks and metadata.

```python
from spectryn.core.domain import UserStory

class UserStory:
    """A user story with description and subtasks."""
    
    id: StoryId          # e.g., "US-001"
    title: str
    description: Description
    story_points: int
    priority: Priority
    status: Status
    subtasks: list[Subtask]
    acceptance_criteria: list[str]
    commits: list[Commit]
```

### Subtask

Represents a subtask under a user story.

```python
from spectryn.core.domain import Subtask

class Subtask:
    """A subtask under a user story."""
    
    number: int
    title: str
    description: str
    story_points: int
    status: Status
```

### Comment

Represents a comment on an issue.

```python
from spectryn.core.domain import Comment

class Comment:
    """A comment on an issue."""
    
    author: str
    body: str
    created_at: datetime
    updated_at: datetime | None
```

## Value Objects

### StoryId

Immutable identifier for user stories.

```python
from spectryn.core.domain import StoryId

class StoryId:
    """User story identifier (e.g., US-001)."""
    
    value: str
    
    @classmethod
    def from_string(cls, value: str) -> "StoryId":
        """Parse from string like 'US-001'."""
        ...
    
    @property
    def number(self) -> int:
        """Extract numeric part."""
        ...
```

### IssueKey

Jira issue key value object.

```python
from spectryn.core.domain import IssueKey

class IssueKey:
    """Jira issue key (e.g., PROJ-123)."""
    
    project: str
    number: int
    
    @classmethod
    def from_string(cls, value: str) -> "IssueKey":
        """Parse from string like 'PROJ-123'."""
        ...
    
    def __str__(self) -> str:
        return f"{self.project}-{self.number}"
```

### Description

Structured user story description.

```python
from spectryn.core.domain import Description

class Description:
    """User story description in As a/I want/So that format."""
    
    role: str           # "As a" part
    want: str           # "I want" part
    benefit: str        # "So that" part
    context: str | None # Additional context
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        ...
    
    def to_adf(self) -> dict:
        """Convert to Atlassian Document Format."""
        ...
```

## Enums

### Status

Issue status values.

```python
from spectryn.core.domain import Status

class Status(Enum):
    """Issue status."""
    
    PLANNED = "planned"      # 📋 Open in Jira
    IN_PROGRESS = "in_progress"  # 🔄 In Progress
    DONE = "done"            # ✅ Resolved
    
    @classmethod
    def from_emoji(cls, emoji: str) -> "Status":
        """Parse from emoji like ✅."""
        ...
    
    def to_emoji(self) -> str:
        """Convert to emoji representation."""
        ...
    
    def to_jira_status(self) -> str:
        """Convert to Jira status name."""
        ...
```

### Priority

Issue priority values.

```python
from spectryn.core.domain import Priority

class Priority(Enum):
    """Issue priority."""
    
    CRITICAL = "critical"  # 🔴
    HIGH = "high"          # 🟡
    MEDIUM = "medium"      # 🟢
    LOW = "low"            # 🟢
    
    @classmethod
    def from_emoji(cls, emoji: str) -> "Priority":
        """Parse from emoji like 🔴."""
        ...
    
    def to_emoji(self) -> str:
        """Convert to emoji representation."""
        ...
```

### IssueType

Jira issue type values.

```python
from spectryn.core.domain import IssueType

class IssueType(Enum):
    """Jira issue type."""
    
    EPIC = "Epic"
    STORY = "Story"
    SUBTASK = "Sub-task"
    TASK = "Task"
    BUG = "Bug"
```

## Usage Examples

### Creating Entities

```python
from spectryn.core.domain import (
    Epic, UserStory, Subtask, Description,
    StoryId, Status, Priority
)

# Create a user story
story = UserStory(
    id=StoryId.from_string("US-001"),
    title="Implement authentication",
    description=Description(
        role="user",
        want="to log in securely",
        benefit="my data is protected"
    ),
    story_points=5,
    priority=Priority.HIGH,
    status=Status.PLANNED,
    subtasks=[
        Subtask(
            number=1,
            title="Create login form",
            description="Build the login UI",
            story_points=2,
            status=Status.PLANNED,
        ),
        Subtask(
            number=2,
            title="Implement JWT auth",
            description="Add token handling",
            story_points=3,
            status=Status.PLANNED,
        ),
    ],
    acceptance_criteria=[
        "Login form validates input",
        "JWT tokens issued on success",
    ],
    commits=[],
)

# Create an epic
epic = Epic(
    title="User Management",
    key="PROJ-123",
    stories=[story],
    status=Status.IN_PROGRESS,
    priority=Priority.CRITICAL,
)
```

### Working with Value Objects

```python
from spectryn.core.domain import IssueKey, StoryId

# Parse issue key
key = IssueKey.from_string("PROJ-123")
print(key.project)  # "PROJ"
print(key.number)   # 123

# Parse story ID
story_id = StoryId.from_string("US-001")
print(story_id.number)  # 1

# Format description
desc = Description(
    role="developer",
    want="automated testing",
    benefit="bugs are caught early"
)
print(desc.to_markdown())
# **As a** developer
# **I want** automated testing
# **So that** bugs are caught early
```

### Status Conversions

```python
from spectryn.core.domain import Status

# From emoji
status = Status.from_emoji("✅")
print(status)  # Status.DONE

# To Jira status
print(status.to_jira_status())  # "Resolved"

# To emoji
print(Status.IN_PROGRESS.to_emoji())  # "🔄"
```

