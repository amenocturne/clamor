# End-of-Conversation Saving

When the user signals conversation end ("let's wrap up", "save this", "that's all"), follow this process:

## Step 1: Explore Existing Notes

- Read relevant files in `knowledge/`, `insights/`, `core/` to understand existing patterns
- Check what notes already exist to avoid duplication
- Search for similar note names to avoid ambiguity

## Step 2: Extract Atomic Notes

For new concepts worth preserving:

- **Knowledge** (`knowledge/`) — general facts, external information
- **Insights** (`insights/`) — personal realizations, patterns discovered
- **Ideas** (`ideas/`) — new frameworks or theories developed

Follow atomic note principle: one concept per file.

### Pre-Save Checklist

Before writing any note to `core/`, `ideas/`, `insights/`, or `knowledge/`:

1. **List all distinct concepts first.** Before writing anything, enumerate every separate idea that emerged. Each one is a candidate for its own note. If the list has 3+ items, you're about to write an article — split it.
2. **One concept = one note.** If a note has multiple `##` sections that could stand alone, it's too big. Extract them.
3. **Check links before writing.** For every `[[wikilink]]`, verify the target filename actually exists or matches what you're about to create. Don't guess prefixes.
4. **Read an example note for calibration.** Pick a short existing note to recalibrate length before writing. If your draft is 2x+ longer, it's probably bundling concepts.

## Step 3: Create Conversation Summary

Save to `logs/YYYY-MM-DD/_Topic.md` using the summary template.

The summary should **link to the notes created in Step 2** instead of repeating content:

```markdown
# {Topic}

> Source: [[conversation-id.json]] (if transcript saved)

## Key Points

- Explored [[note-created]] — brief context
- Realized [[insight-created]]

## Decisions Made

- Any decisions or conclusions reached

## Open Questions

- Unresolved questions for future exploration
```

## Step 4: Maintain the Knowledge Graph

- Add meaningful links with context (not just tag lists)
- Update existing notes with backlinks where relevant

## Proactive Saving

Proactively suggest creating summaries/insights when:
- A significant decision or realization occurs
- A recurring theme is discussed
- The user requests it

## What to Save vs. Skip

**Worth saving:**
- New insights or realizations
- Decisions with rationale
- Synthesized knowledge from research
- Frameworks or models developed
- Action items or next steps

**Skip:**
- Trivial Q&A exchanges
- Debugging sessions (unless pattern learned)
- Repetitive discussions already captured
- Temporary planning that's now complete

## Naming Conventions

- Kebab-case filenames: `concept-name.md`
- No subdirectories within knowledge/insights/core folders
- Links as tags: `[[MOC-topic]]` even if target doesn't exist yet
