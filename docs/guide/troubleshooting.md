# Troubleshooting Guide

Common issues and solutions when using spectryn.

## Quick Diagnostics

Run the built-in diagnostic tool to identify common issues:

```bash
spectryn doctor
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
spectryn doctor
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
spectryn --validate --epic PROJ-123
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
   # In spectryn.yaml
   story_id_pattern: "US-\\d+"    # Matches US-001
   ```

**Validate your markdown:**
```bash
spectryn --validate --markdown EPIC.md
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

**Configure custom mappings in `spectryn.yaml`:**

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

**When spectryn creates duplicates:**

1. **Check state file:** The `.spectryn/` directory tracks synced items
   ```bash
   cat .spectryn/state.json | jq '.stories'
   ```

2. **Reset state for a story:**
   ```bash
   spectryn --reset-state --story US-001
   ```

3. **Force re-link:**
   ```bash
   spectryn --link US-001 JIRA-456
   ```

---

### "Conflict detected" Error

**When tracker and markdown have diverged:**

```bash
# View differences
spectryn diff --markdown EPIC.md --epic PROJ-123

# Resolve interactively
spectryn sync --interactive --markdown EPIC.md

# Force markdown to win (overwrite tracker)
spectryn sync --force-local --markdown EPIC.md

# Force tracker to win (update markdown)
spectryn import --epic PROJ-123 --output EPIC.md
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
   # In spectryn.yaml
   jira:
     subtask_type: "Sub-task"  # Must match your Jira's subtask type
   ```

---

## Performance Issues

### Slow Sync Operations

**Optimize with these settings:**

```yaml
# spectryn.yaml
performance:
  parallel_sync: true
  max_workers: 4
  cache_ttl: 3600  # Cache tracker metadata for 1 hour
  batch_size: 50   # Process in batches
```

**Use incremental sync:**
```bash
spectryn sync --incremental --markdown EPIC.md
```

---

### "Rate limit exceeded"

**Symptoms:**
```
Error: Rate limit exceeded. Retry after 60 seconds.
```

**Solutions:**

1. **Wait and retry** - spectryn auto-retries with backoff
2. **Reduce parallelism:**
   ```yaml
   performance:
     max_workers: 2
     rate_limit: 10  # requests per second
   ```
3. **Use batch operations:**
   ```bash
   spectryn sync --batch --markdown EPIC.md
   ```

---

## Configuration Issues

### "Config file not found"

**Search order for configuration:**
1. `--config` flag path
2. `./spectryn.yaml` (current directory)
3. `./.spectryn/config.yaml`
4. `~/.config/spectryn/config.yaml`
5. Environment variables only

**Create a minimal config:**
```bash
spectryn init
# Or manually:
cat > spectryn.yaml << EOF
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
spectryn --env-file /path/to/.env --markdown EPIC.md
```

**Verify variables are set:**
```bash
spectryn doctor --verbose
```

---

## CLI Issues

### "Command not found: spectryn"

**After pip install:**

1. **Check installation:**
   ```bash
   pip show spectryn
   pip list | grep spectryn
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
   python -m spectryn --help
   ```

---

### Shell Completion Not Working

**Regenerate completions:**

::: code-group
```bash [Bash]
spectryn completions bash > ~/.local/share/bash-completion/completions/spectryn
source ~/.bashrc
```

```bash [Zsh]
spectryn completions zsh > ~/.zfunc/_spectryn
# Add to .zshrc: fpath+=~/.zfunc
source ~/.zshrc
```

```bash [Fish]
spectryn completions fish > ~/.config/fish/completions/spectryn.fish
```

```powershell [PowerShell]
spectryn completions powershell >> $PROFILE
```
:::

---

## Getting More Help

### Debug Mode

Enable verbose logging:
```bash
spectryn --verbose --debug --markdown EPIC.md
```

### Log Files

Check logs for detailed errors:
```bash
# Default log location
cat ~/.spectryn/logs/spectryn.log

# Or specify location
export SPECTRA_LOG_FILE="/tmp/spectryn-debug.log"
spectryn --verbose --markdown EPIC.md
```

### Report an Issue

If you've tried the above and still have issues:

1. **Search existing issues:** [GitHub Issues](https://github.com/adriandarian/spectryn/issues)
2. **Gather diagnostic info:**
   ```bash
   spectryn doctor --report > diagnostic-report.txt
   ```
3. **Open a new issue** with:
   - spectryn version (`spectryn --version`)
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
| `E008` | Config error | Run `spectryn doctor` |

See [Exit Codes Reference](/reference/exit-codes) for complete list.
