# Notification Hook

Send system notifications for Claude Code events.

## Events

- **Stop** — "Session complete" when conversation ends
- **Notification** — triggered when Claude needs user input:
  - `permission_prompt` — "Permission required" (tool approval needed)
  - `idle_prompt` — "Waiting for your input" (idle for 60+ seconds)
  - Other — "Claude needs your input"

## Setup

Configured automatically via `hooks.json`. Both events are included.

## Platforms

- **macOS**: Uses `osascript` for native notifications
- **Linux**: Uses `notify-send` (requires libnotify)
- **Windows**: Not yet supported
