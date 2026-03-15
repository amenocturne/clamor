# Agentic Kit

Dotfiles for Claude Code agents. Small, composable tools — skills, hooks, and presets — that shape how your agent thinks, works, and responds. Unix philosophy: each piece does one thing well, presets compose them.

## Why

Claude Code has skills, hooks, and settings — but no way to compose them. You manually copy SKILL.md files, wire up hooks in settings.json, write CLAUDE.md instructions by hand, and repeat the whole thing for every project.

Agentic Kit treats agent configuration like dotfiles: declare what you want in a manifest, run the installer, get a reproducible environment. Change a skill or instruction once, reinstall, and every project picks up the update.

## How It Relates to Claude Code

Agentic Kit doesn't extend Claude Code's runtime. It manages the config files that Claude Code already reads:

**Claude Code reads natively** | **Agentic Kit adds**
--- | ---
`.claude/skills/*/SKILL.md` | Presets: declarative manifests bundling skills + hooks + instructions
`.claude/settings.json` | Common files: reusable instruction fragments with dependency validation
`.claude/CLAUDE.md` | Symlink management: edit once, propagate everywhere
 | Registry: track installations across projects

After installation, Claude Code has no idea Agentic Kit exists — it just sees its normal config files. Skills are individual primitives. Presets are curated bundles with composition logic on top.

## Quick Start

```bash
# Install a preset to a target directory
just install-to ~/projects/my-app dev-workspace

# Reinstall all registered targets (after modifying skills/hooks/instructions)
just install          # or: just i

# First-time interactive setup
just install-interactive

# List available presets
just list             # or: just l
```

Or without just:

```bash
uv run install.py --preset dev-workspace --target ~/projects/my-app
uv run install.py                    # reinstall all registered targets
uv run install.py --list
```

## What Gets Installed

Running `just install-to ~/projects dev-workspace` produces:

```
~/projects/
├── .claude/
│   ├── CLAUDE.md              # Generated from preset template + common files
│   ├── settings.json          # Merged hook configs and permissions
│   ├── agentic-kit.json       # Paths to agentic-kit and knowledge base
│   ├── skills/
│   │   ├── workspace/  →      # Symlinks to agentic-kit/skills/*
│   │   ├── checkpoint/ →
│   │   └── ...
│   └── hooks/
│       ├── notification/ →    # Symlinks to agentic-kit/hooks/*
│       ├── clamor/       →
│       └── ...
└── WORKSPACE.yaml             # Project index (from template, if not present)
```

**Symlinked** (live-linked, updates propagate automatically): skills, hooks, pipelines
**Generated** (written once per install): CLAUDE.md, settings.json, agentic-kit.json

## Architecture

```
agentic-kit/
├── skills/           # 28 self-contained skill folders
├── hooks/            # 9 event-triggered scripts
├── presets/          # 3 composable installation recipes
├── common/           # 6 reusable instruction fragments
├── pipelines/        # Data processing pipelines
├── tools/            # External tools (clamor)
├── install.py        # Core installer
└── installations.yaml  # Registry of installed presets
```

### Presets

A preset is a manifest (`manifest.yaml`) that declares which components to install, plus a template (`claude.md`) for generating project instructions.

```yaml
# presets/dev-workspace/manifest.yaml
description: Multi-project development workspace
skills:
  - workspace
  - orchestrator
  - checkpoint
  - review
  - ...
hooks:
  - notification
  - workflow-check
  - clamor
common:
  - dev-workflow        # Reusable instruction fragment
  - code-conventions
  - git
external:
  - github.com/anthropics/skills/skill-creator
```

The installer reads the manifest, symlinks all components, processes `{{include:common/git.md}}` directives in the template, validates that common files' required skills are present, merges hook configs from each hook's `hooks.json`, and writes the final `.claude/CLAUDE.md`.

Components are symlinked, not copied — editing a skill in Agentic Kit and running `just install` updates every project that uses it. No duplication, no drift.

### Common Files

Reusable instruction fragments shared across presets. Each can declare required skills:

```markdown
---
required_skills:
  - orchestrator
  - todo
  - review
---

## Dev Workflow

Every non-trivial task follows this cycle: ...
```

The installer validates that all required skills are present in the preset before including the fragment.

### Skills

Skills follow the [skills.sh](https://skills.sh/) format — a folder with a `SKILL.md` (YAML frontmatter + markdown instructions) and optional scripts or templates. Compatible with the skills.sh registry for individual installation. Skills are **atomic and independent**: they don't reference each other. Cross-skill workflows belong in presets.

```
my-skill/
├── SKILL.md          # Required: frontmatter + instructions
├── scripts/          # Optional: executable scripts
└── templates/        # Optional: file templates
```

### Hooks

Event-triggered scripts that Claude Code executes at specific moments (session start, tool use, session end). Each hook has a `hooks.json` declaring which events it listens to. The installer merges all hook configs into `.claude/settings.json`.

### Registry

`installations.yaml` tracks every installed preset and its target path. Running `just install` reinstalls all entries — useful after modifying any skill, hook, or instruction in Agentic Kit.

## Presets

| Preset | Skills | Hooks | Focus |
| ------ | ------ | ----- | ----- |
| `dev-workspace` | 20 | 6 | Multi-project development, orchestration, code review |
| `knowledge-base` | 18 | 6 | Obsidian vault, atomic notes, auto-saving, zettelkasten |
| `work` | 16 | 5 | Scala/infrastructure, Jira, GitLab, corporate tooling |

## Skills

| Skill | Description |
| ----- | ----------- |
| `brainstorm` | Creative exploration for vague ideas |
| `checkpoint` | Verify, commit, and review in one step |
| `config` | Configuration and infrastructure patterns (Ansible, Docker) |
| `confluence` | Import Confluence pages to Markdown |
| `crazy` | Altered-state thinking for boundary-breaking ideation |
| `creative-freedom` | Deep autonomous creative exploration |
| `dev-philosophy` | Core development principles across languages |
| `documentation` | Project documentation guidelines |
| `dp-gitlab` | GitLab interaction via dp CLI |
| `dp-jira` | Jira issue details via dp CLI |
| `frontend` | Frontend dev — stack, architecture, design, production readiness |
| `graph` | Obsidian vault graph analysis |
| `idea-roaster` | Rigorous critical evaluation of ideas |
| `lyrics` | Song lyrics from Genius |
| `orchestrator` | Multi-agent orchestration mode |
| `pinchtab` | Browser control with persistent sessions |
| `playwright` | E2E testing and visual regression |
| `project-setup` | Project scaffolding patterns |
| `reflect` | Reflective listening for processing thoughts |
| `review` | Browser-based code review and file annotation |
| `shh` | Kill TTS playback |
| `spec` | Technical specification generator |
| `talk` | Voice conversation mode with TTS |
| `todo` | Cross-session task tracking |
| `transcribe` | Audio transcription with Whisper |
| `workspace` | Multi-project workspace management |
| `worktree` | Git worktree management for parallel agent isolation |
| `youtube` | YouTube transcript fetcher |

## Hooks

| Hook | Events | Description |
| ---- | ------ | ----------- |
| `clamor` | SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Notification, Stop | Agent state tracking for the [clamor](https://github.com/amenocturne/clamor) dashboard |
| `deny-read` | PreToolUse | Enforce per-project file access deny lists |
| `graph-colors` | Stop | Regenerate Obsidian graph color groups |
| `link-proxy` | SessionStart, PreToolUse, PostToolUse | URL masking for corporate environments |
| `notification` | Notification, Stop | System notifications on events and session end |
| `save-conversation` | Stop | Auto-save transcripts and commit to git |
| `tts` | Stop | Text-to-speech via kokoro-tts |
| `workflow-check` | SubagentStop | Remind agents about uncommitted changes |
| `worktree` | Stop | Auto-clean git worktrees after agent sessions |

## Preset Instructions

Presets compose instructions in two ways:

**Always-active** — embedded in the preset's `claude.md` template, loaded at conversation start. Use for folder structure, naming conventions, communication style.

**On-demand** — separate files in `instructions/`, referenced with `@` imports. The agent reads them when performing a specific action. Use for detailed procedures (saving, linking, processing).

```markdown
## Action-Specific Instructions

- **Creating notes with links**: Read @.claude/instructions/linking.md first
- **Saving conversations**: Read @.claude/instructions/saving.md first
```

## Individual Skill Installation

If you don't need presets, install skills individually via [skills.sh](https://skills.sh/):

```bash
npx skills add amenocturne/agent-kit@youtube
npx skills add amenocturne/agent-kit@spec
```

## Links

- [skills.sh](https://skills.sh/) — Claude Code skill registry
- [Claude Code](https://claude.com/claude-code) — Anthropic's CLI for Claude
- [clamor](https://github.com/amenocturne/clamor) — Terminal multiplexer for parallel Claude Code sessions
