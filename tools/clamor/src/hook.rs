use chrono::Utc;
use serde::Deserialize;

use crate::agent::AgentState;
use crate::state::{try_with_state, with_state};

#[derive(Debug, Deserialize)]
struct HookEvent {
    hook_event_name: String,
    #[serde(default)]
    session_id: Option<String>,
    #[serde(default)]
    tool_name: Option<String>,
    #[serde(default)]
    tool_input: Option<serde_json::Value>,
}

/// Run the hook: read stdin JSON, update agent state.
/// Called as `clamor hook` subcommand.
///
/// Never fails — hooks must not block Claude Code.
/// Silently exits on any error or when CLAMOR_AGENT_ID is not set.
pub fn run() {
    let _ = run_inner();
}

fn run_inner() -> anyhow::Result<()> {
    // Always consume stdin to avoid broken pipe errors in Claude Code
    let mut input = String::new();
    std::io::Read::read_to_string(&mut std::io::stdin(), &mut input)?;

    let agent_id = match std::env::var("CLAMOR_AGENT_ID") {
        Ok(id) => id,
        Err(_) => return Ok(()),
    };

    let event: HookEvent = serde_json::from_str(&input)?;

    // Stop fires at process exit — use blocking lock so the Done transition
    // is never silently dropped. Other events use non-blocking to avoid
    // slowing down Claude Code mid-session.
    let is_stop = event.hook_event_name == "Stop";

    let update = |state: &mut crate::state::ClamorState| {
        let agent = match state.agents.get_mut(&agent_id) {
            Some(a) => a,
            None => return,
        };

        if let Some(ref sid) = event.session_id {
            if agent.session_id.as_ref() != Some(sid) {
                agent.session_id = Some(sid.clone());
            }
        }

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
            "PermissionRequest" => {
                agent.state = AgentState::Input;
                agent.last_tool = Some(format_tool(&event.tool_name, &event.tool_input));
            }
            "PostToolUse" => {
                agent.state = AgentState::Working;
                agent.last_activity_at = Utc::now();
            }
            "Stop" => {
                agent.state = AgentState::Done;
            }
            _ => {}
        }
    };

    if is_stop {
        with_state(update)?;
    } else {
        try_with_state(update)?;
    }

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
