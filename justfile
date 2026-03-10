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
    if [ -S ~/.fleet/fleet.sock ]; then
        echo "Fleet daemon is running."
        read -rp "Stop daemon and install? [y/N] " answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            fleet stop 2>/dev/null || true
            echo "Daemon stopped, installing..."
        else
            echo "Make sure all agents finish, then you can safely install the newer version."
            exit 0
        fi
    fi
    cargo build --release --manifest-path tools/fleet/Cargo.toml
    mkdir -p ~/.local/bin
    rm -f ~/.local/bin/fleet
    cp tools/fleet/target/release/fleet ~/.local/bin/fleet
    echo "fleet installed to ~/.local/bin/fleet"

# Aliases
alias i := install
alias l := list
alias w := workspace
alias f := fmt
