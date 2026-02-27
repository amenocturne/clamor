# Dev Workspace

Multi-project development workspace. Run Claude from this directory and specify which project to work on.

## Working on a Project

When user says "work on X" or mentions a project:

1. **Find project** in WORKSPACE.yaml by name or path
2. **Load project CLAUDE.md** if it exists (`<project>/CLAUDE.md`)
3. **Check knowledge base** for project notes (if configured) at `{knowledge_base}/projects/`

Run all commands from the project directory, not workspace root.

Domain-specific skills (config, frontend-design, playwright, pinchtab) trigger automatically based on context.

## Knowledge Base Integration

If `knowledge_base` is configured in `.claude/agentic-kit.json`, project ideas and plans live there. When working on a project:
- Check if there's a matching project note with context, goals, or decisions
- Update project notes when significant decisions are made
- Use the knowledge base for design inspiration references

---

{{include:common/skills.md}}

{{include:common/workspace.md}}

{{include:common/agentic-kit.md}}

{{include:common/commands.md}}

{{include:common/tmp.md}}

{{include:common/code-style.md}}

{{include:common/comments.md}}

{{include:common/quality.md}}

{{include:common/git.md}}

{{include:common/documentation.md}}
