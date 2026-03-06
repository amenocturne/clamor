#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Remind the agent about uncommitted changes to enforce The Loop workflow."""

import json
import os
import subprocess
import sys


def git_diff_stat(project_dir: str, cached: bool = False) -> str:
    cmd = ["git", "diff", "--stat"]
    if cached:
        cmd.append("--cached")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_dir, timeout=5
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def is_git_repo(project_dir: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def count_files(diff_output: str) -> int:
    if not diff_output:
        return 0
    # Each changed file is a line; the last line is the summary
    lines = diff_output.strip().splitlines()
    # The summary line (e.g. "3 files changed, ...") is always last
    if lines and ("file" in lines[-1] and "changed" in lines[-1]):
        return len(lines) - 1
    return len(lines)


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        data = {}

    project_dir = data.get("stop_hook_active_project_directory") or os.getcwd()

    if not is_git_repo(project_dir):
        sys.exit(0)

    unstaged = git_diff_stat(project_dir, cached=False)
    staged = git_diff_stat(project_dir, cached=True)

    unstaged_count = count_files(unstaged)
    staged_count = count_files(staged)
    total = unstaged_count + staged_count

    if total > 0:
        print(
            f"\u26a0\ufe0f WORKFLOW CHECK: You have uncommitted changes ({total} files modified). "
            "Before responding to the user, follow The Loop: "
            "verify (just test && just lint) \u2192 commit \u2192 review.\n"
            "Do NOT report completion without committing first."
        )
