#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Send notification when Claude Code session ends."""
import subprocess
import sys


def notify(message: str, title: str = "Claude Code"):
    """Send system notification."""
    if sys.platform == "darwin":
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}"'
        ])
    elif sys.platform == "linux":
        subprocess.run(["notify-send", title, message])
    # Windows not yet supported


if __name__ == "__main__":
    notify("Session complete")
