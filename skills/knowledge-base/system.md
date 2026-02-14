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

## Loading Context

When beginning a conversation, load relevant files based on the topic:

- Load `core/*` for conversations about identity, patterns, values
- Load `ideas/*` for conversations involving personal frameworks/theories
- Load `context/situation.md` + relevant `goals/*` for practical planning
- Load `context/history/*` for understanding past context
- Reference `insights/*` when relevant topics come up
- Reference `knowledge/*` for general facts on a topic
- Reference `projects/*` for actionable plans on a topic
- Search `logs/*` for past discussion context

## Zettelkasten Principles

These apply to `core/`, `ideas/`, `insights/`, and `knowledge/`:

1. **Flat structure** — no subdirectories within these folders
2. **Atomic notes** — one concept per file (e.g., `psychopathy.md` and `psychopathy-vs-anhedonia.md` as separate notes)
3. **Brevity** — notes should be quick to read, not articles. Multiple paragraphs and examples are fine, but no verbose explanations
4. **Wiki links only** — no `#tags`, use `[[wiki links]]` for all structure
5. **Links as tags** — add topic links even if the target doesn't exist yet (e.g., `[[MOC-psychology]]` as a tag)

## Naming Conventions

Note names must be unique and unambiguous across all folders.

**Bad names** (too generic):
- `focus.md` — psychology focus? productivity focus?
- `framework.md` — meaningless
- `core-four.md` — could mean anything

**Good names** (self-descriptive with domain prefix):
- `psychology-attention.md` — clear topic
- `agentic-core-four.md` — clearly about agentic coding
- `llm-meta-prompting.md` — LLM-specific technique
- `afk-peter-framework.md` — specific framework name + context

**Prefixes to use:**
- `agentic-` for agentic coding concepts
- `llm-` for LLM/prompt engineering patterns
- `psychology-` or specific framework names for psych concepts
- Domain-specific prefix when concept comes from a specific field

**Rule of thumb:** If the name could reasonably appear in two different domains, add a prefix. When in doubt, be more specific.

## Project Structure

Projects are organized into category subfolders:

```
projects/
├── software/          # Software projects (apps, tools, systems)
├── goals/             # Life goals (immigration, career, health, learning)
├── presentations/     # Talks, workshops, docs-as-code
└── content/           # YouTube video ideas, articles
```

Each project gets its own folder within its category:

```
projects/goals/music-theory/
    ├── _project-music-theory.md  # Overview, goal, core insight
    ├── skills.md                 # Techniques/exercises (optional)
    ├── schedule.md               # Routines (optional)
    └── resources.md              # Tools, links (optional)
```

**Naming convention for index files:**
- Projects: `_project-<name>.md` (e.g., `_project-music-theory.md`)
- Sources: `source-<name>.md` (e.g., `source-article-title.md`)
- Never use generic `index.md` — causes link collisions in Obsidian

Use `templates/project.md` for the project file. Split into additional files when sections become large or independently useful.

### When to use projects/

- Learning plans with exercises and schedules
- Step-by-step guides for achieving a goal
- Curricula synthesized from research/conversations
- Any "how to approach X" that's too actionable for knowledge/

### Processing incoming guides

When user provides a detailed guide/plan to save:

1. **Identify the project name** — short, kebab-case (e.g., `music-theory`)
2. **Create the project folder** — `projects/[category]/[name]/`
3. **Analyze the content** — identify natural split points:
   - Core problem/insight → `_project-<name>.md`
   - Skills/exercises → `skills.md`
   - Schedules/routines → `schedule.md`
   - Tools/resources → `resources.md`
   - Research findings that are general → extract to `knowledge/`
4. **Split or keep whole** — small guides can stay as single `_project-<name>.md`
5. **Add wiki links** — tag with relevant topics, link to related goals
6. **Update goals if relevant** — add reference in `context/goals/` if this supports a stated goal

## Archive

The `archive/` folder holds projects that are no longer active but worth preserving (PARA-style):

- **Projects** = active, have a deadline or clear next action
- **Archive** = completed, paused, or abandoned — out of sight but not deleted

**When to archive:**
- Project completed (goal achieved)
- Project abandoned (no longer relevant)
- Project paused indefinitely (may resume someday)

**How to archive:**
- Move entire folder to `archive/`
- Optionally update status in project file
- Wiki links still work (Obsidian resolves by filename)
