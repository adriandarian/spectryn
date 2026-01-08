# AI Fix

AI Fix is an intelligent assistant that helps you correct markdown formatting issues in your spectryn documents. When validation fails, AI Fix can guide you through repairs using AI-powered tools.

## Overview

spectryn's markdown parser requires specific formatting for stories, metadata, acceptance criteria, and subtasks. When your document doesn't match the expected format, AI Fix offers three ways to resolve issues:

1. **Format Guide** – View the complete format specification
2. **AI Prompt** – Get a copy-paste prompt for your favorite AI tool
3. **Auto-Fix** – Let a detected AI CLI tool fix the file automatically

## Quick Start

```bash
# Validate your markdown file
spectryn --validate --markdown EPIC.md

# If validation fails, you'll see AI Fix suggestions automatically
```

When validation fails, spectryn displays available options:

```
────────────────────────────────────────────────────────────────────
ℹ AI-Assisted Fix Available
────────────────────────────────────────────────────────────────────

Option 1: View format guide
  Run: spectryn --validate --markdown EPIC.md --show-guide

Option 2: Get AI fix prompt (copy to your AI tool)
  Run: spectryn --validate --markdown EPIC.md --suggest-fix

Option 3: Auto-fix with AI tool
  Available AI tools for auto-fix:
    1. Claude CLI (claude 1.0.5)
    2. Ollama (ollama version 0.5.0)
  Run: spectryn --validate --markdown EPIC.md --auto-fix --ai-tool claude
  Or interactively: spectryn --validate --markdown EPIC.md --auto-fix
```

## Option 1: Format Guide

View the complete spectryn markdown format specification:

```bash
spectryn --validate --markdown EPIC.md --show-guide
```

This displays a comprehensive guide covering:

- **Story headers** – Required format: `### [emoji] US-XXX: Story Title`
- **Metadata** – Priority, Story Points, and Status using bold labels
- **User story descriptions** – As a/I want/So that format
- **Acceptance criteria** – Checkbox format for testable criteria
- **Subtasks tables** – 5-column format with #, Subtask, Description, SP, Status
- **Valid status values** – Done, In Progress, Planned, Blocked, etc.
- **Valid priority values** – P0–P3, Critical, High, Medium, Low

Use this guide as a reference when manually fixing your documents.

## Option 2: AI Prompt (Copy-Paste)

Generate a prompt you can copy into any AI assistant (ChatGPT, Claude web, etc.):

```bash
spectryn --validate --markdown EPIC.md --suggest-fix
```

This outputs a prompt like:

```
Fix this markdown file (EPIC.md) to match the spectryn format.

Issues to fix:
- [MD001] Story header missing required format
- [MD003] Metadata section missing Priority field
- [MD005] User story description missing "As a" format

Required format:
- Story headers: ### [emoji] US-XXX: Title
- Metadata: **Priority**: X, **Story Points**: N, **Status**: X
- Description: **As a** role, **I want** feature, **So that** benefit
- Acceptance criteria: - [ ] criterion (checkbox format)
- Separate stories with ---

Paste your file content after this prompt, then I'll return the corrected version.
```

### How to Use

1. Run `spectryn --validate --markdown EPIC.md --suggest-fix`
2. Copy the generated prompt
3. Open your preferred AI tool (ChatGPT, Claude, Gemini, etc.)
4. Paste the prompt
5. Paste your markdown file content after the prompt
6. Copy the AI's corrected output back to your file
7. Re-validate: `spectryn --validate --markdown EPIC.md`

## Option 3: Auto-Fix (CLI Tools)

Auto-fix uses AI CLI tools installed on your system to automatically repair your markdown:

```bash
# Interactive mode (prompts you to select a tool)
spectryn --validate --markdown EPIC.md --auto-fix

# Specify a tool directly
spectryn --validate --markdown EPIC.md --auto-fix --ai-tool claude
```

### Supported AI CLI Tools

spectryn automatically detects these AI CLI tools:

| Tool | Command | Installation |
|------|---------|--------------|
| **Claude CLI** | `claude` | `pip install anthropic` then follow [Claude CLI setup](https://docs.anthropic.com/en/docs/claude-cli) |
| **Ollama** | `ollama` | [ollama.ai](https://ollama.ai) |
| **Aider** | `aider` | `pip install aider-chat` |
| **GitHub Copilot** | `gh copilot` | `gh extension install github/gh-copilot` |
| **Copilot CLI** | `copilot` | `npm install -g @githubnext/github-copilot-cli` |
| **Shell GPT** | `sgpt` | `pip install shell-gpt` |
| **LLM CLI** | `llm` | `pip install llm` |
| **Mods** | `mods` | [charmbracelet/mods](https://github.com/charmbracelet/mods) |

### List Detected Tools

Check which AI tools are available on your system:

```bash
spectryn --list-ai-tools
```

Output:
```
Available AI tools for auto-fix:
  1. Claude CLI (claude 1.0.5)
  2. Ollama (ollama version 0.5.0)
  3. Aider (aider 0.50.0)
```

### Auto-Fix Workflow

1. spectryn reads your markdown file
2. Generates a detailed prompt with:
   - List of validation errors
   - Format specifications
   - Current file content
3. Sends the prompt to the selected AI tool
4. Receives the corrected markdown
5. Writes the fixed content back to your file

::: warning Backup Your Files
Auto-fix modifies your file in place. Consider using version control or making a backup before running auto-fix.
:::

### Example Session

```bash
$ spectryn --validate --markdown stories.md --auto-fix

╭─────────────────────────────────────────────────────────────╮
│  spectryn Validate ✓                                         │
╰─────────────────────────────────────────────────────────────╯

File: stories.md

Validation Result: ✗ FAILED

Errors (3):
  ✗ [MD001] Line 5: Story header missing required format
  ✗ [MD003] Line 7: Metadata section missing Priority field
  ✗ [MD005] Line 12: User story description missing "As a" format

────────────────────────────────────────────────
AI Auto-Fix
────────────────────────────────────────────────

Select an AI tool for auto-fix:
  1. Claude CLI (claude 1.0.5)
  2. Ollama (ollama version 0.5.0)
  0. Cancel

Enter choice [1]: 1

Using Claude CLI to fix formatting issues...

✓ File has been fixed!
Run validation again to verify: spectryn --validate --markdown stories.md
```

## Troubleshooting

### "No AI CLI tools detected"

If no tools are found, install one of the supported tools:

```bash
# Recommended: Claude CLI (requires API key)
pip install anthropic

# Alternative: Ollama (free, runs locally)
# Visit https://ollama.ai for installation

# Alternative: LLM CLI (supports multiple providers)
pip install llm
```

### "AI tool not found or not installed"

The specified tool is not detected on your system:

```bash
# Check available tools
spectryn --list-ai-tools

# Use a different tool
spectryn --validate --markdown EPIC.md --auto-fix --ai-tool ollama
```

### "Command timed out"

AI processing has a 120-second timeout. For large files:

1. Split into smaller documents
2. Use a faster model (e.g., `ollama run llama3.2` instead of larger models)
3. Use the copy-paste method with a web-based AI

### "Failed to write fixed content"

Check file permissions:

```bash
# Ensure the file is writable
ls -la EPIC.md
chmod u+w EPIC.md
```

### AI output doesn't match expected format

Sometimes AI tools produce incomplete or incorrectly formatted output. If this happens:

1. Re-validate: `spectryn --validate --markdown EPIC.md`
2. Try a different AI tool: `spectryn --validate --markdown EPIC.md --auto-fix --ai-tool aider`
3. Use the copy-paste method for more control over the AI interaction
4. Manually fix remaining issues using the format guide

## Best Practices

### 1. Validate First

Always start with validation to understand the issues:

```bash
spectryn --validate --markdown EPIC.md
```

### 2. Start with Copy-Paste

For your first time, use `--suggest-fix` to understand what the AI is doing:

```bash
spectryn --validate --markdown EPIC.md --suggest-fix
```

### 3. Review AI Changes

After auto-fix, review the changes before syncing to Jira:

```bash
# Re-validate
spectryn --validate --markdown EPIC.md

# Review diff if using git
git diff EPIC.md
```

### 4. Use Version Control

Keep your markdown files in git to easily revert unwanted changes:

```bash
git add EPIC.md
git commit -m "Before AI fix"

spectryn --validate --markdown EPIC.md --auto-fix

# If something went wrong:
git checkout EPIC.md
```

## Reporting Issues

If you encounter problems with AI Fix:

### 1. Gather Information

```bash
# Get spectryn version
spectryn --version

# List detected tools
spectryn --list-ai-tools

# Run with verbose output
spectryn --validate --markdown EPIC.md --auto-fix -v
```

### 2. Create a Minimal Reproduction

Create a small markdown file that demonstrates the issue:

```markdown
# Test Epic

## User Stories

---

### STORY-001: Test Story

This is a minimal test case.
```

### 3. Open an Issue

Report issues at: [github.com/adriandarian/spectryn/issues](https://github.com/adriandarian/spectryn/issues)

Include:
- spectryn version
- Operating system
- AI tool used and version
- Error message or unexpected behavior
- Minimal markdown file to reproduce (if possible)
- Expected vs actual behavior

### 4. Check Existing Issues

Search for similar issues before creating a new one:

- [AI Fix issues](https://github.com/adriandarian/spectryn/labels/ai-fix)
- [Validation issues](https://github.com/adriandarian/spectryn/labels/validation)

## Related Documentation

- [Validation Reference](/reference/cli#validation-options) – Complete validation CLI options
- [AI Prompts Guide](/guide/ai-prompts) – Prompts for generating new epic documents
- [AI Agents Guide](/guide/agents) – Context for AI coding assistants working on spectryn
- [Exit Codes](/reference/exit-codes) – Understanding spectryn exit codes
- [Configuration](/guide/configuration) – Configure spectryn behavior

