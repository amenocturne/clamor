#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Send system notification for Claude Code events."""
import json
import os
import subprocess
import sys


def notify(message: str, title: str = "Claude Code", sound: str = "Tink"):
    """Send system notification with sound."""
    if sys.platform == "darwin":
        for tn in ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]:
            if os.path.exists(tn):
                subprocess.run([tn, "-message", message, "-title", title, "-sound", sound])
                return
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "{sound}"'
        ])
    elif sys.platform == "linux":
        subprocess.run(["notify-send", title, message])


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        data = {}

    event = data.get("hook_event_name", "")
    notification_type = data.get("notification_type", "")

    if event == "Notification":
        if notification_type == "permission_prompt":
            notify("Permission required")
        elif notification_type == "idle_prompt":
            notify("Waiting for your input")
        else:
            notify("Claude needs your input")
    elif event == "Stop":
        notify("Session complete")
