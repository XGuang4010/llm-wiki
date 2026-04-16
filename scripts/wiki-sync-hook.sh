#!/usr/bin/env bash
# wiki-sync-hook.sh
# Example startup hook for Unix-like systems (Linux, macOS, WSL).
# Add this to your shell profile (.bashrc, .zshrc) or run it before starting your agent.

WIKI_ROOT="${WIKI_ROOT:-$HOME/wiki}"
SCANNER_SCRIPT="${WIKI_ROOT}/scripts/learning_scanner.py"
REPORT_FILE="/tmp/wiki_sync_report.json"

if [ ! -f "$SCANNER_SCRIPT" ]; then
    echo "[wiki-sync-hook] Scanner not found: $SCANNER_SCRIPT"
    return 0
fi

# Run scanner with auto-stage
python3 "$SCANNER_SCRIPT" \
    --wiki-root "$WIKI_ROOT" \
    --auto-stage \
    --output "$REPORT_FILE" \
    --update-index

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "[wiki-sync-hook] New learnings staged. Run '/wiki sync' in your agent to ingest them."
    # Optional: if your agent CLI supports it, auto-trigger:
    # opencode wiki sync "$WIKI_ROOT"
else
    echo "[wiki-sync-hook] No new learnings to sync."
fi
