# Work Workspace

Work development workspace focused on Scala and infrastructure. Run Claude from this directory and specify which project to work on.

## Skills

**Proactively use skills whenever relevant.** Skills enhance understanding and provide domain-specific patterns. Before starting a task, check if any available skill matches the context — invoke it immediately as your first action. Don't just work on a task when a skill could provide better guidance.

## Project Index

**WORKSPACE.yaml** contains all projects with their paths, tech stacks, and commands. Check it when:
- User mentions a project name → find path and tech stack
- Need to run commands → use project-specific commands from the index
- Starting work → load the project's context

## Configuration

Check `.claude/agentic-kit.json` for workspace-specific paths:
```json
{
  "knowledge_base": "/path/to/obsidian/vault",
  "agentic_kit": "/path/to/agentic-kit"
}
```

If not configured, ask the user or skip knowledge base integration.

## Working on a Project

When user says "work on X" or mentions a project:

1. **Find project** in WORKSPACE.yaml by name or path
2. **Load project CLAUDE.md** if it exists (`<project>/CLAUDE.md`)
3. **Check knowledge base** for project notes (if configured) at `{knowledge_base}/projects/`

Run all commands from the project directory, not workspace root.

Language-specific skills (scala, config) will trigger automatically based on the work being done.

## Knowledge Base Integration

If `knowledge_base` is configured in `.claude/agentic-kit.json`, project ideas and plans live there. When working on a project:
- Check if there's a matching project note with context, goals, or decisions
- Update project notes when significant decisions are made
- Use the knowledge base for design inspiration references

## Universal Rules

### Commands
- Always use `just` for command aliases when available
- Run `just` (no args) to see available commands
- Never run raw `python` — use `uv run` instead

Standard command names across projects:
- `just run` — run the project (optionally: `just run prod`)
- `just setup` — initial setup / install dependencies
- `just test` — run tests
- `just lint` / `just fmt` — code quality
- `just build` — compile/bundle
- `just clean` / `just reset` — cleanup

### Code Style
- **Functional programming**: Pure functions, no classes, no `this`
- **Immutability**: Use `const`, spread operators, `readonly` in types
- **Side effects at boundaries**: IO operations only at entry points (CLI, server handlers)
- **No over-engineering**: Solve the current problem, not hypothetical future ones

### Comments
Only meaningful comments that add value:
- **Good**: Why something is done a certain way, complex flow explanations, non-obvious tradeoffs
- **Bad**: What the code does (code is self-documenting), change history (that's git), TODO/FIXME

```scala
// Bad: "increment counter by 1"
// Bad: "fixed bug #123"
// Good: "Using median instead of mean to handle outliers in sensor data"
// Good: "Retry logic needed because API returns 503 during deployments"
```

### Quality
- Run tests and linter after changes: `just test && just lint` or equivalent
- Never consider a task complete until both pass
- Fix issues immediately, don't leave broken code

### Git
- Concise commit messages (1-2 sentences)
- Focus on "why" not "what"
- No emoji prefixes, no Co-Authored-By lines

### Documentation
- **CLAUDE.md**: Commands, architecture, key patterns (AI context)
- **README.md**: Setup + overview (human context)
- Update docs before committing features
- Keep high-level — code is the source of truth for details
