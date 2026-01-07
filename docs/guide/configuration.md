# Configuration

spectra supports multiple configuration sources with clear precedence rules.

## Configuration Precedence

Configuration is loaded in this order (highest priority first):

1. **CLI arguments** - Command line flags override all other sources
2. **Environment variables** - `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
3. **`.env` file** - In current directory or package directory
4. **Config files** - `.spectra.yaml`, `.spectra.toml`, or `pyproject.toml`

## Config File Locations

spectra searches for config files in this order:

1. Explicit path via `--config` flag
2. Current working directory
3. User home directory (`~`)

## Config File Formats

### YAML (Recommended)

Create `.spectra.yaml` or `.spectra.yml`:

```yaml
# Jira connection settings (required)
jira:
  url: https://your-company.atlassian.net
  email: your-email@company.com
  api_token: your-api-token
  project: PROJ  # Optional: default project key
  story_points_field: customfield_10014  # Optional: custom field ID

# Sync settings (optional)
sync:
  verbose: false
  execute: false  # Set to true for live mode (default: dry-run)
  no_confirm: false  # Set to true to skip confirmation prompts
  descriptions: true
  subtasks: true
  comments: true
  statuses: true

# Default paths (optional)
markdown: ./epics/my-epic.md
epic: PROJ-123
```

### TOML

Create `.spectra.toml`:

```toml
# Default paths
markdown = "./epics/my-epic.md"
epic = "PROJ-123"

# Jira connection settings
[jira]
url = "https://your-company.atlassian.net"
email = "your-email@company.com"
api_token = "your-api-token"
project = "PROJ"
story_points_field = "customfield_10014"

# Sync settings
[sync]
verbose = false
execute = false
no_confirm = false
descriptions = true
subtasks = true
comments = true
statuses = true
```

### pyproject.toml

Add a `[tool.spectra]` section to your project's `pyproject.toml`:

```toml
[tool.spectra]
epic = "PROJ-123"

[tool.spectra.jira]
url = "https://your-company.atlassian.net"
email = "your-email@company.com"
api_token = "your-api-token"
project = "PROJ"

[tool.spectra.sync]
verbose = true
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `JIRA_URL` | Jira instance URL (e.g., `https://company.atlassian.net`) |
| `JIRA_EMAIL` | Jira account email |
| `JIRA_API_TOKEN` | Jira API token ([generate here](https://id.atlassian.com/manage-profile/security/api-tokens)) |
| `JIRA_PROJECT` | Default project key |
| `GITLAB_TOKEN` | GitLab Personal Access Token |
| `GITLAB_PROJECT_ID` | GitLab project ID (numeric or `group/project` path) |
| `GITLAB_BASE_URL` | GitLab API base URL (default: `https://gitlab.com/api/v4`) |
| `GITLAB_GROUP_ID` | GitLab group ID for epics (optional) |
| `GITLAB_USE_SDK` | Use python-gitlab SDK (`true`/`false`) |
| `MONDAY_API_TOKEN` | Monday.com API token (v2) |
| `MONDAY_BOARD_ID` | Monday.com board ID (numeric) |
| `MONDAY_WORKSPACE_ID` | Monday.com workspace ID (optional) |
| `MONDAY_API_URL` | Monday.com API endpoint (default: `https://api.monday.com/v2`) |
| `MONDAY_STATUS_COLUMN_ID` | Status column ID (optional, auto-detected) |
| `MONDAY_PRIORITY_COLUMN_ID` | Priority column ID (optional, auto-detected) |
| `MONDAY_STORY_POINTS_COLUMN_ID` | Story points column ID (optional, auto-detected) |
| `TRELLO_API_KEY` | Trello API key ([get here](https://trello.com/app-key)) |
| `TRELLO_API_TOKEN` | Trello API token ([generate here](https://trello.com/app-key)) |
| `TRELLO_BOARD_ID` | Trello board ID (alphanumeric, from board URL) |
| `TRELLO_API_URL` | Trello API endpoint (default: `https://api.trello.com/1`) |
| `TRELLO_SUBTASK_MODE` | Subtask mode: `checklist` (default) or `linked_card` |
| `SHORTCUT_API_TOKEN` | Shortcut API token ([generate here](https://app.shortcut.com/settings/api-tokens)) |
| `SHORTCUT_WORKSPACE_ID` | Shortcut workspace ID (UUID or slug) |
| `SHORTCUT_API_URL` | Shortcut API endpoint (default: `https://api.app.shortcut.com/api/v3`) |
| `PLANE_API_TOKEN` | Plane.so API token ([generate here](https://app.plane.so/settings/api-tokens)) |
| `PLANE_WORKSPACE_SLUG` | Plane.so workspace slug (from URL) |
| `PLANE_PROJECT_ID` | Plane.so project ID (UUID) |
| `PLANE_API_URL` | Plane.so API endpoint (default: `https://app.plane.so/api/v1`) |
| `CLICKUP_API_TOKEN` | ClickUp API token ([generate here](https://app.clickup.com/settings/apps)) |
| `CLICKUP_SPACE_ID` | ClickUp space ID (optional, for scoping operations) |
| `CLICKUP_FOLDER_ID` | ClickUp folder ID (optional, for scoping operations) |
| `CLICKUP_LIST_ID` | ClickUp list ID (optional, for scoping operations) |
| `CLICKUP_API_URL` | ClickUp API endpoint (default: `https://api.clickup.com/api/v2`) |
| `BITBUCKET_USERNAME` | Bitbucket username |
| `BITBUCKET_APP_PASSWORD` | App Password (Cloud) or PAT (Server) |
| `BITBUCKET_WORKSPACE` | Workspace slug (Cloud) or project key (Server) |
| `BITBUCKET_REPO` | Repository slug |
| `BITBUCKET_BASE_URL` | API base URL (default: `https://api.bitbucket.org/2.0`) |
| `SPECTRA_VERBOSE` | Enable verbose output (`true`/`false`) |

## .env File

Create a `.env` file in your project root:

```bash
# .env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT=PROJ
```

::: warning Security
Add `.env` to your `.gitignore`!
:::

## CLI Override Examples

```bash
# Override Jira URL
spectra --markdown epic.md --epic PROJ-123 --jira-url https://other.atlassian.net

# Specify config file
spectra --markdown epic.md --epic PROJ-123 --config ~/configs/spectra-prod.yaml

# Override project
spectra --markdown epic.md --epic PROJ-123 --project OTHER
```

## Security Best Practices

::: tip Security Recommendations

1. **Never commit secrets** - Add `.env` and config files with tokens to `.gitignore`
2. **Use environment variables** - For CI/CD, use environment variables instead of files
3. **Rotate tokens regularly** - Regenerate API tokens periodically
4. **Limit token scope** - Use tokens with minimal required permissions

:::

### Example `.gitignore` entries

```bash
# spectra config with secrets
.env
.spectra.yaml
.spectra.yml
.spectra.toml
```

## Configuration Reference

### Jira Settings

| Setting | Type | Description |
|---------|------|-------------|
| `jira.url` | string | Jira instance URL |
| `jira.email` | string | Account email for authentication |
| `jira.api_token` | string | API token |
| `jira.project` | string | Default project key |
| `jira.story_points_field` | string | Custom field ID for story points |

### GitLab Settings

| Setting | Type | Description |
|---------|------|-------------|
| `gitlab.token` | string | GitLab Personal Access Token |
| `gitlab.project_id` | string | Project ID (numeric or `group/project` path) |
| `gitlab.base_url` | string | GitLab API base URL (default: `https://gitlab.com/api/v4`) |
| `gitlab.group_id` | string | Group ID for epics (Premium/Ultimate, optional) |
| `gitlab.use_epics` | boolean | Use Epics instead of Milestones (default: `false`) |
| `gitlab.use_sdk` | boolean | Use python-gitlab SDK (default: `false`) |
| `gitlab.epic_label` | string | Label for epic issues (default: `"epic"`) |
| `gitlab.story_label` | string | Label for story issues (default: `"story"`) |
| `gitlab.subtask_label` | string | Label for subtask issues (default: `"subtask"`) |
| `gitlab.status_labels` | dict | Status to label mapping (optional) |

See [GitLab Integration Guide](/guide/gitlab) for detailed configuration examples.

### Monday.com Settings

| Setting | Type | Description |
|---------|------|-------------|
| `monday.api_token` | string | Monday.com API token (v2) |
| `monday.board_id` | string | Board ID (numeric) |
| `monday.workspace_id` | string | Workspace ID (optional) |
| `monday.api_url` | string | API endpoint (default: `https://api.monday.com/v2`) |
| `monday.status_column_id` | string | Status column ID (auto-detected if not specified) |
| `monday.priority_column_id` | string | Priority column ID (auto-detected if not specified) |
| `monday.story_points_column_id` | string | Story points column ID (auto-detected if not specified) |

See [Monday.com Integration Guide](/guide/monday) for detailed configuration examples.

### Shortcut Settings

| Setting | Type | Description |
|---------|------|-------------|
| `shortcut.api_token` | string | Shortcut API token (required) |
| `shortcut.workspace_id` | string | Shortcut workspace ID (UUID or slug, required) |
| `shortcut.api_url` | string | API endpoint (default: `https://api.app.shortcut.com/api/v3`) |

See [Shortcut Integration Guide](/guide/shortcut) for detailed configuration examples.

### GitHub Settings

| Setting | Type | Description |
|---------|------|-------------|
| `github.token` | string | GitHub Personal Access Token (required) |
| `github.owner` | string | Repository owner (user or org, required) |
| `github.repo` | string | Repository name (required) |
| `github.base_url` | string | API base URL (default: `https://api.github.com`) |
| `github.project_number` | number | GitHub Projects v2 number (optional) |
| `github.epic_label` | string | Label for epics (default: `"epic"`) |
| `github.story_label` | string | Label for stories (default: `"user-story"`) |
| `github.priority_labels` | dict | Priority to label mapping (optional) |
| `github.status_labels` | dict | Status to label mapping (optional) |

See [GitHub Integration Guide](/guide/github) for detailed configuration examples.

### Azure DevOps Settings

| Setting | Type | Description |
|---------|------|-------------|
| `azure_devops.organization` | string | Azure DevOps organization (required) |
| `azure_devops.project` | string | Project name (required) |
| `azure_devops.pat` | string | Personal Access Token (required) |
| `azure_devops.base_url` | string | Base URL (default: `https://dev.azure.com`) |
| `azure_devops.area_path` | string | Area path for work items (optional) |
| `azure_devops.iteration_path` | string | Iteration/sprint path (optional) |
| `azure_devops.work_item_types` | dict | Type mapping (epic, story, subtask) |
| `azure_devops.state_mapping` | dict | Status to state mapping (optional) |

See [Azure DevOps Integration Guide](/guide/azure-devops) for detailed configuration examples.

### Linear Settings

| Setting | Type | Description |
|---------|------|-------------|
| `linear.api_key` | string | Linear API key (required) |
| `linear.team_id` | string | Team key or UUID (required) |
| `linear.project_id` | string | Project UUID (optional) |
| `linear.cycle_id` | string | Cycle/sprint UUID (optional) |
| `linear.state_mapping` | dict | Status to state mapping (optional) |
| `linear.priority_mapping` | dict | Priority mapping (1-4, optional) |
| `linear.estimate_scale` | string | Estimate type: `linear`, `exponential` |

See [Linear Integration Guide](/guide/linear) for detailed configuration examples.

### Asana Settings

| Setting | Type | Description |
|---------|------|-------------|
| `asana.access_token` | string | Asana Personal Access Token (required) |
| `asana.workspace_id` | string | Workspace GID (required) |
| `asana.project_id` | string | Project GID (required) |
| `asana.team_id` | string | Team GID (optional) |
| `asana.sections` | dict | Status to section mapping (optional) |
| `asana.custom_fields` | dict | Custom field GID mapping (optional) |
| `asana.priority_mapping` | dict | Priority to enum value mapping (optional) |

See [Asana Integration Guide](/guide/asana) for detailed configuration examples.

### Pivotal Tracker Settings

| Setting | Type | Description |
|---------|------|-------------|
| `pivotal.api_token` | string | Pivotal API token (required) |
| `pivotal.project_id` | number | Project ID (required) |
| `pivotal.story_types` | dict | Type mapping (story, bug, chore) |
| `pivotal.state_mapping` | dict | Status to state mapping (optional) |
| `pivotal.create_epics` | boolean | Create epics from markdown (default: `true`) |

See [Pivotal Tracker Integration Guide](/guide/pivotal) for detailed configuration examples.

### ClickUp Settings

| Setting | Type | Description |
|---------|------|-------------|
| `clickup.api_token` | string | ClickUp API token (required) |
| `clickup.space_id` | string | Space ID (optional, for scoping operations) |
| `clickup.folder_id` | string | Folder ID (optional, for scoping operations) |
| `clickup.list_id` | string | List ID (optional, for scoping operations) |
| `clickup.api_url` | string | API endpoint (default: `https://api.clickup.com/api/v2`) |

See [ClickUp Integration Guide](/guide/clickup) for detailed configuration examples.

### Bitbucket Settings

| Setting | Type | Description |
|---------|------|-------------|
| `bitbucket.username` | string | Bitbucket username (required) |
| `bitbucket.app_password` | string | App Password (Cloud) or PAT (Server, required) |
| `bitbucket.workspace` | string | Workspace slug (Cloud) or project key (Server, required) |
| `bitbucket.repo` | string | Repository slug (required) |
| `bitbucket.base_url` | string | API base URL (default: `https://api.bitbucket.org/2.0`) |
| `bitbucket.epic_label` | string | Label for epic issues (default: `"epic"`) |
| `bitbucket.story_label` | string | Label for story issues (default: `"story"`) |
| `bitbucket.subtask_label` | string | Label for subtask issues (default: `"subtask"`) |
| `bitbucket.status_mapping` | dict | Status to state mapping (optional) |
| `bitbucket.priority_mapping` | dict | Priority mapping (optional) |

See [Bitbucket Integration Guide](/guide/bitbucket) for detailed configuration examples.

### Sync Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `sync.verbose` | boolean | `false` | Enable verbose output |
| `sync.execute` | boolean | `false` | Execute changes (vs dry-run) |
| `sync.no_confirm` | boolean | `false` | Skip confirmation prompts |
| `sync.descriptions` | boolean | `true` | Sync story descriptions |
| `sync.subtasks` | boolean | `true` | Sync subtasks |
| `sync.comments` | boolean | `true` | Sync comments |
| `sync.statuses` | boolean | `true` | Sync status transitions |

### Validation Settings

Configure constraints and guards for your documents and sync operations. All settings are optional - if not specified, defaults are used.

The validation configuration is organized into logical sections:

#### Issue Types (`validation.issue_types`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowed` | list | `["Story", "User Story"]` | Issue types allowed when syncing/creating |
| `default` | string | `"User Story"` | Default type for new stories |
| `aliases` | dict | (see below) | Map alternative names to canonical types |

#### Naming Conventions (`validation.naming`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowed_id_prefixes` | list | `[]` | Allowed story ID prefixes (empty = all) |
| `id_pattern` | string | `""` | Regex pattern for story IDs |
| `require_sequential_ids` | boolean | `false` | IDs must be sequential |
| `normalize_ids_uppercase` | boolean | `true` | Convert IDs to uppercase |
| `epic_id_pattern` | string | `""` | Pattern for epic IDs |
| `title_case` | string | `""` | Enforce title case: "title", "sentence", "upper" |

#### Content Requirements (`validation.content`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_description` | boolean | `false` | Story must have description |
| `description_min_length` | integer | `0` | Minimum description length |
| `description_max_length` | integer | `0` | Maximum description length (0 = unlimited) |
| `require_user_story_format` | boolean | `false` | Require "As a...I want...So that" format |
| `title_min_length` | integer | `1` | Minimum title length |
| `title_max_length` | integer | `0` | Maximum title length (0 = unlimited) |
| `title_pattern` | string | `""` | Regex pattern title must match |
| `require_acceptance_criteria` | boolean | `false` | Must have acceptance criteria |
| `min_acceptance_criteria` | integer | `0` | Minimum AC items |
| `max_acceptance_criteria` | integer | `0` | Maximum AC items |
| `require_technical_notes` | boolean | `false` | Require technical notes |
| `require_dependencies` | boolean | `false` | Require dependencies section |
| `require_links` | boolean | `false` | Require at least one link |
| `require_related_commits` | boolean | `false` | Require related commits |

#### Estimation (`validation.estimation`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_story_points` | boolean | `false` | Story points must be set |
| `min_story_points` | integer | `0` | Minimum story points |
| `max_story_points` | integer | `0` | Maximum story points (0 = unlimited) |
| `allowed_story_points` | list | `[]` | Allowed values (e.g., `[1, 2, 3, 5, 8, 13, 21]`) |
| `fibonacci_only` | boolean | `false` | Only allow Fibonacci values |
| `default_story_points` | integer | `0` | Default story points |
| `require_time_estimate` | boolean | `false` | Require time estimate |

#### Subtasks (`validation.subtasks`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_subtasks` | boolean | `false` | Must have at least one subtask |
| `min_subtasks` | integer | `0` | Minimum subtasks per story |
| `max_subtasks` | integer | `0` | Maximum subtasks (0 = unlimited) |
| `subtask_title_pattern` | string | `""` | Regex for subtask titles |
| `require_subtask_estimates` | boolean | `false` | Subtasks must have estimates |
| `require_subtask_assignee` | boolean | `false` | Subtasks must have assignees |

#### Statuses (`validation.statuses`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowed` | list | `[]` | Allowed status values (empty = all) |
| `default` | string | `"Planned"` | Default status for new stories |
| `require_status` | boolean | `false` | Status must be explicitly set |
| `aliases` | dict | (see below) | Map alternative names to canonical statuses |
| `allowed_transitions` | dict | `{}` | Workflow constraints: status -> allowed targets |
| `require_status_emoji` | boolean | `false` | Require emoji in status |

#### Priorities (`validation.priorities`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowed` | list | `[]` | Allowed priority values (empty = all) |
| `default` | string | `"Medium"` | Default priority |
| `require_priority` | boolean | `false` | Priority must be set |
| `aliases` | dict | (see below) | Map P0/P1/etc to canonical names |

#### Labels (`validation.labels`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `required` | list | `[]` | Labels that must be present |
| `allowed` | list | `[]` | Whitelist of allowed labels |
| `forbidden` | list | `[]` | Labels that are not allowed |
| `min_labels` | integer | `0` | Minimum number of labels |
| `max_labels` | integer | `0` | Maximum labels (0 = unlimited) |
| `label_pattern` | string | `""` | Regex pattern for labels |

#### Components (`validation.components`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `required` | list | `[]` | Components that must be present |
| `allowed` | list | `[]` | Whitelist of allowed components |
| `require_component` | boolean | `false` | At least one component required |

#### Assignees (`validation.assignees`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_assignee` | boolean | `false` | Stories must have an assignee |
| `allowed` | list | `[]` | Whitelist of allowed assignees |
| `default` | string | `""` | Default assignee |
| `max_assignees` | integer | `1` | Maximum assignees per story |

#### Sprints (`validation.sprints`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_sprint` | boolean | `false` | Must be assigned to sprint |
| `allowed` | list | `[]` | Allowed sprint names |
| `sprint_pattern` | string | `""` | Regex for sprint names |

#### Versions (`validation.versions`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_version` | boolean | `false` | Must have fix version |
| `allowed` | list | `[]` | Allowed version values |
| `version_pattern` | string | `""` | Regex for versions |

#### Due Dates (`validation.due_dates`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_due_date` | boolean | `false` | Must have due date |
| `max_days_in_future` | integer | `0` | Max days in future (0 = unlimited) |
| `min_days_in_future` | integer | `0` | Min days (prevent past dates) |
| `date_format` | string | `"YYYY-MM-DD"` | Expected date format |

#### Epic Constraints (`validation.epic`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_stories` | integer | `0` | Maximum stories per epic |
| `min_stories` | integer | `0` | Minimum stories per epic |
| `require_summary` | boolean | `false` | Epic must have summary |
| `require_description` | boolean | `false` | Epic must have description |
| `max_total_story_points` | integer | `0` | Max total points in epic |
| `require_epic_owner` | boolean | `false` | Epic must have owner |
| `max_in_progress_stories` | integer | `0` | Max stories in progress at once |

#### Custom Fields (`validation.custom_fields`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `mappings` | dict | `{}` | Map field names to tracker field IDs |
| `required` | list | `[]` | Custom fields that must be present |
| `aliases` | dict | (see below) | Alternative names for fields |

#### Formatting (`validation.formatting`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_status_emoji` | boolean | `false` | Require status emoji in headers |
| `require_priority_emoji` | boolean | `false` | Require priority emoji |
| `allowed_header_levels` | list | `[1, 2, 3]` | Allowed header levels |
| `require_metadata_table` | boolean | `false` | Require table format metadata |
| `max_heading_depth` | integer | `4` | Maximum heading depth |

#### External Links (`validation.external_links`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_external_links` | boolean | `false` | Require external links |
| `allowed_domains` | list | `[]` | Allowed domains (empty = all) |
| `forbidden_domains` | list | `[]` | Blocked domains |
| `require_https` | boolean | `true` | Links must use HTTPS |

#### Behavior (`validation.behavior`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `strict` | boolean | `false` | Treat warnings as errors |
| `fail_fast` | boolean | `false` | Stop on first error |
| `ignore_rules` | list | `[]` | Rule codes to ignore |
| `auto_fix_ids` | boolean | `false` | Auto-correct ID formatting |
| `auto_fix_statuses` | boolean | `false` | Auto-map status aliases |
| `auto_fix_priorities` | boolean | `false` | Auto-map priority aliases |
| `show_suggestions` | boolean | `true` | Show fix suggestions |
| `max_errors_shown` | integer | `50` | Max errors to display |

---

### Extended Validation Settings

The following sections provide additional constraints for advanced workflows.

#### Workflow (`validation.workflow`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `definition_of_done` | list | `[]` | Checklist items for "done" status |
| `ready_for_dev_criteria` | list | `[]` | Required before story can start |
| `require_review` | boolean | `false` | Must be reviewed before done |
| `require_qa_signoff` | boolean | `false` | QA approval required |
| `blocked_by_types` | list | `[]` | Issue types that can block |
| `max_blocked_days` | integer | `0` | Alert if blocked longer |
| `require_parent` | boolean | `false` | Must have parent issue |
| `require_epic_link` | boolean | `false` | Must link to epic |
| `allowed_parent_types` | list | `[]` | Allowed parent issue types |

#### Scheduling (`validation.scheduling`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_story_age_days` | integer | `0` | Max age for open stories |
| `stale_after_days` | integer | `0` | Days until story is stale |
| `require_start_date` | boolean | `false` | Must have start date |
| `max_duration_days` | integer | `0` | Max days for story duration |
| `work_days_only` | boolean | `false` | Exclude weekends from calculations |
| `sla_days` | integer | `0` | SLA target in days |
| `warn_approaching_sla_days` | integer | `0` | Warn N days before SLA |
| `require_end_date` | boolean | `false` | Must have end/target date |

#### Development (`validation.development`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `branch_naming_pattern` | string | `""` | Regex for branch names |
| `require_branch_link` | boolean | `false` | Must link to branch |
| `require_pr_link` | boolean | `false` | Must link to PR |
| `commit_message_pattern` | string | `""` | Regex for commit messages |
| `require_code_review` | boolean | `false` | Code review required |
| `allowed_branch_prefixes` | list | `[]` | Allowed prefixes (feature/, bugfix/, etc.) |
| `require_merge_before_done` | boolean | `false` | PR must be merged before done |

#### Quality (`validation.quality`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_test_cases` | boolean | `false` | Must have test cases |
| `min_test_cases` | integer | `0` | Minimum test cases |
| `require_test_plan` | boolean | `false` | Test plan required |
| `bug_severity_levels` | list | `[]` | Valid severity levels for bugs |
| `require_reproduction_steps` | boolean | `false` | Bugs must have repro steps |
| `require_expected_behavior` | boolean | `false` | Bugs must describe expected |
| `require_actual_behavior` | boolean | `false` | Bugs must describe actual |
| `require_environment_info` | boolean | `false` | Bugs must have env info |
| `require_screenshots` | boolean | `false` | Bugs must have screenshots |

#### Documentation (`validation.documentation`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_api_docs` | boolean | `false` | API documentation required |
| `require_changelog_entry` | boolean | `false` | Must update changelog |
| `require_release_notes` | boolean | `false` | Release notes required |
| `documentation_link_required` | boolean | `false` | Must link to docs |
| `readme_update_required` | boolean | `false` | README update required |
| `require_user_docs` | boolean | `false` | User-facing docs required |
| `docs_location_pattern` | string | `""` | Regex for docs file paths |

#### Security (`validation.security`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_security_review` | boolean | `false` | Security review required |
| `confidentiality_levels` | list | `[]` | Valid confidentiality levels |
| `require_data_classification` | boolean | `false` | Data classification required |
| `pii_handling_required` | boolean | `false` | PII handling docs required |
| `require_threat_model` | boolean | `false` | Threat model required |
| `compliance_tags` | list | `[]` | Required compliance tags |
| `require_vulnerability_scan` | boolean | `false` | Vuln scan required |
| `security_labels` | list | `[]` | Valid security labels |

#### Templates (`validation.templates`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `story_template` | string | `""` | Path to story template |
| `bug_template` | string | `""` | Path to bug template |
| `epic_template` | string | `""` | Path to epic template |
| `task_template` | string | `""` | Path to task template |
| `enforce_template` | boolean | `false` | Strictly enforce templates |
| `allowed_sections` | list | `[]` | Allowed markdown sections |
| `required_sections` | list | `[]` | Required markdown sections |
| `section_order` | list | `[]` | Enforced section order |

#### Alerts (`validation.alerts`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `alert_on_blocked` | boolean | `false` | Alert when story blocked |
| `alert_on_stale` | boolean | `false` | Alert on stale stories |
| `alert_threshold_days` | integer | `0` | Days before alert |
| `alert_on_over_estimate` | boolean | `false` | Alert on large estimates |
| `watchers` | list | `[]` | Default watchers to notify |
| `alert_on_unassigned` | boolean | `false` | Alert on unassigned stories |
| `alert_on_no_estimate` | boolean | `false` | Alert on missing estimates |
| `notification_channels` | list | `[]` | Notification channels (slack, email) |

#### Dependencies (`validation.dependencies`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `require_dependency_check` | boolean | `false` | Check dependencies |
| `max_dependencies` | integer | `0` | Max dependencies per story |
| `allow_circular_dependencies` | boolean | `false` | Allow circular deps |
| `dependency_types` | list | `[]` | Valid dependency types |
| `cross_project_deps_allowed` | boolean | `true` | Allow cross-project deps |
| `require_dependency_approval` | boolean | `false` | Approve new deps |
| `blocked_dependency_types` | list | `[]` | Disallowed dep types |

#### Archival (`validation.archival`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `auto_archive_after_days` | integer | `0` | Days after done to archive |
| `archive_cancelled` | boolean | `false` | Auto-archive cancelled |
| `retention_days` | integer | `0` | Keep archived for N days |
| `exclude_from_archive` | list | `[]` | Labels/types to exclude |
| `archive_on_done` | boolean | `false` | Archive when done |
| `cleanup_stale_branches` | boolean | `false` | Clean up stale branches |

#### Capacity (`validation.capacity`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `max_stories_per_assignee` | integer | `0` | Max stories per person |
| `max_points_per_sprint` | integer | `0` | Max points per sprint |
| `warn_overload_threshold` | integer | `0` | Warn at N% capacity |
| `require_capacity_check` | boolean | `false` | Check capacity limits |
| `max_parallel_stories` | integer | `0` | Max in-progress per person |
| `points_per_day` | float | `0.0` | Team velocity (pts/day) |

#### Environments (`validation.environments`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `allowed_environments` | list | `[]` | Valid environment names |
| `require_environment` | boolean | `false` | Environment required |
| `environment_order` | list | `[]` | Deployment order (dev->staging->prod) |
| `require_rollback_plan` | boolean | `false` | Rollback plan required |
| `require_deployment_notes` | boolean | `false` | Deployment notes required |
| `production_approval_required` | boolean | `false` | Prod deploy needs approval |

---

#### Complete Example

```yaml
# .spectra.yaml - Complete Validation Configuration Example
validation:
  # Issue Types - Guard against "Story" vs "User Story" confusion
  issue_types:
    allowed:
      - "User Story"
      - "Bug"
      - "Task"
    default: "User Story"
    aliases:
      "story": "User Story"
      "defect": "Bug"

  # Naming Conventions
  naming:
    allowed_id_prefixes:
      - "US"
      - "BUG"
      - "TASK"
    normalize_ids_uppercase: true

  # Content Requirements
  content:
    require_description: true
    require_acceptance_criteria: true
    min_acceptance_criteria: 1
    title_max_length: 100

  # Estimation - Fibonacci story points
  estimation:
    require_story_points: true
    allowed_story_points: [1, 2, 3, 5, 8, 13, 21]
    fibonacci_only: true

  # Subtasks
  subtasks:
    max_subtasks: 10

  # Status Workflow
  statuses:
    allowed:
      - "Planned"
      - "In Progress"
      - "In Review"
      - "Done"
      - "Blocked"
    default: "Planned"
    aliases:
      "todo": "Planned"
      "wip": "In Progress"

  # Priorities
  priorities:
    allowed:
      - "Critical"
      - "High"
      - "Medium"
      - "Low"
    default: "Medium"

  # Labels
  labels:
    required:
      - "team:backend"
    max_labels: 5

  # Epic Constraints
  epic:
    max_stories: 50
    require_summary: true

  # Behavior
  behavior:
    strict: false
    auto_fix_statuses: true
    auto_fix_priorities: true

  # Workflow constraints
  workflow:
    definition_of_done:
      - "Code reviewed"
      - "Tests passing"
      - "Documentation updated"
    require_review: true
    require_epic_link: true

  # Scheduling
  scheduling:
    stale_after_days: 14
    sla_days: 30
    warn_approaching_sla_days: 7

  # Development workflow
  development:
    branch_naming_pattern: "^(feature|bugfix|hotfix)/[A-Z]+-\\d+-.+"
    require_pr_link: true
    allowed_branch_prefixes:
      - "feature/"
      - "bugfix/"
      - "hotfix/"
    require_merge_before_done: true

  # Quality requirements
  quality:
    require_test_cases: true
    min_test_cases: 1
    require_reproduction_steps: true  # For bugs

  # Documentation
  documentation:
    require_changelog_entry: true

  # Security
  security:
    confidentiality_levels:
      - "public"
      - "internal"
      - "confidential"
    compliance_tags:
      - "GDPR"
      - "SOC2"

  # Templates
  templates:
    required_sections:
      - "User Story"
      - "Acceptance Criteria"
    enforce_template: false

  # Alerts
  alerts:
    alert_on_blocked: true
    alert_on_stale: true
    alert_threshold_days: 7

  # Dependencies
  dependencies:
    max_dependencies: 5
    allow_circular_dependencies: false

  # Capacity management
  capacity:
    max_stories_per_assignee: 5
    max_points_per_sprint: 40
    max_parallel_stories: 3

  # Environments
  environments:
    allowed_environments:
      - "development"
      - "staging"
      - "production"
    environment_order:
      - "development"
      - "staging"
      - "production"
    production_approval_required: true
```

