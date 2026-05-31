use crate::config::TerminalBackend;
use crate::diagnostics::terminal_log;

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

    use super::{
        screen_visible_text, CursorState, MouseEncoding, MouseMode, TerminalModel, TerminalModes,
    };
    use crate::config::TerminalLogLevel;
    use crate::diagnostics::terminal_log;

    pub struct GhosttyTerminalModel {
        terminal: Terminal<'static, 'static>,
        render_shadow: super::Vt100TerminalModel,
        viewport_offset: usize,
    }

    impl GhosttyTerminalModel {
        pub fn new(rows: u16, cols: u16, scrollback: usize) -> anyhow::Result<Self> {
            crate::diagnostics::suppress_embedded_ghostty_logging();

            let terminal = Terminal::new(TerminalOptions {
                cols,
                rows,
                max_scrollback: scrollback,
            })
            .context("creating ghostty terminal model")?;

            Ok(Self {
                terminal,
                render_shadow: super::Vt100TerminalModel::new(rows, cols, scrollback),
                viewport_offset: 0,
            })
        }

        pub fn screen(&self) -> &vt100::Screen {
            self.render_shadow.screen()
        }

        fn mode(&self, mode: Mode) -> bool {
            self.terminal.mode(mode).unwrap_or(false)
        }

        fn format(&self, format: Format) -> anyhow::Result<Vec<u8>> {
            let mut formatter = Formatter::new(
                &self.terminal,
                FormatterOptions {
                    format,
                    trim: true,
                    unwrap: false,
                },
            )
            .context("creating ghostty formatter")?;
            let bytes = formatter
                .format_alloc(None::<&libghostty_vt::alloc::Allocator<'_, ()>>)
                .context("formatting ghostty terminal")?;
            Ok(bytes.as_ref().to_vec())
        }
    }

    impl TerminalModel for GhosttyTerminalModel {
        fn process_output(&mut self, bytes: &[u8]) {
            self.terminal.vt_write(bytes);
            self.render_shadow.process_output(bytes);
        }

        fn resize(&mut self, rows: u16, cols: u16) {
            let _ = self.terminal.resize(cols, rows, 0, 0);
            self.render_shadow.resize(rows, cols);
        }

        fn size(&self) -> (u16, u16) {
            let shadow_size = self.render_shadow.size();
            let rows = self.terminal.rows().unwrap_or(shadow_size.0);
            let cols = self.terminal.cols().unwrap_or(shadow_size.1);
            (rows, cols)
        }

        fn cursor(&self) -> CursorState {
            let shadow_cursor = self.render_shadow.cursor();
            CursorState {
                row: self.terminal.cursor_y().unwrap_or(shadow_cursor.row),
                col: self.terminal.cursor_x().unwrap_or(shadow_cursor.col),
            }
        }

        fn set_scrollback(&mut self, offset: usize) {
            let max = self
                .terminal
                .scrollback_rows()
                .unwrap_or_else(|_| self.render_shadow.scrollback_len());
            let target = offset.min(max);
            let delta = target as isize - self.viewport_offset as isize;
            self.terminal.scroll_viewport(ScrollViewport::Delta(delta));
            self.viewport_offset = target;
            self.render_shadow.set_scrollback(offset);
            terminal_log(
                TerminalLogLevel::Debug,
                format!("ghostty set_scrollback requested={offset} target={target} max={max} delta={delta}"),
            );
        }

        fn scrollback_len(&self) -> usize {
            self.viewport_offset
        }

        fn scrollback_total(&mut self) -> usize {
            self.terminal
                .scrollback_rows()
                .unwrap_or_else(|_| self.render_shadow.scrollback_total())
        }

        fn modes(&self) -> TerminalModes {
            let active_screen = self.terminal.active_screen().ok();
            TerminalModes {
                alternate_screen: active_screen
                    == Some(GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_ALTERNATE)
                    && active_screen != Some(GhosttyTerminalScreen_GHOSTTY_TERMINAL_SCREEN_PRIMARY),
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
                    format!("ghostty VT formatter failed, using vt100 shadow: {err:#}"),
                );
                self.render_shadow.contents_formatted()
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
                        "ghostty plain formatter failed, using vt100 shadow",
                    );
                    screen_visible_text(self.render_shadow.screen())
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

pub trait TerminalModel {
    fn process_output(&mut self, bytes: &[u8]);
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
            Self::Ghostty(model) => model.screen(),
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
}
