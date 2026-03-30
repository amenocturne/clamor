## Working with Projects

### When to Create a Project

Use `projects/` for:
- Learning plans with exercises and schedules
- Step-by-step guides for achieving a goal
- Curricula synthesized from research/conversations
- Actionable plans that are too structured for `knowledge/`

### Project Structure

Projects go in category subfolders:

```
projects/
├── software/          # Software projects (apps, tools, systems)
├── goals/             # Life goals (immigration, career, health, learning)
├── presentations/     # Talks, workshops, docs-as-code
└── content/           # YouTube video ideas, articles
```

Each project gets its own folder:

```
projects/goals/music-theory/
├── _project-music-theory.md      # Overview, goal, core insight
├── skills-music-theory.md        # Techniques/exercises (optional)
├── schedule-music-theory.md      # Routines (optional)
└── resources-music-theory.md     # Tools, links (optional)
```

### Naming Convention

- Index file: `_project-<name>.md` (underscore for Obsidian pinning)
- Support files: `<type>-<project-name>.md` (e.g., `background-music-theory.md`)
- Never use generic names like `index.md`, `background.md`, `resources.md` — causes link collisions in graph analysis

### Creating a Project

1. **Identify category** — software, goals, presentations, or content
2. **Create folder** — `projects/<category>/<name>/`
3. **Create index file** — use template from `.claude/templates/project.md`
4. **Split if needed** — large projects get separate files for skills, schedule, resources

### Processing User's Guide/Plan

When user provides a detailed guide to save:

1. **Identify natural split points:**
   - Core problem/insight → `_project-<name>.md`
   - Skills/exercises → `skills-<name>.md`
   - Schedules/routines → `schedule-<name>.md`
   - Tools/resources → `resources-<name>.md`
   - General research findings → extract to `knowledge/`

2. **Keep small guides whole** — don't over-split simple plans

3. **Add wiki links** — tag with relevant topics, link to related projects/goals

### Using the Spec Skill

When using the **spec** skill to create project specifications:
- Save specs in `projects/<category>/<name>/`
- Name the main spec `_project-<name>.md`
- Save implementation plan alongside as `implementation-plan.md`

### Capturing Decision Context

When a conversation involves choosing between approaches, create `background-<project-name>.md` in the project folder. Use template from `.claude/templates/background.md`.

**When to create:**
- Multiple options were seriously considered
- Tradeoffs were discussed (technical, practical, psychological)
- The "why not" for rejected options is worth preserving

**What to capture:**
- Context: what prompted this decision
- Options: all approaches considered
- Rejections: why each alternative won't work (be specific)
- Decision: what we chose and why it wins

**Goal:** Future reader can understand the full problem space, not just the outcome.
