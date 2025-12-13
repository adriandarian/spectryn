"""
Shared pytest fixtures for md2jira test suite.

This module provides common fixtures used across test modules to reduce
code duplication and ensure consistent test data.

Fixture Categories:
- Adapters: Parser, Formatter instances
- Domain: Sample entities, value objects
- Configuration: TrackerConfig, SyncConfig
- Mocks: Mock trackers, API responses
- CLI: Console, argument parser
- Data: Sample markdown content
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING
from unittest.mock import Mock

if TYPE_CHECKING:
    from md2jira.adapters.formatters import ADFFormatter
    from md2jira.adapters.parsers import MarkdownParser
    from md2jira.cli.output import Console


# =============================================================================
# Adapters - Parser & Formatter Fixtures
# =============================================================================


@pytest.fixture
def adf_formatter() -> "ADFFormatter":
    """Create an ADFFormatter instance."""
    from md2jira.adapters.formatters import ADFFormatter
    return ADFFormatter()


@pytest.fixture
def markdown_parser() -> "MarkdownParser":
    """Create a MarkdownParser instance."""
    from md2jira.adapters.parsers import MarkdownParser
    return MarkdownParser()


# =============================================================================
# Sample Markdown Content
# =============================================================================


@pytest.fixture
def sample_markdown() -> str:
    """
    Sample markdown content with two user stories.
    
    Contains:
    - Story US-001: Complete with description, AC, subtasks, commits
    - Story US-002: Simpler story with description only
    """
    return dedent("""
    # Epic Title
    
    ## User Stories
    
    ### ✅ US-001: First Story
    
    | Field | Value |
    |-------|-------|
    | **Story Points** | 5 |
    | **Priority** | 🟡 High |
    | **Status** | ✅ Done |
    
    #### Description
    
    **As a** developer
    **I want** to test parsing
    **So that** the parser works correctly
    
    #### Acceptance Criteria
    
    - [x] Parser extracts story ID
    - [ ] Parser extracts title
    
    #### Subtasks
    
    | # | Subtask | Description | SP | Status |
    |---|---------|-------------|----|---------| 
    | 1 | Create parser | Build markdown parser | 3 | ✅ Done |
    | 2 | Add tests | Write unit tests | 2 | ✅ Done |
    
    #### Related Commits
    
    | Commit | Message |
    |--------|---------|
    | `abc1234` | Initial parser implementation |
    | `def5678` | Add test coverage |
    
    ---
    
    ### 🔄 US-002: Second Story
    
    | Field | Value |
    |-------|-------|
    | **Story Points** | 3 |
    | **Priority** | 🟢 Medium |
    | **Status** | 🔄 In Progress |
    
    #### Description
    
    **As a** user
    **I want** another feature
    **So that** I can do more
    """)


@pytest.fixture
def minimal_markdown() -> str:
    """Minimal valid markdown with one story."""
    return dedent("""
    # Epic Title
    
    ### US-001: Single Story
    
    #### Description
    
    **As a** user
    **I want** a feature
    **So that** I benefit
    """)


@pytest.fixture
def sample_markdown_file(tmp_path: Path, sample_markdown: str) -> Path:
    """Create a temporary markdown file with sample content."""
    md_file = tmp_path / "epic.md"
    md_file.write_text(sample_markdown)
    return md_file


# =============================================================================
# Domain Entities & Value Objects
# =============================================================================


@pytest.fixture
def sample_story_id():
    """Create a sample StoryId."""
    from md2jira.core.domain import StoryId
    return StoryId("US-001")


@pytest.fixture
def sample_issue_key():
    """Create a sample IssueKey."""
    from md2jira.core.domain import IssueKey
    return IssueKey("TEST-123")


@pytest.fixture
def sample_description():
    """Create a sample Description."""
    from md2jira.core.domain import Description
    return Description(
        role="developer",
        want="to test the application",
        benefit="I can verify it works correctly"
    )


@pytest.fixture
def sample_subtask():
    """Create a sample Subtask."""
    from md2jira.core.domain import Subtask, Status
    return Subtask(
        name="Create component",
        description="Build the component",
        story_points=3,
        status=Status.PLANNED,
    )


@pytest.fixture
def sample_commit():
    """Create a sample CommitRef."""
    from md2jira.core.domain import CommitRef
    return CommitRef(hash="abc1234567890", message="Initial implementation")


@pytest.fixture
def sample_user_story(sample_story_id, sample_description, sample_subtask, sample_commit):
    """Create a fully populated sample UserStory."""
    from md2jira.core.domain import (
        UserStory, AcceptanceCriteria, Priority, Status
    )
    return UserStory(
        id=sample_story_id,
        title="Test Story",
        description=sample_description,
        acceptance_criteria=AcceptanceCriteria.from_list(
            ["Criterion 1", "Criterion 2"],
            [True, False]
        ),
        story_points=5,
        priority=Priority.HIGH,
        status=Status.IN_PROGRESS,
        subtasks=[sample_subtask],
        commits=[sample_commit],
    )


@pytest.fixture
def sample_user_story_minimal():
    """Create a minimal UserStory (required fields only)."""
    from md2jira.core.domain import UserStory, StoryId
    return UserStory(
        id=StoryId("US-001"),
        title="Minimal Story",
    )


@pytest.fixture
def sample_epic(sample_issue_key, sample_user_story):
    """Create a sample Epic with stories."""
    from md2jira.core.domain import Epic, UserStory, StoryId, Status
    return Epic(
        key=sample_issue_key,
        title="Test Epic",
        stories=[
            sample_user_story,
            UserStory(
                id=StoryId("US-002"),
                title="Second Story",
                status=Status.DONE,
            ),
        ]
    )


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def tracker_config():
    """Create a test TrackerConfig."""
    from md2jira.core.ports.config_provider import TrackerConfig
    return TrackerConfig(
        url="https://test.atlassian.net",
        email="test@example.com",
        api_token="test-token-123",
        project_key="TEST",
    )


@pytest.fixture
def sync_config():
    """Create a test SyncConfig with all sync options enabled."""
    from md2jira.core.ports.config_provider import SyncConfig
    return SyncConfig(
        dry_run=False,
        sync_descriptions=True,
        sync_subtasks=True,
        sync_comments=True,
        sync_statuses=True,
    )


@pytest.fixture
def sync_config_dry_run():
    """Create a test SyncConfig in dry-run mode."""
    from md2jira.core.ports.config_provider import SyncConfig
    return SyncConfig(
        dry_run=True,
        sync_descriptions=True,
        sync_subtasks=True,
        sync_comments=True,
        sync_statuses=True,
    )


# =============================================================================
# CLI Fixtures
# =============================================================================


@pytest.fixture
def cli_parser():
    """Create a CLI argument parser."""
    from md2jira.cli.app import create_parser
    return create_parser()


@pytest.fixture
def console() -> "Console":
    """Create a Console with colors disabled for testing."""
    from md2jira.cli.output import Console
    return Console(color=False, verbose=False)


@pytest.fixture
def verbose_console() -> "Console":
    """Create a Console in verbose mode."""
    from md2jira.cli.output import Console
    return Console(color=False, verbose=True)


# =============================================================================
# Mock Tracker Fixtures
# =============================================================================


@pytest.fixture
def mock_tracker():
    """
    Create a basic mock issue tracker.
    
    Returns a Mock with common tracker methods configured.
    """
    from md2jira.core.ports.issue_tracker import IssueData
    
    tracker = Mock()
    tracker.name = "MockTracker"
    tracker.is_connected = True
    tracker.test_connection.return_value = True
    
    # Default issue response
    tracker.get_issue.return_value = IssueData(
        key="TEST-123",
        summary="Test Issue",
        description="Test description",
        status="Open",
        issue_type="Story",
    )
    
    # Default operations
    tracker.update_issue_description.return_value = True
    tracker.create_subtask.return_value = "TEST-456"
    tracker.add_comment.return_value = True
    tracker.get_issue_status.return_value = "Open"
    tracker.transition_issue.return_value = True
    tracker.get_issue_comments.return_value = []
    tracker.get_epic_children.return_value = []
    
    return tracker


@pytest.fixture
def mock_tracker_with_children():
    """
    Create a mock tracker with epic children configured.
    
    Returns a tracker with two child issues under the epic.
    """
    from md2jira.core.ports.issue_tracker import IssueData
    
    tracker = Mock()
    tracker.name = "MockTracker"
    tracker.is_connected = True
    tracker.test_connection.return_value = True
    
    # Epic children
    tracker.get_epic_children.return_value = [
        IssueData(
            key="TEST-10",
            summary="Story Alpha",
            status="Open",
            issue_type="Story",
            subtasks=[],
        ),
        IssueData(
            key="TEST-11",
            summary="Story Beta",
            status="In Progress",
            issue_type="Story",
            subtasks=[
                IssueData(
                    key="TEST-12",
                    summary="Beta Subtask",
                    status="Open",
                    issue_type="Sub-task",
                )
            ],
        ),
    ]
    
    # Configure get_issue to return appropriate data
    def get_issue_side_effect(key):
        issues = {
            "TEST-10": IssueData(
                key="TEST-10",
                summary="Story Alpha",
                description=None,
                status="Open",
                issue_type="Story",
                subtasks=[],
            ),
            "TEST-11": IssueData(
                key="TEST-11",
                summary="Story Beta",
                description=None,
                status="In Progress",
                issue_type="Story",
                subtasks=[
                    IssueData(
                        key="TEST-12",
                        summary="Beta Subtask",
                        status="Open",
                        issue_type="Sub-task",
                    )
                ],
            ),
        }
        return issues.get(key, IssueData(key=key, summary="Unknown", status="Open"))
    
    tracker.get_issue.side_effect = get_issue_side_effect
    tracker.update_issue_description.return_value = True
    tracker.create_subtask.return_value = "TEST-99"
    tracker.add_comment.return_value = True
    tracker.get_issue_comments.return_value = []
    tracker.get_issue_status.return_value = "Open"
    tracker.transition_issue.return_value = True
    
    return tracker


# =============================================================================
# Mock Jira API Response Fixtures
# =============================================================================


@pytest.fixture
def mock_myself_response() -> dict:
    """Mock response for /rest/api/3/myself endpoint."""
    return {
        "accountId": "user-123-abc",
        "displayName": "Test User",
        "emailAddress": "test@example.com",
        "active": True,
        "timeZone": "America/New_York",
    }


@pytest.fixture
def mock_issue_response() -> dict:
    """Mock response for Jira issue GET endpoint."""
    return {
        "key": "TEST-123",
        "fields": {
            "summary": "Sample User Story",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Description here"}]}
                ],
            },
            "status": {"name": "Open"},
            "issuetype": {"name": "Story"},
            "subtasks": [
                {
                    "key": "TEST-124",
                    "fields": {
                        "summary": "Subtask 1",
                        "status": {"name": "Open"},
                    },
                },
                {
                    "key": "TEST-125",
                    "fields": {
                        "summary": "Subtask 2",
                        "status": {"name": "In Progress"},
                    },
                },
            ],
        },
    }


@pytest.fixture
def mock_epic_children_response() -> dict:
    """Mock response for JQL search for epic children."""
    return {
        "total": 2,
        "issues": [
            {
                "key": "TEST-10",
                "fields": {
                    "summary": "Story Alpha",
                    "description": None,
                    "status": {"name": "Open"},
                    "issuetype": {"name": "Story"},
                    "subtasks": [],
                },
            },
            {
                "key": "TEST-11",
                "fields": {
                    "summary": "Story Beta",
                    "description": None,
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Story"},
                    "subtasks": [
                        {
                            "key": "TEST-12",
                            "fields": {
                                "summary": "Beta Subtask",
                                "status": {"name": "Open"},
                            },
                        },
                    ],
                },
            },
        ],
    }


@pytest.fixture
def mock_transitions_response() -> dict:
    """Mock response for available Jira transitions."""
    return {
        "transitions": [
            {"id": "4", "name": "Start Progress", "to": {"name": "In Progress"}},
            {"id": "5", "name": "Resolve", "to": {"name": "Resolved"}},
            {"id": "7", "name": "Open", "to": {"name": "Open"}},
        ]
    }


@pytest.fixture
def mock_comments_response() -> dict:
    """Mock response for Jira issue comments."""
    return {
        "comments": [
            {
                "id": "10001",
                "author": {"displayName": "Test User"},
                "body": {"type": "doc", "content": []},
                "created": "2024-01-15T10:00:00.000+0000",
            },
        ]
    }


@pytest.fixture
def mock_create_issue_response() -> dict:
    """Mock response for creating a Jira issue."""
    return {
        "id": "10099",
        "key": "TEST-99",
        "self": "https://test.atlassian.net/rest/api/3/issue/10099",
    }


# =============================================================================
# Mock Parser & Formatter Fixtures
# =============================================================================


@pytest.fixture
def mock_parser():
    """
    Create a mock parser that returns test stories.
    
    Returns two stories: US-001 (Story Alpha) and US-002 (Story Beta).
    """
    from md2jira.core.domain.entities import UserStory, Subtask
    from md2jira.core.domain.enums import Status
    from md2jira.core.domain.value_objects import StoryId, Description
    
    parser = Mock()
    parser.validate.return_value = []
    parser.parse_stories.return_value = [
        UserStory(
            id=StoryId("US-001"),
            title="Story Alpha",
            description=Description(
                role="developer",
                want="to test the alpha story",
                benefit="I can verify the sync works"
            ),
            status=Status.PLANNED,
            subtasks=[
                Subtask(name="Alpha Task 1", description="Do thing 1", story_points=2),
            ],
        ),
        UserStory(
            id=StoryId("US-002"),
            title="Story Beta",
            description=Description(
                role="developer",
                want="to test the beta story",
                benefit="I can verify updates work"
            ),
            status=Status.DONE,
            subtasks=[
                Subtask(name="Beta Subtask", description="Already exists", story_points=3),
            ],
        ),
    ]
    return parser


@pytest.fixture
def mock_formatter():
    """Create a mock ADF formatter."""
    formatter = Mock()
    formatter.format_story_description.return_value = {"type": "doc", "version": 1, "content": []}
    formatter.format_text.return_value = {"type": "doc", "version": 1, "content": []}
    formatter.format_commits_table.return_value = {"type": "doc", "version": 1, "content": []}
    formatter.format_list.return_value = {"type": "doc", "version": 1, "content": []}
    formatter.format_task_list.return_value = {"type": "doc", "version": 1, "content": []}
    return formatter


# =============================================================================
# Hook System Fixtures
# =============================================================================


@pytest.fixture
def hook_manager():
    """Create a fresh HookManager instance."""
    from md2jira.plugins import HookManager
    return HookManager()


# =============================================================================
# Test CLI Args Fixture
# =============================================================================


@pytest.fixture
def base_cli_args():
    """Create base CLI arguments mock for testing."""
    args = Mock()
    args.markdown = "epic.md"
    args.epic = "TEST-123"
    args.execute = False
    args.no_confirm = True
    args.phase = "all"
    args.story = None
    args.config = None  # Config file path
    args.jira_url = None
    args.project = None
    args.verbose = False
    args.no_color = False
    args.export = None
    args.validate = False
    args.interactive = False  # Interactive mode disabled by default
    args.completions = None  # Shell completions disabled by default
    return args

