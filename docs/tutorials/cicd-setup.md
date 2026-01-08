# CI/CD Setup

Automate Jira syncing with GitHub Actions, GitLab CI, or other CI/CD platforms.

**Duration**: ~6 minutes

<div class="video-placeholder" style="background: linear-gradient(135deg, #6554c0 0%, #8777d9 100%); border-radius: 12px; padding: 4rem 2rem; text-align: center; margin: 2rem 0;">
<span style="font-size: 4rem;">⚙️</span>
<p style="color: white; font-size: 1.2rem; margin-top: 1rem;">GitHub Actions Setup Demo</p>
</div>

## Overview

Automatically sync your markdown epics to Jira whenever changes are pushed:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Push to main   │ ──▶ │  GitHub Action  │ ──▶ │  Jira Updated   │
│  (EPIC.md)      │     │  runs spectryn   │     │  automatically  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Step 1: Add Secrets to GitHub

<div style="display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0;">

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>1. Go to Repository Settings</strong>
<p style="opacity: 0.8; margin-top: 0.5rem; font-size: 0.9rem;">Settings → Secrets and variables → Actions</p>
</div>

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>2. Add Repository Secrets</strong>
<ul style="opacity: 0.8; margin-top: 0.5rem; font-size: 0.9rem; padding-left: 1.2rem;">
<li>JIRA_URL</li>
<li>JIRA_EMAIL</li>
<li>JIRA_API_TOKEN</li>
</ul>
</div>

<div style="flex: 1; min-width: 280px; background: var(--vp-c-bg-soft); padding: 1.5rem; border-radius: 8px;">
<strong>3. Add Repository Variables</strong>
<ul style="opacity: 0.8; margin-top: 0.5rem; font-size: 0.9rem; padding-left: 1.2rem;">
<li>EPIC_KEY (e.g., PROJ-123)</li>
</ul>
</div>

</div>

## Step 2: Create Workflow File

<div class="terminal-session">

```bash
$ mkdir -p .github/workflows

$ cat > .github/workflows/jira-sync.yml << 'EOF'
name: Sync to Jira

on:
  push:
    paths:
      - 'docs/EPIC.md'
    branches:
      - main

jobs:
  sync:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
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
          spectryn \
            --markdown docs/EPIC.md \
            --epic ${{ vars.EPIC_KEY }} \
            --execute \
            --no-confirm \
            --export results.json
      
      - name: Upload sync results
        uses: actions/upload-artifact@v4
        with:
          name: jira-sync-results
          path: results.json
EOF
```

</div>

## Step 3: Test the Workflow

<div class="terminal-session">

```bash
# Make a change to EPIC.md
$ echo "Updated: $(date)" >> docs/EPIC.md

# Commit and push
$ git add docs/EPIC.md .github/workflows/jira-sync.yml
$ git commit -m "docs: update epic, add CI sync"
$ git push origin main

# Watch the action run at:
# https://github.com/your-org/your-repo/actions
```

</div>

## Workflow Execution

<div class="terminal-session" style="background: #0d1117;">

```
Run spectryn \
  --markdown docs/EPIC.md \
  --epic PROJ-123 \
  --execute \
  --no-confirm \
  --export results.json

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: docs/EPIC.md → PROJ-123                            │
│  Mode: EXECUTE (CI/CD)                                       │
╰──────────────────────────────────────────────────────────────╯

📋 Found 3 stories in markdown

Syncing stories ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 3/3

✓ PROJ-124: Updated description, 3 subtasks
✓ PROJ-128: Updated description, 2 subtasks
✓ PROJ-131: Updated description, 2 subtasks

╭──────────────────────────────────────────────────────────────╮
│  ✅ Sync Complete                                            │
│  Stories: 3 | Subtasks: 7 | Duration: 3.8s                   │
╰──────────────────────────────────────────────────────────────╯
```

</div>

## Advanced: PR Preview

Add a workflow that shows what would change on pull requests:

```yaml
# .github/workflows/jira-preview.yml
name: Preview Jira Changes

on:
  pull_request:
    paths:
      - 'docs/EPIC.md'

jobs:
  preview:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - run: pip install spectryn
      
      - name: Generate preview
        id: preview
        env:
          JIRA_URL: ${{ secrets.JIRA_URL }}
          JIRA_EMAIL: ${{ secrets.JIRA_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          output=$(spectryn \
            --markdown docs/EPIC.md \
            --epic ${{ vars.EPIC_KEY }} \
            --output json)
          
          stories=$(echo "$output" | jq '.summary.stories')
          subtasks=$(echo "$output" | jq '.summary.subtasks_to_create')
          
          echo "stories=$stories" >> $GITHUB_OUTPUT
          echo "subtasks=$subtasks" >> $GITHUB_OUTPUT
      
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## 📋 Jira Sync Preview
              
              When merged, this PR will sync to **${{ vars.EPIC_KEY }}**:
              
              | Metric | Count |
              |--------|-------|
              | Stories | ${{ steps.preview.outputs.stories }} |
              | Subtasks to create | ${{ steps.preview.outputs.subtasks }} |
              
              ✅ Changes will be applied automatically when merged to main.`
            })
```

## Advanced: Multi-Epic Sync

Sync multiple epics from a monorepo:

```yaml
# .github/workflows/multi-sync.yml
name: Sync All Epics

on:
  push:
    paths:
      - 'docs/epics/**/*.md'
    branches:
      - main

jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      
      - id: detect
        run: |
          changed=$(git diff --name-only HEAD~1 HEAD | grep "docs/epics/.*\.md" || echo "")
          if [ -z "$changed" ]; then
            echo "matrix=[]" >> $GITHUB_OUTPUT
          else
            matrix="["
            for file in $changed; do
              # Extract epic key from frontmatter or filename
              epic=$(grep -m1 "^epic:" "$file" | awk '{print $2}' || basename "$file" .md)
              matrix="$matrix{\"file\":\"$file\",\"epic\":\"$epic\"},"
            done
            matrix="${matrix%,}]"
            echo "matrix=$matrix" >> $GITHUB_OUTPUT
          fi

  sync:
    needs: detect
    if: needs.detect.outputs.matrix != '[]'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include: ${{ fromJson(needs.detect.outputs.matrix) }}
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

## Slack Notifications

Add Slack notifications for sync results:

```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "${{ job.status == 'success' && '✅' || '❌' }} Jira sync ${{ job.status }}",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "*Jira Sync ${{ job.status == 'success' && 'Complete' || 'Failed' }}*\n\nEpic: `${{ vars.EPIC_KEY }}`\nCommit: ${{ github.sha }}"
            }
          }
        ]
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Authentication failed | Check secrets are set correctly |
| File not found | Verify path in `--markdown` flag |
| Epic not found | Ensure epic exists in Jira |
| Timeout | Add retry logic or increase timeout |

### Debug Mode

```yaml
- name: Sync with debug
  run: |
    spectryn \
      --markdown docs/EPIC.md \
      --epic ${{ vars.EPIC_KEY }} \
      --execute \
      --no-confirm \
      --verbose \
      --log-format json
```

## What's Next?

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">

<a href="/examples/cicd" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>📝 More CI/CD Examples</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">GitLab, Jenkins, CircleCI</span>
</a>

<a href="/cookbook/monorepo" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>📦 Monorepo Setup</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Multiple epics</span>
</a>

</div>

<style>
.terminal-session {
  background: #1e1e1e;
  border-radius: 8px;
  margin: 1.5rem 0;
  overflow: hidden;
}

.terminal-session pre {
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
  background: #1e1e1e !important;
}

.terminal-session code {
  font-size: 0.85rem !important;
  line-height: 1.5 !important;
}
</style>

