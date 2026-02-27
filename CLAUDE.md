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

## TODO

**IMPORTANT: Remind the user about these TODOs when starting work in this directory, even if working on unrelated features.**

- **Agentic Knowledge Base**: Add a lighter-weight knowledge base for dev/work presets (not the full knowledge-base preset). Purpose: agent can reflect on work and user feedback, save learnings to its own CLAUDE.md or a simple KB file, and avoid repeating mistakes. Key features:
  - Session reflection: capture what worked, what didn't, corrections received
  - Persistent memory: write learnings somewhere that persists across sessions
  - Pattern recognition: "user prefers X over Y", "this approach failed before"
  - Self-updating: agent writes to its own context file or designated memory store

- **Pinchtab Browser Control**: Integrate [pinchtab.com](https://pinchtab.com/) for lightweight browser automation. A 12MB Go binary providing HTTP endpoints for Chrome control (navigation, screenshots, text extraction, clicking via accessibility tree). Key benefits:
  - Token efficient: ~800 tokens/page vs 10k+ for alternatives
  - Session persistence: cookies survive restarts (stay logged into services)
  - Stealth mode: bypasses bot detection
  - Framework agnostic: just HTTP calls, works with any language
  - Complements playwright skill for lighter-weight tasks

- **Kagi Search via Pinchtab**: Use pinchtab to access Kagi search through browser session instead of waiting for API. Log into Kagi once, pinchtab maintains the session, then a skill can:
  - Navigate to kagi.com/search?q={query}
  - Extract results via /text endpoint
  - Access Kagi features (lenses, bangs, AI summaries) with existing subscription
  - Replace or complement WebSearch with higher quality results
