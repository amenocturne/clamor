#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT="${LINK_PROXY_PORT:-18923}"
HEALTH_URL="http://127.0.0.1:${PORT}/health"

# Check if proxy is already running
if curl -sf --connect-timeout 2 "$HEALTH_URL" > /dev/null 2>&1; then
    exit 0
fi

# Start proxy in background
cd "$SCRIPT_DIR"
nohup uv run ./proxy.py --port "$PORT" \
    >> "$SCRIPT_DIR/data/proxy.log" 2>&1 &

# Wait for it to be ready (up to 10s)
for i in $(seq 1 20); do
    if curl -sf --connect-timeout 1 "$HEALTH_URL" > /dev/null 2>&1; then
        echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"[link-proxy] Proxy started on port '"$PORT"'"}}'
        exit 0
    fi
    sleep 0.5
done

echo "[link-proxy] ERROR: Proxy failed to start within 10s" >&2
echo "[link-proxy] Check $SCRIPT_DIR/data/proxy.log" >&2
exit 1
