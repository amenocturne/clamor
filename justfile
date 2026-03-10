# agent-kit justfile
# Run with: just <recipe>

# Default recipe - list all recipes
default:
    @just --list

# Reinstall all registered installations (falls back to interactive if no registry)
install:
    uv run install.py --all

# Install preset interactively
install-interactive:
    uv run install.py

# Install preset to a target directory
install-to target preset kb="":
    uv run install.py --preset {{ preset }} --target {{ target }} {{ if kb != "" { "--knowledge-base " + kb } else { "" } }}

# List available presets
list:
    uv run install.py --list

# Generate WORKSPACE.yaml for a directory
workspace root="." output="WORKSPACE.yaml":
    uv run pipelines/workspace/generate-workspace.py --root {{ root }} --output {{ output }}

# Run tests
test:
    cd hooks/link-proxy && uv run pytest tests/ -v

# Format all Python files
fmt:
    ruff format .

# Lint all Python files
lint:
    ruff check .

# Clean generated files
clean:
    rm -rf .venv __pycache__ .ruff_cache
    find . -name "*.pyc" -delete
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Build and install fleet binary to ~/.local/bin
fleet-install:
    #!/usr/bin/env bash
    FLEET_DIR="tools/fleet"
    DAEMON_FILES="$FLEET_DIR/src/daemon.rs $FLEET_DIR/src/protocol.rs $FLEET_DIR/src/state.rs $FLEET_DIR/src/agent.rs $FLEET_DIR/Cargo.toml"
    NEW_HASH=$(cat $DAEMON_FILES | shasum -a 256 | cut -d' ' -f1)
    OLD_HASH=""
    [[ -f ~/.fleet/daemon.hash ]] && OLD_HASH=$(cat ~/.fleet/daemon.hash)

    NEED_RESTART=false
    NEED_RESUME=false

    if [ -S ~/.fleet/fleet.sock ]; then
        if [[ "$NEW_HASH" != "$OLD_HASH" ]]; then
            echo "Fleet daemon code changed — restart required."

            TOTAL=0
            RESUMABLE=0
            LOST_NAMES=""
            if [[ -f ~/.fleet/state.json ]]; then
                TOTAL=$(jq '[.agents // {} | to_entries[]] | length' ~/.fleet/state.json 2>/dev/null || echo 0)
                RESUMABLE=$(jq '[.agents // {} | to_entries[] | select(.value.session_id != null)] | length' ~/.fleet/state.json 2>/dev/null || echo 0)
                LOST_NAMES=$(jq -r '[.agents // {} | to_entries[] | select(.value.session_id == null) | "    \(.value.id) \(.value.title)"] | join("\n")' ~/.fleet/state.json 2>/dev/null || echo "")
            fi

            if [[ "$TOTAL" -gt 0 ]]; then
                echo ""
                LOST=$((TOTAL - RESUMABLE))
                if [[ "$LOST" -eq 0 ]]; then
                    echo "$TOTAL session(s) — all will auto-resume after upgrade."
                elif [[ "$RESUMABLE" -eq 0 ]]; then
                    echo "$TOTAL session(s) will be lost (no claude session ID captured):"
                    echo "$LOST_NAMES"
                else
                    echo "$RESUMABLE of $TOTAL session(s) will auto-resume after upgrade."
                    echo ""
                    echo "$LOST will be lost (no claude session ID captured):"
                    echo "$LOST_NAMES"
                fi
                echo ""
                read -rp "Proceed? [y/N] " answer
                if [[ "$answer" =~ ^[Yy]$ ]]; then
                    NEED_RESTART=true
                    [[ "$RESUMABLE" -gt 0 ]] && NEED_RESUME=true
                else
                    echo "Skipping install. Run 'just fleet-install' later."
                    exit 0
                fi
            else
                read -rp "Stop daemon and install? [y/N] " answer
                if [[ "$answer" =~ ^[Yy]$ ]]; then
                    NEED_RESTART=true
                else
                    echo "Skipping install. Run 'just fleet-install' later."
                    exit 0
                fi
            fi

            fleet stop 2>/dev/null || true
            echo "Daemon stopped."
        else
            echo "Daemon running — no daemon code changes, hot-swapping binary."
        fi
    fi

    cargo build --release --manifest-path "$FLEET_DIR/Cargo.toml"
    mkdir -p ~/.local/bin ~/.fleet
    rm -f ~/.local/bin/fleet
    cp "$FLEET_DIR/target/release/fleet" ~/.local/bin/fleet
    echo "$NEW_HASH" > ~/.fleet/daemon.hash
    echo "fleet installed to ~/.local/bin/fleet"

    if [[ "$NEED_RESUME" == "true" ]]; then
        echo ""
        echo "Resuming sessions..."
        fleet resume
    fi

# Aliases
alias i := install
alias l := list
alias w := workspace
alias f := fmt
