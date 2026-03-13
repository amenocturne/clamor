#!/usr/bin/env bash
set -euo pipefail
# Usage: cleanup.sh [worktree-path]
# Removes a specific worktree and its branch, or prunes all stale worktrees

worktree_path="${1:-}"

if [ -z "$worktree_path" ]; then
    git worktree prune
    echo "Pruned stale worktrees"
    exit 0
fi

worktree_path="$(realpath "$worktree_path" 2>/dev/null || echo "$worktree_path")"

# Derive the branch name from the worktree directory name
dir_name="$(basename "$worktree_path")"
branch_name=""
if [[ "$dir_name" == agent-* ]]; then
    agent_id="${dir_name#agent-}"
    branch_name="worktree-$agent_id"
fi

# Remove the worktree (--force handles dirty working trees)
if git worktree list --porcelain | grep -q "worktree $worktree_path"; then
    git worktree remove --force "$worktree_path" 2>/dev/null || true
else
    # Already removed from disk, just prune
    git worktree prune
fi

# Delete the branch if we know it
if [ -n "$branch_name" ]; then
    git branch -D "$branch_name" 2>/dev/null || true
fi

echo "Cleaned up: $worktree_path"
