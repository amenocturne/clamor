# agent-kit

Personal toolkit for Claude Code: skills, hooks, pipelines, and composable presets.

Compatible with [skills.sh](https://skills.sh/).

## Quick Start

```bash
# Interactive preset selection
just install          # or: just i

# Specify presets directly
just install-to ~/projects/my-app base frontend

# List available presets
just list             # or: just l

# Generate WORKSPACE.yaml
just workspace ~/projects
```

Or without just:

```bash
uv run install.py
uv run install.py --presets base frontend --target ~/projects/my-app
uv run install.py --list
```

## What's Included

### Skills

| Skill | Description |
| ----- | ----------- |
| `knowledge-base` | Atomic knowledge management for Obsidian vaults |
| `youtube` | Fetch YouTube transcripts for processing |
| `spec` | Create technical specs from project ideas |

### Hooks

| Hook | Description |
| ---- | ----------- |
| `link-proxy` | URL masking for corporate environments |
| `notification` | System notification on session end |

### Pipelines

| Pipeline | Description |
| -------- | ----------- |
| `workspace` | Generate WORKSPACE.yaml from git repos |

### Presets

| Preset | Description |
| ------ | ----------- |
| `base` | Core defaults - commit style, code style, communication |
| `frontend` | Frontend development (React, Vue, etc.) |
| `backend` | Backend development |

## Manual Installation

If you prefer not to use presets:

```bash
# Install individual skills
npx skills add amenocturne/agent-kit/knowledge-base
npx skills add amenocturne/agent-kit/youtube
npx skills add amenocturne/agent-kit/spec
```

## Links

- [skills.sh](https://skills.sh/) — Claude Code skill registry
- [Claude Code](https://claude.com/claude-code) — Anthropic's CLI for Claude
