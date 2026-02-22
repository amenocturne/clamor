---
name: workspace
description: Multi-project workspace management. Use when user mentions a project name, wants to switch projects, or needs to refresh the project index. Provides project paths, tech stacks, and commands from WORKSPACE.yaml.
author: amenocturne
---

# Workspace

Multi-project workspace management via WORKSPACE.yaml.

## WORKSPACE.yaml

Project index at workspace root:

```yaml
version: 1
projects:
  project-name:
    path: ./path/to/project
    description: What this project does
    tech: [python, uv]
    explore_when: [keywords that suggest this project]
    entry_points: [main files to start reading]
    format_cmd: uv run ruff format .
    lint_cmd: uv run ruff check .
    test_cmd: uv run pytest
```

## Regenerating

To refresh after adding new projects, run the generator:

```bash
uv run .claude/skills/workspace/scripts/generate-workspace.py --root . --output WORKSPACE.yaml
```

This scans for git repos and detects tech stacks. User should fill in `description` and `explore_when` after generation.

## Working on a Project

When user mentions a project:
1. Find it in WORKSPACE.yaml
2. Load project's CLAUDE.md if exists
3. Load language instruction based on tech stack
4. Use commands from WORKSPACE.yaml (format_cmd, test_cmd, etc.)
