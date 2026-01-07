# Azure DevOps Integration Guide

spectra supports Azure DevOps for syncing markdown specifications to Work Items. This guide covers configuration, authentication, and advanced features.

## Overview

The Azure DevOps adapter supports:
- ✅ Azure DevOps Services (cloud) and Azure DevOps Server (on-premises)
- ✅ Work Items: Epics, Features, User Stories, Tasks, Bugs
- ✅ Sprints and Iterations
- ✅ Area Paths
- ✅ Custom fields and templates
- ✅ Boards and Backlogs
- ✅ Wiki linking

## Quick Start

```bash
# Install spectra
pip install spectra

# Sync markdown to Azure DevOps
spectra sync --markdown EPIC.md --tracker azure --project MyProject --execute
```

## Configuration

### Config File (YAML)

Create `.spectra.yaml`:

```yaml
# Azure DevOps connection settings
azure_devops:
  organization: your-org
  project: your-project
  pat: your-personal-access-token

  # Optional: Azure DevOps Server (on-premises)
  base_url: https://dev.azure.com  # or https://tfs.mycompany.com/tfs

  # Work item type mapping (optional)
  work_item_types:
    epic: Epic
    story: User Story
    subtask: Task
    bug: Bug

  # Area path (optional)
  area_path: MyProject\Team A

  # Iteration path (optional)
  iteration_path: MyProject\Sprint 1

  # State mapping (optional)
  state_mapping:
    planned: New
    in_progress: Active
    done: Closed

# Sync settings
sync:
  execute: false
  verbose: true
```

### Config File (TOML)

Create `.spectra.toml`:

```toml
[azure_devops]
organization = "your-org"
project = "your-project"
pat = "your-personal-access-token"
base_url = "https://dev.azure.com"
area_path = "MyProject\\Team A"
iteration_path = "MyProject\\Sprint 1"

[azure_devops.work_item_types]
epic = "Epic"
story = "User Story"
subtask = "Task"
bug = "Bug"

[azure_devops.state_mapping]
planned = "New"
in_progress = "Active"
done = "Closed"

[sync]
execute = false
verbose = true
```

### Environment Variables

```bash
# Required
export AZURE_DEVOPS_ORG=your-organization
export AZURE_DEVOPS_PROJECT=your-project
export AZURE_DEVOPS_PAT=your-personal-access-token

# Optional
export AZURE_DEVOPS_BASE_URL=https://dev.azure.com
export AZURE_DEVOPS_AREA_PATH="MyProject\Team A"
export AZURE_DEVOPS_ITERATION_PATH="MyProject\Sprint 1"
```

### CLI Arguments

```bash
spectra sync \
  --tracker azure \
  --markdown EPIC.md \
  --project MyProject \
  --organization my-org \
  --execute
```

## Authentication

### Personal Access Token (PAT)

1. Go to **User Settings** → **Personal access tokens**
2. Click **+ New Token**
3. Configure:
   - **Name**: spectra-sync
   - **Organization**: Select your organization
   - **Expiration**: Set appropriate expiration
   - **Scopes**: Select these scopes:
     - Work Items: Read & write
     - Project and team: Read
     - Build: Read (optional, for linking)

4. Copy the token immediately (it won't be shown again)

### Service Principal (For CI/CD)

For automated pipelines:

```yaml
azure_devops:
  client_id: your-client-id
  client_secret: your-client-secret
  tenant_id: your-tenant-id
```

## Features

### Work Item Hierarchy

spectra maps to Azure DevOps hierarchy:

| Markdown | Azure DevOps |
|----------|--------------|
| Epic header | Epic |
| Story | User Story / Feature |
| Subtask | Task |
| Bug section | Bug |

### State Mapping

Map markdown statuses to Azure DevOps states:

```yaml
azure_devops:
  state_mapping:
    "📋 Planned": "New"
    "🔄 In Progress": "Active"
    "🔍 Review": "Resolved"
    "✅ Done": "Closed"
    "🚫 Blocked": "Blocked"
```

### Story Points

Story points map to the Effort field:

```markdown
| Field | Value |
|-------|-------|
| **Story Points** | 5 |
```

Custom field mapping:

```yaml
azure_devops:
  fields:
    story_points: Microsoft.VSTS.Scheduling.Effort
    priority: Microsoft.VSTS.Common.Priority
```

### Area and Iteration Paths

Organize work items by team or sprint:

```yaml
azure_devops:
  area_path: MyProject\Backend Team
  iteration_path: MyProject\2024\Sprint 1

  # Or map from markdown
  area_mapping:
    backend: MyProject\Backend Team
    frontend: MyProject\Frontend Team
```

### Custom Fields

Map markdown fields to custom Azure DevOps fields:

```yaml
azure_devops:
  custom_fields:
    business_value: Custom.BusinessValue
    risk: Custom.Risk
    team: Custom.Team
```

Use in markdown:

```markdown
| Field | Value |
|-------|-------|
| **Business Value** | High |
| **Risk** | Medium |
| **Team** | Platform |
```

### Tags

Add tags to work items:

```markdown
| Field | Value |
|-------|-------|
| **Tags** | mvp, customer-request |
```

## Advanced Configuration

### Sprint Planning

Auto-assign to current sprint:

```yaml
azure_devops:
  auto_assign_sprint: true
  sprint_detection: current  # or "next", "backlog"
```

### Acceptance Criteria

Map acceptance criteria to the field:

```yaml
azure_devops:
  acceptance_criteria_field: Microsoft.VSTS.Common.AcceptanceCriteria
```

```markdown
#### Acceptance Criteria

- [ ] User can log in with email
- [ ] Session persists for 24 hours
- [ ] Failed attempts are logged
```

### Related Work Items

Link to existing work items:

```markdown
| Field | Value |
|-------|-------|
| **Related** | #123, #456 |
| **Parent** | #100 |
| **Blocked By** | #789 |
```

### Attachments

Link to attachments:

```yaml
azure_devops:
  sync_attachments: true
  attachment_base_path: ./docs/images
```

## Example Workflow

### 1. Create Epic Markdown

```markdown
# 🚀 Payment System Epic

> **Epic: Complete payment processing system**

---

## User Stories

---

### 💳 US-001: Credit Card Processing

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |
| **Tags** | payments, pci |
| **Area** | backend |
| **Sprint** | Sprint 1 |

#### Description

**As a** customer
**I want** to pay with credit card
**So that** I can complete purchases

#### Acceptance Criteria

- [ ] Support Visa, Mastercard, Amex
- [ ] PCI DSS compliance
- [ ] 3D Secure support

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Payment gateway | Integrate Stripe | 3 | 📋 Planned |
| 2 | Card validation | Implement Luhn check | 2 | 📋 Planned |
| 3 | Tokenization | Store card tokens | 3 | 📋 Planned |

---

### 🧾 US-002: Invoice Generation

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟡 High |
| **Status** | 📋 Planned |
| **Tags** | billing, pdf |
| **Area** | backend |
| **Sprint** | Sprint 2 |

#### Description

**As a** customer
**I want** to receive invoices
**So that** I have purchase records
```

### 2. Preview Sync

```bash
spectra sync --tracker azure --markdown epic.md --project MyProject
```

### 3. Execute Sync

```bash
spectra sync --tracker azure --markdown epic.md --project MyProject --execute
```

### 4. View Results

Check your Azure DevOps Boards and Backlogs.

## Azure Pipelines Integration

### Pipeline YAML

```yaml
# azure-pipelines.yml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - script: pip install spectra
    displayName: 'Install spectra'

  - script: |
      spectra sync \
        --tracker azure \
        --markdown docs/EPIC.md \
        --project $(System.TeamProject) \
        --execute \
        --no-confirm
    displayName: 'Sync to Azure DevOps'
    env:
      AZURE_DEVOPS_PAT: $(AZURE_DEVOPS_PAT)
      AZURE_DEVOPS_ORG: $(System.CollectionUri)
```

## Troubleshooting

### Authentication Errors

```
Error: TF401019: The Git repository does not exist
```

- Verify PAT has correct scopes
- Check organization and project names
- Ensure PAT is not expired

### Work Item Type Errors

```
Error: TF401326: Invalid work item type
```

- Check process template (Agile, Scrum, CMMI, Basic)
- Verify work item types exist in project
- Use correct type names: "User Story" (Agile), "Product Backlog Item" (Scrum)

### Field Mapping Errors

```
Error: TF401320: Rule Error for field
```

- Check field reference names are correct
- Verify required fields are provided
- Check workflow rules don't block the state

## Best Practices

1. **Use PATs with Minimal Scope** - Only grant necessary permissions
2. **Map Work Item Types** - Match your process template
3. **Use Area Paths** - Organize by team or component
4. **Plan Iterations** - Set up sprints before syncing
5. **Configure State Mapping** - Align with your workflow

## Process Template Reference

| Markdown Status | Agile | Scrum | CMMI |
|-----------------|-------|-------|------|
| 📋 Planned | New | New | Proposed |
| 🔄 In Progress | Active | Committed | Active |
| 🔍 Review | Resolved | - | Resolved |
| ✅ Done | Closed | Done | Closed |

## See Also

- [Configuration Reference](/guide/configuration)
- [Quick Start](/guide/quick-start)
- [CI/CD Integration](/examples/cicd)
