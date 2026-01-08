"""
GraphQL Schema Definition.

Defines the GraphQL schema for the Spectra API including:
- Type definitions (Epic, Story, Subtask, etc.)
- Query operations
- Mutation operations
- Subscription operations
"""

# GraphQL Schema Definition Language (SDL)
SCHEMA_SDL = '''
"""
Spectra GraphQL API Schema

This schema provides access to:
- Epics, Stories, and Subtasks
- Sync operations
- Real-time updates via subscriptions
"""

scalar DateTime
scalar JSON

# ============================================================================
# Enums
# ============================================================================

"""Status of a work item"""
enum Status {
  PLANNED
  OPEN
  IN_PROGRESS
  IN_REVIEW
  DONE
  CANCELLED
}

"""Priority level of a work item"""
enum Priority {
  CRITICAL
  HIGH
  MEDIUM
  LOW
}

"""Type of sync operation"""
enum SyncOperation {
  PUSH
  PULL
  BIDIRECTIONAL
}

"""Status of a sync session"""
enum SyncStatus {
  PENDING
  IN_PROGRESS
  COMPLETED
  FAILED
  CANCELLED
}

"""Type of change in a sync operation"""
enum ChangeType {
  CREATED
  UPDATED
  DELETED
  MATCHED
  SKIPPED
}

"""Supported tracker types"""
enum TrackerType {
  JIRA
  GITHUB
  GITLAB
  LINEAR
  ASANA
  AZURE_DEVOPS
  TRELLO
  MONDAY
  CLICKUP
  SHORTCUT
  BITBUCKET
  YOUTRACK
  PLANE
  PIVOTAL
  BASECAMP
}

# ============================================================================
# Input Types
# ============================================================================

"""Filter options for querying epics"""
input EpicFilter {
  """Filter by status"""
  status: [Status!]
  """Filter by priority"""
  priority: [Priority!]
  """Filter by title (partial match)"""
  titleContains: String
  """Filter by key prefix"""
  keyPrefix: String
}

"""Filter options for querying stories"""
input StoryFilter {
  """Filter by status"""
  status: [Status!]
  """Filter by priority"""
  priority: [Priority!]
  """Filter by assignee"""
  assignee: String
  """Filter by labels"""
  labels: [String!]
  """Filter by sprint"""
  sprint: String
  """Filter by title (partial match)"""
  titleContains: String
  """Filter by story points range"""
  minPoints: Int
  maxPoints: Int
  """Filter by epic key"""
  epicKey: String
}

"""Pagination arguments"""
input PaginationInput {
  """Number of items to return"""
  first: Int
  """Cursor for forward pagination"""
  after: String
  """Number of items to return (backward)"""
  last: Int
  """Cursor for backward pagination"""
  before: String
}

"""Sorting options"""
input SortInput {
  """Field to sort by"""
  field: String!
  """Sort direction"""
  ascending: Boolean = true
}

"""Input for creating a story"""
input CreateStoryInput {
  """Story title"""
  title: String!
  """Story description (markdown)"""
  description: String
  """Story points"""
  storyPoints: Int
  """Priority level"""
  priority: Priority
  """Status"""
  status: Status
  """Assignee username"""
  assignee: String
  """Labels"""
  labels: [String!]
  """Sprint name"""
  sprint: String
  """Acceptance criteria"""
  acceptanceCriteria: [String!]
  """Technical notes"""
  technicalNotes: String
}

"""Input for updating a story"""
input UpdateStoryInput {
  """Story title"""
  title: String
  """Story description (markdown)"""
  description: String
  """Story points"""
  storyPoints: Int
  """Priority level"""
  priority: Priority
  """Status"""
  status: Status
  """Assignee username"""
  assignee: String
  """Labels"""
  labels: [String!]
  """Sprint name"""
  sprint: String
  """Acceptance criteria"""
  acceptanceCriteria: [String!]
  """Technical notes"""
  technicalNotes: String
}

"""Input for sync operation"""
input SyncInput {
  """Path to markdown file"""
  markdownPath: String!
  """Target tracker type"""
  tracker: TrackerType!
  """Epic key to sync"""
  epicKey: String
  """Sync operation type"""
  operation: SyncOperation = PUSH
  """Dry run (no actual changes)"""
  dryRun: Boolean = false
  """Create missing items"""
  createMissing: Boolean = true
  """Update existing items"""
  updateExisting: Boolean = true
}

# ============================================================================
# Types
# ============================================================================

"""Information about pagination"""
type PageInfo {
  """Whether there are more items after this page"""
  hasNextPage: Boolean!
  """Whether there are more items before this page"""
  hasPreviousPage: Boolean!
  """Cursor pointing to the first item"""
  startCursor: String
  """Cursor pointing to the last item"""
  endCursor: String
  """Total number of items"""
  totalCount: Int
}

"""A subtask within a user story"""
type Subtask {
  """Unique identifier"""
  id: ID!
  """Subtask number within the story"""
  number: Int!
  """Subtask name"""
  name: String!
  """Subtask description"""
  description: String
  """Story points"""
  storyPoints: Int!
  """Current status"""
  status: Status!
  """Priority level"""
  priority: Priority
  """Assigned user"""
  assignee: String
  """External tracker key"""
  externalKey: String
}

"""A comment on an issue"""
type Comment {
  """Unique identifier"""
  id: ID!
  """Comment body"""
  body: String!
  """Comment author"""
  author: String
  """When the comment was created"""
  createdAt: DateTime
  """Type of comment (text, commits, etc.)"""
  commentType: String!
}

"""A commit reference"""
type CommitRef {
  """Commit hash"""
  hash: String!
  """Commit message"""
  message: String!
}

"""A user story - the primary work item"""
type Story {
  """Unique identifier"""
  id: ID!
  """Story title"""
  title: String!
  """Story description (markdown)"""
  description: String
  """Acceptance criteria"""
  acceptanceCriteria: [String!]!
  """Technical notes"""
  technicalNotes: String
  """Story points"""
  storyPoints: Int!
  """Priority level"""
  priority: Priority!
  """Current status"""
  status: Status!
  """Assigned user"""
  assignee: String
  """Labels/tags"""
  labels: [String!]!
  """Sprint/iteration name"""
  sprint: String
  """Subtasks"""
  subtasks: [Subtask!]!
  """Related commits"""
  commits: [CommitRef!]!
  """Comments"""
  comments: [Comment!]!
  """Attached files"""
  attachments: [String!]!
  """External tracker key"""
  externalKey: String
  """External tracker URL"""
  externalUrl: String
  """When last synced"""
  lastSynced: DateTime
  """Sync status"""
  syncStatus: String
  """Parent epic"""
  epic: Epic
}

"""An edge in a Story connection"""
type StoryEdge {
  """The story"""
  node: Story!
  """Cursor for pagination"""
  cursor: String!
}

"""A paginated list of stories"""
type StoryConnection {
  """List of edges"""
  edges: [StoryEdge!]!
  """Pagination info"""
  pageInfo: PageInfo!
}

"""An epic - a collection of related user stories"""
type Epic {
  """Unique key"""
  key: ID!
  """Epic title"""
  title: String!
  """Short summary"""
  summary: String
  """Full description"""
  description: String
  """Current status"""
  status: Status!
  """Priority level"""
  priority: Priority!
  """Parent epic key (for hierarchy)"""
  parentKey: String
  """Hierarchy level (epic, feature, initiative)"""
  level: String!
  """User stories in this epic"""
  stories(
    filter: StoryFilter
    pagination: PaginationInput
    sort: SortInput
  ): StoryConnection!
  """Child epics"""
  childEpics: [Epic!]!
  """Total story points"""
  totalStoryPoints: Int!
  """Completion percentage"""
  completionPercentage: Float!
  """When the epic was created"""
  createdAt: DateTime
  """When the epic was last updated"""
  updatedAt: DateTime
}

"""An edge in an Epic connection"""
type EpicEdge {
  """The epic"""
  node: Epic!
  """Cursor for pagination"""
  cursor: String!
}

"""A paginated list of epics"""
type EpicConnection {
  """List of edges"""
  edges: [EpicEdge!]!
  """Pagination info"""
  pageInfo: PageInfo!
}

"""A change made during sync"""
type SyncChange {
  """Type of change"""
  changeType: ChangeType!
  """Type of item changed"""
  itemType: String!
  """Item identifier"""
  itemId: String!
  """Item title"""
  itemTitle: String!
  """Previous value (for updates)"""
  previousValue: JSON
  """New value (for updates)"""
  newValue: JSON
  """External key (if applicable)"""
  externalKey: String
}

"""Result of a sync operation"""
type SyncResult {
  """Whether sync completed successfully"""
  success: Boolean!
  """Session identifier"""
  sessionId: String!
  """Sync operation type"""
  operation: SyncOperation!
  """Tracker type used"""
  tracker: TrackerType!
  """Epic key synced"""
  epicKey: String
  """Total items processed"""
  totalItems: Int!
  """Items created"""
  created: Int!
  """Items updated"""
  updated: Int!
  """Items matched"""
  matched: Int!
  """Items skipped"""
  skipped: Int!
  """Items failed"""
  failed: Int!
  """List of changes"""
  changes: [SyncChange!]!
  """Error messages (if any)"""
  errors: [String!]!
  """When sync started"""
  startedAt: DateTime!
  """When sync completed"""
  completedAt: DateTime
  """Duration in milliseconds"""
  durationMs: Int
}

"""Progress update during sync"""
type SyncProgress {
  """Session identifier"""
  sessionId: String!
  """Current operation description"""
  operation: String!
  """Current item being processed"""
  currentItem: String
  """Items processed so far"""
  processed: Int!
  """Total items to process"""
  total: Int!
  """Progress percentage (0-100)"""
  percentage: Float!
}

"""A sync conflict between local and remote"""
type SyncConflict {
  """Conflict identifier"""
  id: ID!
  """Item type"""
  itemType: String!
  """Item identifier"""
  itemId: String!
  """Item title"""
  itemTitle: String!
  """Local value"""
  localValue: JSON!
  """Remote value"""
  remoteValue: JSON!
  """Field in conflict"""
  field: String!
  """When detected"""
  detectedAt: DateTime!
}

"""Statistics about the workspace"""
type WorkspaceStats {
  """Total number of epics"""
  totalEpics: Int!
  """Total number of stories"""
  totalStories: Int!
  """Total number of subtasks"""
  totalSubtasks: Int!
  """Total story points"""
  totalStoryPoints: Int!
  """Completed story points"""
  completedStoryPoints: Int!
  """Stories by status"""
  storiesByStatus: JSON!
  """Stories by priority"""
  storiesByPriority: JSON!
  """Average story points per story"""
  averageStoryPoints: Float!
  """Completion percentage"""
  completionPercentage: Float!
}

"""Server health status"""
type HealthStatus {
  """Whether the server is healthy"""
  healthy: Boolean!
  """Server version"""
  version: String!
  """Server uptime in seconds"""
  uptimeSeconds: Float!
  """Active connections"""
  activeConnections: Int!
  """Memory usage in MB"""
  memoryUsageMb: Float!
}

# ============================================================================
# Queries
# ============================================================================

type Query {
  """Get a specific epic by key"""
  epic(key: ID!): Epic

  """List all epics with filtering and pagination"""
  epics(
    filter: EpicFilter
    pagination: PaginationInput
    sort: SortInput
  ): EpicConnection!

  """Get a specific story by ID"""
  story(id: ID!): Story

  """List all stories with filtering and pagination"""
  stories(
    filter: StoryFilter
    pagination: PaginationInput
    sort: SortInput
  ): StoryConnection!

  """Search for stories by text"""
  searchStories(
    query: String!
    pagination: PaginationInput
  ): StoryConnection!

  """Get workspace statistics"""
  workspaceStats: WorkspaceStats!

  """Get server health status"""
  health: HealthStatus!

  """Get active sync sessions"""
  activeSyncs: [SyncResult!]!

  """Get sync history"""
  syncHistory(
    limit: Int = 10
    offset: Int = 0
  ): [SyncResult!]!
}

# ============================================================================
# Mutations
# ============================================================================

type Mutation {
  """Start a sync operation"""
  sync(input: SyncInput!): SyncResult!

  """Cancel an active sync"""
  cancelSync(sessionId: String!): Boolean!

  """Create a new story"""
  createStory(epicKey: ID!, input: CreateStoryInput!): Story!

  """Update an existing story"""
  updateStory(id: ID!, input: UpdateStoryInput!): Story!

  """Delete a story"""
  deleteStory(id: ID!): Boolean!

  """Update story status"""
  updateStoryStatus(id: ID!, status: Status!): Story!

  """Assign a story to a user"""
  assignStory(id: ID!, assignee: String): Story!

  """Add a label to a story"""
  addLabel(storyId: ID!, label: String!): Story!

  """Remove a label from a story"""
  removeLabel(storyId: ID!, label: String!): Story!

  """Resolve a sync conflict"""
  resolveConflict(
    conflictId: ID!
    resolution: String!
    value: JSON
  ): Boolean!

  """Import from a tracker"""
  importFromTracker(
    tracker: TrackerType!
    projectKey: String!
    outputPath: String!
  ): SyncResult!

  """Validate a markdown file"""
  validateMarkdown(path: String!): JSON!
}

# ============================================================================
# Subscriptions
# ============================================================================

type Subscription {
  """Subscribe to sync progress updates"""
  syncProgress(sessionId: String): SyncProgress!

  """Subscribe to sync completion"""
  syncCompleted(sessionId: String): SyncResult!

  """Subscribe to story updates"""
  storyUpdated(epicKey: ID): Story!

  """Subscribe to new conflicts"""
  conflictDetected: SyncConflict!

  """Subscribe to all sync events"""
  syncEvents: JSON!
}
'''


# Type definitions for Python code
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class GraphQLStatus(Enum):
    """Status values mapped from domain."""

    PLANNED = "PLANNED"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class GraphQLPriority(Enum):
    """Priority values mapped from domain."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GraphQLSyncOperation(Enum):
    """Sync operation types."""

    PUSH = "PUSH"
    PULL = "PULL"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class GraphQLChangeType(Enum):
    """Types of changes in sync."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    MATCHED = "MATCHED"
    SKIPPED = "SKIPPED"


@dataclass
class GraphQLSubtask:
    """GraphQL representation of a subtask."""

    id: str
    number: int
    name: str
    description: str | None
    story_points: int
    status: GraphQLStatus
    priority: GraphQLPriority | None
    assignee: str | None
    external_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "id": self.id,
            "number": self.number,
            "name": self.name,
            "description": self.description,
            "storyPoints": self.story_points,
            "status": self.status.value,
            "priority": self.priority.value if self.priority else None,
            "assignee": self.assignee,
            "externalKey": self.external_key,
        }


@dataclass
class GraphQLStory:
    """GraphQL representation of a story."""

    id: str
    title: str
    description: str | None
    acceptance_criteria: list[str]
    technical_notes: str | None
    story_points: int
    priority: GraphQLPriority
    status: GraphQLStatus
    assignee: str | None
    labels: list[str]
    sprint: str | None
    subtasks: list[GraphQLSubtask]
    commits: list[dict[str, str]]
    comments: list[dict[str, Any]]
    attachments: list[str]
    external_key: str | None
    external_url: str | None
    last_synced: datetime | None
    sync_status: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "acceptanceCriteria": self.acceptance_criteria,
            "technicalNotes": self.technical_notes,
            "storyPoints": self.story_points,
            "priority": self.priority.value,
            "status": self.status.value,
            "assignee": self.assignee,
            "labels": self.labels,
            "sprint": self.sprint,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "commits": self.commits,
            "comments": self.comments,
            "attachments": self.attachments,
            "externalKey": self.external_key,
            "externalUrl": self.external_url,
            "lastSynced": self.last_synced.isoformat() if self.last_synced else None,
            "syncStatus": self.sync_status,
        }


@dataclass
class GraphQLEpic:
    """GraphQL representation of an epic."""

    key: str
    title: str
    summary: str | None
    description: str | None
    status: GraphQLStatus
    priority: GraphQLPriority
    parent_key: str | None
    level: str
    stories: list[GraphQLStory]
    child_epics: list["GraphQLEpic"]
    created_at: datetime | None
    updated_at: datetime | None

    @property
    def total_story_points(self) -> int:
        """Calculate total story points."""
        return sum(s.story_points for s in self.stories)

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if not self.stories:
            return 0.0
        done = sum(1 for s in self.stories if s.status == GraphQLStatus.DONE)
        return (done / len(self.stories)) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "parentKey": self.parent_key,
            "level": self.level,
            "stories": {"edges": [], "pageInfo": {}},  # Resolved dynamically
            "childEpics": [e.to_dict() for e in self.child_epics],
            "totalStoryPoints": self.total_story_points,
            "completionPercentage": self.completion_percentage,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class GraphQLSyncChange:
    """A change made during sync."""

    change_type: GraphQLChangeType
    item_type: str
    item_id: str
    item_title: str
    previous_value: Any = None
    new_value: Any = None
    external_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "changeType": self.change_type.value,
            "itemType": self.item_type,
            "itemId": self.item_id,
            "itemTitle": self.item_title,
            "previousValue": self.previous_value,
            "newValue": self.new_value,
            "externalKey": self.external_key,
        }


@dataclass
class GraphQLSyncResult:
    """Result of a sync operation."""

    success: bool
    session_id: str
    operation: GraphQLSyncOperation
    tracker: str
    epic_key: str | None
    total_items: int
    created: int
    updated: int
    matched: int
    skipped: int
    failed: int
    changes: list[GraphQLSyncChange]
    errors: list[str]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "success": self.success,
            "sessionId": self.session_id,
            "operation": self.operation.value,
            "tracker": self.tracker,
            "epicKey": self.epic_key,
            "totalItems": self.total_items,
            "created": self.created,
            "updated": self.updated,
            "matched": self.matched,
            "skipped": self.skipped,
            "failed": self.failed,
            "changes": [c.to_dict() for c in self.changes],
            "errors": self.errors,
            "startedAt": self.started_at.isoformat(),
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "durationMs": self.duration_ms,
        }


@dataclass
class GraphQLWorkspaceStats:
    """Workspace statistics."""

    total_epics: int = 0
    total_stories: int = 0
    total_subtasks: int = 0
    total_story_points: int = 0
    completed_story_points: int = 0
    stories_by_status: dict[str, int] = field(default_factory=dict)
    stories_by_priority: dict[str, int] = field(default_factory=dict)
    average_story_points: float = 0.0
    completion_percentage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to GraphQL response format."""
        return {
            "totalEpics": self.total_epics,
            "totalStories": self.total_stories,
            "totalSubtasks": self.total_subtasks,
            "totalStoryPoints": self.total_story_points,
            "completedStoryPoints": self.completed_story_points,
            "storiesByStatus": self.stories_by_status,
            "storiesByPriority": self.stories_by_priority,
            "averageStoryPoints": self.average_story_points,
            "completionPercentage": self.completion_percentage,
        }
