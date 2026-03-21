#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Enforce per-project denyRead rules from the nearest .claude/settings.json.

Walks up from the target file to find the project's settings, loads deny
patterns from sandbox.filesystem.denyRead, and blocks access if matched.
This lets deny rules live with the project and work regardless of CWD.
"""

import json
import glob as globmod
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

SETTINGS_CACHE: dict[str, dict | None] = {}

# Max directory depth to search for .claude/settings.json (avoids rglob into
# node_modules, .git, venvs, etc.)
_MAX_PROJECT_DEPTH = 3


def find_project_settings(file_path: str) -> tuple[Path | None, dict | None]:
    """Walk up from file_path to find nearest .claude/settings.json."""
    path = Path(file_path).resolve()
    search_dir = path if path.is_dir() else path.parent

    while search_dir != search_dir.parent:
        cache_key = str(search_dir)
        if cache_key in SETTINGS_CACHE:
            cached = SETTINGS_CACHE[cache_key]
            if cached is not None:
                return search_dir, cached
            search_dir = search_dir.parent
            continue

        settings_file = search_dir / ".claude" / "settings.json"
        if settings_file.is_file():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                SETTINGS_CACHE[cache_key] = settings
                return search_dir, settings
            except (json.JSONDecodeError, OSError):
                pass

        SETTINGS_CACHE[cache_key] = None
        search_dir = search_dir.parent

    return None, None


def get_deny_patterns(settings: dict) -> list[str]:
    """Extract denyRead patterns from settings."""
    return (
        settings.get("sandbox", {}).get("filesystem", {}).get("denyRead", [])
    )


def resolve_pattern(pattern: str, project_root: Path) -> str:
    """Resolve a deny pattern to an absolute path/glob."""
    if pattern.startswith("//"):
        return pattern[1:]
    if pattern.startswith("~/"):
        return str(Path.home() / pattern[2:])
    if pattern.startswith("/"):
        return str(project_root / pattern.lstrip("/"))
    return str(project_root / pattern)


def matches_deny(file_path: str, project_root: Path, patterns: list[str]) -> str | None:
    """Check if file_path matches any deny pattern. Returns matched pattern or None."""
    resolved = str(Path(file_path).resolve())

    for pattern in patterns:
        abs_pattern = resolve_pattern(pattern, project_root)
        if fnmatch(resolved, abs_pattern):
            return pattern

    return None


def get_denied_filenames(project_root: Path, patterns: list[str]) -> set[str]:
    """Expand deny patterns into actual filenames that exist on disk."""
    names: set[str] = set()
    for pattern in patterns:
        abs_pattern = resolve_pattern(pattern, project_root)
        if "*" in abs_pattern:
            for match in globmod.glob(abs_pattern, recursive=True):
                names.add(Path(match).name)
        else:
            names.add(Path(abs_pattern).name)
    return names


def grep_glob_excludes_denied(grep_glob: str, denied_names: set[str]) -> bool:
    """Check if a Grep glob filter naturally excludes all denied filenames."""
    for name in denied_names:
        if fnmatch(name, grep_glob):
            return False
    return True


def find_denied_files_in_dir(search_dir: str, project_root: Path, patterns: list[str]) -> list[str]:
    """Return list of deny patterns that have matching files under search_dir."""
    resolved_dir = Path(search_dir).resolve()
    matched = []

    for pattern in patterns:
        abs_pattern = resolve_pattern(pattern, project_root)

        if "*" in abs_pattern:
            for match in globmod.glob(abs_pattern, recursive=True):
                if Path(match).resolve().is_relative_to(resolved_dir):
                    matched.append(pattern)
                    break
        else:
            if Path(abs_pattern).resolve().is_relative_to(resolved_dir):
                matched.append(pattern)

    return matched


def check_bash_command(command: str, project_root: Path, patterns: list[str]) -> str | None:
    """Check if a Bash command references denied files."""
    for pattern in patterns:
        abs_path = resolve_pattern(pattern, project_root)

        # For glob patterns like "secrets/**", also check the directory prefix
        # e.g., "secrets/**" should match any command containing "secrets/"
        if "**" in pattern:
            dir_prefix = pattern.split("**")[0]  # e.g., "secrets/"
            abs_dir_prefix = resolve_pattern(dir_prefix, project_root)
            # Check both relative and absolute forms of the directory prefix
            cwd_rel = None
            try:
                cwd_rel = str(Path(abs_dir_prefix).relative_to(Path.cwd()))
            except ValueError:
                pass
            for check in [abs_dir_prefix, dir_prefix, cwd_rel]:
                if check and check in command:
                    return pattern

        # Check literal matches (relative, absolute, CWD-relative)
        rel_path = pattern.lstrip("/")
        cwd_rel = None
        try:
            cwd_rel = str(Path(abs_path).relative_to(Path.cwd()))
        except ValueError:
            pass

        for check in [abs_path, rel_path, cwd_rel]:
            if check and check in command:
                return pattern

    return None


def is_git_only_command(command: str) -> bool:
    """Check if every sub-command in a shell chain is a git operation.

    Git porcelain/plumbing commands manage the index and working tree without
    printing file contents to stdout (which is what the deny-read hook cares
    about).  Direct file reads are still guarded by the Read/Edit/Write
    handlers, so allowing git here doesn't weaken protection.
    """
    parts = re.split(r"\s*(?:&&|\|\||;)\s*", command)
    for part in parts:
        tokens = part.strip().split()
        if not tokens:
            continue
        # Skip env-var assignments (FOO=bar) and cd
        idx = 0
        while idx < len(tokens):
            if tokens[idx] == "cd" and idx + 1 < len(tokens):
                idx += 2
            elif "=" in tokens[idx] and not tokens[idx].startswith("-"):
                idx += 1
            else:
                break
        if idx >= len(tokens):
            continue
        if tokens[idx] != "git":
            return False
    return True


def find_project_settings_bounded(root: Path) -> list[Path]:
    """Find .claude/settings.json files up to _MAX_PROJECT_DEPTH levels deep.

    Avoids Path.rglob which traverses every subdirectory (node_modules, .git,
    venvs) and can easily exceed the hook timeout on large workspaces.
    """
    results: list[Path] = []
    for depth in range(_MAX_PROJECT_DEPTH + 1):
        prefix = "/".join(["*"] * depth) if depth else ""
        pattern = f"{prefix}/.claude/settings.json" if prefix else ".claude/settings.json"
        results.extend(root.glob(pattern))
    return results


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            sys.exit(0)

        # Git commands manage the index/working tree — they don't print file
        # contents.  Direct reads are still guarded by Read/Edit/Write handlers.
        if is_git_only_command(command):
            sys.exit(0)

        # Bounded depth search instead of rglob (avoids node_modules, .git, etc.)
        cwd = Path.cwd()
        for settings_file in find_project_settings_bounded(cwd):
            project_root = settings_file.parent.parent
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            patterns = get_deny_patterns(settings)
            if not patterns:
                continue
            matched = check_bash_command(command, project_root, patterns)
            if matched:
                deny(f"deny-read: command accesses file matching '{matched}' (from {project_root.name})")

        sys.exit(0)

    # Grep: check if the search scope contains denied files
    if tool_name == "Grep":
        search_path = tool_input.get("path") or str(Path.cwd())
        search_path_resolved = str(Path(search_path).resolve())

        # If Grep targets a specific file, check it directly
        if Path(search_path_resolved).is_file():
            project_root, settings = find_project_settings(search_path)
            if project_root and settings:
                patterns = get_deny_patterns(settings)
                matched = matches_deny(search_path, project_root, patterns)
                if matched:
                    deny(f"deny-read: grep target '{Path(search_path).name}' matches deny pattern '{matched}' (from {project_root.name})")
            sys.exit(0)

        # Grep targets a directory: check if it contains denied files
        project_root, settings = find_project_settings(search_path)
        if project_root and settings:
            patterns = get_deny_patterns(settings)
            if patterns:
                denied_in_dir = find_denied_files_in_dir(search_path_resolved, project_root, patterns)
                if denied_in_dir:
                    # Check if the grep's own glob/type filter naturally excludes denied files
                    grep_glob = tool_input.get("glob")
                    grep_type = tool_input.get("type")

                    if grep_glob:
                        denied_names = get_denied_filenames(project_root, denied_in_dir)
                        if grep_glob_excludes_denied(grep_glob, denied_names):
                            # The glob filter already excludes denied files
                            sys.exit(0)

                    if grep_type:
                        # Typed searches (e.g., type="py") target specific language
                        # files — safe to allow since denied files are typically
                        # .env, secrets.yml, credentials, etc.
                        sys.exit(0)

                    denied_str = ", ".join(denied_in_dir)
                    deny(
                        f"deny-read: grep on '{Path(search_path).name or 'project'}' would expose "
                        f"files matching [{denied_str}]. Use glob or type filter to exclude "
                        f"denied files, or target a specific non-denied file path."
                    )
        sys.exit(0)

    # File-based tools: Read, Edit, Write
    file_path = tool_input.get("file_path")
    if not file_path:
        sys.exit(0)

    project_root, settings = find_project_settings(file_path)
    if not project_root or not settings:
        sys.exit(0)

    patterns = get_deny_patterns(settings)
    if not patterns:
        sys.exit(0)

    matched = matches_deny(file_path, project_root, patterns)
    if matched:
        deny(f"deny-read: '{Path(file_path).name}' matches deny pattern '{matched}' (from {project_root.name})")
