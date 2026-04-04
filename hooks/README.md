# Clamor Hook

Reports agent state changes (working, waiting for input, done) to the clamor daemon.

Triggered on: `SessionStart`, `Notification`, `PreToolUse`, `UserPromptSubmit`, `Stop`.

Configure in `.claude/settings.json` by pointing each hook event to `clamor hook`. The subcommand reads the event from stdin and updates agent state in `~/.clamor/state.json`. Exits silently if clamor isn't installed.
