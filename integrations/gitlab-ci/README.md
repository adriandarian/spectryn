# Spectra GitLab CI Template

GitLab CI/CD template for syncing markdown specifications to issue trackers.

## Features

- **Multiple Trackers** - Support for Jira, GitHub, Azure DevOps, Linear, and more
- **Flexible Modes** - Dry-run, execute, pull (reverse sync)
- **Multi-Epic Support** - Sync multiple epics from one file
- **Incremental Sync** - Only sync changed stories
- **Caching** - Cache pip packages for faster builds
- **Artifacts** - Export sync results as artifacts

## Quick Start

### Include the Template

Add to your `.gitlab-ci.yml`:

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/spectryn/spectryn/main/integrations/gitlab-ci/.spectryn-ci.yml'

spectryn-sync:
  extends: .spectryn-sync
  variables:
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
    JIRA_URL: "https://company.atlassian.net"
    JIRA_EMAIL: $JIRA_EMAIL  # From CI/CD variables
    JIRA_API_TOKEN: $JIRA_API_TOKEN  # From CI/CD variables
```

### Local Template

Copy `.spectryn-ci.yml` to your repository:

```yaml
include:
  - local: '.gitlab/spectryn-ci.yml'

spectryn-sync:
  extends: .spectryn-sync
  variables:
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
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
| `PHASE` | `all` | Sync phase: `all`, `descriptions`, `subtasks`, `comments`, `statuses` |
| `INCREMENTAL` | `false` | Only sync changed stories |
| `MULTI_EPIC` | `false` | Enable multi-epic mode |
| `EPIC_FILTER` | | Comma-separated epic keys to sync |
| `BACKUP` | `true` | Create backup before sync |
| `VERBOSE` | `false` | Enable verbose output |
| `EXPORT_RESULTS` | | Export results to JSON file |

### Tracker-Specific Variables

#### GitHub Issues

```yaml
variables:
  TRACKER: "github"
  GITHUB_TOKEN: $GITHUB_TOKEN
  GITHUB_OWNER: "myorg"
  GITHUB_REPO: "myrepo"
```

#### Azure DevOps

```yaml
variables:
  TRACKER: "azure-devops"
  AZURE_PAT: $AZURE_PAT
  AZURE_ORGANIZATION: "myorg"
  AZURE_PROJECT: "myproject"
```

#### Linear

```yaml
variables:
  TRACKER: "linear"
  LINEAR_API_KEY: $LINEAR_API_KEY
  LINEAR_TEAM_ID: "TEAM-123"
```

## Examples

### Basic Sync on Push

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/spectryn/spectryn/main/integrations/gitlab-ci/.spectryn-ci.yml'

spectryn-sync:
  extends: .spectryn-sync
  only:
    - main
  variables:
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
```

### Dry-Run on Merge Requests

```yaml
spectryn-preview:
  extends: .spectryn-sync
  only:
    - merge_requests
  variables:
    DRY_RUN: "true"
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
```

### Scheduled Sync

```yaml
spectryn-scheduled:
  extends: .spectryn-sync
  only:
    - schedules
  variables:
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
    INCREMENTAL: "true"
```

### Multi-Epic Sync

```yaml
spectryn-multi:
  extends: .spectryn-sync
  variables:
    MARKDOWN_FILE: "docs/all-epics.md"
    MULTI_EPIC: "true"
    EPIC_FILTER: "PROJ-100,PROJ-101,PROJ-102"
```

### Pull (Reverse Sync)

```yaml
spectryn-pull:
  extends: .spectryn-pull
  only:
    - schedules
  variables:
    EPIC_KEY: "PROJ-123"
    OUTPUT_FILE: "docs/user-stories.md"
  artifacts:
    paths:
      - docs/user-stories.md
    when: always
```

### Export Results

```yaml
spectryn-with-export:
  extends: .spectryn-sync
  variables:
    MARKDOWN_FILE: "docs/user-stories.md"
    EPIC_KEY: "PROJ-123"
    EXPORT_RESULTS: "sync-results.json"
  artifacts:
    paths:
      - sync-results.json
    reports:
      dotenv: sync-results.env
```

## Setting Up CI/CD Variables

1. Go to **Settings > CI/CD > Variables**
2. Add the following variables:
   - `JIRA_EMAIL` (protected)
   - `JIRA_API_TOKEN` (protected, masked)
   - Any tracker-specific credentials

## Caching

The template automatically caches pip packages:

```yaml
cache:
  key: spectryn-${CI_COMMIT_REF_SLUG}
  paths:
    - .cache/pip
```

## Artifacts

Sync results can be exported as artifacts:

```yaml
artifacts:
  paths:
    - sync-results.json
    - backups/
  expire_in: 7 days
```

## Troubleshooting

### Common Issues

1. **Authentication failed**: Check that CI/CD variables are set correctly
2. **File not found**: Ensure the markdown file path is correct
3. **Epic not found**: Verify the epic key exists in the tracker

### Debug Mode

Enable verbose output:

```yaml
variables:
  VERBOSE: "true"
```

## License

MIT License - see [LICENSE](../../LICENSE) for details.
