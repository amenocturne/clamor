# Linking and MOCs

## Wiki Link Conventions

- Use `[[wiki links]]` for all connections — no `#tags`
- Links serve as tags: `[[MOC-psychology]]` at the bottom of a note
- Create links even if the target doesn't exist yet (Obsidian handles this)

## Linking Responsibilities

When creating or updating notes in `core/`, `ideas/`, `insights/`, or `knowledge/`:

1. Add relevant wiki link "tags" at the bottom (topics, themes)
2. Search existing notes across all folders for related content
3. Update those existing notes to link back to the new note
4. Link ideas to relevant core concepts they build upon

This maintains a connected knowledge graph where Claude acts as the link manager.

## MOC Structure

MOCs (Maps of Content) are index notes that organize related concepts:

- Name format: `MOC-<topic>.md` (e.g., `MOC-psychology.md`)
- Location: same folder as related notes (usually `knowledge/`)
- Purpose: provide overview and navigation for a topic area

**MOC format:**

```markdown
# MOC: Topic Name

## Core Concepts

- [[concept-one]] — brief description
- [[concept-two]] — brief description

## Related Ideas

- [[idea-one]]

## Sources

- [[source-article-name]]
```

Update MOCs when adding new notes in their domain.

## Atomicity When Linking

**When connecting two notes creates a new insight, create a new note for it.**

Wrong approach:
- Note A exists, Note B exists
- Connection between A and B reveals new concept C
- Add a "Connection to B" section inside Note A — violates atomicity

Right approach:
- Create new note C that links to both A and B
- Add "See also: [[C]]" to A and B
- Keep A and B focused on their original concepts

**Example:** If connecting `demon-identity` + `qualia` reveals a new insight, create `ai-cannot-be-demon.md` instead of adding a section to existing notes.

## Preserve Conceptual Boundaries

Similar-sounding concepts may have different meanings. When linking, understand what each concept specifically means before claiming equivalence.

Don't merge or conflate concepts just because they seem related. Keep atomic boundaries clear.
