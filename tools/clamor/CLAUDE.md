# clamor

Terminal multiplexer TUI for managing multiple Claude Code agents via a daemon/client architecture.

## Commands

```bash
cargo check                  # Type-check
cargo test                   # Run all tests (unit + integration)
cargo build --release        # Build optimized binary
cargo clippy                 # Lint
cargo fmt                    # Format
```

## Architecture

- **daemon** (`daemon.rs`) — async tokio event loop, manages PTYs via `portable-pty`, communicates over Unix socket with length-prefixed JSON
- **client** (`client.rs`) — async `DaemonClient` with 5s timeouts on all operations
- **dashboard** (`dashboard/mod.rs`) — `tokio::select!` over daemon messages, crossterm `EventStream`, and 16ms frame ticks
- **protocol** (`protocol.rs`) — wire format (4-byte BE length + JSON), both sync and async variants
- **pane** (`pane.rs`) — `vt100::Parser` wrapper with scrollback, selection, clipboard
- **state** (`state.rs`) — file-locked JSON persistence (`~/.clamor/state.json`); three states: Working, Input, Done (Lost was removed — daemon auto-resumes sessions on restart)
- **hook** (`hook.rs`) — sync, runs in separate process (no tokio), must stay fast

## Versioning

**Bump the version in `Cargo.toml` with every release commit.** Follow semver:
- **patch** (0.1.x): bug fixes, small improvements, shortcut changes
- **minor** (0.x.0): new features, protocol changes, architectural changes
- **major** (x.0.0): breaking changes to config/state format

Current protocol messages include `Hello { version }` for version exchange between daemon and client.

## Key Shortcuts

### Dashboard (normal mode)

- Jump keys (`a`/`s`/`d`/`f`/`j`/`k`/`l`/`h` + `1`–`0` overflow) — attach to agent
- `J`/`K` or arrows — navigate agent list
- `g`/`G` — jump to first/last agent
- `Enter` — attach to selected agent
- `c` — create agent (inline prompt), `C` — create via `$EDITOR`
- `x` + key — kill agent (with confirmation)
- `e` + key — edit agent description
- `v` — toggle select, `V` — select/deselect all
- `/` — filter agents by name
- `R` — adopt existing Claude Code session
- `?` — help popup
- `Ctrl+C` — quit hint (press `q` to confirm)
- `Esc` — clear selection
- `q` — quit dashboard

### Spawn prompt

- `Tab` — toggle between title/description fields
- `Up`/`Down` — prompt history
- `Ctrl+W` / `Alt+Backspace` — delete word
- `Ctrl+U` — delete line

### Terminal (attached)

- `Ctrl+F` — detach (back to dashboard)
- `Ctrl+C` — send SIGINT to agent
- `Ctrl+J` — snap to bottom (live view)
