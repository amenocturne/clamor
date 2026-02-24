# Work Workspace

Scala and infrastructure focused workspace.

## Skills

Proactively use skills whenever relevant. Before starting a task, check if any available skill matches the context — invoke it immediately as your first action.

## Project Index

**WORKSPACE.yaml** contains all projects with paths, tech stacks, and commands. Check it when:
- User mentions a project name → find path and tech stack
- Need to run commands → use project-specific commands
- Starting work → load project context

## Configuration

Read `.claude/agentic-kit.json` for workspace paths:
- `knowledge_base` — path to Obsidian vault
- `agentic_kit` — path to agentic-kit

If not configured, ask or skip knowledge base integration.

## Working on a Project

When user mentions a project:
1. Find it in WORKSPACE.yaml
2. Load `<project>/CLAUDE.md` if exists
3. Check `{knowledge_base}/projects/` for project notes

Run commands from project directory, not workspace root.

## Knowledge Base

When `knowledge_base` is configured:
- Check for project notes with context, goals, decisions
- Update notes when significant decisions are made

## Commands

- Use `just` for command aliases when available
- Run `just` (no args) to see available commands
- Never run raw `python` — use `uv run`

## Code Style

- Functional: pure functions, no classes
- Immutable: `const`, spread operators, `readonly`
- Side effects at boundaries only
- No over-engineering

## Comments

Only add comments explaining why, not what. No TODO/FIXME.

## Quality

Run `just test && just lint` after changes. Fix issues immediately.

## Git

Format: `ITAL-1234 | app | Message`
- `ITAL-1234` — task number
- `app` — component(s): app name, `docs`, multiple comma-separated
- Message — concise (Russian or English)

Examples:
```
ITAL-1234 | autobroker | Добавили новый клиент для tcrm
ITAL-5678 | autobroker, docs | Обновили API и документацию
ITAL-9012 | infra | Fix deployment config for staging
```
