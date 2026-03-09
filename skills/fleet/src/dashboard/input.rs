use std::collections::HashMap;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// Actions the dashboard can take in response to keyboard input.
pub enum DashboardAction {
    /// Switch to an agent's tmux session
    Attach(String),
    /// Start inline spawn flow (folder picker → text input popup)
    SpawnInline,
    /// Spawn via $EDITOR (suspend TUI)
    SpawnEditor,
    /// Kill a specific agent by ID
    KillAgent(String),
    /// Enter pending kill mode (waiting for jump key)
    PendingKill,
    /// Folder selected during inline spawn — transition to text input
    FolderPicked(usize),
    /// Inline prompt submitted — spawn the agent
    PromptSubmitted,
    /// Character typed in prompt input
    PromptInput(PromptEdit),
    /// Cancel current mode, return to normal
    Cancel,
    /// Exit the dashboard
    Quit,
    /// Refresh the display (no-op action)
    Refresh,
}

/// Edits to the prompt text input.
pub enum PromptEdit {
    Char(char),
    Backspace,
}

/// Dashboard input mode.
pub enum InputMode {
    Normal,
    WaitingKill,
    PickingFolder { folder_count: usize },
    TypingPrompt { folder_name: String, folder_path: String, input: String },
}

/// Process a keyboard event and return the corresponding action.
pub fn handle_input(event: KeyEvent, key_map: &HashMap<char, String>, mode: &InputMode) -> DashboardAction {
    // Ctrl+C always quits
    if matches!(event.code, KeyCode::Char('c') if event.modifiers.contains(KeyModifiers::CONTROL)) {
        return DashboardAction::Quit;
    }

    match mode {
        InputMode::Normal => handle_normal(event, key_map),
        InputMode::WaitingKill => handle_pending_kill(event, key_map),
        InputMode::PickingFolder { folder_count } => handle_folder_pick(event, *folder_count),
        InputMode::TypingPrompt { .. } => handle_prompt_input(event),
    }
}

fn handle_normal(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char('q') => DashboardAction::Quit,
        KeyCode::Char('c') => DashboardAction::SpawnInline,
        KeyCode::Char('C') => DashboardAction::SpawnEditor,
        KeyCode::Char('K') => DashboardAction::PendingKill,
        KeyCode::Char(c) => match key_map.get(&c) {
            Some(agent_id) => DashboardAction::Attach(agent_id.clone()),
            None => DashboardAction::Refresh,
        },
        KeyCode::Esc => DashboardAction::Quit,
        _ => DashboardAction::Refresh,
    }
}

fn handle_pending_kill(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char(c) => match key_map.get(&c) {
            Some(agent_id) => DashboardAction::KillAgent(agent_id.clone()),
            None => DashboardAction::Cancel,
        },
        KeyCode::Esc => DashboardAction::Cancel,
        _ => DashboardAction::Cancel,
    }
}

fn handle_folder_pick(event: KeyEvent, folder_count: usize) -> DashboardAction {
    match event.code {
        KeyCode::Char(c) if c.is_ascii_digit() => {
            let n = c.to_digit(10).unwrap() as usize;
            if n >= 1 && n <= folder_count {
                DashboardAction::FolderPicked(n - 1)
            } else {
                DashboardAction::Refresh
            }
        }
        KeyCode::Esc => DashboardAction::Cancel,
        _ => DashboardAction::Refresh,
    }
}

fn handle_prompt_input(event: KeyEvent) -> DashboardAction {
    match event.code {
        KeyCode::Enter => DashboardAction::PromptSubmitted,
        KeyCode::Esc => DashboardAction::Cancel,
        KeyCode::Backspace => DashboardAction::PromptInput(PromptEdit::Backspace),
        KeyCode::Char(c) => DashboardAction::PromptInput(PromptEdit::Char(c)),
        _ => DashboardAction::Refresh,
    }
}
