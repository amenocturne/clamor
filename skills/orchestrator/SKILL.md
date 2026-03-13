---
name: orchestrator
description: Multi-agent orchestration mode. Use when user explicitly asks to orchestrate, delegate, or run a long session. Produces coordinated work across subagents with incremental commits and comprehensive wrap-up.
author: amenocturne
---

# Orchestrator Mode

Coordinate complex tasks by delegating to specialized subagents instead of doing the work directly. The orchestrator stays high-level, managing flow and quality while subagents handle implementation.

## When to Use

When to activate is controlled by workspace instructions (e.g., `common/orchestration.md`). This skill defines *how* to orchestrate, not *when*.

## Session Kickoff

### 1. Understand the Task

Accept input in any form:
- Spec file (spec.md, implementation-plan.md)
- Conversational discussion
- High-level goal description
- Numbered task list

### 2. Create Workflow Plan

Before starting any work, present a **phases-with-tasks** plan for approval:

```
## Workflow Plan

### Phase 1: Research
Execution: parallel
- [ ] Explore codebase structure (Explore agent)
- [ ] Analyze existing patterns (Explore agent)
↓ sync: combine findings before implementation

### Phase 2: Implementation
Execution: sequential
- [ ] Implement core feature (general-purpose agent)
  ↓ depends on: Phase 1 findings
- [ ] Add tests (general-purpose agent)
  ↓ depends on: core feature complete

### Phase 3: Integration
Execution: sequential
- [ ] Update documentation (general-purpose agent)
- [ ] Final verification (Explore agent)

---
Verification: [immediate/batched/task-dependent]
Estimated spawns: N agents
Sync points: after Phase 1, after each Phase 2 task

Proceed with this plan?
```

#### Execution Modes

**Parallel**: Tasks run simultaneously, results combined at sync point
```
┌─ Task A (Explore) ─┐
│                    ├─→ sync → continue
└─ Task B (Explore) ─┘
```

**Sequential**: Each task waits for previous, output feeds next
```
Task A → Task B → Task C
```

**Mixed**: Parallel research, sequential implementation
```
┌─ Research A ─┐
│              ├─→ sync → Implement → Test → Verify
└─ Research B ─┘
```

#### Sync Points

Explicitly mark where parallel work must synchronize:
- Before implementation that depends on research
- Before verification that needs all changes complete
- Before commits that should include multiple changes

### 3. Confirm Verification Style

Ask about verification approach if not clear from context:
- **Immediate**: Verify after each task (for critical/complex work)
- **Batched**: Verify at phase boundaries (for straightforward work)
- **Task-dependent**: Critical tasks get immediate QA, others batched

## During Orchestration

### Subagent Selection

Use whatever agent type fits the task:

| Agent Type | Best For |
|------------|----------|
| `Explore` | Codebase research, finding patterns, understanding structure |
| `Plan` | Designing implementation approach, architecture decisions |
| `Bash` | Running commands, git operations, build/test |
| `general-purpose` | Implementation, writing code, complex multi-step tasks |

For critical evaluation, use `idea-roaster` skill in main context, or spawn as subagent when clean context matters (e.g., ideas saved to file, want unpolluted analysis).

### Parallel Isolation

When spawning multiple implementation agents that work on the **same repository** simultaneously, use `isolation: "worktree"` on Agent tool calls:

```
Agent(
  prompt: "Implement feature X...",
  isolation: "worktree"
)
```

This gives each agent an isolated git worktree — no file conflicts, no index locks. Claude Code handles worktree creation and returns changes as a diff.

**When to use isolation:**
- Two or more agents writing code in the same repo at the same time
- Parallel implementation tasks (not just research)

**When NOT needed:**
- Explore/research agents (read-only, no conflicts)
- Sequential tasks (only one agent active at a time)
- Agents working on different repos

### Subagent Instructions

Every subagent prompt should request:
- Clear, concise summary of work done
- List of files modified/created
- Any decisions made or concerns encountered
- Explicit success/failure status

### Monitoring

While subagents work:
1. Review their summaries when they complete
2. If something concerns you → read modified files directly or spawn verification subagent
3. Run verification subagents **separately** from implementation subagents when quality is critical

### Incremental Commits

After each task completion + verification:
1. Review changes
2. Commit following commit-style guidelines
3. This creates revertible checkpoints through the session

### Communication

Provide regular updates:
- When each phase completes
- When making notable decisions
- When encountering blockers or needing input
- Progress indicator: "Phase 2/3: Implementation (task 3/5 complete)"

## Handling Problems

### Subagent Failures

```
If unclear instructions caused failure:
  → Ask user for clarification

If solution is too complex:
  → Brainstorm alternative approaches first
  → If drastic change needed → ask user
  → If minor aligned change → proceed, note decision

If subagent just couldn't solve it:
  → Retry with better context/instructions
  → Or escalate to user
```

### Quality Issues

- Use partial results when possible
- Note what failed in session summary
- Don't let perfect be enemy of good for MVP work

## Session Wrap-Up

When orchestration completes, produce:

### 1. Session Summary

Create or update `session-summary.md`:
```markdown
# Session: [Brief Title]
Date: YYYY-MM-DD

## What Was Done
- [List of completed tasks]

## Decisions Made
- [Key decisions and rationale]

## Files Changed
- [Grouped by purpose]

## Known Issues / Limitations
- [Anything incomplete or needing attention]
```

### 2. Project Notes (if knowledge base configured)

Update the project's notes in knowledge base with:
- Progress made
- Decisions that affect future work
- Updated status

### 3. Next Steps

Clear list of what remains:
```markdown
## Next Steps
1. [Immediate priority]
2. [Secondary items]
3. [Future considerations]
```

## Scope

Orchestrator mode works for any complex task, not just coding:
- **Code**: Features, refactors, bug investigations
- **Knowledge base**: Research, note organization, content creation
- **Exploration**: Codebase analysis, technology evaluation
- **Documentation**: Multi-file doc updates, architecture docs

## Patterns

### Sequential Chain
One subagent completes, next starts with its output.
Use when: Steps have dependencies.

### Parallel Tasks
Multiple subagents work independently, results combined.
Use when: Independent analysis or implementation.

### Iterative Refinement
Review subagent work, spawn follow-ups until satisfied.
Use when: Quality is critical, requirements emerge during work.

### Hierarchical Delegation
Stay high-level, subagents handle all implementation.
Use when: Large scope, clear task breakdown.

## Anti-Patterns

- **Don't**: Skip the plan confirmation step
- **Don't**: Batch all commits to the end
- **Don't**: Let subagent failures cascade without review
- **Don't**: Forget the wrap-up artifacts
