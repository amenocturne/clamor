#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Stop hook: pipe Claude's response to TTS via kokoro-tts."""

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

FLAG_FILE = Path.home() / ".claude" / "tts-active"
PID_FILE = Path.home() / ".claude" / "tts.pid"
SPEED = os.environ.get("CLAUDE_TTS_SPEED", "2.0")
TTS_CMD = [
    "/opt/homebrew/bin/uvx",
    "kokoro-tts",
    "-",
    "--stream",
    "--speed", SPEED,
    "--model", str(Path.home() / ".local/share/kokoro-tts/kokoro-v1.0.onnx"),
    "--voices", str(Path.home() / ".local/share/kokoro-tts/voices-v1.0.bin"),
]


def notify(message: str):
    """Send macOS notification."""
    for tn in ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]:
        if os.path.exists(tn):
            subprocess.Popen([tn, "-message", message, "-title", "TTS", "-sound", "Pop"])
            return
    subprocess.Popen([
        "osascript", "-e",
        f'display notification "{message}" with title "TTS" sound name "Pop"',
    ])


def kill_previous():
    """Kill any previously running TTS process."""
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (FileNotFoundError, ValueError, ProcessLookupError, OSError):
        pass
    PID_FILE.unlink(missing_ok=True)


def extract_last_response(transcript_path: str) -> str:
    """Extract text from the last assistant message in transcript."""
    entries = []
    with open(transcript_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Find last assistant message
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        content = message.get("content", [])
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            return "\n".join(texts)
    return ""


def strip_markdown(text: str) -> str:
    """Strip markdown formatting for natural speech."""
    # Remove fenced code blocks entirely
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove headers — keep the text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove bold/italic markers
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"___(.+?)___", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Remove links — keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Remove table rows
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    # Remove table separator lines
    text = re.sub(r"^\s*\|?[\s\-:|]+\|?\s*$", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^[\s]*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove bullet point markers (- or * at start of line)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

    # Remove numbered list markers
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove blockquotes
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)

    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def main():
    if not FLAG_FILE.exists():
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    transcript_path = data.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    text = extract_last_response(transcript_path)
    text = strip_markdown(text)

    # Skip if too short or empty
    if len(text.strip()) < 10:
        sys.exit(0)

    # Kill previous TTS
    kill_previous()

    word_count = len(text.split())
    notify(f"Speaking {word_count} words...")

    # Start TTS in background
    try:
        proc = subprocess.Popen(
            TTS_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Write text and close stdin (non-blocking — Popen handles this)
        if proc.stdin:
            proc.stdin.write(text.encode())
            proc.stdin.close()

        # Save PID
        PID_FILE.write_text(str(proc.pid))
    except (OSError, FileNotFoundError) as e:
        print(f"TTS error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
