# Spectra Bitbucket Pipelines Template

Bitbucket Pipelines template for syncing markdown specifications to issue trackers.

## Features

- **Multiple Trackers** - Support for Jira, GitHub, Azure DevOps, Linear, and more
- **Flexible Modes** - Dry-run, execute, pull (reverse sync)
- **Multi-Epic Support** - Sync multiple epics from one file
- **Incremental Sync** - Only sync changed stories
- **Caching** - Cache pip packages for faster builds
- **Artifacts** - Export sync results as artifacts

## Quick Start

### Basic Setup

Add to your `bitbucket-pipelines.yml`:

```yaml
image: python:3.11-slim

definitions:
  caches:
    spectra: ~/.cache/pip

pipelines:
  default:
    - step:
        name: Sync to Jira
        caches:
          - spectra
        script:
          - pip install spectra
          - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY --execute --no-confirm
```

### Using the Pipe

```yaml
pipelines:
  default:
    - step:
        name: Sync to Jira
        script:
          - pipe: spectra/spectra-sync:1.0.0
            variables:
              MARKDOWN_FILE: "docs/user-stories.md"
              EPIC_KEY: "PROJ-123"
              JIRA_URL: $JIRA_URL
              JIRA_EMAIL: $JIRA_EMAIL
              JIRA_API_TOKEN: $JIRA_API_TOKEN
```

## Configuration

### Required Variables

| Variable | Description |
|----------|-------------|
| `MARKDOWN_FILE` | Path to the markdown file to sync |
| `EPIC_KEY` | Jira epic key (e.g., `PROJ-123`) |
| `JIRA_URL` | Jira instance URL |
| `JIRA_EMAIL` | Jira account email |
| `JIRA_API_TOKEN` | Jira API token |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `false` | Run without making changes |
| `EXECUTE` | `true` | Execute changes |
| `PHASE` | `all` | Sync phase |
| `INCREMENTAL` | `false` | Only sync changed stories |
| `MULTI_EPIC` | `false` | Enable multi-epic mode |
| `VERBOSE` | `false` | Enable verbose output |

## Examples

### Sync on Push to Main

```yaml
pipelines:
  branches:
    main:
      - step:
          name: Sync to Jira
          script:
            - pip install spectra
            - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY --execute --no-confirm
```

### Dry-Run on Pull Requests

```yaml
pipelines:
  pull-requests:
    '**':
      - step:
          name: Preview Sync
          script:
            - pip install spectra
            - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY
```

### Scheduled Sync

```yaml
pipelines:
  custom:
    scheduled-sync:
      - step:
          name: Scheduled Sync
          script:
            - pip install spectra
            - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY --execute --incremental --no-confirm
```

### Multi-Tracker Setup

```yaml
pipelines:
  branches:
    main:
      - parallel:
          - step:
              name: Sync to Jira
              script:
                - pip install spectra
                - spectra sync --markdown docs/stories.md --epic $JIRA_EPIC --tracker jira --execute --no-confirm
          - step:
              name: Sync to GitHub
              script:
                - pip install spectra
                - spectra sync --markdown docs/stories.md --tracker github --execute --no-confirm
```

### With Artifacts

```yaml
pipelines:
  default:
    - step:
        name: Sync with Export
        script:
          - pip install spectra
          - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY --execute --export sync-results.json --no-confirm
        artifacts:
          - sync-results.json
          - backups/**
```

## Setting Up Repository Variables

1. Go to **Repository Settings > Repository variables**
2. Add the following variables:
   - `JIRA_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN` (secured)
   - `EPIC_KEY`

## Full Example

```yaml
image: python:3.11-slim

definitions:
  caches:
    spectra: ~/.cache/pip

  steps:
    - step: &sync-step
        name: Spectra Sync
        caches:
          - spectra
        script:
          - pip install spectra
          - |
            spectra sync \
              --markdown $MARKDOWN_FILE \
              --epic $EPIC_KEY \
              --tracker jira \
              --execute \
              --no-confirm \
              ${INCREMENTAL:+--incremental} \
              ${VERBOSE:+--verbose}

pipelines:
  default:
    - step:
        <<: *sync-step
        name: Preview Sync (Dry-run)
        script:
          - pip install spectra
          - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY

  branches:
    main:
      - step:
          <<: *sync-step
          deployment: production

  pull-requests:
    '**':
      - step:
          name: Validate Markdown
          script:
            - pip install spectra
            - spectra validate --markdown docs/user-stories.md

  custom:
    full-sync:
      - step:
          <<: *sync-step
          name: Full Sync
          script:
            - pip install spectra
            - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY --execute --no-confirm
```

## Troubleshooting

### Authentication Issues

Ensure repository variables are set:
```bash
# Test locally
export JIRA_URL="https://company.atlassian.net"
export JIRA_EMAIL="user@company.com"
export JIRA_API_TOKEN="your-token"
spectra sync --markdown docs/stories.md --epic PROJ-123
```

### File Not Found

Use relative paths from repository root:
```yaml
script:
  - ls -la docs/  # Debug: list files
  - spectra sync --markdown docs/user-stories.md --epic $EPIC_KEY
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
