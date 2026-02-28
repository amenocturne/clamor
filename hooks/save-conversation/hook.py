#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Stop hook that saves conversation transcripts.
Copies raw JSONL transcript to logs/ and commits to git.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Message types to keep in saved transcripts
# Excludes: progress (subagent streaming - causes GB bloat), file-history-snapshot, queue-operation
KEEP_TYPES = {"user", "assistant", "system"}


def filter_entries(entries: list[dict]) -> list[dict]:
    """Filter out internal/progress messages to reduce file size."""
    return [e for e in entries if e.get("type") in KEEP_TYPES]


def extract_modified_files(entries: list[dict], project_dir: Path) -> list[Path]:
    """Extract file paths from Write/Edit tool uses in transcript."""
    modified = set()
    for entry in entries:
        message = entry.get("message", {})
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Write", "Edit"):
                continue
            file_path = block.get("input", {}).get("file_path")
            if not file_path:
                continue
            path = Path(file_path)
            try:
                rel_path = path.relative_to(project_dir)
                # Skip .claude/ files - they're symlinked and belong to agentic-kit
                if rel_path.parts and rel_path.parts[0] == ".claude":
                    continue
                if path.exists():
                    modified.add(path)
            except ValueError:
                pass
    return list(modified)


def format_markdown(project_dir: Path):
    """Format markdown files with Prettier."""
    try:
        subprocess.run(
            ["npx", "--yes", "prettier", "--write", "**/*.md"],
            cwd=project_dir,
            capture_output=True,
            timeout=60,
        )
        return True
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return False


def git_commit(project_dir: Path, message: str, files: list[Path]):
    """Stage specific files and commit."""
    if not files:
        return False
    try:
        subprocess.run(
            ["git", "add"] + [str(f) for f in files],
            cwd=project_dir,
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=project_dir, capture_output=True
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=project_dir,
                capture_output=True,
                check=True,
            )
            return True
    except subprocess.CalledProcessError:
        pass
    return False


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if input_data.get("stop_hook_active", False):
        sys.exit(0)

    if os.environ.get("NO_LOG"):
        sys.exit(0)

    transcript_path = input_data.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))

    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H%M%S")

    logs_dir = project_dir / "logs" / date_folder
    logs_dir.mkdir(parents=True, exist_ok=True)

    with open(transcript_path, "r") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    # Use session ID from transcript filename (e.g., "abc-123.jsonl" -> "abc-123")
    # This ensures re-saves overwrite instead of creating duplicates
    session_id = Path(transcript_path).stem
    output_path = logs_dir / f"{session_id}.json"
    files_to_commit = [output_path]

    # Filter before saving (removes progress messages that cause GB bloat)
    filtered = filter_entries(entries)
    with open(output_path, "w") as f:
        json.dump(filtered, f, indent=2)

    # Use filtered entries for file extraction (has all tool_use blocks we need)
    modified_files = extract_modified_files(filtered, project_dir)
    files_to_commit.extend(modified_files)

    # Rename pending summaries (_*.md -> timestamp *.md)
    for pending in logs_dir.glob("_*.md"):
        content = pending.read_text()
        content = content.replace("{LOG_ID}", session_id)
        pending.write_text(content)

        topic = pending.name[1:]
        new_path = logs_dir / f"{timestamp} {topic}"
        pending.rename(new_path)
        files_to_commit.append(new_path)

    print(f"Conversation saved to: {output_path}")
    if modified_files:
        print(f"Found {len(modified_files)} modified file(s)")

    format_markdown(project_dir)

    commit_msg = f"Log: {date_folder} {timestamp}"
    if git_commit(project_dir, commit_msg, files_to_commit):
        print(f"Committed: {commit_msg}")

    sys.exit(0)


if __name__ == "__main__":
    main()
