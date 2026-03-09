use std::collections::HashMap;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// Actions the dashboard can take in response to keyboard input.
pub enum DashboardAction {
    /// Switch to an agent's tmux session
    Attach(String),
    /// Spawn a new agent
    SpawnNew,
    /// Kill a specific agent by ID
    KillAgent(String),
    /// Enter pending kill mode (waiting for jump key)
    PendingKill,
    /// Exit the dashboard
    Quit,
    /// Refresh the display (no-op action)
    Refresh,
}

/// Dashboard input mode.
pub enum InputMode {
    Normal,
    /// Waiting for a jump key to complete a kill chord
    WaitingKill,
}

/// Process a keyboard event and return the corresponding action.
pub fn handle_input(event: KeyEvent, key_map: &HashMap<char, String>, mode: &InputMode) -> DashboardAction {
    match mode {
        InputMode::WaitingKill => handle_pending_kill(event, key_map),
        InputMode::Normal => handle_normal(event, key_map),
    }
}

fn handle_normal(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char('q') => DashboardAction::Quit,
        KeyCode::Char('n') => DashboardAction::SpawnNew,
        KeyCode::Char('K') => DashboardAction::PendingKill,
        KeyCode::Char('c') if event.modifiers.contains(KeyModifiers::CONTROL) => {
            DashboardAction::Quit
        }
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
            None => DashboardAction::Refresh, // invalid key, cancel
        },
        KeyCode::Esc => DashboardAction::Refresh, // cancel
        _ => DashboardAction::Refresh,
    }
}
