#!/bin/bash
set -e

# GitHub Action Entrypoint for md2jira
# This script parses inputs and runs md2jira with the appropriate arguments

echo "🚀 md2jira GitHub Action"
echo "========================"

# Required inputs
MARKDOWN_FILE="${INPUT_MARKDOWN_FILE}"
EPIC_KEY="${INPUT_EPIC_KEY}"

# Validate required inputs
if [ -z "$MARKDOWN_FILE" ]; then
    echo "❌ Error: markdown-file input is required"
    exit 1
fi

if [ -z "$EPIC_KEY" ] && [ "$INPUT_PULL" != "true" ] && [ "$INPUT_MULTI_EPIC" != "true" ]; then
    echo "❌ Error: epic-key input is required (unless using pull or multi-epic mode)"
    exit 1
fi

# Check if markdown file exists
if [ ! -f "$MARKDOWN_FILE" ]; then
    echo "❌ Error: Markdown file not found: $MARKDOWN_FILE"
    exit 1
fi

# Build command arguments
CMD_ARGS=()

# Add markdown file
CMD_ARGS+=("--markdown" "$MARKDOWN_FILE")

# Add epic key if provided
if [ -n "$EPIC_KEY" ]; then
    CMD_ARGS+=("--epic" "$EPIC_KEY")
fi

# Execution mode
if [ "$INPUT_DRY_RUN" = "true" ]; then
    echo "📋 Mode: Dry-run (no changes will be made)"
elif [ "$INPUT_EXECUTE" = "true" ]; then
    CMD_ARGS+=("--execute")
    CMD_ARGS+=("--no-confirm")
    echo "⚡ Mode: Execute"
fi

# Sync phase
if [ -n "$INPUT_PHASE" ] && [ "$INPUT_PHASE" != "all" ]; then
    CMD_ARGS+=("--phase" "$INPUT_PHASE")
    echo "📌 Phase: $INPUT_PHASE"
fi

# Incremental mode
if [ "$INPUT_INCREMENTAL" = "true" ]; then
    CMD_ARGS+=("--incremental")
    echo "🔄 Incremental sync enabled"
fi

# Multi-epic mode
if [ "$INPUT_MULTI_EPIC" = "true" ]; then
    CMD_ARGS+=("--multi-epic")
    echo "📚 Multi-epic mode enabled"
    
    if [ -n "$INPUT_EPIC_FILTER" ]; then
        CMD_ARGS+=("--epic-filter" "$INPUT_EPIC_FILTER")
        echo "🔍 Epic filter: $INPUT_EPIC_FILTER"
    fi
fi

# Pull mode
if [ "$INPUT_PULL" = "true" ]; then
    CMD_ARGS+=("--pull")
    echo "⬇️ Pull mode enabled"
    
    if [ -n "$INPUT_PULL_OUTPUT" ]; then
        CMD_ARGS+=("--pull-output" "$INPUT_PULL_OUTPUT")
    fi
fi

# Backup
if [ "$INPUT_BACKUP" = "false" ]; then
    CMD_ARGS+=("--no-backup")
else
    echo "💾 Backup enabled"
fi

# Verbose
if [ "$INPUT_VERBOSE" = "true" ]; then
    CMD_ARGS+=("--verbose")
fi

# Export results
RESULT_FILE=""
if [ -n "$INPUT_EXPORT_RESULTS" ]; then
    RESULT_FILE="$INPUT_EXPORT_RESULTS"
    CMD_ARGS+=("--export" "$RESULT_FILE")
    echo "📤 Results will be exported to: $RESULT_FILE"
fi

# JSON output for parsing
CMD_ARGS+=("--output" "json")

echo ""
echo "📝 Syncing: $MARKDOWN_FILE"
if [ -n "$EPIC_KEY" ]; then
    echo "🎯 Epic: $EPIC_KEY"
fi
echo ""

# Run md2jira and capture output
set +e
OUTPUT=$(md2jira "${CMD_ARGS[@]}" 2>&1)
EXIT_CODE=$?
set -e

# Parse JSON output for GitHub outputs
echo "$OUTPUT"

# Try to extract stats from JSON output
if echo "$OUTPUT" | grep -q '"success"'; then
    # Extract values using grep and sed (portable)
    SUCCESS=$(echo "$OUTPUT" | grep -o '"success":[^,}]*' | sed 's/"success"://' | tr -d ' ')
    STORIES_MATCHED=$(echo "$OUTPUT" | grep -o '"stories_matched":[^,}]*' | sed 's/"stories_matched"://' | tr -d ' ')
    STORIES_UPDATED=$(echo "$OUTPUT" | grep -o '"stories_updated":[^,}]*' | sed 's/"stories_updated"://' | tr -d ' ')
    SUBTASKS_CREATED=$(echo "$OUTPUT" | grep -o '"subtasks_created":[^,}]*' | sed 's/"subtasks_created"://' | tr -d ' ')
    SUBTASKS_UPDATED=$(echo "$OUTPUT" | grep -o '"subtasks_updated":[^,}]*' | sed 's/"subtasks_updated"://' | tr -d ' ')
    COMMENTS_ADDED=$(echo "$OUTPUT" | grep -o '"comments_added":[^,}]*' | sed 's/"comments_added"://' | tr -d ' ')
    
    # Set GitHub outputs
    echo "success=${SUCCESS:-false}" >> "$GITHUB_OUTPUT"
    echo "stories-matched=${STORIES_MATCHED:-0}" >> "$GITHUB_OUTPUT"
    echo "stories-updated=${STORIES_UPDATED:-0}" >> "$GITHUB_OUTPUT"
    echo "subtasks-created=${SUBTASKS_CREATED:-0}" >> "$GITHUB_OUTPUT"
    echo "subtasks-updated=${SUBTASKS_UPDATED:-0}" >> "$GITHUB_OUTPUT"
    echo "comments-added=${COMMENTS_ADDED:-0}" >> "$GITHUB_OUTPUT"
    echo "errors=${EXIT_CODE}" >> "$GITHUB_OUTPUT"
    
    if [ -n "$RESULT_FILE" ]; then
        echo "result-file=${RESULT_FILE}" >> "$GITHUB_OUTPUT"
    fi
fi

# Print summary
echo ""
echo "========================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Sync completed successfully!"
else
    echo "❌ Sync completed with errors (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE

