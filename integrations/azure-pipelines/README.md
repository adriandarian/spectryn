# Spectra Azure Pipelines Template

Azure Pipelines template for syncing markdown specifications to issue trackers.

## Features

- **Multiple Trackers** - Support for Jira, GitHub, Azure DevOps, Linear, and more
- **Flexible Modes** - Dry-run, execute, pull (reverse sync)
- **Multi-Epic Support** - Sync multiple epics from one file
- **Template Library** - Reusable templates for consistent pipelines
- **Variable Groups** - Centralized credential management
- **Stage Deployments** - Environment-based deployments

## Quick Start

### Basic Pipeline

Create `azure-pipelines.yml`:

```yaml
trigger:
  - main

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - script: |
      pip install spectra
      spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY) --execute --no-confirm
    displayName: 'Sync to Jira'
    env:
      JIRA_URL: $(JIRA_URL)
      JIRA_EMAIL: $(JIRA_EMAIL)
      JIRA_API_TOKEN: $(JIRA_API_TOKEN)
```

### Using Templates

Reference the template from your pipeline:

```yaml
resources:
  repositories:
    - repository: spectra
      type: github
      name: spectra/spectra
      ref: main

extends:
  template: integrations/azure-pipelines/spectra-pipeline.yml@spectra
  parameters:
    markdownFile: 'docs/user-stories.md'
    epicKey: 'PROJ-123'
    tracker: 'jira'
```

## Configuration

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `markdownFile` | Yes | | Path to markdown file |
| `epicKey` | No | | Epic key to sync |
| `tracker` | No | `jira` | Tracker type |
| `dryRun` | No | `false` | Preview mode |
| `execute` | No | `true` | Execute changes |
| `phase` | No | `all` | Sync phase |
| `incremental` | No | `false` | Incremental sync |
| `multiEpic` | No | `false` | Multi-epic mode |
| `verbose` | No | `false` | Verbose output |

### Variable Groups

Create a variable group `spectra-credentials`:

1. Go to **Pipelines > Library > Variable groups**
2. Create group `spectra-credentials`
3. Add variables:
   - `JIRA_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN` (secret)

Reference in pipeline:

```yaml
variables:
  - group: spectra-credentials
```

## Examples

### Multi-Stage Pipeline

```yaml
trigger:
  - main
  - develop

pool:
  vmImage: 'ubuntu-latest'

variables:
  - group: spectra-credentials

stages:
  - stage: Validate
    jobs:
      - job: ValidateMarkdown
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'
          - script: |
              pip install spectra
              spectra validate --markdown docs/user-stories.md
            displayName: 'Validate Specs'

  - stage: Preview
    dependsOn: Validate
    condition: and(succeeded(), eq(variables['Build.Reason'], 'PullRequest'))
    jobs:
      - job: PreviewSync
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '3.11'
          - script: |
              pip install spectra
              spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY)
            displayName: 'Preview Sync'
            env:
              JIRA_URL: $(JIRA_URL)
              JIRA_EMAIL: $(JIRA_EMAIL)
              JIRA_API_TOKEN: $(JIRA_API_TOKEN)

  - stage: Deploy
    dependsOn: Validate
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: SyncToJira
        environment: 'production'
        strategy:
          runOnce:
            deploy:
              steps:
                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: '3.11'
                - script: |
                    pip install spectra
                    spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY) --execute --no-confirm
                  displayName: 'Sync to Jira'
                  env:
                    JIRA_URL: $(JIRA_URL)
                    JIRA_EMAIL: $(JIRA_EMAIL)
                    JIRA_API_TOKEN: $(JIRA_API_TOKEN)
```

### Scheduled Sync

```yaml
schedules:
  - cron: '0 6 * * *'
    displayName: 'Daily sync at 6 AM'
    branches:
      include:
        - main
    always: true

trigger: none

pool:
  vmImage: 'ubuntu-latest'

variables:
  - group: spectra-credentials

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'
  - script: |
      pip install spectra
      spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY) --incremental --execute --no-confirm
    displayName: 'Incremental Sync'
    env:
      JIRA_URL: $(JIRA_URL)
      JIRA_EMAIL: $(JIRA_EMAIL)
      JIRA_API_TOKEN: $(JIRA_API_TOKEN)
```

### Azure DevOps Work Items

```yaml
variables:
  - group: spectra-azure-devops

steps:
  - script: |
      pip install spectra
      spectra sync --markdown docs/user-stories.md --tracker azure-devops --execute --no-confirm
    displayName: 'Sync to Azure DevOps'
    env:
      AZURE_PAT: $(AZURE_PAT)
      AZURE_ORGANIZATION: $(AZURE_ORGANIZATION)
      AZURE_PROJECT: $(AZURE_PROJECT)
```

### Pull Request Validation

```yaml
trigger: none

pr:
  branches:
    include:
      - main
  paths:
    include:
      - docs/*.md

pool:
  vmImage: 'ubuntu-latest'

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - script: pip install spectra
    displayName: 'Install Spectra'

  - script: spectra validate --markdown docs/user-stories.md
    displayName: 'Validate Markdown'

  - script: spectra diff --markdown docs/user-stories.md --epic $(EPIC_KEY)
    displayName: 'Show Changes'
    env:
      JIRA_URL: $(JIRA_URL)
      JIRA_EMAIL: $(JIRA_EMAIL)
      JIRA_API_TOKEN: $(JIRA_API_TOKEN)
```

### Export Artifacts

```yaml
steps:
  - script: |
      pip install spectra
      spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY) --export sync-results.json --execute --no-confirm
    displayName: 'Sync with Export'
    env:
      JIRA_URL: $(JIRA_URL)
      JIRA_EMAIL: $(JIRA_EMAIL)
      JIRA_API_TOKEN: $(JIRA_API_TOKEN)

  - publish: sync-results.json
    artifact: SyncResults
    condition: always()
```

## Template Reference

### spectra-sync.yml

```yaml
parameters:
  - name: markdownFile
    type: string
  - name: epicKey
    type: string
    default: ''
  - name: tracker
    type: string
    default: 'jira'
  - name: dryRun
    type: boolean
    default: false
  - name: incremental
    type: boolean
    default: false

steps:
  - template: templates/spectra-sync.yml
    parameters:
      markdownFile: ${{ parameters.markdownFile }}
      epicKey: ${{ parameters.epicKey }}
      tracker: ${{ parameters.tracker }}
      dryRun: ${{ parameters.dryRun }}
      incremental: ${{ parameters.incremental }}
```

## Troubleshooting

### Common Issues

1. **Variable not found**: Ensure variable group is linked to pipeline
2. **Permission denied**: Check service connection permissions
3. **File not found**: Use `$(Build.SourcesDirectory)` for paths

### Debug Mode

```yaml
variables:
  system.debug: true

steps:
  - script: |
      pip install spectra
      spectra sync --markdown docs/user-stories.md --epic $(EPIC_KEY) --verbose
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
