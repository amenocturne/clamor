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

## Dependencies

- **macOS**: Install `terminal-notifier` for reliable notification support:
  ```
  brew install terminal-notifier
  ```
  Without it, falls back to `osascript` which may be silently blocked by macOS on newer versions (Sequoia+).
- **Linux**: Install `libnotify` (provides `notify-send`)

## Platforms

- **macOS**: Uses `terminal-notifier` (preferred) or `osascript` as fallback, with sound
- **Linux**: Uses `notify-send` (no sound)
- **Windows**: Not supported

## Sound

macOS notifications play a subtle "Tink" sound. To customize, edit `hook.py` and change the `sound` parameter in `notify()` calls. Available sounds: `default`, `Glass`, `Ping`, `Pop`, `Purr`, `Sosumi`, `Submarine`, `Blow`, `Bottle`, `Frog`, `Funk`, `Hero`, `Morse`, `Tink`.
