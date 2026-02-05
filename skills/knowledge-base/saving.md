# End-of-Conversation Saving

When the user signals conversation end ("let's wrap up", "save this", "that's all"), follow this process:

## Step 1: Explore Existing Notes

- Read relevant files in `knowledge/`, `insights/`, `core/` to understand existing patterns
- Check what notes already exist to avoid duplication
- Understand the linking and tagging conventions used

## Step 2: Create Conversation Summary

Save to `logs/YYYY-MM-DD/<topic>.md` using the summary template:

```markdown
# {Topic}

> Source: [[conversation-id.json]] (if transcript saved)

## Key Points

- Main takeaways from the conversation

## Decisions Made

- Any decisions or conclusions reached

## Open Questions

- Unresolved questions for future exploration

## Related

- [[link to related notes]]
```

## Step 3: Extract Atomic Notes

For new concepts worth preserving:

- **Knowledge** (`knowledge/`) — general facts, external information
- **Insights** (`insights/`) — personal realizations, patterns discovered
- **Ideas** (`ideas/`) — new frameworks or theories developed

Follow atomic note principle: one concept per file.

## Step 4: Maintain the Knowledge Graph

- Add wiki link tags at bottom of each new note
- Update relevant MOCs with new links
- Add backlinks to existing related notes

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
