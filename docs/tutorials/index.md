# Video Tutorials

Step-by-step visual guides for spectryn.

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin-top: 2rem;">

<a href="/tutorials/first-sync" style="display: block; padding: 0; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; overflow: hidden; transition: all 0.2s;">
<div style="background: linear-gradient(135deg, #0052cc 0%, #2684ff 100%); padding: 2rem; text-align: center;">
<span style="font-size: 3rem;">🚀</span>
</div>
<div style="padding: 1.5rem;">
<strong style="font-size: 1.1rem;">Your First Sync</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">5 min • Set up and sync your first epic</span>
</div>
</a>

<a href="/tutorials/interactive-mode" style="display: block; padding: 0; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; overflow: hidden; transition: all 0.2s;">
<div style="background: linear-gradient(135deg, #00875a 0%, #36b37e 100%); padding: 2rem; text-align: center;">
<span style="font-size: 3rem;">🎮</span>
</div>
<div style="padding: 1.5rem;">
<strong style="font-size: 1.1rem;">Interactive Mode</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">3 min • Step-by-step guided sync</span>
</div>
</a>

<a href="/tutorials/backup-restore" style="display: block; padding: 0; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; overflow: hidden; transition: all 0.2s;">
<div style="background: linear-gradient(135deg, #ff991f 0%, #ffab00 100%); padding: 2rem; text-align: center;">
<span style="font-size: 3rem;">💾</span>
</div>
<div style="padding: 1.5rem;">
<strong style="font-size: 1.1rem;">Backup & Restore</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">4 min • Safe sync with rollback</span>
</div>
</a>

<a href="/tutorials/cicd-setup" style="display: block; padding: 0; border: 1px solid var(--vp-c-divider); border-radius: 12px; text-decoration: none; overflow: hidden; transition: all 0.2s;">
<div style="background: linear-gradient(135deg, #6554c0 0%, #8777d9 100%); padding: 2rem; text-align: center;">
<span style="font-size: 3rem;">⚙️</span>
</div>
<div style="padding: 1.5rem;">
<strong style="font-size: 1.1rem;">CI/CD Setup</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">6 min • Automate with GitHub Actions</span>
</div>
</a>

</div>

## Quick Demos

### Dry Run Preview

<div class="terminal-demo">

```
$ spectryn --markdown EPIC.md --epic PROJ-123

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: EPIC.md → PROJ-123                                 │
│  Mode: DRY RUN (use --execute to apply changes)              │
╰──────────────────────────────────────────────────────────────╯

📋 Found 3 stories in markdown

┌─────────────────────────────────────────────────────────────┐
│ US-001: User Authentication                                 │
├─────────────────────────────────────────────────────────────┤
│ 📝 Would update description                                 │
│ ➕ Would create 3 subtasks                                  │
│ ⏳ Would transition: Open → In Progress                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ US-002: User Registration                                   │
├─────────────────────────────────────────────────────────────┤
│ 📝 Would update description                                 │
│ ➕ Would create 2 subtasks                                  │
│ ✓ Status unchanged                                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ US-003: Password Reset                                      │
├─────────────────────────────────────────────────────────────┤
│ 📝 Would update description                                 │
│ ➕ Would create 2 subtasks                                  │
│ ✓ Status unchanged                                          │
└─────────────────────────────────────────────────────────────┘

Summary:
  Stories: 3
  Subtasks to create: 7
  Descriptions to update: 3
  Status transitions: 1

To apply these changes, run:
  spectryn --markdown EPIC.md --epic PROJ-123 --execute
```

</div>

### Execute Sync

<div class="terminal-demo">

```
$ spectryn --markdown EPIC.md --epic PROJ-123 --execute

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: EPIC.md → PROJ-123                                 │
│  Mode: EXECUTE                                               │
╰──────────────────────────────────────────────────────────────╯

⚠️  This will modify 3 stories in Jira. Continue? [y/N]: y

💾 Creating backup... backup_20250113_142530

Syncing stories ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 3/3

✓ PROJ-124: Updated description
  ✓ Created subtask PROJ-125
  ✓ Created subtask PROJ-126
  ✓ Created subtask PROJ-127
  ✓ Transitioned to In Progress

✓ PROJ-128: Updated description
  ✓ Created subtask PROJ-129
  ✓ Created subtask PROJ-130

✓ PROJ-131: Updated description
  ✓ Created subtask PROJ-132
  ✓ Created subtask PROJ-133

╭──────────────────────────────────────────────────────────────╮
│  ✅ Sync Complete                                            │
│                                                              │
│  Stories synced: 3                                           │
│  Subtasks created: 7                                         │
│  Transitions: 1                                              │
│  Duration: 4.2s                                              │
│                                                              │
│  Backup: backup_20250113_142530                              │
│  To rollback: spectryn --rollback --epic PROJ-123             │
╰──────────────────────────────────────────────────────────────╯
```

</div>

<style>
.terminal-demo {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 0;
  margin: 1.5rem 0;
  overflow: hidden;
}

.terminal-demo::before {
  content: '';
  display: block;
  background: #333;
  padding: 8px 12px;
  border-bottom: 1px solid #444;
}

.terminal-demo pre {
  margin: 0 !important;
  border-radius: 0 !important;
  border: none !important;
}

.terminal-demo code {
  font-size: 0.85rem !important;
  line-height: 1.5 !important;
}
</style>

