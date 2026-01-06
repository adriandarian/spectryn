# Troubleshooting Guide

Common issues and solutions when using spectra.

## Quick Diagnostics

Run the built-in diagnostic tool to identify common issues:

```bash
spectra doctor
```

This checks:
- ✅ Python version compatibility
- ✅ Configuration file validity
- ✅ Environment variables
- ✅ API connectivity
- ✅ Authentication credentials

---

## Authentication Issues

### "401 Unauthorized" Error

**Symptoms:**
```
Error: Authentication failed (401)
```

**Causes & Solutions:**

::: details Jira Cloud
1. **Invalid API token** - Generate a new token at [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. **Wrong email** - Use your Atlassian account email, not username
3. **Token expired** - API tokens don't expire, but may be revoked

```bash
# Verify credentials
export JIRA_API_TOKEN="your-new-token"
export JIRA_EMAIL="your-email@example.com"
spectra doctor
```
:::

::: details GitHub
1. **Token scope insufficient** - Needs `repo` and `project` scopes
2. **Token expired** - Fine-grained tokens have expiration dates
3. **Organization SSO** - Token must be authorized for the org

```bash
# Check token
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```
:::

::: details GitLab
1. **Token scope** - Needs `api` scope
2. **Token expired** - Check expiration in GitLab settings
3. **Self-hosted URL** - Ensure `GITLAB_URL` is correct

```bash
export GITLAB_TOKEN="glpat-xxxxxxxxxxxx"
export GITLAB_URL="https://gitlab.yourcompany.com"
```
:::

::: details Linear
1. **Invalid API key** - Generate at Linear Settings → API
2. **Workspace access** - Ensure key has workspace access

```bash
export LINEAR_API_KEY="lin_api_xxxxxxxxxxxx"
```
:::

---

### "403 Forbidden" Error

**Symptoms:**
```
Error: Permission denied (403)
```

**Solutions:**

1. **Insufficient permissions** - Check your role has write access to the project
2. **Project restrictions** - Some projects may have restricted access
3. **Rate limited** - Wait and retry (see Rate Limiting section)

```bash
# Check project access
spectra --validate --epic PROJ-123
```

---

## Connection Issues

### "Connection Refused" or "Timeout"

**Symptoms:**
```
Error: Connection refused
Error: Request timed out
```

**Solutions:**

1. **Check network connectivity:**
   ```bash
   ping your-jira-instance.atlassian.net
   ```

2. **Verify the URL is correct:**
   ```bash
   echo $JIRA_URL
   # Should be: https://your-instance.atlassian.net
   ```

3. **Check for proxy issues:**
   ```bash
   export HTTP_PROXY="http://proxy.company.com:8080"
   export HTTPS_PROXY="http://proxy.company.com:8080"
   ```

4. **SSL Certificate issues (self-hosted):**
   ```bash
   export REQUESTS_CA_BUNDLE="/path/to/ca-bundle.crt"
   # Or disable verification (not recommended for production)
   export SPECTRA_SSL_VERIFY="false"
   ```

---

### "SSL: CERTIFICATE_VERIFY_FAILED"

**For self-hosted instances:**

```bash
# Option 1: Point to your CA bundle
export REQUESTS_CA_BUNDLE="/etc/ssl/certs/ca-certificates.crt"

# Option 2: Add your cert to the system store
sudo cp your-cert.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

---

## Parsing Issues

### "No stories found in markdown"

**Symptoms:**
```
Warning: No stories found in EPIC.md
```

**Common causes:**

1. **Wrong heading structure:**
   ```markdown
   # Epic Title        ← This is correct
   ## Story Title      ← This is correct
   ### Story Title     ← This won't be detected as a story
   ```

2. **Missing story ID pattern:**
   ```markdown
   ## US-001: Login Feature     ← Correct
   ## Login Feature             ← Missing ID, won't sync
   ```

3. **Story ID format mismatch:**
   ```yaml
   # In spectra.yaml
   story_id_pattern: "US-\\d+"    # Matches US-001
   ```

**Validate your markdown:**
```bash
spectra --validate --markdown EPIC.md
```

---

### "Failed to parse acceptance criteria"

**Ensure proper formatting:**

```markdown
#### Acceptance Criteria

- [ ] User can log in with email    ← Correct
- [x] Session persists              ← Correct (completed)
- User can log out                  ← Wrong: missing checkbox
* [ ] Another criterion             ← Wrong: use dashes
```

---

### "Invalid status/priority mapping"

**Configure custom mappings in `spectra.yaml`:**

```yaml
mappings:
  status:
    "✅ Done": "Done"
    "🔄 In Progress": "In Progress"
    "📋 To Do": "To Do"
    "🔴 Blocked": "Blocked"

  priority:
    "🔴 Critical": "Highest"
    "🟠 High": "High"
    "🟡 Medium": "Medium"
    "🟢 Low": "Low"
```

---

## Sync Issues

### "Story already exists" Error

**When spectra creates duplicates:**

1. **Check state file:** The `.spectra/` directory tracks synced items
   ```bash
   cat .spectra/state.json | jq '.stories'
   ```

2. **Reset state for a story:**
   ```bash
   spectra --reset-state --story US-001
   ```

3. **Force re-link:**
   ```bash
   spectra --link US-001 JIRA-456
   ```

---

### "Conflict detected" Error

**When tracker and markdown have diverged:**

```bash
# View differences
spectra diff --markdown EPIC.md --epic PROJ-123

# Resolve interactively
spectra sync --interactive --markdown EPIC.md

# Force markdown to win (overwrite tracker)
spectra sync --force-local --markdown EPIC.md

# Force tracker to win (update markdown)
spectra import --epic PROJ-123 --output EPIC.md
```

---

### Subtasks Not Creating

**Common issues:**

1. **Wrong table format:**
   ```markdown
   #### Subtasks

   | # | Subtask | Description | SP | Status |
   |---|---------|-------------|:--:|--------|   ← Need separator row
   | 1 | Task A  | Do thing    | 1  | To Do  |
   ```

2. **Missing subtask number:**
   ```markdown
   | 1 | Task A | Description | 1 | To Do |   ← Correct
   |   | Task B | Description | 1 | To Do |   ← Wrong: needs number
   ```

3. **Subtask issue type not configured:**
   ```yaml
   # In spectra.yaml
   jira:
     subtask_type: "Sub-task"  # Must match your Jira's subtask type
   ```

---

## Performance Issues

### Slow Sync Operations

**Optimize with these settings:**

```yaml
# spectra.yaml
performance:
  parallel_sync: true
  max_workers: 4
  cache_ttl: 3600  # Cache tracker metadata for 1 hour
  batch_size: 50   # Process in batches
```

**Use incremental sync:**
```bash
spectra sync --incremental --markdown EPIC.md
```

---

### "Rate limit exceeded"

**Symptoms:**
```
Error: Rate limit exceeded. Retry after 60 seconds.
```

**Solutions:**

1. **Wait and retry** - spectra auto-retries with backoff
2. **Reduce parallelism:**
   ```yaml
   performance:
     max_workers: 2
     rate_limit: 10  # requests per second
   ```
3. **Use batch operations:**
   ```bash
   spectra sync --batch --markdown EPIC.md
   ```

---

## Configuration Issues

### "Config file not found"

**Search order for configuration:**
1. `--config` flag path
2. `./spectra.yaml` (current directory)
3. `./.spectra/config.yaml`
4. `~/.config/spectra/config.yaml`
5. Environment variables only

**Create a minimal config:**
```bash
spectra init
# Or manually:
cat > spectra.yaml << EOF
tracker: jira
jira:
  url: https://your-instance.atlassian.net
  project: PROJ
EOF
```

---

### Environment Variables Not Loading

**Check `.env` file location:**
```bash
# Must be in current directory or specify path
spectra --env-file /path/to/.env --markdown EPIC.md
```

**Verify variables are set:**
```bash
spectra doctor --verbose
```

---

## CLI Issues

### "Command not found: spectra"

**After pip install:**

1. **Check installation:**
   ```bash
   pip show spectra
   pip list | grep spectra
   ```

2. **Add to PATH:**
   ```bash
   # Find where pip installs scripts
   python -m site --user-base
   # Add to PATH in ~/.bashrc or ~/.zshrc
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. **Use module directly:**
   ```bash
   python -m spectra --help
   ```

---

### Shell Completion Not Working

**Regenerate completions:**

::: code-group
```bash [Bash]
spectra completions bash > ~/.local/share/bash-completion/completions/spectra
source ~/.bashrc
```

```bash [Zsh]
spectra completions zsh > ~/.zfunc/_spectra
# Add to .zshrc: fpath+=~/.zfunc
source ~/.zshrc
```

```bash [Fish]
spectra completions fish > ~/.config/fish/completions/spectra.fish
```

```powershell [PowerShell]
spectra completions powershell >> $PROFILE
```
:::

---

## Getting More Help

### Debug Mode

Enable verbose logging:
```bash
spectra --verbose --debug --markdown EPIC.md
```

### Log Files

Check logs for detailed errors:
```bash
# Default log location
cat ~/.spectra/logs/spectra.log

# Or specify location
export SPECTRA_LOG_FILE="/tmp/spectra-debug.log"
spectra --verbose --markdown EPIC.md
```

### Report an Issue

If you've tried the above and still have issues:

1. **Search existing issues:** [GitHub Issues](https://github.com/adriandarian/spectra/issues)
2. **Gather diagnostic info:**
   ```bash
   spectra doctor --report > diagnostic-report.txt
   ```
3. **Open a new issue** with:
   - spectra version (`spectra --version`)
   - Python version (`python --version`)
   - Operating system
   - Full error message
   - Steps to reproduce
   - Redacted configuration

---

## Common Error Reference

| Error Code | Meaning | Quick Fix |
|------------|---------|-----------|
| `E001` | Authentication failed | Check API token/credentials |
| `E002` | Permission denied | Verify project access |
| `E003` | Not found | Check epic/project key |
| `E004` | Rate limited | Wait and retry |
| `E005` | Parse error | Validate markdown format |
| `E006` | Sync conflict | Use `--interactive` to resolve |
| `E007` | Network error | Check connectivity |
| `E008` | Config error | Run `spectra doctor` |

See [Exit Codes Reference](/reference/exit-codes) for complete list.
