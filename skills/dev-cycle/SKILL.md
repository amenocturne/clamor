---
name: dev-cycle
description: Full automated development cycle with specialized subagents. Runs implement → review → test loop per task, respecting dependency order. Triggers on "dev cycle", "full cycle", "implement and test", "auto dev", "automated cycle".
author: amenocturne
---

# Dev Cycle

Automated closed-loop development cycle for spec-driven work. Each task goes through **Implementer → Reviewer → Tester** with automatic retry on failure, all orchestrated asynchronously as background agents respecting task dependencies.

## Task Granularity

Before execution, decompose the spec into tasks where each task is:
- **Completable by one implementer** without coordinating with a parallel in-progress task
- **Meaningful in isolation** — not so small it's noise, not so large context balloons

Good: "Add authentication middleware and update route guards"
Too small: "Rename variable X to Y"
Too large: "Implement the entire payment system"

If the spec already has a phase/task breakdown, use it as-is unless granularity is clearly off.

## Subagent Roles

### Implementer

Writes code, writes/updates tests, ensures everything compiles and passes.

**Prompt template:**
```
You are the implementer for this task: [TASK_DESCRIPTION]

Project: [PROJECT_PATH]
Spec section: [RELEVANT_SPEC_EXCERPT]
Prior review feedback to address: [FEEDBACK or "none"]
Prior tester failure to fix: [FAILURE_REPORT or "none"]

Steps:
1. Read the relevant existing files first to understand context
2. Implement the changes described in the task
3. Write/update tests covering your changes
4. Run the test command: [TEST_CMD] — fix any failures before returning
5. Ensure it compiles clean

Return:
- Status: SUCCESS or FAILED
- Files modified/created (list)
- Summary of what was done
- Key decisions made
- Any concerns or blockers
```

**Isolation:** Always use `isolation: "worktree"` when implementer runs in parallel with other active implementers.

### Reviewer

Reads code in context, reports findings. Read-only — never makes changes.

**Prompt template:**
```
You are the reviewer for this task: [TASK_DESCRIPTION]

Files changed: [FILES_LIST]
Project root: [PROJECT_PATH]

Steps:
1. Read every changed file completely
2. Read surrounding context files as needed to understand patterns
3. Check for: bugs, edge cases, security issues, test coverage gaps,
   inconsistency with existing codebase patterns

Return a structured review:
- Verdict: PASS or CHANGES_NEEDED
- If CHANGES_NEEDED: specific actionable issues with file:line references
  (be precise — the implementer uses this list directly)
- If PASS: brief note on what looks good

Do NOT write any code. Read only.
```

**Isolation:** Never needed (read-only).

### Tester

Runs the actual application and verifies behavior. Profile-specific (see below).

**Prompt template:**
```
You are the tester for this task: [TASK_DESCRIPTION]

Testing profile: [PROFILE]
Project: [PROJECT_PATH]
What to verify: [EXPECTED_BEHAVIOR from spec]

Steps (profile-specific — see below):
[PROFILE_INSTRUCTIONS]

Return:
- Verdict: PASS or FAIL
- Evidence: output, screenshots, or logs proving the verdict
- If FAIL: specific description of what broke and how to reproduce
```

**Isolation:** Never needed.

## Tester Profiles

The orchestrator selects the appropriate profile based on the task and project type. Some tasks skip testing entirely.

| Profile | When to use | Tools |
|---------|-------------|-------|
| `web` | Web app UI feature, visual change, user flow | playwright or pinchtab to browse running app |
| `api` | REST/GraphQL endpoint, backend logic | HTTP requests via Bash, check responses |
| `cli` | Command-line tool, script behavior | Run the command, check stdout/stderr/exit code |
| `unit` | Pure refactor, library code, no user-facing change | Run existing test suite: `[TEST_CMD]` |
| `none` | Style/formatting, comment changes, config-only | Skip tester entirely |

**Selection logic:**
- User specified a profile → use it
- Task adds/modifies a UI route → `web`
- Task adds/modifies an API endpoint → `api`
- Task adds/modifies CLI commands → `cli`
- Task is pure internal refactor or restructuring → `unit`
- Task is style/config/docs only → `none`

When profile is `web`, prefer pinchtab over playwright for simple checks; use playwright for multi-step flows or visual regressions.

## The Cycle Protocol

This is the loop that runs per task:

```
attempt = 1
max_attempts = 3

IMPLEMENT:
  → fire Implementer as background agent (worktree if parallel)
  → on completion:
      if FAILED and attempt < max_attempts:
        attempt++; go to IMPLEMENT
      if FAILED after 3 attempts:
        ESCALATE to user

REVIEW:
  → fire Reviewer as background agent
  → on completion:
      if PASS:
        go to TEST
      if CHANGES_NEEDED and attempt < max_attempts:
        attempt++; go to IMPLEMENT (with review feedback)
      if CHANGES_NEEDED after 3 attempts:
        ESCALATE to user

TEST:
  → if profile == "none": COMMIT and DONE
  → fire Tester as background agent
  → on completion:
      if PASS:
        COMMIT and DONE
      if FAIL and attempt < max_attempts:
        attempt++; go to IMPLEMENT (with tester failure report)
      if FAIL after 3 attempts:
        ESCALATE to user
```

**Escalation** means: stop the task, report to user with full context (what was tried, what failed), and wait for guidance before retrying.

**Attempt counter resets** when a task fully completes (DONE). It tracks retries within one task's cycle.

## Workflow Entry

When invoked with a spec:

1. **Parse** the spec — identify phases, tasks, and dependencies
2. **Present plan** — show the task graph with tester profiles assigned
   ```
   Task A [unit] → Task B [web] → Task C [none]
                ↘ Task D [api] ↗
   ```
3. **Confirm** — wait for user approval before starting
4. **Execute** — run the async scheduler loop
5. **Report** — on each task completion, brief status update to user

Always confirm the plan before firing any agents.
