use std::collections::HashMap;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

/// Which field is active in the two-field spawn popup.
pub enum PromptField {
    Title,
    Description,
}

/// Actions the dashboard can take in response to keyboard input.
pub enum DashboardAction {
    Attach(String),
    SpawnInline,
    SpawnEditor,
    KillAgent(String),
    PendingKill,
    EditAgent(String),
    PendingEdit,
    EditInput(PromptEdit),
    EditSubmitted,
    FolderPicked(usize),
    PromptSubmitted,
    PromptInput(PromptEdit),
    PromptToggleField,
    AdoptStart,
    AdoptInput(PromptEdit),
    AdoptSubmitted,
    SelectNext,
    SelectPrev,
    AttachSelected,
    CleanStale,
    DismissStale,
    ConfirmYes,
    Cancel,
    Quit,
    Refresh,
}

/// Edits to a text input.
pub enum PromptEdit {
    Char(char),
    Paste(String),
    Backspace,
    DeleteWord,
    DeleteLine,
}

/// Dashboard input mode.
pub enum InputMode {
    Normal,
    WaitingKill,
    PickingFolder {
        folder_count: usize,
        for_editor: bool,
    },
    TypingPrompt {
        folder_name: String,
        folder_path: String,
        title: String,
        description: String,
        active_field: PromptField,
    },
    TypingAdopt {
        input: String,
    },
    StalePrompt {
        count: usize,
    },
    StaleAgent {
        agent_id: String,
    },
    ConfirmEmptySpawn {
        folder_name: String,
        folder_path: String,
    },
    WaitingEdit,
    EditingDescription {
        agent_id: String,
        input: String,
    },
}

/// Process a keyboard event and return the corresponding action.
pub fn handle_input(
    event: KeyEvent,
    key_map: &HashMap<char, String>,
    mode: &InputMode,
) -> DashboardAction {
    if event.modifiers.contains(KeyModifiers::CONTROL) && matches!(event.code, KeyCode::Char('c')) {
        return DashboardAction::Quit;
    }

    match mode {
        InputMode::Normal => handle_normal(event, key_map),
        InputMode::WaitingKill => handle_pending_kill(event, key_map),
        InputMode::WaitingEdit => handle_pending_edit(event, key_map),
        InputMode::EditingDescription { .. } => handle_edit_input(event),
        InputMode::PickingFolder { folder_count, .. } => handle_folder_pick(event, *folder_count),
        InputMode::TypingPrompt { .. } => handle_prompt_input(event),
        InputMode::TypingAdopt { .. } => handle_adopt_input(event),
        InputMode::StalePrompt { .. } => handle_stale_input(event),
        InputMode::StaleAgent { .. } => handle_stale_input(event),
        InputMode::ConfirmEmptySpawn { .. } => handle_confirm_input(event),
    }
}

fn handle_normal(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char('q') => DashboardAction::Quit,
        KeyCode::Char('C') => DashboardAction::SpawnEditor,
        KeyCode::Char('c') if event.modifiers.contains(KeyModifiers::SHIFT) => {
            DashboardAction::SpawnEditor
        }
        KeyCode::Char('c') => DashboardAction::SpawnInline,
        KeyCode::Char('K') => DashboardAction::PendingKill,
        KeyCode::Char('k') if event.modifiers.contains(KeyModifiers::SHIFT) => {
            DashboardAction::PendingKill
        }
        KeyCode::Char('e') => DashboardAction::PendingEdit,
        KeyCode::Char('R') => DashboardAction::AdoptStart,
        KeyCode::Char('J') => DashboardAction::SelectNext,
        KeyCode::Char('j') if event.modifiers.contains(KeyModifiers::SHIFT) => {
            DashboardAction::SelectNext
        }
        KeyCode::Down => DashboardAction::SelectNext,
        KeyCode::Up => DashboardAction::SelectPrev,
        KeyCode::Enter => DashboardAction::AttachSelected,
        KeyCode::Char(c) => match key_map.get(&c) {
            Some(agent_id) => DashboardAction::Attach(agent_id.clone()),
            None => DashboardAction::Refresh,
        },
        KeyCode::Esc => DashboardAction::Refresh,
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

fn handle_pending_edit(event: KeyEvent, key_map: &HashMap<char, String>) -> DashboardAction {
    match event.code {
        KeyCode::Char(c) => match key_map.get(&c) {
            Some(agent_id) => DashboardAction::EditAgent(agent_id.clone()),
            None => DashboardAction::Cancel,
        },
        KeyCode::Esc => DashboardAction::Cancel,
        _ => DashboardAction::Cancel,
    }
}

fn handle_edit_input(event: KeyEvent) -> DashboardAction {
    if let Some(edit) = check_text_shortcut(&event) {
        return DashboardAction::EditInput(edit);
    }
    match event.code {
        KeyCode::Enter => DashboardAction::EditSubmitted,
        KeyCode::Esc => DashboardAction::Cancel,
        KeyCode::Backspace => DashboardAction::EditInput(PromptEdit::Backspace),
        KeyCode::Char(c) => DashboardAction::EditInput(PromptEdit::Char(c)),
        _ => DashboardAction::Refresh,
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
    if let Some(edit) = check_text_shortcut(&event) {
        return DashboardAction::PromptInput(edit);
    }
    match event.code {
        KeyCode::Enter => DashboardAction::PromptSubmitted,
        KeyCode::Esc => DashboardAction::Cancel,
        KeyCode::Tab | KeyCode::BackTab => DashboardAction::PromptToggleField,
        KeyCode::Backspace => DashboardAction::PromptInput(PromptEdit::Backspace),
        KeyCode::Char(c) => DashboardAction::PromptInput(PromptEdit::Char(c)),
        _ => DashboardAction::Refresh,
    }
}

fn handle_adopt_input(event: KeyEvent) -> DashboardAction {
    if let Some(edit) = check_text_shortcut(&event) {
        return DashboardAction::AdoptInput(edit);
    }
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

fn handle_confirm_input(event: KeyEvent) -> DashboardAction {
    match event.code {
        KeyCode::Char('y') => DashboardAction::ConfirmYes,
        KeyCode::Char('n') | KeyCode::Esc => DashboardAction::Cancel,
        _ => DashboardAction::Refresh,
    }
}

/// Check for macOS-style text editing shortcuts.
/// Ctrl+W / Alt+Backspace → delete word, Ctrl+U → delete line.
fn check_text_shortcut(event: &KeyEvent) -> Option<PromptEdit> {
    match event.code {
        KeyCode::Char('w') if event.modifiers.contains(KeyModifiers::CONTROL) => {
            Some(PromptEdit::DeleteWord)
        }
        KeyCode::Char('u') if event.modifiers.contains(KeyModifiers::CONTROL) => {
            Some(PromptEdit::DeleteLine)
        }
        KeyCode::Backspace if event.modifiers.contains(KeyModifiers::ALT) => {
            Some(PromptEdit::DeleteWord)
        }
        KeyCode::Backspace if event.modifiers.contains(KeyModifiers::SUPER) => {
            Some(PromptEdit::DeleteLine)
        }
        _ => None,
    }
}
