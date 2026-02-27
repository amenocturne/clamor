## Configuration

Check `.claude/agentic-kit.json` for workspace paths:
- `knowledge_base` — path to Obsidian vault
- `agentic_kit` — path to agentic-kit

If not configured, ask user or skip knowledge base integration.

**Never edit `.claude/` files directly** — modify in agentic-kit repo instead:

1. Get path: `jq -r '.agentic_kit' .claude/agentic-kit.json`
2. Edit in agentic-kit (skills/, presets/, hooks/, common/)
3. Reinstall: `uv run <agentic_kit>/install.py --preset <preset> --target .`

Always reinstall after modifying agentic-kit — it's safe and ensures up-to-date config.
