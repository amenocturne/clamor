---
name: agentic-kit
description: Toolkit self-modification. Use when user wants to add or edit skills, update instructions, or change presets in agentic-kit itself. Enables improving the toolkit without switching projects.
author: amenocturne
---

# Agentic Kit

Modify the agentic-kit toolkit without switching projects.

When user asks to update instructions, add skills, or modify the toolkit, use this context.

## Finding Paths

Get the agentic-kit root from config:
```bash
cat .claude/agentic-kit.json | jq -r '.agentic_kit'
```

## Structure

```
agentic-kit/
├── skills/
│   └── <skill-name>/
│       ├── SKILL.md          # Skill definition (YAML frontmatter + instructions)
│       └── scripts/          # Optional helper scripts
├── presets/
│   └── <preset-name>/
│       ├── manifest.yaml     # Skills and hooks to install
│       ├── claude.md         # Core instructions (always loaded)
│       └── instructions/     # On-demand instruction files
├── hooks/
│   └── <hook-name>/
│       ├── hook.py           # Hook script
│       └── hooks.json        # Hook config with {hook_dir} placeholder
└── install.py                # Installer script
```

## Creating Skills

New skill needs a folder with SKILL.md:
```yaml
---
name: skill-name
description: What it does
author: amenocturne
---

# Skill Name

Instructions for when/how to use this skill.
```

Add to preset's `manifest.yaml` to include in installations.

## Creating Instructions

Language/domain instructions go in `presets/<preset>/instructions/`.
Update the preset's `claude.md` to reference new instructions.

## After Changes

Re-run installer to sync changes to current project:
```bash
uv run <agentic_kit>/install.py --preset <preset> --target .
```

Skills are symlinked, so most changes take effect immediately without re-sync.
