mod input;
pub(crate) mod keys;
mod render;

use std::collections::HashMap;
use std::io;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use chrono::Utc;
use crossterm::event::{self, Event, KeyCode, KeyModifiers};
use crossterm::terminal::{
    self, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::crossterm::event::{
    EnableBracketedPaste, DisableBracketedPaste,
    EnableMouseCapture, DisableMouseCapture,
};
use ratatui::crossterm::execute;
use ratatui::Terminal;

use crate::agent::{generate_id, next_color_index, Agent, AgentState};
use crate::client::DaemonClient;
use crate::config::{resolve_path, FleetConfig};
use crate::daemon;
use crate::pane::{self, PaneView};
use crate::protocol::DaemonMessage;
use crate::state::{with_state, FleetState};

use input::{DashboardAction, InputMode, PromptEdit};

enum AppMode {
    Dashboard,
    Terminal { agent_id: String },
}

fn ensure_daemon() -> Result<()> {
    if !daemon::is_daemon_running() {
        daemon::start_daemon_background()?;
    }
    Ok(())
}

/// Run the interactive dashboard.
pub fn run(config: &FleetConfig) -> Result<()> {
    ensure_daemon()?;
    let mut client = DaemonClient::connect()?;
    client.set_nonblocking(true)?;

    install_panic_hook();
    let mut terminal = setup_terminal()?;
    execute!(io::stdout(), EnableBracketedPaste, EnableMouseCapture)?;

    let result = main_loop(&mut terminal, config, &mut client);

    execute!(io::stdout(), DisableBracketedPaste, DisableMouseCapture)?;
    restore_terminal(&mut terminal)?;

    result
}

/// Install a panic hook that restores the terminal before printing the panic message.
fn install_panic_hook() {
    let original = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = terminal::disable_raw_mode();
        let _ = execute!(io::stdout(), DisableMouseCapture, DisableBracketedPaste);
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
    client: &mut DaemonClient,
) -> Result<()> {
    let mut mode = AppMode::Dashboard;
    let mut input_mode = InputMode::Normal;
    let mut killed_at: HashMap<String, Instant> = HashMap::new();
    let kill_linger = Duration::from_secs(3);
    let mut pane_views: HashMap<String, PaneView> = HashMap::new();

    // Pre-sort folders for picker
    let mut sorted_folders: Vec<(String, String)> = config.folders.iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    sorted_folders.sort_by(|a, b| a.0.cmp(&b.0));

    let min_frame = Duration::from_millis(8);

    loop {
        let frame_start = Instant::now();

        // Drain daemon messages
        loop {
            match client.try_recv() {
                Ok(Some(msg)) => match msg {
                    DaemonMessage::Output { id, data } => {
                        if let Some(pv) = pane_views.get_mut(&id) {
                            pv.process_output(&data);
                        }
                    }
                    DaemonMessage::Exited { id } => {
                        // Mark agent as done in state
                        let _ = with_state(config, |state| {
                            if let Some(agent) = state.agents.get_mut(&id) {
                                agent.state = AgentState::Done;
                            }
                        });
                    }
                    DaemonMessage::CatchUp { id, data } => {
                        if let Some(pv) = pane_views.get_mut(&id) {
                            pv.process_output(&data);
                        }
                    }
                    _ => {}
                },
                Ok(None) => break,
                Err(_) => break,
            }
        }

        match mode {
            AppMode::Dashboard => {
                let action = dashboard_iteration(
                    terminal, config, client, &mut input_mode,
                    &mut killed_at, &kill_linger, &sorted_folders,
                    &mut pane_views,
                )?;

                match action {
                    LoopAction::Continue | LoopAction::SwitchToDashboard => {}
                    LoopAction::Quit => break,
                    LoopAction::SwitchToTerminal(agent_id) => {
                        // Create PaneView if not exists, subscribe, resize
                        let (term_cols, term_rows) = crossterm::terminal::size()?;
                        let content_rows = term_rows.saturating_sub(1);
                        let pv = pane_views.entry(agent_id.clone())
                            .or_insert_with(|| PaneView::new(content_rows, term_cols));

                        // Set socket to blocking briefly for subscribe handshake
                        client.set_nonblocking(false)?;
                        match client.subscribe(&agent_id) {
                            Ok(catch_up) => {
                                if !catch_up.is_empty() {
                                    pv.process_output(&catch_up);
                                }
                            }
                            Err(_) => {
                                client.set_nonblocking(true)?;
                                continue;
                            }
                        }

                        let _ = client.resize(&agent_id, content_rows, term_cols);
                        client.set_nonblocking(true)?;

                        mode = AppMode::Terminal { agent_id };
                    }
                }
            }

            AppMode::Terminal { ref agent_id } => {
                let agent_id_clone = agent_id.clone();
                let action = terminal_iteration(
                    terminal, config, client,
                    &agent_id_clone, &mut pane_views,
                )?;

                match action {
                    LoopAction::Continue => {}
                    LoopAction::Quit => break,
                    LoopAction::SwitchToDashboard => {
                        mode = AppMode::Dashboard;
                        input_mode = InputMode::Normal;
                    }
                    LoopAction::SwitchToTerminal(_) => unreachable!(),
                }
            }
        }

        // Frame rate cap
        let elapsed = frame_start.elapsed();
        if elapsed < min_frame {
            std::thread::sleep(min_frame - elapsed);
        }
    }

    Ok(())
}

enum LoopAction {
    Continue,
    Quit,
    SwitchToTerminal(String),
    SwitchToDashboard,
}

fn dashboard_iteration(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    config: &FleetConfig,
    client: &mut DaemonClient,
    input_mode: &mut InputMode,
    killed_at: &mut HashMap<String, Instant>,
    kill_linger: &Duration,
    sorted_folders: &[(String, String)],
    _pane_views: &mut HashMap<String, PaneView>,
) -> Result<LoopAction> {
    // Expire killed agents that have lingered long enough
    let expired: Vec<String> = killed_at
        .iter()
        .filter(|(_, t)| t.elapsed() > *kill_linger)
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
    let killed_ids: Vec<String> = killed_at.keys().cloned().collect();

    // Build key map from persistent Agent.key fields
    let mut key_map: HashMap<char, String> = HashMap::new();
    for (id, agent) in &state.agents {
        if let Some(k) = agent.key {
            key_map.insert(k, id.clone());
        }
    }

    let agent_refs: HashMap<String, &Agent> = state
        .agents
        .iter()
        .map(|(id, a)| (id.clone(), a))
        .collect();

    // Build overlay from current mode
    let overlay = match input_mode {
        InputMode::Normal => render::Overlay::None,
        InputMode::WaitingKill => render::Overlay::PendingKill,
        InputMode::PickingFolder { .. } => render::Overlay::FolderPicker {
            folders: sorted_folders,
        },
        InputMode::TypingPrompt { folder_name, input, .. } => render::Overlay::PromptInput {
            folder_name,
            input,
        },
        InputMode::TypingAdopt { input } => render::Overlay::AdoptInput {
            input,
        },
    };

    terminal.draw(|frame| {
        render::render(frame, config, &agent_refs, &killed_ids, &overlay);
    })?;

    let poll_duration = Duration::from_millis(50);
    if event::poll(poll_duration).context("Failed to poll for events")? {
        if let Event::Key(key_event) = event::read().context("Failed to read event")? {
            match input::handle_input(key_event, &key_map, input_mode) {
                DashboardAction::Quit => return Ok(LoopAction::Quit),

                DashboardAction::Attach(ref agent_id) => {
                    *input_mode = InputMode::Normal;
                    if state.agents.contains_key(agent_id) {
                        return Ok(LoopAction::SwitchToTerminal(agent_id.clone()));
                    }
                }

                DashboardAction::SpawnInline => {
                    if sorted_folders.len() == 1 {
                        let (name, path) = &sorted_folders[0];
                        *input_mode = InputMode::TypingPrompt {
                            folder_name: name.clone(),
                            folder_path: path.clone(),
                            input: String::new(),
                        };
                    } else if sorted_folders.is_empty() {
                        *input_mode = InputMode::Normal;
                    } else {
                        *input_mode = InputMode::PickingFolder {
                            folder_count: sorted_folders.len(),
                        };
                    }
                }

                DashboardAction::SpawnEditor => {
                    *input_mode = InputMode::Normal;
                    suspend_tui(terminal, || {
                        if let Err(e) = crate::spawn::spawn_agent(None, None, true) {
                            eprintln!("Error: {e}");
                            std::thread::sleep(Duration::from_secs(1));
                        }
                    })?;
                }

                DashboardAction::FolderPicked(idx) => {
                    if let Some((name, path)) = sorted_folders.get(idx) {
                        *input_mode = InputMode::TypingPrompt {
                            folder_name: name.clone(),
                            folder_path: path.clone(),
                            input: String::new(),
                        };
                    } else {
                        *input_mode = InputMode::Normal;
                    }
                }

                DashboardAction::PromptInput(edit) => {
                    if let InputMode::TypingPrompt { ref mut input, .. } = input_mode {
                        match edit {
                            PromptEdit::Char(c) => input.push(c),
                            PromptEdit::Backspace => { input.pop(); }
                        }
                    }
                }

                DashboardAction::PromptSubmitted => {
                    if let InputMode::TypingPrompt { folder_name, folder_path, input } = input_mode {
                        let prompt = input.trim().to_string();
                        if !prompt.is_empty() {
                            let _ = spawn_inline(config, client, folder_name, folder_path, &prompt, &state);
                        }
                    }
                    *input_mode = InputMode::Normal;
                }

                DashboardAction::PendingKill => {
                    *input_mode = InputMode::WaitingKill;
                }

                DashboardAction::KillAgent(agent_id) => {
                    *input_mode = InputMode::Normal;
                    let _ = client.kill_agent(&agent_id);
                    killed_at.insert(agent_id, Instant::now());
                }

                DashboardAction::AdoptStart => {
                    *input_mode = InputMode::TypingAdopt { input: String::new() };
                }

                DashboardAction::AdoptInput(edit) => {
                    if let InputMode::TypingAdopt { ref mut input } = input_mode {
                        match edit {
                            PromptEdit::Char(c) => input.push(c),
                            PromptEdit::Backspace => { input.pop(); }
                        }
                    }
                }

                DashboardAction::AdoptSubmitted => {
                    if let InputMode::TypingAdopt { input } = input_mode {
                        let session_id = input.trim().to_string();
                        if !session_id.is_empty() {
                            // Adopt needs a folder — use first folder if only one, else skip
                            if sorted_folders.len() == 1 {
                                let (folder_name, folder_path) = &sorted_folders[0];
                                let _ = adopt_inline(config, client, &session_id, folder_name, folder_path, &state);
                            }
                            // If multiple folders, a more complex flow would be needed;
                            // for now just adopt with first folder or show error
                            else if !sorted_folders.is_empty() {
                                let (folder_name, folder_path) = &sorted_folders[0];
                                let _ = adopt_inline(config, client, &session_id, folder_name, folder_path, &state);
                            }
                        }
                    }
                    *input_mode = InputMode::Normal;
                }

                DashboardAction::Cancel => {
                    *input_mode = InputMode::Normal;
                }

                DashboardAction::Refresh => {}
            }
        }
    }

    Ok(LoopAction::Continue)
}

fn terminal_iteration(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    config: &FleetConfig,
    client: &mut DaemonClient,
    agent_id: &str,
    pane_views: &mut HashMap<String, PaneView>,
) -> Result<LoopAction> {
    // Load current agent state for title bar
    let state = FleetState::load(config)?;
    let agent = match state.agents.get(agent_id) {
        Some(a) => a,
        None => {
            // Agent no longer exists — go back to dashboard
            client.set_nonblocking(false)?;
            let _ = client.unsubscribe(agent_id);
            client.set_nonblocking(true)?;
            return Ok(LoopAction::SwitchToDashboard);
        }
    };

    // Render
    if let Some(pv) = pane_views.get(agent_id) {
        terminal.draw(|frame| {
            render::render_terminal(frame, pv, agent);
        })?;
    }

    // Poll events
    let poll_duration = Duration::from_millis(5);
    if event::poll(poll_duration).context("Failed to poll for events")? {
        match event::read().context("Failed to read event")? {
            Event::Key(key_event) => {
                // Ctrl+F -> back to dashboard
                if key_event.modifiers.contains(KeyModifiers::CONTROL)
                    && key_event.code == KeyCode::Char('f')
                {
                    client.set_nonblocking(false)?;
                    let _ = client.unsubscribe(agent_id);
                    client.set_nonblocking(true)?;
                    return Ok(LoopAction::SwitchToDashboard);
                }

                // Ctrl+C -> send SIGINT to agent (not quit)
                if key_event.modifiers.contains(KeyModifiers::CONTROL)
                    && key_event.code == KeyCode::Char('c')
                {
                    client.set_nonblocking(false)?;
                    let _ = client.send_sigint(agent_id);
                    client.set_nonblocking(true)?;
                    return Ok(LoopAction::Continue);
                }

                // Forward all other keys to PTY
                if let Some(bytes) = pane::encode_key(key_event) {
                    let _ = client.send_input(agent_id, &bytes);
                }
            }

            Event::Mouse(mouse_event) => {
                // Calculate pane area (minus title bar)
                let (term_cols, term_rows) = crossterm::terminal::size()?;
                let content_rows = term_rows.saturating_sub(1);
                let pane_area = ratatui::layout::Rect::new(0, 1, term_cols, content_rows);
                if let Some(bytes) = pane::encode_mouse_for_pane(mouse_event, pane_area) {
                    let _ = client.send_input(agent_id, &bytes);
                }
            }

            Event::Paste(text) => {
                // Bracketed paste: wrap in bracketed paste sequences
                let mut data = Vec::new();
                data.extend_from_slice(b"\x1b[200~");
                data.extend_from_slice(text.as_bytes());
                data.extend_from_slice(b"\x1b[201~");
                let _ = client.send_input(agent_id, &data);
            }

            Event::Resize(cols, rows) => {
                let content_rows = rows.saturating_sub(1);
                if let Some(pv) = pane_views.get_mut(agent_id) {
                    pv.resize(content_rows, cols);
                }
                client.set_nonblocking(false)?;
                let _ = client.resize(agent_id, content_rows, cols);
                client.set_nonblocking(true)?;
            }

            _ => {}
        }
    }

    Ok(LoopAction::Continue)
}

/// Spawn an agent directly from the dashboard.
fn spawn_inline(
    config: &FleetConfig,
    client: &mut DaemonClient,
    folder_name: &str,
    folder_path: &str,
    prompt: &str,
    current_state: &FleetState,
) -> Result<()> {
    let cwd = resolve_path(folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let id = generate_id();
    let now = Utc::now();

    let existing: Vec<&Agent> = current_state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        description: prompt.to_string(),
        folder: folder_name.to_string(),
        cwd: cwd_str.clone(),
        initial_prompt: prompt.to_string(),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        key,
        color_index,
    };

    with_state(config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    let cmd = crate::spawn::build_agent_cmd(prompt);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];

    // Switch to blocking for the spawn handshake
    client.set_nonblocking(false)?;
    client.spawn_agent(&id, &cwd_str, &cmd, &env)?;
    client.set_nonblocking(true)?;

    Ok(())
}

/// Adopt a session directly from the dashboard.
fn adopt_inline(
    config: &FleetConfig,
    client: &mut DaemonClient,
    session_id: &str,
    folder_name: &str,
    folder_path: &str,
    current_state: &FleetState,
) -> Result<()> {
    let cwd = resolve_path(folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let id = generate_id();
    let now = Utc::now();

    let existing: Vec<&Agent> = current_state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        description: format!("adopted: {session_id}"),
        folder: folder_name.to_string(),
        cwd: cwd_str.clone(),
        initial_prompt: format!("--resume {session_id}"),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        key,
        color_index,
    };

    with_state(config, |state| {
        state.agents.insert(id.clone(), agent);
    })?;

    let cmd = crate::spawn::build_resume_cmd(session_id);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];

    client.set_nonblocking(false)?;
    client.spawn_agent(&id, &cwd_str, &cmd, &env)?;
    client.set_nonblocking(true)?;

    Ok(())
}

/// Temporarily leave the TUI, run a closure, then re-enter.
fn suspend_tui<F>(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, f: F) -> Result<()>
where
    F: FnOnce(),
{
    execute!(io::stdout(), DisableMouseCapture, DisableBracketedPaste)?;
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
    execute!(io::stdout(), EnableMouseCapture, EnableBracketedPaste)?;
    terminal.clear().context("Failed to clear terminal")?;

    Ok(())
}
