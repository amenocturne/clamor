---
name: documentation
description: Project documentation guidelines. Use before committing features that change commands, architecture, or behavior. Also use when writing or updating docs, README, or CLAUDE.md. Triggers on "update docs", "write documentation", "document this", "update README".
author: amenocturne
---

# Documentation

Guidelines for maintaining project documentation.

## When to Update Docs

Update documentation **before committing** when you:
- Add new commands or change existing ones
- Add new components or change architecture
- Introduce patterns that aren't obvious from code
- Change setup or installation steps
- Make significant design decisions

## Documentation Structure

```
project/
├── README.md           # Human entry point (concise)
├── CLAUDE.md           # AI context (concise)
└── docs/               # Full documentation (detailed)
    ├── architecture.md
    ├── decisions/
    │   └── YYYY-MM-DD-decision-name.md
    ├── api.md
    ├── design.md
    └── caveats.md
```

## README.md (Human Entry Point)

What a developer needs to get started — nothing more.

```markdown
# Project Name

What this project does and why (1-2 sentences).

## Setup
git clone ...
just setup
just run

## Usage
Basic usage example.

## Docs
See [docs/](./docs/) for detailed documentation.
```

## CLAUDE.md (AI Context)

What Claude needs to work effectively — quick reference, not a manual.

```markdown
# Project Name

One-line description.

## Commands
just run        # Run in dev mode
just test       # Run tests
just lint       # Check code style

## Architecture
- src/core/     — Business logic (pure functions)
- src/cli/      — CLI entry points
- src/web/      — Web layer

## Key Patterns
- State updates via Elm Architecture
- Database IDs are SHA-256 of file paths

## Docs
Detailed documentation in docs/ — read when needed.
```

## docs/ Folder (Detailed Documentation)

Everything else goes here. Read on-demand, not always.

### docs/architecture.md
- System overview with diagrams
- Component responsibilities
- Data flow
- External dependencies

### docs/decisions/
Architecture Decision Records (ADRs):

```markdown
# YYYY-MM-DD: Decision Title

## Context
What prompted this decision?

## Decision
What was decided?

## Consequences
What are the tradeoffs?
```

### docs/caveats.md
- Known limitations
- Gotchas and edge cases
- Things that look wrong but are intentional
- Performance considerations

### docs/api.md
- Endpoint documentation
- Request/response formats
- Authentication details

### docs/design.md
- UI/UX design decisions
- Color palette, typography
- Interaction patterns

## Style Rules

1. **Concise at the top** — README and CLAUDE.md are entry points, not manuals
2. **Detailed in docs/** — Full explanations, decisions, caveats go here
3. **Commands over prose** — Show `just test`, don't explain
4. **Examples over explanations** — Code snippets clarify faster
5. **Current over historical** — Remove outdated info
6. **Don't duplicate** — If info exists elsewhere, reference it

## Don't Over-Document

Documentation already exists in many places — don't repeat it:

**Commands**: Justfile has comments. Just show 2-3 key commands, then:
```markdown
## Commands
just dev    # Start dev server
just test   # Run tests

Run `just` to see all available commands.
```

**Code**: Types and function signatures are documentation. Don't restate them.

**Config**: Config files often have comments. Reference the file, don't copy it.

**Dependencies**: package.json/pyproject.toml list them. Don't maintain a separate list.

## Anti-patterns

- Listing every just command when `just` shows them all
- Documenting function parameters that types already describe
- Repeating config file contents in docs
- Maintaining dependency lists outside package manager
- Explaining standard library functions
- Adding comments to self-explanatory code
