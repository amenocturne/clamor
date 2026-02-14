# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

agent-kit is a personal toolkit for Claude Code, providing skills, hooks, pipelines, and composable presets. It's compatible with [skills.sh](https://skills.sh/).

## Common Commands

```bash
# Install preset (interactive)
just install            # or: uv run install.py

# Install preset to target directory
just install-to ~/projects/my-app knowledge-base

# List available presets
just list               # or: uv run install.py --list

# Format and lint
just fmt                # ruff format .
just lint               # ruff check .

# Generate WORKSPACE.yaml
just workspace <root> <output>
```

## Architecture

```
agent-kit/
├── skills/         # Self-contained skill folders (SKILL.md + scripts)
├── hooks/          # Event-triggered scripts (stop, pre-tool-use)
├── pipelines/      # Data processing pipelines
├── presets/        # Recipes bundling skills + hooks + instructions
└── install.py      # Installer: symlinks components into target projects
```

### Presets

Presets are recipes declared in `manifest.yaml` that specify which skills, hooks, and pipelines to install together. Each preset has:
- `manifest.yaml` — lists components (skills, hooks, pipelines, external)
- `claude.md` — core agent instructions (embedded, always loaded)
- `instructions/` — action-specific instruction files (read on-demand via `@` imports)
- `templates/` — note/file templates
- `settings.json` — optional Claude settings to merge

### Skills (skills.sh format)

Each skill is a folder with:
- `SKILL.md` — YAML frontmatter + instructions (required)
- `metadata.json` — discovery metadata
- `scripts/` — executable scripts (paths in SKILL.md are relative to skill folder)
- `templates/` — optional templates

**Atomicity principle**: Skills must be self-contained and independent. Cross-skill integration belongs in presets, not skills.

### Hooks

Each hook folder contains:
- `hook.py` or `hook.sh` — the hook script
- `hooks.json` — configuration with `{hook_dir}` placeholder
- `README.md` — documentation

### Installer (`install.py`)

The installer reads a preset's manifest and symlinks everything for auto-sync:
1. Symlinks `.claude/CLAUDE.md` → preset's `claude.md`
2. Symlinks `.claude/instructions/` → preset's `instructions/`
3. Symlinks `.claude/templates/` → preset's `templates/`
4. Symlinks `.claude/skills/<name>/` → skill folders
5. Symlinks `.claude/hooks/<name>/` → hook folders
6. Symlinks `pipelines/<name>/` → pipeline folders
7. Merges hook configs into `.claude/settings.json`

Root `CLAUDE.md` in target project is left untouched for project-specific instructions.

## Testing

Tests use pytest. Run from repo root:

```bash
pytest                              # all tests
pytest tests/test_install.py        # installer tests
pytest skills/youtube/              # skill-specific tests
```

## Script Dependencies

Scripts use PEP 723 inline metadata for dependencies. Run with `uv run`:

```bash
uv run skills/youtube/scripts/yt-subs.py <url>
uv run pipelines/workspace/generate-workspace.py --root .
```
