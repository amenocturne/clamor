# agent-kit justfile
# Run with: just <recipe>

# Default recipe - list all recipes
default:
    @just --list

# Install presets interactively
install:
    uv run install.py

# Install specific presets to a target directory
install-to target *presets:
    uv run install.py --presets {{ presets }} --target {{ target }}

# List available presets
list:
    uv run install.py --list

# Generate WORKSPACE.yaml for a directory
workspace root="." output="WORKSPACE.yaml":
    uv run pipelines/workspace/generate-workspace.py --root {{ root }} --output {{ output }}

# Run tests (placeholder)
test:
    @echo "No tests yet"

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

# Aliases
alias i := install
alias l := list
alias w := workspace
alias f := fmt
