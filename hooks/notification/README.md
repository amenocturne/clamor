# Notification Hook

Send system notifications for Claude Code events.

## Events

- **Stop** — "Session complete" when conversation ends
- **Notification** — "Claude needs your input" when Claude is waiting

## Setup

Configured automatically via `hooks.json`. Both events are included.

## Platforms

- **macOS**: Uses `osascript` for native notifications
- **Linux**: Uses `notify-send` (requires libnotify)
- **Windows**: Not yet supported
