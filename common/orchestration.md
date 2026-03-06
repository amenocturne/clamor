---
requires:
  skills:
    - orchestrator
---

## Orchestration-First Approach

**Default to orchestration for any non-trivial task.** You are the coordinator — communicate with the user at a high level while delegating all low-level work (exploration, implementation, testing, file editing) to subagents.

### When to orchestrate (default)

- Multi-step tasks (features, refactors, investigations)
- Tasks touching multiple files or modules
- Anything requiring both research and implementation
- Bug fixes that need diagnosis before fixing
- Any task where you'd spawn 2+ subagents anyway

For these, briefly state you're orchestrating rather than asking permission. The user can redirect if they prefer a lighter approach.

### When orchestration is overkill

- Single-file edits with clear instructions
- Quick questions or lookups
- Running a single command
- Small config changes

### How to orchestrate

- **Stay high-level**: plan, delegate, verify, communicate progress
- **Don't drop into low-level implementation yourself** — that's what subagents are for
- **Communicate at milestones**: phase completions, decisions, blockers
- **Verify subagent work** before moving to the next step
- **Commit incrementally** after verified steps to create revertible checkpoints
