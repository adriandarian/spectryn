# md2jira GitHub Action

Sync markdown documentation to Jira issues, epics, and subtasks directly from your CI/CD pipeline.

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-md2jira--sync-blue?logo=github)](https://github.com/marketplace/actions/md2jira-sync)

## Features

- 🚀 **Automatic sync** - Keep Jira in sync with your documentation
- 📝 **Markdown-first** - Define epics and stories in markdown
- 🔄 **Bidirectional** - Push to Jira or pull from Jira
- 📊 **Multi-epic** - Sync multiple epics from one file
- ⚡ **Incremental** - Only sync what changed
- 💾 **Backup** - Automatic backups before sync
- 📤 **Export** - Get JSON results for further processing

## Quick Start

```yaml
name: Sync to Jira

on:
  push:
    branches: [main]
    paths:
      - 'docs/EPIC.md'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync to Jira
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/EPIC.md
          epic-key: PROJ-123
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
```

## Inputs

### Required

| Input | Description |
|-------|-------------|
| `markdown-file` | Path to the markdown file to sync |
| `epic-key` | Jira epic key (e.g., `PROJ-123`) |
| `jira-url` | Jira instance URL |
| `jira-email` | Jira account email |
| `jira-api-token` | Jira API token |

### Optional

| Input | Default | Description |
|-------|---------|-------------|
| `execute` | `true` | Execute changes (set to `false` for dry-run) |
| `dry-run` | `false` | Run without making changes |
| `phase` | `all` | Sync phase: `all`, `descriptions`, `subtasks`, `comments`, `statuses` |
| `incremental` | `false` | Only sync changed stories |
| `multi-epic` | `false` | Enable multi-epic mode |
| `epic-filter` | `''` | Comma-separated epic keys to sync |
| `pull` | `false` | Pull from Jira (reverse sync) |
| `pull-output` | `''` | Output file for pull mode |
| `backup` | `true` | Create backup before sync |
| `verbose` | `false` | Enable verbose output |
| `export-results` | `''` | Export results to JSON file |

## Outputs

| Output | Description |
|--------|-------------|
| `success` | Whether the sync was successful |
| `stories-matched` | Number of stories matched |
| `stories-updated` | Number of stories updated |
| `subtasks-created` | Number of subtasks created |
| `subtasks-updated` | Number of subtasks updated |
| `comments-added` | Number of comments added |
| `errors` | Number of errors |
| `result-file` | Path to exported results JSON |

## Examples

### Dry-run on Pull Requests

Preview changes without applying them:

```yaml
name: Preview Jira Sync

on:
  pull_request:
    paths:
      - 'docs/**/*.md'

jobs:
  preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Preview Sync
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/EPIC.md
          epic-key: PROJ-123
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
          execute: false
          
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '📋 Jira sync preview completed. Check the action logs for details.'
            })
```

### Sync on Merge to Main

Automatically sync when changes are merged:

```yaml
name: Sync to Jira

on:
  push:
    branches: [main]
    paths:
      - 'docs/epics/**/*.md'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync to Jira
        id: sync
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/epics/Q1-2024.md
          epic-key: PROJ-100
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
          incremental: true
          
      - name: Report Results
        run: |
          echo "Stories matched: ${{ steps.sync.outputs.stories-matched }}"
          echo "Stories updated: ${{ steps.sync.outputs.stories-updated }}"
          echo "Subtasks created: ${{ steps.sync.outputs.subtasks-created }}"
```

### Multi-Epic Sync

Sync multiple epics from a single roadmap file:

```yaml
name: Sync Roadmap

on:
  push:
    branches: [main]
    paths:
      - 'docs/ROADMAP.md'

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync All Epics
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/ROADMAP.md
          multi-epic: true
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
```

### Pull from Jira (Reverse Sync)

Update markdown from Jira changes:

```yaml
name: Pull from Jira

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM
  workflow_dispatch:

jobs:
  pull:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Pull from Jira
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/EPIC.md
          epic-key: PROJ-123
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
          pull: true
          pull-output: docs/EPIC.md
          
      - name: Commit Changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add docs/EPIC.md
          git diff --staged --quiet || git commit -m "chore: sync from Jira"
          git push
```

### Export Results for Further Processing

```yaml
name: Sync with Export

on:
  push:
    branches: [main]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync to Jira
        id: sync
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/EPIC.md
          epic-key: PROJ-123
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
          export-results: sync-results.json
          
      - name: Upload Results
        uses: actions/upload-artifact@v4
        with:
          name: sync-results
          path: sync-results.json
          
      - name: Process Results
        run: |
          cat sync-results.json | jq '.stats'
```

### Scheduled Sync

Keep Jira in sync on a schedule:

```yaml
name: Scheduled Jira Sync

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync to Jira
        uses: md2jira/md2jira-action@v1
        with:
          markdown-file: docs/EPIC.md
          epic-key: PROJ-123
          jira-url: ${{ secrets.JIRA_URL }}
          jira-email: ${{ secrets.JIRA_EMAIL }}
          jira-api-token: ${{ secrets.JIRA_API_TOKEN }}
          incremental: true
```

## Setting Up Secrets

1. Go to your repository **Settings** → **Secrets and variables** → **Actions**
2. Add the following secrets:
   - `JIRA_URL`: Your Jira instance URL (e.g., `https://company.atlassian.net`)
   - `JIRA_EMAIL`: Your Atlassian account email
   - `JIRA_API_TOKEN`: API token from [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

## Markdown Format

The action expects markdown files in the md2jira format:

```markdown
# Epic: PROJ-123 - Authentication System

## US-001: User Login

**As a** user
**I want** to login to the system
**So that** I can access my account

### Acceptance Criteria
- [ ] User can enter email and password
- [ ] System validates credentials
- [ ] Error shown for invalid credentials

### Subtasks
- [ ] Backend: Implement auth API (3 pts)
- [ ] Frontend: Create login form (2 pts)
- [ ] Testing: Write integration tests (2 pts)
```

See the [md2jira documentation](https://github.com/md2jira/md2jira) for the complete format specification.

## Troubleshooting

### Authentication Errors

- Verify your `JIRA_EMAIL` matches your Atlassian account
- Ensure the API token is valid and not expired
- Check that your account has access to the project

### Permission Errors

- Verify your Jira account has permission to edit issues in the project
- Check that the epic exists and you have access to it

### Sync Failures

- Enable `verbose: true` for detailed logs
- Use `dry-run: true` to preview changes first
- Check that the markdown format is correct

## License

MIT License - see [LICENSE](../LICENSE)

