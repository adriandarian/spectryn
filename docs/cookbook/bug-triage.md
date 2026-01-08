# Bug Triage

Efficiently manage bug backlogs using spectryn for structured bug tracking.

## Bug Tracking Epic

```markdown
# 🐛 Bug Backlog: Q1 2025

> **Epic: Bug fixes and stability improvements**

---

## Summary

| Field | Value |
|-------|-------|
| **Status** | 🔄 In Progress |
| **Priority** | 🟡 High |
| **Period** | January - March 2025 |
| **Target** | Zero critical bugs |

### Bug Metrics

| Severity | Open | In Progress | Resolved |
|----------|------|-------------|----------|
| 🔴 Critical | 0 | 1 | 3 |
| 🟡 High | 2 | 2 | 5 |
| 🟢 Medium | 8 | 1 | 12 |
| ⚪ Low | 15 | 0 | 8 |

---

## Critical Bugs

---

### 🐛 BUG-001: Payment Processing Failure

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 🔄 In Progress |
| **Severity** | Critical |
| **Reported By** | Customer Support |
| **Assignee** | @alice |

#### Description

**As a** customer completing checkout
**I want** payment to process successfully
**So that** my order is confirmed

**Bug Details:**

- **Observed**: Payments fail intermittently with "Gateway Timeout"
- **Expected**: All valid payments should succeed
- **Frequency**: ~5% of transactions
- **Impact**: Revenue loss, customer complaints

#### Steps to Reproduce

1. Add items to cart
2. Proceed to checkout
3. Enter valid payment details
4. Submit payment during peak hours

#### Root Cause Analysis

Payment gateway timeout set too low (5s). Under load, 
gateway response time exceeds timeout.

#### Acceptance Criteria

- [ ] Timeout increased to 30s
- [ ] Retry logic with exponential backoff
- [ ] Better error messaging to users
- [ ] Monitoring alert for payment failures

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Increase timeout | Update gateway config | 1 | ✅ Done |
| 2 | Add retry logic | 3 retries with backoff | 2 | 🔄 In Progress |
| 3 | User messaging | Show "retry in progress" | 1 | 📋 Planned |
| 4 | Add monitoring | Datadog alert for failures | 1 | 📋 Planned |

---

## High Priority Bugs

---

### 🐛 BUG-002: Search Results Empty for Special Characters

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Severity** | High |
| **Reported By** | QA Team |
| **Assignee** | @bob |

#### Description

**As a** user searching for products
**I want** searches with special characters to work
**So that** I can find products like "iPhone 15 Pro (256GB)"

**Bug Details:**

- **Observed**: Search returns empty for queries with `()`, `&`, `+`
- **Expected**: Special characters should be handled or escaped
- **Frequency**: 100% reproducible
- **Impact**: Users can't find products with special chars in name

#### Steps to Reproduce

1. Go to search bar
2. Enter "iPhone (256GB)"
3. Submit search
4. Observe empty results

#### Acceptance Criteria

- [ ] Special characters properly escaped
- [ ] Parentheses, ampersand, plus sign handled
- [ ] Search suggestions work with special chars

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Escape special chars | Sanitize search input | 1 | 📋 Planned |
| 2 | Update Elasticsearch | Configure analyzer | 1 | 📋 Planned |
| 3 | Add test cases | Unit tests for edge cases | 1 | 📋 Planned |

---

### 🐛 BUG-003: Session Expires During Checkout

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 🔄 In Progress |
| **Severity** | High |
| **Reported By** | Customer Feedback |
| **Assignee** | @charlie |

#### Description

**As a** customer in the middle of checkout
**I want** my session to remain active
**So that** I don't lose my cart and progress

**Bug Details:**

- **Observed**: Session expires after 15 min on checkout page
- **Expected**: Session should extend while user is active
- **Frequency**: Affects users who take time on checkout
- **Impact**: Cart abandonment, frustrated users

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Extend timeout | 30 min on checkout pages | 1 | ✅ Done |
| 2 | Activity detection | Extend on mouse/keyboard | 1 | 🔄 In Progress |
| 3 | Warning modal | Show "session expiring" at 25 min | 1 | 📋 Planned |

---

## Medium Priority Bugs

---

### 🐛 BUG-004: Profile Image Not Displaying

| Field | Value |
|-------|-------|
| **Story Points** | 2 |
| **Priority** | 🟢 Medium |
| **Status** | 📋 Planned |
| **Severity** | Medium |
| **Reported By** | User Report |

#### Description

**As a** user with a profile image
**I want** my image to display correctly
**So that** others can identify me

**Bug Details:**

- **Observed**: Some profile images show broken image icon
- **Expected**: All uploaded images should display
- **Frequency**: ~10% of profile images affected
- **Impact**: Poor user experience

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Debug CDN URLs | Check for incorrect paths | 1 | 📋 Planned |
| 2 | Add fallback | Show initials if image fails | 1 | 📋 Planned |

---

### 🐛 BUG-005: Email Notifications Delayed

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟢 Medium |
| **Status** | 📋 Planned |
| **Severity** | Medium |
| **Reported By** | Operations |

#### Description

**As a** user expecting email notifications
**I want** emails delivered promptly
**So that** I don't miss important updates

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Check queue backlog | Investigate SQS delays | 1 | 📋 Planned |
| 2 | Scale workers | Add more email workers | 1 | 📋 Planned |
| 3 | Add metrics | Track email delivery time | 1 | 📋 Planned |

---
```

## Bug Triage Workflow

### 1. Weekly Triage Meeting

```bash
# Before meeting: Get current state
spectryn -m bugs/q1-2025.md -e BUG-100 --output json | jq '
  .stories | group_by(.severity) | 
  map({severity: .[0].severity, count: length, open: map(select(.status != "done")) | length})
'
```

### 2. Update During Meeting

Update the markdown file with:
- New bug reports
- Priority changes
- Assignee updates
- Status changes

### 3. Sync After Meeting

```bash
spectryn -m bugs/q1-2025.md -e BUG-100 -x
```

## Bug Report Template

```markdown
### 🐛 BUG-XXX: [Brief Description]

| Field | Value |
|-------|-------|
| **Story Points** | [1-5] |
| **Priority** | 🔴 Critical / 🟡 High / 🟢 Medium / ⚪ Low |
| **Status** | 📋 Planned |
| **Severity** | Critical / High / Medium / Low |
| **Reported By** | [Source] |
| **Assignee** | @username |

#### Description

**As a** [user type]
**I want** [expected behavior]
**So that** [value/outcome]

**Bug Details:**

- **Observed**: [What happens]
- **Expected**: [What should happen]
- **Frequency**: [How often]
- **Impact**: [Business impact]

#### Steps to Reproduce

1. Step one
2. Step two
3. Observe bug

#### Acceptance Criteria

- [ ] Bug is fixed
- [ ] Test case added
- [ ] No regression

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Investigate | Root cause analysis | 1 | 📋 Planned |
| 2 | Fix | Implement solution | X | 📋 Planned |
| 3 | Test | Verify fix | 1 | 📋 Planned |

---
```

## Severity Guidelines

| Severity | Criteria | Response Time |
|----------|----------|---------------|
| 🔴 Critical | Service down, data loss, security breach | Immediate |
| 🟡 High | Major feature broken, significant user impact | 24 hours |
| 🟢 Medium | Feature impaired, workaround exists | 1 week |
| ⚪ Low | Minor issue, cosmetic, edge case | Backlog |

## Tips

::: tip Efficient Triage
- Triage weekly, sync immediately after
- Use severity to prioritize, not just priority
- Track metrics over time to identify patterns
:::

::: tip Bug Prevention
- Link bugs to root cause stories
- Create follow-up tasks for systemic issues
- Review bug trends in retrospectives
:::

