# Recipes Guide

Common setups and field mapping examples for spectra.

## Quick Recipes

Jump to a recipe:
- [Basic Jira Setup](#basic-jira-setup)
- [GitHub Issues with Projects](#github-issues-with-projects)
- [Custom Field Mapping](#custom-field-mapping)
- [Multi-Team Configuration](#multi-team-configuration)
- [Sprint Planning Setup](#sprint-planning-setup)
- [Bug Tracking Template](#bug-tracking-template)
- [Technical Debt Tracking](#technical-debt-tracking)
- [Release Planning](#release-planning)

---

## Basic Jira Setup

The simplest configuration to get started:

### Configuration

```yaml
# spectra.yaml
tracker: jira
version: 1

jira:
  url: ${JIRA_URL}
  project: PROJ

defaults:
  story_type: Story
  subtask_type: Sub-task
```

### Environment Variables

```bash
# .env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your-api-token
```

### Story Template

```markdown
# 📋 My First Epic

> **Epic: Basic feature epic**

---

## Stories

---

### 📝 US-001: First Story

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 Medium |
| **Status** | 📋 To Do |

#### Description

**As a** user
**I want** this feature
**So that** I can do something

#### Acceptance Criteria

- [ ] First criterion
- [ ] Second criterion
```

### Sync Command

```bash
spectra sync --execute --markdown epic.md --epic PROJ-123
```

---

## GitHub Issues with Projects

Sync to GitHub Issues and GitHub Projects:

### Configuration

```yaml
# spectra.yaml
tracker: github
version: 1

github:
  owner: your-org
  repo: your-repo
  project: 1  # Project number

mappings:
  priority:
    "🔴 Critical": "priority: critical"
    "🟠 High": "priority: high"
    "🟡 Medium": "priority: medium"
    "🟢 Low": "priority: low"

  status:
    "📋 To Do": "Status: Todo"
    "🔄 In Progress": "Status: In Progress"
    "✅ Done": "Status: Done"
```

### Story Template

```markdown
### 🐛 BUG-001: Fix login timeout

| Field | Value |
|-------|-------|
| **Priority** | 🔴 Critical |
| **Status** | 📋 To Do |
| **Labels** | bug, authentication |
| **Milestone** | v2.0.0 |

#### Description

Users are being logged out after 5 minutes of inactivity.
Expected: 30 minute timeout.

#### Acceptance Criteria

- [ ] Timeout extended to 30 minutes
- [ ] "Remember me" extends to 7 days
- [ ] Session refresh on activity
```

---

## Custom Field Mapping

Map custom fields between markdown and your tracker:

### Jira Custom Fields

```yaml
# spectra.yaml
tracker: jira

jira:
  url: ${JIRA_URL}
  project: PROJ

  custom_fields:
    # Map markdown field to Jira custom field ID
    "Team": customfield_10001
    "Risk Level": customfield_10002
    "Business Value": customfield_10003
    "Technical Complexity": customfield_10004
    "Sprint": customfield_10005
    "Release": customfield_10006

  field_mappings:
    # Value transformations
    "Team":
      "Backend": "team-backend"
      "Frontend": "team-frontend"
      "Mobile": "team-mobile"

    "Risk Level":
      "🔴 High": "high"
      "🟡 Medium": "medium"
      "🟢 Low": "low"
```

### Story with Custom Fields

```markdown
### 📦 US-001: New Feature

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟠 High |
| **Status** | 📋 To Do |
| **Team** | Backend |
| **Risk Level** | 🟡 Medium |
| **Business Value** | High |
| **Technical Complexity** | Medium |
| **Sprint** | Sprint 23 |
| **Release** | v2.1.0 |

#### Description

Feature description here...
```

### Linear Custom Fields

```yaml
# spectra.yaml
tracker: linear

linear:
  team_key: TEAM

  custom_fields:
    "Customer": customer_id
    "Revenue Impact": revenue_impact

  labels:
    auto_create: true
    prefix: "team:"
```

---

## Multi-Team Configuration

For organizations with multiple teams/projects:

### Configuration

```yaml
# spectra.yaml
version: 1

# Default tracker
tracker: jira

# Team-specific configurations
teams:
  backend:
    tracker: jira
    jira:
      url: ${JIRA_URL}
      project: BACK
    defaults:
      labels: ["team:backend"]

  frontend:
    tracker: jira
    jira:
      url: ${JIRA_URL}
      project: FRONT
    defaults:
      labels: ["team:frontend"]

  mobile:
    tracker: linear
    linear:
      team_key: MOBILE
    defaults:
      labels: ["team:mobile"]

# Routing rules
routing:
  # Stories with these labels go to specific teams
  rules:
    - match: { labels: ["backend", "api"] }
      team: backend
    - match: { labels: ["frontend", "ui"] }
      team: frontend
    - match: { labels: ["mobile", "ios", "android"] }
      team: mobile
```

### Directory Structure

```
epics/
├── backend/
│   ├── api-v2.md
│   └── performance.md
├── frontend/
│   ├── redesign.md
│   └── accessibility.md
├── mobile/
│   └── offline-mode.md
└── shared/
    └── unified-auth.md  # Cross-team epic
```

### Sync Commands

```bash
# Sync specific team
spectra sync --team backend --markdown epics/backend/

# Sync all teams
spectra sync --all-teams --markdown epics/

# Sync shared epics to multiple trackers
spectra sync --teams backend,frontend --markdown epics/shared/
```

---

## Sprint Planning Setup

Configuration for sprint-based workflows:

### Configuration

```yaml
# spectra.yaml
tracker: jira
version: 1

jira:
  url: ${JIRA_URL}
  project: PROJ
  board_id: 1  # For sprint management

sprints:
  auto_detect: true
  field: Sprint

  # Sprint naming pattern
  pattern: "Sprint {number}"

  # Duration
  duration_weeks: 2
  start_day: monday

validation:
  require_sprint: true  # Stories must have sprint assigned
  max_points_per_sprint: 40
```

### Sprint Planning Template

```markdown
# 🏃 Sprint 23 Planning

> **Sprint: January 6-17, 2026**
> **Capacity: 40 points**

---

## Sprint Goals

1. Complete user authentication epic
2. Start payment integration
3. Address critical bugs

---

## Committed Stories

---

### 🔐 US-101: OAuth Integration

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 To Do |
| **Sprint** | Sprint 23 |
| **Assignee** | @john.doe |

#### Description

Implement Google and GitHub OAuth login.

#### Acceptance Criteria

- [ ] Google OAuth working
- [ ] GitHub OAuth working
- [ ] Account linking for existing users

---

### 💳 US-102: Payment Form

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟠 High |
| **Status** | 📋 To Do |
| **Sprint** | Sprint 23 |
| **Assignee** | @jane.smith |

---

## Sprint Summary

| Metric | Value |
|--------|-------|
| **Total Stories** | 8 |
| **Total Points** | 37 |
| **Capacity Used** | 92% |
| **Carry Over** | 0 |
```

### Sprint Commands

```bash
# Validate sprint capacity
spectra validate --sprint "Sprint 23" --markdown sprint-23.md

# Show sprint summary
spectra stats --sprint "Sprint 23"

# Sync sprint stories only
spectra sync --sprint "Sprint 23" --execute --markdown sprint-23.md
```

---

## Bug Tracking Template

Standardized bug report format:

### Configuration

```yaml
# spectra.yaml
tracker: jira

jira:
  url: ${JIRA_URL}
  project: PROJ

  issue_types:
    bug: Bug
    story: Story
    task: Task

# Bug-specific validation
validation:
  bugs:
    require_severity: true
    require_steps_to_reproduce: true
    require_environment: true
```

### Bug Report Template

```markdown
### 🐛 BUG-001: Login fails on Safari

| Field | Value |
|-------|-------|
| **Type** | Bug |
| **Severity** | 🔴 Critical |
| **Priority** | 🔴 Critical |
| **Status** | 📋 To Do |
| **Reported By** | @customer-support |
| **Affects Version** | v2.0.1 |
| **Environment** | Production |
| **Browser** | Safari 17.0 |
| **OS** | macOS Sonoma |

#### Description

Users cannot log in when using Safari browser. The login button is unresponsive.

#### Steps to Reproduce

1. Open https://app.example.com in Safari 17.0
2. Enter valid credentials
3. Click "Log In" button
4. **Expected:** Redirect to dashboard
5. **Actual:** Nothing happens, button appears frozen

#### Environment Details

```
Browser: Safari 17.0
OS: macOS Sonoma 14.0
Device: MacBook Pro M3
Network: Corporate WiFi
```

#### Error Logs

```
TypeError: Cannot read property 'submit' of undefined
  at LoginForm.handleSubmit (login.js:45)
```

#### Screenshots

![Safari login bug](./attachments/safari-bug.png)

#### Acceptance Criteria

- [ ] Login works in Safari 17.0+
- [ ] No JavaScript errors in console
- [ ] Works with both password and SSO login
- [ ] Regression test added
```

---

## Technical Debt Tracking

Track and prioritize technical debt:

### Configuration

```yaml
# spectra.yaml
tracker: jira

defaults:
  tech_debt_label: "tech-debt"

validation:
  tech_debt:
    require_justification: true
    require_impact_assessment: true
```

### Tech Debt Template

```markdown
# 🔧 Technical Debt Backlog

> **Epic: Technical debt reduction Q1 2026**

---

## High Priority Debt

---

### ⚠️ TD-001: Upgrade React to v19

| Field | Value |
|-------|-------|
| **Story Points** | 13 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 To Do |
| **Labels** | tech-debt, dependencies |
| **Debt Type** | Dependency |
| **Risk** | Security vulnerabilities in React 17 |

#### Justification

React 17 reaches end of support in March 2026. Staying on it
exposes us to unpatched security vulnerabilities.

#### Impact Assessment

| Area | Impact |
|------|--------|
| Security | High - CVEs won't be patched |
| Performance | Medium - Missing optimizations |
| Developer Experience | High - Can't use new features |

#### Approach

1. Audit breaking changes
2. Update dependencies
3. Fix deprecation warnings
4. Run full test suite
5. Gradual rollout with feature flags

#### Acceptance Criteria

- [ ] All tests pass with React 19
- [ ] No console warnings
- [ ] Performance benchmarks unchanged
- [ ] Staged rollout complete

---

### 🔧 TD-002: Refactor Authentication Module

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🟠 High |
| **Status** | 📋 To Do |
| **Labels** | tech-debt, architecture |
| **Debt Type** | Architecture |
| **Code Smell** | God class, 2000+ lines |

#### Justification

The AuthService class has grown to 2000+ lines with 45 methods.
This makes it difficult to test, modify, and reason about.

#### Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Lines of code | 2,000 | <500/class |
| Cyclomatic complexity | 45 | <10 |
| Test coverage | 45% | >80% |
| Methods | 45 | <15/class |
```

---

## Release Planning

Plan and track releases:

### Configuration

```yaml
# spectra.yaml
tracker: jira

jira:
  url: ${JIRA_URL}
  project: PROJ

releases:
  version_field: Fix Version
  auto_create: true
```

### Release Template

```markdown
# 🚀 Release v2.1.0

> **Target Date: January 31, 2026**
> **Code Freeze: January 24, 2026**

---

## Release Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 5 |
| **Bug Fixes** | 12 |
| **Tech Debt** | 3 |
| **Story Points** | 89 |

---

## Features

---

### ✨ FEAT-001: Dark Mode

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Status** | ✅ Done |
| **Release** | v2.1.0 |

---

### ✨ FEAT-002: Export to PDF

| Field | Value |
|-------|-------|
| **Story Points** | 13 |
| **Status** | 🔄 In Progress |
| **Release** | v2.1.0 |

---

## Bug Fixes

| ID | Title | Status | Points |
|----|-------|--------|--------|
| BUG-101 | Fix Safari login | ✅ Done | 3 |
| BUG-102 | Memory leak in dashboard | ✅ Done | 5 |
| BUG-103 | Timezone handling | 🔄 In Progress | 3 |

---

## Release Checklist

- [ ] All features complete
- [ ] All critical bugs fixed
- [ ] QA sign-off
- [ ] Documentation updated
- [ ] Release notes written
- [ ] Stakeholder approval
```

### Release Commands

```bash
# Show release status
spectra stats --release v2.1.0

# Validate release readiness
spectra validate --release v2.1.0 --check-blockers

# Generate release notes
spectra release-notes --release v2.1.0 --output RELEASE.md
```

---

## Field Mapping Reference

Common field mappings across trackers:

### Status Mappings

```yaml
mappings:
  status:
    # Emoji format
    "📋 To Do": To Do
    "🔄 In Progress": In Progress
    "👀 In Review": In Review
    "✅ Done": Done
    "🔴 Blocked": Blocked

    # Plain text format
    "To Do": To Do
    "In Progress": In Progress
    "Done": Done
```

### Priority Mappings

```yaml
mappings:
  priority:
    # Jira
    "🔴 Critical": Highest
    "🟠 High": High
    "🟡 Medium": Medium
    "🟢 Low": Low
    "⚪ Lowest": Lowest

    # GitHub (labels)
    "🔴 Critical": "priority: critical"
    "🟠 High": "priority: high"

    # Linear
    "🔴 Critical": 1
    "🟠 High": 2
    "🟡 Medium": 3
    "🟢 Low": 4
```

### Story Point Mappings

```yaml
mappings:
  story_points:
    # Fibonacci
    allowed: [1, 2, 3, 5, 8, 13, 21]

    # T-shirt sizes
    "XS": 1
    "S": 2
    "M": 3
    "L": 5
    "XL": 8
    "XXL": 13
```

---

## Next Steps

- [Best Practices Guide](/guide/best-practices) - Recommended workflows
- [Troubleshooting](/guide/troubleshooting) - Common issues
- [CLI Reference](/reference/cli) - All commands
