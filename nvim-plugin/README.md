# md2jira.nvim

Neovim plugin for [md2jira](https://github.com/your-org/md2jira) - sync markdown documentation with Jira.

## ✨ Features

- 🔍 **Telescope Integration** - Fuzzy find stories and epics
- ✅ **Validate** - Check markdown syntax and structure
- 🔄 **Sync** - Push changes to Jira (dry-run or execute)
- 📊 **Dashboard** - View sync status at a glance
- ⌨️ **Keymaps** - Quick access to common operations
- 🔔 **Notifications** - Status updates via vim.notify

## 📦 Installation

### lazy.nvim

```lua
{
  "md2jira/nvim-plugin",
  dependencies = {
    "nvim-telescope/telescope.nvim",  -- optional, for fuzzy finding
  },
  ft = "markdown",
  config = function()
    require("md2jira").setup({})
  end,
}
```

### packer.nvim

```lua
use {
  "md2jira/nvim-plugin",
  requires = { "nvim-telescope/telescope.nvim" },
  config = function()
    require("md2jira").setup({})
  end,
}
```

## ⚙️ Configuration

```lua
require("md2jira").setup({
  -- Path to md2jira executable (nil = use PATH)
  executable = nil,

  -- Default arguments passed to all commands
  default_args = {},

  -- Auto-detect epic key from file content
  auto_detect_epic = true,

  -- Show notifications
  notify = true,

  -- Floating window settings
  float = {
    border = "rounded",
    width = 0.8,
    height = 0.8,
  },

  -- Keymaps (set individual keys to false to disable)
  keymaps = {
    validate = "<leader>jv",
    sync = "<leader>js",
    sync_execute = "<leader>jS",
    dashboard = "<leader>jd",
    stories = "<leader>jf",
    init = "<leader>ji",
  },
})
```

## 🎹 Keymaps

| Keymap | Description |
|--------|-------------|
| `<leader>jv` | Validate markdown |
| `<leader>js` | Sync (dry-run) |
| `<leader>jS` | Sync (execute) |
| `<leader>jd` | Show dashboard |
| `<leader>jf` | Find stories (Telescope) |
| `<leader>ji` | Init wizard |

## 📋 Commands

| Command | Description |
|---------|-------------|
| `:Md2JiraValidate` | Validate markdown file |
| `:Md2JiraValidate!` | Validate with strict mode |
| `:Md2JiraSync [epic]` | Sync to Jira (dry-run) |
| `:Md2JiraSyncExecute [epic]` | Sync to Jira (execute) |
| `:Md2JiraDashboard` | Show status dashboard |
| `:Md2JiraInit` | Run setup wizard |
| `:Md2JiraStories` | Browse stories |

## 🔭 Telescope

Browse content with fuzzy finding:

```vim
:Telescope md2jira stories    " Find stories
:Telescope md2jira epics      " Find epics
:Telescope md2jira commands   " All commands
```

### Telescope Keymaps

| Key | Description |
|-----|-------------|
| `<CR>` | Jump to story/epic |
| `<C-y>` | Copy story ID to clipboard |
| `<C-s>` | Sync selected story |

## 🔌 Lua API

```lua
local md2jira = require("md2jira")

-- Parse stories from current buffer
local stories = md2jira.parse_stories()
-- Returns: { { id = "US-001", title = "...", line = 10 }, ... }

-- Jump to a story
md2jira.goto_story("US-001")

-- Detect epic key from buffer
local epic = md2jira.detect_epic()

-- Run commands
md2jira.validate()
md2jira.sync()
md2jira.sync_execute()
md2jira.dashboard()

-- Run async with callback
md2jira.run_async({ "--validate", "--markdown", "epic.md" }, {
  on_complete = function(result)
    print("Exit code:", result.code)
    print("Output:", result.stdout)
  end,
})
```

## 📄 License

MIT License - see [LICENSE](../LICENSE)

