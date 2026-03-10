use chrono::Utc;
use serde::Deserialize;

use crate::agent::AgentState;
use crate::state::try_with_state;

#[derive(Debug, Deserialize)]
struct HookEvent {
    hook_event_name: String,
    #[serde(default)]
    tool_name: Option<String>,
    #[serde(default)]
    tool_input: Option<serde_json::Value>,
}

/// Run the hook: read stdin JSON, update agent state.
/// Called as `fleet hook` subcommand.
///
/// Never fails — hooks must not block Claude Code.
/// Silently exits on any error or when FLEET_AGENT_ID is not set.
pub fn run() {
    let _ = run_inner();
}

fn run_inner() -> anyhow::Result<()> {
    // Always consume stdin to avoid broken pipe errors in Claude Code
    let mut input = String::new();
    std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)?;

    let agent_id = match std::env::var("FLEET_AGENT_ID") {
        Ok(id) => id,
        Err(_) => return Ok(()),
    };

    let event: HookEvent = serde_json::from_str(&input)?;

    try_with_state(|state| {
        let agent = match state.agents.get_mut(&agent_id) {
            Some(a) => a,
            None => return,
        };

        match event.hook_event_name.as_str() {
            "UserPromptSubmit" => {
                agent.state = AgentState::Working;
                agent.last_activity_at = Utc::now();
            }
            "Notification" => {
                agent.state = AgentState::Input;
            }
            "PreToolUse" => {
                agent.state = AgentState::Working;
                agent.last_tool = Some(format_tool(&event.tool_name, &event.tool_input));
                agent.last_activity_at = Utc::now();
            }
            "Stop" => {
                agent.state = AgentState::Done;
            }
            _ => {}
        }
    })?;

    Ok(())
}

fn format_tool(tool_name: &Option<String>, tool_input: &Option<serde_json::Value>) -> String {
    let name = match tool_name {
        Some(n) => n,
        None => return "Unknown".into(),
    };

    let input = tool_input.as_ref();

    match name.as_str() {
        "Edit" | "Write" | "Read" => {
            let path = input
                .and_then(|v| v.get("file_path"))
                .and_then(|v| v.as_str())
                .unwrap_or("?");
            format!("{name} {path}")
        }
        "Bash" => {
            let cmd = input
                .and_then(|v| v.get("command"))
                .and_then(|v| v.as_str())
                .unwrap_or("?");
            let truncated = if cmd.len() > 40 {
                format!("{}...", &cmd[..40])
            } else {
                cmd.to_string()
            };
            format!("Bash: {truncated}")
        }
        other => other.to_string(),
    }
}
