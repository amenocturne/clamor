use crate::config::TerminalBackend;
use crate::diagnostics::terminal_log;
use crate::protocol::{CATCH_UP_ESCAPE_CANCEL, CATCH_UP_MODE_RESET, CATCH_UP_REPAINT_RESET};

mod ghostty {
    use anyhow::Context;
    use libghostty_vt::{
        ffi::{
            GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_ALTERNATE,
            GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_PRIMARY,
        },
        fmt::{Format, Formatter, FormatterOptions},
        terminal::{Mode, ScrollViewport},
        Terminal, TerminalOptions,
    };

    use super::{CursorState, MouseEncoding, MouseMode, TerminalModel, TerminalModes};
    use crate::config::TerminalLogLevel;
    use crate::diagnostics::{terminal_log, with_stderr_suppressed};
    use crate::protocol::catch_up_repair_start;
    use std::time::Instant;

    pub struct GhosttyTerminalModel {
        terminal: Terminal<'static, 'static>,
        max_scrollback: usize,
        viewport_offset: usize,
    }

    impl GhosttyTerminalModel {
        pub fn new(rows: u16, cols: u16, scrollback: usize) -> anyhow::Result<Self> {
            crate::diagnostics::suppress_embedded_ghostty_logging();

            let terminal = Self::new_terminal(rows, cols, scrollback)?;

            Ok(Self {
                terminal,
                max_scrollback: scrollback,
                viewport_offset: 0,
            })
        }

        fn new_terminal(
            rows: u16,
            cols: u16,
            scrollback: usize,
        ) -> anyhow::Result<Terminal<'static, 'static>> {
            with_stderr_suppressed(|| {
                Terminal::new(TerminalOptions {
                    cols,
                    rows,
                    max_scrollback: scrollback,
                })
            })
            .context("creating ghostty terminal model")
        }

        fn mode(&self, mode: Mode) -> bool {
            with_stderr_suppressed(|| self.terminal.mode(mode)).unwrap_or(false)
        }

        fn format(&self, format: Format) -> anyhow::Result<Vec<u8>> {
            let bytes = with_stderr_suppressed(|| {
                let mut formatter = Formatter::new(
                    &self.terminal,
                    FormatterOptions {
                        format,
                        trim: true,
                        unwrap: false,
                    },
                )
                .context("creating ghostty formatter")?;
                formatter
                    .format_alloc(None::<&libghostty_vt::alloc::Allocator<'_, ()>>)
                    .context("formatting ghostty terminal")
            })?;
            Ok(bytes.as_ref().to_vec())
        }
    }

    impl TerminalModel for GhosttyTerminalModel {
        fn process_output(&mut self, bytes: &[u8]) {
            with_stderr_suppressed(|| self.terminal.vt_write(bytes));
        }

        fn process_catch_up(&mut self, bytes: &[u8]) {
            let started = Instant::now();

            let ghostty_bytes = catch_up_repair_start(bytes)
                .map(|start| &bytes[start..])
                .unwrap_or(bytes);
            with_stderr_suppressed(|| self.terminal.vt_write(ghostty_bytes));

            terminal_log(
                TerminalLogLevel::Debug,
                format!(
                    "ghostty catch-up optimized total={} ghostty={} elapsed_ms={}",
                    bytes.len(),
                    ghostty_bytes.len(),
                    started.elapsed().as_millis()
                ),
            );
        }

        fn rebuild_from_history(&mut self, bytes: &[u8]) {
            let started = Instant::now();
            let (rows, cols) = self.size();

            match Self::new_terminal(rows, cols, self.max_scrollback) {
                Ok(mut terminal) => {
                    with_stderr_suppressed(|| terminal.vt_write(bytes));
                    self.terminal = terminal;
                    self.viewport_offset = 0;
                    terminal_log(
                        TerminalLogLevel::Debug,
                        format!(
                            "ghostty rebuild bytes={} elapsed_ms={}",
                            bytes.len(),
                            started.elapsed().as_millis()
                        ),
                    );
                }
                Err(err) => {
                    terminal_log(
                        TerminalLogLevel::Warn,
                        format!("ghostty rebuild failed: {err:#}"),
                    );
                }
            }
        }

        fn resize(&mut self, rows: u16, cols: u16) {
            let _ = with_stderr_suppressed(|| self.terminal.resize(cols, rows, 0, 0));
        }

        fn size(&self) -> (u16, u16) {
            let rows = with_stderr_suppressed(|| self.terminal.rows()).unwrap_or(24);
            let cols = with_stderr_suppressed(|| self.terminal.cols()).unwrap_or(80);
            (rows, cols)
        }

        fn cursor(&self) -> CursorState {
            CursorState {
                row: with_stderr_suppressed(|| self.terminal.cursor_y()).unwrap_or(0),
                col: with_stderr_suppressed(|| self.terminal.cursor_x()).unwrap_or(0),
            }
        }

        fn set_scrollback(&mut self, offset: usize) {
            let total =
                with_stderr_suppressed(|| self.terminal.scrollback_rows()).unwrap_or(0);
            let clamped = offset.min(total);
            with_stderr_suppressed(|| {
                self.terminal.scroll_viewport(ScrollViewport::Bottom);
                if clamped > 0 {
                    self.terminal
                        .scroll_viewport(ScrollViewport::Delta(-(clamped as isize)));
                }
            });
            self.viewport_offset = clamped;
            terminal_log(
                TerminalLogLevel::Trace,
                format!("ghostty set_scrollback requested={offset} actual={clamped}"),
            );
        }

        fn scrollback_len(&self) -> usize {
            self.viewport_offset
        }

        fn scrollback_total(&mut self) -> usize {
            with_stderr_suppressed(|| self.terminal.scrollback_rows()).unwrap_or(0)
        }

        fn modes(&self) -> TerminalModes {
            let active_screen = with_stderr_suppressed(|| self.terminal.active_screen()).ok();
            TerminalModes {
                alternate_screen: active_screen
                    == Some(GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_ALTERNATE)
                    && active_screen
                        != Some(GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_PRIMARY),
                bracketed_paste: self.mode(Mode::BRACKETED_PASTE),
                mouse_mode: if self.mode(Mode::ANY_MOUSE) {
                    MouseMode::AnyMotion
                } else if self.mode(Mode::BUTTON_MOUSE) {
                    MouseMode::ButtonMotion
                } else if self.mode(Mode::NORMAL_MOUSE) {
                    MouseMode::PressRelease
                } else if self.mode(Mode::X10_MOUSE) {
                    MouseMode::Press
                } else {
                    MouseMode::None
                },
                mouse_encoding: if self.mode(Mode::SGR_MOUSE) {
                    MouseEncoding::Sgr
                } else if self.mode(Mode::UTF8_MOUSE) {
                    MouseEncoding::Utf8
                } else {
                    MouseEncoding::Default
                },
            }
        }

        fn contents_formatted(&self) -> Vec<u8> {
            self.format(Format::Vt).unwrap_or_else(|err| {
                terminal_log(
                    TerminalLogLevel::Warn,
                    format!("ghostty VT formatter failed: {err:#}"),
                );
                Vec::new()
            })
        }

        fn visible_text(&self) -> String {
            self.format(Format::Plain)
                .ok()
                .and_then(|bytes| String::from_utf8(bytes).ok())
                .map(|text| text.trim_end_matches('\n').to_string())
                .unwrap_or_else(|| {
                    terminal_log(
                        TerminalLogLevel::Warn,
                        "ghostty plain formatter failed, returning empty",
                    );
                    String::new()
                })
        }

    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CursorState {
    pub row: u16,
    pub col: u16,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MouseMode {
    None,
    Press,
    PressRelease,
    ButtonMotion,
    AnyMotion,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MouseEncoding {
    Default,
    Utf8,
    Sgr,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TerminalModes {
    pub alternate_screen: bool,
    pub bracketed_paste: bool,
    pub mouse_mode: MouseMode,
    pub mouse_encoding: MouseEncoding,
}

pub fn terminal_mode_prelude(modes: TerminalModes) -> Vec<u8> {
    let mut data = Vec::new();

    data.extend_from_slice(CATCH_UP_MODE_RESET);

    if modes.alternate_screen {
        data.extend_from_slice(b"\x1b[?1049h");
    }

    match modes.mouse_mode {
        MouseMode::None => {}
        MouseMode::Press => data.extend_from_slice(b"\x1b[?9h"),
        MouseMode::PressRelease => data.extend_from_slice(b"\x1b[?1000h"),
        MouseMode::ButtonMotion => data.extend_from_slice(b"\x1b[?1002h"),
        MouseMode::AnyMotion => data.extend_from_slice(b"\x1b[?1003h"),
    }

    match modes.mouse_encoding {
        MouseEncoding::Default => {}
        MouseEncoding::Utf8 => data.extend_from_slice(b"\x1b[?1005h"),
        MouseEncoding::Sgr => data.extend_from_slice(b"\x1b[?1006h"),
    }

    if modes.bracketed_paste {
        data.extend_from_slice(b"\x1b[?2004h");
    }

    data
}

pub fn terminal_repair_bytes(
    modes: TerminalModes,
    formatted: &[u8],
    cursor: CursorState,
) -> Vec<u8> {
    let mut data = Vec::with_capacity(CATCH_UP_MODE_RESET.len() + formatted.len() + 64);
    data.push(CATCH_UP_ESCAPE_CANCEL);
    data.extend(terminal_mode_prelude(modes));
    data.extend_from_slice(CATCH_UP_REPAINT_RESET);
    data.extend_from_slice(formatted);
    data.extend_from_slice(
        format!(
            "\x1b[{};{}H",
            cursor.row.saturating_add(1),
            cursor.col.saturating_add(1)
        )
        .as_bytes(),
    );
    data
}

pub trait TerminalModel {
    fn process_output(&mut self, bytes: &[u8]);
    fn process_catch_up(&mut self, bytes: &[u8]) {
        self.process_output(bytes);
    }

    fn rebuild_from_history(&mut self, bytes: &[u8]) {
        self.process_output(bytes);
    }
    fn resize(&mut self, rows: u16, cols: u16);
    fn size(&self) -> (u16, u16);
    fn cursor(&self) -> CursorState;
    fn set_scrollback(&mut self, offset: usize);
    fn scrollback_len(&self) -> usize;
    fn scrollback_total(&mut self) -> usize {
        let current = self.scrollback_len();
        self.set_scrollback(usize::MAX);
        let total = self.scrollback_len();
        self.set_scrollback(current);
        total
    }
    fn modes(&self) -> TerminalModes;
    fn contents_formatted(&self) -> Vec<u8>;
    fn visible_text(&self) -> String;

    fn alternate_screen(&self) -> bool {
        self.modes().alternate_screen
    }

    fn bracketed_paste_active(&self) -> bool {
        self.modes().bracketed_paste
    }

    fn mouse_mode_active(&self) -> bool {
        self.modes().mouse_mode != MouseMode::None
    }
}

#[allow(clippy::large_enum_variant)]
pub enum TerminalModelState {
    Vt100(Vt100TerminalModel),
    Ghostty(ghostty::GhosttyTerminalModel),
}

impl TerminalModelState {
    pub fn new(
        backend: TerminalBackend,
        rows: u16,
        cols: u16,
        scrollback: usize,
    ) -> anyhow::Result<Self> {
        match backend {
            TerminalBackend::Vt100 => {
                Ok(Self::Vt100(Vt100TerminalModel::new(rows, cols, scrollback)))
            }
            TerminalBackend::Ghostty => Ok(Self::Ghostty(ghostty::GhosttyTerminalModel::new(
                rows, cols, scrollback,
            )?)),
        }
    }

    pub fn backend(&self) -> TerminalBackend {
        match self {
            Self::Vt100(_) => TerminalBackend::Vt100,
            Self::Ghostty(_) => TerminalBackend::Ghostty,
        }
    }

    pub fn screen(&self) -> &vt100::Screen {
        match self {
            Self::Vt100(model) => model.screen(),
            Self::Ghostty(_) => {
                panic!(
                    "screen() is not available on the ghostty backend; \
                     use contents_formatted() or visible_text()"
                )
            }
        }
    }
}

impl TerminalModel for TerminalModelState {
    fn process_output(&mut self, bytes: &[u8]) {
        match self {
            Self::Vt100(model) => model.process_output(bytes),
            Self::Ghostty(model) => model.process_output(bytes),
        }
    }

    fn process_catch_up(&mut self, bytes: &[u8]) {
        match self {
            Self::Vt100(model) => model.process_catch_up(bytes),
            Self::Ghostty(model) => model.process_catch_up(bytes),
        }
    }

    fn rebuild_from_history(&mut self, bytes: &[u8]) {
        match self {
            Self::Vt100(model) => model.rebuild_from_history(bytes),
            Self::Ghostty(model) => model.rebuild_from_history(bytes),
        }
    }

    fn resize(&mut self, rows: u16, cols: u16) {
        match self {
            Self::Vt100(model) => model.resize(rows, cols),
            Self::Ghostty(model) => model.resize(rows, cols),
        }
        terminal_log(
            crate::config::TerminalLogLevel::Debug,
            format!(
                "terminal model resized backend={:?} rows={rows} cols={cols}",
                self.backend()
            ),
        );
    }

    fn size(&self) -> (u16, u16) {
        match self {
            Self::Vt100(model) => model.size(),
            Self::Ghostty(model) => model.size(),
        }
    }

    fn cursor(&self) -> CursorState {
        match self {
            Self::Vt100(model) => model.cursor(),
            Self::Ghostty(model) => model.cursor(),
        }
    }

    fn set_scrollback(&mut self, offset: usize) {
        match self {
            Self::Vt100(model) => model.set_scrollback(offset),
            Self::Ghostty(model) => model.set_scrollback(offset),
        }
    }

    fn scrollback_len(&self) -> usize {
        match self {
            Self::Vt100(model) => model.scrollback_len(),
            Self::Ghostty(model) => model.scrollback_len(),
        }
    }

    fn scrollback_total(&mut self) -> usize {
        match self {
            Self::Vt100(model) => model.scrollback_total(),
            Self::Ghostty(model) => model.scrollback_total(),
        }
    }

    fn modes(&self) -> TerminalModes {
        match self {
            Self::Vt100(model) => model.modes(),
            Self::Ghostty(model) => model.modes(),
        }
    }

    fn contents_formatted(&self) -> Vec<u8> {
        match self {
            Self::Vt100(model) => model.contents_formatted(),
            Self::Ghostty(model) => model.contents_formatted(),
        }
    }

    fn visible_text(&self) -> String {
        match self {
            Self::Vt100(model) => model.visible_text(),
            Self::Ghostty(model) => model.visible_text(),
        }
    }

}

pub struct Vt100TerminalModel {
    parser: vt100::Parser,
}

impl Vt100TerminalModel {
    pub fn new(rows: u16, cols: u16, scrollback: usize) -> Self {
        Self {
            parser: vt100::Parser::new(rows, cols, scrollback),
        }
    }

    pub fn screen(&self) -> &vt100::Screen {
        self.parser.screen()
    }
}

impl TerminalModel for Vt100TerminalModel {
    fn process_output(&mut self, bytes: &[u8]) {
        self.parser.process(bytes);
    }

    fn process_catch_up(&mut self, bytes: &[u8]) {
        use crate::protocol::catch_up_repair_start;
        let repair_bytes = catch_up_repair_start(bytes)
            .map(|start| &bytes[start..])
            .unwrap_or(bytes);
        self.parser.process(repair_bytes);
    }

    fn resize(&mut self, rows: u16, cols: u16) {
        self.parser.screen_mut().set_size(rows, cols);
    }

    fn size(&self) -> (u16, u16) {
        self.parser.screen().size()
    }

    fn cursor(&self) -> CursorState {
        let (row, col) = self.parser.screen().cursor_position();
        CursorState { row, col }
    }

    fn set_scrollback(&mut self, offset: usize) {
        self.parser.screen_mut().set_scrollback(offset);
    }

    fn scrollback_len(&self) -> usize {
        self.parser.screen().scrollback()
    }

    fn modes(&self) -> TerminalModes {
        let screen = self.parser.screen();
        TerminalModes {
            alternate_screen: screen.alternate_screen(),
            bracketed_paste: screen.bracketed_paste(),
            mouse_mode: match screen.mouse_protocol_mode() {
                vt100::MouseProtocolMode::None => MouseMode::None,
                vt100::MouseProtocolMode::Press => MouseMode::Press,
                vt100::MouseProtocolMode::PressRelease => MouseMode::PressRelease,
                vt100::MouseProtocolMode::ButtonMotion => MouseMode::ButtonMotion,
                vt100::MouseProtocolMode::AnyMotion => MouseMode::AnyMotion,
            },
            mouse_encoding: match screen.mouse_protocol_encoding() {
                vt100::MouseProtocolEncoding::Default => MouseEncoding::Default,
                vt100::MouseProtocolEncoding::Utf8 => MouseEncoding::Utf8,
                vt100::MouseProtocolEncoding::Sgr => MouseEncoding::Sgr,
            },
        }
    }

    fn contents_formatted(&self) -> Vec<u8> {
        self.parser.screen().contents_formatted()
    }

    fn visible_text(&self) -> String {
        screen_visible_text(self.parser.screen())
    }
}

fn screen_visible_text(screen: &vt100::Screen) -> String {
    let (rows, cols) = screen.size();
    let mut lines = Vec::with_capacity(rows as usize);

    for row in 0..rows {
        let mut line = String::new();
        for col in 0..cols {
            if let Some(cell) = screen.cell(row, col) {
                let contents = cell.contents();
                if contents.is_empty() {
                    line.push(' ');
                } else {
                    line.push_str(contents);
                }
            } else {
                line.push(' ');
            }
        }
        lines.push(line.trim_end().to_string());
    }

    while lines.last().is_some_and(|line| line.is_empty()) {
        lines.pop();
    }

    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{CATCH_UP_ESCAPE_CANCEL, CATCH_UP_MODE_RESET, CATCH_UP_REPAINT_RESET};

    #[test]
    fn vt100_backend_is_constructible() {
        let model = TerminalModelState::new(TerminalBackend::Vt100, 24, 80, 0).unwrap();
        assert_eq!(model.backend(), TerminalBackend::Vt100);
        assert_eq!(model.size(), (24, 80));
    }

    #[test]
    fn ghostty_backend_is_constructible() {
        let model = TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();
        assert_eq!(model.backend(), TerminalBackend::Ghostty);
        assert_eq!(model.size(), (24, 80));
    }

    #[test]
    fn visible_text_trims_blank_cells_and_trailing_empty_lines() {
        let mut model = TerminalModelState::new(TerminalBackend::Vt100, 3, 10, 0).unwrap();
        model.process_output(b"hello\r\nworld");

        assert_eq!(model.visible_text(), "hello\nworld");
    }

    #[test]
    fn ghostty_contents_formatted_produces_valid_vt() {
        let mut ghostty = TerminalModelState::new(TerminalBackend::Ghostty, 3, 10, 0).unwrap();
        ghostty.process_output(b"hello\r\nworld");

        let formatted = ghostty.contents_formatted();
        assert!(!formatted.is_empty());

        // Formatted VT output should be parseable by a vt100 parser
        // and produce equivalent visible text.
        let mut parser = vt100::Parser::new(3, 10, 0);
        parser.process(&formatted);

        assert_eq!(
            screen_visible_text(parser.screen()),
            ghostty.visible_text()
        );
    }

    #[test]
    fn ghostty_scrollback_tracks_correctly() {
        let mut ghostty = TerminalModelState::new(TerminalBackend::Ghostty, 3, 10, 50).unwrap();
        ghostty.process_output(b"one\r\ntwo\r\nthree\r\nfour\r\nfive");

        let total = ghostty.scrollback_total();
        assert!(total > 0, "should have scrollback after overflow");

        ghostty.set_scrollback(1);
        assert_eq!(ghostty.scrollback_len(), 1);

        ghostty.set_scrollback(0);
        assert_eq!(ghostty.scrollback_len(), 0);

        // Setting beyond total clamps
        ghostty.set_scrollback(usize::MAX);
        assert_eq!(ghostty.scrollback_len(), total);
    }

    #[test]
    fn ghostty_catch_up_processes_repair_and_modes() {
        let mut ghostty = TerminalModelState::new(TerminalBackend::Ghostty, 3, 10, 50).unwrap();
        let mut catch_up = b"one\r\ntwo\r\nthree\r\nfour\r\nfive".to_vec();

        catch_up.push(CATCH_UP_ESCAPE_CANCEL);
        catch_up.extend_from_slice(CATCH_UP_MODE_RESET);
        catch_up.extend_from_slice(b"\x1b[?2004h");
        catch_up.extend_from_slice(CATCH_UP_REPAINT_RESET);
        catch_up.extend_from_slice(b"repaired");

        ghostty.process_catch_up(&catch_up);

        assert!(!ghostty.alternate_screen());
        assert!(ghostty.bracketed_paste_active());
        assert_eq!(ghostty.visible_text(), "repaired");
    }

    #[test]
    fn ghostty_rebuild_from_history_restores_state() {
        let mut ghostty = TerminalModelState::new(TerminalBackend::Ghostty, 3, 10, 0).unwrap();

        ghostty.rebuild_from_history(b"one\r\ntwo\r\nthree\r\nfour\x1b[?2004h");

        assert!(ghostty.bracketed_paste_active());
        assert_eq!(ghostty.visible_text(), "two\nthree\nfour");
    }


    // ── DEC 2026 sync output mode ──────────────────────────────────────

    // ── CPR accuracy during DEC 2026 frames ────────────────────────

    #[test]
    fn ghostty_cursor_accurate_during_sync_frame() {
        let mut model = TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();
        model.process_output(b"\x1b[5;1H");
        model.process_output(b"\x1b[?2026h");
        model.process_output(b"Hello");

        let cursor = model.cursor();
        assert_eq!(cursor.row, 4);
        assert_eq!(cursor.col, 5);
    }

    #[test]
    fn ghostty_cursor_matches_with_and_without_sync() {
        let mut with_sync =
            TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();
        let mut without_sync =
            TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();

        with_sync.process_output(b"\x1b[?2026h\x1b[10;1HSync content\x1b[?2026l");
        without_sync.process_output(b"\x1b[10;1HSync content");

        assert_eq!(with_sync.cursor(), without_sync.cursor());
    }

    #[test]
    fn ghostty_cursor_correct_at_cpr_offset_during_sync() {
        let mut model = TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();
        let data = b"\x1b[?2026h\x1b[3;1HABCDEF\x1b[6n";

        let cpr_off = data
            .windows(4)
            .position(|w| w == b"\x1b[6n")
            .expect("CPR should be found");

        model.process_output(&data[..cpr_off]);

        let cursor = model.cursor();
        assert_eq!(cursor.row, 2);
        assert_eq!(cursor.col, 6);
    }

    #[test]
    fn ghostty_cursor_correct_multiple_cprs_in_sync_frame() {
        let mut model = TerminalModelState::new(TerminalBackend::Ghostty, 24, 80, 0).unwrap();
        let data = b"\x1b[?2026h\x1b[1;1HAB\x1b[6nCD\x1b[6n\x1b[?2026l";

        let cpr_off = data
            .windows(4)
            .position(|w| w == b"\x1b[6n")
            .expect("first CPR");

        model.process_output(&data[..cpr_off]);
        assert_eq!(model.cursor().col, 2);

        model.process_output(&data[cpr_off..]);
        assert_eq!(model.cursor().col, 4);
    }
}

#[cfg(test)]
mod vt_perf_bench {
    use super::*;
    use std::time::Instant;

    fn claude_code_output(size: usize) -> Vec<u8> {
        let mut buf = Vec::with_capacity(size);
        let patterns: &[&[u8]] = &[
            b"\x1b[?2026h",
            b"\x1b[2J\x1b[H",
            b"\x1b[38;2;126;156;216m",
            b"\x1b[48;2;30;30;46m",
            b"Hello, this is a line of output from Claude Code with some content\r\n",
            b"\x1b[1m\x1b[3m",
            b"Another line with \x1b[4munderline\x1b[24m text\r\n",
            b"\x1b[0m",
            b"\x1b[10;1H",
            b"\x1b[K",
            b"\x1b[?2026l",
        ];
        let mut i = 0;
        while buf.len() < size {
            buf.extend_from_slice(patterns[i % patterns.len()]);
            i += 1;
        }
        buf.truncate(size);
        buf
    }

    #[test]
    fn bench_vt_backends() {
        let sizes = [1024, 4096, 16384, 65536];
        eprintln!("\n{:>8} {:>12} {:>12} {:>8}", "bytes", "ghostty_ms", "vt100_ms", "ratio");
        eprintln!("{}", "-".repeat(48));

        for &size in &sizes {
            let data = claude_code_output(size);

            let mut ghostty = TerminalModelState::new(
                crate::config::TerminalBackend::Ghostty, 24, 80, 0,
            ).unwrap();
            let t0 = Instant::now();
            ghostty.process_output(&data);
            let ghostty_ms = t0.elapsed().as_secs_f64() * 1000.0;

            let mut vt = TerminalModelState::new(
                crate::config::TerminalBackend::Vt100, 24, 80, 0,
            ).unwrap();
            let t0 = Instant::now();
            vt.process_output(&data);
            let vt100_ms = t0.elapsed().as_secs_f64() * 1000.0;

            let ratio = if vt100_ms > 0.001 { ghostty_ms / vt100_ms } else { f64::NAN };
            eprintln!("{:>8} {:>12.2} {:>12.2} {:>7.1}x", size, ghostty_ms, vt100_ms, ratio);
        }
    }
}
