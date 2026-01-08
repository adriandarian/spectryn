# Sprint Planning

Use spectryn to manage sprint backlogs with markdown as your source of truth.

## The Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Sprint         │     │                 │     │  Jira Sprint    │
│  Planning Doc   │ ──▶ │    spectryn      │ ──▶ │  Board          │
│  (Markdown)     │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                                               │
        │◀──────────── Team Discussion ─────────────────│
```

## Sprint Document Structure

Create a markdown file for each sprint:

```markdown
# 🏃 Sprint 2025-W03

> **Sprint: January 13-24, 2025**

---

## Sprint Summary

| Field | Value |
|-------|-------|
| **Sprint Name** | 2025-W03 |
| **Status** | 🔄 In Progress |
| **Goal** | Complete user authentication MVP |
| **Start Date** | January 13, 2025 |
| **End Date** | January 24, 2025 |
| **Capacity** | 40 story points |

### Sprint Goal

Deliver a working authentication system with login, registration, 
and password reset functionality.

### Team

- **Backend**: Alice, Bob
- **Frontend**: Charlie
- **QA**: Diana

---

## Sprint Backlog

---

### 🔒 US-042: User Login

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
| **Assignee** | Alice |

#### Description

**As a** registered user
**I want** to log in with my email and password
**So that** I can access my account

#### Acceptance Criteria

- [ ] Login form with email/password fields
- [ ] Form validation with error messages
- [ ] Redirect to dashboard on success
- [ ] "Remember me" checkbox
- [ ] Rate limiting (5 attempts per minute)

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Login API endpoint | POST /api/auth/login | 2 | ✅ Done |
| 2 | Login form UI | React form component | 2 | 🔄 In Progress |
| 3 | Rate limiting | Redis-based limiter | 1 | 📋 Planned |

---

### 🔒 US-043: User Registration

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Assignee** | Bob |

#### Description

**As a** new user
**I want** to create an account
**So that** I can use the application

#### Acceptance Criteria

- [ ] Registration form with required fields
- [ ] Email verification link sent
- [ ] Password strength requirements shown
- [ ] Terms of service checkbox

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Registration API | POST /api/auth/register | 2 | 📋 Planned |
| 2 | Email service | Send verification emails | 1 | 📋 Planned |
| 3 | Registration form | React form with validation | 2 | 📋 Planned |

---

### 🔒 US-044: Password Reset

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Assignee** | Alice |

#### Description

**As a** user who forgot their password
**I want** to reset it via email
**So that** I can regain access to my account

#### Acceptance Criteria

- [ ] "Forgot password" link on login page
- [ ] Email with reset link sent
- [ ] Reset link expires after 1 hour
- [ ] New password confirmation

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Reset request API | POST /api/auth/forgot-password | 1 | 📋 Planned |
| 2 | Reset password API | POST /api/auth/reset-password | 1 | 📋 Planned |
| 3 | Reset forms UI | Request and confirm forms | 1 | 📋 Planned |

---

## Sprint Notes

### Risks
- Email deliverability in staging environment
- OAuth integration may be needed for SSO customers

### Dependencies
- Infrastructure team: Redis cluster for rate limiting

### Carry-over from Last Sprint
- None
```

## Sync Commands

```bash
# Preview sprint changes
spectryn -m sprints/2025-W03.md -e PROJ-100

# Sync at sprint start
spectryn -m sprints/2025-W03.md -e PROJ-100 -x

# Update during daily standup
spectryn -m sprints/2025-W03.md -e PROJ-100 -x --phase statuses

# End of sprint - sync final status
spectryn -m sprints/2025-W03.md -e PROJ-100 -x
```

## Daily Standup Workflow

Update the markdown file during standup, then sync:

```bash
#!/bin/bash
# standup-sync.sh

# 1. Pull latest changes
git pull

# 2. Edit sprint doc (done manually during standup)
# Update status emojis: 📋 → 🔄 → ✅

# 3. Sync to Jira
spectryn -m sprints/$(date +%Y-W%V).md -e $SPRINT_EPIC -x --no-confirm

# 4. Commit changes
git add sprints/
git commit -m "chore: standup $(date +%Y-%m-%d)"
git push
```

## Sprint Retrospective

At sprint end, archive the completed sprint:

```bash
# Final sync
spectryn -m sprints/2025-W03.md -e PROJ-100 -x

# Archive
mv sprints/2025-W03.md sprints/archive/

# Create next sprint from template
cp sprints/template.md sprints/2025-W05.md
```

## Tips

::: tip Keep It Simple
- One markdown file per sprint
- Update status during standups
- Sync at least daily
:::

::: tip Version Control
- Commit sprint docs to Git
- Review changes in PRs
- Track history of decisions
:::

::: tip Automation
- Set up CI/CD to auto-sync on merge
- Use webhooks for Slack notifications
- Generate burndown from export data
:::

