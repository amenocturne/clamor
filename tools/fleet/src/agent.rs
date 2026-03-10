use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AgentState {
    Working,
    Input,
    Done,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: String,
    pub description: String,
    pub folder: String,
    pub cwd: String,
    pub initial_prompt: String,
    pub state: AgentState,
    pub started_at: DateTime<Utc>,
    pub last_activity_at: DateTime<Utc>,
    pub last_tool: Option<String>,
    #[serde(default)]
    pub key: Option<char>,
    #[serde(default)]
    pub color_index: u8,
}

pub fn generate_id() -> String {
    use rand::Rng;
    let n: u32 = rand::thread_rng().gen_range(0..0xFFFFFF);
    format!("{:06x}", n)
}

pub fn next_color_index(existing: &[&Agent]) -> u8 {
    let max = existing.iter().map(|a| a.color_index).max().unwrap_or(0);
    if existing.is_empty() { 0 } else { max.wrapping_add(1) }
}
