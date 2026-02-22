---
name: project-setup
description: Project scaffolding patterns. Use when creating new projects. Provides templates for justfile, CLAUDE.md, gitignore, and proper structure.
author: amenocturne
---

# Project Setup

Creating new projects with proper structure.

## Before Starting

1. **Check knowledge base** - Is there a project note in the configured knowledge base?
2. **Clarify scope** - What's the MVP? What's out of scope?
3. **Choose tech stack** - Based on requirements and preferences

## Directory Structure

Projects go in subdirectories of the workspace root.

Use lowercase with hyphens: `my-project`, not `MyProject` or `my_project`.

## Essential Files

Every project needs:

```
project/
├── .git/
├── .gitignore
├── CLAUDE.md        # AI context
├── README.md        # Human context
└── justfile         # Command aliases
```

## Justfile Conventions

### Standard Commands

Use these names consistently across all projects:

| Command | Purpose | Example |
|---------|---------|---------|
| `default` | Show help (just --list) | Always present |
| `setup` | Initial project setup, install deps | `uv sync`, `bun install` |
| `run [mode]` | Run the project | `just run` or `just run prod` |
| `build [mode]` | Compile/bundle | `just build` or `just build release` |
| `test [filter]` | Run tests | `just test` or `just test auth` |
| `lint` | Check code style | `ruff check`, `cargo clippy` |
| `fmt` | Format code | `ruff format`, `cargo fmt` |
| `fix` | Auto-fix lint issues | `ruff check --fix` |
| `clean` | Remove build artifacts | `rm -rf dist/`, `cargo clean` |
| `reset` | Full reset (clean + setup) | Clean everything, reinstall |
| `deploy [env]` | Deploy to environment | `just deploy` or `just deploy staging` |
| `release [version]` | Create release | Tag, build, publish |

### Using Arguments for Variants

Use recipe arguments instead of separate commands:

```just
# Good: single command with argument
run mode="dev":
    @if [ "{{mode}}" = "prod" ]; then \
        cargo run --release; \
    else \
        cargo run; \
    fi

# Usage: just run, just run dev, just run prod
```

```just
# Good: pass-through arguments
test *args:
    uv run pytest {{args}}

# Usage: just test, just test -k auth, just test --verbose
```

```just
# Avoid: separate commands for each variant
run-dev:
    cargo run
run-prod:
    cargo run --release
```

### Naming New Commands

Priority order:
1. **Short verb** if possible: `sync`, `push`, `check`, `repl`
2. **Verb-noun** if needed: `gen-types`, `update-deps`, `dump-db`
3. **Domain-specific** when appropriate: `migrate`, `seed`, `serve`

Rules:
- Lowercase with hyphens: `gen-types` not `genTypes`
- Verbs first: `update-deps` not `deps-update`
- No redundant prefixes: `test` not `run-tests`

### Template

```just
# Default: show available commands
default:
    @just --list

# Initial setup
setup:
    # uv sync / bun install / cargo build

# Run the project
run mode="dev":
    # Implementation varies by stack

# Build for production
build mode="release":
    # Implementation varies by stack

# Run tests
test *args:
    # uv run pytest {{args}} / bun test {{args}} / cargo test {{args}}

# Format code
fmt:
    # uv run ruff format . / bun run format / cargo fmt

# Lint code
lint:
    # uv run ruff check . / bun run lint / cargo clippy

# Auto-fix lint issues
fix:
    # uv run ruff check --fix . / bun run lint --fix

# Remove build artifacts
clean:
    # rm -rf dist/ / rm -rf node_modules/ / cargo clean

# Full reset
reset: clean setup
```

## CLAUDE.md Template

```markdown
# Project Name

One-line description.

## Commands

Run `just` to see all commands. Key ones:

just run        # Run in dev mode
just test       # Run tests
just lint       # Check code style

## Architecture

- src/          - Source code
- tests/        - Test files

## Key Patterns

(Add non-obvious patterns as they emerge)
```

## README.md Template

```markdown
# Project Name

What this project does and why.

## Setup

git clone ...
cd project
just setup

## Usage

just run
```

## .gitignore by Stack

### Python
```gitignore
__pycache__/
*.pyc
.venv/
.ruff_cache/
.pytest_cache/
*.egg-info/
dist/
.env
```

### TypeScript/Node
```gitignore
node_modules/
dist/
.cache/
*.log
.env
```

### Rust
```gitignore
target/
Cargo.lock  # for libraries, keep for binaries
```

## Tech-Specific Setup

### Python Project
```bash
mkdir project && cd project
git init
uv init
# Creates pyproject.toml and basic structure
```

### TypeScript Project
```bash
mkdir project && cd project
git init
bun init
# Creates package.json and basic structure
```

### Rust Project
```bash
cargo new project
cd project
# Creates Cargo.toml and src/main.rs
```

## After Setup

1. **Add to WORKSPACE.yaml** - Run `/workspace refresh`
2. **Create knowledge base note** - If significant project
3. **Initial commit** - `git add . && git commit -m "initial setup"`

## Project Checklist

Before starting development:

- [ ] Git initialized
- [ ] .gitignore configured
- [ ] justfile with basic commands
- [ ] CLAUDE.md with commands and architecture
- [ ] README.md with setup instructions
- [ ] Formatter/linter configured
- [ ] Basic test setup
