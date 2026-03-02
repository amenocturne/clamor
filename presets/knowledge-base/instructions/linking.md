## Linking and MOCs

### Meaningful Links

Links must be meaningful, not just a list of related topics. Each link should have context:

- Good: "supports the idea of [[attention-as-resource]]"
- Good: "contradicts [[multitasking-myth]] because..."
- Bad: just dumping `[[psychology]] [[productivity]] [[focus]]` at the bottom

Links themselves provide the knowledge structure. Don't spam links — each one should earn its place.

### Wiki Link Conventions

- Use `[[wiki links]]` for all connections — no `#tags`
- Create links even if the target doesn't exist yet (Obsidian handles this)

### Link Selectivity

**Only add links that carry meaning.** A link should help someone navigate to something they'd actually want to read next, or tag a topic the note genuinely belongs to.

- **Bottom tags:** 3-5 topic links is typical. 8+ is a smell — the note probably isn't about all of those things equally.
- **Inline links:** Link a term only when the linked note adds real context. Don't link common words just because a note with that name exists.
- **Cross-linking on creation:** When a new note is created, don't update every tangentially related note. Update only notes where the new note is a meaningful "see also."

The goal is a useful graph, not a maximally connected one. A link to everything is a link to nothing.

### Linking Responsibilities

When creating or updating notes in `core/`, `ideas/`, `insights/`, or `knowledge/`:
1. Add relevant wiki link "tags" at the bottom (topics, themes)
2. Search existing notes across all four folders for related content
3. Update those existing notes to link back to the new note
4. Link ideas to relevant core concepts they build upon

This maintains a connected knowledge graph where Claude acts as the link manager.

### MOCs (Maps of Content)

MOCs are **jumping points** to explore a topic, not mandatory connections for every note.

- Name format: `MOC-<topic>.md` (e.g., `MOC-psychology.md`)
- Purpose: quick guide on where to start with a topic
- Not every note needs a direct MOC link — the links between notes provide structure
- Template: `.claude/templates/moc.md`

### Connection Notes

Not every connection needs a new note. Create one when **A + B is bigger than the sum** — when the combination creates something new.

**When to create:**
- The relation between A and B reveals a new insight
- You need to explain *how* they relate and *what new things* their relation creates

**When not to create:**
- A simply supports or references B
- The connection is obvious and doesn't add new meaning

**Example:** `demon-identity` + `qualia` might reveal "why AI cannot be a demon" — that's a new insight worth its own note. But `learning-styles` referencing `psychology` doesn't need a connection note.

### Atomicity When Linking

**When connecting two notes creates a new insight, create a new note for it.**

Wrong approach:
- Note A exists, Note B exists
- Connection between A and B reveals new concept C
- Add a "Connection to B" section inside Note A — violates atomicity

Right approach:
- Create new note C that links to both A and B
- Add "See also: [[C]]" to A and B
- Keep A and B focused on their original concepts

**Preserve conceptual boundaries.** Similar-sounding concepts may have different meanings. When linking, understand what each concept specifically means before claiming equivalence.

### Unique Note Names

Note names must be unique across all folders. If `insights/focus.md` and `core/focus.md` both exist, `[[focus]]` becomes ambiguous.

**Before creating a note:**
1. Search for existing notes with similar names
2. Check if the concept already exists in another folder
3. Use specific prefixes when needed: `psychology-focus.md` vs `productivity-focus.md`
