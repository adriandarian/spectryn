# Your First Sync

A complete walkthrough of setting up spectryn and syncing your first epic to Jira.

**Duration**: ~5 minutes

<div class="video-placeholder" style="background: linear-gradient(135deg, #0052cc 0%, #2684ff 100%); border-radius: 12px; padding: 4rem 2rem; text-align: center; margin: 2rem 0;">
<span style="font-size: 4rem;">🎬</span>
<p style="color: white; font-size: 1.2rem; margin-top: 1rem;">Terminal Recording</p>
</div>

## Step 1: Install spectryn

<div class="step-demo">

```bash
# Install with pip
$ pip install spectryn
Collecting spectryn
  Downloading spectryn-1.0.0-py3-none-any.whl (45 kB)
Installing collected packages: spectryn
Successfully installed spectryn-1.0.0

# Verify installation
$ spectryn --version
spectryn version 1.0.0
```

</div>

::: tip Alternative Installation
You can also use `pipx install spectryn` for an isolated environment, or install via Homebrew on macOS (see [Installation Guide](/guide/installation)).
:::

## Step 2: Configure Credentials

<div class="step-demo">

```bash
# Create a .env file with your Jira credentials
$ cat > .env << 'EOF'
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token-here
EOF

# Verify file was created
$ cat .env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_TOKEN=your-api-token-here
```

</div>

::: warning Security
Add `.env` to your `.gitignore` to avoid committing secrets!

```bash
echo ".env" >> .gitignore
```
:::

### Getting Your API Token

<div style="display: flex; gap: 1rem; align-items: flex-start; margin: 1.5rem 0; flex-wrap: wrap;">

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>1. Go to Atlassian Account</strong>
<p style="opacity: 0.8; margin-top: 0.5rem;">Visit <a href="https://id.atlassian.com/manage-profile/security/api-tokens">id.atlassian.com/manage-profile/security/api-tokens</a></p>
</div>

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>2. Create API Token</strong>
<p style="opacity: 0.8; margin-top: 0.5rem;">Click "Create API token" and give it a name like "spectryn"</p>
</div>

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>3. Copy the Token</strong>
<p style="opacity: 0.8; margin-top: 0.5rem;">Copy immediately - you won't see it again!</p>
</div>

</div>

## Step 3: Create Your Epic Markdown

<div class="step-demo">

```bash
$ cat > EPIC.md << 'EOF'
# 🚀 My First Epic

> **Epic: Getting started with spectryn**

---

## User Stories

---

### 🔧 US-001: Setup Development Environment

| Field | Value |
|-------|-------|
| **Story Points** | 3 |
| **Priority** | 🔴 Critical |
| **Status** | 📋 Planned |

#### Description

**As a** developer
**I want** the development environment configured
**So that** I can start building features

#### Acceptance Criteria

- [ ] All dependencies installed
- [ ] Development server runs
- [ ] Tests pass

#### Subtasks

| # | Subtask | Description | SP | Status |
|---|---------|-------------|:--:|--------|
| 1 | Install deps | Run npm install | 1 | 📋 Planned |
| 2 | Configure env | Set up .env file | 1 | 📋 Planned |
| 3 | Verify setup | Run test suite | 1 | 📋 Planned |

---
EOF
```

</div>

## Step 4: Preview Changes (Dry Run)

<div class="step-demo">

```bash
$ spectryn --markdown EPIC.md --epic PROJ-123

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: EPIC.md → PROJ-123                                 │
│  Mode: DRY RUN (use --execute to apply changes)              │
╰──────────────────────────────────────────────────────────────╯

📋 Found 1 story in markdown

Matching stories with Jira...
  ✓ US-001 matched → PROJ-124 (fuzzy: 92%)

┌─────────────────────────────────────────────────────────────┐
│ US-001: Setup Development Environment                       │
│ Jira: PROJ-124                                              │
├─────────────────────────────────────────────────────────────┤
│ 📝 Would update description                                 │
│ ➕ Would create 3 subtasks                                  │
│ ✓ Status unchanged (Planned)                                │
└─────────────────────────────────────────────────────────────┘

Summary:
  Stories: 1
  Subtasks to create: 3
  Descriptions to update: 1

This is a dry run. No changes were made.
To apply these changes, add --execute flag.
```

</div>

## Step 5: Execute the Sync

<div class="step-demo">

```bash
$ spectryn --markdown EPIC.md --epic PROJ-123 --execute

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: EPIC.md → PROJ-123                                 │
│  Mode: EXECUTE                                               │
╰──────────────────────────────────────────────────────────────╯

⚠️  This will modify 1 story in Jira. Continue? [y/N]: y

💾 Creating backup... backup_20250113_143000

Syncing stories ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 1/1

✓ PROJ-124: Setup Development Environment
  ✓ Updated description
  ✓ Created subtask PROJ-125: Install deps
  ✓ Created subtask PROJ-126: Configure env
  ✓ Created subtask PROJ-127: Verify setup

╭──────────────────────────────────────────────────────────────╮
│  ✅ Sync Complete                                            │
│                                                              │
│  Stories synced: 1                                           │
│  Subtasks created: 3                                         │
│  Duration: 2.1s                                              │
│                                                              │
│  Backup: backup_20250113_143000                              │
╰──────────────────────────────────────────────────────────────╯
```

</div>

## Step 6: Verify in Jira

After syncing, check your Jira epic:

<div style="background: var(--vp-c-bg-soft); border-radius: 12px; padding: 2rem; margin: 1.5rem 0;">

**PROJ-123** (Epic)
└── **PROJ-124**: Setup Development Environment
    - Description updated ✓
    - 3 subtasks created ✓
    └── **PROJ-125**: Install deps
    └── **PROJ-126**: Configure env  
    └── **PROJ-127**: Verify setup

</div>

## What's Next?

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">

<a href="/tutorials/interactive-mode" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>🎮 Interactive Mode</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Step-by-step guided sync</span>
</a>

<a href="/tutorials/backup-restore" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>💾 Backup & Restore</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Safe sync with rollback</span>
</a>

<a href="/guide/schema" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>📐 Schema Reference</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Complete markdown format</span>
</a>

</div>

<style>
.step-demo {
  margin: 1.5rem 0;
}

.step-demo pre {
  border-radius: 8px !important;
}
</style>

