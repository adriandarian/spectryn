"""Tests for workflow automation rules functionality."""

import pytest

from spectryn.application.sync.workflow_rules import (
    RuleAction,
    RuleActionSpec,
    RuleCondition,
    RuleExecutionResult,
    RuleType,
    WorkflowConfig,
    WorkflowEngine,
    WorkflowExecutionResult,
    WorkflowRule,
    create_default_rules,
    evaluate_epic_rules,
    evaluate_story_rules,
)
from spectryn.core.domain.entities import Epic, Subtask, UserStory
from spectryn.core.domain.enums import Status
from spectryn.core.domain.value_objects import IssueKey, StoryId


class TestRuleType:
    """Tests for RuleType enum."""

    def test_all_types_exist(self):
        """Test all rule types are defined."""
        assert RuleType.ALL_SUBTASKS_DONE.value == "all_subtasks_done"
        assert RuleType.ANY_SUBTASK_IN_PROGRESS.value == "any_subtask_in_progress"
        assert RuleType.ALL_STORIES_DONE.value == "all_stories_done"

    def test_from_string(self):
        """Test parsing rule type from string."""
        assert RuleType.from_string("all_subtasks_done") == RuleType.ALL_SUBTASKS_DONE
        assert RuleType.from_string("any-subtask-in-progress") == RuleType.ANY_SUBTASK_IN_PROGRESS
        assert RuleType.from_string("unknown") == RuleType.CUSTOM


class TestRuleAction:
    """Tests for RuleAction enum."""

    def test_all_actions_exist(self):
        """Test all actions are defined."""
        assert RuleAction.SET_STATUS.value == "set_status"
        assert RuleAction.ADD_LABEL.value == "add_label"
        assert RuleAction.REMOVE_LABEL.value == "remove_label"


class TestRuleCondition:
    """Tests for RuleCondition class."""

    def test_evaluate_eq(self):
        """Test equality operator."""
        condition = RuleCondition(field="status", operator="eq", value=Status.DONE)

        class Entity:
            status = Status.DONE

        assert condition.evaluate(Entity()) is True

    def test_evaluate_ne(self):
        """Test not-equal operator."""
        condition = RuleCondition(field="status", operator="ne", value=Status.DONE)

        class Entity:
            status = Status.IN_PROGRESS

        assert condition.evaluate(Entity()) is True

    def test_evaluate_contains(self):
        """Test contains operator."""
        condition = RuleCondition(field="labels", operator="contains", value="urgent")

        class Entity:
            labels = ["urgent", "bug"]

        assert condition.evaluate(Entity()) is True

    def test_evaluate_not_contains(self):
        """Test not-contains operator."""
        condition = RuleCondition(field="labels", operator="not_contains", value="done")

        class Entity:
            labels = ["urgent", "bug"]

        assert condition.evaluate(Entity()) is True

    def test_evaluate_missing_field(self):
        """Test evaluating with missing field."""
        condition = RuleCondition(field="nonexistent", operator="eq", value="test")

        class Entity:
            pass

        assert condition.evaluate(Entity()) is False


class TestRuleActionSpec:
    """Tests for RuleActionSpec class."""

    def test_create_basic(self):
        """Test creating a basic action spec."""
        spec = RuleActionSpec(action=RuleAction.SET_STATUS, params={"status": Status.DONE})
        assert spec.action == RuleAction.SET_STATUS
        assert spec.params["status"] == Status.DONE

    def test_to_dict_and_back(self):
        """Test serialization roundtrip."""
        spec = RuleActionSpec(action=RuleAction.ADD_LABEL, params={"label": "automated"})
        data = spec.to_dict()
        restored = RuleActionSpec.from_dict(data)

        assert restored.action == spec.action
        assert restored.params["label"] == "automated"


class TestWorkflowRule:
    """Tests for WorkflowRule class."""

    def test_create_basic(self):
        """Test creating a basic rule."""
        rule = WorkflowRule(
            id="test-rule",
            name="Test Rule",
            rule_type=RuleType.ALL_SUBTASKS_DONE,
        )
        assert rule.id == "test-rule"
        assert rule.enabled is True

    def test_matches_all_subtasks_done(self):
        """Test matching all subtasks done rule."""
        rule = WorkflowRule(
            id="test",
            name="Test",
            rule_type=RuleType.ALL_SUBTASKS_DONE,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            subtasks=[
                Subtask(name="Task 1", status=Status.DONE),
                Subtask(name="Task 2", status=Status.DONE),
            ],
        )

        assert rule.matches(story) is True

    def test_not_matches_when_subtask_not_done(self):
        """Test not matching when a subtask is not done."""
        rule = WorkflowRule(
            id="test",
            name="Test",
            rule_type=RuleType.ALL_SUBTASKS_DONE,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            subtasks=[
                Subtask(name="Task 1", status=Status.DONE),
                Subtask(name="Task 2", status=Status.IN_PROGRESS),
            ],
        )

        assert rule.matches(story) is False

    def test_matches_any_subtask_in_progress(self):
        """Test matching any subtask in progress rule."""
        rule = WorkflowRule(
            id="test",
            name="Test",
            rule_type=RuleType.ANY_SUBTASK_IN_PROGRESS,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            subtasks=[
                Subtask(name="Task 1", status=Status.PLANNED),
                Subtask(name="Task 2", status=Status.IN_PROGRESS),
            ],
        )

        assert rule.matches(story) is True

    def test_disabled_rule_never_matches(self):
        """Test that disabled rules never match."""
        rule = WorkflowRule(
            id="test",
            name="Test",
            rule_type=RuleType.ALL_SUBTASKS_DONE,
            enabled=False,
        )

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            subtasks=[Subtask(name="Task 1", status=Status.DONE)],
        )

        assert rule.matches(story) is False

    def test_to_dict(self):
        """Test converting rule to dictionary."""
        rule = WorkflowRule(
            id="test-rule",
            name="Test Rule",
            rule_type=RuleType.ALL_SUBTASKS_DONE,
            priority=10,
        )
        data = rule.to_dict()

        assert data["id"] == "test-rule"
        assert data["rule_type"] == "all_subtasks_done"
        assert data["priority"] == 10


class TestWorkflowEngine:
    """Tests for WorkflowEngine class."""

    def test_create_with_default_rules(self):
        """Test creating engine with default rules."""
        engine = WorkflowEngine()
        assert len(engine.rules) > 0

    def test_evaluate_story_all_subtasks_done(self):
        """Test evaluating story with all subtasks done."""
        engine = WorkflowEngine()

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            status=Status.IN_PROGRESS,
            subtasks=[
                Subtask(name="Task 1", status=Status.DONE),
                Subtask(name="Task 2", status=Status.DONE),
            ],
        )

        result = engine.evaluate_story(story, dry_run=True)

        assert result.entities_evaluated == 1
        assert result.rules_matched > 0

    def test_evaluate_story_any_subtask_in_progress(self):
        """Test evaluating story with subtask in progress."""
        engine = WorkflowEngine()

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            status=Status.PLANNED,
            subtasks=[
                Subtask(name="Task 1", status=Status.PLANNED),
                Subtask(name="Task 2", status=Status.IN_PROGRESS),
            ],
        )

        result = engine.evaluate_story(story, dry_run=True)

        assert result.rules_matched > 0

    def test_evaluate_epic_all_stories_done(self):
        """Test evaluating epic with all stories done."""
        engine = WorkflowEngine()

        epic = Epic(
            key=IssueKey("EPIC-001"),
            title="Test Epic",
            status=Status.IN_PROGRESS,
            stories=[
                UserStory(id=StoryId("US-001"), title="Story 1", status=Status.DONE),
                UserStory(id=StoryId("US-002"), title="Story 2", status=Status.DONE),
            ],
        )

        result = engine.evaluate_epic(epic, dry_run=True)

        assert result.rules_matched > 0

    def test_execute_action_set_status(self):
        """Test executing set_status action."""
        engine = WorkflowEngine()

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            status=Status.IN_PROGRESS,
        )

        action_spec = RuleActionSpec(action=RuleAction.SET_STATUS, params={"status": Status.DONE})

        action_name = engine._execute_action(story, action_spec, dry_run=False)

        assert action_name is not None
        assert story.status == Status.DONE

    def test_execute_action_add_label(self):
        """Test executing add_label action."""
        engine = WorkflowEngine()

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            labels=["existing"],
        )

        action_spec = RuleActionSpec(action=RuleAction.ADD_LABEL, params={"label": "automated"})

        engine._execute_action(story, action_spec, dry_run=False)

        assert "automated" in story.labels

    def test_execute_action_remove_label(self):
        """Test executing remove_label action."""
        engine = WorkflowEngine()

        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            labels=["to-remove", "keep"],
        )

        action_spec = RuleActionSpec(action=RuleAction.REMOVE_LABEL, params={"label": "to-remove"})

        engine._execute_action(story, action_spec, dry_run=False)

        assert "to-remove" not in story.labels
        assert "keep" in story.labels


class TestWorkflowConfig:
    """Tests for WorkflowConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = WorkflowConfig()
        assert config.enabled is True
        assert config.auto_complete_on_subtasks is True
        assert config.auto_start_on_subtask is True
        assert config.apply_on_sync is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = WorkflowConfig(auto_complete_on_subtasks=False, sync_changes_to_tracker=False)
        assert config.auto_complete_on_subtasks is False
        assert config.sync_changes_to_tracker is False


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_default_rules(self):
        """Test creating default rules."""
        rules = create_default_rules()
        assert len(rules) >= 4  # At least the basic rules

    def test_evaluate_story_rules(self):
        """Test convenience function for story evaluation."""
        story = UserStory(
            id=StoryId("US-001"),
            title="Test Story",
            subtasks=[Subtask(name="Task", status=Status.DONE)],
        )

        result = evaluate_story_rules(story, dry_run=True)

        assert result.entities_evaluated == 1

    def test_evaluate_epic_rules(self):
        """Test convenience function for epic evaluation."""
        epic = Epic(
            key=IssueKey("EPIC-001"),
            title="Test Epic",
            stories=[UserStory(id=StoryId("US-001"), title="Story", status=Status.DONE)],
        )

        result = evaluate_epic_rules(epic, dry_run=True)

        assert result.entities_evaluated == 1


class TestWorkflowExecutionResult:
    """Tests for WorkflowExecutionResult class."""

    def test_success_by_default(self):
        """Test success is True by default."""
        result = WorkflowExecutionResult()
        assert result.success is True

    def test_counts(self):
        """Test counting properties."""
        result = WorkflowExecutionResult()
        result.entities_evaluated = 5
        result.rules_matched = 3
        result.actions_executed = 6

        assert result.entities_evaluated == 5
        assert result.rules_matched == 3
        assert result.actions_executed == 6
