## Commands

- Always use `just` for command aliases when available
- Run `just` (no args) to see available commands
- Never run raw `python` — use `uv run` instead
- Never use `pip` — use package manager (brew) for system tools, `uvx` for Python CLIs

Standard command names across projects:
- `just run` — run the project (optionally: `just run prod`)
- `just setup` — initial setup / install dependencies
- `just test` — run tests
- `just lint` / `just fmt` — code quality
- `just build` — compile/bundle
- `just clean` / `just reset` — cleanup
