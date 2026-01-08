# Spectra JetBrains Plugin

IDE plugin for IntelliJ IDEA, PyCharm, WebStorm, and other JetBrains IDEs.

## Features

- **Syntax Highlighting** - Custom highlighting for Spectra markdown
- **Code Completion** - Auto-complete status, priority, and tracker IDs
- **Quick Navigation** - Go to epic/story definitions
- **Inspections** - Real-time validation warnings
- **Quick Fixes** - Auto-fix common issues
- **Tool Window** - Sidebar with sync status and stories
- **External Tools** - Run spectryn commands from IDE

## Installation

### From JetBrains Marketplace

1. Open **Settings/Preferences** → **Plugins**
2. Search for "Spectra"
3. Click **Install**

### From Disk

1. Download the latest release from [Releases](https://github.com/spectryn/spectryn/releases)
2. Open **Settings/Preferences** → **Plugins**
3. Click the gear icon → **Install Plugin from Disk...**
4. Select the downloaded `.zip` file

## Requirements

- IntelliJ IDEA 2023.1 or later (or compatible IDE)
- Spectra CLI installed (`pip install spectryn`)

## Configuration

### Settings

Navigate to **Settings/Preferences** → **Tools** → **Spectra**

| Setting | Description | Default |
|---------|-------------|---------|
| Tracker Type | Issue tracker type (Jira, GitHub, etc.) | `jira` |
| Tracker URL | Base URL of your tracker | - |
| Project Key | Project identifier | - |
| Validate on Save | Run validation when saving | `true` |
| Show Sync Status | Display sync status in status bar | `true` |

### External Tools

The plugin automatically detects the `spectryn` CLI. To configure manually:

1. **Settings** → **Tools** → **External Tools**
2. Add a new tool with:
   - **Program**: `spectryn`
   - **Arguments**: `--validate --markdown $FilePath$`
   - **Working directory**: `$ProjectFileDir$`

## Usage

### Keyboard Shortcuts

| Action | Windows/Linux | macOS |
|--------|---------------|-------|
| Validate File | `Ctrl+Shift+V` | `⌘⇧V` |
| Sync to Tracker | `Ctrl+Shift+S` | `⌘⇧S` |
| Go to Definition | `Ctrl+B` | `⌘B` |
| Quick Fix | `Alt+Enter` | `⌥↩` |
| Show Story Details | `Ctrl+Q` | `⌘Q` |

### Tool Window

The Spectra tool window (View → Tool Windows → Spectra) shows:

- **Sync Status** - Current sync state and last sync time
- **Stories** - List of stories in current file
- **Recent Changes** - Recently synced items

### Live Templates

Type these abbreviations and press Tab:

| Abbreviation | Expands To |
|--------------|------------|
| `epic` | `# Epic: $TITLE$` |
| `story` | `## Story: $TITLE$\n**Status**: $STATUS$` |
| `task` | `## Subtask: $TITLE$\n**Status**: $STATUS$` |
| `ac` | `### Acceptance Criteria\n- [ ] $CRITERIA$` |

## Development

### Building from Source

```bash
cd integrations/jetbrains
./gradlew build
```

### Running in Development

```bash
./gradlew runIde
```

### Testing

```bash
./gradlew test
```

## Project Structure

```
jetbrains/
├── src/main/
│   ├── kotlin/
│   │   └── dev/spectryn/plugin/
│   │       ├── SpectraPlugin.kt
│   │       ├── actions/
│   │       ├── completion/
│   │       ├── highlighting/
│   │       ├── inspections/
│   │       ├── navigation/
│   │       ├── settings/
│   │       └── toolwindow/
│   └── resources/
│       ├── META-INF/
│       │   └── plugin.xml
│       └── messages/
├── src/test/
├── build.gradle.kts
└── gradle.properties
```

## License

MIT - See [LICENSE](../../LICENSE)
