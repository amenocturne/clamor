# agentic-kit

Personal toolkit for Claude Code: skills, hooks, pipelines, and composable presets.

## Commands

Run `just` to see available commands. Key ones:

```bash
just install                       # Reinstall all registered targets (run after any change)
just install-interactive           # Install preset interactively (first-time setup)
just install-to <target> <preset>  # Install to specific directory
just test                          # Run tests
just fmt && just lint              # Format and lint
```

**After modifying skills, presets, hooks, or common files:** run `just install` to propagate changes to all targets.

## Testing

```bash
pytest                              # All tests
pytest tests/test_install.py        # Installer tests
pytest skills/youtube/              # Skill-specific tests
```

Scripts use PEP 723 inline metadata. Run with `uv run <script>`.

## Skill Authoring

Each skill lives in `skills/<name>/` with `SKILL.md` + `metadata.json` (+ optional `scripts/`).

**SKILL.md structure rule**: The `description` field in frontmatter handles all "when and why to use" logic — it's what triggers skill activation. The markdown body should be purely operational (how to use, commands, flags, caveats). Don't repeat trigger conditions in the body — if the agent is reading the body, it already decided to use the skill.

```yaml
---
name: my-skill
description: "All trigger/routing info here. When to use, what it does, keyword triggers."
author: amenocturne
---

# My Skill

## Commands        <-- jump straight to usage
## Important       <-- caveats, limits
```

## Clamor Public Repo

Clamor (`tools/clamor/`) is published as a standalone public repo and crate.

- **GitHub**: https://github.com/amenocturne/clamor
- **Crate**: https://crates.io/crates/clamor
- **Hooks**: canonical location is `tools/clamor/hooks/`, symlinked from `hooks/clamor/`
- **License**: MIT

**Before pushing Clamor changes to the public repo, always ask the user first.** Don't push automatically — the user decides when and what gets published.

### Sync workflow

```bash
git subtree push --prefix=tools/clamor clamor-public main
```

### Publishing a new version

1. Bump version in `tools/clamor/Cargo.toml` (follow semver)
2. Sync changes to public repo clone, commit, push
3. Tag the version: `git tag -a v<version> -m "v<version>"` (in the public repo)
4. Publish crate: `cargo publish` (from `tools/clamor/`)

### CI

GitHub Actions runs `cargo fmt --check`, `cargo clippy`, and `cargo test` on push/PR to main. The workflow lives in the public repo's `.github/workflows/ci.yml` (not in the subtree — added directly to the public repo).

## TODO

**Remind the user about these when starting work here.**

- **Agentic Knowledge Base**: Lighter-weight KB for dev/work presets. Agent reflects on work, saves learnings, avoids repeating mistakes. Session reflection, persistent memory, pattern recognition, self-updating.
