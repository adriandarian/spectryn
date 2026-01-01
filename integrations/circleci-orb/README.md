# Spectra CircleCI Orb

CircleCI Orb for syncing markdown specifications to issue trackers.

## Features

- **Reusable Commands** - Pre-built commands for common operations
- **Executors** - Python-based execution environment
- **Jobs** - Ready-to-use jobs for sync, validate, pull
- **Multiple Trackers** - Jira, GitHub, Azure DevOps, Linear, and more
- **Caching** - Automatic pip caching for faster builds

## Installation

### From CircleCI Orb Registry

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

workflows:
  sync:
    jobs:
      - spectra/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
```

### Development Version

```yaml
version: 2.1

orbs:
  spectra:
    commands:
      # ... inline orb definition
```

## Quick Start

### Basic Sync

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

workflows:
  main:
    jobs:
      - spectra/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          context: jira-credentials
```

### With Validation

```yaml
workflows:
  main:
    jobs:
      - spectra/validate:
          markdown-file: docs/user-stories.md
      - spectra/sync:
          requires:
            - spectra/validate
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
```

## Configuration

### Environment Variables

Set these in your CircleCI project settings or context:

| Variable | Description |
|----------|-------------|
| `JIRA_URL` | Jira instance URL |
| `JIRA_EMAIL` | Jira account email |
| `JIRA_API_TOKEN` | Jira API token |
| `GITHUB_TOKEN` | GitHub personal access token |
| `AZURE_PAT` | Azure DevOps PAT |
| `LINEAR_API_KEY` | Linear API key |

### Job Parameters

#### spectra/sync

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `markdown-file` | Yes | | Path to markdown file |
| `epic-key` | No | | Epic key to sync |
| `tracker` | No | `jira` | Tracker type |
| `dry-run` | No | `false` | Preview mode |
| `execute` | No | `true` | Execute changes |
| `phase` | No | `all` | Sync phase |
| `incremental` | No | `false` | Incremental sync |
| `multi-epic` | No | `false` | Multi-epic mode |
| `verbose` | No | `false` | Verbose output |
| `export-results` | No | | Export file path |

#### spectra/validate

| Parameter | Required | Description |
|-----------|----------|-------------|
| `markdown-file` | Yes | Path to markdown file |

#### spectra/pull

| Parameter | Required | Description |
|-----------|----------|-------------|
| `epic-key` | Yes | Epic key to pull |
| `output-file` | Yes | Output markdown file |
| `tracker` | No | Tracker type |

## Examples

### Multi-Branch Workflow

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

workflows:
  sync-workflow:
    jobs:
      # Validate on all branches
      - spectra/validate:
          markdown-file: docs/user-stories.md
          filters:
            branches:
              only: /.*/

      # Preview on feature branches
      - spectra/sync:
          name: preview
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          dry-run: true
          requires:
            - spectra/validate
          filters:
            branches:
              ignore: main
          context: jira-credentials

      # Execute on main
      - spectra/sync:
          name: deploy
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          execute: true
          requires:
            - spectra/validate
          filters:
            branches:
              only: main
          context: jira-credentials
```

### Scheduled Sync

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

workflows:
  nightly-sync:
    triggers:
      - schedule:
          cron: "0 6 * * *"
          filters:
            branches:
              only: main
    jobs:
      - spectra/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          incremental: true
          context: jira-credentials
```

### Multi-Tracker Sync

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

workflows:
  multi-tracker:
    jobs:
      - spectra/sync:
          name: sync-jira
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          tracker: jira
          context: jira-credentials

      - spectra/sync:
          name: sync-github
          markdown-file: docs/user-stories.md
          tracker: github
          context: github-credentials
```

### Using Commands Directly

```yaml
version: 2.1

orbs:
  spectra: spectra/spectra@1.0.0

jobs:
  custom-sync:
    executor: spectra/python
    steps:
      - checkout
      - spectra/install
      - spectra/sync-command:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          execute: true
      - store_artifacts:
          path: sync-results.json

workflows:
  main:
    jobs:
      - custom-sync:
          context: jira-credentials
```

### With Artifacts

```yaml
workflows:
  main:
    jobs:
      - spectra/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          export-results: sync-results.json
          context: jira-credentials
```

## Contexts

Create a context for credentials:

1. Go to **Organization Settings > Contexts**
2. Create context `jira-credentials`
3. Add environment variables:
   - `JIRA_URL`
   - `JIRA_EMAIL`
   - `JIRA_API_TOKEN`

Reference in workflow:

```yaml
jobs:
  - spectra/sync:
      context: jira-credentials
```

## Orb Commands

### spectra/install

Install spectra CLI:

```yaml
steps:
  - spectra/install:
      version: latest
```

### spectra/sync-command

Run sync:

```yaml
steps:
  - spectra/sync-command:
      markdown-file: docs/stories.md
      epic-key: PROJ-123
```

### spectra/validate-command

Validate markdown:

```yaml
steps:
  - spectra/validate-command:
      markdown-file: docs/stories.md
```

### spectra/pull-command

Pull from tracker:

```yaml
steps:
  - spectra/pull-command:
      epic-key: PROJ-123
      output-file: docs/stories.md
```

## Troubleshooting

### Missing Credentials

Ensure context is attached to job:

```yaml
jobs:
  - spectra/sync:
      context: jira-credentials  # Don't forget this!
```

### Python Version

Use specific Python version:

```yaml
jobs:
  custom:
    executor:
      name: spectra/python
      python-version: "3.11"
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
