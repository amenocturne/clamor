# Knowledge Base Mode

You are managing an Obsidian vault with atomic notes following zettelkasten principles.

## Quick Rules

- **YouTube URLs**: Never use WebFetch. Use the **youtube** skill to fetch transcripts.
- **No subtitles?**: Download audio with `uvx yt-dlp -x --audio-format mp3 -o "tmp/%(id)s.%(ext)s" <url>` and use the **transcribe** skill.
- **No auto memory**: Do not use `~/.claude/projects/*/memory/`. Store all persistent knowledge in this vault.
- **tmp/ folder**: Scripts output to `tmp/` inside the vault root. This folder is gitignored.
- **Graph analysis**: Use the **graph** skill with `--exclude=logs,tmp,archive` to analyze the knowledge graph.
- **Project specs**: Use the **spec** skill to create technical specs. Save to `projects/software/<project-name>/`. Specs are the source of truth passed to dev-workspace for implementation.

{{include:common/skills.md}}

{{include:common/agentic-kit.md}}

## Tracking Save-worthy Items

Use the TodoWrite tool to maintain a running list of things worth saving throughout the conversation. This is a scratchpad — not a structured plan.

**What to track:** Anything that might be worth saving later — insights, decisions, interesting ideas, realizations, new information. Don't worry about categorization or structure yet.

**Update frequency:** After each substantive exchange, review and update the list — add new items, consolidate duplicates, refine descriptions.

**At save time:** Use this list as a reference to ensure nothing is forgotten. The items don't map 1:1 to notes — some may merge into a single concept, others may split into several notes. The structure emerges during save planning (see @.claude/instructions/saving.md).

## Action-Specific Instructions

Before performing these actions, read the corresponding instruction file:

- **Planning, priorities, goals, life direction**: Read @.claude/instructions/context.md first
- **Creating/updating notes with links**: Read @.claude/instructions/linking.md first
- **Saving conversations / wrapping up**: Read @.claude/instructions/saving.md first
- **Processing sources (articles, videos, podcasts)**: Read @.claude/instructions/sources.md first
- **Creating or updating projects**: Read @.claude/instructions/projects.md first
- **Writing technical specs**: Read @.claude/instructions/projects.md first, then use the **spec** skill

---

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
│   └── history/
│       └── YYYY[-MM[-DD]]-event.md  # Life events (date-prefixed)
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

## Loading Context

**At conversation start**, proactively load relevant files based on topic signals:

| Topic Signal                             | Load These                                                                              |
| ---------------------------------------- | --------------------------------------------------------------------------------------- |
| Identity, patterns, values               | `core/*`                                                                                |
| Personal frameworks, theories            | `ideas/*`                                                                               |
| Planning, priorities, "what should I do" | `context/history/YYYY-MM.md` + `context/goals/*` (see @.claude/instructions/context.md) |
| "What was I working on", catching up     | `context/history/YYYY-MM.md`                                                            |
| Specific topic facts                     | `knowledge/*`, `insights/*`                                                             |
| Active work                              | `projects/*`                                                                            |
| Past discussions                         | `logs/*`                                                                                |

**Rule:** When planning-related topics come up, always load context files first, then respond.

## Zettelkasten Principles

These apply to `core/`, `ideas/`, `insights/`, and `knowledge/`:

1. **Flat structure** — no subdirectories within these folders
2. **Atomic notes** — one concept per file
3. **Brevity** — notes should be quick to read, not articles
4. **Wiki links only** — no `#tags`, use `[[wiki links]]` for all structure
5. **Links as tags** — add topic links even if the target doesn't exist yet (e.g., `[[MOC-psychology]]`)

## Naming Conventions

Note names must be unique and unambiguous across all folders.

**Bad names** (too generic):
- `focus.md` — psychology focus? productivity focus?
- `framework.md` — meaningless

**Good names** (self-descriptive with domain prefix):
- `psychology-attention.md` — clear topic
- `agentic-core-four.md` — clearly about agentic coding
- `llm-meta-prompting.md` — LLM-specific technique

**Rule:** If the name could appear in two different domains, add a prefix.

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

---

{{include:common/communication-style.md}}
