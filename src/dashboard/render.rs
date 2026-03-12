use std::collections::HashMap;

use chrono::Utc;
use ratatui::layout::Position;
use ratatui::layout::{Constraint, Flex, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, Paragraph, Wrap};
use ratatui::Frame;

use crate::agent::{Agent, AgentState};
use crate::config::FleetConfig;
use crate::pane::{self, Selection};

use super::input::PromptField;

/// An agent prepared for display, with its assigned jump key and status flags.
pub struct DisplayAgent<'a> {
    pub agent: &'a Agent,
    pub key: Option<char>,
    pub killed: bool,
}

/// Overlay state passed to render for popup display.
pub enum Overlay<'a> {
    None,
    PendingKill,
    FolderPicker {
        folders: &'a [(String, String)],
    },
    PromptInput {
        folder_name: &'a str,
        title: &'a str,
        description: &'a str,
        active_field: &'a PromptField,
    },
    AdoptInput {
        input: &'a str,
    },
    StaleAgents {
        count: usize,
    },
    StaleAgent {
        description: &'a str,
    },
    ConfirmEmptySpawn,
    PendingEdit,
    EditInput {
        input: &'a str,
    },
}

/// Render the full dashboard frame.
pub fn render(
    frame: &mut Frame,
    config: &FleetConfig,
    agents: &HashMap<String, &Agent>,
    killed_ids: &[String],
    overlay: &Overlay,
) {
    let area = frame.area();

    // Build display agents grouped by folder
    let groups = build_groups(config, agents, killed_ids);

    // Count stats (exclude killed from count)
    let total = agents.len()
        - killed_ids
            .iter()
            .filter(|id| agents.contains_key(*id))
            .count();
    let needs_input = agents
        .values()
        .filter(|a| a.state == AgentState::Input)
        .count();

    // Layout: header, separator, body, footer
    let chunks = Layout::vertical([
        Constraint::Length(1), // header
        Constraint::Length(1), // separator
        Constraint::Min(1),    // body
        Constraint::Length(1), // footer
    ])
    .split(area);

    render_header(frame, chunks[0], total, needs_input);
    render_separator(frame, chunks[1]);
    render_body(frame, chunks[2], &groups);
    render_footer(frame, chunks[3], overlay);

    // Render overlay popups on top
    match overlay {
        Overlay::FolderPicker { folders } => {
            render_folder_popup(frame, area, folders);
        }
        Overlay::PromptInput {
            folder_name,
            title,
            description,
            active_field,
        } => {
            render_prompt_popup(frame, area, folder_name, title, description, active_field);
        }
        Overlay::AdoptInput { input } => {
            render_adopt_popup(frame, area, input);
        }
        Overlay::StaleAgents { count } => {
            render_stale_popup(frame, area, *count);
        }
        Overlay::StaleAgent { description } => {
            render_stale_agent_popup(frame, area, description);
        }
        Overlay::ConfirmEmptySpawn => {
            render_confirm_empty_popup(frame, area);
        }
        Overlay::EditInput { input } => {
            render_edit_popup(frame, area, input);
        }
        _ => {}
    }
}

/// Render the terminal view for an agent (title bar + PseudoTerminal).
pub fn render_terminal(
    frame: &mut Frame,
    screen: &vt100::Screen,
    agent: &Agent,
    selection: &Option<Selection>,
) {
    let area = frame.area();
    let chunks = Layout::vertical([
        Constraint::Length(1), // title bar
        Constraint::Min(1),    // terminal content
    ])
    .split(area);

    let color = pane::agent_color(agent.color_index);
    let state_str = match agent.state {
        AgentState::Working => "working",
        AgentState::Input => "input",
        AgentState::Done => "done",
        AgentState::Lost => "lost",
    };
    let duration = format_duration(agent.started_at);
    pane::render_title_bar(
        frame,
        chunks[0],
        &agent.folder,
        &agent.title,
        state_str,
        &duration,
        color,
        true,
        Some("^F back  ^J bottom"),
    );

    let pseudo_term = tui_term::widget::PseudoTerminal::new(screen);
    frame.render_widget(pseudo_term, chunks[1]);

    // Overlay selection highlight
    if let Some(sel) = selection {
        let pane = chunks[1];
        render_selection(frame, pane, sel);
    }
}

fn render_header(frame: &mut Frame, area: Rect, total: usize, needs_input: usize) {
    let mut spans = vec![
        Span::styled(
            "FLEET",
            Style::default()
                .fg(Color::White)
                .add_modifier(Modifier::BOLD),
        ),
        Span::raw("  "),
    ];

    let stats = if needs_input > 0 {
        format!(
            "{} agent{} | {} needs input",
            total,
            if total != 1 { "s" } else { "" },
            needs_input
        )
    } else {
        format!("{} agent{}", total, if total != 1 { "s" } else { "" })
    };

    spans.push(Span::styled(stats, Style::default().fg(Color::DarkGray)));

    let header = Paragraph::new(Line::from(spans));
    frame.render_widget(header, area);
}

fn render_separator(frame: &mut Frame, area: Rect) {
    let line = "\u{2500}".repeat(area.width as usize);
    let sep = Paragraph::new(Line::from(Span::styled(
        line,
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(sep, area);
}

fn render_footer(frame: &mut Frame, area: Rect, overlay: &Overlay) {
    let footer = match overlay {
        Overlay::PendingKill => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled(
                "Kill: press agent key (Esc to cancel)",
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
        ])),
        Overlay::PendingEdit => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled(
                "Edit: press agent key (Esc to cancel)",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
        ])),
        _ => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled("[key]", Style::default().fg(Color::Cyan)),
            Span::raw(" attach  "),
            Span::styled("[c]", Style::default().fg(Color::Cyan)),
            Span::raw("reate  "),
            Span::styled("[C]", Style::default().fg(Color::Cyan)),
            Span::raw(" $EDITOR  "),
            Span::styled("[e]", Style::default().fg(Color::Cyan)),
            Span::raw("dit  "),
            Span::styled("[R]", Style::default().fg(Color::Cyan)),
            Span::raw(" adopt  "),
            Span::styled("[K", Style::default().fg(Color::Cyan)),
            Span::raw("+"),
            Span::styled("key]", Style::default().fg(Color::Cyan)),
            Span::raw(" kill  "),
            Span::styled("[q]", Style::default().fg(Color::Cyan)),
            Span::raw("uit"),
        ])),
    };
    frame.render_widget(footer, area);
}

/// A group of agents under a folder heading.
struct AgentGroup<'a> {
    folder_name: String,
    agents: Vec<DisplayAgent<'a>>,
}

fn build_groups<'a>(
    config: &FleetConfig,
    agents: &HashMap<String, &'a Agent>,
    killed_ids: &[String],
) -> Vec<AgentGroup<'a>> {
    // Collect folder names from config, sorted
    let mut folder_keys: Vec<&String> = config.folders.keys().collect();
    folder_keys.sort();

    // Also collect folder keys that appear in agents but not in config
    let mut extra_folders: Vec<String> = agents
        .values()
        .map(|a| a.folder.clone())
        .filter(|f| !config.folders.contains_key(f))
        .collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();
    extra_folders.sort();

    let mut groups = Vec::new();

    let all_folder_keys: Vec<String> = folder_keys
        .iter()
        .map(|k| (*k).clone())
        .chain(extra_folders)
        .collect();

    for folder_key in &all_folder_keys {
        let mut folder_agents: Vec<(&String, &&Agent)> = agents
            .iter()
            .filter(|(_, a)| a.folder == *folder_key)
            .collect();

        if folder_agents.is_empty() {
            continue;
        }

        folder_agents.sort_by_key(|(_, a)| a.started_at);

        let display_agents: Vec<DisplayAgent> = folder_agents
            .iter()
            .map(|(id, agent)| DisplayAgent {
                agent,
                key: agent.key,
                killed: killed_ids.contains(id),
            })
            .collect();

        let folder_name = folder_key.clone();

        groups.push(AgentGroup {
            folder_name,
            agents: display_agents,
        });
    }

    groups
}

fn render_body(frame: &mut Frame, area: Rect, groups: &[AgentGroup]) {
    let mut lines: Vec<Line> = Vec::new();
    let width = area.width as usize;

    for (i, group) in groups.iter().enumerate() {
        if i > 0 {
            lines.push(Line::from(""));
        }

        // Folder header
        lines.push(Line::from(Span::styled(
            format!(" {}", group.folder_name),
            Style::default().add_modifier(Modifier::BOLD),
        )));

        for da in &group.agents {
            lines.push(render_agent_line(da, width));
        }
    }

    let body = Paragraph::new(lines);
    frame.render_widget(body, area);
}

fn render_agent_line(da: &DisplayAgent, width: usize) -> Line<'static> {
    let key_str = da
        .key
        .map(|c| format!("  {}  ", c))
        .unwrap_or_else(|| "     ".into());

    let (state_label, state_style) = if da.killed {
        (
            "killed",
            Style::default().fg(Color::Red).add_modifier(Modifier::DIM),
        )
    } else {
        match da.agent.state {
            AgentState::Input => (
                "input",
                Style::default()
                    .fg(Color::Yellow)
                    .add_modifier(Modifier::BOLD),
            ),
            AgentState::Working => ("work ", Style::default().fg(Color::Green)),
            AgentState::Done => ("done ", Style::default().fg(Color::DarkGray)),
            AgentState::Lost => (
                "lost ",
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(Modifier::DIM),
            ),
        }
    };

    let duration = format_duration(da.agent.started_at);

    // state_label is 5 or 6 chars — normalize to 6 for "killed"
    let state_display = format!("{:<6}", state_label);

    // Calculate available space for description:
    // key(5) + state(6) + spacing(4) + duration(~8) + padding(2)
    let overhead = key_str.len() + 6 + 4 + duration.len() + 2;
    let desc_width = width.saturating_sub(overhead);
    let description = truncate(&da.agent.title, desc_width);

    let padded_desc = format!("{:<width$}", description, width = desc_width);

    let key_style = Style::default()
        .fg(Color::Cyan)
        .add_modifier(Modifier::BOLD);

    let dimmed = da.killed || da.agent.state == AgentState::Lost;

    // Use agent color for description text (unless dimmed)
    let desc_style = if dimmed {
        Style::default().fg(Color::DarkGray)
    } else {
        let color = pane::agent_color(da.agent.color_index);
        Style::default().fg(color)
    };

    let duration_style = Style::default().fg(Color::DarkGray);

    Line::from(vec![
        Span::styled(key_str, key_style),
        Span::styled(state_display, state_style),
        Span::raw("  "),
        Span::styled(padded_desc, desc_style),
        Span::raw("  "),
        Span::styled(duration, duration_style),
    ])
}

pub fn format_duration(started_at: chrono::DateTime<Utc>) -> String {
    let elapsed = Utc::now().signed_duration_since(started_at);
    let total_secs = elapsed.num_seconds().max(0);

    if total_secs < 60 {
        format!("{}s", total_secs)
    } else if total_secs < 3600 {
        format!("{}m", total_secs / 60)
    } else if total_secs < 86400 {
        let hours = total_secs / 3600;
        let mins = (total_secs % 3600) / 60;
        if mins > 0 {
            format!("{}h{}m", hours, mins)
        } else {
            format!("{}h", hours)
        }
    } else {
        format!("{}d", total_secs / 86400)
    }
}

fn truncate(s: &str, max_len: usize) -> String {
    if max_len <= 3 {
        return s.chars().take(max_len).collect();
    }
    if s.len() <= max_len {
        s.to_string()
    } else {
        let truncated: String = s.chars().take(max_len - 3).collect();
        format!("{}...", truncated)
    }
}

/// Center a popup rect of given width/height inside an area.
fn popup_area(area: Rect, width: u16, height: u16) -> Rect {
    let [area] = Layout::horizontal([Constraint::Length(width)])
        .flex(Flex::Center)
        .areas(area);
    let [area] = Layout::vertical([Constraint::Length(height)])
        .flex(Flex::Center)
        .areas(area);
    area
}

fn render_folder_popup(frame: &mut Frame, area: Rect, folders: &[(String, String)]) {
    let height = (folders.len() as u16) + 2; // border top/bottom
    let width = folders
        .iter()
        .map(|(name, _)| name.len() + 6) // "  1  Name"
        .max()
        .unwrap_or(20)
        .max(20) as u16
        + 2; // borders

    let popup = popup_area(area, width, height);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" Create ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let lines: Vec<Line> = folders
        .iter()
        .enumerate()
        .map(|(i, (name, _))| {
            Line::from(vec![
                Span::styled(
                    format!("  {}  ", i + 1),
                    Style::default()
                        .fg(Color::Cyan)
                        .add_modifier(Modifier::BOLD),
                ),
                Span::raw(name.clone()),
            ])
        })
        .collect();

    frame.render_widget(Paragraph::new(lines), inner);
}

fn render_prompt_popup(
    frame: &mut Frame,
    area: Rect,
    folder_name: &str,
    title_text: &str,
    desc_text: &str,
    active_field: &PromptField,
) {
    let width = area.width.min(70);
    let height = (area.height * 2 / 5).clamp(10, 20);
    let popup = popup_area(area, width, height);
    frame.render_widget(Clear, popup);

    let block_title = format!(" {} ", folder_name);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(block_title);

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let cursor = "\u{258e}";
    let (title_active, desc_active) = match active_field {
        PromptField::Title => (true, false),
        PromptField::Description => (false, true),
    };

    let title_label_style = if title_active {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };
    let desc_label_style = if desc_active {
        Style::default().fg(Color::Cyan)
    } else {
        Style::default().fg(Color::DarkGray)
    };

    let title_display = if title_active {
        format!("{title_text}{cursor}")
    } else {
        title_text.to_string()
    };
    let desc_display = if desc_active {
        format!("{desc_text}{cursor}")
    } else {
        desc_text.to_string()
    };

    let lines = vec![
        Line::from(vec![
            Span::styled("Title: ", title_label_style),
            Span::raw(title_display),
        ]),
        Line::from(""),
        Line::from(Span::styled("Description:", desc_label_style)),
        Line::from(Span::raw(desc_display)),
        Line::from(""),
        Line::from(Span::styled(
            "Tab switch \u{00b7} empty = interactive session",
            Style::default().fg(Color::DarkGray),
        )),
    ];

    let paragraph = Paragraph::new(lines).wrap(Wrap { trim: false });
    frame.render_widget(paragraph, inner);
}

fn render_adopt_popup(frame: &mut Frame, area: Rect, input: &str) {
    let width = area.width.min(60);
    let popup = popup_area(area, width, 5);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" Adopt session ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let display = format!("{input}\u{258e}");
    let prompt = Paragraph::new(Line::from(Span::raw(display))).wrap(Wrap { trim: false });
    frame.render_widget(prompt, inner);
}

fn render_stale_popup(frame: &mut Frame, area: Rect, count: usize) {
    let width = area.width.min(58);
    let popup = popup_area(area, width, 7);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray))
        .title(" Stale agents ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let text = vec![
        Line::from(format!(
            " {count} agent(s) lost from a previous daemon session."
        )),
        Line::from(""),
        Line::from(Span::styled(
            " You can resume them: claude --resume <session-id>",
            Style::default().fg(Color::DarkGray),
        )),
        Line::from(""),
        Line::from(" [y] clean up    [n] keep"),
    ];
    frame.render_widget(Paragraph::new(text), inner);
}

fn render_stale_agent_popup(frame: &mut Frame, area: Rect, description: &str) {
    let width = area.width.min(58);
    let popup = popup_area(area, width, 7);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray))
        .title(" Stale session ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let desc = truncate(description, (width - 4) as usize);
    let text = vec![
        Line::from(format!(" \"{}\" is from a previous daemon.", desc)),
        Line::from(""),
        Line::from(Span::styled(
            " Resume outside fleet: claude --resume <session-id>",
            Style::default().fg(Color::DarkGray),
        )),
        Line::from(""),
        Line::from(" [y] remove    [n] keep"),
    ];
    frame.render_widget(Paragraph::new(text), inner);
}

fn render_confirm_empty_popup(frame: &mut Frame, area: Rect) {
    let width = area.width.min(48);
    let popup = popup_area(area, width, 5);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" Empty prompt ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let text = vec![
        Line::from(" Spawn an interactive session?"),
        Line::from(""),
        Line::from(" [y] yes    [n] cancel"),
    ];
    frame.render_widget(Paragraph::new(text), inner);
}

fn render_edit_popup(frame: &mut Frame, area: Rect, input: &str) {
    let width = area.width.min(60);
    let popup = popup_area(area, width, 5);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" Edit description ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let display = format!("{input}\u{258e}");
    let prompt = Paragraph::new(Line::from(Span::raw(display))).wrap(Wrap { trim: false });
    frame.render_widget(prompt, inner);
}

/// Render selection highlight by flipping selected cells to REVERSED style.
fn render_selection(frame: &mut Frame, pane: Rect, sel: &Selection) {
    // Normalize so start is before end
    let (start, end) =
        if sel.start.1 < sel.end.1 || (sel.start.1 == sel.end.1 && sel.start.0 <= sel.end.0) {
            (sel.start, sel.end)
        } else {
            (sel.end, sel.start)
        };

    let (start_col, start_row) = start;
    let (end_col, end_row) = end;

    let buf = frame.buffer_mut();

    for row in start_row..=end_row {
        let from = if row == start_row { start_col } else { 0 };
        let to = if row == end_row {
            end_col
        } else {
            pane.width.saturating_sub(1)
        };

        for col in from..=to {
            let x = pane.x + col;
            let y = pane.y + row;
            if let Some(cell) = buf.cell_mut(Position::new(x, y)) {
                let style = cell.style().add_modifier(Modifier::REVERSED);
                cell.set_style(style);
            }
        }
    }
}
