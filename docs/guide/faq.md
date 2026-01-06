# Frequently Asked Questions

Common questions about spectra answered.

## General

### What is spectra?

spectra is a CLI tool that synchronizes markdown documentation with issue trackers like Jira, GitHub Issues, GitLab, Linear, and more. Write your epics and stories in markdown, and spectra keeps them in sync with your tracker.

### Why use markdown instead of the tracker directly?

| Markdown | Direct Tracker |
|----------|----------------|
| ✅ Version controlled | ❌ No Git history |
| ✅ Review in PRs | ❌ Changes hard to review |
| ✅ Works offline | ❌ Requires connection |
| ✅ Any editor | ❌ Web UI only |
| ✅ AI-friendly | ❌ Manual entry |
| ✅ Bulk editing easy | ❌ One at a time |

### Which trackers are supported?

- **Jira** (Cloud and Server)
- **GitHub Issues** & Projects
- **GitLab Issues**
- **Linear**
- **Trello**
- **ClickUp**
- **Monday.com**
- **Shortcut** (formerly Clubhouse)
- **YouTrack**
- **Plane.so**
- **Pivotal Tracker**
- **Basecamp**
- **Bitbucket Issues**

See [Tracker Guides](/guide/configuration) for setup instructions.

### Is spectra free?

Yes! spectra is open source under the MIT license. Use it for personal and commercial projects freely.

---

## Installation

### How do I install spectra?

```bash
# Using pip (recommended)
pip install spectra

# Using pipx (isolated environment)
pipx install spectra

# Using Homebrew (macOS)
brew install adriandarian/tap/spectra

# Using Docker
docker pull ghcr.io/adriandarian/spectra
```

See [Installation Guide](/guide/installation) for all options.

### What Python version do I need?

Python 3.11 or higher is required.

```bash
python --version  # Should be 3.11+
```

### Does it work on Windows?

Yes! spectra works on Windows, macOS, and Linux. For Windows, we recommend using:
- Windows Terminal
- PowerShell 7+
- Or WSL2

---

## Configuration

### Where should I put my config file?

spectra searches for configuration in this order:
1. `--config` flag path
2. `./spectra.yaml` (current directory)
3. `./.spectra/config.yaml`
4. `~/.config/spectra/config.yaml`

Recommendation: Put `spectra.yaml` in your project root.

### How do I store API tokens securely?

**Never put tokens in config files!** Use environment variables:

```bash
# .env file (add to .gitignore)
JIRA_API_TOKEN=your-token-here
```

```yaml
# spectra.yaml
jira:
  api_token: ${JIRA_API_TOKEN}
```

For teams, use secret managers:
- HashiCorp Vault
- AWS Secrets Manager
- 1Password
- Doppler

See [Secret Management](/guide/environment#secret-management).

### How do I connect to Jira Server (on-premise)?

```yaml
# spectra.yaml
tracker: jira

jira:
  url: https://jira.yourcompany.com
  auth_type: basic  # or 'pat' for personal access token
  username: ${JIRA_USERNAME}
  password: ${JIRA_PASSWORD}  # or api_token for PAT
```

---

## Writing Stories

### What's the recommended story format?

```markdown
### 🔐 US-001: Story Title

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🟠 High |
| **Status** | 📋 To Do |

#### Description

**As a** [user type]
**I want** [goal]
**So that** [benefit]

#### Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Task 1 | Description | 1 | 📋 To Do |
```

See [Schema Reference](/guide/schema) for all options.

### Can I use my own story ID format?

Yes! Configure the pattern in `spectra.yaml`:

```yaml
story_id_pattern: "STORY-\\d+"    # STORY-001
# or
story_id_pattern: "[A-Z]+-\\d+"   # ABC-123
# or
story_id_pattern: "#\\d+"         # #123
```

### Do I need to use emojis?

No, emojis are optional. Plain text works fine:

```markdown
| **Status** | To Do |        # Works
| **Status** | 📋 To Do |     # Also works
```

Configure mappings for your preference:
```yaml
mappings:
  status:
    "To Do": To Do
    "📋 To Do": To Do
```

### How do I handle story dependencies?

Use the "Blocks" or "Depends On" fields:

```markdown
| **Blocks** | US-002, US-003 |
| **Depends On** | US-000 |
```

Or in description:
```markdown
> Blocked by US-000
> Blocks: US-002
```

---

## Syncing

### What happens during a sync?

1. **Parse** - Read markdown file
2. **Fetch** - Get current tracker state
3. **Diff** - Compare markdown vs tracker
4. **Plan** - Determine required changes
5. **Execute** - Apply changes to tracker

### Will sync overwrite my tracker changes?

By default, spectra shows what would change (dry run). Changes only apply with `--execute`:

```bash
# Safe - just shows diff
spectra --markdown EPIC.md

# Actually makes changes
spectra --execute --markdown EPIC.md
```

### How do I sync only specific stories?

```bash
# Single story
spectra sync --story US-001 --markdown EPIC.md

# Multiple stories
spectra sync --stories US-001,US-002,US-003 --markdown EPIC.md

# By status
spectra sync --filter "status=To Do" --markdown EPIC.md
```

### Can I sync bidirectionally?

Yes! Import tracker changes back to markdown:

```bash
# One-way: Markdown → Tracker
spectra sync --execute --markdown EPIC.md

# Import: Tracker → Markdown
spectra import --epic PROJ-123 --output EPIC.md

# Bidirectional with conflict resolution
spectra sync --bidirectional --interactive --markdown EPIC.md
```

### What if there's a conflict?

spectra detects conflicts and offers resolution:

```bash
# Interactive resolution
spectra sync --interactive --markdown EPIC.md

# Force markdown to win
spectra sync --force-local --markdown EPIC.md

# Force tracker to win
spectra sync --force-remote --markdown EPIC.md
```

---

## Troubleshooting

### Why do I get "401 Unauthorized"?

Your API token is invalid or expired:

1. Generate a new token from your tracker
2. Update environment variable
3. Run `spectra doctor` to verify

See [Troubleshooting Guide](/guide/troubleshooting#authentication-issues).

### Why are my stories not being found?

Check your markdown format:

```bash
spectra --validate --markdown EPIC.md
```

Common issues:
- Wrong heading level (use `##` or `###`)
- Missing story ID pattern
- Malformed metadata table

### How do I debug sync issues?

```bash
# Verbose output
spectra --verbose --markdown EPIC.md

# Debug mode with full logs
spectra --debug --markdown EPIC.md

# Check diagnostics
spectra doctor
```

### Where are the log files?

```bash
# Default location
~/.spectra/logs/spectra.log

# Or set custom location
export SPECTRA_LOG_FILE=/path/to/spectra.log
```

---

## Advanced Usage

### Can I use spectra in CI/CD?

Absolutely! spectra is designed for CI/CD:

```yaml
# GitHub Actions
- name: Sync Stories
  run: spectra sync --execute --markdown docs/epics/
  env:
    JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
```

See [CI/CD Setup Tutorial](/tutorials/cicd-setup).

### How do I sync to multiple trackers?

```yaml
# spectra.yaml
trackers:
  jira:
    url: https://company.atlassian.net
    project: BACKEND
  github:
    repo: company/frontend
    project: Frontend Board
```

```bash
# Sync to both
spectra sync --trackers jira,github --markdown EPIC.md
```

### Can I extend spectra with plugins?

Yes! spectra has a plugin system:

```bash
# Install a plugin
spectra plugin install spectra-custom-fields

# List plugins
spectra plugin list

# Create your own
spectra plugin scaffold --name my-plugin
```

See [Plugins Guide](/guide/plugins).

### Does spectra support webhooks?

Yes, for real-time sync:

```bash
# Start webhook listener
spectra webhook listen --port 8080

# Configure in your tracker to send webhooks to:
# https://your-server.com:8080/webhook
```

---

## Performance

### How fast is spectra?

Typical performance:
- Parse 100 stories: ~50ms
- Sync 100 stories: ~10 seconds
- Incremental sync: ~2 seconds

### How do I speed up large syncs?

```yaml
# spectra.yaml
performance:
  parallel_sync: true
  max_workers: 4
  cache:
    enabled: true
```

See [Performance Tuning Guide](/guide/performance).

### Is there a limit on stories?

No hard limit. We've tested with:
- 10,000+ stories
- 50+ epics
- Files >50MB (use streaming mode)

---

## Data & Security

### Where is my data stored?

- **Config**: `spectra.yaml` in your project
- **State**: `.spectra/state.json` (tracks sync state)
- **Cache**: In memory or configured location
- **Logs**: `~/.spectra/logs/`

spectra never sends data to external servers (except your configured tracker).

### Is my data encrypted?

- **In transit**: Yes, all API calls use HTTPS
- **At rest**: Cache can be encrypted with `cache.encrypt: true`
- **Tokens**: Use environment variables, never stored in files

### Does spectra collect telemetry?

By default, no. Optional anonymous usage stats can be enabled:

```yaml
telemetry:
  enabled: false  # Default
```

See [Telemetry Policy](/guide/telemetry).

---

## Getting Help

### Where can I get support?

1. **Documentation**: You're here! 📚
2. **GitHub Issues**: [Report bugs](https://github.com/adriandarian/spectra/issues)
3. **Discussions**: [Ask questions](https://github.com/adriandarian/spectra/discussions)

### How do I report a bug?

```bash
# Generate diagnostic report
spectra doctor --report > diagnostics.txt
```

Then open an issue with:
- spectra version
- Python version
- OS
- Steps to reproduce
- Diagnostic report (redact secrets!)

### How can I contribute?

We welcome contributions! See [Contributing Guide](/contributing).

```bash
# Set up development environment
git clone https://github.com/adriandarian/spectra
cd spectra
pip install -e ".[dev]"
pytest
```
