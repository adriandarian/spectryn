# Interactive Mode

Learn how to use spectryn's interactive mode for step-by-step guided syncing.

**Duration**: ~3 minutes

<div class="video-placeholder" style="background: linear-gradient(135deg, #00875a 0%, #36b37e 100%); border-radius: 12px; padding: 4rem 2rem; text-align: center; margin: 2rem 0;">
<span style="font-size: 4rem;">🎮</span>
<p style="color: white; font-size: 1.2rem; margin-top: 1rem;">Interactive Session Recording</p>
</div>

## When to Use Interactive Mode

Interactive mode is perfect when you want to:

- **Review each change** before applying
- **Skip specific stories** that aren't ready
- **Sync selectively** during development
- **Learn** what spectryn does step-by-step

## Starting Interactive Mode

<div class="terminal-session">

```bash
$ spectryn --markdown EPIC.md --epic PROJ-123 --interactive

╭──────────────────────────────────────────────────────────────╮
│  spectryn v1.0.0 - Interactive Mode                           │
│  Syncing: EPIC.md → PROJ-123                                 │
╰──────────────────────────────────────────────────────────────╯

📋 Found 3 stories to sync

Press Enter to continue or 'q' to quit...
```

</div>

## Story-by-Story Review

### Story 1: Preview Changes

<div class="terminal-session">

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Story 1 of 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 US-001: User Authentication
   Jira Issue: PROJ-124
   Story Points: 5
   Status: Planned → In Progress

┌─────────────────────────────────────────────────────────────┐
│ Changes to apply:                                           │
├─────────────────────────────────────────────────────────────┤
│ 📝 Update description                                       │
│    Current: "Implement user login"                          │
│    New: "As a user, I want to authenticate securely..."     │
│                                                             │
│ ➕ Create 3 subtasks:                                       │
│    1. Create login form (2 SP)                              │
│    2. Implement JWT auth (2 SP)                             │
│    3. Add password reset (1 SP)                             │
│                                                             │
│ 🔄 Transition status:                                       │
│    Open → In Progress                                       │
└─────────────────────────────────────────────────────────────┘

Apply changes to US-001? [y]es / [n]o / [s]kip / [q]uit: █
```

</div>

### Applying Changes

<div class="terminal-session">

```
Apply changes to US-001? [y]es / [n]o / [s]kip / [q]uit: y

Applying changes to PROJ-124...
  ✓ Updated description
  ✓ Created subtask PROJ-125: Create login form
  ✓ Created subtask PROJ-126: Implement JWT auth
  ✓ Created subtask PROJ-127: Add password reset
  ✓ Transitioned to In Progress

✅ Story synced successfully!

Press Enter to continue to next story...
```

</div>

### Skipping a Story

<div class="terminal-session">

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Story 2 of 3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 US-002: User Registration
   Jira Issue: PROJ-128
   Story Points: 5
   Status: Planned (no change)

┌─────────────────────────────────────────────────────────────┐
│ Changes to apply:                                           │
├─────────────────────────────────────────────────────────────┤
│ 📝 Update description                                       │
│ ➕ Create 4 subtasks                                        │
└─────────────────────────────────────────────────────────────┘

Apply changes to US-002? [y]es / [n]o / [s]kip / [q]uit: s

⏭️  Skipped US-002

Press Enter to continue to next story...
```

</div>

### Viewing Diff

Press `d` to see a detailed diff:

<div class="terminal-session">

```
Apply changes to US-003? [y]es / [n]o / [s]kip / [d]iff / [q]uit: d

┌─────────────────────────────────────────────────────────────┐
│ Description Diff                                            │
├─────────────────────────────────────────────────────────────┤
│ - Implement password reset functionality                    │
│ + **As a** user who forgot their password                   │
│ + **I want** to reset it via email                          │
│ + **So that** I can regain access to my account             │
│ +                                                           │
│ + The reset link should expire after 1 hour.                │
└─────────────────────────────────────────────────────────────┘

Apply changes to US-003? [y]es / [n]o / [s]kip / [d]iff / [q]uit: █
```

</div>

## Session Summary

<div class="terminal-session">

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Interactive Session Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

╭──────────────────────────────────────────────────────────────╮
│  📊 Summary                                                  │
│                                                              │
│  Stories processed: 3                                        │
│  ├── Applied: 2                                              │
│  ├── Skipped: 1                                              │
│  └── Failed: 0                                               │
│                                                              │
│  Subtasks created: 6                                         │
│  Descriptions updated: 2                                     │
│  Status transitions: 1                                       │
│                                                              │
│  Duration: 45s                                               │
│  Backup: backup_20250113_144500                              │
╰──────────────────────────────────────────────────────────────╯

Skipped stories can be synced later with:
  spectryn --markdown EPIC.md --epic PROJ-123 --story US-002
```

</div>

## Interactive Mode Commands

| Key | Action |
|-----|--------|
| `y` | Apply changes to this story |
| `n` | Don't apply (same as skip) |
| `s` | Skip this story |
| `d` | Show detailed diff |
| `q` | Quit interactive mode |
| `?` | Show help |

## Tips

::: tip When to Skip
Skip stories that:
- Are still being refined
- Have dependencies not yet ready
- Need discussion before syncing
:::

::: tip Resume Later
Skipped stories can be synced individually:
```bash
spectryn -m EPIC.md -e PROJ-123 --story US-002 -x
```
:::

## What's Next?

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">

<a href="/tutorials/backup-restore" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>💾 Backup & Restore</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Safe sync with rollback</span>
</a>

<a href="/tutorials/cicd-setup" style="display: block; padding: 1rem; border: 1px solid var(--vp-c-divider); border-radius: 8px; text-decoration: none;">
<strong>⚙️ CI/CD Setup</strong><br/>
<span style="opacity: 0.7; font-size: 0.9rem;">Automate syncing</span>
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

