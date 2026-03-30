## Vault Structure

```
vault/
├── core/                    # Stable identity (who I am, how I function)
├── ideas/                   # Personal theories, frameworks, concepts
├── insights/                # Personal realizations and discoveries
├── knowledge/               # General facts (not personal)
├── context/
│   ├── goals/
│   │   ├── life.md          # Ongoing, not time-bound
│   │   ├── YYYY.md          # Year goals
│   │   └── YYYY-MM.md       # Monthly goals
│   ├── history/
│   │   └── YYYY[-MM[-DD]]-event.md  # Life events (date-prefixed)
│   └── people/              # Contacts — people I know (template: .claude/templates/person.md)
├── projects/                # Active actionable plans
│   ├── software/
│   ├── goals/
│   ├── presentations/
│   └── content/
├── sources/                 # Source material references
│   ├── youtube/
│   ├── articles/
│   └── books/
├── logs/                    # Conversation logs
│   └── YYYY-MM-DD/
│       ├── HHMMSS.json      # Raw transcript (auto-saved)
│       └── HHMMSS Topic.md  # Summary (renamed by hook)
├── archive/                 # Completed/paused projects (PARA-style)
└── tmp/                     # Temporary files (gitignored)
```

See `WORKSPACE.yaml` at vault root for folder descriptions. When unsure which folder, ask the user.

## Archive (PARA-style)

The `archive/` folder holds projects that are no longer active but worth preserving:

- **Projects** = active, have a deadline or clear next action
- **Archive** = completed, paused, or abandoned — out of sight but not deleted

**When to archive:**
- Project completed (goal achieved)
- Project abandoned (no longer relevant)
- Project paused indefinitely (may resume someday)

**How to archive:**
- Move entire folder to `archive/`
- Wiki links still work (Obsidian resolves by filename)
