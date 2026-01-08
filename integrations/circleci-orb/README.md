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
  spectryn: spectryn/spectryn@1.0.0

workflows:
  sync:
    jobs:
      - spectryn/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
```

### Development Version

```yaml
version: 2.1

orbs:
  spectryn:
    commands:
      # ... inline orb definition
```

## Quick Start

### Basic Sync

```yaml
version: 2.1

orbs:
  spectryn: spectryn/spectryn@1.0.0

workflows:
  main:
    jobs:
      - spectryn/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          context: jira-credentials
```

### With Validation

```yaml
workflows:
  main:
    jobs:
      - spectryn/validate:
          markdown-file: docs/user-stories.md
      - spectryn/sync:
          requires:
            - spectryn/validate
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

#### spectryn/sync

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

#### spectryn/validate

| Parameter | Required | Description |
|-----------|----------|-------------|
| `markdown-file` | Yes | Path to markdown file |

#### spectryn/pull

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
  spectryn: spectryn/spectryn@1.0.0

workflows:
  sync-workflow:
    jobs:
      # Validate on all branches
      - spectryn/validate:
          markdown-file: docs/user-stories.md
          filters:
            branches:
              only: /.*/

      # Preview on feature branches
      - spectryn/sync:
          name: preview
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          dry-run: true
          requires:
            - spectryn/validate
          filters:
            branches:
              ignore: main
          context: jira-credentials

      # Execute on main
      - spectryn/sync:
          name: deploy
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          execute: true
          requires:
            - spectryn/validate
          filters:
            branches:
              only: main
          context: jira-credentials
```

### Scheduled Sync

```yaml
version: 2.1

orbs:
  spectryn: spectryn/spectryn@1.0.0

workflows:
  nightly-sync:
    triggers:
      - schedule:
          cron: "0 6 * * *"
          filters:
            branches:
              only: main
    jobs:
      - spectryn/sync:
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          incremental: true
          context: jira-credentials
```

### Multi-Tracker Sync

```yaml
version: 2.1

orbs:
  spectryn: spectryn/spectryn@1.0.0

workflows:
  multi-tracker:
    jobs:
      - spectryn/sync:
          name: sync-jira
          markdown-file: docs/user-stories.md
          epic-key: PROJ-123
          tracker: jira
          context: jira-credentials

      - spectryn/sync:
          name: sync-github
          markdown-file: docs/user-stories.md
          tracker: github
          context: github-credentials
```

### Using Commands Directly

```yaml
version: 2.1

orbs:
  spectryn: spectryn/spectryn@1.0.0

jobs:
  custom-sync:
    executor: spectryn/python
    steps:
      - checkout
      - spectryn/install
      - spectryn/sync-command:
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
      - spectryn/sync:
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
  - spectryn/sync:
      context: jira-credentials
```

## Orb Commands

### spectryn/install

Install spectryn CLI:

```yaml
steps:
  - spectryn/install:
      version: latest
```

### spectryn/sync-command

Run sync:

```yaml
steps:
  - spectryn/sync-command:
      markdown-file: docs/stories.md
      epic-key: PROJ-123
```

### spectryn/validate-command

Validate markdown:

```yaml
steps:
  - spectryn/validate-command:
      markdown-file: docs/stories.md
```

### spectryn/pull-command

Pull from tracker:

```yaml
steps:
  - spectryn/pull-command:
      epic-key: PROJ-123
      output-file: docs/stories.md
```

## Troubleshooting

### Missing Credentials

Ensure context is attached to job:

```yaml
jobs:
  - spectryn/sync:
      context: jira-credentials  # Don't forget this!
```

### Python Version

Use specific Python version:

```yaml
jobs:
  custom:
    executor:
      name: spectryn/python
      python-version: "3.11"
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
