# Working with Context

The `context/` folder answers "Where am I now?" — goals and life events.

## Structure

```
context/
├── goals/
│   ├── life.md          # Ongoing, not time-bound
│   ├── YYYY.md          # Year goals
│   └── YYYY-MM.md       # Monthly goals
└── history/
    ├── 2024-relocated.md             # Year-level event
    ├── 2024-03-career-change.md      # Month-level event
    └── 2024-03-15-milestone.md       # Day-level event
```

## When to Load Context

**At conversation start**, load context based on topic signals:

| Topic Signal | Load These Files |
|-------------|------------------|
| Planning, priorities, "what should I focus on" | Recent `history/*` events + current month goals |
| Goal setting, life direction | `goals/life.md` + `goals/YYYY.md` |
| "What's going on in my life", catching up | Recent `history/*` events |

**Rule:** When the user starts discussing priorities, planning, or "what to do next" — proactively load context files first, then respond.

## File Contents

### Goals

| File | Template | Update When |
|------|----------|-------------|
| `goals/life.md` | `.claude/templates/goals-life.md` | Long-term direction changes |
| `goals/YYYY.md` | `.claude/templates/goals-year.md` | Year starts, quarterly review |
| `goals/YYYY-MM.md` | `.claude/templates/goals-month.md` | Month starts, goals complete |

### History (Event-Based)

History notes capture **life events** so the user doesn't have to re-explain them.

- One event per file (atomic)
- Filename format: `<date>-<event>.md`
  - Year event: `2024-relocated.md`
  - Month event: `2024-03-career-change.md`
  - Day event: `2024-03-15-milestone.md`
- Template: `.claude/templates/history-event.md`

**History vs Goals:**
- History = life events and circumstances (reference, not action)
- Goals = what you're trying to achieve (actionable)

## When to Update Context

### Proactive Updates

Update context files when you notice:
- New life event (moved, new job, health issue, etc.) → create new `history/<event>.md`
- Existing event changed or resolved → update the event note
- Goal achieved, abandoned, or priorities changed → update relevant goals file

### During Conversation Wrap-up

When saving a conversation (per `saving.md`), consider:
- Did a significant life event occur? → create `history/<event>.md`
- Does this affect goals? → update goals files

## Relationship to Other Folders

| Folder | vs Context |
|--------|-----------|
| `goals/` | What you're trying to achieve. History = life circumstances around you. |
| `projects/` | Specific actionable plans. Goals = targets. History = context. |
| `core/` | Stable identity. History = changing circumstances. |

**Rule:** Goals track what you want. History tracks what's happening around you. They don't overlap.

## Creating Missing Files

If a context file doesn't exist when needed:
1. Create it with minimal structure
2. Ask user to provide current info
3. Fill in based on conversation

Example prompt: "I notice there are no history events on what we discussed. Want me to create one?"
