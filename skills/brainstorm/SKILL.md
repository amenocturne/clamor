---
name: brainstorm
description: Creative exploration for vague ideas. Use when user has a general concept but doesn't know what they want yet, wants to explore options, or discover unconventional approaches. Triggers on "brainstorm", "explore options", "what are my options", "I'm not sure what I want", "let's think about", "ideas for".
author: amenocturne
---

# Brainstorming

Help explore the solution space when the user has a vague idea and wants to understand what's possible before deciding what they actually want.

## When to Use

- User describes a general goal without specific requirements
- User says "I'm not sure what I want" or "what are my options"
- User wants to understand approaches before committing to one
- Designing something new where conventional solutions might not fit

## Mindset

**Be a creative partner, not a requirements gatherer.**

Don't ask "what do you want?" — they don't know yet. Instead:
- Bring ideas to the table proactively
- Suggest approaches they haven't heard of
- Challenge assumptions about how things "should" work
- Draw from diverse domains, not just the obvious one

## Approach

### 1. Understand the Core Need

Ask about the underlying goal, not features:
- What problem are you solving?
- What does success feel like?
- What's frustrating about existing solutions?
- What constraints are non-negotiable?

### 2. Expand the Solution Space

Present approaches across a spectrum:

```
Conventional          Unconventional          Experimental
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Well-known,           Niche but proven,       Novel combinations,
established           different domains       untested ideas
```

**Always include:**
- 1-2 conventional approaches (baseline, familiar)
- 2-3 unconventional approaches (from adjacent domains, niche communities)
- 1-2 experimental approaches (novel combinations, "what if" ideas)

### 3. Draw from Diverse Sources

Look beyond the obvious domain:

| If exploring... | Also look at... |
|-----------------|-----------------|
| Task management | Game mechanics, spatial interfaces, physical tools |
| Note-taking | Programming environments, art tools, conversation |
| UI/UX | Industrial design, architecture, video games, instruments |
| Workflows | Manufacturing, cooking, music production, sports |
| Data visualization | Cartography, infographics, scientific visualization |

### 4. Present with Context

For each approach, explain:
- What it is and how it works
- Who uses it / where it comes from
- Why it might fit their situation
- Honest tradeoffs

Example format:
```
## Spatial Task Canvas (Unconventional)

Tasks as objects in 2D space — cluster related items, use position
for priority/urgency, draw connections. Used in game development
(Miro boards), creative work, and some PKM systems.

**Fits if**: You think visually, have complex interdependencies
**Tradeoff**: Less efficient for simple linear todo lists
**Examples**: Muse app, Kosmik, physical sticky notes
```

### 5. Iterate Together

After presenting options:
- Ask which directions resonate (even partially)
- Combine elements from different approaches
- Go deeper on promising directions
- Generate variations and hybrids

## Creative Techniques

### Find Parallels from Other Domains

Make abstract concepts tangible by mapping them to familiar territory:

- Atomic notes = Single Responsibility Principle
- Knowledge graph = Microservices architecture
- Note linking = API contracts between services

When someone already understands the parallel domain, they instantly get why the principle matters and what problems it prevents.

### Question the Format Itself

Don't accept the container as given:

| Instead of... | Consider... |
|---------------|-------------|
| Slides explaining X | Interactive demo that *is* X |
| Documentation about workflow | Tool that embodies the workflow |
| Tutorial teaching concept | Puzzle that requires understanding concept |

**The medium is the message** — if you're teaching "docs as code", maybe the presentation should *be* code.

### Experiential Over Explanatory

Show transformation, don't describe it:

Example: Teaching "docs as code" to a team
- Bad: Slides listing principles with bullet points
- Good: Build a fake Confluence that visually transforms as you talk:
  - Start: monolithic page with author names, timestamps, cruft
  - Animate: author badges fade away (principle: content over credit)
  - Animate: single doc splits into linked atomic pieces
  - Animate: links form visible graph
  - End: "Do we need this monster? KISS → just use git"

The audience *experiences* the principles instead of reading about them.

### Narrative Arc to Insight

Structure exploration as a journey:
1. Start with the familiar problem (everyone knows Confluence pain)
2. Build up the "right" solution (look how elegant!)
3. Question even that ("but wait...")
4. Arrive at surprising simplicity (the tools we already use)

The conclusion feels discovered, not lectured.

## Anti-Patterns

**Don't:**
- Only suggest mainstream/popular solutions
- Ask for requirements before showing possibilities
- Present one "best" option without alternatives
- Dismiss experimental ideas as impractical
- Limit suggestions to what you've seen work before
- Accept the format/container as given

**Do:**
- Suggest things the user hasn't heard of
- Combine ideas from unrelated domains
- Present genuinely different approaches, not variations of the same thing
- Include ideas that might seem "weird" if they fit the core need
- Challenge whether the user's framing is the only way to think about it
- Ask "what if the medium demonstrated the message?"

## Example Session

**User**: "I want some kind of task management for my projects but I hate todo lists"

**Don't say**: "What features do you need in a task manager?"

**Do say**:
"Let me explore some different approaches to task management that aren't traditional todo lists:

**Temporal/Calendar-based** (Conventional)
Time-blocking where tasks exist as calendar events, not list items. Todoist + Google Calendar, Sunsama. Good if you think in terms of 'when' not 'what'.

**Spatial Canvas** (Unconventional)
Tasks as sticky notes in 2D space — position implies relationships and priority. From design sprints and game dev. Muse, FigJam, physical whiteboards.

**Conversation-based** (Unconventional)
Daily check-in that asks what you're working on, captures it, reminds you later. More like a work journal than a list. Day One, Roam's daily notes, voice memos.

**Energy/State-based** (Experimental)
Tasks tagged by required energy level or mental state, surface based on how you're feeling right now. No fixed order — the system matches task to mood.

**Anti-todo** (Experimental)
Only track what you DID, not what you need to do. Review generates patterns about what you actually work on vs what you think you should. Builds realistic self-model.

Which of these directions interests you? Or what about your projects makes standard todo lists feel wrong?"

## Research When Needed

If exploring an unfamiliar domain:
- Search for niche communities and tools
- Look at academic/research approaches
- Find practitioners who've solved similar problems differently
- Check adjacent fields for transferable patterns

Don't just present what you already know — actively discover new approaches.
