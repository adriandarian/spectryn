-- md2jira.nvim - Neovim plugin for md2jira
-- Sync markdown documentation with Jira from within Neovim

local M = {}

-- Default configuration
M.config = {
  -- Path to md2jira executable (nil = use PATH)
  executable = nil,

  -- Default arguments
  default_args = {},

  -- Auto-detect epic key from filename or content
  auto_detect_epic = true,

  -- Show notifications
  notify = true,

  -- Floating window settings
  float = {
    border = "rounded",
    width = 0.8,
    height = 0.8,
  },

  -- Keymaps (set to false to disable)
  keymaps = {
    validate = "<leader>jv",
    sync = "<leader>js",
    sync_execute = "<leader>jS",
    dashboard = "<leader>jd",
    stories = "<leader>jf",
    init = "<leader>ji",
  },
}

-- State
M._state = {
  last_epic = nil,
  last_result = nil,
}

-- Setup function
function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})

  -- Create user commands
  M._create_commands()

  -- Setup keymaps if enabled
  if M.config.keymaps then
    M._setup_keymaps()
  end

  -- Setup autocommands
  M._setup_autocmds()
end

-- Get the md2jira executable path
function M._get_executable()
  return M.config.executable or "md2jira"
end

-- Run md2jira command asynchronously
function M.run_async(args, opts)
  opts = opts or {}
  local cmd = { M._get_executable() }
  vim.list_extend(cmd, M.config.default_args)
  vim.list_extend(cmd, args)

  local output = {}
  local on_exit = function(obj)
    local result = {
      code = obj.code,
      stdout = table.concat(output, "\n"),
    }
    M._state.last_result = result

    if opts.on_complete then
      vim.schedule(function()
        opts.on_complete(result)
      end)
    end
  end

  vim.system(cmd, {
    text = true,
    stdout = function(_, data)
      if data then
        table.insert(output, data)
      end
    end,
  }, on_exit)
end

-- Run md2jira command synchronously
function M.run_sync(args)
  local cmd = { M._get_executable() }
  vim.list_extend(cmd, M.config.default_args)
  vim.list_extend(cmd, args)

  local result = vim.system(cmd, { text = true }):wait()
  M._state.last_result = {
    code = result.code,
    stdout = result.stdout or "",
    stderr = result.stderr or "",
  }
  return M._state.last_result
end

-- Detect epic key from current buffer
function M.detect_epic()
  local bufnr = vim.api.nvim_get_current_buf()
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, 50, false)

  for _, line in ipairs(lines) do
    -- Look for epic key patterns like PROJ-123
    local epic = line:match("([A-Z][A-Z0-9]+-[0-9]+)")
    if epic then
      M._state.last_epic = epic
      return epic
    end
  end

  return M._state.last_epic
end

-- Get current markdown file path
function M.get_markdown_path()
  local bufname = vim.api.nvim_buf_get_name(0)
  if bufname:match("%.md$") then
    return bufname
  end
  return nil
end

-- Validate current markdown file
function M.validate(opts)
  opts = opts or {}
  local path = opts.path or M.get_markdown_path()

  if not path then
    M._notify("No markdown file open", vim.log.levels.WARN)
    return
  end

  local args = { "--validate", "--markdown", path }

  if opts.strict then
    table.insert(args, "--strict")
  end

  M.run_async(args, {
    on_complete = function(result)
      if result.code == 0 then
        M._notify("✓ Validation passed", vim.log.levels.INFO)
      else
        M._notify("✗ Validation failed", vim.log.levels.ERROR)
        M._show_output(result.stdout, "Validation Results")
      end
    end,
  })
end

-- Sync current markdown file (dry-run)
function M.sync(opts)
  opts = opts or {}
  local path = opts.path or M.get_markdown_path()
  local epic = opts.epic or M.detect_epic()

  if not path then
    M._notify("No markdown file open", vim.log.levels.WARN)
    return
  end

  if not epic then
    epic = vim.fn.input("Epic key: ")
    if epic == "" then
      return
    end
    M._state.last_epic = epic
  end

  local args = { "--markdown", path, "--epic", epic }

  if opts.execute then
    table.insert(args, "--execute")
    table.insert(args, "--no-confirm")
  end

  M._notify("Syncing " .. path .. " to " .. epic .. "...", vim.log.levels.INFO)

  M.run_async(args, {
    on_complete = function(result)
      if result.code == 0 then
        local msg = opts.execute and "Sync completed" or "Dry-run completed"
        M._notify("✓ " .. msg, vim.log.levels.INFO)
      else
        M._notify("✗ Sync failed", vim.log.levels.ERROR)
      end
      M._show_output(result.stdout, "Sync Results")
    end,
  })
end

-- Sync with execute (actually make changes)
function M.sync_execute(opts)
  opts = opts or {}
  opts.execute = true
  M.sync(opts)
end

-- Show dashboard
function M.dashboard(opts)
  opts = opts or {}
  local path = opts.path or M.get_markdown_path()
  local epic = opts.epic or M.detect_epic()

  local args = { "--dashboard" }

  if path then
    vim.list_extend(args, { "--markdown", path })
  end

  if epic then
    vim.list_extend(args, { "--epic", epic })
  end

  local result = M.run_sync(args)
  M._show_output(result.stdout, "md2jira Dashboard")
end

-- Run init wizard
function M.init()
  local args = { "--init" }
  local result = M.run_sync(args)
  M._show_output(result.stdout, "md2jira Setup")
end

-- Parse stories from current buffer
function M.parse_stories()
  local bufnr = vim.api.nvim_get_current_buf()
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  local stories = {}

  for i, line in ipairs(lines) do
    -- Match story headers like "### 📋 US-001: Title" or "### US-001: Title"
    local id, title = line:match("^###%s+[📋✅🔄⏸️]*%s*([A-Z]+-[0-9]+):%s*(.+)")
    if id and title then
      table.insert(stories, {
        id = id,
        title = title,
        line = i,
      })
    end
  end

  return stories
end

-- Jump to story by ID
function M.goto_story(story_id)
  local stories = M.parse_stories()
  for _, story in ipairs(stories) do
    if story.id == story_id then
      vim.api.nvim_win_set_cursor(0, { story.line, 0 })
      vim.cmd("normal! zz")
      return true
    end
  end
  return false
end

-- Show output in floating window
function M._show_output(content, title)
  local lines = vim.split(content or "", "\n")

  -- Calculate dimensions
  local width = math.floor(vim.o.columns * M.config.float.width)
  local height = math.floor(vim.o.lines * M.config.float.height)
  local row = math.floor((vim.o.lines - height) / 2)
  local col = math.floor((vim.o.columns - width) / 2)

  -- Create buffer
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].filetype = "md2jira"

  -- Create window
  local win = vim.api.nvim_open_win(buf, true, {
    relative = "editor",
    width = width,
    height = height,
    row = row,
    col = col,
    style = "minimal",
    border = M.config.float.border,
    title = title and (" " .. title .. " ") or nil,
    title_pos = "center",
  })

  -- Keymaps for the floating window
  vim.keymap.set("n", "q", function()
    vim.api.nvim_win_close(win, true)
  end, { buffer = buf })

  vim.keymap.set("n", "<Esc>", function()
    vim.api.nvim_win_close(win, true)
  end, { buffer = buf })
end

-- Send notification
function M._notify(msg, level)
  if M.config.notify then
    vim.notify(msg, level, { title = "md2jira" })
  end
end

-- Create user commands
function M._create_commands()
  vim.api.nvim_create_user_command("Md2JiraValidate", function(opts)
    M.validate({ strict = opts.bang })
  end, { bang = true, desc = "Validate markdown file" })

  vim.api.nvim_create_user_command("Md2JiraSync", function(opts)
    M.sync({ epic = opts.args ~= "" and opts.args or nil })
  end, { nargs = "?", desc = "Sync markdown to Jira (dry-run)" })

  vim.api.nvim_create_user_command("Md2JiraSyncExecute", function(opts)
    M.sync_execute({ epic = opts.args ~= "" and opts.args or nil })
  end, { nargs = "?", desc = "Sync markdown to Jira (execute)" })

  vim.api.nvim_create_user_command("Md2JiraDashboard", function()
    M.dashboard()
  end, { desc = "Show md2jira dashboard" })

  vim.api.nvim_create_user_command("Md2JiraInit", function()
    M.init()
  end, { desc = "Run md2jira init wizard" })

  vim.api.nvim_create_user_command("Md2JiraStories", function()
    M.telescope_stories()
  end, { desc = "Browse stories with Telescope" })
end

-- Setup keymaps
function M._setup_keymaps()
  local km = M.config.keymaps

  if km.validate then
    vim.keymap.set("n", km.validate, M.validate, { desc = "md2jira: Validate" })
  end

  if km.sync then
    vim.keymap.set("n", km.sync, M.sync, { desc = "md2jira: Sync (dry-run)" })
  end

  if km.sync_execute then
    vim.keymap.set("n", km.sync_execute, M.sync_execute, { desc = "md2jira: Sync (execute)" })
  end

  if km.dashboard then
    vim.keymap.set("n", km.dashboard, M.dashboard, { desc = "md2jira: Dashboard" })
  end

  if km.stories then
    vim.keymap.set("n", km.stories, M.telescope_stories, { desc = "md2jira: Find stories" })
  end

  if km.init then
    vim.keymap.set("n", km.init, M.init, { desc = "md2jira: Init" })
  end
end

-- Setup autocommands
function M._setup_autocmds()
  local group = vim.api.nvim_create_augroup("md2jira", { clear = true })

  -- Auto-detect epic on buffer enter
  if M.config.auto_detect_epic then
    vim.api.nvim_create_autocmd("BufEnter", {
      group = group,
      pattern = "*.md",
      callback = function()
        M.detect_epic()
      end,
    })
  end
end

-- Telescope integration
function M.telescope_stories()
  local ok, _ = pcall(require, "telescope")
  if not ok then
    M._notify("Telescope not available", vim.log.levels.WARN)
    -- Fallback to simple picker
    M._simple_story_picker()
    return
  end

  require("md2jira.telescope").stories()
end

-- Simple story picker (fallback when Telescope not available)
function M._simple_story_picker()
  local stories = M.parse_stories()

  if #stories == 0 then
    M._notify("No stories found in current buffer", vim.log.levels.WARN)
    return
  end

  local items = {}
  for _, story in ipairs(stories) do
    table.insert(items, string.format("%s: %s", story.id, story.title))
  end

  vim.ui.select(items, {
    prompt = "Select story:",
  }, function(choice, idx)
    if idx then
      M.goto_story(stories[idx].id)
    end
  end)
end

return M

