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
- [ ] **Code Coverage 80%+** - Currently 71.11%, target 80%+ (3003 tests passing)
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

#### 7. YouTrack Adapter
**Priority: Low** | **Effort: Medium** | **Complexity: Medium** | **Status: ✅ Core Implementation Complete**

**Note**: Core adapter is fully functional for basic issue tracking. Advanced features listed below are optional enhancements for future work.

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
  - [ ] Custom fields support (only story points implemented, not full custom fields)

- [ ] **Advanced Features** (Optional - Future Enhancements)

  **High Priority Enhancements** (commonly requested):
  - [x] Basic custom fields mapping (story points field support) ✅ **Core Feature**
  - [ ] Full custom fields support (all field types, dynamic discovery)
  - [ ] Bulk operations (batch create/update/delete issues)
  - [ ] File attachments (upload, download, delete attachments)

  **Medium Priority Enhancements** (workflow improvements):
  - [ ] Workflow automation (state transitions, issue commands)
  - [ ] Due dates support (set/get due dates)
  - [ ] Tags/labels support (YouTrack tags)
  - [ ] Watchers/observers (add/remove watchers, notifications)

  **Low Priority Enhancements** (nice-to-have):
  - [ ] Agile boards integration (YouTrack boards/views)
  - [ ] Sprints support (YouTrack sprints/iterations)
  - [ ] Time tracking (work items, time estimates)
  - [ ] Issue history/activity feed (get issue change history)
  - [ ] Mentions in comments (@user mentions)

- [x] **Testing**
  - [x] Unit tests for adapter methods (28 tests)
  - [ ] Unit tests for API client (needs dedicated test_youtrack_client.py)
  - [x] Contract tests for adapter interface compliance (6 tests)
  - [x] Integration tests with mocked YouTrack API responses (11 tests)
  - [x] Test custom fields (story points only)
  - [ ] Test rate limiting and retry logic
  - [ ] Test error handling (403, 500, network errors, timeouts)
  - [ ] Test edge cases (empty responses, malformed JSON, connection errors)
  - [ ] Test connection pooling and session management
  - [ ] Test dry-run mode for all write operations
  - [ ] Integration tests with live YouTrack API (requires live instance)

- [x] **Dependencies**
  - [x] `requests` (already in dependencies)

- [x] **Documentation**
  - [x] Token setup
  - [x] Project configuration
  - [x] Custom fields mapping

**Status**: ✅ **Core implementation complete** - 45 tests passing (28 unit + 6 contract + 11 integration), all linting/type checks passing. Ready for basic use. Supports core IssueTrackerPort operations: create/read/update issues, subtasks, comments, links, status transitions, and search. Story points custom field is supported; full custom fields support is not yet implemented. Dedicated client tests and advanced features are pending.

**Estimated Time**: 2-3 days (core) | Advanced features: 1-2 days each

---

#### 8. Basecamp Adapter
**Priority: Low** | **Effort: Medium** | **Complexity: Medium**

- [ ] **Core Implementation**
  - [ ] Add `BASECAMP` to `TrackerType` enum
  - [ ] Create `BasecampConfig` dataclass (access_token, account_id, project_id)
  - [ ] Implement `BasecampAdapter` with `IssueTrackerPort`
  - [ ] Create `BasecampApiClient` using Basecamp 3 API
  - [ ] Map Epic → Project or Message Board category
  - [ ] Map Story → Todo or Message
  - [ ] Map Subtask → Todo list item
  - [ ] Status mapping → Todo completion status
  - [ ] Priority mapping → Not natively supported (use notes)
  - [ ] Story points → Not natively supported (use notes)

- [ ] **API Integration**
  - [ ] Authentication: OAuth 2.0 (access token)
  - [ ] Endpoints: `/projects/:id/todosets`, `/projects/:id/todos`, `/projects/:id/messages`
  - [ ] Rate limiting: 40 requests per 10 seconds
  - [ ] Webhooks support

- [ ] **Advanced Features**
  - [ ] Todo lists and todos
  - [ ] Message boards
  - [ ] Comments and file attachments
  - [ ] Campfire (chat) integration (optional)

- [ ] **Testing**
  - [ ] Unit tests for adapter methods
  - [ ] Integration tests with Basecamp API
  - [ ] Test OAuth flow

- [ ] **Dependencies**
  - [ ] `requests` + `requests-oauthlib` for OAuth

- [ ] **Documentation**
  - [ ] OAuth setup
  - [ ] Account and project configuration
  - [ ] Todo vs Message mapping

**Estimated Time**: 2-3 days

---

#### 9. Plane.so Adapter
**Priority: Low** | **Effort: Medium** | **Complexity: Medium**

- [ ] **Core Implementation**
  - [ ] Add `PLANE` to `TrackerType` enum
  - [ ] Create `PlaneConfig` dataclass (api_token, workspace_slug, project_id)
  - [ ] Implement `PlaneAdapter` with `IssueTrackerPort`
  - [ ] Create `PlaneApiClient` using Plane REST API
  - [ ] Map Epic → Cycle or Module
  - [ ] Map Story → Issue
  - [ ] Map Subtask → Sub-issue or checklist item
  - [ ] Status mapping → State
  - [ ] Priority mapping → Priority
  - [ ] Story points → Estimate

- [ ] **API Integration**
  - [ ] Authentication: API Token
  - [ ] Endpoints: `/workspaces/:slug/projects/:id/issues`, `/cycles`, `/modules`
  - [ ] Support self-hosted instances
  - [ ] Rate limiting: Varies by instance
  - [ ] Webhooks support

- [ ] **Advanced Features**
  - [ ] Cycles (sprints) support
  - [ ] Modules (epics) support
  - [ ] Views and filters
  - [ ] Labels and assignees
  - [ ] Comments and attachments

- [ ] **Testing**
  - [ ] Unit tests for adapter methods
  - [ ] Integration tests with Plane API
  - [ ] Test self-hosted instances

- [ ] **Dependencies**
  - [ ] `requests` (already in dependencies)

- [ ] **Documentation**
  - [ ] API token setup
  - [ ] Workspace and project configuration
  - [ ] Self-hosted setup

**Estimated Time**: 2-3 days

---

#### 10. Pivotal Tracker Adapter
**Priority: Low** | **Effort: Low-Medium** | **Complexity: Low**

- [ ] **Core Implementation**
  - [ ] Add `PIVOTAL` to `TrackerType` enum
  - [ ] Create `PivotalConfig` dataclass (api_token, project_id)
  - [ ] Implement `PivotalAdapter` with `IssueTrackerPort`
  - [ ] Create `PivotalApiClient` using Pivotal Tracker REST API v5
  - [ ] Map Epic → Epic
  - [ ] Map Story → Story
  - [ ] Map Subtask → Task (within story)
  - [ ] Status mapping → Current State
  - [ ] Priority mapping → Story priority
  - [ ] Story points → Story estimate

- [ ] **API Integration**
  - [ ] Authentication: API Token
  - [ ] Endpoints: `/projects/:id/stories`, `/projects/:id/epics`
  - [ ] Rate limiting: 400 requests per 15 minutes
  - [ ] Webhooks support

- [ ] **Advanced Features**
  - [ ] Iterations support
  - [ ] Story types (feature, bug, chore, release)
  - [ ] Labels
  - [ ] Comments and file attachments
  - [ ] Activity feed

- [ ] **Testing**
  - [ ] Unit tests for adapter methods
  - [ ] Integration tests with Pivotal Tracker API
  - [ ] Test story state transitions

- [ ] **Dependencies**
  - [ ] `requests` (already in dependencies)

- [ ] **Documentation**
  - [ ] API token setup
  - [ ] Project configuration
  - [ ] Story type mapping

**Estimated Time**: 1-2 days

---

### Implementation Checklist Template

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

- [ ] **ReStructuredText (.rst)** - Python documentation standard
- [ ] **Org-mode** - Emacs users, powerful outliner
- [ ] **Obsidian-flavored Markdown** - Wikilinks, dataview syntax
- [ ] **Confluence Cloud API** - Parse directly from Confluence pages
- [ ] **Google Docs** - Parse from Google Workspace
- [ ] **Protobuf** - Data exchange efficiency
- [ ] **GraphQL Schema** - API-driven specifications
- [ ] **PlantUML/Mermaid** - Diagram-based requirements
- [ ] **OpenAPI/Swagger** - API specifications
- [ ] **Google Sheets** - Direct cloud spreadsheet sync

---

## 🟣 CLI & Developer Experience

### New Commands
- [ ] **`spectra doctor`** - Diagnose common setup issues
- [ ] **`spectra migrate`** - Migrate between trackers (Jira → GitHub, etc.)
- [ ] **`spectra diff`** - Compare local file vs tracker state
- [ ] **`spectra stats`** - Show statistics (stories, points, velocity)
- [ ] **`spectra import`** - Import from tracker to create initial markdown
- [ ] **`spectra plan`** - Show side-by-side comparison before sync (like Terraform)
- [ ] **`spectra tutorial`** - Interactive step-by-step learning experience
- [ ] **`spectra bulk-update`** - Bulk update stories by filter
- [ ] **`spectra bulk-assign`** - Bulk assign to user by filter
- [ ] **`spectra visualize`** - Generate dependency graph (Mermaid/Graphviz)
- [ ] **`spectra velocity`** - Track story points completed over time
- [ ] **`spectra split`** - AI-powered story splitting suggestions
- [ ] **`spectra archive`** - Archive/unarchive stories
- [ ] **`spectra export`** - Export to PDF, HTML, DOCX
- [ ] **`spectra report`** - Generate weekly/monthly reports
- [ ] **`spectra config validate`** - Validate configuration
- [ ] **`spectra version --check`** - Check for updates
- [ ] **`spectra hook install`** - Pre-commit hook integration

### CLI Enhancements
- [ ] **Interactive TUI Dashboard** - Real-time sync progress, epic/story browser, conflict resolution UI
- [ ] **Progress Bars** - Real-time sync progress indicators
- [ ] **Colored Diff Output** - Better visualization of changes
- [ ] **Better Error Messages** - More actionable error messages
- [ ] **JSON/YAML/Markdown Output** - Preview output formats for CI pipelines
- [ ] **Emoji Toggle** - Option to disable emojis in output
- [ ] **Color Themes** - Support different color schemes
- [ ] **PowerShell Completions** - Windows shell completion
- [ ] **Man Pages** - Install man pages for Unix systems
- [ ] **Default Epic from Git Branch** - Parse `feature/PROJ-123-foo` automatically

---

## 🟤 Advanced Sync Features

### Sync Capabilities
- [ ] **Bidirectional Sync** - Pull tracker changes back into markdown with conflict detection
- [ ] **Incremental Sync Optimization** - Only sync changed items (content hash + persisted state)
- [ ] **Delta Sync** - Only fetch/sync changed fields
- [ ] **Partial Sync by Field** - Sync only specific fields (e.g., just status)
- [ ] **Multi-Tracker Sync** - Sync same markdown to multiple trackers simultaneously
- [ ] **Smart Merge Conflicts** - 3-way merge for conflicts
- [ ] **Transactional Behavior** - All-or-nothing mode with rollback
- [ ] **Idempotency Guarantees** - Ensure re-running produces no unintended edits

### Data Sync
- [ ] **Attachment Sync** - Upload/download attachments between markdown and trackers
- [ ] **Custom Field Mapping** - Map custom fields per tracker (via config)
- [ ] **Time Tracking Sync** - Parse/sync time estimates and logged time
- [ ] **Sprint/Iteration Sync** - Parse and sync sprint assignments
- [ ] **Story Dependencies/Relationships** - Parse blocks/depends-on relationships
- [ ] **Epic Hierarchy** - Support multi-level epic hierarchies
- [ ] **Worklog Sync** - Sync time logs

### Automation
- [ ] **Workflow Automation Rules** - If all subtasks Done → Story Done, etc.
- [ ] **Webhooks for Real-time Sync** - Listen for tracker webhooks
- [ ] **Change Notifications** - Slack/Discord/Teams notifications on sync

---

## 🔶 AI & Intelligence Features

- [ ] **Native LLM Integration** - Direct Anthropic/OpenAI/Google API integration
- [ ] **LLM Provider Abstraction** - Support multiple LLM providers + local models
- [ ] **AI Story Generation** - Generate stories from high-level descriptions
- [ ] **AI Story Refiner** - Analyze stories for ambiguity or missing AC
- [ ] **AI Estimation** - Suggest story points based on complexity
- [ ] **AI Labeling/Auto-categorization** - Suggest labels/categories based on content
- [ ] **Smart Splitting** - AI suggests splitting large stories
- [ ] **Acceptance Criteria Generation** - AI writes AC from story description
- [ ] **Dependency Detection** - AI identifies blocked-by relationships
- [ ] **Story Quality Scoring** - Rate story quality (well-written, testable)
- [ ] **Duplicate Detection** - Find similar stories across trackers
- [ ] **Gap Analysis** - Identify missing requirements
- [ ] **AI-Generated Sync Summaries** - Human-readable summary of what was synced
- [ ] **Custom Prompts Config** - Let users customize AI prompts

---

## 🟠 IDE Integrations

### VS Code Extension Enhancements
- [ ] **Quick Actions** - Create story in tracker from cursor position
- [ ] **Sidebar Panel** - Show sync status, recent changes
- [ ] **Hover Previews** - Show tracker issue details on hover
- [ ] **Go to Tracker** - Cmd+Click on issue ID opens in browser
- [ ] **Problem Matcher** - Show validation errors in Problems panel
- [ ] **Settings UI** - Configure spectra via VS Code settings

### New IDE Plugins
- [ ] **JetBrains (IntelliJ, PyCharm)** - IDE integration
- [ ] **Zed** - Modern editor plugin
- [ ] **Helix** - Vim-like modal editor plugin
- [ ] **Emacs (LSP)** - Emacs integration
- [ ] **Sublime Text** - Sublime integration
- [ ] **LSP (Language Server Protocol)** - Universal editor support

---

## 🔷 Enterprise Features

### Security & Compliance
- [ ] **SAML/SSO Integration** - Enterprise authentication
- [ ] **Role-Based Access Control** - Control who can sync what
- [ ] **Audit Logging** - SOC2/HIPAA compliance logs
- [ ] **Compliance Reports** - Generate compliance reports
- [ ] **Encryption at Rest** - Encrypt cached data
- [ ] **Secret Management Integration** - HashiCorp Vault, AWS Secrets Manager, 1Password, Doppler
- [ ] **Secrets Hygiene** - Prevent tokens in logs/backups, redact sensitive fields

### Scalability
- [ ] **Multi-Tenant Support** - Manage multiple organizations
- [ ] **Multi-Workspace Support** - Manage multiple workspaces
- [ ] **Data Retention Policies** - Automatic cleanup of old backups

---

## 🔸 Performance & Scalability

- [ ] **Parallel Epic Sync** - Process multiple epics simultaneously
- [ ] **Parallel File Processing** - Process multiple files concurrently
- [ ] **Streaming Parser** - Handle very large files without loading all in memory
- [ ] **Connection Pooling Tuning** - Optimize HTTP connection reuse
- [ ] **GraphQL Batching** - For GitHub/Linear - batch multiple queries
- [ ] **Lazy Loading** - Load story details only when needed
- [ ] **Configurable Caching Backends** - Redis support for high-concurrency environments
- [ ] **Smart Caching** - Cache tracker metadata more aggressively with TTL
- [ ] **Bounded Concurrency** - Per-tracker concurrency with ordering guarantees
- [ ] **Memory Optimization** - Reduce memory footprint

---

## 🔹 Infrastructure & DevOps

### CI/CD Templates
- [ ] **GitLab CI Template** - Like GitHub Action but for GitLab
- [ ] **Bitbucket Pipelines Template** - Pipeline template
- [ ] **Azure Pipelines Template** - YAML template
- [ ] **Jenkins Plugin** - Jenkins integration
- [ ] **CircleCI Orb** - CircleCI integration

### Deployment
- [ ] **Kubernetes Operator** - Custom resource for scheduled syncs
- [ ] **Helm Chart** - Easy K8s deployment
- [ ] **ARM/Bicep Templates** - Azure deployment
- [ ] **CloudFormation Templates** - AWS deployment
- [ ] **Pulumi Provider** - Modern IaC alternative

---

## 📚 Documentation & Community

### Guides
- [ ] **Troubleshooting Guide** - Common issues & solutions
- [ ] **Video Tutorials** - Setup, sync workflow, advanced features
- [ ] **Case Studies** - Real-world usage examples
- [ ] **API Reference** - For programmatic embedding
- [ ] **Architecture Deep Dive** - Design pattern explanations
- [ ] **Performance Tuning Guide** - Optimization tips
- [ ] **Migration Guides** - Moving from other tools
- [ ] **Recipes Guide** - Common setups with field mapping examples
- [ ] **Best Practices Guide** - Recommended workflows
- [ ] **FAQ Section** - Common questions and answers

### Community
- [ ] **Example Repository** - GitHub repo with real examples users can clone
- [ ] **Interactive Playground** - Web-based demo
- [ ] **Blog/Announcement Site** - Updates, tips, community
- [ ] **Discord/Slack Community** - User community

---

## 🛠️ Technical Improvements

### Code Quality
- [ ] **Reduce mypy Error Overrides** - Tighten type safety incrementally
- [ ] **Type Coverage 100%** - Reduce `Any` usage, improve type hints
- [ ] **More Specific Exception Types** - Better error handling
- [ ] **More Docstrings** - Better code documentation
- [ ] **Refactor Large Files** - e.g., `app.py`
- [ ] **Upgrade Python 3.12 Support** - Current target is 3.11

### Architecture
- [ ] **Event Sourcing** - Store all changes as events
- [ ] **Database Backend Option** - SQLite/PostgreSQL for large-scale state management
- [ ] **Sync History Database** - SQLite for audit trail, rollback, analytics
- [ ] **Plugin Marketplace/Registry** - Discover and install community plugins
- [ ] **Plugin Templates** - Scaffold new plugins
- [ ] **REST API Mode** - Run Spectra as a server
- [ ] **GraphQL API Layer** - Add GraphQL API
- [ ] **WebSocket Support** - Real-time sync updates

### Reliability
- [ ] **Rate Limiting + Retries** - Centralized backoff strategy per adapter
- [ ] **Rollback by Timestamp** - Restore to specific point in time

---

## 🌍 Accessibility & Internationalization

- [ ] **Multi-language CLI Output** - Spanish, French, German, Japanese, Chinese
- [ ] **RTL Language Support** - Hebrew/Arabic markdown content
- [ ] **Screen Reader Support** - Better CLI output for screen readers
- [ ] **Color-blind Friendly** - Ensure output works without color
- [ ] **Keyboard Shortcuts** - More shortcuts in TUI

---

## 📋 Parser Improvements

- [ ] **Stronger Markdown Parsing** - Tolerate formatting variants; precise parse errors
- [ ] **Round-trip Edits** - Modify source markdown while preserving formatting
- [ ] **Schema Validation** - Optional strict mode for required fields
- [ ] **Extensible Frontmatter** - YAML frontmatter as alternative to tables
- [ ] **Inline Task References** - Parse `[ ]` checkboxes as subtasks
- [ ] **Image Embedding** - Handle images in descriptions
- [ ] **Better Table Parsing** - Improved table support in descriptions
- [ ] **Code Block Preservation** - Preserve syntax highlighting

---

## ⚡ Quick Wins (< 2 hours each)

- [ ] AI prompts: use dynamic examples (~1 hr)
- [ ] Parameterized tests for ID prefixes (~2 hrs)
- [ ] Documentation examples: use neutral prefixes (~2 hrs)
- [ ] TrackerType.ASANA full integration check (~30 min)
- [ ] OpenTelemetry/Prometheus setup docs (~1 hr)
- [ ] Add `--version` flag with version info
- [ ] Better error messages
- [ ] Configuration validation on startup
- [ ] Auto-completion improvements
- [ ] Progress bars for long operations
- [ ] Export formats (CSV, Excel, JSON)
- [ ] Import from other tools (Jira CSV, GitHub CSV)
- [ ] Statistics command
- [ ] Health check improvements
- [ ] JSON schema for `.spectra.yaml` (IDE autocompletion)
- [ ] Changelog generation from tracker history

---

## 🏠 Housekeeping

- [ ] **Audit & Update Backlog** - Mark completed items in `BACKLOG.md`
- [ ] **Update `FLEXIBILITY-PLAN.md`** - Mark "Remaining Work" as complete if done
- [ ] **Verify Asana Implementation** - Check if `batch.py` and `async_adapter.py` work

---

## 📊 Summary

| Category | Item Count | Completed |
|----------|------------|-----------|
| High Priority | 3 | 3 |
| Medium Priority (Quality) | 20+ | 20+ |
| New Tracker Integrations | 10 | 7 (GitLab, Monday.com, Trello, Shortcut, ClickUp, Bitbucket, YouTrack) |
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

**Total: 190+ improvement opportunities** | **Completed: 30+ (including GitLab, Monday.com, Trello, Shortcut, ClickUp, Bitbucket, and YouTrack adapters)**

---

## 🎯 Recommended Priority Order

### Phase 1: Quick Wins (1-2 weeks)
1. Custom ID separators
2. Universal `#123` support
3. Better error messages
4. Configuration validation
5. Documentation updates

### Phase 2: High Impact (1-2 months)
1. Integration tests for all trackers ✅
2. Asana adapter parity verification ✅
3. GitLab Issues Adapter ✅ **COMPLETED**
4. Trello Adapter ✅ **COMPLETED**
5. Incremental sync optimization
6. Interactive TUI dashboard

### Phase 3: Major Features (3-6 months)
1. Additional tracker adapters (Monday.com ✅, Shortcut ✅, ClickUp ✅, Bitbucket ✅, YouTrack ✅)
2. AI/ML features (story generation, quality scoring)
3. Bidirectional sync with conflict resolution
4. JetBrains IDE plugin
5. Enterprise features (SSO, RBAC)

