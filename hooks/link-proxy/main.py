#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Link proxy - URL masking for Claude Code.

Transforms internal URLs to placeholders before Claude reads files,
restores them when writing. Designed for environments where a proxy
masks URLs in API traffic but files on disk have real URLs.

Single-file implementation with deterministic mappings.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

# Paths - relative to this script
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DOMAINS_FILE = SCRIPT_DIR / "domains.txt"
MAPPINGS_FILE = DATA_DIR / "mappings.json"
SESSIONS_DIR = DATA_DIR / "sessions"

# Placeholder pattern
PLACEHOLDER_RE = re.compile(r"\[InternalLink_([a-zA-Z0-9]+)_([a-f0-9]{8})\]")


def load_domains() -> list[str]:
    """Load internal domains from config file."""
    if not DOMAINS_FILE.exists():
        return []
    lines = DOMAINS_FILE.read_text().strip().split("\n")
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def build_url_pattern(domains: list[str]) -> re.Pattern | None:
    """Build regex to match URLs for configured domains."""
    if not domains:
        return None

    # Extract base domains (last 2 parts)
    base_domains = set()
    for domain in domains:
        parts = domain.lower().split(".")
        if len(parts) >= 2:
            base_domains.add(".".join(parts[-2:]))

    if not base_domains:
        return None

    escaped = [re.escape(d) for d in base_domains]
    domains_re = r"(?:" + "|".join(escaped) + r")(?![A-Za-z0-9-])"

    pattern = (
        r"(?<![A-Za-z0-9_-])"
        r"(?:https?://)?"
        r"(?:[A-Za-z0-9_\-]+\.)*"
        rf"{domains_re}"
        r"(?::\d+)?"
        r"(?:/[A-Za-z0-9а-яА-ЯёЁ\-/._?=&%#@:]*)?(?<![.,;:])"
    )
    return re.compile(pattern, re.IGNORECASE)


def url_to_placeholder(url: str) -> tuple[str, str]:
    """Convert URL to deterministic placeholder. Returns (placeholder, hash)."""
    url_clean = re.sub(r"^https?://", "", url)
    prefix = url_clean.split("/")[0].split(".")[0]
    prefix = re.sub(r"[^a-zA-Z0-9]", "", prefix).lower() or "link"
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"[InternalLink_{prefix}_{url_hash}]", url_hash


def load_mappings() -> dict[str, str]:
    """Load global URL mappings."""
    if MAPPINGS_FILE.exists():
        try:
            return json.loads(MAPPINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_mappings(mappings: dict[str, str]) -> None:
    """Save global URL mappings."""
    MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAPPINGS_FILE.write_text(json.dumps(mappings, indent=2))


def load_session(session_id: str) -> list[str]:
    """Load list of transformed files for session."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        try:
            return json.loads(session_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_session(session_id: str, files: list[str]) -> None:
    """Save list of transformed files for session."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(files))


def delete_session(session_id: str) -> None:
    """Delete session file."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        session_file.unlink()


def transform_text(text: str, pattern: re.Pattern) -> tuple[str, dict[str, str]]:
    """Replace URLs with placeholders. Returns (transformed, new_mappings)."""
    new_mappings = {}
    matches = list(pattern.finditer(text))

    for match in reversed(matches):
        url = match.group()
        placeholder, url_hash = url_to_placeholder(url)
        new_mappings[url_hash] = url
        text = text[: match.start()] + placeholder + text[match.end() :]

    return text, new_mappings


def restore_text(text: str, mappings: dict[str, str]) -> str:
    """Replace placeholders with original URLs."""
    for match in reversed(list(PLACEHOLDER_RE.finditer(text))):
        url_hash = match.group(2)
        if url_hash in mappings:
            text = text[: match.start()] + mappings[url_hash] + text[match.end() :]
    return text


def output(response: dict) -> None:
    """Output JSON response to stdout."""
    print(json.dumps(response))


def handle_pre_tool_use(data: dict) -> None:
    """Handle PreToolUse hook."""
    session_id = data.get("session_id")
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if not session_id:
        return

    domains = load_domains()
    pattern = build_url_pattern(domains)
    if not pattern:
        return

    if tool == "Read":
        file_path = tool_input.get("file_path")
        if not file_path:
            return

        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return

        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            return

        transformed, new_mappings = transform_text(content, pattern)
        if not new_mappings:
            return

        # Update global mappings
        mappings = load_mappings()
        mappings.update(new_mappings)
        save_mappings(mappings)

        # Track file in session
        session_files = load_session(session_id)
        if file_path not in session_files:
            session_files.append(file_path)
            save_session(session_id, session_files)

        # Transform file in-place
        path.write_text(transformed)

        output(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": f"[link-proxy] Masked {len(new_mappings)} internal URLs",
                }
            }
        )

    elif tool == "Edit":
        new_string = tool_input.get("new_string", "")
        if not new_string:
            return

        mappings = load_mappings()
        if not mappings:
            return

        restored = restore_text(new_string, mappings)
        if restored != new_string:
            output(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "updatedInput": {
                            "file_path": tool_input.get("file_path", ""),
                            "old_string": tool_input.get("old_string", ""),
                            "new_string": restored,
                        },
                    }
                }
            )

    elif tool == "Write":
        content = tool_input.get("content", "")
        file_path = tool_input.get("file_path", "")
        if not content:
            return

        mappings = load_mappings()
        if not mappings:
            return

        restored = restore_text(content, mappings)
        if restored != content:
            # Remove from session tracking since we're writing restored content
            session_files = load_session(session_id)
            if file_path in session_files:
                session_files.remove(file_path)
                save_session(session_id, session_files)

            output(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "updatedInput": {
                            "file_path": file_path,
                            "content": restored,
                        },
                    }
                }
            )


def handle_post_tool_use(data: dict) -> None:
    """Handle PostToolUse hook - re-transform file after edit."""
    session_id = data.get("session_id")
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if not session_id or tool != "Edit":
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    path = Path(file_path)
    if not path.exists():
        return

    domains = load_domains()
    pattern = build_url_pattern(domains)
    if not pattern:
        return

    try:
        content = path.read_text()
    except (OSError, UnicodeDecodeError):
        return

    transformed, new_mappings = transform_text(content, pattern)
    if not new_mappings:
        return

    # Update global mappings
    mappings = load_mappings()
    mappings.update(new_mappings)
    save_mappings(mappings)

    # Track file in session
    session_files = load_session(session_id)
    if file_path not in session_files:
        session_files.append(file_path)
        save_session(session_id, session_files)

    path.write_text(transformed)


def handle_stop(data: dict) -> None:
    """Handle Stop hook - restore all files transformed in this session."""
    session_id = data.get("session_id")
    if not session_id:
        return

    session_files = load_session(session_id)
    if not session_files:
        delete_session(session_id)
        return

    mappings = load_mappings()
    if not mappings:
        delete_session(session_id)
        return

    for file_path in session_files:
        path = Path(file_path)
        if not path.exists():
            continue
        try:
            content = path.read_text()
            restored = restore_text(content, mappings)
            if restored != content:
                path.write_text(restored)
        except (OSError, UnicodeDecodeError):
            continue

    delete_session(session_id)


def main() -> None:
    """Entry point."""
    if len(sys.argv) < 2:
        print("Usage: main.py <hook-type>", file=sys.stderr)
        sys.exit(1)

    hook_type = sys.argv[1]

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    try:
        if hook_type == "pre-tool-use":
            handle_pre_tool_use(data)
        elif hook_type == "post-tool-use":
            handle_post_tool_use(data)
        elif hook_type == "stop":
            handle_stop(data)
        else:
            print(f"Unknown hook type: {hook_type}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[link-proxy] Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
