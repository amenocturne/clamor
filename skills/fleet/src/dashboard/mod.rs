mod input;
mod keys;
mod render;

use std::collections::HashMap;
use std::io;
use std::time::Duration;

use anyhow::{Context, Result};
use crossterm::event::{self, Event};
use crossterm::terminal::{
    self, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use crate::config::FleetConfig;
use crate::state::FleetState;
use crate::tmux;

use input::DashboardAction;

/// Run the interactive dashboard.
pub fn run(config: &FleetConfig) -> Result<()> {
    tmux::require_tmux()?;

    let dashboard_session = tmux::current_session()?;
    tmux::setup_return_key(&config.tmux.return_key, &dashboard_session)?;

    let mut terminal = setup_terminal()?;

    let result = main_loop(&mut terminal, config);

    restore_terminal(&mut terminal)?;

    result
}

fn setup_terminal() -> Result<Terminal<CrosstermBackend<io::Stdout>>> {
    terminal::enable_raw_mode().context("Failed to enable raw mode")?;
    io::stdout()
        .execute(EnterAlternateScreen)
        .context("Failed to enter alternate screen")?;

    let backend = CrosstermBackend::new(io::stdout());
    Terminal::new(backend).context("Failed to create terminal")
}

fn restore_terminal(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>) -> Result<()> {
    terminal::disable_raw_mode().context("Failed to disable raw mode")?;
    terminal
        .backend_mut()
        .execute(LeaveAlternateScreen)
        .context("Failed to leave alternate screen")?;
    terminal.show_cursor().context("Failed to show cursor")?;
    Ok(())
}

fn main_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    config: &FleetConfig,
) -> Result<()> {
    let refresh = Duration::from_secs_f64(config.dashboard.refresh_interval);

    loop {
        // Load current state
        let state = FleetState::load(config)?;

        // Build agent list sorted by folder then start time (stable display order)
        let agent_list = build_agent_list(config, &state);

        // Detect stale agents
        let stale_ids = detect_stale(&state);

        // Assign jump keys
        let key_assignments = keys::assign_keys(&agent_list);

        // Build key_map: char -> agent_id for input handling
        let key_map: HashMap<char, String> = key_assignments
            .iter()
            .map(|(id, k)| (*k, id.clone()))
            .collect();

        // Build agent refs for rendering: id -> &Agent
        let agent_refs: HashMap<String, &crate::agent::Agent> = state
            .agents
            .iter()
            .map(|(id, a)| (id.clone(), a))
            .collect();

        // Render
        terminal.draw(|frame| {
            render::render(frame, config, &agent_refs, &key_assignments, &stale_ids);
        })?;

        // Poll for input with timeout
        if event::poll(refresh).context("Failed to poll for events")? {
            if let Event::Key(key_event) = event::read().context("Failed to read event")? {
                match input::handle_input(key_event, &key_map) {
                    DashboardAction::Quit => break,

                    DashboardAction::Attach(agent_id) => {
                        if let Some(agent) = state.agents.get(&agent_id) {
                            if tmux::session_exists(&agent.tmux_session) {
                                tmux::switch_to(&agent.tmux_session)?;
                                // User will return via the return key binding;
                                // loop continues and re-renders on next iteration
                            }
                        }
                    }

                    DashboardAction::SpawnNew => {
                        suspend_tui(terminal, || {
                            if let Err(e) = crate::spawn::spawn_agent(None, None) {
                                eprintln!("Error: {e}");
                                std::thread::sleep(Duration::from_secs(1));
                            }
                        })?;
                    }

                    DashboardAction::EditAgent => {
                        suspend_tui(terminal, || {
                            print!("Agent ID: ");
                            let _ = io::Write::flush(&mut io::stdout());
                            let mut buf = String::new();
                            if io::stdin().read_line(&mut buf).is_ok() {
                                let id = buf.trim();
                                if !id.is_empty() {
                                    if let Err(e) = crate::spawn::edit_agent(id, None) {
                                        eprintln!("Error: {e}");
                                        std::thread::sleep(Duration::from_secs(1));
                                    }
                                }
                            }
                        })?;
                    }

                    DashboardAction::KillAgent => {
                        suspend_tui(terminal, || {
                            print!("Kill agent ID: ");
                            let _ = io::Write::flush(&mut io::stdout());
                            let mut buf = String::new();
                            if io::stdin().read_line(&mut buf).is_ok() {
                                let id = buf.trim();
                                if !id.is_empty() {
                                    if let Err(e) = crate::spawn::kill_agent(id) {
                                        eprintln!("Error: {e}");
                                        std::thread::sleep(Duration::from_secs(1));
                                    }
                                }
                            }
                        })?;
                    }

                    DashboardAction::Refresh => {}
                }
            }
        }
    }

    Ok(())
}

/// Temporarily leave the TUI, run a closure, then re-enter.
fn suspend_tui<F>(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, f: F) -> Result<()>
where
    F: FnOnce(),
{
    terminal::disable_raw_mode().context("Failed to disable raw mode for suspend")?;
    terminal
        .backend_mut()
        .execute(LeaveAlternateScreen)
        .context("Failed to leave alternate screen for suspend")?;

    f();

    io::stdout()
        .execute(EnterAlternateScreen)
        .context("Failed to re-enter alternate screen")?;
    terminal::enable_raw_mode().context("Failed to re-enable raw mode")?;
    terminal.clear().context("Failed to clear terminal")?;

    Ok(())
}

/// Build a sorted list of (agent_id, &Agent) for display.
/// Sorted by folder name, then by start time within each folder.
fn build_agent_list<'a>(
    _config: &FleetConfig,
    state: &'a FleetState,
) -> Vec<(String, &'a crate::agent::Agent)> {
    let mut list: Vec<(String, &crate::agent::Agent)> = state
        .agents
        .iter()
        .map(|(id, agent)| (id.clone(), agent))
        .collect();

    // Sort by folder name, then start time
    list.sort_by(|a, b| {
        a.1.folder
            .cmp(&b.1.folder)
            .then_with(|| a.1.started_at.cmp(&b.1.started_at))
    });

    list
}

/// Check for stale agents: working or input but their tmux session no longer exists.
fn detect_stale(state: &FleetState) -> Vec<String> {
    state
        .agents
        .iter()
        .filter(|(_, agent)| {
            matches!(
                agent.state,
                crate::agent::AgentState::Working | crate::agent::AgentState::Input
            ) && !tmux::session_exists(&agent.tmux_session)
        })
        .map(|(id, _)| id.clone())
        .collect()
}
