mod input;
mod keys;
mod render;

use std::collections::HashMap;
use std::io;
use std::time::Duration;

use anyhow::{Context, Result};
use chrono::Utc;
use crossterm::event::{self, Event};
use crossterm::terminal::{
    self, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use crate::agent::{generate_id, Agent, AgentState};
use crate::config::{resolve_path, FleetConfig};
use crate::state::{with_state, FleetState};
use crate::tmux;

use input::{DashboardAction, InputMode, PromptEdit};

/// Run the interactive dashboard.
pub fn run(config: &FleetConfig) -> Result<()> {
    tmux::require_tmux()?;

    let dashboard_session = tmux::current_session()?;
    tmux::setup_return_key(&config.tmux.return_key, &dashboard_session)?;

    install_panic_hook();

    let mut terminal = setup_terminal()?;

    let result = main_loop(&mut terminal, config);

    restore_terminal(&mut terminal)?;

    result
}

/// Install a panic hook that restores the terminal before printing the panic message.
/// Without this, a panic leaves the terminal in raw mode + alternate screen.
fn install_panic_hook() {
    let original = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = terminal::disable_raw_mode();
        let _ = io::stdout().execute(LeaveAlternateScreen);
        original(info);
    }));
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
    let mut mode = InputMode::Normal;
    let mut killed_at: HashMap<String, std::time::Instant> = HashMap::new();
    let kill_linger = Duration::from_secs(3);

    // Pre-sort folders for picker
    let mut sorted_folders: Vec<(String, String)> = config.folders.iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    sorted_folders.sort_by(|a, b| a.0.cmp(&b.0));

    loop {
        // Expire killed agents that have lingered long enough
        let expired: Vec<String> = killed_at
            .iter()
            .filter(|(_, t)| t.elapsed() > kill_linger)
            .map(|(id, _)| id.clone())
            .collect();
        if !expired.is_empty() {
            let _ = with_state(config, |state| {
                for id in &expired {
                    state.agents.remove(id);
                }
            });
            for id in &expired {
                killed_at.remove(id);
            }
        }

        let state = FleetState::load(config)?;
        let agent_list = build_agent_list(config, &state);
        let stale_ids = detect_stale(&state);
        let killed_ids: Vec<String> = killed_at.keys().cloned().collect();
        let key_assignments = keys::assign_keys(&agent_list);

        let key_map: HashMap<char, String> = key_assignments
            .iter()
            .map(|(id, k)| (*k, id.clone()))
            .collect();

        let agent_refs: HashMap<String, &Agent> = state
            .agents
            .iter()
            .map(|(id, a)| (id.clone(), a))
            .collect();

        // Build overlay from current mode
        let overlay = match &mode {
            InputMode::Normal => render::Overlay::None,
            InputMode::WaitingKill => render::Overlay::PendingKill,
            InputMode::PickingFolder { .. } => render::Overlay::FolderPicker {
                folders: &sorted_folders,
            },
            InputMode::TypingPrompt { folder_name, input, .. } => render::Overlay::PromptInput {
                folder_name,
                input,
            },
        };

        terminal.draw(|frame| {
            render::render(frame, config, &agent_refs, &key_assignments, &stale_ids, &killed_ids, &overlay);
        })?;

        if event::poll(refresh).context("Failed to poll for events")? {
            if let Event::Key(key_event) = event::read().context("Failed to read event")? {
                match input::handle_input(key_event, &key_map, &mode) {
                    DashboardAction::Quit => break,

                    DashboardAction::Attach(agent_id) => {
                        mode = InputMode::Normal;
                        if let Some(agent) = state.agents.get(&agent_id) {
                            if tmux::session_exists(&agent.tmux_session) {
                                tmux::switch_to(&agent.tmux_session)?;
                            }
                        }
                    }

                    DashboardAction::SpawnInline => {
                        if sorted_folders.len() == 1 {
                            // Skip picker, go straight to prompt
                            let (name, path) = &sorted_folders[0];
                            mode = InputMode::TypingPrompt {
                                folder_name: name.clone(),
                                folder_path: path.clone(),
                                input: String::new(),
                            };
                        } else if sorted_folders.is_empty() {
                            // No folders configured
                            mode = InputMode::Normal;
                        } else {
                            mode = InputMode::PickingFolder {
                                folder_count: sorted_folders.len(),
                            };
                        }
                    }

                    DashboardAction::SpawnEditor => {
                        mode = InputMode::Normal;
                        suspend_tui(terminal, || {
                            if let Err(e) = crate::spawn::spawn_agent(None, None, true) {
                                eprintln!("Error: {e}");
                                std::thread::sleep(Duration::from_secs(1));
                            }
                        })?;
                    }

                    DashboardAction::FolderPicked(idx) => {
                        if let Some((name, path)) = sorted_folders.get(idx) {
                            mode = InputMode::TypingPrompt {
                                folder_name: name.clone(),
                                folder_path: path.clone(),
                                input: String::new(),
                            };
                        } else {
                            mode = InputMode::Normal;
                        }
                    }

                    DashboardAction::PromptInput(edit) => {
                        if let InputMode::TypingPrompt { ref mut input, .. } = mode {
                            match edit {
                                PromptEdit::Char(c) => input.push(c),
                                PromptEdit::Backspace => { input.pop(); }
                            }
                        }
                    }

                    DashboardAction::PromptSubmitted => {
                        if let InputMode::TypingPrompt { folder_name, folder_path, input } = &mode {
                            let prompt = input.trim().to_string();
                            if !prompt.is_empty() {
                                let _ = spawn_inline(config, folder_name, folder_path, &prompt);
                            }
                        }
                        mode = InputMode::Normal;
                    }

                    DashboardAction::PendingKill => {
                        mode = InputMode::WaitingKill;
                    }

                    DashboardAction::KillAgent(agent_id) => {
                        mode = InputMode::Normal;
                        // Kill tmux session but keep agent in state briefly to show "killed"
                        if let Some(agent) = state.agents.get(&agent_id) {
                            if tmux::session_exists(&agent.tmux_session) {
                                let _ = tmux::kill_session(&agent.tmux_session);
                            }
                        }
                        killed_at.insert(agent_id, std::time::Instant::now());
                    }

                    DashboardAction::Cancel => {
                        mode = InputMode::Normal;
                    }

                    DashboardAction::Refresh => {}
                }
            }
        }
    }

    Ok(())
}

/// Spawn an agent directly from the dashboard (no TUI suspend needed).
fn spawn_inline(config: &FleetConfig, folder_name: &str, folder_path: &str, prompt: &str) -> Result<()> {
    let cwd = resolve_path(folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let id = generate_id();
    let session = tmux::session_name(&config.tmux.session_prefix, &id);
    let now = Utc::now();

    let agent = Agent {
        id: id.clone(),
        description: prompt.to_string(),
        folder: folder_name.to_string(),
        cwd: cwd_str.clone(),
        tmux_session: session.clone(),
        initial_prompt: prompt.to_string(),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
    };

    with_state(config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    tmux::create_session(&session, &cwd_str, prompt, &id)?;

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
fn build_agent_list<'a>(
    _config: &FleetConfig,
    state: &'a FleetState,
) -> Vec<(String, &'a Agent)> {
    let mut list: Vec<(String, &Agent)> = state
        .agents
        .iter()
        .map(|(id, agent)| (id.clone(), agent))
        .collect();

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
                AgentState::Working | AgentState::Input
            ) && !tmux::session_exists(&agent.tmux_session)
        })
        .map(|(id, _)| id.clone())
        .collect()
}
