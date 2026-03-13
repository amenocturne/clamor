---
name: worktree
description: Git worktree management for parallel agent isolation. Use when multiple agents need to work on the same repo simultaneously. Triggers on "worktree", "parallel agents", "isolation".
author: amenocturne
---

# Worktree

Isolated working copies for parallel agents via git worktrees. When multiple agents (clamor-managed or AI subagents) work on the same repo simultaneously, they need separate checkouts to avoid conflicts.

## When to Use

- **AI subagents**: Set `isolation: "worktree"` on Agent tool calls when spawning parallel implementation agents on the same repo. Claude Code handles worktree creation and merge automatically.
- **Clamor-managed agents**: Use the scripts in `scripts/` to create and manage worktrees manually.

If agents work sequentially (not in parallel), worktrees are unnecessary.

## Convention

- Worktrees live at `<project>/.worktrees/agent-<id>/` with branch `worktree-<id>`
- `.worktrees/` must be in `.gitignore` (scripts handle this automatically)
- Don't push from worktrees. Merge back to the working branch when done. The orchestrating agent or user handles merge.

## Multi-Instance Awareness

Before creating a worktree, check what's active:

- `git worktree list` — shows all worktrees for the repo
- `~/.clamor/state.json` — shows clamor-managed agents and their cwds
- `scripts/status.sh <project-dir>` — combines both views

## Scripts

| Script | Usage |
|--------|-------|
| `scripts/create.sh <project-dir> [agent-id]` | Create a worktree, prints the path |
| `scripts/cleanup.sh [worktree-path]` | Remove a specific worktree, or prune stale ones |
| `scripts/status.sh [project-dir]` | Show active worktrees and cross-reference clamor agents |

## Cleanup

Worktrees are auto-cleaned on agent Stop via the `worktree` hook (checks if cwd is inside `.worktrees/`). For manual cleanup:

```bash
scripts/cleanup.sh                    # prune all stale worktrees
scripts/cleanup.sh /path/to/worktree  # remove a specific one
```
