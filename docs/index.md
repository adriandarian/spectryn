---
layout: home

hero:
  name: spectryn
  text: Specs to Trackers, Simplified
  tagline: A production-grade CLI tool for syncing markdown specs to issue trackers. Supports Jira, GitHub Issues, Azure DevOps, Linear, Trello, ClickUp, and more.
  image:
    src: /hero-illustration.svg
    alt: spectryn
  actions:
    - theme: brand
      text: Get Started →
      link: /guide/getting-started
    - theme: alt
      text: View on GitHub
      link: https://github.com/adriandarian/spectryn

features:
  - icon: 🚀
    title: Multi-Platform Sync
    details: Sync to Jira, GitHub Issues, Azure DevOps, Linear, Trello, GitLab, Monday.com, ClickUp, Shortcut, and Confluence. One tool for all your issue trackers.
  - icon: 📝
    title: Markdown & YAML Native
    details: Write specs in familiar markdown or YAML format. No need to learn new syntax or use clunky web interfaces.
  - icon: 🔄
    title: Smart Matching
    details: Fuzzy title matching between specs and existing issues. Works with your existing issues without manual linking.
  - icon: 🛡️
    title: Safe by Default
    details: Dry-run mode, confirmations, and detailed previews before any changes. Backup and rollback capabilities built-in.
  - icon: ⚡
    title: Bi-directional Sync
    details: Push specs to trackers or pull changes back. Undo-capable operations with full audit trail.
  - icon: 🔌
    title: Plugin System
    details: Extensible architecture for custom parsers, trackers, and formatters. Easy to add new platform adapters.
  - icon: 📊
    title: Rich CLI Output
    details: Beautiful terminal UI with progress bars, colored output, and detailed reports. JSON output mode for CI/CD integration.
  - icon: 🐳
    title: Docker Ready
    details: Run in containers with Docker or Docker Compose. Perfect for CI/CD pipelines and automated workflows.
---

<style>
:root {
  --vp-home-hero-name-color: transparent;
  --vp-home-hero-name-background: linear-gradient(135deg, #0052cc 0%, #2684ff 50%, #36b37e 100%);
}

.dark {
  --vp-home-hero-name-background: linear-gradient(135deg, #2684ff 0%, #4c9aff 50%, #36b37e 100%);
}
</style>

## Quick Install

::: code-group

```bash [pip]
pip install spectryn
```

```bash [pipx]
pipx install spectryn
```

```bash [Homebrew]
brew tap adriandarian/spectra https://github.com/adriandarian/spectra
brew install spectra
```

```bash [Docker]
docker pull adrianthehactus/spectryn:latest
```

:::

## Example Usage

```bash
# Preview changes (dry-run)
spectryn --markdown EPIC.md --epic PROJ-123

# Execute sync
spectryn --markdown EPIC.md --epic PROJ-123 --execute

# Sync with interactive mode
spectryn --markdown EPIC.md --epic PROJ-123 --execute --interactive
```

## What People Are Saying

> "spectryn transformed our sprint planning. We write everything in markdown and sync to Jira in seconds."

> "Finally, a tool that understands developers prefer markdown over clicking through Jira forms."

> "The backup and rollback features give us confidence to sync without fear."

