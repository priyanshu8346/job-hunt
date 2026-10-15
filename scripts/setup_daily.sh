#!/usr/bin/env bash
# Sets up the macOS LaunchAgent to run the daily job digest automatically at 08:00 local time.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"

if [ ! -f "$PYTHON_BIN" ]; then
    echo "Virtual environment not found at $PYTHON_BIN"
    echo "Please create it first:"
    echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"
PLIST_FILE="$PLIST_DIR/com.jobhunt.daily.plist"

sed \
    -e "s|{{PYTHON_BIN}}|$PYTHON_BIN|g" \
    -e "s|{{RUNNER_SCRIPT}}|$ROOT/scripts/run_daily.py|g" \
    -e "s|{{PROJECT_DIR}}|$ROOT|g" \
    "$ROOT/scripts/com.jobhunt.daily.plist.template" > "$PLIST_FILE"

chmod 644 "$PLIST_FILE"
launchctl bootout "gui/$(id -u)/com.jobhunt.daily" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"

echo "LaunchAgent installed and loaded: $PLIST_FILE"
echo "Daily digest will run every day at 08:00 in your local timezone."
echo "Check status anytime with: launchctl print gui/\$(id -u)/com.jobhunt.daily"
