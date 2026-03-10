use ratatui::crossterm::event::{
    KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use ratatui::layout::Rect;
use ratatui::style::{Color, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

/// 8 visually distinct colors for agent identification on dark terminals.
pub const AGENT_COLORS: &[Color] = &[
    Color::Cyan,
    Color::Magenta,
    Color::Yellow,
    Color::Blue,
    Color::Green,
    Color::Red,
    Color::LightCyan,
    Color::LightMagenta,
];

/// Get the color for an agent by its color_index (wraps around).
pub fn agent_color(color_index: u8) -> Color {
    AGENT_COLORS[color_index as usize % AGENT_COLORS.len()]
}

/// Client-side view of a single PTY pane.
///
/// Does NOT own a PTY -- the daemon does. This struct maintains a vt100 parser
/// that processes output bytes received from the daemon, and tracks scroll state.
pub struct PaneView {
    pub parser: vt100::Parser,
    pub scroll_offset: usize,
}

impl PaneView {
    pub fn new(rows: u16, cols: u16) -> Self {
        Self {
            parser: vt100::Parser::new(rows, cols, 10000),
            scroll_offset: 0,
        }
    }

    /// Feed output bytes (received from daemon) into the vt100 parser.
    pub fn process_output(&mut self, data: &[u8]) {
        self.parser.process(data);
    }

    /// Resize the virtual terminal.
    pub fn resize(&mut self, rows: u16, cols: u16) {
        self.parser.screen_mut().set_size(rows, cols);
    }

    /// Apply scrollback offset and return the screen for rendering.
    /// Clamps offset to actual scrollback size.
    pub fn scrolled_screen(&mut self) -> &vt100::Screen {
        self.parser.screen_mut().set_scrollback(self.scroll_offset);
        self.scroll_offset = self.parser.screen().scrollback();
        self.parser.screen()
    }

    /// Whether the app inside the PTY has mouse mode enabled.
    pub fn mouse_mode_active(&self) -> bool {
        self.parser.screen().mouse_protocol_mode() != vt100::MouseProtocolMode::None
    }

    /// Whether the app is using the alternate screen buffer.
    pub fn alternate_screen(&self) -> bool {
        self.parser.screen().alternate_screen()
    }

    /// Snap back to live view (scroll_offset = 0).
    pub fn snap_to_bottom(&mut self) {
        self.scroll_offset = 0;
    }
}

/// Encode a crossterm KeyEvent to raw bytes suitable for PTY input.
///
/// Returns None for keys that have no PTY representation.
pub fn encode_key(key: KeyEvent) -> Option<Vec<u8>> {
    if key.modifiers.contains(KeyModifiers::CONTROL) {
        match key.code {
            KeyCode::Char(c) if c.is_ascii_lowercase() => {
                return Some(vec![c as u8 - b'a' + 1]);
            }
            KeyCode::Char(c) if c.is_ascii_uppercase() => {
                return Some(vec![c.to_ascii_lowercase() as u8 - b'a' + 1]);
            }
            KeyCode::Char('\\') => return Some(vec![0x1c]),
            KeyCode::Char(']') => return Some(vec![0x1d]),
            _ => {}
        }
    }

    if key.modifiers.contains(KeyModifiers::SUPER) {
        match key.code {
            KeyCode::Backspace => return Some(vec![0x15]),
            _ => {}
        }
    }

    if key.modifiers.contains(KeyModifiers::ALT) {
        match key.code {
            KeyCode::Backspace => return Some(vec![0x1b, 0x7f]),
            KeyCode::Char(c) => {
                let mut bytes = vec![0x1b];
                let mut buf = [0u8; 4];
                let s = c.encode_utf8(&mut buf);
                bytes.extend_from_slice(s.as_bytes());
                return Some(bytes);
            }
            KeyCode::Left => return Some(b"\x1b[1;3D".to_vec()),
            KeyCode::Right => return Some(b"\x1b[1;3C".to_vec()),
            _ => {}
        }
    }

    match key.code {
        KeyCode::Char(c) => {
            let mut buf = [0u8; 4];
            let s = c.encode_utf8(&mut buf);
            Some(s.as_bytes().to_vec())
        }
        KeyCode::Enter => Some(vec![0x0d]),
        KeyCode::Backspace => Some(vec![0x7f]),
        KeyCode::Tab => Some(vec![0x09]),
        KeyCode::BackTab => Some(b"\x1b[Z".to_vec()),
        KeyCode::Esc => Some(vec![0x1b]),
        KeyCode::Up => Some(b"\x1b[A".to_vec()),
        KeyCode::Down => Some(b"\x1b[B".to_vec()),
        KeyCode::Right => Some(b"\x1b[C".to_vec()),
        KeyCode::Left => Some(b"\x1b[D".to_vec()),
        KeyCode::Home => Some(b"\x1b[H".to_vec()),
        KeyCode::End => Some(b"\x1b[F".to_vec()),
        KeyCode::Delete => Some(b"\x1b[3~".to_vec()),
        KeyCode::PageUp => Some(b"\x1b[5~".to_vec()),
        KeyCode::PageDown => Some(b"\x1b[6~".to_vec()),
        KeyCode::F(1) => Some(b"\x1bOP".to_vec()),
        KeyCode::F(2) => Some(b"\x1bOQ".to_vec()),
        KeyCode::F(3) => Some(b"\x1bOR".to_vec()),
        KeyCode::F(4) => Some(b"\x1bOS".to_vec()),
        KeyCode::F(5) => Some(b"\x1b[15~".to_vec()),
        KeyCode::F(6) => Some(b"\x1b[17~".to_vec()),
        KeyCode::F(7) => Some(b"\x1b[18~".to_vec()),
        KeyCode::F(8) => Some(b"\x1b[19~".to_vec()),
        KeyCode::F(9) => Some(b"\x1b[20~".to_vec()),
        KeyCode::F(10) => Some(b"\x1b[21~".to_vec()),
        KeyCode::F(11) => Some(b"\x1b[23~".to_vec()),
        KeyCode::F(12) => Some(b"\x1b[24~".to_vec()),
        _ => None,
    }
}

/// Encode a mouse event relative to a pane area using SGR mouse protocol.
///
/// Translates absolute terminal coordinates to pane-relative coordinates
/// and produces the appropriate SGR escape sequence.
pub fn encode_mouse_for_pane(mouse: MouseEvent, pane_area: Rect) -> Option<Vec<u8>> {
    let col = mouse.column.checked_sub(pane_area.x)?;
    let row = mouse.row.checked_sub(pane_area.y)?;

    if col >= pane_area.width || row >= pane_area.height {
        return None;
    }

    // SGR encoding is 1-indexed
    let c = col as u32 + 1;
    let r = row as u32 + 1;

    let seq = match mouse.kind {
        MouseEventKind::ScrollUp => format!("\x1b[<64;{c};{r}M"),
        MouseEventKind::ScrollDown => format!("\x1b[<65;{c};{r}M"),
        MouseEventKind::Down(MouseButton::Left) => format!("\x1b[<0;{c};{r}M"),
        MouseEventKind::Up(MouseButton::Left) => format!("\x1b[<0;{c};{r}m"),
        MouseEventKind::Down(MouseButton::Right) => format!("\x1b[<2;{c};{r}M"),
        MouseEventKind::Up(MouseButton::Right) => format!("\x1b[<2;{c};{r}m"),
        MouseEventKind::Down(MouseButton::Middle) => format!("\x1b[<1;{c};{r}M"),
        MouseEventKind::Up(MouseButton::Middle) => format!("\x1b[<1;{c};{r}m"),
        MouseEventKind::Moved => format!("\x1b[<35;{c};{r}M"),
        _ => return None,
    };
    Some(seq.into_bytes())
}

/// Render an agent title bar.
///
/// Layout: ` folder | description ... state duration`
///
/// Background color is determined by agent state (via `color` param),
/// tinted by whether the pane is focused.
pub fn render_title_bar(
    frame: &mut Frame,
    area: Rect,
    folder: &str,
    description: &str,
    state: &str,
    duration: &str,
    color: Color,
    focused: bool,
    hint: Option<&str>,
) {
    let bg = if focused {
        color
    } else {
        dim_color(color)
    };
    let fg = if focused {
        Color::Black
    } else {
        Color::Rgb(80, 80, 80)
    };
    let style = Style::default().bg(bg).fg(fg);

    let left = format!(" {} | {}", folder, description);
    let right = match hint {
        Some(h) => format!(" {} {}  {} ", state, duration, h),
        None => format!(" {} {} ", state, duration),
    };
    let padding_len = (area.width as usize).saturating_sub(left.len() + right.len());
    let padding = " ".repeat(padding_len);

    let line = Line::from(vec![Span::styled(
        format!("{}{}{}", left, padding, right),
        style,
    )]);
    frame.render_widget(Paragraph::new(line), area);
}

/// Dim a color for unfocused pane title bars.
fn dim_color(color: Color) -> Color {
    match color {
        Color::Cyan => Color::Rgb(0, 80, 80),
        Color::Magenta => Color::Rgb(80, 0, 80),
        Color::Yellow => Color::Rgb(80, 80, 0),
        Color::Blue => Color::Rgb(0, 0, 100),
        Color::Green => Color::Rgb(0, 80, 0),
        Color::Red => Color::Rgb(100, 0, 0),
        Color::LightCyan => Color::Rgb(0, 100, 100),
        Color::LightMagenta => Color::Rgb(100, 0, 100),
        Color::Rgb(r, g, b) => Color::Rgb(r / 2, g / 2, b / 2),
        other => other,
    }
}
