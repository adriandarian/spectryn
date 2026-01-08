# Release Process

This document describes how to release a new version of Spectra.

## Prerequisites

### Required Secrets

Configure these secrets in GitHub repository settings (Settings → Secrets and variables → Actions):

| Secret | Required For | How to Get |
|--------|--------------|------------|
| `DOCKERHUB_USERNAME` | Docker Hub | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub | [Create access token](https://hub.docker.com/settings/security) |
| `VSCE_PAT` | VS Code Marketplace (optional) | [Create PAT](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#get-a-personal-access-token) |
| `OVSX_PAT` | Open VSX (optional) | [Create token](https://open-vsx.org/user-settings/tokens) |
| `CHOCOLATEY_API_KEY` | Chocolatey | [Get API key](https://community.chocolatey.org/account) |

**Note:** `VSCE_PAT` and `OVSX_PAT` are optional. If not provided, the VS Code extension will be packaged and available as a `.vsix` download from GitHub releases for manual installation.

### PyPI Trusted Publishing (No Secret Needed!)

PyPI uses OIDC trusted publishing. Configure it in PyPI:

1. Go to https://pypi.org/manage/project/spectryn/settings/publishing/
2. Add a new trusted publisher:
   - Owner: `adriandarian`
   - Repository: `spectryn`
   - Workflow: `release.yml`
   - Environment: `pypi`

## How to Release

### Option 1: Tag-based Release (Recommended)

```bash
# 1. Update CHANGELOG.md with release notes
# 2. Commit changes
git add .
git commit -m "Prepare release v1.0.0"

# 3. Create and push tag
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0
```

The release workflow will automatically:
- ✅ Validate the release
- ✅ Run tests
- ✅ Create GitHub Release with notes
- ✅ Publish to PyPI
- ✅ Build and push Docker images
- ✅ Deploy documentation
- ✅ Publish VS Code extension
- ✅ Update Homebrew formula

### Option 2: Manual Trigger

1. Go to Actions → 🚀 Release
2. Click "Run workflow"
3. Enter version (e.g., `1.0.0`)
4. Optionally enable "Dry run" to test without publishing

## Version Format

Follow [Semantic Versioning](https://semver.org/):

- `1.0.0` - Stable release
- `1.0.1` - Patch release (bug fixes)
- `1.1.0` - Minor release (new features, backward compatible)
- `2.0.0` - Major release (breaking changes)
- `1.0.0-alpha.1` - Pre-release (alpha)
- `1.0.0-beta.1` - Pre-release (beta)
- `1.0.0-rc.1` - Pre-release (release candidate)

## Release Checklist

Before releasing:

- [ ] All tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] Type checking passes (`make typecheck`)
- [ ] CHANGELOG.md updated with release notes
- [ ] Version in `pyproject.toml` updated
- [ ] Documentation is up to date
- [ ] Breaking changes are documented

## Rollback

If a release has issues:

1. **PyPI**: You cannot delete releases, but you can yank them:
   ```bash
   pip install twine
   twine yank spectryn==1.0.0
   ```

2. **Docker**: Delete the tag from Docker Hub/GHCR

3. **GitHub**: Mark release as pre-release or delete it

4. **Homebrew**: Commit a fix to the formula in the main repository

## Artifacts Published

| Artifact | Location |
|----------|----------|
| Python package | https://pypi.org/project/spectryn/ |
| Docker image | https://hub.docker.com/r/adrianthehactus/spectryn |
| Docker image | ghcr.io/adriandarian/spectryn |
| VS Code extension | VS Code Marketplace |
| Documentation | https://adriandarian.github.io/spectryn |
| Homebrew | `brew tap adriandarian/spectra https://github.com/adriandarian/spectra && brew install spectra` |
| Shell completions | GitHub Release assets |

