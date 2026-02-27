# Work Workspace

Scala and infrastructure focused workspace.

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

## Working on a Task

When user asks to work on an ITAL task (e.g. "work on ITAL-1234", "implement ITAL-1234"):
1. Fetch task description using the dp-jira skill
2. Create a branch: `git checkout -b feature/ITAL-<number>`
3. Ask the user any clarifying questions needed before starting

## Git

Format: `ITAL-1234 | app | Message`
- `ITAL-1234` — task number (can be omitted if no task)
- `app` — component(s): app name, `docs`, multiple comma-separated
- Message — Russian, passive voice ("добавлен", "обновлен", "исправлен")

Examples:
```
ITAL-1234 | autobroker | Добавлен новый клиент для tcrm
ITAL-5678 | autobroker, docs | Обновлены API и документация
infra | Исправлен конфиг деплоя для staging
```

---

{{include:common/skills.md}}

{{include:common/workspace.md}}

{{include:common/agentic-kit.md}}

{{include:common/commands.md}}

{{include:common/tmp.md}}

{{include:common/code-style.md}}

{{include:common/comments.md}}

{{include:common/quality.md}}

{{include:common/communication-style.md}}
