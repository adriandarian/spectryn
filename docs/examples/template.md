# Epic Template

A blank template to get started with spectra.

## Copy & Customize

Copy this template and replace the placeholders with your content.

````markdown
# 📋 [Epic Title]

> **Epic: [Short Epic Description]**

---

## Epic Summary

| Field | Value |
|-------|-------|
| **Epic Name** | [Epic Name] |
| **Status** | 📋 Planned / 🔄 In Progress / ✅ Done |
| **Priority** | 🔴 Critical / 🟡 High / 🟢 Medium |
| **Start Date** | [Month Year] |
| **Target Release** | [Version] |

### Summary

[One paragraph summary of the epic - what is being built and why]

### Description

[Detailed description of the epic, including context and scope]

**Key Areas:**
- **Area 1**: Brief description
- **Area 2**: Brief description
- **Area 3**: Brief description

### Business Value

- **Value 1**: Description of business impact
- **Value 2**: Description of business impact
- **Value 3**: Description of business impact

---

## User Stories

---

### 🔧 US-001: [Story Title]

| Field | Value |
|-------|-------|
| **Story Points** | [1-13] |
| **Priority** | 🔴 Critical / 🟡 High / 🟢 Medium |
| **Status** | 📋 Planned / 🔄 In Progress / ✅ Done |

#### Description

**As a** [role/persona]
**I want** [feature/capability]
**So that** [benefit/value]

[Optional: Additional context about the story]

#### Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3
- [ ] Criterion 4

#### Technical Notes

[Optional: Technical details, code examples, architecture notes]

```typescript
// Example code if relevant
```

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | [Subtask Name] | [Brief description of the work] | 1 | 📋 Planned |
| 2 | [Subtask Name] | [Brief description of the work] | 1 | 🔄 In Progress |
| 3 | [Subtask Name] | [Brief description of the work] | 1 | ✅ Done |

#### Related Commits

| Commit | Message |
|--------|---------|
| `abc1234` | feat: description of change |
| `def5678` | fix: description of fix |

#### Comments

> **@reviewer** (2025-01-15):
> Initial review feedback - looks good overall.
> Consider adding error handling for edge cases.

> **@developer** (2025-01-16):
> Good point! I'll add try/catch blocks in the next iteration.

---

### 🚀 US-002: [Next Story Title]

[Repeat the same structure for each user story...]

---

## Notes

- Stories should be ordered by dependency or priority
- Use consistent emoji indicators for status
- Keep subtask descriptions concise but actionable
- Story points should follow Fibonacci sequence (1, 2, 3, 5, 8, 13)
````

## Quick Reference

### Story Type Emojis

| Emoji | Use For |
|-------|---------|
| 🔧 | Technical/Infrastructure |
| 🚀 | New Feature |
| 🎨 | UI/Design |
| 🐛 | Bug Fix |
| 📚 | Documentation |
| 🔒 | Security |
| ⚡ | Performance |
| ♻️ | Refactoring |

### Status Emojis

| Emoji | Status | Jira |
|-------|--------|------|
| 📋 | Planned | Open |
| 🔄 | In Progress | In Progress |
| ✅ | Done | Resolved |

### Priority Emojis

| Emoji | Priority |
|-------|----------|
| 🔴 | Critical |
| 🟡 | High |
| 🟢 | Medium/Low |

### Story Points (Fibonacci)

| Points | Complexity |
|--------|------------|
| 1 | Trivial - hours |
| 2 | Simple - half day |
| 3 | Moderate - 1-2 days |
| 5 | Complex - 3-4 days |
| 8 | Very complex - 1 week |
| 13 | Epic-level - break down further |

## Minimal Template

For quick starts, use this minimal structure:

```markdown
# 🚀 [Project Name]

## User Stories

---

### 🔧 US-001: [Title]

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |

#### Description

**As a** user
**I want** feature
**So that** benefit

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Task 1 | Description | 1 | 📋 Planned |
| 2 | Task 2 | Description | 2 | 📋 Planned |

---
```

