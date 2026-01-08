"""
Workflow Automation Rules - Automated state transitions and actions.

This module provides workflow automation:
- If all subtasks Done → Story Done
- If any subtask In Progress → Story In Progress
- If story blocked → Subtasks blocked
- Custom rule definitions
- Rule evaluation and action execution
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from spectryn.core.domain.enums import Status


if TYPE_CHECKING:
    from spectryn.core.domain.entities import Epic, UserStory
    from spectryn.core.ports.issue_tracker import IssueTrackerPort


logger = logging.getLogger(__name__)


# Protocol for entities that can be evaluated by workflow rules
@runtime_checkable
class WorkflowEntity(Protocol):
    """Protocol for entities that workflow rules can operate on."""

    status: Status


# More permissive type for duck-typed entity access
EntityLike = object  # Used where we need duck-typed attribute access


class RuleType(Enum):
    """Types of workflow rules."""

    # Subtask-based rules
    ALL_SUBTASKS_DONE = "all_subtasks_done"  # All subtasks done → parent done
    ANY_SUBTASK_IN_PROGRESS = "any_subtask_in_progress"  # Any subtask started → parent in progress
    ALL_SUBTASKS_BLOCKED = "all_subtasks_blocked"  # All subtasks blocked → parent blocked

    # Story-based rules
    ALL_STORIES_DONE = "all_stories_done"  # All stories done → epic done
    ANY_STORY_IN_PROGRESS = "any_story_in_progress"  # Any story started → epic in progress

    # Status propagation
    PARENT_BLOCKED_CHILDREN_BLOCKED = "parent_blocked"  # Parent blocked → children blocked
    PARENT_CANCELLED_CHILDREN_CANCELLED = (
        "parent_cancelled"  # Parent cancelled → children cancelled
    )

    # Time-based rules
    OVERDUE_TO_BLOCKED = "overdue_blocked"  # Past due date → blocked

    # Custom rule
    CUSTOM = "custom"

    @classmethod
    def from_string(cls, value: str) -> "RuleType":
        """Parse rule type from string."""
        value_lower = value.lower().strip().replace("-", "_").replace(" ", "_")
        for member in cls:
            if member.value == value_lower:
                return member
        return cls.CUSTOM


class RuleAction(Enum):
    """Actions that can be taken when a rule matches."""

    SET_STATUS = "set_status"  # Change status
    ADD_LABEL = "add_label"  # Add a label
    REMOVE_LABEL = "remove_label"  # Remove a label
    ADD_COMMENT = "add_comment"  # Add a comment
    SET_ASSIGNEE = "set_assignee"  # Set assignee
    CLEAR_ASSIGNEE = "clear_assignee"  # Clear assignee
    SET_PRIORITY = "set_priority"  # Change priority
    NOTIFY = "notify"  # Send notification (webhook, etc.)
    CUSTOM = "custom"  # Custom action


@dataclass
class RuleCondition:
    """A condition that must be met for a rule to trigger."""

    field: str  # Field to check (status, subtasks, labels, etc.)
    operator: str  # Comparison operator (eq, ne, gt, lt, contains, all, any)
    value: object  # Value to compare against

    def evaluate(self, entity: EntityLike) -> bool:
        """
        Evaluate the condition against an entity.

        Args:
            entity: Entity to evaluate (UserStory, Epic, Subtask)

        Returns:
            True if condition is met
        """
        # Get field value
        if hasattr(entity, self.field):
            actual_value = getattr(entity, self.field)
        else:
            return False

        # Apply operator
        if self.operator == "eq":
            return actual_value == self.value
        if self.operator == "ne":
            return actual_value != self.value
        if self.operator == "gt":
            return actual_value > self.value
        if self.operator == "lt":
            return actual_value < self.value
        if self.operator == "contains":
            return self.value in actual_value
        if self.operator == "not_contains":
            return self.value not in actual_value
        if self.operator == "all":
            # All items match a condition
            if isinstance(actual_value, list):
                return all(self._check_item(item) for item in actual_value)
        if self.operator == "any":
            # Any item matches a condition
            if isinstance(actual_value, list):
                return any(self._check_item(item) for item in actual_value)
        if self.operator == "none":
            # No items match a condition
            if isinstance(actual_value, list):
                return not any(self._check_item(item) for item in actual_value)

        return False

    def _check_item(self, item: object) -> bool:
        """Check a single item against the value condition."""
        if isinstance(self.value, dict):
            # Value is a sub-condition
            for field_name, expected in self.value.items():
                if hasattr(item, field_name):
                    if getattr(item, field_name) != expected:
                        return False
            return True
        return item == self.value


@dataclass
class RuleActionSpec:
    """Specification for an action to execute."""

    action: RuleAction
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleActionSpec":
        """Create from dictionary."""
        return cls(
            action=RuleAction(data.get("action", "set_status")),
            params=data.get("params", {}),
        )


@dataclass
class WorkflowRule:
    """
    A workflow automation rule.

    Rules define conditions and actions for automated state changes.
    """

    id: str
    name: str
    rule_type: RuleType

    # When should this rule be evaluated
    trigger: str = "on_change"  # on_change, on_sync, scheduled

    # Conditions that must all be true
    conditions: list[RuleCondition] = field(default_factory=list)

    # Actions to execute when conditions are met
    actions: list[RuleActionSpec] = field(default_factory=list)

    # Rule metadata
    enabled: bool = True
    priority: int = 0  # Higher priority rules evaluated first
    description: str = ""

    def matches(self, entity: EntityLike) -> bool:
        """
        Check if all conditions match.

        Args:
            entity: Entity to check

        Returns:
            True if all conditions match
        """
        if not self.enabled:
            return False

        # For built-in rule types, use predefined logic
        if self.rule_type != RuleType.CUSTOM:
            return self._evaluate_builtin(entity)

        # For custom rules, evaluate all conditions
        return all(cond.evaluate(entity) for cond in self.conditions)

    def _evaluate_builtin(self, entity: EntityLike) -> bool:
        """Evaluate built-in rule types."""
        if self.rule_type == RuleType.ALL_SUBTASKS_DONE:
            return self._check_all_subtasks_done(entity)
        if self.rule_type == RuleType.ANY_SUBTASK_IN_PROGRESS:
            return self._check_any_subtask_in_progress(entity)
        if self.rule_type == RuleType.ALL_STORIES_DONE:
            return self._check_all_stories_done(entity)
        if self.rule_type == RuleType.ANY_STORY_IN_PROGRESS:
            return self._check_any_story_in_progress(entity)
        if self.rule_type == RuleType.PARENT_BLOCKED_CHILDREN_BLOCKED:
            return self._check_parent_blocked(entity)
        return False

    def _check_all_subtasks_done(self, entity: EntityLike) -> bool:
        """Check if all subtasks are done."""
        if not hasattr(entity, "subtasks"):
            return False
        subtasks = entity.subtasks
        if not subtasks:
            return False
        return all(st.status.is_complete() for st in subtasks)

    def _check_any_subtask_in_progress(self, entity: EntityLike) -> bool:
        """Check if any subtask is in progress."""
        if not hasattr(entity, "subtasks"):
            return False
        subtasks = entity.subtasks
        return any(st.status == Status.IN_PROGRESS for st in subtasks)

    def _check_all_stories_done(self, entity: EntityLike) -> bool:
        """Check if all stories in epic are done."""
        if not hasattr(entity, "stories"):
            return False
        stories = entity.stories
        if not stories:
            return False
        return all(s.status.is_complete() for s in stories)

    def _check_any_story_in_progress(self, entity: EntityLike) -> bool:
        """Check if any story in epic is in progress."""
        if not hasattr(entity, "stories"):
            return False
        return any(s.status == Status.IN_PROGRESS for s in entity.stories)

    def _check_parent_blocked(self, entity: EntityLike) -> bool:
        """Check if parent is blocked."""
        if hasattr(entity, "status"):
            return entity.status == Status.BLOCKED
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "rule_type": self.rule_type.value,
            "trigger": self.trigger,
            "enabled": self.enabled,
            "priority": self.priority,
            "description": self.description,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class RuleExecutionResult:
    """Result of executing a rule."""

    rule_id: str
    rule_name: str
    matched: bool = False
    actions_executed: list[str] = field(default_factory=list)
    changes_made: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class WorkflowExecutionResult:
    """Result of running all workflow rules."""

    success: bool = True
    dry_run: bool = False

    # Counts
    entities_evaluated: int = 0
    rules_matched: int = 0
    actions_executed: int = 0

    # Details
    rule_results: list[RuleExecutionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Changes
    status_changes: list[dict[str, Any]] = field(default_factory=list)


class WorkflowEngine:
    """
    Engine for evaluating and executing workflow rules.
    """

    def __init__(
        self,
        tracker: "IssueTrackerPort | None" = None,
        rules: list[WorkflowRule] | None = None,
    ):
        """
        Initialize the workflow engine.

        Args:
            tracker: Issue tracker adapter (optional)
            rules: List of rules to use (optional)
        """
        self.tracker = tracker
        self.rules = rules or self._get_default_rules()
        self.logger = logging.getLogger("WorkflowEngine")

    def _get_default_rules(self) -> list[WorkflowRule]:
        """Get default workflow rules."""
        return [
            # All subtasks done → Story done
            WorkflowRule(
                id="all-subtasks-done",
                name="Complete story when all subtasks done",
                rule_type=RuleType.ALL_SUBTASKS_DONE,
                actions=[
                    RuleActionSpec(
                        action=RuleAction.SET_STATUS,
                        params={"status": Status.DONE},
                    )
                ],
                priority=10,
            ),
            # Any subtask in progress → Story in progress
            WorkflowRule(
                id="any-subtask-in-progress",
                name="Start story when any subtask starts",
                rule_type=RuleType.ANY_SUBTASK_IN_PROGRESS,
                actions=[
                    RuleActionSpec(
                        action=RuleAction.SET_STATUS,
                        params={"status": Status.IN_PROGRESS},
                    )
                ],
                priority=5,
            ),
            # All stories done → Epic done
            WorkflowRule(
                id="all-stories-done",
                name="Complete epic when all stories done",
                rule_type=RuleType.ALL_STORIES_DONE,
                actions=[
                    RuleActionSpec(
                        action=RuleAction.SET_STATUS,
                        params={"status": Status.DONE},
                    )
                ],
                priority=10,
            ),
            # Any story in progress → Epic in progress
            WorkflowRule(
                id="any-story-in-progress",
                name="Start epic when any story starts",
                rule_type=RuleType.ANY_STORY_IN_PROGRESS,
                actions=[
                    RuleActionSpec(
                        action=RuleAction.SET_STATUS,
                        params={"status": Status.IN_PROGRESS},
                    )
                ],
                priority=5,
            ),
        ]

    def evaluate_story(
        self,
        story: "UserStory",
        dry_run: bool = True,
    ) -> WorkflowExecutionResult:
        """
        Evaluate workflow rules for a story.

        Args:
            story: Story to evaluate
            dry_run: If True, don't make changes

        Returns:
            WorkflowExecutionResult
        """
        result = WorkflowExecutionResult(dry_run=dry_run)
        result.entities_evaluated = 1

        # Sort rules by priority (higher first)
        sorted_rules = sorted(self.rules, key=lambda r: -r.priority)

        for rule in sorted_rules:
            rule_result = self._evaluate_rule(rule, story, dry_run)
            result.rule_results.append(rule_result)

            if rule_result.matched:
                result.rules_matched += 1
                result.actions_executed += len(rule_result.actions_executed)

                if rule_result.changes_made:
                    result.status_changes.append(
                        {
                            "story_id": str(story.id),
                            "rule": rule.name,
                            "changes": rule_result.changes_made,
                        }
                    )

            if rule_result.error:
                result.errors.append(rule_result.error)
                result.success = False

        return result

    def evaluate_epic(
        self,
        epic: "Epic",
        dry_run: bool = True,
    ) -> WorkflowExecutionResult:
        """
        Evaluate workflow rules for an epic.

        Args:
            epic: Epic to evaluate
            dry_run: If True, don't make changes

        Returns:
            WorkflowExecutionResult
        """
        result = WorkflowExecutionResult(dry_run=dry_run)
        result.entities_evaluated = 1

        # Sort rules by priority (higher first)
        sorted_rules = sorted(self.rules, key=lambda r: -r.priority)

        for rule in sorted_rules:
            rule_result = self._evaluate_rule(rule, epic, dry_run)
            result.rule_results.append(rule_result)

            if rule_result.matched:
                result.rules_matched += 1
                result.actions_executed += len(rule_result.actions_executed)

                if rule_result.changes_made:
                    result.status_changes.append(
                        {
                            "epic_key": str(epic.key),
                            "rule": rule.name,
                            "changes": rule_result.changes_made,
                        }
                    )

            if rule_result.error:
                result.errors.append(rule_result.error)
                result.success = False

        return result

    def _evaluate_rule(
        self,
        rule: WorkflowRule,
        entity: EntityLike,
        dry_run: bool,
    ) -> RuleExecutionResult:
        """Evaluate a single rule against an entity."""
        result = RuleExecutionResult(rule_id=rule.id, rule_name=rule.name)

        try:
            if rule.matches(entity):
                result.matched = True

                # Execute actions
                for action_spec in rule.actions:
                    action_name = self._execute_action(entity, action_spec, dry_run)
                    if action_name:
                        result.actions_executed.append(action_name)

                        # Record changes
                        if action_spec.action == RuleAction.SET_STATUS:
                            new_status = action_spec.params.get("status")
                            if new_status:
                                result.changes_made["status"] = {
                                    "from": entity.status.name
                                    if hasattr(entity, "status")
                                    else None,
                                    "to": new_status.name
                                    if hasattr(new_status, "name")
                                    else str(new_status),
                                }

        except Exception as e:
            result.error = f"Error evaluating rule {rule.name}: {e}"

        return result

    def _execute_action(
        self,
        entity: EntityLike,
        action_spec: RuleActionSpec,
        dry_run: bool,
    ) -> str | None:
        """Execute a rule action."""
        action = action_spec.action
        params = action_spec.params

        if action == RuleAction.SET_STATUS:
            new_status = params.get("status")
            if new_status:
                if dry_run:
                    self.logger.info(f"[DRY-RUN] Would set status to {new_status}")
                else:
                    entity.status = new_status
                return f"set_status:{new_status}"

        if action == RuleAction.ADD_LABEL:
            label = params.get("label")
            if label and hasattr(entity, "labels"):
                if dry_run:
                    self.logger.info(f"[DRY-RUN] Would add label {label}")
                elif label not in entity.labels:
                    entity.labels.append(label)
                return f"add_label:{label}"

        if action == RuleAction.REMOVE_LABEL:
            label = params.get("label")
            if label and hasattr(entity, "labels"):
                if dry_run:
                    self.logger.info(f"[DRY-RUN] Would remove label {label}")
                elif label in entity.labels:
                    entity.labels.remove(label)
                return f"remove_label:{label}"

        return None


@dataclass
class WorkflowConfig:
    """Configuration for workflow automation."""

    enabled: bool = True
    rules: list[WorkflowRule] = field(default_factory=list)

    # Built-in rule toggles
    auto_complete_on_subtasks: bool = True  # All subtasks done → story done
    auto_start_on_subtask: bool = True  # Any subtask in progress → story in progress
    auto_complete_epic_on_stories: bool = True  # All stories done → epic done
    auto_start_epic_on_story: bool = True  # Any story in progress → epic in progress

    # Sync behavior
    apply_on_sync: bool = True  # Apply rules during sync
    sync_changes_to_tracker: bool = True  # Push rule-based changes to tracker


def create_default_rules() -> list[WorkflowRule]:
    """Create the default set of workflow rules."""
    engine = WorkflowEngine()
    return engine._get_default_rules()


def evaluate_story_rules(
    story: "UserStory",
    rules: list[WorkflowRule] | None = None,
    dry_run: bool = True,
) -> WorkflowExecutionResult:
    """
    Convenience function to evaluate rules for a story.

    Args:
        story: Story to evaluate
        rules: Optional custom rules
        dry_run: If True, don't make changes

    Returns:
        WorkflowExecutionResult
    """
    engine = WorkflowEngine(rules=rules)
    return engine.evaluate_story(story, dry_run)


def evaluate_epic_rules(
    epic: "Epic",
    rules: list[WorkflowRule] | None = None,
    dry_run: bool = True,
) -> WorkflowExecutionResult:
    """
    Convenience function to evaluate rules for an epic.

    Args:
        epic: Epic to evaluate
        rules: Optional custom rules
        dry_run: If True, don't make changes

    Returns:
        WorkflowExecutionResult
    """
    engine = WorkflowEngine(rules=rules)
    return engine.evaluate_epic(epic, dry_run)
