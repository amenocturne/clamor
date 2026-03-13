#!/usr/bin/env bash
set -euo pipefail
# Usage: status.sh [project-dir]
# Shows active worktrees and checks clamor state for active agents

project_dir="${1:-.}"
project_dir="$(cd "$project_dir" && pwd)"

if ! git -C "$project_dir" rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Error: $project_dir is not inside a git repository" >&2
    exit 1
fi

echo "=== Git Worktrees ==="
git -C "$project_dir" worktree list
echo ""

clamor_state="$HOME/.clamor/state.json"
if [ ! -f "$clamor_state" ]; then
    echo "=== Clamor ==="
    echo "No clamor state found ($clamor_state)"
    exit 0
fi

# Collect worktree paths
worktree_paths=()
while IFS= read -r line; do
    worktree_paths+=("$line")
done < <(git -C "$project_dir" worktree list --porcelain | grep '^worktree ' | sed 's/^worktree //')

echo "=== Clamor Agent Status ==="

# Parse clamor state and cross-reference with worktree paths
has_matches=false
while IFS= read -r agent_cwd; do
    for wt in "${worktree_paths[@]}"; do
        if [[ "$agent_cwd" == "$wt"* ]]; then
            agent_id="$(basename "$wt")"
            echo "  ACTIVE: $agent_id -> $wt"
            has_matches=true
        fi
    done
done < <(python3 -c "
import json, sys
try:
    with open('$clamor_state') as f:
        state = json.load(f)
    agents = state.get('agents', {})
    for agent_id, agent in agents.items():
        cwd = agent.get('cwd', '')
        if cwd:
            print(cwd)
except Exception:
    pass
" 2>/dev/null)

if [ "$has_matches" = false ]; then
    # Check for orphaned worktrees (no active clamor agent)
    orphaned=false
    for wt in "${worktree_paths[@]}"; do
        if [[ "$wt" == */.worktrees/* ]]; then
            agent_id="$(basename "$wt")"
            echo "  ORPHAN: $agent_id -> $wt"
            orphaned=true
        fi
    done
    if [ "$orphaned" = false ]; then
        echo "  No worktrees with clamor agents"
    fi
fi
