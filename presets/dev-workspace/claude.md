# Dev Workspace

Multi-project development workspace. Run Claude from this directory and specify which project to work on.

## Knowledge Base Integration

If `knowledge_base` is configured, project ideas and plans live there. When working on a project:
- Check if there's a matching project note with context, goals, or decisions
- Update project notes when significant decisions are made

---

{{include:common/skills.md}}

## Resuming Projects

When the user says "continue working on X", "pick up X", or similar:
1. Read WORKSPACE.yaml to find the project
2. **Invoke the `todo` skill** — it handles checking `.claude/tasks/` and resuming tracked progress
3. Load remaining project context (project CLAUDE.md, knowledge base notes) in parallel with step 2

{{include:common/workspace.md}}

{{include:common/agentic-kit.md}}

{{include:common/commands.md}}

{{include:common/cli-tools.md}}

{{include:common/tmp.md}}

{{include:common/code-style.md}}

{{include:common/comments.md}}

{{include:common/quality.md}}

{{include:common/git.md}}

{{include:common/documentation.md}}

{{include:common/communication-style.md}}

{{include:common/bug-reports.md}}
