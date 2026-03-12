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
- **state** (`state.rs`) — file-locked JSON persistence (`~/.clamor/state.json`)
- **hook** (`hook.rs`) — sync, runs in separate process (no tokio), must stay fast

## Versioning

**Bump the version in `Cargo.toml` with every release commit.** Follow semver:
- **patch** (0.1.x): bug fixes, small improvements, shortcut changes
- **minor** (0.x.0): new features, protocol changes, architectural changes
- **major** (x.0.0): breaking changes to config/state format

Current protocol messages include `Hello { version }` for version exchange between daemon and client.

## Key Shortcuts (terminal mode)

- `Ctrl+F` — detach (back to dashboard)
- `Ctrl+C` — send SIGINT to agent
- `Ctrl+J` — snap to bottom (live view)
