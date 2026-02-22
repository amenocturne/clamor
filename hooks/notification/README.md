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

- **macOS**: Uses `osascript` for native notifications with sound
- **Linux**: Uses `notify-send` (requires libnotify, no sound)
- **Windows**: Not yet supported

## Sound

macOS notifications play a subtle "Tink" sound. To customize, edit `hook.py` and change the `sound` parameter in `notify()` calls. Available sounds: `default`, `Glass`, `Ping`, `Pop`, `Purr`, `Sosumi`, `Submarine`, `Blow`, `Bottle`, `Frog`, `Funk`, `Hero`, `Morse`, `Tink`.
