---
name: spec
description: Technical specification generator. Use when user has a project idea and wants to plan before coding, create a spec, or write an implementation plan. Triggers on "write a spec", "create specification", "plan this project", "implementation plan", "design document", "spec.md".
author: amenocturne
---

# Project Spec Generator

Create technical specifications that enable one-shot MVP builds.

## Philosophy

A good spec produces working code on first build. Polish comes after.

**Architecture over features**: Features are what you build. Architecture is how they fit together. A spec without architecture produces pieces that don't connect.

## Process

### 1. Clarify requirements

Ask about unclear points:

- "When you say X, do you mean A or B?"
- "What happens when [edge case]?"
- "Walk me through the full flow, including alternate paths"

**For visual/audio/experiential features:**
- "Can you share a reference?" (image, video, site, sound)
- References resolve ambiguity without requiring exact values.

### 2. Create spec files

**Main spec** (`spec.md`):

```
# Project Name

One-line description.

## Features

- Feature list (what it does)

## User Flow

1. Step by step, including alternate paths
   - Decision point → branch A
   - Decision point → branch B

## Tech Stack

- Runtime, frameworks, key libraries

## Architecture

### Components

Which components exist and their single responsibility.

### Data Flow

How data moves through the system. Use a diagram:

```
Input → A → B → Output
        ↓
        C
```

### State Ownership

Who owns what, how changes propagate:

| State | Owner | Consumers | Update mechanism |
|-------|-------|-----------|------------------|

### Extension Patterns

How to add new things without breaking existing:

- **Add new X**: steps...
- **Add new Y**: steps...

### Constraints

What must stay true. Invariants that shouldn't be violated.

## References

- Links or descriptions of visual/audio/UX inspiration

## Open Decisions

- Things still TBD
```

**Implementation plan** (`implementation-plan.md`):

```
## MVP Scope

**In**: Core features for first working version
**Out**: Polish, nice-to-haves, post-MVP

## Task Breakdown

### Phase 1: Foundation
- Project structure
- Core types and interfaces

**Test**: N/A (types only)

### Phase 2: Components
- Each component built to interface (testable independently)

**Test**:
- Component A: test X behavior, test Y edge case
- Component B: test state transitions

### Phase 3: Integration
- Wire components together
- Verify full user flow

**Test**:
- Full flow from input to output
- Alternate paths (decision branches)

## Testing Strategy

Write unit tests for:
- **State transitions** — given state + action → expected state
- **Complex logic** — parsing, calculations, transformations
- **Component integration** — A calls B, verify B receives correct input
- **Edge cases** — empty input, invalid data, boundary conditions

Skip tests for:
- Trivial utilities (isEven, capitalize)
- Pure wrappers with no logic
- UI rendering (test manually or with e2e)

Each phase should have passing tests before moving to next phase.

## Dev Tooling

Determine if the project needs debug/tuning UI:

**Needs dev tooling if**:
- Visual parameters (colors, sizes, positions, animations)
- Audio parameters (frequencies, timing, volumes)
- Timing-sensitive behavior (delays, durations, easing)
- Complex state machines (need to jump to states, trigger events)

**Dev tooling approach**:

| Method | When to use |
|--------|-------------|
| Debug panel in UI | Visual/interactive projects, need live tweaking |
| Config file | Values change rarely, ok to restart |
| URL params | Quick toggles, shareable debug states |
| Console API | Developer-only, expose functions on window |

**Requirements**:
- Dev tools only in development builds (env check or build flag)
- Never ship to production, not even behind admin auth
- Parameters should sync to config/constants when finalized

**What to expose**:
- List tunable parameters from each component
- Group by component or category
- Include reset to defaults

## Integration Checkpoints

After each phase, what to verify:
- [ ] Tests pass
- [ ] Components work with mock inputs
- [ ] Interfaces match architecture

## Tunable Parameters

Values expected to change during polish. Design for easy tweaking.

| Parameter | Component | Default | Range/Options |
|-----------|-----------|---------|---------------|

## Definition of Done

- All user flows work
- Tests pass for core functionality
- Components communicate via defined interfaces
- Dev tooling works (if applicable)
- Tunable parameters documented
```

### 3. Discuss in Detail

Explore further when requirements are vague:

- "Make it feel like..." → ask for reference
- "Similar to X" → extract key behaviors from X
- Architecture gaps → clarify ownership and data flow
- "Needs tuning" → add to dev tooling scope
