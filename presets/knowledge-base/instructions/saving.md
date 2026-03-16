## Thought Dumping

The user sometimes sends a rapid stream of messages — ideas, observations, half-formed thoughts — without responding to your questions or comments. This is normal. They're brain-dumping, not ignoring you.

**Keep engaging normally** — share your thoughts, react to ideas, make connections, ask questions. The only thing that changes is: don't expect answers right now. If you asked something and the user sends a new unrelated thought instead of answering, that's fine — they'll circle back when the dump is done.

**What NOT to do during a brain dump:**

- Don't push for answers to your questions — note them, move on
- Don't propose saving or wrapping up — the user will signal when they're done
- Don't treat unanswered questions as blockers — keep engaging with new input as it comes

## Tracking Save-worthy Items

**CRITICAL: Use the TodoWrite tool to maintain a running list of things worth saving throughout the conversation.** This is not optional — it is the primary mechanism for ensuring nothing is lost at save time. Without it, you will reconstruct from memory and miss things.

This is a scratchpad — not a structured plan. Quick phrases are fine.

**What to track:** Anything that might be worth saving later — insights, decisions, interesting ideas, realizations, new information, connections between ideas, perception shifts, interesting examples or analogies. Don't worry about categorization or structure yet.

**Update frequency:** After each substantive exchange (every 1-3 messages), review and update the list — add new items, consolidate duplicates, refine descriptions. **Do this proactively as the conversation unfolds, not retroactively at save time.** Each individual message may contain save-worthy content — check each one.

**At save time:** Use this list as a reference to ensure nothing is forgotten. The items don't map 1:1 to notes — some may merge into a single concept, others may split into several notes. The structure emerges during save planning.

## End-of-Conversation Saving

**Trigger phrases:** "let's wrap up", "save this", "that's all", "let's finish", "we're done", "done for now", "that's it", "end this"

**Default action:** When ANY end signal is detected, ALWAYS propose a save plan. Don't just summarize or say goodbye — saving is the default, not optional.

### Step 1: Review Todo List and Conversation

The todo list contains save-worthy items accumulated during the conversation. Use it as the **primary source** to ensure nothing is forgotten.

Note: Items don't map 1:1 to notes — some may merge into a single concept, others may split into several notes. Decide the structure based on atomic note principles.

**Even with a good todo list, re-scan the conversation message by message.** Check each user message for: insights, analogies, perception shifts, connections between domains, new frameworks, interesting examples, and emotional content worth preserving. The todo list captures what you noticed in the moment — the re-scan catches what you missed.

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
