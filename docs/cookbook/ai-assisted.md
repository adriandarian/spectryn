# AI-Assisted Planning

Use AI assistants to generate, refine, and maintain epic documentation.

## Overview

Combine AI capabilities with spectryn for powerful project planning:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Requirements   │ ──▶ │  AI Assistant   │ ──▶ │  Epic Markdown  │
│  (rough ideas)  │     │  (Claude, GPT)  │     │  (structured)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │    spectryn      │ ──▶ Jira
                                                └─────────────────┘
```

## Use Cases

### 1. Generate Epic from Requirements

**Input to AI:**

```
Create a Jira-compatible epic document for:

Project: Customer Support Portal
Requirements:
- Ticket submission form
- Live chat with agents
- Knowledge base search
- Ticket history and status tracking
- Customer satisfaction surveys

Target: 6 user stories
Format: Use spectryn schema with US-XXX IDs, status emojis, subtasks
```

**AI generates complete markdown ready for sync.**

### 2. Refine Existing Stories

**Input to AI:**

```
Review this user story and improve it:

### 🚀 US-003: Chat Feature

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |

#### Description

**As a** customer
**I want** to chat
**So that** I can get help

Make the description more specific, add acceptance criteria, 
and suggest subtasks.
```

### 3. Break Down Large Stories

**Input to AI:**

```
This story is too large (13 points). Break it into smaller stories:

### 🚀 US-005: Complete Payment System

| Field | Value |
|-------|-------|
| **Story Points** | 13 |

#### Description
Implement full payment processing with Stripe, PayPal, 
invoicing, refunds, and reporting.

Split into 3-5 point stories that can be done independently.
```

### 4. Generate from PRD

**Input to AI:**

```
Convert this PRD section into user stories:

## Feature: Multi-language Support

The application should support English, Spanish, and French.
Users should be able to switch languages from their profile.
All UI text, emails, and error messages should be translated.
We need a translation management system for our content team.

Generate 4-6 user stories following spectryn format.
```

## AI Prompts Library

### Epic Generation Prompt

````markdown
You are a technical product manager. Generate a complete epic document 
for syncing with Jira via spectryn.

## Project Context
**Name**: [PROJECT NAME]
**Description**: [WHAT ARE WE BUILDING]
**Duration**: [TIMELINE]
**Team Size**: [NUMBER OF DEVELOPERS]

## Requirements
[LIST KEY REQUIREMENTS]

## Output Format

Generate markdown following this EXACT structure:

```markdown
# 📋 [Epic Title]

> **Epic: [Short description]**

---

## Epic Summary
[Summary section with table]

## User Stories
[Stories with US-XXX format, metadata tables, 
descriptions, acceptance criteria, subtasks]
```

## Rules
1. Use sequential IDs: US-001, US-002, etc.
2. Story points: Fibonacci (1,2,3,5,8,13)
3. Status: all 📋 Planned (new epic)
4. Emojis: 🔧 tech, 🚀 feature, 🎨 UI, 🐛 bug
5. Each story has: description, acceptance criteria, subtasks
6. Subtask SPs should sum to story SP

Generate [N] user stories covering all requirements.
````

### Story Refinement Prompt

```markdown
Review and improve this user story for clarity and completeness:

[PASTE STORY]

Improve by:
1. Making the description more specific
2. Adding measurable acceptance criteria
3. Suggesting realistic subtasks
4. Adjusting story points if needed
5. Identifying any missing edge cases

Output the improved story in the same spectryn format.
```

### Story Splitting Prompt

```markdown
This user story is too large to complete in one sprint.
Split it into smaller, independent stories.

[PASTE LARGE STORY]

Guidelines:
- Each story should be 3-5 points
- Stories should be independently deployable
- Maintain clear dependencies if any
- Keep the same format (spectryn compatible)

Output the split stories.
```

### Technical Spec Addition Prompt

```markdown
Add technical specifications to this user story:

[PASTE STORY]

Include:
1. API endpoints needed
2. Database changes
3. External service integrations
4. Performance considerations
5. Security requirements

Add as a "#### Technical Notes" section.
```

## Workflow Integration

### IDE Integration

Use your editor's AI assistant:

```bash
# In VS Code with Cursor/Copilot
# 1. Open epic markdown file
# 2. Use AI to generate/refine
# 3. Save and commit
# 4. CI syncs to Jira
```

### CLI Workflow

```bash
# Generate with AI (example using Claude API)
cat requirements.txt | claude "Generate epic markdown..." > docs/epics/new-feature.md

# Validate the output
spectryn -m docs/epics/new-feature.md -e PROJ-100 --validate

# Preview sync
spectryn -m docs/epics/new-feature.md -e PROJ-100

# If good, execute
spectryn -m docs/epics/new-feature.md -e PROJ-100 -x
```

### Automation Script

```bash
#!/bin/bash
# ai-epic.sh - Generate and sync epic from requirements

REQUIREMENTS=$1
EPIC_KEY=$2
OUTPUT="docs/epics/${EPIC_KEY}.md"

# Generate with AI (using your preferred AI CLI)
cat "$REQUIREMENTS" | ai-cli generate --template epic > "$OUTPUT"

# Validate
if spectryn -m "$OUTPUT" -e "$EPIC_KEY" --validate; then
  echo "✓ Validation passed"
  
  # Preview
  spectryn -m "$OUTPUT" -e "$EPIC_KEY"
  
  read -p "Sync to Jira? (y/n) " confirm
  if [ "$confirm" = "y" ]; then
    spectryn -m "$OUTPUT" -e "$EPIC_KEY" -x
    echo "✓ Synced to Jira"
  fi
else
  echo "✗ Validation failed - please fix errors"
  exit 1
fi
```

## Quality Checklist

After AI generation, verify:

- [ ] Story IDs are sequential and unique
- [ ] All stories have metadata tables
- [ ] Descriptions follow As a/I want/So that
- [ ] Story points are Fibonacci numbers
- [ ] Subtasks have reasonable point estimates
- [ ] No placeholder text remains
- [ ] Technical feasibility checked
- [ ] Dependencies identified

## Tips

::: tip Iterate with AI
- Start with rough requirements
- Generate first draft with AI
- Refine iteratively
- Human review before sync
:::

::: tip Context Matters
- Provide domain context to AI
- Include constraints and limitations
- Reference existing patterns
- Mention team size and timeline
:::

::: tip Validation
- Always use `--validate` before sync
- Review AI output for feasibility
- Check story point estimates
- Verify acceptance criteria are testable
:::

::: warning AI Limitations
- AI may miss domain-specific constraints
- Story points are estimates only
- Technical feasibility needs human review
- Security requirements need expert input
:::

