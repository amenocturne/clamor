mod input;
pub(crate) mod keys;
pub(crate) mod render;

use std::collections::HashMap;
use std::io;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use chrono::Utc;
use crossterm::event::{Event, KeyCode, KeyEventKind, KeyModifiers};
use crossterm::terminal::{self, EnterAlternateScreen, LeaveAlternateScreen};
use crossterm::ExecutableCommand;
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::crossterm::event::{
    DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture,
    EventStream,
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
use crate::watcher::StateSource;

use input::{DashboardAction, InputMode, PromptEdit, PromptField};

fn apply_edit(s: &mut String, edit: &PromptEdit) {
    match edit {
        PromptEdit::Char(c) => s.push(*c),
        PromptEdit::Paste(text) => s.push_str(text),
        PromptEdit::Backspace => {
            s.pop();
        }
        PromptEdit::DeleteWord => {
            let trimmed = s.trim_end_matches(|c: char| !c.is_alphanumeric());
            let len_after_spaces = trimmed.len();
            let word_trimmed = trimmed.trim_end_matches(|c: char| c.is_alphanumeric());
            let len_after_word = word_trimmed.len();
            if len_after_spaces == s.len() && len_after_word == len_after_spaces {
                s.pop();
            } else {
                s.truncate(len_after_word);
            }
        }
        PromptEdit::DeleteLine => s.clear(),
    }
}

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

async fn reconcile_state(client: &mut DaemonClient) -> Result<usize> {
    let daemon_agents = client.list_agents().await?;
    let daemon_ids: std::collections::HashSet<String> =
        daemon_agents.iter().map(|a| a.id.clone()).collect();

    let lost_count = with_state(|state| {
        let mut count = 0;
        for (id, agent) in state.agents.iter_mut() {
            if agent.state != AgentState::Lost && !daemon_ids.contains(id) {
                agent.state = AgentState::Lost;
                count += 1;
            }
        }
        count
    })?;
    Ok(lost_count)
}

pub async fn run(config: &FleetConfig, attach_to: Option<String>) -> Result<()> {
    ensure_daemon()?;
    let mut client = DaemonClient::connect().await?;

    let lost_count = reconcile_state(&mut client).await?;

    let state_source = StateSource::new(config);

    install_panic_hook();
    let mut terminal = setup_terminal()?;
    execute!(io::stdout(), EnableBracketedPaste, EnableMouseCapture)?;

    let result = main_loop(
        &mut terminal,
        config,
        &mut client,
        attach_to,
        lost_count,
        &state_source,
    )
    .await;

    execute!(io::stdout(), DisableBracketedPaste, DisableMouseCapture)?;
    restore_terminal(&mut terminal)?;

    result
}

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

async fn main_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    config: &FleetConfig,
    client: &mut DaemonClient,
    attach_to: Option<String>,
    lost_count: usize,
    state_source: &StateSource,
) -> Result<()> {
    let mut input_mode = if lost_count > 0 && attach_to.is_none() {
        InputMode::StalePrompt { count: lost_count }
    } else {
        InputMode::Normal
    };
    let mut killed_at: HashMap<String, Instant> = HashMap::new();
    let kill_linger = Duration::from_secs(3);
    let mut pane_views: HashMap<String, PaneView> = HashMap::new();
    let mut last_agent_id: Option<String> = None;

    let mut mode = if let Some(ref agent_id) = attach_to {
        let state = state_source.get();
        let is_lost = state
            .agents
            .get(agent_id)
            .map_or(true, |a| a.state == AgentState::Lost);

        if is_lost {
            input_mode = InputMode::StaleAgent {
                agent_id: agent_id.clone(),
            };
            AppMode::Dashboard
        } else {
            let (term_cols, term_rows) = crossterm::terminal::size()?;
            let content_rows = term_rows.saturating_sub(1);
            let pv = pane_views
                .entry(agent_id.clone())
                .or_insert_with(|| PaneView::new(content_rows, term_cols));
            match client.subscribe(agent_id).await {
                Ok(catch_up) => {
                    if !catch_up.is_empty() {
                        pv.process_output(&catch_up);
                    }
                    let _ = client.resize(agent_id, content_rows, term_cols).await;
                    AppMode::Terminal {
                        agent_id: agent_id.clone(),
                    }
                }
                Err(_) => AppMode::Dashboard,
            }
        }
    } else {
        AppMode::Dashboard
    };

    let mut sorted_folders: Vec<(String, String)> = config
        .folders
        .iter()
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    sorted_folders.sort_by(|a, b| a.0.cmp(&b.0));

    let mut event_stream = EventStream::new();
    let mut frame_interval = tokio::time::interval(Duration::from_millis(16));
    let mut needs_render = true;

    loop {
        tokio::select! {
            msg_result = client.recv() => {
                match msg_result {
                    Ok(msg) => {
                        match msg {
                            DaemonMessage::Output { id, data } => {
                                if let Some(pv) = pane_views.get_mut(&id) {
                                    pv.process_output(&data);
                                }
                            }
                            DaemonMessage::Exited { id } => {
                                let _ = with_state(|state| {
                                    if let Some(agent) = state.agents.get_mut(&id) {
                                        agent.state = AgentState::Done;
                                    }
                                });
                                state_source.invalidate();
                            }
                            DaemonMessage::CatchUp { id, data } => {
                                if let Some(pv) = pane_views.get_mut(&id) {
                                    pv.process_output(&data);
                                }
                            }
                            DaemonMessage::Heartbeat => {
                                let _ = client.pong().await;
                            }
                            _ => {}
                        }
                        needs_render = true;
                    }
                    Err(_) => {
                        // Connection lost — try to reconnect
                        if let Ok(new_client) = DaemonClient::connect().await {
                            *client = new_client;
                        }
                    }
                }
            }

            event_result = event_stream.next() => {
                if let Some(Ok(ev)) = event_result {
                    let action = match mode {
                        AppMode::Dashboard => {
                            handle_dashboard_event(
                                &ev,
                                terminal,
                                client,
                                &mut input_mode,
                                &mut killed_at,
                                &sorted_folders,
                                &last_agent_id,
                                state_source,
                            ).await?
                        }
                        AppMode::Terminal { ref agent_id } => {
                            handle_terminal_event(
                                &ev,
                                terminal,
                                client,
                                agent_id,
                                &mut pane_views,
                            ).await?
                        }
                    };

                    match action {
                        LoopAction::Quit => break,
                        LoopAction::SwitchToTerminal(agent_id) => {
                            let (term_cols, term_rows) = crossterm::terminal::size()?;
                            let content_rows = term_rows.saturating_sub(1);
                            let pv = pane_views
                                .entry(agent_id.clone())
                                .or_insert_with(|| PaneView::new(content_rows, term_cols));

                            match client.subscribe(&agent_id).await {
                                Ok(catch_up) => {
                                    if !catch_up.is_empty() {
                                        pv.process_output(&catch_up);
                                    }
                                }
                                Err(_) => continue,
                            }

                            let _ = client.resize(&agent_id, content_rows, term_cols).await;
                            mode = AppMode::Terminal { agent_id };
                        }
                        LoopAction::SwitchToDashboard => {
                            if let AppMode::Terminal { ref agent_id } = mode {
                                last_agent_id = Some(agent_id.clone());
                            }
                            mode = AppMode::Dashboard;
                            input_mode = InputMode::Normal;
                        }
                        LoopAction::Continue => {}
                    }
                    needs_render = true;
                }
            }

            _ = frame_interval.tick() => {
                // Expire killed agents
                let expired: Vec<String> = killed_at
                    .iter()
                    .filter(|(_, t)| t.elapsed() > kill_linger)
                    .map(|(id, _)| id.clone())
                    .collect();
                if !expired.is_empty() {
                    let _ = with_state(|state| {
                        for id in &expired {
                            state.agents.remove(id);
                        }
                    });
                    state_source.invalidate();
                    for id in &expired {
                        killed_at.remove(id);
                    }
                    needs_render = true;
                }

                if needs_render {
                    match mode {
                        AppMode::Dashboard => {
                            render_dashboard(
                                terminal,
                                config,
                                &input_mode,
                                &killed_at,
                                &sorted_folders,
                                state_source,
                            )?;
                        }
                        AppMode::Terminal { ref agent_id } => {
                            let state = state_source.get();
                            if !state.agents.contains_key(agent_id) {
                                let _ = client.unsubscribe(agent_id).await;
                                last_agent_id = Some(agent_id.clone());
                                mode = AppMode::Dashboard;
                                input_mode = InputMode::Normal;
                                needs_render = true;
                                continue;
                            }
                            render_terminal_view(
                                terminal,
                                agent_id,
                                &mut pane_views,
                                state_source,
                            )?;
                        }
                    }
                    needs_render = false;
                }
            }
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

fn render_dashboard(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    config: &FleetConfig,
    input_mode: &InputMode,
    killed_at: &HashMap<String, Instant>,
    sorted_folders: &[(String, String)],
    state_source: &StateSource,
) -> Result<()> {
    let state = state_source.get();
    let killed_ids: Vec<String> = killed_at.keys().cloned().collect();

    let agent_refs: HashMap<String, &Agent> =
        state.agents.iter().map(|(id, a)| (id.clone(), a)).collect();

    let overlay = build_overlay(input_mode, sorted_folders, &state);

    terminal.draw(|frame| {
        render::render(frame, config, &agent_refs, &killed_ids, &overlay);
    })?;

    Ok(())
}

fn build_overlay<'a>(
    input_mode: &'a InputMode,
    sorted_folders: &'a [(String, String)],
    state: &'a FleetState,
) -> render::Overlay<'a> {
    match input_mode {
        InputMode::Normal => render::Overlay::None,
        InputMode::WaitingKill => render::Overlay::PendingKill,
        InputMode::PickingFolder { .. } => render::Overlay::FolderPicker {
            folders: sorted_folders,
        },
        InputMode::TypingPrompt {
            folder_name,
            title,
            description,
            active_field,
            ..
        } => render::Overlay::PromptInput {
            folder_name,
            title,
            description,
            active_field,
        },
        InputMode::TypingAdopt { input } => render::Overlay::AdoptInput { input },
        InputMode::StalePrompt { count } => render::Overlay::StaleAgents { count: *count },
        InputMode::StaleAgent { ref agent_id } => {
            let desc = state
                .agents
                .get(agent_id)
                .map(|a| a.title.as_str())
                .unwrap_or("unknown");
            render::Overlay::StaleAgent { description: desc }
        }
        InputMode::ConfirmEmptySpawn { .. } => render::Overlay::ConfirmEmptySpawn,
        InputMode::WaitingEdit => render::Overlay::PendingEdit,
        InputMode::EditingDescription { input, .. } => render::Overlay::EditInput { input },
    }
}

fn render_terminal_view(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    agent_id: &str,
    pane_views: &mut HashMap<String, PaneView>,
    state_source: &StateSource,
) -> Result<()> {
    let state = state_source.get();
    let agent = match state.agents.get(agent_id) {
        Some(a) => a,
        None => return Ok(()),
    };

    if let Some(pv) = pane_views.get_mut(agent_id) {
        let sel = pv.selection.clone();
        let screen = pv.scrolled_screen();
        terminal.draw(|frame| {
            render::render_terminal(frame, screen, agent, &sel);
        })?;
    }

    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn handle_dashboard_event(
    ev: &Event,
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    client: &mut DaemonClient,
    input_mode: &mut InputMode,
    killed_at: &mut HashMap<String, Instant>,
    sorted_folders: &[(String, String)],
    last_agent_id: &Option<String>,
    state_source: &StateSource,
) -> Result<LoopAction> {
    let (term_cols, term_rows) = crossterm::terminal::size().unwrap_or((80, 24));
    let pty_rows = term_rows.saturating_sub(1);
    let pty_cols = term_cols;

    let state = state_source.get();

    let mut key_map: HashMap<char, String> = HashMap::new();
    for (id, agent) in &state.agents {
        if let Some(k) = agent.key {
            key_map.insert(k, id.clone());
        }
    }

    if let Event::Paste(text) = ev {
        let action = match input_mode {
            InputMode::TypingPrompt { .. } => {
                DashboardAction::PromptInput(PromptEdit::Paste(text.clone()))
            }
            InputMode::TypingAdopt { .. } => {
                DashboardAction::AdoptInput(PromptEdit::Paste(text.clone()))
            }
            InputMode::EditingDescription { .. } => {
                DashboardAction::EditInput(PromptEdit::Paste(text.clone()))
            }
            _ => DashboardAction::Refresh,
        };
        match action {
            DashboardAction::PromptInput(edit) => {
                if let InputMode::TypingPrompt {
                    ref mut title,
                    ref mut description,
                    ref active_field,
                    ..
                } = input_mode
                {
                    let target = match active_field {
                        PromptField::Title => title,
                        PromptField::Description => description,
                    };
                    apply_edit(target, &edit);
                }
            }
            DashboardAction::AdoptInput(edit) => {
                if let InputMode::TypingAdopt { ref mut input } = input_mode {
                    apply_edit(input, &edit);
                }
            }
            DashboardAction::EditInput(edit) => {
                if let InputMode::EditingDescription { ref mut input, .. } = input_mode {
                    apply_edit(input, &edit);
                }
            }
            _ => {}
        }
        return Ok(LoopAction::Continue);
    }

    if let Event::Key(key_event) = ev {
        if key_event.kind != KeyEventKind::Press {
            return Ok(LoopAction::Continue);
        }

        // Ctrl+F: toggle back to last attached agent
        if matches!(input_mode, InputMode::Normal)
            && key_event.modifiers.contains(KeyModifiers::CONTROL)
            && key_event.code == KeyCode::Char('f')
        {
            if let Some(ref id) = last_agent_id {
                if state.agents.contains_key(id) {
                    return Ok(LoopAction::SwitchToTerminal(id.clone()));
                }
            }
        }

        match input::handle_input(*key_event, &key_map, input_mode) {
            DashboardAction::Quit => return Ok(LoopAction::Quit),

            DashboardAction::Attach(ref agent_id) => {
                *input_mode = InputMode::Normal;
                if let Some(agent) = state.agents.get(agent_id) {
                    if agent.state == AgentState::Lost {
                        *input_mode = InputMode::StaleAgent {
                            agent_id: agent_id.clone(),
                        };
                    } else {
                        return Ok(LoopAction::SwitchToTerminal(agent_id.clone()));
                    }
                }
            }

            DashboardAction::SpawnInline => {
                if sorted_folders.len() == 1 {
                    let (name, path) = &sorted_folders[0];
                    *input_mode = InputMode::TypingPrompt {
                        folder_name: name.clone(),
                        folder_path: path.clone(),
                        title: String::new(),
                        description: String::new(),
                        active_field: PromptField::Title,
                    };
                } else if sorted_folders.is_empty() {
                    *input_mode = InputMode::Normal;
                } else {
                    *input_mode = InputMode::PickingFolder {
                        folder_count: sorted_folders.len(),
                        for_editor: false,
                    };
                }
            }

            DashboardAction::SpawnEditor => {
                if sorted_folders.len() == 1 {
                    let (name, path) = &sorted_folders[0];
                    let folder_name_owned = name.clone();
                    let folder_path_owned = path.clone();
                    let mut editor_result: Option<(String, String)> = None;
                    tokio::task::block_in_place(|| {
                        suspend_tui(terminal, || {
                            if let Ok(result) = crate::spawn::read_task_from_editor() {
                                editor_result = Some(result);
                            }
                        })
                    })?;
                    *client = DaemonClient::connect().await?;
                    match editor_result {
                        Some((title, prompt)) => {
                            let state = state_source.get();
                            let _ = spawn_inline(
                                client,
                                &folder_name_owned,
                                &folder_path_owned,
                                &title,
                                Some(&prompt),
                                &state,
                                state_source,
                                pty_rows,
                                pty_cols,
                            ).await;
                        }
                        None => {
                            *input_mode = InputMode::ConfirmEmptySpawn {
                                folder_name: folder_name_owned,
                                folder_path: folder_path_owned,
                            };
                        }
                    }
                } else if sorted_folders.is_empty() {
                    *input_mode = InputMode::Normal;
                } else {
                    *input_mode = InputMode::PickingFolder {
                        folder_count: sorted_folders.len(),
                        for_editor: true,
                    };
                }
            }

            DashboardAction::FolderPicked(idx) => {
                let for_editor = matches!(
                    input_mode,
                    InputMode::PickingFolder {
                        for_editor: true,
                        ..
                    }
                );
                if let Some((name, path)) = sorted_folders.get(idx) {
                    if for_editor {
                        let folder_name_owned = name.clone();
                        let folder_path_owned = path.clone();
                        let mut editor_result: Option<(String, String)> = None;
                        tokio::task::block_in_place(|| {
                            suspend_tui(terminal, || {
                                match crate::spawn::read_task_from_editor() {
                                    Ok(result) => editor_result = Some(result),
                                    Err(e) => {
                                        eprintln!("Error: {e}");
                                        std::thread::sleep(Duration::from_secs(1));
                                    }
                                }
                            })
                        })?;
                        *client = DaemonClient::connect().await?;
                        match editor_result {
                            Some((title, prompt)) => {
                                let state = state_source.get();
                                let _ = spawn_inline(
                                    client,
                                    &folder_name_owned,
                                    &folder_path_owned,
                                    &title,
                                    Some(&prompt),
                                    &state,
                                    state_source,
                                    pty_rows,
                                    pty_cols,
                                ).await;
                                *input_mode = InputMode::Normal;
                            }
                            None => {
                                *input_mode = InputMode::ConfirmEmptySpawn {
                                    folder_name: folder_name_owned,
                                    folder_path: folder_path_owned,
                                };
                            }
                        }
                    } else {
                        *input_mode = InputMode::TypingPrompt {
                            folder_name: name.clone(),
                            folder_path: path.clone(),
                            title: String::new(),
                            description: String::new(),
                            active_field: PromptField::Title,
                        };
                    }
                } else {
                    *input_mode = InputMode::Normal;
                }
            }

            DashboardAction::PromptToggleField => {
                if let InputMode::TypingPrompt {
                    ref mut active_field,
                    ..
                } = input_mode
                {
                    *active_field = match active_field {
                        PromptField::Title => PromptField::Description,
                        PromptField::Description => PromptField::Title,
                    };
                }
            }

            DashboardAction::PromptInput(edit) => {
                if let InputMode::TypingPrompt {
                    ref mut title,
                    ref mut description,
                    ref active_field,
                    ..
                } = input_mode
                {
                    let target = match active_field {
                        PromptField::Title => title,
                        PromptField::Description => description,
                    };
                    apply_edit(target, &edit);
                }
            }

            DashboardAction::PromptSubmitted => {
                let mut submitted = false;
                if let InputMode::TypingPrompt {
                    folder_name,
                    folder_path,
                    title,
                    description,
                    active_field,
                } = input_mode
                {
                    let title_trimmed = title.trim().to_string();
                    if title_trimmed.is_empty() {
                        *active_field = PromptField::Title;
                    } else {
                        let desc_trimmed = description.trim().to_string();
                        let effective_prompt = if desc_trimmed.is_empty() {
                            None
                        } else {
                            Some(format!("{title_trimmed}\n\n{desc_trimmed}"))
                        };
                        let _ = spawn_inline(
                            client,
                            folder_name,
                            folder_path,
                            &title_trimmed,
                            effective_prompt.as_deref(),
                            &state,
                            state_source,
                            pty_rows,
                            pty_cols,
                        ).await;
                        submitted = true;
                    }
                }
                if submitted {
                    *input_mode = InputMode::Normal;
                }
            }

            DashboardAction::ConfirmYes => {
                if let InputMode::ConfirmEmptySpawn {
                    folder_name,
                    folder_path,
                } = input_mode
                {
                    let _ = spawn_inline(
                        client,
                        folder_name,
                        folder_path,
                        "interactive",
                        None,
                        &state,
                        state_source,
                        pty_rows,
                        pty_cols,
                    ).await;
                }
                *input_mode = InputMode::Normal;
            }

            DashboardAction::PendingEdit => {
                *input_mode = InputMode::WaitingEdit;
            }

            DashboardAction::EditAgent(agent_id) => {
                let current_title = state
                    .agents
                    .get(&agent_id)
                    .map(|a| a.title.clone())
                    .unwrap_or_default();
                *input_mode = InputMode::EditingDescription {
                    agent_id,
                    input: current_title,
                };
            }

            DashboardAction::EditInput(edit) => {
                if let InputMode::EditingDescription { ref mut input, .. } = input_mode {
                    apply_edit(input, &edit);
                }
            }

            DashboardAction::EditSubmitted => {
                if let InputMode::EditingDescription { agent_id, input } = input_mode {
                    let new_title = input.trim().to_string();
                    if !new_title.is_empty() {
                        let id = agent_id.clone();
                        let _ = with_state(|state| {
                            if let Some(agent) = state.agents.get_mut(&id) {
                                agent.title = new_title;
                            }
                        });
                        state_source.invalidate();
                    }
                }
                *input_mode = InputMode::Normal;
            }

            DashboardAction::PendingKill => {
                *input_mode = InputMode::WaitingKill;
            }

            DashboardAction::KillAgent(agent_id) => {
                *input_mode = InputMode::Normal;
                let _ = client.kill_agent(&agent_id).await;
                killed_at.insert(agent_id, Instant::now());
            }

            DashboardAction::AdoptStart => {
                *input_mode = InputMode::TypingAdopt {
                    input: String::new(),
                };
            }

            DashboardAction::AdoptInput(edit) => {
                if let InputMode::TypingAdopt { ref mut input } = input_mode {
                    apply_edit(input, &edit);
                }
            }

            DashboardAction::AdoptSubmitted => {
                if let InputMode::TypingAdopt { input } = input_mode {
                    let session_id = input.trim().to_string();
                    if !session_id.is_empty() {
                        if sorted_folders.len() == 1 {
                            let (folder_name, folder_path) = &sorted_folders[0];
                            let _ = adopt_inline(
                                client,
                                &session_id,
                                folder_name,
                                folder_path,
                                &state,
                                state_source,
                                pty_rows,
                                pty_cols,
                            ).await;
                        } else if !sorted_folders.is_empty() {
                            let (folder_name, folder_path) = &sorted_folders[0];
                            let _ = adopt_inline(
                                client,
                                &session_id,
                                folder_name,
                                folder_path,
                                &state,
                                state_source,
                                pty_rows,
                                pty_cols,
                            ).await;
                        }
                    }
                }
                *input_mode = InputMode::Normal;
            }

            DashboardAction::CleanStale => {
                if let InputMode::StaleAgent { ref agent_id } = input_mode {
                    let id = agent_id.clone();
                    let _ = with_state(|state| {
                        state.agents.remove(&id);
                    });
                } else {
                    let _ = with_state(|state| {
                        state.agents.retain(|_, a| a.state != AgentState::Lost);
                    });
                }
                state_source.invalidate();
                *input_mode = InputMode::Normal;
            }

            DashboardAction::DismissStale => {
                *input_mode = InputMode::Normal;
            }

            DashboardAction::Cancel => {
                *input_mode = InputMode::Normal;
            }

            DashboardAction::Refresh => {}
        }
    }

    Ok(LoopAction::Continue)
}

async fn handle_terminal_event(
    ev: &Event,
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    client: &mut DaemonClient,
    agent_id: &str,
    pane_views: &mut HashMap<String, PaneView>,
) -> Result<LoopAction> {
    match ev {
        Event::Key(key_event) if key_event.kind == KeyEventKind::Press => {
            // Ctrl+F -> back to dashboard
            if key_event.modifiers.contains(KeyModifiers::CONTROL)
                && key_event.code == KeyCode::Char('f')
            {
                let _ = client.unsubscribe(agent_id).await;
                return Ok(LoopAction::SwitchToDashboard);
            }

            // Ctrl+C -> send SIGINT to agent
            if key_event.modifiers.contains(KeyModifiers::CONTROL)
                && key_event.code == KeyCode::Char('c')
            {
                let _ = client.send_sigint(agent_id).await;
                return Ok(LoopAction::Continue);
            }

            if let Some(pv) = pane_views.get_mut(agent_id) {
                pv.clear_selection();
                pv.snap_to_bottom();
            }

            if let Some(bytes) = pane::encode_key(*key_event) {
                let _ = client.send_input(agent_id, &bytes).await;
            }
        }

        Event::Mouse(mouse_event) => {
            let (term_cols, term_rows) = crossterm::terminal::size()?;
            let content_rows = term_rows.saturating_sub(1);
            let pane_area = ratatui::layout::Rect::new(0, 1, term_cols, content_rows);

            let mouse_mode = pane_views
                .get(agent_id)
                .map_or(false, |pv| pv.mouse_mode_active());

            if mouse_mode {
                if let Some(bytes) = pane::encode_mouse_for_pane(*mouse_event, pane_area) {
                    let _ = client.send_input(agent_id, &bytes).await;
                }
            } else {
                use crossterm::event::{MouseButton, MouseEventKind};
                match mouse_event.kind {
                    MouseEventKind::ScrollUp => {
                        if let Some(pv) = pane_views.get_mut(agent_id) {
                            if pv.alternate_screen() {
                                let _ = client.send_input(agent_id, b"\x1b[A\x1b[A\x1b[A").await;
                            } else {
                                pv.scroll_offset = pv.scroll_offset.saturating_add(3);
                            }
                        }
                    }
                    MouseEventKind::ScrollDown => {
                        if let Some(pv) = pane_views.get_mut(agent_id) {
                            if pv.alternate_screen() {
                                let _ = client.send_input(agent_id, b"\x1b[B\x1b[B\x1b[B").await;
                            } else {
                                pv.scroll_offset = pv.scroll_offset.saturating_sub(3);
                            }
                        }
                    }
                    MouseEventKind::Down(MouseButton::Left) => {
                        if let Some(pv) = pane_views.get_mut(agent_id) {
                            if let Some(ref sel) = pv.selection {
                                if !sel.active && sel.start != sel.end {
                                    let sel = sel.clone();
                                    let screen = pv.scrolled_screen();
                                    let text = pane::extract_selected_text(
                                        screen,
                                        &sel,
                                        pane_area.width,
                                    );
                                    if !text.is_empty() {
                                        pane::copy_to_clipboard(&text);
                                    }
                                }
                            }

                            let col = mouse_event.column.saturating_sub(pane_area.x);
                            let row = mouse_event.row.saturating_sub(pane_area.y);
                            if col < pane_area.width && row < pane_area.height {
                                pv.selection = Some(pane::Selection {
                                    start: (col, row),
                                    end: (col, row),
                                    active: true,
                                });
                            }
                        }
                    }
                    MouseEventKind::Drag(MouseButton::Left) => {
                        if let Some(pv) = pane_views.get_mut(agent_id) {
                            if pv.selection.as_ref().map_or(false, |s| s.active) {
                                let col = mouse_event
                                    .column
                                    .saturating_sub(pane_area.x)
                                    .min(pane_area.width.saturating_sub(1));
                                let row = mouse_event
                                    .row
                                    .saturating_sub(pane_area.y)
                                    .min(pane_area.height.saturating_sub(1));

                                if let Some(ref mut sel) = pv.selection {
                                    sel.end = (col, row);
                                }

                                if !pv.alternate_screen() {
                                    if mouse_event.row <= pane_area.y + 1 {
                                        let old = pv.scroll_offset;
                                        pv.scroll_offset = pv.scroll_offset.saturating_add(1);
                                        let delta = (pv.scroll_offset - old) as u16;
                                        if delta > 0 {
                                            if let Some(ref mut sel) = pv.selection {
                                                sel.start.1 =
                                                    sel.start.1.saturating_add(delta).min(
                                                        pane_area.height.saturating_sub(1),
                                                    );
                                            }
                                        }
                                    } else if mouse_event.row
                                        >= pane_area.y + pane_area.height.saturating_sub(2)
                                    {
                                        let old = pv.scroll_offset;
                                        pv.scroll_offset = pv.scroll_offset.saturating_sub(1);
                                        let delta = (old - pv.scroll_offset) as u16;
                                        if delta > 0 {
                                            if let Some(ref mut sel) = pv.selection {
                                                sel.start.1 = sel.start.1.saturating_sub(delta);
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    MouseEventKind::Up(MouseButton::Left) => {
                        if let Some(pv) = pane_views.get_mut(agent_id) {
                            let should_copy = pv
                                .selection
                                .as_ref()
                                .map_or(false, |s| s.active && s.start != s.end);
                            if should_copy {
                                let sel = pv.selection.clone().unwrap();
                                let screen = pv.scrolled_screen();
                                let text =
                                    pane::extract_selected_text(screen, &sel, pane_area.width);
                                if !text.is_empty() {
                                    pane::copy_to_clipboard(&text);
                                }
                            }
                            pv.selection = None;
                        }
                    }
                    _ => {}
                }
            }
        }

        Event::Paste(text) => {
            if let Some(pv) = pane_views.get_mut(agent_id) {
                pv.clear_selection();
                pv.snap_to_bottom();
            }

            let use_bracket = pane_views
                .get(agent_id)
                .map_or(false, |pv| pv.parser.screen().bracketed_paste());

            let data = if use_bracket {
                let mut buf = Vec::with_capacity(text.len() + 14);
                buf.extend_from_slice(b"\x1b[200~");
                buf.extend_from_slice(text.as_bytes());
                buf.extend_from_slice(b"\x1b[201~");
                buf
            } else {
                text.as_bytes().to_vec()
            };
            let _ = client.send_input(agent_id, &data).await;

            terminal.clear()?;
        }

        Event::Resize(cols, rows) => {
            let content_rows = rows.saturating_sub(1);
            if let Some(pv) = pane_views.get_mut(agent_id) {
                pv.resize(content_rows, *cols);
            }
            let _ = client.resize(agent_id, content_rows, *cols).await;
        }

        _ => {}
    }

    Ok(LoopAction::Continue)
}

async fn spawn_inline(
    client: &mut DaemonClient,
    folder_name: &str,
    folder_path: &str,
    title: &str,
    prompt: Option<&str>,
    current_state: &FleetState,
    state_source: &StateSource,
    pty_rows: u16,
    pty_cols: u16,
) -> Result<()> {
    let cwd = resolve_path(folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let existing_ids: std::collections::HashSet<String> =
        current_state.agents.keys().cloned().collect();
    let id = generate_id(&existing_ids);
    let now = Utc::now();

    let existing: Vec<&Agent> = current_state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let initial_state = if prompt.is_some() {
        AgentState::Working
    } else {
        AgentState::Input
    };

    let agent = Agent {
        id: id.clone(),
        title: title.to_string(),
        folder: folder_name.to_string(),
        cwd: cwd_str.clone(),
        initial_prompt: prompt.map(|s| s.to_string()),
        state: initial_state,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        session_id: None,
        key,
        color_index,
    };

    with_state(|state| {
        state.agents.insert(id.clone(), agent);
    })?;
    state_source.invalidate();

    let cmd = crate::spawn::build_agent_cmd(prompt);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];

    client.spawn_agent(&id, &cwd_str, &cmd, &env, pty_rows, pty_cols).await?;

    Ok(())
}

async fn adopt_inline(
    client: &mut DaemonClient,
    session_id: &str,
    folder_name: &str,
    folder_path: &str,
    current_state: &FleetState,
    state_source: &StateSource,
    pty_rows: u16,
    pty_cols: u16,
) -> Result<()> {
    let cwd = resolve_path(folder_path);
    let cwd_str = cwd.to_string_lossy().to_string();

    let existing_ids: std::collections::HashSet<String> =
        current_state.agents.keys().cloned().collect();
    let id = generate_id(&existing_ids);
    let now = Utc::now();

    let existing: Vec<&Agent> = current_state.agents.values().collect();
    let key = keys::next_available_key(&existing);
    let color_index = next_color_index(&existing);

    let agent = Agent {
        id: id.clone(),
        title: format!("adopted: {session_id}"),
        folder: folder_name.to_string(),
        cwd: cwd_str.clone(),
        initial_prompt: Some(format!("--resume {session_id}")),
        state: AgentState::Working,
        started_at: now,
        last_activity_at: now,
        last_tool: None,
        session_id: Some(session_id.to_string()),
        key,
        color_index,
    };

    with_state(|state| {
        state.agents.insert(id.clone(), agent);
    })?;
    state_source.invalidate();

    let cmd = crate::spawn::build_resume_cmd(session_id);
    let env = vec![("FLEET_AGENT_ID".to_string(), id.clone())];

    client.spawn_agent(&id, &cwd_str, &cmd, &env, pty_rows, pty_cols).await?;

    Ok(())
}

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
