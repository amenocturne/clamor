#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Import Confluence pages to Markdown.

Reads host and username from .claude/agentic-kit.json (searched from CWD upward).

Config structure:
    {
      "confluence": {
        "host": "https://confluence.example.com",
        "username": "yourname"
      }
    }

Usage:
    confluence.py --page-id <id> [--folder-path <path>] [--recursive]
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_config() -> dict:
    for parent in [Path.cwd(), *Path.cwd().parents]:
        config_path = parent / ".claude" / "agentic-kit.json"
        if config_path.exists():
            return json.loads(config_path.read_text())
    return {}


def find_page_file(folder: Path, page_id: str) -> Path | None:
    """Return the page file path once it exists on disk, else None."""
    # When page has children the tool creates {page_id}/index.md
    index = folder / page_id / "index.md"
    if index.exists():
        return index
    # When page has no children the tool creates {page_id}.md
    flat = folder / f"{page_id}.md"
    if flat.exists():
        return flat
    return None


def wait_and_kill(
    proc: subprocess.Popen, folder: Path, page_id: str, grace: float = 1.5
):
    """Kill process once the target page file appears on disk."""
    while proc.poll() is None:
        if find_page_file(folder, page_id) is not None:
            time.sleep(grace)  # brief wait for the page's own attachments
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
            return
        time.sleep(0.1)


def cleanup_children(folder: Path, page_id: str):
    """Remove child pages, keeping only the target page and its attachments."""
    page_dir = folder / page_id
    if not page_dir.exists():
        return
    for item in list(page_dir.iterdir()):
        if item.name in ("index.md", f"attachments_{page_id}"):
            continue
        (shutil.rmtree if item.is_dir() else item.unlink)(item)


def main():
    parser = argparse.ArgumentParser(description="Import Confluence pages to Markdown")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument(
        "--folder-path", default="./docs", help="Output directory (default: ./docs)"
    )
    parser.add_argument(
        "--recursive", action="store_true", help="Download child pages recursively"
    )
    parser.add_argument("--host", help="Override Confluence host from config")
    parser.add_argument("--username", help="Override username from config")
    args = parser.parse_args()

    config = find_config()
    confluence_cfg = config.get("confluence", {})

    host = args.host or confluence_cfg.get("host")
    username = args.username or confluence_cfg.get("username")

    if not host:
        print(
            "Error: no host configured. Set confluence.host in .claude/agentic-kit.json or pass --host.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not username:
        print(
            "Error: no username configured. Set confluence.username in .claude/agentic-kit.json or pass --username.",
            file=sys.stderr,
        )
        sys.exit(1)

    host = host.rstrip("/")
    page_url = f"{host}/pages/viewpage.action?pageId={args.page_id}"
    folder = Path(args.folder_path)

    cmd = [
        "npx",
        "@acq-tech/confluence",
        "--username",
        username,
        "--folder-path",
        str(folder),
        page_url,
    ]
    if args.recursive:
        cmd.append("--recursive")

    # Note: --recursive is unimplemented in the tool; it always downloads the
    # full tree. For single-page mode we watch for the target file, kill the
    # process as soon as it's written, then strip any children that snuck in.
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    proc.stdin.write(b"n\n")  # answer the "Download child pages?" prompt
    proc.stdin.flush()
    proc.stdin.close()

    if not args.recursive:
        wait_and_kill(proc, folder, args.page_id)
        cleanup_children(folder, args.page_id)
    else:
        proc.wait()

    sys.exit(proc.returncode if proc.returncode is not None else 0)


if __name__ == "__main__":
    main()
