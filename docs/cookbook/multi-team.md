# Multi-Team Workflows

Coordinate work across multiple teams using spectryn with shared or separate epics.

## Scenarios

### Scenario 1: Shared Epic, Multiple Teams

Teams work on different aspects of the same feature:

```
PROJ-100 (Epic: User Management)
├── Frontend Team → US-001, US-002
├── Backend Team  → US-003, US-004
└── DevOps Team   → US-005
```

### Scenario 2: Separate Epics, Coordinated Release

Each team has their own epic but coordinates for a release:

```
Release 2.0
├── FRONT-100 (Frontend Epic)
├── BACK-200 (Backend Epic)
└── INFRA-50 (Infrastructure Epic)
```

## Shared Epic Structure

Create a single markdown file with team sections:

```markdown
# 🚀 User Management System

> **Epic: Complete user management overhaul**

---

## Frontend Team

---

### 🎨 US-001: User Profile Page

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 🔄 In Progress |
| **Team** | Frontend |
| **Assignee** | @alice |

#### Description

**As a** user
**I want** to view and edit my profile
**So that** I can manage my account information

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Profile view component | Display user info | 2 | ✅ Done |
| 2 | Edit mode | Inline editing | 2 | 🔄 In Progress |
| 3 | Avatar upload | Image upload UI | 1 | 📋 Planned |

---

### 🎨 US-002: User Settings Page

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟢 Medium |
| **Status** | 📋 Planned |
| **Team** | Frontend |

#### Description

**As a** user
**I want** to manage my preferences
**So that** I can customize my experience

---

## Backend Team

---

### 🔧 US-003: User API Endpoints

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
| **Team** | Backend |
| **Assignee** | @bob |

#### Description

**As a** frontend developer
**I want** RESTful user management APIs
**So that** I can build the user interface

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | GET /users/:id | Fetch user profile | 2 | ✅ Done |
| 2 | PATCH /users/:id | Update user profile | 2 | ✅ Done |
| 3 | DELETE /users/:id | Soft delete user | 2 | 🔄 In Progress |
| 4 | Avatar upload API | Handle file uploads | 2 | 📋 Planned |

---

### 🔧 US-004: User Data Migration

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Team** | Backend |

#### Description

**As a** system administrator
**I want** existing user data migrated
**So that** users don't lose their information

---

## DevOps Team

---

### ⚡ US-005: User Service Deployment

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Team** | DevOps |
| **Assignee** | @charlie |

#### Description

**As a** backend developer
**I want** the user service deployed to staging
**So that** I can test API endpoints

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Kubernetes manifests | Create k8s configs | 1 | 📋 Planned |
| 2 | CI/CD pipeline | GitHub Actions workflow | 1 | 📋 Planned |
| 3 | Monitoring | Prometheus + Grafana | 1 | 📋 Planned |

---
```

## Separate Epic Files

For larger teams, maintain separate files:

```
docs/
├── epics/
│   ├── frontend-v2.md      → FRONT-100
│   ├── backend-v2.md       → BACK-200
│   └── infrastructure.md   → INFRA-50
└── releases/
    └── release-2.0.md      → Summary
```

### Team-Specific Sync

```bash
# Frontend team syncs their epic
spectryn -m docs/epics/frontend-v2.md -e FRONT-100 -x

# Backend team syncs their epic
spectryn -m docs/epics/backend-v2.md -e BACK-200 -x

# DevOps syncs infrastructure
spectryn -m docs/epics/infrastructure.md -e INFRA-50 -x
```

### Sync All Epics

```bash
#!/bin/bash
# sync-all-teams.sh

declare -A EPICS=(
  ["docs/epics/frontend-v2.md"]="FRONT-100"
  ["docs/epics/backend-v2.md"]="BACK-200"
  ["docs/epics/infrastructure.md"]="INFRA-50"
)

for file in "${!EPICS[@]}"; do
  epic="${EPICS[$file]}"
  echo "Syncing $file → $epic"
  spectryn -m "$file" -e "$epic" -x --no-confirm
done
```

## Cross-Team Dependencies

Document dependencies in the markdown:

```markdown
### 🔧 US-003: User API Endpoints

...

#### Dependencies

| Dependency | Team | Status |
|------------|------|--------|
| US-005: Deployment | DevOps | 📋 Blocked |
| Database schema | DBA | ✅ Ready |

#### Blocked By
- INFRA-51: PostgreSQL cluster setup

#### Blocks
- US-001: Profile page (needs API)
- US-002: Settings page (needs API)
```

## CI/CD for Multi-Team

```yaml
# .github/workflows/sync-all.yml
name: Sync All Teams

on:
  push:
    paths:
      - 'docs/epics/**/*.md'
    branches:
      - main

jobs:
  sync:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - file: docs/epics/frontend-v2.md
            epic: FRONT-100
          - file: docs/epics/backend-v2.md
            epic: BACK-200
          - file: docs/epics/infrastructure.md
            epic: INFRA-50
    
    steps:
      - uses: actions/checkout@v4
      - run: pip install spectryn
      - name: Sync ${{ matrix.epic }}
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn -m ${{ matrix.file }} -e ${{ matrix.epic }} -x --no-confirm
```

## Team-Specific Config

Each team can have their own config:

```yaml
# .spectryn.frontend.yaml
jira:
  url: https://company.atlassian.net
  project: FRONT

sync:
  verbose: true
```

```bash
# Use team-specific config
spectryn --config .spectryn.frontend.yaml -m frontend.md -e FRONT-100 -x
```

## Tips

::: tip Communication
- Use a shared channel for sync notifications
- Tag teams in PR reviews for cross-team changes
- Document dependencies explicitly
:::

::: tip Organization
- Consistent naming: `[team]-[feature].md`
- Separate directories per team or per release
- README in each directory explaining structure
:::

