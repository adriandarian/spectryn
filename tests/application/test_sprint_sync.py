"""Tests for sprint/iteration sync functionality."""

import textwrap
from datetime import datetime, timedelta

import pytest

from spectryn.application.sync.sprint_sync import (
    Sprint,
    SprintAssignment,
    SprintExtractor,
    SprintState,
    SprintSyncConfig,
    SprintSyncResult,
    extract_sprint,
    parse_sprint_name,
)


class TestSprintState:
    """Tests for SprintState enum."""

    def test_all_states_exist(self):
        """Test all sprint states are defined."""
        assert SprintState.FUTURE.value == "future"
        assert SprintState.ACTIVE.value == "active"
        assert SprintState.CLOSED.value == "closed"
        assert SprintState.UNKNOWN.value == "unknown"


class TestSprint:
    """Tests for Sprint class."""

    def test_create_basic(self):
        """Test creating a basic sprint."""
        sprint = Sprint(
            id="123",
            name="Sprint 23",
            goal="Complete feature X",
            state=SprintState.ACTIVE,
        )
        assert sprint.id == "123"
        assert sprint.name == "Sprint 23"
        assert sprint.goal == "Complete feature X"
        assert sprint.state == SprintState.ACTIVE

    def test_is_active_by_state(self):
        """Test is_active when state is ACTIVE."""
        sprint = Sprint(id="1", name="Sprint", state=SprintState.ACTIVE)
        assert sprint.is_active() is True

    def test_is_active_by_dates(self):
        """Test is_active when within date range."""
        now = datetime.now()
        sprint = Sprint(
            id="1",
            name="Sprint",
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=5),
        )
        assert sprint.is_active() is True

    def test_is_future_by_state(self):
        """Test is_future when state is FUTURE."""
        sprint = Sprint(id="1", name="Sprint", state=SprintState.FUTURE)
        assert sprint.is_future() is True

    def test_is_future_by_dates(self):
        """Test is_future when start date is in future."""
        sprint = Sprint(
            id="1",
            name="Sprint",
            start_date=datetime.now() + timedelta(days=5),
        )
        assert sprint.is_future() is True

    def test_days_remaining(self):
        """Test calculating days remaining."""
        sprint = Sprint(
            id="1",
            name="Sprint",
            end_date=datetime.now() + timedelta(days=10),
        )
        # Allow for timing issues (9 or 10 days depending on time of day)
        assert sprint.days_remaining() in (9, 10)

    def test_days_remaining_none_without_end_date(self):
        """Test days_remaining returns None without end date."""
        sprint = Sprint(id="1", name="Sprint")
        assert sprint.days_remaining() is None

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        sprint = Sprint(
            id="123",
            name="Sprint 23",
            goal="Complete feature",
            state=SprintState.ACTIVE,
            start_date=datetime(2024, 1, 1, 10, 0),
            end_date=datetime(2024, 1, 14, 18, 0),
            board_id="100",
            remote_id="123",
        )
        data = sprint.to_dict()
        restored = Sprint.from_dict(data)

        assert restored.id == sprint.id
        assert restored.name == sprint.name
        assert restored.goal == sprint.goal
        assert restored.state == sprint.state
        assert restored.start_date == sprint.start_date
        assert restored.board_id == sprint.board_id

    def test_from_jira_sprint(self):
        """Test creating Sprint from Jira API response."""
        jira_data = {
            "id": 42,
            "name": "Sprint 23",
            "goal": "Ship the feature",
            "state": "active",
            "startDate": "2024-01-01T10:00:00Z",
            "endDate": "2024-01-14T18:00:00Z",
            "originBoardId": 100,
        }
        sprint = Sprint.from_jira_sprint(jira_data)

        assert sprint.id == "42"
        assert sprint.name == "Sprint 23"
        assert sprint.goal == "Ship the feature"
        assert sprint.state == SprintState.ACTIVE
        assert sprint.board_id == "100"
        assert sprint.start_date is not None


class TestSprintAssignment:
    """Tests for SprintAssignment class."""

    def test_create_basic(self):
        """Test creating a basic assignment."""
        assignment = SprintAssignment(
            story_id="US-001",
            sprint_name="Sprint 23",
        )
        assert assignment.story_id == "US-001"
        assert assignment.sprint_name == "Sprint 23"

    def test_has_sprint_with_name(self):
        """Test has_sprint with sprint name."""
        assignment = SprintAssignment(story_id="US-001", sprint_name="Sprint 23")
        assert assignment.has_sprint() is True

    def test_has_sprint_with_id(self):
        """Test has_sprint with sprint ID."""
        assignment = SprintAssignment(story_id="US-001", sprint_id="42")
        assert assignment.has_sprint() is True

    def test_has_sprint_without_sprint(self):
        """Test has_sprint without any sprint."""
        assignment = SprintAssignment(story_id="US-001")
        assert assignment.has_sprint() is False

    def test_get_sprint_name(self):
        """Test getting sprint name."""
        assignment = SprintAssignment(story_id="US-001", sprint_name="Sprint 23")
        assert assignment.get_sprint_name() == "Sprint 23"

    def test_get_sprint_name_from_sprint(self):
        """Test getting sprint name from Sprint object."""
        sprint = Sprint(name="Sprint 24")
        assignment = SprintAssignment(story_id="US-001", sprint=sprint)
        assert assignment.get_sprint_name() == "Sprint 24"


class TestSprintExtractor:
    """Tests for SprintExtractor."""

    def test_extract_from_table(self):
        """Test extracting sprint from markdown table."""
        content = textwrap.dedent("""
            ### US-001: Test Story

            | **Property** | **Value** |
            |--------------|-----------|
            | **Sprint** | Sprint 23 |
            | **Priority** | High |
        """)
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name == "Sprint 23"

    def test_extract_iteration(self):
        """Test extracting iteration (alternative name)."""
        content = "| **Iteration** | Iteration 5 |"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name == "Iteration 5"

    def test_extract_inline_format(self):
        """Test extracting inline sprint format."""
        content = "**Sprint:** Sprint 23\n**Priority:** High"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name == "Sprint 23"

    def test_extract_obsidian_dataview(self):
        """Test extracting Obsidian dataview format."""
        content = "Sprint:: Sprint 24\nStatus:: In Progress"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name == "Sprint 24"

    def test_no_sprint(self):
        """Test content without sprint."""
        content = "### US-001: Simple Story\n\nJust a description."
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name is None
        assert assignment.has_sprint() is False

    def test_skip_none_value(self):
        """Test skipping 'None' as sprint value."""
        content = "| **Sprint** | None |"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name is None

    def test_skip_na_value(self):
        """Test skipping 'N/A' as sprint value."""
        content = "| **Sprint** | N/A |"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name is None

    def test_skip_dash_value(self):
        """Test skipping '-' as sprint value."""
        content = "| **Sprint** | - |"
        assignment = extract_sprint(content, "US-001")
        assert assignment.sprint_name is None


class TestParseSprintName:
    """Tests for parse_sprint_name function."""

    def test_parse_sprint_number(self):
        """Test parsing 'Sprint N' format."""
        result = parse_sprint_name("Sprint 23")
        assert result["number"] == 23

    def test_parse_iteration_number(self):
        """Test parsing 'Iteration N' format."""
        result = parse_sprint_name("Iteration 5")
        assert result["number"] == 5

    def test_parse_iso_week(self):
        """Test parsing ISO week format."""
        result = parse_sprint_name("2024-W05")
        assert result["year"] == 2024
        assert result["week"] == 5

    def test_parse_unknown_format(self):
        """Test parsing unknown format."""
        result = parse_sprint_name("Custom Sprint Name")
        assert result["raw"] == "Custom Sprint Name"
        assert result["number"] is None


class TestSprintSyncConfig:
    """Tests for SprintSyncConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SprintSyncConfig()
        assert config.enabled is True
        assert config.sync_sprint_assignment is True
        assert config.push_to_tracker is True
        assert config.pull_from_tracker is True
        assert config.match_by_name is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SprintSyncConfig(
            enabled=True,
            push_to_tracker=False,
            default_sprint="Backlog",
            use_active_sprint=True,
        )
        assert config.push_to_tracker is False
        assert config.default_sprint == "Backlog"
        assert config.use_active_sprint is True


class TestSprintSyncResult:
    """Tests for SprintSyncResult."""

    def test_success_when_no_errors(self):
        """Test success property when no errors."""
        result = SprintSyncResult(story_id="US-001")
        assert result.success is True

    def test_failure_when_errors(self):
        """Test success property when errors."""
        result = SprintSyncResult(story_id="US-001", errors=["Sprint not found"])
        assert result.success is False
