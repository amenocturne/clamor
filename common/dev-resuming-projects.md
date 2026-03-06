---
required_skills:
  - todo
  - review
---

## Resuming Projects

When the user says "continue working on X", "pick up X", or similar:
1. Read WORKSPACE.yaml to find the project
2. **Invoke the `todo` skill** — it handles checking `.claude/tasks/` and resuming tracked progress
3. Load remaining project context (project CLAUDE.md, knowledge base notes) in parallel with step 2

## Code Review

After committing significant changes, offer to run the `review` skill so the user can review diffs in a browser UI before proceeding.
