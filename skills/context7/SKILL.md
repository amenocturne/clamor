---
name: context7
description: "Fetch up-to-date library/framework documentation and code examples. Use when writing code with external libraries, setting up tools, configuring frameworks, or needing current API docs. Triggers on: library names, npm/pip/cargo packages, framework setup, API references, \"how do I use X\", \"docs for X\", \"context7\"."
author: amenocturne
---

# Context7 — Library Documentation

## Commands

```bash
# Fetch docs for a library (resolve + query in one step)
uv run scripts/context7.py docs <library> "<query>"

# Examples
uv run scripts/context7.py docs nextjs "how to set up middleware"
uv run scripts/context7.py docs react "useEffect cleanup patterns"
uv run scripts/context7.py docs tailwindcss "dark mode configuration"

# Search for libraries (just resolve, no docs)
uv run scripts/context7.py search <library>

# Fetch docs by exact library ID (skip resolve step)
uv run scripts/context7.py docs --id /vercel/next.js "middleware setup"

# Limit token budget (default: 10000)
uv run scripts/context7.py docs --tokens 5000 react "hooks overview"
```

All commands run from the skill directory: `{SKILL_DIR}/scripts/context7.py`

## Important

- No API key required (rate-limited). Set `CONTEXT7_API_KEY` for higher limits.
- Prefer this over training data for library-specific code — docs are always current.
- If a library isn't found, try alternative names (e.g., "nextjs" vs "next.js").
- Don't call more than 3 times per user question — use the best result you have.
