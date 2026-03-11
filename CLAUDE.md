# agentic-kit

Personal toolkit for Claude Code: skills, hooks, pipelines, and composable presets.

## Commands

Run `just` to see available commands. Key ones:

```bash
just install                       # Reinstall all registered targets (run after any change)
just install-interactive           # Install preset interactively (first-time setup)
just install-to <target> <preset>  # Install to specific directory
just test                          # Run tests
just fmt && just lint              # Format and lint
```

**After modifying skills, presets, hooks, or common files:** run `just install` to propagate changes to all targets.

## Testing

```bash
pytest                              # All tests
pytest tests/test_install.py        # Installer tests
pytest skills/youtube/              # Skill-specific tests
```

Scripts use PEP 723 inline metadata. Run with `uv run <script>`.

## TODO

**Remind the user about these when starting work here.**

- **Agentic Knowledge Base**: Lighter-weight KB for dev/work presets. Agent reflects on work, saves learnings, avoids repeating mistakes. Session reflection, persistent memory, pattern recognition, self-updating.
