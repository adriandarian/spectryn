# Environment Variables

spectra uses environment variables for sensitive configuration like API credentials. This page covers all supported variables and best practices.

## Required Variables

These are required for spectra to connect to Jira:

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_URL` | Your Jira instance URL | `https://company.atlassian.net` |
| `JIRA_EMAIL` | Your Jira account email | `you@company.com` |
| `JIRA_API_TOKEN` | Jira API token | `ATATT3xFf...` |

## Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JIRA_PROJECT` | Default project key | None |
| `MONDAY_API_TOKEN` | Monday.com API token (v2) | None |
| `MONDAY_BOARD_ID` | Monday.com board ID | None |
| `MONDAY_WORKSPACE_ID` | Monday.com workspace ID | None |
| `PLANE_API_TOKEN` | Plane.so API token | None |
| `PLANE_WORKSPACE_SLUG` | Plane.so workspace slug | None |
| `PLANE_PROJECT_ID` | Plane.so project ID | None |
| `PLANE_API_URL` | Plane.so API endpoint (for self-hosted) | `https://app.plane.so/api/v1` |
| `SPECTRA_VERBOSE` | Enable verbose output | `false` |
| `SPECTRA_LOG_LEVEL` | Logging level | `INFO` |
| `SPECTRA_NO_COLOR` | Disable colored output | `false` |

## Setting Environment Variables

### Temporary (Current Session)

::: code-group

```bash [Bash/Zsh]
export JIRA_URL=https://your-company.atlassian.net
export JIRA_EMAIL=your.email@company.com
export JIRA_API_TOKEN=your-api-token
```

```fish [Fish]
set -x JIRA_URL https://your-company.atlassian.net
set -x JIRA_EMAIL your.email@company.com
set -x JIRA_API_TOKEN your-api-token
```

```powershell [PowerShell]
$env:JIRA_URL = "https://your-company.atlassian.net"
$env:JIRA_EMAIL = "your.email@company.com"
$env:JIRA_API_TOKEN = "your-api-token"
```

:::

### Permanent (.env File)

Create a `.env` file in your project directory:

```bash
# .env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token

# Optional
JIRA_PROJECT=MYPROJ
SPECTRA_VERBOSE=true
```

spectra automatically loads `.env` files from:
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

## Getting a Jira API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a descriptive name (e.g., "spectra CLI")
4. Copy the token immediately (you won't see it again)

::: tip Token Best Practices
- Create a dedicated token for spectra
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

      - name: Install spectra
        run: pip install spectra

      - name: Sync to Jira
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectra --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
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
    - pip install spectra
    - spectra --markdown EPIC.md --epic PROJ-123 --execute --no-confirm
```

### Docker

```bash
docker run --rm \
  -e JIRA_URL=$JIRA_URL \
  -e JIRA_EMAIL=$JIRA_EMAIL \
  -e JIRA_API_TOKEN=$JIRA_API_TOKEN \
  -v $(pwd):/workspace \
  adriandarian/spectra:latest \
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
source .env && spectra --markdown EPIC.md --epic PROJ-123
```

