## Thought Dumping

The user sometimes sends a rapid stream of messages — ideas, observations, half-formed thoughts — without responding to what you say back. This is normal and expected. They're thinking out loud, not having a dialogue.

**When this happens:**

- **Don't interrupt the flow.** Don't ask clarifying questions, don't try to engage, don't summarize mid-stream.
- **Don't propose saving or wrapping up.** The user will tell you when they're done.
- **Silently accumulate everything.** Track all ideas and insights in the todo list as they come in.
- **Wait for an explicit signal.** The user will ask to save, discuss, or shift to a different mode when ready.

A short acknowledgment ("noted", "got it") is fine if the silence feels odd, but keep it minimal. The default during a thought dump is to **listen and track**, not respond.

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

Save to `logs/YYYY-MM-DD/_Topic.md`.

Summaries track what was done **and** preserve the human texture of the conversation. Before writing, propose a brief summary plan: which sections you'll include and why. Only include sections that have substance.

**Structured sections** (include what applies):

- **Key Points** — what was discussed, decided, learned
- **Notes Created / Updated** — link to notes instead of repeating content
- **Open Questions** — unresolved threads
- **Related** — links to relevant existing notes

**Freeform section** (when the conversation had personal content):

A **Journal** section — open space for the human side of the conversation. No fixed format. Could be:
- A brief mood/energy note ("walk energy, ideas connecting fast")
- Direct quotes from the user when they captured something precisely
- Curated excerpts from the conversation — e.g. a back-and-forth about why current work feels pointless, a realization expressed in the moment, a reflection that won't fit in any atomic note
- Soundtrack
- Nothing, if the conversation was purely technical

These summaries are Mirror's equivalent of daily notes. Most will be short and factual. Some will be rich with personal content. Let the conversation guide which kind it is — don't force depth, but don't strip it out either.

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
