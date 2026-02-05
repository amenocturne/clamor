#!/usr/bin/env bash
# Hook wrapper script for link-proxy
# Called by Claude Code hooks, runs the Python hook handler

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_TYPE="${1:-}"

# Debug logging (enable with LINK_PROXY_DEBUG=1)
if [ "${LINK_PROXY_DEBUG:-}" = "1" ]; then
    LOG_FILE="${SCRIPT_DIR}/data/hook.log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$(date)] hook.sh called: HOOK_TYPE=$HOOK_TYPE" >> "$LOG_FILE"
fi

if [ -z "$HOOK_TYPE" ]; then
    echo "Usage: hook.sh <hook-type>" >&2
    exit 1
fi

# Run the hook handler
cd "$SCRIPT_DIR"
exec ./main.py "$HOOK_TYPE"
