use std::collections::HashMap;

use chrono::Utc;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::Paragraph;
use ratatui::Frame;

use crate::agent::{Agent, AgentState};
use crate::config::FleetConfig;

/// An agent prepared for display, with its assigned jump key and stale status.
pub struct DisplayAgent<'a> {
    pub agent: &'a Agent,
    pub key: Option<char>,
    pub stale: bool,
}

/// Render the full dashboard frame.
pub fn render(
    frame: &mut Frame,
    config: &FleetConfig,
    agents: &HashMap<String, &Agent>,
    key_assignments: &[(String, char)],
    stale_ids: &[String],
) {
    let area = frame.area();

    // Build key lookup: agent_id -> char
    let id_to_key: HashMap<&str, char> = key_assignments
        .iter()
        .map(|(id, k)| (id.as_str(), *k))
        .collect();

    // Build display agents grouped by folder
    let groups = build_groups(config, agents, &id_to_key, stale_ids);

    // Count stats
    let total = agents.len();
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
    render_footer(frame, chunks[3]);
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
    let line = "─".repeat(area.width as usize);
    let sep = Paragraph::new(Line::from(Span::styled(
        line,
        Style::default().fg(Color::DarkGray),
    )));
    frame.render_widget(sep, area);
}

fn render_footer(frame: &mut Frame, area: Rect) {
    let footer = Paragraph::new(Line::from(vec![
        Span::raw(" "),
        Span::styled("[key]", Style::default().fg(Color::Cyan)),
        Span::raw(" attach  "),
        Span::styled("[n]", Style::default().fg(Color::Cyan)),
        Span::raw("ew  "),
        Span::styled("[e]", Style::default().fg(Color::Cyan)),
        Span::raw("dit  "),
        Span::styled("[K]", Style::default().fg(Color::Cyan)),
        Span::raw("ill  "),
        Span::styled("[q]", Style::default().fg(Color::Cyan)),
        Span::raw("uit"),
    ]));
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
    id_to_key: &HashMap<&str, char>,
    stale_ids: &[String],
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
        // Get agents for this folder, sorted by start time
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
                key: id_to_key.get(id.as_str()).copied(),
                stale: stale_ids.contains(id),
            })
            .collect();

        let folder_name = config
            .folders
            .get(folder_key)
            .map(|f| f.name.clone())
            .unwrap_or_else(|| folder_key.clone());

        groups.push(AgentGroup {
            folder_name,
            agents: display_agents,
        });
    }

    groups
}

fn render_body(frame: &mut Frame, area: Rect, groups: &[AgentGroup]) {
    let mut lines: Vec<Line> = Vec::new();

    for (i, group) in groups.iter().enumerate() {
        if i > 0 {
            lines.push(Line::from(""));
        }

        // Folder header
        lines.push(Line::from(Span::styled(
            format!(" {}", group.folder_name),
            Style::default().add_modifier(Modifier::BOLD),
        )));

        let width = area.width as usize;

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

    let (state_label, state_style) = match da.agent.state {
        AgentState::Input => (
            "input",
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        ),
        AgentState::Working => ("work ", Style::default().fg(Color::Green)),
        AgentState::Done => ("done ", Style::default().fg(Color::DarkGray)),
    };

    let duration = format_duration(da.agent.started_at);
    let stale_suffix = if da.stale { " ?" } else { "" };
    let duration_with_stale = format!("{}{}", duration, stale_suffix);

    // Calculate available space for description:
    // key(5) + state(5) + spacing(4) + duration(~8) + padding(2)
    let overhead = key_str.len() + 5 + 4 + duration_with_stale.len() + 2;
    let desc_width = width.saturating_sub(overhead);
    let description = truncate(&da.agent.description, desc_width);

    // Pad description to fill available width
    let padded_desc = format!("{:<width$}", description, width = desc_width);

    let key_style = Style::default()
        .fg(Color::Cyan)
        .add_modifier(Modifier::BOLD);

    let desc_style = match da.agent.state {
        AgentState::Done => Style::default().fg(Color::DarkGray),
        _ => Style::default(),
    };

    let duration_style = match da.agent.state {
        AgentState::Done => Style::default().fg(Color::DarkGray),
        _ => Style::default().fg(Color::DarkGray),
    };

    Line::from(vec![
        Span::styled(key_str, key_style),
        Span::styled(state_label.to_string(), state_style),
        Span::raw("  "),
        Span::styled(padded_desc, desc_style),
        Span::raw("  "),
        Span::styled(duration_with_stale, duration_style),
    ])
}

fn format_duration(started_at: chrono::DateTime<Utc>) -> String {
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
