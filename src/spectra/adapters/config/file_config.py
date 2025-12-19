"""
File Config Provider - Load configuration from YAML or TOML files.

Supports:
- .spectra.yaml / .spectra.yml
- .spectra.toml
- pyproject.toml [tool.spectra] section

Config file search order:
1. Explicit path (--config flag)
2. Current working directory
3. User home directory
"""

import sys
from pathlib import Path
from typing import Any, ClassVar

# Import ConfigFileError from centralized module and re-export for backward compatibility
from spectra.core.exceptions import ConfigFileError
from spectra.core.ports.config_provider import (
    AlertsConfig,
    AppConfig,
    ArchivalConfig,
    AssigneesConfig,
    BehaviorConfig,
    CapacityConfig,
    ComponentsConfig,
    ConfigProviderPort,
    ContentConfig,
    CustomFieldsConfig,
    DependenciesConfig,
    DevelopmentConfig,
    DocumentationConfig,
    DueDatesConfig,
    EnvironmentsConfig,
    EpicConfig,
    EstimationConfig,
    ExternalLinksConfig,
    FormattingConfig,
    IssueTypesConfig,
    LabelsConfig,
    NamingConfig,
    PrioritiesConfig,
    QualityConfig,
    SchedulingConfig,
    SecurityConfig,
    SprintsConfig,
    StatusesConfig,
    SubtasksConfig,
    SyncConfig,
    TemplatesConfig,
    TrackerConfig,
    ValidationConfig,
    VersionsConfig,
    WorkflowConfig,
)


# TOML support: use stdlib tomllib (3.11+) or tomli fallback (3.10)
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# YAML support
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# ConfigFileError is now imported from core.exceptions and re-exported above
# for backward compatibility. See core/exceptions.py for definition.


class FileConfigProvider(ConfigProviderPort):
    """
    Configuration provider that loads from YAML or TOML config files.

    Supports multiple config file formats and locations, with clear
    error messages for invalid configurations.
    """

    CONFIG_FILES: ClassVar[list[str]] = [
        ".spectra.yaml",
        ".spectra.yml",
        ".spectra.toml",
    ]

    def __init__(
        self,
        config_path: Path | None = None,
        cli_overrides: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the file config provider.

        Args:
            config_path: Explicit path to config file (optional)
            cli_overrides: Command line argument overrides
        """
        self._config_path = config_path
        self._cli_overrides = cli_overrides or {}
        self._values: dict[str, Any] = {}
        self._loaded_from: Path | None = None
        self._load_errors: list[str] = []

        # Load configuration
        self._load_config()
        self._apply_cli_overrides()

    # -------------------------------------------------------------------------
    # ConfigProviderPort Implementation
    # -------------------------------------------------------------------------

    @property
    def name(self) -> str:
        if self._loaded_from:
            return f"File ({self._loaded_from.name})"
        return "File"

    @property
    def config_file_path(self) -> Path | None:
        """Get the path to the loaded config file."""
        return self._loaded_from

    def load(self) -> AppConfig:
        """Load complete configuration."""
        tracker = TrackerConfig(
            url=self._get_nested("jira.url", ""),
            email=self._get_nested("jira.email", ""),
            api_token=self._get_nested("jira.api_token", ""),
            project_key=self._get_nested("jira.project", None),
            story_points_field=self._get_nested("jira.story_points_field", "customfield_10014"),
        )

        sync = SyncConfig(
            dry_run=not self._get_nested("sync.execute", False),
            confirm_changes=not self._get_nested("sync.no_confirm", False),
            verbose=self._get_nested("sync.verbose", False),
            sync_descriptions=self._get_nested("sync.descriptions", True),
            sync_subtasks=self._get_nested("sync.subtasks", True),
            sync_comments=self._get_nested("sync.comments", True),
            sync_statuses=self._get_nested("sync.statuses", True),
            story_filter=self._get_nested("sync.story_filter", None),
            export_path=self._get_nested("sync.export_path", None),
        )

        # Load validation configuration with all nested sections
        validation = self._load_validation_config()

        return AppConfig(
            tracker=tracker,
            sync=sync,
            validation=validation,
            markdown_path=self._get_nested("markdown", None),
            epic_key=self._get_nested("epic", None),
        )

    def _load_validation_config(self) -> ValidationConfig:
        """Load complete validation configuration from nested settings."""
        v = "validation"  # Prefix for all validation settings

        # Issue Types
        issue_types = IssueTypesConfig(
            allowed=self._get_nested(f"{v}.issue_types.allowed", ["Story", "User Story"]),
            default=self._get_nested(f"{v}.issue_types.default", "User Story"),
            aliases=self._get_nested(f"{v}.issue_types.aliases", IssueTypesConfig().aliases),
        )

        # Naming
        naming = NamingConfig(
            allowed_id_prefixes=self._get_nested(f"{v}.naming.allowed_id_prefixes", []),
            id_pattern=self._get_nested(f"{v}.naming.id_pattern", ""),
            require_sequential_ids=self._get_nested(f"{v}.naming.require_sequential_ids", False),
            normalize_ids_uppercase=self._get_nested(f"{v}.naming.normalize_ids_uppercase", True),
            epic_id_pattern=self._get_nested(f"{v}.naming.epic_id_pattern", ""),
            title_case=self._get_nested(f"{v}.naming.title_case", ""),
        )

        # Content
        content = ContentConfig(
            require_description=self._get_nested(f"{v}.content.require_description", False),
            description_min_length=self._get_nested(f"{v}.content.description_min_length", 0),
            description_max_length=self._get_nested(f"{v}.content.description_max_length", 0),
            require_user_story_format=self._get_nested(
                f"{v}.content.require_user_story_format", False
            ),
            user_story_roles=self._get_nested(f"{v}.content.user_story_roles", []),
            title_min_length=self._get_nested(f"{v}.content.title_min_length", 1),
            title_max_length=self._get_nested(f"{v}.content.title_max_length", 0),
            title_pattern=self._get_nested(f"{v}.content.title_pattern", ""),
            title_forbidden_words=self._get_nested(f"{v}.content.title_forbidden_words", []),
            title_required_words=self._get_nested(f"{v}.content.title_required_words", []),
            require_acceptance_criteria=self._get_nested(
                f"{v}.content.require_acceptance_criteria", False
            ),
            min_acceptance_criteria=self._get_nested(f"{v}.content.min_acceptance_criteria", 0),
            max_acceptance_criteria=self._get_nested(f"{v}.content.max_acceptance_criteria", 0),
            ac_format=self._get_nested(f"{v}.content.ac_format", ""),
            require_technical_notes=self._get_nested(f"{v}.content.require_technical_notes", False),
            technical_notes_min_length=self._get_nested(
                f"{v}.content.technical_notes_min_length", 0
            ),
            require_dependencies=self._get_nested(f"{v}.content.require_dependencies", False),
            max_dependencies=self._get_nested(f"{v}.content.max_dependencies", 0),
            require_links=self._get_nested(f"{v}.content.require_links", False),
            min_links=self._get_nested(f"{v}.content.min_links", 0),
            max_links=self._get_nested(f"{v}.content.max_links", 0),
            allowed_link_types=self._get_nested(f"{v}.content.allowed_link_types", []),
            require_related_commits=self._get_nested(f"{v}.content.require_related_commits", False),
        )

        # Estimation
        estimation = EstimationConfig(
            require_story_points=self._get_nested(f"{v}.estimation.require_story_points", False),
            min_story_points=self._get_nested(f"{v}.estimation.min_story_points", 0),
            max_story_points=self._get_nested(f"{v}.estimation.max_story_points", 0),
            allowed_story_points=self._get_nested(f"{v}.estimation.allowed_story_points", []),
            fibonacci_only=self._get_nested(f"{v}.estimation.fibonacci_only", False),
            default_story_points=self._get_nested(f"{v}.estimation.default_story_points", 0),
            require_time_estimate=self._get_nested(f"{v}.estimation.require_time_estimate", False),
            time_estimate_unit=self._get_nested(f"{v}.estimation.time_estimate_unit", "hours"),
            max_time_estimate=self._get_nested(f"{v}.estimation.max_time_estimate", 0),
        )

        # Subtasks
        subtasks = SubtasksConfig(
            require_subtasks=self._get_nested(f"{v}.subtasks.require_subtasks", False),
            min_subtasks=self._get_nested(f"{v}.subtasks.min_subtasks", 0),
            max_subtasks=self._get_nested(f"{v}.subtasks.max_subtasks", 0),
            subtask_title_pattern=self._get_nested(f"{v}.subtasks.subtask_title_pattern", ""),
            subtask_title_min_length=self._get_nested(f"{v}.subtasks.subtask_title_min_length", 1),
            subtask_title_max_length=self._get_nested(f"{v}.subtasks.subtask_title_max_length", 0),
            require_subtask_estimates=self._get_nested(
                f"{v}.subtasks.require_subtask_estimates", False
            ),
            allowed_subtask_statuses=self._get_nested(f"{v}.subtasks.allowed_subtask_statuses", []),
            require_subtask_assignee=self._get_nested(
                f"{v}.subtasks.require_subtask_assignee", False
            ),
        )

        # Statuses
        statuses = StatusesConfig(
            allowed=self._get_nested(f"{v}.statuses.allowed", []),
            default=self._get_nested(f"{v}.statuses.default", "Planned"),
            require_status=self._get_nested(f"{v}.statuses.require_status", False),
            aliases=self._get_nested(f"{v}.statuses.aliases", StatusesConfig().aliases),
            allowed_transitions=self._get_nested(f"{v}.statuses.allowed_transitions", {}),
            require_status_emoji=self._get_nested(f"{v}.statuses.require_status_emoji", False),
        )

        # Priorities
        priorities = PrioritiesConfig(
            allowed=self._get_nested(f"{v}.priorities.allowed", []),
            default=self._get_nested(f"{v}.priorities.default", "Medium"),
            require_priority=self._get_nested(f"{v}.priorities.require_priority", False),
            aliases=self._get_nested(f"{v}.priorities.aliases", PrioritiesConfig().aliases),
            require_priority_emoji=self._get_nested(
                f"{v}.priorities.require_priority_emoji", False
            ),
        )

        # Labels
        labels = LabelsConfig(
            required=self._get_nested(f"{v}.labels.required", []),
            allowed=self._get_nested(f"{v}.labels.allowed", []),
            forbidden=self._get_nested(f"{v}.labels.forbidden", []),
            min_labels=self._get_nested(f"{v}.labels.min_labels", 0),
            max_labels=self._get_nested(f"{v}.labels.max_labels", 0),
            label_pattern=self._get_nested(f"{v}.labels.label_pattern", ""),
            label_prefix=self._get_nested(f"{v}.labels.label_prefix", ""),
            case_sensitive=self._get_nested(f"{v}.labels.case_sensitive", False),
        )

        # Components
        components = ComponentsConfig(
            required=self._get_nested(f"{v}.components.required", []),
            allowed=self._get_nested(f"{v}.components.allowed", []),
            min_components=self._get_nested(f"{v}.components.min_components", 0),
            max_components=self._get_nested(f"{v}.components.max_components", 0),
            require_component=self._get_nested(f"{v}.components.require_component", False),
        )

        # Assignees
        assignees = AssigneesConfig(
            require_assignee=self._get_nested(f"{v}.assignees.require_assignee", False),
            allowed=self._get_nested(f"{v}.assignees.allowed", []),
            default=self._get_nested(f"{v}.assignees.default", ""),
            max_assignees=self._get_nested(f"{v}.assignees.max_assignees", 1),
        )

        # Sprints
        sprints = SprintsConfig(
            require_sprint=self._get_nested(f"{v}.sprints.require_sprint", False),
            allowed=self._get_nested(f"{v}.sprints.allowed", []),
            default=self._get_nested(f"{v}.sprints.default", ""),
            sprint_pattern=self._get_nested(f"{v}.sprints.sprint_pattern", ""),
        )

        # Versions
        versions = VersionsConfig(
            require_version=self._get_nested(f"{v}.versions.require_version", False),
            allowed=self._get_nested(f"{v}.versions.allowed", []),
            version_pattern=self._get_nested(f"{v}.versions.version_pattern", ""),
        )

        # Due Dates
        due_dates = DueDatesConfig(
            require_due_date=self._get_nested(f"{v}.due_dates.require_due_date", False),
            max_days_in_future=self._get_nested(f"{v}.due_dates.max_days_in_future", 0),
            min_days_in_future=self._get_nested(f"{v}.due_dates.min_days_in_future", 0),
            date_format=self._get_nested(f"{v}.due_dates.date_format", "YYYY-MM-DD"),
        )

        # Epic
        epic = EpicConfig(
            max_stories=self._get_nested(f"{v}.epic.max_stories", 0),
            min_stories=self._get_nested(f"{v}.epic.min_stories", 0),
            require_summary=self._get_nested(f"{v}.epic.require_summary", False),
            require_description=self._get_nested(f"{v}.epic.require_description", False),
            max_total_story_points=self._get_nested(f"{v}.epic.max_total_story_points", 0),
            require_epic_owner=self._get_nested(f"{v}.epic.require_epic_owner", False),
            max_in_progress_stories=self._get_nested(f"{v}.epic.max_in_progress_stories", 0),
        )

        # Custom Fields
        custom_fields = CustomFieldsConfig(
            mappings=self._get_nested(f"{v}.custom_fields.mappings", {}),
            required=self._get_nested(f"{v}.custom_fields.required", []),
            aliases=self._get_nested(f"{v}.custom_fields.aliases", CustomFieldsConfig().aliases),
        )

        # Formatting
        formatting = FormattingConfig(
            require_status_emoji=self._get_nested(f"{v}.formatting.require_status_emoji", False),
            require_priority_emoji=self._get_nested(
                f"{v}.formatting.require_priority_emoji", False
            ),
            allowed_header_levels=self._get_nested(
                f"{v}.formatting.allowed_header_levels", [1, 2, 3]
            ),
            require_metadata_table=self._get_nested(
                f"{v}.formatting.require_metadata_table", False
            ),
            allowed_markdown_elements=self._get_nested(
                f"{v}.formatting.allowed_markdown_elements", []
            ),
            max_heading_depth=self._get_nested(f"{v}.formatting.max_heading_depth", 4),
        )

        # External Links
        external_links = ExternalLinksConfig(
            require_external_links=self._get_nested(
                f"{v}.external_links.require_external_links", False
            ),
            allowed_domains=self._get_nested(f"{v}.external_links.allowed_domains", []),
            forbidden_domains=self._get_nested(f"{v}.external_links.forbidden_domains", []),
            require_https=self._get_nested(f"{v}.external_links.require_https", True),
        )

        # Behavior
        behavior = BehaviorConfig(
            strict=self._get_nested(f"{v}.behavior.strict", False),
            fail_fast=self._get_nested(f"{v}.behavior.fail_fast", False),
            ignore_rules=self._get_nested(f"{v}.behavior.ignore_rules", []),
            warning_as_info=self._get_nested(f"{v}.behavior.warning_as_info", []),
            auto_fix_ids=self._get_nested(f"{v}.behavior.auto_fix_ids", False),
            auto_fix_statuses=self._get_nested(f"{v}.behavior.auto_fix_statuses", False),
            auto_fix_priorities=self._get_nested(f"{v}.behavior.auto_fix_priorities", False),
            auto_fix_case=self._get_nested(f"{v}.behavior.auto_fix_case", False),
            auto_add_defaults=self._get_nested(f"{v}.behavior.auto_add_defaults", False),
            show_suggestions=self._get_nested(f"{v}.behavior.show_suggestions", True),
            max_errors_shown=self._get_nested(f"{v}.behavior.max_errors_shown", 50),
            group_by_story=self._get_nested(f"{v}.behavior.group_by_story", True),
        )

        # Workflow
        workflow = WorkflowConfig(
            definition_of_done=self._get_nested(f"{v}.workflow.definition_of_done", []),
            ready_for_dev_criteria=self._get_nested(f"{v}.workflow.ready_for_dev_criteria", []),
            require_review=self._get_nested(f"{v}.workflow.require_review", False),
            require_qa_signoff=self._get_nested(f"{v}.workflow.require_qa_signoff", False),
            blocked_by_types=self._get_nested(f"{v}.workflow.blocked_by_types", []),
            max_blocked_days=self._get_nested(f"{v}.workflow.max_blocked_days", 0),
            require_parent=self._get_nested(f"{v}.workflow.require_parent", False),
            require_epic_link=self._get_nested(f"{v}.workflow.require_epic_link", False),
            allowed_parent_types=self._get_nested(f"{v}.workflow.allowed_parent_types", []),
        )

        # Scheduling
        scheduling = SchedulingConfig(
            max_story_age_days=self._get_nested(f"{v}.scheduling.max_story_age_days", 0),
            stale_after_days=self._get_nested(f"{v}.scheduling.stale_after_days", 0),
            require_start_date=self._get_nested(f"{v}.scheduling.require_start_date", False),
            max_duration_days=self._get_nested(f"{v}.scheduling.max_duration_days", 0),
            work_days_only=self._get_nested(f"{v}.scheduling.work_days_only", False),
            sla_days=self._get_nested(f"{v}.scheduling.sla_days", 0),
            warn_approaching_sla_days=self._get_nested(
                f"{v}.scheduling.warn_approaching_sla_days", 0
            ),
            require_end_date=self._get_nested(f"{v}.scheduling.require_end_date", False),
        )

        # Development
        development = DevelopmentConfig(
            branch_naming_pattern=self._get_nested(f"{v}.development.branch_naming_pattern", ""),
            require_branch_link=self._get_nested(f"{v}.development.require_branch_link", False),
            require_pr_link=self._get_nested(f"{v}.development.require_pr_link", False),
            commit_message_pattern=self._get_nested(f"{v}.development.commit_message_pattern", ""),
            require_code_review=self._get_nested(f"{v}.development.require_code_review", False),
            allowed_branch_prefixes=self._get_nested(
                f"{v}.development.allowed_branch_prefixes", []
            ),
            require_merge_before_done=self._get_nested(
                f"{v}.development.require_merge_before_done", False
            ),
        )

        # Quality
        quality = QualityConfig(
            require_test_cases=self._get_nested(f"{v}.quality.require_test_cases", False),
            min_test_cases=self._get_nested(f"{v}.quality.min_test_cases", 0),
            require_test_plan=self._get_nested(f"{v}.quality.require_test_plan", False),
            bug_severity_levels=self._get_nested(f"{v}.quality.bug_severity_levels", []),
            require_reproduction_steps=self._get_nested(
                f"{v}.quality.require_reproduction_steps", False
            ),
            require_expected_behavior=self._get_nested(
                f"{v}.quality.require_expected_behavior", False
            ),
            require_actual_behavior=self._get_nested(f"{v}.quality.require_actual_behavior", False),
            require_environment_info=self._get_nested(
                f"{v}.quality.require_environment_info", False
            ),
            require_screenshots=self._get_nested(f"{v}.quality.require_screenshots", False),
        )

        # Documentation
        documentation = DocumentationConfig(
            require_api_docs=self._get_nested(f"{v}.documentation.require_api_docs", False),
            require_changelog_entry=self._get_nested(
                f"{v}.documentation.require_changelog_entry", False
            ),
            require_release_notes=self._get_nested(
                f"{v}.documentation.require_release_notes", False
            ),
            documentation_link_required=self._get_nested(
                f"{v}.documentation.documentation_link_required", False
            ),
            readme_update_required=self._get_nested(
                f"{v}.documentation.readme_update_required", False
            ),
            require_user_docs=self._get_nested(f"{v}.documentation.require_user_docs", False),
            docs_location_pattern=self._get_nested(f"{v}.documentation.docs_location_pattern", ""),
        )

        # Security
        security = SecurityConfig(
            require_security_review=self._get_nested(
                f"{v}.security.require_security_review", False
            ),
            confidentiality_levels=self._get_nested(f"{v}.security.confidentiality_levels", []),
            require_data_classification=self._get_nested(
                f"{v}.security.require_data_classification", False
            ),
            pii_handling_required=self._get_nested(f"{v}.security.pii_handling_required", False),
            require_threat_model=self._get_nested(f"{v}.security.require_threat_model", False),
            compliance_tags=self._get_nested(f"{v}.security.compliance_tags", []),
            require_vulnerability_scan=self._get_nested(
                f"{v}.security.require_vulnerability_scan", False
            ),
            security_labels=self._get_nested(f"{v}.security.security_labels", []),
        )

        # Templates
        templates = TemplatesConfig(
            story_template=self._get_nested(f"{v}.templates.story_template", ""),
            bug_template=self._get_nested(f"{v}.templates.bug_template", ""),
            epic_template=self._get_nested(f"{v}.templates.epic_template", ""),
            task_template=self._get_nested(f"{v}.templates.task_template", ""),
            enforce_template=self._get_nested(f"{v}.templates.enforce_template", False),
            allowed_sections=self._get_nested(f"{v}.templates.allowed_sections", []),
            required_sections=self._get_nested(f"{v}.templates.required_sections", []),
            section_order=self._get_nested(f"{v}.templates.section_order", []),
        )

        # Alerts
        alerts = AlertsConfig(
            alert_on_blocked=self._get_nested(f"{v}.alerts.alert_on_blocked", False),
            alert_on_stale=self._get_nested(f"{v}.alerts.alert_on_stale", False),
            alert_threshold_days=self._get_nested(f"{v}.alerts.alert_threshold_days", 0),
            alert_on_over_estimate=self._get_nested(f"{v}.alerts.alert_on_over_estimate", False),
            watchers=self._get_nested(f"{v}.alerts.watchers", []),
            alert_on_unassigned=self._get_nested(f"{v}.alerts.alert_on_unassigned", False),
            alert_on_no_estimate=self._get_nested(f"{v}.alerts.alert_on_no_estimate", False),
            notification_channels=self._get_nested(f"{v}.alerts.notification_channels", []),
        )

        # Dependencies
        dependencies = DependenciesConfig(
            require_dependency_check=self._get_nested(
                f"{v}.dependencies.require_dependency_check", False
            ),
            max_dependencies=self._get_nested(f"{v}.dependencies.max_dependencies", 0),
            allow_circular_dependencies=self._get_nested(
                f"{v}.dependencies.allow_circular_dependencies", False
            ),
            dependency_types=self._get_nested(f"{v}.dependencies.dependency_types", []),
            cross_project_deps_allowed=self._get_nested(
                f"{v}.dependencies.cross_project_deps_allowed", True
            ),
            require_dependency_approval=self._get_nested(
                f"{v}.dependencies.require_dependency_approval", False
            ),
            blocked_dependency_types=self._get_nested(
                f"{v}.dependencies.blocked_dependency_types", []
            ),
        )

        # Archival
        archival = ArchivalConfig(
            auto_archive_after_days=self._get_nested(f"{v}.archival.auto_archive_after_days", 0),
            archive_cancelled=self._get_nested(f"{v}.archival.archive_cancelled", False),
            retention_days=self._get_nested(f"{v}.archival.retention_days", 0),
            exclude_from_archive=self._get_nested(f"{v}.archival.exclude_from_archive", []),
            archive_on_done=self._get_nested(f"{v}.archival.archive_on_done", False),
            cleanup_stale_branches=self._get_nested(f"{v}.archival.cleanup_stale_branches", False),
        )

        # Capacity
        capacity = CapacityConfig(
            max_stories_per_assignee=self._get_nested(f"{v}.capacity.max_stories_per_assignee", 0),
            max_points_per_sprint=self._get_nested(f"{v}.capacity.max_points_per_sprint", 0),
            warn_overload_threshold=self._get_nested(f"{v}.capacity.warn_overload_threshold", 0),
            require_capacity_check=self._get_nested(f"{v}.capacity.require_capacity_check", False),
            max_parallel_stories=self._get_nested(f"{v}.capacity.max_parallel_stories", 0),
            points_per_day=self._get_nested(f"{v}.capacity.points_per_day", 0.0),
        )

        # Environments
        environments = EnvironmentsConfig(
            allowed_environments=self._get_nested(f"{v}.environments.allowed_environments", []),
            require_environment=self._get_nested(f"{v}.environments.require_environment", False),
            environment_order=self._get_nested(f"{v}.environments.environment_order", []),
            require_rollback_plan=self._get_nested(
                f"{v}.environments.require_rollback_plan", False
            ),
            require_deployment_notes=self._get_nested(
                f"{v}.environments.require_deployment_notes", False
            ),
            production_approval_required=self._get_nested(
                f"{v}.environments.production_approval_required", False
            ),
        )

        return ValidationConfig(
            # Core sections
            issue_types=issue_types,
            naming=naming,
            content=content,
            estimation=estimation,
            subtasks=subtasks,
            statuses=statuses,
            priorities=priorities,
            labels=labels,
            components=components,
            assignees=assignees,
            sprints=sprints,
            versions=versions,
            due_dates=due_dates,
            epic=epic,
            custom_fields=custom_fields,
            formatting=formatting,
            external_links=external_links,
            behavior=behavior,
            # Extended sections
            workflow=workflow,
            scheduling=scheduling,
            development=development,
            quality=quality,
            documentation=documentation,
            security=security,
            templates=templates,
            alerts=alerts,
            dependencies=dependencies,
            archival=archival,
            capacity=capacity,
            environments=environments,
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        return self._get_nested(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        parts = key.split(".")
        target = self._values

        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]

        target[parts[-1]] = value

    def validate(self) -> list[str]:
        """Validate configuration with clear error messages."""
        errors = list(self._load_errors)

        # Check required Jira settings
        if not self._get_nested("jira.url"):
            errors.append(
                "Missing 'jira.url' - add to config file or set JIRA_URL environment variable"
            )
        if not self._get_nested("jira.email"):
            errors.append(
                "Missing 'jira.email' - add to config file or set JIRA_EMAIL environment variable"
            )
        if not self._get_nested("jira.api_token"):
            errors.append(
                "Missing 'jira.api_token' - add to config file or set JIRA_API_TOKEN environment variable"
            )

        return errors

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _get_nested(self, key: str, default: Any = None) -> Any:
        """Get a nested configuration value using dot notation."""
        # CLI overrides take precedence
        flat_key = key.replace(".", "_")
        if flat_key in self._cli_overrides and self._cli_overrides[flat_key] is not None:
            return self._cli_overrides[flat_key]

        # Navigate nested dict
        parts = key.split(".")
        value: Any = self._values

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value if value is not None else default

    def _load_config(self) -> None:
        """Load configuration from file."""
        config_file = self._find_config_file()
        if not config_file:
            return

        self._loaded_from = config_file

        try:
            if config_file.suffix in (".yaml", ".yml"):
                self._load_yaml(config_file)
            elif config_file.name == "pyproject.toml":
                self._load_pyproject_toml(config_file)
            elif config_file.suffix == ".toml":
                self._load_toml(config_file)
        except ConfigFileError as e:
            self._load_errors.append(str(e))
        except Exception as e:
            self._load_errors.append(f"{config_file}: Unexpected error: {e}")

    def _find_config_file(self) -> Path | None:
        """Find config file in standard locations."""
        # Explicit path
        if self._config_path:
            if self._config_path.exists():
                return self._config_path
            self._load_errors.append(f"Config file not found: {self._config_path}")
            return None

        # Search locations
        search_paths = [
            Path.cwd(),
            Path.home(),
        ]

        for base_path in search_paths:
            # Check explicit config files
            for config_name in self.CONFIG_FILES:
                config_path = base_path / config_name
                if config_path.exists():
                    return config_path

            # Check pyproject.toml
            pyproject = base_path / "pyproject.toml"
            if pyproject.exists() and self._has_spectra_section(pyproject):
                return pyproject

        return None

    def _has_spectra_section(self, pyproject_path: Path) -> bool:
        """Check if pyproject.toml has [tool.spectra] section."""
        if tomllib is None:
            return False

        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            return "spectra" in data.get("tool", {})
        except Exception:
            return False

    def _load_yaml(self, path: Path) -> None:
        """Load YAML config file."""
        if yaml is None:
            raise ConfigFileError(
                path,
                "PyYAML not installed. Install with: pip install pyyaml",
            )

        try:
            with path.open() as f:
                data = yaml.safe_load(f)
            if data:
                self._values = data
        except yaml.YAMLError as e:
            raise ConfigFileError(path, f"Invalid YAML syntax: {e}") from e

    def _load_toml(self, path: Path) -> None:
        """Load TOML config file."""
        if tomllib is None:
            raise ConfigFileError(
                path,
                "TOML support not available. Install with: pip install tomli",
            )

        try:
            with path.open("rb") as f:
                self._values = tomllib.load(f)
        except Exception as e:
            raise ConfigFileError(path, f"Invalid TOML syntax: {e}") from e

    def _load_pyproject_toml(self, path: Path) -> None:
        """Load config from pyproject.toml [tool.spectra] section."""
        if tomllib is None:
            raise ConfigFileError(
                path,
                "TOML support not available. Install with: pip install tomli",
            )

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            spectra_config = data.get("tool", {}).get("spectra", {})
            if spectra_config:
                self._values = spectra_config
        except Exception as e:
            raise ConfigFileError(path, f"Invalid TOML syntax: {e}") from e

    def _apply_cli_overrides(self) -> None:
        """Apply CLI argument overrides."""
        # Map CLI args to nested config keys
        cli_mapping = {
            "markdown": "markdown",
            "epic": "epic",
            "project": "jira.project",
            "jira_url": "jira.url",
            "story": "sync.story_filter",
            "execute": "sync.execute",
            "no_confirm": "sync.no_confirm",
            "verbose": "sync.verbose",
        }

        for cli_key, config_key in cli_mapping.items():
            if cli_key in self._cli_overrides and self._cli_overrides[cli_key] is not None:
                self.set(config_key, self._cli_overrides[cli_key])
