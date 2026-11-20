#!/usr/bin/env bash
set -euo pipefail

# Resolve project root directory (even when invoked from elsewhere or via symlink)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/venv"
ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
MAIN_SCRIPT="$SCRIPT_DIR/main_ui.py"

if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "Error: Virtual environment not found at $VENV_DIR" >&2
    echo "Please run ./setup_ubuntu.sh first to set up the environment." >&2
    exit 1
fi

if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "Error: Entry script not found at $MAIN_SCRIPT" >&2
    exit 1
fi

# Activate virtual environment and launch the UI
# shellcheck disable=SC1090
source "$ACTIVATE_SCRIPT"

exec python "$MAIN_SCRIPT" "$@"
