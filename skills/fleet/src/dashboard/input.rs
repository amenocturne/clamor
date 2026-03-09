use std::collections::HashMap;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// Actions the dashboard can take in response to keyboard input.
pub enum DashboardAction {
    /// Switch to an agent's tmux session
    Attach(String),
    /// Spawn a new agent
    SpawnNew,
    /// Edit an existing agent
    EditAgent,
    /// Kill an agent
    KillAgent,
    /// Exit the dashboard
    Quit,
    /// Refresh the display (no-op action)
    Refresh,
}

/// Process a keyboard event and return the corresponding action.
/// `key_map` maps jump key chars to agent IDs.
pub fn handle_input(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char('q') => DashboardAction::Quit,
        KeyCode::Char('n') => DashboardAction::SpawnNew,
        KeyCode::Char('e') => DashboardAction::EditAgent,
        KeyCode::Char('K') => DashboardAction::KillAgent,
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
