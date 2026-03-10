# Fleet

Terminal multiplexer for Claude Code agents. Manages multiple instances with a live dashboard, persistent PTYs (agents survive client crashes), and color-coded sessions.

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
  }
}
```

## Commands

| Command | Description |
|---------|-------------|
| `fleet` | Open the live TUI dashboard |
| `fleet ls` | One-shot status table |
| `fleet new` | Spawn a new agent |
| `fleet adopt <session-id>` | Resume an external Claude Code session inside fleet |
| `fleet edit <ref>` | Update an agent's description |
| `fleet kill <ref>` | Terminate an agent |
| `fleet kill --all` | Terminate all agents |
| `fleet clean` | Remove done agents |
| `fleet stop` | Stop the fleet daemon |
| `fleet config` | Open config in $EDITOR |
| `fleet hook` | Process hook event (internal) |

## Dashboard keys

| Key | Action |
|-----|--------|
| Jump key (a/s/d/f/j/k/l/g/h) | Attach to agent |
| `c` | Create new agent (inline) |
| `C` | Create new agent (via $EDITOR) |
| `R` | Adopt external Claude Code session |
| `K` + jump key | Kill agent |
| `q` / `Esc` | Quit dashboard |

## Terminal view keys

| Key | Action |
|-----|--------|
| `Ctrl+F` | Return to dashboard |
| `Ctrl+C` | Send SIGINT to agent |
| All other keys | Forwarded to agent PTY |

## Architecture

Fleet uses a client-server model (like tmux). A background daemon holds all PTYs — agents survive if the dashboard crashes or is closed. The daemon starts automatically and can be stopped with `fleet stop`.

## Debug mode

Set `FLEET_DEBUG=1` to substitute `fleet mock-agent` for `claude`, enabling testing without real Claude instances.
