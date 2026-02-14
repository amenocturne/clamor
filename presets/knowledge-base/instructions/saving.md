# End-of-Conversation Saving

When the user signals conversation end ("let's wrap up", "save this", "that's all"), follow this process:

## Step 1: Explore Existing Notes

First, understand what already exists:
- Search `knowledge/`, `insights/`, `ideas/`, `core/` for related content
- Check for notes that already cover discussed concepts
- Note similar names to avoid collisions

## Step 2: Propose a Save Plan (REQUIRED)

Present a concise plan for user approval. Use this format:

```
**Save Plan:**

**Notes to create:**
- `ideas/concept-name.md` — one-line description
- `knowledge/another-concept.md` — one-line description

**Existing notes to update:** (if any)
- `knowledge/existing-note.md` — add link to new concept

**Log:** `logs/YYYY-MM-DD/_topic.md`

**Skip:** [brief reason if skipping anything discussed]

Proceed?
```

**Rules for the plan:**
- One line per note — just path and brief description
- Mention existing notes that will be updated with backlinks
- No lengthy explanations — user can ask for details
- Wait for user confirmation before creating anything

## Step 3: Create Atomic Notes

After user approves, create notes:

- **Knowledge** (`knowledge/`) — general facts, external information
- **Insights** (`insights/`) — personal realizations, patterns discovered
- **Ideas** (`ideas/`) — new frameworks or theories developed

Follow atomic note principle: one concept per file.

### Pre-Save Checklist

Before writing any note:

1. **One concept = one note.** If a note has multiple `##` sections that could stand alone, it's too big.
2. **Check links before writing.** Verify `[[wikilink]]` targets exist or match what you're creating.
3. **Calibrate length.** Read an existing note if available. If your draft is 2x+ longer, split it.

## Step 4: Create Conversation Summary

Save to `logs/YYYY-MM-DD/_Topic.md` using the summary template.

The summary should **link to the notes created** instead of repeating content:

```markdown
# {Topic}

## Key Points

- Explored [[note-created]] — brief context
- Realized [[insight-created]]

## Decisions Made

- Any decisions or conclusions reached

## Open Questions

- Unresolved questions for future exploration
```

## Step 5: Update Knowledge Graph

- Add backlinks to existing notes where the new content is relevant
- Update MOCs if they exist

## What to Save vs. Skip

**Worth saving:**
- New insights or realizations
- Decisions with rationale
- Synthesized knowledge from research
- Frameworks or models developed

**Skip:**
- Trivial Q&A exchanges
- Debugging sessions (unless pattern learned)
- Repetitive discussions already captured
- Temporary planning that's now complete

## Naming Conventions

- Kebab-case filenames: `concept-name.md`
- No subdirectories within knowledge/insights/core folders
- Links as tags: `[[MOC-topic]]` even if target doesn't exist yet
