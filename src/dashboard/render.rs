use std::collections::{HashMap, HashSet};

use chrono::Utc;
use ratatui::layout::Position;
use ratatui::layout::{Constraint, Flex, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, Paragraph, Wrap};
use ratatui::Frame;

use crate::agent::{Agent, AgentState};
use crate::config::{ClamorConfig, ThemeConfig};
use crate::dashboard::shortcuts;
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
    ConfirmEmptySpawn,
    ConfirmKill {
        agent_id: &'a str,
        description: &'a str,
    },
    ConfirmBatchKill {
        count: usize,
    },
    QuitHint,
    PendingEdit,
    EditInput {
        input: &'a str,
    },
    FilterInput {
        query: &'a str,
    },
    FilterActive {
        query: &'a str,
    },
    Help {
        scroll: usize,
        filter: &'a str,
        filtering: bool,
    },
}

/// Return a flat list of agent IDs in the same order they appear on the dashboard.
///
/// The ordering matches `build_groups`: folders sorted alphabetically (config folders
/// first, then any extra folders from agents), agents within each folder sorted by
/// `started_at`.
pub fn ordered_agent_ids(
    config: &ClamorConfig,
    agents: &HashMap<String, &Agent>,
    filter_query: &str,
) -> Vec<String> {
    let mut folder_keys: Vec<&String> = config.folders.keys().collect();
    folder_keys.sort();

    let mut extra_folders: Vec<String> = agents
        .values()
        .map(|a| a.folder.clone())
        .filter(|f| !config.folders.contains_key(f))
        .collect::<std::collections::HashSet<_>>()
        .into_iter()
        .collect();
    extra_folders.sort();

    let all_folder_keys: Vec<String> = folder_keys
        .iter()
        .map(|k| (*k).clone())
        .chain(extra_folders)
        .collect();

    let q = filter_query.to_lowercase();

    let mut ids = Vec::new();
    for folder_key in &all_folder_keys {
        let mut folder_agents: Vec<(&String, &&Agent)> = agents
            .iter()
            .filter(|(_, a)| a.folder == *folder_key)
            .collect();

        if !q.is_empty() {
            folder_agents.retain(|(_, a)| {
                a.title.to_lowercase().contains(&q) || a.folder.to_lowercase().contains(&q)
            });
        }

        if folder_agents.is_empty() {
            continue;
        }

        folder_agents.sort_by_key(|(_, a)| a.started_at);

        for (id, _) in folder_agents {
            ids.push(id.clone());
        }
    }
    ids
}

/// Render the full dashboard frame.
#[allow(clippy::too_many_arguments)]
pub fn render(
    frame: &mut Frame,
    config: &ClamorConfig,
    agents: &HashMap<String, &Agent>,
    killed_ids: &[String],
    overlay: &Overlay,
    selected_index: Option<usize>,
    filter_query: &str,
    selected_agents: &HashSet<String>,
    daemon_connected: bool,
) {
    let area = frame.area();

    // Build display agents grouped by folder
    let groups = build_groups(config, agents, killed_ids, filter_query);

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

    let batch_count = selected_agents.len();

    // Layout: header, separator, body, footer
    let chunks = Layout::vertical([
        Constraint::Length(1), // header
        Constraint::Length(1), // separator
        Constraint::Min(1),    // body
        Constraint::Length(1), // footer
    ])
    .split(area);

    render_header(frame, chunks[0], total, needs_input, filter_query);

    if !daemon_connected {
        let banner = Paragraph::new(Line::from(Span::styled(
            " DAEMON DISCONNECTED ",
            Style::default()
                .fg(Color::White)
                .bg(Color::Red)
                .add_modifier(Modifier::BOLD),
        )));
        frame.render_widget(banner, chunks[0]);
    }

    let kill_target_id = match overlay {
        Overlay::ConfirmKill { agent_id, .. } => Some(*agent_id),
        _ => None,
    };

    render_separator(frame, chunks[1]);
    render_body(
        frame,
        chunks[2],
        &groups,
        selected_index,
        filter_query,
        selected_agents,
        kill_target_id,
        &config.theme,
    );
    render_footer(frame, chunks[3], overlay, batch_count);

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
        Overlay::ConfirmEmptySpawn => {
            render_confirm_empty_popup(frame, area);
        }
        Overlay::ConfirmKill { description, .. } => {
            render_confirm_kill_popup(frame, area, description);
        }
        Overlay::ConfirmBatchKill { count } => {
            render_batch_kill_popup(frame, area, *count);
        }
        Overlay::QuitHint => {
            render_quit_hint_popup(frame, area);
        }
        Overlay::EditInput { input } => {
            render_edit_popup(frame, area, input);
        }
        Overlay::Help {
            scroll,
            filter,
            filtering,
        } => {
            render_help_popup(frame, area, *scroll, filter, *filtering);
        }
        _ => {}
    }
}

/// Render the terminal view for an agent (title bar + PseudoTerminal).
///
/// `scroll_info` is `Some((offset, total))` when scrolled up, `None` at live view.
/// `has_pending` indicates output is being buffered while the view is frozen.
/// `copy_cursor` is `Some((col, row))` when in copy mode.
pub fn render_terminal(
    frame: &mut Frame,
    screen: &vt100::Screen,
    agent: &Agent,
    selection: &Option<Selection>,
    scroll_info: Option<(usize, usize)>,
    has_pending: bool,
    copy_cursor: Option<(u16, u16)>,
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
    };
    let duration = format_duration(agent.started_at);
    let hint_text = if copy_cursor.is_some() {
        match scroll_info {
            Some((offset, total)) => {
                let pct = if total > 0 {
                    100 - (offset * 100 / total)
                } else {
                    100
                };
                format!("COPY  {}%  v/V:select  y:yank  q:exit", pct)
            }
            None => "COPY  v/V:select  y:yank  q:exit".to_string(),
        }
    } else {
        match scroll_info {
            Some((offset, total)) => {
                let pct = if total > 0 {
                    100 - (offset * 100 / total)
                } else {
                    100
                };
                let frozen = if has_pending { "FROZEN  " } else { "" };
                format!("{}{}%  ^F back  ^J bottom", frozen, pct)
            }
            None => "^F back".to_string(),
        }
    };
    pane::render_title_bar(
        frame,
        chunks[0],
        &pane::TitleBarParams {
            folder: &agent.folder,
            description: &agent.title,
            state: state_str,
            duration: &duration,
            color,
            focused: true,
            hint: Some(&hint_text),
        },
    );

    let content_area = chunks[1];

    // Bottom-anchor: strip trailing empty rows so the prompt sticks to the
    // bottom when Ink's render height fluctuates. Applied in all modes so
    // there's no visual jump when entering/leaving scroll mode.
    let last_row = last_content_row(screen, content_area.height, content_area.width);
    let content_h = (last_row + 2).min(content_area.height);
    let offset = content_area.height - content_h;
    let pane_area = if offset > 0 {
        frame.render_widget(
            Clear,
            Rect {
                x: content_area.x,
                y: content_area.y,
                width: content_area.width,
                height: offset,
            },
        );
        Rect {
            x: content_area.x,
            y: content_area.y + offset,
            width: content_area.width,
            height: content_h,
        }
    } else {
        content_area
    };

    let pseudo_term = tui_term::widget::PseudoTerminal::new(screen);
    frame.render_widget(pseudo_term, pane_area);

    // Overlay selection highlight
    if let Some(sel) = selection {
        render_selection(frame, pane_area, sel);
    }

    // Overlay copy mode cursor
    if let Some((col, row)) = copy_cursor {
        render_copy_cursor(frame, pane_area, col, row);
    }
}

/// Find the last row with visible content in the screen.
fn last_content_row(screen: &vt100::Screen, rows: u16, cols: u16) -> u16 {
    for row in (0..rows).rev() {
        for col in 0..cols {
            if let Some(cell) = screen.cell(row, col) {
                if cell.has_contents() {
                    return row;
                }
            }
        }
    }
    0
}

fn render_header(
    frame: &mut Frame,
    area: Rect,
    total: usize,
    needs_input: usize,
    filter_query: &str,
) {
    let mut spans = vec![
        Span::styled(
            "CLAMOR",
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

    if !filter_query.is_empty() {
        spans.push(Span::raw("  "));
        spans.push(Span::styled(
            format!("filter: {filter_query}"),
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::ITALIC),
        ));
    }

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

fn render_footer(frame: &mut Frame, area: Rect, overlay: &Overlay, batch_count: usize) {
    let footer = match overlay {
        Overlay::PendingKill => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled(
                "Kill: press agent key (Esc to cancel)",
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
        ])),
        Overlay::ConfirmBatchKill { count } => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled(
                format!(
                    "Kill {} agent{}? ",
                    count,
                    if *count != 1 { "s" } else { "" }
                ),
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
            Span::styled("[Enter]", Style::default().fg(Color::Cyan)),
            Span::raw(" yes  "),
            Span::styled("[Esc]", Style::default().fg(Color::Cyan)),
            Span::raw(" cancel"),
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
        Overlay::FilterInput { query } => Paragraph::new(Line::from(vec![
            Span::raw(" filter: "),
            Span::styled(
                format!("{query}\u{258e}"),
                Style::default().fg(Color::White),
            ),
        ])),
        Overlay::FilterActive { query } => Paragraph::new(Line::from(vec![
            Span::raw(" "),
            Span::styled(
                format!("filter: {query}  ",),
                Style::default()
                    .fg(Color::DarkGray)
                    .add_modifier(Modifier::ITALIC),
            ),
            Span::styled("[/]", Style::default().fg(Color::Cyan)),
            Span::raw(" edit  "),
            Span::styled("[Esc]", Style::default().fg(Color::Cyan)),
            Span::raw(" clear"),
        ])),
        _ => {
            let mut spans = vec![Span::raw(" ")];
            if batch_count > 0 {
                spans.push(Span::styled(
                    format!("{} selected  ", batch_count,),
                    Style::default()
                        .fg(Color::Yellow)
                        .add_modifier(Modifier::BOLD),
                ));
            }
            spans.extend([
                Span::styled("[J/K]", Style::default().fg(Color::Cyan)),
                Span::raw(" select  "),
                Span::styled("[v]", Style::default().fg(Color::Cyan)),
                Span::raw(" mark  "),
                Span::styled("[x]", Style::default().fg(Color::Cyan)),
                Span::raw(" kill  "),
                Span::styled("[c]", Style::default().fg(Color::Cyan)),
                Span::raw("reate  "),
                Span::styled("[/]", Style::default().fg(Color::Cyan)),
                Span::raw(" filter  "),
                Span::styled("[?]", Style::default().fg(Color::Cyan)),
                Span::raw(" help"),
            ]);
            Paragraph::new(Line::from(spans))
        }
    };
    frame.render_widget(footer, area);
}

/// A group of agents under a folder heading.
struct AgentGroup<'a> {
    folder_name: String,
    agents: Vec<DisplayAgent<'a>>,
}

fn build_groups<'a>(
    config: &ClamorConfig,
    agents: &HashMap<String, &'a Agent>,
    killed_ids: &[String],
    filter_query: &str,
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

    let q = filter_query.to_lowercase();

    for folder_key in &all_folder_keys {
        let mut folder_agents: Vec<(&String, &&Agent)> = agents
            .iter()
            .filter(|(_, a)| a.folder == *folder_key)
            .collect();

        if !q.is_empty() {
            folder_agents.retain(|(_, a)| {
                a.title.to_lowercase().contains(&q) || a.folder.to_lowercase().contains(&q)
            });
        }

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

#[allow(clippy::too_many_arguments)]
fn render_body(
    frame: &mut Frame,
    area: Rect,
    groups: &[AgentGroup],
    selected_index: Option<usize>,
    filter_query: &str,
    selected_agents: &HashSet<String>,
    kill_target_id: Option<&str>,
    theme: &ThemeConfig,
) {
    if groups.is_empty() && !filter_query.is_empty() {
        let msg = Paragraph::new(Line::from(Span::styled(
            "  No agents match filter",
            Style::default()
                .fg(Color::DarkGray)
                .add_modifier(Modifier::ITALIC),
        )));
        frame.render_widget(msg, area);
        return;
    }

    let mut lines: Vec<Line> = Vec::new();
    let width = area.width as usize;
    let mut agent_idx = 0usize;
    let mut selected_line: Option<usize> = None;

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
            let batch_selected = selected_agents.contains(&da.agent.id);
            let is_kill_target = kill_target_id == Some(da.agent.id.as_str());
            let mut line = render_agent_line(da, width, batch_selected, theme);
            if is_kill_target {
                line = kill_highlight_line(line, theme);
            } else if selected_index == Some(agent_idx) {
                line = highlight_line(line, theme);
                selected_line = Some(lines.len());
            } else if batch_selected {
                line = mark_selected(line, theme);
            }
            lines.push(line);
            agent_idx += 1;
        }
    }

    // Scroll viewport so the selected line stays visible with a 2-line margin
    let viewport_height = area.height as usize;
    let scroll_offset = if let Some(sel_line) = selected_line {
        if viewport_height == 0 || lines.len() <= viewport_height {
            0
        } else {
            let margin = 2usize;
            let min_offset = sel_line.saturating_sub(viewport_height.saturating_sub(1 + margin));
            let max_offset = sel_line.saturating_sub(margin);
            // Clamp: pick min_offset if we need to scroll down, keep current if in range
            // Since we don't persist scroll state, just ensure selected is visible
            min_offset.max(0).min(max_offset)
        }
    } else {
        0
    };

    let body = Paragraph::new(lines).scroll((scroll_offset as u16, 0));
    frame.render_widget(body, area);
}

fn highlight_line(line: Line<'static>, theme: &ThemeConfig) -> Line<'static> {
    let bg = Style::default().bg(theme.highlight.to_ratatui());
    let mut spans = vec![Span::styled(
        "▎",
        Style::default().fg(theme.accent.to_ratatui()),
    )];
    for span in line.spans {
        spans.push(span.patch_style(bg));
    }
    Line::from(spans)
}

fn kill_highlight_line(line: Line<'static>, theme: &ThemeConfig) -> Line<'static> {
    let bg = Style::default().bg(theme.kill_highlight.to_ratatui());
    let mut spans = vec![Span::styled("▎", Style::default().fg(Color::Red))];
    for span in line.spans {
        spans.push(span.patch_style(bg));
    }
    Line::from(spans)
}

fn mark_selected(line: Line<'static>, theme: &ThemeConfig) -> Line<'static> {
    let bg = Style::default().bg(theme.highlight.to_ratatui());
    Line::from(
        line.spans
            .into_iter()
            .map(|span| span.patch_style(bg))
            .collect::<Vec<_>>(),
    )
}

fn render_agent_line(
    da: &DisplayAgent,
    width: usize,
    batch_selected: bool,
    theme: &ThemeConfig,
) -> Line<'static> {
    let select_marker = if batch_selected { "● " } else { "  " };

    let key_str = da
        .key
        .map(|c| format!("{}  ", c))
        .unwrap_or_else(|| "   ".into());

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
                    .fg(theme.status_input.to_ratatui())
                    .add_modifier(Modifier::BOLD),
            ),
            AgentState::Working => (
                "work ",
                Style::default().fg(theme.status_working.to_ratatui()),
            ),
            AgentState::Done => ("done ", Style::default().fg(theme.status_done.to_ratatui())),
        }
    };

    let duration = format_duration(da.agent.started_at);

    // Build tool suffix: "  ToolName 2m" in very dim style
    let tool_suffix = if !da.killed && da.agent.state != AgentState::Done {
        da.agent.last_tool.as_ref().map(|tool| {
            let tool_display = truncate(tool, 20);
            let activity_ago = format_duration(da.agent.last_activity_at);
            format!("  {} {}", tool_display, activity_ago)
        })
    } else {
        None
    };
    let tool_suffix_len = tool_suffix.as_ref().map_or(0, |s| s.len());

    // state_label is 5 or 6 chars — normalize to 6 for "killed"
    let state_display = format!("{:<6}", state_label);

    // Calculate available space for description:
    // marker(2) + key(3) + state(6) + spacing(4) + duration(~8) + padding(2) + tool_suffix
    let overhead = 2 + key_str.len() + 6 + 4 + duration.len() + 2 + tool_suffix_len;
    let desc_width = width.saturating_sub(overhead);
    let description = truncate(&da.agent.title, desc_width);

    let padded_desc = format!("{:<width$}", description, width = desc_width);

    let key_style = Style::default()
        .fg(theme.accent.to_ratatui())
        .add_modifier(Modifier::BOLD);

    let dimmed = da.killed;

    // Use agent color for description text (unless dimmed)
    let desc_style = if dimmed {
        Style::default().fg(theme.dimmed.to_ratatui())
    } else {
        let color = pane::agent_color(da.agent.color_index);
        Style::default().fg(color)
    };

    let duration_style = Style::default().fg(theme.dimmed.to_ratatui());

    let select_style = if batch_selected {
        Style::default().fg(theme.batch_marker.to_ratatui())
    } else {
        Style::default()
    };

    let mut spans = vec![
        Span::styled(select_marker.to_string(), select_style),
        Span::styled(key_str, key_style),
        Span::styled(state_display, state_style),
        Span::raw("  "),
        Span::styled(padded_desc, desc_style),
        Span::raw("  "),
        Span::styled(duration, duration_style),
    ];

    if let Some(suffix) = tool_suffix {
        spans.push(Span::styled(
            suffix,
            Style::default().fg(Color::Rgb(60, 60, 60)),
        ));
    }

    Line::from(spans)
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
    let height = (area.height * 3 / 5).clamp(10, 30);
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

    let desc_width = inner.width as usize;
    let wrapped_desc: Vec<String> = if desc_width == 0 {
        vec![desc_display]
    } else {
        let chars: Vec<char> = desc_display.chars().collect();
        if chars.is_empty() {
            vec![String::new()]
        } else {
            chars
                .chunks(desc_width)
                .map(|chunk| chunk.iter().collect())
                .collect()
        }
    };

    // 5 fixed lines: title + blank + "Description:" label + blank before hint + hint
    let desc_area_height = (inner.height as usize).saturating_sub(5);
    let visible_desc: &[String] = if wrapped_desc.len() > desc_area_height && desc_area_height > 0 {
        &wrapped_desc[wrapped_desc.len() - desc_area_height..]
    } else {
        &wrapped_desc
    };

    let mut lines = vec![
        Line::from(vec![
            Span::styled("Title: ", title_label_style),
            Span::raw(title_display),
        ]),
        Line::from(""),
        Line::from(Span::styled("Description:", desc_label_style)),
    ];
    for line in visible_desc {
        lines.push(Line::from(Span::raw(line.clone())));
    }
    lines.push(Line::from(""));
    lines.push(Line::from(Span::styled(
        "Tab switch \u{00b7} empty = interactive session",
        Style::default().fg(Color::DarkGray),
    )));

    let paragraph = Paragraph::new(lines);
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

fn render_confirm_kill_popup(frame: &mut Frame, area: Rect, description: &str) {
    let popup = popup_area(area, 45, 7);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Red))
        .title(" Kill agent? ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let text = vec![
        Line::from(format!(" {}", description)),
        Line::from(""),
        Line::from(vec![
            Span::raw(" "),
            Span::styled("[Enter]", Style::default().fg(Color::Cyan)),
            Span::raw(" yes  "),
            Span::styled("[Esc]", Style::default().fg(Color::Cyan)),
            Span::raw(" cancel"),
        ]),
    ];
    frame.render_widget(Paragraph::new(text), inner);
}

fn render_quit_hint_popup(frame: &mut Frame, area: Rect) {
    let popup = popup_area(area, 30, 5);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray));

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let text = vec![
        Line::from(""),
        Line::from(vec![
            Span::raw(" Press "),
            Span::styled(
                "q",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::raw(" to quit"),
        ]),
    ];
    frame.render_widget(Paragraph::new(text), inner);
}

fn render_batch_kill_popup(frame: &mut Frame, area: Rect, count: usize) {
    let width = area.width.min(42);
    let popup = popup_area(area, width, 5);
    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Red))
        .title(" Batch kill ");

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let text = vec![
        Line::from(format!(
            " Kill {} agent{}?",
            count,
            if count != 1 { "s" } else { "" }
        )),
        Line::from(""),
        Line::from(vec![
            Span::raw(" "),
            Span::styled("[Enter]", Style::default().fg(Color::Cyan)),
            Span::raw(" yes    "),
            Span::styled("[Esc]", Style::default().fg(Color::Cyan)),
            Span::raw(" cancel"),
        ]),
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

fn render_help_popup(frame: &mut Frame, area: Rect, scroll: usize, filter: &str, filtering: bool) {
    let sections = shortcuts::sections();

    let key_width = sections
        .iter()
        .flat_map(|(_, items)| items.iter())
        .map(|s| s.keys.len())
        .max()
        .unwrap_or(10);

    let filter_lower = filter.to_ascii_lowercase();

    let mut lines: Vec<Line> = Vec::new();
    for (title, items) in sections.iter() {
        let filtered: Vec<_> = items
            .iter()
            .filter(|s| {
                filter.is_empty()
                    || s.keys.to_ascii_lowercase().contains(&filter_lower)
                    || s.description.to_ascii_lowercase().contains(&filter_lower)
            })
            .collect();
        if filtered.is_empty() {
            continue;
        }
        if !lines.is_empty() {
            lines.push(Line::raw(""));
        }
        lines.push(Line::from(Span::styled(
            format!(" {title}"),
            Style::default().add_modifier(Modifier::BOLD),
        )));
        lines.push(Line::from(Span::styled(
            format!(" {}", "\u{2500}".repeat(key_width + 20)),
            Style::default().fg(Color::DarkGray),
        )));
        for s in &filtered {
            let padding = " ".repeat(key_width.saturating_sub(s.keys.len()));
            lines.push(Line::from(vec![
                Span::styled(format!(" {}", s.keys), Style::default().fg(Color::Cyan)),
                Span::raw(format!("{padding}  {}", s.description)),
            ]));
        }
    }

    // Width from actual content
    let max_line_width = sections
        .iter()
        .flat_map(|(_, items)| items.iter())
        .map(|s| 1 + key_width + 2 + s.description.len())
        .max()
        .unwrap_or(40);
    let width = (max_line_width + 4).min(area.width as usize) as u16;

    // Cap height at 70% of terminal, leave room for filter bar
    let max_height = (area.height * 7 / 10).max(10);
    let content_height = lines.len() as u16;
    let needs_scroll = content_height + 3 > max_height; // +3 for border + footer
    let popup_height = if needs_scroll {
        max_height
    } else {
        (content_height + 3).min(area.height) // +3: border top/bottom + footer
    };

    let popup = popup_area(area, width, popup_height);
    frame.render_widget(Clear, popup);

    let title = if filtering {
        format!(" Help  /{}_ ", filter)
    } else if !filter.is_empty() {
        format!(" Help  /{} ", filter)
    } else {
        " Help ".to_string()
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(title);

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    // Scrollable content area: reserve 1 row for footer hints
    let content_area = Rect {
        height: inner.height.saturating_sub(1),
        ..inner
    };
    let footer_area = Rect {
        y: inner.y + content_area.height,
        height: 1,
        ..inner
    };

    let para = Paragraph::new(lines).scroll((scroll as u16, 0));
    frame.render_widget(para, content_area);

    // Footer: hints
    let hint = if filtering {
        "type to filter  Enter/Esc: done"
    } else if needs_scroll {
        "j/k: scroll  /: filter  q: close"
    } else {
        "/: filter  q: close"
    };
    let footer = Line::from(Span::styled(
        format!(" {hint}"),
        Style::default().fg(Color::DarkGray),
    ));
    frame.render_widget(Paragraph::new(footer), footer_area);
}

/// Render copy mode cursor as an inverted block at the given position.
fn render_copy_cursor(frame: &mut Frame, pane: Rect, col: u16, row: u16) {
    let x = pane.x + col;
    let y = pane.y + row;
    if x < pane.x + pane.width && y < pane.y + pane.height {
        let buf = frame.buffer_mut();
        if let Some(cell) = buf.cell_mut(Position::new(x, y)) {
            let style = cell.style().add_modifier(Modifier::REVERSED);
            cell.set_style(style);
        }
    }
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
