# Notification Hook

Send system notification when Claude Code session ends.

## Setup

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python path/to/notification/hook.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Platforms

- **macOS**: Uses `osascript` for native notifications
- **Linux**: Uses `notify-send` (requires libnotify)
- **Windows**: Not yet supported
