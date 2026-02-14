# agent-kit

Personal toolkit for Claude Code: skills, hooks, pipelines, and composable presets.

Compatible with [skills.sh](https://skills.sh/).

## How It Works

```
agent-kit/
├── skills/           # Self-contained skill folders (SKILL.md + scripts, templates, etc.)
├── hooks/            # Event-triggered scripts (stop, pre-tool-use, etc.)
├── pipelines/        # Data processing pipelines
├── presets/          # Recipes that bundle skills + hooks + pipelines + instructions
├── install.py        # Installer: symlinks components into target projects
└── justfile          # Task runner shortcuts
```

**Presets** are recipes that declare which skills, hooks, and pipelines to install together. Each preset has a `manifest.yaml` listing its components and a `claude.md` with agent instructions.

**Skills** follow the [skills.sh](https://skills.sh/) format — each is a folder with a `SKILL.md` (YAML frontmatter + markdown instructions) and optional scripts, templates, or sub-documents. Skills are symlinked into `.claude/skills/` so Claude Code auto-loads them.

**The installer** (`install.py`) reads a preset's manifest, then:
1. Symlinks skills → `.claude/skills/<name>/`
2. Symlinks hooks → `hooks/<name>/`
3. Symlinks pipelines → `pipelines/<name>/`
4. Copies instruction files → `.claude/instructions/`
5. Merges hook configs into `.claude/settings.json`
6. Writes preset instructions to `.claude/CLAUDE.md`

Root `CLAUDE.md` is left untouched for your project-specific instructions. Both files are loaded by Claude Code at startup.

## Quick Start

```bash
# Interactive preset selection
just install          # or: just i

# Specify presets directly
just install-to ~/projects/my-app knowledge-base

# List available presets
just list             # or: just l
```

Or without just:

```bash
uv run install.py
uv run install.py --presets knowledge-base --target ~/projects/my-app
uv run install.py --list
```

## What's Included

### Skills

| Skill | Description |
| ----- | ----------- |
| `youtube` | Fetch YouTube transcripts for processing |
| `transcribe` | Transcribe audio with Whisper (local) or API |
| `spec` | Create technical specs from project ideas |
| `commit-style` | Commit message conventions |
| `uv-over-python` | Always use uv instead of python/pip |

### Hooks

| Hook | Description |
| ---- | ----------- |
| `link-proxy` | URL masking for corporate environments |
| `notification` | System notification on session end |
| `save-conversation` | Auto-save transcripts and commit on Stop |

### Pipelines

| Pipeline | Description |
| -------- | ----------- |
| `workspace` | Generate WORKSPACE.yaml from git repos |

### Presets

| Preset | Description |
| ------ | ----------- |
| `knowledge-base` | Obsidian vault with atomic notes, sources, and auto-saving |

## Preset Architecture

Presets can include instructions in two ways:

### 1. Embedded in `claude.md`

Instructions that should always be active go directly in the preset's `claude.md`. These are loaded automatically at conversation start.

```
presets/my-preset/
├── manifest.yaml
└── claude.md         # Core instructions embedded here
```

### 2. Action-specific instruction files

Instructions for specific actions (saving, linking, processing sources) go in separate files. The agent reads these when performing that action.

```
presets/my-preset/
├── manifest.yaml
├── claude.md                    # References instruction files
└── instructions/
    ├── linking.md               # Read when creating/updating links
    ├── saving.md                # Read when saving conversations
    └── sources.md               # Read when processing sources
```

In `claude.md`, reference these with `@` imports:

```markdown
## Action-Specific Instructions

- **Creating notes with links**: Read @.claude/instructions/linking.md first
- **Saving conversations**: Read @.claude/instructions/saving.md first
```

### Why this split?

- **Embedded instructions** are always in context — folder structure, naming conventions, communication style
- **Action-specific files** are read on-demand — keeps context focused, agent reads when needed
- **Skills remain atomic** — complex workflows live in presets, not skills

## Skill Format

Each skill is a self-contained folder:

```
my-skill/
├── SKILL.md          # Required: frontmatter + instructions
├── metadata.json     # Metadata for discovery (name, version, keywords, etc.)
├── scripts/          # Optional: executable scripts
└── templates/        # Optional: note/file templates
```

`SKILL.md` uses YAML frontmatter:

```yaml
---
name: my-skill
description: What this skill does
author: your-name
---

# My Skill

Instructions for the agent...
```

Script paths in SKILL.md are relative to the skill folder.

### Atomicity Principle

Skills must be **self-contained and independent**:

- A skill must not reference or depend on other skills
- Cross-skill integration (e.g. "if youtube fails, use transcribe") belongs in the **preset**, not in skills
- Tool-specific workflows that combine multiple skills belong in the preset's `claude.md`
- Skills describe *what they do*, presets describe *how to use them together*

## Manual Installation

If you prefer not to use presets:

```bash
npx skills add amenocturne/agent-kit@youtube
npx skills add amenocturne/agent-kit@spec
npx skills add amenocturne/agent-kit@transcribe
```

## Links

- [skills.sh](https://skills.sh/) — Claude Code skill registry
- [Claude Code](https://claude.com/claude-code) — Anthropic's CLI for Claude
