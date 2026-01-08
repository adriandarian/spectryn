#!/bin/bash
# spectryn - Quick runner script
# 
# Usage:
#   ./run.sh EPIC.md PROJ-123           # Dry-run
#   ./run.sh EPIC.md PROJ-123 --execute # Execute

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check if installed
if ! python -c "import spectryn" 2>/dev/null; then
    echo "Installing spectryn..."
    pip install -e . -q
fi

# Run with arguments
python -m spectryn.cli.app "$@"
