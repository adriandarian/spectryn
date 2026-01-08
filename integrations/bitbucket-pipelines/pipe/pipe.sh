#!/bin/bash
# Spectra Bitbucket Pipe
# Syncs markdown specifications to issue trackers

set -e

echo "🚀 Spectra Bitbucket Pipe"
echo "========================="

# Install spectryn
pip install --quiet spectryn
spectryn --version

# Validate required inputs
if [ -z "$MARKDOWN_FILE" ]; then
    echo "❌ Error: MARKDOWN_FILE is required"
    exit 1
fi

if [ ! -f "$MARKDOWN_FILE" ]; then
    echo "❌ Error: Markdown file not found: $MARKDOWN_FILE"
    exit 1
fi

if [ -z "$EPIC_KEY" ] && [ "$MULTI_EPIC" != "true" ]; then
    echo "❌ Error: EPIC_KEY is required (unless using multi-epic mode)"
    exit 1
fi

# Build command
CMD="spectryn sync --markdown $MARKDOWN_FILE --tracker ${TRACKER:-jira}"

# Add epic key if provided
if [ -n "$EPIC_KEY" ]; then
    CMD="$CMD --epic $EPIC_KEY"
fi

# Execution mode
if [ "$DRY_RUN" = "true" ]; then
    echo "📋 Mode: Dry-run (no changes will be made)"
elif [ "$EXECUTE" = "true" ]; then
    CMD="$CMD --execute --no-confirm"
    echo "⚡ Mode: Execute"
fi

# Sync phase
if [ -n "$PHASE" ] && [ "$PHASE" != "all" ]; then
    CMD="$CMD --phase $PHASE"
    echo "📌 Phase: $PHASE"
fi

# Incremental mode
if [ "$INCREMENTAL" = "true" ]; then
    CMD="$CMD --incremental"
    echo "🔄 Incremental sync enabled"
fi

# Multi-epic mode
if [ "$MULTI_EPIC" = "true" ]; then
    CMD="$CMD --multi-epic"
    echo "📚 Multi-epic mode enabled"
    if [ -n "$EPIC_FILTER" ]; then
        CMD="$CMD --epic-filter $EPIC_FILTER"
    fi
fi

# Backup
if [ "$BACKUP" = "true" ]; then
    CMD="$CMD --backup"
fi

# Verbose
if [ "$VERBOSE" = "true" ]; then
    CMD="$CMD --verbose"
fi

# Export results
if [ -n "$EXPORT_RESULTS" ]; then
    CMD="$CMD --export $EXPORT_RESULTS"
fi

# Debug mode
if [ "$DEBUG" = "true" ]; then
    set -x
fi

echo ""
echo "Running: $CMD"
echo ""

# Execute
eval $CMD

echo ""
echo "✅ Spectra sync complete!"
