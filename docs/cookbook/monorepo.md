# Monorepo Setup

Manage multiple epics across packages in a monorepo.

## Monorepo Structure

```
monorepo/
├── apps/
│   ├── web/
│   │   ├── package.json
│   │   └── docs/
│   │       └── EPIC.md          → WEB-100
│   ├── mobile/
│   │   ├── package.json
│   │   └── docs/
│   │       └── EPIC.md          → MOBILE-100
│   └── api/
│       ├── package.json
│       └── docs/
│           └── EPIC.md          → API-100
├── packages/
│   ├── ui/
│   │   └── docs/
│   │       └── EPIC.md          → UI-100
│   └── shared/
│       └── docs/
│           └── EPIC.md          → SHARED-100
├── docs/
│   └── platform/
│       └── EPIC.md              → PLATFORM-100
├── package.json
└── .spectryn/
    └── config.yaml
```

## Configuration

### Root Config

```yaml
# .spectryn/config.yaml
jira:
  url: https://company.atlassian.net
  email: ${JIRA_EMAIL}
  api_token: ${JIRA_API_TOKEN}

# Epic mappings by path pattern
epics:
  "apps/web/docs/EPIC.md": WEB-100
  "apps/mobile/docs/EPIC.md": MOBILE-100
  "apps/api/docs/EPIC.md": API-100
  "packages/ui/docs/EPIC.md": UI-100
  "packages/shared/docs/EPIC.md": SHARED-100
  "docs/platform/EPIC.md": PLATFORM-100
```

### Package-Level Overrides

Each package can have its own config:

```yaml
# apps/web/.spectryn.yaml
jira:
  project: WEB

sync:
  verbose: true
```

## Sync Scripts

### Sync All Epics

```bash
#!/bin/bash
# scripts/sync-all-epics.sh

set -e

# Find all EPIC.md files
find . -name "EPIC.md" -type f | while read -r file; do
  # Extract epic key from file or parent directory
  dir=$(dirname "$file")
  package=$(basename "$(dirname "$dir")")
  
  # Read epic key from config or frontmatter
  epic_key=$(grep -m1 "epic:" "$file" | awk '{print $2}' || echo "")
  
  if [ -n "$epic_key" ]; then
    echo "Syncing $file → $epic_key"
    spectryn -m "$file" -e "$epic_key" -x --no-confirm
  else
    echo "Skipping $file (no epic key)"
  fi
done
```

### Sync Changed Epics Only

```bash
#!/bin/bash
# scripts/sync-changed.sh

# Get changed EPIC.md files
changed_files=$(git diff --name-only HEAD~1 HEAD | grep "EPIC.md" || echo "")

if [ -z "$changed_files" ]; then
  echo "No epic files changed"
  exit 0
fi

for file in $changed_files; do
  if [ -f "$file" ]; then
    epic_key=$(grep -m1 "epic:" "$file" | awk '{print $2}')
    if [ -n "$epic_key" ]; then
      echo "Syncing changed: $file → $epic_key"
      spectryn -m "$file" -e "$epic_key" -x --no-confirm
    fi
  fi
done
```

### Sync Specific Package

```bash
#!/bin/bash
# scripts/sync-package.sh

PACKAGE=$1

if [ -z "$PACKAGE" ]; then
  echo "Usage: ./sync-package.sh <package-name>"
  echo "Example: ./sync-package.sh web"
  exit 1
fi

# Find epic in package
epic_file=$(find . -path "*/$PACKAGE/*/EPIC.md" -o -path "*/$PACKAGE/EPIC.md" | head -1)

if [ -z "$epic_file" ]; then
  echo "No EPIC.md found for package: $PACKAGE"
  exit 1
fi

epic_key=$(grep -m1 "epic:" "$epic_file" | awk '{print $2}')

echo "Syncing $PACKAGE: $epic_file → $epic_key"
spectryn -m "$epic_file" -e "$epic_key" -x
```

## CI/CD Integration

### GitHub Actions Matrix

```yaml
# .github/workflows/sync-epics.yml
name: Sync Epics

on:
  push:
    paths:
      - '**/EPIC.md'
    branches:
      - main

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      
      - id: detect
        run: |
          # Find changed EPIC.md files and their epic keys
          changed=$(git diff --name-only HEAD~1 HEAD | grep "EPIC.md" || echo "")
          
          if [ -z "$changed" ]; then
            echo "matrix=[]" >> $GITHUB_OUTPUT
            exit 0
          fi
          
          matrix="["
          for file in $changed; do
            if [ -f "$file" ]; then
              epic=$(grep -m1 "epic:" "$file" | awk '{print $2}')
              if [ -n "$epic" ]; then
                matrix="$matrix{\"file\":\"$file\",\"epic\":\"$epic\"},"
              fi
            fi
          done
          matrix="${matrix%,}]"
          
          echo "matrix=$matrix" >> $GITHUB_OUTPUT

  sync:
    needs: detect-changes
    if: needs.detect-changes.outputs.matrix != '[]'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include: ${{ fromJson(needs.detect-changes.outputs.matrix) }}
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - run: pip install spectryn
      
      - name: Sync ${{ matrix.epic }}
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          spectryn -m "${{ matrix.file }}" -e "${{ matrix.epic }}" -x --no-confirm
```

### Turborepo Integration

```json
// turbo.json
{
  "pipeline": {
    "sync:jira": {
      "dependsOn": [],
      "inputs": ["docs/EPIC.md"],
      "cache": false
    }
  }
}
```

```json
// apps/web/package.json
{
  "scripts": {
    "sync:jira": "spectryn -m docs/EPIC.md -e WEB-100 -x --no-confirm"
  }
}
```

```bash
# Sync all packages
turbo run sync:jira

# Sync changed packages only
turbo run sync:jira --filter=[HEAD^1]
```

### Nx Integration

```json
// project.json (in each package)
{
  "targets": {
    "sync-jira": {
      "executor": "nx:run-commands",
      "options": {
        "command": "spectryn -m docs/EPIC.md -e WEB-100 -x --no-confirm"
      },
      "inputs": ["docs/EPIC.md"]
    }
  }
}
```

```bash
# Sync affected packages
nx affected --target=sync-jira

# Sync all
nx run-many --target=sync-jira
```

## Epic Document with Package Context

```markdown
# 🌐 Web Application Epic

> **Epic: WEB-100**

---

## Package Info

| Field | Value |
|-------|-------|
| **Package** | @company/web |
| **Epic Key** | WEB-100 |
| **Status** | 🔄 In Progress |
| **Dependencies** | @company/ui, @company/shared |

### Related Epics

| Package | Epic | Status |
|---------|------|--------|
| @company/ui | UI-100 | 🔄 In Progress |
| @company/api | API-100 | ✅ Done |
| @company/shared | SHARED-100 | ✅ Done |

---

## User Stories

---

### 🚀 US-001: Homepage Redesign

| Field | Value |
|-------|-------|
| **Story Points** | 8 |
| **Priority** | 🟡 High |
| **Status** | 🔄 In Progress |
| **Depends On** | UI-100/US-003 (Design System) |

...
```

## Cross-Package Dependencies

Document and track cross-package dependencies:

```markdown
### 🔧 US-005: Shared Authentication

| Field | Value |
|-------|-------|
| **Story Points** | 5 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description

**As a** developer
**I want** shared auth logic in @company/shared
**So that** all apps use consistent authentication

#### Cross-Package Impact

| Package | Impact |
|---------|--------|
| @company/web | Import auth hooks |
| @company/mobile | Import auth logic |
| @company/api | Validate tokens |

#### Blocked By
- SHARED-100/US-001: Token validation utils
- API-100/US-003: Auth endpoints

#### Blocks
- WEB-100/US-006: Protected routes
- MOBILE-100/US-004: Login screen
```

## Tips

::: tip Organization
- Consistent path structure across packages
- Epic key in frontmatter or first line
- README in docs folder explaining structure
:::

::: tip Automation
- Use monorepo tools (Turborepo, Nx, Lerna)
- Sync only changed packages in CI
- Validate all epics in pre-commit
:::

::: tip Dependencies
- Document cross-package dependencies
- Link related epics
- Consider sync order for dependencies
:::

