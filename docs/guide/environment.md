# Environment Variables

spectryn uses environment variables for sensitive configuration like API credentials. This page covers all supported variables and best practices.

## Tracker Credentials

### Jira

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_URL` | Your Jira instance URL | `https://company.atlassian.net` |
| `JIRA_EMAIL` | Your Jira account email | `you@company.com` |
| `JIRA_API_TOKEN` | Jira API token | `ATATT3xFf...` |
| `JIRA_PROJECT` | Default project key (optional) | `PROJ` |

### GitHub

| Variable | Description | Example |
|----------|-------------|---------|
| `GITHUB_TOKEN` | Personal Access Token | `ghp_xxxx...` |
| `GITHUB_OWNER` | Repository owner | `your-org` |
| `GITHUB_REPO` | Repository name | `your-repo` |
| `GITHUB_BASE_URL` | API URL (optional) | `https://api.github.com` |
| `GITHUB_PROJECT_NUMBER` | Projects v2 number (optional) | `1` |

### GitLab

| Variable | Description | Example |
|----------|-------------|---------|
| `GITLAB_TOKEN` | Personal Access Token | `glpat-xxxx...` |
| `GITLAB_PROJECT_ID` | Project ID or path | `12345` or `group/project` |
| `GITLAB_BASE_URL` | API URL (optional) | `https://gitlab.com/api/v4` |
| `GITLAB_GROUP_ID` | Group ID for epics (optional) | `mygroup` |

### Azure DevOps

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_DEVOPS_ORG` | Organization name | `your-org` |
| `AZURE_DEVOPS_PROJECT` | Project name | `your-project` |
| `AZURE_DEVOPS_PAT` | Personal Access Token | `xxxx...` |
| `AZURE_DEVOPS_BASE_URL` | Base URL (optional) | `https://dev.azure.com` |

### Linear

| Variable | Description | Example |
|----------|-------------|---------|
| `LINEAR_API_KEY` | API key | `lin_api_xxxx...` |
| `LINEAR_TEAM_ID` | Team key or UUID | `ENG` |
| `LINEAR_PROJECT_ID` | Project UUID (optional) | `uuid...` |

### Asana

| Variable | Description | Example |
|----------|-------------|---------|
| `ASANA_ACCESS_TOKEN` | Personal Access Token | `1/xxxx...` |
| `ASANA_WORKSPACE_ID` | Workspace GID | `1234567890` |
| `ASANA_PROJECT_ID` | Project GID | `0987654321` |

### Trello

| Variable | Description | Example |
|----------|-------------|---------|
| `TRELLO_API_KEY` | API key | `xxxx...` |
| `TRELLO_API_TOKEN` | API token | `xxxx...` |
| `TRELLO_BOARD_ID` | Board ID | `abc123def` |

### ClickUp

| Variable | Description | Example |
|----------|-------------|---------|
| `CLICKUP_API_TOKEN` | API token | `pk_xxxx...` |
| `CLICKUP_LIST_ID` | List ID (optional) | `123456` |
| `CLICKUP_SPACE_ID` | Space ID (optional) | `789012` |

### Shortcut

| Variable | Description | Example |
|----------|-------------|---------|
| `SHORTCUT_API_TOKEN` | API token | `xxxx...` |
| `SHORTCUT_WORKSPACE_ID` | Workspace UUID or slug | `my-workspace` |

### Monday.com

| Variable | Description | Example |
|----------|-------------|---------|
| `MONDAY_API_TOKEN` | API token (v2) | `xxxx...` |
| `MONDAY_BOARD_ID` | Board ID | `1234567890` |
| `MONDAY_WORKSPACE_ID` | Workspace ID (optional) | `9876543` |

### Plane

| Variable | Description | Example |
|----------|-------------|---------|
| `PLANE_API_TOKEN` | API token | `xxxx...` |
| `PLANE_WORKSPACE_SLUG` | Workspace slug | `my-workspace` |
| `PLANE_PROJECT_ID` | Project UUID | `uuid...` |
| `PLANE_API_URL` | API URL (optional) | `https://app.plane.so/api/v1` |

### YouTrack

| Variable | Description | Example |
|----------|-------------|---------|
| `YOUTRACK_URL` | YouTrack URL | `https://youtrack.mycompany.com` |
| `YOUTRACK_TOKEN` | Permanent token | `perm:xxxx...` |
| `YOUTRACK_PROJECT_ID` | Project ID | `PROJ` |

### Bitbucket

| Variable | Description | Example |
|----------|-------------|---------|
| `BITBUCKET_USERNAME` | Username | `your-username` |
| `BITBUCKET_APP_PASSWORD` | App Password | `xxxx...` |
| `BITBUCKET_WORKSPACE` | Workspace slug | `my-workspace` |
| `BITBUCKET_REPO` | Repository slug | `my-repo` |

### Basecamp

| Variable | Description | Example |
|----------|-------------|---------|
| `BASECAMP_ACCESS_TOKEN` | OAuth access token | `xxxx...` |
| `BASECAMP_ACCOUNT_ID` | Account ID | `1234567` |
| `BASECAMP_PROJECT_ID` | Project ID | `7654321` |

### Pivotal Tracker

| Variable | Description | Example |
|----------|-------------|---------|
| `PIVOTAL_API_TOKEN` | API token | `xxxx...` |
| `PIVOTAL_PROJECT_ID` | Project ID | `1234567` |

## General Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SPECTRA_VERBOSE` | Enable verbose output | `false` |
| `SPECTRA_LOG_LEVEL` | Logging level | `INFO` |
| `SPECTRA_NO_COLOR` | Disable colored output | `false` |
| `SPECTRA_CONFIG` | Config file path | `.spectryn.yaml` |

## Setting Environment Variables

### Temporary (Current Session)

::: code-group

```bash [Bash/Zsh]
export GITHUB_TOKEN=ghp_your-token
export GITHUB_OWNER=your-org
export GITHUB_REPO=your-repo
```

```fish [Fish]
set -x GITHUB_TOKEN ghp_your-token
set -x GITHUB_OWNER your-org
set -x GITHUB_REPO your-repo
```

```powershell [PowerShell]
$env:GITHUB_TOKEN = "ghp_your-token"
$env:GITHUB_OWNER = "your-org"
$env:GITHUB_REPO = "your-repo"
```

:::

### Permanent (.env File)

Create a `.env` file in your project directory:

```bash
# .env - Choose your tracker

# GitHub
GITHUB_TOKEN=ghp_your-token
GITHUB_OWNER=your-org
GITHUB_REPO=your-repo

# Or Jira
# JIRA_URL=https://your-company.atlassian.net
# JIRA_EMAIL=your.email@company.com
# JIRA_API_TOKEN=your-api-token

# Or Linear
# LINEAR_API_KEY=lin_api_your-key
# LINEAR_TEAM_ID=ENG

# General settings
SPECTRA_VERBOSE=true
```

spectryn automatically loads `.env` files from:
1. Current working directory
2. Home directory (`~/.env`)

::: danger Security Warning
**Never commit `.env` files to version control!**

Add to your `.gitignore`:
```bash
.env
.env.local
.env.*.local
```
:::

## Getting API Tokens

### Jira

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a descriptive name (e.g., "spectryn CLI")
4. Copy the token immediately

### GitHub

1. Go to **Settings** → **Developer settings** → **Personal access tokens**
2. Click **Generate new token (classic)**
3. Select scopes: `repo`, `project` (if using Projects)
4. Copy the token (starts with `ghp_`)

### GitLab

1. Go to **User Settings** → **Access Tokens**
2. Create a new token with `api` scope
3. Copy the token (starts with `glpat-`)

### Linear

1. Go to **Settings** → **API** → **Personal API keys**
2. Click **Create key**
3. Copy the key (starts with `lin_api_`)

### Azure DevOps

1. Go to **User Settings** → **Personal access tokens**
2. Click **+ New Token**
3. Select scopes: Work Items (Read & Write)
4. Copy the token

### Asana

1. Go to **My Settings** → **Apps** → **Developer Console**
2. Click **Create new token**
3. Copy the token

::: tip Token Best Practices
- Create a dedicated token for spectryn
- Use a descriptive name for auditing
- Rotate tokens periodically (every 90 days)
- Revoke tokens when no longer needed
:::

## CI/CD Configuration

### GitHub Actions

```yaml
# .github/workflows/sync.yml
jobs:
  sync-jira:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install spectryn
        run: pip install spectryn

      - name: Sync to Jira
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
```

### GitLab CI

```yaml
# .gitlab-ci.yml
sync-jira:
  image: python:3.12
  variables:
    JIRA_URL: $JIRA_URL
    JIRA_EMAIL: $JIRA_EMAIL
    JIRA_API_TOKEN: $JIRA_API_TOKEN
  script:
    - pip install spectryn
    - spectryn --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
```

### Docker

```bash
docker run --rm \
  -e JIRA_URL=$JIRA_URL \
  -e JIRA_EMAIL=$JIRA_EMAIL \
  -e JIRA_API_TOKEN=$JIRA_API_TOKEN \
  -v $(pwd):/workspace \
  adriandarian/spectryn:latest \
  --markdown EPIC.md --epic PROJ-123 --execute
```

## Troubleshooting

### Token Not Working

If you get authentication errors:

1. **Check token validity** - Tokens expire and can be revoked
2. **Verify email** - Must match the account that created the token
3. **Check URL** - Must include `https://` and be the correct domain
4. **Test with curl**:

```bash
curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "$JIRA_URL/rest/api/3/myself"
```

### Environment Not Loading

If `.env` isn't being loaded:

1. Check file location (same directory as running command)
2. Verify file syntax (no quotes around values, no spaces around `=`)
3. Try explicit loading:

```bash
source .env && spectryn --markdown EPIC.md --epic PROJ-123
```

