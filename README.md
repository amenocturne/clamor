# Fleet

A terminal multiplexer for Claude Code agents. Think tmux, but purpose-built for managing multiple AI agents simultaneously.

## Why Fleet Exists

Claude Code is powerful, but it's one agent in one terminal. Real-world development often needs several agents working in parallel — one refactoring a module, another writing tests, a third fixing CI. Without fleet, you're juggling terminal tabs, losing track of which agent is doing what, and if your terminal crashes, all sessions die with it.

Fleet solves this with a daemon-client architecture (like tmux). A background daemon owns the agent processes — they survive if your dashboard crashes, your terminal closes, or you disconnect entirely. Reconnect anytime and pick up where you left off.

## How It Works

Fleet manages the full agent lifecycle:

1. **Spawn** — create an agent with a task description, pointed at a project folder
2. **Monitor** — a live TUI dashboard shows all agents, their current state, and what tool they're using
3. **Interact** — jump into any agent's terminal with a single keypress, interact with it, jump back to the dashboard
4. **Adopt** — already have a Claude Code session running outside fleet? Bring it under management without restarting it

Each agent runs in its own PTY (pseudoterminal) managed by the daemon. The daemon captures output into ring buffers, so when you attach to an agent you see its recent history — not a blank screen.

### State Tracking via Hooks

Fleet installs Claude Code hooks that fire on key events (tool use, notifications, completion). This gives the dashboard real-time awareness of each agent's state:

- **Working** — actively executing tools or processing
- **Input** — waiting for your response
- **Done** — finished its task

You see at a glance which agents need attention vs. which are happily working away.

## Killer Features

**Persistent sessions** — Agents live in the daemon, not your terminal. Close the dashboard, reopen it, everything's still running. No lost work, ever.

**Jump keys** — Each agent gets a home-row key (a/s/d/f/j/k/l/g/h). One keypress to attach, `Ctrl+F` to return to the dashboard. Switching between agents is instant.

**Live state awareness** — Not just "is it running" — you see the actual state (working/waiting/done) and the last tool invoked. Spot a stalled agent immediately instead of discovering it 20 minutes later.

**Session adoption** — Started a Claude Code session the normal way and realize it's going to take a while? `fleet adopt <session-id>` brings it into fleet's management without interruption.

**Non-blocking hooks** — The hook integration uses non-blocking file locks. Fleet never slows down Claude Code, even under heavy load.

## Quick Start

```bash
# Build and install
cd tools/fleet && cargo build --release
cp target/release/fleet ~/.local/bin/fleet

# Or from agentic-kit root
just fleet-install

# Configure your project folders
fleet config
```

Config is a simple JSON file mapping names to paths:

```json
{
  "folders": {
    "my-app": "~/projects/my-app",
    "backend": "~/work/backend"
  }
}
```

Then just run `fleet` to open the dashboard. Create agents, monitor them, switch between them — all from one screen.

Run `fleet --help` for the full command list.

## Troubleshooting

**Agent terminal rendering breaks after attaching** — Some tools (e.g. Claude Code) use non-standard terminal rendering that can leave the attached terminal in a broken state. Double `Ctrl+F` fixes it — the first detaches to the dashboard, the second re-attaches to the last agent, resetting the terminal.
