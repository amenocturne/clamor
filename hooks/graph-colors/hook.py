#!/usr/bin/env python3
"""
Graph colors hook - updates Obsidian graph color groups on conversation stop.

This hook runs the obsidian-graph-colors.py script to regenerate
cluster-based color groups in .obsidian/graph.json
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def find_vault_root(start: Path) -> Path | None:
    """Find vault root by looking for .obsidian folder."""
    current = start.resolve()
    while current != current.parent:
        if (current / '.obsidian').exists():
            return current
        current = current.parent
    return None


def find_script() -> Path | None:
    """Find the obsidian-graph-colors.py script."""
    # Look relative to this hook
    hook_dir = Path(__file__).parent

    # Try agentic-kit structure: hooks/graph-colors/hook.py -> skills/graph/scripts/
    agentic_kit_root = hook_dir.parent.parent
    script = agentic_kit_root / 'skills' / 'graph' / 'scripts' / 'obsidian-graph-colors.py'
    if script.exists():
        return script

    # Try vault structure: .claude/hooks/graph-colors/hook.py -> .claude/skills/graph/scripts/
    vault_root = find_vault_root(hook_dir)
    if vault_root:
        script = vault_root / '.claude' / 'skills' / 'graph' / 'scripts' / 'obsidian-graph-colors.py'
        if script.exists():
            return script

    return None


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_input = {}

    # Get the working directory from hook input or use CWD
    cwd = hook_input.get('cwd', os.getcwd())
    cwd = Path(cwd)

    # Find vault root
    vault_root = find_vault_root(cwd)
    if not vault_root:
        # Not in a vault, skip silently
        print(json.dumps({"continue": True}))
        return

    # Find the script
    script = find_script()
    if not script:
        print(json.dumps({
            "continue": True,
            "message": "obsidian-graph-colors.py script not found"
        }))
        return

    # Run the script
    try:
        result = subprocess.run(
            ['uv', 'run', str(script), '--exclude=logs,tmp,archive'],
            cwd=vault_root,
            capture_output=True,
            text=True,
            timeout=25
        )

        if result.returncode == 0:
            print(json.dumps({
                "continue": True,
                "message": f"Graph colors updated"
            }))
        else:
            print(json.dumps({
                "continue": True,
                "message": f"Graph colors update failed: {result.stderr[:100]}"
            }))

    except subprocess.TimeoutExpired:
        print(json.dumps({
            "continue": True,
            "message": "Graph colors update timed out"
        }))
    except Exception as e:
        print(json.dumps({
            "continue": True,
            "message": f"Graph colors error: {str(e)[:100]}"
        }))


if __name__ == '__main__':
    main()
