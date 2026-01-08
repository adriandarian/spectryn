# AI Prompts

Use these prompts with AI assistants (Claude, ChatGPT, etc.) to generate properly formatted epic documentation.

::: tip Already Have a Document?
If you have an existing markdown file with formatting issues, see the [AI Fix Guide](/guide/ai-fix) for help correcting it. This page covers generating **new** documents from scratch.
:::

## The Prompt

Copy and paste this prompt, replacing the `[PLACEHOLDERS]` with your project details:

````markdown
You are a technical documentation specialist. Generate a Jira-compatible epic document in markdown format for the following project. Follow the EXACT schema below - the format is parsed by automation tools.

## Project Details

**Project Name**: [YOUR PROJECT NAME]
**Project Description**: [DESCRIBE WHAT YOU'RE BUILDING]
**Key Features/Requirements**:
- [FEATURE 1]
- [FEATURE 2]
- [FEATURE 3]

**Target Audience**: [WHO WILL USE THIS]
**Timeline**: [START DATE] to [END DATE]
**Priority**: [Critical/High/Medium]

---

## REQUIRED OUTPUT FORMAT

Generate the epic document following this EXACT structure:

### Epic Header
```markdown
# 📋 [Epic Title]

> **Epic: [Short Description]**

---

## Epic Summary

| Field | Value |
|-------|-------|
| **Epic Name** | [Name] |
| **Status** | 📋 Planned |
| **Priority** | 🔴 Critical / 🟡 High / 🟢 Medium |
| **Start Date** | [Month Year] |
| **Target Release** | [Version] |

### Summary
[One paragraph summary]

### Description
[Detailed description with **Key Areas** bullet list]

### Business Value
[Bullet list of business benefits]
```

### User Story Format (CRITICAL - Follow Exactly)
```markdown
### [emoji] US-XXX: [Story Title]

| Field | Value |
|-------|-------|
| **Story Points** | [1-13 Fibonacci] |
| **Priority** | 🔴 Critical / 🟡 High / 🟢 Medium |
| **Status** | 📋 Planned |

#### Description

**As a** [role]
**I want** [feature]
**So that** [benefit]

[Optional additional context]

#### Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | [Name] | [Description] | 1 | 📋 Planned |
| 2 | [Name] | [Description] | 1 | 📋 Planned |

---
```

## FORMATTING RULES

1. **Story IDs**: Use sequential numbering: STORY-001, STORY-002, STORY-003... (or any prefix like PROJ-123, FEAT-042)
2. **Emojis for Story Types**:
   - 🔧 Technical/Infrastructure
   - 🚀 New Feature
   - 🎨 UI/Design
   - 🐛 Bug Fix
   - 📚 Documentation
   - 🔒 Security
   - ⚡ Performance

3. **Status Emojis**:
   - ✅ Done
   - 🔄 In Progress
   - 📋 Planned

4. **Priority Emojis**:
   - 🔴 Critical
   - 🟡 High
   - 🟢 Medium/Low

5. **Story Points**: Use Fibonacci (1, 2, 3, 5, 8, 13)
6. **Subtasks**:
   - Keep descriptions concise (under 100 chars)
   - Each subtask should be 1-2 story points
   - Sum of subtask SPs should roughly equal story SPs

7. **Separators**: Use `---` between stories

## GENERATE

Now generate a complete epic document with [NUMBER] user stories covering the features I described. Make the stories detailed enough to be actionable but concise enough to be readable.
````

## Example Usage

### Input to AI

```
You are a technical documentation specialist. Generate a Jira-compatible epic document...

## Project Details

**Project Name**: Customer Portal Redesign
**Project Description**: Modernize our customer-facing portal from Angular to React with improved UX
**Key Features/Requirements**:
- User authentication with SSO
- Dashboard with analytics widgets
- Document management system
- Real-time notifications

**Target Audience**: Enterprise customers and internal support team
**Timeline**: January 2025 to June 2025
**Priority**: High

...

Now generate a complete epic document with 6 user stories covering the features I described.
```

### Output from AI

The AI will generate a complete, parseable markdown document ready for spectryn.

## Prompt Variations

### For Bug Fixes Epic

```
Generate a bug fix epic with the following known issues:
- [Bug 1 description]
- [Bug 2 description]
- [Bug 3 description]

Use 🐛 emoji for all stories. Each bug should have acceptance criteria for "bug is fixed when..."
```

### For Documentation Epic

```
Generate a documentation epic for:
- API reference documentation
- User guides
- Developer onboarding docs

Use 📚 emoji for all stories. Include subtasks for: outline, draft, review, publish.
```

### For Migration Epic

```
Generate a migration epic for moving from [OLD SYSTEM] to [NEW SYSTEM]:
- Data migration steps
- Code refactoring
- Testing phases
- Rollback procedures

Focus on risk mitigation and validation criteria.
```

## Tips for Best Results

::: tip Get Better AI Output

1. **Be Specific** - The more detail you provide about features, the better the output
2. **Set Scope** - Specify number of stories to keep output manageable
3. **Iterate** - Generate, review, and ask for refinements
4. **Validate** - Run through spectryn with `--validate` first

:::

## Quick One-Liner Prompt

For simple projects, use this condensed prompt:

```
Generate a Jira epic in markdown for "[PROJECT]" with [N] user stories.
Use this format for each story:
### 🔧 US-XXX: Title
| Field | Value |
| **Story Points** | N |
| **Priority** | emoji Priority |
| **Status** | 📋 Planned |
#### Description
**As a** role **I want** feature **So that** benefit
#### Acceptance Criteria
- [ ] criteria
#### Subtasks
| # | Subtask | Description | SP | Status |
Separate stories with ---
```

## Related Documentation

- [AI Fix Guide](/guide/ai-fix) – Fix formatting issues in existing documents
- [AI Agents Guide](/guide/agents) – Context for AI coding assistants working on spectryn
- [Validation Reference](/reference/cli#validation-options) – CLI validation options
- [Format Schema](/guide/schema) – Complete markdown format specification

