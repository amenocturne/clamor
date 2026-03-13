#!/usr/bin/env bash
set -euo pipefail
# Usage: create.sh [project-dir] [agent-id]
# Creates a worktree at <project>/.worktrees/agent-<id>/
# Prints the worktree path on success

project_dir="${1:?Usage: create.sh <project-dir> [agent-id]}"
agent_id="${2:-$(uuidgen | tr '[:upper:]' '[:lower:]' | cut -c1-8)}"

project_dir="$(cd "$project_dir" && pwd)"

if ! git -C "$project_dir" rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Error: $project_dir is not inside a git repository" >&2
    exit 1
fi

worktree_dir="$project_dir/.worktrees/agent-$agent_id"
branch_name="worktree-$agent_id"

if [ -d "$worktree_dir" ]; then
    echo "Error: worktree already exists at $worktree_dir" >&2
    exit 1
fi

mkdir -p "$project_dir/.worktrees"

gitignore="$project_dir/.gitignore"
if [ -f "$gitignore" ]; then
    if ! grep -qxF '.worktrees/' "$gitignore"; then
        echo '.worktrees/' >> "$gitignore"
    fi
else
    echo '.worktrees/' > "$gitignore"
fi

git -C "$project_dir" worktree add "$worktree_dir" -b "$branch_name"

echo "$worktree_dir"
