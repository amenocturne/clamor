<p align="center">
  <img src="banner.png" alt="Clamor" width="100%">
</p>

<h3 align="center"><i>ORCHESTRATE THE NOISE</i></h3>

<p align="center"> Tmux but for agents. Because one Claude isn't loud enough. </p>

<!-- demo gif placeholder -->

## Install

```bash
cargo install clamor
```

Or build from source:

```bash
git clone https://github.com/amenocturne/clamor.git
cd clamor
cargo build --release
cp target/release/clamor ~/.local/bin/
```

### Hook setup

Clamor tracks agent state (working/waiting/done) via Claude Code hooks. Add these to your `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "type": "command", "command": "clamor hook" }],
    "Notification": [{ "type": "command", "command": "clamor hook" }],
    "PreToolUse": [{ "type": "command", "command": "clamor hook" }],
    "UserPromptSubmit": [{ "type": "command", "command": "clamor hook" }],
    "Stop": [{ "type": "command", "command": "clamor hook" }]
  }
}
```

That's it — no files to copy. The hook reads events from stdin and updates agent state in `~/.clamor/state.json`.

## Quick start

```bash
# Configure your project folders
clamor config
```

This opens `~/.clamor/config.json` — map names to paths:

```json
{
  "folders": {
    "my-app": "~/projects/my-app",
    "backend": "~/work/backend"
  }
}
```

Then launch the dashboard:

```bash
clamor
```

## Features

**Persistent sessions** — Agents live in a background daemon, not your terminal. Close the dashboard, reopen it — everything's still running. Terminal crash? SSH disconnect? Doesn't matter.

**Jump keys** — Each agent gets a home-row key (`a`/`s`/`d`/`f`/`j`/`k`/`l`/`g`/`h`). One keypress to attach, `Ctrl+F` to detach. Switching between agents is instant.

**Live state tracking** — The dashboard shows each agent's actual state (working/waiting/done) and the last tool it invoked. Spot stalled agents immediately.

**Session adoption** — Already have a Claude Code session running? `clamor adopt <session-id>` brings it under management without restarting.

**Non-blocking hooks** — State tracking uses non-blocking file locks. Clamor never slows down your Claude Code sessions.

## Usage

```
clamor                  Open the dashboard (starts daemon if needed)
clamor ls               List all agents
clamor new <title>      Spawn a new agent
clamor attach <ref>     Attach to an agent (by ID or jump key)
clamor adopt <id>       Adopt an existing Claude Code session
clamor edit <ref>       Update agent description
clamor kill <ref>       Terminate an agent
clamor kill --all       Terminate all agents
clamor clean            Remove finished agents
clamor config           Open config in $EDITOR
clamor stop             Stop the daemon
```

### Dashboard keys

| Key       | Action                        |
| --------- | ----------------------------- |
| `a`–`h`   | Jump to agent                 |
| `c`       | Create agent (inline prompt)  |
| `C`       | Create agent ($EDITOR prompt) |
| `K` + key | Kill agent                    |
| `e` + key | Edit agent description        |
| `x`       | Clean finished agents         |
| `q`       | Quit dashboard                |

### Terminal keys

| Key      | Action                     |
| -------- | -------------------------- |
| `Ctrl+F` | Detach (back to dashboard) |
| `Ctrl+C` | Send SIGINT to agent       |
| `Ctrl+J` | Snap to bottom (live view) |

## Architecture

Clamor uses a daemon-client architecture, similar to tmux:

```
┌──────────────┐    Unix socket    ┌────────────────────────┐
│              │◄─────────────────►│         Daemon         │
│   Dashboard  │  length-prefixed  │                        │
│  (TUI client)│       JSON        │  ┌───────┐ ┌───────┐   │
│              │                   │  │  PTY  │ │  PTY  │   │
└──────────────┘                   │  │ agent │ │ agent │…  │
                                   │  └───────┘ └───────┘   │
                                   └────────────────────────┘
```

- The **daemon** runs in the background, owns all agent PTY processes, and persists across dashboard restarts
- The **dashboard** connects over a Unix socket (`~/.clamor/clamor.sock`), subscribes to output streams, and renders the TUI
- **State** is tracked in `~/.clamor/state.json` with file-locked reads/writes, updated by hooks in real time

## Troubleshooting

**Agent terminal looks garbled after attaching** — Double `Ctrl+F` fixes it. The first detaches to the dashboard, the second re-attaches, resetting the terminal state.

**Daemon won't start** — Check if a stale socket exists: `rm ~/.clamor/clamor.sock` and try again.

**Hooks not updating state** — Verify that `clamor` is in your `PATH` and the hook entries are in your `.claude/settings.json`.

## License

[MIT](LICENSE)
