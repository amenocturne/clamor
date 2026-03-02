## Tracking Save-worthy Items

Use the TodoWrite tool to maintain a running list of things worth saving throughout the conversation. This is a scratchpad — not a structured plan.

**What to track:** Anything that might be worth saving later — insights, decisions, interesting ideas, realizations, new information. Don't worry about categorization or structure yet.

**Update frequency:** After each substantive exchange, review and update the list — add new items, consolidate duplicates, refine descriptions.

**At save time:** Use this list as a reference to ensure nothing is forgotten. The items don't map 1:1 to notes — some may merge into a single concept, others may split into several notes. The structure emerges during save planning.

## End-of-Conversation Saving

**Trigger phrases:** "let's wrap up", "save this", "that's all", "let's finish", "we're done", "done for now", "that's it", "end this"

**Default action:** When ANY end signal is detected, ALWAYS propose a save plan. Don't just summarize or say goodbye — saving is the default, not optional.

### Step 1: Review Todo List

The todo list contains save-worthy items accumulated during the conversation. Use it as a reference to ensure nothing is forgotten.

Note: Items don't map 1:1 to notes — some may merge into a single concept, others may split into several notes. Decide the structure based on atomic note principles.

If the todo list is empty or sparse, mentally review the conversation for save-worthy content.

### Step 2: Explore Existing Notes

Understand what already exists:
- Search `knowledge/`, `insights/`, `ideas/`, `core/` for related content
- Check for notes that already cover discussed concepts
- Note similar names to avoid collisions

### Step 3: Propose a Save Plan (REQUIRED)

Present a concise plan for user approval. Use this format:

```
**Save Plan:**

**Notes to create:**
- `ideas/concept-name.md` — one-line description
- `knowledge/another-concept.md` — one-line description

**Existing notes to update:** (if any)
- `knowledge/existing-note.md` — add link to new concept

**Context updates:** (if any)
- `context/history/2024-03-career-change.md` — add new event
- `context/goals/YYYY-MM.md` — mark goal complete

**Source notes to create:** (if research involved)
- `sources/articles/source-name.md` — authoritative reference worth revisiting

**Log:** `logs/YYYY-MM-DD/_topic.md`

**Skip:** [brief reason if skipping anything discussed]

Proceed?
```

**Rules for the plan:**
- One line per note — just path and brief description
- Mention existing notes that will be updated with backlinks
- No lengthy explanations — user can ask for details
- Wait for user confirmation before creating anything

### Step 4: Create Atomic Notes

After user approves, create notes:

- **Knowledge** (`knowledge/`) — general facts, external information
- **Insights** (`insights/`) — personal realizations, patterns discovered
- **Ideas** (`ideas/`) — new frameworks or theories developed

Follow atomic note principle: one concept per file.

#### Pre-Save Checklist

Before writing any note:

1. **One concept = one note.** If a note has multiple `##` sections that could stand alone, it's too big.
2. **Check links before writing.** Verify `[[wikilink]]` targets exist or match what you're creating.
3. **Calibrate length.** Read an existing note if available. If your draft is 2x+ longer, split it.

### Step 5: Create Conversation Summary

Save to `logs/YYYY-MM-DD/_Topic.md` using `.claude/templates/summary.md`.

The summary should **link to the notes created** instead of repeating content.

### Step 6: Update Knowledge Graph

- Add backlinks to existing notes where the new content is relevant
- Update MOCs if they exist

### Step 7: Consider Context Updates

Check if conversation affects context files:

- **history/** — Did a significant life event occur? Create `history/<event>.md`
- **goals/** — Was a goal achieved, abandoned, or priorities shifted?

History = life events (so user doesn't have to re-explain). Goals = what user is trying to achieve.

If updates needed, include them in the save plan.

## What to Save vs Skip

**Worth saving:**
- New insights or realizations
- Decisions with rationale
- Synthesized knowledge from research
- Frameworks or models developed
- Primary sources from research (authoritative references, foundational articles/papers)

**Skip:**
- Trivial Q&A exchanges
- Debugging sessions (unless pattern learned)
- Repetitive discussions already captured
- Temporary planning that's now complete
