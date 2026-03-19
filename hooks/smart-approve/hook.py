#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Auto-approve safe, read-only Bash commands to reduce permission prompts.

Parses compound commands (&&, ||, ;, |), extracts the binary from each
segment, and checks against a safelist. If ALL segments use safe binaries
and no dangerous flags are detected, returns 'allow' to skip the
interactive permission prompt. Otherwise stays silent (normal prompt).

Edit SAFE_BINARIES to customize what gets auto-approved.
"""

import json
import re
import sys
from pathlib import Path

# ── Safelist ─────────────────────────────────────────────────────────
# Binaries that are read-only by nature. If it can write, delete, or
# modify state, it does NOT belong here.

SAFE_BINARIES = {
    # File discovery & listing
    "find", "ls", "tree", "exa", "eza", "fd",
    # File info & checksums
    "stat", "file", "wc", "du", "df",
    "md5", "md5sum", "shasum", "sha256sum", "sha1sum",
    # File reading
    "cat", "head", "tail", "less", "more", "bat",
    # Search
    "grep", "egrep", "fgrep", "rg", "ag", "ack",
    # Text processing (pipeline-safe)
    "sort", "uniq", "cut", "tr", "rev", "tac", "nl",
    "column", "paste", "fold", "expand", "unexpand",
    "awk", "gawk", "mawk", "nawk",
    "sed",  # checked for -i separately
    # Comparison
    "diff", "comm", "cmp",
    # JSON / structured data
    "jq", "yq", "xq", "xmllint",
    # Path utilities
    "dirname", "basename", "realpath", "readlink", "pwd",
    # System info
    "date", "uname", "whoami", "hostname", "id", "uptime",
    "sw_vers", "arch", "nproc", "getconf", "sysctl",
    # Tool lookup
    "which", "where", "type", "command", "hash",
    "man", "apropos", "whatis",
    # Output / control
    "echo", "printf", "true", "false", "test", "[",
    # Environment
    "env", "printenv",
    # Misc safe
    "seq", "expr", "bc", "dc", "xxd", "od",
    "hexdump", "strings",
}

# ── Dangerous flags per binary ───────────────────────────────────────

FIND_DANGEROUS = {"-exec", "-execdir", "-delete", "-ok", "-okdir"}
SED_DANGEROUS = {"-i", "--in-place"}


# ── Helpers ──────────────────────────────────────────────────────────

def allow(reason: str = "") -> None:
    result: dict = {
        "hookSpecificOutput": {
            "permissionDecision": "allow",
        }
    }
    if reason:
        result["systemMessage"] = reason
    print(json.dumps(result))
    sys.exit(0)


def split_commands(command: str) -> list[str]:
    """Split compound command on &&, ||, ;, | into individual segments."""
    parts = re.split(r"\s*(?:&&|\|\||[;|])\s*", command)
    return [p.strip() for p in parts if p.strip()]


def extract_binary(cmd: str) -> str | None:
    """Extract the binary name, skipping env-var assignments and prefixes."""
    tokens = cmd.split()
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        # Skip env-var assignments (FOO=bar)
        if "=" in token and not token.startswith("-") and not token.startswith("/"):
            idx += 1
            continue
        # Skip 'cd dir' prefix
        if token == "cd" and idx + 1 < len(tokens):
            idx += 2
            continue
        # Skip 'env' prefix
        if token == "env":
            idx += 1
            continue
        # Resolve /usr/bin/find → find
        return Path(token).name
    return None


def has_output_redirect(command: str) -> bool:
    """Check for shell output redirection (>, >>)."""
    # Match > or >> not preceded by - or = (to avoid --flag=>value)
    return bool(re.search(r"(?<![=\-])\s[12]?>{1,2}\s", command))


def is_segment_safe(cmd: str) -> bool:
    """Check if a single command segment is safe to auto-approve."""
    binary = extract_binary(cmd)
    if not binary:
        return False

    if binary not in SAFE_BINARIES:
        return False

    tokens = cmd.split()

    # find: block -exec, -execdir, -delete
    if binary == "find":
        if any(t in FIND_DANGEROUS for t in tokens):
            return False

    # sed: block -i (in-place editing)
    if binary == "sed":
        if any(t in SED_DANGEROUS or t.startswith("-i") for t in tokens):
            return False

    return True


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    # Bail on anything too complex to analyze safely
    if "$(" in command or "`" in command:
        sys.exit(0)
    if has_output_redirect(command):
        sys.exit(0)

    parts = split_commands(command)
    if not parts:
        sys.exit(0)

    if all(is_segment_safe(part) for part in parts):
        allow()

    # No output → normal permission flow
    sys.exit(0)
