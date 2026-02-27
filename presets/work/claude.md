# Work Workspace

Scala and infrastructure focused workspace.

## Skills

Proactively use skills whenever relevant. Before starting a task, check if any available skill matches the context — invoke it immediately as your first action.

## Knowledge Base

Project conventions and hard-won patterns live in `/Users/a.ragulin/Vault/Work/knowledge-base/`:
- `scala-zio.md` — ZIO/effect patterns, InterpreterResponse, list-as-chain idiom
- `design.md` — design heuristics, avoiding invalid states
- `git.md` — commit message conventions
- `tooling.md` — workspace/agent conventions

**Search it with Grep by keyword before:**
- Making a design decision (e.g. "how to chain effects", "enum ordering")
- Writing a commit message
- Working with agents, skills, or workspace tooling

**Add to it** when a non-obvious convention is established or a mistake is corrected.

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

## Working on a Task

When user asks to work on an ITAL task (e.g. "work on ITAL-1234", "implement ITAL-1234"):
1. Fetch task description using the dp-jira skill
2. Create a branch: `git checkout -b feature/ITAL-<number>`
3. Ask the user any clarifying questions needed before starting

## Modifying Claude Configuration

**Never edit `.claude/` files directly** — they're symlinks to agentic-kit. To modify skills, instructions, or hooks:

1. Get agentic-kit path: `jq -r '.agentic_kit' .claude/agentic-kit.json`
2. Edit in agentic-kit repo (skills/, presets/, hooks/)
3. Changes sync automatically via symlinks (or re-run installer if needed)

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
- Never use `pip` — use package manager (brew) for system tools, `uvx` for Python CLIs

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
- Message — concise statement of what was done, not imperative/infinitive form (use "добавлен", "разделены", "обновлены" — not "добавить", "разделить", "обновили")

Examples:
```
ITAL-1234 | autobroker | Добавлен новый клиент для tcrm
ITAL-5678 | autobroker, docs | Обновлены API и документация
ITAL-9012 | infra | Fix deployment config for staging
```
