# agent-kit justfile
# Run with: just <recipe>

# Default recipe - list all recipes
default:
    @just --list

# Reinstall all registered installations (falls back to interactive if no registry)
install: deny-read-install graph-colors-install
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

# Build and install clamor binary to ~/.local/bin
clamor-install:
    #!/usr/bin/env bash
    CLAMOR_DIR="tools/clamor"
    DAEMON_FILES="$CLAMOR_DIR/src/daemon.rs $CLAMOR_DIR/src/protocol.rs $CLAMOR_DIR/src/state.rs $CLAMOR_DIR/src/agent.rs $CLAMOR_DIR/Cargo.toml"
    NEW_HASH=$(cat $DAEMON_FILES | shasum -a 256 | cut -d' ' -f1)
    OLD_HASH=""
    [[ -f ~/.clamor/daemon.hash ]] && OLD_HASH=$(cat ~/.clamor/daemon.hash)

    NEED_RESUME=false

    if [ -S ~/.clamor/clamor.sock ]; then
        if [[ "$NEW_HASH" != "$OLD_HASH" ]]; then
            echo "Clamor daemon code changed — restart required."
            clamor pre-upgrade
            rc=$?
            if [[ $rc -ne 0 && $rc -le 128 ]]; then
                exit 0
            fi
            NEED_RESUME=true
        else
            echo "Daemon running — no daemon code changes, hot-swapping binary."
        fi
    fi

    cargo build --release --manifest-path "$CLAMOR_DIR/Cargo.toml"
    mkdir -p ~/.local/bin ~/.clamor
    rm -f ~/.local/bin/clamor
    cp "$CLAMOR_DIR/target/release/clamor" ~/.local/bin/clamor
    echo "$NEW_HASH" > ~/.clamor/daemon.hash
    echo "clamor installed to ~/.local/bin/clamor"

    if [[ "$NEED_RESUME" == "true" ]]; then
        echo ""
        echo "Resuming sessions..."
        clamor resume
    fi

# Build deny-read binary (debug)
deny-read-build:
    cargo build --manifest-path tools/deny-read/Cargo.toml

# Build and install deny-read binary to ~/.local/bin
deny-read-install:
    cargo build --release --manifest-path tools/deny-read/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/deny-read
    cp tools/deny-read/target/release/deny-read ~/.local/bin/deny-read
    @echo "deny-read installed to ~/.local/bin/deny-read"

# Build graph-colors binary (debug)
graph-colors-build:
    cargo build --manifest-path tools/graph-colors/Cargo.toml

# Build and install graph-colors binary to ~/.local/bin
graph-colors-install:
    cargo build --release --manifest-path tools/graph-colors/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/graph-colors
    cp tools/graph-colors/target/release/graph-colors ~/.local/bin/graph-colors
    @echo "graph-colors installed to ~/.local/bin/graph-colors"

# Aliases
alias i := install
alias l := list
alias w := workspace
alias f := fmt
