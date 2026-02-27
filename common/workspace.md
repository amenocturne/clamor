## Project Index

**WORKSPACE.yaml** contains all projects with their paths, tech stacks, and commands.

When user mentions a project:
1. Find it in WORKSPACE.yaml by name or path
2. Load `<project>/CLAUDE.md` if exists
3. Check `{knowledge_base}/projects/` for project notes (if configured)

Run commands from project directory, not workspace root.
