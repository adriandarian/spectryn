# YAML Schema for md2jira

This document defines the YAML schema for defining epics and user stories as an alternative to markdown input.

## Overview

The YAML format provides a structured, machine-friendly way to define epics and stories. It's particularly useful for:

- Generating specs programmatically
- CI/CD pipelines
- Integration with other tools
- Bulk operations

## Quick Example

```yaml
epic:
  key: PROJ-100
  title: "User Authentication System"
  description: "Implement secure authentication for the platform"

stories:
  - id: US-001
    title: "User Login"
    description:
      as_a: "registered user"
      i_want: "to log in with my email and password"
      so_that: "I can access my account"
    story_points: 5
    priority: high
    status: planned
    acceptance_criteria:
      - criterion: "User can enter email and password"
        done: false
      - criterion: "Invalid credentials show error message"
        done: false
    subtasks:
      - name: "Create login form UI"
        description: "Build responsive login form component"
        story_points: 2
        status: planned
      - name: "Implement authentication API"
        story_points: 3
        status: planned
```

## Full Schema Reference

### Root Structure

```yaml
# Optional: Epic metadata
epic:
  key: string          # Optional: Existing Jira/tracker epic key (e.g., "PROJ-123")
  title: string        # Required: Epic title
  description: string  # Optional: Epic description

# Required: List of user stories
stories:
  - # Story definition (see below)
```

### Story Definition

```yaml
stories:
  - id: string                # Required: Story ID (e.g., "US-001")
    title: string             # Required: Story title
    
    # Description - supports two formats:
    # Format 1: Structured (recommended)
    description:
      as_a: string            # User role
      i_want: string          # Desired feature
      so_that: string         # Expected benefit
    
    # Format 2: Simple string
    description: "As a user, I want feature so that benefit"
    
    story_points: integer     # Optional: Story point estimate (default: 0)
    priority: string          # Optional: low, medium, high, critical (default: medium)
    status: string            # Optional: planned, in_progress, done, blocked (default: planned)
    
    acceptance_criteria:      # Optional: List of acceptance criteria
      - criterion: string     # Criterion text
        done: boolean         # Whether it's completed (default: false)
      # Or simple string format:
      - "Simple criterion text"
    
    subtasks:                 # Optional: List of subtasks
      - name: string          # Required: Subtask name
        description: string   # Optional: Subtask description
        story_points: integer # Optional: Story points (default: 1)
        status: string        # Optional: planned, in_progress, done (default: planned)
        assignee: string      # Optional: Assignee email/name
      # Or simple string format:
      - "Simple subtask name"
    
    commits:                  # Optional: Related commits
      - hash: string          # Commit SHA
        message: string       # Commit message
      # Or just the hash:
      - "abc1234"
    
    technical_notes: |        # Optional: Technical notes (multiline)
      Technical implementation details here.
      Can span multiple lines.
```

### Field Details

#### Epic Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `key` | string | No | `EPIC-0` | Existing tracker issue key to use as epic |
| `title` | string | Yes | - | Epic title |
| `description` | string | No | `""` | Epic description |

#### Story Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | Yes | - | Story identifier (e.g., `US-001`) |
| `title` | string | Yes | - | Story title |
| `description` | object/string | No | `null` | User story description |
| `story_points` | integer | No | `0` | Story point estimate |
| `priority` | string | No | `medium` | Priority level |
| `status` | string | No | `planned` | Current status |
| `acceptance_criteria` | array | No | `[]` | List of acceptance criteria |
| `subtasks` | array | No | `[]` | List of subtasks |
| `commits` | array | No | `[]` | Related git commits |
| `technical_notes` | string | No | `""` | Technical implementation notes |

#### Priority Values

- `low` - Low priority
- `medium` - Medium priority (default)
- `high` - High priority
- `critical` - Critical/urgent

#### Status Values

- `planned` - Not started (default)
- `in_progress` - Currently being worked on
- `done` - Completed
- `blocked` - Blocked by dependencies

### Subtask Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Subtask name/title |
| `description` | string | No | `""` | Detailed description |
| `story_points` | integer | No | `1` | Story point estimate |
| `status` | string | No | `planned` | Current status |
| `assignee` | string | No | `null` | Assignee email or name |

## Examples

### Minimal Example

```yaml
stories:
  - id: US-001
    title: "Basic feature"
```

### With Simple Descriptions

```yaml
stories:
  - id: US-001
    title: "User Login"
    description: "As a user, I want to log in so that I can access my account"
    story_points: 3
    acceptance_criteria:
      - "User can enter credentials"
      - "Error shown for invalid login"
    subtasks:
      - "Create login form"
      - "Add validation"
```

### Full-Featured Example

```yaml
epic:
  key: PROJ-500
  title: "Payment Processing"
  description: |
    Implement comprehensive payment processing system
    supporting multiple payment providers.

stories:
  - id: US-010
    title: "Credit Card Payments"
    description:
      as_a: "customer"
      i_want: "to pay with my credit card"
      so_that: "I can complete my purchase quickly"
    story_points: 8
    priority: high
    status: in_progress
    acceptance_criteria:
      - criterion: "Support Visa, Mastercard, Amex"
        done: true
      - criterion: "Display card type icon"
        done: false
      - criterion: "Validate card number format"
        done: true
      - criterion: "Handle payment failures gracefully"
        done: false
    subtasks:
      - name: "Integrate Stripe SDK"
        description: "Add Stripe payment processing library"
        story_points: 2
        status: done
      - name: "Build payment form component"
        description: "Create secure credit card input form with validation"
        story_points: 3
        status: in_progress
      - name: "Add error handling"
        description: "Handle and display payment failures"
        story_points: 2
        status: planned
      - name: "Write integration tests"
        story_points: 1
        status: planned
    commits:
      - hash: "a1b2c3d4"
        message: "Add Stripe dependency"
      - hash: "e5f6g7h8"
        message: "Implement payment form"
    technical_notes: |
      Using Stripe Elements for PCI compliance.
      Card data never touches our servers.
      
      Required environment variables:
      - STRIPE_PUBLIC_KEY
      - STRIPE_SECRET_KEY

  - id: US-011
    title: "PayPal Integration"
    description:
      as_a: "customer"
      i_want: "to pay with PayPal"
      so_that: "I don't need to enter card details"
    story_points: 5
    priority: medium
    status: planned
    acceptance_criteria:
      - criterion: "PayPal button displayed at checkout"
      - criterion: "Redirect to PayPal for authentication"
      - criterion: "Handle PayPal webhooks"
    subtasks:
      - name: "Add PayPal SDK"
        story_points: 1
      - name: "Implement PayPal button"
        story_points: 2
      - name: "Handle webhooks"
        story_points: 2
```

### Multiple Epics in Separate Files

You can organize by having separate YAML files per epic:

**`auth-epic.yaml`:**
```yaml
epic:
  title: "Authentication"
stories:
  - id: US-001
    title: "Login"
    # ...
  - id: US-002
    title: "Logout"
    # ...
```

**`payments-epic.yaml`:**
```yaml
epic:
  title: "Payments"
stories:
  - id: US-010
    title: "Credit Card"
    # ...
```

## Validation

The YAML parser validates:

1. **Structure**: Root must be a dictionary with `stories` or `epic`
2. **Required fields**: Each story must have `id` and `title`
3. **Field types**: Numbers must be numbers, lists must be lists
4. **Enum values**: Priority and status must be valid values

### Validation Errors

Run validation with:

```bash
md2jira validate --input stories.yaml
```

Example error output:

```
stories[0]: missing required field 'id'
stories[1].priority: must be one of ['low', 'medium', 'high', 'critical']
stories[2].subtasks: must be a list
```

## Usage

### CLI

```bash
# Sync from YAML file
md2jira sync --input stories.yaml --epic PROJ-123

# Validate YAML file
md2jira validate --input stories.yaml

# Dry run
md2jira sync --input stories.yaml --epic PROJ-123 --dry-run
```

### Programmatic

```python
from md2jira.adapters.parsers import YamlParser

parser = YamlParser()

# Parse stories
stories = parser.parse_stories("stories.yaml")

# Parse full epic
epic = parser.parse_epic("stories.yaml")

# Validate before parsing
errors = parser.validate("stories.yaml")
if errors:
    for error in errors:
        print(f"Error: {error}")
```

## Converting from Markdown

If you have existing markdown files, you can convert them to YAML:

```python
from md2jira.adapters.parsers import MarkdownParser, YamlParser
import yaml

# Parse from markdown
md_parser = MarkdownParser()
epic = md_parser.parse_epic("epic.md")

# Convert to YAML structure
yaml_data = {
    "epic": {
        "title": epic.title,
    },
    "stories": [
        {
            "id": str(story.id),
            "title": story.title,
            "story_points": story.story_points,
            "priority": story.priority.name.lower(),
            "status": story.status.name.lower(),
            "description": {
                "as_a": story.description.role if story.description else "",
                "i_want": story.description.want if story.description else "",
                "so_that": story.description.benefit if story.description else "",
            } if story.description else None,
        }
        for story in epic.stories
    ],
}

# Write YAML
with open("epic.yaml", "w") as f:
    yaml.dump(yaml_data, f, default_flow_style=False)
```

