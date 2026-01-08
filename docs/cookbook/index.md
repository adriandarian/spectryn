# Cookbook

Practical recipes and patterns for common spectryn use cases.

## Quick Links

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1.5rem;">

<a href="/cookbook/sprint-planning" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">📅</span><br/>
<strong style="font-size: 1.1rem;">Sprint Planning</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Sync sprint backlogs from markdown</span>
</a>

<a href="/cookbook/multi-team" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">👥</span><br/>
<strong style="font-size: 1.1rem;">Multi-Team Workflows</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Coordinate across multiple teams</span>
</a>

<a href="/cookbook/migration" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">🔄</span><br/>
<strong style="font-size: 1.1rem;">Migration Projects</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Track system migrations and upgrades</span>
</a>

<a href="/cookbook/bug-triage" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">🐛</span><br/>
<strong style="font-size: 1.1rem;">Bug Triage</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Manage bug backlogs efficiently</span>
</a>

<a href="/cookbook/release-planning" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">🚀</span><br/>
<strong style="font-size: 1.1rem;">Release Planning</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Plan and track releases</span>
</a>

<a href="/cookbook/documentation-driven" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">📚</span><br/>
<strong style="font-size: 1.1rem;">Documentation-Driven</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Docs as the source of truth</span>
</a>

<a href="/cookbook/ai-assisted" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">🤖</span><br/>
<strong style="font-size: 1.1rem;">AI-Assisted Planning</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Generate epics with AI</span>
</a>

<a href="/cookbook/monorepo" style="display: block; padding: 1.5rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; transition: all 0.2s;">
<span style="font-size: 2rem;">📦</span><br/>
<strong style="font-size: 1.1rem;">Monorepo Setup</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Multiple epics in one repo</span>
</a>

</div>

## Common Patterns

### Sync on Every Commit

Keep Jira automatically in sync with your documentation:

```yaml
# .github/workflows/jira-sync.yml
on:
  push:
    paths: ['docs/**/*.md']
    branches: [main]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install spectryn
      - run: |
          for file in docs/*.md; do
            epic=$(basename "$file" .md)
            spectryn -m "$file" -e "$epic" -x --no-confirm
          done
```

### Validate Before Merge

Catch formatting errors in pull requests:

```yaml
on:
  pull_request:
    paths: ['docs/**/*.md']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install spectryn
      - run: spectryn -m docs/EPIC.md -e PROJ-123 --validate
```

### Weekly Sync Report

Get a summary of what changed:

```bash
#!/bin/bash
# weekly-sync.sh

spectryn -m EPIC.md -e PROJ-123 -x --no-confirm --export weekly-report.json

# Parse and send to Slack
jq '.results | "Stories: \(.stories_processed), Subtasks: \(.subtasks_created)"' \
  weekly-report.json | xargs -I {} curl -X POST "$SLACK_WEBHOOK" -d '{"text":"{}"}'
```

