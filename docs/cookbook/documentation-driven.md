# Documentation-Driven Development

Use markdown documentation as your single source of truth, with Jira as the execution layer.

## The Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENTATION (Source of Truth)              │
│                                                                 │
│  📝 Markdown files in Git                                       │
│  ├── Requirements                                               │
│  ├── User stories                                               │
│  ├── Technical specs                                            │
│  └── Acceptance criteria                                        │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼  spectryn sync
┌─────────────────────────────────────────────────────────────────┐
│                    JIRA (Execution Layer)                       │
│                                                                 │
│  ✅ Task tracking                                               │
│  📊 Sprint boards                                               │
│  📈 Reporting                                                   │
│  🔔 Notifications                                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Benefits

| Benefit | Description |
|---------|-------------|
| **Version Control** | Full history of all requirements changes |
| **Code Review** | PRs for requirement changes, not Jira clicking |
| **Searchable** | grep, ripgrep, IDE search across all docs |
| **Portable** | Not locked into any tool |
| **AI-Friendly** | LLMs can read and generate markdown |
| **Offline** | Edit anywhere, sync when ready |

## Project Structure

```
project/
├── docs/
│   ├── epics/
│   │   ├── auth-system.md          → AUTH-100
│   │   ├── payment-processing.md   → PAY-200
│   │   └── user-dashboard.md       → DASH-300
│   ├── specs/
│   │   ├── api-design.md
│   │   └── data-models.md
│   └── decisions/
│       ├── ADR-001-database.md
│       └── ADR-002-framework.md
├── src/
│   └── ...
└── .github/
    └── workflows/
        └── sync-jira.yml
```

## Epic Document Template

Each epic is a comprehensive document:

```markdown
# 🔐 Authentication System

> **Epic: Modern authentication with OAuth and MFA**

---

## Overview

### Problem Statement

Users currently authenticate with username/password only. We need:
- Social login for easier onboarding
- MFA for security-conscious users
- SSO for enterprise customers

### Goals

1. Reduce sign-up friction by 50%
2. Achieve SOC 2 compliance for enterprise
3. Support 10,000 concurrent sessions

### Non-Goals

- Passwordless authentication (future)
- Biometric login (future)

---

## Technical Design

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   Auth      │────▶│   User      │
│   (React)   │     │   Service   │     │   Store     │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                    ┌─────┴─────┐
                    ▼           ▼
              ┌──────────┐ ┌──────────┐
              │  OAuth   │ │   MFA    │
              │ Providers│ │  Service │
              └──────────┘ └──────────┘
```

### Data Model

| Entity | Fields |
|--------|--------|
| User | id, email, password_hash, mfa_enabled |
| OAuthConnection | id, user_id, provider, provider_id |
| MFADevice | id, user_id, type, secret |
| Session | id, user_id, token, expires_at |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/login | Email/password login |
| POST | /auth/oauth/:provider | OAuth callback |
| POST | /auth/mfa/verify | Verify MFA code |
| POST | /auth/logout | End session |

---

## User Stories

---

### 🔒 US-001: Email/Password Login

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | ✅ Done |

#### Description

**As a** registered user
**I want** to log in with email and password
**So that** I can access my account

#### Acceptance Criteria

- [x] Login form with email/password fields
- [x] Form validation with clear error messages
- [x] Rate limiting (5 attempts per minute)
- [x] Session created on success
- [x] Redirect to intended page or dashboard

#### Technical Notes

- Use bcrypt for password hashing (cost factor 12)
- Sessions stored in Redis with 24h TTL
- JWT for stateless authentication option

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login API | POST /auth/login endpoint | 2 | ✅ Done |
| 2 | Login UI | React form component | 2 | ✅ Done |
| 3 | Rate limiter | Redis-based limiter | 1 | ✅ Done |

---

### 🔒 US-002: Google OAuth Login

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 🔄 In Progress |

#### Description

**As a** user
**I want** to sign in with Google
**So that** I don't need another password

#### Technical Notes

- Use passport-google-oauth20
- Request scopes: email, profile
- Link to existing account if email matches

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Google OAuth config | Set up Google Cloud Console | 1 | ✅ Done |
| 2 | OAuth callback | Handle Google callback | 1 | 🔄 In Progress |
| 3 | Account linking | Link OAuth to existing users | 1 | 📋 Planned |

---

[Additional stories...]

---

## Decisions

### ADR-001: JWT vs Session Tokens

**Status**: Accepted  
**Date**: 2025-01-10

**Context**: Need to choose authentication token strategy.

**Decision**: Use JWTs for API authentication, Redis sessions for web.

**Consequences**: 
- (+) Stateless API authentication
- (+) Easy horizontal scaling
- (-) Token revocation requires blocklist

---

## References

- [OAuth 2.0 Spec](https://oauth.net/2/)
- [OWASP Auth Guidelines](https://owasp.org/www-project-web-security-testing-guide/)
- [Internal: Security Checklist](/docs/security-checklist.md)

---
```

## Workflow

### 1. Write Requirements First

```bash
# Create new epic document
touch docs/epics/new-feature.md

# Write comprehensive documentation
# - Problem statement
# - Technical design
# - User stories
# - Acceptance criteria
```

### 2. Review in Pull Request

```bash
git checkout -b feature/new-feature-docs
git add docs/epics/new-feature.md
git commit -m "docs: add new feature epic documentation"
git push -u origin feature/new-feature-docs
# Create PR for team review
```

### 3. Sync to Jira on Merge

```yaml
# .github/workflows/sync-jira.yml
on:
  push:
    paths: ['docs/epics/**/*.md']
    branches: [main]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install spectryn
      - name: Sync all epics
        run: |
          for file in docs/epics/*.md; do
            epic=$(head -1 "$file" | grep -oP '→ \K\w+-\d+' || echo "")
            if [ -n "$epic" ]; then
              spectryn -m "$file" -e "$epic" -x --no-confirm
            fi
          done
```

### 4. Update Docs as Work Progresses

```bash
# Developer updates status in markdown
# Change: 📋 Planned → 🔄 In Progress → ✅ Done

git add docs/epics/auth-system.md
git commit -m "docs: update auth epic progress"
git push

# CI syncs to Jira automatically
```

## Integration with Development

### Link Stories to Code

In your epic document:

```markdown
#### Related Commits

| Commit | Message |
|--------|---------|
| `abc1234` | feat(auth): implement login API |
| `def5678` | feat(auth): add login form UI |
```

### Link PRs in Commit Messages

```bash
git commit -m "feat(auth): implement login API

Implements US-001 from docs/epics/auth-system.md
Jira: AUTH-101"
```

### Generate from Documentation

Use AI to generate implementation from docs:

```
Based on the technical design in docs/epics/auth-system.md,
implement the login API endpoint with:
- Input validation
- Rate limiting
- Session creation
```

## Tips

::: tip Documentation First
- Write requirements before code
- Get alignment through PR reviews
- Technical design prevents rework
:::

::: tip Keep It Current
- Update docs as you develop
- Treat docs as code (review, test, version)
- Archive completed epics
:::

::: tip Make It Searchable
- Use consistent naming
- Add keywords and tags
- Link related documents
:::

