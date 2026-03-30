# agent-kit justfile
# Run with: just <recipe>

# Default recipe - list all recipes
default:
    @just --list

# Reinstall all registered installations (falls back to interactive if no registry)
install: deny-read-install smart-approve-install graph-colors-install generate-workspace-install notification-install
    uv run install.py --all

# Install interactively (choose profile and agents)
install-interactive:
    uv run install.py

# Install profile + agents to a target directory
install-to target profile +agents kb="":
    uv run install.py --profile {{ profile }} --agents {{ agents }} --target {{ target }} {{ if kb != "" { "--knowledge-base " + kb } else { "" } }}

# List available profiles and agents
list:
    uv run install.py --list

# Generate WORKSPACE.yaml for a directory
workspace root="." output="WORKSPACE.yaml":
    generate-workspace --root {{ root }} --output {{ output }}

# Run tests
test:
    uv run --with pytest pytest tests/test_install.py tests/test_agent_installers.py -v
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

    if [ -S ~/.clamor/clamor.sock ]; then
        if [[ "$NEW_HASH" != "$OLD_HASH" ]]; then
            echo "Clamor daemon code changed — restart required."
            clamor pre-upgrade
            rc=$?
            if [[ $rc -ne 0 && $rc -le 128 ]]; then
                exit 0
            fi
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

# Build generate-workspace binary (debug)
generate-workspace-build:
    cargo build --manifest-path tools/generate-workspace/Cargo.toml

# Build and install generate-workspace binary to ~/.local/bin
generate-workspace-install:
    cargo build --release --manifest-path tools/generate-workspace/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/generate-workspace
    cp tools/generate-workspace/target/release/generate-workspace ~/.local/bin/generate-workspace
    @echo "generate-workspace installed to ~/.local/bin/generate-workspace"

# Build notification binary (debug)
notification-build:
    cargo build --manifest-path tools/notification/Cargo.toml

# Build and install notification binary to ~/.local/bin
notification-install:
    cargo build --release --manifest-path tools/notification/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/notification
    cp tools/notification/target/release/notification ~/.local/bin/notification
    @echo "notification installed to ~/.local/bin/notification"

# Build smart-approve binary (debug)
smart-approve-build:
    cargo build --manifest-path tools/smart-approve/Cargo.toml

# Build and install smart-approve binary to ~/.local/bin
smart-approve-install:
    cargo build --release --manifest-path tools/smart-approve/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/smart-approve
    cp tools/smart-approve/target/release/smart-approve ~/.local/bin/smart-approve
    @echo "smart-approve installed to ~/.local/bin/smart-approve"

# Aliases
alias i := install
alias l := list
alias w := workspace
alias f := fmt
