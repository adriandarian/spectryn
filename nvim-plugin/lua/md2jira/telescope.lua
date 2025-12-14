-- Telescope integration for md2jira
-- Browse and jump to stories with fuzzy finding

local M = {}

local pickers = require("telescope.pickers")
local finders = require("telescope.finders")
local conf = require("telescope.config").values
local actions = require("telescope.actions")
local action_state = require("telescope.actions.state")
local entry_display = require("telescope.pickers.entry_display")

local md2jira = require("md2jira")

-- Create entry display for stories
local function make_display(entry)
  local displayer = entry_display.create({
    separator = " ",
    items = {
      { width = 10 },  -- ID
      { remaining = true },  -- Title
    },
  })

  return displayer({
    { entry.value.id, "TelescopeResultsIdentifier" },
    { entry.value.title, "TelescopeResultsNormal" },
  })
end

-- Stories picker
function M.stories(opts)
  opts = opts or {}

  local stories = md2jira.parse_stories()

  if #stories == 0 then
    vim.notify("No stories found in current buffer", vim.log.levels.WARN, { title = "md2jira" })
    return
  end

  pickers.new(opts, {
    prompt_title = "md2jira Stories",
    finder = finders.new_table({
      results = stories,
      entry_maker = function(entry)
        return {
          value = entry,
          display = make_display,
          ordinal = entry.id .. " " .. entry.title,
          lnum = entry.line,
        }
      end,
    }),
    sorter = conf.generic_sorter(opts),
    previewer = false,
    attach_mappings = function(prompt_bufnr, map)
      -- Default action: jump to story
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection then
          vim.api.nvim_win_set_cursor(0, { selection.lnum, 0 })
          vim.cmd("normal! zz")
        end
      end)

      -- Custom mappings
      map("i", "<C-y>", function()
        -- Copy story ID to clipboard
        local selection = action_state.get_selected_entry()
        if selection then
          vim.fn.setreg("+", selection.value.id)
          vim.notify("Copied: " .. selection.value.id, vim.log.levels.INFO)
        end
      end)

      map("i", "<C-s>", function()
        -- Sync this specific story
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection then
          md2jira.sync({ story = selection.value.id })
        end
      end)

      return true
    end,
  }):find()
end

-- Epics picker (for multi-epic projects)
function M.epics(opts)
  opts = opts or {}

  local bufnr = vim.api.nvim_get_current_buf()
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  local epics = {}
  local seen = {}

  for i, line in ipairs(lines) do
    -- Look for epic headers like "# 🚀 PROJ-100: Epic Title"
    local id, title = line:match("^#%s+[🚀]*%s*([A-Z][A-Z0-9]+-[0-9]+):%s*(.+)")
    if id and title and not seen[id] then
      seen[id] = true
      table.insert(epics, {
        id = id,
        title = title,
        line = i,
      })
    end
  end

  if #epics == 0 then
    vim.notify("No epics found in current buffer", vim.log.levels.WARN, { title = "md2jira" })
    return
  end

  pickers.new(opts, {
    prompt_title = "md2jira Epics",
    finder = finders.new_table({
      results = epics,
      entry_maker = function(entry)
        return {
          value = entry,
          display = make_display,
          ordinal = entry.id .. " " .. entry.title,
          lnum = entry.line,
        }
      end,
    }),
    sorter = conf.generic_sorter(opts),
    previewer = false,
    attach_mappings = function(prompt_bufnr, _)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection then
          vim.api.nvim_win_set_cursor(0, { selection.lnum, 0 })
          vim.cmd("normal! zz")
        end
      end)
      return true
    end,
  }):find()
end

-- Commands picker (all md2jira commands)
function M.commands(opts)
  opts = opts or {}

  local commands = {
    { name = "Validate", desc = "Validate markdown file", fn = md2jira.validate },
    { name = "Sync (dry-run)", desc = "Preview sync changes", fn = md2jira.sync },
    { name = "Sync (execute)", desc = "Execute sync changes", fn = md2jira.sync_execute },
    { name = "Dashboard", desc = "Show status dashboard", fn = md2jira.dashboard },
    { name = "Init", desc = "Run setup wizard", fn = md2jira.init },
    { name = "Find Stories", desc = "Browse stories", fn = M.stories },
  }

  pickers.new(opts, {
    prompt_title = "md2jira Commands",
    finder = finders.new_table({
      results = commands,
      entry_maker = function(entry)
        return {
          value = entry,
          display = entry.name .. " - " .. entry.desc,
          ordinal = entry.name .. " " .. entry.desc,
        }
      end,
    }),
    sorter = conf.generic_sorter(opts),
    attach_mappings = function(prompt_bufnr, _)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection and selection.value.fn then
          selection.value.fn()
        end
      end)
      return true
    end,
  }):find()
end

-- Register as Telescope extension
return require("telescope").register_extension({
  setup = function(ext_config, config)
    -- Extension setup if needed
  end,
  exports = {
    stories = M.stories,
    epics = M.epics,
    commands = M.commands,
    md2jira = M.commands,  -- Alias
  },
})

