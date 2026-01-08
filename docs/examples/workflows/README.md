# Example GitHub Workflows

This directory contains example GitHub Actions workflows demonstrating how to use the Spectra GitHub Action in your own repositories.

## Available Examples

### [spectryn-sync.yml](spectryn-sync.yml)
**Sync Documentation to Jira**

This workflow demonstrates:
- Syncing markdown documentation to Jira on push to main
- Previewing sync changes on pull requests with a PR comment
- Manual dry-run trigger via `workflow_dispatch`
- Incremental sync with result export

### [spectryn-pull.yml](spectryn-pull.yml)
**Pull from Jira to Markdown**

This workflow demonstrates:
- Scheduled weekly sync from Jira (every Monday at 9 AM UTC)
- Automatic PR creation when Jira content has changed
- Manual trigger via `workflow_dispatch`

## Usage

1. Copy the desired workflow file to your repository's `.github/workflows/` directory
2. Configure the required secrets in your repository settings:
   - `JIRA_URL` - Your Jira instance URL
   - `JIRA_EMAIL` - Your Jira account email
   - `JIRA_API_TOKEN` - Your Jira API token
3. Update the workflow to match your epic key and markdown file paths
4. Commit and push the workflow

## Required Secrets

| Secret | Description |
|--------|-------------|
| `JIRA_URL` | The URL of your Jira instance (e.g., `https://your-company.atlassian.net`) |
| `JIRA_EMAIL` | Email address associated with your Jira account |
| `JIRA_API_TOKEN` | API token generated from your Atlassian account settings |

## Customization

Each workflow can be customized by modifying:
- **`epic-key`**: Change to your Jira epic key (e.g., `MYPROJ-456`)
- **`markdown-file`**: Path to your markdown specification file
- **Schedule**: Modify the cron expression for scheduled syncs
- **Branch patterns**: Adjust triggers for your branching strategy
