# clamor

Terminal multiplexer TUI for managing multiple coding agents via a daemon/client architecture.

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
- **config** (`config.rs`) — YAML config at `~/.config/clamor/config.yaml`, backend registry with built-in templates, folder-to-backend mapping, legacy JSON migration
- **spawn** (`spawn.rs`) — backend-driven spawn/resume resolver with `{{var}}` template rendering
- **hook** (`hook.rs`) — sync, runs in separate process (no tokio), must stay fast

## Multi-Backend Support

Clamor is backend-agnostic. Each folder can list multiple backends; one is selected at a time.

- **Config**: `~/.config/clamor/config.yaml` defines backends (spawn/resume commands, capabilities) and folders (path + allowed backends)
- **Built-in backends**: `claude-code`, `open-code`, `pi` — merged with user config at load time
- **Runtime state**: selected backend per folder persists in `~/.clamor/state.json`
- **Hooks**: only enabled for backends with `capabilities.hooks: true` (currently Claude Code)
- **Process exit**: all backends get `Done` state via PTY exit detection, regardless of hook support

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
- `gg`/`G` — jump to first/last agent
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

- `Tab` / `Shift-Tab` — cycle backend for selected folder
- `Tab` — toggle between title/description fields
- `Up`/`Down` — prompt history
- `Ctrl+W` / `Alt+Backspace` — delete word
- `Ctrl+U` — delete line

### Terminal (attached)

- `Ctrl+F` — detach (back to dashboard)
- `Ctrl+C` — send SIGINT to agent
- `Ctrl+J` — snap to bottom (live view)
- `Ctrl+S` — enter copy mode
- Scroll up — freeze display (output buffered, shown on return to live)

### Copy mode

- `h`/`j`/`k`/`l` or arrows — move cursor
- `v` — toggle selection (character-wise)
- `V` — toggle selection (line-wise)
- `y` — yank selection to clipboard + exit
- `0`/`$` — start/end of line
- `Ctrl+U`/`Ctrl+D` — half page up/down
- `gg`/`G` — top/bottom of scrollback
- `q`/`Esc` — exit copy mode
- `Ctrl+J` — exit copy mode (snap to bottom)
