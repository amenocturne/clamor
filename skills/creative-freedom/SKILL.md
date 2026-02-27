---
name: creative-freedom
description: Deep autonomous creative exploration with multi-perspective analysis. Use when user grants full creative control to design a complete solution. Triggers on "take creative freedom", "design it fully", "explore this creatively", "don't be efficient, be creative", "use whatever tools/agents you need".
author: amenocturne
---

# Creative Freedom

Enables deep, autonomous creative exploration where you take full ownership of developing a solution. Instead of incremental back-and-forth, use multiple parallel perspectives to develop a comprehensive vision, then present it for review.

Works for any creative endeavor: system architecture, product design, visual design, writing, problem-solving, strategy, or any task benefiting from divergent exploration.

## When to Use

- User explicitly grants creative freedom
- User wants a complete vision, not incremental decisions
- User says "design it fully" or "explore this creatively"
- User wants you to use whatever tools and resources you need
- The task benefits from divergent thinking before convergence

## Core Approach

**The user has delegated creative authority to you.** Don't ask permission at each step — use the freedom granted.

### 1. Gather Context

Before exploring, understand:
- Read existing work, specs, or prior attempts
- Check project notes for goals and constraints
- Understand what exists vs what's being created

### 2. Launch Parallel Perspectives

Spawn multiple subagents simultaneously, each with a distinct lens:

**Builder Perspective**
- How would you actually construct this?
- What are the components and their relationships?
- What's the structure, flow, or architecture?
- What makes this work well in practice?

**Critical Perspective**
- Stress-test every assumption
- Find flaws, contradictions, blind spots
- Challenge "obvious" choices
- Ask: "What could go wrong? What's missing? What's naive?"

**Research Perspective**
- Find real-world references and prior art
- Search for similar solutions and analyze what works
- Look at adjacent domains for transferable ideas
- Gather specific examples, names, techniques

**Alternatives Perspective**
- Propose radically different directions
- What if we did the opposite?
- Ideas from unrelated domains
- Deliberately unconventional approaches

### 3. Research Grounded in Reality

Use web search to find:
- Real examples and references
- Techniques with proper names
- People or projects doing similar work
- Approaches that have been proven

Don't just imagine — ground ideas in what actually exists.

### 4. Synthesize Into Vision

After gathering all perspectives:
- Find the threads that weave through multiple viewpoints
- Resolve contradictions with intentional choices
- Build a coherent narrative from the fragments
- Create a complete, actionable vision

## Key Principles

| Principle | Description |
|-----------|-------------|
| Breadth first | Explore many directions before converging |
| Multiple lenses | Same problem viewed from builder, critic, researcher, contrarian |
| No premature efficiency | Don't optimize for tokens/time, optimize for insight |
| Research-grounded | Real references, not just imagination |
| Complete output | Present a finished vision, not fragments to assemble |

## Output Format

Adapt the structure to the domain, but always include:

```
## Executive Summary
[Core concept and essence in 2-3 sentences]

## Guiding Principles
[Philosophy driving the decisions, with cited influences where relevant]

## The Solution
[What it is, how it works, why this approach]
[Structure this section appropriately for the domain]

## Key Decisions & Rationale
[Important choices made and why — helps user understand tradeoffs]

## Edge Cases & Considerations
[What happens in unusual situations, potential issues, mitigations]

## What This Is / What This Is Not
[Clear boundaries — prevents scope creep, guides future decisions]

## Open Questions
[Details that need resolution, decisions deferred to user]

## Sources & Inspiration
[Links, references, examples, techniques discovered during research]
```

## Anti-Patterns

**Don't:**
- Ask permission at each step (user granted freedom, use it)
- Converge too early (let contradictory ideas coexist until synthesis)
- Skip the critique (prevents blind spots)
- Ignore research (ground ideas in what actually works)
- Present fragments (synthesize into one coherent vision)
- Be efficient (be thorough instead)

**Do:**
- Take ownership of the creative direction
- Let multiple perspectives argue before resolving
- Include references to real work, not just abstract concepts
- Present a complete vision ready for feedback
- Acknowledge uncertainty where it exists

## Example Prompt Structure for Subagents

When launching parallel agents, give them distinct roles:

**Builder Agent**: "Approach this as someone who needs to actually build it. What's the structure? What are the components? How do they connect? What makes this work well? Be concrete and practical."

**Critical Agent**: "Critique this approach ruthlessly. What assumptions might be wrong? What edge cases are being ignored? What would a skeptic say? What's naive about this? Find the weaknesses before we commit."

**Research Agent**: "Search for similar work, techniques, and references. Find real examples of this done well. Look at adjacent domains. Gather specific names, links, and examples we can learn from."

**Alternatives Agent**: "Propose 3 radically different directions. What if we did the opposite? What would this look like from a completely different angle? What would someone from an unrelated field suggest? Push beyond the obvious."

## Domain Adaptation

The four perspectives apply universally but manifest differently:

| Domain | Builder Focus | Critique Focus | Research Focus |
|--------|---------------|----------------|----------------|
| System design | Architecture, components, data flow | Failure modes, scalability, complexity | Similar systems, patterns, case studies |
| Visual design | Composition, hierarchy, aesthetics | Usability, accessibility, edge cases | Design references, techniques, artists |
| Writing | Structure, voice, narrative arc | Clarity, gaps, reader confusion | Similar works, style references |
| Product | Features, UX flow, value prop | Market fit, competition, assumptions | Competitor analysis, user research |
| Strategy | Actions, timeline, resources | Risks, blind spots, what could fail | Case studies, precedents |

## When to Stop

You're done exploring when:
- Each perspective has contributed meaningful input
- Research has grounded the ideas in reality
- Contradictions have been intentionally resolved
- The synthesis forms a coherent, actionable vision
- You can present it as a complete document

Then present to the user for feedback and iteration.
