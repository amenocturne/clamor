---
name: todo
description: Cross-session task tracking via gitignored .claude/tasks/ directory. Use when working on non-trivial multi-session tasks (specs, features, refactors). Triggers on "track this", "continue working on", "pick up where we left off", "what's left", "clean up tasks".
author: amenocturne
---

# Todo — Cross-Session Task Tracking

Track progress on multi-session work using markdown task files in `.claude/tasks/<project>/`.

## When to Use

**Create task files for:**
- Spec implementations (multi-phase builds)
- Large features or refactors
- Any work that will clearly span multiple sessions

**Do NOT create task files for:**
- Ad-hoc one-off changes ("add this small thing and commit")
- Simple bug fixes
- Quick questions or exploration

**Rule:** Always ask the user before creating a task file. Something like: "This looks like multi-session work. Want me to create a task file to track progress?"

## Directory Structure

Tasks live in the **working directory's** `.claude/tasks/` — that's the directory where Claude was launched, NOT inside individual project directories.

```
<working-directory>/
└── .claude/tasks/
    └── <project-name>/
        ├── feature-a.md
        └── feature-b.md
```

In a multi-project workspace, this means all projects share one `.claude/tasks/` at the workspace root. Do NOT create `.claude/tasks/` inside project subdirectories.

- Agent must specify the project name when creating tasks
- One file per spec/feature/work stream
- If the user is working in a single-project repo, use the repo name as project name

## Setup

When creating `.claude/tasks/` for the first time:

1. Create the directory: `.claude/tasks/<project>/` in the **working directory** (workspace root)
2. Add `.claude/tasks/` to the working directory's `.gitignore` if not already there

## Task File Format

```md
# Feature Name

## Progress
- [x] Phase 1: Foundation
- [ ] Phase 2: Core logic    <-- current
- [ ] Phase 3: Integration

## Current State
What's done, what's blocked, where to pick up next.

## Breakdown

### Phase 1: Foundation (done)
- [x] Set up project structure
- [x] Define core types

### Phase 2: Core logic
- [ ] Implement feed algorithm
- [ ] Add filtering
- [ ] Wire up state management

### Phase 3: Integration
- [ ] Connect UI to feed
- [ ] End-to-end tests

## Notes
- Decision: went with X over Y because...
- Blocked on: need user input on Z
```

**Key sections:**

| Section | Purpose |
|---------|---------|
| Progress | Quick checklist of phases — scannable at a glance |
| Current State | Where to pick up, what's blocked — the "handoff note" |
| Breakdown | Full task details per phase |
| Notes | Decisions, blockers, anything the next session needs to know |

**Rules:**
- Keep the Progress section short — one line per phase
- Mark the current phase so it's obvious where to resume
- Update Current State at the end of each session
- Notes are optional — add them when there's context worth preserving

## Resuming Work

When the user says something like "continue working on X" or "pick up project Y":

1. Check `.claude/tasks/<project>/` in the **working directory** for matching task files
2. Read the relevant file(s)
3. Start from where Current State indicates
4. If multiple task files exist and it's unclear which one, ask the user

If the user only specifies a project name, list available task files and ask which to continue.

## Updating Tasks

As work progresses during a session:

- Check off completed items
- Update Current State before the session ends (or when the user signals wrapping up)
- Add Notes for decisions or context that would be lost between sessions
- Move the "current" marker in Progress

## Cleanup

**When to suggest cleanup:**
- All tasks in a file are complete
- Tasks haven't been touched in a while and seem stale
- The work described no longer matches what's actually happening

**How to clean up:**
- Ask the user before deleting any task files
- For completed work: delete the file (the code is the source of truth now)
- For stale/abandoned work: ask if it should be deleted or updated

Never silently delete task files.
