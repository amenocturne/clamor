---
name: fleet
description: CLI orchestrator for multiple Claude Code instances via tmux. Use when user wants to spawn, monitor, or manage parallel agent sessions.
author: amenocturne
---

# Fleet

Orchestrate multiple Claude Code instances through tmux with a live dashboard.

> Run commands via justfile: `just -f <skill-path>/justfile <recipe> [flags]`

## Setup

Build the fleet binary:

```bash
just -f <skill-path>/justfile build
```

Optionally add the binary to PATH or create a symlink:

```bash
ln -s <skill-path>/target/release/fleet ~/.local/bin/fleet
```

Configure watched folders via:

```bash
fleet config
```

## Commands

### dashboard (default)

Open the live TUI dashboard showing all active agents.

```bash
fleet
```

### ls

One-shot status of all agents (no TUI).

```bash
fleet ls
```

### new

Spawn a new Claude Code agent in a tmux pane.

```bash
fleet new
```

### attach

Switch to an agent's tmux pane.

```bash
fleet attach <ref>
```

`<ref>` can be an agent index or name.

### edit

Update an agent's description.

```bash
fleet edit <ref>
```

### kill

Terminate an agent's tmux pane.

```bash
fleet kill <ref>
```

### clean

Remove all agents in "done" state.

```bash
fleet clean
```

### config

Open fleet configuration for editing.

```bash
fleet config
```

### hook

Process a Claude Code hook event (called by the fleet hook, not directly by users).

```bash
fleet hook
```

## Important

- Fleet requires tmux to be installed and running
- Agents are tracked via hook events (Notification, PreToolUse, Stop)
- The fleet hook must be installed for state tracking to work
