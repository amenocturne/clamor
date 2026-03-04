# Work Workspace

Scala and infrastructure focused workspace.

## sbt

**Always use `sbt --client`** for all sbt commands. This uses thin client mode which connects to an existing sbt server (or spawns one if needed).

Why: Metals runs its own sbt BSP server. Running plain `sbt` spawns a competing instance, causing lock conflicts and resource contention. The thin client shares the same server.

```bash
sbt --client compile      # instead of: sbt compile
sbt --client test         # instead of: sbt test
sbt --client "testOnly *MySpec"
```

To stop the server: `sbt --client shutdown`

Compilation is usually a long-running task, so you must not run it directly and set timeout, instead you should run it as async command without any timeouts

### Lock issue

`sbt --client` can silently hang waiting for `~/.sbt/boot/.../sbt.components.lock`. The workarounds below reduce the risk, but it can still happen — if a background compile produces no output after 30s, this is the likely cause.

Before running any sbt command, check for the lock:
```bash
lock=$(ls ~/.sbt/boot/scala-*/org.scala-sbt/sbt/*/sbt.components.lock 2>/dev/null)
[ -n "$lock" ] && echo "WARNING: sbt lock exists: $lock — remove before running sbt" && exit 1
```

Wrap background compiles with a timeout to avoid silent hangs:
```bash
timeout 600 sbt --client compile || {
  ec=$?
  [ $ec -eq 124 ] && echo "sbt timed out — check for stale lock: ~/.sbt/boot/.../sbt.components.lock"
  exit $ec
}
```

To clear a stale lock: `rm ~/.sbt/boot/scala-*/org.scala-sbt/sbt/*/sbt.components.lock`

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

When researching something or creating new branch, make sure to firstly switch to `master` if other instructions from user are present.

Proactively use orchestration skill instead of manually doing low-level work.
You are the agent who communicates with user, gathers requirements and plans the
work, not the one doing it

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

## Link Proxy

A local proxy intercepts API traffic and transforms internal URLs to/from
placeholders. It starts automatically on session start.

**What you need to know:**
- Internal URLs work transparently — no special handling needed
- If you see connection errors, the proxy may not be running.
  Check: `curl http://127.0.0.1:18923/health`
  Start: `uv run hooks/link-proxy/proxy.py`

