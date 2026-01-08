# Terraform Provider for Jira

Manage Jira issues, epics, and subtasks as infrastructure-as-code using Terraform.

## Features

- **Create and manage Jira issues** - Stories, Bugs, Tasks, Epics
- **Create subtasks** - Break down stories into actionable items
- **Read existing issues** - Use data sources to reference existing Jira data
- **Import support** - Import existing issues into Terraform state
- **Full CRUD operations** - Create, Read, Update, Delete

## Requirements

- [Terraform](https://www.terraform.io/downloads.html) >= 1.0
- [Go](https://golang.org/doc/install) >= 1.21 (for building)
- Jira Cloud account with API access

## Installation

### Building from Source

```bash
cd terraform-provider-jira
go build -o terraform-provider-jira
```

### Installing Locally

```bash
# Create plugin directory
mkdir -p ~/.terraform.d/plugins/registry.terraform.io/spectryn/jira/1.0.0/$(go env GOOS)_$(go env GOARCH)

# Copy the binary
cp terraform-provider-jira ~/.terraform.d/plugins/registry.terraform.io/spectryn/jira/1.0.0/$(go env GOOS)_$(go env GOARCH)/
```

## Authentication

The provider requires Jira Cloud API credentials. You can provide them via:

### Environment Variables (Recommended)

```bash
export JIRA_URL="https://your-company.atlassian.net"
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-api-token"
```

### Provider Configuration

```hcl
provider "jira" {
  url       = "https://your-company.atlassian.net"
  email     = "your-email@company.com"
  api_token = var.jira_api_token  # Use a variable, not hardcoded!
}
```

### Getting an API Token

1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Give it a descriptive name (e.g., "Terraform")
4. Copy the token and store it securely

## Quick Start

```hcl
terraform {
  required_providers {
    jira = {
      source  = "spectryn/jira"
      version = "~> 1.0"
    }
  }
}

provider "jira" {}

# Create a Story
resource "jira_issue" "my_story" {
  project     = "PROJ"
  summary     = "Implement new feature"
  description = "As a user, I want this feature so that I can do something."
  issue_type  = "Story"
  priority    = "Medium"
  labels      = ["sprint-1", "backend"]
}

# Create subtasks
resource "jira_subtask" "task1" {
  project     = "PROJ"
  parent_key  = jira_issue.my_story.key
  summary     = "Backend implementation"
  story_points = 3
}

resource "jira_subtask" "task2" {
  project     = "PROJ"
  parent_key  = jira_issue.my_story.key
  summary     = "Frontend implementation"
  story_points = 2
}
```

## Resources

### jira_issue

Manages a Jira issue (Story, Bug, Task, Epic, etc.).

#### Arguments

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project key (e.g., "PROJ") |
| `summary` | string | Yes | Issue summary/title |
| `issue_type` | string | Yes | Issue type (Story, Bug, Task, Epic, etc.) |
| `description` | string | No | Issue description |
| `priority` | string | No | Priority (Highest, High, Medium, Low, Lowest) |
| `labels` | list(string) | No | Issue labels |
| `parent_key` | string | No | Parent issue key (for stories in epics) |

#### Attributes

| Name | Description |
|------|-------------|
| `id` | Jira issue ID |
| `key` | Jira issue key (e.g., "PROJ-123") |
| `status` | Current issue status |

### jira_subtask

Manages a Jira subtask under a parent issue.

#### Arguments

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project key |
| `parent_key` | string | Yes | Parent issue key |
| `summary` | string | Yes | Subtask summary |
| `description` | string | No | Subtask description |
| `story_points` | number | No | Story points estimate |

#### Attributes

| Name | Description |
|------|-------------|
| `id` | Jira issue ID |
| `key` | Jira issue key |
| `status` | Current status |

## Data Sources

### jira_issue

Fetches an existing Jira issue.

```hcl
data "jira_issue" "existing" {
  key = "PROJ-123"
}
```

### jira_project

Fetches a Jira project.

```hcl
data "jira_project" "main" {
  key = "PROJ"
}
```

## Import

Import existing issues into Terraform state:

```bash
# Import an issue
terraform import jira_issue.example PROJ-123

# Import a subtask
terraform import jira_subtask.example PROJ-456
```

## Examples

See the [examples](./examples) directory for complete examples:

- [Basic](./examples/basic) - Story with subtasks
- [Epic](./examples/epic) - Epic with multiple stories
- [Data Sources](./examples/data-sources) - Reading existing data

## Development

### Building

```bash
go build -o terraform-provider-jira
```

### Testing

```bash
go test ./...
```

### Running Acceptance Tests

```bash
export JIRA_URL="https://your-company.atlassian.net"
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-api-token"
export TF_ACC=1

go test ./... -v
```

## Integration with spectryn

This provider is part of the [spectryn](https://github.com/spectryn/spectryn) project, which provides tools for managing Jira from markdown documentation.

You can use this Terraform provider alongside spectryn for different use cases:

- **spectryn**: Sync existing markdown documentation to Jira
- **Terraform provider**: Manage Jira as infrastructure-as-code

## License

MIT License - see [LICENSE](../LICENSE) for details.

