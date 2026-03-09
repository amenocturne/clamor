# Fleet

Orchestrate multiple Claude Code instances through tmux with a live dashboard.

## Setup

### 1. Build and install

```bash
cd tools/fleet && cargo build --release
cp target/release/fleet ~/.local/bin/fleet
```

Or from the agentic-kit root: `just fleet-install`

### 2. Configure

```bash
fleet config
```

```json
{
  "folders": {
    "my-app": "~/projects/my-app"
  },
  "pinned_sessions": {
    "editor": "main"
  }
}
```

`pinned_sessions` maps a label to a tmux session name — these appear at the top of the dashboard with number keys for quick switching.

### 3. Tmux keybinding

Add to your tmux config (`~/.config/tmux/tmux.conf` or `~/.tmux.conf`):

```tmux
bind-key -n 'C-f' run-shell -b "fleet popup"
```

Reload: `tmux source-file ~/.config/tmux/tmux.conf`

This opens the fleet dashboard as a popup overlay. `fleet popup` handles edge cases automatically (e.g. dismissing the popup terminal first if it's open).

### 4. Claude Code keybindings

Claude Code captures `Ctrl+F` and `Ctrl+T` by default. Unbind them so tmux can intercept — create `~/.claude/keybindings.json`:

```json
{
  "bindings": [
    {
      "context": "Global",
      "bindings": {
        "ctrl+f": null,
        "ctrl+t": null
      }
    }
  ]
}
```

Fleet warns on startup if this isn't configured.

## Commands

| Command | Description |
|---------|-------------|
| `fleet` | Open the live TUI dashboard |
| `fleet popup` | Open dashboard in a tmux popup (bind to Ctrl+F) |
| `fleet ls` | One-shot status table |
| `fleet new` | Spawn a new agent |
| `fleet attach <ref>` | Switch to an agent's tmux session |
| `fleet edit <ref>` | Update an agent's description |
| `fleet kill <ref>` | Terminate an agent |
| `fleet kill --all` | Terminate all agents |
| `fleet clean` | Remove done agents |
| `fleet config` | Open config in $EDITOR |
| `fleet pick` | Lightweight session picker |
| `fleet hook` | Process hook event (internal) |

## Popup workflow

1. Press `Ctrl+F` from any tmux session (including inside Claude Code agents)
2. Fleet dashboard opens as a popup overlay
3. Press a jump key to switch to an agent, or `c` to spawn a new one
4. Popup closes automatically after switching

If a popup terminal is open (`Ctrl+T`), fleet dismisses it first (detach, not kill — running processes are preserved), then opens the dashboard.
