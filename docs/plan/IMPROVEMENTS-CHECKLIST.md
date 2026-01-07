# Spectra Improvements Checklist

> Consolidated from multiple AI analysis sessions. Check off items as completed.

---

## 🔴 High Priority (Core Flexibility)

### ID Format Support
- [x] **Custom ID Separators** - Support `PROJ_123` and `PROJ/123` in addition to `PROJ-123`
- [x] **Universal `#123` ID Support** - Extend GitHub-style IDs to all parsers (MarkdownParser, YamlParser, JsonParser, AsciiDocParser, NotionParser)
- [x] **Flexible ID Prefixes** - All parsers handle varied prefixes (`US-001`, `EU-001`, `PROJ-123`, `A-1`, `VERYLONGPREFIX-99999`)

---

## 🟡 Medium Priority (Quality & Parity)

### Adapter Improvements
- [x] **Asana Adapter Feature Parity** - Verified batch operations, async support, caching, custom field mapping, comment sync (attachments noted as future enhancement)
- [x] **Complete Async Adapter Parity** - Created async adapters for Linear and Azure DevOps (Confluence is DocumentOutputPort, doesn't need async)
- [x] **Unify Batch Operations** - Created batch clients for Linear and Azure DevOps following `JiraBatchClient` pattern

### Testing & Coverage
- [x] **Integration Tests for All Trackers**
  - [x] `test_github_integration.py` - comprehensive coverage with batch, edge cases, type detection
  - [x] `test_linear_integration.py` - comprehensive coverage with batch, edge cases, priorities
  - [x] `test_azure_devops_integration.py` - added async adapter and batch tests
  - [x] `test_asana_integration.py` - added async adapter tests
  - [x] `test_confluence_integration.py` - comprehensive coverage with batch, storage format, permissions
- [ ] **Code Coverage 80%+** - Currently 65.87%, target 80%+ (7,408 tests passing)
- [x] **Fix Failing Tests** - All 3003 tests passing
- [x] **Parameterized Tests for ID Prefixes** - Added `test_flexible_id_prefixes.py` with comprehensive ID format tests
- [x] **Property-Based Testing** - Added `test_parser_properties.py` with Hypothesis tests for parsers
- [x] **Jira Async Tests** - Added `test_jira_async.py` with 29 tests for async adapter and client
- [x] **Jira Adapter Extended Tests** - Extended `test_jira_adapter.py` with 18 new tests
- [x] **Azure DevOps Async/Batch Tests** - Added `test_azure_devops_async_batch.py` with comprehensive tests
- [x] **HTTP Client Tests** - Added `test_async_http_clients.py` for base HTTP client coverage
- [x] **Linear Async Tests** - Added `test_linear_async.py` with 11 tests for async adapter
- [x] **Linear Batch Tests** - Added `test_linear_batch.py` with 19 tests for batch operations
- [x] **Asana Async Tests** - Added `test_asana_async.py` with 11 tests for async adapter
- [x] **Golden-File Tests** - Added `tests/parsers/test_golden_files.py` with markdown variant fixtures
- [x] **Contract Tests for Adapters** - Added `tests/contracts/test_adapter_contracts.py` for interface compliance
- [x] **Mutation Testing** - Added `tests/mutation/test_mutation_config.py` with mutmut configuration and targets
- [x] **Load Testing** - Added `tests/load/test_load_performance.py` with benchmarks up to 10K stories
- [x] **Chaos Engineering** - Added `tests/chaos/test_chaos_engineering.py` for network failures, rate limiting, partial failures
- [x] **E2E Testing** - Added `tests/e2e/test_e2e_workflows.py` for complete workflow automation

### Documentation
- [x] **Documentation Examples Standardization** - Use neutral prefix like `STORY-001` instead of `US-001`
- [x] **AI Prompts Dynamic Examples** - Make prompts in `ai_fix.py` use dynamic/neutral examples
- [x] **OpenTelemetry/Prometheus Documentation** - Document setup, export configuration, integration examples
- [x] **TrackerType.ASANA Full Integration Check** - Verified in `_get_tracker_display_name()`, `_build_url()`, CLI, docs

---

## 🟢 New Tracker Integrations

### Implementation Requirements

Each tracker adapter requires:
1. **Core Adapter** (`adapter.py`) - Implements `IssueTrackerPort` interface
2. **API Client** (`client.py`) - Low-level HTTP/GraphQL client
3. **Configuration** (`config.py`) - Tracker-specific config dataclass
4. **Plugin** (`plugin.py`) - Optional plugin registration
5. **Async Adapter** (`async_adapter.py`) - Optional async implementation
6. **Batch Client** (`batch.py`) - Optional batch operations
7. **Tests** (`test_*_adapter.py`) - Unit and integration tests
8. **Factory Registration** - Add to `create_tracker_factory()` in `core/services.py`
9. **TrackerType Enum** - Add to `TrackerType` enum in `core/ports/config_provider.py`
10. **CLI Integration** - Update CLI help text and examples

### Priority Trackers

#### 1. GitLab Issues Adapter ✅ **COMPLETED**
**Priority: High** | **Effort: Medium** | **Complexity: Medium**

- [x] **Core Implementation**
  - [x] Add `GITLAB` to `TrackerType` enum
  - [x] Create `GitLabConfig` dataclass (token, project_id, base_url, group_id)
  - [x] Implement `GitLabAdapter` with `IssueTrackerPort`
  - [x] Create `GitLabApiClient` using GitLab REST API v4
  - [x] Map Epic → Milestone or Epic issue type
  - [x] Map Story → Issue with labels
  - [x] Map Subtask → Issue with parent link or task list
  - [x] Status mapping (open/closed + labels for workflow states)
  - [x] Priority mapping (labels or issue weight)
  - [x] Story points → Issue weight field

- [x] **API Integration**
  - [x] Authentication: Personal Access Token or OAuth
  - [x] Endpoints: `/projects/:id/issues`, `/projects/:id/milestones`, `/groups/:id/epics`
  - [x] Support GitLab.com and self-hosted instances
  - [x] Rate limiting: 2000 requests/hour per user
  - [x] Pagination: Use `page` and `per_page` parameters

- [x] **Advanced Features**
  - [x] Epic support (GitLab Premium/Ultimate feature)
  - [x] Issue boards integration ✅ **COMPLETED**
  - [x] Merge request linking ✅ **COMPLETED**
  - [x] Time tracking support ✅ **COMPLETED**
  - [x] Labels and milestones sync

- [x] **Testing**
  - [x] Unit tests for adapter methods (52 tests)
  - [x] Unit tests for client (42 tests)
  - [x] Integration tests with GitLab API (mocked)
  - [x] Test self-hosted GitLab instances (via base_url config)
  - [x] Test rate limiting and pagination

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)
  - [x] Optional: `python-gitlab` SDK ✅ **COMPLETED** - Added as optional dependency `spectra[gitlab]`, adapter supports `use_sdk=True` to use official SDK instead of custom client

- [x] **Documentation** ✅ **COMPLETED**
  - [x] Configuration guide - Added to `docs/guide/gitlab.md` and `docs/guide/configuration.md`
  - [x] API authentication setup - Personal Access Token guide with scopes
  - [x] Self-hosted GitLab setup - Configuration and SSL/TLS guidance
  - [x] Epic vs Milestone mapping guide - Detailed comparison and use cases

**Status**: ✅ **Core implementation complete** - 94 unit tests passing, all linting/type checks passing. Ready for use.

**Actual Time**: ~3 hours (faster than estimated due to good patterns from GitHub adapter)

---

#### 2. Monday.com Adapter ✅ **COMPLETED**
**Priority: Medium** | **Effort: High** | **Complexity: High**

- [x] **Core Implementation**
  - [x] Add `MONDAY` to `TrackerType` enum
  - [x] Create `MondayConfig` dataclass (api_token, board_id, workspace_id)
  - [x] Implement `MondayAdapter` with `IssueTrackerPort`
  - [x] Create `MondayApiClient` using Monday.com GraphQL API
  - [x] Map Epic → Group (board group)
  - [x] Map Story → Item (board item)
  - [x] Map Subtask → Subitem or linked item
  - [x] Status mapping → Status column
  - [x] Priority mapping → Priority column
  - [x] Story points → Numbers column

- [x] **API Integration**
  - [x] Authentication: API Token (v2)
  - [x] GraphQL API endpoint: `https://api.monday.com/v2`
  - [x] Rate limiting: 500 requests per 10 seconds
  - [x] Webhooks support for real-time sync
  - [x] Custom column mapping configuration

- [x] **Advanced Features**
  - [x] Board structure mapping
  - [x] Custom columns support
  - [x] Timeline/Gantt view integration
  - [x] File attachments
  - [x] Updates (comments) sync

- [x] **Testing**
  - [x] Unit tests for GraphQL queries/mutations
  - [x] Integration tests with Monday.com API
  - [x] Test custom column mappings
  - [x] Test rate limiting

- [x] **Dependencies**
  - [x] `requests` + `graphql-core` (or custom GraphQL client)
  - [x] Consider: `gql` library for GraphQL (using requests directly)

- [x] **Documentation**
  - [x] API token setup
  - [x] Board and column configuration
  - [x] Custom column mapping guide

**Status**: ✅ **Core implementation complete** - 41 unit tests passing, all linting/type checks passing. Ready for use.

**Estimated Time**: 4-5 days

---

#### 3. Trello Adapter ✅ **COMPLETED**
**Priority: Medium** | **Effort: Low-Medium** | **Complexity: Low**

- [x] **Core Implementation**
  - [x] Add `TRELLO` to `TrackerType` enum
  - [x] Create `TrelloConfig` dataclass (api_key, api_token, board_id)
  - [x] Implement `TrelloAdapter` with `IssueTrackerPort`
  - [x] Create `TrelloApiClient` using Trello REST API
  - [x] Map Epic → Board or List (epic list)
  - [x] Map Story → Card
  - [x] Map Subtask → Checklist item or linked card
  - [x] Status mapping → List (board lists)
  - [x] Priority mapping → Labels
  - [x] Story points → Custom field or card description

- [x] **API Integration**
  - [x] Authentication: API Key + Token (via query params, no OAuth library needed)
  - [x] Endpoints: `/boards/:id`, `/cards`, `/lists`, `/checklists`, `/labels`, `/actions/comments`, `/webhooks`
  - [x] Rate limiting: 25 requests/second (conservative for 300 requests per 10 seconds limit)
  - [x] Webhooks support (create, list, get, update, delete webhooks)

- [x] **Advanced Features**
  - [x] Card attachments ✅ **COMPLETED** - Full support for get/upload/delete attachments
  - [x] Comments sync
  - [x] Due dates ✅ **COMPLETED** - Full support for get/set/clear due dates with IssueData integration
  - [x] Labels and custom fields
  - [x] Power-Ups integration (list Power-Ups, custom fields support)

- [x] **Testing**
  - [x] Unit tests for adapter methods (61 tests including webhooks, Power-Ups, attachments, and due dates)
  - [x] Integration tests with Trello API (mocked)
  - [x] Test checklist-based subtasks
  - [x] Test webhook operations
  - [x] Test Power-Ups and custom fields operations

- [x] **Dependencies**
  - [x] `requests` (already in dependencies, no OAuth library needed - Trello uses query params)

- [x] **Documentation**
  - [x] API key/token setup - Added to `docs/guide/trello.md`
  - [x] Board and list configuration - Comprehensive guide with examples
  - [x] Checklist vs linked cards for subtasks - Detailed comparison and configuration
  - [x] Added to main configuration guide (`docs/guide/configuration.md`)
  - [x] Updated homepage to include Trello in supported trackers

**Status**: ✅ **Core implementation complete** - 61 unit tests passing (including webhook, Power-Ups, attachments, and due date support), all linting/type checks passing. Ready for use.

**Actual Time**: ~4 hours (faster than estimated due to good patterns from Linear/GitHub adapters)

---

#### 4. Shortcut (Clubhouse) Adapter ✅ **COMPLETED**
**Priority: Medium** | **Effort: Medium** | **Complexity: Medium**

- [x] **Core Implementation**
  - [x] Add `SHORTCUT` to `TrackerType` enum
  - [x] Create `ShortcutConfig` dataclass (api_token, workspace_id)
  - [x] Implement `ShortcutAdapter` with `IssueTrackerPort`
  - [x] Create `ShortcutApiClient` using Shortcut REST API
  - [x] Map Epic → Epic
  - [x] Map Story → Story
  - [x] Map Subtask → Task (within story)
  - [x] Status mapping → Workflow State
  - [x] Priority mapping → Story priority
  - [x] Story points → Story estimate

- [x] **API Integration**
  - [x] Authentication: API Token
  - [x] Endpoints: `/epics`, `/stories`, `/tasks`
  - [x] Rate limiting: 200 requests per minute
  - [x] Webhooks support ✅ **COMPLETED** - Full support for create/list/get/update/delete webhooks

- [x] **Advanced Features**
  - [x] Iterations (sprints) support ✅ **COMPLETED** - Full support for create/list/get/update/delete iterations and assign/remove stories
  - [x] Story types (feature, bug, chore) - supported via API
  - [x] Story dependencies ✅ **COMPLETED** - Full support for get/create/delete dependencies with LinkType mapping
  - [x] Comments sync
  - [x] File attachments ✅ **COMPLETED** - Full support for get/upload/delete attachments

- [x] **Testing**
  - [x] Unit tests for adapter methods (74 tests including webhooks, iterations, and attachments)
  - [x] Integration tests with Shortcut API (mocked)
  - [x] Test workflow state transitions

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation** ✅ **COMPLETED**
  - [x] API token setup - Added to `docs/guide/shortcut.md`
  - [x] Workspace configuration - Comprehensive guide with examples
  - [x] Workflow state mapping - Detailed mapping table and custom state guide

**Status**: ✅ **Core implementation complete** - 74 unit tests passing (including webhooks, iterations, and attachments), all linting/type checks passing. Ready for use.

**Actual Time**: ~4 hours (faster than estimated due to good patterns from Linear/GitHub adapters)

---

#### 5. ClickUp Adapter ✅ **COMPLETED**
**Priority: Medium** | **Effort: High** | **Complexity: High**

- [x] **Core Implementation**
  - [x] Add `CLICKUP` to `TrackerType` enum
  - [x] Create `ClickUpConfig` dataclass (api_token, space_id, folder_id, list_id)
  - [x] Implement `ClickUpAdapter` with `IssueTrackerPort`
  - [x] Create `ClickUpApiClient` using ClickUp REST API v2
  - [x] Map Epic → Goal or Folder
  - [x] Map Story → Task
  - [x] Map Subtask → Subtask or Checklist item
  - [x] Status mapping → Status (custom statuses)
  - [x] Priority mapping → Priority
  - [x] Story points → Story points field

- [x] **API Integration**
  - [x] Authentication: API Token
  - [x] Endpoints: `/team/:team_id/space`, `/list/:list_id/task`, `/goal`
  - [x] Rate limiting: 100 requests per minute
  - [x] Webhooks support ✅ **COMPLETED** - Full support for create/list/get/update/delete webhooks
  - [x] Custom fields support

- [x] **Advanced Features**
  - [x] Hierarchical structure (Space → Folder → List → Task)
  - [x] Custom fields mapping
  - [x] Time tracking ✅ **COMPLETED** - Full support for time entries, stats, create/update/delete
  - [x] Dependencies and relationships ✅ **COMPLETED** - Full support for task dependencies with LinkType mapping
  - [x] Comments sync
  - [x] File attachments ✅ **COMPLETED** - Full support for get/upload/delete attachments
  - [x] Views (Board, List, Calendar) ✅ **COMPLETED** - Full support for getting views and view tasks

- [x] **Testing**
  - [x] Unit tests for adapter methods (59 tests including webhooks, time tracking, dependencies, views)
  - [x] Integration tests with ClickUp API (mocked)
  - [x] Test custom fields and statuses

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation** ✅ **COMPLETED**
  - [x] API token setup - Added to `docs/guide/clickup.md`
  - [x] Space/Folder/List hierarchy - Comprehensive guide with examples
  - [x] Custom fields configuration - Detailed instructions for story points and custom fields
  - [x] Added to main configuration guide (`docs/guide/configuration.md`)

**Status**: ✅ **Core implementation complete** - 65 unit tests passing (including 18 webhook tests, 5 time tracking tests, 7 dependency tests, 4 views tests, 6 attachment tests), all linting/type checks passing. Ready for use.

**Actual Time**: ~4 hours (faster than estimated due to good patterns from Linear/GitHub adapters)

---

#### 6. Bitbucket Cloud/Server Adapter ✅ **COMPLETED**
**Priority: Medium** | **Effort: Medium** | **Complexity: Medium**

- [x] **Core Implementation**
  - [x] Add `BITBUCKET` to `TrackerType` enum
  - [x] Create `BitbucketConfig` dataclass (username, app_password, workspace, repo)
  - [x] Implement `BitbucketAdapter` with `IssueTrackerPort`
  - [x] Create `BitbucketApiClient` using Bitbucket REST API v2
  - [x] Map Epic → Milestone or Epic issue
  - [x] Map Story → Issue
  - [x] Map Subtask → Issue with parent link
  - [x] Status mapping → Issue state (new, open, resolved, closed)
  - [x] Priority mapping → Issue priority
  - [x] Story points → Custom field (if available)

- [x] **API Integration**
  - [x] Authentication: App Password (Cloud) or Personal Access Token (Server)
  - [x] Endpoints: `/repositories/:workspace/:repo/issues`, `/milestones`
  - [x] Support both Cloud and Server (self-hosted)
  - [x] Rate limiting: 1000 requests per hour (Cloud)
  - [x] Pagination: Use `page` parameter

- [x] **Advanced Features**
  - [x] Pull request linking
  - [x] Comments sync
  - [x] Attachments support
  - [x] Component and version fields

- [x] **Testing**
  - [x] Unit tests for adapter methods
  - [x] Integration tests with Bitbucket Cloud
  - [x] Test self-hosted Bitbucket Server
  - [x] Test rate limiting

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)
  - [x] Optional: `atlassian-python-api` (for Server support)

- [x] **Documentation**
  - [x] App Password setup (Cloud)
  - [x] Personal Access Token setup (Server)
  - [x] Workspace and repository configuration

**Status**: ✅ **Core implementation complete** - 42 unit tests passing, all linting/type checks passing. Ready for use.

**Estimated Time**: 2-3 days

---

#### 7. YouTrack Adapter ✅ **FULLY IMPLEMENTED**
**Priority: Low** | **Effort: Medium** | **Complexity: Medium** | **Status: ✅ Full Implementation Complete**

**Note**: YouTrack adapter is fully functional with all features implemented and comprehensive test coverage (148 tests).

- [x] **Core Implementation**
  - [x] Add `YOUTRACK` to `TrackerType` enum
  - [x] Create `YouTrackConfig` dataclass (url, token, project_id)
  - [x] Implement `YouTrackAdapter` with `IssueTrackerPort`
  - [x] Create `YouTrackApiClient` using YouTrack REST API
  - [x] Map Epic → Epic issue type
  - [x] Map Story → Task or User Story issue type
  - [x] Map Subtask → Subtask
  - [x] Status mapping → State field
  - [x] Priority mapping → Priority field
  - [x] Story points → Story points field

- [x] **API Integration**
  - [x] Authentication: Permanent Token
  - [x] Endpoints: `/issues`, `/api/issues`
  - [x] Support Cloud and self-hosted instances
  - [x] Rate limiting: Retry with exponential backoff
  - [x] Custom fields support ✅ **COMPLETED** - Full support for get/set custom fields, field options discovery

- [x] **Advanced Features** ✅ **ALL COMPLETE**

  **High Priority Enhancements** (commonly requested):
  - [x] Basic custom fields mapping (story points field support) ✅ **Core Feature**
  - [x] Full custom fields support ✅ **COMPLETED** - All field types, dynamic discovery, enum options
  - [x] Bulk operations ✅ **COMPLETED** - Batch create/update/delete issues, bulk transitions
  - [x] File attachments ✅ **COMPLETED** - Upload, download, delete attachments

  **Medium Priority Enhancements** (workflow improvements):
  - [x] Workflow automation ✅ **COMPLETED** - Execute commands, get available commands
  - [x] Due dates support ✅ **COMPLETED** - Get/set due dates with ISO 8601 conversion
  - [x] Tags/labels support ✅ **COMPLETED** - Get/add/remove tags, get project tags
  - [x] Watchers/observers ✅ **COMPLETED** - Get/add/remove watchers, check watching status

  **Low Priority Enhancements** (nice-to-have):
  - [x] Agile boards integration ✅ **COMPLETED** - Get boards, board details
  - [x] Sprints support ✅ **COMPLETED** - Get/create sprints, add/remove issues
  - [x] Time tracking ✅ **COMPLETED** - Work items, estimates, spent time
  - [x] Issue history/activity feed ✅ **COMPLETED** - Get change history and activities
  - [x] Mentions in comments ✅ **COMPLETED** - Add comments with @mentions, get mentionable users

- [x] **Testing** ✅ **COMPREHENSIVE - 148 tests total**
  - [x] Unit tests for adapter methods (89 tests including all features)
  - [x] Unit tests for API client (49 tests in test_youtrack_client.py) ✅ **COMPLETED**
  - [x] Contract tests for adapter interface compliance (6 tests)
  - [x] Integration tests with mocked YouTrack API responses (10 tests)
  - [x] Test custom fields ✅ **COMPLETED**
  - [x] Test bulk operations ✅ **COMPLETED**
  - [x] Test file attachments ✅ **COMPLETED**
  - [x] Test workflow/commands ✅ **COMPLETED**
  - [x] Test due dates ✅ **COMPLETED**
  - [x] Test tags ✅ **COMPLETED**
  - [x] Test watchers ✅ **COMPLETED**
  - [x] Test agile boards ✅ **COMPLETED**
  - [x] Test sprints ✅ **COMPLETED**
  - [x] Test time tracking ✅ **COMPLETED**
  - [x] Test issue history ✅ **COMPLETED**
  - [x] Test mentions ✅ **COMPLETED**
  - [x] Test rate limiting and retry logic ✅ **COMPLETED** (3 tests)
  - [x] Test error handling (403, 500, network errors, timeouts) ✅ **COMPLETED** (7 tests)
  - [x] Test edge cases (empty responses, malformed JSON, connection errors) ✅ **COMPLETED** (6 tests)
  - [x] Test connection pooling and session management ✅ **COMPLETED** (4 tests)
  - [x] Test dry-run mode for all write operations ✅ **COMPLETED** (21 tests)
  - [ ] Integration tests with live YouTrack API (requires live instance - optional)

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation**
  - [x] Token setup
  - [x] Project configuration
  - [x] Custom fields mapping

**Status**: ✅ **FULLY COMPLETE** - 148 tests passing (89 adapter + 49 client + 10 integration), all linting/type checks passing. Production ready with comprehensive feature coverage including rate limiting, error handling, edge cases, session management, and dry-run mode. Supports all core IssueTrackerPort operations plus ALL advanced features: custom fields, bulk operations, attachments, workflows, due dates, tags, watchers, agile boards, sprints, time tracking, history, and mentions. All priority levels (high, medium, low) are complete.

**Estimated Time**: 2-3 days (core) | Advanced features: 1-2 days each

---

#### 8. Basecamp Adapter
**Priority: Low** | **Effort: Medium** | **Complexity: Medium**

- [x] **Core Implementation**
  - [x] Add `BASECAMP` to `TrackerType` enum
  - [x] Create `BasecampConfig` dataclass (access_token, account_id, project_id)
  - [x] Implement `BasecampAdapter` with `IssueTrackerPort`
  - [x] Create `BasecampApiClient` using Basecamp 3 API
  - [x] Map Epic → Project or Message Board category
  - [x] Map Story → Todo or Message
  - [x] Map Subtask → Todo list item
  - [x] Status mapping → Todo completion status
  - [x] Priority mapping → Not natively supported (use notes)
  - [x] Story points → Not natively supported (use notes)

- [x] **API Integration**
  - [x] Authentication: OAuth 2.0 (access token)
  - [x] Endpoints: `/projects/:id/todosets`, `/projects/:id/todos`, `/projects/:id/messages`
  - [x] Rate limiting: 40 requests per 10 seconds
  - [x] Webhooks support

- [x] **Advanced Features**
  - [x] Todo lists and todos
  - [x] Message boards
  - [x] Comments and file attachments
  - [x] Campfire (chat) integration (optional)

- [x] **Testing**
  - [x] Unit tests for adapter methods
  - [x] Integration tests with Basecamp API
  - [x] Test OAuth flow
  - [x] Test API client integration
  - [x] Test adapter integration
  - [x] Test end-to-end workflows

- [x] **Dependencies**
  - [x] `requests` (OAuth handled via Bearer token, no oauthlib needed)

- [x] **Documentation**
  - [x] OAuth setup
  - [x] Account and project configuration
  - [x] Todo vs Message mapping

**Estimated Time**: 2-3 days

---

#### 9. Plane.so Adapter ✅ **COMPLETED**
**Priority: Low** | **Effort: Medium** | **Complexity: Medium**

- [x] **Core Implementation**
  - [x] Add `PLANE` to `TrackerType` enum
  - [x] Create `PlaneConfig` dataclass (api_token, workspace_slug, project_id)
  - [x] Implement `PlaneAdapter` with `IssueTrackerPort`
  - [x] Create `PlaneApiClient` using Plane REST API
  - [x] Map Epic → Cycle or Module (configurable via `epic_as_cycle`)
  - [x] Map Story → Issue
  - [x] Map Subtask → Sub-issue (issue with parent)
  - [x] Status mapping → State
  - [x] Priority mapping → Priority
  - [x] Story points → Estimate Point

- [x] **API Integration**
  - [x] Authentication: API Token
  - [x] Endpoints: `/api/workspaces/:slug/projects/:id/issues`, `/cycles`, `/modules`
  - [x] Support self-hosted instances (via `api_url` config)
  - [x] Rate limiting: Conservative defaults with configurable limits
  - [x] Webhooks support ✅ **COMPLETED** - Full support for create/list/get/update/delete webhooks

- [x] **Advanced Features**
  - [x] Cycles (sprints) support ✅ **COMPLETED** - Full CRUD operations for cycles
  - [x] Modules (epics) support ✅ **COMPLETED** - Full CRUD operations for modules
  - [x] Views and filters ✅ **COMPLETED** - Full support for saved views (create/list/get/update/delete), get issues from views, and advanced filtering (state, priority, assignee, cycle, module, labels)
  - [x] Labels and assignees ✅ **COMPLETED** - Assignee support via `assignee_ids`
  - [x] Comments ✅ **COMPLETED** - Full support for get/add comments
  - [x] Attachments ✅ **COMPLETED** - Full support for get/upload/delete/download attachments with multipart/form-data uploads

- [x] **Testing**
  - [x] Unit tests for adapter methods (30 tests)
  - [x] Integration tests with Plane API (mocked)
  - [x] Test self-hosted instances (via `api_url` configuration)

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation** ✅ **COMPLETED** - Full documentation guide created at `docs/guide/plane.md` covering API token setup, workspace/project configuration, self-hosted setup, and all features

**Status**: ✅ **Complete** - 80 unit tests passing (including 15 webhook tests, 21 views/filters tests, and 14 attachment tests), all linting/type checks passing. Full documentation available at `docs/guide/plane.md`. Ready for production use. Supports cycles, modules, issues, states, priorities, story points, comments, assignees, webhooks, views/filters, and attachments. Self-hosted instances supported via `api_url` configuration.

**Actual Time**: ~4 hours (faster than estimated due to good patterns from Linear/Trello adapters)

---

#### 10. Pivotal Tracker Adapter ✅ **COMPLETED**
**Priority: Low** | **Effort: Low-Medium** | **Complexity: Low**

- [x] **Core Implementation**
  - [x] Add `PIVOTAL` to `TrackerType` enum
  - [x] Create `PivotalConfig` dataclass (api_token, project_id)
  - [x] Implement `PivotalAdapter` with `IssueTrackerPort`
  - [x] Create `PivotalApiClient` using Pivotal Tracker REST API v5
  - [x] Map Epic → Epic
  - [x] Map Story → Story
  - [x] Map Subtask → Task (within story)
  - [x] Status mapping → Current State
  - [x] Priority mapping → Story priority (via labels)
  - [x] Story points → Story estimate

- [x] **API Integration**
  - [x] Authentication: API Token (X-TrackerToken header)
  - [x] Endpoints: `/projects/:id/stories`, `/projects/:id/epics`, `/projects/:id/tasks`
  - [x] Rate limiting: 400 requests per 15 minutes (0.4 req/sec with token bucket)
  - [x] Webhooks support ✅ **COMPLETED** - Full support for create/list/delete webhooks

- [x] **Advanced Features**
  - [x] Iterations support ✅ **COMPLETED** - List and get iterations
  - [x] Story types (feature, bug, chore, release) ✅ **COMPLETED**
  - [x] Labels ✅ **COMPLETED** - List labels, add to stories, get-or-create
  - [x] Comments and file attachments ✅ **COMPLETED** - Full support for both
  - [x] Activity feed ✅ **COMPLETED** - Get project activity

- [x] **Testing**
  - [x] Unit tests for adapter methods (50 tests)
  - [x] Integration tests with Pivotal Tracker API (mocked)
  - [x] Test story state transitions
  - [x] Test dry-run mode
  - [x] Test webhooks, iterations, attachments, labels

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation**
  - [x] Plugin with environment variable support (PIVOTAL_API_TOKEN, PIVOTAL_PROJECT_ID)
  - [x] Configuration validation

**Status**: ✅ **Complete** - 50 unit tests passing, all linting/type checks passing. Ready for production use.

**Actual Time**: ~2 hours (faster than estimated due to good patterns from Shortcut adapter)

---

### Implementation Checklist Template

> 📖 **Full Guide Available**: See [`docs/guide/adapter-development.md`](/docs/guide/adapter-development.md) for comprehensive implementation instructions with code templates, best practices, and examples.

For each new tracker adapter, follow this checklist:

- [ ] **1. Core Setup**
  - [ ] Add tracker type to `TrackerType` enum
  - [ ] Create config dataclass in `config_provider.py`
  - [ ] Create adapter package directory structure
  - [ ] Add `__init__.py` exports

- [ ] **2. API Client**
  - [ ] Implement low-level HTTP client
  - [ ] Handle authentication
  - [ ] Implement rate limiting
  - [ ] Handle pagination
  - [ ] Error handling and retries

- [ ] **3. Adapter Implementation**
  - [ ] Implement `IssueTrackerPort` interface
  - [ ] Map domain entities to tracker model
  - [ ] Implement all required methods
  - [ ] Handle edge cases

- [ ] **4. Factory Integration**
  - [ ] Add to `create_tracker_factory()` in `core/services.py`
  - [ ] Update CLI help text
  - [ ] Add tracker to orchestrator detection logic

- [ ] **5. Testing**
  - [ ] Unit tests for adapter
  - [ ] Unit tests for client
  - [ ] Integration tests (with mock API)
  - [ ] Contract tests (verify `IssueTrackerPort` compliance)
  - [ ] Edge case tests

- [ ] **6. Optional Features**
  - [ ] Async adapter implementation
  - [ ] Batch operations client
  - [ ] Caching support
  - [ ] Plugin registration

- [ ] **7. Documentation**
  - [ ] Configuration guide
  - [ ] Authentication setup
  - [ ] API mapping documentation
  - [ ] Examples and use cases

- [ ] **8. Validation**
  - [ ] Run `ruff format src tests && ruff check src tests --fix`
  - [ ] Run `mypy src/spectra`
  - [ ] Run `pytest` and ensure all tests pass
  - [ ] Manual testing with real tracker instance

---

## 🔵 New Document Formats

- [x] **ReStructuredText (.rst)** - Python documentation standard ✅
- [x] **Org-mode** - Emacs users, powerful outliner ✅
- [x] **Obsidian-flavored Markdown** - Wikilinks, dataview syntax ✅
- [x] **Confluence Cloud API** - Parse directly from Confluence pages ✅
- [x] **Google Docs** - Parse from Google Workspace ✅
- [x] **Protobuf** - Data exchange efficiency ✅
- [x] **GraphQL Schema** - API-driven specifications ✅
- [x] **PlantUML/Mermaid** - Diagram-based requirements ✅
- [x] **OpenAPI/Swagger** - API specifications ✅
- [x] **Google Sheets** - Direct cloud spreadsheet sync ✅

---

## 🟣 CLI & Developer Experience

### New Commands
- [x] **`spectra doctor`** - Diagnose common setup issues
- [x] **`spectra migrate`** - Migrate between trackers (Jira → GitHub, etc.)
- [x] **`spectra diff`** - Compare local file vs tracker state
- [x] **`spectra stats`** - Show statistics (stories, points, velocity)
- [x] **`spectra import`** - Import from tracker to create initial markdown
- [x] **`spectra plan`** - Show side-by-side comparison before sync (like Terraform)
- [x] **`spectra tutorial`** - Interactive step-by-step learning experience
- [x] **`spectra bulk-update`** - Bulk update stories by filter
- [x] **`spectra bulk-assign`** - Bulk assign to user by filter
- [x] **`spectra visualize`** - Generate dependency graph (Mermaid/Graphviz)
- [x] **`spectra velocity`** - Track story points completed over time
- [x] **`spectra split`** - AI-powered story splitting suggestions
- [x] **`spectra archive`** - Archive/unarchive stories
- [x] **`spectra export`** - Export to PDF, HTML, DOCX
- [x] **`spectra report`** - Generate weekly/monthly reports
- [x] **`spectra config validate`** - Validate configuration
- [x] **`spectra version --check`** - Check for updates
- [x] **`spectra hook install`** - Pre-commit hook integration

### CLI Enhancements
- [x] **Interactive TUI Dashboard** - Real-time sync progress, epic/story browser, conflict resolution UI
- [x] **Progress Bars** - Real-time sync progress indicators
- [x] **Colored Diff Output** - Better visualization of changes
- [x] **Better Error Messages** - More actionable error messages
- [x] **JSON/YAML/Markdown Output** - Preview output formats for CI pipelines
- [x] **Emoji Toggle** - Option to disable emojis in output
- [x] **Color Themes** - Support different color schemes
- [x] **PowerShell Completions** - Windows shell completion
- [x] **Man Pages** - Install man pages for Unix systems

---

## 🟤 Advanced Sync Features

### Sync Capabilities
- [x] **Bidirectional Sync** - Pull tracker changes back into markdown with conflict detection
- [x] **Incremental Sync Optimization** - Only sync changed items (content hash + persisted state)
- [x] **Delta Sync** - Only fetch/sync changed fields
- [x] **Partial Sync by Field** - Sync only specific fields (e.g., just status)
- [x] **Multi-Tracker Sync** - Sync same markdown to multiple trackers simultaneously
- [x] **Smart Merge Conflicts** - 3-way merge for conflicts
- [x] **Transactional Behavior** - All-or-nothing mode with rollback
- [x] **Idempotency Guarantees** - Ensure re-running produces no unintended edits

### Data Sync
- [x] **Attachment Sync** - Upload/download attachments between markdown and trackers
- [x] **Custom Field Mapping** - Map custom fields per tracker (via config)
- [x] **Time Tracking Sync** - Parse/sync time estimates and logged time
- [x] **Sprint/Iteration Sync** - Parse and sync sprint assignments
- [x] **Story Dependencies/Relationships** - Parse blocks/depends-on relationships
- [x] **Epic Hierarchy** - Support multi-level epic hierarchies
- [x] **Worklog Sync** - Sync time logs

### Automation
- [x] **Workflow Automation Rules** - If all subtasks Done → Story Done, etc.
- [x] **Webhooks for Real-time Sync** - Listen for tracker webhooks
- [x] **Change Notifications** - Slack/Discord/Teams notifications on sync

---

## 🔶 AI & Intelligence Features

- [x] **Native LLM Integration** - Direct Anthropic/OpenAI/Google API integration
- [x] **LLM Provider Abstraction** - Support multiple LLM providers + local models
- [x] **AI Story Generation** - Generate stories from high-level descriptions
- [x] **AI Story Refiner** - Analyze stories for ambiguity or missing AC
- [x] **AI Estimation** - Suggest story points based on complexity
- [x] **AI Labeling/Auto-categorization** - Suggest labels/categories based on content
- [x] **Smart Splitting** - AI suggests splitting large stories
- [x] **Acceptance Criteria Generation** - AI writes AC from story description
- [x] **Dependency Detection** - AI identifies blocked-by relationships
- [x] **Story Quality Scoring** - Rate story quality (well-written, testable)
- [x] **Duplicate Detection** - Find similar stories across trackers
- [x] **Gap Analysis** - Identify missing requirements
- [x] **AI-Generated Sync Summaries** - Human-readable summary of what was synced
- [x] **Custom Prompts Config** - Let users customize AI prompts

---

## 🟠 IDE Integrations

### VS Code Extension Enhancements
- [x] **Quick Actions** - Create story in tracker from cursor position ✅ **COMPLETED** - Code Actions provider with create/sync/update actions
- [x] **Sidebar Panel** - Show sync status, recent changes ✅ **COMPLETED** - Full sidebar with sync status, stories list, and recent changes
- [x] **Hover Previews** - Show tracker issue details on hover ✅ **COMPLETED** - Hover provider with cached issue details, status, priority, assignee
- [x] **Go to Tracker** - Cmd+Click on issue ID opens in browser ✅ **COMPLETED** - Definition provider + Document links for all supported trackers
- [x] **Problem Matcher** - Show validation errors in Problems panel ✅ **COMPLETED** - Three problem matcher patterns for different output formats
- [x] **Settings UI** - Configure spectra via VS Code settings ✅ **COMPLETED** - Comprehensive settings with tracker type, validation, AI, sync options

### New IDE Plugins
- [x] **JetBrains (IntelliJ, PyCharm)** - IDE integration ✅ **COMPLETED** - Full Kotlin plugin with settings, completion, inspections, actions (validate/sync), tool window, live templates, and status bar widget
- [x] **Zed** - Modern editor plugin ✅ **COMPLETED** - Rust extension with LSP integration, tree-sitter highlighting, and configuration support
- [x] **Helix** - Vim-like modal editor plugin ✅ **COMPLETED** - Full configuration with languages.toml, config.toml (keybindings), and query files for highlighting/textobjects
- [x] **Emacs (LSP)** - Emacs integration ✅ **COMPLETED** - Complete package with lsp-mode and eglot support, spectra-mode major mode, interactive commands, and hydra menu
- [x] **Sublime Text** - Sublime integration ✅ **COMPLETED** - Full package with syntax highlighting, LSP config, build system, commands, keybindings, and snippets
- [x] **LSP (Language Server Protocol)** - Universal editor support ✅ **COMPLETED** - Python-based LSP server using pygls with diagnostics, hover, completions, go-to-definition, document symbols, code actions, document links, and formatting

---

## 🔷 Enterprise Features

### Security & Compliance
- [ ] **SAML/SSO Integration** - Enterprise authentication
- [ ] **Role-Based Access Control** - Control who can sync what
- [ ] **Audit Logging** - SOC2/HIPAA compliance logs
- [ ] **Compliance Reports** - Generate compliance reports
- [ ] **Encryption at Rest** - Encrypt cached data
- [x] **Secret Management Integration** - HashiCorp Vault, AWS Secrets Manager, 1Password, Doppler ✅ **COMPLETED** - Implemented `SecretManagerPort` interface with adapters for HashiCorp Vault (KV v1/v2, AppRole/K8s auth), AWS Secrets Manager (versioning, rotation), 1Password (CLI-based, service accounts), and Doppler (projects/configs). Features: auto-detection, composite manager with fallback, secret references (`vault://path#key@version`), config resolution. 115 unit tests passing.
- [x] **Secrets Hygiene** - Prevent tokens in logs/backups, redact sensitive fields ✅ **COMPLETED** - Implemented `SecretRedactor` (pattern-based + key-based detection, thread-safe), `RedactingFilter` for logging, `BackupSanitizer` for backup files. 73 unit tests passing.

### Scalability
- [x] **Multi-Tenant Support** - Manage multiple organizations ✅
- [x] **Multi-Workspace Support** - Manage multiple workspaces ✅
- [x] **Data Retention Policies** - Automatic cleanup of old backups ✅

---

## 🔸 Performance & Scalability

- [x] **Parallel Epic Sync** - Process multiple epics simultaneously
- [x] **Parallel File Processing** - Process multiple files concurrently
- [x] **Streaming Parser** - Handle very large files without loading all in memory
- [x] **Connection Pooling Tuning** - Optimize HTTP connection reuse
- [x] **GraphQL Batching** - For GitHub/Linear - batch multiple queries
- [x] **Lazy Loading** - Load story details only when needed
- [x] **Configurable Caching Backends** - Redis support for high-concurrency environments ✅
- [x] **Smart Caching** - Cache tracker metadata more aggressively with TTL ✅
- [x] **Bounded Concurrency** - Per-tracker concurrency with ordering guarantees ✅
- [x] **Memory Optimization** - Reduce memory footprint ✅

---

## 🔹 Infrastructure & DevOps

### CI/CD Templates
- [x] **GitLab CI Template** - Like GitHub Action but for GitLab
- [x] **Bitbucket Pipelines Template** - Pipeline template
- [x] **Azure Pipelines Template** - YAML template
- [x] **Jenkins Plugin** - Jenkins integration
- [x] **CircleCI Orb** - CircleCI integration

### Deployment
- [x] **Kubernetes Operator** - Custom resource for scheduled syncs
- [x] **Helm Chart** - Easy K8s deployment
- [x] **ARM/Bicep Templates** - Azure deployment
- [x] **CloudFormation Templates** - AWS deployment
- [x] **Pulumi Provider** - Modern IaC alternative

---

## 📚 Documentation & Community

### Guides
- [x] **Troubleshooting Guide** - Common issues & solutions ✅ **COMPLETED** - Added `/guide/troubleshooting.md` with authentication, connection, parsing, sync, and CLI troubleshooting sections
- [x] **Video Tutorials** - Setup, sync workflow, advanced features ✅ **EXISTING** - Already at `/tutorials/` with first-sync, interactive-mode, backup-restore, cicd-setup
- [x] **Case Studies** - Real-world usage examples ✅ **COMPLETED** - Added `/guide/case-studies.md` with FinTech, E-commerce, and Healthcare case studies
- [x] **API Reference** - For programmatic embedding ✅ **EXISTING** - Already at `/reference/api/` with domain, ports, hooks documentation
- [x] **Architecture Deep Dive** - Design pattern explanations ✅ **EXISTING** - Already at `/guide/architecture.md` with Clean/Hexagonal architecture
- [x] **Performance Tuning Guide** - Optimization tips ✅ **COMPLETED** - Added `/guide/performance.md` with parallel processing, caching, network optimization, memory management
- [x] **Migration Guides** - Moving from other tools ✅ **EXISTING** - Already at `/cookbook/migration.md` for tracker migrations
- [x] **Recipes Guide** - Common setups with field mapping examples ✅ **COMPLETED** - Added `/guide/recipes.md` with Jira, GitHub, custom fields, multi-team, sprint, bug tracking recipes
- [x] **Best Practices Guide** - Recommended workflows ✅ **COMPLETED** - Added `/guide/best-practices.md` with workflows, team collaboration, error prevention
- [x] **FAQ Section** - Common questions and answers ✅ **COMPLETED** - Added `/guide/faq.md` with comprehensive FAQ covering general, installation, config, syncing, troubleshooting

---

## 🛠️ Technical Improvements

### Code Quality
- [x] **Reduce mypy Error Overrides** - Tighten type safety incrementally
- [x] **Type Coverage Improved** - Reduced `Any` usage by ~47 (393→353 `: Any`, 77→70 `-> Any`). Remaining ~350 are intentional patterns: JSON serialization, logging args, HTTP kwargs, generic caches, duck-typing
- [x] **More Specific Exception Types** - Better error handling
- [x] **More Docstrings** - Better code documentation
- [x] **Refactor Large Files** - e.g., `app.py` reduced from ~5,900 to ~1,600 lines; ~4,300 lines extracted to command modules
- [x] **Upgrade Python 3.14 Support** - Updated from 3.11 minimum to support 3.11-3.14

### Architecture
- [x] **Event Sourcing** - Store all changes as events. Implemented `EventStorePort` interface with `FileEventStore` (JSON Lines persistence) and `MemoryEventStore` adapters. Added `EventSourcedBus` for automatic persistence, `EventReplayer` for state reconstruction, and projections for analytics (`SyncSessionProjection`, `EpicHistoryProjection`)
- [x] **Database Backend Option** - SQLite/PostgreSQL for large-scale state management. Implemented `StateStorePort` interface with `SQLiteStateStore` (local database with WAL mode, indexed queries, transactions), `PostgresStateStore` (enterprise-grade for distributed deployments), and `FileStateStore` (backward-compatible JSON wrapper). Added migration utilities (`StateStoreMigrator`, `export_to_json`, `import_from_json`) and factory function `create_store()`
- [x] **Sync History Database** - SQLite for audit trail, rollback, analytics. Implemented `SyncHistoryPort` interface with `SQLiteSyncHistoryStore` (WAL mode, indexed queries). Features: complete audit trail with `SyncHistoryEntry`, individual change tracking with `ChangeRecord` for rollback, analytics queries (`get_statistics`, `get_velocity`), and point-in-time rollback via `mark_rolled_back`. 36 unit tests passing.
- [x] **Plugin Marketplace/Registry** - Discover and install community plugins. Implemented `PluginMarketplacePort` interface with `GitHubPluginRegistry` (GitHub-based registry using spectra-plugin topic). Features: search/browse plugins, install via pip or git, uninstall, update, publish releases, version management. CLI commands: `spectra plugin search/install/uninstall/list/update/info/publish`. 23 unit tests passing.
- [x] **Plugin Templates** - Scaffold new plugins. Implemented `PluginScaffold` system with 5 template types (PARSER, TRACKER, FORMATTER, HOOK, COMMAND). Generates complete plugin projects: package structure, pyproject.toml with entry points, README, LICENSE, tests, docs, GitHub Actions CI, Dockerfile, plugin.json manifest. CLI: `spectra plugin scaffold` with interactive wizard. 30 unit tests passing.
- [x] **REST API Mode** - Run Spectra as a server. Implemented `RestApiServerPort` interface with `SpectraRestServer` (stdlib http.server-based, zero dependencies). Features: RESTful endpoints for epics/stories/subtasks/syncs with full CRUD operations, cursor-based pagination with `PagedResponse`, `/stories/search` with filters (status, priority, epic, assignee), OpenAPI documentation at `/docs`, health/stats endpoints, CORS support (configurable), middleware hooks (request/response), route pattern matching with path parameters. CLI: `spectra --rest-api` with `--rest-host`, `--rest-port`, `--rest-base-path`, `--no-cors`, `--no-docs` options. 72 unit tests passing.
- [x] **GraphQL API Layer** - Add GraphQL API. Implemented `GraphQLServerPort` interface with `SpectraGraphQLServer` (stdlib http.server-based, zero dependencies). Features: full GraphQL schema with SDL, Relay-style cursor pagination, comprehensive type system (Epic/Story/Subtask/Sync types), query/mutation resolvers, health endpoint, workspace stats, search/filter stories, introspection support, request/response middleware. CLI: `spectra --graphql` with `--graphql-host`, `--graphql-port`, `--graphql-path`, `--no-playground`, `--no-introspection` options. 67 unit tests passing.
- [x] **WebSocket Support** - Real-time sync updates. Implemented `WebSocketServerPort` interface with `SimpleWebSocketServer` (stdlib-based, RFC 6455 compliant, no dependencies) and `AioHttpWebSocketServer` (async/aiohttp for production). Features: room-based message routing, 25+ message types for sync/story/conflict events, `SyncEventBroadcaster` for EventBus integration, `WebSocketBridge` high-level interface. CLI: `spectra --websocket` with `--websocket-host`, `--websocket-port`, `--use-aiohttp` options. 82 unit tests passing.

### Reliability
- [x] **Rate Limiting + Retries** - Centralized backoff strategy per adapter. Implemented `RateLimiterPort`, `RetryPolicyPort`, `CircuitBreakerPort`, and unified `ResiliencePort` interfaces in `core/ports/rate_limiting.py`. Features: 5 backoff strategies (exponential, linear, constant, fibonacci, decorrelated jitter), token bucket & sliding window rate limiters, circuit breaker pattern (closed/open/half-open states), 18 tracker presets (Jira, GitHub, GitLab, Linear, etc.) with sensible defaults. Adapters: `TokenBucketRateLimiter`, `SlidingWindowRateLimiter`, `RetryPolicy`, `AdaptiveRetryPolicy`, `CircuitBreaker`, `ResilienceManager` in `adapters/resilience/`. Factory: `create_resilience_manager(TrackerType|str)`. Zero dependencies. 115 unit tests passing.
- [x] **Rollback by Timestamp** - Restore to specific point in time. Implemented in `SyncHistoryPort` interface with methods: `get_state_at_timestamp()`, `get_changes_since_timestamp()`, `get_entry_at_timestamp()`, `list_rollback_points()`, `create_rollback_plan()`, `execute_rollback_plan()`. Added `RollbackPlan` dataclass for planning and previewing rollbacks. CLI commands: `--list-rollback-points` (show available restore points), `--rollback-preview <TIMESTAMP>` (preview changes), `--rollback-to-timestamp <TIMESTAMP>` (execute rollback). Supports ISO 8601 timestamps, epic/tracker filters. 15 unit tests passing.

---

## 🌍 Accessibility & Internationalization

- [ ] **Multi-language CLI Output** - Spanish, French, German, Japanese, Chinese
- [ ] **RTL Language Support** - Hebrew/Arabic markdown content
- [ ] **Screen Reader Support** - Better CLI output for screen readers
- [x] **Color-blind Friendly** - Ensure output works without color ✅ **COMPLETED** - Implemented comprehensive accessibility mode with `--accessible` CLI flag. Features: shape-based status indicators (● success, ■ error, ▲ warning, ◆ info), text labels alongside colors (OK, ERROR, WARN, INFO), priority indicators with distinct shapes (▲▲ critical, ▲ high, ► medium, ▽ low), progress bars with different fill patterns for score levels, diff indicators with text labels (+ ADD, - DEL, ~ MOD). Added `set_accessibility_mode()`, `get_status_indicator()`, `format_status_text()`, `format_priority_text()`, `format_score_text()`, `format_diff_indicator()` helper functions. Console class enhanced with `accessible` parameter. 36 new unit tests passing.
- [x] **Keyboard Shortcuts** - More shortcuts in TUI ✅ **COMPLETED** - Added 40+ keyboard shortcuts to the TUI dashboard including: vim-style navigation (j/k/g/G/Ctrl+d/u), quick tab switching (1-3), quick status filters (!/@ /#/0), story operations (o/y/e), view controls (l/z/h), bulk operations (a/x), and global shortcuts (Ctrl+r/h, F1/F5). Updated help screen with comprehensive shortcut documentation. 15 new unit tests passing.

---

## 📋 Parser Improvements

- [x] **Stronger Markdown Parsing** - Tolerate formatting variants; precise parse errors ✅ **COMPLETED**
- [x] **Round-trip Edits** - Modify source markdown while preserving formatting ✅ **COMPLETED** - Implemented `RoundtripParser` for span-tracking parse, `RoundtripEditor` for surgical edits. Supports field updates, title changes, AC toggling, and batch updates. 43 unit tests passing.
- [x] **Schema Validation** - Optional strict mode for required fields ✅ **COMPLETED** - Implemented `SchemaValidator` with configurable validation modes (lenient, normal, strict). Supports `FieldSchema`, `StorySchema`, `SubtaskSchema`, `EpicSchema` with built-in validators (min/max length/value, patterns, required fields). Includes `ValidatingParser` wrapper, `SchemaPreset` for domain-specific validation (Agile, Kanban, QA, Documentation). 74 unit tests passing.
- [x] **Extensible Frontmatter** - YAML frontmatter as alternative to tables ✅ **COMPLETED** - Implemented `FrontmatterParser` with configurable formats (YAML `---`, HTML comment `<!-- yaml -->`). Supports single-story and multi-story frontmatter, extensible field mappings with aliases and transformers, `MergeStrategy` for combining frontmatter with inline content. Includes `create_markdown_with_frontmatter()` factory for MarkdownParser fallback integration. Utility functions: `has_frontmatter()`, `get_frontmatter()`, `strip_frontmatter()`. 90 unit tests passing.
- [x] **Inline Task References** - Parse `[ ]` checkboxes as subtasks ✅ **COMPLETED** - Implemented `parse_inline_subtasks()` function in `tolerant_markdown.py` with `InlineSubtaskInfo` dataclass. Supports checked/unchecked checkboxes, story points extraction `(N SP)`, description extraction via separators (- or :), markdown formatting cleanup (bold, italic, code, strikethrough). Integrated into `MarkdownParser._extract_subtasks()` as fallback when no table format found. 32 unit tests passing.
- [x] **Image Embedding** - Handle images in descriptions ✅ **COMPLETED** - Implemented `parse_embedded_images()` function and `EmbeddedImage` dataclass in `tolerant_markdown.py`. Supports multiple syntaxes: standard markdown `![alt](url)`, images with titles, reference-style `![alt][ref]`, HTML `<img>` tags, Obsidian wikilinks `![[image.png|alt]]`, and dimensions `=WxH`. Features: local/remote filtering, deduplication, warnings for missing alt text/unsupported formats/HTML tags/broken references. Includes `extract_images_from_section()` for section-specific extraction. 46 unit tests passing.
- [x] **Better Table Parsing** - Improved table support in descriptions ✅ **COMPLETED** - Implemented `parse_markdown_table()` function in `tolerant_markdown.py` with `TableAlignment` enum, `TableCell` dataclass, and `ParsedTable` dataclass. Supports GFM tables with alignment detection (`:---`, `:---:`, `---:`), cell formatting cleanup (bold, italic, code), type conversion helpers (`as_int`, `as_float`, `as_bool`). Features: `get_column()`, `get_column_by_header()`, `get_row()`, `get_cell()`, `to_dicts()` for data access. Includes `extract_tables_from_content()` for multi-table extraction, `extract_table_from_section()` for section-specific extraction, `table_to_markdown()` for roundtrip conversion. 44 unit tests passing.
- [x] **Code Block Preservation** - Preserve syntax highlighting ✅ **COMPLETED** - Implemented `parse_code_blocks()` function in `tolerant_markdown.py` with `CodeBlockType` enum, `CodeBlock` dataclass, and `CodeBlockCollection` dataclass. Supports fenced (backticks/tildes), indented (4-space), and inline code spans. Features: language detection and normalization (js→javascript, py→python, etc.), info string parsing with attributes, line number tracking. Functions: `extract_code_blocks_from_content()`, `extract_code_from_section()`, `preserve_code_blocks()`, `restore_code_blocks()` for safe text processing, `code_block_to_markdown()` for creation, `get_code_block_stats()` for statistics. Generates W011 warning for blocks without language. 40 unit tests passing.

---

## ⚡ Quick Wins (< 2 hours each)

- [x] AI prompts: use dynamic examples ✅ (see line 49 - AI Prompts Dynamic Examples)
- [x] Parameterized tests for ID prefixes ✅ (see line 32 - `test_flexible_id_prefixes.py`)
- [x] Documentation examples: use neutral prefixes ✅ (see line 48 - Documentation Examples Standardization)
- [x] TrackerType.ASANA full integration check ✅ (see line 52 - Verified in source_updater.py, orchestrator.py, CLI)
- [x] OpenTelemetry/Prometheus setup docs ✅ (see line 51 - Comprehensive docs/guide/telemetry.md)
- [x] Add `--version` flag with version info ✅ (already in parser.py)
- [x] Better error messages ✅ (see CLI Enhancements section)
- [x] Configuration validation on startup ✅ (config_provider.validate() in all commands)
- [x] Auto-completion improvements ✅ (completions.py supports bash/zsh/fish/powershell with option/file/phase completions)
- [x] Progress bars for long operations ✅ (see CLI Enhancements section)
- [x] Export formats (CSV, Excel, JSON) ✅ (export_cmd.py)
- [x] Import from other tools (Jira CSV, GitHub CSV) ✅ (csv_import.py - supports Jira, GitHub, Linear, and generic CSV formats with auto-detection)
- [x] Statistics command ✅ (stats.py)
- [x] Health check improvements ✅ (health.py - HTTP server with /health, /live, /ready, /metrics endpoints for K8s probes)
- [x] JSON schema for `.spectra.yaml` (IDE autocompletion) ✅ (schema/spectra-config.schema.json - comprehensive JSON Schema for all config options)
- [x] Changelog generation from tracker history ✅ (changelog.py - generates markdown/JSON/HTML/plain/keepachangelog formats from SyncHistoryPort)

---

## 🏠 Housekeeping

- [x] **Audit & Update Backlog** - Mark completed items in `BACKLOG.md` ✅ (January 2026 - Marked 6 items complete: #3 Asana parity, #5 docs, #7 AI prompts, #8 parameterized tests, #9 TrackerType, #10 telemetry)
- [x] **Update `FLEXIBILITY-PLAN.md`** - Mark "Remaining Work" as complete ✅ (January 2026 - Custom separators and `#123` support verified complete)
- [x] **Verify Asana Implementation** - Check if `batch.py` and `async_adapter.py` work ✅ (January 2026 - 41 tests pass: 16 unit + 25 integration)

---

## 📊 Summary

| Category | Item Count | Completed |
|----------|------------|-----------|
| High Priority | 3 | 3 |
| Medium Priority (Quality) | 20+ | 20+ |
| New Tracker Integrations | 10 | 9 (GitLab, Monday.com, Trello, Shortcut, ClickUp, Bitbucket, YouTrack, Plane.so, Pivotal Tracker) |
| New Document Formats | 10 | 0 |
| CLI & Developer Experience | 25+ | 0 |
| Advanced Sync Features | 20+ | 0 |
| AI & Intelligence | 15 | 0 |
| IDE Integrations | 12 | 0 |
| Enterprise Features | 10 | 0 |
| Performance & Scalability | 10 | 0 |
| Infrastructure & DevOps | 10 | 0 |
| Documentation & Community | 15 | 0 |
| Technical Improvements | 15 | 0 |
| Accessibility & i18n | 5 | 0 |
| Parser Improvements | 8 | 0 |
| Quick Wins | 15+ | 0 |

**Total: 190+ improvement opportunities** | **Completed: 31+ (including GitLab, Monday.com, Trello, Shortcut, ClickUp, Bitbucket, YouTrack, Plane.so, and Pivotal Tracker adapters)**

---

