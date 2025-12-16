# Branch Protection Rules

This document outlines the branch protection rules for the `spectra` repository.

## Protected Branches

### `main` Branch

The `main` branch is the primary protected branch. All changes must go through pull requests.

#### Required Status Checks

The following CI checks **must pass** before merging:

| Check | Description | Blocking |
|-------|-------------|----------|
| `quick-checks` | Debug code detection, commit format, file permissions | ✅ Yes |
| `lint` | Ruff lint, Ruff format, Black format | ✅ Yes |
| `typecheck` | MyPy strict type checking | ✅ Yes |
| `test` | Unit tests (Python 3.10/3.11/3.12 × Ubuntu/macOS/Windows) | ✅ Yes |
| `build` | Package build, twine verify, installation test | ✅ Yes |
| `status-check` | Final aggregated gate job | ✅ Yes |

The following checks run but are **informational only**:

| Check | Description | Blocking |
|-------|-------------|----------|
| `security` | Bandit, pip-audit, TruffleHog | ⚠️ No (review required) |
| `integration` | Integration test suite | ℹ️ No |
| `property-tests` | Hypothesis property-based tests | ℹ️ No |
| `docker` | Docker image build & test | ℹ️ No |
| `docs` | Documentation build, markdown lint | ℹ️ No |
| `vscode-extension` | VS Code extension build | ℹ️ No |
| `api-compat` | API compatibility (griffe) | ℹ️ No |
| `size-check` | Package size monitoring | ℹ️ No |

#### Review Requirements

- **Required approving reviews:** 1
- **Dismiss stale reviews:** Yes (when new commits are pushed)
- **Require review from CODEOWNERS:** Yes
- **Restrict who can dismiss reviews:** Maintainers only

#### Additional Rules

| Rule | Setting |
|------|---------|
| Require branches to be up to date | ✅ Enabled |
| Require signed commits | ⚠️ Recommended |
| Require linear history | ✅ Enabled (squash merge) |
| Include administrators | ✅ Enabled |
| Restrict pushes | ✅ Enabled (no direct pushes) |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

## Merge Strategy

We use **squash merge** for all PRs to maintain a clean, linear history.

### Squash Merge Settings

- **Default commit message:** PR title + description
- **Commit message format:** Conventional Commits
- **Delete branch after merge:** ✅ Enabled

## Setting Up Branch Protection

### Via GitHub UI

1. Go to **Settings** → **Branches**
2. Click **Add branch protection rule**
3. Set **Branch name pattern:** `main`
4. Configure as described above

### Via GitHub CLI

```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["quick-checks","lint","typecheck","test","build","status-check"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"dismiss_stale_reviews":true,"require_code_owner_reviews":true,"required_approving_review_count":1}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false \
  --field required_linear_history=true
```

## Emergency Procedures

In case of critical issues requiring immediate fixes:

1. **Never bypass branch protection** unless absolutely necessary
2. Contact a maintainer with admin access
3. Document the bypass in the PR description
4. Create a follow-up issue to address any skipped checks

## Rulesets (GitHub Rulesets Alternative)

For organizations using GitHub Rulesets (newer feature):

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "pull_request" },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "quick-checks" },
          { "context": "lint" },
          { "context": "typecheck" },
          { "context": "test" },
          { "context": "build" },
          { "context": "status-check" }
        ]
      }
    },
    { "type": "non_fast_forward" }
  ]
}
```

## Related Documentation

- [Contributing Guide](../CONTRIBUTING.md)
- [PR Template](./PULL_REQUEST_TEMPLATE.md)
- [Release Process](./RELEASE.md)
- [CODEOWNERS](./CODEOWNERS)
