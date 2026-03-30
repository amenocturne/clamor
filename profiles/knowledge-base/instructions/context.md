## Loading Context

**At conversation start**, proactively load relevant files based on topic signals:

| Topic Signal                             | Load These                                                 |
| ---------------------------------------- | ---------------------------------------------------------- |
| Identity, patterns, values               | `core/*`                                                   |
| Personal frameworks, theories            | `ideas/*`                                                  |
| Planning, priorities, "what should I do" | `context/history/YYYY-MM.md` + `context/goals/*`           |
| "What was I working on", catching up     | `context/history/YYYY-MM.md`                               |
| Specific topic facts                     | `knowledge/*`, `insights/*`                                |
| Active work                              | `projects/*`                                               |
| Past discussions                         | `logs/*`                                                   |
| People, contacts, networking             | `context/people/*`, `knowledge/MOC-contacts.md`            |

**Rule:** When planning-related topics come up, always load context files first, then respond.

## Working with Context

The `context/` folder answers "Where am I now?" — goals and life events.

### Structure

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

### File Contents

#### Goals

| File | Template | Update When |
|------|----------|-------------|
| `goals/life.md` | `.claude/templates/goals-life.md` | Long-term direction changes |
| `goals/YYYY.md` | `.claude/templates/goals-year.md` | Year starts, quarterly review |
| `goals/YYYY-MM.md` | `.claude/templates/goals-month.md` | Month starts, goals complete |

#### History (Event-Based)

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

### When to Update Context

#### Proactive Updates

Update context files when you notice:
- New life event (moved, new job, health issue, etc.) → create new `history/<event>.md`
- Existing event changed or resolved → update the event note
- Goal achieved, abandoned, or priorities changed → update relevant goals file

#### During Conversation Wrap-up

When saving a conversation, consider:
- Did a significant life event occur? → create `history/<event>.md`
- Does this affect goals? → update goals files

### Relationship to Other Folders

| Folder | vs Context |
|--------|-----------|
| `goals/` | What you're trying to achieve. History = life circumstances around you. |
| `projects/` | Specific actionable plans. Goals = targets. History = context. |
| `core/` | Stable identity. History = changing circumstances. |

**Rule:** Goals track what you want. History tracks what's happening around you. They don't overlap.

### Creating Missing Files

If a context file doesn't exist when needed:
1. Create it with minimal structure
2. Ask user to provide current info
3. Fill in based on conversation

Example prompt: "I notice there are no history events on what we discussed. Want me to create one?"
