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

**After committing, always run the `review` skill before moving on.** This is a mandatory workflow step, not optional. The user reviews diffs in a browser UI and may request changes — those must be addressed before continuing.

The only exceptions: trivial one-line fixes, config changes, or when the user explicitly skips review.
