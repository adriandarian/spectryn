# Backup & Restore

Learn how spectryn protects your Jira data with automatic backups and easy rollback.

**Duration**: ~4 minutes

<div class="video-placeholder" style="background: linear-gradient(135deg, #ff991f 0%, #ffab00 100%); border-radius: 12px; padding: 4rem 2rem; text-align: center; margin: 2rem 0;">
<span style="font-size: 4rem;">💾</span>
<p style="color: white; font-size: 1.2rem; margin-top: 1rem;">Backup & Rollback Demo</p>
</div>

## Automatic Backups

Every time you run spectryn with `--execute`, it automatically creates a backup of the current Jira state.

<div class="terminal-session">

```bash
$ spectryn --markdown EPIC.md --epic PROJ-123 --execute

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0                                              │
│  Syncing: EPIC.md → PROJ-123                                 │
│  Mode: EXECUTE                                               │
╰──────────────────────────────────────────────────────────────╯

⚠️  This will modify 3 stories in Jira. Continue? [y/N]: y

💾 Creating backup... backup_20250113_150000

Syncing stories ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 3/3

✅ Sync complete! Backup saved: backup_20250113_150000
```

</div>

::: tip Backup Location
Backups are stored in `~/.spectryn/backups/` by default. Each backup contains the full state of all synced issues.
:::

## Listing Backups

<div class="terminal-session">

```bash
$ spectryn --list-backups

╭──────────────────────────────────────────────────────────────╮
│  Available Backups                                           │
╰──────────────────────────────────────────────────────────────╯

┌────────────────────────────────────────────────────────────┐
│ # │ Backup ID              │ Epic     │ Stories │ Age     │
├───┼────────────────────────┼──────────┼─────────┼─────────┤
│ 1 │ backup_20250113_150000 │ PROJ-123 │ 3       │ 2 min   │
│ 2 │ backup_20250113_143000 │ PROJ-123 │ 3       │ 1 hour  │
│ 3 │ backup_20250112_160000 │ PROJ-123 │ 2       │ 1 day   │
│ 4 │ backup_20250110_090000 │ PROJ-456 │ 5       │ 3 days  │
└────────────────────────────────────────────────────────────┘

To view changes: spectryn --diff-backup <backup_id> --epic <epic>
To restore:      spectryn --restore-backup <backup_id> --epic <epic>
```

</div>

## Viewing Diff from Backup

See what changed since a backup was created:

<div class="terminal-session">

```bash
$ spectryn --diff-latest --epic PROJ-123

╭──────────────────────────────────────────────────────────────╮
│  Diff: backup_20250113_150000 → Current                      │
│  Epic: PROJ-123                                              │
╰──────────────────────────────────────────────────────────────╯

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJ-124: User Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Description:
┌─────────────────────────────────────────────────────────────┐
│ - Implement user login                                      │
│ + **As a** user                                             │
│ + **I want** to authenticate securely                       │
│ + **So that** my data is protected                          │
│ +                                                           │
│ + Additional context about the authentication flow.         │
└─────────────────────────────────────────────────────────────┘

Subtasks:
┌─────────────────────────────────────────────────────────────┐
│ + PROJ-125: Create login form (NEW)                         │
│ + PROJ-126: Implement JWT auth (NEW)                        │
│ + PROJ-127: Add password reset (NEW)                        │
└─────────────────────────────────────────────────────────────┘

Status:
┌─────────────────────────────────────────────────────────────┐
│ - Open                                                      │
│ + In Progress                                               │
└─────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJ-128: User Registration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Description:
┌─────────────────────────────────────────────────────────────┐
│ - Allow new users to register                               │
│ + **As a** new user                                         │
│ + **I want** to create an account                           │
│ + **So that** I can use the application                     │
└─────────────────────────────────────────────────────────────┘

Summary:
  Issues changed: 2
  Subtasks added: 3
  Status transitions: 1
```

</div>

### Diff from Specific Backup

<div class="terminal-session">

```bash
$ spectryn --diff-backup backup_20250112_160000 --epic PROJ-123

# Shows diff from that specific backup to current state
```

</div>

## Rollback Last Sync

Made a mistake? Roll back to the previous state:

### Preview Rollback

<div class="terminal-session">

```bash
$ spectryn --rollback --epic PROJ-123

╭──────────────────────────────────────────────────────────────╮
│  Rollback Preview                                            │
│  Restoring: backup_20250113_150000 → PROJ-123                │
│  Mode: DRY RUN                                               │
╰──────────────────────────────────────────────────────────────╯

The following changes would be made:

┌─────────────────────────────────────────────────────────────┐
│ PROJ-124: User Authentication                               │
├─────────────────────────────────────────────────────────────┤
│ 📝 Restore original description                             │
│ 🗑️  Delete 3 subtasks (PROJ-125, PROJ-126, PROJ-127)        │
│ ⏪ Transition: In Progress → Open                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PROJ-128: User Registration                                 │
├─────────────────────────────────────────────────────────────┤
│ 📝 Restore original description                             │
└─────────────────────────────────────────────────────────────┘

To execute rollback, add --execute flag.
```

</div>

### Execute Rollback

<div class="terminal-session">

```bash
$ spectryn --rollback --epic PROJ-123 --execute

╭──────────────────────────────────────────────────────────────╮
│  Rollback                                                    │
│  Restoring: backup_20250113_150000 → PROJ-123                │
│  Mode: EXECUTE                                               │
╰──────────────────────────────────────────────────────────────╯

⚠️  This will revert 2 issues to their previous state. Continue? [y/N]: y

💾 Creating pre-rollback backup... backup_20250113_151500

Rolling back ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 2/2

✓ PROJ-124: Restored description
  ✓ Deleted subtask PROJ-125
  ✓ Deleted subtask PROJ-126
  ✓ Deleted subtask PROJ-127
  ✓ Transitioned to Open

✓ PROJ-128: Restored description

╭──────────────────────────────────────────────────────────────╮
│  ✅ Rollback Complete                                        │
│                                                              │
│  Issues restored: 2                                          │
│  Subtasks deleted: 3                                         │
│  Pre-rollback backup: backup_20250113_151500                 │
│                                                              │
│  You can undo this rollback with:                            │
│  spectryn --restore-backup backup_20250113_151500 --epic ...  │
╰──────────────────────────────────────────────────────────────╯
```

</div>

## Restore from Specific Backup

Restore from any previous backup:

<div class="terminal-session">

```bash
$ spectryn --restore-backup backup_20250110_090000 --epic PROJ-123

# Preview what would be restored
╭──────────────────────────────────────────────────────────────╮
│  Restore Preview                                             │
│  From: backup_20250110_090000                                │
│  To: PROJ-123                                                │
╰──────────────────────────────────────────────────────────────╯

This will restore the epic to its state from 3 days ago.
Stories in backup: 2
Current stories: 3

⚠️  Note: Story PROJ-130 exists now but not in backup.
    It will NOT be deleted (only descriptions/subtasks restored).

To execute, add --execute flag.
```

</div>

## Disable Backups

For CI/CD where you don't need backups:

<div class="terminal-session">

```bash
$ spectryn -m EPIC.md -e PROJ-123 -x --no-backup --no-confirm

# Syncs without creating a backup
# Use with caution!
```

</div>

## Backup Best Practices

::: tip Regular Backups
- Backups are created automatically on every sync
- Keep at least a week's worth of backups
- Old backups can be cleaned up with `spectryn --cleanup-backups --keep 10`
:::

::: warning Before Major Changes
For significant changes, manually create a named backup:
```bash
spectryn --backup "before-sprint-5" --epic PROJ-123
```
:::

## What's Next?

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">

<a href="/tutorials/cicd-setup" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>⚙️ CI/CD Setup</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Automate syncing</span>
</a>

<a href="/reference/cli" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>📚 CLI Reference</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">All backup commands</span>
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

