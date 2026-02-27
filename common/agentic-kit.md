## Modifying Claude Configuration

**Never edit `.claude/` files directly** — they're symlinks to agentic-kit. To modify skills, instructions, or hooks:

1. Get agentic-kit path: `jq -r '.agentic_kit' .claude/agentic-kit.json`
2. Edit in agentic-kit repo (skills/, presets/, hooks/)
3. Re-run installer to apply changes: `uv run <agentic_kit>/install.py --preset <preset> --target .`

Always reinstall after modifying agentic-kit — it's safe and ensures the workspace is up-to-date.
