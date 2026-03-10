use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentState {
    Working,
    Input,
    Done,
    Lost,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: String,
    /// Display name shown in dashboard. Renamed from `description`.
    #[serde(alias = "description")]
    pub title: String,
    pub folder: String,
    pub cwd: String,
    /// Prompt sent to claude. None = interactive (bare `claude`).
    #[serde(default)]
    pub initial_prompt: Option<String>,
    pub state: AgentState,
    pub started_at: DateTime<Utc>,
    pub last_activity_at: DateTime<Utc>,
    pub last_tool: Option<String>,
    /// Claude Code session ID, captured from hooks. Used to resume sessions.
    #[serde(default)]
    pub session_id: Option<String>,
    #[serde(default)]
    pub key: Option<char>,
    #[serde(default)]
    pub color_index: u8,
}

pub fn generate_id(existing: &std::collections::HashSet<String>) -> String {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    loop {
        let n: u32 = rng.gen_range(0..0xFFFFFF);
        let id = format!("{:06x}", n);
        if !existing.contains(&id) {
            return id;
        }
    }
}

pub fn next_color_index(existing: &[&Agent]) -> u8 {
    let max = existing.iter().map(|a| a.color_index).max().unwrap_or(0);
    if existing.is_empty() { 0 } else { max.wrapping_add(1) }
}
