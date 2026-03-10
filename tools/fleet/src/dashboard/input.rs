use std::collections::HashMap;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// Actions the dashboard can take in response to keyboard input.
pub enum DashboardAction {
    Attach(String),
    SpawnInline,
    KillAgent(String),
    PendingKill,
    FolderPicked(usize),
    PromptSubmitted,
    SpawnEmpty,
    PromptInput(PromptEdit),
    AdoptStart,
    AdoptInput(PromptEdit),
    AdoptSubmitted,
    CleanStale,
    DismissStale,
    Cancel,
    Quit,
    Refresh,
}

/// Edits to a text input.
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
    TypingAdopt { input: String },
    StalePrompt { count: usize },
    StaleAgent { agent_id: String },
}

/// Process a keyboard event and return the corresponding action.
pub fn handle_input(event: KeyEvent, key_map: &HashMap<char, String>, mode: &InputMode) -> DashboardAction {
    if event.modifiers.contains(KeyModifiers::CONTROL) {
        if matches!(event.code, KeyCode::Char('c')) {
            return DashboardAction::Quit;
        }
    }

    match mode {
        InputMode::Normal => handle_normal(event, key_map),
        InputMode::WaitingKill => handle_pending_kill(event, key_map),
        InputMode::PickingFolder { folder_count } => handle_folder_pick(event, *folder_count),
        InputMode::TypingPrompt { .. } => handle_prompt_input(event),
        InputMode::TypingAdopt { .. } => handle_adopt_input(event),
        InputMode::StalePrompt { .. } => handle_stale_input(event),
        InputMode::StaleAgent { .. } => handle_stale_input(event),
    }
}

fn handle_normal(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char('q') => DashboardAction::Quit,
        KeyCode::Char('c') => DashboardAction::SpawnInline,
        KeyCode::Char('K') => DashboardAction::PendingKill,
        KeyCode::Char('k') if event.modifiers.contains(KeyModifiers::SHIFT) => DashboardAction::PendingKill,
        KeyCode::Char('R') => DashboardAction::AdoptStart,
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
        KeyCode::Tab => DashboardAction::SpawnEmpty,
        KeyCode::Esc => DashboardAction::Cancel,
        KeyCode::Backspace => DashboardAction::PromptInput(PromptEdit::Backspace),
        KeyCode::Char(c) => DashboardAction::PromptInput(PromptEdit::Char(c)),
        _ => DashboardAction::Refresh,
    }
}

fn handle_adopt_input(event: KeyEvent) -> DashboardAction {
    match event.code {
        KeyCode::Enter => DashboardAction::AdoptSubmitted,
        KeyCode::Esc => DashboardAction::Cancel,
        KeyCode::Backspace => DashboardAction::AdoptInput(PromptEdit::Backspace),
        KeyCode::Char(c) => DashboardAction::AdoptInput(PromptEdit::Char(c)),
        _ => DashboardAction::Refresh,
    }
}

fn handle_stale_input(event: KeyEvent) -> DashboardAction {
    match event.code {
        KeyCode::Char('y') => DashboardAction::CleanStale,
        KeyCode::Char('n') | KeyCode::Esc => DashboardAction::DismissStale,
        _ => DashboardAction::Refresh,
    }
}
