#!/usr/bin/env bash
set -euo pipefail
# Auto-cleanup worktree on agent stop.
# Checks if the session's working directory is inside a .worktrees/ directory.
# If so, removes the worktree and prunes.

# Hook receives JSON on stdin with session info
cwd=""
if read -t 1 -r input_json; then
    cwd="$(echo "$input_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || true)"
fi

# Fall back to PWD if stdin didn't provide cwd
if [ -z "$cwd" ]; then
    cwd="${PWD:-}"
fi

# Only act if we're inside a .worktrees/ directory
if [[ "$cwd" != */.worktrees/* ]]; then
    exit 0
fi

# Extract the worktree path (everything up to and including agent-<id>)
worktree_path="$(echo "$cwd" | sed 's|\(/.worktrees/agent-[^/]*\).*|\1|')"

if [ -z "$worktree_path" ] || [ ! -d "$worktree_path" ]; then
    exit 0
fi

# Navigate to the main repo (parent of .worktrees/)
git_root="$(echo "$worktree_path" | sed 's|/.worktrees/.*||')"

if [ -z "$git_root" ] || [ ! -d "$git_root/.git" ]; then
    exit 0
fi

# Derive branch name
dir_name="$(basename "$worktree_path")"
branch_name=""
if [[ "$dir_name" == agent-* ]]; then
    agent_id="${dir_name#agent-}"
    branch_name="worktree-$agent_id"
fi

# Remove the worktree (without --force: will fail if there are uncommitted changes)
if ! git -C "$git_root" worktree remove "$worktree_path" 2>/dev/null; then
    # Dirty worktree — don't destroy uncommitted work
    exit 0
fi

git -C "$git_root" worktree prune 2>/dev/null || true

# Preserve the branch for merge — don't delete it
# User or orchestrating agent handles merge + branch cleanup
