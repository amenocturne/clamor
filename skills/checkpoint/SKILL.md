---
name: checkpoint
description: Verify, commit, and review in one step. Use after completing any code changes. Triggers on "checkpoint", "verify and commit", "commit and review", or automatically after implementation work.
author: amenocturne
---

# Checkpoint

One-step workflow completion: verify → commit → review. Use this after ANY code changes instead of manually remembering each step.

## When to Use

After completing any code changes — whether from direct edits or subagent work. This replaces manually running test/lint, committing, and invoking review separately.

**Trigger automatically** when you've finished making changes and are about to report to the user.

## Steps

Execute these in order. Stop at any failure and fix before continuing.

### 1. Verify

Run the project's test and lint commands:

```bash
just test && just lint
```

If no `justfile` exists, check `package.json` scripts or project CLAUDE.md for equivalent commands. If no test/lint commands exist at all, skip to step 2.

If tests or lint fail: fix the issues first, then re-run verification. Do NOT proceed to commit with failures.

### 2. Commit

Stage and commit the changes:

1. Run `git diff --stat` to review what changed
2. Stage relevant files (prefer specific files over `git add -A`)
3. Commit with a concise message following the project's git conventions
4. Check `git log --oneline -5` first to match existing commit style

### 3. Review

Invoke the `review` skill:

1. Determine the commit range (usually `HEAD~1..HEAD` for a single commit, or `HEAD~N..HEAD` if multiple commits were made during this task)
2. Launch the review server
3. **STOP and wait for review feedback**
4. Address any review comments before reporting completion

## Important

- This skill is the LAST thing you do before talking to the user
- If review has feedback, address it and run checkpoint AGAIN
- Never skip steps — the whole point is that this is one atomic action
