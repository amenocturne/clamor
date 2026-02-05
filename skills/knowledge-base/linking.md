# Linking and MOCs

## Meaningful Links

Links must be meaningful, not just a list of related topics. Each link should have context:

- Good: "supports the idea of [[attention-as-resource]]"
- Good: "contradicts [[multitasking-myth]] because..."
- Bad: just dumping `[[psychology]] [[productivity]] [[focus]]` at the bottom

Links themselves provide the knowledge structure. Don't spam links — each one should earn its place.

## Wiki Link Conventions

- Use `[[wiki links]]` for all connections — no `#tags`
- Create links even if the target doesn't exist yet (Obsidian handles this)

## MOCs (Maps of Content)

MOCs are **jumping points** to explore a topic, not mandatory connections for every note.

- Name format: `MOC-<topic>.md` (e.g., `MOC-psychology.md`)
- Purpose: quick guide on where to start with a topic
- Not every note needs a direct MOC link — the links between notes provide structure

**MOC format:**

```markdown
# MOC: Topic Name

## Core Concepts

- [[concept-one]] — brief description
- [[concept-two]] — brief description

## Sources

- [[source-article-name]]
```

## Connection Notes

Not every connection needs a new note. Create one when **A + B is bigger than the sum** — when the combination creates something new.

**When to create:**
- The relation between A and B reveals a new insight
- You need to explain *how* they relate and *what new things* their relation creates

**When not to create:**
- A simply supports or references B
- The connection is obvious and doesn't add new meaning

**Example:** `demon-identity` + `qualia` might reveal "why AI cannot be a demon" — that's a new insight worth its own note. But `learning-styles` referencing `psychology` doesn't need a connection note.

## Unique Note Names

Note names must be unique across all folders. If `insights/focus.md` and `core/focus.md` both exist, `[[focus]]` becomes ambiguous.

**Before creating a note:**
1. Search for existing notes with similar names
2. Check if the concept already exists in another folder
3. Use specific prefixes when needed: `psychology-focus.md` vs `productivity-focus.md`
