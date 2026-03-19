<p align="center">
  <img src="banner.png" alt="Clamor" width="100%">
</p>

<h3 align="center"><i>ORCHESTRATE THE NOISE</i></h3>

<p align="center"> Tmux for agents. Because one Claude isn't loud enough. </p>

<p align="center">A terminal multiplexer for managing parallel Claude Code sessions.</p>

<!-- demo gif placeholder -->

## Why

You're running five Claude Code sessions in parallel. Tab names blur together. You can't tell which agent needs input and which is still working. Switching between them means hunting through tmux windows or terminal tabs. Spawning a new one is a ritual of `cd`, naming, and arranging.

Clamor fixes this without replacing your workflow. It's *not* a new terminal, *not* a new editor, *not* an IDE that swallows everything. It's a single tool that does one thing well: manage parallel agent sessions. It runs inside your existing terminal, alongside tmux, inside whatever setup you already have. Unix philosophy — small, composable, stays out of the way.

## Features

**Persistent sessions** — Agents live in a background daemon, not your terminal. Close the dashboard, reopen it — everything's still running. Terminal crash? SSH disconnect? Doesn't matter.

**Jump keys** — Each agent gets a home-row key (`a`/`s`/`d`/`f`/`j`/`k`/`l`/`h`, overflow to `1`–`0`). One keypress to attach, `Ctrl+F` to detach. Switching between agents is instant.

**Live state tracking** — The dashboard shows each agent's actual state (working/waiting/done). Spot stalled agents immediately.

**Color-coded title bar** — When attached, a title bar shows the project name and a distinct color so you always know where you are. No squinting at tab names.

**Auto-resume** — The daemon automatically resumes agent sessions on restart. Terminal crash, SSH disconnect, daemon restart — agents pick up where they left off.

**Session adoption** — Already have Claude Code sessions from before? Press `R` in the dashboard to adopt an existing session into Clamor.

**Batch operations** — Select multiple agents with `v`, select all with `V`, then act on the selection. Filter agents by name with `/`.

**Non-blocking hooks** — State tracking uses non-blocking file locks. Clamor never slows down your Claude Code sessions.

## Quick start

### Install

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

### Configure folders

```bash
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

### Launch

```bash
clamor
```

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

| Key            | Action                           |
| -------------- | -------------------------------- |
| `a`–`h`, `1`–`0` | Jump to agent                 |
| `J` / `K`      | Navigate agent list (vim-style)  |
| `g` / `G`      | Jump to first / last agent       |
| `Enter`        | Attach to selected agent         |
| `c`            | Create agent (inline prompt)     |
| `C`            | Create agent ($EDITOR prompt)    |
| `x` + key      | Kill agent (with confirmation)   |
| `e` + key      | Edit agent description           |
| `v`            | Toggle select agent              |
| `V`            | Select / deselect all            |
| `/`            | Filter agents by name            |
| `R`            | Adopt existing Claude session    |
| `?`            | Help popup                       |
| `Esc`          | Clear selection                  |
| `q`            | Quit dashboard                   |

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
