#!/bin/bash
# Find fleet binary - check if it's in PATH first, then fallback to built binary
if command -v fleet &>/dev/null; then
    fleet hook
else
    DIR="$(cd "$(dirname "$0")" && pwd)"
    FLEET_BIN="$DIR/../../skills/fleet/target/release/fleet"
    if [ -x "$FLEET_BIN" ]; then
        "$FLEET_BIN" hook
    fi
fi
