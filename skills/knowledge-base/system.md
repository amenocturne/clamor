# System Structure

## Folder Purposes

Your vault should have these primary folders for atomic notes:

| Folder       | Purpose                                           | Example                                      |
| ------------ | ------------------------------------------------- | -------------------------------------------- |
| `core/`      | Stable identity facts (who I am, how I function)  | values, patterns, traits                     |
| `ideas/`     | Personal theories, frameworks, concepts I created | models, approaches, methodologies            |
| `insights/`  | Personal realizations and discoveries             | "I work better when...", learned patterns    |
| `knowledge/` | General facts (not personal)                      | research findings, external information      |
| `projects/`  | Actionable plans with deadlines                   | learning plans, project specs                |
| `sources/`   | Source material references                        | articles, videos, podcasts                   |
| `logs/`      | Conversation logs and summaries                   | dated folders with transcripts and summaries |

**Key distinction:**
- `core/` answers "who am I?" — traits, values, patterns of functioning
- `ideas/` answers "what do I think?" — theories, models, frameworks that could apply beyond just me
- `insights/` answers "what did I learn about myself?" — discoveries from reflection/experience
- `knowledge/` answers "what is true?" — facts independent of me

When unsure which folder, ask the user. Gray areas exist.

## Zettelkasten Principles

These apply to `core/`, `ideas/`, `insights/`, and `knowledge/`:

1. **Flat structure** — no subdirectories within these folders
2. **Atomic notes** — one concept per file (e.g., `psychopathy.md` and `psychopathy-vs-anhedonia.md` as separate notes)
3. **Brevity** — notes should be quick to read, not articles. Multiple paragraphs and examples are fine, but no verbose explanations
4. **Wiki links only** — no `#tags`, use `[[wiki links]]` for all structure
5. **Links as tags** — add topic links even if the target doesn't exist yet (e.g., `[[MOC-psychology]]` as a tag)

## Naming Conventions

Note names must be specific enough to avoid future collisions.

**Bad names** (too generic):
- `core-four.md` — could mean anything
- `leverage-points.md` — ambiguous
- `framework.md` — meaningless

**Good names** (self-descriptive with domain prefix):
- `agentic-core-four.md` — clearly about agentic coding
- `agentic-leverage-points.md` — domain is clear
- `llm-meta-prompting.md` — LLM-specific technique
- `psychology-attachment-styles.md` — domain-specific

**Prefixes to use:**
- `agentic-` for agentic coding concepts
- `llm-` for LLM/prompt engineering patterns
- `psychology-` or specific framework names for psych concepts
- Domain-specific prefix when concept comes from a specific field

**Rule of thumb:** If the name could reasonably appear in two different domains, add a prefix.

## Project Structure

Each project gets its own folder:

```
projects/
└── project-name/
    ├── _project-name.md     # Overview, goal, core insight
    ├── skills.md            # Techniques/exercises (optional)
    ├── schedule.md          # Routines (optional)
    └── resources.md         # Tools, links (optional)
```

**Naming convention for index files:**
- Projects: `_project-<name>.md` (e.g., `_project-music-theory.md`)
- Sources: `source-<name>.md` (e.g., `source-article-title.md`)
- Never use generic `index.md` — causes link collisions in Obsidian

## Archive

The `archive/` folder holds projects that are no longer active but worth preserving (PARA-style):

- **Projects** = active, have a deadline or clear next action
- **Archive** = completed, paused, or abandoned — out of sight but not deleted

When to archive:
- Project completed (goal achieved)
- Project abandoned (no longer relevant)
- Project paused indefinitely (may resume someday)

Move entire folder to `archive/`. Wiki links still work (Obsidian resolves by filename).
