## Project Index

**WORKSPACE.yaml** at workspace root is the source of truth for:
- Project locations, tech stacks, and commands
- Folder structure descriptions (if present)

**Always read WORKSPACE.yaml directly** with the Read tool when you need to:
- Find a project by name
- Understand folder purposes
- Get project commands

It's a small file — reading it is faster than spawning an explore agent or running find commands.

When user mentions a project:
1. Read WORKSPACE.yaml directly (not via agent)
2. Load `<project>/CLAUDE.md` if exists
3. Check `{knowledge_base}/projects/` for project notes (if configured)

Run commands from project directory, not workspace root.
